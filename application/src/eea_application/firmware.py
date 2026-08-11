"""M12 FirmwareIR generation, source snapshots, and sandboxed build execution."""

from __future__ import annotations

import hashlib
import json
import platform
import tempfile
from collections.abc import Iterable, Sequence
from pathlib import Path
from uuid import UUID

from eea_adapters.sandbox import StructuredCommandExecutor
from eea_core.build import BuildDiagnostic, BuildRun
from eea_core.entities import utc_now
from eea_core.enums import BuildStatus, EngineeringErrorCode, IssueSeverity
from eea_core.errors import EngineeringError
from eea_core.firmware import (
    BSPConfig,
    FirmwareBuildTarget,
    FirmwareBundle,
    FirmwareInterrupt,
    FirmwareIR,
    FirmwareModule,
    FirmwareSourceFile,
    FirmwareTask,
    MemoryLayout,
    PeripheralDriverConfig,
    SharedResource,
    StartupConfig,
)
from eea_core.mcu_config import MCUConfigIR
from eea_core.sandbox import CommandSpec, SandboxPolicy, SandboxWorkspace
from eea_core.source import BuildInputSnapshot, SourceRevision


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash_json(value: object) -> str:
    return _sha256_bytes(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def _empty_hash() -> str:
    return _hash_json({})


def _unique(values: Iterable[UUID]) -> list[UUID]:
    result: list[UUID] = []
    seen: set[UUID] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _identifier(value: str) -> str:
    normalized = "".join(character if character.isalnum() else "_" for character in value)
    return normalized.strip("_").lower() or "peripheral"


class FirmwareService:
    """Derive deterministic firmware structure and source candidates from MCUConfigIR."""

    generator_version = "m12.1"

    def generate(
        self,
        config: MCUConfigIR,
        *,
        build_target: FirmwareBuildTarget | None = None,
        board_name: str = "generic-stm32",
    ) -> FirmwareBundle:
        failed_rules = [result.rule_id for result in config.rule_results if result.status == "FAIL"]
        if failed_rules:
            raise EngineeringError(
                EngineeringErrorCode.INVALID_REQUIREMENT,
                "Firmware generation is blocked by MCUConfigIR rule failures",
                details={"reason": "MCU_CONFIG_RULE_GATE", "rule_ids": failed_rules},
            )
        target = build_target or FirmwareBuildTarget()
        input_hash = _hash_json(
            config.model_dump(
                mode="json",
                exclude={"id", "created_at", "updated_at", "metadata", "status"},
            )
        )
        target = target.model_copy(update={"name": target.name.strip()})
        source_files = self._source_files(config, target, input_hash)
        source_revision = self._source_revision(config, source_files)
        drivers = self._drivers(config)
        interrupts = self._interrupts(config)
        modules = self._modules(config, drivers, interrupts)
        requirements = _unique(
            [
                *config.requirement_ids,
                *[value for item in config.gpio for value in item.requirement_ids],
                *[
                    value
                    for peripheral in config.peripherals
                    for value in peripheral.requirement_ids
                ],
                *[value for item in config.dma for value in item.requirement_ids],
                *[value for item in config.interrupts for value in item.requirement_ids],
            ]
        )
        evidence = _unique(
            [
                *config.evidence_ids,
                *[value for item in config.gpio for value in item.evidence_ids],
                *[value for peripheral in config.peripherals for value in peripheral.evidence_ids],
                *[value for item in config.dma for value in item.evidence_ids],
                *[value for item in config.interrupts for value in item.evidence_ids],
            ]
        )
        firmware = FirmwareIR(
            project_id=config.project_id,
            mcu_config_id=config.id,
            mcu_config_revision=config.revision,
            hardware_ir_id=config.hardware_ir_id,
            hardware_ir_revision=config.hardware_ir_revision,
            circuit_id=config.circuit_id,
            circuit_revision=config.circuit_revision,
            schematic_id=config.schematic_id,
            schematic_revision=config.schematic_revision,
            source_revision_id=source_revision.id,
            layers=["STARTUP", "BSP", "HAL", "APPLICATION"],
            modules=modules,
            tasks=[FirmwareTask(name="main", priority=0, resources=["mcu_config"])],
            interrupts=interrupts,
            shared_resources=self._shared_resources(config),
            startup=StartupConfig(),
            clock_tree=config.clock.model_dump(mode="json"),
            peripheral_drivers=drivers,
            memory_layout=MemoryLayout(
                linker_script=config.memory.linker_script_ref if config.memory else None
            ),
            bsp=BSPConfig(board_name=board_name),
            build_target=target,
            rule_results=list(config.rule_results),
            requirement_ids=requirements,
            evidence_ids=evidence,
            input_hash=input_hash,
        )
        return FirmwareBundle(
            firmware=firmware, source_revision=source_revision, files=source_files
        )

    @staticmethod
    def _source_revision(
        config: MCUConfigIR, files: Sequence[FirmwareSourceFile]
    ) -> SourceRevision:
        manifest = {
            item.path: item.content_hash for item in sorted(files, key=lambda value: value.path)
        }
        manifest_hash = _hash_json(manifest)
        return SourceRevision(
            project_id=config.project_id,
            repository_id=f"generated-firmware:{config.project_id}",
            commit_sha=None,
            tree_hash=manifest_hash,
            dirty=True,
            base_commit=None,
            workspace_revision=0,
            source_manifest_hash=manifest_hash,
            file_manifest=manifest,
            created_by="eea:m12",
        )

    def _source_files(
        self, config: MCUConfigIR, target: FirmwareBuildTarget, input_hash: str
    ) -> list[FirmwareSourceFile]:
        identifier = str(config.id)
        header = "\n".join(
            [
                "/* Generated by EEA M12; do not edit as source-of-truth. */",
                "#pragma once",
                "",
                f'#define EEA_MCU_CONFIG_ID "{identifier}"',
                f"#define EEA_MCU_CONFIG_REVISION {config.revision}",
                f'#define EEA_HARDWARE_IR_ID "{config.hardware_ir_id}"',
                f'#define EEA_CIRCUIT_IR_ID "{config.circuit_id}"',
                f'#define EEA_SCHEMATIC_IR_ID "{config.schematic_id}"',
                f'#define EEA_CLOCK_SOURCE "{config.clock.source}"',
                "",
                "void eea_firmware_init(void);",
                "",
            ]
        )
        source = "\n".join(
            [
                "/* Generated by EEA M12; do not edit as source-of-truth. */",
                '#include "eea_firmware_config.h"',
                "",
                "void eea_firmware_init(void) {",
                "    /* Realized peripheral setup is supplied by the selected HAL adapter. */",
                "}",
                "",
            ]
        )
        main = "\n".join(
            [
                "/* Generated by EEA M12; do not edit as source-of-truth. */",
                '#include "eea_firmware_config.h"',
                "",
                "int main(void) {",
                "    eea_firmware_init();",
                "    for (;;) {",
                "    }",
                "}",
                "",
            ]
        )
        compile_options = (
            f"target_compile_options({target.output_name} PRIVATE "
            f"{' '.join(target.compiler_flags)})"
            if target.compiler_flags
            else None
        )
        link_options = (
            f"target_link_options({target.output_name} PRIVATE {' '.join(target.linker_flags)})"
            if target.linker_flags
            else None
        )
        cmake = "\n".join(
            [
                "# Generated by EEA M12; candidate build adapter.",
                "cmake_minimum_required(VERSION 3.20)",
                f"project({target.output_name} C)",
                "set(CMAKE_C_STANDARD 11)",
                f"add_executable({target.output_name}",
                "    Core/Src/main.c",
                "    Core/Src/eea_firmware_config.c",
                ")",
                f"target_include_directories({target.output_name} PRIVATE Core/Inc)",
                *([compile_options] if compile_options else []),
                *([link_options] if link_options else []),
                "",
            ]
        )
        files: list[tuple[str, str]] = [
            ("Core/Inc/eea_firmware_config.h", header),
            ("Core/Src/eea_firmware_config.c", source),
            ("Core/Src/main.c", main),
            ("CMakeLists.txt", cmake),
            (
                "README.md",
                "\n".join(
                    [
                        "# EEA Generated Firmware Candidate",
                        "",
                        f"- MCUConfigIR: `{identifier}` revision `{config.revision}`",
                        f"- Input hash: `{input_hash}`",
                        f"- Build system: `{target.build_system}`",
                        "",
                    ]
                ),
            ),
        ]
        if target.build_system.upper() == "PLATFORMIO":
            files.append(
                (
                    "platformio.ini",
                    "\n".join(
                        [
                            "; Generated by EEA M12; candidate build adapter.",
                            "\n".join(
                                [
                                    "[env:eea]",
                                    "platform = native",
                                    "build_type = debug",
                                    "build_src_filter = +<Core/Src>",
                                    "build_flags = -ICore/Inc",
                                ]
                            ),
                            "",
                        ]
                    ),
                )
            )
        return [
            FirmwareSourceFile(
                path=path,
                content=content,
                content_hash=_sha256_bytes(content.encode("utf-8")),
                input_hash=input_hash,
                generated_owned=True,
                generator_version=self.generator_version,
            )
            for path, content in sorted(files)
        ]

    @staticmethod
    def _drivers(config: MCUConfigIR) -> list[PeripheralDriverConfig]:
        return [
            PeripheralDriverConfig(
                peripheral=peripheral.instance,
                driver_name=f"eea_{_identifier(peripheral.instance)}_driver",
                init_function=f"eea_{_identifier(peripheral.instance)}_init",
                config_refs=[f"mcu_config:{config.id}"],
                dependencies=sorted({f"dma:{value}" for value in peripheral.dma_refs}),
            )
            for peripheral in sorted(config.peripherals, key=lambda value: value.instance)
        ]

    @staticmethod
    def _interrupts(config: MCUConfigIR) -> list[FirmwareInterrupt]:
        return [
            FirmwareInterrupt(
                source=interrupt.source,
                handler=f"eea_{_identifier(interrupt.source)}_irq_handler",
                priority=interrupt.priority,
                allowed_operations=list(interrupt.allowed_operations),
                communicates_with_tasks=list(interrupt.communicates_with_tasks),
            )
            for interrupt in sorted(
                config.interrupts, key=lambda value: (value.priority, value.irq)
            )
        ]

    @staticmethod
    def _modules(
        config: MCUConfigIR,
        drivers: Sequence[PeripheralDriverConfig],
        interrupts: Sequence[FirmwareInterrupt],
    ) -> list[FirmwareModule]:
        modules = [
            FirmwareModule(
                name="startup",
                layer="STARTUP",
                responsibility="Reset and system initialization entry points.",
                public_api=["Reset_Handler", "SystemInit"],
                testability=["host-smoke"],
                requirement_ids=list(config.requirement_ids),
                evidence_ids=list(config.evidence_ids),
            ),
            FirmwareModule(
                name="bsp",
                layer="BSP",
                responsibility="Board support and MCU configuration boundary.",
                public_api=["eea_firmware_init"],
                dependencies=[driver.driver_name for driver in drivers],
                testability=["host-smoke", "hal-adapter"],
                requirement_ids=list(config.requirement_ids),
                evidence_ids=list(config.evidence_ids),
            ),
        ]
        modules.extend(
            FirmwareModule(
                name=driver.driver_name,
                layer="HAL",
                responsibility=f"Initialize {driver.peripheral} from MCUConfigIR.",
                public_api=[driver.init_function],
                dependencies=list(driver.dependencies),
                testability=["host-smoke", "hal-adapter"],
                requirement_ids=list(config.requirement_ids),
                evidence_ids=list(config.evidence_ids),
            )
            for driver in drivers
        )
        if interrupts:
            modules.append(
                FirmwareModule(
                    name="interrupts",
                    layer="HAL",
                    responsibility=(
                        "Dispatch configured interrupt sources without changing priorities."
                    ),
                    public_api=sorted(item.handler for item in interrupts),
                    testability=["interrupt-vector-review"],
                    requirement_ids=list(config.requirement_ids),
                    evidence_ids=list(config.evidence_ids),
                )
            )
        return modules

    @staticmethod
    def _shared_resources(config: MCUConfigIR) -> list[SharedResource]:
        return [
            SharedResource(
                name=f"dma:{item.id}",
                kind="DMA",
                users=[item.request],
                protection="configuration-immutable",
            )
            for item in sorted(config.dma, key=lambda value: str(value.id))
        ]


class FirmwareBuildService:
    """Materialize only generated candidates inside a sandbox and run an allowlisted build."""

    def __init__(self, executor: StructuredCommandExecutor | None = None) -> None:
        self._executor = executor or StructuredCommandExecutor()

    def build(
        self,
        bundle: FirmwareBundle,
        workspace_root: Path,
        *,
        environment_profile: dict[str, str] | None = None,
    ) -> tuple[BuildInputSnapshot, BuildRun]:
        workspace_root.mkdir(parents=True, exist_ok=True)
        unknown_rules = [
            result.rule_id for result in bundle.firmware.rule_results if result.status == "UNKNOWN"
        ]
        environment = environment_profile or {
            "os": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        }
        toolchain_id = bundle.firmware.build_target.toolchain_id
        executable = self._executable(bundle.firmware.build_target)
        toolchain_version = "UNKNOWN"
        build_config_hash = _hash_json(bundle.firmware.build_target.model_dump(mode="json"))
        environment_hash = _hash_json(environment)
        snapshot = self._snapshot(
            bundle,
            build_config_hash=build_config_hash,
            toolchain_id=toolchain_id,
            toolchain_version=toolchain_version,
            environment_hash=environment_hash,
        )
        if unknown_rules:
            diagnostic = self._diagnostic(
                bundle.firmware.project_id,
                "MCU_CONFIG_UNKNOWN",
                "Build is blocked because MCUConfigIR contains UNKNOWN rule results.",
                "TOOLCHAIN",
            )
            return snapshot, self._run(
                bundle,
                snapshot,
                BuildStatus.BLOCKED,
                toolchain_id,
                toolchain_version,
                environment_hash,
                [diagnostic],
            )

        with tempfile.TemporaryDirectory(dir=workspace_root) as temporary:
            workspace = SandboxWorkspace.from_root(Path(temporary))
            self._materialize(bundle.files, workspace)
            policy = SandboxPolicy(allowed_executables=(executable,))
            try:
                version = self._executor.execute(
                    self._command_spec((executable, "--version"), workspace.root),
                    workspace.root,
                    policy,
                )
                toolchain_version = version.stdout.splitlines()[0].strip() or "UNKNOWN"
                snapshot = self._snapshot(
                    bundle,
                    build_config_hash=build_config_hash,
                    toolchain_id=toolchain_id,
                    toolchain_version=toolchain_version,
                    environment_hash=environment_hash,
                )
                configure, command = self._commands(bundle.firmware.build_target)
                configure_result = self._executor.execute(
                    self._command_spec(configure, workspace.root), workspace.root, policy
                )
                if configure_result.returncode != 0:
                    return snapshot, self._run(
                        bundle,
                        snapshot,
                        BuildStatus.FAIL,
                        toolchain_id,
                        toolchain_version,
                        environment_hash,
                        [
                            self._diagnostic(
                                bundle.firmware.project_id,
                                "BUILD_CONFIGURE_FAILED",
                                configure_result.stderr
                                or configure_result.stdout
                                or "Configure failed.",
                                "CONFIGURE",
                            )
                        ],
                        stdout=configure_result.stdout,
                        stderr=configure_result.stderr,
                        command=list(configure),
                    )
                result = self._executor.execute(
                    self._command_spec(command, workspace.root), workspace.root, policy
                )
                status = BuildStatus.PASS if result.returncode == 0 else BuildStatus.FAIL
                diagnostics = (
                    []
                    if status is BuildStatus.PASS
                    else [
                        self._diagnostic(
                            bundle.firmware.project_id,
                            "BUILD_FAILED",
                            result.stderr or result.stdout or "Build failed.",
                            "COMPILE",
                        )
                    ]
                )
                artifact_hash = self._artifact_hash(workspace, bundle.firmware.build_target)
                if status is BuildStatus.PASS and artifact_hash is None:
                    diagnostics.append(
                        self._diagnostic(
                            bundle.firmware.project_id,
                            "BUILD_ARTIFACT_MISSING",
                            "Build passed but the expected output artifact was not found.",
                            "ARTIFACT",
                        )
                    )
                    status = BuildStatus.UNKNOWN
                return snapshot, self._run(
                    bundle,
                    snapshot,
                    status,
                    toolchain_id,
                    toolchain_version,
                    environment_hash,
                    diagnostics,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    command=list(command),
                    artifact_hash=artifact_hash,
                )
            except EngineeringError as error:
                if error.code not in {
                    EngineeringErrorCode.TOOL_UNAVAILABLE,
                    EngineeringErrorCode.COMMAND_NOT_ALLOWED,
                }:
                    raise
                diagnostic = self._diagnostic(
                    bundle.firmware.project_id,
                    "TOOL_UNAVAILABLE",
                    error.message,
                    "TOOLCHAIN",
                )
                return snapshot, self._run(
                    bundle,
                    snapshot,
                    BuildStatus.UNKNOWN,
                    toolchain_id,
                    toolchain_version,
                    environment_hash,
                    [diagnostic],
                )

    @staticmethod
    def _snapshot(
        bundle: FirmwareBundle,
        *,
        build_config_hash: str,
        toolchain_id: str,
        toolchain_version: str,
        environment_hash: str,
    ) -> BuildInputSnapshot:
        generated_manifest = {
            item.path: item.content_hash
            for item in sorted(bundle.files, key=lambda value: value.path)
        }
        generated_hash = _hash_json(generated_manifest)
        tracked_hash = _empty_hash()
        allowed_hash = _empty_hash()
        build_input_hash = _hash_json(
            {
                "tracked_file_manifest_hash": tracked_hash,
                "allowed_untracked_input_hash": allowed_hash,
                "generated_input_hash": generated_hash,
                "submodule_commit_map": {},
                "build_config_hash": build_config_hash,
                "toolchain_id": toolchain_id,
                "toolchain_version": toolchain_version,
                "environment_profile_hash": environment_hash,
                "source_manifest_hash": bundle.source_revision.source_manifest_hash,
            }
        )
        return BuildInputSnapshot(
            project_id=bundle.firmware.project_id,
            source_revision_id=bundle.source_revision.id,
            tracked_file_manifest_hash=tracked_hash,
            allowed_untracked_input_hash=allowed_hash,
            generated_input_hash=generated_hash,
            build_config_hash=build_config_hash,
            toolchain_id=toolchain_id,
            toolchain_version=toolchain_version,
            environment_profile_hash=environment_hash,
            source_manifest_hash=bundle.source_revision.source_manifest_hash,
            build_input_hash=build_input_hash,
        )

    @staticmethod
    def _materialize(files: Sequence[FirmwareSourceFile], workspace: SandboxWorkspace) -> None:
        for item in files:
            target = workspace.path(item.path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8", newline="") as stream:
                stream.write(item.content)

    @staticmethod
    def _executable(target: FirmwareBuildTarget) -> str:
        if target.build_system.upper() == "PLATFORMIO":
            return "pio"
        return "cmake"

    @staticmethod
    def _command_spec(argv: Sequence[str], workspace: Path) -> CommandSpec:
        """Keep compiler temporary files inside the isolated build workspace."""
        return CommandSpec(
            argv=tuple(argv),
            environment={"TEMP": str(workspace), "TMP": str(workspace)},
        )

    @staticmethod
    def _commands(target: FirmwareBuildTarget) -> tuple[tuple[str, ...], tuple[str, ...]]:
        if target.build_system.upper() == "PLATFORMIO":
            return ("pio", "run"), ("pio", "run")
        return (
            "cmake",
            "-S",
            ".",
            "-B",
            "build",
        ), (
            "cmake",
            "--build",
            "build",
        )

    @staticmethod
    def _artifact_hash(workspace: SandboxWorkspace, target: FirmwareBuildTarget) -> str | None:
        candidates = [workspace.path(f"build/{target.output_name}")]
        if platform.system() == "Windows":
            candidates.append(workspace.path(f"build/{target.output_name}.exe"))
        for candidate in candidates:
            if candidate.is_file():
                return _sha256_bytes(candidate.read_bytes())
        return None

    @staticmethod
    def _diagnostic(project_id: UUID, code: str, message: str, phase: str) -> BuildDiagnostic:
        return BuildDiagnostic(
            project_id=project_id,
            severity=IssueSeverity.HIGH if phase != "TOOLCHAIN" else IssueSeverity.MEDIUM,
            code=code,
            message=message[:4000],
            phase=phase,  # type: ignore[arg-type]
        )

    @staticmethod
    def _run(
        bundle: FirmwareBundle,
        snapshot: BuildInputSnapshot,
        status: BuildStatus,
        toolchain_id: str,
        toolchain_version: str,
        environment_hash: str,
        diagnostics: list[BuildDiagnostic],
        *,
        stdout: str = "",
        stderr: str = "",
        command: list[str] | None = None,
        artifact_hash: str | None = None,
    ) -> BuildRun:
        return BuildRun(
            project_id=bundle.firmware.project_id,
            firmware_id=bundle.firmware.id,
            firmware_revision=bundle.firmware.revision,
            source_revision_id=bundle.source_revision.id,
            build_input_snapshot_id=snapshot.id,
            status=status,
            toolchain_id=toolchain_id,
            toolchain_version=toolchain_version,
            environment_profile_hash=environment_hash,
            build_input_hash=snapshot.build_input_hash,
            command=command or [],
            diagnostics=diagnostics,
            stdout=stdout,
            stderr=stderr,
            artifact_hash=artifact_hash,
            error_code=(EngineeringErrorCode.BUILD_FAILED if status is BuildStatus.FAIL else None),
            duration_ms=0,
            updated_at=utc_now(),
        )


__all__ = ["FirmwareBuildService", "FirmwareService"]
