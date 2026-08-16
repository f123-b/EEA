"""M18E renderer, NFR, backup and identity foundation persistence."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0031_m18e_renderer_nfr_hardening"
down_revision: str | None = "0030_m18d_hardware_commissioning_safety"
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
    "CAPACITY_EXCEEDED",
    "BACKUP_INVALID",
    "BACKUP_INCOMPATIBLE",
    "RESTORE_CONFLICT",
    "RENDER_CONTENT_REJECTED",
    "NFR_LIMIT_EXCEEDED",
)
_PREVIOUS_ERROR_CODES = _ERROR_CODES[:-6]


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
                name[len(prefix) :] if name.startswith(prefix) else name, type_="check"
            )
        batch_op.create_check_constraint(
            "error_code", f"error_code IS NULL OR error_code IN ({serialized})"
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
        "identity_users",
        *_entity_columns(),
        sa.Column("stable_actor_id", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("mode", sa.String(length=40), nullable=False),
        sa.CheckConstraint("mode IN ('LOCAL_SINGLE_USER','TEAM')", name="mode"),
        sa.UniqueConstraint("stable_actor_id", name="uq_identity_users_stable_actor_id"),
    )
    op.create_table(
        "organizations",
        *_entity_columns(),
        sa.Column("stable_key", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.UniqueConstraint("stable_key", name="uq_organizations_stable_key"),
    )
    op.create_table(
        "organization_memberships",
        *_entity_columns(),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["identity_users.id"]),
        sa.CheckConstraint("role IN ('OWNER','MAINTAINER','ENGINEER','VIEWER')", name="role"),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_membership_organization_user"),
    )
    op.create_table(
        "project_role_assignments",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["identity_users.id"]),
        sa.CheckConstraint("role IN ('OWNER','MAINTAINER','ENGINEER','VIEWER')", name="role"),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_role_project_user"),
    )
    op.create_table(
        "backup_manifests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("manifest_version", sa.String(length=30), nullable=False),
        sa.Column("schema_version", sa.String(length=50), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("content_hashes", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.CheckConstraint("length(manifest_hash) = 64", name="manifest_hash_length"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("manifest_hash", name="uq_backup_manifests_manifest_hash"),
    )
    op.create_index("ix_identity_users_stable_actor_id", "identity_users", ["stable_actor_id"])
    op.create_index(
        "ix_project_role_assignments_project_id", "project_role_assignments", ["project_id"]
    )
    op.create_index("ix_project_role_assignments_user_id", "project_role_assignments", ["user_id"])
    op.create_index("ix_backup_manifests_project_id", "backup_manifests", ["project_id"])


def downgrade() -> None:
    _replace_error_constraint("jobs", _PREVIOUS_ERROR_CODES)
    _replace_error_constraint("ai_usage_records", _PREVIOUS_ERROR_CODES)
    op.drop_index("ix_backup_manifests_project_id", table_name="backup_manifests")
    op.drop_index("ix_project_role_assignments_user_id", table_name="project_role_assignments")
    op.drop_index("ix_project_role_assignments_project_id", table_name="project_role_assignments")
    op.drop_index("ix_identity_users_stable_actor_id", table_name="identity_users")
    op.drop_table("backup_manifests")
    op.drop_table("project_role_assignments")
    op.drop_table("organization_memberships")
    op.drop_table("organizations")
    op.drop_table("identity_users")
