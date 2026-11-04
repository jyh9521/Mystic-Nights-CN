"""Strict, read-only ISO9660 inventory and same-length copy patching.

This module deliberately does not rebuild the filesystem.  File replacements
keep every directory record, extent, timestamp, and sector address unchanged.
Only the primary ISO9660 namespace, one volume, and non-interleaved,
single-extent records are supported.  Unsupported structures fail explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
from typing import BinaryIO, Mapping


SECTOR_SIZE = 2048
_COPY_CHUNK = 1024 * 1024


class IsoError(ValueError):
    """An invalid or unsupported ISO9660 structure."""


@dataclass(frozen=True)
class IsoEntry:
    path: str
    lba: int
    size: int
    record_offset: int
    is_directory: bool = False

    @property
    def offset(self) -> int:
        return self.lba * SECTOR_SIZE


def _dual(data: bytes, offset: int, width: int, label: str) -> int:
    if offset < 0 or offset + width * 2 > len(data):
        raise IsoError(f"Truncated {label}")
    low = int.from_bytes(data[offset:offset + width], "little")
    high = int.from_bytes(data[offset + width:offset + width * 2], "big")
    if low != high:
        raise IsoError(f"Endian copies disagree for {label}: {low} != {high}")
    return low


def _read_at(stream: BinaryIO, offset: int, length: int) -> bytes:
    stream.seek(offset)
    result = stream.read(length)
    if len(result) != length:
        raise IsoError(f"Truncated image at byte {offset}: expected {length} bytes")
    return result


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(_COPY_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _name(raw: bytes) -> str:
    try:
        value = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise IsoError("Non-ASCII primary ISO9660 identifier") from exc
    if any(c in value for c in "\\/\x00") or value in {"", ".", ".."}:
        raise IsoError(f"Invalid ISO9660 identifier {value!r}")
    if ";" in value:
        base, separator, version = value.partition(";")
        if not separator or not base or not version.isdecimal() or not 1 <= int(version) <= 32767:
            raise IsoError(f"Invalid ISO9660 version suffix {value!r}")
        value = base
    return value


class IsoImage:
    """Inventory primary-namespace files without extracting the whole disc.

    ``files`` keys omit the leading slash and ISO version suffix, e.g.
    ``RES/SYSTEM.RES``.  ``directories`` includes the root under ``""``.
    The image file is not kept open after inventory creation.
    """

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)
        self.size = self.path.stat().st_size
        self.files: dict[str, IsoEntry] = {}
        self.directories: dict[str, IsoEntry] = {}
        self.volume_id = ""
        self.volume_size = 0
        self._metadata_ranges: list[tuple[int, int]] = []
        if self.size < 18 * SECTOR_SIZE or self.size % SECTOR_SIZE:
            raise IsoError("Image size is not a complete 2048-byte-sector ISO9660 image")
        with self.path.open("rb") as stream:
            primary = None
            primary_sector = None
            terminator_seen = False
            for sector in range(16, min(self.size // SECTOR_SIZE, 272)):
                descriptor = _read_at(stream, sector * SECTOR_SIZE, SECTOR_SIZE)
                if descriptor[1:6] != b"CD001" or descriptor[6] != 1:
                    raise IsoError(f"Invalid volume descriptor at sector {sector}")
                kind = descriptor[0]
                if kind == 1:
                    if primary is not None:
                        raise IsoError("Multiple primary volume descriptors")
                    primary = descriptor
                    primary_sector = sector
                elif kind == 255:
                    terminator_seen = True
                    self._metadata_ranges.append((0, (sector + 1) * SECTOR_SIZE))
                    break
                elif kind not in (0, 2, 3):
                    raise IsoError(f"Unsupported volume descriptor type {kind}")
            if primary is None or not terminator_seen:
                raise IsoError("Missing primary volume descriptor or terminator")
            if _dual(primary, 128, 2, "logical block size") != SECTOR_SIZE:
                raise IsoError("Only 2048-byte logical blocks are supported")
            if _dual(primary, 120, 2, "volume set size") != 1:
                raise IsoError("Multi-volume images are not supported")
            if _dual(primary, 124, 2, "volume sequence number") != 1:
                raise IsoError("Unexpected volume sequence number")
            self.volume_size = _dual(primary, 80, 4, "volume space size") * SECTOR_SIZE
            if not 18 * SECTOR_SIZE <= self.volume_size <= self.size:
                raise IsoError("Declared volume lies outside the image")
            try:
                self.volume_id = primary[40:72].decode("ascii").rstrip(" \x00")
            except UnicodeDecodeError as exc:
                raise IsoError("Non-ASCII volume identifier") from exc
            table_size = _dual(primary, 132, 4, "path table size")
            for offset, order in ((140, "little"), (144, "little"), (148, "big"), (152, "big")):
                lba = int.from_bytes(primary[offset:offset + 4], order)
                if lba:
                    start = lba * SECTOR_SIZE
                    if start < 16 * SECTOR_SIZE or start + table_size > self.volume_size:
                        raise IsoError("Path table lies outside the volume")
                    self._metadata_ranges.append((start, start + table_size))
            root_length = primary[156]
            root, name, _flags = self._record(primary[156:156 + root_length], "", primary_sector * SECTOR_SIZE + 156)
            if name != b"\x00" or not root.is_directory:
                raise IsoError("Invalid root directory record")
            pending = [(root, root)]
            visited: set[tuple[int, int]] = set()
            all_paths: set[str] = set()
            while pending:
                directory, parent = pending.pop()
                identity = (directory.lba, directory.size)
                if identity in visited:
                    raise IsoError("Directory cycle or reused directory extent")
                visited.add(identity)
                if len(visited) > 100_000:
                    raise IsoError("Directory count exceeds supported limit")
                if any(directory.offset < end and directory.offset + directory.size > start for start, end in self._metadata_ranges):
                    raise IsoError("Directory extent overlaps filesystem metadata")
                self.directories[directory.path] = directory
                self._metadata_ranges.append((directory.offset, directory.offset + directory.size))
                data = _read_at(stream, directory.offset, directory.size)
                cursor = 0
                specials: set[bytes] = set()
                while cursor < len(data):
                    length = data[cursor]
                    if length == 0:
                        end = min(len(data), (cursor // SECTOR_SIZE + 1) * SECTOR_SIZE)
                        if any(data[cursor:end]):
                            raise IsoError("Nonzero data after directory-sector padding marker")
                        cursor = end
                        continue
                    if cursor + length > len(data) or cursor % SECTOR_SIZE + length > SECTOR_SIZE:
                        raise IsoError("Directory record crosses a sector or directory boundary")
                    entry, raw_name, _flags = self._record(
                        data[cursor:cursor + length], directory.path, directory.offset + cursor
                    )
                    cursor += length
                    if raw_name in (b"\x00", b"\x01"):
                        expected = directory if raw_name == b"\x00" else parent
                        if raw_name in specials or not entry.is_directory or (entry.lba, entry.size) != (expected.lba, expected.size):
                            raise IsoError("Invalid current/parent directory record")
                        specials.add(raw_name)
                        continue
                    if entry.path in all_paths:
                        raise IsoError(f"Duplicate ISO9660 path: {entry.path}")
                    all_paths.add(entry.path)
                    if entry.is_directory:
                        pending.append((entry, directory))
                    else:
                        self.files[entry.path] = entry
                if specials != {b"\x00", b"\x01"}:
                    raise IsoError("Directory lacks current/parent records")
        for entry in self.files.values():
            if entry.size and any(entry.offset < end and entry.offset + entry.size > start for start, end in self._metadata_ranges):
                raise IsoError(f"File overlaps filesystem metadata: {entry.path}")

    def _record(self, data: bytes, parent: str, record_offset: int) -> tuple[IsoEntry, bytes, int]:
        if len(data) < 34 or data[0] != len(data):
            raise IsoError("Truncated or inconsistent directory record")
        if data[1] or data[26] or data[27]:
            raise IsoError("Extended attributes and interleaved files are unsupported")
        flags = data[25]
        if flags & 0x80:
            raise IsoError("Multi-extent files are unsupported")
        if _dual(data, 28, 2, "directory volume sequence") != 1:
            raise IsoError("Directory references a different volume")
        lba = _dual(data, 2, 4, "directory extent")
        size = _dual(data, 10, 4, "directory data length")
        if lba * SECTOR_SIZE + size > self.volume_size:
            raise IsoError("Directory extent lies outside the declared volume")
        name_length = data[32]
        minimum = 33 + name_length + (name_length % 2 == 0)
        if name_length == 0 or minimum > len(data):
            raise IsoError("Invalid directory identifier length")
        raw = data[33:33 + name_length]
        path = parent if raw in (b"\x00", b"\x01") else "/".join(filter(None, (parent, _name(raw))))
        is_directory = bool(flags & 2)
        if is_directory and size == 0:
            raise IsoError("Empty directory extent")
        return IsoEntry(path, lba, size, record_offset, is_directory), raw, flags

    def get(self, path: str) -> IsoEntry:
        key = path.replace("\\", "/").strip("/")
        if ";" in key:
            parent, _, leaf = key.rpartition("/")
            key = "/".join(filter(None, (parent, _name(leaf.encode("ascii")))))
        try:
            return self.files[key]
        except KeyError as exc:
            raise KeyError(f"ISO9660 file not found: {path}") from exc

    def read(self, path: str) -> bytes:
        entry = self.get(path)
        with self.path.open("rb") as stream:
            return _read_at(stream, entry.offset, entry.size)


def replace_files(
    source: str | os.PathLike[str],
    output: str | os.PathLike[str],
    replacements: Mapping[str, bytes | os.PathLike[str]],
    *,
    expected_sha256: str,
    expected_size: int | None = None,
) -> dict:
    """Copy a verified image, then replace same-length member payloads.

    Output creation is exclusive: originals and existing output files are never
    overwritten.  All names, sizes, and extent overlaps are checked before the
    output is created.  A failed operation removes only its own partial output.
    """
    source, output = Path(source), Path(output)
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
        raise ValueError("expected_sha256 must contain 64 hexadecimal characters")
    expected_sha256 = expected_sha256.lower()
    if source.resolve() == output.resolve() or os.path.lexists(output):
        raise FileExistsError(f"Output must be a new file distinct from input: {output}")
    if expected_size is not None and source.stat().st_size != expected_size:
        raise IsoError("Original image size does not match the supported version")
    if sha256_file(source) != expected_sha256:
        raise IsoError("Original image SHA-256 does not match the supported version")
    image = IsoImage(source)
    planned: list[tuple[IsoEntry, bytes]] = []
    names: set[str] = set()
    report = []
    for name, value in replacements.items():
        entry = image.get(name)
        if entry.path in names:
            raise IsoError(f"Replacement specified twice: {entry.path}")
        names.add(entry.path)
        payload = value if isinstance(value, bytes) else Path(value).read_bytes()
        if len(payload) != entry.size:
            raise IsoError(f"Replacement size differs for {entry.path}: {len(payload)} != {entry.size}")
        for other in image.files.values():
            if other.path != entry.path and entry.size and other.size and entry.offset < other.offset + other.size and entry.offset + entry.size > other.offset:
                raise IsoError(f"Replacement overlaps another file: {entry.path} / {other.path}")
        planned.append((entry, payload))
        report.append({"path": entry.path, "offset": entry.offset, "size": entry.size,
                       "sha256": hashlib.sha256(payload).hexdigest()})
    output.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with source.open("rb") as original, output.open("xb+") as modified:
            created = True
            copied_hash = hashlib.sha256()
            copied = 0
            for block in iter(lambda: original.read(_COPY_CHUNK), b""):
                copied_hash.update(block)
                copied += len(block)
                modified.write(block)
            if copied != image.size or copied_hash.hexdigest() != expected_sha256:
                raise IsoError("Input changed while copying")
            for entry, payload in planned:
                modified.seek(entry.offset)
                modified.write(payload)
            modified.flush()
            modified.seek(0)
            final_hash = hashlib.sha256()
            for block in iter(lambda: modified.read(_COPY_CHUNK), b""):
                final_hash.update(block)
        reopened = IsoImage(output)
        if reopened.files != image.files or reopened.directories != image.directories:
            raise IsoError("Filesystem metadata changed unexpectedly")
        for entry, payload in planned:
            if reopened.read(entry.path) != payload:
                raise IsoError(f"Replacement readback failed: {entry.path}")
        return {"source_sha256": expected_sha256, "sha256": final_hash.hexdigest(),
                "size": image.size, "replacements": report, "output": str(output.resolve())}
    except BaseException:
        if created:
            output.unlink(missing_ok=True)
        raise
