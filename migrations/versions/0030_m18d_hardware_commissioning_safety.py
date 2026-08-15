"""M18D Hardware Commissioning & Safety persistence contract."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_m18d_hardware_commissioning_safety"
down_revision: str | None = "0029_m18cr_source_mutation_cas_recovery"
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


_STATES = ",".join(
    f"'{value}'"
    for value in (
        "CREATED",
        "PREFLIGHT",
        "FLASHED_SAFE",
        "SENSOR_CHECK",
        "LOW_POWER",
        "CLOSED_LOOP_LIMITED",
        "USER_APPROVAL",
        "NORMAL_OPERATION",
        "BLOCKED",
        "ABORTED",
        "EMERGENCY_STOP",
        "FAULTED",
        "ROLLBACK_REQUIRED",
    )
)

_PERMISSION_TOKEN_STATUSES = "'ACTIVE','REVOKED','EXPIRED'"
_PERMISSIONS = ",".join(
    f"'{value}'"
    for value in (
        "READ",
        "WRITE",
        "BUILD",
        "NETWORK",
        "SECRET_USE",
        "FLASH",
        "DEBUG",
        "HARDWARE_CONTROL",
        "ACTUATOR_ENABLE",
        "DELETE",
        "PLUGIN_INSTALL",
        "KNOWLEDGE_PROMOTE",
        "EXPORT_PRIVATE",
    )
)
_STEP_STATUSES = ",".join(
    f"'{value}'" for value in ("PENDING", "RUNNING", "PASS", "FAIL", "BLOCKED", "ABORTED")
)
_STOP_SOURCES = ",".join(
    f"'{value}'"
    for value in (
        "USER",
        "HARDWARE_FAULT",
        "WATCHDOG",
        "RULE_ENGINE",
        "SAFETY_MONITOR",
        "TOOL_ADAPTER",
        "AGENT_POLICY",
        "LOCK_LOSS",
        "TIMEOUT",
        "CANCELLATION",
    )
)
_RESOURCE_TYPES = ",".join(
    f"'{value}'"
    for value in (
        "DebugProbe",
        "SerialPort",
        "CANInterface",
        "Instrument",
        "SimulatorInstance",
        "HardwareTarget",
    )
)


def upgrade() -> None:
    op.create_table(
        "permission_tokens",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=200), nullable=False),
        sa.Column("permission", sa.String(length=40), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.String(length=500), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("reason", sa.String(length=2000), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(f"permission IN ({_PERMISSIONS})", name="permission"),
        sa.CheckConstraint(f"status IN ({_PERMISSION_TOKEN_STATUSES})", name="status"),
    )
    op.create_index("ix_permission_tokens_project_id", "permission_tokens", ["project_id"])
    op.create_index("ix_permission_tokens_actor_id", "permission_tokens", ["actor_id"])
    op.create_index(
        "ix_permission_tokens_scope",
        "permission_tokens",
        ["project_id", "actor_id", "permission"],
    )
    op.create_index("ix_permission_tokens_session_id", "permission_tokens", ["session_id"])
    op.create_table(
        "commissioning_profiles",
        *_entity_columns(),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("applicable_target_types", sa.JSON(), nullable=False),
        sa.Column("applicable_domains", sa.JSON(), nullable=False),
        sa.Column("required_steps", sa.JSON(), nullable=False),
        sa.Column("required_permissions", sa.JSON(), nullable=False),
        sa.Column("user_approval_required", sa.Boolean(), nullable=False),
        sa.Column("safety_limits", sa.JSON(), nullable=False),
        sa.Column("required_safety_capabilities", sa.JSON(), nullable=False),
        sa.Column("watchdog_policy", sa.JSON(), nullable=False),
        sa.Column("emergency_stop_policy", sa.JSON(), nullable=False),
        sa.Column("safe_state_policy", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_commissioning_profiles_name_version"),
    )
    op.create_index("ix_commissioning_profiles_name", "commissioning_profiles", ["name"])

    op.create_table(
        "hardware_targets",
        *_entity_columns(),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("identity", sa.JSON(), nullable=False),
        sa.Column("safe_state", sa.JSON(), nullable=False),
        sa.Column("safety_capability", sa.JSON(), nullable=False),
        sa.Column("safety_critical", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_hardware_targets_project_name"),
    )
    op.create_index("ix_hardware_targets_project_id", "hardware_targets", ["project_id"])

    op.create_table(
        "target_safety_capabilities",
        *_entity_columns(),
        sa.Column("target_id", sa.String(length=500), nullable=False),
        sa.Column("capability", sa.JSON(), nullable=False),
        sa.Column("verification_status", sa.String(length=30), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("target_id", name="uq_target_safety_capabilities_target"),
        sa.CheckConstraint(
            "verification_status IN ('VERIFIED','SUPPORTED_UNVERIFIED','NOT_SUPPORTED','UNKNOWN')",
            name="verification_status",
        ),
    )
    op.create_index(
        "ix_target_safety_capabilities_target_id", "target_safety_capabilities", ["target_id"]
    )

    op.create_table(
        "resource_locks",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", sa.String(length=500), nullable=False),
        sa.Column("owner_job_id", sa.String(length=36), nullable=True),
        sa.Column("owner_session", sa.String(length=36), nullable=True),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            f"resource_type IN ({_RESOURCE_TYPES})",
            name="resource_type",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','RELEASED','EXPIRED','QUARANTINED')", name="status"
        ),
    )
    op.create_index("ix_resource_locks_project_id", "resource_locks", ["project_id"])
    op.create_index(
        "ix_resource_locks_resource_active",
        "resource_locks",
        ["resource_type", "resource_id", "status"],
    )
    op.create_index(
        "uq_resource_locks_active_owner",
        "resource_locks",
        ["resource_type", "resource_id"],
        unique=True,
        sqlite_where=sa.text("status = 'ACTIVE'"),
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "commissioning_sessions",
        *_entity_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("target_id", sa.String(length=500), nullable=False),
        sa.Column("firmware_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("firmware_hash", sa.String(length=64), nullable=False),
        sa.Column("build_run_id", sa.String(length=36), nullable=True),
        sa.Column("source_revision_id", sa.String(length=36), nullable=True),
        sa.Column("build_input_snapshot_id", sa.String(length=36), nullable=True),
        sa.Column("hardware_identity", sa.JSON(), nullable=False),
        sa.Column("probe_identity", sa.JSON(), nullable=False),
        sa.Column("board_revision", sa.String(length=100), nullable=True),
        sa.Column("commissioning_profile_id", sa.String(length=36), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False),
        sa.Column("current_step", sa.String(length=100), nullable=True),
        sa.Column("started_by", sa.String(length=200), nullable=False),
        sa.Column("approved_by", sa.String(length=200), nullable=True),
        sa.Column("safety_limits_snapshot", sa.JSON(), nullable=False),
        sa.Column("preflight_results", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("emergency_stop_state", sa.String(length=30), nullable=False),
        sa.Column("watchdog_state", sa.JSON(), nullable=False),
        sa.Column("resource_lock_ids", sa.JSON(), nullable=False),
        sa.Column("permission_token_ids", sa.JSON(), nullable=False),
        sa.Column("approval_snapshot", sa.JSON(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("aborted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active_action_id", sa.String(length=36), nullable=True),
        sa.Column("active_action_kind", sa.String(length=100), nullable=True),
        sa.Column("active_action_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active_action_expected_revision", sa.Integer(), nullable=True),
        sa.Column("active_action_request_hash", sa.String(length=64), nullable=True),
        sa.Column("active_action_journal_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["commissioning_profile_id"], ["commissioning_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(f"state IN ({_STATES})", name="state"),
        sa.CheckConstraint(
            "emergency_stop_state IN ('INACTIVE','REQUESTED','ACTIVE','UNKNOWN')",
            name="emergency_stop_state",
        ),
    )
    op.create_index(
        "ix_commissioning_sessions_project_id", "commissioning_sessions", ["project_id"]
    )
    op.create_index("ix_commissioning_sessions_target_id", "commissioning_sessions", ["target_id"])
    op.create_index(
        "ix_commissioning_sessions_firmware_artifact_id",
        "commissioning_sessions",
        ["firmware_artifact_id"],
    )

    op.create_table(
        "safety_limits",
        *_entity_columns(),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("immutable", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["commissioning_sessions.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["commissioning_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_safety_limits_session"),
    )
    op.create_index("ix_safety_limits_session_id", "safety_limits", ["session_id"])

    op.create_table(
        "commissioning_step_results",
        *_entity_columns(),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("step_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("measurements", sa.JSON(), nullable=False),
        sa.Column("thresholds", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("tool_version", sa.String(length=100), nullable=False),
        sa.Column("rule_version", sa.String(length=100), nullable=False),
        sa.Column("operator", sa.String(length=200), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["commissioning_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "step_id", name="uq_commissioning_step_session_step"),
        sa.CheckConstraint(f"status IN ({_STEP_STATUSES})", name="status"),
    )
    op.create_index(
        "ix_commissioning_step_results_session_id", "commissioning_step_results", ["session_id"]
    )

    op.create_table(
        "emergency_stop_events",
        *_entity_columns(),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.String(length=4000), nullable=False),
        sa.Column("safe_state_attempted", sa.Boolean(), nullable=False),
        sa.Column("safe_state_verified", sa.Boolean(), nullable=False),
        sa.Column("quarantined_resource_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=300), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["commissioning_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_emergency_stop_idempotency_key"),
        sa.CheckConstraint(f"source IN ({_STOP_SOURCES})", name="source"),
    )
    op.create_index("ix_emergency_stop_events_session_id", "emergency_stop_events", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_emergency_stop_events_session_id", table_name="emergency_stop_events")
    op.drop_table("emergency_stop_events")
    op.drop_index(
        "ix_commissioning_step_results_session_id", table_name="commissioning_step_results"
    )
    op.drop_table("commissioning_step_results")
    op.drop_index("ix_safety_limits_session_id", table_name="safety_limits")
    op.drop_table("safety_limits")
    op.drop_index(
        "ix_commissioning_sessions_firmware_artifact_id", table_name="commissioning_sessions"
    )
    op.drop_index("ix_commissioning_sessions_target_id", table_name="commissioning_sessions")
    op.drop_index("ix_commissioning_sessions_project_id", table_name="commissioning_sessions")
    op.drop_table("commissioning_sessions")
    op.drop_index("ix_resource_locks_resource_active", table_name="resource_locks")
    op.drop_index("uq_resource_locks_active_owner", table_name="resource_locks")
    op.drop_index("ix_resource_locks_project_id", table_name="resource_locks")
    op.drop_table("resource_locks")
    op.drop_index("ix_permission_tokens_session_id", table_name="permission_tokens")
    op.drop_index("ix_permission_tokens_scope", table_name="permission_tokens")
    op.drop_index("ix_permission_tokens_actor_id", table_name="permission_tokens")
    op.drop_index("ix_permission_tokens_project_id", table_name="permission_tokens")
    op.drop_table("permission_tokens")
    op.drop_index(
        "ix_target_safety_capabilities_target_id", table_name="target_safety_capabilities"
    )
    op.drop_table("target_safety_capabilities")
    op.drop_index("ix_hardware_targets_project_id", table_name="hardware_targets")
    op.drop_table("hardware_targets")
    op.drop_index("ix_commissioning_profiles_name", table_name="commissioning_profiles")
    op.drop_table("commissioning_profiles")
