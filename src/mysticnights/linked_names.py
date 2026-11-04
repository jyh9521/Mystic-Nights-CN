"""Audited linked-name discovery and all-or-nothing in-memory replacement.

Name definitions are both displayed and used as lookup keys.  This module
joins complete SCR fields, the known SCN item-field pattern, and exact
NUL-bounded names in the main ELF's file-backed PT_LOAD segments.  It never
edits a disc or starts the game.  ELF literal identity is verified; each
constant's display/lookup call-site semantics remain an inference.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import re
import struct
from typing import Callable, Mapping

from .resources import parse_res
from .scripts import extract_strings, protected_tokens


FORMAT = "mystic-nights-linked-names"
VERSION = 1
MAIN_ELF = "SCKA_200.55"
CANONICAL_RESOURCE = "RES/SUBSYS.RES"
NETWORK_RESOURCE = "RES/NETSUB.RES"
LIMITATIONS = [
    "Verified is static file evidence, not observed gameplay or inventory/save acceptance.",
    "ELF matches prove complete literal identity in PT_LOAD; exact display/lookup use is not inferred as verified.",
    "Only the recognized SCN 0x0068/name[32]/GEO[32] structure is covered; the complete SCN grammar remains unknown.",
    "No scanning or modification of DWARF, NETGUICD.ELF, textures, saves, or original ISO bytes.",
    "Capacity permits no growth beyond each original name; future engine relocation requires a separate design.",
]


class NameLinkError(ValueError):
    """Unsupported source, incomplete manifest, or invalid atomic rename."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def elf_load_segments(data: bytes) -> list[dict]:
    """Read bounded ELF32 little-endian MIPS file-backed PT_LOAD ranges only."""
    if len(data) < 52 or data[:7] != b"\x7fELF\x01\x01\x01":
        raise NameLinkError("Expected ELF32 little-endian version 1")
    if struct.unpack_from("<H", data, 18)[0] != 8:
        raise NameLinkError("Expected MIPS ELF machine")
    if struct.unpack_from("<I", data, 20)[0] != 1:
        raise NameLinkError("Unexpected ELF version")
    offset = struct.unpack_from("<I", data, 28)[0]
    ehsize, entry_size, count = struct.unpack_from("<3H", data, 40)
    if ehsize != 52 or entry_size != 32 or not 1 <= count <= 512:
        raise NameLinkError("Unsupported ELF program-header layout")
    if offset < 52 or offset + count * entry_size > len(data):
        raise NameLinkError("ELF program-header table outside file")
    loads = []
    for index in range(count):
        kind, start, virtual, physical, file_size, memory_size, flags, alignment = struct.unpack_from(
            "<8I", data, offset + index * entry_size
        )
        if kind != 1:
            continue
        if file_size > memory_size or start + file_size > len(data) or virtual + memory_size > 0x100000000:
            raise NameLinkError("Invalid ELF PT_LOAD size/range")
        if alignment not in (0, 1) and (alignment & (alignment - 1) or start % alignment != virtual % alignment):
            raise NameLinkError("Invalid ELF PT_LOAD alignment")
        if file_size:
            loads.append({"index": index, "offset": start, "size": file_size,
                          "virtual_address": virtual, "physical_address": physical,
                          "memory_size": memory_size, "flags": flags, "alignment": alignment})
    if not loads:
        raise NameLinkError("ELF has no file-backed PT_LOAD segment")
    loads.sort(key=lambda row: row["offset"])
    for left, right in zip(loads, loads[1:]):
        if left["offset"] + left["size"] > right["offset"]:
            raise NameLinkError("Overlapping ELF PT_LOAD file ranges")
    return loads


