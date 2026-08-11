"""M11 MCUConfigIR generation, deterministic rules, and API persistence tests."""

from typing import Any
from uuid import UUID

import pytest
from eea_application.mcu_config import MCUConfigService
from eea_application.requirements import RequirementAnalysisService, RequirementProfileRegistry
from eea_application.schematic import SchematicService
from eea_backend.repositories import SqlAlchemyEvidenceRepository
from eea_backend.requirement_repositories import (
    SqlAlchemyRequirementProfileRepository,
    persist_requirement_analysis_bundle,
)
from eea_core.architecture import HardwareDeviceInstance, HardwareInterface, HardwareIR
from eea_core.circuit import CircuitIR
from eea_core.claims import EngineeringValue
from eea_core.enums import EngineeringDimension
from eea_core.errors import EngineeringError
from eea_core.mcu_config import (
    DMAIR,
    ADCConfig,
    ClockIR,
    GPIOConfig,
    InterruptConfigIR,
    PeripheralConfigIR,
    PWMConfig,
)
from eea_core.requirements import RequirementAnalysisDraft, RequirementDraft
from eea_core.schematic import SchematicIR
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

PROJECT_ID = UUID(int=110)
PIN_ID = UUID(int=1101)
DEVICE_ID = UUID(int=1102)
MODULE_ID = UUID(int=1103)


def _frequency(value: float, unit: str = "Hz") -> EngineeringValue:
    return EngineeringValue(unit=unit, dimension=EngineeringDimension.FREQUENCY, nominal=value)


def _hardware() -> HardwareIR:
    return HardwareIR(
        project_id=PROJECT_ID,
        architecture_id=UUID(int=1104),
        pin_plan_id=UUID(int=1105),
        pin_plan_revision=1,
        device_instances=[
            HardwareDeviceInstance(
                id=DEVICE_ID,
                name="MCU",
                device_ref="STM32G431",
                package="UFQFPN48",
                module_ref=MODULE_ID,
                pin_assignment_ids=[PIN_ID],
            )
        ],
        interfaces=[
            HardwareInterface(
                name="PWM_OUT",
                interface_type="TIM1",
                endpoint_refs=[str(DEVICE_ID), "external:pwm"],
                pin_assignment_ids=[PIN_ID],
            )
        ],
        pin_assignment_revisions={str(PIN_ID): 2},
    )


def _sources() -> tuple[HardwareIR, CircuitIR, SchematicIR]:
    hardware = _hardware()
    circuit = CircuitIR(
        project_id=PROJECT_ID,
        hardware_ir_id=hardware.id,
        hardware_ir_revision=hardware.revision,
        pin_assignment_revisions={str(PIN_ID): 2},
    )
    schematic = SchematicService().generate(circuit).schematic
    return hardware, circuit, schematic


def _config_inputs() -> tuple[
    ClockIR,
    list[GPIOConfig],
    list[PeripheralConfigIR],
    list[DMAIR],
    list[InterruptConfigIR],
    dict[str, object],
]:
    dma = DMAIR(
        controller="DMA1",
        channel_or_stream="CH1",
        request="ADC1",
        direction="PERIPHERAL_TO_MEMORY",
    )
    peripherals = [
        PeripheralConfigIR(
            instance="TIM1",
            mode="PWM",
            pwm=[
                PWMConfig(
                    timer="TIM1",
                    channel="CH1",
                    complementary_channel="CH1N",
                    switching_frequency=_frequency(20_000),
                    pin_assignment_ids=[PIN_ID],
                )
            ],
        ),
        PeripheralConfigIR(
            instance="ADC1",
            mode="REGULAR",
            adc=[
                ADCConfig(
                    instance="ADC1",
                    channels=["IN1"],
                    trigger_source="TIM1_UP",
                    dma_ref="ADC1",
                )
            ],
        ),
    ]
    capabilities: dict[str, object] = {
        "clock_sources": {"HSE": {"max_frequency_hz": 170_000_000}},
        "timers": {
            "TIM1": {
                "channels": ["CH1"],
                "complementary": True,
                "max_frequency_hz": 100_000,
            }
        },
        "adc": {"ADC1": {"channels": ["IN1"], "triggers": ["TIM1_UP"]}},
        "dma": {"DMA1": {"requests": ["ADC1"], "channels": ["CH1"]}},
        "interrupts": ["ADC1_1"],
    }
    return (
        ClockIR(source="HSE", target_frequency=_frequency(170, "MHz")),
        [GPIOConfig(pin_assignment_id=PIN_ID, signal_ref="pwm", mode="ALTERNATE")],
        peripherals,
        [dma],
        [InterruptConfigIR(source="ADC1", irq="ADC1_1", priority=3)],
        capabilities,
    )


