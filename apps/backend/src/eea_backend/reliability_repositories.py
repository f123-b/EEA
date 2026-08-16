"""SQLAlchemy repositories for M18A durable delivery records."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from eea_core.reliability import (
    OutboxEvent,
    OutboxEventStatus,
    ProcessedEvent,
    SideEffectJournal,
    SideEffectStatus,
)
from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from eea_backend.models import OutboxEventRecord, ProcessedEventRecord, SideEffectJournalRecord


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True)
class BusyRetryPolicy:
    """Small bounded retry policy for SQLite's explicit busy/locked failures."""

    attempts: int = 3
    delay_seconds: float = 0.01
    sleep: Callable[[float], None] = time.sleep


def _is_sqlite_busy(error: OperationalError) -> bool:
    message = str(getattr(error, "orig", error)).lower()
    return "database is locked" in message or "database table is locked" in message


def commit_with_busy_retry[T](
    session: Session,
    policy: BusyRetryPolicy,
    operation: Callable[[], T] | None = None,
) -> T | None:
    """Run and commit a complete unit of work with bounded SQLite retry.

    A retry is only safe when the caller supplies the complete operation.  A
    bare commit is deliberately attempted once and propagates a busy failure;
    retrying only that commit after rollback could report a false success or
    silently discard the caller's unit of work.
    """

    if operation is None:
        try:
            session.commit()
            return None
        except OperationalError as error:
            if _is_sqlite_busy(error):
                session.rollback()
            raise
    for attempt in range(policy.attempts):
        try:
            result = operation()
            session.commit()
            return result
        except OperationalError as error:
            if not _is_sqlite_busy(error) or attempt + 1 >= policy.attempts:
                raise
            session.rollback()
            policy.sleep(policy.delay_seconds * (attempt + 1))
    raise RuntimeError("bounded SQLite busy retry exhausted")


def _event(record: OutboxEventRecord) -> OutboxEvent:
    return OutboxEvent(
        id=UUID(record.id),
        schema_version=record.schema_version,
        project_id=UUID(record.project_id) if record.project_id else None,
        event_type=record.event_type,
        event_version=record.event_version,
        aggregate_type=record.aggregate_type,
        aggregate_id=record.aggregate_id,
        aggregate_revision=record.aggregate_revision,
        event_key=record.event_key,
        payload=record.payload,
        payload_hash=record.payload_hash,
        correlation_id=UUID(record.correlation_id) if record.correlation_id else None,
        causation_id=UUID(record.causation_id) if record.causation_id else None,
        status=OutboxEventStatus(record.status),
        attempt_count=record.attempt_count,
        max_attempts=record.max_attempts,
        available_at=_utc(record.available_at),
        lease_owner=record.lease_owner,
        lease_expires_at=_utc(record.lease_expires_at) if record.lease_expires_at else None,
        last_error=record.last_error,
        processed_at=_utc(record.processed_at) if record.processed_at else None,
        created_at=_utc(record.created_at),
        updated_at=_utc(record.updated_at),
        revision=record.revision,
    )


