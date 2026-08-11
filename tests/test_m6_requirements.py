"""M6 Requirement DSL acceptance tests."""

import asyncio
import json
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from eea_application.requirements import (
    RequirementAnalysisService,
    RequirementProfileRegistry,
    build_foc_benchmark_profile,
    build_requirement_analysis_prompt_definition,
    ensure_requirement_prompt_registered,
)
from eea_backend.claim_repositories import SqlAlchemyEngineeringClaimRepository
from eea_backend.database import create_database_engine
from eea_backend.main import create_app
from eea_backend.models import AIUsageRecordModel
from eea_backend.repositories import SqlAlchemyProjectRepository
from eea_backend.requirement_repositories import (
    SqlAlchemyRequirementAnalysisRepository,
    SqlAlchemyRequirementProfileRepository,
    SqlAlchemyRequirementRepository,
    persist_requirement_analysis_bundle,
)
from eea_backend.settings import Settings
from eea_core.claims import EngineeringValue
from eea_core.entities import Evidence, Project
from eea_core.enums import (
    EngineeringDimension,
    EngineeringErrorCode,
    EvidenceType,
    RequirementFieldStatus,
    RequirementStatus,
)
from eea_core.errors import EngineeringError
from eea_core.requirements import (
    RequirementAnalysisDraft,
    RequirementDraft,
    RequirementFieldObservation,
)
from eea_ports.ai import AIProviderResponse, ProviderUsage
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


class MemoryProfileRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], object] = {}

    def add(self, profile: object) -> object:
        key = (profile.profile_name, profile.profile_version)  # type: ignore[attr-defined]
        if key in self.items:
            raise ValueError("duplicate profile")
        self.items[key] = profile
        return profile

    def get(self, profile_name: str, profile_version: str | None = None) -> object | None:
        if profile_version is not None:
            return self.items.get((profile_name, profile_version))
        return next(
            (profile for (name, _), profile in self.items.items() if name == profile_name),
            None,
        )


class MemoryEvidenceRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Evidence] = {}

    def add(self, evidence: Evidence) -> Evidence:
        self.items[evidence.id] = evidence
        return evidence

    def get(self, evidence_id: UUID) -> Evidence | None:
        return self.items.get(evidence_id)


class MemoryPromptRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], object] = {}

    def add(self, definition: object) -> object:
        key = (definition.name, definition.prompt_version)  # type: ignore[attr-defined]
        if key in self.items:
            raise ValueError("duplicate prompt")
        self.items[key] = definition
        return definition

    def get(self, name: str, version: str | None = None) -> object | None:
        if version is None:
            return next(
                (item for (item_name, _), item in self.items.items() if item_name == name),
                None,
            )
        return self.items.get((name, version))


class FakeStructuredGeneration:
    def __init__(self, draft: RequirementAnalysisDraft) -> None:
        self.draft = draft
        self.calls: list[dict[str, object]] = []

    async def generate(self, **kwargs: object) -> RequirementAnalysisDraft:
        self.calls.append(kwargs)
        return self.draft


class FakeProvider:
    name = "m6-test-provider"

    async def generate(self, request: object) -> AIProviderResponse:
        del request
        return AIProviderResponse(
            content=json.dumps(
                {
                    "profile_name": "foc-benchmark",
                    "profile_version": "1.0",
                    "requirements": [
                        {
                            "code": "REQ-START",
                            "title": "Startup requirement",
                            "statement": "The device shall start safely.",
                        }
                    ],
                    "field_observations": [],
                    "claims": [],
                    "issues": [],
                    "follow_up_questions": [],
                }
            ),
            model="m6-test-model",
            usage=ProviderUsage(input_tokens=1, output_tokens=1, total_tokens=2),
        )


def make_service() -> tuple[RequirementAnalysisService, MemoryEvidenceRepository]:
    repository = MemoryProfileRepository()
    repository.add(build_foc_benchmark_profile())
    evidence_repository = MemoryEvidenceRepository()
    registry = RequirementProfileRegistry(repository)  # type: ignore[arg-type]
    return (
        RequirementAnalysisService(registry, evidence_repository=evidence_repository),
        evidence_repository,
    )


