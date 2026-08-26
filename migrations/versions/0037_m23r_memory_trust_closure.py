"""M23R trusted identity, memory audit, and propagation closure."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0037_m23r_memory_trust_closure"
down_revision: str | None = "0036_m22r_import_candidates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_ERROR_CODES = (
    "INVALID_MEMORY_TRANSITION",
    "VERIFICATION_EVIDENCE_REQUIRED",
    "ORGANIZATION_SCOPE_UNAVAILABLE",
)
_ERROR_CODES = (
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
    *_NEW_ERROR_CODES,
    "REPOSITORY_UNTRUSTED",
    "JOB_CANCELLED",
    "SCHEMA_VERSION_UNSUPPORTED",
    "AUTH_REQUIRED",
    "SOURCE_REVISION_CONFLICT",
    "DOMAIN_COMPOSITION_CONFLICT",
    "DOMAIN_DEPENDENCY_MISSING",
    "DOMAIN_INCOMPATIBLE",
    "DOMAIN_NOT_FOUND",
    "DOMAIN_CONFIGURATION_INVALID",
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
    "SOURCE_FILE_NOT_FOUND",
    "PATCH_PROPOSAL_NOT_FOUND",
    "GENERATED_SOURCE_DIVERGED",
    "SANDBOX_VIOLATION",
    "ARCHIVE_UNSAFE",
    "COMMAND_NOT_ALLOWED",
    "NETWORK_DENIED",
    "RESOURCE_LIMIT_EXCEEDED",
    "COMPONENT_UNAVAILABLE",
    "COMPONENT_VERSION_UNRESOLVED",
    "COMPONENT_INCOMPATIBLE",
    "COMPONENT_HASH_MISMATCH",
    "COMPONENT_LICENSE_BLOCKED",
    "COMPONENT_REFERENCE_ONLY",
    "DEPENDENCY_CONFLICT",
    "DEPENDENCY_CYCLE",
    "DEPENDENCY_LOCK_REQUIRED",
    "DEPENDENCY_LOCK_STALE",
    "COMPONENT_MATERIALIZATION_FAILED",
    "TOOLCHAIN_INCOMPATIBLE",
    "DEVICE_BUILD_UNAVAILABLE",
    "CAPACITY_EXCEEDED",
    "BACKUP_INVALID",
    "BACKUP_INCOMPATIBLE",
    "RESTORE_CONFLICT",
    "RENDER_CONTENT_REJECTED",
    "NFR_LIMIT_EXCEEDED",
)
_PREVIOUS_ERROR_CODES = tuple(code for code in _ERROR_CODES if code not in _NEW_ERROR_CODES)


def _replace_error_constraint(table_name: str, values: tuple[str, ...]) -> None:
    existing = [
        item["name"]
        for item in inspect(op.get_bind()).get_check_constraints(table_name)
        if "error_code" in (item.get("sqltext") or "").lower()
    ]
    serialized_values = ", ".join(f"'{value}'" for value in values)
    with op.batch_alter_table(table_name, recreate="always") as batch_op:
        if existing:
            name = existing[0]
            prefix = f"ck_{table_name}_"
            batch_op.drop_constraint(
                name[len(prefix) :] if name.startswith(prefix) else name,
                type_="check",
            )
        batch_op.create_check_constraint(
            "error_code", f"error_code IS NULL OR error_code IN ({serialized_values})"
        )


def upgrade() -> None:
    _replace_error_constraint("jobs", _ERROR_CODES)
    _replace_error_constraint("ai_usage_records", _ERROR_CODES)
    op.create_table(
        "knowledge_audits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("schema_version", sa.String(length=30), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("entry_id", sa.String(length=36), nullable=True),
        sa.Column("principal_id", sa.String(length=200), nullable=False),
        sa.Column("user_id", sa.String(length=200), nullable=False),
        sa.Column("session_id", sa.String(length=200), nullable=False),
        sa.Column("request_id", sa.String(length=200), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("before", sa.JSON(), nullable=False),
        sa.Column("after", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["entry_id"], ["knowledge_entries.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_audits"),
    )
    op.create_index("ix_knowledge_audits_project_id", "knowledge_audits", ["project_id"])
    op.create_index("ix_knowledge_audits_entry_id", "knowledge_audits", ["entry_id"])
    op.create_index("ix_knowledge_audits_principal_id", "knowledge_audits", ["principal_id"])
    op.create_index("ix_knowledge_audits_user_id", "knowledge_audits", ["user_id"])
    op.create_index("ix_knowledge_audits_action", "knowledge_audits", ["action"])
    op.create_index(
        "ix_knowledge_audits_entry_created", "knowledge_audits", ["entry_id", "created_at"]
    )
    op.create_index(
        "ix_knowledge_audits_project_created", "knowledge_audits", ["project_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_audits_project_created", table_name="knowledge_audits")
    op.drop_index("ix_knowledge_audits_entry_created", table_name="knowledge_audits")
    op.drop_index("ix_knowledge_audits_action", table_name="knowledge_audits")
    op.drop_index("ix_knowledge_audits_user_id", table_name="knowledge_audits")
    op.drop_index("ix_knowledge_audits_principal_id", table_name="knowledge_audits")
    op.drop_index("ix_knowledge_audits_entry_id", table_name="knowledge_audits")
    op.drop_index("ix_knowledge_audits_project_id", table_name="knowledge_audits")
    op.drop_table("knowledge_audits")
    _replace_error_constraint("jobs", _PREVIOUS_ERROR_CODES)
    _replace_error_constraint("ai_usage_records", _PREVIOUS_ERROR_CODES)
