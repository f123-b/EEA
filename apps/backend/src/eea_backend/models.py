"""SQLAlchemy persistence models owned by the backend adapter."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from eea_core.backup import RestoreOperationState
from eea_core.enums import (
    ArtifactStatus,
    AuthorityLevel,
    BuildStatus,
    ClaimConflictStatus,
    ClaimConflictStrategy,
    ClaimConflictType,
    ClaimLifecycle,
    ComponentAuthority,
    ComponentMaterializationStatus,
    ComponentRevisionKind,
    ComponentSourceType,
    DecisionStatus,
    DependencyKind,
    DependencyLockStatus,
    DependencyNodeStatus,
    DocumentParseStatus,
    DocumentType,
    DomainActivationStatus,
    EngineeringDimension,
    EngineeringErrorCode,
    EvidenceType,
    InvalidationPolicy,
    IssueSeverity,
    IssueStatus,
    JobStatus,
    KnowledgeLifecycle,
    KnowledgeScope,
    KnowledgeType,
    Permission,
    ProjectStatus,
    RequirementPriority,
    RequirementStatus,
    RequirementType,
    SoftwareComponentRole,
    StaticAnalysisStatus,
    TraceabilityRelation,
    TrustLevel,
)
from eea_core.hardware import (
    CapabilityVerificationStatus,
    CommissioningState,
    CommissioningStepStatus,
    EmergencyStopSource,
    EmergencyStopState,
    ResourceLockStatus,
    ResourceType,
)
from eea_core.identity import IdentityMode, ProjectRole
from eea_core.reliability import OutboxEventStatus, SideEffectStatus
from eea_core.security import PermissionTokenStatus
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def _enum_values(enum_type: type[StrEnum]) -> str:
    return ", ".join(f"'{member.value}'" for member in enum_type)


class Base(DeclarativeBase):
    """Declarative base shared by all future milestones."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class SystemMetadata(Base):
    """Small bootstrap table proving schema migrations are operational."""

    __tablename__ = "system_metadata"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CoreRecordMixin:
    """Shared columns matching ``eea_core.entities.EntityBase``."""

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(30), nullable=False, default="1.0")
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    entity_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False)


class ProjectRecord(CoreRecordMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(f"status IN ({_enum_values(ProjectStatus)})", name="status"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ArtifactRecord(CoreRecordMixin, Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(f"status IN ({_enum_values(ArtifactStatus)})", name="status"),
        UniqueConstraint(
            "project_id",
            "logical_name",
            "version_label",
            name="uq_artifacts_project_logical_version",
        ),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    logical_name: Mapped[str] = mapped_column(String(300), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(100), nullable=False)
    version_label: Mapped[str] = mapped_column(String(100), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(2000), nullable=False)
    parent_artifact_id: Mapped[str | None] = mapped_column(ForeignKey("artifacts.id"))
    dependency_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    dependency_hashes: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    source_job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"))
    generator_version: Mapped[str | None] = mapped_column(String(100))
    tool_versions: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    knowledge_snapshot: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), nullable=False)


class EvidenceRecord(CoreRecordMixin, Base):
    __tablename__ = "evidence"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(f"evidence_type IN ({_enum_values(EvidenceType)})", name="type"),
    )

    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False)
    locator: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source_uri: Mapped[str | None] = mapped_column(String(2000))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")


class IssueRecord(CoreRecordMixin, Base):
    __tablename__ = "issues"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(f"severity IN ({_enum_values(IssueSeverity)})", name="severity"),
        CheckConstraint(f"status IN ({_enum_values(IssueStatus)})", name="status"),
        UniqueConstraint("project_id", "dedupe_key", name="uq_issues_project_dedupe_key"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    claim_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    resolution: Mapped[str | None] = mapped_column(Text)
    dedupe_key: Mapped[str | None] = mapped_column(String(64), index=True)
    source_kind: Mapped[str | None] = mapped_column(String(100))
    source_ref: Mapped[str | None] = mapped_column(String(300))
    affected_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    occurrence_count: Mapped[int] = mapped_column(nullable=False, default=1)
    last_review_id: Mapped[str | None] = mapped_column(String(36))


class EngineeringDecisionRecord(CoreRecordMixin, Base):
    __tablename__ = "engineering_decisions"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(f"status IN ({_enum_values(DecisionStatus)})", name="status"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    context: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    alternatives: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)


class JobRecord(CoreRecordMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint("progress >= 0 AND progress <= 1", name="progress"),
        CheckConstraint(f"status IN ({_enum_values(JobStatus)})", name="status"),
        CheckConstraint(
            f"error_code IS NULL OR error_code IN ({_enum_values(EngineeringErrorCode)})",
            name="error_code",
        ),
    )

    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    phase: Mapped[str | None] = mapped_column(String(200))
    result_ref: Mapped[str | None] = mapped_column(String(2000))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    budget_usage: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False)
    resource_lock_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class PermissionAuditRecordModel(CoreRecordMixin, Base):
    __tablename__ = "permissions_audit"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(f"permission IN ({_enum_values(Permission)})", name="permission"),
    )

    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(500), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)


