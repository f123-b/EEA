"""M7 Pin Planner and Core Rule Engine acceptance tests."""

from uuid import UUID

import pytest
from eea_adapters.devices import Stm32G431FixtureProvider
from eea_application.pin_planner import PinPlannerService
from eea_application.requirements import RequirementAnalysisService, RequirementProfileRegistry
from eea_backend.repositories import SqlAlchemyEvidenceRepository
from eea_backend.requirement_repositories import (
    SqlAlchemyRequirementProfileRepository,
    persist_requirement_analysis_bundle,
)
from eea_core.claims import EngineeringValue
from eea_core.enums import EngineeringDimension, EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_core.intelligence import PinFunction
from eea_core.pin_planner import PinRequirement
from eea_core.requirements import RequirementAnalysisDraft, RequirementDraft
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

PROJECT_ID = UUID(int=70)


def requirement(
    *,
    signal_name: str = "pwm-a",
    peripheral: str = "TIM1",
    function: str = "CH1",
    hard_constraints: dict[str, object] | None = None,
    preferred_constraints: dict[str, object] | None = None,
) -> PinRequirement:
    return PinRequirement(
        project_id=PROJECT_ID,
        signal_name=signal_name,
        required_peripheral=peripheral,
        required_function=function,
        hard_constraints=hard_constraints or {},
        preferred_constraints=preferred_constraints or {},
        requirement_ids=[UUID(int=701)],
        claim_ids=[UUID(int=702)],
    )


def test_valid_af_is_assigned_and_traceability_is_preserved() -> None:
    plan = PinPlannerService().plan(
        project_id=PROJECT_ID,
        device_ref="STM32G431",
        package="UFQFPN48",
        requirements=[requirement()],
        device_provider=Stm32G431FixtureProvider(),
    )

    assert len(plan.assignments) == 1
    assert plan.assignments[0].pin_name == "PA8"
    assert plan.assignments[0].function.signal == "CH1"
    assert plan.assignments[0].claim_ids == [UUID(int=702)]
    assert [(result.rule_id, result.status) for result in plan.rule_results] == [
        ("PIN_ASSIGNMENT_VALID", "PASS")
    ]


def test_invalid_af_is_rejected_deterministically() -> None:
    plan = PinPlannerService().plan(
        project_id=PROJECT_ID,
        device_ref="STM32G431",
        package="UFQFPN48",
        requirements=[requirement(function="CH2")],
        device_provider=Stm32G431FixtureProvider(),
    )

    assert plan.assignments == []
    assert plan.rule_results[0].rule_id == "PIN_FUNCTION_INVALID"
    assert plan.rule_results[0].status == "FAIL"


def test_package_and_missing_device_facts_never_infer_pass() -> None:
    service = PinPlannerService()
    package_plan = service.plan(
        project_id=PROJECT_ID,
        device_ref="STM32G431",
        package="NOT-A-PACKAGE",
        requirements=[requirement()],
        device_provider=Stm32G431FixtureProvider(),
    )
    unknown_plan = service.plan(
        project_id=PROJECT_ID,
        device_ref="UNKNOWN-MCU",
        package=None,
        requirements=[requirement()],
        device_provider=Stm32G431FixtureProvider(),
    )

    assert package_plan.rule_results[0].rule_id == "PIN_PACKAGE_MISSING"
    assert package_plan.rule_results[0].status == "FAIL"
    assert unknown_plan.rule_results[0].rule_id == "DEVICE_FACTS_UNAVAILABLE"
    assert unknown_plan.rule_results[0].status == "UNKNOWN"
    assert unknown_plan.assignments == []


def test_voltage_and_five_v_constraints_use_canonical_facts() -> None:
    service = PinPlannerService()
    voltage_plan = service.plan(
        project_id=PROJECT_ID,
        device_ref="STM32G431",
        package="UFQFPN48",
        requirements=[
            requirement(
                hard_constraints={
                    "voltage": EngineeringValue(
                        unit="V", dimension=EngineeringDimension.VOLTAGE, nominal=5
                    )
                }
            )
        ],
        device_provider=Stm32G431FixtureProvider(),
    )
    tolerance_plan = service.plan(
        project_id=PROJECT_ID,
        device_ref="STM32G431",
        package="UFQFPN48",
        requirements=[
            requirement(
                signal_name="pwm-not-tolerant",
                hard_constraints={"five_v_tolerant": True},
            )
        ],
        device_provider=Stm32G431FixtureProvider(),
    )

    assert voltage_plan.rule_results[0].rule_id == "GPIO_VOLTAGE_EXCEEDED"
    assert voltage_plan.rule_results[0].status == "FAIL"
    assert tolerance_plan.rule_results[0].rule_id == "FIVE_V_TOLERANCE_INVALID"
    assert tolerance_plan.rule_results[0].status == "FAIL"


