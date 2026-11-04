"""Deterministic, reversible, sparse byte patches for equal-sized files.

The ZIP contains only changed ranges, their original bytes for rollback, and
an integrity manifest.  No ZIP member is ever extracted to the filesystem.
Application verifies the complete input, every payload, range bounds, expected
bytes, and the complete result.  Outputs are always new files.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from typing import BinaryIO
import zipfile


FORMAT = "sparse-byte-patch"
VERSION = 1
_CHUNK = 1024 * 1024
_MAX_MANIFEST = 16 * 1024 * 1024
_MAX_RANGES = 100_000


class PatchError(ValueError):
    """Invalid patch data, source identity, or output verification."""


def sha256_file(path: str | os.PathLike[str]) -> str:
    with Path(path).open("rb") as stream:
        return _hash_stream(stream)


def _hash_stream(stream: BinaryIO) -> str:
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(_CHUNK), b""):
        digest.update(block)
    return digest.hexdigest()


def _new_output(path: Path, inputs: tuple[Path, ...]) -> None:
    if any(path.resolve() == item.resolve() for item in inputs) or os.path.lexists(path):
        raise FileExistsError(f"Output must be a new file distinct from every input: {path}")


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def _put_range(archive: zipfile.ZipFile, stream: BinaryIO, name: str, start: int, size: int) -> str:
    digest = hashlib.sha256()
    stream.seek(start)
    remaining = size
    with archive.open(_zip_info(name), "w", force_zip64=True) as member:
        while remaining:
            data = stream.read(min(_CHUNK, remaining))
            if not data:
                raise PatchError("Input was truncated during patch creation")
            member.write(data)
            digest.update(data)
            remaining -= len(data)
    return digest.hexdigest()


def build_patch(
    original: str | os.PathLike[str],
    modified: str | os.PathLike[str],
    patch_path: str | os.PathLike[str],
    *,
    merge_gap: int = 16,
) -> dict:
    """Create a deterministic ZIP patch; equal gaps up to ``merge_gap`` merge.

    The range scan streams input files and retains only offset pairs, rather
    than keeping complete images or changed payloads in memory.
    """
    original, modified, patch_path = Path(original), Path(modified), Path(patch_path)
    _new_output(patch_path, (original, modified))
    if isinstance(merge_gap, bool) or not isinstance(merge_gap, int) or not 0 <= merge_gap <= 4096:
        raise ValueError("merge_gap must be an integer from 0 through 4096")
    size = original.stat().st_size
    if modified.stat().st_size != size:
        raise PatchError("Sparse patches require equal-sized input and output files")
    hashes = [hashlib.sha256(), hashlib.sha256()]
    ranges: list[list[int]] = []
    with original.open("rb") as before, modified.open("rb") as after:
        offset = 0
        while True:
            left, right = before.read(_CHUNK), after.read(_CHUNK)
            if len(left) != len(right):
                raise PatchError("Input sizes changed during patch scan")
            if not left:
                break
            hashes[0].update(left)
            hashes[1].update(right)
            if left != right:
                for index, (old, new) in enumerate(zip(left, right)):
                    if old == new:
                        continue
                    position = offset + index
                    if ranges and position - ranges[-1][1] <= merge_gap:
                        ranges[-1][1] = position + 1
                    else:
                        ranges.append([position, position + 1])
                        if len(ranges) > _MAX_RANGES:
                            raise PatchError("Patch range count exceeds supported limit")
            offset += len(left)
        if offset != size:
            raise PatchError("Input size changed during patch scan")
        manifest = {
            "format": FORMAT,
            "version": VERSION,
            "original": {"size": size, "sha256": hashes[0].hexdigest()},
            "modified": {"size": size, "sha256": hashes[1].hexdigest()},
            "ranges": [],
        }
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        created = False
        try:
            with patch_path.open("xb") as output:
                created = True
                with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                    for index, (start, end) in enumerate(ranges):
                        record = {"offset": start, "size": end - start,
                                  "before": f"before/{index:06d}.bin", "after": f"after/{index:06d}.bin"}
                        record["before_sha256"] = _put_range(archive, before, record["before"], start, end - start)
                        record["after_sha256"] = _put_range(archive, after, record["after"], start, end - start)
                        manifest["ranges"].append(record)
                    encoded = (json.dumps(manifest, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
                    if len(encoded) > _MAX_MANIFEST:
                        raise PatchError("Patch manifest exceeds supported size")
                    archive.writestr(_zip_info("manifest.json"), encoded)
                before.seek(0)
                after.seek(0)
                if _hash_stream(before) != manifest["original"]["sha256"] or _hash_stream(after) != manifest["modified"]["sha256"]:
                    raise PatchError("An input changed during patch creation")
            return manifest
        except BaseException:
            if created:
                patch_path.unlink(missing_ok=True)
            raise


def _integer(value: object, label: str, *, positive: bool = False) -> int:
    if type(value) is not int or value < (1 if positive else 0):
        raise PatchError(f"Invalid integer field: {label}")
    return value


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise PatchError(f"Invalid SHA-256 field: {label}")
    return value


def _json_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise PatchError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_manifest(archive: zipfile.ZipFile) -> dict:
    names = archive.namelist()
    if len(names) != len(set(names)) or "manifest.json" not in names:
        raise PatchError("Missing manifest or duplicate ZIP member")
    info = archive.getinfo("manifest.json")
    if info.file_size > _MAX_MANIFEST or info.flag_bits & 1 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        raise PatchError("Oversized or encrypted patch manifest")
    try:
        manifest = json.loads(archive.read(info).decode("utf-8"), object_pairs_hook=_json_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PatchError("Invalid UTF-8 JSON patch manifest") from exc
    if not isinstance(manifest, dict) or set(manifest) != {"format", "version", "original", "modified", "ranges"}:
        raise PatchError("Invalid patch manifest fields")
    if manifest["format"] != FORMAT or type(manifest["version"]) is not int or manifest["version"] != VERSION:
        raise PatchError("Unsupported patch format/version")
    for side in ("original", "modified"):
        identity = manifest[side]
        if not isinstance(identity, dict) or set(identity) != {"size", "sha256"}:
            raise PatchError(f"Invalid {side} identity")
        _integer(identity["size"], side + ".size")
        _digest(identity["sha256"], side + ".sha256")
    size = manifest["original"]["size"]
    if manifest["modified"]["size"] != size:
        raise PatchError("Patch changes file size")
    if not isinstance(manifest["ranges"], list) or len(manifest["ranges"]) > _MAX_RANGES:
        raise PatchError("Invalid patch range list")
    expected_names = {"manifest.json"}
    previous_end = 0
    for index, record in enumerate(manifest["ranges"]):
        if not isinstance(record, dict) or set(record) != {"offset", "size", "before", "after", "before_sha256", "after_sha256"}:
            raise PatchError("Invalid patch range fields")
        start = _integer(record["offset"], "range.offset")
        length = _integer(record["size"], "range.size", positive=True)
        if start < previous_end or start + length > size:
            raise PatchError("Patch ranges overlap, are unsorted, or lie outside the file")
        previous_end = start + length
        for side in ("before", "after"):
            name = f"{side}/{index:06d}.bin"
            if record[side] != name:
                raise PatchError("Unexpected patch member path")
            _digest(record[side + "_sha256"], side + ".sha256")
            expected_names.add(name)
            try:
                info = archive.getinfo(name)
            except KeyError as exc:
                raise PatchError(f"Missing patch member: {name}") from exc
            if info.file_size != length or info.flag_bits & 1 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise PatchError(f"Invalid patch member metadata: {name}")
    if set(names) != expected_names:
        raise PatchError("Unexpected additional ZIP members")
    return manifest


def inspect_patch(patch_path: str | os.PathLike[str]) -> dict:
    """Read and structurally validate a patch manifest without applying it."""
    with zipfile.ZipFile(patch_path, "r") as archive:
        return _load_manifest(archive)


def apply_patch(
    source: str | os.PathLike[str],
    patch_path: str | os.PathLike[str],
    output: str | os.PathLike[str],
    *,
    reverse: bool = False,
) -> dict:
    """Apply or roll back a patch to a new copy, verifying all byte identities."""
    source, patch_path, output = Path(source), Path(patch_path), Path(output)
    _new_output(output, (source, patch_path))
    with zipfile.ZipFile(patch_path, "r") as archive, source.open("rb") as original:
        manifest = _load_manifest(archive)
        source_side, target_side = ("modified", "original") if reverse else ("original", "modified")
        expected_side, replacement_side = ("after", "before") if reverse else ("before", "after")
        source_identity, target_identity = manifest[source_side], manifest[target_side]
        if os.fstat(original.fileno()).st_size != source_identity["size"] or _hash_stream(original) != source_identity["sha256"]:
            raise PatchError("Input size or SHA-256 does not match the patch source")
        # Validate every payload and all source ranges before creating output.
        for record in manifest["ranges"]:
            for side in ("before", "after"):
                with archive.open(record[side], "r") as member:
                    if _hash_stream(member) != record[side + "_sha256"]:
                        raise PatchError(f"Patch payload SHA-256 mismatch: {record[side]}")
            original.seek(record["offset"])
            remaining = record["size"]
            digest = hashlib.sha256()
            while remaining:
                block = original.read(min(remaining, _CHUNK))
                if not block:
                    raise PatchError("Input changed during expected-byte verification")
                digest.update(block)
                remaining -= len(block)
            if digest.hexdigest() != record[expected_side + "_sha256"]:
                raise PatchError("Patch expected bytes do not match the input range")
        output.parent.mkdir(parents=True, exist_ok=True)
        created = False
        try:
            with output.open("xb+") as destination:
                created = True
                original.seek(0)
                copied_hash = hashlib.sha256()
                copied = 0
                for block in iter(lambda: original.read(_CHUNK), b""):
                    destination.write(block)
                    copied_hash.update(block)
                    copied += len(block)
                if copied != source_identity["size"] or copied_hash.hexdigest() != source_identity["sha256"]:
                    raise PatchError("Input changed while copying")
                for record in manifest["ranges"]:
                    destination.seek(record["offset"])
                    with archive.open(record[replacement_side], "r") as member:
                        for block in iter(lambda: member.read(_CHUNK), b""):
                            destination.write(block)
                destination.flush()
                destination.seek(0)
                actual_hash = _hash_stream(destination)
                if os.fstat(destination.fileno()).st_size != target_identity["size"] or actual_hash != target_identity["sha256"]:
                    raise PatchError("Patched output SHA-256/size verification failed")
            if sha256_file(output) != target_identity["sha256"]:
                raise PatchError("Patched output readback SHA-256 verification failed")
            return {"mode": "rollback" if reverse else "apply", "sha256": actual_hash,
                    "size": target_identity["size"], "ranges": len(manifest["ranges"]),
                    "output": str(output.resolve())}
        except BaseException:
            if created:
                output.unlink(missing_ok=True)
            raise