def test_mcu_config_rules_are_deterministic_and_traceable() -> None:
    hardware, circuit, schematic = _sources()
    clock, gpio, peripherals, dma, interrupts, capabilities = _config_inputs()
    bundle = MCUConfigService().generate(
        hardware,
        circuit,
        schematic,
        device_instance_id=DEVICE_ID,
        clock=clock,
        gpio=gpio,
        peripherals=peripherals,
        dma=dma,
        interrupts=interrupts,
        capability_snapshot=capabilities,
    )

    statuses = {(result.rule_id, result.status) for result in bundle.rule_results}
    assert ("PINMAP_SOURCE_VALID", "PASS") in statuses
    assert ("CLOCK_SOURCE_INVALID", "PASS") in statuses
    assert ("TIMER_FREQUENCY_IMPOSSIBLE", "PASS") in statuses
    assert ("COMPLEMENTARY_PWM_MISSING", "PASS") not in statuses
    assert ("ADC_CHANNEL_INVALID", "PASS") in statuses
    assert ("ADC_TRIGGER_INVALID", "PASS") in statuses
    assert ("DMA_REQUEST_INVALID", "PASS") in statuses
    assert ("IRQ_PRIORITY_CONFLICT", "PASS") in statuses
    assert all(
        result.input_snapshot["mcu_config_id"] == str(bundle.config.id)
        for result in bundle.rule_results
    )

    bad_pwm = peripherals[0].pwm[0].model_copy(update={"channel": "CH9"})
    bad_peripherals = [peripherals[0].model_copy(update={"pwm": [bad_pwm]}), peripherals[1]]
    bad = bundle.config.model_copy(update={"peripherals": bad_peripherals})
    bad_results = MCUConfigService().validate(bad, hardware, circuit, schematic)
    assert any(
        result.rule_id == "TIMER_CHANNEL_CONFLICT" and result.status == "FAIL"
        for result in bad_results
    )

    unknown = bundle.config.model_copy(update={"capability_snapshot": {}})
    unknown_results = MCUConfigService().validate(unknown, hardware, circuit, schematic)
    assert any(
        result.rule_id == "CLOCK_SOURCE_INVALID" and result.status == "UNKNOWN"
        for result in unknown_results
    )
    assert not any(
        result.rule_id == "CLOCK_SOURCE_INVALID" and result.status == "PASS"
        for result in unknown_results
    )


def test_mcu_config_rejects_mismatched_source_revision() -> None:
    hardware, circuit, schematic = _sources()
    clock, gpio, peripherals, dma, interrupts, capabilities = _config_inputs()
    with pytest.raises(EngineeringError) as error:
        MCUConfigService().generate(
            hardware,
            circuit.model_copy(update={"hardware_ir_revision": 2}),
            schematic,
            device_instance_id=DEVICE_ID,
            clock=clock,
            gpio=gpio,
            peripherals=peripherals,
            dma=dma,
            interrupts=interrupts,
            capability_snapshot=capabilities,
        )
    assert error.value.details["reason"] == "SOURCE_REVISION_MISMATCH"