class PermissionTokenRecord(CoreRecordMixin, Base):
    __tablename__ = "permission_tokens"
    __table_args__ = (
        CheckConstraint(f"permission IN ({_enum_values(Permission)})", name="permission"),
        CheckConstraint(f"status IN ({_enum_values(PermissionTokenStatus)})", name="status"),
        Index("ix_permission_tokens_scope", "project_id", "actor_id", "permission"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(500), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class TraceabilityEdgeRecord(CoreRecordMixin, Base):
    __tablename__ = "traceability_edges"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(f"relation IN ({_enum_values(TraceabilityRelation)})", name="relation"),
        UniqueConstraint(
            "project_id",
            "source_type",
            "source_id",
            "target_type",
            "target_id",
            "relation",
            name="uq_traceability_edges_identity",
        ),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    relation: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class EngineeringDependencyEdgeRecord(CoreRecordMixin, Base):
    """M18 engineering freshness graph edge, separate from traceability."""

    __tablename__ = "engineering_dependency_edges"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(
            f"dependency_kind IN ({_enum_values(DependencyKind)})", name="dependency_kind"
        ),
        CheckConstraint(
            f"invalidation_policy IN ({_enum_values(InvalidationPolicy)})",
            name="invalidation_policy",
        ),
        CheckConstraint("length(bound_upstream_semantic_hash) = 64", name="semantic_hash_length"),
        CheckConstraint(
            "NOT (upstream_type = downstream_type AND upstream_id = downstream_id)",
            name="not_self_dependency",
        ),
        UniqueConstraint(
            "project_id",
            "upstream_type",
            "upstream_id",
            "downstream_type",
            "downstream_id",
            "dependency_kind",
            name="uq_engineering_dependency_edges_identity",
        ),
        Index(
            "ix_engineering_dependency_edges_project_upstream",
            "project_id",
            "upstream_type",
            "upstream_id",
        ),
        Index(
            "ix_engineering_dependency_edges_project_downstream",
            "project_id",
            "downstream_type",
            "downstream_id",
        ),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    upstream_type: Mapped[str] = mapped_column(String(100), nullable=False)
    upstream_id: Mapped[str] = mapped_column(String(500), nullable=False)
    downstream_type: Mapped[str] = mapped_column(String(100), nullable=False)
    downstream_id: Mapped[str] = mapped_column(String(500), nullable=False)
    dependency_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    invalidation_policy: Mapped[str] = mapped_column(String(80), nullable=False)
    bound_upstream_revision: Mapped[int] = mapped_column(nullable=False)
    bound_upstream_semantic_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class EngineeringDependencyNodeStateRecord(CoreRecordMixin, Base):
    """Current graph-owned status for a project-scoped node."""

    __tablename__ = "engineering_dependency_node_states"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(f"status IN ({_enum_values(DependencyNodeStatus)})", name="status"),
        CheckConstraint("length(observed_semantic_hash) = 64", name="semantic_hash_length"),
        UniqueConstraint(
            "project_id",
            "entity_type",
            "entity_id",
            name="uq_engineering_dependency_node_states_identity",
        ),
        Index(
            "ix_engineering_dependency_node_states_project_status",
            "project_id",
            "status",
        ),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(500), nullable=False)
    observed_revision: Mapped[int] = mapped_column(nullable=False)
    observed_semantic_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    invalidated_by: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    stale_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TestIRRecord(CoreRecordMixin, Base):
    __tablename__ = "test_irs"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        UniqueConstraint("project_id", "input_hash", name="uq_test_irs_project_input_hash"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    requirement_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    requirement_revisions: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    requirement_snapshots: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    cases: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    generator_version: Mapped[str] = mapped_column(String(100), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(100), nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class TestRunRecord(CoreRecordMixin, Base):
    __tablename__ = "test_runs"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(
            "status IN ('PASS', 'FAIL', 'UNKNOWN', 'BLOCKED', 'SKIPPED')", name="status"
        ),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    test_ir_id: Mapped[str] = mapped_column(ForeignKey("test_irs.id"), nullable=False, index=True)
    test_ir_revision: Mapped[int] = mapped_column(nullable=False)
    test_input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_revision_id: Mapped[str] = mapped_column(
        ForeignKey("source_revisions.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    case_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    tool_versions: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class ReviewRunRecord(CoreRecordMixin, Base):
    __tablename__ = "review_runs"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint("status IN ('PASS', 'FAIL', 'UNKNOWN', 'BLOCKED')", name="status"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    source_revision_id: Mapped[str] = mapped_column(
        ForeignKey("source_revisions.id"), nullable=False, index=True
    )
    policy_version: Mapped[str] = mapped_column(String(100), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    build_run_id: Mapped[str | None] = mapped_column(String(36))
    static_analysis_id: Mapped[str | None] = mapped_column(String(36))
    test_run_id: Mapped[str | None] = mapped_column(String(36))
    test_ir_id: Mapped[str | None] = mapped_column(String(36))
    test_ir_revision: Mapped[int | None] = mapped_column()
    protocol_id: Mapped[str | None] = mapped_column(String(36))
    protocol_revision: Mapped[int | None] = mapped_column()
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    issue_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class SchemaRegistryRecord(Base):
    __tablename__ = "schema_registry"

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(30), primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    json_schema: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DomainActivationRecord(CoreRecordMixin, Base):
    __tablename__ = "domain_activations"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(f"status IN ({_enum_values(DomainActivationStatus)})", name="status"),
        UniqueConstraint("project_id", "domain_id", name="uq_domain_activations_project_domain"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    domain_id: Mapped[str] = mapped_column(String(200), nullable=False)
    plugin_id: Mapped[str] = mapped_column(String(200), nullable=False)
    plugin_version: Mapped[str] = mapped_column(String(100), nullable=False)
    domain_schema_version: Mapped[str] = mapped_column(String(30), nullable=False)
    configuration_schema_version: Mapped[str] = mapped_column(String(30), nullable=False)
    configuration_schema_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_by: Mapped[str] = mapped_column(String(200), nullable=False)
    capability_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    dependency_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class DomainCompositionStateRecord(CoreRecordMixin, Base):
    """Project-scoped authoritative Domain composition snapshot."""

    __tablename__ = "domain_composition_states"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint("length(plan_hash) = 64", name="plan_hash_length"),
        UniqueConstraint("project_id", name="uq_domain_composition_states_project"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    active_domain_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    ordered_domain_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    selected_capabilities: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    capability_routes: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    dependency_edges: Mapped[list[list[str]]] = mapped_column(JSON, nullable=False)
    domain_snapshots: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    rule_order: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    generator_order: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    plan_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(200), nullable=False)


class CommissioningProfileRecord(CoreRecordMixin, Base):
    __tablename__ = "commissioning_profiles"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        UniqueConstraint("name", "version", name="uq_commissioning_profiles_name_version"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    applicable_target_types: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    applicable_domains: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    required_steps: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    required_permissions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    user_approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    safety_limits: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    required_safety_capabilities: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    watchdog_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    emergency_stop_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    safe_state_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class HardwareTargetRecord(CoreRecordMixin, Base):
    __tablename__ = "hardware_targets"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        UniqueConstraint("project_id", "name", name="uq_hardware_targets_project_name"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    identity: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    safe_state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    safety_capability: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    safety_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class TargetSafetyCapabilityRecord(CoreRecordMixin, Base):
    __tablename__ = "target_safety_capabilities"
    __table_args__ = (
        CheckConstraint(
            f"verification_status IN ({_enum_values(CapabilityVerificationStatus)})",
            name="verification_status",
        ),
        UniqueConstraint("target_id", name="uq_target_safety_capabilities_target"),
    )

    target_id: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    capability: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(30), nullable=False)


class ResourceLockRecord(CoreRecordMixin, Base):
    __tablename__ = "resource_locks"
    __table_args__ = (
        CheckConstraint(f"resource_type IN ({_enum_values(ResourceType)})", name="resource_type"),
        CheckConstraint(f"status IN ({_enum_values(ResourceLockStatus)})", name="status"),
        Index("ix_resource_locks_resource_active", "resource_type", "resource_id", "status"),
        Index(
            "uq_resource_locks_active_owner",
            "resource_type",
            "resource_id",
            unique=True,
            sqlite_where=text("status = 'ACTIVE'"),
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )

    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(500), nullable=False)
    owner_job_id: Mapped[str | None] = mapped_column(String(36))
    owner_session: Mapped[str | None] = mapped_column(String(36))
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)


class CommissioningSessionRecord(CoreRecordMixin, Base):
    __tablename__ = "commissioning_sessions"
    __table_args__ = (
        CheckConstraint(f"state IN ({_enum_values(CommissioningState)})", name="state"),
        CheckConstraint(
            f"emergency_stop_state IN ({_enum_values(EmergencyStopState)})",
            name="emergency_stop_state",
        ),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    firmware_artifact_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    firmware_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    build_run_id: Mapped[str | None] = mapped_column(String(36))
    source_revision_id: Mapped[str | None] = mapped_column(String(36))
    build_input_snapshot_id: Mapped[str | None] = mapped_column(String(36))
    hardware_identity: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    probe_identity: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    board_revision: Mapped[str | None] = mapped_column(String(100))
    commissioning_profile_id: Mapped[str] = mapped_column(
        ForeignKey("commissioning_profiles.id"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(30), nullable=False)
    current_step: Mapped[str | None] = mapped_column(String(100))
    started_by: Mapped[str] = mapped_column(String(200), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(200))
    safety_limits_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    preflight_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    emergency_stop_state: Mapped[str] = mapped_column(String(30), nullable=False)
    watchdog_state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    resource_lock_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    permission_token_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    approval_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aborted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_action_id: Mapped[str | None] = mapped_column(String(36))
    active_action_kind: Mapped[str | None] = mapped_column(String(100))
    active_action_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_action_expected_revision: Mapped[int | None] = mapped_column()
    active_action_request_hash: Mapped[str | None] = mapped_column(String(64))
    active_action_journal_id: Mapped[str | None] = mapped_column(String(36))


class SafetyLimitRecord(CoreRecordMixin, Base):
    __tablename__ = "safety_limits"
    __table_args__ = (UniqueConstraint("session_id", name="uq_safety_limits_session"),)

    session_id: Mapped[str] = mapped_column(
        ForeignKey("commissioning_sessions.id"), nullable=False, index=True
    )
    profile_id: Mapped[str] = mapped_column(ForeignKey("commissioning_profiles.id"), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    immutable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CommissioningStepResultRecord(CoreRecordMixin, Base):
    __tablename__ = "commissioning_step_results"
    __table_args__ = (
        CheckConstraint(f"status IN ({_enum_values(CommissioningStepStatus)})", name="status"),
        UniqueConstraint("session_id", "step_id", name="uq_commissioning_step_session_step"),
    )

    session_id: Mapped[str] = mapped_column(
        ForeignKey("commissioning_sessions.id"), nullable=False, index=True
    )
    step_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    measurements: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    thresholds: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    tool_version: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(100), nullable=False)
    operator: Mapped[str] = mapped_column(String(200), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text)


class EmergencyStopEventRecord(CoreRecordMixin, Base):
    __tablename__ = "emergency_stop_events"
    __table_args__ = (
        CheckConstraint(f"source IN ({_enum_values(EmergencyStopSource)})", name="source"),
        UniqueConstraint("idempotency_key", name="uq_emergency_stop_idempotency_key"),
    )

    session_id: Mapped[str] = mapped_column(
        ForeignKey("commissioning_sessions.id"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(String(4000), nullable=False)
    safe_state_attempted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    safe_state_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    quarantined_resource_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(300), nullable=False)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)


class RequirementProfileRecord(CoreRecordMixin, Base):
    __tablename__ = "requirement_profiles"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        UniqueConstraint(
            "profile_name", "profile_version", name="uq_requirement_profiles_name_version"
        ),
    )

    profile_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    profile_version: Mapped[str] = mapped_column(String(50), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    fields: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    evidence_contracts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)


class RequirementRecord(CoreRecordMixin, Base):
    __tablename__ = "requirements"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(f"requirement_type IN ({_enum_values(RequirementType)})", name="type"),
        CheckConstraint(f"priority IN ({_enum_values(RequirementPriority)})", name="priority"),
        CheckConstraint(f"status IN ({_enum_values(RequirementStatus)})", name="status"),
        UniqueConstraint("project_id", "code", name="uq_requirements_project_code"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    requirement_type: Mapped[str] = mapped_column(String(30), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source_evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)


class RequirementAnalysisRecord(CoreRecordMixin, Base):
    __tablename__ = "requirement_analyses"
    __table_args__ = (CheckConstraint("revision >= 1", name="revision_positive"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    profile_name: Mapped[str] = mapped_column(String(120), nullable=False)
    profile_version: Mapped[str] = mapped_column(String(50), nullable=False)
    requirements: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    field_observations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    claims: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    follow_up_questions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    completeness: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    requirement_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    claim_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class PinPlanRecord(CoreRecordMixin, Base):
    __tablename__ = "pin_plans"
    __table_args__ = (CheckConstraint("revision >= 1", name="revision_positive"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    analysis_id: Mapped[str | None] = mapped_column(
        ForeignKey("requirement_analyses.id"), index=True
    )
    device_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    package: Mapped[str | None] = mapped_column(String(100))
    requirements: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)


class PinAssignmentRecord(CoreRecordMixin, Base):
    __tablename__ = "pin_assignments"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint("score >= 0 AND score <= 1", name="score_range"),
        UniqueConstraint("plan_id", "pin_name", name="uq_pin_assignments_plan_pin"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("pin_plans.id"), nullable=False, index=True)
    requirement_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    device_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    package: Mapped[str | None] = mapped_column(String(100))
    pin_name: Mapped[str] = mapped_column(String(50), nullable=False)
    function: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    claim_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class PinLockRecord(CoreRecordMixin, Base):
    __tablename__ = "pin_locks"
    __table_args__ = (CheckConstraint("revision >= 1", name="revision_positive"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    assignment_id: Mapped[str] = mapped_column(
        ForeignKey("pin_assignments.id"), nullable=False, index=True
    )
    locked_by: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    released_by: Mapped[str | None] = mapped_column(String(200))
    released_reason: Mapped[str | None] = mapped_column(Text)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PinRuleResultRecord(CoreRecordMixin, Base):
    __tablename__ = "pin_rule_results"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(
            "stage IN ("
            "'PRE_GENERATION', 'POST_GENERATION', 'PRE_TOOL', 'POST_TOOL', 'RELEASE_GATE'"
            ")",
            name="stage",
        ),
        CheckConstraint(
            "status IN ('PASS', 'FAIL', 'NOT_APPLICABLE', 'UNKNOWN')",
            name="status",
        ),
        CheckConstraint(f"severity IN ({_enum_values(IssueSeverity)})", name="severity"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("pin_plans.id"), nullable=False, index=True)
    rule_id: Mapped[str] = mapped_column(String(200), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(50), nullable=False)
    stage: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    affected_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    measured: Mapped[object | None] = mapped_column(JSON)
    threshold: Mapped[object | None] = mapped_column(JSON)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    claim_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)


class SystemArchitectureRecord(CoreRecordMixin, Base):
    __tablename__ = "system_architectures"
    __table_args__ = (CheckConstraint("revision >= 1", name="revision_positive"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    pin_plan_id: Mapped[str] = mapped_column(ForeignKey("pin_plans.id"), nullable=False, index=True)
    pin_plan_revision: Mapped[int] = mapped_column(nullable=False)
    blocks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    interfaces: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    decisions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    requirement_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source_artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    pin_assignment_revisions: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)


class HardwareIRRecord(CoreRecordMixin, Base):
    __tablename__ = "hardware_irs"
    __table_args__ = (CheckConstraint("revision >= 1", name="revision_positive"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    architecture_id: Mapped[str] = mapped_column(
        ForeignKey("system_architectures.id"), nullable=False, index=True
    )
    pin_plan_id: Mapped[str] = mapped_column(ForeignKey("pin_plans.id"), nullable=False, index=True)
    pin_plan_revision: Mapped[int] = mapped_column(nullable=False)
    modules: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    device_instances: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    power_domains: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    interfaces: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    pin_requirements: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    constraints: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    requirement_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    pin_assignment_revisions: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)


class CircuitRecord(CoreRecordMixin, Base):
    __tablename__ = "circuits"
    __table_args__ = (CheckConstraint("revision >= 1", name="revision_positive"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    hardware_ir_id: Mapped[str] = mapped_column(
        ForeignKey("hardware_irs.id"), nullable=False, index=True
    )
    hardware_ir_revision: Mapped[int] = mapped_column(nullable=False)
    components: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    nets: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    power_nets: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    constraints: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    requirement_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    pin_assignment_revisions: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)


class CircuitRuleResultRecord(CoreRecordMixin, Base):
    __tablename__ = "circuit_rule_results"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(
            "stage IN ('PRE_GENERATION', 'POST_GENERATION', 'PRE_TOOL', 'POST_TOOL', "
            "'RELEASE_GATE')",
            name="stage",
        ),
        CheckConstraint(
            "status IN ('PASS', 'FAIL', 'NOT_APPLICABLE', 'UNKNOWN')",
            name="status",
        ),
        CheckConstraint(f"severity IN ({_enum_values(IssueSeverity)})", name="severity"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    circuit_id: Mapped[str] = mapped_column(ForeignKey("circuits.id"), nullable=False, index=True)
    rule_id: Mapped[str] = mapped_column(String(200), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(50), nullable=False)
    stage: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    affected_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    measured: Mapped[object | None] = mapped_column(JSON)
    threshold: Mapped[object | None] = mapped_column(JSON)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    claim_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)


class SchematicArtifactRecord(CoreRecordMixin, Base):
    __tablename__ = "schematic_artifacts"
    __table_args__ = (CheckConstraint("revision >= 1", name="revision_positive"),)

    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifacts.id"), nullable=False, unique=True
    )
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    circuit_id: Mapped[str] = mapped_column(ForeignKey("circuits.id"), nullable=False, index=True)
    circuit_revision: Mapped[int] = mapped_column(nullable=False)
    hardware_ir_id: Mapped[str] = mapped_column(
        ForeignKey("hardware_irs.id"), nullable=False, index=True
    )
    hardware_ir_revision: Mapped[int] = mapped_column(nullable=False)
    format: Mapped[str] = mapped_column(String(50), nullable=False)
    components: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    nets: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    power_nets: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    constraints: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    netlist_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    preflight_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    requirement_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    pin_assignment_revisions: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)


class ErcReportRecord(CoreRecordMixin, Base):
    __tablename__ = "erc_reports"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint("status IN ('PASS', 'FAIL', 'UNKNOWN')", name="status"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    schematic_id: Mapped[str] = mapped_column(
        ForeignKey("schematic_artifacts.id"), nullable=False, index=True
    )
    schematic_revision: Mapped[int] = mapped_column(nullable=False)
    circuit_id: Mapped[str] = mapped_column(ForeignKey("circuits.id"), nullable=False, index=True)
    circuit_revision: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(100))
    tool_version: Mapped[str | None] = mapped_column(String(100))
    executed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    source_revision_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)


class MCUConfigRecord(CoreRecordMixin, Base):
    __tablename__ = "mcu_configs"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(f"status IN ({_enum_values(ArtifactStatus)})", name="status"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    hardware_ir_id: Mapped[str] = mapped_column(
        ForeignKey("hardware_irs.id"), nullable=False, index=True
    )
    hardware_ir_revision: Mapped[int] = mapped_column(nullable=False)
    circuit_id: Mapped[str] = mapped_column(ForeignKey("circuits.id"), nullable=False, index=True)
    circuit_revision: Mapped[int] = mapped_column(nullable=False)
    schematic_id: Mapped[str] = mapped_column(
        ForeignKey("schematic_artifacts.id"), nullable=False, index=True
    )
    schematic_revision: Mapped[int] = mapped_column(nullable=False)
    device_instance_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    clock: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    gpio: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    peripherals: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    dma: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    interrupts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    memory: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    debug: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    capability_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    requirement_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    pin_assignment_revisions: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)


class MCUConfigRuleResultRecord(CoreRecordMixin, Base):
    __tablename__ = "mcu_config_rule_results"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(
            "stage IN ('PRE_GENERATION', 'POST_GENERATION', 'PRE_TOOL', 'POST_TOOL', "
            "'RELEASE_GATE')",
            name="stage",
        ),
        CheckConstraint(
            "status IN ('PASS', 'FAIL', 'NOT_APPLICABLE', 'UNKNOWN')",
            name="status",
        ),
        CheckConstraint(f"severity IN ({_enum_values(IssueSeverity)})", name="severity"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    mcu_config_id: Mapped[str] = mapped_column(
        ForeignKey("mcu_configs.id"), nullable=False, index=True
    )
    rule_id: Mapped[str] = mapped_column(String(200), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(50), nullable=False)
    stage: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    affected_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    measured: Mapped[object | None] = mapped_column(JSON)
    threshold: Mapped[object | None] = mapped_column(JSON)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    claim_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)


class SourceRevisionRecord(CoreRecordMixin, Base):
    __tablename__ = "source_revisions"
    __table_args__ = (CheckConstraint("revision >= 1", name="revision_positive"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    repository_id: Mapped[str] = mapped_column(String(300), nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(String(100))
    tree_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dirty: Mapped[bool] = mapped_column(Boolean, nullable=False)
    base_commit: Mapped[str | None] = mapped_column(String(100))
    workspace_revision: Mapped[int] = mapped_column(nullable=False)
    source_manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_manifest: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)


class SourceWorkspaceRecord(CoreRecordMixin, Base):
    """Project-scoped workspace metadata; source bytes remain on disk."""

    __tablename__ = "source_workspaces"
    __table_args__ = (
        CheckConstraint("workspace_revision >= 0", name="workspace_revision_non_negative"),
        UniqueConstraint("project_id", name="uq_source_workspaces_project"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    repository_id: Mapped[str] = mapped_column(String(300), nullable=False)
    root_path: Mapped[str] = mapped_column(String(2000), nullable=False)
    current_source_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_revisions.id"), nullable=True, index=True
    )
    workspace_revision: Mapped[int] = mapped_column(nullable=False, default=0)
    base_commit: Mapped[str | None] = mapped_column(String(100))
    last_reconciled_manifest_hash: Mapped[str | None] = mapped_column(String(64))
    active_mutation_id: Mapped[str | None] = mapped_column(String(36), index=True)
    active_mutation_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_mutation_expected_revision: Mapped[int | None] = mapped_column()


class ImportSessionRecord(CoreRecordMixin, Base):
    """Durable M22 import session; findings remain candidates until reviewed."""

    __tablename__ = "import_sessions"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('LOCAL_FOLDER', 'GIT_REPOSITORY', 'ARCHIVE')",
            name="source_type",
        ),
        CheckConstraint(
            "status IN ('CREATED', 'SCANNED', 'REVIEWED', 'WORKSPACE_CREATED', 'FAILED')",
            name="status",
        ),
        CheckConstraint("scan_revision >= 0", name="scan_revision_non_negative"),
    )

    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True, index=True
    )
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_locator: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    requested_ref: Mapped[str | None] = mapped_column(String(300))
    resolved_commit: Mapped[str | None] = mapped_column(String(100))
    staging_path: Mapped[str] = mapped_column(String(2000), nullable=False)
    workspace_path: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    scan_revision: Mapped[int] = mapped_column(nullable=False, default=0)
    source_manifest_hash: Mapped[str | None] = mapped_column(String(64))
    file_manifest: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    findings: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    issues: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    scan_result: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeEntryRecord(CoreRecordMixin, Base):
    """M23 structured memory; canonical claims and evidence stay referenced, not copied."""

    __tablename__ = "knowledge_entries"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(f"scope IN ({_enum_values(KnowledgeScope)})", name="scope"),
        CheckConstraint(
            f"knowledge_type IN ({_enum_values(KnowledgeType)})", name="knowledge_type"
        ),
        CheckConstraint(
            f"authority_level IN ({_enum_values(AuthorityLevel)})", name="authority_level"
        ),
        CheckConstraint(f"trust_level IN ({_enum_values(TrustLevel)})", name="trust_level"),
        CheckConstraint(f"lifecycle IN ({_enum_values(KnowledgeLifecycle)})", name="lifecycle"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint("freshness_score >= 0 AND freshness_score <= 1", name="freshness_range"),
        CheckConstraint(
            "scope NOT IN ('PROJECT_PRIVATE', 'TASK_ONLY') OR project_id IS NOT NULL",
            name="project_scope_requires_project",
        ),
        CheckConstraint(
            "scope <> 'USER_PRIVATE' OR owner_ref IS NOT NULL", name="user_scope_requires_owner"
        ),
        CheckConstraint(
            "scope <> 'ORGANIZATION_PRIVATE' OR organization_ref IS NOT NULL",
            name="organization_scope_requires_organization",
        ),
        CheckConstraint(
            "scope <> 'TASK_ONLY' OR task_ref IS NOT NULL", name="task_scope_requires_task"
        ),
        Index("ix_knowledge_entries_scope_lifecycle", "scope", "lifecycle"),
    )

    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True, index=True
    )
    scope: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    owner_ref: Mapped[str | None] = mapped_column(String(200))
    organization_ref: Mapped[str | None] = mapped_column(String(200))
    task_ref: Mapped[str | None] = mapped_column(String(200))
    knowledge_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    applicability: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    claim_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_revisions.id"), nullable=True, index=True
    )
    source_ref: Mapped[str | None] = mapped_column(String(2000))
    source_version: Mapped[str | None] = mapped_column(String(200))
    authority_level: Mapped[str] = mapped_column(String(30), nullable=False)
    verification_levels: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    trust_level: Mapped[str] = mapped_column(String(20), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    freshness_score: Mapped[float] = mapped_column(Float, nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    license_ref: Mapped[str | None] = mapped_column(String(500))
    usage_policy: Mapped[str | None] = mapped_column(String(2000))
    related_entry_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(200))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeRecallAuditRecord(CoreRecordMixin, Base):
    """Append-only audit record for explicit, scope-filtered memory recall."""

    __tablename__ = "knowledge_recall_audits"
    __table_args__ = (CheckConstraint("revision >= 1", name="revision_positive"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    actor_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    query: Mapped[str] = mapped_column(String(2000), nullable=False)
    scope_context: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    result_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    result_count: Mapped[int] = mapped_column(nullable=False)
    request_id: Mapped[str] = mapped_column(String(200), nullable=False)


class PatchProposalRecord(CoreRecordMixin, Base):
    """Review metadata for a proposed source mutation."""

    __tablename__ = "patch_proposals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'READY', 'APPLIED', 'STALE', 'REJECTED', 'FAILED')",
            name="status",
        ),
        CheckConstraint(
            "base_workspace_revision >= 0", name="base_workspace_revision_non_negative"
        ),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    base_source_revision_id: Mapped[str] = mapped_column(
        ForeignKey("source_revisions.id"), nullable=False, index=True
    )
    base_workspace_revision: Mapped[int] = mapped_column(nullable=False)
    affected_files: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    expected_file_hashes: Mapped[dict[str, str | None]] = mapped_column(JSON, nullable=False)
    patch: Mapped[str | None] = mapped_column(Text)
    structured_edits: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    expected_impact: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    required_builds: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    required_tests: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(4000))


class GeneratedSourceOwnershipRecord(CoreRecordMixin, Base):
    """Hash and generator metadata for generated-owned workspace paths."""

    __tablename__ = "generated_source_ownership"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'DIVERGED')", name="status"),
        UniqueConstraint("project_id", "path", name="uq_generated_source_ownership_path"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    generator_id: Mapped[str] = mapped_column(String(200), nullable=False)
    generator_version: Mapped[str] = mapped_column(String(100), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)


class SourceMutationJournalRecord(CoreRecordMixin, Base):
    """Durable marker spanning a filesystem replace and SQL finalization."""

    __tablename__ = "source_mutation_journal"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PREPARED', 'COMPLETED', 'ROLLED_BACK', 'RECOVERED', 'RECOVERY_REQUIRED')",
            name="status",
        ),
        CheckConstraint(
            "expected_workspace_revision >= 0", name="expected_workspace_revision_non_negative"
        ),
        UniqueConstraint("operation_id", name="uq_source_mutation_journal_operation"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    operation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    proposal_id: Mapped[str | None] = mapped_column(
        ForeignKey("patch_proposals.id"), nullable=True, index=True
    )
    previous_source_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_revisions.id"), nullable=True, index=True
    )
    expected_workspace_revision: Mapped[int] = mapped_column(nullable=False)
    affected_files: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    before_manifest: Mapped[dict[str, str | None]] = mapped_column(JSON, nullable=False)
    after_manifest: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    recovery_bundle_path: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(4000))


class FirmwareRecord(CoreRecordMixin, Base):
    __tablename__ = "firmware_irs"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(f"status IN ({_enum_values(ArtifactStatus)})", name="status"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    mcu_config_id: Mapped[str] = mapped_column(
        ForeignKey("mcu_configs.id"), nullable=False, index=True
    )
    mcu_config_revision: Mapped[int] = mapped_column(nullable=False)
    hardware_ir_id: Mapped[str] = mapped_column(
        ForeignKey("hardware_irs.id"), nullable=False, index=True
    )
    hardware_ir_revision: Mapped[int] = mapped_column(nullable=False)
    circuit_id: Mapped[str] = mapped_column(ForeignKey("circuits.id"), nullable=False, index=True)
    circuit_revision: Mapped[int] = mapped_column(nullable=False)
    schematic_id: Mapped[str] = mapped_column(
        ForeignKey("schematic_artifacts.id"), nullable=False, index=True
    )
    schematic_revision: Mapped[int] = mapped_column(nullable=False)
    source_revision_id: Mapped[str] = mapped_column(
        ForeignKey("source_revisions.id"), nullable=False, index=True
    )
    dependency_lock_id: Mapped[str | None] = mapped_column(
        ForeignKey("dependency_locks.id"), index=True
    )
    dependency_lock_hash: Mapped[str | None] = mapped_column(String(64))
    component_refs: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    platform_adapter_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    platform_adapter_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    layers: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    modules: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    tasks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    interrupts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    shared_resources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    startup: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    clock_tree: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    peripheral_drivers: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    memory_layout: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    bsp: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    build_target: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    rule_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    requirement_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)


class ProtocolRecord(Base):
    """Revision history for the project-scoped M16 ProtocolIR."""

    __tablename__ = "protocols"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint("status IN ('CURRENT', 'STALE')", name="status"),
        UniqueConstraint("id", "revision", name="uq_protocols_id_revision"),
    )

    record_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    schema_version: Mapped[str] = mapped_column(String(30), nullable=False)
    revision: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    entity_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    version_label: Mapped[str] = mapped_column(String(100), nullable=False)
    transports: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    messages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    requirement_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)


class GeneratedProtocolOutputRecord(CoreRecordMixin, Base):
    """Durable generated ProtocolIR fan-out output used by M18 freshness."""

    __tablename__ = "generated_protocol_outputs"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        UniqueConstraint("project_id", "protocol_id", "target", name="uq_protocol_output_target"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    protocol_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    protocol_revision: Mapped[int] = mapped_column(nullable=False)
    target: Mapped[str] = mapped_column(String(40), nullable=False)
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    generator_version: Mapped[str] = mapped_column(String(100), nullable=False)


class FirmwareSourceFileRecord(CoreRecordMixin, Base):
    __tablename__ = "firmware_source_files"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        UniqueConstraint("firmware_id", "path", name="uq_firmware_source_files_path"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    firmware_id: Mapped[str] = mapped_column(
        ForeignKey("firmware_irs.id"), nullable=False, index=True
    )
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_owned: Mapped[bool] = mapped_column(Boolean, nullable=False)
    generator_version: Mapped[str] = mapped_column(String(100), nullable=False)


class BuildInputSnapshotRecord(CoreRecordMixin, Base):
    __tablename__ = "build_input_snapshots"
    __table_args__ = (CheckConstraint("revision >= 1", name="revision_positive"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    source_revision_id: Mapped[str] = mapped_column(
        ForeignKey("source_revisions.id"), nullable=False, index=True
    )
    tracked_file_manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    allowed_untracked_input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    submodule_commit_map: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    build_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    toolchain_id: Mapped[str] = mapped_column(String(200), nullable=False)
    toolchain_version: Mapped[str] = mapped_column(String(200), nullable=False)
    environment_profile_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dependency_lock_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    component_manifest_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    toolchain_manifest_hash: Mapped[str | None] = mapped_column(String(64))
    build_profile: Mapped[str | None] = mapped_column(String(30), nullable=True)
    build_input_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class FirmwareStaticAnalysisRecord(CoreRecordMixin, Base):
    __tablename__ = "firmware_static_analyses"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(f"status IN ({_enum_values(StaticAnalysisStatus)})", name="status"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    firmware_id: Mapped[str] = mapped_column(
        ForeignKey("firmware_irs.id"), nullable=False, index=True
    )
    firmware_revision: Mapped[int] = mapped_column(nullable=False)
    source_revision_id: Mapped[str] = mapped_column(
        ForeignKey("source_revisions.id"), nullable=False, index=True
    )
    build_input_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("build_input_snapshots.id"), nullable=True, index=True
    )
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ruleset_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    tool_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)


class FirmwareStaticAnalysisResultRecord(CoreRecordMixin, Base):
    __tablename__ = "firmware_static_analysis_results"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(
            "stage IN ('PRE_GENERATION', 'POST_GENERATION', 'PRE_TOOL', 'POST_TOOL', "
            "'RELEASE_GATE')",
            name="stage",
        ),
        CheckConstraint(
            "status IN ('PASS', 'FAIL', 'NOT_APPLICABLE', 'UNKNOWN')",
            name="status",
        ),
        CheckConstraint(f"severity IN ({_enum_values(IssueSeverity)})", name="severity"),
        UniqueConstraint("analysis_id", "rule_id", name="uq_static_analysis_rule"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("firmware_static_analyses.id"), nullable=False, index=True
    )
    rule_id: Mapped[str] = mapped_column(String(200), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(50), nullable=False)
    stage: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    affected_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    measured: Mapped[object | None] = mapped_column(JSON)
    threshold: Mapped[object | None] = mapped_column(JSON)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    claim_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)


class BuildRunRecord(CoreRecordMixin, Base):
    __tablename__ = "build_runs"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(f"status IN ({_enum_values(BuildStatus)})", name="status"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    firmware_id: Mapped[str] = mapped_column(
        ForeignKey("firmware_irs.id"), nullable=False, index=True
    )
    firmware_revision: Mapped[int] = mapped_column(nullable=False)
    source_revision_id: Mapped[str] = mapped_column(
        ForeignKey("source_revisions.id"), nullable=False, index=True
    )
    build_input_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("build_input_snapshots.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    profile: Mapped[str | None] = mapped_column(String(30), nullable=True)
    toolchain_id: Mapped[str] = mapped_column(String(200), nullable=False)
    toolchain_version: Mapped[str] = mapped_column(String(200), nullable=False)
    environment_profile_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    build_input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    command: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    diagnostics: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    stdout: Mapped[str] = mapped_column(Text, nullable=False)
    stderr: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_hash: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(80))
    duration_ms: Mapped[int] = mapped_column(nullable=False)


class SoftwareComponentRecord(CoreRecordMixin, Base):
    __tablename__ = "software_components"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(f"authority IN ({_enum_values(ComponentAuthority)})", name="authority"),
        CheckConstraint(f"role IN ({_enum_values(SoftwareComponentRole)})", name="role"),
        CheckConstraint(
            f"source_type IN ({_enum_values(ComponentSourceType)})", name="source_type"
        ),
        UniqueConstraint("component_key", name="uq_software_components_component_key"),
    )

    component_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    vendor: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    authority: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_uri: Mapped[str | None] = mapped_column(String(2000))
    capabilities: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    compatibility: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    license_expression: Mapped[str | None] = mapped_column(String(200))
    license_text_hash: Mapped[str | None] = mapped_column(String(64))
    dependencies: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    production_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reference_only: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ComponentReleaseRecord(CoreRecordMixin, Base):
    __tablename__ = "software_component_releases"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(
            f"revision_kind IN ({_enum_values(ComponentRevisionKind)})", name="revision_kind"
        ),
        UniqueConstraint("component_id", "source_revision", name="uq_component_release_revision"),
    )

    component_id: Mapped[str] = mapped_column(
        ForeignKey("software_components.id"), nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    revision_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(200), nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    files: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    submodule_commit_map: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    source_uri: Mapped[str | None] = mapped_column(String(2000))
    yanked: Mapped[bool] = mapped_column(Boolean, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False)


class DependencyLockRecord(CoreRecordMixin, Base):
    __tablename__ = "dependency_locks"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(f"status IN ({_enum_values(DependencyLockStatus)})", name="status"),
        UniqueConstraint("project_id", "lock_hash", name="uq_dependency_locks_project_hash"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    mcu_config_id: Mapped[str] = mapped_column(
        ForeignKey("mcu_configs.id"), nullable=False, index=True
    )
    mcu_config_revision: Mapped[int] = mapped_column(nullable=False)
    requirements: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    resolved_components: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    resolution_policy_version: Mapped[str] = mapped_column(String(100), nullable=False)
    resolver_version: Mapped[str] = mapped_column(String(100), nullable=False)
    lock_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)


class DependencyLockComponentRecord(CoreRecordMixin, Base):
    __tablename__ = "dependency_lock_components"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        UniqueConstraint("dependency_lock_id", "component_key", name="uq_lock_component_key"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    dependency_lock_id: Mapped[str] = mapped_column(
        ForeignKey("dependency_locks.id"), nullable=False, index=True
    )
    component_id: Mapped[str] = mapped_column(
        ForeignKey("software_components.id"), nullable=False, index=True
    )
    release_id: Mapped[str] = mapped_column(
        ForeignKey("software_component_releases.id"), nullable=False, index=True
    )
    component_key: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    component_revision: Mapped[str] = mapped_column(String(200), nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class ComponentMaterializationRecord(CoreRecordMixin, Base):
    __tablename__ = "component_materializations"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(
            f"status IN ({_enum_values(ComponentMaterializationStatus)})", name="status"
        ),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    component_id: Mapped[str] = mapped_column(
        ForeignKey("software_components.id"), nullable=False, index=True
    )
    release_id: Mapped[str] = mapped_column(
        ForeignKey("software_component_releases.id"), nullable=False, index=True
    )
    owner: Mapped[str] = mapped_column(String(30), nullable=False)
    cache_key: Mapped[str] = mapped_column(String(200), nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(2000), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    network_used: Mapped[bool] = mapped_column(Boolean, nullable=False)


class PromptDefinitionRecord(CoreRecordMixin, Base):
    __tablename__ = "prompt_definitions"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint("max_steps >= 1", name="max_steps_positive"),
        UniqueConstraint("name", "prompt_version", name="uq_prompt_definitions_name_version"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    system_template: Mapped[str] = mapped_column(Text, nullable=False)
    user_template: Mapped[str] = mapped_column(Text, nullable=False)
    model_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    allowed_tools: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evidence_requirements: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    fallback: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    max_steps: Mapped[int] = mapped_column(nullable=False)
    budget_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)


class AIUsageRecordModel(CoreRecordMixin, Base):
    __tablename__ = "ai_usage_records"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint("input_tokens >= 0", name="input_tokens_non_negative"),
        CheckConstraint("output_tokens >= 0", name="output_tokens_non_negative"),
        CheckConstraint("total_tokens >= input_tokens + output_tokens", name="total_tokens_valid"),
        CheckConstraint("llm_cost >= 0", name="llm_cost_non_negative"),
        CheckConstraint("duration_ms >= 0", name="duration_ms_non_negative"),
        CheckConstraint(
            f"error_code IS NULL OR error_code IN ({_enum_values(EngineeringErrorCode)})",
            name="error_code",
        ),
    )

    request_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    prompt_definition_id: Mapped[str] = mapped_column(
        ForeignKey("prompt_definitions.id"), nullable=False, index=True
    )
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), index=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    input_tokens: Mapped[int] = mapped_column(nullable=False)
    output_tokens: Mapped[int] = mapped_column(nullable=False)
    total_tokens: Mapped[int] = mapped_column(nullable=False)
    llm_cost: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    duration_ms: Mapped[int] = mapped_column(nullable=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))


class ClaimPredicateDefinitionRecord(CoreRecordMixin, Base):
    __tablename__ = "claim_predicate_definitions"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(
            f"conflict_strategy IN ({_enum_values(ClaimConflictStrategy)})",
            name="conflict_strategy",
        ),
        CheckConstraint(
            f"unit_dimension IS NULL OR unit_dimension IN ({_enum_values(EngineeringDimension)})",
            name="unit_dimension",
        ),
        UniqueConstraint(
            "predicate", "schema_version", name="uq_claim_predicates_predicate_schema"
        ),
    )

    predicate: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    value_schema_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    applicability_schema_ref: Mapped[str | None] = mapped_column(String(200))
    unit_dimension: Mapped[str | None] = mapped_column(String(40))
    conflict_strategy: Mapped[str] = mapped_column(String(40), nullable=False)
    validator_ref: Mapped[str | None] = mapped_column(String(200))


class EngineeringClaimRecord(CoreRecordMixin, Base):
    __tablename__ = "engineering_claims"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint(
            "source_priority >= 0 AND source_priority <= 1000", name="source_priority_range"
        ),
        CheckConstraint(f"lifecycle IN ({_enum_values(ClaimLifecycle)})", name="lifecycle"),
    )

    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    subject_ref: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    predicate: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    value_schema_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    value_json: Mapped[object] = mapped_column("value", JSON, nullable=False)
    applicability: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    verification_levels: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source_priority: Mapped[int] = mapped_column(nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(200))
    lifecycle: Mapped[str] = mapped_column(String(40), nullable=False)


class ClaimConflictRecord(CoreRecordMixin, Base):
    __tablename__ = "claim_conflicts"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint("claim_a_id <> claim_b_id", name="distinct_claims"),
        CheckConstraint(
            f"conflict_type IN ({_enum_values(ClaimConflictType)})", name="conflict_type"
        ),
        CheckConstraint(f"status IN ({_enum_values(ClaimConflictStatus)})", name="status"),
    )

    claim_a_id: Mapped[str] = mapped_column(ForeignKey("engineering_claims.id"), nullable=False)
    claim_b_id: Mapped[str] = mapped_column(ForeignKey("engineering_claims.id"), nullable=False)
    conflict_type: Mapped[str] = mapped_column(String(40), nullable=False)
    overlapping_applicability: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    resolver: Mapped[str] = mapped_column(String(100), nullable=False)
    resolution: Mapped[str | None] = mapped_column(Text)
    selected_claim_id: Mapped[str | None] = mapped_column(ForeignKey("engineering_claims.id"))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)


class DocumentRecord(CoreRecordMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(f"document_type IN ({_enum_values(DocumentType)})", name="document_type"),
        CheckConstraint(
            f"parse_status IN ({_enum_values(DocumentParseStatus)})", name="parse_status"
        ),
    )

    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    document_type: Mapped[str] = mapped_column(String(40), nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(200))
    product: Mapped[str | None] = mapped_column(String(200))
    version_label: Mapped[str | None] = mapped_column(String(100))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_uri: Mapped[str] = mapped_column(String(2000), nullable=False)
    parse_status: Mapped[str] = mapped_column(String(30), nullable=False)
    parse_error: Mapped[str | None] = mapped_column(Text)


class DocumentIRRecord(CoreRecordMixin, Base):
    __tablename__ = "document_irs"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        UniqueConstraint("document_id", name="uq_document_irs_document_id"),
    )

    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    parser: Mapped[str] = mapped_column(String(200), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(100), nullable=False)
    pages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    tables: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    figures: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    extracted_claim_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class OutboxEventRecord(Base):
    """Durable event envelope used for at-least-once delivery."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint("attempt_count >= 0", name="attempt_count_non_negative"),
        CheckConstraint("max_attempts >= 1", name="max_attempts_positive"),
        CheckConstraint("length(payload_hash) = 64", name="payload_hash_length"),
        CheckConstraint(f"status IN ({_enum_values(OutboxEventStatus)})", name="status"),
        UniqueConstraint("event_key", name="uq_outbox_events_event_key"),
        Index("ix_outbox_events_status_available", "status", "available_at"),
        Index("ix_outbox_events_status_lease", "status", "lease_expires_at"),
        Index("ix_outbox_events_project_status", "project_id", "status"),
        Index("ix_outbox_events_event_type", "event_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(30), nullable=False)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(200), nullable=False)
    event_version: Mapped[int] = mapped_column(nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(500), nullable=False)
    aggregate_revision: Mapped[int | None] = mapped_column()
    event_key: Mapped[str] = mapped_column(String(700), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(36))
    causation_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(nullable=False, default=8)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(200))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revision: Mapped[int] = mapped_column(nullable=False, default=1)


class ProcessedEventRecord(Base):
    """Consumer-level idempotency marker."""

    __tablename__ = "processed_events"
    __table_args__ = (
        CheckConstraint("length(event_payload_hash) = 64", name="event_payload_hash_length"),
        CheckConstraint(
            "result_hash IS NULL OR length(result_hash) = 64", name="result_hash_length"
        ),
        UniqueConstraint("event_id", "consumer_id", name="uq_processed_events_identity"),
        Index("ix_processed_events_consumer_processed", "consumer_id", "processed_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("outbox_events.id"), nullable=False)
    consumer_id: Mapped[str] = mapped_column(String(200), nullable=False)
    event_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result_ref: Mapped[str | None] = mapped_column(String(2000))
    result_hash: Mapped[str | None] = mapped_column(String(64))


class SideEffectJournalRecord(Base):
    """Effect-level idempotency and unknown-outcome reconciliation marker."""

    __tablename__ = "side_effect_journal"
    __table_args__ = (
        CheckConstraint("length(request_hash) = 64", name="request_hash_length"),
        CheckConstraint(
            "result_hash IS NULL OR length(result_hash) = 64", name="result_hash_length"
        ),
        CheckConstraint(f"status IN ({_enum_values(SideEffectStatus)})", name="status"),
        UniqueConstraint(
            "event_id", "consumer_id", "effect_key", name="uq_side_effect_journal_identity"
        ),
        Index("ix_side_effect_journal_status_event", "status", "event_id", "consumer_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("outbox_events.id"), nullable=False)
    consumer_id: Mapped[str] = mapped_column(String(200), nullable=False)
    effect_key: Mapped[str] = mapped_column(String(300), nullable=False)
    effect_type: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0)
    result_ref: Mapped[str | None] = mapped_column(String(2000))
    result_hash: Mapped[str | None] = mapped_column(String(64))
    last_error: Mapped[str | None] = mapped_column(Text)
    prepared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RestoreOperationRecord(Base):
    """Durable bridge for a restore spanning SQL and filesystem activation."""

    __tablename__ = "restore_operations"
    __table_args__ = (
        CheckConstraint(
            f"state IN ({_enum_values(RestoreOperationState)})", name="restore_operation_state"
        ),
        CheckConstraint("length(manifest_hash) = 64", name="restore_manifest_hash_length"),
        Index("ix_restore_operations_state_updated", "state", "updated_at"),
        Index("ix_restore_operations_project", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False)
    staging_path: Mapped[str] = mapped_column(String(2000), nullable=False)
    destination_path: Mapped[str] = mapped_column(String(2000), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source_revision_id: Mapped[str | None] = mapped_column(String(36))
    source_revision_hash: Mapped[str | None] = mapped_column(String(64))
    operation_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revision: Mapped[int] = mapped_column(nullable=False, default=1)


class IdentityUserRecord(CoreRecordMixin, Base):
    """Stable user identity; local mode uses a deterministic actor, never free text."""

    __tablename__ = "identity_users"
    __table_args__ = (
        CheckConstraint(f"mode IN ({_enum_values(IdentityMode)})", name="mode"),
        Index("uq_identity_users_id_m18er", "id", unique=True),
        UniqueConstraint("stable_actor_id", name="uq_identity_users_stable_actor_id"),
    )

    stable_actor_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    mode: Mapped[str] = mapped_column(String(40), nullable=False)


class OrganizationRecord(CoreRecordMixin, Base):
    __tablename__ = "organizations"

    __table_args__ = (Index("uq_organizations_id_m18er", "id", unique=True),)

    stable_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)


class MembershipRecord(CoreRecordMixin, Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        CheckConstraint(f"role IN ({_enum_values(ProjectRole)})", name="role"),
        UniqueConstraint("organization_id", "user_id", name="uq_membership_organization_user"),
    )

    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("identity_users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)


class ProjectRoleAssignmentRecord(CoreRecordMixin, Base):
    __tablename__ = "project_role_assignments"
    __table_args__ = (
        CheckConstraint(f"role IN ({_enum_values(ProjectRole)})", name="role"),
        UniqueConstraint("project_id", "user_id", name="uq_project_role_project_user"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("identity_users.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(40), nullable=False)


class BackupManifestRecord(Base):
    __tablename__ = "backup_manifests"
    __table_args__ = (
        CheckConstraint("length(manifest_hash) = 64", name="manifest_hash_length"),
        UniqueConstraint("manifest_hash", name="uq_backup_manifests_manifest_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    manifest_version: Mapped[str] = mapped_column(String(30), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(50), nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hashes: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
