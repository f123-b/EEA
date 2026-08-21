from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_script(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / name), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_release_manifest_hash_backend_and_secret_scan(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    release_dir = tmp_path / "release"
    input_dir.mkdir()
    (input_dir / "EEA-Desktop-v1.3.1-linux-x64.AppImage").write_bytes(b"linux package")
    (input_dir / "EEA-Desktop-v1.3.1-windows-x64.exe").write_bytes(b"windows package")
    for platform in ("linux-x64", "windows-x64"):
        (input_dir / f"build-metadata-{platform}.json").write_text(
            json.dumps(
                {
                    "frontend_size_bytes": 123,
                    "backend_size_bytes": 456,
                    "backend_bundled": True,
                    "backend_source": "BUNDLED_RESOURCE",
                }
            ),
            encoding="utf-8",
        )

    assembled = run_script(
        "create_release_manifest.py",
        "--input-dir",
        str(input_dir),
        "--output-dir",
        str(release_dir),
        "--commit",
        "test-commit",
    )
    assert assembled.returncode == 0, assembled.stderr
    validated = run_script(
        "validate_release_artifact.py",
        "--release-dir",
        str(release_dir),
        "--commit",
        "test-commit",
    )
    assert validated.returncode == 0, validated.stderr
    scanned = run_script("scan_release_secrets.py", "--release-dir", str(release_dir))
    assert scanned.returncode == 0, scanned.stderr

    manifest = json.loads((release_dir / "release-manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "1.3.1"
    assert manifest["backend"] == {
        "bundled": True,
        "development_path": None,
        "resource": "resources/eea-api*",
        "source": "BUNDLED_RESOURCE",
    }
    assert len(manifest["artifacts"]) == 2
    assert all(len(item["sha256"]) == 64 for item in manifest["artifacts"])


def test_release_secret_scan_rejects_bearer_token(tmp_path: Path) -> None:
    release_dir = tmp_path / "release"
    release_dir.mkdir()
    (release_dir / "leak.txt").write_text(
        "Authorization: Bearer abcdefghijklmnopqrstuv",
        encoding="utf-8",
    )
    scanned = run_script("scan_release_secrets.py", "--release-dir", str(release_dir))
    assert scanned.returncode != 0
