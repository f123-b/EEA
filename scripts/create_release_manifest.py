"""Assemble normalized desktop artifacts, hashes, manifest, and size report."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--version", default="1.3.1")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata: dict[str, dict[str, object]] = {}
    artifacts: list[dict[str, object]] = []
    checksums: list[str] = []
    for platform in PLATFORMS:
        name = package_name(args.version, platform)
        source = input_dir / name
        if not source.is_file():
            raise SystemExit(f"missing collected release artifact: {source}")
        target = output_dir / name
        shutil.copy2(source, target)
        metadata_path = input_dir / f"build-metadata-{platform}.json"
        if metadata_path.is_file():
            metadata[platform] = json.loads(metadata_path.read_text(encoding="utf-8"))
        digest = sha256(target)
        size = target.stat().st_size
        checksums.append(f"{digest}  {name}")
        artifacts.append(
            {
                "name": name,
                "platform": platform,
                "format": "AppImage" if platform == "linux-x64" else "NSIS installer",
                "size_bytes": size,
                "sha256": digest,
            }
        )

    package_sizes = {item["platform"]: item["size_bytes"] for item in artifacts}
    frontend_sizes = [int(item.get("frontend_size_bytes", 0)) for item in metadata.values()]
    backend_sizes = [int(item.get("backend_size_bytes", 0)) for item in metadata.values()]
    baseline_report: dict[str, object] | None = None
    growth_warnings: list[str] = []
    current_sizes = {
        "frontend_bytes": max(frontend_sizes, default=0),
        "backend_bytes": max(backend_sizes, default=0),
    }
    if args.baseline:
        baseline_path = args.baseline.resolve()
        if not baseline_path.is_file():
            growth_warnings.append(f"size baseline was requested but not found: {baseline_path}")
        else:
            baseline_report = json.loads(baseline_path.read_text(encoding="utf-8"))
            for key in ("frontend_bytes", "backend_bytes"):
                previous = int(baseline_report.get(key, 0))
                current = current_sizes[key]
                if previous and current > previous * 1.25:
                    growth_warnings.append(f"{key} grew above the 25% review threshold")
            previous_packages = baseline_report.get("package_bytes", {})
            if isinstance(previous_packages, dict):
                for platform, current in package_sizes.items():
                    previous = int(previous_packages.get(platform, 0))
                    if previous and int(current) > previous * 1.25:
                        growth_warnings.append(
                            f"{platform} package grew above the 25% review threshold"
                        )
    else:
        growth_warnings.append(
            "no previous release size baseline supplied; manual growth review is required"
        )

    size_report = {
        "frontend_bytes": current_sizes["frontend_bytes"],
        "backend_bytes": current_sizes["backend_bytes"],
        "package_bytes": package_sizes,
        "total_artifact_bytes": sum(int(item["size_bytes"]) for item in artifacts),
        "baseline": str(args.baseline) if args.baseline else None,
        "growth_warnings": growth_warnings,
        "growth_policy": (
            "Review frontend/backend/package growth against the previous release before publishing."
        ),
    }
    (output_dir / "release-size-report.json").write_text(
        json.dumps(size_report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "product": PRODUCT,
        "version": args.version,
        "commit": args.commit,
        "build_time_utc": (
            datetime.now(timezone.utc)  # noqa: UP017
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        ),
        "platforms": list(PLATFORMS),
        "backend": {
            "bundled": True,
            "source": "BUNDLED_RESOURCE",
            "resource": "resources/eea-api*",
            "development_path": None,
        },
        "artifacts": artifacts,
        "size_report": "release-size-report.json",
        "checksums": "SHA256SUMS.txt",
    }
    (output_dir / "release-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for warning in growth_warnings:
        print(f"WARNING: {warning}")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
