"""Bounded in-process outbox dispatcher and conservative startup recovery."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID

from eea_application.reliability import (
    Clock,
    CrashInjector,
    CrashPoint,
    EventOutboxService,
    HandlerRegistration,
    InjectedCrashError,
    NoopCrashInjector,
    OutboxHandlerRegistry,
    SystemClock,
)
from eea_core.entities import utc_now
from eea_core.enums import JobStatus
from eea_core.reliability import (
    OutboxEvent,
    OutboxEventStatus,
    ProcessedEvent,
    SideEffectJournal,
    SideEffectStatus,
    payload_sha256,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from eea_backend.models import (
    ArtifactRecord,
    JobRecord,
    OutboxEventRecord,
    SideEffectJournalRecord,
)
from eea_backend.reliability_repositories import (
    SqlAlchemyOutboxRepository,
    SqlAlchemyProcessedEventRepository,
    SqlAlchemySideEffectJournalRepository,
)


class RecoveryService:
    """Owns delivery/recovery semantics, never M18 authoritative graph propagation."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        registry: OutboxHandlerRegistry | None = None,
        clock: Clock | None = None,
        worker_id: str = "recovery-service",
        crash_injector: CrashInjector | None = None,
    ) -> None:
        self._session_factory = session_factory
        self.clock = clock or SystemClock()
        self.worker_id = worker_id
        self.crash_injector = crash_injector or NoopCrashInjector()
        self.registry = registry or default_handler_registry()

    def recover_expired_outbox_leases(self, *, limit: int = 100) -> int:
        with self._session_factory() as session:
            return SqlAlchemyOutboxRepository(session).reclaim_expired(
                now=self.clock.now(), limit=limit
            )

    def dispatch_ready_events(self, *, limit: int = 100) -> dict[str, int]:
        counts = {"processed": 0, "retry": 0, "dead_letter": 0, "reconcile_required": 0}
        for _ in range(limit):
            with self._session_factory() as session:
                event = SqlAlchemyOutboxRepository(session).claim(
                    worker_id=self.worker_id, now=self.clock.now()
                )
            if event is None:
                break
            try:
                result = self._consume_event(event, counts)
            except InjectedCrashError:
                raise
            except Exception as exc:  # handler failure is isolated from the producer transaction
                result = self._retry_or_dead(event, str(exc))
            if result == OutboxEventStatus.PROCESSED:
                counts["processed"] += 1
            elif result == OutboxEventStatus.DEAD_LETTER:
                counts["dead_letter"] += 1
            else:
                counts["retry"] += 1
        return counts

    def _consume_event(self, event: OutboxEvent, counts: dict[str, int]) -> OutboxEventStatus:
        handlers = self.registry.for_event(event)
        if not handlers:
            return self._retry_or_dead(event, "no compatible registered handler")
        for registration in handlers:
            with self._session_factory() as consumer_session:
                processed_repo = SqlAlchemyProcessedEventRepository(consumer_session)
                existing = processed_repo.get(event.id, registration.consumer_id)
                if existing is not None:
                    if existing.event_payload_hash != event.payload_hash:
                        raise ValueError("processed event payload hash mismatch")
                    continue
                result_ref = registration.handler(consumer_session, event)
                processed_repo.add(
                    ProcessedEvent(
                        event_id=event.id,
                        consumer_id=registration.consumer_id,
                        event_payload_hash=event.payload_hash,
                        processed_at=self.clock.now(),
                        result_ref=result_ref,
                        result_hash=sha256(result_ref.encode()).hexdigest() if result_ref else None,
                    )
                )
                consumer_session.commit()
            self.crash_injector.maybe_crash(
                CrashPoint.AFTER_CONSUMER_EFFECT_COMMIT_BEFORE_OUTBOX_FINALIZE
            )
        with self._session_factory() as session:
            finalized = SqlAlchemyOutboxRepository(session).finalize(
                event.id,
                worker_id=self.worker_id,
                status=OutboxEventStatus.PROCESSED,
                now=self.clock.now(),
            )
        if not finalized:
            return OutboxEventStatus.RETRY
        return OutboxEventStatus.PROCESSED

    def _retry_or_dead(self, event: OutboxEvent, error: str) -> OutboxEventStatus:
        now = self.clock.now()
        status = (
            OutboxEventStatus.DEAD_LETTER
            if event.attempt_count >= event.max_attempts
            else OutboxEventStatus.RETRY
        )
        available = now + EventOutboxService.retry_delay(event.attempt_count)
        with self._session_factory() as session:
            SqlAlchemyOutboxRepository(session).finalize(
                event.id,
                worker_id=self.worker_id,
                status=status,
                now=now,
                error=error[:4000],
                available_at=available,
            )
        return status

    def reconcile_side_effects(self, *, limit: int = 100) -> int:
        """Only content-addressed/naturally idempotent effects may be auto-reconciled."""

        with self._session_factory() as session:
            return sum(
                1
                for _ in session.scalars(
                    select(SideEffectJournalRecord)
                    .where(
                        SideEffectJournalRecord.status == SideEffectStatus.RECONCILE_REQUIRED.value
                    )
                    .limit(limit)
                )
            )

    def reconcile_interrupted_jobs(
        self, *, cutoff: timedelta = timedelta(minutes=15), limit: int = 100
    ) -> int:
        threshold = self.clock.now() - cutoff
        with self._session_factory() as session:
            rows = list(
                session.scalars(
                    select(JobRecord)
                    .where(
                        JobRecord.status == JobStatus.RUNNING.value,
                        JobRecord.updated_at < threshold,
                    )
                    .limit(limit)
                )
            )
            for row in rows:
                row.status = JobStatus.FAILED_NEEDS_RECONCILE.value
                row.error_message = "interrupted job requires explicit reconciliation"
                row.updated_at = self.clock.now()
                row.revision += 1
            session.commit()
            return len(rows)

    def reconcile_project(self, project_id: UUID) -> dict[str, Any]:
        with self._session_factory() as session:
            events = SqlAlchemyOutboxRepository(session).list(project_id=project_id)
            reconcile_required = sum(
                1
                for _ in session.scalars(
                    select(SideEffectJournalRecord)
                    .join(
                        OutboxEventRecord,
                        SideEffectJournalRecord.event_id == OutboxEventRecord.id,
                    )
                    .where(
                        OutboxEventRecord.project_id == str(project_id),
                        SideEffectJournalRecord.status == SideEffectStatus.RECONCILE_REQUIRED.value,
                    )
                )
            )
        pending = [event for event in events if event.status != OutboxEventStatus.PROCESSED]
        return {
            "project_id": str(project_id),
            "status": "RECOVERY_REQUIRED" if pending or reconcile_required > 0 else "CLEAN",
            "pending": sum(
                event.status in {OutboxEventStatus.PENDING, OutboxEventStatus.RETRY}
                for event in pending
            ),
            "retry": sum(event.status is OutboxEventStatus.RETRY for event in pending),
            "dead_letter": sum(event.status is OutboxEventStatus.DEAD_LETTER for event in pending),
            "reconcile_required": reconcile_required,
        }

    def startup_recover(self, *, batch_limit: int = 100) -> dict[str, Any]:
        reclaimed = self.recover_expired_outbox_leases(limit=batch_limit)
        interrupted = self.reconcile_interrupted_jobs(limit=batch_limit)
        dispatched = self.dispatch_ready_events(limit=batch_limit)
        return {"reclaimed": reclaimed, "interrupted_jobs": interrupted, "dispatch": dispatched}


