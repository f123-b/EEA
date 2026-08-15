"""M18B Domain Composition Contract acceptance tests."""

from collections.abc import Sequence
from uuid import UUID

import pytest
from eea_application.domains import DomainExtensionRegistry, DomainExtensionService
from eea_core.domain_extensions import (
    DomainActivation,
    DomainCompositionState,
    DomainDescriptor,
    DomainGeneratorContribution,
    DomainRuleContribution,
)
from eea_core.entities import Project
from eea_core.enums import DomainActivationStatus, DomainRulePhase, EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_core.repositories import (
    DomainActivationRepository,
    DomainCompositionStateRepository,
    ProjectRepository,
)


class FakePlugin:
    def __init__(
        self,
        descriptor: DomainDescriptor,
        *,
        rules: Sequence[DomainRuleContribution] = (),
        generators: Sequence[DomainGeneratorContribution] = (),
        schema: dict[str, object] | None = None,
    ) -> None:
        self.descriptor = descriptor
        self._rules = tuple(rules)
        self._generators = tuple(generators)
        self._schema = schema or {"type": "object"}

    def rules(self) -> Sequence[object]:
        return self._rules

    def generators(self) -> Sequence[object]:
        return self._generators

    def contexts(self) -> Sequence[object]:
        return ()

    def ui_extensions(self) -> Sequence[object]:
        return ()

    def schema(self) -> dict[str, object]:
        return self._schema


class MemoryProjectRepository(ProjectRepository):
    def __init__(self) -> None:
        self.items: dict[UUID, Project] = {}

    def add(self, project: Project) -> Project:
        self.items[project.id] = project
        return project

    def get(self, project_id: UUID, *, include_deleted: bool = False) -> Project | None:
        return self.items.get(project_id)

    def list(self, *, include_deleted: bool = False) -> list[Project]:
        return list(self.items.values())

    def save(self, project: Project, *, expected_revision: int) -> Project | None:
        self.items[project.id] = project
        return project


class MemoryActivationRepository(DomainActivationRepository):
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, str], DomainActivation] = {}

    def add(self, activation: DomainActivation) -> DomainActivation:
        self.items[(activation.project_id, activation.domain_id)] = activation
        return activation

    def get(self, project_id: UUID, domain_id: str) -> DomainActivation | None:
        return self.items.get((project_id, domain_id))

    def list_for_project(self, project_id: UUID) -> list[DomainActivation]:
        return sorted(
            (
                item
                for (item_project_id, _), item in self.items.items()
                if item_project_id == project_id
            ),
            key=lambda item: item.domain_id,
        )

    def save(self, activation: DomainActivation) -> DomainActivation | None:
        key = (activation.project_id, activation.domain_id)
        if key not in self.items:
            return None
        self.items[key] = activation
        return activation


class MemoryCompositionRepository(DomainCompositionStateRepository):
    def __init__(self) -> None:
        self.items: dict[UUID, DomainCompositionState] = {}

    def add(self, state: DomainCompositionState) -> DomainCompositionState:
        self.items[state.project_id] = state
        return state

    def get(self, project_id: UUID) -> DomainCompositionState | None:
        return self.items.get(project_id)

    def save(
        self, state: DomainCompositionState, *, expected_revision: int
    ) -> DomainCompositionState | None:
        current = self.items.get(state.project_id)
        if current is None or current.revision != expected_revision:
            return None
        self.items[state.project_id] = state
        return state


class FailingActivationRepository(MemoryActivationRepository):
    def __init__(self, fail_on: int) -> None:
        super().__init__()
        self.fail_on = fail_on
        self.calls = 0

    def add(self, activation: DomainActivation) -> DomainActivation:
        self.calls += 1
        if self.calls == self.fail_on:
            raise RuntimeError("injected activation persistence failure")
        return super().add(activation)


def _plugin(
    domain_id: str,
    *,
    capabilities: list[str] | None = None,
    required_capabilities: list[str] | None = None,
    requires_domains: list[str] | None = None,
    conflicts_with: list[str] | None = None,
    priority: int = 0,
    version: str = "1.0.0",
    schema_version: str = "1.0",
    migration_provider: str | None = None,
    rule_id: str | None = None,
    rule_version: str = "1",
    generator_id: str | None = None,
    generator_version: str = "1",
    after: list[str] | None = None,
    schema: dict[str, object] | None = None,
) -> FakePlugin:
    return FakePlugin(
        DomainDescriptor(
            id=domain_id,
            plugin_id=f"plugin.{domain_id}",
            name=domain_id,
            version=version,
            api_version="1",
            schema_version=schema_version,
            capabilities=capabilities or [],
            required_capabilities=required_capabilities or [],
            requires_domains=requires_domains or [],
            conflicts_with=conflicts_with or [],
            priority=priority,
            migration_provider=migration_provider,
        ),
        rules=(
            DomainRuleContribution(
                rule_id=rule_id or f"{domain_id}.rule",
                rule_version=rule_version,
                phase=DomainRulePhase.PRE_DESIGN,
            ),
        ),
        generators=(
            DomainGeneratorContribution(
                generator_id=generator_id or f"{domain_id}.generator",
                version=generator_version,
                after=after or [],
            ),
        ),
        schema=schema,
    )