def find_elf_names(data: bytes, names: Mapping[str, str]) -> tuple[list[dict], list[dict], list[dict]]:
    """Find complete name+NUL fields, excluding suffixes and all non-load data."""
    loads = elf_load_segments(data)
    matches, rejected = [], []
    for identifier, source in names.items():
        raw = source.encode("cp949")
        if not raw or b"\0" in raw:
            raise NameLinkError(f"Invalid canonical name: {identifier}")
        needle = raw + b"\0"
        for segment in loads:
            begin, end = segment["offset"], segment["offset"] + segment["size"]
            position = begin
            while True:
                position = data.find(needle, position, end)
                if position < 0:
                    break
                if position != begin and data[position - 1] != 0:
                    rejected.append({"item_id": identifier, "source": source, "offset": position,
                                     "reason": "not a complete NUL-bounded field (suffix/embedded match)"})
                else:
                    context_begin, context_end = max(begin, position - 16), min(end, position + len(needle) + 16)
                    matches.append({"item_id": identifier, "source": source, "kind": "elf",
                                    "resource": MAIN_ELF, "offset": position, "capacity": len(needle),
                                    "max_encoded_bytes": len(raw), "capacity_includes_nul": True,
                                    "expected_hex": needle.hex(), "source_sha256": _sha(needle),
                                    "role": "elf_name_mirror", "evidence": "Verified literal identity",
                                    "semantic_evidence": "Inference: potential display/lookup mirror; call sites not verified",
                                    "context": {"segment_index": segment["index"],
                                                "virtual_address": segment["virtual_address"] + position - begin,
                                                "context_offset": context_begin, "context_size": context_end - context_begin,
                                                "context_sha256": _sha(data[context_begin:context_end])}})
                position += 1
    return sorted(matches, key=lambda row: row["offset"]), rejected, loads


