"""Collect one platform's real Tauri bundle under the release artifact name."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def find_bundle(bundle_root: Path, platform: str) -> Path:
    if "debug" in bundle_root.parts or bundle_root.name != "bundle":
        raise SystemExit(f"release collection requires a release bundle directory: {bundle_root}")
    subdir = bundle_root / ("appimage" if platform == "linux-x64" else "nsis")
    suffix = ".AppImage" if platform == "linux-x64" else ".exe"
    candidates = sorted(path for path in subdir.glob(f"*{suffix}") if path.is_file())
    if len(candidates) != 1:
        raise SystemExit(f"expected one {platform} Tauri bundle in {subdir}, found {candidates}")
    return candidates[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle-root",
        type=Path,
        default=ROOT / "apps/desktop/src-tauri/target/release/bundle",
    )
    parser.add_argument("--platform", choices=("linux-x64", "windows-x64"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", default="1.3.1")
    args = parser.parse_args()

    bundle_root = args.bundle_root.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    package = find_bundle(bundle_root, args.platform)
    extension = ".AppImage" if args.platform == "linux-x64" else ".exe"
    target = output / f"EEA-Desktop-v{args.version}-{args.platform}{extension}"
    shutil.copy2(package, target)

    backend_name = "eea-api.exe" if args.platform == "windows-x64" else "eea-api"
    backend = ROOT / "apps/desktop/src-tauri/resources" / backend_name
    metadata = {
        "platform": args.platform,
        "artifact": target.name,
        "package_size_bytes": target.stat().st_size,
        "package_sha256": sha256(target),
        "frontend_size_bytes": directory_size(ROOT / "apps/desktop/dist"),
        "backend_size_bytes": backend.stat().st_size if backend.is_file() else 0,
        "backend_resource": f"resources/{backend_name}",
        "backend_bundled": True,
        "backend_source": "BUNDLED_RESOURCE",
    }
    (output / f"build-metadata-{args.platform}.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"Collected {target.name} ({target.stat().st_size} bytes, "
        f"sha256 {metadata['package_sha256']})"
    )


if __name__ == "__main__":
    main()
