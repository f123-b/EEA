"""M9 CircuitIR and deterministic electrical rule acceptance tests."""

from uuid import UUID

import pytest
from eea_application.circuit import CircuitService
from eea_application.requirements import RequirementAnalysisService, RequirementProfileRegistry
from eea_backend.repositories import SqlAlchemyEvidenceRepository
from eea_backend.requirement_repositories import (
    SqlAlchemyRequirementProfileRepository,
    persist_requirement_analysis_bundle,
)
from eea_core.architecture import HardwareInterface, HardwareIR
from eea_core.circuit import CircuitConstraint, CircuitEndpoint, CircuitNet
from eea_core.claims import EngineeringValue
from eea_core.enums import EngineeringDimension, EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_core.requirements import RequirementAnalysisDraft, RequirementDraft
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

PROJECT_ID = UUID(int=90)
ASSIGNMENT_ID = UUID(int=9001)


def _voltage(value: float) -> EngineeringValue:
    return EngineeringValue(unit="V", dimension=EngineeringDimension.VOLTAGE, nominal=value)


def _hardware() -> HardwareIR:
    return HardwareIR(
        project_id=PROJECT_ID,
        architecture_id=UUID(int=9002),
        pin_plan_id=UUID(int=9003),
        pin_plan_revision=1,
        interfaces=[
            HardwareInterface(
                name="MCU_PWM",
                interface_type="DIGITAL",
                endpoint_refs=["MCU"],
                pin_assignment_ids=[ASSIGNMENT_ID],
            )
        ],
        pin_assignment_revisions={str(ASSIGNMENT_ID): 2},
    )


def _constraint(rule_id: str, parameters: dict[str, object]) -> CircuitConstraint:
    return CircuitConstraint(rule_id=rule_id, target_ref="Q1", parameters=parameters)


def test_circuit_rules_are_deterministic_and_unknown_never_passes() -> None:
    service = CircuitService()
    hardware = _hardware()
    cases = [
        (
            _constraint(
                "MOSFET_VDS_MARGIN",
                {
                    "bus_voltage": _voltage(24),
                    "transient_voltage": _voltage(30),
                    "vds_rating": _voltage(40),
                },
            ),
            "PASS",
        ),
        (
            _constraint(
                "MOSFET_VDS_MARGIN",
                {
                    "bus_voltage": _voltage(24),
                    "transient_voltage": _voltage(40),
                    "vds_rating": _voltage(40),
                },
            ),
            "FAIL",
        ),
        (_constraint("MOSFET_VDS_MARGIN", {}), "UNKNOWN"),
        (
            _constraint(
                "ADC_RANGE",
                {
                    "input_min": _voltage(0),
                    "input_max": _voltage(3.0),
                    "adc_min": _voltage(0),
                    "adc_max": _voltage(3.3),
                },
            ),
            "PASS",
        ),
        (
            _constraint(
                "ADC_RANGE",
                {
                    "input_min": _voltage(-1),
                    "input_max": _voltage(4),
                    "adc_min": _voltage(0),
                    "adc_max": _voltage(3.3),
                },
            ),
            "FAIL",
        ),
        (
            _constraint(
                "GATE_DRIVER_VOLTAGE",
                {"driver_voltage": _voltage(10), "gate_required": _voltage(12)},
            ),
            "FAIL",
        ),
        (_constraint("CAN_TRANSCEIVER", {"transceiver_present": True}), "PASS"),
        (_constraint("CAN_TRANSCEIVER", {}), "UNKNOWN"),
        (_constraint("TERMINATION", {"termination_count": 1}), "FAIL"),
        (_constraint("TERMINATION", {"termination_count": 2}), "PASS"),
        (_constraint("FUTURE_RULE", {}), "NOT_APPLICABLE"),
    ]

    for constraint, expected in cases:
        result = service.generate(hardware, constraints=[constraint]).rule_results[0]
        assert result.status == expected
        if expected == "UNKNOWN":
            assert result.status != "PASS"


