"""Scan release metadata and packages for forbidden secret material."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

SECRET_NAME_PARTS = (".env", ".key", ".pem", ".p12", ".pfx", ".sqlite", ".db", "credentials")
SECRET_VALUE = re.compile(
    rb"(?i)(?:bearer|token|password|passwd|secret|api[_-]?key)\s*[:=]\s*[\"']?([A-Za-z0-9._~+/=-]{20,})"
)
RAW_BEARER = re.compile(rb"(?i)bearer\s+[A-Za-z0-9._~+/=-]{20,}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, required=True)
    args = parser.parse_args()
    release_dir = args.release_dir.resolve()
    if not release_dir.is_dir():
        raise SystemExit(f"release directory does not exist: {release_dir}")
    findings: list[str] = []
    for path in release_dir.rglob("*"):
        if not path.is_file():
            continue
        lowered_parts = {part.lower() for part in path.parts}
        if any(any(secret in part for secret in SECRET_NAME_PARTS) for part in lowered_parts):
            findings.append(f"forbidden secret-like filename: {path.relative_to(release_dir)}")
            continue
        data = path.read_bytes()
        if RAW_BEARER.search(data) or SECRET_VALUE.search(data):
            findings.append(f"credential-like value in: {path.relative_to(release_dir)}")
    if findings:
        raise SystemExit("release secret scan failed:\n" + "\n".join(findings))
    print("Release secret scan passed: no secret-like filenames or credential values found")


if __name__ == "__main__":
    main()
