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
    AuthorityLevel,
    DecisionStatus,
    EngineeringErrorCode,
    EvidenceType,
    IssueSeverity,
    IssueStatus,
    JobStatus,
    KnowledgeLifecycle,
    KnowledgeScope,
    KnowledgeType,
    Permission,
    ProjectStatus,
    TraceabilityRelation,
    TrustLevel,
    VerificationLevel,
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


class KnowledgeEntry(EntityBase):
    """Structured memory that references canonical claims and evidence."""

    project_id: UUID | None = None
    scope: KnowledgeScope = KnowledgeScope.PROJECT_PRIVATE
    owner_ref: str | None = Field(default=None, max_length=200)
    organization_ref: str | None = Field(default=None, max_length=200)
    task_ref: str | None = Field(default=None, max_length=200)
    knowledge_type: KnowledgeType
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(default="", max_length=12000)
    tags: list[str] = Field(default_factory=list, max_length=50)
    applicability: dict[str, object] = Field(default_factory=dict)
    claim_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    source_revision_id: UUID | None = None
    source_ref: str | None = Field(default=None, max_length=2000)
    source_version: str | None = Field(default=None, max_length=200)
    authority_level: AuthorityLevel = AuthorityLevel.T6_AI_INFERENCE
    verification_levels: list[VerificationLevel] = Field(default_factory=list)
    trust_level: TrustLevel = TrustLevel.UNTRUSTED
    lifecycle: KnowledgeLifecycle = KnowledgeLifecycle.CANDIDATE
    confidence: float = Field(default=0, ge=0, le=1)
    freshness_score: float = Field(default=1, ge=0, le=1)
    last_verified_at: datetime | None = None
    license_ref: str | None = Field(default=None, max_length=500)
    usage_policy: str | None = Field(default=None, max_length=2000)
    related_entry_ids: list[UUID] = Field(default_factory=list)
    created_by: str = Field(default="eea:m23", min_length=1, max_length=200)
    reviewed_by: str | None = Field(default=None, max_length=200)
    reviewed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_scope_context(self) -> "KnowledgeEntry":
        if (
            self.scope in {KnowledgeScope.PROJECT_PRIVATE, KnowledgeScope.TASK_ONLY}
            and self.project_id is None
        ):
            raise ValueError("project and task memory require project_id")
        if self.scope is KnowledgeScope.USER_PRIVATE and not self.owner_ref:
            raise ValueError("user-private memory requires owner_ref")
        if self.scope is KnowledgeScope.ORGANIZATION_PRIVATE and not self.organization_ref:
            raise ValueError("organization-private memory requires organization_ref")
        if self.scope is KnowledgeScope.TASK_ONLY and not self.task_ref:
            raise ValueError("task memory requires task_ref")
        if len(set(self.claim_ids)) != len(self.claim_ids):
            raise ValueError("claim_ids must not contain duplicates")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("evidence_ids must not contain duplicates")
        if len(set(self.verification_levels)) != len(self.verification_levels):
            raise ValueError("verification levels must not contain duplicates")
        return self
