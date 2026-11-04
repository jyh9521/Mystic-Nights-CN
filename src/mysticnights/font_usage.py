"""Survey retained CP949 text before reusing an original font slot.

This is a static literal survey, not proof that an arbitrary runtime path never
constructs a character. Complete SCR plaintext, plain-text files, RES names and
both executable load segments are inspected independently of the translation
catalogue. Opaque binary hits are reported separately, never silently promoted
to display-text references. Inputs are read-only and output creation exclusive.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from functools import lru_cache
import hashlib
from pathlib import Path
import re
import struct
import unicodedata

from .font import parse_fnt
from .resources import parse_res
from .versions import verify_original


OPAQUE_EXTENSIONS = frozenset({".GEO", ".ANI", ".BIN", ".SCN"})
TEXT_EXTENSIONS = frozenset({".TXT", ".CNF"})
MAIN_ELF = "SCKA_200.55"
AUXILIARY_ELF = "NETGUICD.ELF"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_printable_text(text: str) -> bool:
    """CP949 punctuation and space separators count; embedded NUL/control does not."""
    return bool(text) and all(c in "\t\r\n" or c.isprintable()
                             or unicodedata.category(c) == "Zs" for c in text)


def cp949_code_positions(data: bytes, font_codes: set[int] | frozenset[int]):
    """Yield exact encoded keys, never cross-character adjacent-byte pairs."""
    data.decode("cp949", errors="strict")
    position = 0
    while position < len(data):
        if data[position] & 0x80:
            code = (data[position] << 8) | data[position + 1]
            if code in font_codes:
                yield position, code
            position += 2
        else:
            position += 1


def printable_cstrings(data: bytes):
    """Yield (offset, bytes, text) for whole NUL-delimited printable CP949 spans.

    A span starts at byte zero or immediately after another NUL. Unterminated
    tails and invalid/nonprintable spans are rejected, not repaired or trimmed.
    Even one-character candidates are retained; binary false positives remain
    explicit in the report and are conservatively reserved in the text survey.
    """
    start = 0
    while True:
        end = data.find(b"\0", start)
        if end == -1:
            return
        raw = data[start:end]
        try:
            text = raw.decode("cp949", errors="strict")
        except UnicodeDecodeError:
            text = ""
        if is_printable_text(text):
            yield start, raw, text
        start = end + 1


@lru_cache(maxsize=1)
def printable_cp949_pairs() -> frozenset[int]:
    result = set()
    for lead in range(0x80, 0x100):
        for trail in range(1, 0x100):
            try:
                text = bytes((lead, trail)).decode("cp949", errors="strict")
            except UnicodeDecodeError:
                continue
            if len(text) == 1 and is_printable_text(text):
                result.add((lead << 8) | trail)
    return frozenset(result)


def suffix_code_candidates(data: bytes, font_codes: set[int] | frozenset[int]):
    """Yield (key_offset, key, NUL_offset) for every printable CP949 suffix.

    Backwards two-state validation follows actual one/two-byte code units. It
    also covers strings immediately following a non-text field rather than a
    NUL. Every returned key can begin a strictly printable CP949 string ending
    at the recorded NUL. No arbitrary byte-pair match is accepted here.
    """
    pairs = printable_cp949_pairs()
    start = 0
    while True:
        end = data.find(b"\0", start)
        if end == -1:
            return
        valid_next, valid_after_next = True, False
        for position in range(end - 1, start - 1, -1):
            byte = data[position]
            ascii_valid = valid_next and (byte in (9, 10, 13) or 32 <= byte <= 126)
            code = (byte << 8) | data[position + 1] if position + 1 < end else 0
            pair_valid = valid_after_next and code in pairs
            if pair_valid and code in font_codes:
                yield position, code, end
            valid = ascii_valid or pair_valid
            # A preceding token spans at most two bytes; two invalid suffixes
            # therefore prove that no earlier suffix can reach this terminator.
            if not valid and not valid_next:
                break
            valid_after_next, valid_next = valid_next, valid
        start = end + 1


def raw_pair_hits(data: bytes, font_codes: set[int] | frozenset[int]) -> dict[int, int]:
    """Diagnostic upper bound only: first arbitrary byte-pair hit for each key."""
    if not font_codes:
        return {}
    leads = bytes(sorted({code >> 8 for code in font_codes}))
    trails = bytes(sorted({code & 0xFF for code in font_codes}))
    pattern = re.compile(b"(?=([" + re.escape(leads) + b"][" + re.escape(trails) + b"]))")
    found = {}
    for match in pattern.finditer(data):
        raw = match.group(1)
        code = (raw[0] << 8) | raw[1]
        if code in font_codes and code not in found:
            found[code] = match.start()
            if len(found) == len(font_codes):
                break  # All possible keys have a positive witness already.
    return found


def elf_load_segments(elf: bytes) -> list[dict]:
    """Read file-backed ELF32/MIPS PT_LOAD ranges without importing a CLI tool."""
    if len(elf) < 52 or elf[:7] != b"\x7fELF\x01\x01\x01":
        raise ValueError("Expected little-endian ELF32")
    if struct.unpack_from("<H", elf, 18)[0] != 8:
        raise ValueError("Expected MIPS ELF machine")
    offset = struct.unpack_from("<I", elf, 28)[0]
    size, count = struct.unpack_from("<HH", elf, 42)
    if size != 32 or offset + size * count > len(elf):
        raise ValueError("Invalid ELF program-header table")
    result = []
    for index in range(count):
        kind, start, virtual, physical, file_size, memory_size, flags, alignment = struct.unpack_from(
            "<8I", elf, offset + index * size)
        if kind != 1:
            continue
        if start + file_size > len(elf) or memory_size < file_size:
            raise ValueError("Invalid ELF load-segment bounds")
        result.append({"offset": start, "virtual_address": virtual,
                       "physical_address": physical, "file_size": file_size,
                       "memory_size": memory_size, "flags": flags, "alignment": alignment})
    if not result:
        raise ValueError("ELF has no load segments")
    return result


def _code_list(codes) -> list[int]:
    return sorted(codes)


def _source(image, path: str, data: bytes, *, member: str | None = None,
            offset: int = 0, label: str = "") -> dict:
    return {"path": path, "member": member, "label": label,
            "offset_in_file": offset, "offset_in_iso": image.get(path).offset + offset,
            "size": len(data), "sha256": digest(data)}


def _witness(source: dict, data: bytes, offset: int, code: int, **extra) -> dict:
    actual = data[offset:offset + 2]
    expected = code.to_bytes(2, "big")
    if actual != expected:
        raise ValueError("Font-usage source-byte witness mismatch")
    return {"path": source["path"], "member": source["member"],
            "source_sha256": source["sha256"],
            "offset_in_source": offset, "offset_in_file": source["offset_in_file"] + offset,
            "offset_in_iso": source["offset_in_iso"] + offset,
            "expected_hex": expected.hex(), "actual_hex": actual.hex(), **extra}


def collect_protected_codes(iso_path: str | Path, version: dict, *, audit_unknown: bool = False):
    """Return (protected codes, report) after validating the complete original ISO.

    Protection is the union of complete source plaintext, RES names, both ELFs'
    printable NUL-terminated spans and every printable NUL-terminated suffix.
    Opaque RES structures are audited separately: their byte coincidences do not
    prove a display reference, and absent candidates do not prove unused code.
    """
    image = verify_original(Path(iso_path), version)
    original_font = parse_fnt(parse_res(image.read("RES/SYSTEM.RES")).read("FONT.FNT"))
    font_codes = frozenset(g.code for g in original_font if g.code > 127)
    if len(original_font) != 2539 or len(font_codes) != 2444:
        raise ValueError("Unexpected supported font inventory")
    tiers: dict[str, set[int]] = defaultdict(set)
    first: dict[str, dict[int, dict]] = defaultdict(dict)
    counts = Counter()
    sources = []
    archives = []
    opaque = []
    opaque_cache = {}
    embedded_text = []
    excluded_types = Counter()
    all_resource_names = []

    def add_text(data: bytes, source: dict, tier: str, *, require_printable: bool = False):
        text = data.decode("cp949", errors="strict")
        if require_printable and not is_printable_text(text):
            raise ValueError(f"Expected printable text: {source['path']} / {source['member']}")
        local = Counter(code for _, code in cp949_code_positions(data, font_codes))
        for position, code in cp949_code_positions(data, font_codes):
            tiers[tier].add(code)
            if code not in first[tier]:
                first[tier][code] = _witness(source, data, position, code, evidence=tier)
        counts[tier + "_code_occurrences"] += sum(local.values())
        counts[tier + "_sources"] += 1
        sources.append({**source, "evidence": tier, "font_codes": _code_list(local),
                        "code_occurrences": sum(local.values()), "strict_cp949": True})

    for path in sorted(image.files):
        if path.endswith(".RES"):
            data = image.read(path)
            archive = parse_res(data)
            archives.append({"path": path, "size": len(data), "sha256": digest(data),
                             "members": len(archive.entries), "group_counts": list(archive.group_counts)})
            for member in archive.entries:
                counts["res_members"] += 1
                name_bytes = data[member.header_offset:member.header_offset + 32].split(b"\0", 1)[0]
                if name_bytes.decode("cp949") != member.name:
                    raise ValueError("RES member-name round-trip mismatch")
                header_source = _source(image, path, name_bytes, member=member.name,
                                        offset=member.header_offset, label="member name")
                name_codes = list(cp949_code_positions(name_bytes, font_codes))
                for position, code in name_codes:
                    tiers["resource_names"].add(code)
                    first["resource_names"].setdefault(code, _witness(
                        header_source, name_bytes, position, code, evidence="resource_names"))
                if name_codes:
                    all_resource_names.append({**header_source,
                                               "font_codes": sorted({c for _, c in name_codes})})
                payload = archive.read(member)
                extension = Path(member.name).suffix.upper()
                source = _source(image, path, payload, member=member.name, offset=member.offset,
                                 label=f"RES group {member.group}")
                if extension == ".SCR" or payload.startswith(b"SCR_TYPE "):
                    if not payload.startswith(b"SCR_TYPE "):
                        raise ValueError(f"SCR member lacks its verified header: {path} / {member.name}")
                    add_text(payload, source, "complete_scr_plaintext")
                    counts["scr_members"] += 1
                else:
                    # Detect entire plain-text payloads without relying only on
                    # the filename suffix. Binary/control-filled bodies do not pass.
                    try:
                        decoded = payload.decode("cp949", errors="strict")
                    except UnicodeDecodeError:
                        decoded = ""
                    if is_printable_text(decoded):
                        add_text(payload, source, "other_complete_plaintext", require_printable=True)
                        embedded_text.append(source)
                    if extension in OPAQUE_EXTENSIONS:
                        record = {**source, "extension": extension}
                        key = (extension, source["sha256"])
                        if audit_unknown and key not in opaque_cache:
                            candidate_codes = set()
                            candidate_first = {}
                            candidate_count = 0
                            for start, raw, text in printable_cstrings(payload):
                                positions = list(cp949_code_positions(raw, font_codes))
                                if positions:
                                    candidate_count += 1
                                for position, code in positions:
                                    candidate_codes.add(code)
                                    candidate_first.setdefault(code, start + position)
                            raw_hits = raw_pair_hits(payload, font_codes)
                            opaque_cache[key] = (candidate_codes, candidate_first, candidate_count, raw_hits)
                        if audit_unknown:
                            candidates, witnesses, candidate_count, raw_hits = opaque_cache[key]
                            tiers["opaque_binary_cstring_candidates"].update(candidates)
                            tiers["opaque_binary_any_byte_pairs"].update(raw_hits)
                            for code, position in witnesses.items():
                                first["opaque_binary_cstring_candidates"].setdefault(code, _witness(
                                    source, payload, position, code, evidence="opaque binary coincidence; not a verified display reference"))
                            for code, position in raw_hits.items():
                                first["opaque_binary_any_byte_pairs"].setdefault(code, _witness(
                                    source, payload, position, code, evidence="arbitrary binary byte-pair; not text evidence"))
                            record.update({"printable_nul_candidates": candidate_count,
                                           "candidate_font_code_count": len(candidates),
                                           "arbitrary_byte_pair_code_count": len(raw_hits)})
                        opaque.append(record)
                    else:
                        excluded_types[extension or "<no suffix>"] += 1
        elif Path(path).suffix.upper() in TEXT_EXTENSIONS:
            payload = image.read(path)
            add_text(payload, _source(image, path, payload), "complete_disc_plaintext", require_printable=True)

    elf_sources = []
    for path, prefix in ((MAIN_ELF, "main_elf"), (AUXILIARY_ELF, "auxiliary_elf")):
        elf = image.read(path)
        expected = version["files"][path]
        if len(elf) != expected["size"] or digest(elf) != expected["sha256"]:
            raise ValueError(f"Executable changed during survey: {path}")
        segments = elf_load_segments(elf)
        for index, segment in enumerate(segments):
            payload = elf[segment["offset"]:segment["offset"] + segment["file_size"]]
            source = _source(image, path, payload, offset=segment["offset"], label=f"PT_LOAD {index}")
            text_counts = Counter()
            whole_codes = set()
            for start, raw, text in printable_cstrings(payload):
                positions = list(cp949_code_positions(raw, font_codes))
                text_counts["printable_nul_spans"] += 1
                if positions:
                    text_counts["font_key_nul_spans"] += 1
                for position, code in positions:
                    whole_codes.add(code)
                    first[prefix + "_printable_cstrings"].setdefault(code, _witness(
                        source, payload, start + position, code,
                        cstring_start_in_source=start, cstring_length=len(raw),
                        cstring_sha256=digest(raw), evidence="strict printable NUL-delimited CP949 candidate"))
            tiers[prefix + "_printable_cstrings"].update(whole_codes)
            suffix_codes = set()
            for position, code, end in suffix_code_candidates(payload, font_codes):
                suffix_codes.add(code)
                text_counts["suffix_font_key_occurrences"] += 1
                first[prefix + "_printable_suffixes"].setdefault(code, _witness(
                    source, payload, position, code, nul_offset_in_source=end,
                    evidence="strict printable CP949 NUL-terminated suffix candidate"))
            tiers[prefix + "_printable_suffixes"].update(suffix_codes)
            raw_hits = raw_pair_hits(payload, font_codes)
            tiers[prefix + "_any_byte_pairs"].update(raw_hits)
            for code, position in raw_hits.items():
                first[prefix + "_any_byte_pairs"].setdefault(code, _witness(
                    source, payload, position, code, evidence="arbitrary loaded byte-pair, including instruction/data coincidences"))
            elf_sources.append({**source, **segment, **text_counts,
                                "printable_nul_codes": _code_list(whole_codes),
                                "printable_suffix_codes": _code_list(suffix_codes),
                                "any_adjacent_byte_pair_codes": _code_list(raw_hits)})

    plaintext_tiers = ("complete_scr_plaintext", "complete_disc_plaintext", "other_complete_plaintext", "resource_names")
    survey_tiers = plaintext_tiers + ("main_elf_printable_cstrings", "main_elf_printable_suffixes",
                                     "auxiliary_elf_printable_cstrings", "auxiliary_elf_printable_suffixes")
    plaintext_codes = set().union(*(tiers[name] for name in plaintext_tiers))
    protected = frozenset().union(*(tiers[name] for name in survey_tiers))
    candidates = font_codes - protected
    raw_main_guard = plaintext_codes | tiers["main_elf_any_byte_pairs"]
    raw_both_guard = raw_main_guard | tiers["auxiliary_elf_any_byte_pairs"]
    raw_all_guard = raw_both_guard | tiers["opaque_binary_any_byte_pairs"]
    report = {
        "schema_version": 1,
        "method": "complete retained plaintext plus printable CP949 NUL candidates; unknown binary coincidences kept separate",
        "supported_version": version,
        "game_executed": False,
        "input_modified": False,
        "font": {"records": len(original_font), "non_ascii_slots": len(font_codes),
                 "source": "RES/SYSTEM.RES:FONT.FNT", "codes": _code_list(font_codes)},
        "counts": {**dict(sorted(counts.items())), "res_archives": len(archives),
                   "plaintext_used_codes": len(plaintext_codes), "protected_codes": len(protected),
                   "text_survey_candidate_codes": len(candidates), "opaque_members": len(opaque),
                   "unique_opaque_payloads_scanned": len(opaque_cache)},
        "protection": {"included_tiers": list(survey_tiers),
                       "protected_codes": _code_list(protected),
                       "candidate_codes": _code_list(candidates),
                       "candidate_status": "not observed in this retained-literal text survey; not globally proved idle",
                       "candidate_ranges_sha256": digest(b"".join(code.to_bytes(2, "big") for code in sorted(candidates))),
                       "fits_600": len(candidates) >= 600, "fits_1000": len(candidates) >= 1000,
                       "globally_proved_idle": False},
        "diagnostic_extremes": {
            "plaintext_only_candidate_count": len(font_codes - plaintext_codes),
            "plaintext_plus_any_main_load_byte_pair_candidate_count": len(font_codes - raw_main_guard),
            "plaintext_plus_any_both_elf_byte_pair_candidate_count": len(font_codes - raw_both_guard),
            "plaintext_plus_any_both_elf_and_opaque_byte_pair_candidate_count": len(font_codes - raw_all_guard) if audit_unknown else None,
            "opaque_binary_printable_candidate_code_count": len(tiers["opaque_binary_cstring_candidates"]),
            "note": "Arbitrary instruction/geometry/animation bytes are not glyph references. These limits measure over-conservative coincidences only."},
        "tier_codes": {name: _code_list(values) for name, values in sorted(tiers.items())},
        "first_code_witnesses": {name: {f"{code:04X}": evidence for code, evidence in sorted(values.items())}
                                 for name, values in sorted(first.items())},
        "plaintext_sources": sources,
        "res_member_name_sources_with_font_codes": all_resource_names,
        "res_archives": archives,
        "other_entire_plaintext_payloads": embedded_text,
        "elf_load_segments": elf_sources,
        "opaque_binary_audit": {"enabled": audit_unknown, "members": opaque,
                                "use_for_automatic_protection": False,
                                "reason": "Formats contain numeric geometry/animation/camera data and internal names; CP949-compatible byte patterns alone do not establish a renderer path."},
        "excluded_res_member_types": dict(sorted(excluded_types.items())),
        "confidence_boundaries": [
            "Complete CP949 plaintext includes every SCR byte, comments, nonquoted fields and DATA/AGREE.TXT; no translation-catalogue filter is used.",
            "ELF scans cover every file-backed PT_LOAD byte, including code; printable candidates may be instruction coincidences and are nevertheless reserved.",
            "NUL suffix candidates also cover strings with a non-text predecessor; unterminated, computed and non-CP949 strings are not established by this survey.",
            "Opaque GEO/ANI/BIN/SCN string-compatible patterns are diagnostic only until a format or renderer reference identifies them as display text.",
            "Texture/audio/font payloads are not text references. Image-baked text remains unchanged by glyph-slot replacement; NETGUI has separate PF fonts whose runtime relationship is not inferred here.",
            "Network/user-entered characters, runtime synthesis, decompressed text and paths not represented by surveyed literals can still use a candidate slot.",
            "Candidate allocation must be regenerated against the supported original, preserve every protected code and remain separate from in-game acceptance.",
        ],
    }
    return protected, report
