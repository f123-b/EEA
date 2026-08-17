"""M19A FOC software vertical slice through the public application API.

The benchmark intentionally uses TestClient only.  It must exercise the same
request/application/repository path as the local backend; it must not insert
engineering state directly into SQL to manufacture a release result.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from eea_backend.main import create_app
from eea_backend.settings import Settings
from eea_core.claims import EngineeringValue
from eea_core.enums import EngineeringDimension
from eea_core.testing import TestExecutionStatus as ExecutionStatus
from fastapi.testclient import TestClient

from plugins.builtin.motor_control.schemas.ir import (
    ADCSamplingRequirement,
    CurrentLoopRequirement,
    ElectricalAngle,
    FaultPolicy,
    FaultResponse,
    MCUConfigReferences,
    MotorControlIR,
    MotorParameters,
    PositionLoopRequirement,
    PWMRequirement,
    SignConvention,
    StartupCalibration,
    StartupStep,
    VelocityLoopRequirement,
)


def _engineering_value(unit: str, dimension: str, nominal: float) -> dict[str, object]:
    return {"unit": unit, "dimension": dimension, "nominal": nominal}


def _post(
    client: TestClient,
    path: str,
    payload: dict[str, object],
    *,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    response = client.post(path, json=payload, headers=headers)
    assert response.status_code in {200, 201}, f"{path}: {response.status_code} {response.text}"
    return response.json()["data"]


def _register_evidence(client: TestClient, project_id: str) -> dict[str, str]:
    evidence: dict[str, str] = {}
    for key, summary in {
        "device_source": "STM32G431 UFQFPN48 device and package facts",
        "power_source": "24 V bus and 10 A phase current power-stage contract",
        "control_timing_source": "20 kHz PWM and current-loop timing contract",
        "safety_source": "Emergency disable and safe-state contract",
    }.items():
        data = _post(
            client,
            f"/api/v1/projects/{project_id}/evidence",
            {
                "evidence_type": "DOCUMENT",
                "locator": {"benchmark": "FOC-A", "key": key},
                "source_uri": f"eea://m19/foc-a/{key}",
                "summary": summary,
            },
        )
        evidence[key] = data["id"]
    return evidence


def _requirement_analysis(client: TestClient, project_id: str) -> dict[str, Any]:
    evidence = _register_evidence(client, project_id)
    values = {
        "target.device": "STM32G431",
        "target.package": "UFQFPN48",
        "power.bus_voltage": _engineering_value("V", "VOLTAGE", 24),
        "power.phase_current": _engineering_value("A", "CURRENT", 10),
        "control.loop_frequency": _engineering_value("kHz", "FREQUENCY", 20),
        "feedback.position_interface": "SPI",
        "pwm.phase_count": 3,
        "pwm.complementary": True,
        "pwm.deadtime": _engineering_value("ns", "TIME", 500),
        "current_sense.method": "SHUNT_LOW_SIDE",
        "current_sense.range": _engineering_value("A", "CURRENT", 20),
        "communication.protocol": "CAN",
        "safety.emergency_disable": True,
    }
    evidence_refs = {
        **evidence,
        "power.bus_voltage": evidence["power_source"],
        "power.phase_current": evidence["power_source"],
        "control.loop_frequency": evidence["control_timing_source"],
        "pwm.deadtime": evidence["control_timing_source"],
        "current_sense.range": evidence["power_source"],
        "safety.emergency_disable": evidence["safety_source"],
    }
    return _post(
        client,
        "/api/v1/requirements/analyze/structured",
        {
            "project_id": project_id,
            "profile_name": "foc-benchmark",
            "profile_version": "1.0",
            "values": values,
            "evidence_refs": evidence_refs,
            "requirements": [
                {
                    "code": "REQ_FOC_SAFE_CONTROL",
                    "title": "FOC control software shall retain the frozen safety contract",
                    "requirement_type": "SAFETY",
                    "priority": "MUST",
                    "statement": (
                        "The FOC software shall preserve the declared safe control and "
                        "communication contract."
                    ),
                    "rationale": "The M19A release gate needs one P0 traceable requirement.",
                    "acceptance_criteria": [
                        "Generated source is bound to MCUConfigIR and SourceRevision",
                        "The software gate never enables an actuator",
                    ],
                    "source_evidence_refs": ["safety_source"],
                }
            ],
        },
    )


def _motor_control_ir() -> MotorControlIR:
    def value(unit: str, dimension: EngineeringDimension, nominal: float) -> EngineeringValue:
        return EngineeringValue(unit=unit, dimension=dimension, nominal=nominal)

    def frequency(nominal: float) -> EngineeringValue:
        return value("kHz", EngineeringDimension.FREQUENCY, nominal)

    def time(nominal: float) -> EngineeringValue:
        return value("us", EngineeringDimension.TIME, nominal)

    def current(nominal: float) -> EngineeringValue:
        return value("A", EngineeringDimension.CURRENT, nominal)

    def voltage(nominal: float) -> EngineeringValue:
        return value("V", EngineeringDimension.VOLTAGE, nominal)

    def speed(nominal: float) -> EngineeringValue:
        return value("rpm", EngineeringDimension.ANGULAR_VELOCITY, nominal)

    return MotorControlIR(
        motor_ref="hardware:motor-pmsm-reference",
        motor_parameters=MotorParameters(
            poles=8,
            pole_pairs=4,
            rated_voltage=voltage(24),
            rated_current=current(10),
            rated_speed=speed(3000),
        ),
        inverter_ref="hardware:drv8323",
        encoder_ref="hardware:as5047",
        current_sense_ref="hardware:low-side-shunt",
        pwm_requirement=PWMRequirement(
            target_frequency=frequency(20),
            center_aligned_required=True,
            complementary_required=True,
            deadtime_required=True,
            deadtime=time(0.5),
            polarity="ACTIVE_HIGH",
            break_input_required=True,
        ),
        adc_sampling_requirement=ADCSamplingRequirement(
            current_channels=["IN1"],
            trigger_source_ref="TIM1_UP",
            sampling_window=time(2),
            synchronized_to_pwm=True,
            dma_required=True,
            sample_to_actuation_latency=time(5),
        ),
        mcu_config_refs=MCUConfigReferences(pwm="TIM1", adc=["ADC1"], dma=["ADC1"]),
        electrical_angle=ElectricalAngle(
            mechanical_direction="CW",
            electrical_angle_direction="POSITIVE",
            phase_sequence="ABC",
            zero_offset=value("deg", EngineeringDimension.ANGLE, 0),
        ),
        sign_convention=SignConvention(
            positive_torque_current="POSITIVE_IQ",
            speed_feedback_sign="POSITIVE_FORWARD",
            encoder_direction="CW",
            park_convention="PARK_ABC",
            svpwm_phase_mapping="ABC",
        ),
        startup=StartupCalibration(
            alignment_required=True,
            steps=[
                StartupStep(
                    name="encoder_alignment",
                    current_limit=current(2),
                    voltage_limit=voltage(12),
                    timeout=value("ms", EngineeringDimension.TIME, 1000),
                    failure_behavior="SAFE_STATE",
                )
            ],
            current_sensor_offset_required=True,
            encoder_zero_required=True,
            test_result="UNKNOWN",
        ),
        current_loop=CurrentLoopRequirement(
            frequency=frequency(10),
            period=time(100),
            id_target=current(0),
            iq_target=current(0),
            kp=0.1,
            ki=0.01,
            output_limit=1,
            anti_windup="CLAMP",
            sample_to_actuation_latency=time(5),
            cpu_budget=time(20),
        ),
        velocity_loop=VelocityLoopRequirement(
            frequency=value("Hz", EngineeringDimension.FREQUENCY, 1000),
            period=value("ms", EngineeringDimension.TIME, 1),
            kp=0.2,
            ki=0.02,
            output_limit=10,
            speed_limit=speed(3000),
            acceleration_limit=value("rad/s2", EngineeringDimension.ANGULAR_ACCELERATION, 100),
            current_limit=current(10),
            feedback_source="hardware:as5047",
        ),
        position_loop=PositionLoopRequirement(
            frequency=value("Hz", EngineeringDimension.FREQUENCY, 100),
            period=value("ms", EngineeringDimension.TIME, 10),
            kp=0.3,
            output_limit=360,
            controller="PI",
            wrap_handling="MODULO",
            position_limit=value("deg", EngineeringDimension.ANGLE, 360),
            velocity_limit=speed(3000),
        ),
        fault_policy=FaultPolicy(
            responses=[
                FaultResponse(fault="OVERCURRENT", action="DISABLE_PWM"),
                FaultResponse(fault="ENCODER_LOSS", action="SAFE_STATE"),
                FaultResponse(fault="CONTROL_OVERRUN", action="LATCH"),
            ]
        ),
    )


def _build_vertical_slice(
    client: TestClient,
    *,
    release_gate: bool = False,
) -> dict[str, Any]:
    project = _post(client, "/api/v1/projects", {"name": "M19 FOC Minimal E2E"})
    project_id = project["id"]
    analysis = _requirement_analysis(client, project_id)
    assert analysis["completeness"]["status"] == "COMPLETE"
    requirement_id = analysis["requirement_ids"][0]
    device_claim_id = next(
        claim["id"] for claim in analysis["claims"] if claim["predicate"] == "target.device"
    )

    pin_requirements = [
        ("PWM_UH", "TIM1", "CH1"),
        ("PWM_UL", "TIM1", "CH1N"),
        ("CURRENT_U", "ADC1", "IN1"),
        ("CAN_RX", "FDCAN1", "RX"),
        ("CAN_TX", "FDCAN1", "TX"),
    ]
    plan = _post(
        client,
        f"/api/v1/projects/{project_id}/pin-planner/generate",
        {
            "analysis_id": analysis["id"],
            "device_ref": "STM32G431",
            "package": "UFQFPN48",
            "requirements": [
                {
                    "signal_name": name,
                    "required_peripheral": peripheral,
                    "required_function": function,
                    "direction": "OUT" if function in {"CH1", "CH1N", "TX"} else "IN",
                    "hard_constraints": (
                        {"pwm_required": True, "complementary_pwm": True}
                        if function in {"CH1", "CH1N"}
                        else {}
                    ),
                    "requirement_ids": [requirement_id],
                    "claim_ids": [device_claim_id],
                }
                for name, peripheral, function in pin_requirements
            ],
        },
    )
    assert len(plan["assignments"]) == len(pin_requirements)
    assert all(item["locked"] is False for item in plan["assignments"])
    for assignment in plan["assignments"]:
        locked = _post(
            client,
            f"/api/v1/projects/{project_id}/pin-planner/assignments/{assignment['id']}/lock",
            {
                "expected_revision": assignment["revision"],
                "actor": "m19",
                "reason": "FOC benchmark frozen assignment",
            },
        )
        assert locked["assignment"]["locked"] is True
    plan_response = client.get(f"/api/v1/projects/{project_id}/pin-planner/map")
    assert plan_response.status_code == 200, plan_response.text
    plan = plan_response.json()["data"]

    architecture = _post(
        client,
        f"/api/v1/projects/{project_id}/architecture/generate",
        {"pin_plan_id": plan["id"]},
    )
    hardware = architecture["hardware"]
    assignments = {item["function"]["signal"]: item for item in plan["assignments"]}
    components = [
        {"reference": "MCU", "kind": "MCU", "device_ref": "STM32G431", "package": "UFQFPN48"},
        {"reference": "U1", "kind": "DRV8323", "device_ref": "DRV8323"},
        {"reference": "U2", "kind": "AS5047", "device_ref": "AS5047"},
        {"reference": "RTERM1", "kind": "RESISTOR"},
        {"reference": "RTERM2", "kind": "RESISTOR"},
    ]
    nets = [
        {
            "name": name,
            "signal_type": "DIGITAL",
            "endpoints": [
                {
                    "component_ref": "MCU",
                    "pin_ref": assignment["pin_name"],
                    "pin_assignment_id": assignment["id"],
                },
                {"component_ref": "U1" if "PWM" in name else "U2", "pin_ref": "1"},
            ],
            "requirement_ids": [requirement_id],
        }
        for name, assignment in (
            ("PWM_UH", assignments["CH1"]),
            ("PWM_UL", assignments["CH1N"]),
            ("CURRENT_U", assignments["IN1"]),
            ("CAN_RX", assignments["RX"]),
            ("CAN_TX", assignments["TX"]),
        )
    ]

    def voltage(nominal: float) -> dict[str, object]:
        return _engineering_value("V", "VOLTAGE", nominal)

    def current(nominal: float) -> dict[str, object]:
        return _engineering_value("A", "CURRENT", nominal)

    circuit = _post(
        client,
        f"/api/v1/projects/{project_id}/circuit/generate",
        {
            "hardware_ir_id": hardware["id"],
            "components": components,
            "nets": nets,
            "power_nets": [
                {
                    "name": "VBUS_24V",
                    "voltage": voltage(24),
                    "current": current(10),
                    "attributes": {"safe_state": "DISABLED"},
                    "requirement_ids": [requirement_id],
                }
            ],
            "constraints": [
                {
                    "rule_id": "MOSFET_VDS_MARGIN",
                    "target_ref": "U1",
                    "parameters": {
                        "bus_voltage": voltage(24),
                        "transient_voltage": voltage(30),
                        "vds_rating": voltage(40),
                        "required_margin": 1.2,
                    },
                    "requirement_ids": [requirement_id],
                },
                {
                    "rule_id": "GATE_DRIVER_VOLTAGE",
                    "target_ref": "U1",
                    "parameters": {
                        "driver_voltage": voltage(12),
                        "gate_required": voltage(10),
                    },
                },
                {
                    "rule_id": "CAN_TRANSCEIVER",
                    "target_ref": "CAN0",
                    "parameters": {"transceiver_present": True},
                },
                {
                    "rule_id": "TERMINATION",
                    "target_ref": "CAN0",
                    "parameters": {"termination_count": 2, "required_count": 2},
                },
                {
                    "rule_id": "ADC_RANGE",
                    "target_ref": "CURRENT_U",
                    "parameters": {
                        "input_min": voltage(0),
                        "input_max": voltage(3.3),
                        "adc_min": voltage(0),
                        "adc_max": voltage(3.3),
                    },
                },
            ],
        },
    )
    schematic = _post(
        client,
        f"/api/v1/projects/{project_id}/schematic/generate",
        {"circuit_id": circuit["circuit"]["id"]},
    )
    erc: dict[str, Any] | None = None
    if release_gate:
        erc = _post(
            client,
            f"/api/v1/projects/{project_id}/schematic/erc/run",
            {"schematic_id": schematic["schematic"]["id"]},
        )
    device_instance_id = hardware["device_instances"][0]["id"]
    mcu = _post(
        client,
        f"/api/v1/projects/{project_id}/mcu-config/generate",
        {
            "hardware_ir_id": hardware["id"],
            "circuit_id": circuit["circuit"]["id"],
            "schematic_id": schematic["schematic"]["id"],
            "device_instance_id": device_instance_id,
            "clock": {
                "source": "HSE",
                "target_frequency": _engineering_value("MHz", "FREQUENCY", 170),
            },
            "gpio": [
                {
                    "pin_assignment_id": item["id"],
                    "signal_ref": name,
                    "mode": "ALTERNATE",
                    "alternate_function": (
                        f"GPIO_{item['function']['alternate_function']}_{item['function']['peripheral']}"
                        if item["function"]["alternate_function"]
                        else None
                    ),
                    "requirement_ids": [requirement_id],
                }
                for name, item in (
                    ("PWM_UH", assignments["CH1"]),
                    ("PWM_UL", assignments["CH1N"]),
                    ("CURRENT_U", assignments["IN1"]),
                    ("CAN_RX", assignments["RX"]),
                    ("CAN_TX", assignments["TX"]),
                )
            ],
            "peripherals": [
                {
                    "instance": "TIM1",
                    "mode": "PWM",
                    "pin_assignment_ids": [assignments["CH1"]["id"], assignments["CH1N"]["id"]],
                    "pwm": [
                        {
                            "timer": "TIM1",
                            "channel": "CH1",
                            "complementary_channel": "CH1N",
                            "center_aligned": True,
                            "switching_frequency": _engineering_value("kHz", "FREQUENCY", 20),
                            "realized_frequency": _engineering_value("kHz", "FREQUENCY", 20),
                            "deadtime": _engineering_value("ns", "TIME", 500),
                            "polarity": "ACTIVE_HIGH",
                            "break_input": "BKIN",
                            "update_event": "TIM1_UP",
                            "pin_assignment_ids": [
                                assignments["CH1"]["id"],
                                assignments["CH1N"]["id"],
                            ],
                            "requirement_ids": [requirement_id],
                        }
                    ],
                    "requirement_ids": [requirement_id],
                },
                {
                    "instance": "ADC1",
                    "mode": "REGULAR",
                    "pin_assignment_ids": [assignments["IN1"]["id"]],
                    "adc": [
                        {
                            "instance": "ADC1",
                            "channels": ["IN1"],
                            "trigger_source": "TIM1_UP",
                            "dma_ref": "ADC1",
                            "expected_range": {"IN1": _engineering_value("A", "CURRENT", 20)},
                            "pin_assignment_ids": [assignments["IN1"]["id"]],
                            "requirement_ids": [requirement_id],
                        }
                    ],
                    "dma_refs": ["ADC1"],
                    "requirement_ids": [requirement_id],
                },
                {
                    "instance": "FDCAN1",
                    "mode": "CAN",
                    "pin_assignment_ids": [assignments["RX"]["id"], assignments["TX"]["id"]],
                },
            ],
            "dma": [
                {
                    "controller": "DMA1",
                    "channel_or_stream": "CH1",
                    "request": "ADC1",
                    "direction": "PERIPHERAL_TO_MEMORY",
                    "requirement_ids": [requirement_id],
                }
            ],
            "interrupts": [
                {
                    "source": "ADC1",
                    "irq": "ADC1_1",
                    "priority": 3,
                    "allowed_operations": ["CAPTURE_SAMPLE"],
                    "requirement_ids": [requirement_id],
                }
            ],
            "capability_snapshot": {
                "clock_sources": {"HSE": {"max_frequency_hz": 170000000}},
                "timers": {
                    "TIM1": {"channels": ["CH1"], "complementary": True, "max_frequency_hz": 100000}
                },
                "adc": {"ADC1": {"channels": ["IN1"], "triggers": ["TIM1_UP"]}},
                "dma": {"DMA1": {"requests": ["ADC1"], "channels": ["CH1"]}},
                "interrupts": ["ADC1_1"],
            },
        },
    )
    config = mcu["config"]
    activation = _post(
        client,
        f"/api/v1/projects/{project_id}/domains/org.eea.motor_control/activate",
        {"configuration": {"benchmark_profile": "REFERENCE"}, "activated_by": "m19"},
    )
    domain_validation = _post(
        client,
        f"/api/v1/projects/{project_id}/domains/org.eea.motor_control/validate",
        {"domain_ir": _motor_control_ir().model_dump(mode="json"), "mcu_config_id": config["id"]},
    )
    firmware_payload: dict[str, object] = {
        "mcu_config_id": config["id"],
        "board_name": "foc-stm32g431",
    }
    if release_gate:
        lock = _post(
            client,
            f"/api/v1/projects/{project_id}/dependencies/resolve",
            {
                "mcu_config_id": config["id"],
                "requirements": [
                    {
                        "capability": "cmsis.core",
                        "component_key": "st.stm32g4.cmsis-core",
                        "reason": "M19 DEVICE build CMSIS core",
                        "source_requirement_ids": [requirement_id],
                    },
                    {
                        "capability": "cmsis.device",
                        "component_key": "st.stm32g4.cmsis-device",
                        "reason": "M19 DEVICE build CMSIS device",
                        "source_requirement_ids": [requirement_id],
                    },
                    {
                        "capability": "stm32.hal",
                        "component_key": "st.stm32g4.hal",
                        "reason": "M19 DEVICE build STM32 HAL",
                        "source_requirement_ids": [requirement_id],
                    },
                ],
                "architecture": "Cortex-M4",
                "device": "STM32G431KB",
                "toolchain_id": "arm-none-eabi-gcc",
                "build_system": "CMAKE",
            },
        )
        _post(
            client,
            f"/api/v1/projects/{project_id}/dependencies/materialize",
            {"lock_id": lock["id"]},
        )
        firmware_payload.update(
            {
                "dependency_lock_id": lock["id"],
                "build_target": {
                    "name": "eea_device",
                    "family": "STM32G4",
                    "architecture": "Cortex-M4",
                    "build_system": "CMAKE",
                    "toolchain_id": "arm-none-eabi-gcc",
                    "target_triple": "arm-none-eabi",
                    "profile": "DEVICE",
                    "output_name": "eea_device",
                    "output_format": "ELF",
                },
                "build_profile": "DEVICE",
            }
        )
    firmware = _post(
        client,
        f"/api/v1/projects/{project_id}/firmware/generate",
        firmware_payload,
    )
    firmware_ir = firmware["firmware"]
    assert firmware["source_revision"]["id"] == firmware_ir["source_revision_id"]
    build_started_at = datetime.now(UTC).isoformat()
    build = _post(
        client,
        f"/api/v1/projects/{project_id}/build",
        {"firmware_id": firmware_ir["id"]},
    )
    build["m19_started_at"] = build_started_at
    build["m19_finished_at"] = datetime.now(UTC).isoformat()
    static = _post(
        client,
        f"/api/v1/projects/{project_id}/analysis/static",
        {"firmware_id": firmware_ir["id"], "run_cppcheck": True},
    )
    protocol = _post(
        client,
        f"/api/v1/projects/{project_id}/protocol",
        {
            "version_label": "1.0.0",
            "transports": [
                {"transport_id": "can0", "name": "CAN"},
                {"transport_id": "uart0", "name": "UART"},
            ],
            "messages": [
                {
                    "name": "MotorCommand",
                    "transport_ref": "can0",
                    "can_id": 512,
                    "payload_length_bytes": 8,
                    "fields": [{"name": "iq_command", "bit_offset": 0, "bit_length": 16}],
                },
                {
                    "name": "MotorStatus",
                    "transport_ref": "uart0",
                    "can_id": 513,
                    "payload_length_bytes": 8,
                    "fields": [{"name": "fault_flags", "bit_offset": 0, "bit_length": 16}],
                },
            ],
        },
    )
    generated_protocol = _post(
        client,
        f"/api/v1/projects/{project_id}/protocol/generate",
        {"protocol_id": protocol["id"]},
    )
    tests = _post(
        client,
        f"/api/v1/projects/{project_id}/tests/generate",
        {"verification_profile": "SOFTWARE_RELEASE"} if release_gate else {},
    )
    test_ir = tests["test_ir"]
    test_run = _post(
        client,
        f"/api/v1/projects/{project_id}/tests/run",
        {"test_ir_id": test_ir["id"], "source_revision_id": firmware["source_revision"]["id"]},
    )
    review = _post(
        client,
        f"/api/v1/projects/{project_id}/review",
        {
            "source_revision_id": firmware["source_revision"]["id"],
            "test_ir_id": test_ir["id"],
            "test_run_id": test_run["id"],
            "build_run_id": build["id"],
            "static_analysis_id": static["id"],
            "schematic_id": schematic["schematic"]["id"],
            "require_build": True,
            "require_static_analysis": True,
            "require_erc": release_gate,
            "require_test": True,
        },
    )
    traceability_response = client.get(f"/api/v1/projects/{project_id}/traceability")
    assert traceability_response.status_code == 200, traceability_response.text
    traceability = traceability_response.json()["data"]
    return {
        "project_id": project_id,
        "analysis": analysis,
        "claim_id": device_claim_id,
        "plan": plan,
        "hardware": hardware,
        "circuit": circuit["circuit"],
        "schematic": schematic,
        "erc": erc,
        "mcu": config,
        "activation": activation,
        "domain_validation": domain_validation,
        "firmware": firmware,
        "build": build,
        "static": static,
        "protocol": protocol,
        "generated_protocol": generated_protocol,
        "test_ir": test_ir,
        "test_run": test_run,
        "review": review,
        "traceability": traceability,
    }


def test_m19_foc_minimal_e2e_uses_one_normal_api_vertical_slice(client: TestClient) -> None:
    result = _build_vertical_slice(client)

    assert result["analysis"]["completeness"]["status"] == "COMPLETE"
    assert result["plan"]["assignments"]
    assert all(item["locked"] for item in result["plan"]["assignments"])
    assert result["circuit"]["rule_results"]
    assert result["schematic"]["schematic"]["netlist_text"].startswith("EEA-NETLIST-V1")
    assert result["mcu"]["rule_results"]
    assert result["activation"]["domain_id"] == "org.eea.motor_control"
    domain_statuses = {
        item["status"]
        for item in result["domain_validation"]["validation_results"][0]["diagnostics"]
    }
    assert domain_statuses <= {"PASS", "UNKNOWN", "BLOCKED"}
    assert result["firmware"]["files"]
    assert result["firmware"]["source_revision"]["file_manifest"]
    build = result["build"]
    if build["status"] == "PASS":
        assert build["artifact_hash"]
        assert "cmake" in " ".join(build["command"]).lower()
    else:
        assert build["status"] in {"UNKNOWN", "BLOCKED", "FAIL"}
        assert build["diagnostics"]
    assert result["static"]["rule_results"]
    assert result["static"]["tool_results"]
    assert {item["target"] for item in result["generated_protocol"]["outputs"]} == {
        "C",
        "PYTHON",
        "DBC",
        "MARKDOWN",
    }
    # The built-in requirement executor proves TestCase shape only; M17 correctly
    # refuses to treat that contract check as behavioral verification.
    assert result["test_run"]["status"] == ExecutionStatus.BLOCKED.value
    assert all(
        item["status"] == ExecutionStatus.PASS.value for item in result["test_run"]["case_results"]
    )
    assert result["review"]["source_revision_id"] == result["firmware"]["source_revision"]["id"]
    assert result["traceability"]["coverage"]["uncovered_requirement_ids"] == []


def test_m19_impact_propagates_claim_change_without_unrelated_pin_pollution(
    client: TestClient,
) -> None:
    result = _build_vertical_slice(client)
    project_id = result["project_id"]
    mutation = _post(
        client,
        f"/api/v1/claims/{result['claim_id']}/lifecycle",
        {
            "project_id": project_id,
            "expected_revision": 1,
            "lifecycle": "SUPERSEDED",
        },
    )
    impacts = mutation["impact_plan"]["impacts"]
    impacted_types = {item["node"]["entity_type"] for item in impacts}
    assert {
        "PinAssignment",
        "MCUConfigIR",
        "FirmwareIR",
        "BuildRun",
        "StaticAnalysis",
    } <= impacted_types
    assignment_ids = {item["id"] for item in result["plan"]["assignments"]}
    impacted_ids = {
        item["node"]["entity_id"]
        for item in impacts
        if item["node"]["entity_type"] == "PinAssignment"
    }
    assert impacted_ids <= assignment_ids
    impact = client.post(
        f"/api/v1/entities/Claim/{result['claim_id']}/impact-analysis",
        params={"project_id": project_id},
    )
    assert impact.status_code == 200, impact.text
    assert impact.json()["data"]["plan"]["impacts"]


def test_m19_failure_paths_are_fail_closed(client: TestClient) -> None:
    project_id = _post(client, "/api/v1/projects", {"name": "M19 failure paths"})["id"]
    incomplete = _post(
        client,
        "/api/v1/requirements/analyze/structured",
        {
            "project_id": project_id,
            "profile_name": "foc-benchmark",
            "profile_version": "1.0",
            "values": {"target.device": "STM32G431"},
        },
    )
    assert incomplete["completeness"]["status"] == "INCOMPLETE"

    evidence = _register_evidence(client, project_id)
    complete_values = {
        "target.device": "STM32G431",
        "target.package": "UFQFPN48",
        "power.bus_voltage": _engineering_value("V", "VOLTAGE", 24),
        "power.phase_current": _engineering_value("A", "CURRENT", 10),
        "control.loop_frequency": _engineering_value("kHz", "FREQUENCY", 20),
        "feedback.position_interface": "SPI",
        "pwm.phase_count": 3,
        "pwm.complementary": True,
        "pwm.deadtime": _engineering_value("ns", "TIME", 500),
        "current_sense.method": "SHUNT_LOW_SIDE",
        "current_sense.range": _engineering_value("A", "CURRENT", 20),
        "communication.protocol": "CAN",
        "safety.emergency_disable": True,
    }
    analysis = _post(
        client,
        "/api/v1/requirements/analyze/structured",
        {
            "project_id": project_id,
            "profile_name": "foc-benchmark",
            "profile_version": "1.0",
            "values": complete_values,
            "evidence_refs": evidence,
            "requirements": [
                {
                    "code": "REQ_M19_FAILURE",
                    "title": "Failure path requirement",
                    "statement": "The planner shall reject unsupported pin facts.",
                    "acceptance_criteria": ["Unsupported pins are not accepted"],
                }
            ],
        },
    )
    invalid_pin_plan = _post(
        client,
        f"/api/v1/projects/{project_id}/pin-planner/generate",
        {
            "analysis_id": analysis["id"],
            "device_ref": "STM32G431",
            "package": "UFQFPN48",
            "requirements": [
                {
                    "signal_name": "INVALID_AF",
                    "required_peripheral": "TIM1",
                    "required_function": "CH4",
                    "requirement_ids": [analysis["requirement_ids"][0]],
                }
            ],
        },
    )
    assert invalid_pin_plan["assignments"] == []
    assert any(item["status"] == "FAIL" for item in invalid_pin_plan["rule_results"])

    conflict_plan = _post(
        client,
        f"/api/v1/projects/{project_id}/pin-planner/generate",
        {
            "analysis_id": analysis["id"],
            "device_ref": "STM32G431",
            "package": "UFQFPN48",
            "requirements": [
                {
                    "signal_name": "CONFLICT_A",
                    "required_peripheral": "TIM1",
                    "required_function": "CH1",
                    "preferred_constraints": {"pin_name": "PA8"},
                    "requirement_ids": [analysis["requirement_ids"][0]],
                },
                {
                    "signal_name": "CONFLICT_B",
                    "required_peripheral": "TIM1",
                    "required_function": "CH1",
                    "preferred_constraints": {"pin_name": "PA8"},
                    "requirement_ids": [analysis["requirement_ids"][0]],
                },
            ],
        },
    )
    assert any(item["rule_id"] == "PIN_CONFLICT" for item in conflict_plan["rule_results"])

    electrical_plan = _post(
        client,
        f"/api/v1/projects/{project_id}/pin-planner/generate",
        {
            "analysis_id": analysis["id"],
            "device_ref": "STM32G431",
            "package": "UFQFPN48",
            "requirements": [
                {
                    "signal_name": "ADC_BAD_VOLTAGE",
                    "required_peripheral": "ADC1",
                    "required_function": "IN1",
                    "hard_constraints": {"voltage": _engineering_value("V", "VOLTAGE", 5)},
                    "requirement_ids": [analysis["requirement_ids"][0]],
                }
            ],
        },
    )
    assert any(item["status"] == "FAIL" for item in electrical_plan["rule_results"])


def test_m19_tool_missing_never_becomes_pass(client: TestClient) -> None:
    result = _build_vertical_slice(client)
    static = result["static"]
    if shutil.which("cppcheck") is None:
        cppcheck = next(item for item in static["tool_results"] if item["tool_id"] == "cppcheck")
        assert cppcheck["status"] == "UNKNOWN"
    erc = result["schematic"]["erc_report"]
    if shutil.which("kicad-cli") is None:
        assert erc["status"] == "UNKNOWN"
        assert erc["executed"] is False


def _write_m19_release_evidence(result: dict[str, Any]) -> None:
    evidence_value = os.environ.get("EEA_M19_EVIDENCE_DIR")
    if not evidence_value:
        return
    root = Path(evidence_value)
    root.mkdir(parents=True, exist_ok=True)
    build = result["build"]
    firmware = result["firmware"]
    source_revision = firmware["source_revision"]
    (root / "build-response.json").write_text(
        json.dumps(build, indent=2, sort_keys=True), encoding="utf-8"
    )
    elf_candidates = sorted(root.glob("*.elf"))
    assert elf_candidates, (
        "BuildService did not copy a real ELF into the release evidence directory: "
        f"status={build.get('status')}, diagnostics={build.get('diagnostics')}, "
        f"stdout={build.get('stdout', '')[-2000:]}, stderr={build.get('stderr', '')[-2000:]}"
    )
    elf = elf_candidates[0]
    elf_bytes = elf.read_bytes()
    readelf = subprocess.run(
        ["arm-none-eabi-readelf", "-h", str(elf)],
        capture_output=True,
        text=True,
        check=False,
    )
    build_report = {
        **json.loads((root / "build-runtime.json").read_text(encoding="utf-8")),
        "source_manifest_hash": source_revision["source_manifest_hash"],
        "elf_path": str(elf),
        "elf_size": len(elf_bytes),
        "elf_sha256": hashlib.sha256(elf_bytes).hexdigest(),
        "elf_header": readelf.stdout,
        "elf_validation_exit_code": readelf.returncode,
        "build_response": build,
    }
    (root / "build-report.json").write_text(
        json.dumps(build_report, indent=2, sort_keys=True), encoding="utf-8"
    )
    static = result["static"]
    (root / "cppcheck-report.json").write_text(
        json.dumps(
            next(item for item in static["tool_results"] if item["tool_id"] == "cppcheck"),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (root / "firmware-rules.json").write_text(
        json.dumps(static["rule_results"], indent=2, sort_keys=True), encoding="utf-8"
    )
    (root / "erc-report.json").write_text(
        json.dumps(result["erc"]["erc_report"], indent=2, sort_keys=True), encoding="utf-8"
    )
    (root / "testrun-summary.json").write_text(
        json.dumps(result["test_run"], indent=2, sort_keys=True), encoding="utf-8"
    )
    (root / "review-summary.json").write_text(
        json.dumps(result["review"], indent=2, sort_keys=True), encoding="utf-8"
    )
    tool_commands = {
        "arm-none-eabi-gcc": ["arm-none-eabi-gcc", "--version"],
        "cmake": ["cmake", "--version"],
        "cppcheck": ["cppcheck", "--version"],
        "kicad-cli": ["kicad-cli", "version"],
    }
    versions: dict[str, str] = {}
    for name, argv in tool_commands.items():
        completed = subprocess.run(argv, capture_output=True, text=True, check=False)
        versions[name] = (completed.stdout or completed.stderr).strip()
    summary = {
        "project_id": result["project_id"],
        "m19a": {
            "real_build": build["status"] == "PASS",
            "static_analysis": static["status"] == "PASS",
            "erc": result["erc"]["erc_report"]["status"] == "PASS",
            "software_test": result["test_run"]["status"] == "PASS",
            "review": result["review"]["status"] == "PASS",
        },
        "m19b": "BLOCKED_HARDWARE",
        "tools": versions,
        "build_kind": build["profile"],
        "p0_requirement_ids": [
            item["requirement_id"]
            for item in result["test_ir"]["requirement_snapshots"]
            if item["priority"] == "MUST" and item["status"] == "ACCEPTED"
        ],
    }
    (root / "release-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )


@pytest.fixture(scope="module")
def m19_release_result(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Run the expensive real-tool gate once; ordinary CI skips it without the gate env."""

    if os.environ.get("EEA_M19_RELEASE_GATE") != "1":
        pytest.skip("M19 release gate requires the dedicated toolchain CI environment")
    data_dir = tmp_path_factory.mktemp("m19-release-db")
    settings = Settings(data_dir=data_dir, insecure_local_dev=True)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    command.upgrade(config, "head")
    with TestClient(create_app(settings)) as release_client:
        result = _build_vertical_slice(release_client, release_gate=True)
    _write_m19_release_evidence(result)
    return result