class SqlAlchemyOutboxRepository:
    def __init__(self, session: Session, *, busy_retry: BusyRetryPolicy | None = None) -> None:
        self.session = session
        self.busy_retry = busy_retry or BusyRetryPolicy()

    def add(self, event: OutboxEvent, *, commit: bool = True) -> OutboxEvent:
        def insert() -> OutboxEventRecord:
            record = OutboxEventRecord(
                id=str(event.id),
                schema_version=event.schema_version,
                project_id=str(event.project_id) if event.project_id else None,
                event_type=event.event_type,
                event_version=event.event_version,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                aggregate_revision=event.aggregate_revision,
                event_key=event.event_key,
                payload=event.payload,
                payload_hash=event.payload_hash,
                correlation_id=str(event.correlation_id) if event.correlation_id else None,
                causation_id=str(event.causation_id) if event.causation_id else None,
                status=event.status.value,
                attempt_count=event.attempt_count,
                max_attempts=event.max_attempts,
                available_at=event.available_at,
                lease_owner=event.lease_owner,
                lease_expires_at=event.lease_expires_at,
                last_error=event.last_error,
                processed_at=event.processed_at,
                created_at=event.created_at,
                updated_at=event.updated_at,
                revision=event.revision,
            )
            with self.session.begin_nested():
                self.session.add(record)
                self.session.flush()
            return record

        try:
            if commit:
                record = commit_with_busy_retry(self.session, self.busy_retry, insert)
                assert record is not None
            else:
                record = insert()
        except IntegrityError:
            existing = self.get_by_key(event.event_key)
            if existing and existing.payload_hash == event.payload_hash:
                return existing
            raise ValueError("event_key already exists with a different payload_hash") from None
        return _event(record)

    def get(self, event_id: UUID) -> OutboxEvent | None:
        record = self.session.get(OutboxEventRecord, str(event_id))
        return _event(record) if record else None

    def get_by_key(self, event_key: str) -> OutboxEvent | None:
        record = self.session.scalar(
            select(OutboxEventRecord).where(OutboxEventRecord.event_key == event_key)
        )
        return _event(record) if record else None

    def list(self, *, project_id: UUID | None = None) -> list[OutboxEvent]:
        statement = select(OutboxEventRecord).order_by(
            OutboxEventRecord.available_at, OutboxEventRecord.created_at, OutboxEventRecord.id
        )
        if project_id is not None:
            statement = statement.where(OutboxEventRecord.project_id == str(project_id))
        return [_event(record) for record in self.session.scalars(statement)]

    def diagnostics(self, *, now: datetime, project_id: UUID | None = None) -> dict[str, object]:
        statement = select(OutboxEventRecord)
        if project_id is not None:
            statement = statement.where(OutboxEventRecord.project_id == str(project_id))
        rows = list(self.session.scalars(statement))
        processing = [row for row in rows if row.status == OutboxEventStatus.PROCESSING.value]
        pending = [
            row
            for row in rows
            if row.status in {OutboxEventStatus.PENDING.value, OutboxEventStatus.RETRY.value}
        ]
        oldest_pending = min((row.available_at for row in pending), default=None)
        expired = sum(
            row.lease_expires_at is not None and _utc(row.lease_expires_at) < _utc(now)
            for row in processing
        )
        age = (
            max(0.0, (_utc(now) - _utc(oldest_pending)).total_seconds()) if oldest_pending else 0.0
        )
        return {
            "expired_processing_count": expired,
            "oldest_pending_at": _utc(oldest_pending) if oldest_pending else None,
            "oldest_pending_age_seconds": age,
            # Every outstanding event is counted once.  Expiry is an
            # orthogonal diagnostic subset, not an additional count.
            "pending_recovery_count": len(pending) + len(processing),
            "processing_count": len(processing),
            "dead_letter_count": sum(
                row.status == OutboxEventStatus.DEAD_LETTER.value for row in rows
            ),
            "total": len(rows),
        }

    def claim(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int = 30,
        project_id: UUID | None = None,
    ) -> OutboxEvent | None:
        eligible = or_(
            and_(
                OutboxEventRecord.status.in_(
                    [OutboxEventStatus.PENDING.value, OutboxEventStatus.RETRY.value]
                ),
                OutboxEventRecord.available_at <= now,
            ),
            and_(
                OutboxEventRecord.status == OutboxEventStatus.PROCESSING.value,
                OutboxEventRecord.lease_expires_at < now,
            ),
        )
        if project_id is not None:
            eligible = and_(eligible, OutboxEventRecord.project_id == str(project_id))

        def claim_one() -> UUID | None:
            self.session.expire_all()
            candidate = self.session.scalar(
                select(OutboxEventRecord)
                .where(eligible)
                .order_by(
                    OutboxEventRecord.available_at,
                    OutboxEventRecord.created_at,
                    OutboxEventRecord.id,
                )
                .limit(1)
            )
            if candidate is None:
                return None
            expires = now + timedelta(seconds=lease_seconds)
            result = self.session.execute(
                update(OutboxEventRecord)
                .where(
                    OutboxEventRecord.id == candidate.id,
                    OutboxEventRecord.revision == candidate.revision,
                    eligible,
                )
                .execution_options(synchronize_session=False)
                .values(
                    status=OutboxEventStatus.PROCESSING.value,
                    lease_owner=worker_id,
                    lease_expires_at=expires,
                    attempt_count=OutboxEventRecord.attempt_count + 1,
                    updated_at=now,
                    revision=OutboxEventRecord.revision + 1,
                )
            )
            if getattr(result, "rowcount", 0) != 1:
                return None
            return UUID(candidate.id)

        claimed_id = commit_with_busy_retry(self.session, self.busy_retry, claim_one)
        if claimed_id is None:
            return None
        self.session.expire_all()
        return self.get(claimed_id)

    def renew(
        self,
        event_id: UUID,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int = 30,
    ) -> bool:
        def renew_one() -> bool:
            result = self.session.execute(
                update(OutboxEventRecord)
                .where(
                    OutboxEventRecord.id == str(event_id),
                    OutboxEventRecord.status == OutboxEventStatus.PROCESSING.value,
                    OutboxEventRecord.lease_owner == worker_id,
                    OutboxEventRecord.lease_expires_at >= now,
                )
                .execution_options(synchronize_session=False)
                .values(lease_expires_at=now + timedelta(seconds=lease_seconds), updated_at=now)
            )
            return bool(getattr(result, "rowcount", 0) == 1)

        return bool(commit_with_busy_retry(self.session, self.busy_retry, renew_one))

    def finalize(
        self,
        event_id: UUID,
        *,
        worker_id: str,
        status: OutboxEventStatus,
        now: datetime,
        error: str | None = None,
        available_at: datetime | None = None,
    ) -> bool:
        values: dict[str, Any] = {
            "status": status.value,
            "lease_owner": None,
            "lease_expires_at": None,
            "last_error": error,
            "updated_at": now,
            "processed_at": now if status is OutboxEventStatus.PROCESSED else None,
            "revision": OutboxEventRecord.revision + 1,
        }
        if available_at is not None:
            values["available_at"] = available_at

        def finalize_one() -> bool:
            result = self.session.execute(
                update(OutboxEventRecord)
                .where(
                    OutboxEventRecord.id == str(event_id),
                    OutboxEventRecord.status == OutboxEventStatus.PROCESSING.value,
                    OutboxEventRecord.lease_owner == worker_id,
                    or_(
                        OutboxEventRecord.lease_expires_at.is_(None),
                        OutboxEventRecord.lease_expires_at >= now,
                    ),
                )
                .execution_options(synchronize_session=False)
                .values(**values)
            )
            return bool(getattr(result, "rowcount", 0) == 1)

        return bool(commit_with_busy_retry(self.session, self.busy_retry, finalize_one))

    def reclaim_expired(
        self, *, now: datetime, limit: int = 100, project_id: UUID | None = None
    ) -> int:
        def reclaim() -> int:
            rows = list(
                self.session.scalars(
                    select(OutboxEventRecord)
                    .where(
                        OutboxEventRecord.status == OutboxEventStatus.PROCESSING.value,
                        OutboxEventRecord.lease_expires_at < now,
                        *([OutboxEventRecord.project_id == str(project_id)] if project_id else []),
                    )
                    .limit(limit)
                )
            )
            reclaimed = 0
            for row in rows:
                status = (
                    OutboxEventStatus.RETRY.value
                    if row.attempt_count < row.max_attempts
                    else OutboxEventStatus.DEAD_LETTER.value
                )
                lease_owner = row.lease_owner
                lease_condition = (
                    OutboxEventRecord.lease_owner == lease_owner
                    if lease_owner is not None
                    else OutboxEventRecord.lease_owner.is_(None)
                )
                result = self.session.execute(
                    update(OutboxEventRecord)
                    .where(
                        OutboxEventRecord.id == row.id,
                        OutboxEventRecord.revision == row.revision,
                        OutboxEventRecord.status == OutboxEventStatus.PROCESSING.value,
                        OutboxEventRecord.lease_expires_at == row.lease_expires_at,
                        OutboxEventRecord.updated_at == row.updated_at,
                        lease_condition,
                    )
                    .execution_options(synchronize_session=False)
                    .values(
                        status=status,
                        lease_owner=None,
                        lease_expires_at=None,
                        updated_at=now,
                        last_error=row.last_error or "lease expired during processing",
                        revision=OutboxEventRecord.revision + 1,
                    )
                )
                reclaimed += int(getattr(result, "rowcount", 0) == 1)
            return reclaimed

        return int(commit_with_busy_retry(self.session, self.busy_retry, reclaim) or 0)


