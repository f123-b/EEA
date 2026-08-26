"""SQLAlchemy repository adapters."""

from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from eea_core.ai import AIUsage, AIUsageRecord, PromptDefinition
from eea_core.entities import Artifact, Evidence, Project, utc_now
from eea_core.enums import ArtifactStatus, EngineeringErrorCode, ProjectStatus
from sqlalchemy import desc, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from eea_backend.models import (
    AIUsageRecordModel,
    ArtifactRecord,
    EvidenceRecord,
    ProjectRecord,
    PromptDefinitionRecord,
)


def _to_artifact(record: ArtifactRecord) -> Artifact:
    return Artifact.model_validate(
        {
            "id": record.id,
            "schema_version": record.schema_version,
            "revision": record.revision,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "metadata": record.entity_metadata,
            "project_id": record.project_id,
            "logical_name": record.logical_name,
            "artifact_type": record.artifact_type,
            "version_label": record.version_label,
            "content_hash": record.content_hash,
            "input_hash": record.input_hash,
            "storage_uri": record.storage_uri,
            "parent_artifact_id": record.parent_artifact_id,
            "dependency_ids": record.dependency_ids,
            "dependency_hashes": record.dependency_hashes,
            "created_by": record.created_by,
            "source_job_id": record.source_job_id,
            "generator_version": record.generator_version,
            "tool_versions": record.tool_versions,
            "knowledge_snapshot": record.knowledge_snapshot,
            "status": record.status,
        }
    )


class SqlAlchemyArtifactRepository:
    """Project-scoped artifact lookup used by M18 compatibility APIs."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, artifact_id: UUID, *, project_id: UUID | None = None) -> Artifact | None:
        statement = select(ArtifactRecord).where(ArtifactRecord.id == str(artifact_id))
        if project_id is not None:
            statement = statement.where(ArtifactRecord.project_id == str(project_id))
        record = self._session.scalar(statement)
        return _to_artifact(record) if record else None

    def add(self, artifact: Artifact, *, commit: bool = True) -> Artifact:
        """Persist a derived artifact without poisoning the caller transaction."""

        record = ArtifactRecord(
            id=str(artifact.id),
            schema_version=artifact.schema_version,
            revision=artifact.revision,
            created_at=artifact.created_at,
            updated_at=artifact.updated_at,
            entity_metadata=artifact.metadata,
            project_id=str(artifact.project_id),
            logical_name=artifact.logical_name,
            artifact_type=artifact.artifact_type,
            version_label=artifact.version_label,
            content_hash=artifact.content_hash,
            input_hash=artifact.input_hash,
            storage_uri=artifact.storage_uri,
            parent_artifact_id=str(artifact.parent_artifact_id)
            if artifact.parent_artifact_id
            else None,
            dependency_ids=[str(value) for value in artifact.dependency_ids],
            dependency_hashes=artifact.dependency_hashes,
            created_by=artifact.created_by,
            source_job_id=str(artifact.source_job_id) if artifact.source_job_id else None,
            generator_version=artifact.generator_version,
            tool_versions=artifact.tool_versions,
            knowledge_snapshot=artifact.knowledge_snapshot,
            status=artifact.status.value,
        )
        existing = self._session.get(ArtifactRecord, str(artifact.id))
        if existing is not None:
            return _to_artifact(existing)
        try:
            with self._session.begin_nested():
                self._session.add(record)
                self._session.flush()
        except IntegrityError:
            existing = self._session.scalar(
                select(ArtifactRecord).where(
                    ArtifactRecord.project_id == str(artifact.project_id),
                    ArtifactRecord.logical_name == artifact.logical_name,
                    ArtifactRecord.version_label == artifact.version_label,
                )
            )
            if existing is None:
                raise ValueError("derived artifact identity race could not be resolved") from None
            return _to_artifact(existing)
        if commit:
            self._session.commit()
        return _to_artifact(record)

    def list_for_project(self, project_id: UUID) -> list[Artifact]:
        records = self._session.scalars(
            select(ArtifactRecord)
            .where(ArtifactRecord.project_id == str(project_id))
            .order_by(ArtifactRecord.logical_name, ArtifactRecord.created_at, ArtifactRecord.id)
        )
        return [_to_artifact(record) for record in records]

    def list_versions(self, artifact: Artifact) -> list[Artifact]:
        records = self._session.scalars(
            select(ArtifactRecord)
            .where(
                ArtifactRecord.project_id == str(artifact.project_id),
                ArtifactRecord.logical_name == artifact.logical_name,
            )
            .order_by(ArtifactRecord.created_at, ArtifactRecord.id)
        )
        return [_to_artifact(record) for record in records]

    def save_status_projection(
        self, artifact: Artifact, status: ArtifactStatus, *, commit: bool = True
    ) -> Artifact:
        record = self._session.scalar(
            select(ArtifactRecord).where(
                ArtifactRecord.id == str(artifact.id),
                ArtifactRecord.project_id == str(artifact.project_id),
            )
        )
        if record is None:
            raise ValueError("artifact is not available in the requested project")
        record.status = status.value
        record.revision += 1
        record.updated_at = utc_now()
        if commit:
            self._session.commit()
        return _to_artifact(record)


def _to_evidence(record: EvidenceRecord) -> Evidence:
    return Evidence.model_validate(
        {
            "id": record.id,
            "schema_version": record.schema_version,
            "revision": record.revision,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "metadata": record.entity_metadata,
            "project_id": record.project_id,
            "evidence_type": record.evidence_type,
            "locator": record.locator,
            "source_uri": record.source_uri,
            "content_hash": record.content_hash,
            "summary": record.summary,
        }
    )


class SqlAlchemyEvidenceRepository:
    """Evidence lookup with canonical project-scope semantics."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, evidence: Evidence, *, commit: bool = True) -> Evidence:
        record = EvidenceRecord(
            id=str(evidence.id),
            schema_version=evidence.schema_version,
            revision=evidence.revision,
            created_at=evidence.created_at,
            updated_at=evidence.updated_at,
            entity_metadata=evidence.metadata,
            project_id=str(evidence.project_id) if evidence.project_id else None,
            evidence_type=evidence.evidence_type.value,
            locator=evidence.locator,
            source_uri=evidence.source_uri,
            content_hash=evidence.content_hash,
            summary=evidence.summary,
        )
        self._session.add(record)
        if commit:
            self._session.commit()
            self._session.refresh(record)
        else:
            self._session.flush()
        return _to_evidence(record)

    def get(self, evidence_id: UUID, *, project_id: UUID | None) -> Evidence | None:
        scope = (
            EvidenceRecord.project_id.is_(None)
            if project_id is None
            else or_(
                EvidenceRecord.project_id == str(project_id), EvidenceRecord.project_id.is_(None)
            )
        )
        record = self._session.scalar(
            select(EvidenceRecord).where(EvidenceRecord.id == str(evidence_id), scope)
        )
        return _to_evidence(record) if record else None

    def exists(self, evidence_id: UUID) -> bool:
        return (
            self._session.scalar(
                select(EvidenceRecord.id).where(EvidenceRecord.id == str(evidence_id)).limit(1)
            )
            is not None
        )


