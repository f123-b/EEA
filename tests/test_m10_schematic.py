"""M10 schematic generation, ERC fallback, and source invalidation tests."""

from uuid import UUID

import pytest
from eea_application.requirements import RequirementAnalysisService, RequirementProfileRegistry
from eea_application.schematic import SchematicService
from eea_backend.repositories import SqlAlchemyEvidenceRepository
from eea_backend.requirement_repositories import (
    SqlAlchemyRequirementProfileRepository,
    persist_requirement_analysis_bundle,
)
from eea_backend.schematic_repositories import SqlAlchemySchematicRepository
from eea_core.circuit import CircuitComponent, CircuitEndpoint, CircuitIR, CircuitNet
from eea_core.enums import IssueSeverity
from eea_core.errors import EngineeringError
from eea_core.requirements import RequirementAnalysisDraft, RequirementDraft
from eea_core.schematic import ErcIssue
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

PROJECT_ID = UUID(int=100)
HARDWARE_ID = UUID(int=1001)
PIN_ASSIGNMENT_ID = UUID(int=1002)


def _circuit(*, missing_component: bool = False) -> CircuitIR:
    components = [CircuitComponent(reference="MCU", kind="MCU")]
    if not missing_component:
        components.append(CircuitComponent(reference="R1", kind="RESISTOR"))
    return CircuitIR(
        project_id=PROJECT_ID,
        hardware_ir_id=HARDWARE_ID,
        hardware_ir_revision=1,
        components=components,
        nets=[
            CircuitNet(
                name="pwm",
                endpoints=[
                    CircuitEndpoint(
                        component_ref="MCU",
                        pin_ref="PA8",
                        pin_assignment_id=PIN_ASSIGNMENT_ID,
                    ),
                    CircuitEndpoint(component_ref="R1", pin_ref="1"),
                ],
            )
        ],
        pin_assignment_revisions={str(PIN_ASSIGNMENT_ID): 2},
    )


def test_schematic_netlist_is_deterministic_and_erc_unknown_without_kicad() -> None:
    service = SchematicService()
    circuit = _circuit()
    first = service.generate(circuit)
    reversed_components = list(reversed(circuit.components))
    reversed_nets = list(reversed(circuit.nets))
    reordered = circuit.model_copy(
        update={
            "components": reversed_components,
            "nets": reversed_nets,
        }
    )
    second = service.generate(reordered)

    assert first.schematic.netlist_text == second.schematic.netlist_text
    assert first.schematic.content_hash == second.schematic.content_hash
    assert first.schematic.pin_assignment_revisions == {str(PIN_ASSIGNMENT_ID): 2}
    assert first.erc_report.status == "UNKNOWN"
    assert first.erc_report.executed is False
    assert "not ERC verified" in first.erc_report.recommendation


def test_schematic_preflight_reports_missing_endpoint_component_and_imports_erc() -> None:
    service = SchematicService()
    circuit = _circuit(missing_component=True)
    bundle = service.generate(circuit)
    assert bundle.erc_report.status == "FAIL"
    assert bundle.erc_report.issues[0].code == "SCHEMATIC_NET_COMPONENT_MISSING"

    imported = service.import_erc(
        bundle.schematic,
        circuit,
        status="PASS",
        tool_name="kicad-cli",
        tool_version="9.0.0",
        issues=[
            ErcIssue(
                code="ERC_INFO",
                title="No electrical violations",
                severity=IssueSeverity.INFO,
            )
        ],
    )
    assert imported.status == "PASS"
    assert imported.executed is True
    assert imported.tool_name == "kicad-cli"

    mismatched = circuit.model_copy(update={"revision": 2})
    with pytest.raises(EngineeringError) as error:
        service.validate(bundle.schematic, mismatched)
    assert error.value.details["reason"] == "SOURCE_REVISION_MISMATCH"


