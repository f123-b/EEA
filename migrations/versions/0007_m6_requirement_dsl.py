"""Create M6 versioned requirement profiles and analysis persistence.

Revision ID: 0007_m6
Revises: 0006_m5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_m6"
down_revision: str | None = "0006_m5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REQUIREMENT_TYPES = ("FUNCTIONAL", "PERFORMANCE", "INTERFACE", "SAFETY", "CONSTRAINT", "UNKNOWN")
REQUIREMENT_PRIORITIES = ("MUST", "SHOULD", "COULD", "UNKNOWN")
REQUIREMENT_STATUSES = (
    "CANDIDATE",
    "INCOMPLETE",
    "AMBIGUOUS",
    "COMPLETE",
    "ACCEPTED",
    "REJECTED",
)


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
        "requirement_profiles",
        *_entity_columns(),
        sa.Column("profile_name", sa.String(length=120), nullable=False),
        sa.Column("profile_version", sa.String(length=50), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("evidence_contracts", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_requirement_profiles"),
        sa.UniqueConstraint(
            "profile_name", "profile_version", name="uq_requirement_profiles_name_version"
        ),
    )
    op.create_index(
        "ix_requirement_profiles_profile_name", "requirement_profiles", ["profile_name"]
    )

    op.create_table(
        "requirements",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("requirement_type", sa.String(length=30), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("acceptance_criteria", sa.JSON(), nullable=False),
        sa.Column("source_evidence_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(f"requirement_type IN ({_values(REQUIREMENT_TYPES)})", name="type"),
        sa.CheckConstraint(f"priority IN ({_values(REQUIREMENT_PRIORITIES)})", name="priority"),
        sa.CheckConstraint(f"status IN ({_values(REQUIREMENT_STATUSES)})", name="status"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_requirements_project_id_projects",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_requirements"),
        sa.UniqueConstraint("project_id", "code", name="uq_requirements_project_code"),
    )
    op.create_index("ix_requirements_project_id", "requirements", ["project_id"])

    op.create_table(
        "requirement_analyses",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("profile_name", sa.String(length=120), nullable=False),
        sa.Column("profile_version", sa.String(length=50), nullable=False),
        sa.Column("requirements", sa.JSON(), nullable=False),
        sa.Column("field_observations", sa.JSON(), nullable=False),
        sa.Column("claims", sa.JSON(), nullable=False),
        sa.Column("issues", sa.JSON(), nullable=False),
        sa.Column("follow_up_questions", sa.JSON(), nullable=False),
        sa.Column("completeness", sa.JSON(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_requirement_analyses_project_id_projects"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_requirement_analyses"),
    )
    op.create_index("ix_requirement_analyses_project_id", "requirement_analyses", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_requirement_analyses_project_id", table_name="requirement_analyses")
    op.drop_table("requirement_analyses")
    op.drop_index("ix_requirements_project_id", table_name="requirements")
    op.drop_table("requirements")
    op.drop_index("ix_requirement_profiles_profile_name", table_name="requirement_profiles")
    op.drop_table("requirement_profiles")
