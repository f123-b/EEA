"""Persistence ports owned by the Core boundary."""

from typing import Protocol
from uuid import UUID

from eea_core.ai import AIUsageRecord, PromptDefinition
from eea_core.entities import Project


class ProjectRepository(Protocol):
    def add(self, project: Project) -> Project: ...

    def get(self, project_id: UUID, *, include_deleted: bool = False) -> Project | None: ...

    def list(self, *, include_deleted: bool = False) -> list[Project]: ...

    def save(self, project: Project, *, expected_revision: int) -> Project | None: ...


class PromptRepository(Protocol):
    def add(self, definition: PromptDefinition) -> PromptDefinition: ...

    def get(self, name: str, version: str | None = None) -> PromptDefinition | None: ...


class AIUsageRepository(Protocol):
    def add(self, record: AIUsageRecord) -> AIUsageRecord: ...

    def list_for_request(self, request_id: object) -> list[AIUsageRecord]: ...
