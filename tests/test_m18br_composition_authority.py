"""M18BR Composition Authority and Apply Closure regression tests."""

from pathlib import Path
from typing import Any

import pytest
from eea_application.domains import DomainExtensionRegistry, DomainExtensionService
from eea_backend.domain_repositories import (
    SqlAlchemyDomainActivationRepository,
    SqlAlchemyDomainCompositionStateRepository,
)
from eea_backend.models import Base
from eea_backend.repositories import SqlAlchemyProjectRepository
from eea_core.entities import Project
from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from test_m18b_domain_composition import _plugin


class FailingSqlAlchemyDomainActivationRepository(SqlAlchemyDomainActivationRepository):
    def __init__(self, session: Session, *, fail_on: int) -> None:
        super().__init__(session)
        self._fail_on = fail_on
        self._calls = 0

    def add(self, activation: Any, *, commit: bool = True) -> Any:
        self._calls += 1
        if self._calls == self._fail_on:
            raise RuntimeError("injected SQL activation persistence failure")
        return super().add(activation, commit=commit)


def _sql_environment(
    tmp_path: Path,
    plugins: list[object],
    *,
    activation_repository: SqlAlchemyDomainActivationRepository | None = None,
    migration_providers: dict[str, object] | None = None,
) -> tuple[Any, sessionmaker[Session], Session, Project, DomainExtensionService]:
    engine = create_engine(f"sqlite:///{(tmp_path / 'm18br.db').as_posix()}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    session = sessions()
    project_repository = SqlAlchemyProjectRepository(session)
    project = project_repository.add(Project(name="M18BR SQL project"))
    service = DomainExtensionService(
        DomainExtensionRegistry(plugins, migration_providers=migration_providers),
        activation_repository or SqlAlchemyDomainActivationRepository(session),
        project_repository,
        SqlAlchemyDomainCompositionStateRepository(session),
    )
    return engine, sessions, session, project, service


def test_m18br_public_apply_requires_revision_and_hash_tokens(client) -> None:
    project_id = client.post("/api/v1/projects", json={"name": "M18BR token API"}).json()["data"][
        "id"
    ]
    base = {"domain_ids": ["org.eea.motor_control"]}
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/domains/apply-composition", json=base
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/domains/apply-composition",
            json={**base, "expected_composition_revision": 1},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/domains/apply-composition",
            json={
                **base,
                "expected_composition_revision": 1,
                "expected_plan_hash": "0" * 63 + "G",
            },
        ).status_code
        == 422
    )


def test_m18br_public_apply_rejects_stale_revision_and_hash(client) -> None:
    project_id = client.post("/api/v1/projects", json={"name": "M18BR stale API"}).json()["data"][
        "id"
    ]
    preview = client.post(
        f"/api/v1/projects/{project_id}/domains/resolve-composition",
        json={"domain_ids": ["org.eea.motor_control"]},
    ).json()["data"]
    apply_url = f"/api/v1/projects/{project_id}/domains/apply-composition"
    payload = {
        "domain_ids": preview["active_domain_ids"],
        "selected_capabilities": preview["selected_capabilities"],
        "expected_composition_revision": preview["composition_revision"],
        "expected_plan_hash": preview["plan_hash"],
    }
    assert client.post(apply_url, json=payload).status_code == 200
    stale_revision = client.post(apply_url, json=payload)
    assert stale_revision.status_code == 409
    assert stale_revision.json()["error"]["code"] == "DOMAIN_COMPOSITION_CONFLICT"

    current = client.post(
        f"/api/v1/projects/{project_id}/domains/resolve-composition",
        json={"domain_ids": ["org.eea.motor_control"]},
    ).json()["data"]
    stale_hash = {
        "domain_ids": current["active_domain_ids"],
        "expected_composition_revision": current["composition_revision"],
        "expected_plan_hash": "0" * 64,
    }
    response = client.post(apply_url, json=stale_hash)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DOMAIN_COMPOSITION_CONFLICT"


