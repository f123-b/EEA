"""M14 Domain Extension Infrastructure acceptance tests."""

from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from eea_application.domains import DomainExtensionRegistry, DomainExtensionService
from eea_backend.main import create_app
from eea_backend.settings import Settings
from eea_core.domain_extensions import (
    DomainActivation,
    DomainDescriptor,
    DomainGeneratorContribution,
    DomainIREnvelope,
    DomainIRRef,
    DomainRuleContribution,
    DomainUIContribution,
)
from eea_core.entities import Project
from eea_core.enums import (
    DomainActivationStatus,
    DomainRulePhase,
    DomainTrustTier,
    EngineeringErrorCode,
)
from eea_core.errors import EngineeringError
from eea_core.repositories import DomainActivationRepository, ProjectRepository
from eea_core.schema_registry import create_core_schema_registry
from fastapi.testclient import TestClient


class FakeDomainPlugin:
    def __init__(
        self,
        descriptor: DomainDescriptor,
        *,
        rules: Sequence[DomainRuleContribution] = (),
        generators: Sequence[DomainGeneratorContribution] = (),
        ui_extensions: Sequence[DomainUIContribution] = (),
        schema: dict[str, object] | None = None,
    ) -> None:
        self.descriptor = descriptor
        self._rules = tuple(rules)
        self._generators = tuple(generators)
        self._ui_extensions = tuple(ui_extensions)
        self._schema = schema if schema is not None else {"type": "object"}

    def rules(self) -> Sequence[object]:
        return self._rules

    def generators(self) -> Sequence[object]:
        return self._generators

    def contexts(self) -> Sequence[object]:
        return ()

    def ui_extensions(self) -> Sequence[object]:
        return self._ui_extensions

    def schema(self) -> dict[str, object]:
        return self._schema

    def artifacts(self) -> Sequence[dict[str, object]]:
        return ({"kind": "metadata", "version": self.descriptor.version},)


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


class MemoryDomainActivationRepository(DomainActivationRepository):
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
                activation
                for (item_project_id, _), activation in self.items.items()
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


def _plugin_set() -> tuple[FakeDomainPlugin, ...]:
    base = FakeDomainPlugin(
        DomainDescriptor(
            id="org.test.base",
            plugin_id="org.test.base.plugin",
            name="Base Domain",
            version="1.0.0",
            api_version="1",
            capabilities=["transport"],
            priority=10,
        ),
        rules=(
            DomainRuleContribution(
                rule_id="base.rule",
                rule_version="1",
                phase=DomainRulePhase.PRE_DESIGN,
            ),
        ),
        generators=(DomainGeneratorContribution(generator_id="base.generator", version="1"),),
    )
    dependent = FakeDomainPlugin(
        DomainDescriptor(
            id="org.test.dependent",
            plugin_id="org.test.dependent.plugin",
            name="Dependent Domain",
            version="1.0.0",
            api_version="1",
            requires_domains=["org.test.base"],
            required_capabilities=["transport"],
        ),
        rules=(
            DomainRuleContribution(
                rule_id="dependent.rule",
                rule_version="1",
                phase=DomainRulePhase.RELEASE_GATE,
                safety_mode="ADDITIVE",
            ),
        ),
        generators=(
            DomainGeneratorContribution(
                generator_id="dependent.generator", version="1", after=["base.generator"]
            ),
        ),
        ui_extensions=(
            DomainUIContribution(
                extension_id="dependent.navigation",
                kind="navigation",
                label="Dependent",
                route="/projects/{project_id}/dependent",
            ),
        ),
        schema={"type": "object", "properties": {"enabled": {"type": "boolean"}}},
    )
    return base, dependent


