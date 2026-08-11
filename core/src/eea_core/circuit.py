"""Core-neutral CircuitIR contracts and electrical rule snapshots."""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from eea_core.claims import EngineeringValue
from eea_core.entities import EntityBase
from eea_core.pin_planner import RuleResult


class CircuitComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    reference: str = Field(min_length=1, max_length=100)
    kind: str = Field(min_length=1, max_length=100)
    device_ref: str | None = Field(default=None, max_length=200)
    package: str | None = Field(default=None, max_length=100)
    ratings: dict[str, object] = Field(default_factory=dict)
    attributes: dict[str, object] = Field(default_factory=dict)
    claim_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class CircuitEndpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_ref: str = Field(min_length=1, max_length=100)
    pin_ref: str = Field(min_length=1, max_length=100)
    pin_assignment_id: UUID | None = None
    attributes: dict[str, object] = Field(default_factory=dict)


class CircuitNet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    endpoints: list[CircuitEndpoint] = Field(default_factory=list)
    signal_type: str = Field(default="UNKNOWN", min_length=1, max_length=100)
    voltage_domain: str | None = Field(default=None, max_length=100)
    criticality: str = Field(default="UNKNOWN", min_length=1, max_length=30)
    attributes: dict[str, object] = Field(default_factory=dict)
    requirement_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class PowerNet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    voltage: EngineeringValue | None = None
    current: EngineeringValue | None = None
    net_ids: list[UUID] = Field(default_factory=list)
    source_component_ids: list[UUID] = Field(default_factory=list)
    attributes: dict[str, object] = Field(default_factory=dict)
    requirement_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class CircuitConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    rule_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Z][A-Z0-9_.-]*$")
    target_ref: str = Field(min_length=1, max_length=200)
    parameters: dict[str, object] = Field(default_factory=dict)
    requirement_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class CircuitIR(EntityBase):
    """Circuit topology derived from one persisted M8 HardwareIR snapshot."""

    project_id: UUID
    hardware_ir_id: UUID
    hardware_ir_revision: int = Field(ge=1)
    components: list[CircuitComponent] = Field(default_factory=list)
    nets: list[CircuitNet] = Field(default_factory=list)
    power_nets: list[PowerNet] = Field(default_factory=list)
    constraints: list[CircuitConstraint] = Field(default_factory=list)
    rule_results: list[RuleResult] = Field(default_factory=list)
    requirement_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    pin_assignment_revisions: dict[str, int] = Field(default_factory=dict)


class CircuitBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    circuit: CircuitIR
    rule_results: list[RuleResult] = Field(default_factory=list)


__all__ = [
    "CircuitBundle",
    "CircuitComponent",
    "CircuitConstraint",
    "CircuitEndpoint",
    "CircuitIR",
    "CircuitNet",
    "PowerNet",
]
