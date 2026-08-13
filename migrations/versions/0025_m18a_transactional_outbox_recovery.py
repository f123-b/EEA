"""Add the M18A transactional outbox and recovery journal."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_m18a_transactional_outbox_recovery"
down_revision: str | None = "0024_m18_engineering_dependency_graph"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("schema_version", sa.String(length=30), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=200), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False),
        sa.Column("aggregate_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_id", sa.String(length=500), nullable=False),
        sa.Column("aggregate_revision", sa.Integer(), nullable=True),
        sa.Column("event_key", sa.String(length=700), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=36), nullable=True),
        sa.Column("causation_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(length=200), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("attempt_count >= 0", name="attempt_count_non_negative"),
        sa.CheckConstraint("max_attempts >= 1", name="max_attempts_positive"),
        sa.CheckConstraint("length(payload_hash) = 64", name="payload_hash_length"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'RETRY', 'PROCESSED', 'DEAD_LETTER')",
            name="status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key", name="uq_outbox_events_event_key"),
    )
    op.create_index("ix_outbox_events_project_id", "outbox_events", ["project_id"])
    op.create_index(
        "ix_outbox_events_status_available", "outbox_events", ["status", "available_at"]
    )
    op.create_index(
        "ix_outbox_events_status_lease", "outbox_events", ["status", "lease_expires_at"]
    )
    op.create_index("ix_outbox_events_project_status", "outbox_events", ["project_id", "status"])
    op.create_index("ix_outbox_events_event_type", "outbox_events", ["event_type"])

    op.create_table(
        "processed_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("consumer_id", sa.String(length=200), nullable=False),
        sa.Column("event_payload_hash", sa.String(length=64), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_ref", sa.String(length=2000), nullable=True),
        sa.Column("result_hash", sa.String(length=64), nullable=True),
        sa.CheckConstraint("length(event_payload_hash) = 64", name="event_payload_hash_length"),
        sa.CheckConstraint(
            "result_hash IS NULL OR length(result_hash) = 64", name="result_hash_length"
        ),
        sa.ForeignKeyConstraint(["event_id"], ["outbox_events.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "consumer_id", name="uq_processed_events_identity"),
    )
    op.create_index(
        "ix_processed_events_consumer_processed",
        "processed_events",
        ["consumer_id", "processed_at"],
    )

    op.create_table(
        "side_effect_journal",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("consumer_id", sa.String(length=200), nullable=False),
        sa.Column("effect_key", sa.String(length=300), nullable=False),
        sa.Column("effect_type", sa.String(length=200), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_ref", sa.String(length=2000), nullable=True),
        sa.Column("result_hash", sa.String(length=64), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(request_hash) = 64", name="request_hash_length"),
        sa.CheckConstraint(
            "result_hash IS NULL OR length(result_hash) = 64", name="result_hash_length"
        ),
        sa.CheckConstraint(
            "status IN ('PREPARED', 'APPLIED', 'FAILED', 'RECONCILE_REQUIRED')", name="status"
        ),
        sa.ForeignKeyConstraint(["event_id"], ["outbox_events.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id", "consumer_id", "effect_key", name="uq_side_effect_journal_identity"
        ),
    )
    op.create_index(
        "ix_side_effect_journal_status_event",
        "side_effect_journal",
        ["status", "event_id", "consumer_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_side_effect_journal_status_event", table_name="side_effect_journal")
    op.drop_table("side_effect_journal")
    op.drop_index("ix_processed_events_consumer_processed", table_name="processed_events")
    op.drop_table("processed_events")
    op.drop_index("ix_outbox_events_event_type", table_name="outbox_events")
    op.drop_index("ix_outbox_events_project_status", table_name="outbox_events")
    op.drop_index("ix_outbox_events_status_lease", table_name="outbox_events")
    op.drop_index("ix_outbox_events_status_available", table_name="outbox_events")
    op.drop_index("ix_outbox_events_project_id", table_name="outbox_events")
    op.drop_table("outbox_events")
