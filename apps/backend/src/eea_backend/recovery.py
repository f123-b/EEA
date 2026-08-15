"""Bounded in-process outbox dispatcher and conservative startup recovery."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import timedelta
from hashlib import sha256
from threading import Event, Lock
from time import monotonic
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
    new_recovery_worker_id,
)
from eea_core.entities import utc_now
from eea_core.enums import DependencyNodeStatus, JobStatus
from eea_core.reliability import (
    OutboxEvent,
    OutboxEventStatus,
    ProcessedEvent,
    SideEffectJournal,
    SideEffectStatus,
    payload_sha256,
)
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from eea_backend.models import (
    ArtifactRecord,
    EngineeringDependencyNodeStateRecord,
    JobRecord,
    OutboxEventRecord,
    SideEffectJournalRecord,
)
from eea_backend.reliability_repositories import (
    BusyRetryPolicy,
    SqlAlchemyOutboxRepository,
    SqlAlchemyProcessedEventRepository,
    SqlAlchemySideEffectJournalRepository,
    commit_with_busy_retry,
)

SafeSideEffectReconciler = Callable[[Session, SideEffectJournal], str | None]


class SafeSideEffectReconcilerRegistry:
    """Allowlist for effects whose outcome is safe to verify and project again."""

    def __init__(self, reconcilers: dict[str, SafeSideEffectReconciler] | None = None) -> None:
        self._reconcilers = dict(reconcilers or {})

    def register(self, effect_type: str, reconciler: SafeSideEffectReconciler) -> None:
        if not effect_type:
            raise ValueError("effect_type is required")
        if effect_type in self._reconcilers:
            raise ValueError(f"safe reconciler already registered: {effect_type}")
        self._reconcilers[effect_type] = reconciler

    def get(self, effect_type: str) -> SafeSideEffectReconciler | None:
        return self._reconcilers.get(effect_type)


class RecoveryService:
    """Owns delivery/recovery semantics, never M18 authoritative graph propagation."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        registry: OutboxHandlerRegistry | None = None,
        clock: Clock | None = None,
        worker_id: str | None = None,
        crash_injector: CrashInjector | None = None,
        lease_seconds: int = 30,
        handler_budget_seconds: int = 10,
        safe_reconcilers: SafeSideEffectReconcilerRegistry | None = None,
        busy_retry: BusyRetryPolicy | None = None,
    ) -> None:
        if lease_seconds <= handler_budget_seconds:
            raise ValueError("lease_seconds must exceed handler_budget_seconds")
        self._session_factory = session_factory
        self.clock = clock or SystemClock()
        self.worker_id = worker_id or new_recovery_worker_id()
        self.crash_injector = crash_injector or NoopCrashInjector()
        self.registry = registry or default_handler_registry()
        self.lease_seconds = lease_seconds
        self.handler_budget_seconds = handler_budget_seconds
        self.safe_reconcilers = safe_reconcilers or SafeSideEffectReconcilerRegistry()
        self.busy_retry = busy_retry or BusyRetryPolicy()

    def recover_expired_outbox_leases(
        self, *, limit: int = 100, project_id: UUID | None = None
    ) -> int:
        with self._session_factory() as session:
            return SqlAlchemyOutboxRepository(session, busy_retry=self.busy_retry).reclaim_expired(
                now=self.clock.now(), limit=limit, project_id=project_id
            )

    def dispatch_ready_events(
        self,
        *,
        limit: int = 100,
        project_id: UUID | None = None,
        stop_requested: Callable[[], bool] | None = None,
    ) -> dict[str, int]:
        counts = {
            "processed": 0,
            "retry": 0,
            "dead_letter": 0,
            "reconcile_required": 0,
            "lease_lost": 0,
        }
        for _ in range(limit):
            if stop_requested is not None and stop_requested():
                break
            with self._session_factory() as session:
                if stop_requested is not None and stop_requested():
                    break
                event = SqlAlchemyOutboxRepository(session, busy_retry=self.busy_retry).claim(
                    worker_id=self.worker_id,
                    now=self.clock.now(),
                    lease_seconds=self.lease_seconds,
                    project_id=project_id,
                )
            if event is None:
                break
            try:
                result = self._consume_event(event, counts)
            except InjectedCrashError:
                raise
            except Exception as exc:  # handler failure is isolated from the producer transaction
                result = self._retry_or_dead(event, str(exc))
            if result is None:
                counts["lease_lost"] += 1
            elif result == OutboxEventStatus.PROCESSED:
                counts["processed"] += 1
            elif result == OutboxEventStatus.DEAD_LETTER:
                counts["dead_letter"] += 1
            else:
                counts["retry"] += 1
        return counts

    def _consume_event(
        self, event: OutboxEvent, counts: dict[str, int]
    ) -> OutboxEventStatus | None:
        del counts
        handlers = self.registry.for_event(event)
        if not handlers:
            return self._retry_or_dead(event, "no compatible registered handler")
        for registration in handlers:
            with self._session_factory() as consumer_session:

                def consume_registration(
                    registration: HandlerRegistration = registration,
                ) -> tuple[bool, bool]:
                    if not SqlAlchemyOutboxRepository(
                        consumer_session, busy_retry=self.busy_retry
                    ).renew(
                        event.id,
                        worker_id=self.worker_id,
                        now=self.clock.now(),
                        lease_seconds=self.lease_seconds,
                    ):
                        return False, False
                    processed_repo = SqlAlchemyProcessedEventRepository(
                        consumer_session, busy_retry=self.busy_retry
                    )
                    existing = processed_repo.get(event.id, registration.consumer_id)
                    if existing is not None:
                        if existing.event_payload_hash != event.payload_hash:
                            raise ValueError("processed event payload hash mismatch")
                        return True, False
                    handler_started = monotonic()
                    result_ref = registration.handler(consumer_session, event)
                    if monotonic() - handler_started > self.handler_budget_seconds:
                        raise TimeoutError("outbox handler execution budget exceeded")
                    _, inserted = processed_repo.add_idempotent(
                        ProcessedEvent(
                            event_id=event.id,
                            consumer_id=registration.consumer_id,
                            event_payload_hash=event.payload_hash,
                            processed_at=self.clock.now(),
                            result_ref=result_ref,
                            result_hash=sha256(result_ref.encode()).hexdigest()
                            if result_ref
                            else None,
                        )
                    )
                    if not inserted:
                        # The handler may have added a derived projection before
                        # a competing worker won the marker race. Its
                        # transaction is disposable; never commit that duplicate.
                        consumer_session.rollback()
                        return True, False
                    return True, True

                lease_valid, _ = commit_with_busy_retry(
                    consumer_session, self.busy_retry, consume_registration
                ) or (False, False)
                if not lease_valid:
                    return None
            self.crash_injector.maybe_crash(
                CrashPoint.AFTER_CONSUMER_EFFECT_COMMIT_BEFORE_OUTBOX_FINALIZE
            )
        with self._session_factory() as session:
            finalized = SqlAlchemyOutboxRepository(session, busy_retry=self.busy_retry).finalize(
                event.id,
                worker_id=self.worker_id,
                status=OutboxEventStatus.PROCESSED,
                now=self.clock.now(),
            )
        if not finalized:
            return None
        return OutboxEventStatus.PROCESSED

    def _retry_or_dead(self, event: OutboxEvent, error: str) -> OutboxEventStatus | None:
        now = self.clock.now()
        status = (
            OutboxEventStatus.DEAD_LETTER
            if event.attempt_count >= event.max_attempts
            else OutboxEventStatus.RETRY
        )
        available = now + EventOutboxService.retry_delay(event.attempt_count)
        with self._session_factory() as session:
            finalized = SqlAlchemyOutboxRepository(session, busy_retry=self.busy_retry).finalize(
                event.id,
                worker_id=self.worker_id,
                status=status,
                now=now,
                error=error[:4000],
                available_at=available,
            )
        return status if finalized else None

    def inspect_reconcile_required(
        self, *, limit: int = 100, project_id: UUID | None = None
    ) -> int:
        with self._session_factory() as session:
            statement = select(SideEffectJournalRecord).where(
                SideEffectJournalRecord.status == SideEffectStatus.RECONCILE_REQUIRED.value
            )
            if project_id is not None:
                statement = statement.join(
                    OutboxEventRecord,
                    SideEffectJournalRecord.event_id == OutboxEventRecord.id,
                ).where(OutboxEventRecord.project_id == str(project_id))
            return sum(1 for _ in session.scalars(statement.limit(limit)))

    def reconcile_side_effects(self, *, limit: int = 100, project_id: UUID | None = None) -> int:
        """Reconcile only effects registered as safe; unknown effects remain visible."""

        with self._session_factory() as session:

            def reconcile() -> int:
                statement = select(SideEffectJournalRecord).where(
                    SideEffectJournalRecord.status == SideEffectStatus.RECONCILE_REQUIRED.value
                )
                if project_id is not None:
                    statement = statement.join(
                        OutboxEventRecord,
                        SideEffectJournalRecord.event_id == OutboxEventRecord.id,
                    ).where(OutboxEventRecord.project_id == str(project_id))
                rows = list(session.scalars(statement.limit(limit)))
                reconciled = 0
                journal = SqlAlchemySideEffectJournalRepository(session, busy_retry=self.busy_retry)
                for record in rows:
                    item = journal.get(UUID(record.event_id), record.consumer_id, record.effect_key)
                    reconciler = self.safe_reconcilers.get(record.effect_type)
                    if item is None or reconciler is None:
                        continue
                    result_ref = reconciler(session, item)
                    journal.mark_applied(item, result_ref=result_ref, now=self.clock.now())
                    reconciled += 1
                return reconciled

            return int(commit_with_busy_retry(session, self.busy_retry, reconcile) or 0)

    def reconcile_interrupted_jobs(
        self,
        *,
        cutoff: timedelta = timedelta(minutes=15),
        limit: int = 100,
        project_id: UUID | None = None,
    ) -> int:
        threshold = self.clock.now() - cutoff
        with self._session_factory() as session:

            def reconcile() -> int:
                rows = list(
                    session.scalars(
                        select(JobRecord)
                        .where(
                            JobRecord.status == JobStatus.RUNNING.value,
                            JobRecord.updated_at < threshold,
                            *([JobRecord.project_id == str(project_id)] if project_id else []),
                        )
                        .limit(limit)
                    )
                )
                reconciled = 0
                now = self.clock.now()
                for row in rows:
                    result = session.execute(
                        update(JobRecord)
                        .where(
                            JobRecord.id == row.id,
                            JobRecord.revision == row.revision,
                            JobRecord.status == JobStatus.RUNNING.value,
                            JobRecord.updated_at == row.updated_at,
                            JobRecord.updated_at < threshold,
                        )
                        .execution_options(synchronize_session=False)
                        .values(
                            status=JobStatus.FAILED_NEEDS_RECONCILE.value,
                            error_message="interrupted job requires explicit reconciliation",
                            updated_at=now,
                            revision=JobRecord.revision + 1,
                        )
                    )
                    reconciled += int(getattr(result, "rowcount", 0) == 1)
                return reconciled

            return int(commit_with_busy_retry(session, self.busy_retry, reconcile) or 0)

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
            interrupted_jobs = sum(
                1
                for _ in session.scalars(
                    select(JobRecord).where(
                        JobRecord.project_id == str(project_id),
                        JobRecord.status == JobStatus.FAILED_NEEDS_RECONCILE.value,
                    )
                )
            )
            freshness_rows = list(
                session.scalars(
                    select(EngineeringDependencyNodeStateRecord).where(
                        EngineeringDependencyNodeStateRecord.project_id == str(project_id)
                    )
                )
            )
        pending = [event for event in events if event.status != OutboxEventStatus.PROCESSED]
        transactional = {
            "pending": sum(event.status is OutboxEventStatus.PENDING for event in pending),
            "processing": sum(event.status is OutboxEventStatus.PROCESSING for event in pending),
            "retry": sum(event.status is OutboxEventStatus.RETRY for event in pending),
            "dead_letter": sum(event.status is OutboxEventStatus.DEAD_LETTER for event in pending),
            "reconcile_required": reconcile_required,
            "interrupted_jobs": interrupted_jobs,
        }
        freshness = {
            "stale": sum(row.status == DependencyNodeStatus.STALE.value for row in freshness_rows),
            "invalid": sum(
                row.status == DependencyNodeStatus.INVALID.value for row in freshness_rows
            ),
        }
        status = (
            "RECOVERY_REQUIRED"
            if any(transactional.values())
            else "DEGRADED"
            if any(freshness.values())
            else "CONSISTENT"
        )
        return {
            "project_id": str(project_id),
            "status": status,
            "transactional_recovery": transactional,
            "engineering_freshness": freshness,
        }

    def startup_recover(self, *, batch_limit: int = 100) -> dict[str, Any]:
        reclaimed = self.recover_expired_outbox_leases(limit=batch_limit)
        interrupted = self.reconcile_interrupted_jobs(limit=batch_limit)
        dispatched = self.dispatch_ready_events(limit=batch_limit)
        return {"reclaimed": reclaimed, "interrupted_jobs": interrupted, "dispatch": dispatched}


