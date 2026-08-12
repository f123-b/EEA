"""Focused M18 graph contract and traversal tests."""

from __future__ import annotations

from collections import defaultdict
from uuid import UUID

import pytest
from eea_application.dependency_graph import (
    CallbackDependencyNodeProvider,
    DependencyGraphService,
    DependencyNodeProviderRegistry,
    DependencyNodeSnapshot,
    observe_entity_change,
)
from eea_core.dependency_graph import (
    ChangeObservation,
    DependencyNodeRef,
    DependencyNodeState,
    EngineeringDependencyEdge,
    canonical_semantic_hash,
)
from eea_core.enums import (
    DependencyKind,
    DependencyNodeStatus,
    EngineeringErrorCode,
    ImpactAction,
    InvalidationPolicy,
)
from eea_core.errors import EngineeringError

PROJECT = UUID("00000000-0000-0000-0000-000000000001")


class MemoryGraphRepository:
    def __init__(self) -> None:
        self.edges: dict[tuple[object, ...], EngineeringDependencyEdge] = {}
        self.states: dict[tuple[UUID, str, str], DependencyNodeState] = {}

    def bind(
        self, edge: EngineeringDependencyEdge, *, commit: bool = True
    ) -> EngineeringDependencyEdge:
        key = edge.identity
        if key in self.edges:
            current = self.edges[key]
            self.edges[key] = current.model_copy(
                update={"evidence_ids": sorted(set(current.evidence_ids) | set(edge.evidence_ids))}
            )
        else:
            self.edges[key] = edge
        return self.edges[key]

    def list_edges(self, project_id: UUID) -> list[EngineeringDependencyEdge]:
        return sorted(
            [edge for edge in self.edges.values() if edge.project_id == project_id],
            key=lambda edge: (
                edge.upstream_type,
                edge.upstream_id,
                edge.downstream_type,
                edge.downstream_id,
            ),
        )

    def list_dependencies(
        self, project_id: UUID, entity_type: str, entity_id: str
    ) -> list[EngineeringDependencyEdge]:
        return [
            edge
            for edge in self.list_edges(project_id)
            if (edge.downstream_type, edge.downstream_id) == (entity_type, entity_id)
        ]

    def list_dependents(
        self, project_id: UUID, entity_type: str, entity_id: str
    ) -> list[EngineeringDependencyEdge]:
        return [
            edge
            for edge in self.list_edges(project_id)
            if (edge.upstream_type, edge.upstream_id) == (entity_type, entity_id)
        ]

    def get_node_state(
        self, project_id: UUID, entity_type: str, entity_id: str
    ) -> DependencyNodeState | None:
        return self.states.get((project_id, entity_type, entity_id))

    def list_node_states(
        self, project_id: UUID, *, status: DependencyNodeStatus | None = None
    ) -> list[DependencyNodeState]:
        values = [state for key, state in self.states.items() if key[0] == project_id]
        return [state for state in values if status is None or state.status is status]

    def upsert_node_state(
        self,
        state: DependencyNodeState,
        *,
        expected_revision: int | None = None,
        commit: bool = True,
    ) -> DependencyNodeState:
        key = (state.project_id, state.entity_type, state.entity_id)
        current = self.states.get(key)
        if (
            current is not None
            and expected_revision is not None
            and current.revision != expected_revision
        ):
            raise ValueError("CAS conflict")
        if current is not None:
            rank = {
                DependencyNodeStatus.UNKNOWN: 0,
                DependencyNodeStatus.CURRENT: 1,
                DependencyNodeStatus.STALE: 2,
                DependencyNodeStatus.INVALID: 3,
            }
            state = state.model_copy(
                update={
                    "id": current.id,
                    "revision": current.revision + 1,
                    "created_at": current.created_at,
                    "invalidated_by": sorted(
                        set(current.invalidated_by) | set(state.invalidated_by)
                    ),
                    "reason_codes": sorted(set(current.reason_codes) | set(state.reason_codes)),
                    "status": state.status
                    if rank[state.status] >= rank[current.status]
                    else current.status,
                }
            )
        self.states[key] = state
        return state

    def rebind(self, project_id: UUID, **kwargs: object) -> EngineeringDependencyEdge | None:
        key = (
            project_id,
            str(kwargs["upstream_type"]),
            str(kwargs["upstream_id"]),
            str(kwargs["downstream_type"]),
            str(kwargs["downstream_id"]),
            kwargs["dependency_kind"],
        )
        edge = self.edges.get(key)
        if edge is None:
            return None
        edge = edge.model_copy(
            update={
                "bound_upstream_revision": kwargs["revision"],
                "bound_upstream_semantic_hash": kwargs["semantic_hash"],
            }
        )
        self.edges[key] = edge
        return edge


def _provider(
    nodes: dict[tuple[str, str], DependencyNodeSnapshot],
) -> DependencyNodeProviderRegistry:
    grouped: dict[str, dict[str, DependencyNodeSnapshot]] = defaultdict(dict)
    for (entity_type, entity_id), snapshot in nodes.items():
        grouped[entity_type][entity_id] = snapshot
    return DependencyNodeProviderRegistry(
        CallbackDependencyNodeProvider(
            entity_type,
            lambda _project_id, entity_id, values=values: values.get(entity_id),
        )
        for entity_type, values in grouped.items()
    )


