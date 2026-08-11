"""Persist M12 FirmwareIR, source snapshots, and BuildRun records.

Revision ID: 0014_m12_firmware_build
Revises: 0013_m11_mcu_config
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_m12_firmware_build"
down_revision: str | None = "0013_m11_mcu_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
        "source_revisions",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("repository_id", sa.String(length=300), nullable=False),
        sa.Column("commit_sha", sa.String(length=100)),
        sa.Column("tree_hash", sa.String(length=64), nullable=False),
        sa.Column("dirty", sa.Boolean(), nullable=False),
        sa.Column("base_commit", sa.String(length=100)),
        sa.Column("workspace_revision", sa.Integer(), nullable=False),
        sa.Column("source_manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("file_manifest", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_source_revisions_project_id_projects"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_source_revisions"),
    )
    op.create_index("ix_source_revisions_project_id", "source_revisions", ["project_id"])

    op.create_table(
        "firmware_irs",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("mcu_config_id", sa.String(length=36), nullable=False),
        sa.Column("mcu_config_revision", sa.Integer(), nullable=False),
        sa.Column("hardware_ir_id", sa.String(length=36), nullable=False),
        sa.Column("hardware_ir_revision", sa.Integer(), nullable=False),
        sa.Column("circuit_id", sa.String(length=36), nullable=False),
        sa.Column("circuit_revision", sa.Integer(), nullable=False),
        sa.Column("schematic_id", sa.String(length=36), nullable=False),
        sa.Column("schematic_revision", sa.Integer(), nullable=False),
        sa.Column("source_revision_id", sa.String(length=36), nullable=False),
        sa.Column("layers", sa.JSON(), nullable=False),
        sa.Column("modules", sa.JSON(), nullable=False),
        sa.Column("tasks", sa.JSON(), nullable=False),
        sa.Column("interrupts", sa.JSON(), nullable=False),
        sa.Column("shared_resources", sa.JSON(), nullable=False),
        sa.Column("startup", sa.JSON(), nullable=False),
        sa.Column("clock_tree", sa.JSON(), nullable=False),
        sa.Column("peripheral_drivers", sa.JSON(), nullable=False),
        sa.Column("memory_layout", sa.JSON(), nullable=False),
        sa.Column("bsp", sa.JSON(), nullable=False),
        sa.Column("build_target", sa.JSON(), nullable=False),
        sa.Column("rule_results", sa.JSON(), nullable=False),
        sa.Column("requirement_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(
            "status IN ('CURRENT', 'STALE', 'INVALID', 'DEPRECATED', 'ARCHIVED')",
            name="status",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_firmware_irs_project_id_projects"
        ),
        sa.ForeignKeyConstraint(
            ["mcu_config_id"], ["mcu_configs.id"], name="fk_firmware_irs_mcu_config_id_mcu_configs"
        ),
        sa.ForeignKeyConstraint(
            ["hardware_ir_id"],
            ["hardware_irs.id"],
            name="fk_firmware_irs_hardware_ir_id_hardware_irs",
        ),
        sa.ForeignKeyConstraint(
            ["circuit_id"], ["circuits.id"], name="fk_firmware_irs_circuit_id_circuits"
        ),
        sa.ForeignKeyConstraint(
            ["schematic_id"],
            ["schematic_artifacts.id"],
            name="fk_firmware_irs_schematic_id_schematic_artifacts",
        ),
        sa.ForeignKeyConstraint(
            ["source_revision_id"],
            ["source_revisions.id"],
            name="fk_firmware_irs_source_revision_id_source_revisions",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_firmware_irs"),
    )
    for column in (
        "project_id",
        "mcu_config_id",
        "hardware_ir_id",
        "circuit_id",
        "schematic_id",
        "source_revision_id",
    ):
        op.create_index(f"ix_firmware_irs_{column}", "firmware_irs", [column])

    op.create_table(
        "firmware_source_files",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("firmware_id", sa.String(length=36), nullable=False),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("generated_owned", sa.Boolean(), nullable=False),
        sa.Column("generator_version", sa.String(length=100), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_firmware_source_files_project_id_projects"
        ),
        sa.ForeignKeyConstraint(
            ["firmware_id"],
            ["firmware_irs.id"],
            name="fk_firmware_source_files_firmware_id_firmware_irs",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_firmware_source_files"),
        sa.UniqueConstraint("firmware_id", "path", name="uq_firmware_source_files_path"),
    )
    op.create_index("ix_firmware_source_files_project_id", "firmware_source_files", ["project_id"])
    op.create_index(
        "ix_firmware_source_files_firmware_id", "firmware_source_files", ["firmware_id"]
    )

    op.create_table(
        "build_input_snapshots",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("source_revision_id", sa.String(length=36), nullable=False),
        sa.Column("tracked_file_manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("allowed_untracked_input_hash", sa.String(length=64), nullable=False),
        sa.Column("generated_input_hash", sa.String(length=64), nullable=False),
        sa.Column("submodule_commit_map", sa.JSON(), nullable=False),
        sa.Column("build_config_hash", sa.String(length=64), nullable=False),
        sa.Column("toolchain_id", sa.String(length=200), nullable=False),
        sa.Column("toolchain_version", sa.String(length=200), nullable=False),
        sa.Column("environment_profile_hash", sa.String(length=64), nullable=False),
        sa.Column("source_manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("build_input_hash", sa.String(length=64), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_build_input_snapshots_project_id_projects"
        ),
        sa.ForeignKeyConstraint(
            ["source_revision_id"],
            ["source_revisions.id"],
            name="fk_build_input_snapshots_source_revision_id_source_revisions",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_build_input_snapshots"),
    )
    op.create_index("ix_build_input_snapshots_project_id", "build_input_snapshots", ["project_id"])
    op.create_index(
        "ix_build_input_snapshots_source_revision_id",
        "build_input_snapshots",
        ["source_revision_id"],
    )

    op.create_table(
        "build_runs",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("firmware_id", sa.String(length=36), nullable=False),
        sa.Column("firmware_revision", sa.Integer(), nullable=False),
        sa.Column("source_revision_id", sa.String(length=36), nullable=False),
        sa.Column("build_input_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("toolchain_id", sa.String(length=200), nullable=False),
        sa.Column("toolchain_version", sa.String(length=200), nullable=False),
        sa.Column("environment_profile_hash", sa.String(length=64), nullable=False),
        sa.Column("build_input_hash", sa.String(length=64), nullable=False),
        sa.Column("command", sa.JSON(), nullable=False),
        sa.Column("diagnostics", sa.JSON(), nullable=False),
        sa.Column("stdout", sa.Text(), nullable=False),
        sa.Column("stderr", sa.Text(), nullable=False),
        sa.Column("artifact_hash", sa.String(length=64)),
        sa.Column("error_code", sa.String(length=80)),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'PASS', 'FAIL', 'UNKNOWN', 'BLOCKED')",
            name="status",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_build_runs_project_id_projects"
        ),
        sa.ForeignKeyConstraint(
            ["firmware_id"], ["firmware_irs.id"], name="fk_build_runs_firmware_id_firmware_irs"
        ),
        sa.ForeignKeyConstraint(
            ["source_revision_id"],
            ["source_revisions.id"],
            name="fk_build_runs_source_revision_id_source_revisions",
        ),
        sa.ForeignKeyConstraint(
            ["build_input_snapshot_id"],
            ["build_input_snapshots.id"],
            name="fk_build_runs_build_input_snapshot_id_build_input_snapshots",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_build_runs"),
    )
    for column in (
        "project_id",
        "firmware_id",
        "source_revision_id",
        "build_input_snapshot_id",
    ):
        op.create_index(f"ix_build_runs_{column}", "build_runs", [column])


def downgrade() -> None:
    for column in (
        "build_input_snapshot_id",
        "source_revision_id",
        "firmware_id",
        "project_id",
    ):
        op.drop_index(f"ix_build_runs_{column}", table_name="build_runs")
    op.drop_table("build_runs")
    op.drop_index("ix_build_input_snapshots_source_revision_id", table_name="build_input_snapshots")
    op.drop_index("ix_build_input_snapshots_project_id", table_name="build_input_snapshots")
    op.drop_table("build_input_snapshots")
    op.drop_index("ix_firmware_source_files_firmware_id", table_name="firmware_source_files")
    op.drop_index("ix_firmware_source_files_project_id", table_name="firmware_source_files")
    op.drop_table("firmware_source_files")
    for column in (
        "source_revision_id",
        "schematic_id",
        "circuit_id",
        "hardware_ir_id",
        "mcu_config_id",
        "project_id",
    ):
        op.drop_index(f"ix_firmware_irs_{column}", table_name="firmware_irs")
    op.drop_table("firmware_irs")
    op.drop_index("ix_source_revisions_project_id", table_name="source_revisions")
    op.drop_table("source_revisions")
