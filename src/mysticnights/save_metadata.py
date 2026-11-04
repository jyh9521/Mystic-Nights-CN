"""Source-bound PS2 memory-card browser metadata, separate from game fonts.

The audited resource is the network configuration's icon.sys template.  Its
title is Shift-JIS, not the game's CP949/FNT alias encoding.  The game save's
ASCII-to-SJIS call chain is deliberately not a supported patch target.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .iso9660 import sha256_file


ICON_SYS_SIZE = 0x3C4
TITLE_OFFSET = 0xC0
TITLE_CAPACITY = 0x44
TITLE_ID = "CNF/ICON_EN.SYS@000000c0"
RESOURCE = "CNF/ICON_EN.SYS"
_FILENAMES = (0x104, 0x144, 0x184)


@dataclass(frozen=True)
class IconSys:
    type: int
    nl_offset: int
    title: str
    title_bytes: bytes
    title_lines: tuple[str, str]
    filenames: tuple[str, str, str]


def _terminated_field(field: bytes, encoding: str, name: str) -> tuple[str, bytes]:
    terminator = field.find(b"\0")
    if terminator < 0 or any(field[terminator:]):
        raise ValueError(f"Invalid NUL termination/padding in icon.sys {name}")
    raw = field[:terminator]
    try:
        text = raw.decode(encoding, errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Invalid {encoding} icon.sys {name}") from exc
    if not text or not all(c.isprintable() or c == "\u3000" for c in text):
        raise ValueError(f"Invalid printable icon.sys {name}")
    return text, raw


def parse_icon_sys(data: bytes) -> IconSys:
    """Parse the verified 964-byte PS2D layout without changing any bytes.

    nlOffset is a BYTE offset into the SJIS title, not a character count.
    A value equal to its encoded length means an empty second title line.
    Both halves are decoded independently to reject a split multibyte glyph.
    """
    if len(data) != ICON_SYS_SIZE or data[:4] != b"PS2D":
        raise ValueError("Unsupported icon.sys size or magic")
    title, raw = _terminated_field(data[TITLE_OFFSET:TITLE_OFFSET + TITLE_CAPACITY],
                                   "cp932", "title")
    nl_offset = int.from_bytes(data[6:8], "little")
    if nl_offset > len(raw):
        raise ValueError("icon.sys newline offset exceeds title")
    try:
        lines = (raw[:nl_offset].decode("cp932"), raw[nl_offset:].decode("cp932"))
    except UnicodeDecodeError as exc:
        raise ValueError("icon.sys newline offset splits a Shift-JIS character") from exc
    filenames = tuple(_terminated_field(data[o:o + 64], "ascii", "filename")[0]
                      for o in _FILENAMES)
    if any("/" in name or "\\" in name or name in {".", ".."} for name in filenames):
        raise ValueError("Invalid icon.sys filename")
    return IconSys(int.from_bytes(data[4:6], "little"), nl_offset, title, raw, lines, filenames)


def patch_icon_sys(data: bytes, definition: dict, translation: dict) -> bytes:
    """Return one equal-sized, source-hash-checked network title replacement.

    Only u16 nlOffset at 0x06 and the 68-byte title at 0xC0 may change.
    File names, transparency, colors, lights and all reserved bytes remain
    identical.  All validation happens before the output bytearray is made.
    """
    if definition.get("resource") != RESOURCE or definition.get("format") != "ps2-icon-sys":
        raise ValueError("Unsupported save metadata resource/format")
    if definition.get("size") != ICON_SYS_SIZE or hashlib.sha256(data).hexdigest() != definition.get("sha256"):
        raise ValueError("Save metadata source size/hash mismatch")
    parsed = parse_icon_sys(data)
    slot = definition["title"]
    if (slot.get("id") != TITLE_ID or slot.get("offset") != TITLE_OFFSET
            or slot.get("capacity") != TITLE_CAPACITY or slot.get("source") != parsed.title
            or hashlib.sha256(data[TITLE_OFFSET:TITLE_OFFSET + TITLE_CAPACITY]).hexdigest()
            != slot.get("source_sha256")):
        raise ValueError("Save metadata original title field mismatch")
    if (definition.get("expected_type") != parsed.type
            or definition.get("expected_nl_offset") != parsed.nl_offset
            or definition.get("expected_icon_filenames") != list(parsed.filenames)):
        raise ValueError("Save metadata original structure mismatch")
    if (translation.get("id") != TITLE_ID or translation.get("source") != parsed.title
            or translation.get("source_sha256") != slot["source_sha256"]
            or translation.get("encoding") != "cp932"
            or translation.get("status") not in {"draft", "reviewed"}):
        raise ValueError("Save metadata translation source/status mismatch")
    target = translation.get("target")
    if (not isinstance(target, str) or not target.strip()
            or not all(c.isprintable() or c == "\u3000" for c in target)):
        raise ValueError("Save metadata target must be nonempty printable text")
    try:
        encoded = target.encode("cp932", errors="strict")
    except UnicodeEncodeError as exc:
        raise ValueError("Save metadata target is not encodable in the firmware font") from exc
    # CP932 has Unicode aliases. Require an exact round-trip so validation
    # cannot claim one title while firmware's byte decoder selects another.
    if encoded.decode("cp932") != target:
        raise ValueError("Save metadata target has an ambiguous CP932 round-trip")
    if len(encoded) >= TITLE_CAPACITY:
        raise ValueError("Save metadata title exceeds its NUL-terminated field")
    split = translation.get("line_break_after")
    if type(split) is not int or not 0 <= split <= len(target):
        raise ValueError("Save metadata line_break_after must be a character boundary")
    nl_offset = len(target[:split].encode("cp932"))
    output = bytearray(data)
    output[6:8] = nl_offset.to_bytes(2, "little")
    output[TITLE_OFFSET:TITLE_OFFSET + TITLE_CAPACITY] = encoded.ljust(TITLE_CAPACITY, b"\0")
    result = bytes(output)
    checked = parse_icon_sys(result)
    if (checked.title != target or checked.nl_offset != nl_offset
            or checked.filenames != parsed.filenames or len(result) != len(data)
            or result[:6] != data[:6] or result[8:TITLE_OFFSET] != data[8:TITLE_OFFSET]
            or result[TITLE_OFFSET + TITLE_CAPACITY:] != data[TITLE_OFFSET + TITLE_CAPACITY:]):
        raise AssertionError("Save metadata readback/isolation failure")
    return result


def build_save_metadata(image, recipe: dict, catalogue: dict) -> dict[str, bytes]:
    """Verify the original disc binding and prepare the sole audited resource.

    The caller remains responsible for writing a new ISO copy.  This function
    reads but never writes the supplied image; it also accepts synthetic image
    objects with ``path`` and ``read`` in tests.
    """
    if recipe.get("format") != "save-metadata-slots" or recipe.get("version") != 1:
        raise ValueError("Unsupported save metadata recipe")
    if (catalogue.get("format") != "save-metadata-catalogue" or catalogue.get("version") != 1
            or not isinstance(catalogue.get("locale"), str) or not catalogue["locale"]):
        raise ValueError("Unsupported save metadata catalogue")
    expected = recipe.get("original_iso_sha256")
    if (not isinstance(expected, str) or len(expected) != 64
            or catalogue.get("original_iso_sha256") != expected
            or sha256_file(image.path) != expected):
        raise ValueError("Save metadata original ISO hash mismatch")
    sources, entries = recipe.get("sources", []), catalogue.get("entries", [])
    if (len(sources) != 1 or len(entries) != 1
            or sources[0].get("resource") != RESOURCE or entries[0].get("id") != TITLE_ID):
        raise ValueError("Save metadata requires exactly the audited network title")
    return {RESOURCE: patch_icon_sys(image.read(RESOURCE), sources[0], entries[0])}
