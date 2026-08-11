"""Add the M14 Domain-not-found error to existing error-code constraints.

Revision ID: 0019_m14_domain_error_catalog
Revises: 0018_m14_domain_extensions
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "0019_m14_domain_error_catalog"
down_revision: str | None = "0018_m14_domain_extensions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_ERROR_CODES = (
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
    "SANDBOX_VIOLATION",
    "ARCHIVE_UNSAFE",
    "COMMAND_NOT_ALLOWED",
    "NETWORK_DENIED",
    "RESOURCE_LIMIT_EXCEEDED",
)
NEW_ERROR_CODES = (
    "COMPONENT_UNAVAILABLE",
    "COMPONENT_VERSION_UNRESOLVED",
    "COMPONENT_INCOMPATIBLE",
    "COMPONENT_HASH_MISMATCH",
    "COMPONENT_LICENSE_BLOCKED",
    "COMPONENT_REFERENCE_ONLY",
    "DEPENDENCY_CONFLICT",
    "DEPENDENCY_CYCLE",
    "DEPENDENCY_LOCK_REQUIRED",
    "DEPENDENCY_LOCK_STALE",
    "COMPONENT_MATERIALIZATION_FAILED",
    "TOOLCHAIN_INCOMPATIBLE",
    "DEVICE_BUILD_UNAVAILABLE",
)


def _values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _replace_error_constraint(table_name: str, values: tuple[str, ...]) -> None:
    existing = [
        item["name"]
        for item in inspect(op.get_bind()).get_check_constraints(table_name)
        if "error_code" in (item.get("sqltext") or "").lower()
    ]
    with op.batch_alter_table(table_name, recreate="always") as batch_op:
        if existing:
            name = existing[0]
            prefix = f"ck_{table_name}_"
            batch_op.drop_constraint(
                name[len(prefix) :] if name.startswith(prefix) else name,
                type_="check",
            )
        batch_op.create_check_constraint(
            "error_code",
            f"error_code IS NULL OR error_code IN ({_values(values)})",
        )


def upgrade() -> None:
    values = LEGACY_ERROR_CODES + NEW_ERROR_CODES + ("DOMAIN_NOT_FOUND",)
    _replace_error_constraint("jobs", values)
    _replace_error_constraint("ai_usage_records", values)


def downgrade() -> None:
    values = LEGACY_ERROR_CODES + NEW_ERROR_CODES
    _replace_error_constraint("jobs", values)
    _replace_error_constraint("ai_usage_records", values)