def _create_architecture_source(client: TestClient) -> tuple[UUID, dict[str, object]]:
    project_response = client.post("/api/v1/projects", json={"name": "M10 schematic API"})
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
                        code="REQ-M10-SCHEMATIC",
                        title="Schematic traceability",
                        statement="The schematic shall retain its CircuitIR source revision.",
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
                "signal_name": "m10-pwm-output",
                "required_peripheral": "TIM1",
                "required_function": "CH1",
                "requirement_ids": [str(saved.requirement_ids[0])],
            }
        ],
    }


def _create_circuit(client: TestClient) -> tuple[UUID, str, str]:
    project_id, pin_payload = _create_architecture_source(client)
    plan = client.post(
        f"/api/v1/projects/{project_id}/pin-planner/generate", json=pin_payload
    ).json()["data"]
    assignment_id = plan["assignments"][0]["id"]
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/pin-planner/assignments/{assignment_id}/lock",
            headers={"If-Match": 'W/"1"'},
            json={"actor": "m10", "reason": "Schematic source"},
        ).status_code
        == 200
    )
    hardware = client.post(
        f"/api/v1/projects/{project_id}/architecture/generate",
        json={"pin_plan_id": plan["id"]},
    ).json()["data"]["hardware"]
    circuit = client.post(
        f"/api/v1/projects/{project_id}/circuit/generate",
        json={
            "hardware_ir_id": hardware["id"],
            "components": [
                {"reference": "MCU", "kind": "MCU"},
                {"reference": "R1", "kind": "RESISTOR"},
            ],
            "nets": [
                {
                    "name": "pwm",
                    "signal_type": "DIGITAL",
                    "endpoints": [
                        {
                            "component_ref": "MCU",
                            "pin_ref": "PA8",
                            "pin_assignment_id": assignment_id,
                        },
                        {"component_ref": "R1", "pin_ref": "1"},
                    ],
                }
            ],
        },
    ).json()["data"]["circuit"]
    return project_id, circuit["id"], hardware["id"]


def test_schematic_api_round_trip_import_and_stale_source_gate(client: TestClient) -> None:
    project_id, circuit_id, hardware_id = _create_circuit(client)
    generated = client.post(
        f"/api/v1/projects/{project_id}/schematic/generate",
        json={"circuit_id": circuit_id},
    )
    assert generated.status_code == 201
    bundle = generated.json()["data"]
    assert bundle["artifact"]["status"] == "CURRENT"
    assert bundle["schematic"]["circuit_id"] == circuit_id
    assert bundle["erc_report"]["status"] == "UNKNOWN"
    assert bundle["erc_report"]["executed"] is False

    fetched = client.get(f"/api/v1/projects/{project_id}/schematic")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["schematic"]["id"] == bundle["schematic"]["id"]

    validated = client.post(
        f"/api/v1/projects/{project_id}/schematic/validate",
        json={"schematic_id": bundle["schematic"]["id"]},
    )
    assert validated.status_code == 200
    assert validated.json()["data"]["erc_report"]["status"] == "UNKNOWN"

    imported = client.post(
        f"/api/v1/projects/{project_id}/schematic/erc/import",
        json={
            "schematic_id": bundle["schematic"]["id"],
            "status": "PASS",
            "tool_name": "kicad-cli",
            "tool_version": "9.0.0",
        },
    )
    assert imported.status_code == 200
    assert imported.json()["data"]["erc_report"]["status"] == "PASS"
    assert imported.json()["data"]["erc_report"]["executed"] is True

    new_circuit = client.post(
        f"/api/v1/projects/{project_id}/circuit/generate",
        json={"hardware_ir_id": hardware_id},
    )
    assert new_circuit.status_code == 201
    with Session(client.app.state.engine) as session:
        stale_bundle = SqlAlchemySchematicRepository(session).get(UUID(bundle["schematic"]["id"]))
        assert stale_bundle is not None
        assert stale_bundle.artifact.status.value == "STALE"
    stale = client.post(
        f"/api/v1/projects/{project_id}/schematic/validate",
        json={"schematic_id": bundle["schematic"]["id"]},
    )
    assert stale.status_code == 400
    assert stale.json()["error"]["details"]["reason"] == "STALE_CIRCUIT_IR"
