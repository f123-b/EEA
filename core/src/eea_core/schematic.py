"""Core-neutral schematic artifacts and ERC reports derived from CircuitIR."""

from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from eea_core.circuit import CircuitComponent, CircuitConstraint, CircuitNet, PowerNet
from eea_core.entities import Artifact, EntityBase, Sha256
from eea_core.enums import IssueSeverity
from eea_core.pin_planner import RuleResult


class SchematicIR(EntityBase):
    """Editable deterministic netlist derived from one persisted CircuitIR snapshot."""

    project_id: UUID
    artifact_id: UUID
    circuit_id: UUID
    circuit_revision: int = Field(ge=1)
    hardware_ir_id: UUID
    hardware_ir_revision: int = Field(ge=1)
    format: str = Field(default="EEA_NETLIST_V1", min_length=1, max_length=50)
    components: list[CircuitComponent] = Field(default_factory=list)
    nets: list[CircuitNet] = Field(default_factory=list)
    power_nets: list[PowerNet] = Field(default_factory=list)
    constraints: list[CircuitConstraint] = Field(default_factory=list)
    netlist_text: str = Field(min_length=1)
    content_hash: Sha256
    input_hash: Sha256
    preflight_results: list[RuleResult] = Field(default_factory=list)
    requirement_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    pin_assignment_revisions: dict[str, int] = Field(default_factory=dict)


class ErcIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    code: str = Field(min_length=1, max_length=100, pattern=r"^[A-Z][A-Z0-9_.-]*$")
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=4000)
    severity: IssueSeverity
    affected_refs: list[str] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class ErcReport(EntityBase):
    """Auditable ERC execution/import result; UNKNOWN is never tool verification."""

    project_id: UUID
    schematic_id: UUID
    schematic_revision: int = Field(ge=1)
    circuit_id: UUID
    circuit_revision: int = Field(ge=1)
    status: Literal["PASS", "FAIL", "UNKNOWN"]
    tool_name: str | None = Field(default=None, max_length=100)
    tool_version: str | None = Field(default=None, max_length=100)
    executed: bool = False
    issues: list[ErcIssue] = Field(default_factory=list)
    source_revision_snapshot: dict[str, object] = Field(default_factory=dict)
    evidence_ids: list[UUID] = Field(default_factory=list)
    recommendation: str = Field(default="", max_length=2000)


class SchematicBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact: Artifact
    schematic: SchematicIR
    erc_report: ErcReport


__all__ = ["ErcIssue", "ErcReport", "SchematicBundle", "SchematicIR"]
