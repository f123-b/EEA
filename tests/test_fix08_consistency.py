"""FIX-08 cross-surface enum and error-code invariants."""

import json
from pathlib import Path

from eea_core.enums import EngineeringErrorCode, JobStatus, Permission
from fastapi.testclient import TestClient
from sqlalchemy import inspect


def _openapi_enum(name: str) -> list[str]:
    document = json.loads(Path("schemas/openapi.json").read_text(encoding="utf-8"))
    return document["components"]["schemas"][name]["enum"]  # type: ignore[no-any-return]


def test_job_state_enum_consistent(client: TestClient) -> None:
    """JOB_STATE_ENUM_CONSISTENT."""

    expected = [item.value for item in JobStatus]
    constraints = inspect(client.app.state.engine).get_check_constraints("jobs")
    status_constraint = next(
        item["sqltext"] for item in constraints if item["name"] == "ck_jobs_status"
    )

    assert _openapi_enum("JobStatus") == expected
    assert all(f"'{value}'" in status_constraint for value in expected)
    frontend = Path("apps/desktop/src/domain/jobStatus.ts").read_text(encoding="utf-8")
    assert all(f"{value}:" in frontend for value in expected)


def test_actuator_permission_enum_consistent(client: TestClient) -> None:
    """ACTUATOR_PERMISSION_ENUM_CONSISTENT."""

    expected = [item.value for item in Permission]
    constraints = inspect(client.app.state.engine).get_check_constraints("permissions_audit")
    permission_constraint = next(
        item["sqltext"] for item in constraints if item["name"] == "ck_permissions_audit_permission"
    )

    assert _openapi_enum("Permission") == expected
    assert all(f"'{value}'" in permission_constraint for value in expected)
    assert "ACTUATOR_ENABLE" in expected
    assert Permission.FLASH is not Permission.ACTUATOR_ENABLE


def test_api_error_enum_consistent(client: TestClient) -> None:
    """API_ERROR_ENUM_CONSISTENT."""

    expected = [item.value for item in EngineeringErrorCode]
    meta_enums = client.get("/api/v1/meta/enums").json()["data"]["enums"]
    generated = Path("apps/desktop/src/api/generated.ts").read_text(encoding="utf-8")
    constraints = inspect(client.app.state.engine).get_check_constraints("jobs")
    error_constraint = next(
        item["sqltext"] for item in constraints if item["name"] == "ck_jobs_error_code"
    )

    assert _openapi_enum("EngineeringErrorCode") == expected
    assert meta_enums["EngineeringErrorCode"] == expected
    assert all(f'"{value}"' in generated for value in expected)
    assert all(f"'{value}'" in error_constraint for value in expected)
