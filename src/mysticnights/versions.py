"""Disc identity checks shared by extraction, builds and verification."""
import hashlib
import json
from pathlib import Path

from .iso9660 import IsoImage, sha256_file


def load_version(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_original(path: Path, version: dict) -> IsoImage:
    actual_size = path.stat().st_size
    if actual_size != version["iso"]["size"]:
        raise ValueError(f"Unsupported disc size: {actual_size}")
    digest = sha256_file(path)
    if digest != version["iso"]["sha256"]:
        raise ValueError(f"Unsupported disc SHA-256: {digest}")
    image = IsoImage(path)
    for name, expected in version["files"].items():
        entry = image.get(name)
        if entry.size != expected["size"]:
            raise ValueError(f"Unsupported member size: {name}")
        if hashlib.sha256(image.read(name)).hexdigest() != expected["sha256"]:
            raise ValueError(f"Unsupported member SHA-256: {name}")
    return image
