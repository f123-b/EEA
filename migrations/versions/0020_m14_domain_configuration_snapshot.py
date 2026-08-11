"""Persist Domain configuration schema compatibility snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_m14_domain_configuration_snapshot"
down_revision: str | None = "0019_m14_domain_error_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "domain_activations",
        sa.Column(
            "configuration_schema_version",
            sa.String(length=30),
            nullable=False,
            server_default="1.0",
        ),
    )
    op.execute(
        sa.text(
            "UPDATE domain_activations SET configuration_schema_version = domain_schema_version"
        )
    )
    op.add_column(
        "domain_activations",
        sa.Column("configuration_schema_hash", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("domain_activations", "configuration_schema_hash")
    op.drop_column("domain_activations", "configuration_schema_version")