def _to_project(record: ProjectRecord) -> Project:
    return Project(
        id=UUID(record.id),
        schema_version=record.schema_version,
        revision=record.revision,
        created_at=record.created_at,
        updated_at=record.updated_at,
        metadata=record.entity_metadata,
        name=record.name,
        description=record.description,
        status=ProjectStatus(record.status),
        deleted_at=record.deleted_at,
    )


class SqlAlchemyProjectRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, project: Project, *, commit: bool = True) -> Project:
        record = ProjectRecord(
            id=str(project.id),
            schema_version=project.schema_version,
            revision=project.revision,
            created_at=project.created_at,
            updated_at=project.updated_at,
            entity_metadata=project.metadata,
            name=project.name,
            description=project.description,
            status=project.status.value,
            deleted_at=project.deleted_at,
        )
        self._session.add(record)
        if commit:
            self._session.commit()
            self._session.refresh(record)
        else:
            self._session.flush()
        return _to_project(record)

    def get(self, project_id: UUID, *, include_deleted: bool = False) -> Project | None:
        statement = select(ProjectRecord).where(ProjectRecord.id == str(project_id))
        if not include_deleted:
            statement = statement.where(ProjectRecord.deleted_at.is_(None))
        record = self._session.scalar(statement)
        return _to_project(record) if record else None

    def list(self, *, include_deleted: bool = False) -> list[Project]:
        statement = select(ProjectRecord).order_by(ProjectRecord.created_at, ProjectRecord.id)
        if not include_deleted:
            statement = statement.where(ProjectRecord.deleted_at.is_(None))
        return [_to_project(record) for record in self._session.scalars(statement)]

    def save(self, project: Project, *, expected_revision: int) -> Project | None:
        statement = (
            update(ProjectRecord)
            .where(
                ProjectRecord.id == str(project.id),
                ProjectRecord.revision == expected_revision,
            )
            .values(
                schema_version=project.schema_version,
                revision=project.revision,
                updated_at=project.updated_at,
                entity_metadata=project.metadata,
                name=project.name,
                description=project.description,
                status=project.status.value,
                deleted_at=project.deleted_at,
            )
        )
        result = self._session.execute(statement)
        if not isinstance(result, CursorResult) or result.rowcount != 1:
            self._session.rollback()
            return None
        self._session.commit()
        return self.get(project.id, include_deleted=True)


