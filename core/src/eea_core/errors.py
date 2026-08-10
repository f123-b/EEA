"""Deterministic engineering errors shared across application surfaces."""

from collections.abc import Mapping

from eea_core.enums import EngineeringErrorCode


class EngineeringError(Exception):
    """A public, stable engineering error with structured details."""

    def __init__(
        self,
        code: EngineeringErrorCode,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


class ProjectNotFoundError(EngineeringError):
    def __init__(self, project_id: object) -> None:
        super().__init__(
            EngineeringErrorCode.PROJECT_NOT_FOUND,
            "Project was not found",
            details={"project_id": str(project_id)},
        )


class RevisionConflictError(EngineeringError):
    def __init__(self, entity_id: object, expected_revision: int) -> None:
        super().__init__(
            EngineeringErrorCode.REVISION_CONFLICT,
            "The entity changed after it was read",
            details={"entity_id": str(entity_id), "expected_revision": expected_revision},
        )
