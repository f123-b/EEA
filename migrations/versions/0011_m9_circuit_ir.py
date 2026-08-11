"""Persist M9 CircuitIR and electrical rule results.

Revision ID: 0011_m9_circuit_ir
Revises: 0010_m8_architecture_ir
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_m9_circuit_ir"
down_revision: str | None = "0010_m8_architecture_ir"
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
        "circuits",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("hardware_ir_id", sa.String(length=36), nullable=False),
        sa.Column("hardware_ir_revision", sa.Integer(), nullable=False),
        sa.Column("components", sa.JSON(), nullable=False),
        sa.Column("nets", sa.JSON(), nullable=False),
        sa.Column("power_nets", sa.JSON(), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False),
        sa.Column("requirement_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("pin_assignment_revisions", sa.JSON(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_circuits_project_id_projects"
        ),
        sa.ForeignKeyConstraint(
            ["hardware_ir_id"], ["hardware_irs.id"], name="fk_circuits_hardware_ir_id_hardware_irs"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_circuits"),
    )
    op.create_index("ix_circuits_project_id", "circuits", ["project_id"])
    op.create_index("ix_circuits_hardware_ir_id", "circuits", ["hardware_ir_id"])

    op.create_table(
        "circuit_rule_results",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("circuit_id", sa.String(length=36), nullable=False),
        sa.Column("rule_id", sa.String(length=200), nullable=False),
        sa.Column("rule_version", sa.String(length=50), nullable=False),
        sa.Column("stage", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("affected_refs", sa.JSON(), nullable=False),
        sa.Column("measured", sa.JSON(), nullable=True),
        sa.Column("threshold", sa.JSON(), nullable=True),
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
            ["project_id"], ["projects.id"], name="fk_circuit_rule_results_project_id_projects"
        ),
        sa.ForeignKeyConstraint(
            ["circuit_id"], ["circuits.id"], name="fk_circuit_rule_results_circuit_id_circuits"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_circuit_rule_results"),
    )
    op.create_index("ix_circuit_rule_results_project_id", "circuit_rule_results", ["project_id"])
    op.create_index("ix_circuit_rule_results_circuit_id", "circuit_rule_results", ["circuit_id"])


def downgrade() -> None:
    op.drop_index("ix_circuit_rule_results_circuit_id", table_name="circuit_rule_results")
    op.drop_index("ix_circuit_rule_results_project_id", table_name="circuit_rule_results")
    op.drop_table("circuit_rule_results")
    op.drop_index("ix_circuits_hardware_ir_id", table_name="circuits")
    op.drop_index("ix_circuits_project_id", table_name="circuits")
    op.drop_table("circuits")
