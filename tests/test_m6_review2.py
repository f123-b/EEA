"""Review-2 regression coverage for M6 canonical and runtime boundaries."""

import asyncio
from typing import Any
from uuid import UUID

import pytest
from eea_adapters.ai.litellm import LiteLLMProvider
from eea_adapters.secrets import KeyringSecretService
from eea_application.requirements import (
    RequirementAnalysisService,
    RequirementProfileRegistry,
)
from eea_backend.claim_repositories import (
    SqlAlchemyClaimConflictRepository,
    SqlAlchemyClaimPredicateRepository,
    SqlAlchemyEngineeringClaimRepository,
)
from eea_backend.main import create_app
from eea_backend.repositories import SqlAlchemyEvidenceRepository
from eea_backend.requirement_repositories import (
    SqlAlchemyRequirementAnalysisRepository,
    SqlAlchemyRequirementProfileRepository,
    SqlAlchemyRequirementRepository,
    persist_requirement_analysis_bundle,
)
from eea_backend.settings import Settings
from eea_core.claims import EngineeringValue
from eea_core.enums import EngineeringDimension, EngineeringErrorCode, EvidenceType
from eea_core.errors import EngineeringError
from eea_core.requirements import RequirementAnalysisDraft, RequirementDraft
from eea_ports.ai import AIMessage, AIProviderRequest
from eea_ports.secrets import SecretReference, SecretValue
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


class _Keyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service_name: str, username: str) -> str | None:
        return self.values.get((service_name, username))

    def set_password(self, service_name: str, username: str, password: str) -> None:
        self.values[(service_name, username)] = password

    def delete_password(self, service_name: str, username: str) -> None:
        del self.values[(service_name, username)]


def _project(client: TestClient, name: str = "M6 review-2") -> UUID:
    response = client.post("/api/v1/projects", json={"name": name})
    assert response.status_code == 201
    return UUID(response.json()["data"]["id"])


def _value(unit: str, nominal: float) -> dict[str, object]:
    return EngineeringValue(
        unit=unit,
        dimension=EngineeringDimension.VOLTAGE,
        nominal=nominal,
    ).model_dump(mode="json")


def _analyze_voltage(client: TestClient, project_id: UUID, value: dict[str, object]):
    response = client.post(
        "/api/v1/requirements/analyze/structured",
        json={
            "project_id": str(project_id),
            "profile_name": "foc-benchmark",
            "profile_version": "1.0",
            "values": {"power.bus_voltage": value},
        },
    )
    assert response.status_code == 201
    return response.json()["data"]


def test_engineering_value_requirement_claim_roundtrips_as_canonical_engineering_value(
    client: TestClient,
) -> None:
    project_id = _project(client)
    first = _analyze_voltage(client, project_id, _value("V", 24))
    second = _analyze_voltage(client, project_id, _value("mV", 24_000))

    with Session(client.app.state.engine) as session:
        claims = SqlAlchemyEngineeringClaimRepository(session).list_for_subject_predicate(
            project_id=project_id,
            subject_ref=f"project:{project_id}",
            predicate="power.bus-voltage",
        )
        assert len(claims) == 2
        assert all(claim.value_schema_ref == "core://engineering-value/v1" for claim in claims)
        assert all(isinstance(claim.value, EngineeringValue) for claim in claims)
        assert claims[0].value.dimension is EngineeringDimension.VOLTAGE  # type: ignore[union-attr]
        assert claims[0].value.normalized_nominal == 24  # type: ignore[union-attr]
        assert claims[0].value.equivalent_to(claims[1].value)  # type: ignore[union-attr]

        for response_data in (first, second):
            analysis = SqlAlchemyRequirementAnalysisRepository(session).get(
                UUID(response_data["id"])
            )
            assert analysis is not None
            assert [item.id for item in analysis.claims] == analysis.claim_ids
            repository_claim = next(item for item in claims if item.id == analysis.claims[0].id)
            assert analysis.claims[0].model_dump(mode="json") == repository_claim.model_dump(
                mode="json"
            )


def test_requirement_claim_conflict_is_retained(client: TestClient) -> None:
    project_id = _project(client, "M6 conflict")
    first = _analyze_voltage(client, project_id, _value("V", 24))
    second = _analyze_voltage(client, project_id, _value("V", 48))

    with Session(client.app.state.engine) as session:
        claim_repository = SqlAlchemyEngineeringClaimRepository(session)
        claims = claim_repository.list_for_subject_predicate(
            project_id=project_id,
            subject_ref=f"project:{project_id}",
            predicate="power.bus-voltage",
        )
        assert len(claims) == 2
        assert {str(claim.id) for claim in claims} == {
            first["claim_ids"][0],
            second["claim_ids"][0],
        }
        conflicts = SqlAlchemyClaimConflictRepository(session).list_for_claim(claims[1].id)
        assert len(conflicts) == 1
        assert {conflicts[0].claim_a_id, conflicts[0].claim_b_id} == {
            claims[0].id,
            claims[1].id,
        }