def test_pwm_adc_and_complementary_rules_are_deterministic() -> None:
    service = PinPlannerService()
    pwm = service.plan(
        project_id=PROJECT_ID,
        device_ref="STM32G431",
        package="UFQFPN48",
        requirements=[
            requirement(
                signal_name="pwm-complementary",
                hard_constraints={"complementary_pwm": True},
            )
        ],
        device_provider=Stm32G431FixtureProvider(),
    )
    adc = service.plan(
        project_id=PROJECT_ID,
        device_ref="STM32G431",
        package="UFQFPN48",
        requirements=[
            requirement(
                signal_name="adc-invalid",
                peripheral="ADC1",
                function="IN9",
                hard_constraints={"adc_channel": "IN9"},
            )
        ],
        device_provider=Stm32G431FixtureProvider(),
    )

    assert pwm.assignments[0].pin_name == "PA8"
    assert pwm.rule_results[0].status == "PASS"
    assert adc.rule_results[0].rule_id == "ADC_CHANNEL_INVALID"
    assert adc.rule_results[0].status == "FAIL"


def test_pin_conflict_is_rejected_without_silent_overwrite() -> None:
    plan = PinPlannerService().plan(
        project_id=PROJECT_ID,
        device_ref="STM32G431",
        package="UFQFPN48",
        requirements=[requirement(signal_name="first"), requirement(signal_name="second")],
        device_provider=Stm32G431FixtureProvider(),
    )

    assert [assignment.pin_name for assignment in plan.assignments] == ["PA8"]
    assert plan.rule_results[-1].rule_id == "PIN_CONFLICT"
    assert plan.rule_results[-1].status == "FAIL"


def test_lock_is_explicit_and_retained() -> None:
    service = PinPlannerService()
    pinned_requirement = requirement()
    first = service.plan(
        project_id=PROJECT_ID,
        device_ref="STM32G431",
        package="UFQFPN48",
        requirements=[pinned_requirement],
        device_provider=Stm32G431FixtureProvider(),
    )
    locked, lock = service.lock_assignment(
        first.assignments[0], locked_by="user:reviewer", reason="Board routing constraint"
    )
    second = service.plan(
        project_id=PROJECT_ID,
        device_ref="STM32G431",
        package="UFQFPN48",
        requirements=[pinned_requirement],
        device_provider=Stm32G431FixtureProvider(),
        locked_assignments=[locked],
        locks=[lock],
    )

    assert locked.locked is True
    assert lock.assignment_id == locked.id
    assert second.assignments == [locked]
    assert second.rule_results[0].rule_id == "PIN_LOCK_RETAINED"

    with pytest.raises(EngineeringError) as captured:
        service.lock_assignment(first.assignments[0], locked_by="", reason="")
    assert captured.value.code is EngineeringErrorCode.VALIDATION_ERROR


def test_validate_rejects_duplicate_and_invalid_assignment() -> None:
    provider = Stm32G431FixtureProvider()
    base = PinPlannerService().plan(
        project_id=PROJECT_ID,
        device_ref="STM32G431",
        package="UFQFPN48",
        requirements=[requirement()],
        device_provider=provider,
    )
    duplicate = base.assignments[0].model_copy()
    invalid = base.assignments[0].model_copy(
        update={
            "id": UUID(int=703),
            "function": PinFunction(peripheral="TIM1", signal="CH2"),
        }
    )
    plan = base.model_copy(update={"assignments": [duplicate, invalid]})
    results = PinPlannerService().validate(plan, provider)
    invalid_results = PinPlannerService().validate(
        base.model_copy(update={"assignments": [invalid]}), provider
    )

    assert [result.rule_id for result in results] == [
        "PIN_ASSIGNMENT_VALID",
        "PIN_CONFLICT",
    ]
    assert invalid_results[0].rule_id == "PIN_FUNCTION_INVALID"


