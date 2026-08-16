"""Persistence adapter for the M18E stable identity foundation."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from eea_core.identity import IdentityMode, ProjectRole, UserIdentity, local_single_user
from sqlalchemy import select
from sqlalchemy.orm import Session

from eea_backend.models import (
    IdentityUserRecord,
    ProjectRecord,
    ProjectRoleAssignmentRecord,
)


def _now() -> datetime:
    return datetime.now(UTC)


class IdentityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def ensure_local_user(self) -> UserIdentity:
        expected = local_single_user()
        record = self.session.scalar(
            select(IdentityUserRecord).where(
                IdentityUserRecord.stable_actor_id == expected.stable_actor_id
            )
        )
        if record is None:
            now = _now()
            record = IdentityUserRecord(
                id=str(expected.id),
                schema_version="1.0",
                revision=1,
                created_at=now,
                updated_at=now,
                entity_metadata={},
                stable_actor_id=expected.stable_actor_id,
                display_name=expected.display_name,
                mode=expected.mode.value,
            )
            self.session.add(record)
            self.session.commit()
        return UserIdentity(
            id=UUID(record.id),
            stable_actor_id=record.stable_actor_id,
            display_name=record.display_name,
            mode=IdentityMode(record.mode),
        )

    def ensure_project_owner(self, project_id: UUID, user: UserIdentity) -> ProjectRole:
        assignment = self.session.scalar(
            select(ProjectRoleAssignmentRecord).where(
                ProjectRoleAssignmentRecord.project_id == str(project_id),
                ProjectRoleAssignmentRecord.user_id == str(user.id),
            )
        )
        if assignment is None:
            if self.session.get(ProjectRecord, str(project_id)) is None:
                raise ValueError("project does not exist")
            now = _now()
            assignment = ProjectRoleAssignmentRecord(
                id=f"{project_id}:{user.id}",
                schema_version="1.0",
                revision=1,
                created_at=now,
                updated_at=now,
                entity_metadata={},
                project_id=str(project_id),
                user_id=str(user.id),
                role=ProjectRole.OWNER.value,
            )
            self.session.add(assignment)
            self.session.commit()
        return ProjectRole(assignment.role)


__all__ = ["IdentityRepository"]
