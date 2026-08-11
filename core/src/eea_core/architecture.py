"""Core-neutral SystemArchitecture and Hardware IR contracts."""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from eea_core.claims import EngineeringValue
from eea_core.entities import EntityBase
from eea_core.pin_planner import PinRequirement


class ArchitectureBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    attributes: dict[str, object] = Field(default_factory=dict)
    requirement_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class ArchitectureInterface(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    interface_type: str = Field(min_length=1, max_length=100)
    source_ref: str = Field(min_length=1, max_length=200)
    target_ref: str = Field(min_length=1, max_length=200)
    attributes: dict[str, object] = Field(default_factory=dict)
    pin_assignment_ids: list[UUID] = Field(default_factory=list)
    requirement_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class ArchitectureDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    title: str = Field(min_length=1, max_length=300)
    decision: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(min_length=1, max_length=4000)
    requirement_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class HardwareModule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(min_length=1, max_length=100)
    attributes: dict[str, object] = Field(default_factory=dict)
    requirement_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class HardwareDeviceInstance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    device_ref: str = Field(min_length=1, max_length=200)
    package: str | None = Field(default=None, max_length=100)
    module_ref: UUID
    pin_assignment_ids: list[UUID] = Field(default_factory=list)
    attributes: dict[str, object] = Field(default_factory=dict)
    claim_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class PowerDomain(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    voltage: EngineeringValue | None = None
    attributes: dict[str, object] = Field(default_factory=dict)
    evidence_ids: list[UUID] = Field(default_factory=list)


class HardwareInterface(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    interface_type: str = Field(min_length=1, max_length=100)
    endpoint_refs: list[str] = Field(min_length=1)
    attributes: dict[str, object] = Field(default_factory=dict)
    pin_assignment_ids: list[UUID] = Field(default_factory=list)
    requirement_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class SystemArchitectureIR(EntityBase):
    """Project architecture derived from one persisted, validated M7 plan."""

    project_id: UUID
    pin_plan_id: UUID
    pin_plan_revision: int = Field(ge=1)
    blocks: list[ArchitectureBlock] = Field(default_factory=list)
    interfaces: list[ArchitectureInterface] = Field(default_factory=list)
    decisions: list[ArchitectureDecision] = Field(default_factory=list)
    requirement_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    source_artifact_ids: list[UUID] = Field(default_factory=list)
    pin_assignment_revisions: dict[str, int] = Field(default_factory=dict)


class HardwareIR(EntityBase):
    """Hardware topology derived from the same persisted M7 plan as the architecture IR."""

    project_id: UUID
    architecture_id: UUID
    pin_plan_id: UUID
    pin_plan_revision: int = Field(ge=1)
    modules: list[HardwareModule] = Field(default_factory=list)
    device_instances: list[HardwareDeviceInstance] = Field(default_factory=list)
    power_domains: list[PowerDomain] = Field(default_factory=list)
    interfaces: list[HardwareInterface] = Field(default_factory=list)
    pin_requirements: list[PinRequirement] = Field(default_factory=list)
    constraints: list[dict[str, object]] = Field(default_factory=list)
    requirement_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    pin_assignment_revisions: dict[str, int] = Field(default_factory=dict)


class ArchitectureBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_architecture: SystemArchitectureIR
    hardware: HardwareIR


__all__ = [
    "ArchitectureBlock",
    "ArchitectureBundle",
    "ArchitectureDecision",
    "ArchitectureInterface",
    "HardwareDeviceInstance",
    "HardwareIR",
    "HardwareInterface",
    "HardwareModule",
    "PowerDomain",
    "SystemArchitectureIR",
]
