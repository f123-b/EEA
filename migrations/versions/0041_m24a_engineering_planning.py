"""Create the M24A engineering planning persistence boundary."""

# Alembic table declarations are kept close to their SQL shape for auditability.

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041_m24a_engineering_planning"
down_revision: str | None = "0040_m23l_m23r_memory_trust_closure"
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


def _revision_check() -> sa.CheckConstraint:
    return sa.CheckConstraint("revision >= 1", name="revision_positive")


def upgrade() -> None:
    op.create_table(
        "engineering_requirements",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("requirement_type", sa.String(length=40), nullable=False),
        sa.Column("priority", sa.String(length=30), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False),
        sa.Column("acceptance_criteria", sa.JSON(), nullable=False),
        sa.Column("source", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        _revision_check(),
        sa.CheckConstraint(
            "requirement_type IN ('FEATURE', 'BUG_FIX', 'PERFORMANCE', 'RELIABILITY', "
            "'HARDWARE_CHANGE', 'FIRMWARE_CHANGE', 'PROTOCOL_CHANGE', 'BUILD_CHANGE', "
            "'TEST_CHANGE', 'REFACTOR', 'INVESTIGATION')",
            name="requirement_type",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'READY', 'ANALYZING', 'PLANNED', 'NEEDS_INPUT', 'BLOCKED', "
            "'APPROVED', 'REJECTED', 'ARCHIVED')",
            name="status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_engineering_requirements"),
    )
    op.create_index(
        "ix_engineering_requirements_project_id", "engineering_requirements", ["project_id"]
    )

    op.create_table(
        "planning_context_snapshots",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("source_revision_id", sa.String(length=36), nullable=True),
        sa.Column("selected_context", sa.JSON(), nullable=False),
        sa.Column("excluded_context", sa.JSON(), nullable=False),
        sa.Column("selection_reason", sa.JSON(), nullable=False),
        sa.Column("claim_revisions", sa.JSON(), nullable=False),
        sa.Column("evidence_revisions", sa.JSON(), nullable=False),
        sa.Column("memory_refs", sa.JSON(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("source_content_is_untrusted", sa.Boolean(), nullable=False),
        _revision_check(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["source_revision_id"], ["source_revisions.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_planning_context_snapshots"),
    )
    op.create_index(
        "ix_planning_context_snapshots_project_id", "planning_context_snapshots", ["project_id"]
    )
    op.create_index(
        "ix_planning_context_snapshots_source_revision_id",
        "planning_context_snapshots",
        ["source_revision_id"],
    )

    op.create_table(
        "engineering_plans",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("requirement_id", sa.String(length=36), nullable=False),
        sa.Column("source_revision_id", sa.String(length=36), nullable=True),
        sa.Column("context_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("affected_components", sa.JSON(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("memory_refs", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(length=200), nullable=False),
        sa.Column("model_version", sa.String(length=200), nullable=False),
        sa.Column("prompt_template_version", sa.String(length=100), nullable=False),
        sa.Column("planning_policy_version", sa.String(length=100), nullable=False),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column("supersedes_plan_id", sa.String(length=36), nullable=True),
        sa.Column("validation_issues", sa.JSON(), nullable=False),
        sa.Column("quality_issues", sa.JSON(), nullable=False),
        sa.Column("plan_only", sa.Boolean(), nullable=False),
        _revision_check(),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'READY_FOR_REVIEW', 'NEEDS_INPUT', 'BLOCKED', 'APPROVED', "
            "'REJECTED', 'SUPERSEDED', 'STALE')",
            name="status",
        ),
        sa.CheckConstraint("plan_only = 1", name="plan_only"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["requirement_id"], ["engineering_requirements.id"]),
        sa.ForeignKeyConstraint(["source_revision_id"], ["source_revisions.id"]),
        sa.ForeignKeyConstraint(["context_snapshot_id"], ["planning_context_snapshots.id"]),
        sa.ForeignKeyConstraint(["supersedes_plan_id"], ["engineering_plans.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_engineering_plans"),
    )
    for column in (
        "project_id",
        "requirement_id",
        "source_revision_id",
        "context_snapshot_id",
        "status",
        "supersedes_plan_id",
    ):
        op.create_index(f"ix_engineering_plans_{column}", "engineering_plans", [column])

    op.create_table(
        "engineering_plan_steps",
        *_entity_columns(),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("action_type", sa.String(length=40), nullable=False),
        sa.Column("target_type", sa.String(length=60), nullable=False),
        sa.Column("target_ref", sa.String(length=2000), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("dependencies", sa.JSON(), nullable=False),
        sa.Column("preconditions", sa.JSON(), nullable=False),
        sa.Column("expected_result", sa.Text(), nullable=False),
        sa.Column("verification_plan", sa.JSON(), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        _revision_check(),
        sa.ForeignKeyConstraint(["plan_id"], ["engineering_plans.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_engineering_plan_steps"),
        sa.UniqueConstraint("plan_id", "step_order", name="uq_engineering_plan_steps_order"),
    )
    op.create_index("ix_engineering_plan_steps_plan_id", "engineering_plan_steps", ["plan_id"])

    op.create_table(
        "engineering_plan_changes",
        *_entity_columns(),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("change_type", sa.String(length=40), nullable=False),
        sa.Column("target_kind", sa.String(length=60), nullable=False),
        sa.Column("target_ref", sa.String(length=2000), nullable=False),
        sa.Column("current_state", sa.JSON(), nullable=True),
        sa.Column("proposed_state", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("impact", sa.Text(), nullable=False),
        sa.Column("risk", sa.String(length=20), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("expected_diff_intent", sa.Text(), nullable=False),
        _revision_check(),
        sa.CheckConstraint(
            "status IN ('PROPOSED', 'ACCEPTED', 'REJECTED', 'NEEDS_REVISION', 'BLOCKED')",
            name="status",
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["engineering_plans.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_engineering_plan_changes"),
    )
    op.create_index("ix_engineering_plan_changes_plan_id", "engineering_plan_changes", ["plan_id"])

    nested_tables = (
        (
            "engineering_plan_risks",
            [
                sa.Column("category", sa.String(40), nullable=False),
                sa.Column("severity", sa.String(20), nullable=False),
                sa.Column("likelihood", sa.String(20), nullable=False),
                sa.Column("description", sa.Text(), nullable=False),
                sa.Column("affected_ref", sa.String(500), nullable=False),
                sa.Column("mitigation", sa.Text(), nullable=False),
                sa.Column("verification", sa.Text(), nullable=False),
                sa.Column("reason", sa.Text(), nullable=False),
                sa.Column("evidence_refs", sa.JSON(), nullable=False),
            ],
        ),
        (
            "engineering_plan_assumptions",
            [
                sa.Column("description", sa.Text(), nullable=False),
                sa.Column("basis", sa.Text(), nullable=False),
                sa.Column("confidence", sa.String(20), nullable=False),
                sa.Column("evidence_refs", sa.JSON(), nullable=False),
                sa.Column("validation_required", sa.Boolean(), nullable=False),
            ],
        ),
        (
            "engineering_plan_unknowns",
            [
                sa.Column("question", sa.Text(), nullable=False),
                sa.Column("why_needed", sa.Text(), nullable=False),
                sa.Column("blocking", sa.Boolean(), nullable=False),
                sa.Column("recommended_resolution", sa.Text(), nullable=False),
                sa.Column("related_refs", sa.JSON(), nullable=False),
            ],
        ),
        (
            "engineering_plan_acceptance_mappings",
            [
                sa.Column("criterion", sa.Text(), nullable=False),
                sa.Column("step_ids", sa.JSON(), nullable=False),
                sa.Column("verification_refs", sa.JSON(), nullable=False),
            ],
        ),
    )
    for table, nested_columns in nested_tables:
        columns = [
            *_entity_columns(),
            sa.Column("plan_id", sa.String(length=36), nullable=False),
            *nested_columns,
        ]
        op.create_table(
            table,
            *columns,
            _revision_check(),
            sa.ForeignKeyConstraint(["plan_id"], ["engineering_plans.id"]),
            sa.PrimaryKeyConstraint("id", name=f"pk_{table}"),
        )
        op.create_index(f"ix_{table}_plan_id", table, ["plan_id"])

    op.create_table(
        "engineering_plan_verifications",
        *_entity_columns(),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("change_id", sa.String(length=36), nullable=False),
        sa.Column("method", sa.String(length=500), nullable=False),
        sa.Column("expected_result", sa.Text(), nullable=False),
        sa.Column("execution_allowed_in_m24a", sa.Boolean(), nullable=False),
        _revision_check(),
        sa.CheckConstraint("execution_allowed_in_m24a = 0", name="execution_allowed_in_m24a"),
        sa.ForeignKeyConstraint(["plan_id"], ["engineering_plans.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_engineering_plan_verifications"),
    )
    op.create_index(
        "ix_engineering_plan_verifications_plan_id", "engineering_plan_verifications", ["plan_id"]
    )

    op.create_table(
        "engineering_plan_reviews",
        *_entity_columns(),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("expected_plan_revision", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.String(200), nullable=False),
        sa.Column("execution_authorized", sa.Boolean(), nullable=False),
        _revision_check(),
        sa.CheckConstraint("execution_authorized = 0", name="execution_authorized"),
        sa.CheckConstraint("action IN ('APPROVE', 'REJECT', 'REQUEST_REVISION')", name="action"),
        sa.ForeignKeyConstraint(["plan_id"], ["engineering_plans.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_engineering_plan_reviews"),
    )
    op.create_index("ix_engineering_plan_reviews_plan_id", "engineering_plan_reviews", ["plan_id"])

    op.create_table(
        "engineering_plan_review_comments",
        *_entity_columns(),
        sa.Column("plan_id", sa.String(36), nullable=False),
        sa.Column("target_kind", sa.String(100), nullable=False),
        sa.Column("target_ref", sa.String(500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(200), nullable=False),
        _revision_check(),
        sa.ForeignKeyConstraint(["plan_id"], ["engineering_plans.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_engineering_plan_review_comments"),
    )
    op.create_index(
        "ix_engineering_plan_review_comments_plan_id",
        "engineering_plan_review_comments",
        ["plan_id"],
    )

    op.create_table(
        "engineering_planning_audits",
        *_entity_columns(),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("requirement_id", sa.String(36), nullable=True),
        sa.Column("plan_id", sa.String(36), nullable=True),
        sa.Column("principal_id", sa.String(200), nullable=False),
        sa.Column("user_id", sa.String(200), nullable=False),
        sa.Column("session_id", sa.String(200), nullable=False),
        sa.Column("request_id", sa.String(200), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("before", sa.JSON(), nullable=False),
        sa.Column("after", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        _revision_check(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["requirement_id"], ["engineering_requirements.id"]),
        sa.ForeignKeyConstraint(["plan_id"], ["engineering_plans.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_engineering_planning_audits"),
    )
    for column in ("project_id", "requirement_id", "plan_id", "principal_id", "user_id", "action"):
        op.create_index(
            f"ix_engineering_planning_audits_{column}", "engineering_planning_audits", [column]
        )


def downgrade() -> None:
    for column in ("action", "user_id", "principal_id", "plan_id", "requirement_id", "project_id"):
        op.drop_index(
            f"ix_engineering_planning_audits_{column}", table_name="engineering_planning_audits"
        )
    op.drop_table("engineering_planning_audits")
    op.drop_index(
        "ix_engineering_plan_review_comments_plan_id", table_name="engineering_plan_review_comments"
    )
    op.drop_table("engineering_plan_review_comments")
    op.drop_index("ix_engineering_plan_reviews_plan_id", table_name="engineering_plan_reviews")
    op.drop_table("engineering_plan_reviews")
    op.drop_index(
        "ix_engineering_plan_verifications_plan_id", table_name="engineering_plan_verifications"
    )
    op.drop_table("engineering_plan_verifications")
    for table in (
        "engineering_plan_acceptance_mappings",
        "engineering_plan_unknowns",
        "engineering_plan_assumptions",
        "engineering_plan_risks",
    ):
        op.drop_index(f"ix_{table}_plan_id", table_name=table)
        op.drop_table(table)
    op.drop_index("ix_engineering_plan_changes_plan_id", table_name="engineering_plan_changes")
    op.drop_table("engineering_plan_changes")
    op.drop_index("ix_engineering_plan_steps_plan_id", table_name="engineering_plan_steps")
    op.drop_table("engineering_plan_steps")
    for column in (
        "supersedes_plan_id",
        "status",
        "context_snapshot_id",
        "source_revision_id",
        "requirement_id",
        "project_id",
    ):
        op.drop_index(f"ix_engineering_plans_{column}", table_name="engineering_plans")
    op.drop_table("engineering_plans")
    op.drop_index(
        "ix_planning_context_snapshots_source_revision_id", table_name="planning_context_snapshots"
    )
    op.drop_index(
        "ix_planning_context_snapshots_project_id", table_name="planning_context_snapshots"
    )
    op.drop_table("planning_context_snapshots")
    op.drop_index("ix_engineering_requirements_project_id", table_name="engineering_requirements")
    op.drop_table("engineering_requirements")
