"""M6 Requirement DSL acceptance tests."""

import asyncio
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from eea_application.requirements import (
    RequirementAnalysisService,
    RequirementProfileRegistry,
    build_foc_benchmark_profile,
    build_requirement_analysis_prompt_definition,
)
from eea_backend.database import create_database_engine
from eea_backend.repositories import SqlAlchemyProjectRepository
from eea_backend.requirement_repositories import (
    SqlAlchemyRequirementAnalysisRepository,
    SqlAlchemyRequirementProfileRepository,
)
from eea_backend.settings import Settings
from eea_core.claims import EngineeringValue
from eea_core.entities import Project
from eea_core.enums import (
    EngineeringDimension,
    EngineeringErrorCode,
    RequirementFieldStatus,
    RequirementStatus,
)
from eea_core.errors import EngineeringError
from eea_core.requirements import RequirementAnalysisDraft, RequirementFieldObservation
from fastapi.testclient import TestClient
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


class FakeStructuredGeneration:
    def __init__(self, draft: RequirementAnalysisDraft) -> None:
        self.draft = draft
        self.calls: list[dict[str, object]] = []

    async def generate(self, **kwargs: object) -> RequirementAnalysisDraft:
        self.calls.append(kwargs)
        return self.draft


def make_service() -> tuple[RequirementAnalysisService, object]:
    repository = MemoryProfileRepository()
    repository.add(build_foc_benchmark_profile())
    registry = RequirementProfileRegistry(repository)  # type: ignore[arg-type]
    return RequirementAnalysisService(registry), repository


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


def evidence_for(values: dict[str, object]) -> dict[str, UUID]:
    return {key: uuid4() for key in values} | {
        "device_source": uuid4(),
        "power_source": uuid4(),
        "control_timing_source": uuid4(),
        "safety_source": uuid4(),
    }


def test_foc_profile_is_generic_and_full_structured_input_is_complete() -> None:
    service, _ = make_service()
    values = valid_values()
    analysis = service.analyze_structured(
        project_id=UUID(int=1),
        profile_name="foc-benchmark",
        profile_version="1.0",
        values=values,
        evidence_refs=evidence_for(values),
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


def test_natural_language_service_only_uses_structured_generation() -> None:
    repository = MemoryProfileRepository()
    profile = build_foc_benchmark_profile()
    repository.add(profile)
    draft = RequirementAnalysisDraft(
        profile_name=profile.profile_name,
        profile_version=profile.profile_version,
    )
    generator = FakeStructuredGeneration(draft)
    service = RequirementAnalysisService(
        RequirementProfileRegistry(repository),  # type: ignore[arg-type]
        generator,  # type: ignore[arg-type]
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
            analysis = RequirementAnalysisService(
                RequirementProfileRegistry(profiles)
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
