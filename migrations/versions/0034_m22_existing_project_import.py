"""M22 durable existing-project import sessions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_m22_existing_project_import"
down_revision: str | None = "0033_m18er1_atomic_restore_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("schema_version", sa.String(length=30), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_locator", sa.JSON(), nullable=False),
        sa.Column("requested_ref", sa.String(length=300), nullable=True),
        sa.Column("resolved_commit", sa.String(length=100), nullable=True),
        sa.Column("staging_path", sa.String(length=2000), nullable=False),
        sa.Column("workspace_path", sa.String(length=2000), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("scan_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_manifest_hash", sa.String(length=64), nullable=True),
        sa.Column("file_manifest", sa.JSON(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("issues", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("scan_result", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "source_type IN ('LOCAL_FOLDER', 'GIT_REPOSITORY', 'ARCHIVE')",
            name="source_type",
        ),
        sa.CheckConstraint(
            "status IN ('CREATED', 'SCANNED', 'REVIEWED', 'WORKSPACE_CREATED', 'FAILED')",
            name="status",
        ),
        sa.CheckConstraint("scan_revision >= 0", name="scan_revision_non_negative"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_import_sessions"),
    )
    op.create_index("ix_import_sessions_project_id", "import_sessions", ["project_id"])
    op.create_index("ix_import_sessions_status", "import_sessions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_import_sessions_status", table_name="import_sessions")
    op.drop_index("ix_import_sessions_project_id", table_name="import_sessions")
    op.drop_table("import_sessions")
