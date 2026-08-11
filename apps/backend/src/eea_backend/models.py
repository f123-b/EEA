"""SQLAlchemy persistence models owned by the backend adapter."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from eea_core.enums import (
    ArtifactStatus,
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
    DependencyLockStatus,
    DocumentParseStatus,
    DocumentType,
    EngineeringDimension,
    EngineeringErrorCode,
    EvidenceType,
    IssueSeverity,
    IssueStatus,
    JobStatus,
    Permission,
    ProjectStatus,
    RequirementPriority,
    RequirementStatus,
    RequirementType,
    SoftwareComponentRole,
    StaticAnalysisStatus,
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