def _service(
    plugins: Sequence[FakePlugin],
    *,
    activations: MemoryActivationRepository | None = None,
    compositions: MemoryCompositionRepository | None = None,
) -> tuple[
    DomainExtensionService, Project, MemoryActivationRepository, MemoryCompositionRepository
]:
    projects = MemoryProjectRepository()
    project = projects.add(Project(name="M18B project"))
    activation_repo = activations or MemoryActivationRepository()
    composition_repo = compositions or MemoryCompositionRepository()
    return (
        DomainExtensionService(
            DomainExtensionRegistry(plugins), activation_repo, projects, composition_repo
        ),
        project,
        activation_repo,
        composition_repo,
    )


def test_m18b_zero_one_two_three_domain_compositions() -> None:
    transport = _plugin("transport", capabilities=["transport"], priority=10)
    motor = _plugin(
        "motor",
        required_capabilities=["transport"],
        requires_domains=["transport"],
        after=["transport.generator"],
    )
    robotics = _plugin("robotics", requires_domains=["motor"], after=["motor.generator"])
    service, project, _, _ = _service([transport, motor, robotics])

    empty = service.preview_composition(project.id)
    assert empty.active_domain_ids == []
    assert empty.capability_routes == {}

    one = service.preview_composition(project.id, ["transport"])
    two = service.preview_composition(project.id, ["motor"])
    three = service.preview_composition(project.id, ["robotics"])
    assert one.active_domain_ids == ["transport"]
    assert two.active_domain_ids == ["motor", "transport"]
    assert three.active_domain_ids == ["motor", "robotics", "transport"]
    assert three.ordered_domain_ids == ["transport", "motor", "robotics"]
    assert three.generator_order == ["transport.generator", "motor.generator", "robotics.generator"]


def test_m18b_selected_capability_is_ssot_and_survives_registration_order() -> None:
    provider_a = _plugin("provider-a", capabilities=["transport"], priority=20)
    provider_b = _plugin("provider-b", capabilities=["transport"], priority=10)
    consumer = _plugin("consumer", required_capabilities=["transport"])
    service, project, activations, compositions = _service([provider_a, provider_b, consumer])
    preview = service.preview_composition(
        project.id,
        ["consumer", "provider-a", "provider-b"],
        selected_capabilities={"transport": "provider-b"},
    )
    applied = service.apply_composition(
        project.id,
        preview.active_domain_ids,
        selected_capabilities={"transport": "provider-b"},
        expected_composition_revision=preview.composition_revision,
        expected_plan_hash=preview.plan_hash,
        applied_by="test",
    )
    assert applied.capability_routes == {"transport": "provider-b"}
    assert compositions.items[project.id].selected_capabilities == {"transport": "provider-b"}

    restarted, _, _, _ = _service(
        [consumer, provider_b, provider_a], activations=activations, compositions=compositions
    )
    restarted._projects = service._projects
    current = restarted.current_composition(project.id)
    assert current.plan_hash == applied.plan_hash
    assert current.capability_routes == {"transport": "provider-b"}
    assert current.rule_order == applied.rule_order
    assert current.generator_order == applied.generator_order


@pytest.mark.parametrize("kind", ["missing", "conflict", "cycle"])
def test_m18b_resolution_fail_closed_without_state_mutation(kind: str) -> None:
    base = _plugin("base", capabilities=["transport"])
    if kind == "missing":
        plugins = [_plugin("consumer", requires_domains=["not-registered"])]
        requested = ["consumer"]
    elif kind == "conflict":
        plugins = [base, _plugin("conflict", conflicts_with=["base"])]
        requested = ["base", "conflict"]
    else:
        plugins = [
            _plugin("cycle-a", generator_id="cycle-a", after=["cycle-b"]),
            _plugin("cycle-b", generator_id="cycle-b", after=["cycle-a"]),
        ]
        requested = ["cycle-a", "cycle-b"]
    service, project, activations, compositions = _service(plugins)
    current = service.current_composition(project.id)
    before = (dict(activations.items), dict(compositions.items))
    with pytest.raises(EngineeringError):
        service.apply_composition(
            project.id,
            requested,
            expected_composition_revision=current.composition_revision,
            expected_plan_hash=current.plan_hash,
        )
    assert activations.items == before[0]
    assert compositions.items == before[1]


