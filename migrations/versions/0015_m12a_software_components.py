"""Add ESCR component catalog, immutable releases, dependency locks, and materializations.

Revision ID: 0015_m12a_software_components
Revises: 0014_m12_firmware_build
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0015_m12a_software_components"
down_revision: str | None = "0014_m12_firmware_build"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_ERROR_CODES = (
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
    "SANDBOX_VIOLATION",
    "ARCHIVE_UNSAFE",
    "COMMAND_NOT_ALLOWED",
    "NETWORK_DENIED",
    "RESOURCE_LIMIT_EXCEEDED",
)
NEW_ERROR_CODES = (
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
)


def _values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _replace_error_constraint(table_name: str, values: tuple[str, ...]) -> None:
    existing = [
        item["name"]
        for item in inspect(op.get_bind()).get_check_constraints(table_name)
        if "error_code" in (item.get("sqltext") or "").lower()
    ]
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
            f"error_code IS NULL OR error_code IN ({_values(values)})",
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
    current_error_codes = LEGACY_ERROR_CODES + NEW_ERROR_CODES
    _replace_error_constraint("jobs", current_error_codes)
    _replace_error_constraint("ai_usage_records", current_error_codes)
    op.create_table(
        "software_components",
        *_entity_columns(),
        sa.Column("component_key", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("vendor", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("authority", sa.String(length=50), nullable=False),
        sa.Column("provider_id", sa.String(length=200), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_uri", sa.String(length=2000)),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("compatibility", sa.JSON(), nullable=False),
        sa.Column("license_expression", sa.String(length=200)),
        sa.Column("license_text_hash", sa.String(length=64)),
        sa.Column("dependencies", sa.JSON(), nullable=False),
        sa.Column("production_eligible", sa.Boolean(), nullable=False),
        sa.Column("reference_only", sa.Boolean(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(
            "authority IN ("
            "'VENDOR_OFFICIAL', 'UPSTREAM_OFFICIAL', 'EEA_CURATED', "
            "'PROJECT_LOCAL', 'REFERENCE_ONLY')",
            name="authority",
        ),
        sa.CheckConstraint(
            "role IN ("
            "'MCU_SDK', 'CMSIS_CORE', 'CMSIS_DEVICE', 'HAL', 'LL', 'RTOS', "
            "'DSP', 'MIDDLEWARE', 'BSP', 'LIBRARY', 'REFERENCE')",
            name="role",
        ),
        sa.CheckConstraint(
            "source_type IN ("
            "'CMSIS_PACK', 'VENDOR_SDK', 'GIT', 'ARCHIVE', 'LOCAL_PROJECT', "
            "'PLATFORMIO', 'CURATED')",
            name="source_type",
        ),
        sa.UniqueConstraint("component_key", name="uq_software_components_component_key"),
        sa.PrimaryKeyConstraint("id", name="pk_software_components"),
    )
    op.create_index(
        "ix_software_components_component_key", "software_components", ["component_key"]
    )

    op.create_table(
        "software_component_releases",
        *_entity_columns(),
        sa.Column("component_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("revision_kind", sa.String(length=50), nullable=False),
        sa.Column("source_revision", sa.String(length=200), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64)),
        sa.Column("files", sa.JSON(), nullable=False),
        sa.Column("submodule_commit_map", sa.JSON(), nullable=False),
        sa.Column("source_uri", sa.String(length=2000)),
        sa.Column("yanked", sa.Boolean(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(
            "revision_kind IN ("
            "'GIT_COMMIT', 'PACK_HASH', 'ARCHIVE_HASH', 'CONTENT_HASH', 'IMMUTABLE_ID')",
            name="revision_kind",
        ),
        sa.ForeignKeyConstraint(["component_id"], ["software_components.id"]),
        sa.UniqueConstraint(
            "component_id", "source_revision", name="uq_component_release_revision"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_software_component_releases"),
    )
    op.create_index(
        "ix_software_component_releases_component_id",
        "software_component_releases",
        ["component_id"],
    )

    op.create_table(
        "dependency_locks",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("mcu_config_id", sa.String(length=36), nullable=False),
        sa.Column("mcu_config_revision", sa.Integer(), nullable=False),
        sa.Column("requirements", sa.JSON(), nullable=False),
        sa.Column("resolved_components", sa.JSON(), nullable=False),
        sa.Column("resolution_policy_version", sa.String(length=100), nullable=False),
        sa.Column("resolver_version", sa.String(length=100), nullable=False),
        sa.Column("lock_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint("status IN ('DRAFT', 'LOCKED', 'STALE', 'INVALID')", name="status"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["mcu_config_id"], ["mcu_configs.id"]),
        sa.UniqueConstraint("project_id", "lock_hash", name="uq_dependency_locks_project_hash"),
        sa.PrimaryKeyConstraint("id", name="pk_dependency_locks"),
    )
    op.create_index("ix_dependency_locks_project_id", "dependency_locks", ["project_id"])
    op.create_index("ix_dependency_locks_mcu_config_id", "dependency_locks", ["mcu_config_id"])

    op.create_table(
        "dependency_lock_components",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("dependency_lock_id", sa.String(length=36), nullable=False),
        sa.Column("component_id", sa.String(length=36), nullable=False),
        sa.Column("release_id", sa.String(length=36), nullable=False),
        sa.Column("component_key", sa.String(length=200), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("component_revision", sa.String(length=200), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["dependency_lock_id"], ["dependency_locks.id"]),
        sa.ForeignKeyConstraint(["component_id"], ["software_components.id"]),
        sa.ForeignKeyConstraint(["release_id"], ["software_component_releases.id"]),
        sa.UniqueConstraint("dependency_lock_id", "component_key", name="uq_lock_component_key"),
        sa.PrimaryKeyConstraint("id", name="pk_dependency_lock_components"),
    )
    for column in ("project_id", "dependency_lock_id", "component_id", "release_id"):
        op.create_index(
            f"ix_dependency_lock_components_{column}",
            "dependency_lock_components",
            [column],
        )

    op.create_table(
        "component_materializations",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("component_id", sa.String(length=36), nullable=False),
        sa.Column("release_id", sa.String(length=36), nullable=False),
        sa.Column("owner", sa.String(length=30), nullable=False),
        sa.Column("cache_key", sa.String(length=200), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_uri", sa.String(length=2000), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("network_used", sa.Boolean(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'MATERIALIZED', 'HASH_MISMATCH', 'FAILED')", name="status"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["component_id"], ["software_components.id"]),
        sa.ForeignKeyConstraint(["release_id"], ["software_component_releases.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_component_materializations"),
    )
    for column in ("project_id", "component_id", "release_id"):
        op.create_index(
            f"ix_component_materializations_{column}",
            "component_materializations",
            [column],
        )

    with op.batch_alter_table("firmware_irs") as batch:
        batch.add_column(sa.Column("dependency_lock_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("dependency_lock_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("component_refs", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("platform_adapter_id", sa.String(length=200), nullable=True))
        batch.add_column(
            sa.Column("platform_adapter_version", sa.String(length=100), nullable=True)
        )
        batch.create_index("ix_firmware_irs_dependency_lock_id", ["dependency_lock_id"])
        batch.create_foreign_key(
            "fk_firmware_irs_dependency_lock_id_dependency_locks",
            "dependency_locks",
            ["dependency_lock_id"],
            ["id"],
        )
    with op.batch_alter_table("build_input_snapshots") as batch:
        batch.add_column(sa.Column("dependency_lock_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("component_manifest_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("toolchain_manifest_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("build_profile", sa.String(length=30), nullable=True))
    with op.batch_alter_table("build_runs") as batch:
        batch.add_column(sa.Column("profile", sa.String(length=30), nullable=True))


def downgrade() -> None:
    _replace_error_constraint("ai_usage_records", LEGACY_ERROR_CODES)
    _replace_error_constraint("jobs", LEGACY_ERROR_CODES)
    with op.batch_alter_table("build_runs") as batch:
        batch.drop_column("profile")
    with op.batch_alter_table("build_input_snapshots") as batch:
        batch.drop_column("build_profile")
        batch.drop_column("toolchain_manifest_hash")
        batch.drop_column("component_manifest_hash")
        batch.drop_column("dependency_lock_hash")
    with op.batch_alter_table("firmware_irs") as batch:
        batch.drop_constraint(
            "fk_firmware_irs_dependency_lock_id_dependency_locks", type_="foreignkey"
        )
        batch.drop_index("ix_firmware_irs_dependency_lock_id")
        batch.drop_column("platform_adapter_version")
        batch.drop_column("platform_adapter_id")
        batch.drop_column("component_refs")
        batch.drop_column("dependency_lock_hash")
        batch.drop_column("dependency_lock_id")
    for column in ("project_id", "component_id", "release_id"):
        op.drop_index(
            f"ix_component_materializations_{column}", table_name="component_materializations"
        )
    op.drop_table("component_materializations")
    for column in ("project_id", "dependency_lock_id", "component_id", "release_id"):
        op.drop_index(
            f"ix_dependency_lock_components_{column}", table_name="dependency_lock_components"
        )
    op.drop_table("dependency_lock_components")
    op.drop_index("ix_dependency_locks_mcu_config_id", table_name="dependency_locks")
    op.drop_index("ix_dependency_locks_project_id", table_name="dependency_locks")
    op.drop_table("dependency_locks")
    op.drop_index(
        "ix_software_component_releases_component_id", table_name="software_component_releases"
    )
    op.drop_table("software_component_releases")
    op.drop_index("ix_software_components_component_key", table_name="software_components")
    op.drop_table("software_components")
