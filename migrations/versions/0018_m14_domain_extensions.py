"""Persist project-scoped Domain Extension activation state."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_m14_domain_extensions"
down_revision: str | None = "0017_project_scope_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "domain_activations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("schema_version", sa.String(length=30), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("domain_id", sa.String(length=200), nullable=False),
        sa.Column("plugin_id", sa.String(length=200), nullable=False),
        sa.Column("plugin_version", sa.String(length=100), nullable=False),
        sa.Column("domain_schema_version", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_by", sa.String(length=200), nullable=False),
        sa.Column("capability_snapshot", sa.JSON(), nullable=False),
        sa.Column("dependency_snapshot", sa.JSON(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'DISABLED', 'INCOMPATIBLE', 'BLOCKED')", name="status"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.UniqueConstraint("project_id", "domain_id", name="uq_domain_activations_project_domain"),
        sa.PrimaryKeyConstraint("id", name="pk_domain_activations"),
    )
    op.create_index("ix_domain_activations_project_id", "domain_activations", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_domain_activations_project_id", table_name="domain_activations")
    op.drop_table("domain_activations")
