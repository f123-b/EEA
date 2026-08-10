"""Project application-service tests, including concurrent-write behavior."""

from uuid import UUID

import pytest
from eea_application.projects import ProjectService
from eea_core.entities import Project
from eea_core.errors import ProjectNotFoundError, RevisionConflictError


class InMemoryProjectRepository:
    def __init__(self) -> None:
        self.projects: dict[UUID, Project] = {}
        self.force_conflict = False

    def add(self, project: Project) -> Project:
        self.projects[project.id] = project
        return project

    def get(self, project_id: UUID, *, include_deleted: bool = False) -> Project | None:
        project = self.projects.get(project_id)
        if project is None or (project.deleted_at is not None and not include_deleted):
            return None
        return project

    def list(self, *, include_deleted: bool = False) -> list[Project]:
        return [
            project
            for project in self.projects.values()
            if include_deleted or project.deleted_at is None
        ]

    def save(self, project: Project, *, expected_revision: int) -> Project | None:
        if self.force_conflict:
            return None
        current = self.projects.get(project.id)
        if current is None or current.revision != expected_revision:
            return None
        self.projects[project.id] = project
        return project


def test_project_lifecycle_and_soft_delete() -> None:
    repository = InMemoryProjectRepository()
    service = ProjectService(repository)

    created = service.create(name="FOC Controller", metadata={"owner": "test"})
    assert service.get(created.id) == created
    assert service.list() == [created]

    updated = service.update(created.id, expected_revision=1, description="Reference benchmark")
    assert updated.revision == 2
    assert updated.description == "Reference benchmark"

    deleted = service.delete(created.id, expected_revision=2)
    assert deleted.deleted_at is not None
    assert service.list() == []
    with pytest.raises(ProjectNotFoundError):
        service.get(created.id)


def test_project_service_reports_stale_and_racing_revisions() -> None:
    repository = InMemoryProjectRepository()
    service = ProjectService(repository)
    created = service.create(name="Concurrent")

    with pytest.raises(RevisionConflictError):
        service.update(created.id, expected_revision=9, name="stale")

    repository.force_conflict = True
    with pytest.raises(RevisionConflictError):
        service.update(created.id, expected_revision=1, name="racing writer")
    with pytest.raises(RevisionConflictError):
        service.delete(created.id, expected_revision=1)


def test_missing_project_raises_stable_error() -> None:
    service = ProjectService(InMemoryProjectRepository())

    with pytest.raises(ProjectNotFoundError) as exc_info:
        service.get(UUID(int=0))

    assert exc_info.value.code.value == "PROJECT_NOT_FOUND"
