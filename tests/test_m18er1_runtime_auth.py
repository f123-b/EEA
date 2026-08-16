"""Real backend-child authentication checks for the desktop runtime boundary."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from secrets import token_urlsafe

import httpx


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def test_runtime_backend_child_requires_ephemeral_bearer(tmp_path: Path) -> None:
    port = _free_port()
    token = token_urlsafe(32)
    environment = {
        **os.environ,
        "EEA_RUNTIME_HOST": "127.0.0.1",
        "EEA_RUNTIME_PORT": str(port),
        "EEA_SESSION_TOKEN": token,
        "EEA_DATA_DIR": str(tmp_path),
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "eea_backend"],
        cwd=Path(__file__).parents[1],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        url = f"http://127.0.0.1:{port}/api/v1/meta/version"
        response: httpx.Response | None = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError("backend child exited before readiness")
            try:
                response = httpx.get(url, timeout=0.5)
                break
            except httpx.HTTPError:
                time.sleep(0.05)
        assert response is not None
        assert response.status_code == 401
        assert httpx.get(url, headers={"Authorization": "Bearer wrong"}).status_code == 401
        authenticated = httpx.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=2,
        )
        assert authenticated.status_code == 200, authenticated.text
        assert "token=" not in str(authenticated.request.url)
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_tauri_renderer_runtime_has_no_persistent_token_boundary() -> None:
    root = Path(__file__).parents[1] / "apps" / "desktop" / "src"
    client = (root / "api" / "client.ts").read_text(encoding="utf-8")
    runtime = (root / "api" / "runtime.ts").read_text(encoding="utf-8")
    assert "get_runtime_session" in runtime
    assert "Authorization" in client
    assert "localStorage" not in client + runtime
    assert "sessionStorage" not in client + runtime
    assert "console.log" not in client + runtime
    assert "?token=" in client and "#token=" in client
