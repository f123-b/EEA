"""M1 core entities with stable IDs, versions, and optimistic revisions."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from eea_core.enums import (
    ArtifactStatus,
    DecisionStatus,
    EngineeringErrorCode,
    EvidenceType,
    IssueSeverity,
    IssueStatus,
    JobStatus,
    Permission,
    ProjectStatus,
    TraceabilityRelation,
)

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


def utc_now() -> datetime:
    return datetime.now(UTC)


class EntityBase(BaseModel):
    """Common immutable identity and optimistic-concurrency metadata."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    schema_version: str = "1.0"
    revision: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_datetime_to_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def updated_at_cannot_precede_creation(self) -> "EntityBase":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        return self


class Project(EntityBase):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    status: ProjectStatus = ProjectStatus.DRAFT
    deleted_at: datetime | None = None

    @field_validator("deleted_at")
    @classmethod
    def normalize_optional_datetime_to_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class Artifact(EntityBase):
    """Immutable versioned output or snapshot metadata."""

    project_id: UUID
    logical_name: str = Field(min_length=1, max_length=300)
    artifact_type: str = Field(min_length=1, max_length=100)
    version_label: str = Field(min_length=1, max_length=100)
    content_hash: Sha256
    input_hash: Sha256
    storage_uri: str = Field(min_length=1, max_length=2000)
    parent_artifact_id: UUID | None = None
    dependency_ids: list[UUID] = Field(default_factory=list)
    dependency_hashes: dict[str, Sha256] = Field(default_factory=dict)
    created_by: str = Field(min_length=1, max_length=200)
    source_job_id: UUID | None = None
    generator_version: str | None = Field(default=None, max_length=100)
    tool_versions: dict[str, str] = Field(default_factory=dict)
    knowledge_snapshot: str | None = Field(default=None, max_length=200)
    status: ArtifactStatus = ArtifactStatus.CURRENT


class Evidence(EntityBase):
    project_id: UUID | None = None
    evidence_type: EvidenceType
    locator: dict[str, object]
    source_uri: str | None = Field(default=None, max_length=2000)
    content_hash: Sha256 | None = None
    summary: str = Field(default="", max_length=4000)


class Issue(EntityBase):
    project_id: UUID
    code: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=8000)
    severity: IssueSeverity
    status: IssueStatus = IssueStatus.OPEN
    claim_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    resolution: str | None = Field(default=None, max_length=8000)
    dedupe_key: str | None = Field(default=None, max_length=64)
    source_kind: str | None = Field(default=None, max_length=100)
    source_ref: str | None = Field(default=None, max_length=300)
    affected_refs: list[str] = Field(default_factory=list)
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    occurrence_count: int = Field(default=1, ge=1)
    last_review_id: UUID | None = None


class EngineeringDecision(EntityBase):
    project_id: UUID
    title: str = Field(min_length=1, max_length=300)
    context: str = Field(min_length=1, max_length=8000)
    decision: str = Field(min_length=1, max_length=8000)
    rationale: str = Field(min_length=1, max_length=8000)
    alternatives: list[str] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    status: DecisionStatus = DecisionStatus.PROPOSED


class Job(EntityBase):
    project_id: UUID | None = None
    job_type: str = Field(min_length=1, max_length=100)
    status: JobStatus = JobStatus.QUEUED
    progress: float = Field(default=0, ge=0, le=1)
    phase: str | None = Field(default=None, max_length=200)
    result_ref: str | None = Field(default=None, max_length=2000)
    error_code: EngineeringErrorCode | None = None
    error_message: str | None = Field(default=None, max_length=8000)
    budget_usage: dict[str, float] = Field(default_factory=dict)
    resource_lock_ids: list[UUID] = Field(default_factory=list)


class PermissionAuditRecord(EntityBase):
    project_id: UUID | None = None
    actor_id: str = Field(min_length=1, max_length=200)
    permission: Permission
    resource_type: str = Field(min_length=1, max_length=100)
    resource_id: str = Field(min_length=1, max_length=500)
    granted: bool
    reason: str = Field(min_length=1, max_length=2000)


class TraceabilityEdge(EntityBase):
    project_id: UUID
    source_type: str = Field(min_length=1, max_length=100)
    source_id: UUID
    target_type: str = Field(min_length=1, max_length=100)
    target_id: UUID
    relation: TraceabilityRelation
    evidence_ids: list[UUID] = Field(default_factory=list)