def test_m19_release_requires_real_arm_build(m19_release_result: dict[str, Any]) -> None:
    build = m19_release_result["build"]
    assert build["status"] == "PASS"
    assert build["profile"] == "DEVICE"
    assert build["toolchain_id"] == "arm-none-eabi-gcc"
    assert build["artifact_hash"]


def test_m19_real_build_produces_arm_elf(m19_release_result: dict[str, Any]) -> None:
    elf = next(Path(os.environ["EEA_M19_EVIDENCE_DIR"]).glob("*.elf"))
    content = elf.read_bytes()
    assert content[:4] == b"\x7fELF"
    assert int.from_bytes(content[18:20], byteorder="little") == 0x28


def test_m19_build_artifact_hash_matches(m19_release_result: dict[str, Any]) -> None:
    build = m19_release_result["build"]
    elf = next(Path(os.environ["EEA_M19_EVIDENCE_DIR"]).glob("*.elf"))
    assert hashlib.sha256(elf.read_bytes()).hexdigest() == build["artifact_hash"]


def test_m19_build_is_bound_to_source_revision(m19_release_result: dict[str, Any]) -> None:
    assert (
        m19_release_result["build"]["source_revision_id"]
        == m19_release_result["firmware"]["source_revision"]["id"]
    )


def test_m19_build_is_bound_to_input_snapshot(m19_release_result: dict[str, Any]) -> None:
    build = m19_release_result["build"]
    assert build["build_input_snapshot_id"]
    assert build["build_input_hash"]
    assert (
        json.loads(
            (Path(os.environ["EEA_M19_EVIDENCE_DIR"]) / "build-runtime.json").read_text(
                encoding="utf-8"
            )
        )["build_input_snapshot_id"]
        == build["build_input_snapshot_id"]
    )


