"""Framework-neutral contracts for durable outbox and recovery workflows."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _now() -> datetime:
    return datetime.now(UTC)


def _json_default(value: object) -> str:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        # Canonical JSON must not depend on the host's local timezone.  A
        # legacy naive value is interpreted explicitly as UTC at this boundary.
        normalized = value.replace(tzinfo=UTC) if value.tzinfo is None else value
        return normalized.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, StrEnum):
        return value.value
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json(payload: dict[str, Any]) -> str:
    """Serialize event payloads deterministically across Python and database adapters."""

    return json.dumps(
        payload,
        default=_json_default,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def payload_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class OutboxEventStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    RETRY = "RETRY"
    PROCESSED = "PROCESSED"
    DEAD_LETTER = "DEAD_LETTER"


class SideEffectStatus(StrEnum):
    PREPARED = "PREPARED"
    APPLIED = "APPLIED"
    FAILED = "FAILED"
    RECONCILE_REQUIRED = "RECONCILE_REQUIRED"


class OutboxEvent(BaseModel):
    """Immutable persisted event envelope; delivery is at-least-once."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    schema_version: str = "1.0"
    project_id: UUID | None = None
    event_type: str = Field(min_length=1, max_length=200, pattern=r"^[a-z][a-z0-9_.-]*$")
    event_version: int = Field(default=1, ge=1)
    aggregate_type: str = Field(min_length=1, max_length=100)
    aggregate_id: str = Field(min_length=1, max_length=500)
    aggregate_revision: int | None = Field(default=None, ge=1)
    event_key: str = Field(min_length=1, max_length=700)
    payload: dict[str, Any]
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    correlation_id: UUID | None = None
    causation_id: UUID | None = None
    status: OutboxEventStatus = OutboxEventStatus.PENDING
    attempt_count: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=8, ge=1)
    available_at: datetime = Field(default_factory=_now)
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    last_error: str | None = Field(default=None, max_length=4000)
    processed_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    revision: int = Field(default=1, ge=1)

    @field_validator("available_at", "created_at", "updated_at", "lease_expires_at", "processed_at")
    @classmethod
    def normalize_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_hash(self) -> OutboxEvent:
        if payload_sha256(self.payload) != self.payload_hash:
            raise ValueError("payload_hash must equal SHA256(canonical JSON payload)")
        return self


class ProcessedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    event_id: UUID
    consumer_id: str = Field(min_length=1, max_length=200)
    event_payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    processed_at: datetime = Field(default_factory=_now)
    result_ref: str | None = Field(default=None, max_length=2000)
    result_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class SideEffectJournal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    event_id: UUID
    consumer_id: str = Field(min_length=1, max_length=200)
    effect_key: str = Field(min_length=1, max_length=300)
    effect_type: str = Field(min_length=1, max_length=200)
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: SideEffectStatus = SideEffectStatus.PREPARED
    attempt_count: int = Field(default=0, ge=0)
    result_ref: str | None = Field(default=None, max_length=2000)
    result_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    last_error: str | None = Field(default=None, max_length=4000)
    prepared_at: datetime = Field(default_factory=_now)
    applied_at: datetime | None = None
    updated_at: datetime = Field(default_factory=_now)


def stable_event_key(
    event_type: str,
    aggregate_type: str,
    aggregate_id: str | UUID,
    aggregate_revision: int | None,
) -> str:
    """Return the stable producer idempotency key for one business transition."""

    revision = "none" if aggregate_revision is None else str(aggregate_revision)
    return f"{event_type}:{aggregate_type}:{aggregate_id}:{revision}"


__all__ = [
    "OutboxEvent",
    "OutboxEventStatus",
    "ProcessedEvent",
    "SideEffectJournal",
    "SideEffectStatus",
    "canonical_json",
    "payload_sha256",
    "stable_event_key",
]
