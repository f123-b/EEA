"""Portable, hash-verifiable project backup contracts."""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID


class BackupValidationError(ValueError):
    """A backup cannot be accepted without risking data loss or authority bypass."""


class BackupSecretPolicy:
    """Fail-closed structured inspection for secrets excluded from project backups."""

    _secret_key = re.compile(
        r"(?:authorization|bearer|api[_-]?key|apikey|secret|client[_-]?secret|password|passwd|"
        r"token|access[_-]?token|refresh[_-]?token|cookie|private[_-]?key|credential|credentials|"
        r"environment|env)",
        re.IGNORECASE,
    )
    _secret_value = re.compile(
        r"(?:\bbearer\s+[A-Za-z0-9._~+/=-]{8,}|\bsk-[A-Za-z0-9_-]{8,}|"
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----)",
        re.IGNORECASE,
    )

    @classmethod
    def contains_secret(cls, value: object, *, key: str | None = None) -> bool:
        if key and cls._secret_key.search(key):
            return True
        if isinstance(value, dict):
            return any(cls.contains_secret(item, key=str(name)) for name, item in value.items())
        if isinstance(value, (list, tuple)):
            return any(cls.contains_secret(item) for item in value)
        if isinstance(value, str):
            return bool(cls._secret_value.search(value))
        return False

    @classmethod
    def assert_safe(cls, value: object) -> None:
        if cls.contains_secret(value):
            raise BackupValidationError("backup contains prohibited secret material")


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def validate_archive_member(name: str) -> str:
    """Reject absolute paths, traversal, drive-like paths and empty archive members."""

    normalized = name.replace("\\", "/")
    if not normalized or normalized.startswith("/") or ":" in normalized.split("/", 1)[0]:
        raise BackupValidationError("archive member path is absolute")
    if any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise BackupValidationError("archive member path traversal is not allowed")
    safe = posixpath.normpath(normalized)
    if safe != normalized or safe == "." or safe.startswith("../"):
        raise BackupValidationError("archive member path is not normalized")
    return safe


@dataclass(frozen=True, slots=True)
class BackupObjectRef:
    path: str
    content_hash: str
    size_bytes: int
    object_type: str = "record"

    def __post_init__(self) -> None:
        validate_archive_member(self.path)
        if len(self.content_hash) != 64 or any(
            c not in "0123456789abcdef" for c in self.content_hash
        ):
            raise BackupValidationError("object hash must be lowercase SHA-256")
        if self.size_bytes < 0:
            raise BackupValidationError("object size cannot be negative")


@dataclass(frozen=True, slots=True)
class ProjectBackupManifest:
    manifest_version: str
    schema_version: str
    project_id: UUID
    exported_at: datetime
    source_revision_id: UUID | None
    source_revision_hash: str | None
    objects: tuple[BackupObjectRef, ...]
    knowledge_snapshot_refs: tuple[str, ...] = ()
    schema_versions: dict[str, str] | None = None
    manifest_hash: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "manifest_version": self.manifest_version,
            "schema_version": self.schema_version,
            "project_id": str(self.project_id),
            "exported_at": self.exported_at.astimezone(UTC).isoformat(),
            "source_revision_id": str(self.source_revision_id) if self.source_revision_id else None,
            "source_revision_hash": self.source_revision_hash,
            "objects": [
                {
                    "path": item.path,
                    "content_hash": item.content_hash,
                    "size_bytes": item.size_bytes,
                    "object_type": item.object_type,
                }
                for item in self.objects
            ],
            "knowledge_snapshot_refs": list(self.knowledge_snapshot_refs),
            "schema_versions": dict(sorted((self.schema_versions or {}).items())),
        }

    def compute_hash(self) -> str:
        return sha256_bytes(canonical_json(self.payload()))

    def with_hash(self) -> ProjectBackupManifest:
        return ProjectBackupManifest(
            manifest_version=self.manifest_version,
            schema_version=self.schema_version,
            project_id=self.project_id,
            exported_at=self.exported_at,
            source_revision_id=self.source_revision_id,
            source_revision_hash=self.source_revision_hash,
            objects=self.objects,
            knowledge_snapshot_refs=self.knowledge_snapshot_refs,
            schema_versions=self.schema_versions,
            manifest_hash=self.compute_hash(),
        )

    def verify_hash(self) -> None:
        if self.manifest_hash != self.compute_hash():
            raise BackupValidationError("backup manifest hash mismatch")

    def to_json(self) -> bytes:
        if self.manifest_hash is None:
            raise BackupValidationError("manifest must be finalized before serialization")
        self.verify_hash()
        return canonical_json({**self.payload(), "manifest_hash": self.manifest_hash})


def manifest_from_json(raw: bytes) -> ProjectBackupManifest:
    try:
        data = json.loads(raw)
        manifest = ProjectBackupManifest(
            manifest_version=data["manifest_version"],
            schema_version=data["schema_version"],
            project_id=UUID(data["project_id"]),
            exported_at=datetime.fromisoformat(data["exported_at"]),
            source_revision_id=UUID(data["source_revision_id"])
            if data.get("source_revision_id")
            else None,
            source_revision_hash=data.get("source_revision_hash"),
            objects=tuple(BackupObjectRef(**item) for item in data["objects"]),
            knowledge_snapshot_refs=tuple(data.get("knowledge_snapshot_refs", [])),
            schema_versions=dict(data.get("schema_versions", {})),
            manifest_hash=data["manifest_hash"],
        )
        manifest.verify_hash()
        return manifest
    except BackupValidationError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise BackupValidationError("backup manifest is invalid") from exc


__all__ = [
    "BackupObjectRef",
    "BackupSecretPolicy",
    "BackupValidationError",
    "ProjectBackupManifest",
    "canonical_json",
    "manifest_from_json",
    "sha256_bytes",
    "validate_archive_member",
]
