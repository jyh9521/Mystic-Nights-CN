"""Build a separate localization validation ISO; never starts a game/emulator."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import textwrap

from _bootstrap import ROOT
from mysticnights.font import render_preview
from mysticnights.iso9660 import replace_files
from mysticnights.localization import load_catalogue, localized_resources
from mysticnights.patch import build_patch
from mysticnights.versions import load_version, verify_original
from mysticnights.auxiliary import read_auxiliary, extra_elf_entries, patch_auxiliary_slots, merge_resource_edits


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", required=True, type=Path)
    parser.add_argument("--locale", default="zh-CN")
    parser.add_argument("--output", type=Path, default=ROOT / "build/full-text")
    parser.add_argument("--font", type=Path)
    parser.add_argument("--release", action="store_true")
    args = parser.parse_args()
    if args.release:
        parser.error("This creates a validation build; final gameplay acceptance is required before release")
    if not args.locale or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for c in args.locale):
        parser.error("Invalid locale identifier")
    locale_dir = ROOT / "locales" / args.locale
    config = json.loads((locale_dir / "config.json").read_text(encoding="utf-8"))
    catalogue_path = locale_dir / config["translations"]
    catalogue = load_catalogue(catalogue_path)
    if catalogue["locale"] != args.locale or config["locale"] != args.locale:
        raise ValueError("Locale configuration/catalogue mismatch")
    if config.get("profile", catalogue["profile"]) != catalogue["profile"]:
        raise ValueError("Build profile/catalogue mismatch")
    version = load_version(ROOT / "assets/game-version.json")
    elf_recipe = json.loads((ROOT / "assets/elf-text-slots.json").read_text(encoding="utf-8"))
    font_spec = json.loads((ROOT / config["font_spec"]).read_text(encoding="utf-8"))
    font_path = args.font or ROOT / "build/fonts" / font_spec["filename"]
    iso_name = f"Mystic-Nights-{args.locale}-{catalogue['profile']}.iso"
    if args.output.exists():
        raise FileExistsError(f"Use a new output directory: {args.output}")
    image = verify_original(args.iso, version)
    if catalogue["profile"] in {"partial", "full-text"}:
        from validate_translations import validate_project
        validate_project(locale_dir, image)
    full_details, name_targets, plaintext = {}, None, None
    if catalogue["profile"] == "full-text":
        auxiliary = read_auxiliary(locale_dir, config, json.loads((ROOT / "assets/auxiliary-text-sources.json").read_text(encoding="utf8")), image)
        extra = extra_elf_entries(auxiliary["extra_interface"])
        catalogue = {**catalogue, "entries": catalogue["entries"] + extra}
        elf_recipe = {**elf_recipe, "entries": elf_recipe["entries"] + extra}
        names = json.loads((locale_dir / config["names"]).read_text(encoding="utf8"))["entries"]
        name_targets = {r["id"]: r["target"] for r in names}
        plaintext = {r["resource"]: r for r in auxiliary["agreement"]}
        full_details = {"names": names, "auxiliary": auxiliary}
    replacements, font, protected = localized_resources(image, catalogue, config, font_spec, font_path, elf_recipe,
                                                         version=version, name_targets=name_targets, plaintext_replacements=plaintext)
    if catalogue["profile"] == "full-text":
        from mysticnights.font import encode_text
        from mysticnights.linked_names import discover_name_links, patch_linked_names
        from mysticnights.network_font import build_network_font, collect_protected_codepoints, encode_text as encode_network
        links = discover_name_links(image)
        full_details["name_links_sha256"] = links["core_sha256"]
        full_details["name_links_summary"] = links["summary"]
        name_changes = patch_linked_names(image, links, name_targets, lambda text: encode_text(text, font.mapping))
        for name, data in name_changes.items():
            replacements[name] = merge_resource_edits(image.read(name), replacements.get(name, image.read(name)), data)
        replacements["DATA/AGREE.TXT"] = patch_auxiliary_slots(image.read("DATA/AGREE.TXT"), auxiliary["agreement"],
                                                               lambda text: encode_text(text, font.mapping), plain=True)
        network_protected = collect_protected_codepoints(image.read("NETGUICD.ELF"))
        network_font = build_network_font(image.read("NETGUI/KOREAN.PF"), [r["target"] for r in auxiliary["network"]],
                                          font_path, font_spec["sha256"], protected_codepoints=network_protected)
        replacements["NETGUI/KOREAN.PF"] = network_font.data
        replacements["NETGUICD.ELF"] = patch_auxiliary_slots(image.read("NETGUICD.ELF"), auxiliary["network"],
                                                             lambda text: encode_network(text, network_font.mapping))
        full_details["network_font"] = {"mapping": network_font.mapping, "changed_glyphs": network_font.changed_glyphs,
                                        "source_sha256": network_font.source_sha256, "font_sha256": network_font.font_sha256,
                                        "pixel_size": network_font.pixel_size, "protected_codepoints": sorted(network_protected)}
        from mysticnights.save_metadata import build_save_metadata
        metadata_recipe = json.loads((ROOT / "assets/save-metadata-slots.json").read_text(encoding="utf8"))
        metadata_catalogue = json.loads((locale_dir / config["save_metadata"]).read_text(encoding="utf8"))
        if metadata_catalogue["locale"] != args.locale:
            raise ValueError("Save metadata locale mismatch")
        replacements.update(build_save_metadata(image, metadata_recipe, metadata_catalogue))
        full_details["save_metadata"] = {"recipe": metadata_recipe, "catalogue": metadata_catalogue}
        from mysticnights.graphics import build_graphics
        from mysticnights.artwork import load_graphics_catalogue
        graphics_recipe = json.loads((ROOT / "assets/graphics-text-slots.json").read_text(encoding="utf8"))
        graphics_catalogue = load_graphics_catalogue(locale_dir / config["graphics"])
        if graphics_catalogue["locale"] != args.locale or graphics_recipe["source_iso_sha256"] != version["iso"]["sha256"]:
            raise ValueError("Graphics locale/original version mismatch")
        replacements, graphics_report = build_graphics(image, graphics_recipe, graphics_catalogue, font_path, replacements)
        full_details["graphics"] = {"recipe": graphics_recipe, "catalogue": graphics_catalogue, "report": graphics_report}
        if config.get("raw_images"):
            from mysticnights.raw_images import build_raw_images
            raw_recipe = json.loads((ROOT / "assets/raw-image-slots.json").read_text(encoding="utf8"))
            raw_catalogue = load_graphics_catalogue(locale_dir / config["raw_images"])
            if raw_catalogue["locale"] != args.locale or raw_recipe["source_iso_sha256"] != version["iso"]["sha256"]:
                raise ValueError("Raw image locale/original version mismatch")
            replacements, raw_report = build_raw_images(image, raw_recipe, raw_catalogue, replacements)
            full_details["raw_images"] = {"recipe": raw_recipe, "catalogue": raw_catalogue, "report": raw_report}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    parent = args.output.parent.resolve()
    # Only a newly allocated sibling directory is ever cleaned on failure.
    # Existing outputs (including the original ISO) are never overwritten.
    with tempfile.TemporaryDirectory(prefix=f".{args.output.name}-", dir=parent) as temporary:
        work = Path(temporary).resolve()
        if work.parent != parent or args.output.resolve().parent != parent:
            raise ValueError("Transactional output escaped its intended parent")
        result = replace_files(args.iso, work / iso_name, replacements,
                               expected_sha256=version["iso"]["sha256"], expected_size=version["iso"]["size"])
        patch = build_patch(args.iso, work / iso_name, work / "DIFF_FILE.mnp.zip")
        art_pending = bool(full_details.get("graphics", {}).get("report", {}).get("pending_art_restoration_slots", []))
        manifest = {"profile": catalogue["profile"], "status": "awaiting-art-review-and-runtime-test" if art_pending else "awaiting-user-runtime-test", "locale": args.locale,
                "localized_title": config.get("title", "Mystic Nights"),
                "original": version["iso"], "modified": {"size": result["size"], "sha256": result["sha256"]},
                "changed_files": result["replacements"], "entries": catalogue["entries"],
                "font": {"name": font_spec["name"], "sha256": font.font_sha256,
                         "pixel_size": config["font_pixel_size"], "mapping": font.mapping,
                         "protection_policy": config.get("font_protection", "poc-source-text"),
                         "protected_codes": protected},
                "catalogue_sha256": hashlib.sha256(catalogue_path.read_bytes()).hexdigest(),
                "catalogue_files_sha256": catalogue.get("catalogue_files_sha256", {}),
                "coverage": catalogue.get("coverage", {}),
                "full_text": full_details,
                "sparse_ranges": len(patch["ranges"])}
        write_json(work / "manifest.json", manifest)
        by_id = {row["id"]: row for row in catalogue["entries"]}
        preview_ids = config.get("preview_ids", list(by_id))
        if not preview_ids or len(set(preview_ids)) != len(preview_ids) or any(i not in by_id for i in preview_ids):
            raise ValueError("Preview must select existing translated IDs")
        # Preview wrapping affects only this image, never the runtime strings.
        preview_lines = []
        for identifier in preview_ids:
            for line in by_id[identifier]["target"].replace("<BR>", "\n").splitlines():
                preview_lines.extend(textwrap.wrap(line, width=36, break_long_words=True, break_on_hyphens=False) or [""])
        if full_details:
            auxiliary_by_id = {r["id"]: r for r in auxiliary["agreement"]}
            for selection in config.get("preview_auxiliary_lines", []):
                if selection["id"] not in auxiliary_by_id:
                    raise ValueError("Unknown auxiliary preview ID")
                lines = auxiliary_by_id[selection["id"]]["target"].split("\r\r\n")
                for index in selection["lines"]:
                    if type(index) is not int or not 0 <= index < len(lines):
                        raise ValueError("Invalid auxiliary preview line")
                    preview_lines.append(lines[index])
        preview_text = "\n".join(preview_lines)
        preview = render_preview(font.fnt, font.textures, preview_text, font.mapping, scale=3)
        from PIL import Image
        background = Image.new("RGBA", preview.size, (24, 28, 32, 255))
        background.alpha_composite(preview)
        background.convert("RGB").save(work / "font-preview.png")
        if full_details:
            from mysticnights.network_font import render_preview as render_network_preview
            # Actual translated rows, sampled at the PF's native 26px cell size.
            selected = [auxiliary["network"][i]["target"] for i in (128, 124, 0, 171)]
            network_preview = render_network_preview(network_font.data, "\n".join(selected), network_font.mapping, scale=2)
            backdrop = Image.new("RGBA", network_preview.size, (24, 28, 32, 255))
            backdrop.alpha_composite(network_preview)
            backdrop.convert("RGB").save(work / "network-font-preview.png")
        (work / "ROLLBACK.sh").write_text(
            '#!/usr/bin/env bash\nset -euo pipefail\n'
            'HERE="$(cd -- "$(dirname -- "$0")" && pwd)"\n'
            'ROOT="$HERE"\n'
            'while [ ! -f "$ROOT/tools/apply_patch.py" ]; do\n'
            '  PARENT="$(dirname -- "$ROOT")"\n'
            '  if [ "$PARENT" = "$ROOT" ]; then echo "Place this build inside a project checkout" >&2; exit 2; fi\n'
            '  ROOT="$PARENT"\n'
            'done\n'
            'if [ "$#" -ne 2 ]; then echo "usage: ROLLBACK.sh modified-copy.iso restored-new.iso" >&2; exit 2; fi\n'
            'python -X utf8 "$ROOT/tools/apply_patch.py" --reverse --input "$1" --patch "$HERE/DIFF_FILE.mnp.zip" --output "$2"\n',
            encoding="utf8", newline="\n")
        # The target is checked again after generation to avoid replacing a
        # concurrently created output directory, even an empty one.
        if args.output.exists():
            raise FileExistsError(f"Output appeared during build: {args.output}")
        work.rename(args.output)
    print(f"BUILD profile={catalogue['profile']} strings={len(catalogue['entries'])} glyphs={len(font.mapping)} changed_files={len(replacements)}")
    print(f"OUTPUT sha256={result['sha256']} size={result['size']}")
    print(f"ISO {args.output.resolve() / iso_name}")


if __name__ == "__main__":
    main()
