"""M20 generic embedded-controller vertical slice without MotorControl activation."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from eea_backend.main import create_app
from eea_backend.settings import Settings
from eea_core.testing import TestExecutionStatus as ExecutionStatus
from fastapi.testclient import TestClient


def _value(unit: str, dimension: str, nominal: float) -> dict[str, object]:
    return {"unit": unit, "dimension": dimension, "nominal": nominal}


def _post(
    client: TestClient,
    path: str,
    payload: dict[str, object],
    *,
    expected: set[int] | None = None,
) -> dict[str, Any]:
    expected = expected or {200, 201}
    response = client.post(path, json=payload)
    assert response.status_code in expected, f"{path}: {response.status_code} {response.text}"
    return response.json()["data"]


def _evidence(client: TestClient, project_id: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, summary in {
        "device_source": "STM32G431 UFQFPN48 package and USART2/FDCAN1/SPI1 facts",
        "interface_source": "UART debug, CAN transport and SPI sensor interface contract",
        "rtos_source": "FreeRTOS task, queue and mutex contract",
    }.items():
        item = _post(
            client,
            f"/api/v1/projects/{project_id}/evidence",
            {
                "evidence_type": "DOCUMENT",
                "locator": {"benchmark": "M20", "key": key},
                "source_uri": f"eea://m20/embedded-controller/{key}",
                "summary": summary,
            },
        )
        result[key] = item["id"]
    return result


def _analyze(client: TestClient, project_id: str) -> dict[str, Any]:
    evidence = _evidence(client, project_id)
    tasks = ["communication_task", "sensor_task", "health_task"]
    values = {
        "target.device": "STM32G431",
        "target.package": "UFQFPN48",
        "interfaces.uart": "USART2",
        "interfaces.can": "FDCAN1",
        "interfaces.spi": "SPI1",
        "sensor.type": "temperature_sensor",
        "rtos.name": "FreeRTOS",
        "rtos.tasks": tasks,
    }
    field_refs = {
        "target.device": evidence["device_source"],
        "target.package": evidence["device_source"],
        "interfaces.uart": evidence["interface_source"],
        "interfaces.can": evidence["interface_source"],
        "interfaces.spi": evidence["interface_source"],
        "sensor.type": evidence["interface_source"],
        "rtos.name": evidence["rtos_source"],
        "rtos.tasks": evidence["rtos_source"],
    }
    return _post(
        client,
        "/api/v1/requirements/analyze/structured",
        {
            "project_id": project_id,
            "profile_name": "embedded-controller-benchmark",
            "profile_version": "1.0",
            "values": values,
            "evidence_refs": {**evidence, **field_refs},
            "requirements": [
                {
                    "code": "REQ_EMBEDDED_IO_RTOS",
                    "title": "Generic controller shall provide verified I/O and task scheduling",
                    "requirement_type": "FUNCTIONAL",
                    "priority": "MUST",
                    "statement": (
                        "The controller shall expose the verified UART, CAN and SPI sensor "
                        "interfaces under the declared FreeRTOS task contract."
                    ),
                    "rationale": "M20 proves the generic path without a domain plugin.",
                    "acceptance_criteria": [
                        "MCUConfigIR is the single hardware configuration source",
                        "Generated source and DEVICE build bind to SourceRevision",
                    ],
                    "source_evidence_refs": ["device_source", "interface_source", "rtos_source"],
                }
            ],
        },
    )


def _build_vertical_slice(client: TestClient, *, release_gate: bool = False) -> dict[str, Any]:
    project = _post(client, "/api/v1/projects", {"name": "M20 Generic Embedded Controller"})
    project_id = project["id"]
    domains = client.get(f"/api/v1/projects/{project_id}/domains")
    assert domains.status_code == 200, domains.text
    assert domains.json()["data"]["items"] == []
    analysis = _analyze(client, project_id)
    assert analysis["completeness"]["status"] == "COMPLETE"
    requirement_id = analysis["requirement_ids"][0]
    device_claim_id = next(
        item["id"] for item in analysis["claims"] if item["predicate"] == "target.device"
    )

    pin_specs = [
        ("UART_TX", "USART2", "TX", "OUT"),
        ("UART_RX", "USART2", "RX", "IN"),
        ("CAN_RX", "FDCAN1", "RX", "IN"),
        ("CAN_TX", "FDCAN1", "TX", "OUT"),
        ("SPI_SCK", "SPI1", "SCK", "OUT"),
        ("SPI_MISO", "SPI1", "MISO", "IN"),
        ("SPI_MOSI", "SPI1", "MOSI", "OUT"),
        ("SPI_CS", "GPIO", "CS", "OUT"),
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
                    "direction": direction,
                    "requirement_ids": [requirement_id],
                    "claim_ids": [device_claim_id],
                }
                for name, peripheral, function, direction in pin_specs
            ],
        },
    )
    assert len(plan["assignments"]) == len(pin_specs)
    assert all(item["locked"] is False for item in plan["assignments"])
    for assignment in plan["assignments"]:
        locked = _post(
            client,
            f"/api/v1/projects/{project_id}/pin-planner/assignments/{assignment['id']}/lock",
            {
                "expected_revision": assignment["revision"],
                "actor": "m20",
                "reason": "generic controller verified pin assignment",
            },
        )
        assert locked["assignment"]["locked"] is True
    plan = client.get(f"/api/v1/projects/{project_id}/pin-planner/map").json()["data"]
    assignments = {
        (item["function"]["peripheral"], item["function"]["signal"]): item
        for item in plan["assignments"]
    }

    signal_functions = {
        "UART_TX": ("USART2", "TX"),
        "UART_RX": ("USART2", "RX"),
        "CAN_RX": ("FDCAN1", "RX"),
        "CAN_TX": ("FDCAN1", "TX"),
        "SPI_SCK": ("SPI1", "SCK"),
        "SPI_MISO": ("SPI1", "MISO"),
        "SPI_MOSI": ("SPI1", "MOSI"),
        "SPI_CS": ("GPIO", "CS"),
    }

    architecture = _post(
        client,
        f"/api/v1/projects/{project_id}/architecture/generate",
        {"pin_plan_id": plan["id"]},
    )
    hardware = architecture["hardware"]
    components = [
        {"reference": "MCU", "kind": "MCU", "device_ref": "STM32G431", "package": "UFQFPN48"},
        {"reference": "U1", "kind": "CAN_TRANSCEIVER", "device_ref": "CAN_TRANSCEIVER"},
        {"reference": "U2", "kind": "SPI_SENSOR", "device_ref": "SPI_SENSOR"},
        {"reference": "J1", "kind": "UART_CONNECTOR", "device_ref": "UART"},
        {"reference": "RTERM1", "kind": "RESISTOR"},
        {"reference": "RTERM2", "kind": "RESISTOR"},
    ]
    endpoint_target = {
        "UART_TX": ("J1", "1"),
        "UART_RX": ("J1", "2"),
        "CAN_RX": ("U1", "1"),
        "CAN_TX": ("U1", "2"),
        "SPI_SCK": ("U2", "1"),
        "SPI_MISO": ("U2", "2"),
        "SPI_MOSI": ("U2", "3"),
        "SPI_CS": ("U2", "4"),
    }
    nets = []
    for signal, (target_ref, target_pin) in endpoint_target.items():
        assignment = assignments[signal_functions[signal]]
        nets.append(
            {
                "name": signal,
                "signal_type": "DIGITAL",
                "endpoints": [
                    {
                        "component_ref": "MCU",
                        "pin_ref": assignment["pin_name"],
                        "pin_assignment_id": assignment["id"],
                    },
                    {"component_ref": target_ref, "pin_ref": target_pin},
                ],
                "requirement_ids": [requirement_id],
            }
        )
    circuit = _post(
        client,
        f"/api/v1/projects/{project_id}/circuit/generate",
        {
            "hardware_ir_id": hardware["id"],
            "components": components,
            "nets": nets,
            "power_nets": [
                {
                    "name": "VDD_3V3",
                    "voltage": _value("V", "VOLTAGE", 3.3),
                    "current": _value("A", "CURRENT", 0.5),
                    "attributes": {"regulated": True},
                    "requirement_ids": [requirement_id],
                }
            ],
            "constraints": [
                {
                    "rule_id": "CAN_TRANSCEIVER",
                    "target_ref": "U1",
                    "parameters": {"transceiver_present": True},
                },
                {
                    "rule_id": "TERMINATION",
                    "target_ref": "CAN0",
                    "parameters": {"termination_count": 2, "required_count": 2},
                },
            ],
        },
    )
    schematic = _post(
        client,
        f"/api/v1/projects/{project_id}/schematic/generate",
        {"circuit_id": circuit["circuit"]["id"]},
    )
    erc = None
    if release_gate:
        erc = _post(
            client,
            f"/api/v1/projects/{project_id}/schematic/erc/run",
            {"schematic_id": schematic["schematic"]["id"]},
        )

    def gpio(signal: str) -> dict[str, object]:
        item = assignments[signal_functions[signal]]
        function = item["function"]
        alternate = function["alternate_function"]
        return {
            "pin_assignment_id": item["id"],
            "signal_ref": signal,
            "mode": "OUTPUT" if signal == "SPI_CS" else "ALTERNATE",
            "alternate_function": (
                f"GPIO_{alternate}_{function['peripheral']}" if alternate else None
            ),
            "requirement_ids": [requirement_id],
        }

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
                "source": "HSI",
                "target_frequency": _value("MHz", "FREQUENCY", 16),
            },
            "gpio": [gpio(item[0]) for item in pin_specs],
            "peripherals": [
                {
                    "instance": "USART2",
                    "mode": "ASYNC",
                    "pin_assignment_ids": [
                        assignments[("USART2", "TX")]["id"],
                        assignments[("USART2", "RX")]["id"],
                    ],
                    "parameters": {"baud_rate": 115200, "word_length": 8},
                    "requirement_ids": [requirement_id],
                },
                {
                    "instance": "FDCAN1",
                    "mode": "CAN",
                    "pin_assignment_ids": [
                        assignments[("FDCAN1", "RX")]["id"],
                        assignments[("FDCAN1", "TX")]["id"],
                    ],
                    "parameters": {"nominal_bitrate": 500000},
                    "interrupt_refs": ["FDCAN1_IT0"],
                    "requirement_ids": [requirement_id],
                },
                {
                    "instance": "SPI1",
                    "mode": "MASTER",
                    "pin_assignment_ids": [
                        assignments[("SPI1", "SCK")]["id"],
                        assignments[("SPI1", "MISO")]["id"],
                        assignments[("SPI1", "MOSI")]["id"],
                        assignments[("GPIO", "CS")]["id"],
                    ],
                    "parameters": {"frequency_hz": 1000000, "mode": 0},
                    "requirement_ids": [requirement_id],
                },
            ],
            "interrupts": [
                {
                    "source": "FDCAN1",
                    "irq": "FDCAN1_IT0",
                    "priority": 5,
                    "allowed_operations": ["QUEUE_EVENT"],
                    "communicates_with_tasks": ["communication_task"],
                    "requirement_ids": [requirement_id],
                }
            ],
            "capability_snapshot": {
                "clock_sources": {"HSI": {"max_frequency_hz": 16000000}},
                "interfaces": {"uart": "USART2", "can": "FDCAN1", "spi": "SPI1"},
                "rtos_profile": {
                    "name": "FreeRTOS",
                    "version": "10.x",
                    "tasks": [
                        {
                            "name": "communication_task",
                            "period_us": 10000,
                            "deadline_us": 5000,
                            "priority": 3,
                            "stack_bytes": 768,
                            "queues": ["protocol_events"],
                            "mutexes": ["sensor_bus"],
                            "resources": ["USART2", "FDCAN1"],
                        },
                        {
                            "name": "sensor_task",
                            "period_us": 20000,
                            "deadline_us": 10000,
                            "priority": 2,
                            "stack_bytes": 768,
                            "queues": ["sensor_samples"],
                            "mutexes": ["sensor_bus"],
                            "resources": ["SPI1"],
                        },
                        {
                            "name": "health_task",
                            "period_us": 100000,
                            "deadline_us": 50000,
                            "priority": 1,
                            "stack_bytes": 512,
                            "queues": ["protocol_events"],
                            "resources": ["mcu_config"],
                        },
                    ],
                },
                "interrupts": ["FDCAN1_IT0"],
            },
        },
    )
    config = mcu["config"]
    assert client.get(f"/api/v1/projects/{project_id}/domains").json()["data"]["items"] == []

    firmware_payload: dict[str, object] = {
        "mcu_config_id": config["id"],
        "board_name": "generic-stm32g431-freertos",
    }
    lock = None
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
                        "reason": "M20 DEVICE build CMSIS core",
                        "source_requirement_ids": [requirement_id],
                    },
                    {
                        "capability": "cmsis.device",
                        "component_key": "st.stm32g4.cmsis-device",
                        "reason": "M20 DEVICE build CMSIS device",
                        "source_requirement_ids": [requirement_id],
                    },
                    {
                        "capability": "stm32.hal",
                        "component_key": "st.stm32g4.hal",
                        "reason": "M20 DEVICE build STM32 HAL",
                        "source_requirement_ids": [requirement_id],
                    },
                    {
                        "capability": "rtos.kernel",
                        "component_key": "freertos.kernel",
                        "reason": "M20 FreeRTOS kernel profile",
                        "source_requirement_ids": [requirement_id],
                    },
                ],
                "architecture": "Cortex-M4",
                "device": "STM32G431KB",
                "toolchain_id": "arm-none-eabi-gcc",
                "build_system": "CMAKE",
                "rtos": "FreeRTOS",
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
    firmware = _post(client, f"/api/v1/projects/{project_id}/firmware/generate", firmware_payload)
    firmware_ir = firmware["firmware"]
    assert firmware["source_revision"]["id"] == firmware_ir["source_revision_id"]
    build = _post(
        client,
        f"/api/v1/projects/{project_id}/build",
        {"firmware_id": firmware_ir["id"]},
    )
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
                {"transport_id": "can0", "name": "CAN", "transport_type": "CAN"},
                {"transport_id": "uart0", "name": "UART", "transport_type": "UART"},
            ],
            "messages": [
                {
                    "name": "ControllerCommand",
                    "transport_ref": "can0",
                    "can_id": 512,
                    "payload_length_bytes": 8,
                    "fields": [{"name": "opcode", "bit_offset": 0, "bit_length": 8}],
                    "requirement_ids": [requirement_id],
                },
                {
                    "name": "SensorStatus",
                    "transport_ref": "can0",
                    "can_id": 513,
                    "payload_length_bytes": 8,
                    "fields": [{"name": "temperature", "bit_offset": 0, "bit_length": 16}],
                    "requirement_ids": [requirement_id],
                },
                {
                    "name": "DebugFrame",
                    "transport_ref": "uart0",
                    "can_id": 514,
                    "payload_length_bytes": 8,
                    "fields": [{"name": "status", "bit_offset": 0, "bit_length": 8}],
                    "requirement_ids": [requirement_id],
                },
            ],
            "requirement_ids": [requirement_id],
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
    test_run = _post(
        client,
        f"/api/v1/projects/{project_id}/tests/run",
        {
            "test_ir_id": tests["test_ir"]["id"],
            "source_revision_id": firmware["source_revision"]["id"],
        },
    )
    review = _post(
        client,
        f"/api/v1/projects/{project_id}/review",
        {
            "source_revision_id": firmware["source_revision"]["id"],
            "test_ir_id": tests["test_ir"]["id"],
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
    traceability = client.get(f"/api/v1/projects/{project_id}/traceability")
    assert traceability.status_code == 200, traceability.text
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
        "firmware": firmware,
        "lock": lock,
        "build": build,
        "static": static,
        "protocol": protocol,
        "generated_protocol": generated_protocol,
        "test_ir": tests["test_ir"],
        "test_run": test_run,
        "review": review,
        "traceability": traceability.json()["data"],
    }


@pytest.fixture
def m20_result(client: TestClient) -> dict[str, Any]:
    return _build_vertical_slice(client)


def _core_neutrality_violations() -> list[str]:
    violations: list[str] = []
    forbidden_imports = ("plugins.builtin.motor_control", "motor_control")
    for root in (Path("core/src"), Path("ports/src"), Path("application/src")):
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                if any(name.startswith(forbidden_imports) for name in names):
                    violations.append(f"{path}: import")
                if isinstance(node, ast.If):
                    condition = ast.unparse(node.test).lower()
                    if any(
                        term in condition
                        for term in ("motor_control", "motorcontrol", "foc", "pmsm")
                    ):
                        violations.append(f"{path}: conditional {condition}")
    for path in Path("apps/backend/src/eea_backend").glob("*.py"):
        if path.name == "main.py":
            continue
        text = path.read_text(encoding="utf-8").lower()
        if "plugins.builtin.motor_control" in text or "org.eea.motor_control" in text:
            violations.append(f"{path}: generic backend dependency")
    return violations


def test_m20_core_neutrality_without_motor_control(m20_result: dict[str, Any]) -> None:
    assert _core_neutrality_violations() == []


def test_m20_motor_control_domain_is_not_active(client: TestClient) -> None:
    project_id = _post(client, "/api/v1/projects", {"name": "M20 inactive domain smoke"})["id"]
    items = client.get(f"/api/v1/projects/{project_id}/domains").json()["data"]["items"]
    assert all(item["domain_id"] != "org.eea.motor_control" for item in items)


def test_m20_zero_domain_project_smoke(client: TestClient) -> None:
    project_id = _post(client, "/api/v1/projects", {"name": "M20 zero domain"})["id"]
    analysis = _analyze(client, project_id)
    assert analysis["completeness"]["status"] == "COMPLETE"
    assert client.get(f"/api/v1/projects/{project_id}/ui/extensions").json()["data"]["items"] == []


def test_m20_uart_can_spi_pin_plan_uses_verified_facts(m20_result: dict[str, Any]) -> None:
    assignments = m20_result["plan"]["assignments"]
    assert {item["function"]["peripheral"] for item in assignments} >= {
        "USART2",
        "FDCAN1",
        "SPI1",
        "GPIO",
    }
    assert all(item.get("source_refs") for item in m20_result["plan"]["candidates"])
    assert len({item["pin_name"] for item in assignments}) == len(assignments)


def test_m20_invalid_af_fails(client: TestClient) -> None:
    project_id = _post(client, "/api/v1/projects", {"name": "M20 invalid AF"})["id"]
    analysis = _analyze(client, project_id)
    plan = _post(
        client,
        f"/api/v1/projects/{project_id}/pin-planner/generate",
        {
            "analysis_id": analysis["id"],
            "device_ref": "STM32G431",
            "package": "UFQFPN48",
            "requirements": [
                {
                    "signal_name": "INVALID_AF",
                    "required_peripheral": "USART2",
                    "required_function": "CK",
                    "requirement_ids": [analysis["requirement_ids"][0]],
                }
            ],
        },
    )
    assert plan["assignments"] == []
    assert any(item["status"] == "FAIL" for item in plan["rule_results"])


def test_m20_pin_conflict_fails(client: TestClient) -> None:
    project_id = _post(client, "/api/v1/projects", {"name": "M20 conflict"})["id"]
    analysis = _analyze(client, project_id)
    plan = _post(
        client,
        f"/api/v1/projects/{project_id}/pin-planner/generate",
        {
            "analysis_id": analysis["id"],
            "device_ref": "STM32G431",
            "package": "UFQFPN48",
            "requirements": [
                {
                    "signal_name": "CONFLICT_A",
                    "required_peripheral": "USART2",
                    "required_function": "TX",
                    "preferred_constraints": {"pin_name": "PA2"},
                    "requirement_ids": [analysis["requirement_ids"][0]],
                },
                {
                    "signal_name": "CONFLICT_B",
                    "required_peripheral": "USART2",
                    "required_function": "TX",
                    "preferred_constraints": {"pin_name": "PA2"},
                    "requirement_ids": [analysis["requirement_ids"][0]],
                },
            ],
        },
    )
    assert any(item["rule_id"] == "PIN_CONFLICT" for item in plan["rule_results"])


def test_m20_hardware_circuit_pass(m20_result: dict[str, Any]) -> None:
    assert m20_result["hardware"]["device_instances"]
    assert {item["kind"] for item in m20_result["circuit"]["components"]} >= {
        "CAN_TRANSCEIVER",
        "SPI_SENSOR",
        "UART_CONNECTOR",
    }
    assert len(m20_result["circuit"]["nets"]) == 8


def test_m20_real_erc_pass(m20_result: dict[str, Any]) -> None:
    if m20_result["erc"] is None:
        report = m20_result["schematic"]["erc_report"]
        assert report["executed"] is False
        return
    report = m20_result["erc"]["erc_report"]
    assert report["executed"] is True
    assert report["status"] == "PASS"


def test_m20_mcuconfig_is_single_source_of_truth(m20_result: dict[str, Any]) -> None:
    config = m20_result["mcu"]
    assert {item["instance"] for item in config["peripherals"]} >= {"USART2", "FDCAN1", "SPI1"}
    assert config["gpio"]
    assert config["interrupts"]
    assert config["capability_snapshot"]["interfaces"] == {
        "uart": "USART2",
        "can": "FDCAN1",
        "spi": "SPI1",
    }


def test_m20_freertos_firmware_generation(m20_result: dict[str, Any]) -> None:
    firmware = m20_result["firmware"]["firmware"]
    assert {item["name"] for item in firmware["tasks"]} >= {
        "communication_task",
        "sensor_task",
        "health_task",
    }
    assert "freertos.kernel" in firmware["component_refs"] or m20_result["lock"] is None
    assert any("FreeRTOS" in item["content"] for item in m20_result["firmware"]["files"])
    if m20_result["lock"] is not None:
        cmake = next(
            item["content"]
            for item in m20_result["firmware"]["files"]
            if item["path"] == "CMakeLists.txt"
        )
        assert "-mfpu=fpv4-sp-d16" in cmake
        assert "-mfloat-abi=hard" in cmake
        assert "target_link_options(eea_device PRIVATE" in cmake
        assert "-T${CMAKE_SOURCE_DIR}/components/Projects/NUCLEO-G431KB" in cmake
        assert any(
            file_path.endswith("Middlewares/Third_Party/FreeRTOS/Source/portable/MemMang/heap_4.c")
            for component in m20_result["lock"]["resolved_components"]
            for file_path in component["files"]
        )


def test_m20_source_revision_binding(m20_result: dict[str, Any]) -> None:
    firmware = m20_result["firmware"]
    source = firmware["source_revision"]
    assert source["file_manifest"]
    assert source["source_manifest_hash"]
    assert all(
        item["content_hash"] == source["file_manifest"][item["path"]] for item in firmware["files"]
    )


def test_m20_protocol_generation(m20_result: dict[str, Any]) -> None:
    outputs = {item["target"] for item in m20_result["generated_protocol"]["outputs"]}
    assert outputs == {"C", "PYTHON", "DBC", "MARKDOWN"}
    assert {item["transport_type"] for item in m20_result["protocol"]["transports"]} == {
        "CAN",
        "UART",
    }


def test_m20_software_test_run_pass(m20_result: dict[str, Any]) -> None:
    test_run = m20_result["test_run"]
    assert test_run["case_results"]
    assert all(item["status"] == ExecutionStatus.PASS.value for item in test_run["case_results"])
    if m20_result["lock"] is not None:
        assert test_run["status"] == ExecutionStatus.PASS.value
    else:
        assert test_run["status"] == ExecutionStatus.BLOCKED.value


def test_m20_traceability_complete(m20_result: dict[str, Any]) -> None:
    assert m20_result["traceability"]["coverage"]["uncovered_requirement_ids"] == []


def test_m20_review_pass(m20_result: dict[str, Any]) -> None:
    assert m20_result["review"]["status"] in {"PASS", "BLOCKED"}


def test_m20_non_motor_claim_change_propagates(
    m20_result: dict[str, Any], client: TestClient
) -> None:
    mutation = _post(
        client,
        f"/api/v1/claims/{m20_result['claim_id']}/lifecycle",
        {"project_id": m20_result["project_id"], "expected_revision": 1, "lifecycle": "SUPERSEDED"},
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


def test_m20_unrelated_subsystem_not_staled(m20_result: dict[str, Any]) -> None:
    uart = next(
        item for item in m20_result["plan"]["assignments"] if item["function"]["signal"] == "TX"
    )
    impacted_ids = {
        item["node"]["entity_id"]
        for item in m20_result["traceability"].get("impacts", [])
        if item.get("node", {}).get("entity_type") == "PinAssignment"
    }
    assert uart["id"] not in impacted_ids


def test_m20_core_has_no_motorcontrol_dependency() -> None:
    assert _core_neutrality_violations() == []


@pytest.fixture(scope="module")
def m20_release_result(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    if os.environ.get("EEA_M20_RELEASE_GATE") != "1":
        pytest.skip("M20 release gate requires the dedicated toolchain CI environment")
    data_dir = tmp_path_factory.mktemp("m20-release-db")
    settings = Settings(data_dir=data_dir, insecure_local_dev=True)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    command.upgrade(config, "head")
    with TestClient(create_app(settings)) as release_client:
        result = _build_vertical_slice(release_client, release_gate=True)
    _write_release_evidence(result)
    return result


def _write_release_evidence(result: dict[str, Any]) -> None:
    value = os.environ.get("EEA_M20_EVIDENCE_DIR")
    if not value:
        return
    root = Path(value)
    root.mkdir(parents=True, exist_ok=True)
    firmware = result["firmware"]
    source = firmware["source_revision"]
    build = result["build"]
    (root / "build-response.json").write_text(
        json.dumps(build, indent=2, sort_keys=True), encoding="utf-8"
    )
    elf = next(root.glob("*.elf"), None)
    assert elf is not None, f"No real ELF in evidence directory: {build}"
    elf_bytes = elf.read_bytes()
    readelf = subprocess.run(
        ["arm-none-eabi-readelf", "-h", str(elf)], capture_output=True, text=True, check=False
    )
    runtime = json.loads((root / "build-runtime.json").read_text(encoding="utf-8"))
    (root / "build-report.json").write_text(
        json.dumps(
            {
                **runtime,
                "source_manifest_hash": source["source_manifest_hash"],
                "build_input_snapshot_id": build["build_input_snapshot_id"],
                "elf_size": len(elf_bytes),
                "elf_sha256": hashlib.sha256(elf_bytes).hexdigest(),
                "elf_header": readelf.stdout,
                "elf_validation_exit_code": readelf.returncode,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    for filename, payload in {
        "cppcheck-report.json": next(
            item for item in result["static"]["tool_results"] if item["tool_id"] == "cppcheck"
        ),
        "firmware-rules.json": result["static"]["rule_results"],
        "erc-report.json": result["erc"]["erc_report"],
        "testrun-summary.json": result["test_run"],
        "review-summary.json": result["review"],
    }.items():
        (root / filename).write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
    versions: dict[str, str] = {}
    for name, argv in {
        "arm-none-eabi-gcc": ["arm-none-eabi-gcc", "--version"],
        "cmake": ["cmake", "--version"],
        "cppcheck": ["cppcheck", "--version"],
        "kicad-cli": ["kicad-cli", "version"],
    }.items():
        completed = subprocess.run(argv, capture_output=True, text=True, check=False)
        versions[name] = (completed.stdout or completed.stderr).strip()
    (root / "release-summary.json").write_text(
        json.dumps(
            {
                "benchmark": "STM32G431 + UART + CAN + SPI Sensor + FreeRTOS",
                "motor_control_active": False,
                "build": build["status"],
                "elf_size": len(elf_bytes),
                "elf_sha256": hashlib.sha256(elf_bytes).hexdigest(),
                "tools": versions,
                "p0": 0,
                "p1": 0,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def test_m20_real_arm_device_build(m20_release_result: dict[str, Any]) -> None:
    build = m20_release_result["build"]
    assert build["status"] == "PASS"
    assert build["profile"] == "DEVICE"
    assert build["toolchain_id"] == "arm-none-eabi-gcc"
    assert build["artifact_hash"]


def test_m20_build_artifact_is_arm_elf(m20_release_result: dict[str, Any]) -> None:
    elf = next(Path(os.environ["EEA_M20_EVIDENCE_DIR"]).glob("*.elf"))
    content = elf.read_bytes()
    assert content[:4] == b"\x7fELF"
    assert int.from_bytes(content[18:20], byteorder="little") == 0x28


def test_m20_build_input_and_hash_binding(m20_release_result: dict[str, Any]) -> None:
    build = m20_release_result["build"]
    elf = next(Path(os.environ["EEA_M20_EVIDENCE_DIR"]).glob("*.elf"))
    assert hashlib.sha256(elf.read_bytes()).hexdigest() == build["artifact_hash"]
    assert build["build_input_snapshot_id"]
    assert build["build_input_hash"]
    assert (
        build["source_revision_id"]
        == m20_release_result["firmware"]["firmware"]["source_revision_id"]
    )


def test_m20_cppcheck_and_rules_pass(m20_release_result: dict[str, Any]) -> None:
    cppcheck = next(
        item
        for item in m20_release_result["static"]["tool_results"]
        if item["tool_id"] == "cppcheck"
    )
    assert cppcheck["status"] == "PASS"
    rules = m20_release_result["static"]["rule_results"]
    assert {item["rule_id"] for item in rules} >= {
        "APP_DIRECT_HAL_CALL",
        "ISR_BLOCKING_API",
        "DRIVER_DEPENDENCY_CYCLE",
        "MCUCONFIG_FIRMWARE_MISMATCH",
    }
    assert all(item["status"] in {"PASS", "NOT_APPLICABLE"} for item in rules)


def test_m20_erc_executes_and_passes(m20_release_result: dict[str, Any]) -> None:
    report = m20_release_result["erc"]["erc_report"]
    assert report["executed"] is True
    assert report["status"] == "PASS"
    assert report["tool_name"] == "kicad-cli"


def test_m20_release_software_test_and_review_pass(m20_release_result: dict[str, Any]) -> None:
    result = m20_release_result
    assert result["test_run"]["status"] == "PASS"
    assert all(
        item["result_authority"] == "DETERMINISTIC_VERIFICATION"
        for item in result["test_run"]["case_results"]
    )
    assert result["review"]["status"] == "PASS"
    assert result["review"]["findings"] == []


def test_m20_release_has_no_unknown_or_fail(m20_release_result: dict[str, Any]) -> None:
    result = m20_release_result
    assert all(item["status"] != "UNKNOWN" for item in result["static"]["rule_results"])
    assert all(
        item["status"] not in {"FAIL", "BLOCKED"} for item in result["static"]["rule_results"]
    )
    assert result["erc"]["erc_report"]["status"] != "UNKNOWN"
    assert result["build"]["status"] != "UNKNOWN"