@pytest.mark.parametrize("change", ["plugin", "rule", "generator", "schema"])
def test_m18br_runtime_rejects_persisted_state_drift(change: str) -> None:
    from test_m18b_domain_composition import _service

    original = _plugin(
        "domain",
        schema={"type": "object", "properties": {"value": {"type": "integer"}}},
    )
    service, project, activations, compositions = _service([original])
    preview = service.preview_composition(project.id, ["domain"])
    service.apply_composition(
        project.id,
        ["domain"],
        expected_composition_revision=preview.composition_revision,
        expected_plan_hash=preview.plan_hash,
    )
    stored_state = service.composition_state(project.id)
    if change == "plugin":
        changed = _plugin("domain", version="2.0.0")
    elif change == "rule":
        changed = _plugin("domain", rule_version="2")
    elif change == "generator":
        changed = _plugin("domain", generator_version="2")
    else:
        changed = _plugin(
            "domain",
            schema={"type": "object", "properties": {"changed": {"type": "boolean"}}},
        )
    restarted, _, _, _ = _service([changed], activations=activations, compositions=compositions)
    restarted._projects = service._projects
    with pytest.raises(EngineeringError) as error:
        restarted.current_composition(project.id)
    assert error.value.code is EngineeringErrorCode.DOMAIN_INCOMPATIBLE
    assert error.value.details["stored_plan_hash"] == stored_state.plan_hash
    assert error.value.details["stored_revision"] == stored_state.revision
    assert service.composition_state(project.id) == stored_state
    assert activations.get(project.id, "domain") is not None


def test_m18br_migration_provider_is_executable_and_fail_closed() -> None:
    from test_m18b_domain_composition import _service

    original = _plugin("domain", version="1.0.0", schema_version="1.0")
    service, project, activations, compositions = _service([original])
    preview = service.preview_composition(project.id, ["domain"])
    service.apply_composition(
        project.id,
        ["domain"],
        expected_composition_revision=preview.composition_revision,
        expected_plan_hash=preview.plan_hash,
    )
    state_before = service.composition_state(project.id)
    activations_before = dict(activations.items)

    def required(_: object) -> dict[str, object]:
        return {"status": "MIGRATION_REQUIRED", "applicable": True, "reason": "manual migration"}

    changed = _plugin(
        "domain",
        version="2.0.0",
        schema_version="2.0",
        migration_provider="domain.migrate",
    )
    migrated, _, _, _ = _service([changed], activations=activations, compositions=compositions)
    migrated.registry = DomainExtensionRegistry(
        [changed], migration_providers={"domain.migrate": required}
    )
    migrated._projects = service._projects
    migration_preview = migrated.preview_composition(project.id, ["domain"])
    assert migration_preview.compatibility_results[0]["status"] == "MIGRATION_REQUIRED"
    with pytest.raises(EngineeringError) as error:
        migrated.apply_composition(
            project.id,
            ["domain"],
            expected_composition_revision=migration_preview.composition_revision,
            expected_plan_hash=migration_preview.plan_hash,
        )
    assert error.value.code is EngineeringErrorCode.DOMAIN_INCOMPATIBLE
    assert migrated.composition_state(project.id) == state_before
    assert activations.items == activations_before

    blocked, _, _, _ = _service([changed], activations=activations, compositions=compositions)
    blocked._projects = service._projects
    assert (
        blocked.preview_composition(project.id, ["domain"]).compatibility_results[0]["reason"]
        == "MIGRATION_PROVIDER_NOT_REGISTERED"
    )

    rejecting = _plugin(
        "domain",
        version="2.0.0",
        schema_version="2.0",
        migration_provider="domain.reject",
    )

    def reject(_: object) -> dict[str, object]:
        raise RuntimeError("dry-run rejected")

    rejected, _, _, _ = _service([rejecting], activations=activations, compositions=compositions)
    rejected.registry = DomainExtensionRegistry(
        [rejecting], migration_providers={"domain.reject": reject}
    )
    rejected._projects = service._projects
    assert (
        rejected.preview_composition(project.id, ["domain"]).compatibility_results[0]["status"]
        == "BLOCKED"
    )


def test_m18br_migration_compatible_apply_and_empty_selection_semantics() -> None:
    from test_m18b_domain_composition import _service

    provider_a = _plugin("provider-a", capabilities=["transport"], priority=20)
    provider_b = _plugin("provider-b", capabilities=["transport"], priority=10)
    consumer = _plugin("consumer", required_capabilities=["transport"])
    service, project, activations, compositions = _service([provider_a, provider_b, consumer])
    selected = service.preview_composition(
        project.id,
        ["consumer", "provider-a", "provider-b"],
        selected_capabilities={"transport": "provider-b"},
    )
    service.apply_composition(
        project.id,
        selected.active_domain_ids,
        selected_capabilities={"transport": "provider-b"},
        expected_composition_revision=selected.composition_revision,
        expected_plan_hash=selected.plan_hash,
    )
    omitted = service.preview_composition(project.id, selected.active_domain_ids)
    defaulted = service.preview_composition(
        project.id, selected.active_domain_ids, selected_capabilities={}
    )
    assert omitted.capability_routes == {"transport": "provider-b"}
    assert defaulted.capability_routes == {"transport": "provider-a"}
    assert omitted.plan_hash != defaulted.plan_hash

    def compatible(_: object) -> dict[str, object]:
        return {"status": "COMPATIBLE", "applicable": True, "reason": "safe"}

    changed = _plugin(
        "consumer",
        required_capabilities=["transport"],
        version="2.0.0",
        migration_provider="consumer.migrate",
    )
    service2, _, _, _ = _service(
        [provider_a, provider_b, changed], activations=activations, compositions=compositions
    )
    service2._projects = service._projects
    service2.registry = DomainExtensionRegistry(
        [provider_a, provider_b, changed],
        migration_providers={"consumer.migrate": compatible},
    )
    upgrade = service2.preview_composition(project.id, selected.active_domain_ids)
    consumer_result = next(
        item for item in upgrade.compatibility_results if item.get("domain_id") == "consumer"
    )
    assert consumer_result["status"] == "COMPATIBLE"
    service2.apply_composition(
        project.id,
        selected.active_domain_ids,
        expected_composition_revision=upgrade.composition_revision,
        expected_plan_hash=upgrade.plan_hash,
    )