def test_registry_resolves_dependencies_capabilities_and_order() -> None:
    registry = DomainExtensionRegistry(_plugin_set())
    plan = registry.resolve_composition(["org.test.dependent"])

    assert plan.active_domain_ids == ["org.test.base", "org.test.dependent"]
    assert plan.ordered_domain_ids == ["org.test.base", "org.test.dependent"]
    assert plan.capability_routes == {"transport": "org.test.base"}
    assert [item.rule_id for item in plan.rules] == ["base.rule", "dependent.rule"]
    assert [item.generator_id for item in plan.generators] == [
        "base.generator",
        "dependent.generator",
    ]


def test_registry_fails_closed_for_dependency_conflict_and_generator_cycle() -> None:
    registry = DomainExtensionRegistry(_plugin_set())
    with pytest.raises(EngineeringError) as missing:
        registry.resolve_composition(["org.test.missing"])
    assert missing.value.code is EngineeringErrorCode.DOMAIN_NOT_FOUND

    conflict = FakeDomainPlugin(
        DomainDescriptor(
            id="org.test.conflict",
            plugin_id="org.test.conflict.plugin",
            name="Conflict",
            version="1",
            api_version="1",
            conflicts_with=["org.test.base"],
        )
    )
    conflicting = DomainExtensionRegistry((*_plugin_set(), conflict))
    with pytest.raises(EngineeringError) as error:
        conflicting.resolve_composition(["org.test.base", "org.test.conflict"])
    assert error.value.code is EngineeringErrorCode.DOMAIN_COMPOSITION_CONFLICT

    cycle = FakeDomainPlugin(
        DomainDescriptor(
            id="org.test.cycle",
            plugin_id="org.test.cycle.plugin",
            name="Cycle",
            version="1",
            api_version="1",
        ),
        generators=(
            DomainGeneratorContribution(generator_id="cycle.a", version="1", before=["cycle.b"]),
            DomainGeneratorContribution(generator_id="cycle.b", version="1", before=["cycle.a"]),
        ),
    )
    with pytest.raises(EngineeringError) as cycle_error:
        DomainExtensionRegistry((cycle,)).resolve_composition(["org.test.cycle"])
    assert cycle_error.value.code is EngineeringErrorCode.DOMAIN_COMPOSITION_CONFLICT


def test_registry_rejects_remote_ui_metadata() -> None:
    with pytest.raises(ValueError):
        DomainUIContribution(
            extension_id="remote",
            kind="navigation",
            label="Remote",
            route="https://untrusted.example/extension",
        )


@pytest.mark.parametrize(
    "trust_tier",
    [DomainTrustTier.SIGNED_TRUSTED, DomainTrustTier.COMMUNITY_UNTRUSTED],
)
def test_registry_fails_closed_for_non_bundled_plugins(trust_tier: DomainTrustTier) -> None:
    plugin = FakeDomainPlugin(
        DomainDescriptor(
            id="org.test.non_bundled",
            plugin_id="org.test.non_bundled.plugin",
            name="Non-bundled",
            version="1",
            api_version="1",
            trust_tier=trust_tier,
        )
    )
    with pytest.raises(EngineeringError) as error:
        DomainExtensionRegistry((plugin,))
    assert error.value.code is EngineeringErrorCode.CAPABILITY_UNAVAILABLE


def test_domain_ir_is_opaque_and_registered_in_core_schema_registry() -> None:
    project_id = UUID("00000000-0000-0000-0000-000000000001")
    envelope = DomainIREnvelope(
        project_id=project_id,
        domain_id="org.test.domain",
        plugin_id="org.test.plugin",
        domain_schema_version="1",
        payload={"plugin_owned": {"key": "value"}},
        refs=[
            DomainIRRef(
                domain_id="org.test.domain",
                entity_type="OpaqueEntity",
                entity_id=UUID("00000000-0000-0000-0000-000000000002"),
                schema_version="1",
            )
        ],
    )
    assert envelope.payload["plugin_owned"] == {"key": "value"}
    assert create_core_schema_registry().get("DomainIREnvelope") is not None


