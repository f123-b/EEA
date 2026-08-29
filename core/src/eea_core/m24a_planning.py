"""M24A planning contracts.

M24A is deliberately proposal-only.  These models describe an auditable
engineering plan and its provenance; they do not represent a source patch,
command, build, test run, or hardware action.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from eea_core.entities import EntityBase


class EngineeringRequirementType(StrEnum):
    FEATURE = "FEATURE"
    BUG_FIX = "BUG_FIX"
    PERFORMANCE = "PERFORMANCE"
    RELIABILITY = "RELIABILITY"
    HARDWARE_CHANGE = "HARDWARE_CHANGE"
    FIRMWARE_CHANGE = "FIRMWARE_CHANGE"
    PROTOCOL_CHANGE = "PROTOCOL_CHANGE"
    BUILD_CHANGE = "BUILD_CHANGE"
    TEST_CHANGE = "TEST_CHANGE"
    REFACTOR = "REFACTOR"
    INVESTIGATION = "INVESTIGATION"


class EngineeringRequirementPriority(StrEnum):
    UNKNOWN = "UNKNOWN"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    MUST = "MUST"
    SHOULD = "SHOULD"
    COULD = "COULD"


class EngineeringRequirementStatus(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    ANALYZING = "ANALYZING"
    PLANNED = "PLANNED"
    NEEDS_INPUT = "NEEDS_INPUT"
    BLOCKED = "BLOCKED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class EngineeringPlanStatus(StrEnum):
    DRAFT = "DRAFT"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    NEEDS_INPUT = "NEEDS_INPUT"
    BLOCKED = "BLOCKED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    STALE = "STALE"


class PlanningActionType(StrEnum):
    ANALYZE = "ANALYZE"
    MODIFY_SOURCE = "MODIFY_SOURCE"
    MODIFY_CONFIG = "MODIFY_CONFIG"
    MODIFY_HARDWARE = "MODIFY_HARDWARE"
    MODIFY_PROTOCOL = "MODIFY_PROTOCOL"
    ADD_TEST = "ADD_TEST"
    UPDATE_BUILD = "UPDATE_BUILD"
    UPDATE_DOCUMENTATION = "UPDATE_DOCUMENTATION"
    VERIFY = "VERIFY"
    INVESTIGATE = "INVESTIGATE"


class PlanningTargetType(StrEnum):
    FILE = "file"
    SYMBOL = "symbol"
    MODULE = "module"
    CONFIG = "config"
    CLAIM = "claim"
    HARDWARE_COMPONENT = "hardware_component"
    PROTOCOL_ITEM = "protocol_item"
    REQUIREMENT = "requirement"
    PROJECT = "project"


class ProposedChangeStatus(StrEnum):
    PROPOSED = "PROPOSED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    NEEDS_REVISION = "NEEDS_REVISION"
    BLOCKED = "BLOCKED"


class EngineeringRiskCategory(StrEnum):
    FUNCTIONAL = "FUNCTIONAL"
    SAFETY = "SAFETY"
    TIMING = "TIMING"
    RESOURCE = "RESOURCE"
    COMPATIBILITY = "COMPATIBILITY"
    HARDWARE = "HARDWARE"
    PROTOCOL = "PROTOCOL"
    BUILD = "BUILD"
    TEST = "TEST"
    SECURITY = "SECURITY"
    MAINTAINABILITY = "MAINTAINABILITY"


class EngineeringRiskSeverity(StrEnum):
    UNKNOWN = "UNKNOWN"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EngineeringRiskLikelihood(StrEnum):
    UNKNOWN = "UNKNOWN"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ContextAuthority(StrEnum):
    USER_REQUIREMENT = "USER_REQUIREMENT"
    CANONICAL = "CANONICAL"
    DERIVED = "DERIVED"
    MEMORY = "MEMORY"
    UNTRUSTED_SOURCE = "UNTRUSTED_SOURCE"


class ContextTrust(StrEnum):
    TRUSTED = "TRUSTED"
    REVIEWED = "REVIEWED"
    UNTRUSTED = "UNTRUSTED"
    UNKNOWN = "UNKNOWN"


class ContextFreshness(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    CONFLICTED = "CONFLICTED"
    UNKNOWN = "UNKNOWN"


class PlanReviewAction(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_REVISION = "REQUEST_REVISION"


class PlanReviewStatus(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVISION_REQUESTED = "REVISION_REQUESTED"


class EngineeringRequirement(EntityBase):
    """A project-scoped, reviewable engineering requirement intake."""

    project_id: UUID
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20_000)
    requirement_type: EngineeringRequirementType = EngineeringRequirementType.INVESTIGATION
    priority: EngineeringRequirementPriority = EngineeringRequirementPriority.UNKNOWN
    constraints: list[str] = Field(default_factory=list, max_length=100)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=100)
    source: dict[str, Any] = Field(default_factory=dict)
    created_by: str = Field(min_length=1, max_length=200)
    status: EngineeringRequirementStatus = EngineeringRequirementStatus.DRAFT


class PlanningValueModel(BaseModel):
    """Strict nested planning value with no server-owned identity fields."""

    model_config = ConfigDict(extra="forbid")


class ContextItem(PlanningValueModel):
    """One selected context item with authority, trust and freshness."""

    kind: str = Field(min_length=1, max_length=100)
    canonical_ref: str = Field(min_length=1, max_length=500)
    value: Any
    authority: ContextAuthority
    trust: ContextTrust
    freshness: ContextFreshness
    evidence_refs: list[UUID] = Field(default_factory=list)
    source_revision_ref: UUID | None = None
    reason: str = Field(default="", max_length=2_000)


class PlanningContextSnapshot(EntityBase):
    """The reproducible planner input; it is not canonical engineering truth."""

    project_id: UUID
    source_revision_id: UUID | None = None
    selected_context: list[ContextItem] = Field(default_factory=list)
    excluded_context: list[ContextItem] = Field(default_factory=list)
    selection_reason: dict[str, str] = Field(default_factory=dict)
    claim_revisions: dict[str, int] = Field(default_factory=dict)
    evidence_revisions: dict[str, int] = Field(default_factory=dict)
    memory_refs: list[UUID] = Field(default_factory=list)
    evidence_refs: list[UUID] = Field(default_factory=list)
    source_content_is_untrusted: bool = True


class EngineeringAssumption(PlanningValueModel):
    description: str = Field(min_length=1, max_length=4_000)
    basis: str = Field(min_length=1, max_length=4_000)
    confidence: EngineeringRiskSeverity = EngineeringRiskSeverity.UNKNOWN
    evidence_refs: list[UUID] = Field(default_factory=list)
    validation_required: bool = True


class EngineeringUnknown(PlanningValueModel):
    question: str = Field(min_length=1, max_length=4_000)
    why_needed: str = Field(min_length=1, max_length=4_000)
    blocking: bool = True
    recommended_resolution: str = Field(min_length=1, max_length=4_000)
    related_refs: list[str] = Field(default_factory=list)


class EngineeringRisk(PlanningValueModel):
    id: UUID = Field(default_factory=uuid4)
    category: EngineeringRiskCategory
    severity: EngineeringRiskSeverity
    likelihood: EngineeringRiskLikelihood
    description: str = Field(min_length=1, max_length=4_000)
    affected_ref: str = Field(min_length=1, max_length=500)
    mitigation: str = Field(min_length=1, max_length=4_000)
    verification: str = Field(min_length=1, max_length=4_000)
    reason: str = Field(default="", max_length=4_000)
    evidence_refs: list[UUID] = Field(default_factory=list)


class ProposedEngineeringChange(PlanningValueModel):
    id: UUID = Field(default_factory=uuid4)
    change_type: PlanningActionType
    target_kind: PlanningTargetType
    target_ref: str = Field(min_length=1, max_length=2_000)
    current_state: Any = None
    proposed_state: Any = None
    reason: str = Field(min_length=1, max_length=4_000)
    impact: str = Field(default="", max_length=4_000)
    risk: EngineeringRiskSeverity = EngineeringRiskSeverity.UNKNOWN
    evidence_refs: list[UUID] = Field(default_factory=list)
    confidence: EngineeringRiskSeverity = EngineeringRiskSeverity.UNKNOWN
    status: ProposedChangeStatus = ProposedChangeStatus.PROPOSED
    expected_diff_intent: str = Field(default="", max_length=8_000)

    @model_validator(mode="after")
    def reject_executable_mutations(self) -> ProposedEngineeringChange:
        text = f"{self.expected_diff_intent} {self.reason} {self.impact}".lower()
        if any(
            token in text for token in ("shell", "subprocess", "exec(", "apply patch", "git commit")
        ):
            raise ValueError("a proposed change cannot contain executable mutation instructions")
        return self


class EngineeringPlanStep(PlanningValueModel):
    id: UUID = Field(default_factory=uuid4)
    order: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=8_000)
    action_type: PlanningActionType
    target_type: PlanningTargetType
    target_ref: str = Field(min_length=1, max_length=2_000)
    reason: str = Field(min_length=1, max_length=4_000)
    dependencies: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    expected_result: str = Field(min_length=1, max_length=4_000)
    verification_plan: list[str] = Field(default_factory=list, min_length=1)
    risk_level: EngineeringRiskSeverity = EngineeringRiskSeverity.UNKNOWN
    evidence_refs: list[UUID] = Field(default_factory=list)


class AcceptanceCriterionMapping(PlanningValueModel):
    criterion: str = Field(min_length=1, max_length=4_000)
    step_ids: list[UUID] = Field(min_length=1)
    verification_refs: list[str] = Field(min_length=1)


class PlanVerification(PlanningValueModel):
    id: UUID = Field(default_factory=uuid4)
    change_id: UUID
    method: str = Field(min_length=1, max_length=500)
    expected_result: str = Field(min_length=1, max_length=4_000)
    execution_allowed_in_m24a: bool = False


class EngineeringPlan(EntityBase):
    """Structured proposal whose approval never authorizes execution in M24A."""

    project_id: UUID
    requirement_id: UUID
    source_revision_id: UUID | None = None
    context_snapshot_id: UUID
    status: EngineeringPlanStatus = EngineeringPlanStatus.DRAFT
    summary: str = Field(min_length=1, max_length=12_000)
    assumptions: list[EngineeringAssumption] = Field(default_factory=list)
    unknowns: list[EngineeringUnknown] = Field(default_factory=list)
    risks: list[EngineeringRisk] = Field(default_factory=list)
    steps: list[EngineeringPlanStep] = Field(default_factory=list)
    proposed_changes: list[ProposedEngineeringChange] = Field(default_factory=list)
    affected_components: list[str] = Field(default_factory=list)
    evidence_refs: list[UUID] = Field(default_factory=list)
    memory_refs: list[UUID] = Field(default_factory=list)
    acceptance_criteria_mapping: list[AcceptanceCriterionMapping] = Field(default_factory=list)
    verification_plans: list[PlanVerification] = Field(default_factory=list)
    provider: str = Field(min_length=1, max_length=200)
    model_version: str = Field(min_length=1, max_length=200)
    prompt_template_version: str = Field(min_length=1, max_length=100)
    planning_policy_version: str = Field(min_length=1, max_length=100)
    created_by: str = Field(min_length=1, max_length=200)
    supersedes_plan_id: UUID | None = None


class PlanReview(PlanningValueModel):
    id: UUID = Field(default_factory=uuid4)
    plan_id: UUID
    action: PlanReviewAction
    status: PlanReviewStatus
    expected_revision: int = Field(ge=1)
    comment: str = Field(default="", max_length=8_000)
    reviewed_by: str = Field(min_length=1, max_length=200)
    execution_authorized: bool = False


class PlanReviewComment(PlanningValueModel):
    id: UUID = Field(default_factory=uuid4)
    plan_id: UUID
    target_kind: str = Field(min_length=1, max_length=100)
    target_ref: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=8_000)
    created_by: str = Field(min_length=1, max_length=200)


__all__ = [
    "AcceptanceCriterionMapping",
    "ContextAuthority",
    "ContextFreshness",
    "ContextItem",
    "ContextTrust",
    "EngineeringAssumption",
    "EngineeringPlan",
    "EngineeringPlanStatus",
    "EngineeringPlanStep",
    "EngineeringRequirement",
    "EngineeringRequirementPriority",
    "EngineeringRequirementStatus",
    "EngineeringRequirementType",
    "EngineeringRisk",
    "EngineeringRiskCategory",
    "EngineeringRiskLikelihood",
    "EngineeringRiskSeverity",
    "EngineeringUnknown",
    "PlanReview",
    "PlanReviewAction",
    "PlanReviewComment",
    "PlanReviewStatus",
    "PlanVerification",
    "PlanningActionType",
    "PlanningContextSnapshot",
    "PlanningTargetType",
    "ProposedChangeStatus",
    "ProposedEngineeringChange",
]
