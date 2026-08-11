"""Create M3 normalized engineering-value and claim-core tables.

Revision ID: 0004_m3
Revises: 0003_m2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_m3"
down_revision: str | None = "0003_m2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENGINEERING_DIMENSIONS = (
    "VOLTAGE",
    "CURRENT",
    "RESISTANCE",
    "CAPACITANCE",
    "INDUCTANCE",
    "FREQUENCY",
    "TIME",
    "TEMPERATURE",
    "ANGLE",
    "ANGULAR_VELOCITY",
    "LENGTH",
    "POWER",
    "ENERGY",
    "DIMENSIONLESS",
)
CLAIM_LIFECYCLES = (
    "CANDIDATE",
    "ACTIVE",
    "SUPERSEDED",
    "CONFLICTED",
    "DEPRECATED",
    "ARCHIVED",
    "REJECTED",
)
CLAIM_CONFLICT_TYPES = ("VALUE_MISMATCH",)
CLAIM_CONFLICT_STATUSES = ("OPEN", "RESOLVED")
CLAIM_CONFLICT_STRATEGIES = ("SOURCE_PRIORITY", "SOURCE_VERSION", "MANUAL_REVIEW")


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
        "claim_predicate_definitions",
        *_entity_columns(),
        sa.Column("predicate", sa.String(length=200), nullable=False),
        sa.Column("value_schema_ref", sa.String(length=200), nullable=False),
        sa.Column("applicability_schema_ref", sa.String(length=200), nullable=True),
        sa.Column("unit_dimension", sa.String(length=40), nullable=True),
        sa.Column("conflict_strategy", sa.String(length=40), nullable=False),
        sa.Column("validator_ref", sa.String(length=200), nullable=True),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(
            f"conflict_strategy IN ({_values(CLAIM_CONFLICT_STRATEGIES)})",
            name="conflict_strategy",
        ),
        sa.CheckConstraint(
            f"unit_dimension IS NULL OR unit_dimension IN ({_values(ENGINEERING_DIMENSIONS)})",
            name="unit_dimension",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_claim_predicate_definitions"),
        sa.UniqueConstraint(
            "predicate", "schema_version", name="uq_claim_predicates_predicate_schema"
        ),
    )
    op.create_index(
        "ix_claim_predicate_definitions_predicate", "claim_predicate_definitions", ["predicate"]
    )

    op.create_table(
        "engineering_claims",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("subject_ref", sa.String(length=500), nullable=False),
        sa.Column("predicate", sa.String(length=200), nullable=False),
        sa.Column("value_schema_ref", sa.String(length=200), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("applicability", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("verification_levels", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_priority", sa.Integer(), nullable=False),
        sa.Column("source_version", sa.String(length=200), nullable=True),
        sa.Column("lifecycle", sa.String(length=40), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        sa.CheckConstraint(
            "source_priority >= 0 AND source_priority <= 1000", name="source_priority_range"
        ),
        sa.CheckConstraint(f"lifecycle IN ({_values(CLAIM_LIFECYCLES)})", name="lifecycle"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_engineering_claims_project_id_projects"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_engineering_claims"),
    )
    op.create_index("ix_engineering_claims_project_id", "engineering_claims", ["project_id"])
    op.create_index("ix_engineering_claims_subject_ref", "engineering_claims", ["subject_ref"])
    op.create_index("ix_engineering_claims_predicate", "engineering_claims", ["predicate"])

    op.create_table(
        "claim_conflicts",
        *_entity_columns(),
        sa.Column("claim_a_id", sa.String(length=36), nullable=False),
        sa.Column("claim_b_id", sa.String(length=36), nullable=False),
        sa.Column("conflict_type", sa.String(length=40), nullable=False),
        sa.Column("overlapping_applicability", sa.JSON(), nullable=False),
        sa.Column("resolver", sa.String(length=100), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("selected_claim_id", sa.String(length=36), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint("claim_a_id <> claim_b_id", name="distinct_claims"),
        sa.CheckConstraint(
            f"conflict_type IN ({_values(CLAIM_CONFLICT_TYPES)})", name="conflict_type"
        ),
        sa.CheckConstraint(f"status IN ({_values(CLAIM_CONFLICT_STATUSES)})", name="status"),
        sa.ForeignKeyConstraint(
            ["claim_a_id"], ["engineering_claims.id"], name="fk_claim_conflicts_claim_a_id_claims"
        ),
        sa.ForeignKeyConstraint(
            ["claim_b_id"], ["engineering_claims.id"], name="fk_claim_conflicts_claim_b_id_claims"
        ),
        sa.ForeignKeyConstraint(
            ["selected_claim_id"],
            ["engineering_claims.id"],
            name="fk_claim_conflicts_selected_claim_id_claims",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_claim_conflicts"),
    )


def downgrade() -> None:
    op.drop_table("claim_conflicts")
    op.drop_index("ix_engineering_claims_predicate", table_name="engineering_claims")
    op.drop_index("ix_engineering_claims_subject_ref", table_name="engineering_claims")
    op.drop_index("ix_engineering_claims_project_id", table_name="engineering_claims")
    op.drop_table("engineering_claims")
    op.drop_index(
        "ix_claim_predicate_definitions_predicate", table_name="claim_predicate_definitions"
    )
    op.drop_table("claim_predicate_definitions")
