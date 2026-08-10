"""Create M1 core-domain tables.

Revision ID: 0002_m1
Revises: 0001_m0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_m1"
down_revision: str | None = "0001_m0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROJECT_STATUSES = ("DRAFT", "ACTIVE", "ARCHIVED")
ARTIFACT_STATUSES = ("CURRENT", "STALE", "INVALID", "DEPRECATED", "ARCHIVED")
EVIDENCE_TYPES = (
    "DOCUMENT",
    "DEVICE_DB",
    "REPOSITORY",
    "RULE",
    "TOOL",
    "SIMULATION",
    "HARDWARE_TEST",
    "USER_CONFIRMATION",
    "IMPORTED_PROJECT",
)
ISSUE_SEVERITIES = ("INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL")
ISSUE_STATUSES = ("OPEN", "RESOLVED", "IGNORED")
DECISION_STATUSES = ("PROPOSED", "ACCEPTED", "SUPERSEDED", "REJECTED")
JOB_STATUSES = (
    "QUEUED",
    "RUNNING",
    "BLOCKED_PERMISSION",
    "BLOCKED_RESOURCE",
    "RECOVERING",
    "SUCCESS",
    "FAILED",
    "FAILED_NEEDS_RECONCILE",
    "CANCELLED",
)
PERMISSIONS = (
    "READ",
    "WRITE",
    "BUILD",
    "NETWORK",
    "SECRET_USE",
    "FLASH",
    "DEBUG",
    "HARDWARE_CONTROL",
    "ACTUATOR_ENABLE",
    "DELETE",
    "PLUGIN_INSTALL",
    "KNOWLEDGE_PROMOTE",
    "EXPORT_PRIVATE",
)
ENGINEERING_ERROR_CODES = (
    "VALIDATION_ERROR",
    "PROJECT_NOT_FOUND",
    "DOCUMENT_PARSE_FAILED",
    "CLAIM_CONFLICT",
    "DEVICE_NOT_FOUND",
    "PIN_CONFLICT",
    "PIN_FUNCTION_INVALID",
    "INVALID_REQUIREMENT",
    "REVISION_CONFLICT",
    "BUILD_FAILED",
    "ERC_FAILED",
    "STATIC_ANALYSIS_FAILED",
    "TOOL_UNAVAILABLE",
    "CAPABILITY_UNAVAILABLE",
    "AI_PROVIDER_UNAVAILABLE",
    "PERMISSION_REQUIRED",
    "RESOURCE_BUSY",
    "BUDGET_EXCEEDED",
    "KNOWLEDGE_SCOPE_DENIED",
    "REPOSITORY_UNTRUSTED",
    "JOB_CANCELLED",
    "SCHEMA_VERSION_UNSUPPORTED",
    "AUTH_REQUIRED",
    "SOURCE_REVISION_CONFLICT",
    "DOMAIN_COMPOSITION_CONFLICT",
    "DOMAIN_DEPENDENCY_MISSING",
    "DOMAIN_INCOMPATIBLE",
    "COMMISSIONING_REQUIRED",
    "COMMISSIONING_BLOCKED",
    "SAFETY_LIMIT_VIOLATION",
    "TARGET_IDENTITY_MISMATCH",
    "SAFE_STATE_FAILED",
    "EMERGENCY_STOP_ACTIVE",
    "RECOVERY_REQUIRED",
    "EVENT_DELIVERY_FAILED",
    "INDEX_REBUILD_REQUIRED",
    "BUILD_INPUT_UNDECLARED",
)
TRACEABILITY_RELATIONS = (
    "IMPLEMENTS",
    "DERIVED_FROM",
    "VERIFIED_BY",
    "AFFECTS",
    "DEPENDS_ON",
    "GENERATED_FROM",
    "INVALIDATES",
)


def _values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _entity_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("schema_version", sa.String(length=30), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "projects",
        *_entity_columns(),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(f"status IN ({_values(PROJECT_STATUSES)})", name="status"),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
    )
    op.create_index("ix_projects_name", "projects", ["name"])

    op.create_table(
        "jobs",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("phase", sa.String(length=200), nullable=True),
        sa.Column("result_ref", sa.String(length=2000), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("budget_usage", sa.JSON(), nullable=False),
        sa.Column("resource_lock_ids", sa.JSON(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint("progress >= 0 AND progress <= 1", name="progress"),
        sa.CheckConstraint(f"status IN ({_values(JOB_STATUSES)})", name="status"),
        sa.CheckConstraint(
            f"error_code IS NULL OR error_code IN ({_values(ENGINEERING_ERROR_CODES)})",
            name="error_code",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_jobs_project_id_projects"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
    )
    op.create_index("ix_jobs_project_id", "jobs", ["project_id"])

    op.create_table(
        "artifacts",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("logical_name", sa.String(length=300), nullable=False),
        sa.Column("artifact_type", sa.String(length=100), nullable=False),
        sa.Column("version_label", sa.String(length=100), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_uri", sa.String(length=2000), nullable=False),
        sa.Column("parent_artifact_id", sa.String(length=36), nullable=True),
        sa.Column("dependency_ids", sa.JSON(), nullable=False),
        sa.Column("dependency_hashes", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column("source_job_id", sa.String(length=36), nullable=True),
        sa.Column("generator_version", sa.String(length=100), nullable=True),
        sa.Column("tool_versions", sa.JSON(), nullable=False),
        sa.Column("knowledge_snapshot", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(f"status IN ({_values(ARTIFACT_STATUSES)})", name="status"),
        sa.ForeignKeyConstraint(
            ["parent_artifact_id"],
            ["artifacts.id"],
            name="fk_artifacts_parent_artifact_id_artifacts",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_artifacts_project_id_projects"
        ),
        sa.ForeignKeyConstraint(
            ["source_job_id"], ["jobs.id"], name="fk_artifacts_source_job_id_jobs"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_artifacts"),
        sa.UniqueConstraint(
            "project_id",
            "logical_name",
            "version_label",
            name="uq_artifacts_project_logical_version",
        ),
    )
    op.create_index("ix_artifacts_project_id", "artifacts", ["project_id"])

    op.create_table(
        "evidence",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("evidence_type", sa.String(length=40), nullable=False),
        sa.Column("locator", sa.JSON(), nullable=False),
        sa.Column("source_uri", sa.String(length=2000), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(f"evidence_type IN ({_values(EVIDENCE_TYPES)})", name="type"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_evidence_project_id_projects"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence"),
    )
    op.create_index("ix_evidence_project_id", "evidence", ["project_id"])

    op.create_table(
        "issues",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("claim_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(f"severity IN ({_values(ISSUE_SEVERITIES)})", name="severity"),
        sa.CheckConstraint(f"status IN ({_values(ISSUE_STATUSES)})", name="status"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_issues_project_id_projects"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_issues"),
    )
    op.create_index("ix_issues_project_id", "issues", ["project_id"])

    op.create_table(
        "engineering_decisions",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("context", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("alternatives", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(f"status IN ({_values(DECISION_STATUSES)})", name="status"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_engineering_decisions_project_id_projects",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_engineering_decisions"),
    )
    op.create_index("ix_engineering_decisions_project_id", "engineering_decisions", ["project_id"])

    op.create_table(
        "permissions_audit",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("actor_id", sa.String(length=200), nullable=False),
        sa.Column("permission", sa.String(length=40), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.String(length=500), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=2000), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(f"permission IN ({_values(PERMISSIONS)})", name="permission"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_permissions_audit_project_id_projects"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_permissions_audit"),
    )
    op.create_index("ix_permissions_audit_actor_id", "permissions_audit", ["actor_id"])
    op.create_index("ix_permissions_audit_project_id", "permissions_audit", ["project_id"])

    op.create_table(
        "traceability_edges",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=100), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("target_type", sa.String(length=100), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("relation", sa.String(length=40), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(
            f"relation IN ({_values(TRACEABILITY_RELATIONS)})",
            name="relation",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_traceability_edges_project_id_projects"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_traceability_edges"),
        sa.UniqueConstraint(
            "project_id",
            "source_type",
            "source_id",
            "target_type",
            "target_id",
            "relation",
            name="uq_traceability_edges_identity",
        ),
    )
    op.create_index("ix_traceability_edges_project_id", "traceability_edges", ["project_id"])

    op.create_table(
        "schema_registry",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("schema_version", sa.String(length=30), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("json_schema", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("name", "schema_version", name="pk_schema_registry"),
    )


def downgrade() -> None:
    op.drop_table("schema_registry")
    op.drop_index("ix_traceability_edges_project_id", table_name="traceability_edges")
    op.drop_table("traceability_edges")
    op.drop_index("ix_permissions_audit_project_id", table_name="permissions_audit")
    op.drop_index("ix_permissions_audit_actor_id", table_name="permissions_audit")
    op.drop_table("permissions_audit")
    op.drop_index("ix_engineering_decisions_project_id", table_name="engineering_decisions")
    op.drop_table("engineering_decisions")
    op.drop_index("ix_issues_project_id", table_name="issues")
    op.drop_table("issues")
    op.drop_index("ix_evidence_project_id", table_name="evidence")
    op.drop_table("evidence")
    op.drop_index("ix_artifacts_project_id", table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_index("ix_jobs_project_id", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_projects_name", table_name="projects")
    op.drop_table("projects")