def _snap(
    entity_type: str, entity_id: str, value: str = "a", *, valid: bool = True
) -> DependencyNodeSnapshot:
    return DependencyNodeSnapshot(
        ref=DependencyNodeRef(
            entity_type=entity_type,
            entity_id=entity_id,
            revision=1,
            semantic_hash=canonical_semantic_hash({"value": value}),
        ),
        valid=valid,
        recovery_action=ImpactAction.REGENERATE,
    )


def test_semantic_hash_ignores_mapping_order_and_sorts_reference_lists() -> None:
    assert canonical_semantic_hash({"b": ["z", "a"], "a": 1}) == canonical_semantic_hash(
        {"a": 1, "b": ["a", "z"]}
    )


def test_change_observation_distinguishes_nonsemantic_semantic_and_invalid() -> None:
    before = _snap("Requirement", "r1", "same")
    assert (
        observe_entity_change(before, _snap("Requirement", "r1", "same"))
        is ChangeObservation.NON_SEMANTIC
    )
    assert (
        observe_entity_change(before, _snap("Requirement", "r1", "changed"))
        is ChangeObservation.SEMANTIC_CHANGED
    )
    assert (
        observe_entity_change(before, _snap("Requirement", "r1", "same", valid=False))
        is ChangeObservation.SOURCE_INVALID
    )


def test_bfs_diamond_is_deduplicated_and_deterministic() -> None:
    nodes = {
        (kind, name): _snap(kind, name)
        for kind, name in [("Claim", "c"), ("Pin", "p1"), ("Pin", "p2"), ("Firmware", "f")]
    }
    repository = MemoryGraphRepository()
    service = DependencyGraphService(repository, _provider(nodes))
    for upstream, downstream in [("c", "p1"), ("c", "p2")]:
        service.bind(
            PROJECT,
            upstream_type="Claim",
            upstream_id=upstream,
            downstream_type="Pin",
            downstream_id=downstream,
            dependency_kind=DependencyKind.SELECTION,
            required=True,
            invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE,
            reason="claim selects pin",
        )
    service.bind(
        PROJECT,
        upstream_type="Pin",
        upstream_id="p1",
        downstream_type="Firmware",
        downstream_id="f",
        dependency_kind=DependencyKind.GENERATION,
        required=True,
        invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE,
        reason="pin feeds firmware",
    )
    service.bind(
        PROJECT,
        upstream_type="Pin",
        upstream_id="p2",
        downstream_type="Firmware",
        downstream_id="f",
        dependency_kind=DependencyKind.GENERATION,
        required=True,
        invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE,
        reason="pin feeds firmware",
    )
    changed = _snap("Claim", "c", "changed")
    plan = service.propagate(PROJECT, nodes[("Claim", "c")], changed)
    assert [(item.node.entity_type, item.node.entity_id) for item in plan.impacts] == [
        ("Pin", "p1"),
        ("Pin", "p2"),
        ("Firmware", "f"),
    ]
    assert len([item for item in plan.impacts if item.node.entity_id == "f"]) == 1


def test_required_invalid_source_invalidates_and_cannot_be_downgraded() -> None:
    nodes = {("Claim", "c"): _snap("Claim", "c"), ("Artifact", "a"): _snap("Artifact", "a")}
    repository = MemoryGraphRepository()
    service = DependencyGraphService(repository, _provider(nodes))
    service.bind(
        PROJECT,
        upstream_type="Claim",
        upstream_id="c",
        downstream_type="Artifact",
        downstream_id="a",
        dependency_kind=DependencyKind.INPUT,
        required=True,
        invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
        reason="required claim",
    )
    plan = service.propagate(PROJECT, nodes[("Claim", "c")], _snap("Claim", "c", valid=False))
    assert plan.impacts[0].projected_status is DependencyNodeStatus.INVALID
    state = repository.get_node_state(PROJECT, "Artifact", "a")
    assert state is not None and state.status is DependencyNodeStatus.INVALID
    service.propagate(
        PROJECT, _snap("Claim", "c", valid=False), _snap("Claim", "c", "new", valid=True)
    )
    assert (
        repository.get_node_state(PROJECT, "Artifact", "a").status is DependencyNodeStatus.INVALID
    )


def test_cycle_is_rejected_with_stable_error_code() -> None:
    nodes = {("A", "a"): _snap("A", "a"), ("B", "b"): _snap("B", "b")}
    repository = MemoryGraphRepository()
    service = DependencyGraphService(repository, _provider(nodes))
    service.bind(
        PROJECT,
        upstream_type="A",
        upstream_id="a",
        downstream_type="B",
        downstream_id="b",
        dependency_kind=DependencyKind.INPUT,
        required=True,
        invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE,
        reason="a to b",
    )
    with pytest.raises(EngineeringError) as error:
        service.bind(
            PROJECT,
            upstream_type="B",
            upstream_id="b",
            downstream_type="A",
            downstream_id="a",
            dependency_kind=DependencyKind.INPUT,
            required=True,
            invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE,
            reason="b to a",
        )
    assert error.value.code is EngineeringErrorCode.DEPENDENCY_CYCLE


def test_unknown_provider_fails_closed() -> None:
    registry = DependencyNodeProviderRegistry()
    with pytest.raises(EngineeringError) as error:
        registry.resolve(PROJECT, "NotRegistered", "x")
    assert error.value.code is EngineeringErrorCode.CAPABILITY_UNAVAILABLE