def _journal_effect(
    session: Session, event: OutboxEvent, consumer_id: str, effect_key: str, *, result_ref: str
) -> str:
    now = utc_now()
    request_hash = payload_sha256({"event_id": str(event.id), "effect_key": effect_key})
    journal = SqlAlchemySideEffectJournalRepository(session)
    existing = journal.get(event.id, consumer_id, effect_key)
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("side-effect request_hash mismatch")
        if existing.status is SideEffectStatus.RECONCILE_REQUIRED:
            raise ValueError("side-effect requires reconciliation")
        return existing.result_ref or result_ref
    item = journal.prepare(
        SideEffectJournal(
            event_id=event.id,
            consumer_id=consumer_id,
            effect_key=effect_key,
            effect_type="database-projection",
            request_hash=request_hash,
            prepared_at=now,
            updated_at=now,
        )
    )
    journal.mark_applied(item, result_ref=result_ref, now=now)
    return result_ref


def _project_created(session: Session, event: OutboxEvent) -> str:
    return _journal_effect(
        session, event, "project-created-v1", "project-row", result_ref=event.aggregate_id
    )


def _build_completed(session: Session, event: OutboxEvent) -> str:
    return _journal_effect(
        session, event, "build-completed-v1", "build-notification", result_ref=event.aggregate_id
    )


def _artifact_created(session: Session, event: OutboxEvent) -> str:
    payload = event.payload
    artifact_id = str(payload["artifact_id"])
    record = session.get(ArtifactRecord, artifact_id)
    if record is None:
        session.add(
            ArtifactRecord(
                id=artifact_id,
                schema_version="1.0",
                revision=1,
                created_at=utc_now(),
                updated_at=utc_now(),
                entity_metadata={},
                project_id=str(payload["project_id"]),
                logical_name=str(payload["logical_name"]),
                artifact_type=str(payload["artifact_type"]),
                version_label=str(payload["version_label"]),
                content_hash=str(payload["content_hash"]),
                input_hash=str(payload["input_hash"]),
                storage_uri=str(payload.get("storage_uri", "outbox://artifact")),
                dependency_ids=[],
                dependency_hashes={},
                created_by="outbox-artifact-consumer",
                source_job_id=None,
                generator_version=None,
                tool_versions={},
                knowledge_snapshot=None,
                status="CURRENT",
            )
        )
    return _journal_effect(
        session, event, "artifact-created-v1", "artifact-row", result_ref=artifact_id
    )


def default_handler_registry() -> OutboxHandlerRegistry:
    return OutboxHandlerRegistry(
        (
            HandlerRegistration(
                "project-created-v1", "project.created", frozenset({1}), _project_created
            ),
            HandlerRegistration(
                "artifact-created-v1", "artifact.created", frozenset({1}), _artifact_created
            ),
            HandlerRegistration(
                "build-completed-v1", "build.completed", frozenset({1}), _build_completed
            ),
        )
    )


__all__ = ["RecoveryService", "default_handler_registry"]