class SqlAlchemyProcessedEventRepository:
    def __init__(self, session: Session, *, busy_retry: BusyRetryPolicy | None = None) -> None:
        self.session = session
        self.busy_retry = busy_retry or BusyRetryPolicy()

    def get(self, event_id: UUID, consumer_id: str) -> ProcessedEvent | None:
        record = self.session.scalar(
            select(ProcessedEventRecord).where(
                ProcessedEventRecord.event_id == str(event_id),
                ProcessedEventRecord.consumer_id == consumer_id,
            )
        )
        if record is None:
            return None
        return ProcessedEvent(
            id=UUID(record.id),
            event_id=UUID(record.event_id),
            consumer_id=record.consumer_id,
            event_payload_hash=record.event_payload_hash,
            processed_at=_utc(record.processed_at),
            result_ref=record.result_ref,
            result_hash=record.result_hash,
        )

    def add_idempotent(self, item: ProcessedEvent) -> tuple[ProcessedEvent, bool]:
        record = ProcessedEventRecord(
            id=str(item.id),
            event_id=str(item.event_id),
            consumer_id=item.consumer_id,
            event_payload_hash=item.event_payload_hash,
            processed_at=item.processed_at,
            result_ref=item.result_ref,
            result_hash=item.result_hash,
        )
        for attempt in range(self.busy_retry.attempts):
            try:
                with self.session.begin_nested():
                    self.session.add(record)
                    self.session.flush()
            except IntegrityError:
                existing = self.get(item.event_id, item.consumer_id)
                if existing is None:
                    raise ValueError(
                        "processed event identity race could not be resolved"
                    ) from None
                if existing.event_payload_hash != item.event_payload_hash:
                    raise ValueError("processed event payload hash mismatch") from None
                return existing, False
            except OperationalError as error:
                if not _is_sqlite_busy(error) or attempt + 1 >= self.busy_retry.attempts:
                    raise
                self.busy_retry.sleep(self.busy_retry.delay_seconds * (attempt + 1))
                continue
            return item, True
        raise RuntimeError("bounded SQLite busy retry exhausted")

    def add(self, item: ProcessedEvent) -> ProcessedEvent:
        return self.add_idempotent(item)[0]


