"""Persist project-scoped M16 ProtocolIR revision history."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_m16_protocol_ir"
down_revision: str | None = "0021_m14_domain_configuration_error_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "protocols",
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("schema_version", sa.String(length=30), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("version_label", sa.String(length=100), nullable=False),
        sa.Column("transports", sa.JSON(), nullable=False),
        sa.Column("messages", sa.JSON(), nullable=False),
        sa.Column("requirement_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint("status IN ('CURRENT', 'STALE')", name="status"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("record_id", name="pk_protocols"),
        sa.UniqueConstraint("id", "revision", name="uq_protocols_id_revision"),
    )
    op.create_index("ix_protocols_id", "protocols", ["id"])
    op.create_index("ix_protocols_project_id", "protocols", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_protocols_project_id", table_name="protocols")
    op.drop_index("ix_protocols_id", table_name="protocols")
    op.drop_table("protocols")
