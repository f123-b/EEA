"""M23 structured knowledge and memory records."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_m23_knowledge_memory"
down_revision: str | None = "0034_m22_existing_project_import"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("schema_version", sa.String(length=30), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("scope", sa.String(length=40), nullable=False),
        sa.Column("owner_ref", sa.String(length=200), nullable=True),
        sa.Column("organization_ref", sa.String(length=200), nullable=True),
        sa.Column("task_ref", sa.String(length=200), nullable=True),
        sa.Column("knowledge_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("applicability", sa.JSON(), nullable=False),
        sa.Column("claim_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("source_revision_id", sa.String(length=36), nullable=True),
        sa.Column("source_ref", sa.String(length=2000), nullable=True),
        sa.Column("source_version", sa.String(length=200), nullable=True),
        sa.Column("authority_level", sa.String(length=30), nullable=False),
        sa.Column("verification_levels", sa.JSON(), nullable=False),
        sa.Column("trust_level", sa.String(length=20), nullable=False),
        sa.Column("lifecycle", sa.String(length=30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("freshness_score", sa.Float(), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("license_ref", sa.String(length=500), nullable=True),
        sa.Column("usage_policy", sa.String(length=2000), nullable=True),
        sa.Column("related_entry_ids", sa.JSON(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column("reviewed_by", sa.String(length=200), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(
            "scope IN ('GLOBAL_PUBLIC', 'USER_PRIVATE', 'PROJECT_PRIVATE', "
            "'ORGANIZATION_PRIVATE', 'TASK_ONLY')",
            name="scope",
        ),
        sa.CheckConstraint(
            "knowledge_type IN ('CLAIM_SET', 'REFERENCE_ARCHITECTURE', 'PATTERN', "
            "'ANTI_PATTERN', 'DEBUG_CASE', 'ADR', 'PROJECT_EXPERIENCE', 'NOTE', "
            "'TASK_WORKING')",
            name="knowledge_type",
        ),
        sa.CheckConstraint(
            "authority_level IN ('T0_OFFICIAL', 'T1_VENDOR', 'T2_MAINTAINER', "
            "'T3_REVIEWED', 'T4_PROJECT', 'T5_USER', 'T6_AI_INFERENCE')",
            name="authority_level",
        ),
        sa.CheckConstraint(
            "trust_level IN ('UNTRUSTED', 'LOW', 'MEDIUM', 'HIGH', 'TRUSTED')",
            name="trust_level",
        ),
        sa.CheckConstraint(
            "lifecycle IN ('CANDIDATE', 'ACTIVE', 'TRUSTED', 'STALE', 'CONFLICTED', "
            "'DEPRECATED', 'ARCHIVED', 'REJECTED')",
            name="lifecycle",
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        sa.CheckConstraint("freshness_score >= 0 AND freshness_score <= 1", name="freshness_range"),
        sa.CheckConstraint(
            "scope NOT IN ('PROJECT_PRIVATE', 'TASK_ONLY') OR project_id IS NOT NULL",
            name="project_scope_requires_project",
        ),
        sa.CheckConstraint(
            "scope <> 'USER_PRIVATE' OR owner_ref IS NOT NULL", name="user_scope_requires_owner"
        ),
        sa.CheckConstraint(
            "scope <> 'ORGANIZATION_PRIVATE' OR organization_ref IS NOT NULL",
            name="organization_scope_requires_organization",
        ),
        sa.CheckConstraint(
            "scope <> 'TASK_ONLY' OR task_ref IS NOT NULL", name="task_scope_requires_task"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["source_revision_id"], ["source_revisions.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_entries"),
    )
    op.create_index("ix_knowledge_entries_project_id", "knowledge_entries", ["project_id"])
    op.create_index("ix_knowledge_entries_scope", "knowledge_entries", ["scope"])
    op.create_index("ix_knowledge_entries_knowledge_type", "knowledge_entries", ["knowledge_type"])
    op.create_index("ix_knowledge_entries_title", "knowledge_entries", ["title"])
    op.create_index(
        "ix_knowledge_entries_source_revision_id", "knowledge_entries", ["source_revision_id"]
    )
    op.create_index("ix_knowledge_entries_lifecycle", "knowledge_entries", ["lifecycle"])
    op.create_index(
        "ix_knowledge_entries_scope_lifecycle",
        "knowledge_entries",
        ["scope", "lifecycle"],
    )

    op.create_table(
        "knowledge_recall_audits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("schema_version", sa.String(length=30), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("actor_ref", sa.String(length=200), nullable=False),
        sa.Column("query", sa.String(length=2000), nullable=False),
        sa.Column("scope_context", sa.JSON(), nullable=False),
        sa.Column("result_ids", sa.JSON(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=200), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_recall_audits"),
    )
    op.create_index(
        "ix_knowledge_recall_audits_project_id", "knowledge_recall_audits", ["project_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_recall_audits_project_id", table_name="knowledge_recall_audits")
    op.drop_table("knowledge_recall_audits")
    op.drop_index("ix_knowledge_entries_scope_lifecycle", table_name="knowledge_entries")
    op.drop_index("ix_knowledge_entries_lifecycle", table_name="knowledge_entries")
    op.drop_index("ix_knowledge_entries_source_revision_id", table_name="knowledge_entries")
    op.drop_index("ix_knowledge_entries_title", table_name="knowledge_entries")
    op.drop_index("ix_knowledge_entries_knowledge_type", table_name="knowledge_entries")
    op.drop_index("ix_knowledge_entries_scope", table_name="knowledge_entries")
    op.drop_index("ix_knowledge_entries_project_id", table_name="knowledge_entries")
    op.drop_table("knowledge_entries")