def valid_values() -> dict[str, object]:
    return {
        "target.device": "STM32G431",
        "target.package": "UFQFPN48",
        "power.bus_voltage": EngineeringValue(
            unit="V", dimension=EngineeringDimension.VOLTAGE, nominal=24
        ).model_dump(mode="json"),
        "power.phase_current": EngineeringValue(
            unit="A", dimension=EngineeringDimension.CURRENT, nominal=10
        ).model_dump(mode="json"),
        "control.loop_frequency": EngineeringValue(
            unit="kHz", dimension=EngineeringDimension.FREQUENCY, nominal=20
        ).model_dump(mode="json"),
        "feedback.position_interface": "ABZ",
        "pwm.phase_count": 3,
        "pwm.complementary": True,
        "pwm.deadtime": EngineeringValue(
            unit="ns", dimension=EngineeringDimension.TIME, nominal=500
        ).model_dump(mode="json"),
        "current_sense.method": "SHUNT_LOW_SIDE",
        "current_sense.range": EngineeringValue(
            unit="A", dimension=EngineeringDimension.CURRENT, nominal=20
        ).model_dump(mode="json"),
        "communication.protocol": "CAN",
        "safety.emergency_disable": True,
    }


def evidence_for(
    repository: MemoryEvidenceRepository, project_id: UUID, values: dict[str, object]
) -> dict[str, UUID]:
    refs: dict[str, UUID] = {}
    for key in values:
        evidence = repository.add(
            Evidence(
                project_id=project_id,
                evidence_type=EvidenceType.DOCUMENT,
                locator={"test": key},
            )
        )
        refs[key] = evidence.id
    for key in ("device_source", "power_source", "control_timing_source", "safety_source"):
        evidence = repository.add(
            Evidence(
                project_id=project_id,
                evidence_type=EvidenceType.DOCUMENT,
                locator={"test": key},
            )
        )
        refs[key] = evidence.id
    return refs


def test_foc_profile_is_generic_and_full_structured_input_is_complete() -> None:
    service, evidence_repository = make_service()
    values = valid_values()
    project_id = UUID(int=1)
    analysis = service.analyze_structured(
        project_id=project_id,
        profile_name="foc-benchmark",
        profile_version="1.0",
        values=values,
        evidence_refs=evidence_for(evidence_repository, project_id, values),
    )

    assert analysis.completeness.status is RequirementStatus.COMPLETE
    assert analysis.completeness.score == 1
    assert len(analysis.claims) == len(values)
    assert all("motor_control" not in type(item).__module__ for item in analysis.claims)


def test_missing_foc_fields_are_incomplete_and_generate_questions() -> None:
    service, _ = make_service()
    analysis = service.analyze_structured(
        project_id=UUID(int=2),
        profile_name="foc-benchmark",
        profile_version="1.0",
        values={"target.device": "STM32G431"},
    )

    assert analysis.completeness.status is RequirementStatus.INCOMPLETE
    assert "power.bus_voltage" in analysis.completeness.missing_field_keys
    assert analysis.follow_up_questions
    assert analysis.issues
    assert all(issue.project_id == UUID(int=2) for issue in analysis.issues)


def test_ambiguous_field_is_not_treated_as_complete() -> None:
    service, _ = make_service()
    profile = build_foc_benchmark_profile()
    draft = RequirementAnalysisDraft(
        profile_name=profile.profile_name,
        profile_version=profile.profile_version,
        field_observations=[
            RequirementFieldObservation(
                field_key="target.device",
                status=RequirementFieldStatus.AMBIGUOUS,
                ambiguity_reason="Two package variants were mentioned.",
            )
        ],
    )
    analysis = service.complete_draft(
        project_id=UUID(int=3),
        profile_name=profile.profile_name,
        profile_version=profile.profile_version,
        draft=draft,
    )
    assert analysis.completeness.status is RequirementStatus.INCOMPLETE
    assert "target.device" in analysis.completeness.ambiguous_field_keys


