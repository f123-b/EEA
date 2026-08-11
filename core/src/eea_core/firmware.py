"""Core-neutral FirmwareIR and generated-source contracts."""

import re
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from eea_core.components import DependencyLock
from eea_core.entities import EntityBase, Sha256
from eea_core.enums import ArtifactStatus, BuildProfile
from eea_core.pin_planner import RuleResult
from eea_core.source import SourceRevision


class FirmwareModule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    layer: str = Field(min_length=1, max_length=80)
    responsibility: str = Field(min_length=1, max_length=2000)
    public_api: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    timing: dict[str, object] = Field(default_factory=dict)
    state: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    testability: list[str] = Field(default_factory=list)
    requirement_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class FirmwareTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=100)
    period_us: int | None = Field(default=None, ge=1)
    deadline_us: int | None = Field(default=None, ge=1)
    priority: int | None = Field(default=None, ge=0)
    stack_bytes: int | None = Field(default=None, ge=1)
    execution_budget_us: int | None = Field(default=None, ge=1)
    queues: list[str] = Field(default_factory=list)
    mutexes: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)


class FirmwareInterrupt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    source: str = Field(min_length=1, max_length=100)
    handler: str = Field(min_length=1, max_length=200)
    priority: int = Field(ge=0)
    allowed_operations: list[str] = Field(default_factory=list)
    communicates_with_tasks: list[str] = Field(default_factory=list)


class SharedResource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    kind: str = Field(min_length=1, max_length=50)
    users: list[str] = Field(default_factory=list)
    protection: str | None = Field(default=None, max_length=100)


class FirmwareBuildTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="host_skeleton", min_length=1, max_length=100)
    family: str = Field(default="STM32", min_length=1, max_length=100)
    architecture: str = Field(default="Cortex-M4", min_length=1, max_length=100)
    build_system: str = Field(default="CMAKE", min_length=1, max_length=50)
    toolchain_id: str = Field(default="cmake-host", min_length=1, max_length=200)
    target_triple: str = Field(default="host", min_length=1, max_length=100)
    profile: BuildProfile = BuildProfile.HOST_SMOKE
    output_name: str = Field(default="eea_firmware", min_length=1, max_length=100)
    output_format: str = Field(default="ELF", min_length=1, max_length=30)
    defines: dict[str, str] = Field(default_factory=dict)
    compiler_flags: list[str] = Field(default_factory=list)
    linker_flags: list[str] = Field(default_factory=list)

    @field_validator("name", "output_name")
    @classmethod
    def validate_cmake_identifiers(cls, value: str) -> str:
        if value != "host-skeleton" and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,99}", value) is None:
            raise ValueError("name and output_name must be CMake identifiers")
        return value

    @field_validator("compiler_flags", "linker_flags")
    @classmethod
    def validate_cmake_tokens(cls, values: list[str]) -> list[str]:
        for value in values:
            if (
                not value
                or any(character in value for character in "\x00\r\n;(){}$")
                or any(character.isspace() for character in value)
            ):
                raise ValueError("build flags must be single safe CMake tokens")
        return values

    @field_validator("defines")
    @classmethod
    def validate_cmake_defines(cls, values: dict[str, str]) -> dict[str, str]:
        for key, value in values.items():
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,99}", key) is None:
                raise ValueError("define names must be C identifiers")
            if any(character in value for character in "\x00\r\n;(){}$") or any(
                character.isspace() for character in value
            ):
                raise ValueError("define values must be safe single CMake tokens")
        return values


class StartupConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_symbol: str = "main"
    reset_handler: str = "Reset_Handler"
    system_init: str = "SystemInit"
    vector_table: str | None = None
    watchdog: str | None = None


class MemoryLayout(BaseModel):
    model_config = ConfigDict(extra="forbid")

    linker_script: str | None = None
    sections: dict[str, object] = Field(default_factory=dict)


class BSPConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    board_name: str = "generic-stm32"
    cmsis_device: str | None = None
    hal_family: str = "STM32_HAL"
    component_refs: list[str] = Field(default_factory=list)
    generated_include_paths: list[str] = Field(default_factory=list)
    generated_source_paths: list[str] = Field(default_factory=list)
    # Kept for reading legacy M12 rows; new generation uses generated_* fields.
    include_paths: list[str] = Field(default_factory=list)
    source_paths: list[str] = Field(default_factory=list)


class PeripheralDriverConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    peripheral: str = Field(min_length=1, max_length=100)
    driver_name: str = Field(min_length=1, max_length=200)
    init_function: str = Field(min_length=1, max_length=200)
    config_refs: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class FirmwareSourceFile(EntityBase):
    path: str = Field(min_length=1, max_length=1000)
    content: str
    content_hash: Sha256
    input_hash: Sha256
    generated_owned: bool = True
    generator_version: str = Field(min_length=1, max_length=100)


class FirmwareIR(EntityBase):
    """Structural firmware intent derived solely from the locked MCUConfigIR."""

    project_id: UUID
    mcu_config_id: UUID
    mcu_config_revision: int = Field(ge=1)
    hardware_ir_id: UUID
    hardware_ir_revision: int = Field(ge=1)
    circuit_id: UUID
    circuit_revision: int = Field(ge=1)
    schematic_id: UUID
    schematic_revision: int = Field(ge=1)
    source_revision_id: UUID
    dependency_lock_id: UUID | None = None
    dependency_lock_hash: Sha256 | None = None
    component_refs: list[str] = Field(default_factory=list)
    platform_adapter_id: str = "host-skeleton"
    platform_adapter_version: str = "m12.1"
    layers: list[str] = Field(default_factory=list)
    modules: list[FirmwareModule] = Field(default_factory=list)
    tasks: list[FirmwareTask] = Field(default_factory=list)
    interrupts: list[FirmwareInterrupt] = Field(default_factory=list)
    shared_resources: list[SharedResource] = Field(default_factory=list)
    startup: StartupConfig
    clock_tree: dict[str, object] = Field(default_factory=dict)
    peripheral_drivers: list[PeripheralDriverConfig] = Field(default_factory=list)
    memory_layout: MemoryLayout
    bsp: BSPConfig
    build_target: FirmwareBuildTarget
    rule_results: list[RuleResult] = Field(default_factory=list)
    requirement_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    input_hash: Sha256
    status: ArtifactStatus = ArtifactStatus.CURRENT


class FirmwareBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    firmware: FirmwareIR
    source_revision: SourceRevision
    files: list[FirmwareSourceFile] = Field(default_factory=list)
    dependency_lock: DependencyLock | None = None


__all__ = [
    "BSPConfig",
    "FirmwareBuildTarget",
    "FirmwareBundle",
    "FirmwareIR",
    "FirmwareInterrupt",
    "FirmwareModule",
    "FirmwareSourceFile",
    "FirmwareTask",
    "MemoryLayout",
    "PeripheralDriverConfig",
    "SharedResource",
    "StartupConfig",
]
