"""Bounded project export and fail-closed restore workflow."""

from __future__ import annotations

import json
import os
import stat
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import IO, BinaryIO
from uuid import UUID, uuid4

from eea_core.backup import (
    BackupObjectRef,
    BackupSecretPolicy,
    BackupValidationError,
    ProjectBackupManifest,
    manifest_from_json,
    sha256_bytes,
    validate_archive_member,
)
from eea_core.capacity import (
    CapacityExceededError,
    CapacityProfile,
    CapacityProfileName,
    get_capacity_profile,
)
from eea_core.failure_injection import (
    FailureInjectionHarness,
    FailureInjectionPoint,
    InjectedFailureError,
)
from eea_core.sandbox import SafePath


class BackupOperationError(RuntimeError):
    """Export or restore failed before a success could be reported."""


class RestoreConflictError(BackupOperationError):
    """Restore would overwrite an existing project without explicit policy."""


class RestoreState(StrEnum):
    VALIDATED = "VALIDATED"
    STAGED = "STAGED"
    PREPARED = "PREPARED"
    FS_ACTIVATED = "FS_ACTIVATED"
    ACTIVATED = "ACTIVATED"
    ROLLBACK_REQUIRED = "ROLLBACK_REQUIRED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class RestoreResult:
    manifest: ProjectBackupManifest
    state: RestoreState
    destination: Path

    @property
    def manifest_hash(self) -> str | None:
        return self.manifest.manifest_hash


@dataclass(frozen=True, slots=True)
class RestoreStaging:
    """A fully verified staging tree that has not been activated yet."""

    manifest: ProjectBackupManifest
    staging: Path
    destination: Path


@dataclass(frozen=True, slots=True)
class BackupRecord:
    path: str
    content: bytes
    object_type: str = "record"


_CHUNK_SIZE = 64 * 1024