def test_unknown_profile_version_is_rejected() -> None:
    service, _ = make_service()
    with pytest.raises(EngineeringError) as captured:
        service.analyze_structured(
            project_id=UUID(int=4),
            profile_name="foc-benchmark",
            profile_version="9.9",
            values={},
        )
    assert captured.value.code is EngineeringErrorCode.SCHEMA_VERSION_UNSUPPORTED


def test_unknown_field_and_wrong_engineering_dimension_are_rejected() -> None:
    service, _ = make_service()
    with pytest.raises(EngineeringError) as unknown:
        service.analyze_structured(
            project_id=UUID(int=5),
            profile_name="foc-benchmark",
            profile_version="1.0",
            values={"unknown.field": True},
        )
    assert unknown.value.code is EngineeringErrorCode.INVALID_REQUIREMENT

    values = {
        "power.bus_voltage": EngineeringValue(
            unit="A", dimension=EngineeringDimension.CURRENT, nominal=1
        ).model_dump(mode="json")
    }
    with pytest.raises(EngineeringError) as invalid:
        service.analyze_structured(
            project_id=UUID(int=6),
            profile_name="foc-benchmark",
            profile_version="1.0",
            values=values,
        )
    assert invalid.value.code is EngineeringErrorCode.INVALID_REQUIREMENT


def test_random_uuid_is_not_valid_evidence() -> None:
    service, _ = make_service()
    with pytest.raises(EngineeringError) as captured:
        service.analyze_structured(
            project_id=UUID(int=10),
            profile_name="foc-benchmark",
            profile_version="1.0",
            values={},
            evidence_refs={"device_source": uuid4()},
        )
    assert captured.value.code is EngineeringErrorCode.INVALID_REQUIREMENT


def test_missing_evidence_record_does_not_complete_requirement() -> None:
    service, _ = make_service()
    analysis = service.analyze_structured(
        project_id=UUID(int=11),
        profile_name="foc-benchmark",
        profile_version="1.0",
        values=valid_values(),
    )
    assert analysis.completeness.status is RequirementStatus.INCOMPLETE
    assert analysis.completeness.missing_evidence_keys


def test_cross_project_evidence_is_rejected() -> None:
    service, evidence_repository = make_service()
    foreign = evidence_repository.add(
        Evidence(
            project_id=UUID(int=99),
            evidence_type=EvidenceType.DOCUMENT,
            locator={"test": "foreign"},
        )
    )
    with pytest.raises(EngineeringError) as captured:
        service.analyze_structured(
            project_id=UUID(int=12),
            profile_name="foc-benchmark",
            profile_version="1.0",
            values={},
            evidence_refs={"device_source": foreign.id},
        )
    assert captured.value.code is EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED


def test_global_evidence_is_allowed() -> None:
    service, evidence_repository = make_service()
    public = evidence_repository.add(
        Evidence(
            evidence_type=EvidenceType.DEVICE_DB,
            locator={"test": "global"},
        )
    )
    analysis = service.analyze_structured(
        project_id=UUID(int=13),
        profile_name="foc-benchmark",
        profile_version="1.0",
        values={},
        evidence_refs={"device_source": public.id},
    )
    assert "device_source" not in analysis.completeness.missing_evidence_keys


def test_wrong_evidence_type_is_rejected() -> None:
    service, evidence_repository = make_service()
    wrong = evidence_repository.add(
        Evidence(
            project_id=UUID(int=14),
            evidence_type=EvidenceType.REPOSITORY,
            locator={"test": "wrong"},
        )
    )
    with pytest.raises(EngineeringError) as captured:
        service.analyze_structured(
            project_id=UUID(int=14),
            profile_name="foc-benchmark",
            profile_version="1.0",
            values={},
            evidence_refs={"device_source": wrong.id},
        )
    assert captured.value.code is EngineeringErrorCode.INVALID_REQUIREMENT