def test_empty_domain_composition_and_project_activation_are_safe() -> None:
    projects = MemoryProjectRepository()
    activations = MemoryDomainActivationRepository()
    project = projects.add(Project(name="plain MCU"))
    service = DomainExtensionService(DomainExtensionRegistry(), activations, projects)
    assert service.resolve(project.id).ordered_domain_ids == []
    assert service.available(project.id) == []

    registry = DomainExtensionRegistry(_plugin_set())
    service = DomainExtensionService(registry, activations, projects)
    dependent = service.activate(project.id, "org.test.dependent", activated_by="test")
    assert dependent.status is DomainActivationStatus.ACTIVE
    assert [item.domain_id for item in service.list_activations(project.id)] == [
        "org.test.base",
        "org.test.dependent",
    ]
    with pytest.raises(EngineeringError) as blocked:
        service.deactivate(project.id, "org.test.base")
    assert blocked.value.code is EngineeringErrorCode.DOMAIN_DEPENDENCY_MISSING
    assert (
        service.deactivate(project.id, "org.test.dependent").status
        is DomainActivationStatus.DISABLED
    )


def test_reactivate_preserves_configuration_when_omitted() -> None:
    projects = MemoryProjectRepository()
    activations = MemoryDomainActivationRepository()
    project = projects.add(Project(name="configuration lifecycle"))
    service = DomainExtensionService(DomainExtensionRegistry(_plugin_set()), activations, projects)

    first = service.activate(
        project.id, "org.test.dependent", configuration={"enabled": True}, activated_by="test"
    )
    disabled = service.deactivate(project.id, "org.test.dependent")
    assert disabled.configuration == {"enabled": True}
    assert disabled.revision == first.revision + 1
    reactivated = service.activate(project.id, "org.test.dependent", activated_by="test")

    assert reactivated.configuration == {"enabled": True}
    assert reactivated.revision == first.revision + 2
    assert reactivated.configuration_schema_version == "1.0"
    assert reactivated.configuration_schema_hash is not None
    assert len(reactivated.configuration_schema_hash) == 64


def test_active_reactivation_applies_new_configuration_and_increments_revision() -> None:
    projects = MemoryProjectRepository()
    activations = MemoryDomainActivationRepository()
    project = projects.add(Project(name="active reactivation"))
    service = DomainExtensionService(DomainExtensionRegistry(_plugin_set()), activations, projects)

    first = service.activate(
        project.id, "org.test.dependent", configuration={"enabled": True}, activated_by="test"
    )
    updated = service.activate(
        project.id, "org.test.dependent", configuration={"enabled": False}, activated_by="test"
    )
    omitted = service.activate(project.id, "org.test.dependent", activated_by="test")

    assert updated.configuration == {"enabled": False}
    assert updated.revision == first.revision + 1
    assert omitted.configuration == updated.configuration
    assert omitted.revision == updated.revision


def test_explicit_empty_configuration_is_validated_and_rejected_without_writes() -> None:
    projects = MemoryProjectRepository()
    activations = MemoryDomainActivationRepository()
    project = projects.add(Project(name="required configuration"))
    plugin = FakeDomainPlugin(
        DomainDescriptor(
            id="org.test.required-config",
            plugin_id="org.test.required-config.plugin",
            name="Required configuration",
            version="1.0.0",
            api_version="1",
        ),
        schema={
            "type": "object",
            "properties": {"enabled": {"type": "boolean"}},
            "required": ["enabled"],
            "additionalProperties": False,
        },
    )
    service = DomainExtensionService(DomainExtensionRegistry((plugin,)), activations, projects)

    with pytest.raises(EngineeringError) as error:
        service.activate(project.id, plugin.descriptor.domain_id, configuration={})
    assert error.value.code is EngineeringErrorCode.DOMAIN_CONFIGURATION_INVALID
    assert activations.items == {}