class ProjectBackupService:
    """Write authoritative records and content-addressed objects to a verified archive."""

    def __init__(
        self,
        *,
        profile: CapacityProfile | None = None,
        failure_injector: FailureInjectionHarness | None = None,
    ) -> None:
        self.profile = profile or get_capacity_profile(CapacityProfileName.DEV)
        self.failure_injector = failure_injector or FailureInjectionHarness()

    def _check_backup_limit(self, resource: str, actual: int | float) -> None:
        try:
            self.profile.check_backup(resource, actual)
        except CapacityExceededError as exc:
            raise BackupOperationError(str(exc)) from exc

    def _check_size(self, path: str, content: bytes) -> None:
        self._check_backup_limit("backup_path_length", len(path))
        self._check_backup_limit("backup_member_bytes", len(content))
        self.profile.check("object_quota_bytes", len(content))
        validate_archive_member(path)

    @staticmethod
    def _inspect_record_content(content: bytes, object_type: str = "record") -> None:
        # Source and portable artifact bytes are opaque content, not
        # structured authority records. Normal source code may contain words
        # such as ``token`` or ``password`` without being credential material.
        if object_type in {"source_file", "artifact_bytes"}:
            return
        try:
            structured: object = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            structured = content.decode("utf-8", errors="ignore")
        BackupSecretPolicy.assert_safe(structured)

    @staticmethod
    def _read_manifest(archive: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int) -> bytes:
        with archive.open(info, "r") as source:
            raw = source.read(limit + 1)
        if len(raw) > limit:
            raise BackupOperationError("backup manifest exceeds capacity limit")
        return raw

    def _preflight_archive(
        self, archive: zipfile.ZipFile
    ) -> tuple[ProjectBackupManifest, dict[str, zipfile.ZipInfo]]:
        infos = archive.infolist()
        self._check_backup_limit("backup_member_count", len(infos))
        names: list[str] = []
        total_uncompressed = 0
        by_name: dict[str, zipfile.ZipInfo] = {}
        for info in infos:
            name = validate_archive_member(info.filename)
            self._check_backup_limit("backup_path_length", len(name))
            if info.is_dir():
                raise BackupValidationError("backup archive contains a directory member")
            mode = (info.external_attr >> 16) & 0o170000
            if mode and not stat.S_ISREG(mode):
                raise BackupValidationError("backup archive contains a special member")
            self._check_backup_limit("backup_member_bytes", info.file_size)
            total_uncompressed += info.file_size
            self._check_backup_limit("backup_uncompressed_bytes", total_uncompressed)
            if info.file_size and info.compress_size == 0:
                raise BackupValidationError("backup member has an invalid compression size")
            if info.compress_size:
                ratio = info.file_size / info.compress_size
                self._check_backup_limit("backup_compression_ratio", ratio)
            if name in by_name:
                raise BackupValidationError("backup archive contains duplicate members")
            names.append(name)
            by_name[name] = info

        if names.count("manifest.json") != 1:
            raise BackupValidationError("backup archive manifest is missing or duplicated")
        manifest_info = by_name["manifest.json"]
        self._check_backup_limit("backup_manifest_bytes", manifest_info.file_size)
        manifest = manifest_from_json(
            self._read_manifest(archive, manifest_info, self.profile.maximum_backup_manifest_bytes)
        )
        declared = {"manifest.json", *(item.path for item in manifest.objects)}
        declared_paths = [item.path for item in manifest.objects]
        if len(declared_paths) != len(set(declared_paths)):
            raise BackupValidationError("backup manifest contains duplicate object paths")
        if set(names) != declared:
            raise BackupValidationError("backup archive contains undeclared members")
        return manifest, by_name

    @staticmethod
    def _stream_member(
        source: IO[bytes],
        *,
        expected_size: int,
        maximum_size: int,
        output: BinaryIO | None = None,
    ) -> tuple[int, str]:
        import hashlib

        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = source.read(_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > maximum_size or total > expected_size:
                raise BackupValidationError("backup member exceeds its declared size")
            digest.update(chunk)
            if output is not None:
                output.write(chunk)
        if total != expected_size:
            raise BackupValidationError("backup member size does not match its declaration")
        return total, digest.hexdigest()

    def _verify_archive(self, archive_path: Path, manifest: ProjectBackupManifest) -> None:
        with zipfile.ZipFile(archive_path, "r") as archive:
            parsed, members = self._preflight_archive(archive)
            if parsed.manifest_hash != manifest.manifest_hash:
                raise BackupValidationError("backup manifest changed while writing")
            for item in parsed.objects:
                with archive.open(members[item.path], "r") as source:
                    size, content_hash = self._stream_member(
                        source,
                        expected_size=item.size_bytes,
                        maximum_size=self.profile.maximum_backup_member_bytes,
                    )
                if size != item.size_bytes or content_hash != item.content_hash:
                    raise BackupValidationError("backup object hash or size mismatch")

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
        """Export authoritative records to a verified sibling temporary archive."""

        materialized: list[BackupRecord] = []
        seen: set[str] = set()
        objects: list[BackupObjectRef] = []
        total_uncompressed = 0
        for record in records:
            self._check_backup_limit("backup_member_count", len(materialized) + 2)
            self._check_size(record.path, record.content)
            if record.path in seen or record.path == "manifest.json":
                raise BackupOperationError("backup contains duplicate or reserved object path")
            self._inspect_record_content(record.content, record.object_type)
            seen.add(record.path)
            materialized.append(record)
            total_uncompressed += len(record.content)
            self._check_backup_limit("backup_uncompressed_bytes", total_uncompressed)
            objects.append(
                BackupObjectRef(
                    record.path,
                    sha256_bytes(record.content),
                    len(record.content),
                    record.object_type,
                )
            )
        if not materialized:
            raise BackupOperationError("backup must contain authoritative project records")
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
        manifest_bytes = manifest.to_json()
        self._check_backup_limit("backup_manifest_bytes", len(manifest_bytes))
        self._check_backup_limit(
            "backup_uncompressed_bytes", total_uncompressed + len(manifest_bytes)
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            with zipfile.ZipFile(
                temporary, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=False
            ) as archive:
                archive.writestr("manifest.json", manifest_bytes)
                for record in materialized:
                    self.failure_injector.inject(FailureInjectionPoint.ARTIFACT_OBJECT_WRITE)
                    archive.writestr(record.path, record.content)
            self._check_backup_limit("backup_archive_bytes", temporary.stat().st_size)
            self._verify_archive(temporary, manifest)
            os.replace(temporary, target)
            return manifest
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            if isinstance(exc, (BackupOperationError, BackupValidationError, InjectedFailureError)):
                raise
            raise BackupOperationError("backup export failed before activation") from exc

    def validate_archive(self, archive_path: Path) -> ProjectBackupManifest:
        """Run bounded preflight plus a streaming hash pass over every object."""

        try:
            self._check_backup_limit("backup_archive_bytes", archive_path.stat().st_size)
            with zipfile.ZipFile(archive_path, "r") as archive:
                manifest, members = self._preflight_archive(archive)
                for item in manifest.objects:
                    with archive.open(members[item.path], "r") as source:
                        size, content_hash = self._stream_member(
                            source,
                            expected_size=item.size_bytes,
                            maximum_size=self.profile.maximum_backup_member_bytes,
                        )
                    if size != item.size_bytes or content_hash != item.content_hash:
                        raise BackupValidationError("backup object hash or size mismatch")
                return manifest
        except (OSError, zipfile.BadZipFile) as exc:
            raise BackupValidationError("backup archive cannot be opened") from exc

    def stage_project(
        self,
        archive_path: Path,
        destination: Path,
        *,
        authorized_project_id: UUID,
        actor_id: str,
        authorize: Callable[[UUID, str], bool],
        supported_schema_versions: frozenset[str] = frozenset({"m18e.1"}),
        migration_dry_run: Callable[[ProjectBackupManifest], None] | None = None,
        staging: Path | None = None,
    ) -> RestoreStaging:
        """Validate and stream an archive into a durable, unactivated tree."""

        if not actor_id or not authorize(authorized_project_id, actor_id):
            raise RestoreConflictError("restore authority was not granted")
        if destination.exists():
            raise RestoreConflictError("restore destination collision requires replacement policy")
        staging_path = staging or destination.with_name(
            f".{destination.name}.{uuid4().hex}.staging"
        )
        try:
            self._check_backup_limit("backup_archive_bytes", archive_path.stat().st_size)
            with zipfile.ZipFile(archive_path, "r") as archive:
                manifest, members = self._preflight_archive(archive)
                if manifest.schema_version not in supported_schema_versions:
                    raise BackupValidationError("backup schema version is unsupported")
                if manifest.project_id != authorized_project_id:
                    raise RestoreConflictError("backup project does not match authorized project")
                # A full streaming verification pass precedes any filesystem
                # writes, so staging is never the first integrity check.
                for item in manifest.objects:
                    with archive.open(members[item.path], "r") as source:
                        size, content_hash = self._stream_member(
                            source,
                            expected_size=item.size_bytes,
                            maximum_size=self.profile.maximum_backup_member_bytes,
                        )
                    if size != item.size_bytes or content_hash != item.content_hash:
                        raise BackupValidationError("backup object hash or size mismatch")
                if migration_dry_run is not None:
                    migration_dry_run(manifest)
                staging_path.mkdir(parents=True, exist_ok=False)
                guard = SafePath(staging_path)
                for item in manifest.objects:
                    self.failure_injector.inject(FailureInjectionPoint.ARTIFACT_OBJECT_WRITE)
                    output = guard.resolve(item.path)
                    output.parent.mkdir(parents=True, exist_ok=True)
                    with (
                        archive.open(members[item.path], "r") as source,
                        output.open("wb") as target,
                    ):
                        size, content_hash = self._stream_member(
                            source,
                            expected_size=item.size_bytes,
                            maximum_size=self.profile.maximum_backup_member_bytes,
                            output=target,
                        )
                        target.flush()
                        os.fsync(target.fileno())
                    if size != item.size_bytes or content_hash != item.content_hash:
                        raise BackupValidationError("backup object hash mismatch")
                manifest_output = guard.resolve("manifest.json")
                with manifest_output.open("wb") as target:
                    target.write(manifest.to_json())
                    target.flush()
                    os.fsync(target.fileno())
            self.failure_injector.inject(FailureInjectionPoint.RESTORE_AFTER_STAGE)
            return RestoreStaging(manifest, staging_path, destination)
        except Exception as exc:
            # A process-kill injection represents a crash after the durable
            # staging write. Leave that tree in place for startup recovery;
            # all ordinary failures still clean up their temporary data.
            preserve_for_recovery = isinstance(exc, InjectedFailureError) and (
                exc.plan.point == FailureInjectionPoint.RESTORE_AFTER_STAGE
            )
            if staging_path.exists() and not preserve_for_recovery:
                self._cleanup_tree(staging_path)
            if isinstance(exc, (BackupOperationError, BackupValidationError, InjectedFailureError)):
                raise
            if isinstance(exc, OSError):
                raise BackupOperationError("restore failed during bounded staging write") from exc
            raise BackupOperationError("restore failed closed before activation") from exc

    @staticmethod
    def _cleanup_tree(path: Path) -> None:
        if path.exists():
            for candidate in sorted(path.rglob("*"), reverse=True):
                if candidate.is_file() or candidate.is_symlink():
                    candidate.unlink(missing_ok=True)
                elif candidate.is_dir():
                    candidate.rmdir()
            path.rmdir()

    @staticmethod
    def activate_staged(staging: Path, destination: Path) -> None:
        """Atomically publish a prepared staging tree and fsync its parent."""

        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, destination)
        try:
            descriptor = os.open(destination.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def verify_activated_tree(self, root: Path, manifest: ProjectBackupManifest) -> None:
        """Verify an activated tree without loading large objects into memory."""

        manifest_path = SafePath(root).resolve("manifest.json")
        if not manifest_path.is_file():
            raise BackupValidationError("activated restore manifest is missing")
        if (
            manifest_from_json(self._read_bounded_file(manifest_path)).manifest_hash
            != manifest.manifest_hash
        ):
            raise BackupValidationError("activated restore manifest does not match journal")
        guard = SafePath(root)
        expected_paths = {"manifest.json", *(item.path for item in manifest.objects)}
        for candidate in root.rglob("*"):
            if candidate.is_symlink():
                raise BackupValidationError("activated restore contains a symlink")
            if candidate.is_file() and candidate.relative_to(root).as_posix() not in expected_paths:
                raise BackupValidationError("activated restore contains an undeclared file")
        for item in manifest.objects:
            target = guard.resolve(item.path)
            if not target.is_file() or target.is_symlink():
                raise BackupValidationError("activated restore object is missing")
            with target.open("rb") as source:
                size, content_hash = self._stream_member(
                    source,
                    expected_size=item.size_bytes,
                    maximum_size=self.profile.maximum_backup_member_bytes,
                )
            if size != item.size_bytes or content_hash != item.content_hash:
                raise BackupValidationError("activated restore object hash mismatch")

    def _read_bounded_file(self, path: Path) -> bytes:
        limit = self.profile.maximum_backup_manifest_bytes
        with path.open("rb") as source:
            raw = source.read(limit + 1)
        if len(raw) > limit:
            raise BackupValidationError("backup manifest exceeds capacity limit")
        return raw

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
        before_activate: Callable[[Path, ProjectBackupManifest], None] | None = None,
        allow_overwrite: bool = False,
    ) -> RestoreResult:
        """Validate, stream to staging, then atomically activate a portable project package."""

        if not actor_id or not authorize(authorized_project_id, actor_id):
            raise RestoreConflictError("restore authority was not granted")
        if destination.exists() or allow_overwrite:
            raise RestoreConflictError("restore destination collision requires replacement policy")
        staging = destination.with_name(f".{destination.name}.{uuid4().hex}.staging")
        try:
            self._check_backup_limit("backup_archive_bytes", archive_path.stat().st_size)
            with zipfile.ZipFile(archive_path, "r") as archive:
                manifest, members = self._preflight_archive(archive)
                if manifest.schema_version not in supported_schema_versions:
                    raise BackupValidationError("backup schema version is unsupported")
                if manifest.project_id != authorized_project_id:
                    raise RestoreConflictError("backup project does not match authorized project")
                if migration_dry_run is not None:
                    migration_dry_run(manifest)
                staging.mkdir(parents=True, exist_ok=False)
                for item in manifest.objects:
                    self.failure_injector.inject(FailureInjectionPoint.ARTIFACT_OBJECT_WRITE)
                    output = staging.joinpath(*item.path.split("/"))
                    output.parent.mkdir(parents=True, exist_ok=True)
                    with (
                        archive.open(members[item.path], "r") as source,
                        output.open("wb") as target,
                    ):
                        size, content_hash = self._stream_member(
                            source,
                            expected_size=item.size_bytes,
                            maximum_size=self.profile.maximum_backup_member_bytes,
                            output=target,
                        )
                        target.flush()
                        os.fsync(target.fileno())
                    if size != item.size_bytes or content_hash != item.content_hash:
                        raise BackupValidationError("backup object hash mismatch")
                manifest_output = staging / "manifest.json"
                with manifest_output.open("wb") as target:
                    target.write(manifest.to_json())
                    target.flush()
                    os.fsync(target.fileno())
                if before_activate is not None:
                    before_activate(staging, manifest)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging, destination)
            return RestoreResult(manifest, RestoreState.ACTIVATED, destination)
        except Exception as exc:
            if staging.exists():
                self._cleanup_tree(staging)
            if isinstance(exc, (BackupOperationError, BackupValidationError, InjectedFailureError)):
                raise
            if isinstance(exc, OSError):
                raise BackupOperationError("restore failed during bounded staging write") from exc
            raise BackupOperationError("restore failed closed before activation") from exc


__all__ = [
    "BackupOperationError",
    "BackupRecord",
    "ProjectBackupService",
    "RestoreConflictError",
    "RestoreResult",
    "RestoreStaging",
    "RestoreState",
]
