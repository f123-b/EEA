"""SQLAlchemy persistence for project-scoped Domain activation state."""

from uuid import UUID

from eea_core.domain_extensions import DomainActivation, DomainCompositionState
from eea_core.enums import DomainActivationStatus
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from eea_backend.models import DomainActivationRecord, DomainCompositionStateRecord


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
        configuration_schema_version=record.configuration_schema_version,
        configuration_schema_hash=record.configuration_schema_hash,
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

    def add(self, activation: DomainActivation, *, commit: bool = True) -> DomainActivation:
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
            configuration_schema_version=activation.configuration_schema_version,
            configuration_schema_hash=activation.configuration_schema_hash,
            status=activation.status.value,
            configuration=activation.configuration,
            activated_at=activation.activated_at,
            activated_by=activation.activated_by,
            capability_snapshot=activation.capability_snapshot,
            dependency_snapshot=activation.dependency_snapshot,
        )
        self._session.add(record)
        self._session.flush()
        if commit:
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

    def save(self, activation: DomainActivation, *, commit: bool = True) -> DomainActivation | None:
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
        record.configuration_schema_version = activation.configuration_schema_version
        record.configuration_schema_hash = activation.configuration_schema_hash
        record.status = activation.status.value
        record.configuration = activation.configuration
        record.activated_at = activation.activated_at
        record.activated_by = activation.activated_by
        record.capability_snapshot = activation.capability_snapshot
        record.dependency_snapshot = activation.dependency_snapshot
        self._session.flush()
        if commit:
            self._session.commit()
        self._session.refresh(record)
        return _to_activation(record)


def _to_composition_state(record: DomainCompositionStateRecord) -> DomainCompositionState:
    return DomainCompositionState(
        id=UUID(record.id),
        schema_version=record.schema_version,
        revision=record.revision,
        created_at=record.created_at,
        updated_at=record.updated_at,
        metadata=record.entity_metadata,
        project_id=UUID(record.project_id),
        active_domain_ids=record.active_domain_ids,
        ordered_domain_ids=record.ordered_domain_ids,
        selected_capabilities=record.selected_capabilities,
        capability_routes=record.capability_routes,
        dependency_edges=record.dependency_edges,
        domain_snapshots=record.domain_snapshots,
        rule_order=record.rule_order,
        generator_order=record.generator_order,
        plan_hash=record.plan_hash,
        updated_by=record.updated_by,
    )


class SqlAlchemyDomainCompositionStateRepository:
    """CAS-aware persistence for the canonical project composition state."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, project_id: UUID) -> DomainCompositionState | None:
        record = self._session.scalar(
            select(DomainCompositionStateRecord).where(
                DomainCompositionStateRecord.project_id == str(project_id)
            )
        )
        return _to_composition_state(record) if record else None

    def add(self, state: DomainCompositionState, *, commit: bool = True) -> DomainCompositionState:
        record = DomainCompositionStateRecord(
            id=str(state.id),
            schema_version=state.schema_version,
            revision=state.revision,
            created_at=state.created_at,
            updated_at=state.updated_at,
            entity_metadata=state.metadata,
            project_id=str(state.project_id),
            active_domain_ids=state.active_domain_ids,
            ordered_domain_ids=state.ordered_domain_ids,
            selected_capabilities=state.selected_capabilities,
            capability_routes=state.capability_routes,
            dependency_edges=state.dependency_edges,
            domain_snapshots=state.domain_snapshots,
            rule_order=state.rule_order,
            generator_order=state.generator_order,
            plan_hash=state.plan_hash,
            updated_by=state.updated_by,
        )
        self._session.add(record)
        self._session.flush()
        if commit:
            self._session.commit()
        self._session.refresh(record)
        return _to_composition_state(record)

    def save(
        self,
        state: DomainCompositionState,
        *,
        expected_revision: int,
        commit: bool = True,
    ) -> DomainCompositionState | None:
        result = self._session.execute(
            update(DomainCompositionStateRecord)
            .where(
                DomainCompositionStateRecord.project_id == str(state.project_id),
                DomainCompositionStateRecord.revision == expected_revision,
            )
            .values(
                schema_version=state.schema_version,
                revision=state.revision,
                updated_at=state.updated_at,
                entity_metadata=state.metadata,
                active_domain_ids=state.active_domain_ids,
                ordered_domain_ids=state.ordered_domain_ids,
                selected_capabilities=state.selected_capabilities,
                capability_routes=state.capability_routes,
                dependency_edges=state.dependency_edges,
                domain_snapshots=state.domain_snapshots,
                rule_order=state.rule_order,
                generator_order=state.generator_order,
                plan_hash=state.plan_hash,
                updated_by=state.updated_by,
            )
        )
        if not isinstance(result, CursorResult) or result.rowcount != 1:
            return None
        self._session.flush()
        if commit:
            self._session.commit()
        return self.get(state.project_id)
