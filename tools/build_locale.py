"""Build a separate localization validation ISO; never starts a game/emulator."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from _bootstrap import ROOT
from mysticnights.font import render_preview
from mysticnights.iso9660 import replace_files
from mysticnights.localization import load_catalogue, localized_resources
from mysticnights.patch import build_patch
from mysticnights.versions import load_version, verify_original


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", required=True, type=Path)
    parser.add_argument("--locale", default="zh-CN")
    parser.add_argument("--output", type=Path, default=ROOT / "build/poc")
    parser.add_argument("--font", type=Path)
    parser.add_argument("--release", action="store_true")
    args = parser.parse_args()
    if args.release:
        parser.error("Full-release generation is not enabled: the current profile is a runtime proof of concept")
    if not args.locale or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for c in args.locale):
        parser.error("Invalid locale identifier")
    locale_dir = ROOT / "locales" / args.locale
    config = json.loads((locale_dir / "config.json").read_text(encoding="utf-8"))
    catalogue_path = locale_dir / config["translations"]
    catalogue = load_catalogue(catalogue_path)
    if catalogue["locale"] != args.locale or config["locale"] != args.locale:
        raise ValueError("Locale configuration/catalogue mismatch")
    version = load_version(ROOT / "assets/game-version.json")
    elf_recipe = json.loads((ROOT / "assets/elf-text-slots.json").read_text(encoding="utf-8"))
    font_spec = json.loads((ROOT / config["font_spec"]).read_text(encoding="utf-8"))
    font_path = args.font or ROOT / "build/fonts" / font_spec["filename"]
    iso_name = f"Mystic-Nights-{args.locale}-poc.iso"
    if args.output.exists():
        raise FileExistsError(f"Use a new output directory: {args.output}")
    image = verify_original(args.iso, version)
    replacements, font, protected = localized_resources(image, catalogue, config, font_spec, font_path, elf_recipe)
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
        manifest = {"profile": "poc", "status": "awaiting-user-runtime-test", "locale": args.locale,
                "localized_title": config.get("title", "Mystic Nights"),
                "original": version["iso"], "modified": {"size": result["size"], "sha256": result["sha256"]},
                "changed_files": result["replacements"], "entries": catalogue["entries"],
                "font": {"name": font_spec["name"], "sha256": font.font_sha256,
                         "pixel_size": config["font_pixel_size"], "mapping": font.mapping,
                         "protected_jamo_codes": protected},
                "catalogue_sha256": hashlib.sha256(catalogue_path.read_bytes()).hexdigest(),
                "sparse_ranges": len(patch["ranges"])}
        write_json(work / "manifest.json", manifest)
        preview_text = "\n".join(row["target"] for row in catalogue["entries"])
        preview = render_preview(font.fnt, font.textures, preview_text, font.mapping, scale=3)
        from PIL import Image
        background = Image.new("RGBA", preview.size, (24, 28, 32, 255))
        background.alpha_composite(preview)
        background.convert("RGB").save(work / "font-preview.png")
        # The target is checked again after generation to avoid replacing a
        # concurrently created output directory, even an empty one.
        if args.output.exists():
            raise FileExistsError(f"Output appeared during build: {args.output}")
        work.rename(args.output)
    print(f"BUILD profile=poc strings={len(catalogue['entries'])} glyphs={len(font.mapping)} changed_files={len(replacements)}")
    print(f"OUTPUT sha256={result['sha256']} size={result['size']}")
    print(f"ISO {args.output.resolve() / iso_name}")


if __name__ == "__main__":
    main()