def test_allowed_evidence_type_is_accepted() -> None:
    service, evidence_repository = make_service()
    allowed = evidence_repository.add(
        Evidence(
            project_id=UUID(int=15),
            evidence_type=EvidenceType.DEVICE_DB,
            locator={"test": "allowed"},
        )
    )
    analysis = service.analyze_structured(
        project_id=UUID(int=15),
        profile_name="foc-benchmark",
        profile_version="1.0",
        values={},
        evidence_refs={"device_source": allowed.id},
    )
    assert analysis.completeness.status is RequirementStatus.INCOMPLETE


def test_field_evidence_type_contract_is_enforced() -> None:
    service, evidence_repository = make_service()
    wrong = evidence_repository.add(
        Evidence(
            project_id=UUID(int=16),
            evidence_type=EvidenceType.REPOSITORY,
            locator={"test": "field-wrong"},
        )
    )
    with pytest.raises(EngineeringError) as captured:
        service.analyze_structured(
            project_id=UUID(int=16),
            profile_name="foc-benchmark",
            profile_version="1.0",
            values={"power.bus_voltage": valid_values()["power.bus_voltage"]},
            evidence_refs={"power.bus_voltage": wrong.id},
        )
    assert captured.value.code is EngineeringErrorCode.INVALID_REQUIREMENT


def test_empty_required_text_is_rejected() -> None:
    service, _ = make_service()
    with pytest.raises(EngineeringError):
        service.analyze_structured(
            project_id=UUID(int=17),
            profile_name="foc-benchmark",
            profile_version="1.0",
            values={"target.device": ""},
        )


def test_whitespace_required_text_is_rejected() -> None:
    service, _ = make_service()
    with pytest.raises(EngineeringError):
        service.analyze_structured(
            project_id=UUID(int=18),
            profile_name="foc-benchmark",
            profile_version="1.0",
            values={"target.device": "   "},
        )


@pytest.mark.parametrize("phase_count", [0, 3.5])
def test_foc_phase_count_invalid_values_are_rejected(phase_count: float) -> None:
    service, _ = make_service()
    with pytest.raises(EngineeringError):
        service.analyze_structured(
            project_id=UUID(int=19),
            profile_name="foc-benchmark",
            profile_version="1.0",
            values={"pwm.phase_count": phase_count},
        )


def test_foc_phase_count_three_is_valid() -> None:
    service, _ = make_service()
    analysis = service.analyze_structured(
        project_id=UUID(int=20),
        profile_name="foc-benchmark",
        profile_version="1.0",
        values={"pwm.phase_count": 3},
    )
    assert analysis.field_observations[0].status is RequirementFieldStatus.PRESENT


def test_requirement_draft_cannot_supply_server_identity() -> None:
    profile = build_foc_benchmark_profile()
    with pytest.raises(ValueError):
        RequirementAnalysisDraft.model_validate(
            {
                "profile_name": profile.profile_name,
                "profile_version": profile.profile_version,
                "requirements": [
                    {
                        "id": str(uuid4()),
                        "code": "REQ-1",
                        "title": "A requirement",
                        "statement": "The device shall start.",
                    }
                ],
            }
        )
    assert "id" not in RequirementDraft.model_json_schema()["properties"]


def test_requirement_identity_is_created_server_side() -> None:
    service, _ = make_service()
    analysis = service.complete_draft(
        project_id=UUID(int=21),
        profile_name="foc-benchmark",
        profile_version="1.0",
        draft=RequirementAnalysisDraft(
            profile_name="foc-benchmark",
            profile_version="1.0",
            requirements=[
                RequirementDraft(
                    code="REQ-1",
                    title="A requirement",
                    statement="The device shall start.",
                )
            ],
        ),
    )
    assert analysis.requirements[0].project_id == UUID(int=21)
    assert analysis.requirements[0].status is RequirementStatus.INCOMPLETE


