"""Deterministic Domain Extension registry, composition, and project activation service."""

from __future__ import annotations

import heapq
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from eea_core.domain_extensions import (
    DomainActivation,
    DomainCompositionPlan,
    DomainContextContribution,
    DomainDescriptor,
    DomainGeneratorContribution,
    DomainRuleContribution,
    DomainUIContribution,
)
from eea_core.enums import DomainActivationStatus, DomainRulePhase, DomainTrustTier
from eea_core.errors import EngineeringError, ProjectNotFoundError
from eea_core.repositories import DomainActivationRepository, ProjectRepository
from eea_ports.domain_extensions import DomainPlugin
from pydantic import BaseModel, ValidationError

SUPPORTED_DOMAIN_API_VERSION = "1"
_PHASE_ORDER = {phase: index for index, phase in enumerate(DomainRulePhase)}


def _plugin_value(plugin: DomainPlugin, name: str, default: object) -> object:
    value = getattr(plugin, name, default)
    if callable(value):
        return value()
    return value


def _parse_model[ModelT: BaseModel](
    value: object, model_type: type[ModelT], *, domain_id: str
) -> ModelT:
    if isinstance(value, model_type):
        return value
    try:
        return model_type.model_validate(value)
    except (TypeError, ValidationError) as exc:
        raise EngineeringError(
            "DOMAIN_INCOMPATIBLE",  # type: ignore[arg-type]
            "Domain contribution does not match the M14 contract",
            details={"domain_id": domain_id, "model": model_type.__name__, "reason": str(exc)},
        ) from None


