"""Core-owned permission-token contracts.

Tokens are references to a server-issued grant.  They never contain bearer credentials or
secrets; verification is performed by an application/backend authority against these immutable
scope fields.
"""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from eea_core.entities import EntityBase, utc_now
from eea_core.enums import Permission


class PermissionTokenStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class PermissionToken(EntityBase):
    """A server-issued, resource-scoped permission grant."""

    project_id: UUID
    actor_id: str = Field(min_length=1, max_length=200)
    permission: Permission
    resource_type: str = Field(min_length=1, max_length=100)
    resource_id: str = Field(min_length=1, max_length=500)
    issued_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    status: PermissionTokenStatus = PermissionTokenStatus.ACTIVE
    session_id: UUID | None = None
    reason: str = Field(default="", max_length=2000)
    evidence_ids: list[UUID] = Field(default_factory=list)

    def is_valid(self, now: datetime | None = None) -> bool:
        current = now or utc_now()
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        issued = self.issued_at
        if issued.tzinfo is None:
            issued = issued.replace(tzinfo=UTC)
        return self.status is PermissionTokenStatus.ACTIVE and issued <= current < expires


class PermissionVerificationContext(BaseModel):
    """Exact context bound by a permission authority before a dangerous action."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    token_id: UUID
    actor_id: str = Field(min_length=1, max_length=200)
    project_id: UUID
    permission: Permission
    resource_type: str = Field(min_length=1, max_length=100)
    resource_id: str = Field(min_length=1, max_length=500)
    session_id: UUID | None = None
    now: datetime = Field(default_factory=utc_now)


class ValidatedPermissionGrant(BaseModel):
    """Non-secret proof that a server-side token matched one exact context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    token_id: UUID
    actor_id: str
    project_id: UUID
    permission: Permission
    resource_type: str
    resource_id: str
    session_id: UUID | None = None
    verified_at: datetime = Field(default_factory=utc_now)


__all__ = [
    "PermissionToken",
    "PermissionTokenStatus",
    "PermissionVerificationContext",
    "ValidatedPermissionGrant",
]
