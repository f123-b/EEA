"""SQLAlchemy persistence models owned by the backend adapter."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

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
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
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
