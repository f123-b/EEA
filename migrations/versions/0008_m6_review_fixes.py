"""Add canonical references for M6 requirement analyses.

Revision ID: 0008_m6_review_fixes
Revises: 0007_m6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_m6_review_fixes"
down_revision: str | None = "0007_m6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "requirement_analyses",
        sa.Column("requirement_ids", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "requirement_analyses",
        sa.Column("claim_ids", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("requirement_analyses", "claim_ids")
    op.drop_column("requirement_analyses", "requirement_ids")
