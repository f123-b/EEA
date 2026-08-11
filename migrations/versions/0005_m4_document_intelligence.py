"""Create M4 document and DocumentIR persistence tables.

Revision ID: 0005_m4
Revises: 0004_m3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_m4"
down_revision: str | None = "0004_m3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DOCUMENT_TYPES = (
    "DATASHEET",
    "REFERENCE_MANUAL",
    "ERRATA",
    "APPLICATION_NOTE",
    "USER_DOCUMENT",
    "UNKNOWN",
)
PARSE_STATUSES = ("UPLOADED", "PARSING", "PARSED", "FAILED")


def _values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _entity_columns() -> list[sa.Column[object]]:
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
        "documents",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("document_type", sa.String(length=40), nullable=False),
        sa.Column("vendor", sa.String(length=200), nullable=True),
        sa.Column("product", sa.String(length=200), nullable=True),
        sa.Column("version_label", sa.String(length=100), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_uri", sa.String(length=2000), nullable=False),
        sa.Column("parse_status", sa.String(length=30), nullable=False),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(f"document_type IN ({_values(DOCUMENT_TYPES)})", name="document_type"),
        sa.CheckConstraint(f"parse_status IN ({_values(PARSE_STATUSES)})", name="parse_status"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_documents_project_id_projects"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.UniqueConstraint("content_hash", name="uq_documents_content_hash"),
    )
    op.create_index("ix_documents_project_id", "documents", ["project_id"])

    op.create_table(
        "document_irs",
        *_entity_columns(),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("parser", sa.String(length=200), nullable=False),
        sa.Column("parser_version", sa.String(length=100), nullable=False),
        sa.Column("pages", sa.JSON(), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("tables", sa.JSON(), nullable=False),
        sa.Column("figures", sa.JSON(), nullable=False),
        sa.Column("extracted_claim_ids", sa.JSON(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], name="fk_document_irs_document_id_documents"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_irs"),
        sa.UniqueConstraint("document_id", name="uq_document_irs_document_id"),
    )
    op.create_index("ix_document_irs_document_id", "document_irs", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_document_irs_document_id", table_name="document_irs")
    op.drop_table("document_irs")
    op.drop_index("ix_documents_project_id", table_name="documents")
    op.drop_table("documents")
