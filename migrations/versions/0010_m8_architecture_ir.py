"""Persist M8 SystemArchitectureIR and HardwareIR.

Revision ID: 0010_m8_architecture_ir
Revises: 0009_m7_pin_planner
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_m8_architecture_ir"
down_revision: str | None = "0009_m7_pin_planner"
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
        "system_architectures",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("pin_plan_id", sa.String(length=36), nullable=False),
        sa.Column("pin_plan_revision", sa.Integer(), nullable=False),
        sa.Column("blocks", sa.JSON(), nullable=False),
        sa.Column("interfaces", sa.JSON(), nullable=False),
        sa.Column("decisions", sa.JSON(), nullable=False),
        sa.Column("requirement_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("source_artifact_ids", sa.JSON(), nullable=False),
        sa.Column("pin_assignment_revisions", sa.JSON(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_system_architectures_project_id_projects",
        ),
        sa.ForeignKeyConstraint(
            ["pin_plan_id"],
            ["pin_plans.id"],
            name="fk_system_architectures_pin_plan_id_pin_plans",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_system_architectures"),
    )
    op.create_index("ix_system_architectures_project_id", "system_architectures", ["project_id"])
    op.create_index("ix_system_architectures_pin_plan_id", "system_architectures", ["pin_plan_id"])

    op.create_table(
        "hardware_irs",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("architecture_id", sa.String(length=36), nullable=False),
        sa.Column("pin_plan_id", sa.String(length=36), nullable=False),
        sa.Column("pin_plan_revision", sa.Integer(), nullable=False),
        sa.Column("modules", sa.JSON(), nullable=False),
        sa.Column("device_instances", sa.JSON(), nullable=False),
        sa.Column("power_domains", sa.JSON(), nullable=False),
        sa.Column("interfaces", sa.JSON(), nullable=False),
        sa.Column("pin_requirements", sa.JSON(), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False),
        sa.Column("requirement_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("pin_assignment_revisions", sa.JSON(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_hardware_irs_project_id_projects"
        ),
        sa.ForeignKeyConstraint(
            ["architecture_id"],
            ["system_architectures.id"],
            name="fk_hardware_irs_architecture_id_system_architectures",
        ),
        sa.ForeignKeyConstraint(
            ["pin_plan_id"], ["pin_plans.id"], name="fk_hardware_irs_pin_plan_id_pin_plans"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hardware_irs"),
    )
    op.create_index("ix_hardware_irs_project_id", "hardware_irs", ["project_id"])
    op.create_index("ix_hardware_irs_architecture_id", "hardware_irs", ["architecture_id"])
    op.create_index("ix_hardware_irs_pin_plan_id", "hardware_irs", ["pin_plan_id"])


def downgrade() -> None:
    op.drop_index("ix_hardware_irs_pin_plan_id", table_name="hardware_irs")
    op.drop_index("ix_hardware_irs_architecture_id", table_name="hardware_irs")
    op.drop_index("ix_hardware_irs_project_id", table_name="hardware_irs")
    op.drop_table("hardware_irs")
    op.drop_index("ix_system_architectures_pin_plan_id", table_name="system_architectures")
    op.drop_index("ix_system_architectures_project_id", table_name="system_architectures")
    op.drop_table("system_architectures")
