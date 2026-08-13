"""Persist the M18 Engineering Dependency Graph."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_m18_engineering_dependency_graph"
down_revision: str | None = "0023_m17_test_traceability_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _common_columns() -> list[sa.Column[object]]:
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
        "engineering_dependency_edges",
        *_common_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("upstream_type", sa.String(length=100), nullable=False),
        sa.Column("upstream_id", sa.String(length=500), nullable=False),
        sa.Column("downstream_type", sa.String(length=100), nullable=False),
        sa.Column("downstream_id", sa.String(length=500), nullable=False),
        sa.Column("dependency_kind", sa.String(length=30), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("invalidation_policy", sa.String(length=80), nullable=False),
        sa.Column("bound_upstream_revision", sa.Integer(), nullable=False),
        sa.Column("bound_upstream_semantic_hash", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=2000), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(
            "dependency_kind IN ('INPUT', 'DERIVATION', 'GENERATION', 'CONFIGURATION', "
            "'SELECTION', 'VERIFICATION', 'EVIDENCE')",
            name="dependency_kind",
        ),
        sa.CheckConstraint(
            "invalidation_policy IN ('NONE', 'SEMANTIC_CHANGE_STALE', 'SOURCE_INVALID_STALE', "
            "'SOURCE_INVALID_INVALID', 'SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID')",
            name="invalidation_policy",
        ),
        sa.CheckConstraint(
            "length(bound_upstream_semantic_hash) = 64", name="semantic_hash_length"
        ),
        sa.CheckConstraint(
            "NOT (upstream_type = downstream_type AND upstream_id = downstream_id)",
            name="not_self_dependency",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "upstream_type",
            "upstream_id",
            "downstream_type",
            "downstream_id",
            "dependency_kind",
            name="uq_engineering_dependency_edges_identity",
        ),
    )
    op.create_index(
        "ix_engineering_dependency_edges_project_id",
        "engineering_dependency_edges",
        ["project_id"],
    )
    op.create_index(
        "ix_engineering_dependency_edges_project_upstream",
        "engineering_dependency_edges",
        ["project_id", "upstream_type", "upstream_id"],
    )
    op.create_index(
        "ix_engineering_dependency_edges_project_downstream",
        "engineering_dependency_edges",
        ["project_id", "downstream_type", "downstream_id"],
    )

    op.create_table(
        "engineering_dependency_node_states",
        *_common_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=500), nullable=False),
        sa.Column("observed_revision", sa.Integer(), nullable=False),
        sa.Column("observed_semantic_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("invalidated_by", sa.JSON(), nullable=False),
        sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.Column("stale_since", sa.DateTime(timezone=True)),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint("status IN ('CURRENT', 'STALE', 'INVALID', 'UNKNOWN')", name="status"),
        sa.CheckConstraint("length(observed_semantic_hash) = 64", name="semantic_hash_length"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "entity_type",
            "entity_id",
            name="uq_engineering_dependency_node_states_identity",
        ),
    )
    op.create_index(
        "ix_engineering_dependency_node_states_project_id",
        "engineering_dependency_node_states",
        ["project_id"],
    )
    op.create_index(
        "ix_engineering_dependency_node_states_project_status",
        "engineering_dependency_node_states",
        ["project_id", "status"],
    )

    op.create_table(
        "generated_protocol_outputs",
        *_common_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("protocol_id", sa.String(length=36), nullable=False),
        sa.Column("protocol_revision", sa.Integer(), nullable=False),
        sa.Column("target", sa.String(length=40), nullable=False),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("generator_version", sa.String(length=100), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "protocol_id", "target", name="uq_protocol_output_target"
        ),
    )
    op.create_index(
        "ix_generated_protocol_outputs_project_id",
        "generated_protocol_outputs",
        ["project_id"],
    )
    op.create_index(
        "ix_generated_protocol_outputs_protocol_id",
        "generated_protocol_outputs",
        ["protocol_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_generated_protocol_outputs_protocol_id", table_name="generated_protocol_outputs"
    )
    op.drop_index(
        "ix_generated_protocol_outputs_project_id", table_name="generated_protocol_outputs"
    )
    op.drop_table("generated_protocol_outputs")
    op.drop_index(
        "ix_engineering_dependency_node_states_project_status",
        table_name="engineering_dependency_node_states",
    )
    op.drop_index(
        "ix_engineering_dependency_node_states_project_id",
        table_name="engineering_dependency_node_states",
    )
    op.drop_table("engineering_dependency_node_states")
    op.drop_index(
        "ix_engineering_dependency_edges_project_downstream",
        table_name="engineering_dependency_edges",
    )
    op.drop_index(
        "ix_engineering_dependency_edges_project_upstream",
        table_name="engineering_dependency_edges",
    )
    op.drop_index(
        "ix_engineering_dependency_edges_project_id",
        table_name="engineering_dependency_edges",
    )
    op.drop_table("engineering_dependency_edges")
