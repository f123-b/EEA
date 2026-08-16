"""Crash-recoverable project restore coordinator.

The coordinator owns the SQL/filesystem boundary.  The application backup
service owns bounded archive validation and streaming; this adapter owns the
durable journal and authoritative SQL finalization.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from eea_application.backup import (
    BackupOperationError,
    ProjectBackupService,
    RestoreConflictError,
    RestoreStaging,
)
from eea_core.backup import (
    BackupValidationError,
    ProjectBackupManifest,
    RestoreOperationState,
    manifest_from_json,
)
from eea_core.enums import ArtifactStatus
from eea_core.failure_injection import FailureInjectionHarness, FailureInjectionPoint
from eea_core.sandbox import SafePath
from eea_core.source import source_file_manifest, source_manifest_hash
from sqlalchemy import select
from sqlalchemy.orm import Session

from eea_backend.identity_repositories import IdentityRepository
from eea_backend.models import (
    ArtifactRecord,
    ProjectRecord,
    RestoreOperationRecord,
    SourceRevisionRecord,
    SourceWorkspaceRecord,
)
from eea_backend.settings import Settings


@dataclass(frozen=True, slots=True)
class RestoreOutcome:
    manifest: ProjectBackupManifest
    state: RestoreOperationState
    destination: Path
    operation_id: UUID


def _now() -> datetime:
    return datetime.now(UTC)


def _model_from_payload(model: type[Any], payload: dict[str, object]) -> Any:
    columns = {column.name for column in model.__table__.columns}
    values: dict[str, object] = {}
    for column in model.__table__.columns:
        key = "metadata" if column.name == "metadata" else column.name
        if key not in payload:
            continue
        value = payload[key]
        if column.name in {"created_at", "updated_at", "deleted_at"} and isinstance(value, str):
            value = datetime.fromisoformat(value)
        values["entity_metadata" if column.name == "metadata" else column.name] = value
    if "id" not in columns or "id" not in values:
        raise BackupValidationError("project backup record has no stable id")
    return model(**values)


class RestoreCoordinator:
    """Implement a journaled PREPARED → FS_ACTIVATED → ACTIVATED workflow."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        settings: Settings,
        *,
        failure_injector: FailureInjectionHarness | None = None,
    ) -> None:
        self._session_factory = session_factory
        self.settings = settings
        self.failure_injector = failure_injector or FailureInjectionHarness()

    def _backup_service(self) -> ProjectBackupService:
        return ProjectBackupService(profile=self._profile(), failure_injector=self.failure_injector)

    def _profile(self) -> Any:
        from eea_core.capacity import get_capacity_profile

        return get_capacity_profile(self.settings.capacity_profile)

    @staticmethod
    def operation_id(project_id: UUID, manifest_hash: str, requested: UUID | None = None) -> UUID:
        return requested or uuid5(NAMESPACE_URL, f"eea-restore:{project_id}:{manifest_hash}")

    def _destination(self, project_id: UUID) -> Path:
        return Path(self.settings.data_dir).resolve() / "restored" / str(project_id)

    def _set_state(
        self,
        operation_id: UUID,
        state: RestoreOperationState,
        *,
        error_code: str | None = None,
    ) -> None:
        with self._session_factory() as session:
            operation = session.get(RestoreOperationRecord, str(operation_id))
            if operation is None:
                raise BackupOperationError("restore operation journal is missing")
            if operation.state == RestoreOperationState.ACTIVATED.value:
                return
            operation.state = state.value
            operation.error_code = error_code
            operation.updated_at = _now()
            operation.revision += 1
            session.commit()

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BackupValidationError("restore record is unreadable") from exc
        if not isinstance(value, dict):
            raise BackupValidationError("restore record must be an object")
        return value

    def _record_paths(self, manifest: ProjectBackupManifest, prefix: str) -> list[str]:
        return [item.path for item in manifest.objects if item.path.startswith(prefix)]

    def _validate_source_tree(self, staging: Path, manifest: ProjectBackupManifest) -> None:
        source_objects = [item for item in manifest.objects if item.object_type == "source_file"]
        source_paths = [item.path for item in source_objects]
        revision_paths = self._record_paths(manifest, "records/source-revisions/")
        if not source_paths and not revision_paths:
            return
        if not source_paths or not revision_paths:
            raise BackupValidationError(
                "source metadata and source bytes must be restored together"
            )
        revisions = [self._read_json(staging / path) for path in revision_paths]
        matching = [row for row in revisions if row.get("id") == str(manifest.source_revision_id)]
        if manifest.source_revision_id is None or len(matching) != 1:
            raise BackupValidationError("backup source revision binding is incomplete")
        revision = matching[0]
        raw_manifest = revision.get("file_manifest")
        if not isinstance(raw_manifest, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in raw_manifest.items()
        ):
            raise BackupValidationError("source revision file manifest is invalid")
        files: dict[str, bytes] = {}
        guard = SafePath(staging)
        for item in source_objects:
            relative = item.path.removeprefix("source/")
            target = guard.resolve(item.path)
            if not target.is_file() or target.is_symlink():
                raise BackupValidationError("source file is missing from staged restore")
            files[relative] = target.read_bytes()
        actual_manifest = source_file_manifest(files)
        expected_manifest = {str(key): str(value) for key, value in raw_manifest.items()}
        if actual_manifest != expected_manifest:
            raise BackupValidationError("restored source file manifest does not match revision")
        actual_hash = source_manifest_hash(actual_manifest)
        if revision.get("source_manifest_hash") != actual_hash:
            raise BackupValidationError("restored source manifest hash does not match revision")
        if manifest.source_revision_hash != actual_hash:
            raise BackupValidationError("backup source binding hash does not match source bytes")

    def _validate_artifact_bytes(self, staging: Path, manifest: ProjectBackupManifest) -> None:
        for path in self._record_paths(manifest, "records/artifacts/"):
            payload = self._read_json(staging / path)
            artifact_id = str(payload.get("id", ""))
            if not artifact_id:
                raise BackupValidationError("artifact record has no stable id")
            bytes_path = SafePath(staging).resolve(f"artifacts/{artifact_id}.bin")
            if bytes_path.exists():
                if not bytes_path.is_file() or bytes_path.is_symlink():
                    raise BackupValidationError("portable artifact bytes are not a regular file")
                import hashlib

                if hashlib.sha256(bytes_path.read_bytes()).hexdigest() != payload.get(
                    "content_hash"
                ):
                    raise BackupValidationError("portable artifact hash does not match metadata")

    def _create_or_get_operation(
        self,
        operation_id: UUID,
        manifest: ProjectBackupManifest,
        *,
        actor_id: str,
        archive_path: Path,
        staging_path: Path,
        destination: Path,
    ) -> RestoreOperationRecord:
        with self._session_factory() as session:
            existing = session.get(RestoreOperationRecord, str(operation_id))
            if existing is not None:
                if existing.manifest_hash != manifest.manifest_hash or existing.project_id != str(
                    manifest.project_id
                ):
                    raise RestoreConflictError("restore operation identity does not match manifest")
                return existing
            now = _now()
            operation = RestoreOperationRecord(
                id=str(operation_id),
                project_id=str(manifest.project_id),
                manifest_hash=manifest.manifest_hash or "",
                state=RestoreOperationState.STAGED.value,
                staging_path=str(staging_path),
                destination_path=str(destination),
                actor_id=actor_id,
                source_revision_id=(
                    str(manifest.source_revision_id) if manifest.source_revision_id else None
                ),
                source_revision_hash=manifest.source_revision_hash,
                operation_metadata={"archive_path": str(archive_path)},
                error_code=None,
                created_at=now,
                updated_at=now,
                revision=1,
            )
            session.add(operation)
            session.commit()
            return operation

    def _operation(self, operation_id: UUID) -> RestoreOperationRecord | None:
        with self._session_factory() as session:
            return session.get(RestoreOperationRecord, str(operation_id))

    def _finalize_records(
        self, operation: RestoreOperationRecord, manifest: ProjectBackupManifest | None = None
    ) -> None:
        destination = Path(operation.destination_path)
        if manifest is None:
            try:
                manifest = manifest_from_json((destination / "manifest.json").read_bytes())
            except (OSError, ValueError) as exc:
                raise BackupValidationError("activated restore manifest is unreadable") from exc
        self._backup_service().verify_activated_tree(destination, manifest)
        with self._session_factory() as session, session.begin():
            current = session.get(RestoreOperationRecord, operation.id)
            if current is None:
                raise BackupOperationError("restore operation journal is missing")
            if current.state == RestoreOperationState.ACTIVATED.value:
                return
            if current.state != RestoreOperationState.FS_ACTIVATED.value:
                raise BackupOperationError("restore operation is not filesystem activated")
            self._insert_authoritative_records(session, current, destination, manifest)
            current.state = RestoreOperationState.ACTIVATED.value
            current.error_code = None
            current.updated_at = _now()
            current.revision += 1

    def _insert_authoritative_records(
        self,
        session: Session,
        operation: RestoreOperationRecord,
        destination: Path,
        manifest: ProjectBackupManifest,
    ) -> None:
        project_path = destination / "records" / "projects.json"
        project_payload = self._read_json(project_path)
        if project_payload.get("id") != operation.project_id:
            raise RestoreConflictError("project record identity does not match manifest")
        project = session.get(ProjectRecord, operation.project_id)
        if project is None:
            session.add(_model_from_payload(ProjectRecord, project_payload))
        elif project.id != operation.project_id:
            raise RestoreConflictError("restore project identity collision")
        for model, prefix in (
            (SourceRevisionRecord, "records/source-revisions/"),
            (SourceWorkspaceRecord, "records/source-workspaces/"),
            (ArtifactRecord, "records/artifacts/"),
        ):
            for item in manifest.objects:
                if not item.path.startswith(prefix):
                    continue
                payload = self._read_json(destination / item.path)
                if payload.get("project_id") != operation.project_id:
                    raise RestoreConflictError("record project scope does not match manifest")
                record_id = str(payload.get("id", ""))
                if model is SourceWorkspaceRecord:
                    payload["root_path"] = str(destination / "source")
                if model is ArtifactRecord:
                    artifact_bytes = destination / "artifacts" / f"{record_id}.bin"
                    if artifact_bytes.is_file():
                        payload["storage_uri"] = str(artifact_bytes)
                    else:
                        payload["storage_uri"] = f"rebuild://artifact/{record_id}"
                        if payload.get("status") == ArtifactStatus.CURRENT.value:
                            payload["status"] = ArtifactStatus.STALE.value
                if session.get(model, record_id) is None:
                    session.add(_model_from_payload(model, payload))
        identity = IdentityRepository(session).ensure_local_user(commit=False)
        IdentityRepository(session).ensure_project_owner(
            UUID(operation.project_id), identity, commit=False
        )
        session.flush()

    def restore(
        self,
        archive_path: Path,
        *,
        project_id: UUID,
        actor_id: str,
        authorize: Callable[[UUID, str], bool],
        requested_operation_id: UUID | None = None,
    ) -> RestoreOutcome:
        service = self._backup_service()
        manifest = service.validate_archive(archive_path)
        if manifest.project_id != project_id:
            raise RestoreConflictError("backup project does not match authorized project")
        operation_id = self.operation_id(
            project_id, manifest.manifest_hash or "", requested_operation_id
        )
        destination = self._destination(project_id)
        staging = destination.with_name(f".{destination.name}.{operation_id}.staging")
        existing = self._operation(operation_id)
        if existing is not None and existing.state == RestoreOperationState.ACTIVATED.value:
            return RestoreOutcome(
                manifest, RestoreOperationState.ACTIVATED, destination, operation_id
            )
        if existing is None:
            if destination.exists():
                raise RestoreConflictError(
                    "restore destination collision requires replacement policy"
                )
            existing = self._create_or_get_operation(
                operation_id,
                manifest,
                actor_id=actor_id,
                archive_path=archive_path,
                staging_path=staging,
                destination=destination,
            )
            # The SQLAlchemy row is detached after its commit; reload it before
            # inspecting state so restore decisions never depend on expired ORM
            # attributes.
            existing = self._operation(operation_id)
            if existing is None:
                raise BackupOperationError("restore operation journal could not be reloaded")
        if existing.state == RestoreOperationState.STAGED.value:
            if staging.exists():
                service.verify_activated_tree(staging, manifest)
                staged = RestoreStaging(manifest, staging, destination)
            else:
                staged = service.stage_project(
                    archive_path,
                    destination,
                    authorized_project_id=project_id,
                    actor_id=actor_id,
                    authorize=authorize,
                    staging=staging,
                )
            self._validate_source_tree(staged.staging, manifest)
            self._validate_artifact_bytes(staged.staging, manifest)
            self._set_state(operation_id, RestoreOperationState.PREPARED)
            self.failure_injector.inject(FailureInjectionPoint.RESTORE_AFTER_PREPARE_COMMIT)
        current = self._operation(operation_id)
        if current is None:
            raise BackupOperationError("restore operation journal disappeared")
        if current.state == RestoreOperationState.PREPARED.value:
            if destination.exists():
                service.verify_activated_tree(destination, manifest)
            else:
                service.activate_staged(Path(current.staging_path), destination)
            self._set_state(operation_id, RestoreOperationState.FS_ACTIVATED)
            self.failure_injector.inject(FailureInjectionPoint.RESTORE_AFTER_FS_ACTIVATE)
        current = self._operation(operation_id)
        if current is None or current.state != RestoreOperationState.FS_ACTIVATED.value:
            if current is not None and current.state == RestoreOperationState.ACTIVATED.value:
                return RestoreOutcome(
                    manifest, RestoreOperationState.ACTIVATED, destination, operation_id
                )
            raise BackupOperationError("restore did not reach filesystem activation")
        self.failure_injector.inject(FailureInjectionPoint.RESTORE_BEFORE_DB_FINALIZE)
        try:
            self._finalize_records(current, manifest)
        except Exception:
            with self._session_factory() as session:
                row = session.get(RestoreOperationRecord, str(operation_id))
                if row is not None and row.state != RestoreOperationState.ACTIVATED.value:
                    row.error_code = "FINALIZE_FAILED"
                    row.updated_at = _now()
                    session.commit()
            raise
        self.failure_injector.inject(FailureInjectionPoint.RESTORE_AFTER_DB_FINALIZE)
        return RestoreOutcome(manifest, RestoreOperationState.ACTIVATED, destination, operation_id)

    def recover_pending(self, *, limit: int = 100) -> dict[str, int]:
        summary = {"recovered": 0, "failed": 0, "quarantined": 0}
        with self._session_factory() as session:
            operations = list(
                session.scalars(
                    select(RestoreOperationRecord)
                    .where(
                        RestoreOperationRecord.state.in_(
                            [
                                RestoreOperationState.STAGED.value,
                                RestoreOperationState.PREPARED.value,
                                RestoreOperationState.FS_ACTIVATED.value,
                            ]
                        )
                    )
                    .order_by(RestoreOperationRecord.created_at)
                    .limit(limit)
                )
            )
        for operation in operations:
            try:
                self._recover_one(operation)
                summary["recovered"] += 1
            except BackupValidationError:
                self._set_state(
                    UUID(operation.id),
                    RestoreOperationState.ROLLBACK_REQUIRED,
                    error_code="RESTORE_INCONSISTENT",
                )
                summary["quarantined"] += 1
            except Exception:
                with self._session_factory() as session:
                    row = session.get(RestoreOperationRecord, operation.id)
                    if row is not None:
                        row.error_code = "RECOVERY_FAILED"
                        row.updated_at = _now()
                        session.commit()
                summary["failed"] += 1
        return summary

    def _recover_one(self, operation: RestoreOperationRecord) -> None:
        operation_id = UUID(operation.id)
        destination = Path(operation.destination_path)
        staging = Path(operation.staging_path)
        service = self._backup_service()
        manifest_root = destination if destination.exists() else staging
        try:
            manifest = manifest_from_json((manifest_root / "manifest.json").read_bytes())
        except (OSError, ValueError) as exc:
            raise BackupValidationError("restore recovery manifest is unreadable") from exc
        if operation.state == RestoreOperationState.STAGED.value:
            if not staging.exists() and not destination.exists():
                raise BackupOperationError("staged restore has no recoverable filesystem input")
            if staging.exists() and not destination.exists():
                service.verify_activated_tree(staging, manifest)
                self._validate_source_tree(staging, manifest)
                self._validate_artifact_bytes(staging, manifest)
                service.activate_staged(staging, destination)
            elif staging.exists() and destination.exists():
                raise BackupValidationError("staging and destination both exist")
            self._set_state(operation_id, RestoreOperationState.FS_ACTIVATED)
        elif operation.state == RestoreOperationState.PREPARED.value:
            if staging.exists() and destination.exists():
                raise BackupValidationError("prepared restore has two activation trees")
            if staging.exists():
                service.verify_activated_tree(staging, manifest)
                self._validate_source_tree(staging, manifest)
                self._validate_artifact_bytes(staging, manifest)
                service.activate_staged(staging, destination)
            elif not destination.exists():
                raise BackupValidationError("prepared restore has no activation tree")
            else:
                service.verify_activated_tree(destination, manifest)
            self._set_state(operation_id, RestoreOperationState.FS_ACTIVATED)
        current = self._operation(operation_id)
        if current is None or current.state != RestoreOperationState.FS_ACTIVATED.value:
            return
        service.verify_activated_tree(destination, manifest)
        self._validate_source_tree(destination, manifest)
        self._validate_artifact_bytes(destination, manifest)
        self._finalize_records(current, manifest)


__all__ = ["RestoreCoordinator", "RestoreOutcome"]
