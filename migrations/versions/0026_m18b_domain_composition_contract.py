"""Persist the M18B project-scoped Domain composition contract."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_m18b_domain_composition_contract"
down_revision: str | None = "0025_m18a_transactional_outbox_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "domain_composition_states",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("schema_version", sa.String(length=30), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("active_domain_ids", sa.JSON(), nullable=False),
        sa.Column("ordered_domain_ids", sa.JSON(), nullable=False),
        sa.Column("selected_capabilities", sa.JSON(), nullable=False),
        sa.Column("capability_routes", sa.JSON(), nullable=False),
        sa.Column("dependency_edges", sa.JSON(), nullable=False),
        sa.Column("domain_snapshots", sa.JSON(), nullable=False),
        sa.Column("rule_order", sa.JSON(), nullable=False),
        sa.Column("generator_order", sa.JSON(), nullable=False),
        sa.Column("plan_hash", sa.String(length=64), nullable=False),
        sa.Column("updated_by", sa.String(length=200), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint("length(plan_hash) = 64", name="plan_hash_length"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_domain_composition_states_project"),
    )
    op.create_index(
        "ix_domain_composition_states_project_id",
        "domain_composition_states",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_domain_composition_states_project_id",
        table_name="domain_composition_states",
    )
    op.drop_table("domain_composition_states")
