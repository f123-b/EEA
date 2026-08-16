"""M18E reliability, backup, identity and renderer-policy API routes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any, cast
from uuid import UUID

from eea_adapters.source import FileSystemSourceWorkspaceAdapter
from eea_application.backup import (
    BackupOperationError,
    BackupRecord,
    ProjectBackupService,
    RestoreConflictError,
    RestoreState,
)
from eea_core.backup import (
    BackupSecretPolicy,
    BackupValidationError,
    ProjectBackupManifest,
    canonical_json,
)
from eea_core.capacity import CAPACITY_PROFILES, get_capacity_profile
from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_core.renderer_security import default_renderer_csp
from eea_core.source import source_file_manifest, source_manifest_hash
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from eea_backend.identity_repositories import IdentityRepository
from eea_backend.models import (
    ArtifactRecord,
    ProjectRecord,
    SourceRevisionRecord,
    SourceWorkspaceRecord,
)
from eea_backend.restore_service import RestoreCoordinator
from eea_backend.schemas import (
    ApiEnvelope,
    BackupExportData,
    BackupExportRequest,
    CapacityProfileData,
    LocalIdentityData,
    RestoreData,
    RestoreValidateRequest,
)
from eea_backend.security import authenticated_actor_id

router = APIRouter()


def _session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


SessionDependency = Annotated[Session, Depends(_session)]

_SOURCE_CREDENTIAL_FILENAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.development",
        ".env.production",
        "credentials.json",
        "credentials.yaml",
        "credentials.yml",
        "secrets.json",
        "secrets.yaml",
        "secrets.yml",
        "id_rsa",
        "id_ed25519",
    }
)
_SOURCE_CREDENTIAL_SUFFIXES = frozenset({".key", ".pem", ".p12", ".pfx"})


def _is_source_credential_file(relative: str) -> bool:
    name = Path(relative.replace("\\", "/")).name.lower()
    return name in _SOURCE_CREDENTIAL_FILENAMES or Path(name).suffix in _SOURCE_CREDENTIAL_SUFFIXES


def _request_id(request: Request) -> str:
    return str(request.state.request_id)


def _safe_data_path(request: Request, raw: str | None, default_name: str) -> Path:
    root = Path(request.app.state.settings.data_dir).resolve()
    supplied = Path(raw) if raw else Path("exports") / default_name
    candidate = (supplied if supplied.is_absolute() else root / supplied).resolve()
    if root not in candidate.parents and candidate != root:
        raise EngineeringError(
            EngineeringErrorCode.BACKUP_INVALID, "archive path escapes data directory"
        )
    return candidate


def _record_payload(record: Any) -> bytes:
    table = record.__table__
    payload: dict[str, object] = {}
    for column in table.columns:
        attribute = "entity_metadata" if column.name == "metadata" else column.name
        payload[column.name] = getattr(record, attribute)
    BackupSecretPolicy.assert_safe(payload)
    return canonical_json(json.loads(json.dumps(payload, default=str)))


def _backup_service(request: Request) -> ProjectBackupService:
    try:
        profile = get_capacity_profile(request.app.state.settings.capacity_profile)
    except (KeyError, ValueError) as exc:
        raise EngineeringError(
            EngineeringErrorCode.BACKUP_INVALID, "configured backup capacity profile is invalid"
        ) from exc
    return ProjectBackupService(profile=profile)


def _project_records(session: Session, project_id: UUID) -> tuple[BackupRecord, ...]:
    project = session.get(ProjectRecord, str(project_id))
    if project is None:
        raise EngineeringError(EngineeringErrorCode.PROJECT_NOT_FOUND, "project was not found")
    records: list[BackupRecord] = [
        BackupRecord("records/projects.json", _record_payload(project), "project")
    ]
    for model, directory, object_type in (
        (ArtifactRecord, "records/artifacts", "artifact"),
        (SourceRevisionRecord, "records/source-revisions", "source_revision"),
        (SourceWorkspaceRecord, "records/source-workspaces", "source_workspace"),
    ):
        rows = session.scalars(select(model).where(model.project_id == str(project_id))).all()
        for row in rows:
            row_with_id = cast(Any, row)
            records.append(
                BackupRecord(
                    f"{directory}/{row_with_id.id}.json", _record_payload(row), object_type
                )
            )
            if model is ArtifactRecord:
                storage_uri = Path(str(row_with_id.storage_uri))
                if storage_uri.is_file() and not storage_uri.is_symlink():
                    content = storage_uri.read_bytes()
                    if hashlib.sha256(content).hexdigest() != row_with_id.content_hash:
                        raise BackupValidationError(
                            "portable artifact content hash does not match metadata"
                        )
                    records.append(
                        BackupRecord(
                            f"artifacts/{row_with_id.id}.bin",
                            content,
                            "artifact_bytes",
                        )
                    )
    workspace = session.scalar(
        select(SourceWorkspaceRecord).where(SourceWorkspaceRecord.project_id == str(project_id))
    )
    if workspace is not None:
        files = dict(FileSystemSourceWorkspaceAdapter(Path(workspace.root_path)).list_files())
        revision = (
            session.get(SourceRevisionRecord, workspace.current_source_revision_id)
            if workspace.current_source_revision_id
            else None
        )
        if files and revision is None:
            raise BackupValidationError(
                "source bytes exist without an authoritative source revision"
            )
        if revision is not None:
            actual_manifest = source_file_manifest(files)
            if (
                actual_manifest != revision.file_manifest
                or source_manifest_hash(actual_manifest) != revision.source_manifest_hash
            ):
                raise BackupValidationError("source bytes do not match SourceRevision authority")
            for relative, content in sorted(files.items()):
                if _is_source_credential_file(relative):
                    raise BackupValidationError(
                        "source credential files are excluded from project backups"
                    )
                records.append(BackupRecord(f"source/{relative}", content, "source_file"))
    return tuple(records)


def _source_binding(session: Session, project_id: UUID) -> tuple[UUID | None, str | None]:
    workspace = session.scalar(
        select(SourceWorkspaceRecord).where(SourceWorkspaceRecord.project_id == str(project_id))
    )
    if workspace is None or workspace.current_source_revision_id is None:
        return None, None
    revision = session.get(SourceRevisionRecord, workspace.current_source_revision_id)
    if revision is None:
        return None, None
    return UUID(revision.id), revision.source_manifest_hash


@router.get("/identity/local", response_model=ApiEnvelope[LocalIdentityData], tags=["m18e"])
def local_identity(request: Request, session: SessionDependency) -> ApiEnvelope[LocalIdentityData]:
    identity = IdentityRepository(session).ensure_local_user()
    return ApiEnvelope(
        data=LocalIdentityData(
            id=identity.id,
            stable_actor_id=identity.stable_actor_id,
            display_name=identity.display_name,
            mode=identity.mode.value,
        ),
        request_id=_request_id(request),
    )


@router.get(
    "/capacity/profiles", response_model=ApiEnvelope[list[CapacityProfileData]], tags=["m18e"]
)
def capacity_profiles(request: Request) -> ApiEnvelope[list[CapacityProfileData]]:
    data = [
        CapacityProfileData(
            name=profile.name.value,
            version=profile.version,
            limits={
                "project_file_count": profile.maximum_project_file_count,
                "repository_bytes": profile.maximum_repository_bytes,
                "document_bytes": profile.maximum_document_bytes,
                "document_pages": profile.maximum_document_pages,
                "concurrent_jobs": profile.maximum_concurrent_jobs,
                "vector_entries": profile.maximum_vector_entries,
                "log_retention_days": profile.maximum_log_retention_days,
                "object_quota_bytes": profile.maximum_object_quota_bytes,
                "single_tool_runtime_seconds": profile.maximum_single_tool_runtime_seconds,
            },
        )
        for profile in CAPACITY_PROFILES.values()
    ]
    return ApiEnvelope(data=data, request_id=_request_id(request))


@router.get(
    "/renderer/security-policy", response_model=ApiEnvelope[dict[str, object]], tags=["m18e"]
)
def renderer_security_policy(request: Request) -> ApiEnvelope[dict[str, object]]:
    return ApiEnvelope(
        data={
            "csp": default_renderer_csp(),
            "remote_javascript_allowed": False,
            "remote_navigation_allowed": False,
            "external_link_isolation": "system_browser",
            "token_exposure": "forbidden",
        },
        request_id=_request_id(request),
    )


@router.post(
    "/projects/{project_id}/exports", response_model=ApiEnvelope[BackupExportData], tags=["m18e"]
)
def export_project(
    project_id: UUID,
    payload: BackupExportRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[BackupExportData]:
    actor = authenticated_actor_id(request)
    identity = IdentityRepository(session).ensure_local_user()
    if actor not in {
        identity.stable_actor_id,
        "local-authenticated-session",
        "configured-authenticated-session",
    }:
        raise EngineeringError(
            EngineeringErrorCode.PERMISSION_REQUIRED, "export actor is not authorized"
        )
    target = _safe_data_path(request, payload.destination, f"{project_id}.eea.zip")
    records = _project_records(session, project_id)
    IdentityRepository(session).ensure_project_owner(project_id, identity)
    source_revision_id, source_revision_hash = _source_binding(session, project_id)
    try:
        manifest = _backup_service(request).export_project(
            project_id,
            target,
            records,
            source_revision_id=source_revision_id,
            source_revision_hash=source_revision_hash,
            schema_versions={"0031_m18e_renderer_nfr_hardening": "1"},
        )
    except (BackupOperationError, BackupValidationError, OSError, ValueError) as exc:
        raise EngineeringError(
            EngineeringErrorCode.BACKUP_INVALID, "project export failed"
        ) from exc
    return ApiEnvelope(
        data=BackupExportData(
            archive_path=str(target),
            manifest_hash=manifest.manifest_hash or "",
            object_count=len(manifest.objects),
            project_id=project_id,
        ),
        request_id=_request_id(request),
    )


def _read_manifest(path: Path, service: ProjectBackupService) -> ProjectBackupManifest:
    try:
        return service.validate_archive(path)
    except (OSError, ValueError, BackupValidationError, BackupOperationError) as exc:
        raise EngineeringError(EngineeringErrorCode.BACKUP_INVALID, "backup is invalid") from exc


@router.post("/projects/restore/validate", response_model=ApiEnvelope[RestoreData], tags=["m18e"])
def validate_restore(
    payload: RestoreValidateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[RestoreData]:
    del session
    actor = authenticated_actor_id(request)
    if not actor:
        raise EngineeringError(EngineeringErrorCode.AUTH_REQUIRED, "restore actor is missing")
    path = _safe_data_path(request, payload.archive_path, "restore.eea.zip")
    manifest = _read_manifest(path, _backup_service(request))
    if manifest.project_id != payload.project_id:
        raise EngineeringError(EngineeringErrorCode.RESTORE_CONFLICT, "backup project mismatch")
    return ApiEnvelope(
        data=RestoreData(
            valid=True,
            state=RestoreState.VALIDATED.value,
            manifest_hash=manifest.manifest_hash or "",
            project_id=manifest.project_id,
            object_count=len(manifest.objects),
        ),
        request_id=_request_id(request),
    )


@router.post("/projects/restore", response_model=ApiEnvelope[RestoreData], tags=["m18e"])
def restore_project(
    payload: RestoreValidateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[RestoreData]:
    actor = authenticated_actor_id(request)
    path = _safe_data_path(request, payload.archive_path, "restore.eea.zip")
    identity = IdentityRepository(session).ensure_local_user()
    if actor not in {
        identity.stable_actor_id,
        "local-authenticated-session",
        "configured-authenticated-session",
    }:
        raise EngineeringError(
            EngineeringErrorCode.PERMISSION_REQUIRED, "restore actor is not authorized"
        )
    try:
        restore = RestoreCoordinator(
            lambda: Session(request.app.state.engine),
            request.app.state.settings,
            failure_injector=request.app.state.restore_failure_injector,
        ).restore(
            path,
            project_id=payload.project_id,
            actor_id=actor,
            authorize=lambda project, actor_value: (
                project == payload.project_id and actor_value == actor
            ),
            requested_operation_id=payload.operation_id,
        )
    except FileNotFoundError as exc:
        raise EngineeringError(
            EngineeringErrorCode.BACKUP_INVALID, "backup archive was not found"
        ) from exc
    except BackupValidationError as exc:
        raise EngineeringError(
            EngineeringErrorCode.BACKUP_INVALID, "backup validation failed"
        ) from exc
    except RestoreConflictError as exc:
        raise EngineeringError(EngineeringErrorCode.RESTORE_CONFLICT, "restore conflict") from exc
    except BackupOperationError as exc:
        raise EngineeringError(
            EngineeringErrorCode.BACKUP_INVALID, "restore failed closed"
        ) from exc
    except OSError as exc:
        raise EngineeringError(
            EngineeringErrorCode.BACKUP_INVALID, "restore failed closed"
        ) from exc
    return ApiEnvelope(
        data=RestoreData(
            valid=True,
            state=restore.state.value,
            manifest_hash=restore.manifest.manifest_hash or "",
            project_id=restore.manifest.project_id,
            object_count=len(restore.manifest.objects),
            staging_path=str(restore.destination),
        ),
        request_id=_request_id(request),
    )


__all__ = ["router"]
