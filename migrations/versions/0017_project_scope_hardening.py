"""Separate document metadata identity from cross-project blob deduplication.

Revision ID: 0017_project_scope_hardening
Revises: 0016_m13_firmware_static_analysis
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017_project_scope_hardening"
down_revision: str | None = "0016_m13_firmware_static_analysis"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_constraint("uq_documents_content_hash", type_="unique")
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"])


def downgrade() -> None:
    op.drop_index("ix_documents_content_hash", table_name="documents")
    with op.batch_alter_table("documents") as batch_op:
        batch_op.create_unique_constraint("uq_documents_content_hash", ["content_hash"])
