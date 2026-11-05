"""Source-bound auxiliary text: UTF-8 network UI and original plain-text files.

Discovery is deterministic and separate from reviewed locale data. Patching
uses only source-recipe-declared alignment padding and never moves a pointer or
terminator outside that slot. A verified original ISO is required by the build.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .executable import validate_tokens
from .typography import validate_text


def nul_candidates(data: bytes, encoding: str, unicode_ranges=()):
    offset = 0
    for raw in data.split(b"\0")[:-1]:
        try:
            source = raw.decode(encoding, errors="strict")
        except UnicodeDecodeError:
            source = ""
        printable = source and all(c.isprintable() or c in "\r\n\t" for c in source)
        selected = not unicode_ranges or any(low <= ord(c) <= high for c in source for low, high in unicode_ranges)
        if printable and selected:
            yield offset, raw, source
        offset += len(raw) + 1


def extract_auxiliary(image, recipe):
    reports = []
    for definition in recipe["sources"]:
        resource, encoding = definition["resource"], definition["encoding"]
        data = image.read(resource)
        layout = definition["layout"]
        if layout == "nul-candidates":
            values = list(nul_candidates(data, encoding, definition.get("unicode_ranges", [])))
        elif layout == "plain":
            values = [(0, data, data.decode(encoding, errors="strict"))]
        elif layout == "explicit-slots":
            values = []
            for slot in definition["slots"]:
                offset, source = slot["offset"], slot["source"]
                raw = source.encode(encoding)
                padding = slot.get("padding_bytes", 0)
                if type(padding) is not int or not 0 <= padding <= 15:
                    raise ValueError("Invalid explicit alignment padding")
                if data[offset:offset + len(raw) + 1 + padding] != raw + b"\0" * (1 + padding):
                    raise ValueError(f"Explicit auxiliary source mismatch: {resource}@{offset:x}")
                values.append((offset, raw, source))
        else:
            raise ValueError(f"Unknown text source layout: {layout}")
        rows = [{"id": f"{resource}@{offset:08x}", "resource": resource, "offset": offset,
                 "source_bytes": len(raw), "source_sha256": hashlib.sha256(raw).hexdigest(),
                 "source": source, "target": "", "status": "untranslated", "encoding": encoding,
                 "role": "candidate_display", "patch_ready": False} for offset, raw, source in values]
        if layout == "explicit-slots":
            for row, slot in zip(rows, definition["slots"]):
                if slot.get("padding_bytes", 0):
                    row["padding_bytes"] = slot["padding_bytes"]
        reports.append({"resource": resource, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                        "encoding": encoding, "layout": layout, "separate_font": definition.get("font"),
                        "entries": rows})
    return reports


def read_auxiliary(locale_dir: Path, config, recipe, image=None):
    """Read complete auxiliary catalogues, optionally re-extract their sources."""
    source_groups = extract_auxiliary(image, recipe) if image is not None else None
    expected = {r["resource"]: r for r in source_groups or []}
    reviewed_padding = {(definition["resource"], slot["offset"]): slot.get("padding_bytes", 0)
                        for definition in recipe["sources"] if definition["layout"] == "explicit-slots"
                        for slot in definition["slots"]}
    result, hashes = {}, {}
    for key, resource in (("network", "NETGUICD.ELF"), ("agreement", "DATA/AGREE.TXT"),
                          ("extra_interface", "SCKA_200.55")):
        relative = Path(config[key])
        path = (locale_dir / relative).resolve()
        if relative.is_absolute() or ".." in relative.parts or not path.is_relative_to(locale_dir.resolve()):
            raise ValueError("Auxiliary catalogue escapes locale directory")
        raw = path.read_bytes()
        data = json.loads(raw)
        hashes[key] = hashlib.sha256(raw).hexdigest()
        if data.get("locale") != config["locale"] or not data.get("entries"):
            raise ValueError("Auxiliary locale/entries mismatch")
        rows = data["entries"]
        ids = set()
        if source_groups is not None and len(rows) != len(expected[resource]["entries"]):
            raise ValueError(f"Auxiliary source count mismatch: {key}")
        for index, row in enumerate(rows):
            identifier = f"{resource}@{row['offset']:08x}"
            if row["id"] != identifier or identifier in ids or row["resource"] != resource:
                raise ValueError("Duplicate or noncanonical auxiliary ID")
            ids.add(identifier)
            source = row["source"].encode(row["encoding"])
            if len(source) != row["source_bytes"] or hashlib.sha256(source).hexdigest() != row["source_sha256"]:
                raise ValueError(f"Auxiliary source/hash mismatch: {identifier}")
            if source_groups is not None:
                original = expected[resource]["entries"][index]
                if any(row.get(k) != original[k] for k in original if k not in {"target", "status", "role", "patch_ready"}):
                    raise ValueError(f"Auxiliary source metadata changed: {identifier}")
            if (row.get("status") not in {"draft", "reviewed"} or not row.get("target", "").strip()
                    or row.get("role") != "display" or row.get("patch_ready") is not True):
                raise ValueError(f"Auxiliary text is not translated/reviewed for insertion: {identifier}")
            target = row["target"]
            validate_tokens(row["source"], target)
            typography = {**config["punctuation"],
                          "no_line_start": config.get("text_layout", {}).get("no_line_start", "")}
            text_type = "system_message" if row.get("text_type") == "network_dialog" else row.get("text_type", "ui_label")
            validate_text(target, text_type, typography)
            if key == "network":
                if target.count("\n") != row["source"].count("\n") or "\r" in target:
                    raise ValueError(f"Network dialog line structure changed: {identifier}")
                # The PF alias encoder emits three UTF-8 bytes for every
                # non-ASCII glyph, including symbols originally using two.
                size = sum(1 if ord(c) < 128 else 3 for c in target)
            else:
                size = sum(1 if ord(c) < 128 else 2 for c in target)
            padding = row.get("padding_bytes", 0)
            # Missing metadata means zero authorization, not a free choice of
            # capacity. Bind it to the recipe even without an original image.
            authorized_padding = reviewed_padding.get((resource, row["offset"]), 0)
            if (type(padding) is not int or not 0 <= padding <= 15 or (key != "extra_interface" and padding)
                    or type(authorized_padding) is not int or padding != authorized_padding):
                raise ValueError("Unreviewed auxiliary alignment padding")
            if size > row["source_bytes"] + padding:
                raise ValueError(f"Auxiliary fixed-slot overflow: {identifier}: {size} > {row['source_bytes'] + padding}")
            if key == "agreement":
                if target.count("<END>") != 1 or not target.endswith("<END>\r\r\n"):
                    raise ValueError("Agreement terminal marker/line ending changed")
                if "\r" in target.replace("\r\r\n", "") or "\n" in target.replace("\r\r\n", ""):
                    raise ValueError("Agreement has mixed line endings")
                if any(sum(1 if ord(c) < 128 else 2 for c in line) > 70 for line in target.split("\r\r\n")):
                    raise ValueError("Agreement visual line exceeds reviewed width")
        result[key] = rows
    result["catalogue_sha256"] = hashes
    return result


def extra_elf_entries(rows):
    return [{**r, "kind": "elf", "capacity": r["source_bytes"] + 1 + r.get("padding_bytes", 0),
             "source_sha256": hashlib.sha256(r["source"].encode("cp949") + b"\0" * (1 + r.get("padding_bytes", 0))).hexdigest()}
            for r in rows]


def patch_auxiliary_slots(data, rows, encode, *, plain=False):
    """Validate the complete original byte spans before any equal-sized edit."""
    plans = []
    for row in rows:
        raw = row["source"].encode(row["encoding"])
        if len(raw) != row["source_bytes"] or hashlib.sha256(raw).hexdigest() != row["source_sha256"]:
            raise ValueError("Auxiliary source hash mismatch")
        padding = row.get("padding_bytes", 0)
        if type(padding) is not int or not 0 <= padding <= 15 or (plain and padding):
            raise ValueError("Invalid auxiliary alignment padding")
        expected = raw if plain else raw + b"\0" * (1 + padding)
        start, end = row["offset"], row["offset"] + len(expected)
        if not 0 <= start < end <= len(data) or data[start:end] != expected:
            raise ValueError(f"Auxiliary original bytes mismatch: {row['id']}")
        validate_tokens(row["source"], row["target"])
        target = encode(row["target"])
        if b"\0" in target:
            raise ValueError("Auxiliary encoder introduced NUL")
        if not plain:
            target += b"\0"
        if len(target) > len(expected):
            raise ValueError(f"Auxiliary slot overflow: {row['id']}")
        plans.append((start, end, target.ljust(len(expected), b"\0")))
    plans.sort()
    if any(a[1] > b[0] for a, b in zip(plans, plans[1:])):
        raise ValueError("Overlapping auxiliary slots")
    output = bytearray(data)
    for start, end, target in plans:
        output[start:end] = target
    return bytes(output)


def merge_resource_edits(original, left, right):
    """Merge two source-based edits; shared bytes must request the same value."""
    if len(original) != len(left) or len(original) != len(right):
        raise ValueError("Cannot merge resized resource edits")
    output = bytearray(left)
    for index, (source, first, second) in enumerate(zip(original, left, right)):
        if second != source:
            if first != source and first != second:
                raise ValueError(f"Conflicting resource edits at {index:#x}")
            output[index] = second
    return bytes(output)
