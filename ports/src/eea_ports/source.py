"""Ports for the project source workspace and bounded Git operations."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RecoveryBundle:
    """Durable, workspace-local evidence for one source mutation."""

    operation_id: UUID
    path: Path
    before_manifest: Mapping[str, str | None]
    after_manifest: Mapping[str, str]


class SourceWorkspacePort(Protocol):
    """The only application-facing port for editable source bytes."""

    @property
    def root(self) -> Path: ...

    def ensure_exists(self) -> None: ...

    def read_bytes(self, path: str) -> bytes: ...

    def list_files(self) -> Mapping[str, bytes]: ...

    def atomic_replace(self, files: Mapping[str, bytes]) -> None: ...

    def cleanup_temporary(self) -> None: ...

    def prepare_recovery_bundle(
        self,
        operation_id: UUID,
        before_files: Mapping[str, bytes | None],
        after_files: Mapping[str, bytes],
        *,
        metadata: Mapping[str, object],
    ) -> RecoveryBundle: ...

    def classify_recovery_bundle(self, bundle_path: str) -> str: ...

    def restore_recovery_bundle(self, bundle_path: str, target: str) -> None: ...

    def cleanup_recovery_bundle(self, bundle_path: str) -> None: ...


@dataclass(frozen=True, slots=True)
class GitStatus:
    repository_id: str
    commit_sha: str | None
    base_commit: str | None
    branch: str | None
    dirty: bool


@dataclass(frozen=True, slots=True)
class GitCommit:
    commit_sha: str
    tree_hash: str | None


class GitWorkspacePort(Protocol):
    """Narrow, non-destructive Git contract used by SourceWorkspaceService."""

    def status(self) -> GitStatus: ...

    def commit(self, message: str, *, actor: str) -> GitCommit: ...


__all__ = [
    "GitCommit",
    "GitStatus",
    "GitWorkspacePort",
    "RecoveryBundle",
    "SourceWorkspacePort",
]