def audit_elf_suffix_references(data: bytes, rejected_suffixes: list[dict], whole_fields: list[dict]) -> dict:
    """Report bounded static evidence for rejected suffix-address references.

    A lack of aligned address literals and exact ADDIU/ORI/DADDIU low-immediate
    candidates does not exclude GP-relative/computed addresses.  Instruction
    decoding here only classifies aligned words; it is not reachability or
    complete data-flow analysis.  Whole-name controls show whether the same
    finite check finds candidate constant construction for enclosing names.
    """
    loads = elf_load_segments(data)
    words = []
    for segment in loads:
        start, end = segment["offset"], segment["offset"] + segment["size"]
        for offset in range((start + 3) // 4 * 4, end - 3, 4):
            word = struct.unpack_from("<I", data, offset)[0]
            words.append((offset, word, segment))
    by_immediate = defaultdict(list)
    for offset, word, segment in words:
        if word >> 26 in (9, 13, 25):
            by_immediate[word & 0xFFFF].append((offset, word, segment))

    def address_evidence(offset: int) -> dict:
        containing = [segment for segment in loads if segment["offset"] <= offset < segment["offset"] + segment["size"]]
        if len(containing) != 1:
            raise NameLinkError("Suffix audit offset is outside a unique load segment")
        segment = containing[0]
        virtual = segment["virtual_address"] + offset - segment["offset"]
        needle = struct.pack("<I", virtual)
        aligned, unaligned = [], []
        for area in loads:
            position, end = area["offset"], area["offset"] + area["size"]
            while True:
                position = data.find(needle, position, end)
                if position < 0:
                    break
                hit = {"offset": position, "bytes_hex": needle.hex()}
                if position % 4:
                    boundary = position // 4 * 4
                    hit["neighbor_aligned_words"] = [
                        {"offset": place, "word": f"0x{struct.unpack_from('<I', data, place)[0]:08x}"}
                        for place in (boundary, boundary + 4) if area["offset"] <= place and place + 4 <= end
                    ]
                    unaligned.append(hit)
                else:
                    aligned.append(hit)
                position += 1
        immediates = []
        for place, word, area in by_immediate[virtual & 0xFFFF]:
            opcode, source_register = word >> 26, (word >> 21) & 31
            expected_high = virtual >> 16 if opcode == 13 else ((virtual + 0x8000) >> 16) & 0xFFFF
            prior_lui = []
            for before in range(max(area["offset"], place - 128), place, 4):
                previous = struct.unpack_from("<I", data, before)[0]
                if previous >> 26 == 15 and (previous >> 16) & 31 == source_register and previous & 0xFFFF == expected_high:
                    prior_lui.append(before)
            immediates.append({"offset": place, "word": f"0x{word:08x}",
                               "opcode": {9: "ADDIU", 13: "ORI", 25: "DADDIU"}[opcode],
                               "source_register": source_register, "target_register": (word >> 16) & 31,
                               "prior_32_word_matching_lui_candidates": prior_lui})
        return {"file_offset": offset, "virtual_address": virtual, "aligned_u32_address_hits": aligned,
                "unaligned_byte_hits": unaligned, "exact_low_immediate_candidates": immediates}

    rows, control_offsets = [], set()
    for suffix in rejected_suffixes:
        offset = suffix["offset"]
        raw = suffix["source"].encode("cp949") + b"\0"
        if data[offset:offset + len(raw)] != raw or offset == 0 or data[offset - 1] == 0:
            raise NameLinkError("Suffix audit source no longer matches an embedded name")
        enclosing = [field for field in whole_fields if field["offset"] < offset
                     and offset + len(raw) == field["offset"] + field["capacity"]]
        control_offsets.update(field["offset"] for field in enclosing)
        rows.append({"item_id": suffix["item_id"], "source": suffix["source"],
                     "enclosing_whole_name_offsets": [field["offset"] for field in enclosing], **address_evidence(offset)})
    controls = [address_evidence(offset) for offset in sorted(control_offsets)]
    return {"summary": {"suffix_addresses": len(rows),
                        "aligned_u32_address_hits": sum(len(row["aligned_u32_address_hits"]) for row in rows),
                        "unaligned_byte_hits": sum(len(row["unaligned_byte_hits"]) for row in rows),
                        "exact_low_immediate_candidates": sum(len(row["exact_low_immediate_candidates"]) for row in rows),
                        "enclosing_whole_name_controls": len(controls),
                        "controls_with_low_immediate_candidates": sum(bool(row["exact_low_immediate_candidates"]) for row in controls)},
            "elf_sha256": _sha(data), "load_segments": loads, "suffixes": rows, "whole_name_controls": controls,
            "conclusion": "Bounded static evidence only; absence of these two direct-reference forms is not proof of no suffix use.",
            "limitations": ["No instruction reachability or register-liveness proof; nearby LUI matches are candidates only.",
                            "GP-relative addressing, arithmetic from an enclosing string, pointer decompression and indirect runtime values are not excluded.",
                            "An unaligned four-byte byte pattern is reported separately and is not labeled a pointer.",
                            "No game execution or change to actual item names."]}


def _scene_fields(payload: bytes) -> list[dict]:
    """Independent validation of the same finite pattern used by inspect_links."""
    result = []
    for match in re.finditer(rb"h\x00", payload):
        offset = match.end()
        if offset + 64 > len(payload):
            continue
        name_field, model_field = payload[offset:offset + 32], payload[offset + 32:offset + 64]
        if b"\0" not in name_field or b"\0" not in model_field:
            continue
        raw, model = name_field.split(b"\0", 1)[0], model_field.split(b"\0", 1)[0]
        if not raw or re.fullmatch(rb"[A-Za-z0-9_.-]+\.GEO", model) is None:
            continue
        try:
            source = raw.decode("cp949")
        except UnicodeDecodeError:
            continue
        if any(ord(char) < 32 for char in source):
            continue
        expected = raw + b"\0"
        result.append({"source": source, "kind": "scn", "member_relative_offset": offset,
                       "capacity": len(expected), "max_encoded_bytes": len(raw), "capacity_includes_nul": True,
                       "expected_hex": expected.hex(), "source_sha256": _sha(expected),
                       "role": "item_reference", "evidence": "Verified recognized SCN pattern",
                       "context": {"type_hex": "6800", "name_field_bytes": 32,
                                   "name_field_sha256": _sha(name_field), "model": model.decode("ascii"),
                                   "record_prefix_sha256": _sha(payload[offset - 2:offset + 64])}})
    return result


def _core(manifest: Mapping) -> dict:
    try:
        groups = [{key: value for key, value in row.items() if key != "reference_en"} for row in manifest["groups"]]
        return {"format": manifest["format"], "version": manifest["version"], "scope": manifest["scope"],
                "groups": groups, "network": manifest["network"], "gaps": manifest["gaps"],
                "elf_rejected_suffixes": manifest["elf_rejected_suffixes"]}
    except (KeyError, TypeError, AttributeError) as exc:
        raise NameLinkError("Malformed linked-name manifest") from exc


def discover_name_links(image, *, inspect_report: Mapping | None = None) -> dict:
    """Derive a hash-bound closure over every ISO RES and the main executable.

    `image` supplies `.files` and `.read(path)`, as IsoImage does.  An optional
    inspect_links report is cross-checked rather than trusted for mutation.
    The complete source scope is recorded so a later rename can reconstruct
    and compare the closure, detecting removed references or changed inputs.
    """
    scopes, fields, canonical, network_names, network_drops = [], [], [], [], []
    resource_names = sorted(name for name in image.files if name.endswith(".RES"))
    if CANONICAL_RESOURCE not in resource_names or MAIN_ELF not in image.files:
        raise NameLinkError("Missing canonical item resource or main executable")
    for name in resource_names:
        data = image.read(name)
        identity = {"path": name, "size": len(data), "sha256": _sha(data)}
        scopes.append(identity)
        archive = parse_res(data)
        for member in archive.entries:
            if not member.name.endswith((".SCR", ".SCN")):
                continue
            payload = archive.read(member)
            common = {"resource": name, "resource_size": len(data), "resource_sha256": identity["sha256"],
                      "member": member.name, "member_group": member.group, "member_index": member.index,
                      "member_offset": member.offset, "member_size": member.size, "member_sha256": _sha(payload)}
            if member.name.endswith(".SCN"):
                for field in _scene_fields(payload):
                    fields.append({**common, **field, "offset": member.offset + field["member_relative_offset"]})
                continue
            for record in extract_strings(payload, member.name):
                if record.role not in {"display_identifier", "item_reference"}:
                    continue
                field = {**common, "source": record.source, "kind": "script", "script_id": record.id,
                         "member_relative_offset": record.offset, "offset": member.offset + record.offset,
                         "capacity": record.capacity, "max_encoded_bytes": record.capacity,
                         "capacity_includes_nul": False, "expected_hex": record.source_bytes.hex(),
                         "source_sha256": record.source_sha256, "role": record.role, "command": record.command,
                         "evidence": "Verified parsed SCR field",
                         "context": {"record": record.context, "line": record.line, "quote_index": record.quote_index}}
                fields.append(field)
                if member.name == "ITEM.SCR" and record.command == "NAME":
                    definition = {"id": record.context, "source": record.source,
                                  "offset": field["offset"], "resource": name}
                    if name == CANONICAL_RESOURCE:
                        canonical.append(definition)
                    elif name == NETWORK_RESOURCE:
                        network_names.append(definition)
                elif name == NETWORK_RESOURCE and member.name == "VAMPIRE.SCR" and record.command == "ITEM":
                    network_drops.append({"source": record.source, "offset": field["offset"]})
    by_name, by_id = {}, {}
    for definition in canonical:
        source, identifier = definition["source"], definition["id"]
        if not source or source in by_name or identifier in by_id or not re.fullmatch(r"id:\d+", identifier):
            raise NameLinkError("Empty/duplicate canonical item name or invalid ID")
        by_name[source] = identifier
        by_id[identifier] = definition
    if not by_name:
        raise NameLinkError("Canonical item table is empty")
    elf = image.read(MAIN_ELF)
    elf_fields, rejected, loads = find_elf_names(elf, {key: row["source"] for key, row in by_id.items()})
    elf_identity = {"path": MAIN_ELF, "size": len(elf), "sha256": _sha(elf), "load_segments": loads}
    for field in elf_fields:
        fields.append({**field, "resource_size": len(elf), "resource_sha256": elf_identity["sha256"]})
    gaps, grouped = [], defaultdict(list)
    for field in fields:
        identifier = by_name.get(field["source"])
        if identifier is None:
            gaps.append({"kind": "unknown referenced name", "source": field["source"],
                         "resource": field["resource"], "offset": field["offset"], "role": field["role"]})
        else:
            grouped[identifier].append(field)
    network_extra = [row for row in network_names if row["source"] not in by_name]
    network_id_mismatches = [row for row in network_names if row["source"] in by_name and by_name[row["source"]] != row["id"]]
    defined_network = {row["source"] for row in network_names}
    undefined_drops = [row for row in network_drops if row["source"] not in defined_network]
    for kind, rows in (("network extra definition", network_extra), ("network ID mismatch", network_id_mismatches),
                       ("network drop lacks local definition", undefined_drops)):
        gaps.extend({"kind": kind, **row} for row in rows)
    references_en = {}
    if inspect_report is not None:
        try:
            reference_items = {row["id"]: row for row in inspect_report["item_names.json"]}
            if {key: row["source_ko"] for key, row in reference_items.items()} != {key: row["source"] for key, row in by_id.items()}:
                raise NameLinkError("inspect_links canonical names differ from current source")
            expected_res = {(field["resource"], field["offset"], field["source"], field["max_encoded_bytes"])
                            for field in fields if field["kind"] != "elf" and field["source"] in by_name}
            reported_res = {(reference["resource"], reference["offset"], item["source_ko"], reference["capacity"])
                            for item in reference_items.values() for reference in item["references"]}
            if expected_res != reported_res:
                raise NameLinkError("inspect_links RES reference closure differs from current source")
            references_en = {key: row.get("reference_en") for key, row in reference_items.items()}
        except (KeyError, TypeError) as exc:
            raise NameLinkError("Malformed inspect_links report") from exc
    groups = []
    for identifier, definition in by_id.items():
        references = sorted(grouped[identifier], key=lambda row: (row["resource"], row["offset"], row["kind"]))
        groups.append({"id": identifier, "source": definition["source"], "reference_en": references_en.get(identifier),
                       "canonical_definition": definition, "source_text_sha256": _sha(definition["source"].encode("cp949")),
                       "max_encoded_bytes": min(row["max_encoded_bytes"] for row in references),
                       "references": references})
    all_ranges = sorted((row["resource"], row["offset"], row["capacity"]) for group in groups for row in group["references"])
    for left, right in zip(all_ranges, all_ranges[1:]):
        if left[0] == right[0] and left[1] + left[2] > right[1]:
            raise NameLinkError("Overlapping linked-name fields")
    manifest = {"format": FORMAT, "version": VERSION,
                "scope": {"res_files": scopes, "main_elf": elf_identity}, "groups": groups,
                "network": {"definitions": network_names, "drop_references": len(network_drops),
                            "drop_names": dict(sorted(Counter(row["source"] for row in network_drops).items())),
                            "extra_definitions": network_extra, "id_mismatches": network_id_mismatches,
                            "drops_without_local_definition": undefined_drops},
                "gaps": gaps, "elf_rejected_suffixes": rejected, "limitations": LIMITATIONS,
                "capacity_semantics": "reference.capacity is writable span; NUL fields include their existing terminator. max_encoded_bytes excludes it."}
    manifest["core_sha256"] = _sha(_canonical_json(_core(manifest)))
    manifest["summary"] = {"canonical_names": len(groups), "references": len(all_ranges),
                           "references_by_kind": dict(Counter(row["kind"] for group in groups for row in group["references"])),
                           "elf_names": len({row["source"] for row in elf_fields}), "elf_exact_fields": len(elf_fields),
                           "elf_rejected_suffixes": len(rejected), "network_definitions": len(network_names),
                           "network_extra_names": len(network_extra), "gaps": len(gaps),
                           "minimum_encoded_capacity": min(row["max_encoded_bytes"] for row in groups)}
    return manifest


def patch_linked_names(image, manifest: Mapping, targets: Mapping[str, str],
                       encode: Callable[[str], bytes]) -> dict[str, bytes]:
    """Validate the whole recorded closure, then return changed payload copies.

    All group references receive the same encoded name in one operation.  The
    current source is rediscovered and compared with the full manifest core;
    deleted/altered references, unknown sources, collisions and overflows abort
    before any modified payload is returned.  No input or filesystem is written.
    """
    fresh = discover_name_links(image)
    supplied_core = _core(manifest)
    if manifest.get("core_sha256") != _sha(_canonical_json(supplied_core)) or supplied_core != _core(fresh):
        raise NameLinkError("Linked-name manifest does not match complete current source closure")
    if fresh["gaps"]:
        raise NameLinkError("Unresolved linked-name gaps must be reviewed before renaming")
    groups = {row["id"]: row for row in fresh["groups"]}
    if set(targets) - set(groups):
        raise NameLinkError(f"Unknown linked-name IDs: {sorted(set(targets) - set(groups))}")
    encoded, changed = {}, {}
    for identifier, group in groups.items():
        target = targets.get(identifier, group["source"])
        if not isinstance(target, str) or not target.strip() or any(char in target for char in ('"', "\0", "\n", "\r")):
            raise NameLinkError(f"Invalid target name: {identifier}")
        if protected_tokens(target) != protected_tokens(group["source"]):
            raise NameLinkError(f"Protected tokens changed in name: {identifier}")
        if target == group["source"]:
            value = group["source"].encode("cp949")
        else:
            try:
                value = encode(target)
            except (ValueError, UnicodeError) as exc:
                raise NameLinkError(f"Name encoding failed: {identifier}: {exc}") from exc
            if not isinstance(value, bytes) or not value or any(byte in value for byte in (0, 10, 13, 34)):
                raise NameLinkError(f"Encoder produced invalid name bytes: {identifier}")
            if len(value) > group["max_encoded_bytes"]:
                raise NameLinkError(f"Linked-name overflow {identifier}: {len(value)} > {group['max_encoded_bytes']}")
            changed[identifier] = value
        encoded[identifier] = value
    reverse = {}
    for identifier, value in encoded.items():
        if value in reverse:
            raise NameLinkError(f"Encoded item-name collision: {reverse[value]} and {identifier}")
        reverse[value] = identifier
    plans = defaultdict(list)
    for identifier, value in changed.items():
        for reference in groups[identifier]["references"]:
            replacement = value + (b"\0" if reference["capacity_includes_nul"] else b"")
            if len(replacement) > reference["capacity"]:
                raise NameLinkError(f"Reference overflow: {identifier}/{reference['resource']}")
            plans[reference["resource"]].append((reference, replacement.ljust(reference["capacity"], b"\0")))
    originals = {}
    for name, fields in plans.items():
        data = image.read(name)
        first = fields[0][0]
        if len(data) != first["resource_size"] or _sha(data) != first["resource_sha256"]:
            raise NameLinkError(f"Source changed after discovery: {name}")
        for field, _replacement in fields:
            start, end = field["offset"], field["offset"] + field["capacity"]
            expected = bytes.fromhex(field["expected_hex"])
            if data[start:end] != expected or _sha(expected) != field["source_sha256"]:
                raise NameLinkError(f"Source field changed: {name}@{start:#x}")
        originals[name] = data
    result = {}
    for name, fields in plans.items():
        output = bytearray(originals[name])
        for field, replacement in fields:
            output[field["offset"]:field["offset"] + field["capacity"]] = replacement
        revised = bytes(output)
        if len(revised) != len(originals[name]):
            raise NameLinkError(f"Unexpected resource resizing: {name}")
        if name.endswith(".RES") and parse_res(revised).entries != parse_res(originals[name]).entries:
            raise NameLinkError(f"Archive structure changed: {name}")
        for field, replacement in fields:
            if revised[field["offset"]:field["offset"] + field["capacity"]] != replacement:
                raise NameLinkError(f"Linked-name readback mismatch: {name}")
        result[name] = revised
    return result
