"""Persist M7 pin plans, assignments, locks, and rule results.

Revision ID: 0009_m7_pin_planner
Revises: 0008_m6_review_fixes
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_m7_pin_planner"
down_revision: str | None = "0008_m6_review_fixes"
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
        "pin_plans",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("analysis_id", sa.String(length=36), nullable=True),
        sa.Column("device_ref", sa.String(length=200), nullable=False),
        sa.Column("package", sa.String(length=100), nullable=True),
        sa.Column("requirements", sa.JSON(), nullable=False),
        sa.Column("candidates", sa.JSON(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_pin_plans_project_id_projects"
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["requirement_analyses.id"],
            name="fk_pin_plans_analysis_id_requirement_analyses",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pin_plans"),
    )
    op.create_index("ix_pin_plans_project_id", "pin_plans", ["project_id"])
    op.create_index("ix_pin_plans_analysis_id", "pin_plans", ["analysis_id"])

    op.create_table(
        "pin_assignments",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("requirement_id", sa.String(length=36), nullable=False),
        sa.Column("device_ref", sa.String(length=200), nullable=False),
        sa.Column("package", sa.String(length=100), nullable=True),
        sa.Column("pin_name", sa.String(length=50), nullable=False),
        sa.Column("function", sa.JSON(), nullable=False),
        sa.Column("locked", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("claim_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint("score >= 0 AND score <= 1", name="score_range"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_pin_assignments_project_id_projects"
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["pin_plans.id"], name="fk_pin_assignments_plan_id_pin_plans"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pin_assignments"),
        sa.UniqueConstraint("plan_id", "pin_name", name="uq_pin_assignments_plan_pin"),
    )
    op.create_index("ix_pin_assignments_project_id", "pin_assignments", ["project_id"])
    op.create_index("ix_pin_assignments_plan_id", "pin_assignments", ["plan_id"])
    op.create_index("ix_pin_assignments_requirement_id", "pin_assignments", ["requirement_id"])

    op.create_table(
        "pin_locks",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("assignment_id", sa.String(length=36), nullable=False),
        sa.Column("locked_by", sa.String(length=200), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("released_by", sa.String(length=200), nullable=True),
        sa.Column("released_reason", sa.Text(), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_pin_locks_project_id_projects"
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["pin_assignments.id"],
            name="fk_pin_locks_assignment_id_pin_assignments",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pin_locks"),
    )
    op.create_index("ix_pin_locks_project_id", "pin_locks", ["project_id"])
    op.create_index("ix_pin_locks_assignment_id", "pin_locks", ["assignment_id"])
    op.create_index("ix_pin_locks_active", "pin_locks", ["active"])

    op.create_table(
        "pin_rule_results",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
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
            "stage IN ("
            "'PRE_GENERATION', 'POST_GENERATION', 'PRE_TOOL', 'POST_TOOL', 'RELEASE_GATE'"
            ")",
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
            ["project_id"], ["projects.id"], name="fk_pin_rule_results_project_id_projects"
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["pin_plans.id"], name="fk_pin_rule_results_plan_id_pin_plans"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pin_rule_results"),
    )
    op.create_index("ix_pin_rule_results_project_id", "pin_rule_results", ["project_id"])
    op.create_index("ix_pin_rule_results_plan_id", "pin_rule_results", ["plan_id"])


def downgrade() -> None:
    op.drop_index("ix_pin_rule_results_plan_id", table_name="pin_rule_results")
    op.drop_index("ix_pin_rule_results_project_id", table_name="pin_rule_results")
    op.drop_table("pin_rule_results")
    op.drop_index("ix_pin_locks_active", table_name="pin_locks")
    op.drop_index("ix_pin_locks_assignment_id", table_name="pin_locks")
    op.drop_index("ix_pin_locks_project_id", table_name="pin_locks")
    op.drop_table("pin_locks")
    op.drop_index("ix_pin_assignments_requirement_id", table_name="pin_assignments")
    op.drop_index("ix_pin_assignments_plan_id", table_name="pin_assignments")
    op.drop_index("ix_pin_assignments_project_id", table_name="pin_assignments")
    op.drop_table("pin_assignments")
    op.drop_index("ix_pin_plans_analysis_id", table_name="pin_plans")
    op.drop_index("ix_pin_plans_project_id", table_name="pin_plans")
    op.drop_table("pin_plans")
