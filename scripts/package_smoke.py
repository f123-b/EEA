"""Launch a packaged backend sidecar and verify the authenticated runtime contract."""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    args = parser.parse_args()
    executable = args.executable.resolve()
    if not executable.is_file():
        raise SystemExit(f"sidecar does not exist: {executable}")

    port = free_port()
    token = "m21-package-smoke-token"
    env = os.environ.copy()
    env.update(
        {
            "EEA_RUNTIME_HOST": "127.0.0.1",
            "EEA_RUNTIME_PORT": str(port),
            "EEA_SESSION_TOKEN": token,
            "EEA_ENV": "development",
            "EEA_INSECURE_LOCAL_DEV": "false",
        }
    )
    with tempfile.TemporaryDirectory(
        prefix="eea-package-smoke-", ignore_cleanup_errors=True
    ) as data_dir:
        env["EEA_DATA_DIR"] = data_dir
        process = subprocess.Popen(
            [str(executable)],
            cwd=executable.parent,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        base_url = f"http://127.0.0.1:{port}"
        try:
            deadline = time.monotonic() + 30
            response_body: bytes | None = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise SystemExit(f"sidecar exited early with code {process.returncode}")
                try:
                    request = Request(
                        f"{base_url}/api/v1/meta/version",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    with urlopen(request, timeout=1) as response:
                        if response.status == 200:
                            response_body = response.read()
                            break
                except OSError:
                    time.sleep(0.1)
            if response_body is None:
                raise SystemExit("sidecar did not complete the authenticated version handshake")
            if b'"success":true' not in response_body.replace(b" ", b"").lower():
                raise SystemExit(f"unexpected version envelope: {response_body!r}")

            try:
                urlopen(f"{base_url}/api/v1/meta/version", timeout=2)
            except HTTPError as error:
                if error.code not in {401, 403}:
                    raise SystemExit(
                        f"unauthenticated request returned HTTP {error.code}"
                    ) from error
            else:
                raise SystemExit("unauthenticated request unexpectedly succeeded")
            print(f"Package smoke passed: authenticated sidecar at {base_url}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


if __name__ == "__main__":
    main()
