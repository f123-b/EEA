"""SQLAlchemy repository adapters."""

from typing import Any, cast
from uuid import UUID

from eea_core.entities import Project
from eea_core.enums import ProjectStatus
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from eea_backend.models import ProjectRecord


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

    def add(self, project: Project) -> Project:
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
        self._session.commit()
        self._session.refresh(record)
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
        result = cast(CursorResult[Any], self._session.execute(statement))
        if result.rowcount != 1:
            self._session.rollback()
            return None
        self._session.commit()
        return self.get(project.id, include_deleted=True)
