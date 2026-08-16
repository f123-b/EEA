"""Bounded project export and fail-closed restore workflow."""

from __future__ import annotations

import os
import re
import zipfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from eea_core.backup import (
    BackupObjectRef,
    BackupValidationError,
    ProjectBackupManifest,
    manifest_from_json,
    sha256_bytes,
    validate_archive_member,
)
from eea_core.capacity import CapacityExceededError, CapacityProfile
from eea_core.failure_injection import (
    FailureInjectionHarness,
    FailureInjectionPoint,
    InjectedFailureError,
)


class BackupOperationError(RuntimeError):
    """Export or restore failed before a success could be reported."""


class RestoreConflictError(BackupOperationError):
    """Restore would overwrite an existing project without explicit policy."""


_SECRET_KEY = re.compile(
    r"(?:bearer|authorization|api[_-]?key|secret|password|private[_-]?key|token|cookie|env)", re.I
)


@dataclass(frozen=True, slots=True)
class BackupRecord:
    path: str
    content: bytes
    object_type: str = "record"


def _contains_secret(value: object, *, key: str | None = None) -> bool:
    if key and _SECRET_KEY.search(key):
        return True
    if isinstance(value, Mapping):
        return any(_contains_secret(item, key=str(name)) for name, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_secret(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return "-----begin " in lowered and "private key-----" in lowered
    return False


class ProjectBackupService:
    """Write authoritative records and content-addressed objects to a verified archive."""

    def __init__(
        self,
        *,
        profile: CapacityProfile | None = None,
        failure_injector: FailureInjectionHarness | None = None,
    ) -> None:
        self.profile = profile
        self.failure_injector = failure_injector or FailureInjectionHarness()

    def _check_size(self, path: str, content: bytes) -> None:
        if self.profile is not None:
            try:
                self.profile.check("object_quota_bytes", len(content))
            except CapacityExceededError as exc:
                raise BackupOperationError(str(exc)) from exc
        if len(content) > 1_000_000_000:
            raise BackupOperationError("backup object exceeds bounded writer limit")
        validate_archive_member(path)

    def export_project(
        self,
        project_id: UUID,
        target: Path,
        records: Iterable[BackupRecord],
        *,
        source_revision_id: UUID | None = None,
        source_revision_hash: str | None = None,
        knowledge_snapshot_refs: tuple[str, ...] = (),
        schema_versions: dict[str, str] | None = None,
    ) -> ProjectBackupManifest:
        """Export to a sibling temporary file and atomically activate the final archive."""

        materialized = tuple(records)
        if not materialized:
            raise BackupOperationError("backup must contain authoritative project records")
        seen: set[str] = set()
        objects: list[BackupObjectRef] = []
        for record in materialized:
            self._check_size(record.path, record.content)
            if record.path in seen or record.path == "manifest.json":
                raise BackupOperationError("backup contains duplicate or reserved object path")
            decoded = record.content.decode("utf-8", errors="ignore")
            if _contains_secret(decoded) or re.search(
                r"(?:bearer|authorization|api[_-]?key|secret|password|private[_-]?key|token)\s*[:=]",
                decoded,
                re.I,
            ):
                raise BackupOperationError("backup object contains a secret-shaped value")
            seen.add(record.path)
            objects.append(
                BackupObjectRef(
                    record.path,
                    sha256_bytes(record.content),
                    len(record.content),
                    record.object_type,
                )
            )
        manifest = ProjectBackupManifest(
            manifest_version="1.0",
            schema_version="m18e.1",
            project_id=project_id,
            exported_at=datetime.now(UTC),
            source_revision_id=source_revision_id,
            source_revision_hash=source_revision_hash,
            objects=tuple(objects),
            knowledge_snapshot_refs=knowledge_snapshot_refs,
            schema_versions=schema_versions or {},
        ).with_hash()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            with zipfile.ZipFile(
                temporary, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=False
            ) as archive:
                archive.writestr("manifest.json", manifest.to_json())
                for record in materialized:
                    self.failure_injector.inject(FailureInjectionPoint.ARTIFACT_OBJECT_WRITE)
                    archive.writestr(record.path, record.content)
            self._verify_archive(temporary, manifest)
            os.replace(temporary, target)
            return manifest
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            if isinstance(exc, (BackupOperationError, BackupValidationError, InjectedFailureError)):
                raise
            raise BackupOperationError("backup export failed before activation") from exc

    def _verify_archive(self, archive_path: Path, manifest: ProjectBackupManifest) -> None:
        with zipfile.ZipFile(archive_path, "r") as archive:
            names = archive.namelist()
            if names.count("manifest.json") != 1 or len(names) != len(set(names)):
                raise BackupValidationError("backup archive manifest/member set is invalid")
            parsed = manifest_from_json(archive.read("manifest.json"))
            if parsed.manifest_hash != manifest.manifest_hash:
                raise BackupValidationError("backup manifest changed while writing")
            for item in parsed.objects:
                validate_archive_member(item.path)
                info = archive.getinfo(item.path)
                content = archive.read(item.path)
                if info.file_size != item.size_bytes or sha256_bytes(content) != item.content_hash:
                    raise BackupValidationError("backup object hash or size mismatch")

    def restore_project(
        self,
        archive_path: Path,
        destination: Path,
        *,
        authorized_project_id: UUID,
        actor_id: str,
        authorize: Callable[[UUID, str], bool],
        supported_schema_versions: frozenset[str] = frozenset({"m18e.1"}),
        migration_dry_run: Callable[[ProjectBackupManifest], None] | None = None,
        allow_overwrite: bool = False,
    ) -> ProjectBackupManifest:
        """Validate everything in staging, then atomically activate one restore root."""

        if not actor_id or not authorize(authorized_project_id, actor_id):
            raise RestoreConflictError("restore authority was not granted")
        if destination.exists() and not allow_overwrite:
            raise RestoreConflictError("restore destination already exists")
        staging = destination.with_name(f".{destination.name}.{uuid4().hex}.staging")
        try:
            with zipfile.ZipFile(archive_path, "r") as archive:
                infos = archive.infolist()
                names = [validate_archive_member(info.filename) for info in infos]
                if len(names) != len(set(names)) or "manifest.json" not in names:
                    raise BackupValidationError("backup archive has unsafe member names")
                manifest = manifest_from_json(archive.read("manifest.json"))
                if manifest.schema_version not in supported_schema_versions:
                    raise BackupValidationError("backup schema version is unsupported")
                if manifest.project_id != authorized_project_id:
                    raise RestoreConflictError("backup project does not match authorized project")
                if migration_dry_run is not None:
                    migration_dry_run(manifest)
                staging.mkdir(parents=True, exist_ok=False)
                for item in manifest.objects:
                    self.failure_injector.inject(FailureInjectionPoint.ARTIFACT_OBJECT_WRITE)
                    content = archive.read(item.path)
                    if (
                        len(content) != item.size_bytes
                        or sha256_bytes(content) != item.content_hash
                    ):
                        raise BackupValidationError("backup object hash mismatch")
                    output = staging.joinpath(*item.path.split("/"))
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(content)
                (staging / "manifest.json").write_bytes(manifest.to_json())
            if destination.exists() and allow_overwrite:
                raise RestoreConflictError(
                    "overwrite policy requires an explicit replacement adapter"
                )
            os.replace(staging, destination)
            return manifest
        except Exception as exc:
            if staging.exists():
                for path in sorted(staging.rglob("*"), reverse=True):
                    if path.is_file() or path.is_symlink():
                        path.unlink(missing_ok=True)
                    elif path.is_dir():
                        path.rmdir()
                staging.rmdir()
            if isinstance(exc, (BackupOperationError, BackupValidationError)):
                raise
            if isinstance(exc, OSError):
                raise BackupOperationError("restore failed during bounded staging write") from exc
            raise BackupOperationError("restore failed closed before activation") from exc


__all__ = ["BackupOperationError", "BackupRecord", "ProjectBackupService", "RestoreConflictError"]
