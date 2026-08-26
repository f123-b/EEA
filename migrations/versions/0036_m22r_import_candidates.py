"""M22R normalized import candidates, reviews, and apply conflicts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036_m22r_import_candidates"
down_revision: str | None = "0035_m23_knowledge_memory"
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
        "import_candidates",
        *_common_columns(),
        sa.Column("import_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("source_scan_revision", sa.Integer(), nullable=False),
        sa.Column("source_revision_id", sa.String(length=36), nullable=True),
        sa.Column("candidate_type", sa.String(length=40), nullable=False),
        sa.Column("semantic_key", sa.String(length=500), nullable=False),
        sa.Column("proposed_value", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_kind", sa.String(length=100), nullable=False),
        sa.Column("source_ref", sa.String(length=2000), nullable=False),
        sa.Column("source_file", sa.String(length=2000), nullable=False),
        sa.Column("source_location", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("parser_name", sa.String(length=100), nullable=False),
        sa.Column("parser_version", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("canonical_ref", sa.String(length=500), nullable=True),
        sa.Column("apply_revision", sa.Integer(), nullable=True),
        sa.Column("apply_evidence", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        sa.CheckConstraint(
            "status IN ('DETECTED', 'UNKNOWN', 'CONFLICTED', 'ACCEPTED_CANDIDATE', "
            "'EDITED_CANDIDATE', 'REJECTED', 'APPLIED', 'STALE')",
            name="status",
        ),
        sa.ForeignKeyConstraint(["import_id"], ["import_sessions.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["source_revision_id"], ["source_revisions.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_import_candidates"),
        sa.UniqueConstraint(
            "import_id",
            "source_scan_revision",
            "semantic_key",
            name="uq_import_candidate_scan_key",
        ),
    )
    op.create_index("ix_import_candidates_import_id", "import_candidates", ["import_id"])
    op.create_index("ix_import_candidates_project_id", "import_candidates", ["project_id"])
    op.create_index(
        "ix_import_candidates_source_revision_id",
        "import_candidates",
        ["source_revision_id"],
    )
    op.create_index("ix_import_candidates_candidate_type", "import_candidates", ["candidate_type"])
    op.create_index("ix_import_candidates_semantic_key", "import_candidates", ["semantic_key"])
    op.create_index("ix_import_candidates_status", "import_candidates", ["status"])

    op.create_table(
        "import_candidate_reviews",
        *_common_columns(),
        sa.Column("import_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("expected_candidate_revision", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("from_status", sa.String(length=30), nullable=False),
        sa.Column("to_status", sa.String(length=30), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.String(length=200), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.ForeignKeyConstraint(["import_id"], ["import_sessions.id"]),
        sa.ForeignKeyConstraint(["candidate_id"], ["import_candidates.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_import_candidate_reviews"),
    )
    op.create_index(
        "ix_import_candidate_reviews_import_id",
        "import_candidate_reviews",
        ["import_id"],
    )
    op.create_index(
        "ix_import_candidate_reviews_candidate_id",
        "import_candidate_reviews",
        ["candidate_id"],
    )

    op.create_table(
        "import_conflicts",
        *_common_columns(),
        sa.Column("import_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("conflict_kind", sa.String(length=40), nullable=False),
        sa.Column("canonical_type", sa.String(length=100), nullable=False),
        sa.Column("canonical_ref", sa.String(length=500), nullable=True),
        sa.Column("before_value", sa.JSON(), nullable=True),
        sa.Column("after_value", sa.JSON(), nullable=True),
        sa.Column("source_revision_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint("status IN ('OPEN', 'RESOLVED', 'BLOCKED')", name="status"),
        sa.ForeignKeyConstraint(["import_id"], ["import_sessions.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["candidate_id"], ["import_candidates.id"]),
        sa.ForeignKeyConstraint(["source_revision_id"], ["source_revisions.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_import_conflicts"),
    )
    op.create_index("ix_import_conflicts_import_id", "import_conflicts", ["import_id"])
    op.create_index("ix_import_conflicts_project_id", "import_conflicts", ["project_id"])
    op.create_index("ix_import_conflicts_candidate_id", "import_conflicts", ["candidate_id"])
    op.create_index(
        "ix_import_conflicts_source_revision_id",
        "import_conflicts",
        ["source_revision_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_import_conflicts_source_revision_id", table_name="import_conflicts")
    op.drop_index("ix_import_conflicts_candidate_id", table_name="import_conflicts")
    op.drop_index("ix_import_conflicts_project_id", table_name="import_conflicts")
    op.drop_index("ix_import_conflicts_import_id", table_name="import_conflicts")
    op.drop_table("import_conflicts")
    op.drop_index("ix_import_candidate_reviews_candidate_id", table_name="import_candidate_reviews")
    op.drop_index("ix_import_candidate_reviews_import_id", table_name="import_candidate_reviews")
    op.drop_table("import_candidate_reviews")
    op.drop_index("ix_import_candidates_status", table_name="import_candidates")
    op.drop_index("ix_import_candidates_semantic_key", table_name="import_candidates")
    op.drop_index("ix_import_candidates_candidate_type", table_name="import_candidates")
    op.drop_index("ix_import_candidates_source_revision_id", table_name="import_candidates")
    op.drop_index("ix_import_candidates_project_id", table_name="import_candidates")
    op.drop_index("ix_import_candidates_import_id", table_name="import_candidates")
    op.drop_table("import_candidates")
