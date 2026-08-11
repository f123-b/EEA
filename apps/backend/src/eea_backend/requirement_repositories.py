"""SQLAlchemy adapters for M6 requirement profiles and analysis results."""

from typing import Any, cast
from uuid import UUID

from eea_core.requirements import Requirement, RequirementAnalysis, RequirementProfile
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from eea_backend.models import (
    RequirementAnalysisRecord,
    RequirementProfileRecord,
    RequirementRecord,
)


def _entity_kwargs(record: object) -> dict[str, Any]:
    typed = cast(Any, record)
    return {
        "id": UUID(typed.id),
        "schema_version": typed.schema_version,
        "revision": typed.revision,
        "created_at": typed.created_at,
        "updated_at": typed.updated_at,
        "metadata": typed.entity_metadata,
    }


def _to_profile(record: RequirementProfileRecord) -> RequirementProfile:
    return RequirementProfile.model_validate(
        {
            **_entity_kwargs(record),
            "profile_name": record.profile_name,
            "profile_version": record.profile_version,
            "purpose": record.purpose,
            "fields": record.fields,
            "evidence_contracts": record.evidence_contracts,
            "active": record.active,
        }
    )


class SqlAlchemyRequirementProfileRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, profile: RequirementProfile) -> RequirementProfile:
        serialized = profile.model_dump(mode="json")
        record = RequirementProfileRecord(
            id=str(profile.id),
            schema_version=profile.schema_version,
            revision=profile.revision,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
            entity_metadata=profile.metadata,
            profile_name=profile.profile_name,
            profile_version=profile.profile_version,
            purpose=profile.purpose,
            fields=cast(list[dict[str, Any]], serialized["fields"]),
            evidence_contracts=cast(list[dict[str, Any]], serialized["evidence_contracts"]),
            active=profile.active,
        )
        self._session.add(record)
        try:
            self._session.commit()
        except IntegrityError:
            self._session.rollback()
            raise ValueError(
                "Requirement profile version is already registered: "
                f"{profile.profile_name}@{profile.profile_version}"
            ) from None
        self._session.refresh(record)
        return _to_profile(record)

    def get(
        self, profile_name: str, profile_version: str | None = None
    ) -> RequirementProfile | None:
        statement = select(RequirementProfileRecord).where(
            RequirementProfileRecord.profile_name == profile_name
        )
        if profile_version is not None:
            statement = statement.where(RequirementProfileRecord.profile_version == profile_version)
        else:
            statement = statement.where(RequirementProfileRecord.active.is_(True)).order_by(
                desc(RequirementProfileRecord.created_at),
                desc(RequirementProfileRecord.profile_version),
            )
        record = self._session.scalar(statement.limit(1))
        return _to_profile(record) if record else None


def _to_requirement(record: RequirementRecord) -> Requirement:
    return Requirement.model_validate(
        {
            **_entity_kwargs(record),
            "project_id": UUID(record.project_id),
            "code": record.code,
            "title": record.title,
            "requirement_type": record.requirement_type,
            "priority": record.priority,
            "statement": record.statement,
            "rationale": record.rationale,
            "acceptance_criteria": record.acceptance_criteria,
            "source_evidence_ids": record.source_evidence_ids,
            "status": record.status,
        }
    )


class SqlAlchemyRequirementRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, requirement: Requirement, *, commit: bool = True) -> Requirement:
        record = RequirementRecord(
            id=str(requirement.id),
            schema_version=requirement.schema_version,
            revision=requirement.revision,
            created_at=requirement.created_at,
            updated_at=requirement.updated_at,
            entity_metadata=requirement.metadata,
            project_id=str(requirement.project_id),
            code=requirement.code,
            title=requirement.title,
            requirement_type=requirement.requirement_type.value,
            priority=requirement.priority.value,
            statement=requirement.statement,
            rationale=requirement.rationale,
            acceptance_criteria=requirement.acceptance_criteria,
            source_evidence_ids=[str(value) for value in requirement.source_evidence_ids],
            status=requirement.status.value,
        )
        self._session.add(record)
        if commit:
            self._session.commit()
            self._session.refresh(record)
        else:
            self._session.flush()
        return _to_requirement(record)

    def list_for_project(self, project_id: UUID) -> list[Requirement]:
        statement = (
            select(RequirementRecord)
            .where(RequirementRecord.project_id == str(project_id))
            .order_by(RequirementRecord.created_at, RequirementRecord.id)
        )
        return [_to_requirement(record) for record in self._session.scalars(statement)]


def _to_analysis(record: RequirementAnalysisRecord) -> RequirementAnalysis:
    return RequirementAnalysis.model_validate(
        {
            **_entity_kwargs(record),
            "project_id": UUID(record.project_id),
            "profile_name": record.profile_name,
            "profile_version": record.profile_version,
            "requirements": record.requirements,
            "field_observations": record.field_observations,
            "claims": record.claims,
            "issues": record.issues,
            "follow_up_questions": record.follow_up_questions,
            "completeness": record.completeness,
            "requirement_ids": record.requirement_ids,
            "claim_ids": record.claim_ids,
        }
    )


class SqlAlchemyRequirementAnalysisRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, analysis: RequirementAnalysis, *, commit: bool = True) -> RequirementAnalysis:
        serialized = analysis.model_dump(mode="json")
        record = RequirementAnalysisRecord(
            id=str(analysis.id),
            schema_version=analysis.schema_version,
            revision=analysis.revision,
            created_at=analysis.created_at,
            updated_at=analysis.updated_at,
            entity_metadata=analysis.metadata,
            project_id=str(analysis.project_id),
            profile_name=analysis.profile_name,
            profile_version=analysis.profile_version,
            requirements=cast(list[dict[str, Any]], serialized["requirements"]),
            field_observations=cast(list[dict[str, Any]], serialized["field_observations"]),
            claims=cast(list[dict[str, Any]], serialized["claims"]),
            issues=cast(list[dict[str, Any]], serialized["issues"]),
            follow_up_questions=cast(list[dict[str, Any]], serialized["follow_up_questions"]),
            completeness=cast(dict[str, Any], serialized["completeness"]),
            requirement_ids=[str(value) for value in analysis.requirement_ids],
            claim_ids=[str(value) for value in analysis.claim_ids],
        )
        self._session.add(record)
        if commit:
            self._session.commit()
            self._session.refresh(record)
        else:
            self._session.flush()
        return _to_analysis(record)

    def get(self, analysis_id: UUID) -> RequirementAnalysis | None:
        record = self._session.get(RequirementAnalysisRecord, str(analysis_id))
        return _to_analysis(record) if record else None


def persist_requirement_analysis_bundle(
    session: Session, analysis: RequirementAnalysis
) -> RequirementAnalysis:
    """Persist the canonical requirements, claims, and analysis atomically."""

    from eea_backend.claim_repositories import SqlAlchemyEngineeringClaimRepository

    requirements = SqlAlchemyRequirementRepository(session)
    claims = SqlAlchemyEngineeringClaimRepository(session)
    analyses = SqlAlchemyRequirementAnalysisRepository(session)
    try:
        saved_requirements = [
            requirements.add(value, commit=False) for value in analysis.requirements
        ]
        saved_claims = [claims.add(value, commit=False) for value in analysis.claims]
        canonical = analysis.model_copy(
            update={
                "requirement_ids": [item.id for item in saved_requirements],
                "claim_ids": [item.id for item in saved_claims],
            }
        )
        analyses.add(canonical, commit=False)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return canonical
