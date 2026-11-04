"""Guarded fixed-slot edits to an explicitly reviewed ELF string catalogue.

This module deliberately does not discover strings heuristically during a build.
Each edit must carry its original text, offset and capacity from a reviewed
version-specific recipe. Instruction bytes and ELF layout are never rewritten.
"""

from __future__ import annotations

from collections import Counter
import re
from typing import Callable, Mapping, Sequence


PRINTF = re.compile(
    r"%%|%(?:\d+\$)?[-+ #0]*(?:\d+|\*)?(?:\.(?:\d+|\*))?"
    r"(?:hh|ll|[hljztL])?[diuoxXfFeEgGaAcspn]"
)
# Only renderer commands, not arbitrary bracketed natural-language messages.
TAGS = re.compile(r"<(?:BR|O|X|T|S|L[123]|R[123]|START|SELECT)>")


def validate_tokens(source: str, target: str) -> None:
    """Preserve ordered printf arguments and non-linebreak renderer commands."""
    if PRINTF.findall(source) != PRINTF.findall(target):
        raise ValueError("printf placeholder sequence changed")
    def controls(text: str) -> Counter:
        return Counter(t for t in TAGS.findall(text) if t != "<BR>")
    if controls(source) != controls(target):
        raise ValueError("renderer control tokens changed")
    if "\0" in target:
        raise ValueError("translation contains an embedded NUL")


def patch_strings(data: bytes, entries: Sequence[Mapping], encode: Callable[[str], bytes]) -> bytes:
    """Patch only nominated, non-empty translations; validate before mutation."""
    if not data.startswith(b"\x7fELF\x01\x01"):
        raise ValueError("expected a little-endian ELF32 image")
    plans = []
    ids = set()
    for entry in entries:
        if entry["id"] in ids:
            raise ValueError(f"duplicate ID: {entry['id']}")
        ids.add(entry["id"])
        offset, capacity = entry["offset"], entry["capacity"]
        if not isinstance(offset, int) or not isinstance(capacity, int) or offset < 0 or capacity < 1:
            raise ValueError("invalid string range")
        expected = entry["source"].encode("cp949") + b"\0"
        if len(expected) != capacity or offset + capacity > len(data):
            raise ValueError(f"invalid capacity: {entry['id']}")
        if data[offset:offset + capacity] != expected:
            raise ValueError(f"original bytes mismatch: {entry['id']}")
        target = entry.get("target", "")
        if not target:
            continue
        validate_tokens(entry["source"], target)
        replacement = encode(target) + b"\0"
        if len(replacement) > capacity:
            raise ValueError(f"fixed-slot overflow: {entry['id']}: {len(replacement)} > {capacity}")
        plans.append((offset, capacity, replacement.ljust(capacity, b"\0")))
    plans.sort()
    for left, right in zip(plans, plans[1:]):
        if left[0] + left[1] > right[0]:
            raise ValueError("overlapping string edits")
    out = bytearray(data)
    for offset, capacity, replacement in plans:
        out[offset:offset + capacity] = replacement
    assert len(out) == len(data)
    return bytes(out)
