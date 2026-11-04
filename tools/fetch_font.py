"""Fetch the one hash-pinned open font; no game or emulator files are fetched."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

from _bootstrap import ROOT


def fetch(url: str, destination: Path, expected: str) -> None:
    if destination.exists():
        data = destination.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"Existing file has wrong SHA-256: {destination}")
        print(f"VERIFIED {destination.name} sha256={expected}")
        return
    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read(30 * 1024 * 1024 + 1)
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"Downloaded file has wrong SHA-256: {destination.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with destination.open("xb") as stream:
            created = True
            stream.write(data)
        if hashlib.sha256(destination.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Written file has wrong SHA-256: {destination.name}")
    except BaseException:
        if created:
            destination.unlink(missing_ok=True)
        raise
    print(f"FETCHED {destination.name} sha256={expected}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/fonts")
    args = parser.parse_args()
    spec = json.loads((ROOT / "assets/font-source.json").read_text(encoding="utf-8"))
    fetch(spec["url"], args.output / spec["filename"], spec["sha256"])
    fetch(spec["license_url"], args.output / "OFL.txt", spec["license_sha256"])


if __name__ == "__main__":
    main()