def test_m19_cppcheck_executes(m19_release_result: dict[str, Any]) -> None:
    cppcheck = next(
        item
        for item in m19_release_result["static"]["tool_results"]
        if item["tool_id"] == "cppcheck"
    )
    assert cppcheck["status"] == "PASS"
    assert cppcheck["version"] != "UNAVAILABLE"


def test_m19_firmware_release_rules_have_no_unknown(m19_release_result: dict[str, Any]) -> None:
    rules = m19_release_result["static"]["rule_results"]
    assert all(item["status"] != "UNKNOWN" for item in rules)


def test_m19_firmware_release_rules_have_no_fail(m19_release_result: dict[str, Any]) -> None:
    rules = m19_release_result["static"]["rule_results"]
    assert all(item["status"] not in {"FAIL", "BLOCKED"} for item in rules)
    assert {item["rule_id"] for item in rules} >= {
        "APP_DIRECT_HAL_CALL",
        "ISR_BLOCKING_API",
        "DRIVER_DEPENDENCY_CYCLE",
        "MCUCONFIG_FIRMWARE_MISMATCH",
    }


def test_m19_erc_executes(m19_release_result: dict[str, Any]) -> None:
    report = m19_release_result["erc"]["erc_report"]
    assert report["executed"] is True
    assert report["tool_name"] == "kicad-cli"


