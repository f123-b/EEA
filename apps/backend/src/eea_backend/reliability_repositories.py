"""SQLAlchemy repositories for M18A durable delivery records."""

from __future__ import annotations

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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from eea_backend.models import OutboxEventRecord, ProcessedEventRecord, SideEffectJournalRecord


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


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
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, event: OutboxEvent, *, commit: bool = True) -> OutboxEvent:
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
        self.session.add(record)
        try:
            if commit:
                self.session.commit()
            else:
                self.session.flush()
        except IntegrityError:
            self.session.rollback()
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

    def claim(
        self, *, worker_id: str, now: datetime, lease_seconds: int = 30
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
        candidate = self.session.scalar(
            select(OutboxEventRecord)
            .where(eligible)
            .order_by(
                OutboxEventRecord.available_at, OutboxEventRecord.created_at, OutboxEventRecord.id
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
        self.session.commit()
        if getattr(result, "rowcount", 0) != 1:
            return None
        return self.get(UUID(candidate.id))

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
        self.session.commit()
        return bool(getattr(result, "rowcount", 0) == 1)

    def reclaim_expired(self, *, now: datetime, limit: int = 100) -> int:
        rows = list(
            self.session.scalars(
                select(OutboxEventRecord)
                .where(
                    OutboxEventRecord.status == OutboxEventStatus.PROCESSING.value,
                    OutboxEventRecord.lease_expires_at < now,
                )
                .limit(limit)
            )
        )
        for row in rows:
            row.status = (
                OutboxEventStatus.RETRY.value
                if row.attempt_count < row.max_attempts
                else OutboxEventStatus.DEAD_LETTER.value
            )
            row.lease_owner = None
            row.lease_expires_at = None
            row.updated_at = now
            row.last_error = row.last_error or "lease expired during processing"
            row.revision += 1
        self.session.commit()
        return len(rows)


class SqlAlchemyProcessedEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

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

    def add(self, item: ProcessedEvent) -> ProcessedEvent:
        self.session.add(
            ProcessedEventRecord(
                id=str(item.id),
                event_id=str(item.event_id),
                consumer_id=item.consumer_id,
                event_payload_hash=item.event_payload_hash,
                processed_at=item.processed_at,
                result_ref=item.result_ref,
                result_hash=item.result_hash,
            )
        )
        self.session.flush()
        return item


class SqlAlchemySideEffectJournalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

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
        self.session.add(
            SideEffectJournalRecord(
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
        )
        self.session.flush()
        return item

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


__all__ = [
    "SqlAlchemyOutboxRepository",
    "SqlAlchemyProcessedEventRepository",
    "SqlAlchemySideEffectJournalRepository",
]
