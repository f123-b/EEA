"""Trusted identity context used by the Knowledge / Memory boundary.

The memory API may retain legacy identity-shaped fields for wire compatibility,
but authorization is performed with this server-owned value only.  The local
desktop principal is deliberately explicit: it is a single-user principal,
not an arbitrary actor string supplied by the renderer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

ProjectPermissions = Mapping[str, frozenset[str]]


@dataclass(frozen=True, slots=True)
class IdentityContext:
    """The complete trusted identity and scope context for one request."""

    principal_id: str
    user_id: str
    organization_ids: frozenset[str] = frozenset()
    active_organization_id: str | None = None
    task_id: str | None = None
    project_permissions: ProjectPermissions = field(default_factory=dict)
    session_id: str = ""
    authentication_source: str = "unknown"

    @classmethod
    def local(
        cls,
        *,
        session_id: str,
        project_permissions: ProjectPermissions | None = None,
        task_id: str | None = None,
    ) -> IdentityContext:
        return cls(
            principal_id="local:single-user",
            user_id="local:single-user",
            project_permissions=project_permissions or {},
            task_id=task_id,
            session_id=session_id,
            authentication_source="local-principal",
        )

    def can_project(self, project_id: str, action: str = "read") -> bool:
        """Return whether server-owned project access grants ``action``.

        A local desktop installation has one trusted principal.  The backend
        still records OWNER assignments for auditability, while the explicit
        local-principal fallback keeps pre-M18E local projects usable during
        migration.  Team principals must have a recorded permission.
        """

        permissions = self.project_permissions.get(str(project_id), frozenset())
        if action in permissions or "owner" in permissions or "admin" in permissions:
            return True
        return self.authentication_source == "local-principal"

    def can_publish_global(self) -> bool:
        return self.authentication_source == "local-principal" or any(
            permission in {"publish", "admin"}
            for permissions in self.project_permissions.values()
            for permission in permissions
        )

    def allowed_scopes(self, *, project_id: str | None = None) -> frozenset[str]:
        """Return scopes this identity may ask the memory policy to inspect."""

        scopes = {"GLOBAL_PUBLIC", "USER_PRIVATE"}
        if project_id is not None and self.can_project(project_id):
            scopes.add("PROJECT_PRIVATE")
        if self.organization_ids:
            scopes.add("ORGANIZATION_PRIVATE")
        if self.task_id:
            scopes.add("TASK_ONLY")
        return frozenset(scopes)


__all__ = ["IdentityContext", "ProjectPermissions"]