def test_natural_language_service_only_uses_structured_generation() -> None:
    repository = MemoryProfileRepository()
    profile = build_foc_benchmark_profile()
    repository.add(profile)
    draft = RequirementAnalysisDraft(
        profile_name=profile.profile_name,
        profile_version=profile.profile_version,
    )
    generator = FakeStructuredGeneration(draft)
    evidence_repository = MemoryEvidenceRepository()
    service = RequirementAnalysisService(
        RequirementProfileRegistry(repository),  # type: ignore[arg-type]
        generator,  # type: ignore[arg-type]
        evidence_repository,
    )
    analysis = asyncio.run(
        service.analyze_natural_language(
            project_id=UUID(int=7),
            profile_name=profile.profile_name,
            profile_version=profile.profile_version,
            source_text="Build a controller.",
        )
    )

    assert analysis.completeness.status is RequirementStatus.INCOMPLETE
    assert generator.calls[0]["prompt_name"] == "requirements.analyze"
    assert generator.calls[0]["output_model"] is RequirementAnalysisDraft


def test_requirement_prompt_schema_is_versioned_and_shell_free() -> None:
    prompt = build_requirement_analysis_prompt_definition()
    assert prompt.name == "requirements.analyze"  # type: ignore[attr-defined]
    assert prompt.allowed_tools == []  # type: ignore[attr-defined]
    assert prompt.output_schema == RequirementAnalysisDraft.model_json_schema()  # type: ignore[attr-defined]


def test_requirement_profile_and_structured_analysis_api(client: TestClient) -> None:
    project_response = client.post("/api/v1/projects", json={"name": "M6"})
    assert project_response.status_code == 201
    project_id = project_response.json()["data"]["id"]

    profile_response = client.get("/api/v1/requirement-profiles/foc-benchmark/1.0")
    assert profile_response.status_code == 200
    assert profile_response.json()["data"]["profile_name"] == "foc-benchmark"

    response = client.post(
        "/api/v1/requirements/analyze/structured",
        json={
            "project_id": project_id,
            "profile_name": "foc-benchmark",
            "profile_version": "1.0",
            "values": {"target.device": "STM32G431"},
        },
    )
    assert response.status_code == 201
    assert response.json()["data"]["completeness"]["status"] == "INCOMPLETE"
    response_data = response.json()["data"]
    assert len(response_data["claim_ids"]) == 1
    with Session(client.app.state.engine) as session:
        analysis = SqlAlchemyRequirementAnalysisRepository(session).get(UUID(response_data["id"]))
        assert analysis is not None
        assert analysis.claim_ids == [UUID(response_data["claim_ids"][0])]
        canonical_claims = SqlAlchemyEngineeringClaimRepository(session).list_for_subject_predicate(
            project_id=UUID(project_id),
            subject_ref=f"project:{project_id}",
            predicate="target.device",
        )
        assert [item.id for item in canonical_claims] == analysis.claim_ids