def test_pin_planner_api_requires_and_consumes_canonical_m6_refs(client: TestClient) -> None:
    project_response = client.post("/api/v1/projects", json={"name": "M7 API"})
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
                        code="REQ-PIN",
                        title="PWM pin",
                        statement="The PWM output shall be routable.",
                    )
                ],
            ),
        )
        saved = persist_requirement_analysis_bundle(session, analysis)

    payload = {
        "analysis_id": str(saved.id),
        "device_ref": "STM32G431",
        "package": "UFQFPN48",
        "requirements": [
            {
                "signal_name": "pwm-output",
                "required_peripheral": "TIM1",
                "required_function": "CH1",
                "requirement_ids": [str(saved.requirement_ids[0])],
            }
        ],
    }
    response = client.post(f"/api/v1/projects/{project_id}/pin-planner/generate", json=payload)
    assert response.status_code == 201
    assert response.json()["data"]["assignments"][0]["pin_name"] == "PA8"

    payload["requirements"][0]["requirement_ids"] = [str(UUID(int=9999))]
    rejected = client.post(f"/api/v1/projects/{project_id}/pin-planner/generate", json=payload)
    assert rejected.status_code == 400
    assert rejected.json()["error"]["code"] == "INVALID_REQUIREMENT"


def _create_pin_plan_payload(client: TestClient) -> tuple[UUID, dict[str, object]]:
    project_response = client.post("/api/v1/projects", json={"name": "M7 durable API"})
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
                        code="REQ-PIN-DURABLE",
                        title="Durable PWM pin",
                        statement="The PWM output shall remain traceable.",
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
                "signal_name": "durable-pwm-output",
                "required_peripheral": "TIM1",
                "required_function": "CH1",
                "requirement_ids": [str(saved.requirement_ids[0])],
            }
        ],
    }


def test_pin_plan_persistence_lock_unlock_validate_and_replan(client: TestClient) -> None:
    project_id, payload = _create_pin_plan_payload(client)

    generated = client.post(f"/api/v1/projects/{project_id}/pin-planner/generate", json=payload)
    assert generated.status_code == 201
    plan = generated.json()["data"]
    assignment = plan["assignments"][0]
    assert plan["analysis_id"] == payload["analysis_id"]

    mapped = client.get(f"/api/v1/projects/{project_id}/pin-planner/map")
    assert mapped.status_code == 200
    assert mapped.json()["data"]["id"] == plan["id"]

    validated = client.post(
        f"/api/v1/projects/{project_id}/pin-planner/validate",
        json={"plan_id": plan["id"]},
    )
    assert validated.status_code == 200
    assert validated.json()["data"]["rule_results"][0]["status"] == "PASS"

    missing_precondition = client.post(
        f"/api/v1/projects/{project_id}/pin-planner/assignments/{assignment['id']}/lock",
        json={"actor": "reviewer", "reason": "Route reservation"},
    )
    assert missing_precondition.status_code == 422

    locked = client.post(
        f"/api/v1/projects/{project_id}/pin-planner/assignments/{assignment['id']}/lock",
        headers={"If-Match": 'W/"1"'},
        json={"actor": "reviewer", "reason": "Route reservation"},
    )
    assert locked.status_code == 200
    assert locked.headers["ETag"] == 'W/"2"'
    assert locked.json()["data"]["assignment"]["locked"] is True
    assert locked.json()["data"]["lock"]["locked_by"] == "reviewer"
    locked_map = client.get(f"/api/v1/projects/{project_id}/pin-planner/map")
    assert locked_map.json()["data"]["assignments"][0]["locked"] is True
    assert locked_map.json()["data"]["locks"][0]["assignment_id"] == assignment["id"]

    stale = client.post(
        f"/api/v1/projects/{project_id}/pin-planner/assignments/{assignment['id']}/unlock",
        headers={"If-Match": 'W/"1"'},
        json={"actor": "reviewer", "reason": "Stale unlock"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "REVISION_CONFLICT"

    unlocked = client.post(
        f"/api/v1/projects/{project_id}/pin-planner/assignments/{assignment['id']}/unlock",
        headers={"If-Match": 'W/"2"'},
        json={"actor": "reviewer", "reason": "Route changed"},
    )
    assert unlocked.status_code == 200
    assert unlocked.headers["ETag"] == 'W/"3"'
    assert unlocked.json()["data"]["assignment"]["locked"] is False
    assert unlocked.json()["data"]["lock"] is None
    unlocked_map = client.get(f"/api/v1/projects/{project_id}/pin-planner/map")
    assert unlocked_map.json()["data"]["assignments"][0]["locked"] is False
    assert unlocked_map.json()["data"]["locks"] == []

    replanned = client.post(f"/api/v1/projects/{project_id}/pin-planner/replan", json=payload)
    assert replanned.status_code == 201
    assert replanned.json()["data"]["id"] != plan["id"]
