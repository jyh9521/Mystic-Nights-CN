"""Locale-configured prose punctuation, separate from runtime encoding rules."""
from .scripts import protected_tokens


def validate_text(text: str, text_type: str, policy: dict) -> None:
    """Apply an explicit locale rule to complete system/description sentences.

    Menu labels are not sentences. Dialogue and cutscenes use normal prose.
    Engine tags/printf placeholders are not natural-language punctuation.
    Question marks/exclamation marks retain their intended sentence endings.
    """
    if text_type not in policy.get("conditional_period_types", []):
        return
    period = policy["terminal_period"]
    punctuation = set(policy["internal_punctuation"])
    visible = text
    for token in protected_tokens(text):
        visible = visible.replace(token, "", 1)
    visible = visible.strip()
    if not visible:
        return
    has_period = visible.endswith(period)
    body = visible[:-len(period)] if has_period else visible
    # A different terminal mark is not an internal punctuation mark.
    if not has_period and visible[-1] in policy.get("alternative_endings", ""):
        return
    internal = any(char in punctuation for char in body)
    if has_period and not internal:
        raise ValueError("System/description sentence without internal punctuation must omit the final period")
    if not has_period and internal:
        raise ValueError("System/description sentence with internal punctuation must keep its final period")