class DomainExtensionRegistry:
    """Registry with deterministic dependency, capability, rule, and generator ordering."""

    def __init__(self, plugins: Iterable[DomainPlugin] = ()) -> None:
        self._plugins: dict[str, DomainPlugin] = {}
        self._descriptors: dict[str, DomainDescriptor] = {}
        self._rules: dict[str, tuple[DomainRuleContribution, ...]] = {}
        self._generators: dict[str, tuple[DomainGeneratorContribution, ...]] = {}
        self._contexts: dict[str, tuple[DomainContextContribution, ...]] = {}
        self._ui_extensions: dict[str, tuple[DomainUIContribution, ...]] = {}
        for plugin in plugins:
            self.register(plugin)

    def register(self, plugin: DomainPlugin) -> DomainDescriptor:
        descriptor = _parse_model(
            _plugin_value(plugin, "descriptor", None), DomainDescriptor, domain_id="unknown"
        )
        if descriptor.api_version != SUPPORTED_DOMAIN_API_VERSION:
            raise EngineeringError(
                "DOMAIN_INCOMPATIBLE",  # type: ignore[arg-type]
                "Domain plugin API version is not supported",
                details={
                    "domain_id": descriptor.domain_id,
                    "api_version": descriptor.api_version,
                    "supported_api_version": SUPPORTED_DOMAIN_API_VERSION,
                },
            )
        if descriptor.trust_tier is not DomainTrustTier.BUNDLED:
            raise EngineeringError(
                "CAPABILITY_UNAVAILABLE",  # type: ignore[arg-type]
                "Non-bundled Domain plugins require unavailable trust verification or isolation",
                details={"domain_id": descriptor.domain_id, "trust_tier": descriptor.trust_tier},
            )
        if descriptor.domain_id in self._plugins:
            raise EngineeringError(
                "DOMAIN_COMPOSITION_CONFLICT",  # type: ignore[arg-type]
                "A Domain with this id is already registered",
                details={"domain_id": descriptor.domain_id},
            )
        rules = tuple(
            _parse_model(item, DomainRuleContribution, domain_id=descriptor.domain_id)
            for item in cast(Sequence[object], _plugin_value(plugin, "rules", ()))
        )
        generators = tuple(
            _parse_model(item, DomainGeneratorContribution, domain_id=descriptor.domain_id)
            for item in cast(Sequence[object], _plugin_value(plugin, "generators", ()))
        )
        contexts = tuple(
            _parse_model(item, DomainContextContribution, domain_id=descriptor.domain_id)
            for item in cast(Sequence[object], _plugin_value(plugin, "contexts", ()))
        )
        ui_extensions = tuple(
            _parse_model(item, DomainUIContribution, domain_id=descriptor.domain_id)
            for item in cast(Sequence[object], _plugin_value(plugin, "ui_extensions", ()))
        )
        self._assert_unique((item.rule_id for item in rules), "rule_id", descriptor.domain_id)
        self._assert_unique(
            (item.generator_id for item in generators), "generator_id", descriptor.domain_id
        )
        self._assert_unique(
            (item.context_id for item in contexts), "context_id", descriptor.domain_id
        )
        self._assert_unique(
            (item.extension_id for item in ui_extensions), "extension_id", descriptor.domain_id
        )
        self._plugins[descriptor.domain_id] = plugin
        self._descriptors[descriptor.domain_id] = descriptor
        self._rules[descriptor.domain_id] = rules
        self._generators[descriptor.domain_id] = generators
        self._contexts[descriptor.domain_id] = contexts
        self._ui_extensions[descriptor.domain_id] = ui_extensions
        return descriptor

    @staticmethod
    def _assert_unique(values: Iterable[str], kind: str, domain_id: str) -> None:
        values_list = list(values)
        if len(values_list) != len(set(values_list)):
            raise EngineeringError(
                "DOMAIN_COMPOSITION_CONFLICT",  # type: ignore[arg-type]
                f"Domain contains duplicate {kind} values",
                details={"domain_id": domain_id, kind: sorted(values_list)},
            )

    def descriptors(self) -> list[DomainDescriptor]:
        return [self._descriptors[key] for key in sorted(self._descriptors)]

    def get_descriptor(self, domain_id: str) -> DomainDescriptor:
        descriptor = self._descriptors.get(domain_id)
        if descriptor is None:
            raise EngineeringError(
                "DOMAIN_NOT_FOUND",  # type: ignore[arg-type]
                "Domain plugin was not found",
                details={"domain_id": domain_id},
            )
        return descriptor

    def schema(self, domain_id: str) -> dict[str, object]:
        self.get_descriptor(domain_id)
        value = _plugin_value(self._plugins[domain_id], "schema", {})
        if not isinstance(value, dict):
            raise EngineeringError(
                "DOMAIN_INCOMPATIBLE",  # type: ignore[arg-type]
                "Domain schema contribution must be an object",
                details={"domain_id": domain_id},
            )
        return cast(dict[str, object], value)

    def artifacts(self, domain_id: str) -> list[dict[str, Any]]:
        self.get_descriptor(domain_id)
        value = _plugin_value(self._plugins[domain_id], "artifacts", ())
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise EngineeringError(
                "DOMAIN_INCOMPATIBLE",  # type: ignore[arg-type]
                "Domain artifact contribution must be a sequence",
                details={"domain_id": domain_id},
            )
        artifacts: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                raise EngineeringError(
                    "DOMAIN_INCOMPATIBLE",  # type: ignore[arg-type]
                    "Domain artifact metadata must be an object",
                    details={"domain_id": domain_id},
                )
            artifacts.append(dict(item))
        return artifacts

    def resolve_composition(
        self,
        domain_ids: Iterable[str],
        *,
        selected_capabilities: Mapping[str, str] | None = None,
    ) -> DomainCompositionPlan:
        requested = sorted(set(domain_ids))
        for domain_id in requested:
            self.get_descriptor(domain_id)
        included = set(requested)
        dependency_edges: set[tuple[str, str]] = set()
        pending = list(requested)
        while pending:
            domain_id = pending.pop(0)
            descriptor = self.get_descriptor(domain_id)
            for required in sorted(descriptor.requires_domains):
                if required not in self._descriptors:
                    raise EngineeringError(
                        "DOMAIN_DEPENDENCY_MISSING",  # type: ignore[arg-type]
                        "Required Domain is not registered",
                        details={"domain_id": domain_id, "required_domain": required},
                    )
                dependency_edges.add((domain_id, required))
                if required not in included:
                    included.add(required)
                    pending.append(required)

        for domain_id in sorted(included):
            descriptor = self._descriptors[domain_id]
            conflicts = sorted(set(descriptor.conflicts_with) & included)
            if conflicts:
                raise EngineeringError(
                    "DOMAIN_COMPOSITION_CONFLICT",  # type: ignore[arg-type]
                    "Domain composition contains a declared conflict",
                    details={"domain_id": domain_id, "conflicts_with": conflicts},
                )

        capability_providers: dict[str, list[str]] = {}
        for domain_id in sorted(included):
            for capability in self._descriptors[domain_id].provided_capabilities:
                capability_providers.setdefault(capability, []).append(domain_id)
        routes: dict[str, str] = {}
        selected = selected_capabilities or {}
        for capability in sorted(capability_providers):
            providers = sorted(
                capability_providers[capability],
                key=lambda key: (-self._descriptors[key].priority, key),
            )
            selected_provider = selected.get(capability, providers[0])
            if selected_provider not in providers:
                raise EngineeringError(
                    "DOMAIN_COMPOSITION_CONFLICT",  # type: ignore[arg-type]
                    "Selected capability provider is not in the active composition",
                    details={
                        "capability": capability,
                        "selected_provider": selected_provider,
                        "providers": providers,
                    },
                )
            routes[capability] = selected_provider
        for domain_id in sorted(included):
            for capability in self._descriptors[domain_id].required_capabilities:
                if capability not in routes:
                    raise EngineeringError(
                        "DOMAIN_DEPENDENCY_MISSING",  # type: ignore[arg-type]
                        "Required Domain capability is not provided",
                        details={"domain_id": domain_id, "capability": capability},
                    )
            for generator in self._generators[domain_id]:
                missing = sorted(set(generator.requires_capabilities) - set(routes))
                if missing:
                    raise EngineeringError(
                        "DOMAIN_DEPENDENCY_MISSING",  # type: ignore[arg-type]
                        "Generator requires an unavailable capability",
                        details={
                            "domain_id": domain_id,
                            "generator_id": generator.generator_id,
                            "capabilities": missing,
                        },
                    )

        ordered_domains = self._topological_domains(included, dependency_edges)
        rules = self._ordered_rules(ordered_domains)
        generators = self._ordered_generators(ordered_domains)
        contexts = sorted(
            (item for domain_id in ordered_domains for item in self._contexts[domain_id]),
            key=lambda item: item.context_id,
        )
        ui_extensions = sorted(
            (item for domain_id in ordered_domains for item in self._ui_extensions[domain_id]),
            key=lambda item: item.extension_id,
        )
        return DomainCompositionPlan(
            active_domain_ids=sorted(included),
            ordered_domain_ids=ordered_domains,
            dependency_edges=[list(edge) for edge in sorted(dependency_edges)],
            capability_routes=routes,
            rules=rules,
            generators=generators,
            context_contributions=contexts,
            ui_contributions=ui_extensions,
        )

    def _topological_domains(self, domain_ids: set[str], edges: set[tuple[str, str]]) -> list[str]:
        outgoing: dict[str, set[str]] = {domain_id: set() for domain_id in domain_ids}
        indegree: dict[str, int] = dict.fromkeys(domain_ids, 0)
        for dependent, required in edges:
            if dependent not in outgoing or required not in outgoing:
                continue
            outgoing[required].add(dependent)
            indegree[dependent] += 1
        queue = [
            (-self._descriptors[domain_id].priority, domain_id)
            for domain_id, degree in indegree.items()
            if degree == 0
        ]
        heapq.heapify(queue)
        ordered: list[str] = []
        while queue:
            _, domain_id = heapq.heappop(queue)
            ordered.append(domain_id)
            for dependent in sorted(outgoing[domain_id]):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    heapq.heappush(queue, (-self._descriptors[dependent].priority, dependent))
        if len(ordered) != len(domain_ids):
            raise EngineeringError(
                "DOMAIN_COMPOSITION_CONFLICT",  # type: ignore[arg-type]
                "Domain dependency graph contains a cycle",
                details={"domain_ids": sorted(domain_ids)},
            )
        return ordered

    def _ordered_rules(self, ordered_domains: list[str]) -> list[DomainRuleContribution]:
        rules = [item for domain_id in ordered_domains for item in self._rules[domain_id]]
        self._assert_unique((item.rule_id for item in rules), "rule_id", "composition")
        return sorted(
            rules,
            key=lambda item: (
                _PHASE_ORDER[item.phase],
                -item.priority,
                item.rule_id,
                item.rule_version,
            ),
        )

    def _ordered_generators(self, ordered_domains: list[str]) -> list[DomainGeneratorContribution]:
        generators = [item for domain_id in ordered_domains for item in self._generators[domain_id]]
        self._assert_unique(
            (item.generator_id for item in generators), "generator_id", "composition"
        )
        by_id = {item.generator_id: item for item in generators}
        outgoing: dict[str, set[str]] = {generator_id: set() for generator_id in by_id}
        indegree: dict[str, int] = dict.fromkeys(by_id, 0)
        for item in generators:
            for target in item.before:
                if target not in by_id:
                    raise EngineeringError(
                        "DOMAIN_COMPOSITION_CONFLICT",  # type: ignore[arg-type]
                        "Generator ordering references an unknown generator",
                        details={"generator_id": item.generator_id, "target": target},
                    )
                outgoing[item.generator_id].add(target)
                indegree[target] += 1
            for target in item.after:
                if target not in by_id:
                    raise EngineeringError(
                        "DOMAIN_COMPOSITION_CONFLICT",  # type: ignore[arg-type]
                        "Generator ordering references an unknown generator",
                        details={"generator_id": item.generator_id, "target": target},
                    )
                outgoing[target].add(item.generator_id)
                indegree[item.generator_id] += 1
        queue = [generator_id for generator_id, degree in indegree.items() if degree == 0]
        heapq.heapify(queue)
        ordered: list[DomainGeneratorContribution] = []
        while queue:
            generator_id = heapq.heappop(queue)
            ordered.append(by_id[generator_id])
            for dependent in sorted(outgoing[generator_id]):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    heapq.heappush(queue, dependent)
        if len(ordered) != len(generators):
            raise EngineeringError(
                "DOMAIN_COMPOSITION_CONFLICT",  # type: ignore[arg-type]
                "Generator graph contains a cycle",
                details={"generator_ids": sorted(by_id)},
            )
        return ordered

    def ui_extensions(self, domain_ids: Iterable[str]) -> list[DomainUIContribution]:
        plan = self.resolve_composition(domain_ids)
        return plan.ui_contributions


