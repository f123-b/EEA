"""Validate the normalized desktop release directory and its manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

PRODUCT = "Embedded Engineering Agent"
PLATFORMS = ("linux-x64", "windows-x64")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_name(version: str, platform: str) -> str:
    extension = ".AppImage" if platform == "linux-x64" else ".exe"
    return f"EEA-Desktop-v{version}-{platform}{extension}"


def fail(message: str) -> None:
    raise SystemExit(f"release artifact validation failed: {message}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--version", default="1.3.1")
    parser.add_argument("--commit")
    args = parser.parse_args()
    release_dir = args.release_dir.resolve()
    manifest_path = release_dir / "release-manifest.json"
    sums_path = release_dir / "SHA256SUMS.txt"
    if not manifest_path.is_file() or not sums_path.is_file():
        fail("release-manifest.json and SHA256SUMS.txt are required")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail(f"invalid release manifest: {error}")

    if manifest.get("product") != PRODUCT:
        fail(f"unexpected product: {manifest.get('product')!r}")
    if manifest.get("version") != args.version:
        fail(f"unexpected version: {manifest.get('version')!r}")
    if args.commit and manifest.get("commit") != args.commit:
        fail("manifest commit does not match the build commit")
    if manifest.get("platforms") != list(PLATFORMS):
        fail(f"platform list must be {list(PLATFORMS)!r}")
    backend = manifest.get("backend")
    if (
        not isinstance(backend, dict)
        or backend.get("bundled") is not True
        or backend.get("source") != "BUNDLED_RESOURCE"
    ):
        fail("backend must be marked bundled from BUNDLED_RESOURCE")
    if backend.get("development_path") is not None:
        fail("development backend path must be null")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != len(PLATFORMS):
        fail("manifest must contain exactly one artifact per platform")
    expected: dict[str, dict[str, object]] = {}
    for platform in PLATFORMS:
        name = package_name(args.version, platform)
        path = release_dir / name
        if not path.is_file() or path.stat().st_size <= 0:
            fail(f"missing or empty artifact: {name}")
        if "debug" in path.parts or "node_modules" in path.parts:
            fail(f"development content is present in artifact path: {path}")
        expected[name] = {
            "platform": platform,
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
        }

    by_name = {str(item.get("name")): item for item in artifacts if isinstance(item, dict)}
    if set(by_name) != set(expected):
        fail("manifest artifact names do not match the normalized release directory")
    for name, actual in expected.items():
        item = by_name[name]
        if (
            item.get("platform") != actual["platform"]
            or item.get("size_bytes") != actual["size_bytes"]
            or item.get("sha256") != actual["sha256"]
        ):
            fail(f"manifest metadata does not match {name}")

    checksum_lines = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            fail(f"malformed checksum line: {line!r}")
        checksum_lines[parts[1].removeprefix("*")] = parts[0]
    if checksum_lines != {name: str(item["sha256"]) for name, item in expected.items()}:
        fail("SHA256SUMS.txt does not match the packaged artifacts")

    forbidden = {"node_modules", "debug", "target", ".env", ".key", ".pem", ".sqlite", ".db"}
    for path in release_dir.rglob("*"):
        if any(part.lower() in forbidden for part in path.parts):
            fail(f"forbidden development or secret path in release directory: {path}")
        if path.is_file() and path.suffix.lower() in {".zip", ".tar", ".gz", ".7z"}:
            fail(f"source archive is not allowed in release directory: {path.name}")
    print(f"Release artifacts validated: {', '.join(expected)}")


if __name__ == "__main__":
    main()