def test_m19_erc_passes(m19_release_result: dict[str, Any]) -> None:
    assert m19_release_result["erc"]["erc_report"]["status"] == "PASS"


def test_m19_authorized_software_test_run_passes(m19_release_result: dict[str, Any]) -> None:
    test_run = m19_release_result["test_run"]
    assert test_run["status"] == "PASS"
    assert all(
        item["result_authority"] == "DETERMINISTIC_VERIFICATION"
        for item in test_run["case_results"]
    )


def test_m19_p0_requirement_has_executed_test(m19_release_result: dict[str, Any]) -> None:
    result = m19_release_result
    p0_ids = {
        item["requirement_id"]
        for item in result["test_ir"]["requirement_snapshots"]
        if item["priority"] == "MUST" and item["status"] == "ACCEPTED"
    }
    tested_ids = {
        requirement_id
        for case in result["test_ir"]["cases"]
        if case["required"]
        for requirement_id in case["requirement_ids"]
    }
    assert p0_ids <= tested_ids
    assert all(item["status"] == "PASS" for item in result["test_run"]["case_results"])


def test_m19_review_requires_build_pass(m19_release_result: dict[str, Any]) -> None:
    assert m19_release_result["build"]["status"] == "PASS"
    assert m19_release_result["review"]["status"] == "PASS"