def test_circuit_generation_reuses_only_hardware_pin_assignments() -> None:
    service = CircuitService()
    net = CircuitNet(
        name="pwm",
        endpoints=[
            CircuitEndpoint(component_ref="MCU", pin_ref="PA8", pin_assignment_id=ASSIGNMENT_ID)
        ],
    )
    bundle = service.generate(_hardware(), nets=[net])
    assert bundle.circuit.pin_assignment_revisions == {str(ASSIGNMENT_ID): 2}
    assert bundle.rule_results[0].rule_id == "CIRCUIT_VALIDATION_NOT_APPLICABLE"

    bad_net = net.model_copy(
        update={
            "endpoints": [net.endpoints[0].model_copy(update={"pin_assignment_id": UUID(int=9004)})]
        }
    )
    with pytest.raises(EngineeringError) as error:
        service.generate(_hardware(), nets=[bad_net])
    assert error.value.code is EngineeringErrorCode.INVALID_REQUIREMENT
    assert error.value.details["reason"] == "PIN_ASSIGNMENT_SOURCE_MISMATCH"


def _create_architecture_source(client: TestClient) -> tuple[UUID, dict[str, object]]:
    project_response = client.post("/api/v1/projects", json={"name": "M9 circuit API"})
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
                        code="REQ-M9-CIRCUIT",
                        title="Circuit traceability",
                        statement="The circuit shall retain the locked pin source.",
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
                "signal_name": "m9-pwm-output",
                "required_peripheral": "TIM1",
                "required_function": "CH1",
                "requirement_ids": [str(saved.requirement_ids[0])],
            }
        ],
    }


def test_circuit_api_persists_bundle_validates_and_rejects_stale_hardware(
    client: TestClient,
) -> None:
    project_id, pin_payload = _create_architecture_source(client)
    plan_response = client.post(
        f"/api/v1/projects/{project_id}/pin-planner/generate", json=pin_payload
    )
    assert plan_response.status_code == 201
    plan = plan_response.json()["data"]
    assignment_id = plan["assignments"][0]["id"]
    locked = client.post(
        f"/api/v1/projects/{project_id}/pin-planner/assignments/{assignment_id}/lock",
        headers={"If-Match": 'W/"1"'},
        json={"actor": "m9", "reason": "Circuit source"},
    )
    assert locked.status_code == 200
    architecture = client.post(
        f"/api/v1/projects/{project_id}/architecture/generate",
        json={"pin_plan_id": plan["id"]},
    )
    assert architecture.status_code == 201
    hardware = architecture.json()["data"]["hardware"]

    circuit_response = client.post(
        f"/api/v1/projects/{project_id}/circuit/generate",
        json={
            "hardware_ir_id": hardware["id"],
            "components": [{"reference": "Q1", "kind": "MOSFET"}],
            "nets": [
                {
                    "name": "pwm",
                    "signal_type": "DIGITAL",
                    "endpoints": [
                        {
                            "component_ref": "MCU",
                            "pin_ref": "PA8",
                            "pin_assignment_id": assignment_id,
                        }
                    ],
                }
            ],
            "constraints": [
                {
                    "rule_id": "TERMINATION",
                    "target_ref": "can0",
                    "parameters": {"termination_count": 2},
                }
            ],
        },
    )
    assert circuit_response.status_code == 201
    bundle = circuit_response.json()["data"]
    assert bundle["circuit"]["hardware_ir_id"] == hardware["id"]
    assert bundle["circuit"]["pin_assignment_revisions"][assignment_id] == 2
    assert bundle["rule_results"][0]["status"] == "PASS"

    fetched = client.get(f"/api/v1/projects/{project_id}/circuit")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["circuit"]["id"] == bundle["circuit"]["id"]
    validated = client.post(
        f"/api/v1/projects/{project_id}/circuit/validate",
        json={"circuit_id": bundle["circuit"]["id"]},
    )
    assert validated.status_code == 200
    assert validated.json()["data"]["rule_results"][0]["status"] == "PASS"

    replanned = client.post(f"/api/v1/projects/{project_id}/pin-planner/replan", json=pin_payload)
    assert replanned.status_code == 201
    new_plan = replanned.json()["data"]
    new_assignment_id = new_plan["assignments"][0]["id"]
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/pin-planner/assignments/{new_assignment_id}/lock",
            headers={"If-Match": 'W/"1"'},
            json={"actor": "m9", "reason": "Refresh circuit source"},
        ).status_code
        == 200
    )
    refreshed = client.post(
        f"/api/v1/projects/{project_id}/architecture/generate",
        json={"pin_plan_id": new_plan["id"]},
    )
    assert refreshed.status_code == 201
    stale = client.post(
        f"/api/v1/projects/{project_id}/circuit/validate",
        json={"circuit_id": bundle["circuit"]["id"]},
    )
    assert stale.status_code == 400
    assert stale.json()["error"]["details"]["reason"] == "STALE_HARDWARE_IR"
