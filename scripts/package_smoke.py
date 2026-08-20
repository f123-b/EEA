"""Launch the final Tauri AppImage and verify bundled-backend renderer readiness."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

REQUIRED_TRUE_FIELDS = (
    "desktop_started",
    "backend_authenticated",
    "unauthenticated_rejected",
    "renderer_ready",
    "workbench_ready",
    "backend_loopback",
    "sidecar_auto_started",
    "url_clean",
    "storage_clean",
    "dom_clean",
    "token_leak_scan_pass",
)
TOKEN_PATTERN = re.compile(r"(?:Authorization:\s*Bearer|session_token|\b[0-9a-f]{64}\b)", re.I)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_appimage(package: Path, destination: Path) -> tuple[Path, Path]:
    completed = subprocess.run(
        [str(package), "--appimage-extract"],
        cwd=destination,
        env={**os.environ, "APPIMAGE_EXTRACT_AND_RUN": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(f"AppImage extraction failed: {completed.stderr[-2000:]}")
    root = destination / "squashfs-root"
    candidates = [
        path
        for path in root.rglob("eea-api")
        if path.is_file() and "resources" in {part.lower() for part in path.parts}
    ]
    if len(candidates) != 1:
        raise SystemExit(f"expected one bundled resources/eea-api, found: {candidates}")
    return root, candidates[0]


def endpoint_closed(endpoint: str) -> bool:
    host_port = endpoint.removeprefix("http://")
    host, port_text = host_port.rsplit(":", 1)
    try:
        with socket.create_connection((host, int(port_text)), timeout=0.5):
            return False
    except OSError:
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()

    package = args.package.resolve()
    evidence_dir = args.evidence_dir.resolve()
    if not package.is_file():
        raise SystemExit(f"Tauri AppImage does not exist: {package}")
    if not os.access(package, os.X_OK):
        raise SystemExit(f"Tauri AppImage is not executable: {package}")
    xvfb_run = shutil.which("xvfb-run")
    if not xvfb_run:
        raise SystemExit("xvfb-run is required for the packaged desktop launch gate")

    clean_path = os.pathsep.join(("/usr/bin", "/bin"))
    if shutil.which("eea-api", path=clean_path):
        raise SystemExit("clean package smoke PATH unexpectedly provides eea-api")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    readiness = evidence_dir / "desktop-ready.json"
    stdout_path = evidence_dir / "desktop-stdout.log"
    stderr_path = evidence_dir / "desktop-stderr.log"

    with tempfile.TemporaryDirectory(prefix="eea-appimage-inspect-") as inspect_dir:
        extracted_root, bundled_backend = extract_appimage(package, Path(inspect_dir))
        bundled_relative = bundled_backend.relative_to(extracted_root).as_posix()
        bundled_hash = sha256(bundled_backend)

    with tempfile.TemporaryDirectory(prefix="eea-packaged-runtime-") as runtime_dir:
        env = os.environ.copy()
        for key in (
            "EEA_BACKEND_EXECUTABLE",
            "EEA_SESSION_TOKEN",
            "EEA_RUNTIME_HOST",
            "EEA_RUNTIME_PORT",
            "PYTHONPATH",
            "VITE_EEA_API_URL",
            "VITE_EEA_SESSION_TOKEN",
        ):
            env.pop(key, None)
        env.update(
            {
                "PATH": clean_path,
                "APPIMAGE_EXTRACT_AND_RUN": "1",
                "EEA_DATA_DIR": runtime_dir,
                "EEA_ENV": "production",
                "EEA_INSECURE_LOCAL_DEV": "false",
                "EEA_DESKTOP_SMOKE_EVIDENCE_FILE": str(readiness),
                "WEBKIT_DISABLE_COMPOSITING_MODE": "1",
                "LIBGL_ALWAYS_SOFTWARE": "1",
            }
        )
        with (
            stdout_path.open("w", encoding="utf-8") as stdout,
            stderr_path.open("w", encoding="utf-8") as stderr,
        ):
            process = subprocess.Popen(
                [xvfb_run, "-a", str(package)],
                cwd=package.parent,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                text=True,
            )
            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline and not readiness.is_file():
                if process.poll() is not None:
                    raise SystemExit(
                        f"packaged desktop exited before readiness ({process.returncode})"
                    )
                time.sleep(0.1)
            if not readiness.is_file():
                process.terminate()
                process.wait(timeout=10)
                raise SystemExit("packaged desktop did not publish renderer readiness")
            time.sleep(0.5)
            if process.poll() is not None:
                raise SystemExit("packaged desktop did not stay alive after renderer readiness")
            try:
                return_code = process.wait(timeout=20)
            except subprocess.TimeoutExpired as error:
                process.terminate()
                process.wait(timeout=10)
                raise SystemExit(
                    "packaged desktop did not terminate cleanly after smoke"
                ) from error
            if return_code != 0:
                raise SystemExit(f"packaged desktop clean exit returned {return_code}")

        evidence = json.loads(readiness.read_text(encoding="utf-8"))
        missing = [field for field in REQUIRED_TRUE_FIELDS if evidence.get(field) is not True]
        if missing:
            raise SystemExit(f"packaged desktop readiness fields did not pass: {missing}")
        if evidence.get("source") != "BUNDLED_RESOURCE":
            raise SystemExit(f"backend source is not bundled: {evidence.get('source')}")
        if evidence.get("backend_basename") != "eea-api":
            raise SystemExit(f"unexpected backend basename: {evidence.get('backend_basename')}")
        if evidence.get("runtime_session_source") != "TAURI_IPC":
            raise SystemExit("renderer did not obtain its session through Tauri IPC")
        endpoint = str(evidence.get("backend_endpoint", ""))
        if not endpoint.startswith("http://127.0.0.1:"):
            raise SystemExit(f"backend endpoint is not loopback: {endpoint}")
        if not endpoint_closed(endpoint):
            raise SystemExit("bundled backend remained reachable after clean desktop termination")

        logs_and_evidence = "\n".join(
            (
                stdout_path.read_text(encoding="utf-8", errors="replace"),
                stderr_path.read_text(encoding="utf-8", errors="replace"),
                readiness.read_text(encoding="utf-8"),
            )
        )
        if TOKEN_PATTERN.search(logs_and_evidence):
            raise SystemExit("credential-like material appeared in package smoke output")

        summary = {
            **evidence,
            "tauri_package": package.name,
            "tauri_package_sha256": sha256(package),
            "packaged_executable_launched": True,
            "bundled_backend_relative_path": bundled_relative,
            "bundled_backend_sha256": bundled_hash,
            "development_path_eea_api": None,
            "clean_termination": True,
            "backend_closed_after_exit": True,
            "token_leak_scan": "PASS",
        }
        (evidence_dir / "package-launch-summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
        )
        print("Desktop package launch smoke passed: bundled backend and renderer ready")


if __name__ == "__main__":
    main()
