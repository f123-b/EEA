"""Application contract for exclusive, lease-based resource ownership."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from eea_core.hardware import ResourceLock, ResourceType


class ResourceLockRepository(Protocol):
    def acquire_lock(
        self,
        *,
        project_id: UUID,
        resource_type: ResourceType,
        resource_id: str,
        owner_session: UUID | None,
        owner_job_id: UUID | None = None,
        lease_seconds: int = 30,
    ) -> ResourceLock | None: ...

    def get_lock(self, lock_id: UUID) -> ResourceLock | None: ...

    def heartbeat_lock(
        self, lock_id: UUID, *, owner_session: UUID, lease_seconds: int = 30
    ) -> bool: ...

    def release_lock(self, lock_id: UUID, *, owner_session: UUID) -> bool: ...

    def quarantine_lock(self, lock_id: UUID, *, commit: bool = False) -> bool: ...

    def commit(self) -> None: ...


class ResourceLockService:
    """The only normal application path for commissioning resource ownership."""

    def __init__(self, repository: ResourceLockRepository) -> None:
        self.repository = repository

    def acquire(
        self,
        *,
        project_id: UUID,
        resource_type: ResourceType,
        resource_id: str,
        owner_session: UUID | None,
        owner_job_id: UUID | None = None,
        lease_seconds: int = 30,
    ) -> ResourceLock:
        lock = self.repository.acquire_lock(
            project_id=project_id,
            resource_type=resource_type,
            resource_id=resource_id,
            owner_session=owner_session,
            owner_job_id=owner_job_id,
            lease_seconds=lease_seconds,
        )
        if lock is None:
            raise ValueError("resource is already exclusively owned")
        self.repository.commit()
        return lock

    def validate(
        self,
        lock_id: UUID,
        *,
        project_id: UUID,
        resource_type: ResourceType,
        resource_id: str,
        owner_session: UUID,
    ) -> ResourceLock:
        lock = self.repository.get_lock(lock_id)
        if (
            lock is None
            or lock.project_id != project_id
            or lock.resource_type is not resource_type
            or lock.resource_id != resource_id
            or lock.owner_session != owner_session
            or not lock.is_active()
        ):
            raise ValueError("resource lock is not valid for this owner and resource")
        return lock

    def heartbeat(self, lock_id: UUID, *, owner_session: UUID, lease_seconds: int = 30) -> None:
        if not self.repository.heartbeat_lock(
            lock_id, owner_session=owner_session, lease_seconds=lease_seconds
        ):
            raise ValueError("resource lock heartbeat rejected")
        self.repository.commit()

    def release(self, lock_id: UUID, *, owner_session: UUID) -> None:
        if not self.repository.release_lock(lock_id, owner_session=owner_session):
            raise ValueError("resource lock release rejected")
        self.repository.commit()

    def quarantine(self, lock_id: UUID) -> None:
        if not self.repository.quarantine_lock(lock_id, commit=False):
            raise ValueError("resource lock quarantine rejected")
        self.repository.commit()


__all__ = ["ResourceLockRepository", "ResourceLockService"]