def test_m18b_atomic_apply_failure_rolls_back_everything() -> None:
    plugins = [_plugin("a"), _plugin("b"), _plugin("c")]
    failing = FailingActivationRepository(fail_on=2)
    service, project, activations, compositions = _service(plugins, activations=failing)
    state_before = service.composition_state(project.id)
    preview = service.preview_composition(project.id, ["a", "b", "c"])
    with pytest.raises(RuntimeError):
        service.apply_composition(
            project.id,
            ["a", "b", "c"],
            expected_composition_revision=preview.composition_revision,
            expected_plan_hash=preview.plan_hash,
        )
    assert activations.items == {}
    assert compositions.items[project.id] == state_before


def test_m18b_cas_and_stale_preview_are_rejected() -> None:
    first = _plugin("first", capabilities=["transport"], version="1.0.0")
    service, project, activations, compositions = _service([first])
    preview = service.preview_composition(project.id, ["first"])
    service.apply_composition(
        project.id,
        ["first"],
        expected_composition_revision=preview.composition_revision,
        expected_plan_hash=preview.plan_hash,
    )
    with pytest.raises(EngineeringError) as cas:
        service.apply_composition(
            project.id,
            [],
            expected_composition_revision=preview.composition_revision,
            expected_plan_hash=preview.plan_hash,
        )
    assert cas.value.code is EngineeringErrorCode.DOMAIN_COMPOSITION_CONFLICT

    changed = _plugin("first", capabilities=["transport"], version="2.0.0")
    changed_service, _, _, _ = _service(
        [changed], activations=activations, compositions=compositions
    )
    changed_service._projects = service._projects
    with pytest.raises(EngineeringError) as stale:
        changed_service.apply_composition(
            project.id,
            ["first"],
            expected_composition_revision=2,
            expected_plan_hash=preview.plan_hash,
        )
    assert stale.value.code in {
        EngineeringErrorCode.DOMAIN_COMPOSITION_CONFLICT,
        EngineeringErrorCode.DOMAIN_INCOMPATIBLE,
    }


def test_m18b_disable_enable_preserves_configuration_and_migration_dry_run() -> None:
    original = _plugin(
        "domain", schema={"type": "object", "properties": {"enabled": {"type": "boolean"}}}
    )
    service, project, activations, compositions = _service([original])
    preview = service.preview_composition(
        project.id, ["domain"], configurations={"domain": {"enabled": True}}
    )
    service.apply_composition(
        project.id,
        ["domain"],
        configurations={"domain": {"enabled": True}},
        expected_composition_revision=preview.composition_revision,
        expected_plan_hash=preview.plan_hash,
    )
    disabled = service.deactivate(project.id, "domain")
    assert disabled.status is DomainActivationStatus.DISABLED
    assert disabled.configuration == {"enabled": True}
    service.activate(project.id, "domain")
    assert activations.get(project.id, "domain").configuration == {"enabled": True}  # type: ignore[union-attr]

    migrated_plugin = _plugin(
        "domain",
        version="2.0.0",
        schema_version="2.0",
        migration_provider="plugin.domain.migrate",
        schema={"type": "object", "properties": {"enabled": {"type": "boolean"}}},
    )
    migrated, _, _, _ = _service(
        [migrated_plugin], activations=activations, compositions=compositions
    )
    migrated._projects = service._projects
    dry_run = migrated.preview_composition(project.id, ["domain"])
    assert dry_run.compatibility_results[0]["status"] == "BLOCKED"
    assert dry_run.compatibility_results[0]["reason"] == "MIGRATION_PROVIDER_NOT_REGISTERED"


def test_m18b_backend_preview_apply_and_authoritative_get(client) -> None:
    project_id = client.post("/api/v1/projects", json={"name": "M18B API"}).json()["data"]["id"]
    preview = client.post(
        f"/api/v1/projects/{project_id}/domains/resolve-composition",
        json={"domain_ids": ["org.eea.motor_control"]},
    )
    assert preview.status_code == 200
    data = preview.json()["data"]
    assert data["composition_revision"] == 1
    assert len(data["plan_hash"]) == 64

    applied = client.post(
        f"/api/v1/projects/{project_id}/domains/apply-composition",
        json={
            "domain_ids": data["active_domain_ids"],
            "selected_capabilities": data["selected_capabilities"],
            "expected_composition_revision": data["composition_revision"],
            "expected_plan_hash": data["plan_hash"],
            "applied_by": "m18b-test",
        },
    )
    assert applied.status_code == 200
    assert applied.json()["data"]["composition_revision"] == 2

    current = client.get(f"/api/v1/projects/{project_id}/domains/composition")
    assert current.status_code == 200
    assert current.json()["data"]["plan_hash"] == data["plan_hash"]
    assert current.json()["data"]["capability_routes"] == data["capability_routes"]
