"""Locale-configured prose punctuation, separate from runtime encoding rules."""
from .scripts import protected_tokens


def _visible_positions(text):
    """Visible text and original offsets, keeping engine-token edits explicit."""
    chars = list(text); positions = list(range(len(text)))
    for token in protected_tokens(text):
        start = ''.join(chars).find(token)
        if start >= 0:
            del chars[start:start+len(token)]
            del positions[start:start+len(token)]
    visible = ''.join(chars)
    first, end = len(visible)-len(visible.lstrip()), len(visible.rstrip())
    return visible[first:end], positions[first:end]


def _visible(text):
    return _visible_positions(text)[0]


def _has_clause_punctuation(text, policy):
    """Balanced enclosure delimiters are not clause punctuation; content is."""
    delimiters = {i for start, end, body in parenthetical_spans(text, policy) for i in (start, end)}
    return any(c in policy['internal_punctuation'] for i, c in enumerate(text) if i not in delimiters)


def _validate_sentence(visible, policy):
    period = policy["terminal_period"]
    for start, end, body in parenthetical_spans(visible, policy):
        if start == 0 and end == len(visible)-1:
            visible = body.strip()
            break
    if not visible:
        return
    has_period = visible.endswith(period)
    body = visible[:-len(period)] if has_period else visible
    if not has_period and visible[-1] in policy.get("alternative_endings", ""):
        return
    if has_period and not _has_clause_punctuation(body, policy):
        raise ValueError("System/description sentence without internal punctuation must omit the final period")
    if not has_period and _has_clause_punctuation(body, policy):
        raise ValueError("System/description sentence with internal punctuation must keep its final period")


def parenthetical_spans(text, policy):
    """Yield balanced enclosure interiors, including inline asides, not engine tags."""
    pairs = dict(policy.get("enclosure_pairs", [])); stack = []
    for i, char in enumerate(text):
        if char in pairs:
            stack.append((i, char))
        elif stack and char == pairs[stack[-1][1]]:
            start, left = stack.pop()
            yield start, i, text[start+len(left):i]


def _normalize_parenthetical_periods_once(text, policy):
    period = policy["terminal_period"]; changes = []
    for start, end, body in parenthetical_spans(text, policy):
        visible = _visible(body)
        if visible.endswith(period) and not _has_clause_punctuation(visible[:-len(period)], policy):
            position = end-len(period)
            if text[position:end] == period:changes.append(position)
    visible, positions = _visible_positions(text)
    if visible.endswith(period):
        body = visible[:-len(period)]
        if (any(start == 0 and end == len(body)-1 for start, end, inner in parenthetical_spans(body, policy))
                and not _has_clause_punctuation(body, policy)):
            changes.extend(positions[-len(period):])
    for position in sorted(changes, reverse=True):
        text = text[:position]+text[position+len(period):]
    return text


def normalize_parenthetical_periods(text, policy):
    """Explicit editor helper; nested asides settle before validating a build."""
    while True:
        changed = _normalize_parenthetical_periods_once(text, policy)
        if changed == text:
            return text
        text = changed


def normalize_conditional_periods(text, text_type, policy):
    """Explicit data-editor helper, never called to rewrite a build's inputs."""
    if policy.get('conditional_parentheticals'):
        text = normalize_parenthetical_periods(text, policy)
    visible, positions = _visible_positions(text)
    period = policy['terminal_period']
    if (text_type in policy.get('conditional_period_types', []) and visible.endswith(period)
            and not _has_clause_punctuation(visible[:-len(period)], policy)):
        for position in reversed(positions[-len(period):]):
            text = text[:position]+text[position+1:]
    return text


def validate_text(text: str, text_type: str, policy: dict) -> None:
    """Apply an explicit locale rule to complete system/description sentences.

    Menu labels are not sentences. Dialogue and cutscenes use normal prose.
    Engine tags/printf placeholders are not natural-language punctuation.
    Question marks/exclamation marks retain their intended sentence endings.
    """
    for line in text.replace('<BR>', '\n').splitlines()[1:]:
        visible = _visible(line)
        if visible and visible[0] in policy.get('no_line_start', ''):
            raise ValueError('Explicit line break leaves punctuation at line start')
    if policy.get("conditional_parentheticals") and normalize_parenthetical_periods(text, policy) != text:
        raise ValueError("Parenthetical single sentence must omit the final period")
    if text_type in policy.get("conditional_period_types", []):
        _validate_sentence(_visible(text), policy)
