"""SQLAlchemy persistence for project-scoped Domain activation state."""

from uuid import UUID

from eea_core.domain_extensions import DomainActivation
from eea_core.enums import DomainActivationStatus
from sqlalchemy import select
from sqlalchemy.orm import Session

from eea_backend.models import DomainActivationRecord


def _to_activation(record: DomainActivationRecord) -> DomainActivation:
    return DomainActivation(
        id=UUID(record.id),
        schema_version=record.schema_version,
        revision=record.revision,
        created_at=record.created_at,
        updated_at=record.updated_at,
        metadata=record.entity_metadata,
        project_id=UUID(record.project_id),
        domain_id=record.domain_id,
        plugin_id=record.plugin_id,
        plugin_version=record.plugin_version,
        domain_schema_version=record.domain_schema_version,
        status=DomainActivationStatus(record.status),
        configuration=record.configuration,
        activated_at=record.activated_at,
        activated_by=record.activated_by,
        capability_snapshot=record.capability_snapshot,
        dependency_snapshot=record.dependency_snapshot,
    )


class SqlAlchemyDomainActivationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, activation: DomainActivation) -> DomainActivation:
        record = DomainActivationRecord(
            id=str(activation.id),
            schema_version=activation.schema_version,
            revision=activation.revision,
            created_at=activation.created_at,
            updated_at=activation.updated_at,
            entity_metadata=activation.metadata,
            project_id=str(activation.project_id),
            domain_id=activation.domain_id,
            plugin_id=activation.plugin_id,
            plugin_version=activation.plugin_version,
            domain_schema_version=activation.domain_schema_version,
            status=activation.status.value,
            configuration=activation.configuration,
            activated_at=activation.activated_at,
            activated_by=activation.activated_by,
            capability_snapshot=activation.capability_snapshot,
            dependency_snapshot=activation.dependency_snapshot,
        )
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return _to_activation(record)

    def get(self, project_id: UUID, domain_id: str) -> DomainActivation | None:
        record = self._session.scalar(
            select(DomainActivationRecord).where(
                DomainActivationRecord.project_id == str(project_id),
                DomainActivationRecord.domain_id == domain_id,
            )
        )
        return _to_activation(record) if record else None

    def list_for_project(self, project_id: UUID) -> list[DomainActivation]:
        records = self._session.scalars(
            select(DomainActivationRecord)
            .where(DomainActivationRecord.project_id == str(project_id))
            .order_by(DomainActivationRecord.domain_id)
        )
        return [_to_activation(record) for record in records]

    def save(self, activation: DomainActivation) -> DomainActivation | None:
        record = self._session.scalar(
            select(DomainActivationRecord).where(
                DomainActivationRecord.project_id == str(activation.project_id),
                DomainActivationRecord.domain_id == activation.domain_id,
            )
        )
        if record is None:
            return None
        record.schema_version = activation.schema_version
        record.revision = activation.revision
        record.updated_at = activation.updated_at
        record.entity_metadata = activation.metadata
        record.plugin_id = activation.plugin_id
        record.plugin_version = activation.plugin_version
        record.domain_schema_version = activation.domain_schema_version
        record.status = activation.status.value
        record.configuration = activation.configuration
        record.activated_at = activation.activated_at
        record.activated_by = activation.activated_by
        record.capability_snapshot = activation.capability_snapshot
        record.dependency_snapshot = activation.dependency_snapshot
        self._session.commit()
        self._session.refresh(record)
        return _to_activation(record)
