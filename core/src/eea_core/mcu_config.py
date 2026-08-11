"""Core-neutral MCU configuration IR and deterministic rule snapshots."""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from eea_core.claims import EngineeringValue
from eea_core.entities import EntityBase
from eea_core.enums import ArtifactStatus
from eea_core.pin_planner import RuleResult


class ClockIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=100)
    source_frequency: EngineeringValue | None = None
    target_frequency: EngineeringValue | None = None
    peripheral_clocks: dict[str, EngineeringValue] = Field(default_factory=dict)
    parameters: dict[str, object] = Field(default_factory=dict)
    tolerance_percent: float | None = Field(default=None, ge=0)
    evidence_ids: list[UUID] = Field(default_factory=list)


class GPIOConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    pin_assignment_id: UUID
    signal_ref: str = Field(min_length=1, max_length=200)
    mode: str = Field(min_length=1, max_length=50)
    pull: str | None = Field(default=None, max_length=30)
    output_type: str | None = Field(default=None, max_length=30)
    speed: str | None = Field(default=None, max_length=30)
    alternate_function: str | None = Field(default=None, max_length=50)
    voltage: EngineeringValue | None = None
    requirement_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class PWMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    timer: str = Field(min_length=1, max_length=100)
    channel: str = Field(min_length=1, max_length=50)
    complementary_channel: str | None = Field(default=None, max_length=50)
    center_aligned: bool = False
    switching_frequency: EngineeringValue | None = None
    realized_frequency: EngineeringValue | None = None
    deadtime: EngineeringValue | None = None
    polarity: str = Field(default="ACTIVE_HIGH", max_length=30)
    break_input: str | None = Field(default=None, max_length=100)
    update_event: str | None = Field(default=None, max_length=100)
    pin_assignment_ids: list[UUID] = Field(default_factory=list)
    requirement_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class ADCConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    instance: str = Field(min_length=1, max_length=100)
    channels: list[str] = Field(default_factory=list)
    sampling_time: EngineeringValue | None = None
    trigger_source: str | None = Field(default=None, max_length=100)
    trigger_edge: str | None = Field(default=None, max_length=30)
    conversion_mode: str = Field(default="REGULAR", max_length=50)
    injected_or_regular: str = Field(default="REGULAR", max_length=30)
    dma_ref: str | None = Field(default=None, max_length=100)
    expected_range: dict[str, EngineeringValue] = Field(default_factory=dict)
    pin_assignment_ids: list[UUID] = Field(default_factory=list)
    requirement_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class PeripheralConfigIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    instance: str = Field(min_length=1, max_length=100)
    mode: str = Field(min_length=1, max_length=100)
    pin_assignment_ids: list[UUID] = Field(default_factory=list)
    clock: EngineeringValue | None = None
    parameters: dict[str, object] = Field(default_factory=dict)
    dma_refs: list[str] = Field(default_factory=list)
    interrupt_refs: list[str] = Field(default_factory=list)
    trigger_refs: list[str] = Field(default_factory=list)
    pwm: list[PWMConfig] = Field(default_factory=list)
    adc: list[ADCConfig] = Field(default_factory=list)
    requirement_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class DMAIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    controller: str = Field(min_length=1, max_length=100)
    channel_or_stream: str = Field(min_length=1, max_length=50)
    request: str = Field(min_length=1, max_length=100)
    direction: str = Field(min_length=1, max_length=30)
    width: int = Field(default=32, ge=1)
    mode: str = Field(default="NORMAL", max_length=30)
    priority: int = Field(default=0, ge=0)
    circular: bool = False
    buffer: dict[str, object] = Field(default_factory=dict)
    requirement_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class InterruptConfigIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    source: str = Field(min_length=1, max_length=100)
    irq: str = Field(min_length=1, max_length=100)
    priority: int = Field(ge=0)
    subpriority: int = Field(default=0, ge=0)
    max_execution_us: EngineeringValue | None = None
    allowed_operations: list[str] = Field(default_factory=list)
    communicates_with_tasks: list[str] = Field(default_factory=list)
    requirement_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class MemoryConfigIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flash_origin: int | None = Field(default=None, ge=0)
    flash_length: int | None = Field(default=None, ge=0)
    ram_origin: int | None = Field(default=None, ge=0)
    ram_length: int | None = Field(default=None, ge=0)
    linker_script_ref: str | None = Field(default=None, max_length=200)


class DebugConfigIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interface: str = Field(min_length=1, max_length=50)
    pin_assignment_ids: list[UUID] = Field(default_factory=list)
    enabled: bool = True


class MCUConfigIR(EntityBase):
    """The sole realized source for timer/PWM/ADC/DMA/IRQ configuration."""

    project_id: UUID
    hardware_ir_id: UUID
    hardware_ir_revision: int = Field(ge=1)
    circuit_id: UUID
    circuit_revision: int = Field(ge=1)
    schematic_id: UUID
    schematic_revision: int = Field(ge=1)
    device_instance_id: UUID
    clock: ClockIR
    gpio: list[GPIOConfig] = Field(default_factory=list)
    peripherals: list[PeripheralConfigIR] = Field(default_factory=list)
    dma: list[DMAIR] = Field(default_factory=list)
    interrupts: list[InterruptConfigIR] = Field(default_factory=list)
    memory: MemoryConfigIR | None = None
    debug: DebugConfigIR | None = None
    capability_snapshot: dict[str, object] = Field(default_factory=dict)
    rule_results: list[RuleResult] = Field(default_factory=list)
    requirement_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    pin_assignment_revisions: dict[str, int] = Field(default_factory=dict)
    status: ArtifactStatus = ArtifactStatus.CURRENT


class MCUConfigBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: MCUConfigIR
    rule_results: list[RuleResult] = Field(default_factory=list)


__all__ = [
    "DMAIR",
    "ADCConfig",
    "ClockIR",
    "DebugConfigIR",
    "GPIOConfig",
    "InterruptConfigIR",
    "MCUConfigBundle",
    "MCUConfigIR",
    "MemoryConfigIR",
    "PWMConfig",
    "PeripheralConfigIR",
]
