"""Persist M17 TestIR, TestRun, ReviewRun, and issue deduplication metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_m17_test_traceability_review"
down_revision: str | None = "0022_m16_protocol_ir"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _common_columns() -> list[sa.Column[object]]:
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
        "test_irs",
        *_common_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("requirement_ids", sa.JSON(), nullable=False),
        sa.Column("cases", sa.JSON(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("generator_version", sa.String(length=100), nullable=False),
        sa.Column("policy_version", sa.String(length=100), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "input_hash", name="uq_test_irs_project_input_hash"),
    )
    op.create_index("ix_test_irs_project_id", "test_irs", ["project_id"])

    op.create_table(
        "test_runs",
        *_common_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("test_ir_id", sa.String(length=36), nullable=False),
        sa.Column("test_ir_revision", sa.Integer(), nullable=False),
        sa.Column("test_input_hash", sa.String(length=64), nullable=False),
        sa.Column("source_revision_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("case_results", sa.JSON(), nullable=False),
        sa.Column("tool_versions", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(
            "status IN ('PASS', 'FAIL', 'UNKNOWN', 'BLOCKED', 'SKIPPED')", name="status"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["test_ir_id"], ["test_irs.id"]),
        sa.ForeignKeyConstraint(["source_revision_id"], ["source_revisions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_test_runs_project_id", "test_runs", ["project_id"])
    op.create_index("ix_test_runs_test_ir_id", "test_runs", ["test_ir_id"])
    op.create_index("ix_test_runs_source_revision_id", "test_runs", ["source_revision_id"])

    op.create_table(
        "review_runs",
        *_common_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("source_revision_id", sa.String(length=36), nullable=False),
        sa.Column("policy_version", sa.String(length=100), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("build_run_id", sa.String(length=36)),
        sa.Column("static_analysis_id", sa.String(length=36)),
        sa.Column("test_run_id", sa.String(length=36)),
        sa.Column("test_ir_id", sa.String(length=36)),
        sa.Column("test_ir_revision", sa.Integer()),
        sa.Column("protocol_id", sa.String(length=36)),
        sa.Column("protocol_revision", sa.Integer()),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("issue_ids", sa.JSON(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(
            "status IN ('PASS', 'FAIL', 'UNKNOWN', 'BLOCKED', 'SKIPPED')", name="status"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["source_revision_id"], ["source_revisions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_runs_project_id", "review_runs", ["project_id"])
    op.create_index("ix_review_runs_source_revision_id", "review_runs", ["source_revision_id"])

    with op.batch_alter_table("issues", recreate="always") as batch:
        batch.add_column(sa.Column("dedupe_key", sa.String(length=64)))
        batch.add_column(sa.Column("source_kind", sa.String(length=100)))
        batch.add_column(sa.Column("source_ref", sa.String(length=300)))
        batch.add_column(sa.Column("affected_refs", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("first_seen_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("last_seen_at", sa.DateTime(timezone=True)))
        batch.add_column(
            sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(sa.Column("last_review_id", sa.String(length=36)))
        batch.create_unique_constraint("uq_issues_project_dedupe_key", ["project_id", "dedupe_key"])
        batch.create_index("ix_issues_dedupe_key", ["dedupe_key"])


def downgrade() -> None:
    with op.batch_alter_table("issues", recreate="always") as batch:
        batch.drop_index("ix_issues_dedupe_key")
        batch.drop_constraint("uq_issues_project_dedupe_key", type_="unique")
        for name in (
            "last_review_id",
            "occurrence_count",
            "last_seen_at",
            "first_seen_at",
            "affected_refs",
            "source_ref",
            "source_kind",
            "dedupe_key",
        ):
            batch.drop_column(name)
    op.drop_index("ix_review_runs_source_revision_id", table_name="review_runs")
    op.drop_index("ix_review_runs_project_id", table_name="review_runs")
    op.drop_table("review_runs")
    op.drop_index("ix_test_runs_source_revision_id", table_name="test_runs")
    op.drop_index("ix_test_runs_test_ir_id", table_name="test_runs")
    op.drop_index("ix_test_runs_project_id", table_name="test_runs")
    op.drop_table("test_runs")
    op.drop_index("ix_test_irs_project_id", table_name="test_irs")
    op.drop_table("test_irs")
