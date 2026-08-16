"""M18ER reliability closure for identity foreign-key parent keys."""

from collections.abc import Sequence

from alembic import op

revision: str = "0032_m18er_reliability_closure"
down_revision: str | None = "0031_m18e_renderer_nfr_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Make legacy entity ids valid referenced keys without rewriting history."""

    op.create_index(
        "uq_identity_users_id_m18er",
        "identity_users",
        ["id"],
        unique=True,
    )
    op.create_index(
        "uq_organizations_id_m18er",
        "organizations",
        ["id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_organizations_id_m18er", table_name="organizations")
    op.drop_index("uq_identity_users_id_m18er", table_name="identity_users")
