"""Close M18C source mutation ownership, CAS, and crash recovery semantics."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_m18cr_source_mutation_cas_recovery"
down_revision: str | None = "0027_m18c_source_authority"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("source_workspaces") as batch:
        batch.add_column(sa.Column("active_mutation_id", sa.String(length=36), nullable=True))
        batch.add_column(
            sa.Column("active_mutation_started_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(
            sa.Column("active_mutation_expected_revision", sa.Integer(), nullable=True)
        )
    op.create_index(
        "ix_source_workspaces_active_mutation_id",
        "source_workspaces",
        ["active_mutation_id"],
    )

    with op.batch_alter_table("source_mutation_journal", recreate="always") as batch:
        batch.alter_column("proposal_id", existing_type=sa.String(length=36), nullable=True)
        batch.alter_column(
            "previous_source_revision_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )
        batch.add_column(
            sa.Column("before_manifest", sa.JSON(), nullable=False, server_default="{}")
        )
        batch.add_column(
            sa.Column("after_manifest", sa.JSON(), nullable=False, server_default="{}")
        )
        batch.add_column(sa.Column("recovery_bundle_path", sa.String(length=2000), nullable=True))
        batch.drop_constraint("status", type_="check")
        batch.create_check_constraint(
            "status",
            "status IN ('PREPARED', 'COMPLETED', 'ROLLED_BACK', 'RECOVERED', 'RECOVERY_REQUIRED')",
        )


def downgrade() -> None:
    with op.batch_alter_table("source_mutation_journal", recreate="always") as batch:
        batch.drop_constraint("status", type_="check")
        batch.create_check_constraint(
            "status",
            "status IN ('PREPARED', 'COMPLETED', 'ROLLED_BACK', 'RECOVERED')",
        )
        batch.drop_column("recovery_bundle_path")
        batch.drop_column("after_manifest")
        batch.drop_column("before_manifest")
        batch.alter_column("proposal_id", existing_type=sa.String(length=36), nullable=False)
        batch.alter_column(
            "previous_source_revision_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
    op.drop_index("ix_source_workspaces_active_mutation_id", table_name="source_workspaces")
    with op.batch_alter_table("source_workspaces") as batch:
        batch.drop_column("active_mutation_expected_revision")
        batch.drop_column("active_mutation_started_at")
        batch.drop_column("active_mutation_id")