def test_m18br_real_sql_atomic_rollback(tmp_path: Path) -> None:
    plugins = [_plugin("a"), _plugin("b"), _plugin("c")]
    engine, sessions, session, project, _ = _sql_environment(tmp_path, plugins)
    session.close()
    failing_session = sessions()
    failing_repository = FailingSqlAlchemyDomainActivationRepository(failing_session, fail_on=2)
    project_repository = SqlAlchemyProjectRepository(failing_session)
    service = DomainExtensionService(
        DomainExtensionRegistry(plugins),
        failing_repository,
        project_repository,
        SqlAlchemyDomainCompositionStateRepository(failing_session),
    )
    state_before = service.composition_state(project.id)
    preview = service.preview_composition(project.id, ["a", "b", "c"])
    with pytest.raises(RuntimeError):
        service.apply_composition(
            project.id,
            ["a", "b", "c"],
            expected_composition_revision=preview.composition_revision,
            expected_plan_hash=preview.plan_hash,
        )
    failing_session.rollback()
    check_session = sessions()
    try:
        assert (
            SqlAlchemyDomainActivationRepository(check_session).list_for_project(project.id) == []
        )
        assert (
            SqlAlchemyDomainCompositionStateRepository(check_session).get(project.id)
            == state_before
        )
    finally:
        check_session.close()
        failing_session.close()
        engine.dispose()


def test_m18br_two_session_sql_cas_has_no_loser_residue(tmp_path: Path) -> None:
    plugin = _plugin(
        "domain", schema={"type": "object", "properties": {"value": {"type": "integer"}}}
    )
    engine, sessions, seed_session, project, seed = _sql_environment(tmp_path, [plugin])
    initial = seed.preview_composition(project.id, ["domain"])
    seed.apply_composition(
        project.id,
        ["domain"],
        expected_composition_revision=initial.composition_revision,
        expected_plan_hash=initial.plan_hash,
    )
    seed_session.close()

    session_a = sessions()
    session_b = sessions()
    try:

        def service_for(session: Session) -> DomainExtensionService:
            return DomainExtensionService(
                DomainExtensionRegistry([plugin]),
                SqlAlchemyDomainActivationRepository(session),
                SqlAlchemyProjectRepository(session),
                SqlAlchemyDomainCompositionStateRepository(session),
            )

        service_a = service_for(session_a)
        service_b = service_for(session_b)
        preview_a = service_a.preview_composition(
            project.id, ["domain"], configurations={"domain": {"value": 1}}
        )
        preview_b = service_b.preview_composition(
            project.id, ["domain"], configurations={"domain": {"value": 2}}
        )
        winner = service_a.apply_composition(
            project.id,
            ["domain"],
            configurations={"domain": {"value": 1}},
            expected_composition_revision=preview_a.composition_revision,
            expected_plan_hash=preview_a.plan_hash,
        )
        with pytest.raises(EngineeringError) as loser:
            service_b.apply_composition(
                project.id,
                ["domain"],
                configurations={"domain": {"value": 2}},
                expected_composition_revision=preview_b.composition_revision,
                expected_plan_hash=preview_b.plan_hash,
            )
        assert loser.value.code is EngineeringErrorCode.DOMAIN_COMPOSITION_CONFLICT
        session_b.rollback()
        check_session = sessions()
        try:
            state = SqlAlchemyDomainCompositionStateRepository(check_session).get(project.id)
            activation = SqlAlchemyDomainActivationRepository(check_session).get(
                project.id, "domain"
            )
            assert state is not None
            assert state.revision == winner.composition_revision
            assert state.plan_hash == winner.plan_hash
            assert activation is not None
            assert activation.configuration == {"value": 1}
        finally:
            check_session.close()
    finally:
        session_a.close()
        session_b.close()
        engine.dispose()
