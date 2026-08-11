"""M13 firmware static-analysis rules, tool gates, and API persistence."""

import hashlib
from pathlib import Path

from eea_adapters.static_analysis.cppcheck import CppcheckAdapter
from eea_application.firmware import FirmwareService
from eea_application.static_analysis import FirmwareStaticAnalysisService
from eea_core.enums import StaticAnalysisStatus
from eea_core.firmware import FirmwareInterrupt, FirmwareModule, FirmwareSourceFile
from eea_core.static_analysis import StaticAnalysisToolResult
from fastapi.testclient import TestClient
from test_m11_mcu_config import _create_sources_for_api
from test_m12_firmware import _config


def _source(path: str, content: str) -> FirmwareSourceFile:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return FirmwareSourceFile(
        path=path,
        content=content,
        content_hash=digest,
        input_hash=digest,
        generated_owned=False,
        generator_version="m13-test",
    )


def _bundle(*files: FirmwareSourceFile, modules: list[FirmwareModule] | None = None):
    config = _config()
    bundle = FirmwareService().generate(config)
    firmware = bundle.firmware.model_copy(update={"modules": modules or bundle.firmware.modules})
    return bundle.model_copy(update={"firmware": firmware, "files": list(files)})


def test_m13_analysis_ids_and_input_hash_are_repeatable() -> None:
    bundle = _bundle(_source("Application/Src/control.c", "int control(void) { return 0; }"))
    service = FirmwareStaticAnalysisService()
    config = _config()

    first = service.analyze(bundle, mcu_config=config, run_cppcheck=False)
    second = service.analyze(bundle, mcu_config=config, run_cppcheck=False)

    assert first.input_hash == second.input_hash
    assert first.id == second.id
    assert [item.id for item in first.rule_results] == [item.id for item in second.rule_results]
    assert all(
        item.input_snapshot["analysis_input_hash"] == first.input_hash
        for item in first.rule_results
    )


def test_m13_direct_hal_rule_has_positive_and_negative_paths() -> None:
    service = FirmwareStaticAnalysisService()
    clean = service.analyze(
        _bundle(_source("Application/Src/control.c", "int control(void) { return 0; }")),
        mcu_config=_config(),
        run_cppcheck=False,
    )
    direct = service.analyze(
        _bundle(_source("Application/Src/control.c", "void control(void) { HAL_GPIO_Init(); }")),
        mcu_config=_config(),
        run_cppcheck=False,
    )

    assert (
        next(item for item in clean.rule_results if item.rule_id == "APP_DIRECT_HAL_CALL").status
        == "PASS"
    )
    result = next(item for item in direct.rule_results if item.rule_id == "APP_DIRECT_HAL_CALL")
    assert result.status == "FAIL"
    assert result.affected_refs == ["Application/Src/control.c:1"]


def test_m13_isr_rule_detects_blocking_and_missing_handlers() -> None:
    interrupt = FirmwareInterrupt(source="TIM1", handler="TIM1_UP_IRQHandler", priority=1)
    base = _bundle(_source("Application/Src/isr.c", "void TIM1_UP_IRQHandler(void) { return; }"))
    base = base.model_copy(
        update={"firmware": base.firmware.model_copy(update={"interrupts": [interrupt]})}
    )
    blocked = base.model_copy(
        update={
            "files": [
                _source("Application/Src/isr.c", "void TIM1_UP_IRQHandler(void) { vTaskDelay(1); }")
            ]
        }
    )
    missing = base.model_copy(update={"files": []})
    service = FirmwareStaticAnalysisService()

    blocked_result = next(
        item
        for item in service.analyze(blocked, mcu_config=_config(), run_cppcheck=False).rule_results
        if item.rule_id == "ISR_BLOCKING_API"
    )
    missing_result = next(
        item
        for item in service.analyze(missing, mcu_config=_config(), run_cppcheck=False).rule_results
        if item.rule_id == "ISR_BLOCKING_API"
    )
    assert blocked_result.status == "FAIL"
    assert missing_result.status == "UNKNOWN"


