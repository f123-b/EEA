"""Core-neutral Pin Planner contracts and deterministic Rule results.

The planner models requirements and assignments only. Device facts remain owned by the
M4 provider boundary; no concrete product-domain schema is defined here.
"""

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from eea_core.claims import EngineeringValue
from eea_core.entities import EntityBase
from eea_core.enums import IssueSeverity
from eea_core.intelligence import PinFunction

RuleStatus = Literal["PASS", "FAIL", "NOT_APPLICABLE", "UNKNOWN"]
RuleStage = Literal["PRE_GENERATION", "POST_GENERATION", "PRE_TOOL", "POST_TOOL", "RELEASE_GATE"]


class PinRequirement(EntityBase):
    """A generic signal requirement derived from canonical project facts."""

    project_id: UUID
    signal_name: str = Field(min_length=1, max_length=200)
    required_peripheral: str = Field(min_length=1, max_length=100)
    required_function: str = Field(min_length=1, max_length=100)
    direction: str = Field(default="UNKNOWN", min_length=1, max_length=30)
    electrical_requirements: dict[str, object] = Field(default_factory=dict)
    hard_constraints: dict[str, object] = Field(default_factory=dict)
    preferred_constraints: dict[str, object] = Field(default_factory=dict)
    timing_constraints: dict[str, object] = Field(default_factory=dict)
    requirement_ids: list[UUID] = Field(default_factory=list)
    claim_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_voltage_constraint(self) -> "PinRequirement":
        if not self.requirement_ids and not self.claim_ids:
            raise ValueError("a PinRequirement must reference a canonical requirement or claim")
        voltage = self.hard_constraints.get("voltage")
        if voltage is not None:
            try:
                EngineeringValue.model_validate(voltage)
            except ValueError as exc:
                raise ValueError("hard_constraints.voltage must be an EngineeringValue") from exc
        return self


class PinCandidate(EntityBase):
    """One device pin/function candidate for a PinRequirement."""

    project_id: UUID
    requirement_id: UUID
    device_ref: str = Field(min_length=1, max_length=200)
    package: str | None = Field(default=None, max_length=100)
    pin_name: str = Field(min_length=1, max_length=50)
    function: PinFunction
    score: float = Field(default=0, ge=0, le=1)
    source_refs: list[str] = Field(default_factory=list)


class PinAssignment(EntityBase):
    """A deterministic, traceable pin assignment candidate."""

    project_id: UUID
    requirement_id: UUID
    device_ref: str = Field(min_length=1, max_length=200)
    package: str | None = Field(default=None, max_length=100)
    pin_name: str = Field(min_length=1, max_length=50)
    function: PinFunction
    locked: bool = False
    score: float = Field(default=0, ge=0, le=1)
    claim_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class PinLock(EntityBase):
    """Explicit user lock; a later plan must not silently replace it."""

    project_id: UUID
    assignment_id: UUID
    locked_by: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=2000)


class RuleResult(EntityBase):
    """Auditable deterministic rule output; UNKNOWN is never promoted to PASS."""

    project_id: UUID
    rule_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Z][A-Z0-9_.-]*$")
    rule_version: str = Field(min_length=1, max_length=50)
    stage: RuleStage
    status: RuleStatus
    severity: IssueSeverity
    affected_refs: list[str] = Field(default_factory=list)
    measured: object | None = None
    threshold: object | None = None
    evidence_ids: list[UUID] = Field(default_factory=list)
    claim_ids: list[UUID] = Field(default_factory=list)
    recommendation: str = Field(default="", max_length=2000)
    input_snapshot: dict[str, object] = Field(default_factory=dict)


class PinPlan(EntityBase):
    """An in-memory M7 planning result ready for a later durable adapter."""

    project_id: UUID
    device_ref: str = Field(min_length=1, max_length=200)
    package: str | None = Field(default=None, max_length=100)
    requirements: list[PinRequirement] = Field(default_factory=list)
    candidates: list[PinCandidate] = Field(default_factory=list)
    assignments: list[PinAssignment] = Field(default_factory=list)
    locks: list[PinLock] = Field(default_factory=list)
    rule_results: list[RuleResult] = Field(default_factory=list)
