"""Project use cases independent of HTTP and SQLAlchemy."""

from datetime import UTC, datetime
from uuid import UUID

from eea_core.entities import Project
from eea_core.enums import ProjectStatus
from eea_core.errors import ProjectNotFoundError, RevisionConflictError
from eea_core.repositories import ProjectRepository


class ProjectService:
    def __init__(self, repository: ProjectRepository) -> None:
        self._repository = repository

    def create(
        self,
        *,
        name: str,
        description: str = "",
        metadata: dict[str, object] | None = None,
    ) -> Project:
        project = Project(name=name, description=description, metadata=metadata or {})
        return self._repository.add(project)

    def get(self, project_id: UUID) -> Project:
        project = self._repository.get(project_id)
        if project is None:
            raise ProjectNotFoundError(project_id)
        return project

    def list(self) -> list[Project]:
        return self._repository.list()

    def update(
        self,
        project_id: UUID,
        *,
        expected_revision: int,
        name: str | None = None,
        description: str | None = None,
        status: ProjectStatus | None = None,
        metadata: dict[str, object] | None = None,
    ) -> Project:
        current = self.get(project_id)
        if current.revision != expected_revision:
            raise RevisionConflictError(project_id, expected_revision)
        changes: dict[str, object] = {
            "revision": current.revision + 1,
            "updated_at": datetime.now(UTC),
        }
        if name is not None:
            changes["name"] = name
        if description is not None:
            changes["description"] = description
        if status is not None:
            changes["status"] = status
        if metadata is not None:
            changes["metadata"] = metadata
        updated = Project.model_validate({**current.model_dump(), **changes})
        saved = self._repository.save(updated, expected_revision=expected_revision)
        if saved is None:
            raise RevisionConflictError(project_id, expected_revision)
        return saved

    def delete(self, project_id: UUID, *, expected_revision: int) -> Project:
        current = self.get(project_id)
        if current.revision != expected_revision:
            raise RevisionConflictError(project_id, expected_revision)
        deleted = Project.model_validate(
            {
                **current.model_dump(),
                "status": ProjectStatus.ARCHIVED,
                "deleted_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "revision": current.revision + 1,
            }
        )
        saved = self._repository.save(deleted, expected_revision=expected_revision)
        if saved is None:
            raise RevisionConflictError(project_id, expected_revision)
        return saved
