"""M12 FirmwareIR, source snapshot, deterministic generation, and build gates."""

from pathlib import Path
from uuid import UUID

import pytest
from eea_application.firmware import FirmwareBuildService, FirmwareService
from eea_core.build import BuildRun
from eea_core.claims import EngineeringValue
from eea_core.enums import BuildProfile, BuildStatus, EngineeringDimension, IssueSeverity
from eea_core.errors import EngineeringError
from eea_core.firmware import FirmwareBuildTarget
from eea_core.mcu_config import ClockIR, MCUConfigIR
from eea_core.sandbox import CommandResult, CommandSpec

PROJECT_ID = UUID(int=120)
HARDWARE_ID = UUID(int=1201)
CIRCUIT_ID = UUID(int=1202)
SCHEMATIC_ID = UUID(int=1203)


def _config(*, unknown: bool = False) -> MCUConfigIR:
    from eea_core.pin_planner import RuleResult

    rules = (
        [
            RuleResult(
                project_id=PROJECT_ID,
                rule_id="CLOCK_SOURCE_INVALID",
                rule_version="1.0",
                stage="PRE_GENERATION",
                status="UNKNOWN",
                severity=IssueSeverity.HIGH,
            )
        ]
        if unknown
        else []
    )
    return MCUConfigIR(
        project_id=PROJECT_ID,
        hardware_ir_id=HARDWARE_ID,
        hardware_ir_revision=1,
        circuit_id=CIRCUIT_ID,
        circuit_revision=1,
        schematic_id=SCHEMATIC_ID,
        schematic_revision=1,
        device_instance_id=UUID(int=1204),
        clock=ClockIR(
            source="HSE",
            target_frequency=EngineeringValue(
                unit="MHz", dimension=EngineeringDimension.FREQUENCY, nominal=170
            ),
        ),
        rule_results=rules,
    )


def test_firmware_generation_is_deterministic_and_source_bound() -> None:
    service = FirmwareService()
    config = _config()
    first = service.generate(config)
    second = service.generate(config)

    assert first.firmware.hardware_ir_id == HARDWARE_ID
    assert first.firmware.input_hash == second.firmware.input_hash
    assert first.source_revision.dirty is True
    assert first.source_revision.commit_sha is None
    assert first.source_revision.tree_hash == second.source_revision.tree_hash
    assert [(item.path, item.content, item.content_hash) for item in first.files] == [
        (item.path, item.content, item.content_hash) for item in second.files
    ]
    assert "PA" not in "\n".join(item.content for item in first.files)
    assert "EEA_MCU_CONFIG_ID" in next(
        item.content for item in first.files if item.path.endswith(".h")
    )


def test_firmware_generation_blocks_failed_mcu_rules_and_build_blocks_unknown() -> None:
    from eea_core.pin_planner import RuleResult

    failed = _config().model_copy(
        update={
            "rule_results": [
                RuleResult(
                    project_id=PROJECT_ID,
                    rule_id="PINMAP_SOURCE_MISMATCH",
                    rule_version="1.0",
                    stage="PRE_GENERATION",
                    status="FAIL",
                    severity=IssueSeverity.HIGH,
                )
            ]
        }
    )
    with pytest.raises(EngineeringError) as error:
        FirmwareService().generate(failed)
    assert error.value.details["reason"] == "MCU_CONFIG_RULE_GATE"

    class UnexpectedExecutor:
        def execute(self, *_: object, **__: object) -> CommandResult:
            raise AssertionError("UNKNOWN MCU rules must block before tool execution")

    bundle = FirmwareService().generate(_config(unknown=True))
    snapshot, build = FirmwareBuildService(UnexpectedExecutor()).build(  # type: ignore[arg-type]
        bundle, Path(".eea-test-build")
    )
    assert build.status is BuildStatus.BLOCKED
    assert build.build_input_snapshot_id == snapshot.id
    assert build.source_revision_id == bundle.source_revision.id
    assert build.diagnostics[0].code == "MCU_CONFIG_UNKNOWN"


def test_build_snapshot_hashes_generated_inputs_and_reports_artifact_unknown(
    tmp_path: Path,
) -> None:
    class FakeExecutor:
        def execute(self, spec: CommandSpec, _workspace: Path, _policy: object) -> CommandResult:
            argv = spec.argv
            if argv[-1] == "--version":
                return CommandResult(
                    argv=tuple(argv),
                    returncode=0,
                    stdout="cmake version test",
                    stderr="",
                    duration_ms=1,
                )
            return CommandResult(
                argv=tuple(argv), returncode=0, stdout="built", stderr="", duration_ms=1
            )

    bundle = FirmwareService().generate(
        _config(), build_target=FirmwareBuildTarget(toolchain_id="fake-cmake")
    )
    snapshot, build = FirmwareBuildService(FakeExecutor()).build(  # type: ignore[arg-type]
        bundle, tmp_path
    )

    assert isinstance(build, BuildRun)
    assert build.status is BuildStatus.UNKNOWN
    assert snapshot.generated_input_hash != snapshot.tracked_file_manifest_hash
    assert snapshot.build_input_hash == build.build_input_hash
    assert build.build_input_snapshot_id == snapshot.id


def test_m12r_generation_hash_covers_target_and_board() -> None:
    service = FirmwareService()
    base = service.generate(_config(), board_name="board-a")
    changed_target = service.generate(
        _config(),
        board_name="board-a",
        build_target=FirmwareBuildTarget(toolchain_id="alternate-cmake"),
    )
    changed_board = service.generate(_config(), board_name="board-b")
    assert base.firmware.input_hash != changed_target.firmware.input_hash
    assert base.firmware.input_hash != changed_board.firmware.input_hash


def test_m12r_rejects_cmake_injection_and_platformio_native_fallback() -> None:
    with pytest.raises(ValueError):
        FirmwareBuildTarget(output_name="x)\nexecute_process(COMMAND whoami)")
    with pytest.raises(ValueError):
        FirmwareBuildTarget(compiler_flags=["-O2\nexecute_process(COMMAND whoami)"])
    with pytest.raises(EngineeringError) as error:
        FirmwareService().generate(
            _config(),
            build_target=FirmwareBuildTarget(build_system="PLATFORMIO"),
        )
    assert error.value.code.value == "CAPABILITY_UNAVAILABLE"


def test_m12r_buildrun_timestamps_are_monotonic_for_all_terminal_states() -> None:
    bundle = FirmwareService().generate(_config())

    class FakeExecutor:
        def execute(self, spec: CommandSpec, _workspace: Path, _policy: object) -> CommandResult:
            return CommandResult(
                argv=tuple(spec.argv),
                returncode=0,
                stdout="cmake version test",
                stderr="",
                duration_ms=1,
            )

    snapshot, build = FirmwareBuildService(FakeExecutor()).build(bundle, Path(".eea-test-build"))  # type: ignore[arg-type]
    for status in (
        BuildStatus.BLOCKED,
        BuildStatus.UNKNOWN,
        BuildStatus.FAIL,
        BuildStatus.PASS,
    ) * 25:
        candidate = FirmwareBuildService._run(
            bundle,
            snapshot,
            status,
            "cmake-host",
            "test",
            snapshot.environment_profile_hash,
            build.diagnostics,
        )
        assert candidate.updated_at >= candidate.created_at
        assert candidate.profile is BuildProfile.HOST_SMOKE
