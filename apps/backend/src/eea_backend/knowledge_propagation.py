"""Transactional propagation from canonical engineering changes to memory.

The synchronous path is used by API mutations before their transaction commits.
The same operation is idempotently replayed by the outbox consumer after a
crash, so a committed canonical change cannot leave a trusted memory active.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from eea_application.knowledge_authority import EvidenceContext, KnowledgeFreshnessService
from eea_application.reliability import EventOutboxService
from eea_core.entities import KnowledgeEntry
from eea_core.enums import EvidenceType, KnowledgeLifecycle
from eea_core.reliability import OutboxEvent, payload_sha256, stable_event_key
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from eea_backend.knowledge_repositories import (
    SqlAlchemyKnowledgeAuditRepository,
    SqlAlchemyKnowledgeEntryRepository,
    _to_entry,
)
from eea_backend.models import (
    ClaimConflictRecord,
    EngineeringClaimRecord,
    EvidenceRecord,
    KnowledgeEntryRecord,
    SourceWorkspaceRecord,
)
from eea_backend.reliability_repositories import SqlAlchemyOutboxRepository

MEMORY_EVENT_TYPES = frozenset(
    {
        "ClaimChanged",
        "ClaimConflictOpened",
        "ClaimConflictResolved",
        "EvidenceInvalidated",
        "EvidenceSuperseded",
        "SourceRevisionChanged",
    }
)


def _uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _evidence_contexts(session: Session, entry: KnowledgeEntry) -> tuple[EvidenceContext, ...]:
    if not entry.evidence_ids:
        return ()
    records = session.scalars(
        select(EvidenceRecord).where(
            EvidenceRecord.id.in_([str(value) for value in entry.evidence_ids])
        )
    )
    contexts: list[EvidenceContext] = []
    for record in records:
        locator = dict(record.locator)
        contexts.append(
            EvidenceContext(
                evidence_id=UUID(record.id),
                project_id=_uuid(record.project_id),
                evidence_type=EvidenceType(record.evidence_type),
                locator=locator,
                source_revision_id=_uuid(locator.get("source_revision_id")),
                producer=str(locator["producer"]) if locator.get("producer") else None,
                producer_version=(
                    str(locator["producer_version"]) if locator.get("producer_version") else None
                ),
                recorded_at=None,
            )
        )
    return tuple(contexts)


def _open_conflict(session: Session, claim_ids: Iterable[UUID]) -> bool:
    ids = [str(value) for value in claim_ids]
    if not ids:
        return False
    return (
        session.scalar(
            select(ClaimConflictRecord.id)
            .where(
                ClaimConflictRecord.status == "OPEN",
                or_(
                    ClaimConflictRecord.claim_a_id.in_(ids),
                    ClaimConflictRecord.claim_b_id.in_(ids),
                ),
            )
            .limit(1)
        )
        is not None
    )


def _current_source(session: Session, project_id: UUID | None) -> UUID | None:
    if project_id is None:
        return None
    value = session.scalar(
        select(SourceWorkspaceRecord.current_source_revision_id).where(
            SourceWorkspaceRecord.project_id == str(project_id)
        )
    )
    return _uuid(value)


def _stale_evidence_ids(
    entry: KnowledgeEntry, contexts: tuple[EvidenceContext, ...]
) -> tuple[UUID, ...]:
    stale: list[UUID] = []
    loaded = {item.evidence_id for item in contexts}
    for evidence in contexts:
        locator = evidence.locator
        evidence_source = _uuid(locator.get("source_revision_id"))
        if (
            locator.get("valid") is False
            or locator.get("stale") is True
            or str(locator.get("status", "PASS")).upper()
            in {"STALE", "INVALID", "SUPERSEDED", "FAIL"}
            or (
                evidence_source is not None
                and entry.source_revision_id is not None
                and evidence_source != entry.source_revision_id
            )
        ):
            stale.append(evidence.evidence_id)
    stale.extend(value for value in entry.evidence_ids if value not in loaded)
    return tuple(dict.fromkeys(stale))


def _claim_revision_changed(session: Session, entry: KnowledgeEntry, claim_ids: set[str]) -> bool:
    snapshot = entry.metadata.get("claim_revision_snapshot")
    if not isinstance(snapshot, dict):
        return bool(claim_ids.intersection(str(value) for value in entry.claim_ids))
    records = list(
        session.scalars(
            select(EngineeringClaimRecord).where(
                EngineeringClaimRecord.id.in_([str(value) for value in entry.claim_ids])
            )
        )
    )
    record_ids = {str(record.id) for record in records}
    for record in records:
        if str(record.id) in claim_ids or str(record.revision) != str(snapshot.get(record.id)):
            return True
    return any(str(value) not in record_ids for value in entry.claim_ids)


def _data(entry: KnowledgeEntry) -> dict[str, object]:
    return entry.model_dump(mode="json")


def reconcile_memory_entries(
    session: Session,
    *,
    event_type: str,
    project_id: UUID | None,
    claim_ids: Iterable[UUID] = (),
    evidence_ids: Iterable[UUID] = (),
    source_revision_id: UUID | None = None,
    principal_id: str = "system:m23r",
    user_id: str = "system:m23r",
    session_id: str = "outbox",
    request_id: str = "outbox",
    reason: str | None = None,
) -> int:
    """Reconcile impacted entries and append an audit record per transition."""

    claim_set = {str(value) for value in claim_ids}
    evidence_set = {str(value) for value in evidence_ids}
    changed = 0
    repository = SqlAlchemyKnowledgeEntryRepository(session)
    records = session.scalars(
        select(KnowledgeEntryRecord).where(
            *([KnowledgeEntryRecord.project_id == str(project_id)] if project_id else [])
        )
    )
    for record in records:
        entry = _to_entry(record)
        entry_claims = {str(value) for value in entry.claim_ids}
        entry_evidence = {str(value) for value in entry.evidence_ids}
        relevant = (
            (
                event_type in {"ClaimConflictOpened", "ClaimConflictResolved"}
                and bool(claim_set.intersection(entry_claims))
            )
            or bool(claim_set.intersection(entry_claims))
            or bool(evidence_set.intersection(entry_evidence))
        )
        if source_revision_id is not None and entry.source_revision_id == source_revision_id:
            relevant = True
        if event_type == "SourceRevisionChanged" and project_id == entry.project_id:
            relevant = True
        if not relevant:
            continue

        conflict_open = _open_conflict(session, entry.claim_ids)
        current_source_id = _current_source(session, entry.project_id)
        stale_ids = _stale_evidence_ids(entry, _evidence_contexts(session, entry))
        claim_changed = event_type == "ClaimChanged" and _claim_revision_changed(
            session, entry, claim_set
        )
        if claim_changed and not stale_ids and not conflict_open:
            # ``KnowledgeFreshnessService`` needs a non-empty dependency set
            # to produce a stale transition.  The entry id is only a marker;
            # the audit metadata carries the actual ClaimChanged event.
            stale_ids = (entry.id,)
        if (
            event_type == "SourceRevisionChanged"
            and entry.source_revision_id is not None
            and current_source_id != entry.source_revision_id
        ):
            stale_ids = stale_ids or (entry.id,)

        if entry.lifecycle is KnowledgeLifecycle.CONFLICTED and not conflict_open:
            # A resolved canonical conflict never silently restores the old
            # trust; the user must explicitly revalidate the projection.
            continue
        before = _data(entry)
        updated, decision = KnowledgeFreshnessService().reconcile(
            entry,
            current_source_revision_id=current_source_id,
            conflict_open=conflict_open,
            stale_evidence_ids=stale_ids,
        )
        if updated == entry:
            continue
        metadata = dict(updated.metadata)
        metadata.update(
            {
                "freshness_status": decision.status,
                "freshness_reason": decision.reason or reason or event_type,
                "last_propagation_event": event_type,
            }
        )
        updated = updated.model_copy(update={"metadata": metadata})
        saved = repository.save(updated, expected_revision=entry.revision, commit=False)
        if saved is None:
            # Another request won the CAS.  The outbox replay will retry the
            # same deterministic transition without overwriting it.
            continue
        SqlAlchemyKnowledgeAuditRepository(session).add(
            entry_id=saved.id,
            project_id=saved.project_id,
            principal_id=principal_id,
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            action=decision.status.lower() + "_transition",
            before=before,
            after=_data(saved),
            reason=decision.reason or reason or event_type,
            commit=False,
        )
        changed += 1
    return changed


def enqueue_memory_event(
    session: Session,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    aggregate_revision: int | None,
    project_id: UUID | None,
    payload: dict[str, object],
) -> None:
    if event_type not in MEMORY_EVENT_TYPES:
        raise ValueError(f"unsupported memory propagation event: {event_type}")
    EventOutboxService(SqlAlchemyOutboxRepository(session)).enqueue(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        aggregate_revision=aggregate_revision,
        event_key=stable_event_key(event_type, aggregate_type, aggregate_id, aggregate_revision),
        payload=payload,
        payload_hash=payload_sha256(payload),
        project_id=project_id,
        commit=False,
    )


def handle_memory_event(session: Session, event: OutboxEvent) -> str:
    payload = event.payload
    event_type = str(event.event_type)
    project_id = _uuid(payload.get("project_id")) if isinstance(payload, dict) else None
    claim_ids: list[UUID] = []
    evidence_ids: list[UUID] = []
    for key, target in (("claim_id", claim_ids), ("claim_ids", claim_ids)):
        if isinstance(payload, dict):
            value = payload.get(key)
            values = value if isinstance(value, list) else [value]
            target.extend(item for item in (_uuid(item) for item in values) if item is not None)
    for key in ("evidence_id", "evidence_ids"):
        if isinstance(payload, dict):
            value = payload.get(key)
            values = value if isinstance(value, list) else [value]
            evidence_ids.extend(
                item for item in (_uuid(item) for item in values) if item is not None
            )
    source_id = (
        _uuid(payload.get("previous_source_revision_id")) if isinstance(payload, dict) else None
    )
    count = reconcile_memory_entries(
        session,
        event_type=event_type,
        project_id=project_id,
        claim_ids=claim_ids,
        evidence_ids=evidence_ids,
        source_revision_id=source_id,
        reason=str(payload.get("reason", event_type)) if isinstance(payload, dict) else event_type,
    )
    return str(count)


__all__ = [
    "MEMORY_EVENT_TYPES",
    "enqueue_memory_event",
    "handle_memory_event",
    "reconcile_memory_entries",
]
