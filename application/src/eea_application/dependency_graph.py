"""M18 dependency providers and deterministic impact propagation service."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol, cast
from uuid import UUID

from eea_core.dependency_graph import (
    ChangeObservation,
    DependencyImpact,
    DependencyNodeRef,
    DependencyNodeState,
    EngineeringDependencyEdge,
    ImpactPlan,
    ImpactPlanStep,
)
from eea_core.entities import utc_now
from eea_core.enums import (
    DependencyKind,
    DependencyNodeStatus,
    EngineeringErrorCode,
    ImpactAction,
    InvalidationPolicy,
)
from eea_core.errors import EngineeringError


@dataclass(frozen=True)
class DependencyNodeSnapshot:
    """Provider output used for binding and change observation."""

    ref: DependencyNodeRef
    valid: bool = True
    reason: str = ""
    recovery_action: ImpactAction = ImpactAction.MANUAL_REVIEW
    fingerprint_aliases: tuple[str, ...] = ()

    @property
    def status(self) -> DependencyNodeStatus:
        return DependencyNodeStatus.CURRENT if self.valid else DependencyNodeStatus.INVALID


class DependencyNodeProvider(Protocol):
    entity_type: str

    def resolve(self, project_id: UUID, entity_id: str) -> DependencyNodeSnapshot | None: ...


class CallbackDependencyNodeProvider:
    """Explicit provider adapter; it never constructs SQL or imports by name."""

    def __init__(
        self,
        entity_type: str,
        resolver: Callable[[UUID, str], DependencyNodeSnapshot | None],
    ) -> None:
        self.entity_type = entity_type
        self._resolver = resolver

    def resolve(self, project_id: UUID, entity_id: str) -> DependencyNodeSnapshot | None:
        return self._resolver(project_id, entity_id)


class DependencyNodeProviderRegistry:
    """Application-owned allow-list for graph node types.

    Unknown node types are rejected.  Providers are registered explicitly by
    the backend composition root, so a graph payload cannot select a table,
    import path, or executable callback dynamically.
    """

    def __init__(self, providers: Iterable[DependencyNodeProvider] = ()) -> None:
        self._providers: dict[str, DependencyNodeProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: DependencyNodeProvider) -> None:
        if provider.entity_type in self._providers:
            raise ValueError(f"dependency provider already registered: {provider.entity_type}")
        self._providers[provider.entity_type] = provider

    def resolve(self, project_id: UUID, entity_type: str, entity_id: str) -> DependencyNodeSnapshot:
        provider = self._providers.get(entity_type)
        if provider is None:
            raise EngineeringError(
                EngineeringErrorCode.CAPABILITY_UNAVAILABLE,
                "Dependency node type is not registered",
                details={"entity_type": entity_type},
            )
        snapshot = provider.resolve(project_id, entity_id)
        if snapshot is None:
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR,
                "Dependency node was not found in the requested project",
                details={"entity_type": entity_type, "entity_id": entity_id},
            )
        return snapshot

    def supports(self, entity_type: str) -> bool:
        return entity_type in self._providers

    @property
    def entity_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))


def observe_entity_change(
    before: DependencyNodeSnapshot, after: DependencyNodeSnapshot
) -> ChangeObservation:
    """Classify a mutation from semantic content and validity only."""

    if not after.valid:
        return ChangeObservation.SOURCE_INVALID
    if before.ref.semantic_hash != after.ref.semantic_hash:
        return ChangeObservation.SEMANTIC_CHANGED
    return ChangeObservation.NON_SEMANTIC


class DependencyGraphRepository(Protocol):
    def bind(
        self, edge: EngineeringDependencyEdge, *, commit: bool = True
    ) -> EngineeringDependencyEdge: ...

    def list_edges(self, project_id: UUID) -> list[EngineeringDependencyEdge]: ...

    def list_dependencies(
        self, project_id: UUID, entity_type: str, entity_id: str
    ) -> list[EngineeringDependencyEdge]: ...

    def list_dependents(
        self, project_id: UUID, entity_type: str, entity_id: str
    ) -> list[EngineeringDependencyEdge]: ...

    def get_node_state(
        self, project_id: UUID, entity_type: str, entity_id: str
    ) -> DependencyNodeState | None: ...

    def list_node_states(
        self, project_id: UUID, *, status: DependencyNodeStatus | None = None
    ) -> list[DependencyNodeState]: ...

    def upsert_node_state(
        self,
        state: DependencyNodeState,
        *,
        expected_revision: int | None = None,
        commit: bool = True,
    ) -> DependencyNodeState: ...

    def merge_invalidation_state(
        self,
        state: DependencyNodeState,
        *,
        expected_revision: int | None = None,
        commit: bool = True,
    ) -> DependencyNodeState: ...

    def replace_revalidated_state(
        self,
        state: DependencyNodeState,
        *,
        expected_revision: int | None = None,
        commit: bool = True,
    ) -> DependencyNodeState: ...

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
    ) -> EngineeringDependencyEdge | None: ...


_STATUS_PRECEDENCE = {
    DependencyNodeStatus.UNKNOWN: 0,
    DependencyNodeStatus.CURRENT: 1,
    DependencyNodeStatus.STALE: 2,
    DependencyNodeStatus.INVALID: 3,
}


def _effective_policy(edge: EngineeringDependencyEdge) -> InvalidationPolicy:
    return edge.invalidation_policy


def _merge_state(
    repository: DependencyGraphRepository,
    state: DependencyNodeState,
    *,
    expected_revision: int | None = None,
    commit: bool = True,
) -> DependencyNodeState:
    method = getattr(repository, "merge_invalidation_state", None)
    if method is not None:
        return cast(
            DependencyNodeState,
            method(state, expected_revision=expected_revision, commit=commit),
        )
    return repository.upsert_node_state(state, expected_revision=expected_revision, commit=commit)


def _replace_state(
    repository: DependencyGraphRepository,
    state: DependencyNodeState,
    *,
    expected_revision: int | None = None,
    commit: bool = True,
) -> DependencyNodeState:
    method = getattr(repository, "replace_revalidated_state", None)
    if method is not None:
        return cast(
            DependencyNodeState,
            method(state, expected_revision=expected_revision, commit=commit),
        )
    return repository.upsert_node_state(state, expected_revision=expected_revision, commit=commit)


def _snapshot_matches_edge(
    snapshot: DependencyNodeSnapshot, edge: EngineeringDependencyEdge
) -> bool:
    return (
        snapshot.ref.semantic_hash == edge.bound_upstream_semantic_hash
        or edge.bound_upstream_semantic_hash in snapshot.fingerprint_aliases
    )


def _merge_with_retry(
    repository: DependencyGraphRepository,
    state: DependencyNodeState,
    *,
    expected_revision: int | None = None,
    commit: bool = False,
) -> DependencyNodeState:
    current_expected = expected_revision
    for _ in range(3):
        try:
            return _merge_state(
                repository,
                state,
                expected_revision=current_expected,
                commit=commit,
            )
        except (EngineeringError, ValueError) as error:
            if (
                isinstance(error, EngineeringError)
                and error.code is not EngineeringErrorCode.REVISION_CONFLICT
            ):
                raise
            current = repository.get_node_state(
                state.project_id, state.entity_type, state.entity_id
            )
            current_expected = current.revision if current is not None else None
    raise EngineeringError(
        EngineeringErrorCode.REVISION_CONFLICT,
        "Dependency node state could not be merged after bounded retries",
        details={"entity_type": state.entity_type, "entity_id": state.entity_id},
    )


def _projected_status(
    edge: EngineeringDependencyEdge,
    observation: ChangeObservation,
    upstream_status: DependencyNodeStatus,
) -> DependencyNodeStatus | None:
    policy = _effective_policy(edge)
    if observation is ChangeObservation.NON_SEMANTIC:
        return None
    if observation is ChangeObservation.SEMANTIC_CHANGED:
        if policy in {
            InvalidationPolicy.SEMANTIC_CHANGE_STALE,
            InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
        }:
            return DependencyNodeStatus.STALE
        return None
    if policy in {
        InvalidationPolicy.SOURCE_INVALID_INVALID,
        InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
    }:
        return DependencyNodeStatus.INVALID
    if policy is InvalidationPolicy.SOURCE_INVALID_STALE:
        return DependencyNodeStatus.STALE
    return None


def _action_for(entity_type: str, recovery_action: ImpactAction | None = None) -> ImpactAction:
    if recovery_action is not None and recovery_action is not ImpactAction.MANUAL_REVIEW:
        return recovery_action
    if entity_type in {"Artifact", "ProtocolArtifact", "GeneratedProtocolOutput"}:
        return ImpactAction.REVALIDATE
    if entity_type in {"TestRun"}:
        return ImpactAction.RERUN_TEST
    if entity_type in {"ReviewRun"}:
        return ImpactAction.RERUN_REVIEW
    if entity_type in {"BuildRun"}:
        return ImpactAction.REBUILD
    if entity_type in {
        "TestIR",
        "PinAssignment",
        "MCUConfigIR",
        "FirmwareIR",
        "ProtocolIR",
        "SystemArchitectureIR",
        "HardwareIR",
        "CircuitIR",
        "SchematicIR",
    }:
        return ImpactAction.REGENERATE
    return ImpactAction.MANUAL_REVIEW


class DependencyGraphService:
    """Synchronous graph mutation, traversal, and read-only planning."""

    def __init__(
        self,
        repository: DependencyGraphRepository,
        providers: DependencyNodeProviderRegistry,
    ) -> None:
        self.repository = repository
        self.providers = providers

    def _assert_no_cycle(self, edge: EngineeringDependencyEdge) -> None:
        adjacency: dict[tuple[str, str], list[tuple[str, str]]] = {}
        for existing in self.repository.list_edges(edge.project_id):
            adjacency.setdefault((existing.upstream_type, existing.upstream_id), []).append(
                (existing.downstream_type, existing.downstream_id)
            )
        start = (edge.downstream_type, edge.downstream_id)
        target = (edge.upstream_type, edge.upstream_id)
        queue = deque([start])
        visited = {start}
        while queue:
            current = queue.popleft()
            if current == target:
                raise EngineeringError(
                    EngineeringErrorCode.DEPENDENCY_CYCLE,
                    "Dependency graph propagation cycle detected",
                    details={
                        "project_id": str(edge.project_id),
                        "upstream": f"{edge.upstream_type}:{edge.upstream_id}",
                        "downstream": f"{edge.downstream_type}:{edge.downstream_id}",
                    },
                )
            for child in sorted(adjacency.get(current, [])):
                if child not in visited:
                    visited.add(child)
                    queue.append(child)

    def bind(
        self,
        project_id: UUID,
        *,
        upstream_type: str,
        upstream_id: str,
        downstream_type: str,
        downstream_id: str,
        dependency_kind: DependencyKind,
        required: bool,
        invalidation_policy: InvalidationPolicy,
        reason: str,
        evidence_ids: list[UUID] | None = None,
        bound_upstream_revision: int | None = None,
        bound_upstream_semantic_hash: str | None = None,
        commit: bool = True,
    ) -> EngineeringDependencyEdge:
        upstream = self.providers.resolve(project_id, upstream_type, upstream_id)
        self.providers.resolve(project_id, downstream_type, downstream_id)
        edge = EngineeringDependencyEdge(
            project_id=project_id,
            upstream_type=upstream_type,
            upstream_id=upstream_id,
            downstream_type=downstream_type,
            downstream_id=downstream_id,
            dependency_kind=dependency_kind,
            required=required,
            invalidation_policy=invalidation_policy,
            bound_upstream_revision=bound_upstream_revision or upstream.ref.revision,
            bound_upstream_semantic_hash=bound_upstream_semantic_hash or upstream.ref.semantic_hash,
            reason=reason,
            evidence_ids=evidence_ids or [],
        )
        self._assert_no_cycle(edge)
        saved = self.repository.bind(edge, commit=commit)
        downstream = self.providers.resolve(project_id, downstream_type, downstream_id)
        if self.repository.get_node_state(project_id, downstream_type, downstream_id) is None:
            _replace_state(
                self.repository,
                DependencyNodeState(
                    project_id=project_id,
                    entity_type=downstream_type,
                    entity_id=downstream_id,
                    observed_revision=downstream.ref.revision,
                    observed_semantic_hash=downstream.ref.semantic_hash,
                    status=downstream.status,
                ),
                commit=commit,
            )
        return saved

    def bind_explicit_artifact_dependencies(
        self,
        project_id: UUID,
        *,
        artifact_id: str,
        dependency_ids: list[str],
        dependency_hashes: dict[str, str],
        commit: bool = True,
    ) -> list[EngineeringDependencyEdge]:
        """Bind only dependency IDs/hashes declared by an artifact record."""

        edges: list[EngineeringDependencyEdge] = []
        for dependency_id in sorted(set(dependency_ids)):
            if dependency_id not in dependency_hashes:
                continue
            edges.append(
                self.bind_artifact_input(
                    project_id,
                    upstream_id=dependency_id,
                    downstream_id=artifact_id,
                    bound_upstream_semantic_hash=dependency_hashes[dependency_id],
                    reason="Artifact declared dependency_ids/dependency_hashes",
                    commit=False,
                )
            )
        if commit:
            session = getattr(self.repository, "session", None)
            if session is not None:
                session.commit()
        return edges

    def bind_artifact_input(
        self,
        project_id: UUID,
        *,
        upstream_type: str = "Artifact",
        upstream_id: str,
        downstream_id: str,
        bound_upstream_semantic_hash: str | None = None,
        dependency_kind: DependencyKind = DependencyKind.INPUT,
        reason: str,
        commit: bool = True,
    ) -> EngineeringDependencyEdge:
        return self.bind(
            project_id,
            upstream_type=upstream_type,
            upstream_id=upstream_id,
            downstream_type="Artifact",
            downstream_id=downstream_id,
            dependency_kind=dependency_kind,
            required=True,
            invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
            reason=reason,
            bound_upstream_semantic_hash=bound_upstream_semantic_hash,
            commit=commit,
        )

    def bootstrap_explicit_edges(self, project_id: UUID, *, commit: bool = True) -> int:
        """Reconcile graph edges from explicit durable references only.

        Missing declarations are intentionally not inferred.  Callers can run
        this repeatedly; edge identity makes the operation idempotent.
        """

        count = 0
        for edge in self.repository.list_edges(project_id):
            if self.providers.supports(edge.upstream_type) and self.providers.supports(
                edge.downstream_type
            ):
                count += 1
        if commit:
            session = getattr(self.repository, "session", None)
            if session is not None:
                session.commit()
        return count

    def _state_for(
        self, project_id: UUID, entity_type: str, entity_id: str
    ) -> tuple[DependencyNodeState | None, DependencyNodeSnapshot | None]:
        state = self.repository.get_node_state(project_id, entity_type, entity_id)
        try:
            snapshot = self.providers.resolve(project_id, entity_type, entity_id)
        except EngineeringError:
            snapshot = None
        return state, snapshot

    def _node_ref(
        self,
        project_id: UUID,
        entity_type: str,
        entity_id: str,
        *,
        fallback: DependencyNodeRef | None = None,
    ) -> DependencyNodeRef:
        try:
            return self.providers.resolve(project_id, entity_type, entity_id).ref
        except EngineeringError:
            if fallback is not None:
                return fallback
            state = self.repository.get_node_state(project_id, entity_type, entity_id)
            if state is not None:
                return state.ref()
            return DependencyNodeRef(
                entity_type=entity_type,
                entity_id=entity_id,
                revision=1,
                semantic_hash="0" * 64,
            )

    def impact_analysis(
        self,
        project_id: UUID,
        entity_type: str,
        entity_id: str,
        *,
        observation: ChangeObservation = ChangeObservation.SEMANTIC_CHANGED,
    ) -> ImpactPlan:
        source_snapshot = self.providers.resolve(project_id, entity_type, entity_id)
        source_state = self.repository.get_node_state(project_id, entity_type, entity_id)
        source_status = source_snapshot.status
        if source_state is not None and source_state.status is DependencyNodeStatus.INVALID:
            source_status = DependencyNodeStatus.INVALID
        source_ref = source_snapshot.ref
        impacts: list[DependencyImpact] = []
        impact_indexes: dict[tuple[str, str], int] = {}
        queue: deque[
            tuple[str, str, int, list[DependencyNodeRef], ChangeObservation, DependencyNodeStatus]
        ] = deque([(entity_type, entity_id, 0, [source_ref], observation, source_status)])
        visited: dict[tuple[str, str], DependencyNodeStatus] = {}
        edges = self.repository.list_edges(project_id)
        by_upstream: dict[tuple[str, str], list[EngineeringDependencyEdge]] = {}
        for edge in edges:
            by_upstream.setdefault((edge.upstream_type, edge.upstream_id), []).append(edge)
        while queue:
            current_type, current_id, depth, path, change, current_status = queue.popleft()
            for edge in sorted(
                by_upstream.get((current_type, current_id), []),
                key=lambda item: (
                    item.downstream_type,
                    item.downstream_id,
                    item.dependency_kind.value,
                ),
            ):
                child_key = (edge.downstream_type, edge.downstream_id)
                projected = _projected_status(edge, change, current_status)
                if projected is None:
                    continue
                state, snapshot = self._state_for(project_id, *child_key)
                before = (
                    state.status
                    if state is not None
                    else (snapshot.status if snapshot is not None else DependencyNodeStatus.UNKNOWN)
                )
                previous = visited.get(child_key)
                if (
                    previous is not None
                    and _STATUS_PRECEDENCE[previous] >= _STATUS_PRECEDENCE[projected]
                ):
                    continue
                visited[child_key] = projected
                fallback = DependencyNodeRef(
                    entity_type=edge.downstream_type,
                    entity_id=edge.downstream_id,
                    revision=state.observed_revision if state else 1,
                    semantic_hash=state.observed_semantic_hash if state else "0" * 64,
                )
                child_ref = snapshot.ref if snapshot is not None else fallback
                child_path = [*path, child_ref]
                impact = DependencyImpact(
                    node=child_ref,
                    depth=depth + 1,
                    status_before=before,
                    projected_status=projected,
                    reason=edge.reason,
                    dependency_path=child_path,
                    via_edge_id=edge.id,
                    recommended_action=_action_for(
                        edge.downstream_type,
                        snapshot.recovery_action if snapshot else None,
                    ),
                )
                existing_index = impact_indexes.get(child_key)
                if existing_index is None:
                    impact_indexes[child_key] = len(impacts)
                    impacts.append(impact)
                else:
                    impacts[existing_index] = impact
                queue.append(
                    (
                        edge.downstream_type,
                        edge.downstream_id,
                        depth + 1,
                        child_path,
                        ChangeObservation.SOURCE_INVALID
                        if projected is DependencyNodeStatus.INVALID
                        else ChangeObservation.SEMANTIC_CHANGED,
                        projected,
                    )
                )
        impacts.sort(key=lambda item: (item.depth, item.node.entity_type, item.node.entity_id))
        steps = [
            ImpactPlanStep(
                action=item.recommended_action,
                node=item.node,
                depth=item.depth,
                reason=item.reason,
                dependency_path=item.dependency_path,
            )
            for item in impacts
        ]
        steps.sort(key=lambda item: (item.depth, item.node.entity_type, item.node.entity_id))
        return ImpactPlan(
            source=source_ref,
            source_status=source_status,
            impacts=impacts,
            steps=steps,
        )

    def propagate(
        self,
        project_id: UUID,
        before: DependencyNodeSnapshot,
        after: DependencyNodeSnapshot,
        *,
        commit: bool = True,
    ) -> ImpactPlan:
        if (
            before.ref.entity_type != after.ref.entity_type
            or before.ref.entity_id != after.ref.entity_id
        ):
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR,
                "Change observation references different nodes",
            )
        observation = observe_entity_change(before, after)
        source_state = DependencyNodeState(
            project_id=project_id,
            entity_type=after.ref.entity_type,
            entity_id=after.ref.entity_id,
            observed_revision=after.ref.revision,
            observed_semantic_hash=after.ref.semantic_hash,
            status=after.status,
            invalidated_by=[]
            if after.valid
            else [f"{after.ref.entity_type}:{after.ref.entity_id}"],
            reason_codes=[]
            if observation is ChangeObservation.NON_SEMANTIC
            else [observation.value],
            stale_since=None if observation is ChangeObservation.NON_SEMANTIC else utc_now(),
        )
        if after.valid:
            _replace_state(self.repository, source_state, commit=False)
        else:
            _merge_with_retry(self.repository, source_state, commit=False)
        plan = self.impact_analysis(
            project_id,
            after.ref.entity_type,
            after.ref.entity_id,
            observation=observation,
        )
        if observation is not ChangeObservation.NON_SEMANTIC:
            for impact in plan.impacts:
                state, snapshot = self._state_for(
                    project_id, impact.node.entity_type, impact.node.entity_id
                )
                next_state = DependencyNodeState(
                    project_id=project_id,
                    entity_type=impact.node.entity_type,
                    entity_id=impact.node.entity_id,
                    observed_revision=snapshot.ref.revision if snapshot else impact.node.revision,
                    observed_semantic_hash=(
                        snapshot.ref.semantic_hash if snapshot else impact.node.semantic_hash
                    ),
                    status=impact.projected_status,
                    invalidated_by=[f"{after.ref.entity_type}:{after.ref.entity_id}"],
                    reason_codes=[impact.projected_status.value, observation.value],
                    stale_since=utc_now(),
                )
                _merge_with_retry(
                    self.repository,
                    next_state,
                    expected_revision=state.revision if state else None,
                    commit=False,
                )
        if commit:
            # The repository owns the ambient SQL transaction.  All graph
            # writes above are flushed before this single commit.
            session = getattr(self.repository, "session", None)
            if session is not None:
                session.commit()
        return plan

    def rebind(
        self,
        project_id: UUID,
        *,
        upstream_type: str,
        upstream_id: str,
        downstream_type: str,
        downstream_id: str,
        dependency_kind: DependencyKind,
        commit: bool = True,
    ) -> EngineeringDependencyEdge | None:
        snapshot = self.providers.resolve(project_id, upstream_type, upstream_id)
        edge = self.repository.rebind(
            project_id,
            upstream_type=upstream_type,
            upstream_id=upstream_id,
            downstream_type=downstream_type,
            downstream_id=downstream_id,
            dependency_kind=dependency_kind,
            revision=snapshot.ref.revision,
            semantic_hash=snapshot.ref.semantic_hash,
            commit=False,
        )
        if edge is not None:
            self.revalidate(project_id, downstream_type, downstream_id, commit=False)
            if commit:
                session = getattr(self.repository, "session", None)
                if session is not None:
                    session.commit()
        return edge

    def revalidate(
        self,
        project_id: UUID,
        entity_type: str,
        entity_id: str,
        *,
        commit: bool = True,
    ) -> DependencyNodeState:
        """Reconcile one node against every currently resolved input binding."""

        snapshot = self.providers.resolve(project_id, entity_type, entity_id)
        incoming = self.repository.list_dependencies(project_id, entity_type, entity_id)
        projected = snapshot.status
        reasons: list[str] = []
        invalidated_by: list[str] = []
        all_required_current = True
        all_incoming_current = True
        for edge in incoming:
            upstream = self.providers.resolve(project_id, edge.upstream_type, edge.upstream_id)
            upstream_state = self.repository.get_node_state(
                project_id, edge.upstream_type, edge.upstream_id
            )
            if not upstream.valid or (
                upstream_state is not None and upstream_state.status is DependencyNodeStatus.INVALID
            ):
                observation = ChangeObservation.SOURCE_INVALID
            elif not _snapshot_matches_edge(upstream, edge):
                observation = (
                    ChangeObservation.SEMANTIC_CHANGED
                    if upstream.ref.semantic_hash != edge.bound_upstream_semantic_hash
                    else ChangeObservation.NON_SEMANTIC
                )
            elif (
                upstream_state is not None
                and upstream_state.status is not DependencyNodeStatus.CURRENT
            ):
                observation = ChangeObservation.SEMANTIC_CHANGED
            else:
                observation = ChangeObservation.NON_SEMANTIC
            candidate = _projected_status(edge, observation, upstream.status)
            if candidate is not None:
                all_incoming_current = False
            if (
                edge.required
                and edge.invalidation_policy is not InvalidationPolicy.NONE
                and (not upstream.valid or observation is not ChangeObservation.NON_SEMANTIC)
            ):
                all_required_current = False
            if (
                candidate is not None
                and _STATUS_PRECEDENCE[candidate] > _STATUS_PRECEDENCE[projected]
            ):
                projected = candidate
            if observation is not ChangeObservation.NON_SEMANTIC:
                reasons.append(f"{edge.upstream_type}:{edge.upstream_id}:{observation.value}")
                invalidated_by.append(f"{edge.upstream_type}:{edge.upstream_id}")
            elif upstream.ref.revision != edge.bound_upstream_revision:
                reasons.append(
                    f"{edge.upstream_type}:{edge.upstream_id}:{ChangeObservation.NON_SEMANTIC.value}"
                )
        if all_required_current and all_incoming_current and snapshot.valid:
            projected = DependencyNodeStatus.CURRENT
            reasons = []
            invalidated_by = []
        state = DependencyNodeState(
            project_id=project_id,
            entity_type=entity_type,
            entity_id=entity_id,
            observed_revision=snapshot.ref.revision,
            observed_semantic_hash=snapshot.ref.semantic_hash,
            status=projected,
            invalidated_by=invalidated_by,
            reason_codes=reasons,
            stale_since=utc_now() if projected is not DependencyNodeStatus.CURRENT else None,
        )
        existing = self.repository.get_node_state(project_id, entity_type, entity_id)
        saved = _replace_state(
            self.repository,
            state,
            expected_revision=existing.revision if existing else None,
            commit=commit,
        )
        return saved


__all__ = [
    "CallbackDependencyNodeProvider",
    "DependencyGraphService",
    "DependencyNodeProvider",
    "DependencyNodeProviderRegistry",
    "DependencyNodeSnapshot",
    "observe_entity_change",
]
