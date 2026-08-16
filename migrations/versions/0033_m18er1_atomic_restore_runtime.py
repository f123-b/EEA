"""M18ER.1 durable runtime and atomic restore operation journal."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_m18er1_atomic_restore_runtime"
down_revision: str | None = "0032_m18er_reliability_closure"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "restore_operations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False),
        sa.Column("staging_path", sa.String(length=2000), nullable=False),
        sa.Column("destination_path", sa.String(length=2000), nullable=False),
        sa.Column("actor_id", sa.String(length=200), nullable=False),
        sa.Column("source_revision_id", sa.String(length=36), nullable=True),
        sa.Column("source_revision_hash", sa.String(length=64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "state IN ("
            "'VALIDATED', 'STAGED', 'PREPARED', 'FS_ACTIVATED', "
            "'ACTIVATED', 'ROLLBACK_REQUIRED', 'FAILED')",
            name="restore_operation_state",
        ),
        sa.CheckConstraint("length(manifest_hash) = 64", name="restore_manifest_hash_length"),
        sa.PrimaryKeyConstraint("id", name="pk_restore_operations"),
    )
    op.create_index(
        "ix_restore_operations_state_updated",
        "restore_operations",
        ["state", "updated_at"],
    )
    op.create_index("ix_restore_operations_project", "restore_operations", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_restore_operations_project", table_name="restore_operations")
    op.drop_index("ix_restore_operations_state_updated", table_name="restore_operations")
    op.drop_table("restore_operations")
