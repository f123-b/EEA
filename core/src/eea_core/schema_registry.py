"""Versioned Core schema registry."""

from dataclasses import dataclass

from pydantic import BaseModel

from eea_core.ai import AIUsageRecord, PromptDefinition
from eea_core.claims import (
    ClaimConflict,
    ClaimPredicateDefinition,
    EngineeringClaim,
    EngineeringValue,
)
from eea_core.entities import (
    Artifact,
    EngineeringDecision,
    Evidence,
    Issue,
    Job,
    PermissionAuditRecord,
    Project,
    TraceabilityEdge,
)


@dataclass(frozen=True, slots=True)
class SchemaRegistration:
    name: str
    version: str
    model: type[BaseModel]


class SchemaRegistry:
    """Rejects unknown or duplicate schemas and exports JSON Schema."""

    def __init__(self) -> None:
        self._registrations: dict[str, SchemaRegistration] = {}

    def register(self, registration: SchemaRegistration) -> None:
        if registration.name in self._registrations:
            raise ValueError(f"Schema is already registered: {registration.name}")
        self._registrations[registration.name] = registration

    def list(self) -> list[SchemaRegistration]:
        return sorted(self._registrations.values(), key=lambda item: item.name)

    def get(self, name: str) -> SchemaRegistration | None:
        return self._registrations.get(name)

    def json_schema(self, name: str) -> dict[str, object] | None:
        registration = self.get(name)
        if registration is None:
            return None
        return registration.model.model_json_schema()


def create_core_schema_registry() -> SchemaRegistry:
    registry = SchemaRegistry()
    for model in (
        AIUsageRecord,
        Artifact,
        ClaimConflict,
        ClaimPredicateDefinition,
        EngineeringDecision,
        EngineeringClaim,
        EngineeringValue,
        Evidence,
        Issue,
        Job,
        PermissionAuditRecord,
        PromptDefinition,
        Project,
        TraceabilityEdge,
    ):
        registry.register(SchemaRegistration(model.__name__, "1.0", model))
    return registry
