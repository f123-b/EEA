"""Persistence adapter for the M18E stable identity foundation."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from eea_application.knowledge_identity import IdentityContext
from eea_core.identity import IdentityMode, ProjectRole, UserIdentity, local_single_user
from sqlalchemy import select
from sqlalchemy.orm import Session

from eea_backend.models import (
    IdentityUserRecord,
    MembershipRecord,
    ProjectRecord,
    ProjectRoleAssignmentRecord,
)


def _now() -> datetime:
    return datetime.now(UTC)


class IdentityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def ensure_local_user(self, *, commit: bool = True) -> UserIdentity:
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
            if commit:
                self.session.commit()
        return UserIdentity(
            id=UUID(record.id),
            stable_actor_id=record.stable_actor_id,
            display_name=record.display_name,
            mode=IdentityMode(record.mode),
        )

    def ensure_project_owner(
        self, project_id: UUID, user: UserIdentity, *, commit: bool = True
    ) -> ProjectRole:
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
            if commit:
                self.session.commit()
        return ProjectRole(assignment.role)

    def load_context(
        self,
        *,
        principal_id: str,
        user_id: str,
        session_id: str,
        authentication_source: str,
        task_id: str | None = None,
    ) -> IdentityContext:
        """Resolve organization and project permissions from server-owned rows."""

        user = self.session.scalar(
            select(IdentityUserRecord).where(IdentityUserRecord.stable_actor_id == user_id)
        )
        if user is None and user_id == "local:single-user":
            self.ensure_local_user(commit=False)
            user = self.session.scalar(
                select(IdentityUserRecord).where(
                    IdentityUserRecord.stable_actor_id == "local:single-user"
                )
            )
        if user is None:
            return IdentityContext(
                principal_id=principal_id,
                user_id=user_id,
                session_id=session_id,
                authentication_source=authentication_source,
                task_id=task_id,
            )
        organizations = list(
            self.session.scalars(
                select(MembershipRecord.organization_id)
                .where(MembershipRecord.user_id == user.id)
                .order_by(MembershipRecord.created_at, MembershipRecord.id)
            )
        )
        assignments = self.session.scalars(
            select(ProjectRoleAssignmentRecord).where(
                ProjectRoleAssignmentRecord.user_id == user.id
            )
        )
        permissions: dict[str, frozenset[str]] = {}
        for assignment in assignments:
            role = assignment.role.lower()
            granted = {"read", role}
            if role in {"owner", "maintainer", "engineer"}:
                granted.update({"write", "review", "publish"})
            permissions[assignment.project_id] = frozenset(granted)
        organization_ids = frozenset(str(value) for value in organizations)
        return IdentityContext(
            principal_id=principal_id,
            user_id=user_id,
            organization_ids=organization_ids,
            active_organization_id=(str(organizations[0]) if organizations else None),
            task_id=task_id,
            project_permissions=permissions,
            session_id=session_id,
            authentication_source=authentication_source,
        )


__all__ = ["IdentityRepository"]
