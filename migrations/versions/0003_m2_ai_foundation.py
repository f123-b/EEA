"""Create M2 prompt registry and AI usage accounting tables.

Revision ID: 0003_m2
Revises: 0002_m1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_m2"
down_revision: str | None = "0002_m1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENGINEERING_ERROR_CODES = (
    "VALIDATION_ERROR",
    "PROJECT_NOT_FOUND",
    "DOCUMENT_PARSE_FAILED",
    "CLAIM_CONFLICT",
    "DEVICE_NOT_FOUND",
    "PIN_CONFLICT",
    "PIN_FUNCTION_INVALID",
    "INVALID_REQUIREMENT",
    "REVISION_CONFLICT",
    "BUILD_FAILED",
    "ERC_FAILED",
    "STATIC_ANALYSIS_FAILED",
    "TOOL_UNAVAILABLE",
    "CAPABILITY_UNAVAILABLE",
    "AI_PROVIDER_UNAVAILABLE",
    "PERMISSION_REQUIRED",
    "RESOURCE_BUSY",
    "BUDGET_EXCEEDED",
    "KNOWLEDGE_SCOPE_DENIED",
    "REPOSITORY_UNTRUSTED",
    "JOB_CANCELLED",
    "SCHEMA_VERSION_UNSUPPORTED",
    "AUTH_REQUIRED",
    "SOURCE_REVISION_CONFLICT",
    "DOMAIN_COMPOSITION_CONFLICT",
    "DOMAIN_DEPENDENCY_MISSING",
    "DOMAIN_INCOMPATIBLE",
    "COMMISSIONING_REQUIRED",
    "COMMISSIONING_BLOCKED",
    "SAFETY_LIMIT_VIOLATION",
    "TARGET_IDENTITY_MISMATCH",
    "SAFE_STATE_FAILED",
    "EMERGENCY_STOP_ACTIVE",
    "RECOVERY_REQUIRED",
    "EVENT_DELIVERY_FAILED",
    "INDEX_REBUILD_REQUIRED",
    "BUILD_INPUT_UNDECLARED",
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
        "prompt_definitions",
        *_entity_columns(),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("system_template", sa.Text(), nullable=False),
        sa.Column("user_template", sa.Text(), nullable=False),
        sa.Column("model_policy", sa.JSON(), nullable=False),
        sa.Column("allowed_tools", sa.JSON(), nullable=False),
        sa.Column("input_schema", sa.JSON(), nullable=False),
        sa.Column("output_schema", sa.JSON(), nullable=False),
        sa.Column("evidence_requirements", sa.JSON(), nullable=False),
        sa.Column("fallback", sa.JSON(), nullable=False),
        sa.Column("max_steps", sa.Integer(), nullable=False),
        sa.Column("budget_policy", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint("max_steps >= 1", name="max_steps_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_prompt_definitions"),
        sa.UniqueConstraint("name", "prompt_version", name="uq_prompt_definitions_name_version"),
    )
    op.create_index("ix_prompt_definitions_name", "prompt_definitions", ["name"])

    op.create_table(
        "ai_usage_records",
        *_entity_columns(),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("prompt_definition_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("llm_cost", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint("input_tokens >= 0", name="input_tokens_non_negative"),
        sa.CheckConstraint("output_tokens >= 0", name="output_tokens_non_negative"),
        sa.CheckConstraint(
            "total_tokens >= input_tokens + output_tokens", name="total_tokens_valid"
        ),
        sa.CheckConstraint("llm_cost >= 0", name="llm_cost_non_negative"),
        sa.CheckConstraint("duration_ms >= 0", name="duration_ms_non_negative"),
        sa.CheckConstraint(
            f"error_code IS NULL OR error_code IN ({_values(ENGINEERING_ERROR_CODES)})",
            name="error_code",
        ),
        sa.ForeignKeyConstraint(
            ["prompt_definition_id"],
            ["prompt_definitions.id"],
            name="fk_ai_usage_records_prompt_definition_id_prompt_definitions",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_ai_usage_records_project_id_projects"
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], name="fk_ai_usage_records_job_id_jobs"),
        sa.PrimaryKeyConstraint("id", name="pk_ai_usage_records"),
    )
    op.create_index("ix_ai_usage_records_request_id", "ai_usage_records", ["request_id"])
    op.create_index(
        "ix_ai_usage_records_prompt_definition_id",
        "ai_usage_records",
        ["prompt_definition_id"],
    )
    op.create_index("ix_ai_usage_records_project_id", "ai_usage_records", ["project_id"])
    op.create_index("ix_ai_usage_records_job_id", "ai_usage_records", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_records_job_id", table_name="ai_usage_records")
    op.drop_index("ix_ai_usage_records_project_id", table_name="ai_usage_records")
    op.drop_index("ix_ai_usage_records_prompt_definition_id", table_name="ai_usage_records")
    op.drop_index("ix_ai_usage_records_request_id", table_name="ai_usage_records")
    op.drop_table("ai_usage_records")
    op.drop_index("ix_prompt_definitions_name", table_name="prompt_definitions")
    op.drop_table("prompt_definitions")
