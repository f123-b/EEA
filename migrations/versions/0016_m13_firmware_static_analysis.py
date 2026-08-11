"""Persist M13 firmware static-analysis runs and normalized rule results.

Revision ID: 0016_m13_firmware_static_analysis
Revises: 0015_m12a_software_components
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_m13_firmware_static_analysis"
down_revision: str | None = "0015_m12a_software_components"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
        "firmware_static_analyses",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("firmware_id", sa.String(length=36), nullable=False),
        sa.Column("firmware_revision", sa.Integer(), nullable=False),
        sa.Column("source_revision_id", sa.String(length=36), nullable=False),
        sa.Column("build_input_snapshot_id", sa.String(length=36), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("ruleset_version", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("tool_results", sa.JSON(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint("status IN ('PASS', 'FAIL', 'UNKNOWN', 'BLOCKED')", name="status"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["firmware_id"], ["firmware_irs.id"]),
        sa.ForeignKeyConstraint(["source_revision_id"], ["source_revisions.id"]),
        sa.ForeignKeyConstraint(["build_input_snapshot_id"], ["build_input_snapshots.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_firmware_static_analyses"),
    )
    for column in ("project_id", "firmware_id", "source_revision_id", "build_input_snapshot_id"):
        op.create_index(
            f"ix_firmware_static_analyses_{column}", "firmware_static_analyses", [column]
        )

    op.create_table(
        "firmware_static_analysis_results",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("analysis_id", sa.String(length=36), nullable=False),
        sa.Column("rule_id", sa.String(length=200), nullable=False),
        sa.Column("rule_version", sa.String(length=50), nullable=False),
        sa.Column("stage", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("affected_refs", sa.JSON(), nullable=False),
        sa.Column("measured", sa.JSON()),
        sa.Column("threshold", sa.JSON()),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("claim_ids", sa.JSON(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(
            "stage IN ('PRE_GENERATION', 'POST_GENERATION', 'PRE_TOOL', 'POST_TOOL', "
            "'RELEASE_GATE')",
            name="stage",
        ),
        sa.CheckConstraint(
            "status IN ('PASS', 'FAIL', 'NOT_APPLICABLE', 'UNKNOWN')", name="status"
        ),
        sa.CheckConstraint(
            "severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')", name="severity"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["analysis_id"], ["firmware_static_analyses.id"]),
        sa.UniqueConstraint("analysis_id", "rule_id", name="uq_static_analysis_rule"),
        sa.PrimaryKeyConstraint("id", name="pk_firmware_static_analysis_results"),
    )
    for column in ("project_id", "analysis_id"):
        op.create_index(
            f"ix_firmware_static_analysis_results_{column}",
            "firmware_static_analysis_results",
            [column],
        )


def downgrade() -> None:
    for column in ("project_id", "analysis_id"):
        op.drop_index(
            f"ix_firmware_static_analysis_results_{column}",
            table_name="firmware_static_analysis_results",
        )
    op.drop_table("firmware_static_analysis_results")
    for column in ("project_id", "firmware_id", "source_revision_id", "build_input_snapshot_id"):
        op.drop_index(
            f"ix_firmware_static_analyses_{column}", table_name="firmware_static_analyses"
        )
    op.drop_table("firmware_static_analyses")
