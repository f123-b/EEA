"""Persist M11 MCU configuration snapshots and deterministic rule results.

Revision ID: 0013_m11_mcu_config
Revises: 0012_m10_schematic
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_m11_mcu_config"
down_revision: str | None = "0012_m10_schematic"
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
        "mcu_configs",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("hardware_ir_id", sa.String(length=36), nullable=False),
        sa.Column("hardware_ir_revision", sa.Integer(), nullable=False),
        sa.Column("circuit_id", sa.String(length=36), nullable=False),
        sa.Column("circuit_revision", sa.Integer(), nullable=False),
        sa.Column("schematic_id", sa.String(length=36), nullable=False),
        sa.Column("schematic_revision", sa.Integer(), nullable=False),
        sa.Column("device_instance_id", sa.String(length=36), nullable=False),
        sa.Column("clock", sa.JSON(), nullable=False),
        sa.Column("gpio", sa.JSON(), nullable=False),
        sa.Column("peripherals", sa.JSON(), nullable=False),
        sa.Column("dma", sa.JSON(), nullable=False),
        sa.Column("interrupts", sa.JSON(), nullable=False),
        sa.Column("memory", sa.JSON()),
        sa.Column("debug", sa.JSON()),
        sa.Column("capability_snapshot", sa.JSON(), nullable=False),
        sa.Column("requirement_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("pin_assignment_revisions", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(
            "status IN ('CURRENT', 'STALE', 'INVALID', 'DEPRECATED', 'ARCHIVED')",
            name="status",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_mcu_configs_project_id_projects"
        ),
        sa.ForeignKeyConstraint(
            ["hardware_ir_id"],
            ["hardware_irs.id"],
            name="fk_mcu_configs_hardware_ir_id_hardware_irs",
        ),
        sa.ForeignKeyConstraint(
            ["circuit_id"], ["circuits.id"], name="fk_mcu_configs_circuit_id_circuits"
        ),
        sa.ForeignKeyConstraint(
            ["schematic_id"],
            ["schematic_artifacts.id"],
            name="fk_mcu_configs_schematic_id_schematic_artifacts",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mcu_configs"),
    )
    for column in (
        "project_id",
        "hardware_ir_id",
        "circuit_id",
        "schematic_id",
        "device_instance_id",
    ):
        op.create_index(f"ix_mcu_configs_{column}", "mcu_configs", [column])

    op.create_table(
        "mcu_config_rule_results",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("mcu_config_id", sa.String(length=36), nullable=False),
        sa.Column("rule_id", sa.String(length=200), nullable=False),
        sa.Column("rule_version", sa.String(length=50), nullable=False),
        sa.Column("stage", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("affected_refs", sa.JSON(), nullable=False),
        sa.Column("measured", sa.JSON()),
        sa.Column("threshold", sa.JSON()),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("claim_ids", sa.JSON(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(
            "stage IN ('PRE_GENERATION', 'POST_GENERATION', 'PRE_TOOL', 'POST_TOOL', "
            "'RELEASE_GATE')",
            name="stage",
        ),
        sa.CheckConstraint(
            "status IN ('PASS', 'FAIL', 'NOT_APPLICABLE', 'UNKNOWN')",
            name="status",
        ),
        sa.CheckConstraint(
            "severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')", name="severity"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_mcu_config_rule_results_project_id_projects",
        ),
        sa.ForeignKeyConstraint(
            ["mcu_config_id"],
            ["mcu_configs.id"],
            name="fk_mcu_config_rule_results_mcu_config_id_mcu_configs",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mcu_config_rule_results"),
    )
    op.create_index(
        "ix_mcu_config_rule_results_project_id",
        "mcu_config_rule_results",
        ["project_id"],
    )
    op.create_index(
        "ix_mcu_config_rule_results_mcu_config_id",
        "mcu_config_rule_results",
        ["mcu_config_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_mcu_config_rule_results_mcu_config_id", table_name="mcu_config_rule_results")
    op.drop_index("ix_mcu_config_rule_results_project_id", table_name="mcu_config_rule_results")
    op.drop_table("mcu_config_rule_results")
    for column in (
        "device_instance_id",
        "schematic_id",
        "circuit_id",
        "hardware_ir_id",
        "project_id",
    ):
        op.drop_index(f"ix_mcu_configs_{column}", table_name="mcu_configs")
    op.drop_table("mcu_configs")
