"""Framework-independent contracts for the M18 Engineering Dependency Graph.

The graph deliberately lives beside, rather than inside, traceability.  It
describes engineering freshness and invalidation, while ``TraceabilityEdge``
continues to describe historical evidence and relationships.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from eea_core.entities import EntityBase, Sha256, utc_now
from eea_core.enums import (
    ChangeObservation,
    DependencyKind,
    DependencyNodeStatus,
    ImpactAction,
    InvalidationPolicy,
)

DEPENDENCY_GRAPH_SCHEMA_VERSION = "1.0.0"
DEPENDENCY_GRAPH_POLICY_VERSION = "m18-dependency-policy-1"


def _canonical_value(value: Any) -> Any:
    """Convert supported values to deterministic JSON-compatible values.

    Lists are ordered canonically by their serialized representation.  This
    keeps semantic hashes stable when callers supply sets of references in a
    different order, while field-level providers remain responsible for
    deciding which fields are semantic in the first place.
    """

    if isinstance(value, BaseModel):
        return _canonical_value(value.model_dump(mode="json"))
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        timestamp = value if value.tzinfo else value.replace(tzinfo=UTC)
        return timestamp.astimezone(UTC).isoformat()
    if isinstance(value, dict):
        return {str(key): _canonical_value(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple, set, frozenset)):
        values = [_canonical_value(item) for item in value]
        return sorted(
            values,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
        )
    if hasattr(value, "value") and isinstance(value.value, str):
        return value.value
    return value


def canonical_semantic_hash(payload: Any) -> str:
    """Return the SHA-256 hash of a canonical semantic JSON payload."""

    encoded = json.dumps(
        _canonical_value(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class DependencyNodeRef(BaseModel):
    """Stable, project-scoped reference to a graph node snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_type: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")
    entity_id: str = Field(min_length=1, max_length=500)
    revision: int = Field(ge=1)
    semantic_hash: Sha256


class EngineeringDependencyEdge(EntityBase):
    """A uniform upstream -> downstream engineering dependency."""

    schema_version: str = DEPENDENCY_GRAPH_SCHEMA_VERSION
    project_id: UUID
    upstream_type: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")
    upstream_id: str = Field(min_length=1, max_length=500)
    downstream_type: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")
    downstream_id: str = Field(min_length=1, max_length=500)
    dependency_kind: DependencyKind
    required: bool = True
    invalidation_policy: InvalidationPolicy
    bound_upstream_revision: int = Field(ge=1)
    bound_upstream_semantic_hash: Sha256
    reason: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def cannot_self_depend(self) -> Self:
        if (self.upstream_type, self.upstream_id) == (self.downstream_type, self.downstream_id):
            raise ValueError("dependency edge cannot point from a node to itself")
        return self

    @property
    def identity(self) -> tuple[UUID, str, str, str, str, DependencyKind]:
        return (
            self.project_id,
            self.upstream_type,
            self.upstream_id,
            self.downstream_type,
            self.downstream_id,
            self.dependency_kind,
        )

    def upstream_ref(self) -> DependencyNodeRef:
        return DependencyNodeRef(
            entity_type=self.upstream_type,
            entity_id=self.upstream_id,
            revision=self.bound_upstream_revision,
            semantic_hash=self.bound_upstream_semantic_hash,
        )

    def downstream_ref(
        self, *, revision: int = 1, semantic_hash: str = "0" * 64
    ) -> DependencyNodeRef:
        return DependencyNodeRef(
            entity_type=self.downstream_type,
            entity_id=self.downstream_id,
            revision=revision,
            semantic_hash=semantic_hash,
        )


class DependencyNodeState(EntityBase):
    """Latest observed graph state for one project-scoped node."""

    schema_version: str = DEPENDENCY_GRAPH_SCHEMA_VERSION
    project_id: UUID
    entity_type: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")
    entity_id: str = Field(min_length=1, max_length=500)
    observed_revision: int = Field(ge=1)
    observed_semantic_hash: Sha256
    status: DependencyNodeStatus = DependencyNodeStatus.CURRENT
    invalidated_by: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    stale_since: datetime | None = None

    @field_validator("stale_since")
    @classmethod
    def normalize_stale_since(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @property
    def node_key(self) -> tuple[str, str]:
        return self.entity_type, self.entity_id

    def ref(self) -> DependencyNodeRef:
        return DependencyNodeRef(
            entity_type=self.entity_type,
            entity_id=self.entity_id,
            revision=self.observed_revision,
            semantic_hash=self.observed_semantic_hash,
        )


class DependencyImpact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node: DependencyNodeRef
    depth: int = Field(ge=1)
    status_before: DependencyNodeStatus
    projected_status: DependencyNodeStatus
    reason: str = Field(min_length=1, max_length=2000)
    dependency_path: list[DependencyNodeRef] = Field(default_factory=list)
    via_edge_id: UUID | None = None
    recommended_action: ImpactAction


class ImpactPlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ImpactAction
    node: DependencyNodeRef
    depth: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)
    dependency_path: list[DependencyNodeRef] = Field(default_factory=list)


class ImpactPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = DEPENDENCY_GRAPH_SCHEMA_VERSION
    policy_version: str = DEPENDENCY_GRAPH_POLICY_VERSION
    generated_at: datetime = Field(default_factory=utc_now)
    source: DependencyNodeRef
    source_status: DependencyNodeStatus
    impacts: list[DependencyImpact] = Field(default_factory=list)
    steps: list[ImpactPlanStep] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = [
    "DEPENDENCY_GRAPH_POLICY_VERSION",
    "DEPENDENCY_GRAPH_SCHEMA_VERSION",
    "ChangeObservation",
    "DependencyImpact",
    "DependencyKind",
    "DependencyNodeRef",
    "DependencyNodeState",
    "DependencyNodeStatus",
    "EngineeringDependencyEdge",
    "ImpactAction",
    "ImpactPlan",
    "ImpactPlanStep",
    "InvalidationPolicy",
    "canonical_semantic_hash",
]
