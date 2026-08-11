"""M8 SystemArchitecture/HardwareIR gate and persistence tests."""

from uuid import UUID

import pytest
from eea_application.architecture import ArchitectureService
from eea_application.requirements import RequirementAnalysisService, RequirementProfileRegistry
from eea_backend.repositories import SqlAlchemyEvidenceRepository
from eea_backend.requirement_repositories import (
    SqlAlchemyRequirementProfileRepository,
    persist_requirement_analysis_bundle,
)
from eea_core.enums import EngineeringErrorCode, IssueSeverity
from eea_core.errors import EngineeringError
from eea_core.intelligence import PinFunction
from eea_core.pin_planner import PinAssignment, PinPlan, PinRequirement, RuleResult
from eea_core.requirements import RequirementAnalysisDraft, RequirementDraft
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

PROJECT_ID = UUID(int=80)


def _minimal_plan(*, locked: bool = True, status: str = "PASS") -> PinPlan:
    requirement = PinRequirement(
        project_id=PROJECT_ID,
        signal_name="generic-signal",
        required_peripheral="PERIPHERAL1",
        required_function="SIGNAL1",
        requirement_ids=[UUID(int=801)],
    )
    assignment = PinAssignment(
        project_id=PROJECT_ID,
        requirement_id=requirement.id,
        device_ref="DEVICE1",
        package="PACKAGE1",
        pin_name="P1",
        function=PinFunction(peripheral="PERIPHERAL1", signal="SIGNAL1"),
        locked=locked,
        claim_ids=[UUID(int=802)],
    )
    result = RuleResult(
        project_id=PROJECT_ID,
        rule_id="PIN_ASSIGNMENT_VALID",
        rule_version="1.0",
        stage="PRE_GENERATION",
        status=status,  # type: ignore[arg-type]
        severity=IssueSeverity.INFO,
    )
    return PinPlan(
        project_id=PROJECT_ID,
        analysis_id=UUID(int=803),
        device_ref="DEVICE1",
        package="PACKAGE1",
        requirements=[requirement],
        assignments=[assignment],
        rule_results=[result],
    )


def test_architecture_service_rejects_unlocked_and_blocked_prerequisites() -> None:
    service = ArchitectureService()
    unlocked = _minimal_plan(locked=False)
    with pytest.raises(EngineeringError) as unlocked_error:
        service.generate(unlocked, latest_plan_id=unlocked.id)
    assert unlocked_error.value.code is EngineeringErrorCode.INVALID_REQUIREMENT
    assert unlocked_error.value.details["reason"] == "UNLOCKED_ASSIGNMENTS"

    blocked = _minimal_plan(status="UNKNOWN")
    with pytest.raises(EngineeringError) as blocked_error:
        service.generate(blocked, latest_plan_id=blocked.id)
    assert blocked_error.value.details["reason"] == "M7_RULE_GATE_FAILED"

    stale = _minimal_plan()
    with pytest.raises(EngineeringError) as stale_error:
        service.generate(stale, latest_plan_id=UUID(int=804))
    assert stale_error.value.details["reason"] == "STALE_PIN_PLAN"


def _create_pin_plan_payload(client: TestClient) -> tuple[UUID, dict[str, object]]:
    project_response = client.post("/api/v1/projects", json={"name": "M8 architecture API"})
    project_id = UUID(project_response.json()["data"]["id"])
    with Session(client.app.state.engine) as session:
        profiles = SqlAlchemyRequirementProfileRepository(session)
        profile = profiles.get("foc-benchmark", "1.0")
        assert profile is not None
        analysis = RequirementAnalysisService(
            RequirementProfileRegistry(profiles),
            evidence_repository=SqlAlchemyEvidenceRepository(session),
        ).complete_draft(
            project_id=project_id,
            profile_name=profile.profile_name,
            profile_version=profile.profile_version,
            draft=RequirementAnalysisDraft(
                profile_name=profile.profile_name,
                profile_version=profile.profile_version,
                requirements=[
                    RequirementDraft(
                        code="REQ-M8-PIN",
                        title="Architecture signal",
                        statement="The signal shall remain traceable into architecture IR.",
                    )
                ],
            ),
        )
        saved = persist_requirement_analysis_bundle(session, analysis)
    return project_id, {
        "analysis_id": str(saved.id),
        "device_ref": "STM32G431",
        "package": "UFQFPN48",
        "requirements": [
            {
                "signal_name": "architecture-pwm-output",
                "required_peripheral": "TIM1",
                "required_function": "CH1",
                "requirement_ids": [str(saved.requirement_ids[0])],
            }
        ],
    }


def test_architecture_api_requires_lock_persists_bundle_and_rejects_stale(
    client: TestClient,
) -> None:
    project_id, payload = _create_pin_plan_payload(client)
    generated = client.post(f"/api/v1/projects/{project_id}/pin-planner/generate", json=payload)
    plan = generated.json()["data"]
    assignment_id = plan["assignments"][0]["id"]

    rejected = client.post(
        f"/api/v1/projects/{project_id}/architecture/generate",
        json={"pin_plan_id": plan["id"]},
    )
    assert rejected.status_code == 400
    assert rejected.json()["error"]["details"]["reason"] == "UNLOCKED_ASSIGNMENTS"

    locked = client.post(
        f"/api/v1/projects/{project_id}/pin-planner/assignments/{assignment_id}/lock",
        headers={"If-Match": 'W/"1"'},
        json={"actor": "architect", "reason": "Architecture source map"},
    )
    assert locked.status_code == 200

    generated_architecture = client.post(
        f"/api/v1/projects/{project_id}/architecture/generate",
        json={"pin_plan_id": plan["id"]},
    )
    assert generated_architecture.status_code == 201
    bundle = generated_architecture.json()["data"]
    assert bundle["system_architecture"]["pin_plan_id"] == plan["id"]
    assert bundle["hardware"]["pin_plan_id"] == plan["id"]
    assert bundle["hardware"]["pin_assignment_revisions"][assignment_id] == 2
    assert bundle["hardware"]["interfaces"][0]["pin_assignment_ids"] == [assignment_id]

    fetched = client.get(f"/api/v1/projects/{project_id}/architecture")
    assert fetched.status_code == 200
    assert (
        fetched.json()["data"]["system_architecture"]["id"] == bundle["system_architecture"]["id"]
    )

    replanned = client.post(f"/api/v1/projects/{project_id}/pin-planner/replan", json=payload)
    assert replanned.status_code == 201
    stale = client.post(
        f"/api/v1/projects/{project_id}/architecture/generate",
        json={"pin_plan_id": plan["id"]},
    )
    assert stale.status_code == 400
    assert stale.json()["error"]["details"]["reason"] == "STALE_PIN_PLAN"