def _to_prompt_definition(record: PromptDefinitionRecord) -> PromptDefinition:
    return PromptDefinition.model_validate(
        {
            "id": record.id,
            "schema_version": record.schema_version,
            "revision": record.revision,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "metadata": record.entity_metadata,
            "name": record.name,
            "prompt_version": record.prompt_version,
            "purpose": record.purpose,
            "system_template": record.system_template,
            "user_template": record.user_template,
            "model_policy": record.model_policy,
            "allowed_tools": record.allowed_tools,
            "input_schema": record.input_schema,
            "output_schema": record.output_schema,
            "evidence_requirements": record.evidence_requirements,
            "fallback": record.fallback,
            "max_steps": record.max_steps,
            "budget_policy": record.budget_policy,
            "active": record.active,
        }
    )


class SqlAlchemyPromptRepository:
    """Durable versioned prompt registry."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, definition: PromptDefinition) -> PromptDefinition:
        serialized = definition.model_dump(mode="json")
        record = PromptDefinitionRecord(
            id=str(definition.id),
            schema_version=definition.schema_version,
            revision=definition.revision,
            created_at=definition.created_at,
            updated_at=definition.updated_at,
            entity_metadata=definition.metadata,
            name=definition.name,
            prompt_version=definition.prompt_version,
            purpose=definition.purpose,
            system_template=definition.system_template,
            user_template=definition.user_template,
            model_policy=cast(dict[str, Any], serialized["model_policy"]),
            allowed_tools=definition.allowed_tools,
            input_schema=definition.input_schema,
            output_schema=definition.output_schema,
            evidence_requirements=definition.evidence_requirements,
            fallback=definition.fallback,
            max_steps=definition.max_steps,
            budget_policy=cast(dict[str, Any], serialized["budget_policy"]),
            active=definition.active,
        )
        self._session.add(record)
        try:
            self._session.commit()
        except IntegrityError:
            self._session.rollback()
            raise ValueError(
                "Prompt version is already registered: "
                f"{definition.name}@{definition.prompt_version}"
            ) from None
        self._session.refresh(record)
        return _to_prompt_definition(record)

    def get(self, name: str, version: str | None = None) -> PromptDefinition | None:
        statement = select(PromptDefinitionRecord).where(PromptDefinitionRecord.name == name)
        if version is not None:
            statement = statement.where(PromptDefinitionRecord.prompt_version == version)
        else:
            statement = statement.where(PromptDefinitionRecord.active.is_(True)).order_by(
                desc(PromptDefinitionRecord.created_at),
                desc(PromptDefinitionRecord.prompt_version),
            )
        record = self._session.scalar(statement.limit(1))
        return _to_prompt_definition(record) if record else None


def _to_usage_record(record: AIUsageRecordModel) -> AIUsageRecord:
    return AIUsageRecord(
        id=UUID(record.id),
        schema_version=record.schema_version,
        revision=record.revision,
        created_at=record.created_at,
        updated_at=record.updated_at,
        metadata=record.entity_metadata,
        request_id=UUID(record.request_id),
        prompt_definition_id=UUID(record.prompt_definition_id),
        project_id=UUID(record.project_id) if record.project_id else None,
        job_id=UUID(record.job_id) if record.job_id else None,
        provider=record.provider,
        model=record.model,
        usage=AIUsage(
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            total_tokens=record.total_tokens,
            llm_cost=Decimal(str(record.llm_cost)),
        ),
        duration_ms=record.duration_ms,
        succeeded=record.succeeded,
        error_code=EngineeringErrorCode(record.error_code) if record.error_code else None,
    )


class SqlAlchemyAIUsageRepository:
    """Append-only AI usage accounting repository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, usage_record: AIUsageRecord) -> AIUsageRecord:
        record = AIUsageRecordModel(
            id=str(usage_record.id),
            schema_version=usage_record.schema_version,
            revision=usage_record.revision,
            created_at=usage_record.created_at,
            updated_at=usage_record.updated_at,
            entity_metadata=usage_record.metadata,
            request_id=str(usage_record.request_id),
            prompt_definition_id=str(usage_record.prompt_definition_id),
            project_id=str(usage_record.project_id) if usage_record.project_id else None,
            job_id=str(usage_record.job_id) if usage_record.job_id else None,
            provider=usage_record.provider,
            model=usage_record.model,
            input_tokens=usage_record.usage.input_tokens,
            output_tokens=usage_record.usage.output_tokens,
            total_tokens=usage_record.usage.total_tokens,
            llm_cost=usage_record.usage.llm_cost,
            duration_ms=usage_record.duration_ms,
            succeeded=usage_record.succeeded,
            error_code=usage_record.error_code.value if usage_record.error_code else None,
        )
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return _to_usage_record(record)

    def list_for_request(self, request_id: object) -> list[AIUsageRecord]:
        statement = (
            select(AIUsageRecordModel)
            .where(AIUsageRecordModel.request_id == str(request_id))
            .order_by(AIUsageRecordModel.created_at, AIUsageRecordModel.id)
        )
        return [_to_usage_record(record) for record in self._session.scalars(statement)]
