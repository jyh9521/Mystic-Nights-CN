"""Byte-exact SCR quoted-field extraction and guarded fixed-slot reinsertion.

Only natural-language commands are editable by default.  Names used by item,
document and scene lookup are separately classified and require an explicit
linked-identifier workflow; object names, passwords and script arguments are
never silently treated as translated prose.  IDs are source-member offsets,
which remain stable under this equal-size editing strategy.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Callable, Iterable, Mapping


class ScriptError(ValueError):
    """Malformed script or unsafe text replacement."""


DISPLAY_COMMANDS = frozenset(
    {"TEXT", "MESSAGE", "GAME_OVER", "DESCRIPTION", "USE_MESSAGE",
     "NOT_USE_MESSAGE1", "NOT_USE_MESSAGE2"}
)
ITEM_REFERENCE_COMMANDS = frozenset({"ITEM_LIST", "DOCUMENT", "MAP_ITEM"})
_QUOTED = re.compile(rb'"([^"\r\n]*)"')
_COMMAND = re.compile(rb"[A-Z_][A-Z_0-9]*")
_TOKEN = re.compile(
    r"<[^<>\r\n]+>|%%|(?<!\d)%(?:\d+\$)?[-+ #0]*(?:\d+|\*)?(?:\.(?:\d+|\*))?"
    r"(?:hh|ll|[hljztL])?[diuoxXfFeEgGaAcspn]|\{\d+(?::[^{}]+)?\}"
    r"|\\[nrt]|\$n"
)


def protected_tokens(text: str) -> tuple[str, ...]:
    """Return ordered markup/format/control tokens, ignoring ordinary percentages."""
    return tuple(_TOKEN.findall(text))


def validate_script_tokens(source: str, target: str, literal_translations=()) -> None:
    """Allow individually reviewed literal headings, never renderer commands.

    Callers bind these exceptions to a source ID/hash in a versioned recipe.
    Unknown angle-bracket text stays protected unless explicitly nominated.
    """
    from .executable import TAGS, validate_tokens
    try:
        validate_tokens(source, target)
    except ValueError as exc:
        raise ScriptError(f"Protected token mismatch: {exc}") from exc
    replacements = {}
    before, after = protected_tokens(source), protected_tokens(target)
    for pair in literal_translations:
        if not isinstance(pair, dict) or set(pair) != {"source", "target"}:
            raise ScriptError("Malformed literal-token translation")
        a, b = pair["source"], pair["target"]
        if (not isinstance(a, str) or not isinstance(b, str) or a in replacements
                or a not in before or b not in after
                or re.fullmatch(r"<[^<>\r\n]+>", a) is None
                or re.fullmatch(r"<[^<>\r\n]+>", b) is None
                or TAGS.fullmatch(a) or TAGS.fullmatch(b)):
            raise ScriptError("Invalid or protected literal-token translation")
        replacements[a] = b
    if tuple(replacements.get(token, token) for token in before) != after:
        raise ScriptError("Protected token mismatch")


@dataclass(frozen=True)
class ScriptString:
    id: str
    member: str
    command: str
    line: int
    quote_index: int
    offset: int
    capacity: int
    source: str
    source_bytes: bytes
    role: str
    context: str
    tokens: tuple[str, ...]

    @property
    def source_sha256(self) -> str:
        return hashlib.sha256(self.source_bytes).hexdigest()

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "member": self.member,
            "command": self.command,
            "line": self.line,
            "quote_index": self.quote_index,
            "offset": self.offset,
            "capacity": self.capacity,
            "source_ko": self.source,
            "source_sha256": self.source_sha256,
            "role": self.role,
            "context": self.context,
            "protected_tokens": list(self.tokens),
        }


def _active_line(line: bytes) -> bytes:
    """Strip a semicolon comment only outside quoted strings."""
    quoted = False
    for index, byte in enumerate(line):
        if byte == 34:
            quoted = not quoted
        elif byte == 59 and not quoted:
            return line[:index]
    return line


def extract_strings(data: bytes, member_name: str = "SCRIPT.SCR") -> list[ScriptString]:
    if not data.startswith(b"SCR_TYPE "):
        raise ScriptError(f"Missing SCR_TYPE header: {member_name}")
    header_fields = data.splitlines()[0].split()
    if len(header_fields) != 2 or re.fullmatch(rb"[A-Z_0-9]+", header_fields[1]) is None:
        raise ScriptError(f"Malformed SCR_TYPE header: {member_name}")
    member_type = header_fields[1]
    records: list[ScriptString] = []
    position = 0
    context = "global"
    block_count = 0
    for line_number, raw_line in enumerate(data.splitlines(keepends=True), 1):
        line = _active_line(raw_line)
        stripped = line.lstrip(b" \t\r\n")
        command_match = _COMMAND.match(stripped)
        if command_match is None:
            position += len(raw_line)
            continue
        command = command_match.group().decode("ascii")
        if re.match(rb"(?:EVENT|ITEM|VAMPIRE)\s*\{", stripped):
            block_count += 1
            context = f"block:{block_count:04d}"
        identity = re.match(rb"(EVENT_ID|ID|TYPE)\s+(\d+)(?:\s|$)", stripped)
        if identity is not None:
            context = f"{identity[1].decode('ascii').lower()}:{identity[2].decode('ascii')}"
        if line.count(b'"') % 2:
            raise ScriptError(f"Unbalanced quote in {member_name}:{line_number}")
        for quote_index, match in enumerate(_QUOTED.finditer(line)):
            raw_text = match.group(1)
            # Upstream uses embedded NUL padding inside fixed-width quoted slots.
            visible = raw_text.split(b"\0", 1)[0]
            if b"\0" in raw_text and raw_text[len(visible):].strip(b"\0 "):
                raise ScriptError(f"Non-padding bytes after NUL in {member_name}:{line_number}")
            try:
                source = visible.decode("cp949")
            except UnicodeDecodeError as exc:
                raise ScriptError(f"Invalid CP949 in {member_name}:{line_number}") from exc
            if command in DISPLAY_COMMANDS:
                role = "display"
            elif command == "NAME" and member_type in {b"ITEM", b"DOC"}:
                role = "display_identifier"
            elif command in ITEM_REFERENCE_COMMANDS or (
                command == "ITEM" and member_type == b"VAMPIRE"
            ):
                role = "item_reference"
            elif command == "PASSWORD":
                role = "protected"
            else:
                role = "identifier"
            offset = position + match.start(1)
            records.append(
                ScriptString(
                    f"{member_name}@{offset:08x}", member_name, command,
                    line_number, quote_index, offset, len(raw_text), source,
                    raw_text, role, context, protected_tokens(source),
                )
            )
        position += len(raw_line)
    return records


def patch_strings(
    data: bytes,
    records: Iterable[ScriptString],
    replacements: Mapping[str, str],
    encode: Callable[[str], bytes] | None = None,
    *,
    allowed_roles: Iterable[str] = ("display",),
    padding: bytes = b"\0",
    literal_translations: Mapping[str, list] | None = None,
) -> bytes:
    """Validate all edits before returning an equal-length modified script.

    `encode` supplies the locale's renderer-aware encoding; the default is
    CP949 for source round trips.  A caller must explicitly opt in to editing
    linked identifiers after collecting every reference.  Syntax bytes and
    ordered control tokens may not be introduced, removed or reordered.
    """
    if encode is None:
        encode = lambda text: text.encode("cp949")
    if padding not in (b"\0", b" "):
        raise ScriptError("Padding must be a single NUL or ASCII space")
    record_list = list(records)
    by_id = {record.id: record for record in record_list}
    if len(by_id) != len(record_list):
        raise ScriptError("Duplicate source IDs")
    unknown = set(replacements) - set(by_id)
    if unknown:
        raise ScriptError(f"Unknown replacement IDs: {sorted(unknown)}")
    literal_translations = literal_translations or {}
    if set(literal_translations) - set(replacements):
        raise ScriptError("Literal exception without a selected translation")
    roles = set(allowed_roles)
    planned: list[tuple[ScriptString, bytes]] = []
    for identifier, target in replacements.items():
        record = by_id[identifier]
        if record.role not in roles:
            raise ScriptError(f"Protected role {record.role}: {identifier}")
        if not isinstance(target, str):
            raise ScriptError(f"Target is not text: {identifier}")
        if any(char in target for char in ('"', "\r", "\n", "\0")):
            raise ScriptError(f"Target contains script delimiter/control bytes: {identifier}")
        if record.source and not target:
            raise ScriptError(f"Unexpected empty target: {identifier}")
        try:
            validate_script_tokens(record.source, target, literal_translations.get(identifier, ()))
        except ScriptError as exc:
            raise ScriptError(f"{exc}: {identifier}") from exc
        start, end = record.offset, record.offset + record.capacity
        if start < 1 or end >= len(data) or data[start - 1 : start] != b'"' or data[end : end + 1] != b'"':
            raise ScriptError(f"Source field bounds/delimiters changed: {identifier}")
        if data[start:end] != record.source_bytes:
            raise ScriptError(f"Source bytes changed: {identifier}")
        if target == record.source:
            planned.append((record, record.source_bytes))
            continue
        try:
            encoded = encode(target)
        except (UnicodeError, ValueError) as exc:
            raise ScriptError(f"Target encoding failed: {identifier}: {exc}") from exc
        if not isinstance(encoded, bytes):
            raise ScriptError(f"Encoder did not return bytes: {identifier}")
        if any(byte in encoded for byte in (0, 10, 13, 34)):
            raise ScriptError(f"Encoder emitted a script delimiter/control byte: {identifier}")
        if len(encoded) > record.capacity:
            raise ScriptError(
                f"Fixed slot overflow {identifier}: {len(encoded)} > {record.capacity} bytes"
            )
        planned.append((record, encoded + padding * (record.capacity - len(encoded))))
    planned.sort(key=lambda item: item[0].offset)
    for (previous, _), (following, _) in zip(planned, planned[1:]):
        if previous.offset + previous.capacity > following.offset:
            raise ScriptError("Overlapping replacement fields")
    output = bytearray(data)
    for record, encoded in planned:
        output[record.offset : record.offset + record.capacity] = encoded
    if len(output) != len(data):
        raise ScriptError("Unexpected script size change")
    return bytes(output)
