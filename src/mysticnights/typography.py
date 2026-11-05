"""Locale-configured prose punctuation, separate from runtime encoding rules."""
from .scripts import protected_tokens


def _visible(text):
    for token in protected_tokens(text):
        text = text.replace(token, "", 1)
    return text.strip()


def _validate_sentence(visible, policy):
    period = policy["terminal_period"]
    punctuation = set(policy["internal_punctuation"])
    for left, right in policy.get("enclosure_pairs", []):
        if visible.startswith(left) and visible.endswith(right):
            visible = visible[len(left):-len(right)].strip()
            break
    if not visible:
        return
    has_period = visible.endswith(period)
    body = visible[:-len(period)] if has_period else visible
    if not has_period and visible[-1] in policy.get("alternative_endings", ""):
        return
    if has_period and not any(char in punctuation for char in body):
        raise ValueError("System/description sentence without internal punctuation must omit the final period")
    if not has_period and any(char in punctuation for char in body):
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


def normalize_parenthetical_periods(text, policy):
    """Explicit editor helper; the build validates and never silently rewrites."""
    period = policy["terminal_period"]; changes = []
    for start, end, body in parenthetical_spans(text, policy):
        visible = _visible(body)
        if (visible.endswith(period) and not any(c in policy["internal_punctuation"]
                                                for c in visible[:-len(period)])):
            position = end-len(period)
            if text[position:end] == period:changes.append(position)
    for position in sorted(changes, reverse=True):
        text = text[:position]+text[position+len(period):]
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
