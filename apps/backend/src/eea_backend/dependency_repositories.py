"""SQLAlchemy persistence adapters for the M18 dependency graph."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from eea_core.dependency_graph import (
    DependencyNodeState,
    EngineeringDependencyEdge,
)
from eea_core.entities import utc_now
from eea_core.enums import DependencyKind, DependencyNodeStatus, EngineeringErrorCode
from eea_core.errors import EngineeringError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from eea_backend.models import (
    EngineeringDependencyEdgeRecord,
    EngineeringDependencyNodeStateRecord,
)


def _entity_kwargs(record: object) -> dict[str, Any]:
    value = cast(Any, record)
    return {
        "id": UUID(value.id),
        "schema_version": value.schema_version,
        "revision": value.revision,
        "created_at": value.created_at,
        "updated_at": value.updated_at,
        "metadata": value.entity_metadata,
    }


def _to_edge(record: EngineeringDependencyEdgeRecord) -> EngineeringDependencyEdge:
    return EngineeringDependencyEdge.model_validate(
        {
            **_entity_kwargs(record),
            "project_id": UUID(record.project_id),
            "upstream_type": record.upstream_type,
            "upstream_id": record.upstream_id,
            "downstream_type": record.downstream_type,
            "downstream_id": record.downstream_id,
            "dependency_kind": record.dependency_kind,
            "required": record.required,
            "invalidation_policy": record.invalidation_policy,
            "bound_upstream_revision": record.bound_upstream_revision,
            "bound_upstream_semantic_hash": record.bound_upstream_semantic_hash,
            "reason": record.reason,
            "evidence_ids": record.evidence_ids,
        }
    )


def _to_node_state(record: EngineeringDependencyNodeStateRecord) -> DependencyNodeState:
    return DependencyNodeState.model_validate(
        {
            **_entity_kwargs(record),
            "project_id": UUID(record.project_id),
            "entity_type": record.entity_type,
            "entity_id": record.entity_id,
            "observed_revision": record.observed_revision,
            "observed_semantic_hash": record.observed_semantic_hash,
            "status": record.status,
            "invalidated_by": record.invalidated_by,
            "reason_codes": record.reason_codes,
            "stale_since": record.stale_since,
        }
    )


class SqlAlchemyDependencyGraphRepository:
    """Project-scoped graph store with idempotent edge and CAS state writes."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _edge_identity(edge: EngineeringDependencyEdge) -> tuple[Any, ...]:
        return (
            EngineeringDependencyEdgeRecord.project_id == str(edge.project_id),
            EngineeringDependencyEdgeRecord.upstream_type == edge.upstream_type,
            EngineeringDependencyEdgeRecord.upstream_id == edge.upstream_id,
            EngineeringDependencyEdgeRecord.downstream_type == edge.downstream_type,
            EngineeringDependencyEdgeRecord.downstream_id == edge.downstream_id,
            EngineeringDependencyEdgeRecord.dependency_kind == edge.dependency_kind.value,
        )

    def bind(
        self, edge: EngineeringDependencyEdge, *, commit: bool = True
    ) -> EngineeringDependencyEdge:
        identity = self._edge_identity(edge)
        existing = self.session.scalar(select(EngineeringDependencyEdgeRecord).where(*identity))
        if existing is None:
            record = EngineeringDependencyEdgeRecord(
                id=str(edge.id),
                schema_version=edge.schema_version,
                revision=edge.revision,
                created_at=edge.created_at,
                updated_at=edge.updated_at,
                entity_metadata=edge.metadata,
                project_id=str(edge.project_id),
                upstream_type=edge.upstream_type,
                upstream_id=edge.upstream_id,
                downstream_type=edge.downstream_type,
                downstream_id=edge.downstream_id,
                dependency_kind=edge.dependency_kind.value,
                required=edge.required,
                invalidation_policy=edge.invalidation_policy.value,
                bound_upstream_revision=edge.bound_upstream_revision,
                bound_upstream_semantic_hash=edge.bound_upstream_semantic_hash,
                reason=edge.reason,
                evidence_ids=sorted({str(item) for item in edge.evidence_ids}),
            )
            try:
                with self.session.begin_nested():
                    self.session.add(record)
                    self.session.flush()
            except IntegrityError:
                existing = self.session.scalar(
                    select(EngineeringDependencyEdgeRecord).where(*identity)
                )
                if existing is None:
                    raise
            else:
                if commit:
                    self.session.commit()
                return _to_edge(record)

        assert existing is not None
        # Rebinding is explicit: do not silently change the bound snapshot on a
        # normal idempotent bind.  Evidence and reason metadata can be merged.
        merged_evidence = sorted(
            set(existing.evidence_ids) | {str(item) for item in edge.evidence_ids}
        )
        if merged_evidence != sorted(existing.evidence_ids) or existing.reason != edge.reason:
            existing.evidence_ids = merged_evidence
            existing.reason = edge.reason
            existing.revision += 1
            existing.updated_at = utc_now()
            if commit:
                self.session.commit()
        return _to_edge(existing)

    def rebind(
        self,
        project_id: UUID,
        *,
        upstream_type: str,
        upstream_id: str,
        downstream_type: str,
        downstream_id: str,
        dependency_kind: DependencyKind,
        revision: int,
        semantic_hash: str,
        commit: bool = True,
    ) -> EngineeringDependencyEdge | None:
        identity = (
            EngineeringDependencyEdgeRecord.project_id == str(project_id),
            EngineeringDependencyEdgeRecord.upstream_type == upstream_type,
            EngineeringDependencyEdgeRecord.upstream_id == upstream_id,
            EngineeringDependencyEdgeRecord.downstream_type == downstream_type,
            EngineeringDependencyEdgeRecord.downstream_id == downstream_id,
            EngineeringDependencyEdgeRecord.dependency_kind == dependency_kind.value,
        )
        record = self.session.scalar(select(EngineeringDependencyEdgeRecord).where(*identity))
        if record is None:
            return None
        record.bound_upstream_revision = revision
        record.bound_upstream_semantic_hash = semantic_hash
        record.revision += 1
        record.updated_at = utc_now()
        if commit:
            self.session.commit()
        return _to_edge(record)

    def get_edge(self, edge_id: UUID, *, project_id: UUID) -> EngineeringDependencyEdge | None:
        record = self.session.scalar(
            select(EngineeringDependencyEdgeRecord).where(
                EngineeringDependencyEdgeRecord.id == str(edge_id),
                EngineeringDependencyEdgeRecord.project_id == str(project_id),
            )
        )
        return _to_edge(record) if record else None

    def list_edges(self, project_id: UUID) -> list[EngineeringDependencyEdge]:
        records = self.session.scalars(
            select(EngineeringDependencyEdgeRecord)
            .where(EngineeringDependencyEdgeRecord.project_id == str(project_id))
            .order_by(
                EngineeringDependencyEdgeRecord.upstream_type,
                EngineeringDependencyEdgeRecord.upstream_id,
                EngineeringDependencyEdgeRecord.downstream_type,
                EngineeringDependencyEdgeRecord.downstream_id,
                EngineeringDependencyEdgeRecord.dependency_kind,
            )
        )
        return [_to_edge(record) for record in records]

    def list_dependencies(
        self, project_id: UUID, entity_type: str, entity_id: str
    ) -> list[EngineeringDependencyEdge]:
        return [
            edge
            for edge in self.list_edges(project_id)
            if edge.downstream_type == entity_type and edge.downstream_id == entity_id
        ]

    def list_dependents(
        self, project_id: UUID, entity_type: str, entity_id: str
    ) -> list[EngineeringDependencyEdge]:
        return [
            edge
            for edge in self.list_edges(project_id)
            if edge.upstream_type == entity_type and edge.upstream_id == entity_id
        ]

    def get_node_state(
        self, project_id: UUID, entity_type: str, entity_id: str
    ) -> DependencyNodeState | None:
        record = self.session.scalar(
            select(EngineeringDependencyNodeStateRecord).where(
                EngineeringDependencyNodeStateRecord.project_id == str(project_id),
                EngineeringDependencyNodeStateRecord.entity_type == entity_type,
                EngineeringDependencyNodeStateRecord.entity_id == entity_id,
            )
        )
        return _to_node_state(record) if record else None

    def list_node_states(
        self, project_id: UUID, *, status: DependencyNodeStatus | None = None
    ) -> list[DependencyNodeState]:
        statement = select(EngineeringDependencyNodeStateRecord).where(
            EngineeringDependencyNodeStateRecord.project_id == str(project_id)
        )
        if status is not None:
            statement = statement.where(EngineeringDependencyNodeStateRecord.status == status.value)
        records = self.session.scalars(
            statement.order_by(
                EngineeringDependencyNodeStateRecord.entity_type,
                EngineeringDependencyNodeStateRecord.entity_id,
            )
        )
        return [_to_node_state(record) for record in records]

    def upsert_node_state(
        self,
        state: DependencyNodeState,
        *,
        expected_revision: int | None = None,
        commit: bool = True,
    ) -> DependencyNodeState:
        return self.merge_invalidation_state(
            state, expected_revision=expected_revision, commit=commit
        )

    def _insert_state(self, state: DependencyNodeState) -> DependencyNodeState | None:
        record = EngineeringDependencyNodeStateRecord(
            id=str(state.id),
            schema_version=state.schema_version,
            revision=state.revision,
            created_at=state.created_at,
            updated_at=state.updated_at,
            entity_metadata=state.metadata,
            project_id=str(state.project_id),
            entity_type=state.entity_type,
            entity_id=state.entity_id,
            observed_revision=state.observed_revision,
            observed_semantic_hash=state.observed_semantic_hash,
            status=state.status.value,
            invalidated_by=sorted(set(state.invalidated_by)),
            reason_codes=sorted(set(state.reason_codes)),
            stale_since=state.stale_since,
        )
        try:
            with self.session.begin_nested():
                self.session.add(record)
                self.session.flush()
        except IntegrityError:
            return None
        return _to_node_state(record)

    def _state_identity(self, state: DependencyNodeState) -> tuple[Any, ...]:
        return (
            EngineeringDependencyNodeStateRecord.project_id == str(state.project_id),
            EngineeringDependencyNodeStateRecord.entity_type == state.entity_type,
            EngineeringDependencyNodeStateRecord.entity_id == state.entity_id,
        )

    def merge_invalidation_state(
        self,
        state: DependencyNodeState,
        *,
        expected_revision: int | None = None,
        commit: bool = True,
    ) -> DependencyNodeState:
        """CAS merge for propagation; status and invalidation evidence only grow."""

        identity = (*self._state_identity(state),)
        return self._merge_state_impl(
            state, identity, expected_revision=expected_revision, commit=commit
        )

    def _merge_state_impl(
        self,
        state: DependencyNodeState,
        identity: tuple[Any, ...],
        *,
        expected_revision: int | None,
        commit: bool,
    ) -> DependencyNodeState:
        current = self.session.scalar(select(EngineeringDependencyNodeStateRecord).where(*identity))
        if current is None:
            inserted = self._insert_state(state)
            if inserted is not None:
                if commit:
                    self.session.commit()
                return inserted
            current = self.session.scalar(
                select(EngineeringDependencyNodeStateRecord).where(*identity)
            )
        if current is None:
            raise EngineeringError(
                EngineeringErrorCode.REVISION_CONFLICT,
                "Dependency node state could not be loaded after concurrent insert",
            )
        if expected_revision is not None and current.revision != expected_revision:
            raise EngineeringError(
                EngineeringErrorCode.REVISION_CONFLICT,
                "Dependency node state changed concurrently",
                details={"entity_type": state.entity_type, "entity_id": state.entity_id},
            )
        precedence = {
            DependencyNodeStatus.UNKNOWN: 0,
            DependencyNodeStatus.CURRENT: 1,
            DependencyNodeStatus.STALE: 2,
            DependencyNodeStatus.INVALID: 3,
        }
        merged_status = max(
            DependencyNodeStatus(current.status), state.status, key=precedence.__getitem__
        )
        result = self.session.execute(
            update(EngineeringDependencyNodeStateRecord)
            .where(*identity, EngineeringDependencyNodeStateRecord.revision == current.revision)
            .values(
                schema_version=state.schema_version,
                revision=current.revision + 1,
                updated_at=utc_now(),
                entity_metadata=state.metadata,
                observed_revision=state.observed_revision,
                observed_semantic_hash=state.observed_semantic_hash,
                status=merged_status.value,
                invalidated_by=sorted(set(current.invalidated_by) | set(state.invalidated_by)),
                reason_codes=sorted(set(current.reason_codes) | set(state.reason_codes)),
                stale_since=current.stale_since or state.stale_since,
            )
        )
        if not isinstance(result, CursorResult) or result.rowcount != 1:
            raise EngineeringError(
                EngineeringErrorCode.REVISION_CONFLICT,
                "Dependency node state changed concurrently",
            )
        if commit:
            self.session.commit()
        refreshed = self.session.scalar(
            select(EngineeringDependencyNodeStateRecord).where(*identity)
        )
        if refreshed is None:
            raise EngineeringError(
                EngineeringErrorCode.REVISION_CONFLICT,
                "Dependency node state disappeared after CAS update",
            )
        return _to_node_state(refreshed)

    def replace_revalidated_state(
        self,
        state: DependencyNodeState,
        *,
        expected_revision: int | None = None,
        commit: bool = True,
    ) -> DependencyNodeState:
        """CAS replacement after a complete, successful revalidation."""

        identity = self._state_identity(state)
        current = self.session.scalar(select(EngineeringDependencyNodeStateRecord).where(*identity))
        if current is None:
            inserted = self._insert_state(state)
            if inserted is not None:
                if commit:
                    self.session.commit()
                return inserted
            current = self.session.scalar(
                select(EngineeringDependencyNodeStateRecord).where(*identity)
            )
        if current is None or (
            expected_revision is not None and current.revision != expected_revision
        ):
            raise EngineeringError(
                EngineeringErrorCode.REVISION_CONFLICT,
                "Dependency node state changed during revalidation",
                details={"entity_type": state.entity_type, "entity_id": state.entity_id},
            )
        result = self.session.execute(
            update(EngineeringDependencyNodeStateRecord)
            .where(*identity, EngineeringDependencyNodeStateRecord.revision == current.revision)
            .values(
                schema_version=state.schema_version,
                revision=current.revision + 1,
                updated_at=utc_now(),
                entity_metadata=state.metadata,
                observed_revision=state.observed_revision,
                observed_semantic_hash=state.observed_semantic_hash,
                status=state.status.value,
                invalidated_by=sorted(set(state.invalidated_by)),
                reason_codes=sorted(set(state.reason_codes)),
                stale_since=state.stale_since,
            )
        )
        if not isinstance(result, CursorResult) or result.rowcount != 1:
            raise EngineeringError(
                EngineeringErrorCode.REVISION_CONFLICT,
                "Dependency node state changed during revalidation",
            )
        if commit:
            self.session.commit()
        refreshed = self.session.scalar(
            select(EngineeringDependencyNodeStateRecord).where(*identity)
        )
        if refreshed is None:
            raise EngineeringError(
                EngineeringErrorCode.REVISION_CONFLICT,
                "Dependency node state disappeared after revalidation",
            )
        return _to_node_state(refreshed)


__all__ = ["SqlAlchemyDependencyGraphRepository"]
