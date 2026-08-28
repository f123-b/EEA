"""API startup, health, contract-envelope, and authentication tests."""

from pathlib import Path

from eea_backend.main import create_app
from eea_backend.settings import Settings
from eea_backend.version import CURRENT_MILESTONE, __version__
from fastapi.testclient import TestClient
from pydantic import SecretStr


def test_health_reports_database_and_version(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "ok"
    assert response.headers["X-Request-ID"].startswith("req_")


def test_version_uses_v1_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/meta/version", headers={"X-Request-ID": "req_test"})

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "product": "Embedded Engineering Agent",
            "version": __version__,
            "api_version": "v1",
            "milestone": CURRENT_MILESTONE,
        },
        "request_id": "req_test",
    }


def test_configured_session_token_protects_versioned_api(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, session_token=SecretStr("correct-token"))
    with TestClient(create_app(settings)) as protected_client:
        assert protected_client.get("/health").status_code == 200
        assert protected_client.get("/api/v1/meta/version").status_code == 401
        assert (
            protected_client.get(
                "/api/v1/meta/version", headers={"Authorization": "Bearer wrong-token"}
            ).status_code
            == 401
        )
        assert (
            protected_client.get(
                "/api/v1/meta/version", headers={"Authorization": "Bearer correct-token"}
            ).status_code
            == 200
        )


def test_packaged_tauri_origin_can_preflight_authenticated_loopback_api(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path, session_token=SecretStr("desktop-token"))
    with TestClient(create_app(settings)) as protected_client:
        response = protected_client.options(
            "/api/v1/meta/version",
            headers={
                "Origin": "http://tauri.localhost",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://tauri.localhost"
    assert "authorization" in response.headers["access-control-allow-headers"].lower()