def test_configuration_validation_rejects_invalid_values_and_preserves_existing_state() -> None:
    projects = MemoryProjectRepository()
    activations = MemoryDomainActivationRepository()
    project = projects.add(Project(name="invalid configuration"))
    service = DomainExtensionService(DomainExtensionRegistry(_plugin_set()), activations, projects)
    existing = service.activate(
        project.id, "org.test.dependent", configuration={"enabled": True}, activated_by="test"
    )

    with pytest.raises(EngineeringError) as error:
        service.activate(
            project.id,
            "org.test.dependent",
            configuration={"enabled": "yes"},  # type: ignore[dict-item]
        )
    assert error.value.code is EngineeringErrorCode.DOMAIN_CONFIGURATION_INVALID
    current = service.state(project.id, "org.test.dependent")
    assert current.configuration == existing.configuration
    assert current.revision == existing.revision


def test_invalid_plugin_schema_fails_closed() -> None:
    plugin = FakeDomainPlugin(
        DomainDescriptor(
            id="org.test.invalid-schema",
            plugin_id="org.test.invalid-schema.plugin",
            name="Invalid schema",
            version="1.0.0",
            api_version="1",
        ),
        schema={"type": "object", "x-unsupported-validation": True},
    )
    with pytest.raises(EngineeringError) as error:
        DomainExtensionRegistry((plugin,))
    assert error.value.code is EngineeringErrorCode.DOMAIN_CONFIGURATION_INVALID


def test_empty_domain_list_api_and_domain_contract_routes(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    command.upgrade(config, "head")
    registry = DomainExtensionRegistry(_plugin_set())
    with TestClient(create_app(settings, domain_registry=registry)) as client:
        project = client.post("/api/v1/projects", json={"name": "M14 project"}).json()["data"]
        project_id = project["id"]
        available = client.get(f"/api/v1/projects/{project_id}/domains/available")
        assert available.status_code == 200
        assert len(available.json()["data"]["items"]) == 2

        activated = client.post(
            f"/api/v1/projects/{project_id}/domains/org.test.dependent/activate",
            json={"activated_by": "test"},
        )
        assert activated.status_code == 201
        assert activated.json()["data"]["domain_id"] == "org.test.dependent"
        assert len(activated.json()["data"]["configuration_schema_hash"]) == 64

        invalid_configuration = client.post(
            f"/api/v1/projects/{project_id}/domains/org.test.dependent/activate",
            json={"configuration": {"enabled": "yes"}},
        )
        assert invalid_configuration.status_code == 422
        assert (
            invalid_configuration.json()["error"]["code"]
            == EngineeringErrorCode.DOMAIN_CONFIGURATION_INVALID.value
        )

        states = client.get(f"/api/v1/projects/{project_id}/domains")
        assert [item["domain_id"] for item in states.json()["data"]["items"]] == [
            "org.test.base",
            "org.test.dependent",
        ]
        schema = client.get(f"/api/v1/projects/{project_id}/domains/org.test.dependent/schema")
        assert schema.json()["data"]["json_schema"]["type"] == "object"
        extensions = client.get(f"/api/v1/projects/{project_id}/ui/extensions")
        assert extensions.json()["data"]["items"][0]["route"].startswith("/projects/")

    empty_settings = Settings(data_dir=tmp_path / "empty")
    empty_settings.data_dir.mkdir(parents=True, exist_ok=True)
    empty_config = Config("alembic.ini")
    empty_config.set_main_option("sqlalchemy.url", empty_settings.database_url.replace("%", "%%"))
    command.upgrade(empty_config, "head")
    with TestClient(create_app(empty_settings)) as empty_client:
        plain_project = empty_client.post(
            "/api/v1/projects", json={"name": "plain MCU without a Domain"}
        )
        assert plain_project.status_code == 201
        plain_project_id = plain_project.json()["data"]["id"]
        assert (
            empty_client.get(f"/api/v1/projects/{plain_project_id}/domains").json()["data"]["items"]
            == []
        )