class DomainExtensionService:
    """Project-scoped activation operations backed by a durable repository."""

    def __init__(
        self,
        registry: DomainExtensionRegistry,
        activation_repository: DomainActivationRepository,
        project_repository: ProjectRepository,
    ) -> None:
        self.registry = registry
        self._activations = activation_repository
        self._projects = project_repository

    def _ensure_project(self, project_id: UUID) -> None:
        if self._projects.get(project_id) is None:
            raise ProjectNotFoundError(project_id)

    def ensure_project(self, project_id: UUID) -> None:
        self._ensure_project(project_id)

    def list_activations(self, project_id: UUID) -> list[DomainActivation]:
        self._ensure_project(project_id)
        return self._activations.list_for_project(project_id)

    def state(self, project_id: UUID, domain_id: str) -> DomainActivation:
        self._ensure_project(project_id)
        self.registry.get_descriptor(domain_id)
        activation = self._activations.get(project_id, domain_id)
        if activation is None:
            raise EngineeringError(
                "DOMAIN_NOT_FOUND",  # type: ignore[arg-type]
                "Domain activation was not found",
                details={"project_id": str(project_id), "domain_id": domain_id},
            )
        return activation

    def available(self, project_id: UUID) -> list[tuple[DomainDescriptor, bool]]:
        active = {
            item.domain_id
            for item in self.list_activations(project_id)
            if item.status is DomainActivationStatus.ACTIVE
        }
        return [
            (descriptor, descriptor.domain_id in active)
            for descriptor in self.registry.descriptors()
        ]

    def resolve(
        self,
        project_id: UUID,
        additional_domain_ids: Iterable[str] = (),
        *,
        selected_capabilities: Mapping[str, str] | None = None,
    ) -> DomainCompositionPlan:
        active = [
            item.domain_id
            for item in self.list_activations(project_id)
            if item.status is DomainActivationStatus.ACTIVE
        ]
        return self.registry.resolve_composition(
            [*active, *additional_domain_ids], selected_capabilities=selected_capabilities
        )

    def activate(
        self,
        project_id: UUID,
        domain_id: str,
        *,
        configuration: dict[str, object] | None = None,
        activated_by: str = "system",
    ) -> DomainActivation:
        self._ensure_project(project_id)
        plan = self.resolve(project_id, [domain_id])
        requested_activation: DomainActivation | None = None
        for resolved_domain_id in plan.ordered_domain_ids:
            existing = self._activations.get(project_id, resolved_domain_id)
            if existing is not None and existing.status is DomainActivationStatus.ACTIVE:
                if resolved_domain_id == domain_id:
                    requested_activation = existing
                continue
            descriptor = self.registry.get_descriptor(resolved_domain_id)
            activation = self._build_activation(
                project_id,
                resolved_domain_id,
                descriptor,
                plan,
                existing=existing,
                configuration=configuration if resolved_domain_id == domain_id else {},
                activated_by=activated_by,
            )
            if existing is None:
                stored: DomainActivation = self._activations.add(activation)
            else:
                saved = self._activations.save(activation)
                if saved is None:
                    raise EngineeringError(
                        "DOMAIN_INCOMPATIBLE",  # type: ignore[arg-type]
                        "Domain activation could not be updated",
                        details={"project_id": str(project_id), "domain_id": resolved_domain_id},
                    )
                stored = saved
            if resolved_domain_id == domain_id:
                requested_activation = stored
        if requested_activation is None:
            raise EngineeringError(
                "DOMAIN_INCOMPATIBLE",  # type: ignore[arg-type]
                "Requested Domain was not present in the resolved composition",
                details={"domain_id": domain_id},
            )
        return requested_activation

    @staticmethod
    def _build_activation(
        project_id: UUID,
        domain_id: str,
        descriptor: DomainDescriptor,
        plan: DomainCompositionPlan,
        *,
        existing: DomainActivation | None,
        configuration: dict[str, object] | None,
        activated_by: str,
    ) -> DomainActivation:
        now = datetime.now(UTC)
        return DomainActivation(
            id=existing.id if existing else uuid4(),
            schema_version=existing.schema_version if existing else "1.0",
            revision=existing.revision + 1 if existing else 1,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            metadata=existing.metadata if existing else {},
            project_id=project_id,
            domain_id=domain_id,
            plugin_id=descriptor.plugin_id,
            plugin_version=descriptor.version,
            domain_schema_version=descriptor.schema_version,
            status=DomainActivationStatus.ACTIVE,
            configuration=configuration or {},
            activated_at=now,
            activated_by=activated_by,
            capability_snapshot=dict(plan.capability_routes),
            dependency_snapshot={
                "domain_ids": plan.active_domain_ids,
                "edges": plan.dependency_edges,
            },
        )

    def deactivate(self, project_id: UUID, domain_id: str) -> DomainActivation:
        self._ensure_project(project_id)
        existing = self._activations.get(project_id, domain_id)
        if existing is None:
            raise EngineeringError(
                "DOMAIN_NOT_FOUND",  # type: ignore[arg-type]
                "Domain activation was not found",
                details={"project_id": str(project_id), "domain_id": domain_id},
            )
        remaining = [
            item.domain_id
            for item in self._activations.list_for_project(project_id)
            if item.status is DomainActivationStatus.ACTIVE and item.domain_id != domain_id
        ]
        remaining_plan = self.registry.resolve_composition(remaining)
        if set(remaining_plan.active_domain_ids) != set(remaining):
            missing = sorted(set(remaining_plan.active_domain_ids) - set(remaining))
            raise EngineeringError(
                "DOMAIN_DEPENDENCY_MISSING",  # type: ignore[arg-type]
                "A required Domain cannot be disabled while dependents remain active",
                details={"domain_id": domain_id, "required_by_active_domains": missing},
            )
        now = datetime.now(UTC)
        disabled = existing.model_copy(
            update={
                "revision": existing.revision + 1,
                "updated_at": now,
                "status": DomainActivationStatus.DISABLED,
            }
        )
        saved = self._activations.save(disabled)
        if saved is None:
            raise EngineeringError(
                "DOMAIN_INCOMPATIBLE",  # type: ignore[arg-type]
                "Domain activation could not be updated",
                details={"project_id": str(project_id), "domain_id": domain_id},
            )
        return saved

    def validate(
        self,
        project_id: UUID,
        domain_ids: Iterable[str],
        *,
        selected_capabilities: Mapping[str, str] | None = None,
    ) -> DomainCompositionPlan:
        return self.resolve(project_id, domain_ids, selected_capabilities=selected_capabilities)
