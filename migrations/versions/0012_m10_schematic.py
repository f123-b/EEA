"""Persist M10 schematic artifacts and ERC reports.

Revision ID: 0012_m10_schematic
Revises: 0011_m9_circuit_ir
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_m10_schematic"
down_revision: str | None = "0011_m9_circuit_ir"
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
        "schematic_artifacts",
        *_entity_columns(),
        sa.Column("artifact_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("circuit_id", sa.String(length=36), nullable=False),
        sa.Column("circuit_revision", sa.Integer(), nullable=False),
        sa.Column("hardware_ir_id", sa.String(length=36), nullable=False),
        sa.Column("hardware_ir_revision", sa.Integer(), nullable=False),
        sa.Column("format", sa.String(length=50), nullable=False),
        sa.Column("components", sa.JSON(), nullable=False),
        sa.Column("nets", sa.JSON(), nullable=False),
        sa.Column("power_nets", sa.JSON(), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False),
        sa.Column("netlist_text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("preflight_results", sa.JSON(), nullable=False),
        sa.Column("requirement_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("pin_assignment_revisions", sa.JSON(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.ForeignKeyConstraint(
            ["artifact_id"], ["artifacts.id"], name="fk_schematic_artifacts_artifact_id_artifacts"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_schematic_artifacts_project_id_projects"
        ),
        sa.ForeignKeyConstraint(
            ["circuit_id"], ["circuits.id"], name="fk_schematic_artifacts_circuit_id_circuits"
        ),
        sa.ForeignKeyConstraint(
            ["hardware_ir_id"],
            ["hardware_irs.id"],
            name="fk_schematic_artifacts_hardware_ir_id_hardware_irs",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_schematic_artifacts"),
        sa.UniqueConstraint("artifact_id", name="uq_schematic_artifacts_artifact_id"),
    )
    op.create_index("ix_schematic_artifacts_project_id", "schematic_artifacts", ["project_id"])
    op.create_index("ix_schematic_artifacts_circuit_id", "schematic_artifacts", ["circuit_id"])
    op.create_index(
        "ix_schematic_artifacts_hardware_ir_id", "schematic_artifacts", ["hardware_ir_id"]
    )

    op.create_table(
        "erc_reports",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("schematic_id", sa.String(length=36), nullable=False),
        sa.Column("schematic_revision", sa.Integer(), nullable=False),
        sa.Column("circuit_id", sa.String(length=36), nullable=False),
        sa.Column("circuit_revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=True),
        sa.Column("tool_version", sa.String(length=100), nullable=True),
        sa.Column("executed", sa.Boolean(), nullable=False),
        sa.Column("issues", sa.JSON(), nullable=False),
        sa.Column("source_revision_snapshot", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint("status IN ('PASS', 'FAIL', 'UNKNOWN')", name="status"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_erc_reports_project_id_projects"
        ),
        sa.ForeignKeyConstraint(
            ["schematic_id"],
            ["schematic_artifacts.id"],
            name="fk_erc_reports_schematic_id_schematic_artifacts",
        ),
        sa.ForeignKeyConstraint(
            ["circuit_id"], ["circuits.id"], name="fk_erc_reports_circuit_id_circuits"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_erc_reports"),
    )
    op.create_index("ix_erc_reports_project_id", "erc_reports", ["project_id"])
    op.create_index("ix_erc_reports_schematic_id", "erc_reports", ["schematic_id"])
    op.create_index("ix_erc_reports_circuit_id", "erc_reports", ["circuit_id"])


def downgrade() -> None:
    op.drop_index("ix_erc_reports_circuit_id", table_name="erc_reports")
    op.drop_index("ix_erc_reports_schematic_id", table_name="erc_reports")
    op.drop_index("ix_erc_reports_project_id", table_name="erc_reports")
    op.drop_table("erc_reports")
    op.drop_index("ix_schematic_artifacts_hardware_ir_id", table_name="schematic_artifacts")
    op.drop_index("ix_schematic_artifacts_circuit_id", table_name="schematic_artifacts")
    op.drop_index("ix_schematic_artifacts_project_id", table_name="schematic_artifacts")
    op.drop_table("schematic_artifacts")