class OutboxDispatcher:
    """Lifecycle-owned polling dispatcher with a joinable cooperative worker."""

    def __init__(
        self,
        service: RecoveryService,
        *,
        batch_limit: int = 100,
        poll_interval_seconds: float = 1.0,
        graceful_timeout_seconds: float | None = None,
    ) -> None:
        if graceful_timeout_seconds is not None and graceful_timeout_seconds <= 0:
            raise ValueError("graceful_timeout_seconds must be positive")
        self.service = service
        self.batch_limit = batch_limit
        self.poll_interval_seconds = poll_interval_seconds
        # This is a soft shutdown deadline.  It is deliberately longer than
        # the legal handler budget by default; stop() still joins the worker
        # after the deadline instead of cancelling a non-cancellable sync call.
        self.graceful_timeout_seconds = (
            float(service.handler_budget_seconds + 1)
            if graceful_timeout_seconds is None
            else float(graceful_timeout_seconds)
        )
        self.last_summary: dict[str, Any] = {}
        self._stop: asyncio.Event | None = None
        self._wake: asyncio.Event | None = None
        self._task: asyncio.Task[None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._stop_requested = Event()
        self._stop_lock = asyncio.Lock()
        self._dispatch_lock = Lock()

    def dispatch_once(self, *, project_id: UUID | None = None) -> dict[str, Any]:
        with self._dispatch_lock:
            stop_requested = self._stop_requested.is_set if self._task is not None else None
            return self._dispatch_once(
                project_id=project_id,
                stop_requested=stop_requested,
            )

    def _dispatch_once(
        self,
        *,
        project_id: UUID | None = None,
        stop_requested: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        if stop_requested is not None and stop_requested():
            return summary
        summary["reclaimed"] = self.service.recover_expired_outbox_leases(
            limit=self.batch_limit, project_id=project_id
        )
        if stop_requested is not None and stop_requested():
            self.last_summary = summary
            return summary
        summary["interrupted_jobs"] = self.service.reconcile_interrupted_jobs(
            limit=self.batch_limit, project_id=project_id
        )
        if stop_requested is not None and stop_requested():
            self.last_summary = summary
            return summary
        summary["dispatch"] = self.service.dispatch_ready_events(
            limit=self.batch_limit,
            project_id=project_id,
            stop_requested=stop_requested,
        )
        self.last_summary = summary
        return summary

    def wake(self) -> None:
        if self._loop is not None and self._wake is not None:
            self._loop.call_soon_threadsafe(self._wake.set)

    def start(self) -> None:
        if self._task is not None:
            return
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()
        self._stop_requested.clear()
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="eea-outbox-dispatcher",
        )
        self._task = asyncio.create_task(self._run(), name="eea-outbox-dispatcher")

    async def _run(self) -> None:
        assert self._stop is not None
        assert self._wake is not None
        assert self._executor is not None
        loop = asyncio.get_running_loop()
        executor = self._executor
        while not self._stop.is_set():
            # The executor belongs to this dispatcher and is shut down only
            # after this task has joined its final synchronous operation.
            await loop.run_in_executor(executor, self.dispatch_once)
            if self._stop.is_set():
                break
            self._wake.clear()
            with suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=self.poll_interval_seconds)

    async def stop(self) -> None:
        async with self._stop_lock:
            if self._task is None or self._stop is None:
                return
            self._stop_requested.set()
            self._stop.set()
            self.wake()
            task = self._task
            executor = self._executor
            try:
                try:
                    await asyncio.wait_for(
                        asyncio.shield(task), timeout=self.graceful_timeout_seconds
                    )
                except TimeoutError:
                    # A synchronous handler cannot be cancelled safely.  The
                    # deadline is diagnostic only; always join the task before
                    # disposing its database resources.
                    await task
            finally:
                self._task = None
                self._loop = None
                self._stop = None
                self._wake = None
                self._executor = None
                if executor is not None:
                    # The executor future is complete after task joined.  The
                    # wait is retained as the lifecycle safety invariant.
                    executor.shutdown(wait=True)


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
        raise ValueError("authoritative Artifact is missing for artifact.created")
    if record.project_id != str(payload["project_id"]):
        raise ValueError("artifact.created project scope does not match Artifact")
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


__all__ = [
    "OutboxDispatcher",
    "RecoveryService",
    "SafeSideEffectReconcilerRegistry",
    "default_handler_registry",
]
