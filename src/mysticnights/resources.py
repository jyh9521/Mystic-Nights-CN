"""Strict, lossless reader and equal-size editor for Mystic Nights RES 1.30.

The on-disc format has eight consecutive member groups.  A member contains a
32-byte name, a little-endian u32 payload length, then unaligned payload bytes.
Unknown group semantics and all bytes outside an explicitly replaced payload
are preserved.  This module does not execute scripts or decode game assets.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Mapping


MAGIC = b"1.30\0\0\0\0Buil"
GROUP_COUNT = 8


class ResourceError(ValueError):
    """Malformed resource or unsupported replacement."""


@dataclass(frozen=True)
class ResEntry:
    group: int
    index: int
    name: str
    header_offset: int
    offset: int
    size: int

    @property
    def end(self) -> int:
        return self.offset + self.size

    @property
    def key(self) -> tuple[int, int]:
        return self.group, self.index


@dataclass(frozen=True)
class ResArchive:
    data: bytes
    entries: tuple[ResEntry, ...]
    group_counts: tuple[int, ...]

    def get(self, name: str) -> ResEntry:
        matches = [entry for entry in self.entries if entry.name == name]
        if len(matches) != 1:
            raise ResourceError(f"Expected one member {name!r}; found {len(matches)}")
        return matches[0]

    def read(self, member: str | ResEntry) -> bytes:
        entry = self.get(member) if isinstance(member, str) else member
        if entry not in self.entries:
            raise ResourceError("Member does not belong to this archive")
        return self.data[entry.offset : entry.end]

    def replace(self, replacements: Mapping[str | tuple[int, int], bytes]) -> bytes:
        """Replace named/keyed payloads; changing a payload length is rejected.

        Tuple keys select (group, index), including archives with duplicate names.
        A named member and its tuple key may not both be supplied.
        """
        planned: list[tuple[ResEntry, bytes]] = []
        selected: set[tuple[int, int]] = set()
        for key, payload in replacements.items():
            if isinstance(key, str):
                entry = self.get(key)
            else:
                matches = [e for e in self.entries if e.key == key]
                if len(matches) != 1:
                    raise ResourceError(f"Unknown member key: {key!r}")
                entry = matches[0]
            if entry.key in selected:
                raise ResourceError(f"Duplicate replacement: {entry.name}")
            if not isinstance(payload, bytes):
                raise ResourceError(f"Replacement must be bytes: {entry.name}")
            if len(payload) != entry.size:
                raise ResourceError(
                    f"Equal-size replacement required for {entry.name}: "
                    f"expected {entry.size}, got {len(payload)}"
                )
            selected.add(entry.key)
            planned.append((entry, payload))
        output = bytearray(self.data)
        for entry, payload in planned:
            output[entry.offset : entry.end] = payload
        result = bytes(output)
        reparsed = parse_res(result)
        if reparsed.entries != self.entries:
            raise ResourceError("Replacement changed archive structure")
        return result


def parse_res(data: bytes) -> ResArchive:
    """Validate the complete RES 1.30 container and return byte-addressed members."""
    if not isinstance(data, bytes):
        data = bytes(data)
    if data[: len(MAGIC)] != MAGIC:
        raise ResourceError("Unsupported RES header (expected 1.30/Buil)")
    position = len(MAGIC)
    entries: list[ResEntry] = []
    counts: list[int] = []
    for group in range(GROUP_COUNT):
        if position + 4 > len(data):
            raise ResourceError(f"Truncated group count at {position:#x}")
        count = struct.unpack_from("<I", data, position)[0]
        position += 4
        if count > (len(data) - position) // 36:
            raise ResourceError(f"Impossible member count in group {group}: {count}")
        counts.append(count)
        for index in range(count):
            if position + 36 > len(data):
                raise ResourceError(f"Truncated member header at {position:#x}")
            name_field = data[position : position + 32]
            raw_name = name_field.split(b"\0", 1)[0]
            if not raw_name:
                raise ResourceError(f"Empty member name at {position:#x}")
            try:
                name = raw_name.decode("cp949")
            except UnicodeDecodeError as exc:
                raise ResourceError(f"Invalid member name at {position:#x}") from exc
            if any(ord(char) < 32 for char in name):
                raise ResourceError(f"Control byte in member name at {position:#x}")
            size = struct.unpack_from("<I", data, position + 32)[0]
            payload_offset = position + 36
            if size > len(data) - payload_offset:
                raise ResourceError(f"Out-of-bounds member {name!r} at {position:#x}")
            entries.append(ResEntry(group, index, name, position, payload_offset, size))
            position = payload_offset + size
    if position != len(data):
        raise ResourceError(f"Unexpected trailing bytes: {len(data) - position}")
    return ResArchive(data, tuple(entries), tuple(counts))