class SqlAlchemySideEffectJournalRepository:
    def __init__(self, session: Session, *, busy_retry: BusyRetryPolicy | None = None) -> None:
        self.session = session
        self.busy_retry = busy_retry or BusyRetryPolicy()

    def get(self, event_id: UUID, consumer_id: str, effect_key: str) -> SideEffectJournal | None:
        record = self.session.scalar(
            select(SideEffectJournalRecord).where(
                SideEffectJournalRecord.event_id == str(event_id),
                SideEffectJournalRecord.consumer_id == consumer_id,
                SideEffectJournalRecord.effect_key == effect_key,
            )
        )
        if record is None:
            return None
        return SideEffectJournal(
            id=UUID(record.id),
            event_id=UUID(record.event_id),
            consumer_id=record.consumer_id,
            effect_key=record.effect_key,
            effect_type=record.effect_type,
            request_hash=record.request_hash,
            status=SideEffectStatus(record.status),
            attempt_count=record.attempt_count,
            result_ref=record.result_ref,
            result_hash=record.result_hash,
            last_error=record.last_error,
            prepared_at=_utc(record.prepared_at),
            applied_at=_utc(record.applied_at) if record.applied_at else None,
            updated_at=_utc(record.updated_at),
        )

    def prepare(self, item: SideEffectJournal) -> SideEffectJournal:
        existing = self.get(item.event_id, item.consumer_id, item.effect_key)
        if existing is not None:
            if existing.request_hash != item.request_hash:
                raise ValueError("side-effect request_hash mismatch")
            return existing
        record = SideEffectJournalRecord(
            id=str(item.id),
            event_id=str(item.event_id),
            consumer_id=item.consumer_id,
            effect_key=item.effect_key,
            effect_type=item.effect_type,
            request_hash=item.request_hash,
            status=item.status.value,
            attempt_count=item.attempt_count,
            result_ref=item.result_ref,
            result_hash=item.result_hash,
            last_error=item.last_error,
            prepared_at=item.prepared_at,
            applied_at=item.applied_at,
            updated_at=item.updated_at,
        )
        for attempt in range(self.busy_retry.attempts):
            try:
                with self.session.begin_nested():
                    self.session.add(record)
                    self.session.flush()
            except IntegrityError:
                existing = self.get(item.event_id, item.consumer_id, item.effect_key)
                if existing is None:
                    raise ValueError("side-effect identity race could not be resolved") from None
                if existing.request_hash != item.request_hash:
                    raise ValueError("side-effect request_hash mismatch") from None
                return existing
            except OperationalError as error:
                if not _is_sqlite_busy(error) or attempt + 1 >= self.busy_retry.attempts:
                    raise
                self.busy_retry.sleep(self.busy_retry.delay_seconds * (attempt + 1))
                continue
            return item
        raise RuntimeError("bounded SQLite busy retry exhausted")

    def mark_applied(
        self, item: SideEffectJournal, *, result_ref: str | None, now: datetime
    ) -> None:
        self.session.execute(
            update(SideEffectJournalRecord)
            .where(SideEffectJournalRecord.id == str(item.id))
            .values(
                status=SideEffectStatus.APPLIED.value,
                result_ref=result_ref,
                applied_at=now,
                updated_at=now,
            )
        )
        self.session.flush()

    def mark_reconcile_required(
        self, item: SideEffectJournal, *, error: str, now: datetime
    ) -> None:
        self.session.execute(
            update(SideEffectJournalRecord)
            .where(SideEffectJournalRecord.id == str(item.id))
            .values(
                status=SideEffectStatus.RECONCILE_REQUIRED.value, last_error=error, updated_at=now
            )
        )
        self.session.flush()

    def mark_failed(self, item: SideEffectJournal, *, error: str, now: datetime) -> None:
        self.session.execute(
            update(SideEffectJournalRecord)
            .where(SideEffectJournalRecord.id == str(item.id))
            .values(
                status=SideEffectStatus.FAILED.value,
                last_error=error,
                updated_at=now,
            )
        )
        self.session.flush()


__all__ = [
    "BusyRetryPolicy",
    "SqlAlchemyOutboxRepository",
    "SqlAlchemyProcessedEventRepository",
    "SqlAlchemySideEffectJournalRepository",
    "commit_with_busy_retry",
]
