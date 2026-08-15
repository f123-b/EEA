"""Ports for the project source workspace and bounded Git operations."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class SourceWorkspacePort(Protocol):
    """The only application-facing port for editable source bytes."""

    @property
    def root(self) -> Path: ...

    def ensure_exists(self) -> None: ...

    def read_bytes(self, path: str) -> bytes: ...

    def list_files(self) -> Mapping[str, bytes]: ...

    def atomic_replace(self, files: Mapping[str, bytes]) -> None: ...

    def cleanup_temporary(self) -> None: ...


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


__all__ = ["GitCommit", "GitStatus", "GitWorkspacePort", "SourceWorkspacePort"]