def test_requirement_reanalysis_preserves_id_increments_revision_and_updates_semantics(
    client: TestClient,
) -> None:
    project_id = _project(client, "M6 reanalysis")
    with Session(client.app.state.engine) as session:
        profile = SqlAlchemyRequirementProfileRepository(session).get("foc-benchmark", "1.0")
        assert profile is not None
        service = RequirementAnalysisService(
            RequirementProfileRegistry(SqlAlchemyRequirementProfileRepository(session)),
            evidence_repository=SqlAlchemyEvidenceRepository(session),
        )
        first = service.complete_draft(
            project_id=project_id,
            profile_name=profile.profile_name,
            profile_version=profile.profile_version,
            draft=RequirementAnalysisDraft(
                profile_name=profile.profile_name,
                profile_version=profile.profile_version,
                requirements=[
                    RequirementDraft(
                        code="REQ-START",
                        title="Initial title",
                        statement="The device shall start.",
                    )
                ],
            ),
        )
        first_saved = persist_requirement_analysis_bundle(session, first)

        second = service.complete_draft(
            project_id=project_id,
            profile_name=profile.profile_name,
            profile_version=profile.profile_version,
            draft=RequirementAnalysisDraft(
                profile_name=profile.profile_name,
                profile_version=profile.profile_version,
                requirements=[
                    RequirementDraft(
                        code="REQ-START",
                        title="Updated title",
                        statement="The device shall start safely.",
                    )
                ],
            ),
        )
        second_saved = persist_requirement_analysis_bundle(session, second)
        requirement = SqlAlchemyRequirementRepository(session).get_by_code(project_id, "REQ-START")
        assert requirement is not None
        assert requirement.id == first_saved.requirement_ids[0] == second_saved.requirement_ids[0]
        assert requirement.revision == 2
        assert requirement.title == "Updated title"
        assert requirement.statement == "The device shall start safely."


def test_claim_predicate_contract_is_seeded_and_registered(client: TestClient) -> None:
    with Session(client.app.state.engine) as session:
        definition = SqlAlchemyClaimPredicateRepository(session).get("power.bus-voltage")
        assert definition is not None
        assert definition.value_schema_ref == "core://engineering-value/v1"
        assert definition.unit_dimension is EngineeringDimension.VOLTAGE


def test_client_cannot_forge_trusted_evidence_types(client: TestClient) -> None:
    project_id = _project(client, "M6 evidence")
    allowed = client.post(
        f"/api/v1/projects/{project_id}/evidence",
        json={
            "evidence_type": EvidenceType.DOCUMENT.value,
            "locator": {"filename": "requirements.pdf"},
            "summary": "Uploaded requirements document",
        },
    )
    assert allowed.status_code == 201
    evidence_id = allowed.json()["data"]["id"]
    fetched = client.get(f"/api/v1/projects/{project_id}/evidence/{evidence_id}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["project_id"] == str(project_id)

    for evidence_type in (EvidenceType.HARDWARE_TEST, EvidenceType.RULE, EvidenceType.TOOL):
        rejected = client.post(
            f"/api/v1/projects/{project_id}/evidence",
            json={
                "evidence_type": evidence_type.value,
            },
        )
        assert rejected.status_code == 422
        assert rejected.json()["error"]["code"] == EngineeringErrorCode.VALIDATION_ERROR.value


def test_model_alias_resolves_before_provider_call() -> None:
    backend = _Keyring()
    secrets = KeyringSecretService(backend=backend)
    reference = SecretReference("provider.review2")
    secrets.set(reference, SecretValue("sk-test"))
    captured: dict[str, Any] = {}

    async def completion(**kwargs: object) -> object:
        captured.update(kwargs)
        return {
            "model": "provider-concrete",
            "choices": [{"message": {"content": "{}"}}],
            "usage": {},
        }

    provider = LiteLLMProvider(
        secrets,
        reference,
        model_map={"requirements-default": "provider-concrete"},
        completion=completion,
    )
    asyncio.run(
        provider.generate(
            AIProviderRequest(
                model="requirements-default",
                messages=(AIMessage(role="user", content="{}"),),
                response_schema={"type": "object"},
                temperature=0,
                max_output_tokens=10,
                timeout_seconds=1,
            )
        )
    )
    assert captured["model"] == "provider-concrete"


def test_unconfigured_model_alias_fails_closed_before_secret_or_provider_call() -> None:
    called = False

    async def completion(**_: object) -> object:
        nonlocal called
        called = True
        return {}

    class FailingSecrets:
        def get(self, _: SecretReference) -> SecretValue:
            raise AssertionError("secret lookup must not happen for an unresolved alias")

    provider = LiteLLMProvider(
        FailingSecrets(),  # type: ignore[arg-type]
        SecretReference("provider.review2"),
        completion=completion,
    )
    with pytest.raises(EngineeringError) as captured:
        asyncio.run(
            provider.generate(
                AIProviderRequest(
                    model="missing-alias",
                    messages=(AIMessage(role="user", content="{}"),),
                    response_schema={"type": "object"},
                    temperature=0,
                    max_output_tokens=10,
                    timeout_seconds=1,
                )
            )
        )
    assert captured.value.code is EngineeringErrorCode.CAPABILITY_UNAVAILABLE
    assert called is False


def test_production_composition_builds_configured_litellm_provider(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        ai_provider_enabled=True,
        requirements_model="provider-concrete",
        ai_api_key_reference="provider.review2",
    )
    application = create_app(settings)
    try:
        assert isinstance(application.state.ai_provider, LiteLLMProvider)
    finally:
        application.state.engine.dispose()
