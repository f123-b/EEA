"""Application semantics for durable event delivery and recovery."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from eea_core.reliability import OutboxEvent, payload_sha256, stable_event_key


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class CrashPoint(StrEnum):
    AFTER_OUTBOX_INSERT_BEFORE_COMMIT = "AFTER_OUTBOX_INSERT_BEFORE_COMMIT"
    AFTER_BUSINESS_COMMIT_BEFORE_DISPATCH = "AFTER_BUSINESS_COMMIT_BEFORE_DISPATCH"
    AFTER_CONSUMER_EFFECT_COMMIT_BEFORE_OUTBOX_FINALIZE = (
        "AFTER_CONSUMER_EFFECT_COMMIT_BEFORE_OUTBOX_FINALIZE"
    )


class CrashInjector(Protocol):
    def maybe_crash(self, point: CrashPoint) -> None: ...


class NoopCrashInjector:
    def maybe_crash(self, point: CrashPoint) -> None:
        del point


class InjectedCrashError(RuntimeError):
    """Test-only process crash simulation; never exposed as an HTTP parameter."""


class OutboxRepository(Protocol):
    def add(self, event: OutboxEvent, *, commit: bool = True) -> OutboxEvent: ...

    def get(self, event_id: Any) -> OutboxEvent | None: ...

    def get_by_key(self, event_key: str) -> OutboxEvent | None: ...

    def list(self, *, project_id: Any | None = None) -> list[OutboxEvent]: ...


@dataclass(frozen=True)
class HandlerRegistration:
    consumer_id: str
    event_type: str
    supported_versions: frozenset[int]
    handler: Callable[[Any, OutboxEvent], str | None]


class OutboxHandlerRegistry:
    """Explicit, deterministic handler allow-list."""

    def __init__(self, handlers: Sequence[HandlerRegistration] = ()) -> None:
        self._handlers: list[HandlerRegistration] = []
        for handler in handlers:
            self.register(handler)

    def register(self, handler: HandlerRegistration) -> None:
        if not handler.consumer_id or not handler.event_type or not handler.supported_versions:
            raise ValueError("handler registration is incomplete")
        if any(item.consumer_id == handler.consumer_id for item in self._handlers):
            raise ValueError(f"consumer already registered: {handler.consumer_id}")
        self._handlers.append(handler)

    def for_event(self, event: OutboxEvent) -> list[HandlerRegistration]:
        return sorted(
            (
                item
                for item in self._handlers
                if item.event_type == event.event_type
                and event.event_version in item.supported_versions
            ),
            key=lambda item: item.consumer_id,
        )

    def known_event_type(self, event_type: str) -> bool:
        return any(item.event_type == event_type for item in self._handlers)

    def has_compatible_handler(self, event: OutboxEvent) -> bool:
        return bool(self.for_event(event))


class EventOutboxService:
    """Producer-side semantics; enqueue never commits its caller's business transaction."""

    def __init__(self, repository: OutboxRepository, clock: Clock | None = None) -> None:
        self._repository = repository
        self._clock = clock or SystemClock()

    def enqueue(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        event_key: str | None = None,
        payload: dict[str, Any],
        payload_hash: str | None = None,
        project_id: Any | None = None,
        aggregate_revision: int | None = None,
        event_version: int = 1,
        correlation_id: Any | None = None,
        causation_id: Any | None = None,
        max_attempts: int = 8,
        commit: bool = False,
    ) -> OutboxEvent:
        resolved_key = event_key or stable_event_key(
            event_type, aggregate_type, aggregate_id, aggregate_revision
        )
        resolved_hash = payload_hash or payload_sha256(payload)
        existing = self._repository.get_by_key(resolved_key)
        if existing is not None:
            if existing.payload_hash != resolved_hash:
                raise ValueError("event_key already exists with a different payload_hash")
            return existing
        now = self._clock.now()
        event = OutboxEvent(
            project_id=project_id,
            event_type=event_type,
            event_version=event_version,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_revision=aggregate_revision,
            event_key=resolved_key,
            payload=payload,
            payload_hash=resolved_hash,
            correlation_id=correlation_id,
            causation_id=causation_id,
            max_attempts=max_attempts,
            available_at=now,
            created_at=now,
            updated_at=now,
        )
        return self._repository.add(event, commit=commit)

    @staticmethod
    def retry_delay(attempt_count: int) -> timedelta:
        return timedelta(seconds=min(60, 2 ** max(0, attempt_count - 1)))


__all__ = [
    "CrashInjector",
    "CrashPoint",
    "EventOutboxService",
    "HandlerRegistration",
    "InjectedCrashError",
    "NoopCrashInjector",
    "OutboxHandlerRegistry",
    "SystemClock",
]