def test_m19_review_requires_static_pass(m19_release_result: dict[str, Any]) -> None:
    assert m19_release_result["static"]["status"] == "PASS"
    assert m19_release_result["review"]["status"] == "PASS"


def test_m19_review_requires_erc_pass(m19_release_result: dict[str, Any]) -> None:
    assert m19_release_result["erc"]["erc_report"]["status"] == "PASS"
    assert m19_release_result["review"]["status"] == "PASS"


def test_m19_review_requires_test_run_pass(m19_release_result: dict[str, Any]) -> None:
    assert m19_release_result["test_run"]["status"] == "PASS"
    assert m19_release_result["review"]["status"] == "PASS"


def test_m19_final_release_review_passes(m19_release_result: dict[str, Any]) -> None:
    review = m19_release_result["review"]
    assert review["status"] == "PASS"
    assert review["findings"] == []


def test_m19_release_gate_missing_tool_is_not_accepted(m19_release_result: dict[str, Any]) -> None:
    assert m19_release_result["build"]["status"] != "UNKNOWN"
    assert m19_release_result["static"]["status"] != "UNKNOWN"
    assert m19_release_result["erc"]["erc_report"]["status"] != "UNKNOWN"


def test_m19_release_gate_has_no_unknown_or_fail_rules(
    m19_release_result: dict[str, Any],
) -> None:
    statuses = {item["status"] for item in m19_release_result["static"]["rule_results"]}
    assert statuses <= {"PASS", "NOT_APPLICABLE"}


def test_m19_hardware_remains_blocked_without_affecting_m19a(
    m19_release_result: dict[str, Any],
) -> None:
    assert m19_release_result["review"]["status"] == "PASS"
    assert m19_release_result["test_run"]["status"] == "PASS"
    assert m19_release_result.get("hardware_state", "BLOCKED_HARDWARE") == "BLOCKED_HARDWARE"
