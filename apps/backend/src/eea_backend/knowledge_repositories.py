"""Persistence adapters for M23 structured memory."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID, uuid4

from eea_application.knowledge_memory import build_search_text
from eea_core.entities import KnowledgeEntry
from eea_core.enums import (
    AuthorityLevel,
    KnowledgeLifecycle,
    KnowledgeScope,
    KnowledgeType,
    TrustLevel,
    VerificationLevel,
)
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from eea_backend.models import KnowledgeEntryRecord, KnowledgeRecallAuditRecord


def _to_entry(record: KnowledgeEntryRecord) -> KnowledgeEntry:
    return KnowledgeEntry.model_validate(
        {
            "id": record.id,
            "schema_version": record.schema_version,
            "revision": record.revision,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "metadata": record.entity_metadata,
            "project_id": record.project_id,
            "scope": KnowledgeScope(record.scope),
            "owner_ref": record.owner_ref,
            "organization_ref": record.organization_ref,
            "task_ref": record.task_ref,
            "knowledge_type": KnowledgeType(record.knowledge_type),
            "title": record.title,
            "summary": record.summary,
            "tags": list(record.tags),
            "applicability": dict(record.applicability),
            "claim_ids": [UUID(value) for value in record.claim_ids],
            "evidence_ids": [UUID(value) for value in record.evidence_ids],
            "source_revision_id": (
                UUID(record.source_revision_id) if record.source_revision_id else None
            ),
            "source_ref": record.source_ref,
            "source_version": record.source_version,
            "authority_level": AuthorityLevel(record.authority_level),
            "verification_levels": [
                VerificationLevel(value) for value in record.verification_levels
            ],
            "trust_level": TrustLevel(record.trust_level),
            "lifecycle": KnowledgeLifecycle(record.lifecycle),
            "confidence": record.confidence,
            "freshness_score": record.freshness_score,
            "last_verified_at": record.last_verified_at,
            "license_ref": record.license_ref,
            "usage_policy": record.usage_policy,
            "related_entry_ids": [UUID(value) for value in record.related_entry_ids],
            "created_by": record.created_by,
            "reviewed_by": record.reviewed_by,
            "reviewed_at": record.reviewed_at,
        }
    )


def _record_values(entry: KnowledgeEntry) -> dict[str, Any]:
    return {
        "id": str(entry.id),
        "schema_version": entry.schema_version,
        "revision": entry.revision,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
        "entity_metadata": entry.metadata,
        "project_id": str(entry.project_id) if entry.project_id else None,
        "scope": entry.scope.value,
        "owner_ref": entry.owner_ref,
        "organization_ref": entry.organization_ref,
        "task_ref": entry.task_ref,
        "knowledge_type": entry.knowledge_type.value,
        "title": entry.title,
        "summary": entry.summary,
        "tags": entry.tags,
        "applicability": entry.applicability,
        "claim_ids": [str(value) for value in entry.claim_ids],
        "evidence_ids": [str(value) for value in entry.evidence_ids],
        "source_revision_id": str(entry.source_revision_id) if entry.source_revision_id else None,
        "source_ref": entry.source_ref,
        "source_version": entry.source_version,
        "authority_level": entry.authority_level.value,
        "verification_levels": [value.value for value in entry.verification_levels],
        "trust_level": entry.trust_level.value,
        "lifecycle": entry.lifecycle.value,
        "confidence": entry.confidence,
        "freshness_score": entry.freshness_score,
        "last_verified_at": entry.last_verified_at,
        "license_ref": entry.license_ref,
        "usage_policy": entry.usage_policy,
        "related_entry_ids": [str(value) for value in entry.related_entry_ids],
        "search_text": build_search_text(entry),
        "created_by": entry.created_by,
        "reviewed_by": entry.reviewed_by,
        "reviewed_at": entry.reviewed_at,
    }


class SqlAlchemyKnowledgeEntryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, entry: KnowledgeEntry, *, commit: bool = True) -> KnowledgeEntry:
        record = KnowledgeEntryRecord(**_record_values(entry))
        self._session.add(record)
        if commit:
            self._session.commit()
            self._session.refresh(record)
        else:
            self._session.flush()
        return _to_entry(record)

    def get(self, entry_id: UUID) -> KnowledgeEntry | None:
        record = self._session.get(KnowledgeEntryRecord, str(entry_id))
        return _to_entry(record) if record else None

    def list_for_recall(self) -> list[KnowledgeEntry]:
        records = self._session.scalars(
            select(KnowledgeEntryRecord).order_by(
                KnowledgeEntryRecord.created_at, KnowledgeEntryRecord.id
            )
        )
        return [_to_entry(record) for record in records]

    def save(
        self,
        entry: KnowledgeEntry,
        *,
        expected_revision: int,
        commit: bool = True,
    ) -> KnowledgeEntry | None:
        values = _record_values(entry)
        values.pop("id")
        values.pop("created_at")
        result = cast(
            CursorResult[object],
            self._session.execute(
                update(KnowledgeEntryRecord)
                .where(
                    KnowledgeEntryRecord.id == str(entry.id),
                    KnowledgeEntryRecord.revision == expected_revision,
                )
                .values(**values)
            ),
        )
        if result.rowcount != 1:
            if commit:
                self._session.rollback()
            return None
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        return self.get(entry.id)


class SqlAlchemyKnowledgeRecallAuditRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self,
        *,
        project_id: UUID,
        actor_ref: str,
        query: str,
        scope_context: list[KnowledgeScope],
        result_ids: list[UUID],
        request_id: str,
    ) -> UUID:
        from eea_core.entities import utc_now

        audit_id = uuid4()
        now = utc_now()
        self._session.add(
            KnowledgeRecallAuditRecord(
                id=str(audit_id),
                schema_version="1.0",
                revision=1,
                created_at=now,
                updated_at=now,
                entity_metadata={},
                project_id=str(project_id),
                actor_ref=actor_ref,
                query=query,
                scope_context=[value.value for value in scope_context],
                result_ids=[str(value) for value in result_ids],
                result_count=len(result_ids),
                request_id=request_id,
            )
        )
        self._session.commit()
        return audit_id


__all__ = [
    "SqlAlchemyKnowledgeEntryRepository",
    "SqlAlchemyKnowledgeRecallAuditRepository",
    "_to_entry",
]
