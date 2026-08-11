"""M6 versioned Requirement DSL and completeness contracts.

The Core owns only generic requirement and profile contracts. Domain-specific
profiles are registered outside Core as data.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from eea_core.claims import EngineeringClaim
from eea_core.entities import EntityBase, Issue
from eea_core.enums import (
    EngineeringDimension,
    EvidenceType,
    IssueSeverity,
    RequirementFieldStatus,
    RequirementPriority,
    RequirementStatus,
    RequirementType,
    RequirementValueType,
)


class RequirementFieldSpec(BaseModel):
    """One generic field contract in a versioned requirement profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, max_length=120, pattern=r"^[a-z][a-z0-9_.-]*$")
    label: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    value_type: RequirementValueType
    required: bool = False
    evidence_required: bool = False
    claim_predicate: str | None = Field(default=None, max_length=200)
    engineering_dimension: EngineeringDimension | None = None
    allowed_values: list[str] = Field(default_factory=list)
    text_min_length: int | None = Field(default=None, ge=1)
    number_minimum: float | None = None
    number_maximum: float | None = None
    integer_only: bool = False
    list_min_items: int | None = Field(default=None, ge=1)
    allowed_evidence_types: list[EvidenceType] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_value_contract(self) -> "RequirementFieldSpec":
        if self.value_type is RequirementValueType.ENGINEERING_VALUE:
            if self.engineering_dimension is None:
                raise ValueError("engineering-value fields require an engineering_dimension")
        elif self.engineering_dimension is not None:
            raise ValueError("engineering_dimension is only valid for engineering-value fields")
        if self.value_type is RequirementValueType.ENUM and not self.allowed_values:
            raise ValueError("enum fields require at least one allowed value")
        if len(set(self.allowed_values)) != len(self.allowed_values):
            raise ValueError("allowed_values must not contain duplicates")
        if self.text_min_length is not None and self.value_type is not RequirementValueType.TEXT:
            raise ValueError("text_min_length is only valid for text fields")
        if (
            self.number_minimum is not None or self.number_maximum is not None or self.integer_only
        ) and self.value_type is not RequirementValueType.NUMBER:
            raise ValueError("number constraints are only valid for number fields")
        if (
            self.number_minimum is not None
            and self.number_maximum is not None
            and self.number_minimum > self.number_maximum
        ):
            raise ValueError("number_minimum must not exceed number_maximum")
        if self.list_min_items is not None and self.value_type is not RequirementValueType.LIST:
            raise ValueError("list_min_items is only valid for list fields")
        return self


class RequirementEvidenceContract(BaseModel):
    """Evidence obligation declared by a requirement profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, max_length=120, pattern=r"^[a-z][a-z0-9_.-]*$")
    description: str = Field(min_length=1, max_length=1000)
    required: bool = True
    allowed_types: list[EvidenceType] = Field(default_factory=list)


class RequirementProfile(EntityBase):
    """Reproducible field/evidence contract selected by name and version."""

    profile_name: str = Field(min_length=1, max_length=120, pattern=r"^[a-z][a-z0-9_.-]*$")
    profile_version: str = Field(min_length=1, max_length=50)
    purpose: str = Field(min_length=1, max_length=2000)
    fields: list[RequirementFieldSpec] = Field(min_length=1)
    evidence_contracts: list[RequirementEvidenceContract] = Field(default_factory=list)
    active: bool = True

    @model_validator(mode="after")
    def fields_and_evidence_are_unique(self) -> "RequirementProfile":
        field_keys = [field.key for field in self.fields]
        evidence_keys = [contract.key for contract in self.evidence_contracts]
        if len(set(field_keys)) != len(field_keys):
            raise ValueError("requirement profile fields must be unique")
        if len(set(evidence_keys)) != len(evidence_keys):
            raise ValueError("requirement evidence contracts must be unique")
        return self


class Requirement(EntityBase):
    """A candidate requirement with explicit acceptance and evidence links."""

    project_id: UUID
    code: str = Field(min_length=1, max_length=120, pattern=r"^[A-Z][A-Z0-9_.-]*$")
    title: str = Field(min_length=1, max_length=300)
    requirement_type: RequirementType = RequirementType.UNKNOWN
    priority: RequirementPriority = RequirementPriority.UNKNOWN
    statement: str = Field(min_length=1, max_length=8000)
    rationale: str = Field(default="", max_length=8000)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=50)
    source_evidence_ids: list[UUID] = Field(default_factory=list)
    status: RequirementStatus = RequirementStatus.CANDIDATE


class RequirementDraft(BaseModel):
    """Provider-owned requirement content without server-owned identity fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1, max_length=120, pattern=r"^[A-Z][A-Z0-9_.-]*$")
    title: str = Field(min_length=1, max_length=300)
    requirement_type: RequirementType = RequirementType.UNKNOWN
    priority: RequirementPriority = RequirementPriority.UNKNOWN
    statement: str = Field(min_length=1, max_length=8000)
    rationale: str = Field(default="", max_length=8000)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=50)
    source_evidence_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_blank_content(self) -> "RequirementDraft":
        for field_name in ("code", "title", "statement"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} cannot be empty or whitespace")
        return self


