"""SQLAlchemy persistence for project-scoped M16 ProtocolIR revisions."""

from typing import Any, cast
from uuid import UUID, uuid4

from eea_core.protocol import ProtocolIR
from sqlalchemy import desc, select, update
from sqlalchemy.orm import Session

from eea_backend.models import ProtocolRecord


def _entity_kwargs(record: ProtocolRecord) -> dict[str, Any]:
    return {
        "id": UUID(record.id),
        "schema_version": record.schema_version,
        "revision": record.revision,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "metadata": record.entity_metadata,
    }


class SqlAlchemyProtocolRepository:
    """Persist immutable ProtocolIR revisions with project isolation."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, protocol: ProtocolIR, *, commit: bool = True) -> ProtocolIR:
        self._mark_current_stale(protocol.project_id)
        record = self._record(protocol)
        self._session.add(record)
        self._session.flush()
        if commit:
            self._session.commit()
            self._session.refresh(record)
        return (
            self.get(protocol.id, project_id=protocol.project_id, revision=protocol.revision)
            or protocol
        )

    def get(
        self,
        protocol_id: UUID,
        *,
        project_id: UUID | None = None,
        revision: int | None = None,
    ) -> ProtocolIR | None:
        statement = select(ProtocolRecord).where(ProtocolRecord.id == str(protocol_id))
        if project_id is not None:
            statement = statement.where(ProtocolRecord.project_id == str(project_id))
        if revision is not None:
            statement = statement.where(ProtocolRecord.revision == revision)
        else:
            statement = statement.order_by(desc(ProtocolRecord.revision)).limit(1)
        record = self._session.scalar(statement)
        return self._to_protocol(record) if record else None

    def latest_for_project(self, project_id: UUID) -> ProtocolIR | None:
        statement = (
            select(ProtocolRecord)
            .where(
                ProtocolRecord.project_id == str(project_id),
                ProtocolRecord.status == "CURRENT",
            )
            .order_by(desc(ProtocolRecord.revision), desc(ProtocolRecord.updated_at))
            .limit(1)
        )
        record = self._session.scalar(statement)
        return self._to_protocol(record) if record else None

    def save(
        self,
        protocol: ProtocolIR,
        *,
        expected_revision: int,
        commit: bool = True,
    ) -> ProtocolIR | None:
        latest = self.get(protocol.id, project_id=protocol.project_id)
        if latest is None or latest.revision != expected_revision:
            return None
        if protocol.revision != expected_revision + 1:
            raise ValueError("ProtocolIR revision must increment by exactly one")
        self._mark_current_stale(protocol.project_id)
        record = self._record(protocol)
        self._session.add(record)
        self._session.flush()
        if commit:
            self._session.commit()
            self._session.refresh(record)
        return self.get(protocol.id, project_id=protocol.project_id, revision=protocol.revision)

    @staticmethod
    def _record(protocol: ProtocolIR) -> ProtocolRecord:
        serialized = protocol.model_dump(mode="json")
        return ProtocolRecord(
            record_id=str(uuid4()),
            id=str(protocol.id),
            schema_version=protocol.schema_version,
            revision=protocol.revision,
            created_at=protocol.created_at,
            updated_at=protocol.updated_at,
            entity_metadata=protocol.metadata,
            project_id=str(protocol.project_id),
            version_label=protocol.version_label,
            transports=cast(list[dict[str, Any]], serialized["transports"]),
            messages=cast(list[dict[str, Any]], serialized["messages"]),
            requirement_ids=[str(value) for value in protocol.requirement_ids],
            evidence_ids=[str(value) for value in protocol.evidence_ids],
            input_hash=protocol.input_hash,
            status="CURRENT",
        )

    @staticmethod
    def _to_protocol(record: ProtocolRecord) -> ProtocolIR:
        return ProtocolIR.model_validate(
            {
                **_entity_kwargs(record),
                "project_id": UUID(record.project_id),
                "version_label": record.version_label,
                "transports": record.transports,
                "messages": record.messages,
                "requirement_ids": record.requirement_ids,
                "evidence_ids": record.evidence_ids,
                "input_hash": record.input_hash,
            }
        )

    def _mark_current_stale(self, project_id: UUID) -> None:
        self._session.execute(
            update(ProtocolRecord)
            .where(
                ProtocolRecord.project_id == str(project_id),
                ProtocolRecord.status == "CURRENT",
            )
            .values(status="STALE")
        )


__all__ = ["SqlAlchemyProtocolRepository"]
