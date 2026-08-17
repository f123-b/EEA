"""SQLAlchemy persistence for ESCR descriptors, releases, locks and materializations."""

from typing import Any, cast
from uuid import UUID

from eea_core.components import (
    ComponentMaterialization,
    ComponentRelease,
    DependencyLock,
    SoftwareComponentDescriptor,
)
from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from eea_backend.models import (
    ComponentMaterializationRecord,
    ComponentReleaseRecord,
    DependencyLockComponentRecord,
    DependencyLockRecord,
    SoftwareComponentRecord,
)


def _entity_kwargs(record: object) -> dict[str, Any]:
    typed = cast(Any, record)
    return {
        "id": UUID(typed.id),
        "schema_version": typed.schema_version,
        "revision": typed.revision,
        "created_at": typed.created_at,
        "updated_at": typed.updated_at,
        "metadata": typed.entity_metadata,
    }


def _to_descriptor(record: SoftwareComponentRecord) -> SoftwareComponentDescriptor:
    return SoftwareComponentDescriptor.model_validate(
        {
            **_entity_kwargs(record),
            "component_key": record.component_key,
            "name": record.name,
            "vendor": record.vendor,
            "role": record.role,
            "authority": record.authority,
            "provider_id": record.provider_id,
            "source_type": record.source_type,
            "source_uri": record.source_uri,
            "capabilities": record.capabilities,
            "compatibility": record.compatibility,
            "license_expression": record.license_expression,
            "license_text_hash": record.license_text_hash,
            "dependencies": record.dependencies,
            "production_eligible": record.production_eligible,
            "reference_only": record.reference_only,
        }
    )


def _to_release(record: ComponentReleaseRecord) -> ComponentRelease:
    return ComponentRelease.model_validate(
        {
            **_entity_kwargs(record),
            "component_id": UUID(record.component_id),
            "version": record.version,
            "revision_kind": record.revision_kind,
            "source_revision": record.source_revision,
            "manifest_hash": record.manifest_hash,
            "content_hash": record.content_hash,
            "files": record.files,
            "submodule_commit_map": record.submodule_commit_map,
            "source_uri": record.source_uri,
            "yanked": record.yanked,
            "verified": record.verified,
        }
    )


class SqlAlchemyComponentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_descriptor(
        self, descriptor: SoftwareComponentDescriptor, *, commit: bool = True
    ) -> SoftwareComponentDescriptor:
        self._session.add(
            SoftwareComponentRecord(
                id=str(descriptor.id),
                schema_version=descriptor.schema_version,
                revision=descriptor.revision,
                created_at=descriptor.created_at,
                updated_at=descriptor.updated_at,
                entity_metadata=descriptor.metadata,
                component_key=descriptor.component_key,
                name=descriptor.name,
                vendor=descriptor.vendor,
                role=descriptor.role.value,
                authority=descriptor.authority.value,
                provider_id=descriptor.provider_id,
                source_type=descriptor.source_type.value,
                source_uri=descriptor.source_uri,
                capabilities=descriptor.capabilities,
                compatibility=descriptor.compatibility.model_dump(mode="json"),
                license_expression=descriptor.license_expression,
                license_text_hash=descriptor.license_text_hash,
                dependencies=[item.model_dump(mode="json") for item in descriptor.dependencies],
                production_eligible=descriptor.production_eligible,
                reference_only=descriptor.reference_only,
            )
        )
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        return descriptor

    def add_release(self, release: ComponentRelease, *, commit: bool = True) -> ComponentRelease:
        self._session.add(
            ComponentReleaseRecord(
                id=str(release.id),
                schema_version=release.schema_version,
                revision=release.revision,
                created_at=release.created_at,
                updated_at=release.updated_at,
                entity_metadata=release.metadata,
                component_id=str(release.component_id),
                version=release.version,
                revision_kind=release.revision_kind.value,
                source_revision=release.source_revision,
                manifest_hash=release.manifest_hash,
                content_hash=release.content_hash,
                files=release.files,
                submodule_commit_map=release.submodule_commit_map,
                source_uri=release.source_uri,
                yanked=release.yanked,
                verified=release.verified,
            )
        )
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        return release

    def list_descriptors(self) -> list[SoftwareComponentDescriptor]:
        return [
            _to_descriptor(record)
            for record in self._session.scalars(
                select(SoftwareComponentRecord).order_by(SoftwareComponentRecord.component_key)
            )
        ]

    def get(self, component_key: str) -> SoftwareComponentDescriptor | None:
        record = self._session.scalar(
            select(SoftwareComponentRecord).where(
                SoftwareComponentRecord.component_key == component_key
            )
        )
        return _to_descriptor(record) if record else None

    def releases(self, component_id: UUID) -> list[ComponentRelease]:
        return [
            _to_release(record)
            for record in self._session.scalars(
                select(ComponentReleaseRecord)
                .where(ComponentReleaseRecord.component_id == str(component_id))
                .order_by(desc(ComponentReleaseRecord.version))
            )
        ]

    def get_release(self, release_id: UUID) -> ComponentRelease | None:
        record = self._session.scalar(
            select(ComponentReleaseRecord).where(ComponentReleaseRecord.id == str(release_id))
        )
        return _to_release(record) if record else None

    def sync_provider_catalog(self, providers: list[object]) -> None:
        """Persist provider descriptors/releases before creating FK-backed locks.

        Providers are the authoritative source for immutable catalog data, while
        dependency locks and materializations reference the SQL rows.  Syncing is
        idempotent and deliberately rejects a changed descriptor or release rather
        than overwriting an existing catalog record.
        """
        for provider in providers:
            typed = cast(Any, provider)
            for descriptor in typed.descriptors():
                existing_descriptor = self.get(descriptor.component_key)
                if existing_descriptor is None:
                    self.add_descriptor(descriptor, commit=False)
                elif existing_descriptor.model_dump(mode="json") != descriptor.model_dump(
                    mode="json"
                ):
                    raise EngineeringError(
                        EngineeringErrorCode.DEPENDENCY_CONFLICT,
                        "Component catalog conflict for an immutable provider descriptor.",
                        details={"component_key": descriptor.component_key},
                    )
                for release in typed.releases(descriptor.id):
                    existing_release = self.get_release(release.id)
                    if existing_release is None:
                        self.add_release(release, commit=False)
                    elif existing_release.model_dump(mode="json") != release.model_dump(
                        mode="json"
                    ):
                        raise EngineeringError(
                            EngineeringErrorCode.DEPENDENCY_CONFLICT,
                            "Component release conflict for an immutable provider release.",
                            details={"release_id": str(release.id)},
                        )
        self._session.flush()


class SqlAlchemyDependencyLockRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, lock: DependencyLock, *, commit: bool = True) -> DependencyLock:
        existing_record = self._session.scalar(
            select(DependencyLockRecord).where(
                DependencyLockRecord.project_id == str(lock.project_id),
                DependencyLockRecord.lock_hash == lock.lock_hash,
            )
        )
        if existing_record is not None:
            existing = self.get(UUID(existing_record.id), project_id=lock.project_id)
            if existing is not None:
                return existing
        self._session.add(
            DependencyLockRecord(
                id=str(lock.id),
                schema_version=lock.schema_version,
                revision=lock.revision,
                created_at=lock.created_at,
                updated_at=lock.updated_at,
                entity_metadata=lock.metadata,
                project_id=str(lock.project_id),
                mcu_config_id=str(lock.mcu_config_id),
                mcu_config_revision=lock.mcu_config_revision,
                requirements=[item.model_dump(mode="json") for item in lock.requirements],
                resolved_components=[
                    item.model_dump(mode="json") for item in lock.resolved_components
                ],
                resolution_policy_version=lock.resolution_policy_version,
                resolver_version=lock.resolver_version,
                lock_hash=lock.lock_hash,
                status=lock.status.value,
            )
        )
        self._session.flush()
        for item in lock.resolved_components:
            self._session.add(
                DependencyLockComponentRecord(
                    id=str(UUID(int=(item.release_id.int ^ lock.id.int) % (1 << 128))),
                    schema_version="1.0",
                    revision=1,
                    created_at=lock.created_at,
                    updated_at=lock.updated_at,
                    entity_metadata={},
                    project_id=str(lock.project_id),
                    dependency_lock_id=str(lock.id),
                    component_id=str(item.component_id),
                    release_id=str(item.release_id),
                    component_key=item.component_key,
                    version=item.version,
                    component_revision=item.revision,
                    manifest_hash=item.manifest_hash,
                    content_hash=item.content_hash,
                )
            )
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        return self.get(lock.id, project_id=lock.project_id) or lock

    def get(self, lock_id: UUID, *, project_id: UUID | None = None) -> DependencyLock | None:
        statement = select(DependencyLockRecord).where(DependencyLockRecord.id == str(lock_id))
        if project_id is not None:
            statement = statement.where(DependencyLockRecord.project_id == str(project_id))
        record = self._session.scalar(statement)
        if record is None:
            return None
        return DependencyLock.model_validate(
            {
                **_entity_kwargs(record),
                "project_id": UUID(record.project_id),
                "mcu_config_id": UUID(record.mcu_config_id),
                "mcu_config_revision": record.mcu_config_revision,
                "requirements": record.requirements,
                "resolved_components": record.resolved_components,
                "resolution_policy_version": record.resolution_policy_version,
                "resolver_version": record.resolver_version,
                "lock_hash": record.lock_hash,
                "status": record.status,
            }
        )

    def latest_for_project(self, project_id: UUID) -> DependencyLock | None:
        record = self._session.scalar(
            select(DependencyLockRecord)
            .where(DependencyLockRecord.project_id == str(project_id))
            .order_by(desc(DependencyLockRecord.created_at), desc(DependencyLockRecord.id))
            .limit(1)
        )
        return self.get(UUID(record.id), project_id=project_id) if record else None


class SqlAlchemyComponentMaterializationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self, materialization: ComponentMaterialization, *, commit: bool = True
    ) -> ComponentMaterialization:
        self._session.add(
            ComponentMaterializationRecord(
                id=str(materialization.id),
                schema_version=materialization.schema_version,
                revision=materialization.revision,
                created_at=materialization.created_at,
                updated_at=materialization.updated_at,
                entity_metadata=materialization.metadata,
                project_id=str(materialization.project_id),
                component_id=str(materialization.component_id),
                release_id=str(materialization.release_id),
                owner=materialization.owner,
                cache_key=materialization.cache_key,
                manifest_hash=materialization.manifest_hash,
                content_hash=materialization.content_hash,
                storage_uri=materialization.storage_uri,
                status=materialization.status.value,
                network_used=materialization.network_used,
            )
        )
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        return materialization


__all__ = [
    "SqlAlchemyComponentMaterializationRepository",
    "SqlAlchemyComponentRepository",
    "SqlAlchemyDependencyLockRepository",
]
