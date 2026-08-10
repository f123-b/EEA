"""Create M0 system metadata table.

Revision ID: 0001_m0
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_m0"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the bootstrap metadata table."""

    op.create_table(
        "system_metadata",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_system_metadata")),
        sa.UniqueConstraint("key", name=op.f("uq_system_metadata_key")),
    )
    op.bulk_insert(
        sa.table(
            "system_metadata",
            sa.column("key", sa.String()),
            sa.column("value", sa.String()),
        ),
        [{"key": "schema_version", "value": revision}],
    )


def downgrade() -> None:
    """Remove the bootstrap metadata table."""

    op.drop_table("system_metadata")