def test_natural_language_api_uses_structured_generation(settings: Settings) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    command.upgrade(config, "head")
    with TestClient(create_app(settings, ai_provider=FakeProvider())) as test_client:
        project_response = test_client.post("/api/v1/projects", json={"name": "M6 natural"})
        project_id = project_response.json()["data"]["id"]
        response = test_client.post(
            "/api/v1/requirements/analyze/natural-language",
            json={
                "project_id": project_id,
                "profile_name": "foc-benchmark",
                "profile_version": "1.0",
                "source_text": "The device shall start safely.",
            },
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert len(data["requirement_ids"]) == 1
        assert data["requirements"][0]["id"] == data["requirement_ids"][0]
    engine = create_database_engine(settings)
    try:
        with Session(engine) as session:
            usage = list(
                session.scalars(
                    select(AIUsageRecordModel).where(AIUsageRecordModel.project_id == project_id)
                )
            )
            assert len(usage) == 1
            assert usage[0].succeeded is True
    finally:
        engine.dispose()


def test_natural_language_api_rejects_empty_source(client: TestClient) -> None:
    project_id = client.post("/api/v1/projects", json={"name": "M6 empty"}).json()["data"]["id"]
    response = client.post(
        "/api/v1/requirements/analyze/natural-language",
        json={
            "project_id": project_id,
            "profile_name": "foc-benchmark",
            "profile_version": "1.0",
            "source_text": "   ",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUIREMENT"


def test_natural_language_api_returns_capability_unavailable_without_provider(
    client: TestClient,
) -> None:
    project_id = client.post("/api/v1/projects", json={"name": "M6 no provider"}).json()["data"][
        "id"
    ]
    response = client.post(
        "/api/v1/requirements/analyze/natural-language",
        json={
            "project_id": project_id,
            "profile_name": "foc-benchmark",
            "profile_version": "1.0",
            "source_text": "The device shall start.",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CAPABILITY_UNAVAILABLE"


def test_requirement_prompt_is_seeded_once_and_contract_mismatch_rejected() -> None:
    repository = MemoryPromptRepository()
    first = ensure_requirement_prompt_registered(repository)  # type: ignore[arg-type]
    second = ensure_requirement_prompt_registered(repository)  # type: ignore[arg-type]
    assert first == second
    assert len(repository.items) == 1
    repository.items[(first.name, first.prompt_version)] = first.model_copy(  # type: ignore[attr-defined]
        update={"output_schema": {"broken": True}}
    )
    with pytest.raises(EngineeringError) as captured:
        ensure_requirement_prompt_registered(repository)  # type: ignore[arg-type]
    assert captured.value.code is EngineeringErrorCode.SCHEMA_VERSION_UNSUPPORTED


def test_requirement_profile_and_analysis_sql_roundtrip(settings: Settings) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    command.upgrade(config, "head")
    engine = create_database_engine(settings)
    project_id = UUID(int=8)
    try:
        with Session(engine) as session:
            SqlAlchemyProjectRepository(session).add(Project(id=project_id, name="M6 persistence"))
            profiles = SqlAlchemyRequirementProfileRepository(session)
            profile = profiles.add(build_foc_benchmark_profile())
            assert profiles.get(profile.profile_name, profile.profile_version) == profile
            evidence_repository = MemoryEvidenceRepository()
            analysis = RequirementAnalysisService(
                RequirementProfileRegistry(profiles),
                evidence_repository=evidence_repository,
            ).analyze_structured(
                project_id=project_id,
                profile_name=profile.profile_name,
                profile_version=profile.profile_version,
                values={"target.device": "STM32G431"},
            )
            analyses = SqlAlchemyRequirementAnalysisRepository(session)
            saved = analyses.add(analysis)
            loaded = analyses.get(saved.id)
            assert loaded is not None
            assert loaded.completeness.status is RequirementStatus.INCOMPLETE
            assert loaded.issues[0].project_id == project_id
    finally:
        engine.dispose()


def test_analysis_bundle_rolls_back_atomically_on_failure(settings: Settings) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    command.upgrade(config, "head")
    engine = create_database_engine(settings)
    project_id = UUID(int=22)
    try:
        with Session(engine) as session:
            SqlAlchemyProjectRepository(session).add(Project(id=project_id, name="M6 rollback"))
            profiles = SqlAlchemyRequirementProfileRepository(session)
            profile = profiles.add(build_foc_benchmark_profile())
            service = RequirementAnalysisService(
                RequirementProfileRegistry(profiles),
                evidence_repository=MemoryEvidenceRepository(),
            )
            analysis = service.complete_draft(
                project_id=project_id,
                profile_name=profile.profile_name,
                profile_version=profile.profile_version,
                draft=RequirementAnalysisDraft(
                    profile_name=profile.profile_name,
                    profile_version=profile.profile_version,
                    requirements=[
                        RequirementDraft(
                            code="REQ-DUP",
                            title="First",
                            statement="The first requirement.",
                        ),
                        RequirementDraft(
                            code="REQ-DUP",
                            title="Second",
                            statement="The second requirement.",
                        ),
                    ],
                ),
            )
            with pytest.raises(EngineeringError) as captured:
                persist_requirement_analysis_bundle(session, analysis)
            assert captured.value.code is EngineeringErrorCode.INVALID_REQUIREMENT
            assert SqlAlchemyRequirementRepository(session).list_for_project(project_id) == []
            assert SqlAlchemyRequirementAnalysisRepository(session).get(analysis.id) is None
    finally:
        engine.dispose()