def test_m13_dependency_cycle_and_boundary_cases() -> None:
    modules = [
        FirmwareModule(name="a", layer="DRIVER", responsibility="a", dependencies=["b"]),
        FirmwareModule(name="b", layer="DRIVER", responsibility="b", dependencies=["a"]),
    ]
    acyclic = [
        FirmwareModule(name="a", layer="DRIVER", responsibility="a"),
        FirmwareModule(name="b", layer="DRIVER", responsibility="b", dependencies=["a"]),
    ]
    service = FirmwareStaticAnalysisService()
    cycle = service.analyze(
        _bundle(
            _source("Application/Src/control.c", "int control(void) { return 0; }"), modules=modules
        ),
        mcu_config=_config(),
        run_cppcheck=False,
    )
    no_cycle = service.analyze(
        _bundle(
            _source("Application/Src/control.c", "int control(void) { return 0; }"), modules=acyclic
        ),
        mcu_config=_config(),
        run_cppcheck=False,
    )
    cycle_result = next(
        item for item in cycle.rule_results if item.rule_id == "DRIVER_DEPENDENCY_CYCLE"
    )
    pass_result = next(
        item for item in no_cycle.rule_results if item.rule_id == "DRIVER_DEPENDENCY_CYCLE"
    )
    assert cycle_result.status == "FAIL"
    assert pass_result.status == "PASS"


def test_m13_mcu_mismatch_and_cppcheck_unknown_are_not_promoted() -> None:
    bundle = _bundle(_source("Application/Src/control.c", "int control(void) { return 0; }"))
    mismatch = _config().model_copy(update={"revision": 2})

    class UnknownProvider:
        provider_id = "fake-cppcheck"

        def analyze(
            self, _files: tuple[tuple[str, str], ...], _workspace: Path
        ) -> StaticAnalysisToolResult:
            return StaticAnalysisToolResult(
                tool_id="fake-cppcheck",
                version="test",
                status=StaticAnalysisStatus.UNKNOWN,
                diagnostics=["fixture missing"],
            )

    result = FirmwareStaticAnalysisService(UnknownProvider()).analyze(
        bundle, mcu_config=mismatch, run_cppcheck=True
    )
    mcu_result = next(
        item for item in result.rule_results if item.rule_id == "MCUCONFIG_FIRMWARE_MISMATCH"
    )
    assert mcu_result.status == "FAIL"
    assert result.status is StaticAnalysisStatus.FAIL


def test_m13_cppcheck_missing_executable_is_unknown(monkeypatch) -> None:
    monkeypatch.setattr("eea_adapters.static_analysis.cppcheck.shutil.which", lambda _: None)
    result = CppcheckAdapter().analyze((("main.c", "int main(void) { return 0; }"),), Path("."))
    assert result.status is StaticAnalysisStatus.UNKNOWN
    assert result.version == "UNAVAILABLE"


def test_m13_static_analysis_api_persists_normalized_results(client: TestClient) -> None:
    project_id, hardware, circuit, schematic = _create_sources_for_api(client)
    mcu_response = client.post(
        f"/api/v1/projects/{project_id}/mcu-config/generate",
        json={
            "hardware_ir_id": hardware["id"],
            "circuit_id": circuit["id"],
            "schematic_id": schematic["id"],
            "device_instance_id": hardware["device_instances"][0]["id"],
            "clock": {
                "source": "HSE",
                "target_frequency": {
                    "unit": "MHz",
                    "dimension": "FREQUENCY",
                    "nominal": 170,
                },
            },
        },
    )
    assert mcu_response.status_code == 201, mcu_response.text
    mcu_id = mcu_response.json()["data"]["config"]["id"]
    firmware_response = client.post(
        f"/api/v1/projects/{project_id}/firmware/generate",
        json={"mcu_config_id": mcu_id},
    )
    assert firmware_response.status_code == 201, firmware_response.text
    firmware_id = firmware_response.json()["data"]["firmware"]["id"]

    response = client.post(
        f"/api/v1/projects/{project_id}/analysis/static",
        json={"firmware_id": firmware_id, "run_cppcheck": False},
    )
    assert response.status_code == 201, response.text
    analysis = response.json()["data"]
    assert analysis["status"] == "PASS"
    assert {result["rule_id"] for result in analysis["rule_results"]} == {
        "APP_DIRECT_HAL_CALL",
        "DRIVER_DEPENDENCY_CYCLE",
        "ISR_BLOCKING_API",
        "MCUCONFIG_FIRMWARE_MISMATCH",
    }
    fetched = client.get(f"/api/v1/projects/{project_id}/analysis/static/{analysis['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["data"]["input_hash"] == analysis["input_hash"]
