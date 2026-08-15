"""Persist M18C Source Authority metadata and filesystem/SQL recovery markers."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0027_m18c_source_authority"
down_revision: str | None = "0026_m18b_domain_composition_contract"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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
    "SOURCE_FILE_NOT_FOUND",
    "PATCH_PROPOSAL_NOT_FOUND",
    "GENERATED_SOURCE_DIVERGED",
)


def _replace_error_constraint(table_name: str, values: tuple[str, ...]) -> None:
    existing = [
        item["name"]
        for item in inspect(op.get_bind()).get_check_constraints(table_name)
        if "error_code" in (item.get("sqltext") or "").lower()
    ]
    serialized = ", ".join(f"'{value}'" for value in values)
    with op.batch_alter_table(table_name, recreate="always") as batch_op:
        if existing:
            name = existing[0]
            prefix = f"ck_{table_name}_"
            batch_op.drop_constraint(
                name[len(prefix) :] if name.startswith(prefix) else name,
                type_="check",
            )
        batch_op.create_check_constraint(
            "error_code",
            f"error_code IS NULL OR error_code IN ({serialized})",
        )


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
    _replace_error_constraint("jobs", _ERROR_CODES)
    _replace_error_constraint("ai_usage_records", _ERROR_CODES)
    op.create_table(
        "source_workspaces",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("repository_id", sa.String(length=300), nullable=False),
        sa.Column("root_path", sa.String(length=2000), nullable=False),
        sa.Column("current_source_revision_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("base_commit", sa.String(length=100), nullable=True),
        sa.Column("last_reconciled_manifest_hash", sa.String(length=64), nullable=True),
        sa.CheckConstraint("workspace_revision >= 0", name="workspace_revision_non_negative"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["current_source_revision_id"], ["source_revisions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_source_workspaces_project"),
    )
    op.create_index("ix_source_workspaces_project_id", "source_workspaces", ["project_id"])
    op.create_index(
        "ix_source_workspaces_current_source_revision_id",
        "source_workspaces",
        ["current_source_revision_id"],
    )

    op.create_table(
        "patch_proposals",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("base_source_revision_id", sa.String(length=36), nullable=False),
        sa.Column("base_workspace_revision", sa.Integer(), nullable=False),
        sa.Column("affected_files", sa.JSON(), nullable=False),
        sa.Column("expected_file_hashes", sa.JSON(), nullable=False),
        sa.Column("patch", sa.Text(), nullable=True),
        sa.Column("structured_edits", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("expected_impact", sa.JSON(), nullable=False),
        sa.Column("required_builds", sa.JSON(), nullable=False),
        sa.Column("required_tests", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("failure_reason", sa.String(length=4000), nullable=True),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'READY', 'APPLIED', 'STALE', 'REJECTED', 'FAILED')",
            name="status",
        ),
        sa.CheckConstraint(
            "base_workspace_revision >= 0", name="base_workspace_revision_non_negative"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["base_source_revision_id"], ["source_revisions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_patch_proposals_project_id", "patch_proposals", ["project_id"])
    op.create_index(
        "ix_patch_proposals_base_source_revision_id",
        "patch_proposals",
        ["base_source_revision_id"],
    )

    op.create_table(
        "generated_source_ownership",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column("generator_id", sa.String(length=200), nullable=False),
        sa.Column("generator_version", sa.String(length=100), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE', 'DIVERGED')", name="status"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "path", name="uq_generated_source_ownership_path"),
    )
    op.create_index(
        "ix_generated_source_ownership_project_id",
        "generated_source_ownership",
        ["project_id"],
    )

    op.create_table(
        "source_mutation_journal",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("operation_id", sa.String(length=36), nullable=False),
        sa.Column("proposal_id", sa.String(length=36), nullable=False),
        sa.Column("previous_source_revision_id", sa.String(length=36), nullable=False),
        sa.Column("expected_workspace_revision", sa.Integer(), nullable=False),
        sa.Column("affected_files", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("last_error", sa.String(length=4000), nullable=True),
        sa.CheckConstraint(
            "status IN ('PREPARED', 'COMPLETED', 'ROLLED_BACK', 'RECOVERED')",
            name="status",
        ),
        sa.CheckConstraint(
            "expected_workspace_revision >= 0", name="expected_workspace_revision_non_negative"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["proposal_id"], ["patch_proposals.id"]),
        sa.ForeignKeyConstraint(["previous_source_revision_id"], ["source_revisions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation_id", name="uq_source_mutation_journal_operation"),
    )
    op.create_index(
        "ix_source_mutation_journal_project_id",
        "source_mutation_journal",
        ["project_id"],
    )
    op.create_index(
        "ix_source_mutation_journal_proposal_id",
        "source_mutation_journal",
        ["proposal_id"],
    )
    op.create_index(
        "ix_source_mutation_journal_previous_source_revision_id",
        "source_mutation_journal",
        ["previous_source_revision_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_source_mutation_journal_previous_source_revision_id",
        table_name="source_mutation_journal",
    )
    op.drop_index("ix_source_mutation_journal_proposal_id", table_name="source_mutation_journal")
    op.drop_index("ix_source_mutation_journal_project_id", table_name="source_mutation_journal")
    op.drop_table("source_mutation_journal")
    op.drop_index(
        "ix_generated_source_ownership_project_id", table_name="generated_source_ownership"
    )
    op.drop_table("generated_source_ownership")
    op.drop_index("ix_patch_proposals_base_source_revision_id", table_name="patch_proposals")
    op.drop_index("ix_patch_proposals_project_id", table_name="patch_proposals")
    op.drop_table("patch_proposals")
    op.drop_index("ix_source_workspaces_current_source_revision_id", table_name="source_workspaces")
    op.drop_index("ix_source_workspaces_project_id", table_name="source_workspaces")
    op.drop_table("source_workspaces")
    prior_codes = tuple(
        code
        for code in _ERROR_CODES
        if code
        not in {
            "SOURCE_FILE_NOT_FOUND",
            "PATCH_PROPOSAL_NOT_FOUND",
            "GENERATED_SOURCE_DIVERGED",
        }
    )
    _replace_error_constraint("jobs", prior_codes)
    _replace_error_constraint("ai_usage_records", prior_codes)
