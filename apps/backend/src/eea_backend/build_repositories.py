"""SQLAlchemy persistence adapter for M12 BuildInputSnapshot and BuildRun."""

from typing import Any, cast
from uuid import UUID

from eea_core.build import BuildRun
from eea_core.source import BuildInputSnapshot
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from eea_backend.models import BuildInputSnapshotRecord, BuildRunRecord


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


class SqlAlchemyBuildRunRepository:
    """Persist each build with its exact input snapshot."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self, snapshot: BuildInputSnapshot, build: BuildRun, *, commit: bool = True
    ) -> BuildRun:
        self._session.add(
            BuildInputSnapshotRecord(
                id=str(snapshot.id),
                schema_version=snapshot.schema_version,
                revision=snapshot.revision,
                created_at=snapshot.created_at,
                updated_at=snapshot.updated_at,
                entity_metadata=snapshot.metadata,
                project_id=str(snapshot.project_id),
                source_revision_id=str(snapshot.source_revision_id),
                tracked_file_manifest_hash=snapshot.tracked_file_manifest_hash,
                allowed_untracked_input_hash=snapshot.allowed_untracked_input_hash,
                generated_input_hash=snapshot.generated_input_hash,
                submodule_commit_map=snapshot.submodule_commit_map,
                build_config_hash=snapshot.build_config_hash,
                build_profile=snapshot.build_profile.value,
                toolchain_id=snapshot.toolchain_id,
                toolchain_version=snapshot.toolchain_version,
                environment_profile_hash=snapshot.environment_profile_hash,
                source_manifest_hash=snapshot.source_manifest_hash,
                dependency_lock_hash=snapshot.dependency_lock_hash,
                component_manifest_hash=snapshot.component_manifest_hash,
                toolchain_manifest_hash=snapshot.toolchain_manifest_hash,
                build_input_hash=snapshot.build_input_hash,
            )
        )
        serialized = build.model_dump(mode="json")
        self._session.add(
            BuildRunRecord(
                id=str(build.id),
                schema_version=build.schema_version,
                revision=build.revision,
                created_at=build.created_at,
                updated_at=build.updated_at,
                entity_metadata=build.metadata,
                project_id=str(build.project_id),
                firmware_id=str(build.firmware_id),
                firmware_revision=build.firmware_revision,
                source_revision_id=str(build.source_revision_id),
                build_input_snapshot_id=str(build.build_input_snapshot_id),
                status=build.status.value,
                profile=build.profile.value,
                toolchain_id=build.toolchain_id,
                toolchain_version=build.toolchain_version,
                environment_profile_hash=build.environment_profile_hash,
                build_input_hash=build.build_input_hash,
                command=build.command,
                diagnostics=cast(list[dict[str, Any]], serialized["diagnostics"]),
                stdout=build.stdout,
                stderr=build.stderr,
                artifact_hash=build.artifact_hash,
                error_code=build.error_code.value if build.error_code else None,
                duration_ms=build.duration_ms,
            )
        )
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        return self.get(build.id, project_id=build.project_id) or build

    def get(self, build_id: UUID, *, project_id: UUID | None = None) -> BuildRun | None:
        statement = select(BuildRunRecord).where(BuildRunRecord.id == str(build_id))
        if project_id is not None:
            statement = statement.where(BuildRunRecord.project_id == str(project_id))
        record = self._session.scalar(statement)
        return self._to_build(record) if record else None

    def list_for_project(self, project_id: UUID) -> list[BuildRun]:
        statement = (
            select(BuildRunRecord)
            .where(BuildRunRecord.project_id == str(project_id))
            .order_by(desc(BuildRunRecord.created_at), desc(BuildRunRecord.id))
        )
        return [self._to_build(record) for record in self._session.scalars(statement)]

    @staticmethod
    def _to_build(record: BuildRunRecord) -> BuildRun:
        return BuildRun.model_validate(
            {
                **_entity_kwargs(record),
                "project_id": UUID(record.project_id),
                "firmware_id": UUID(record.firmware_id),
                "firmware_revision": record.firmware_revision,
                "source_revision_id": UUID(record.source_revision_id),
                "build_input_snapshot_id": UUID(record.build_input_snapshot_id),
                "status": record.status,
                "profile": record.profile or "HOST_SMOKE",
                "toolchain_id": record.toolchain_id,
                "toolchain_version": record.toolchain_version,
                "environment_profile_hash": record.environment_profile_hash,
                "build_input_hash": record.build_input_hash,
                "command": record.command,
                "diagnostics": record.diagnostics,
                "stdout": record.stdout,
                "stderr": record.stderr,
                "artifact_hash": record.artifact_hash,
                "error_code": record.error_code,
                "duration_ms": record.duration_ms,
            }
        )


__all__ = ["SqlAlchemyBuildRunRepository"]