def _create_sources_for_api(
    client: Any,
) -> tuple[UUID, dict[str, Any], dict[str, Any], dict[str, Any]]:
    project_response = client.post("/api/v1/projects", json={"name": "M11 MCU config API"})
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
                        code="REQ-M11-MCU",
                        title="MCU configuration traceability",
                        statement="The MCU configuration shall retain all source revisions.",
                    )
                ],
            ),
        )
        saved = persist_requirement_analysis_bundle(session, analysis)
    pin_payload = {
        "analysis_id": str(saved.id),
        "device_ref": "STM32G431",
        "package": "UFQFPN48",
        "requirements": [
            {
                "signal_name": "m11-pwm-output",
                "required_peripheral": "TIM1",
                "required_function": "CH1",
                "requirement_ids": [str(saved.requirement_ids[0])],
            }
        ],
    }
    plan = client.post(
        f"/api/v1/projects/{project_id}/pin-planner/generate", json=pin_payload
    ).json()["data"]
    assignment_id = plan["assignments"][0]["id"]
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/pin-planner/assignments/{assignment_id}/lock",
            headers={"If-Match": 'W/"1"'},
            json={"actor": "m11", "reason": "MCUConfig source"},
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
    schematic = client.post(
        f"/api/v1/projects/{project_id}/schematic/generate",
        json={"circuit_id": circuit["id"]},
    ).json()["data"]["schematic"]
    return project_id, hardware, circuit, schematic


def test_mcu_config_api_persists_and_validates_current_sources(client: TestClient) -> None:
    project_id, hardware, circuit, schematic = _create_sources_for_api(client)
    assignment_id = hardware["device_instances"][0]["pin_assignment_ids"][0]
    device_instance_id = hardware["device_instances"][0]["id"]
    payload = {
        "hardware_ir_id": hardware["id"],
        "circuit_id": circuit["id"],
        "schematic_id": schematic["id"],
        "device_instance_id": device_instance_id,
        "clock": {
            "source": "HSE",
            "target_frequency": {"unit": "MHz", "dimension": "FREQUENCY", "nominal": 170},
        },
        "gpio": [
            {
                "pin_assignment_id": assignment_id,
                "signal_ref": "pwm",
                "mode": "ALTERNATE",
            }
        ],
        "peripherals": [
            {
                "instance": "TIM1",
                "mode": "PWM",
                "pwm": [
                    {
                        "timer": "TIM1",
                        "channel": "CH1",
                        "complementary_channel": "CH1N",
                        "switching_frequency": {
                            "unit": "Hz",
                            "dimension": "FREQUENCY",
                            "nominal": 20000,
                        },
                        "pin_assignment_ids": [assignment_id],
                    }
                ],
            },
            {
                "instance": "ADC1",
                "mode": "REGULAR",
                "adc": [
                    {
                        "instance": "ADC1",
                        "channels": ["IN1"],
                        "trigger_source": "TIM1_UP",
                        "dma_ref": "ADC1",
                    }
                ],
            },
        ],
        "dma": [
            {
                "controller": "DMA1",
                "channel_or_stream": "CH1",
                "request": "ADC1",
                "direction": "PERIPHERAL_TO_MEMORY",
            }
        ],
        "interrupts": [{"source": "ADC1", "irq": "ADC1_1", "priority": 3}],
        "capability_snapshot": {
            "clock_sources": {"HSE": {"max_frequency_hz": 170000000}},
            "timers": {
                "TIM1": {
                    "channels": ["CH1"],
                    "complementary": True,
                    "max_frequency_hz": 100000,
                }
            },
            "adc": {"ADC1": {"channels": ["IN1"], "triggers": ["TIM1_UP"]}},
            "dma": {"DMA1": {"requests": ["ADC1"], "channels": ["CH1"]}},
            "interrupts": ["ADC1_1"],
        },
    }
    generated = client.post(f"/api/v1/projects/{project_id}/mcu-config/generate", json=payload)
    assert generated.status_code == 201, generated.text
    bundle = generated.json()["data"]
    assert bundle["config"]["hardware_ir_id"] == hardware["id"]
    assert bundle["config"]["schematic_id"] == schematic["id"]
    assert any(result["status"] == "PASS" for result in bundle["rule_results"])

    fetched = client.get(f"/api/v1/projects/{project_id}/mcu-config")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["config"]["id"] == bundle["config"]["id"]

    validated = client.post(
        f"/api/v1/projects/{project_id}/mcu-config/validate",
        json={"config_id": bundle["config"]["id"]},
    )
    assert validated.status_code == 200, validated.text
    assert validated.json()["data"]["config_id"] == bundle["config"]["id"]
    assert any(
        result["rule_id"] == "ADC_TRIGGER_INVALID"
        for result in validated.json()["data"]["rule_results"]
    )
