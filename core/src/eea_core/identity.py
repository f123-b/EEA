"""Stable, Core-neutral identity and project-role contracts."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field


class IdentityMode(StrEnum):
    LOCAL_SINGLE_USER = "LOCAL_SINGLE_USER"
    TEAM = "TEAM"


class ProjectRole(StrEnum):
    OWNER = "OWNER"
    MAINTAINER = "MAINTAINER"
    ENGINEER = "ENGINEER"
    VIEWER = "VIEWER"


class UserIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    stable_actor_id: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    mode: IdentityMode


class Organization(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    stable_key: str = Field(min_length=1, max_length=200, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    display_name: str = Field(min_length=1, max_length=200)


class Membership(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    organization_id: UUID
    user_id: UUID
    role: ProjectRole


class ProjectRoleAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    project_id: UUID
    user_id: UUID
    role: ProjectRole


LOCAL_USER_NAMESPACE = UUID("f7df9e8a-75f7-5a9c-a3b9-0500c6cc2277")


def local_single_user() -> UserIdentity:
    """Return the same auditable local actor on every process launch."""

    identity_id = uuid5(LOCAL_USER_NAMESPACE, "eea-local-single-user")
    return UserIdentity(
        id=identity_id,
        stable_actor_id="local:single-user",
        display_name="Local User",
        mode=IdentityMode.LOCAL_SINGLE_USER,
    )


__all__ = [
    "IdentityMode",
    "Membership",
    "Organization",
    "ProjectRole",
    "ProjectRoleAssignment",
    "UserIdentity",
    "local_single_user",
]