class RequirementFieldObservation(BaseModel):
    """Structured-generation observation for one profile field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field_key: str = Field(min_length=1, max_length=120)
    status: RequirementFieldStatus = RequirementFieldStatus.UNKNOWN
    value: object | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)
    ambiguity_reason: str | None = Field(default=None, max_length=2000)


class RequirementClaimDraft(BaseModel):
    """Provider output for a claim; refs are resolved by the application layer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject_ref: str = Field(min_length=1, max_length=500)
    predicate: str = Field(min_length=1, max_length=200, pattern=r"^[a-z][a-z0-9_.-]*$")
    value: object
    applicability: dict[str, object] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)
    source_priority: int = Field(default=0, ge=0, le=1000)
    source_version: str | None = Field(default=None, max_length=200)


class RequirementIssueDraft(BaseModel):
    """Provider or deterministic finding before UUID references are resolved."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1, max_length=100, pattern=r"^[A-Z][A-Z0-9_.-]*$")
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=8000)
    severity: IssueSeverity = IssueSeverity.MEDIUM
    field_keys: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class FollowUpQuestion(BaseModel):
    """A question that must be answered before a requirement can be accepted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1, max_length=100, pattern=r"^[A-Z][A-Z0-9_.-]*$")
    question: str = Field(min_length=1, max_length=2000)
    field_keys: list[str] = Field(default_factory=list)
    blocking: bool = True
    reason: str = Field(min_length=1, max_length=2000)


class RequirementAnalysisDraft(BaseModel):
    """Strict structured-generation response for natural-language analysis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_name: str = Field(min_length=1, max_length=120)
    profile_version: str = Field(min_length=1, max_length=50)
    requirements: list[RequirementDraft] = Field(default_factory=list)
    field_observations: list[RequirementFieldObservation] = Field(default_factory=list)
    claims: list[RequirementClaimDraft] = Field(default_factory=list)
    issues: list[RequirementIssueDraft] = Field(default_factory=list)
    follow_up_questions: list[FollowUpQuestion] = Field(default_factory=list)


class RequirementCompleteness(BaseModel):
    """Deterministic completeness result; UNKNOWN is never promoted to PASS."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: RequirementStatus
    score: float = Field(ge=0, le=1)
    required_field_keys: list[str] = Field(default_factory=list)
    missing_field_keys: list[str] = Field(default_factory=list)
    ambiguous_field_keys: list[str] = Field(default_factory=list)
    missing_evidence_keys: list[str] = Field(default_factory=list)


class RequirementAnalysis(EntityBase):
    """Auditable result of deterministic or structured requirement analysis.

    ``requirements`` and ``claims`` are immutable snapshots for this analysis.
    ``requirement_ids`` and ``claim_ids`` are canonical persistence references;
    M7+ consumers must use those references as the source of truth.
    """

    project_id: UUID
    profile_name: str = Field(min_length=1, max_length=120)
    profile_version: str = Field(min_length=1, max_length=50)
    requirements: list[Requirement] = Field(default_factory=list)
    field_observations: list[RequirementFieldObservation] = Field(default_factory=list)
    claims: list[EngineeringClaim] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    follow_up_questions: list[FollowUpQuestion] = Field(default_factory=list)
    completeness: RequirementCompleteness
    requirement_ids: list[UUID] = Field(default_factory=list)
    claim_ids: list[UUID] = Field(default_factory=list)
