"""Filesystem and bounded Git adapters for Source Authority."""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_core.sandbox import SafePath
from eea_ports.source import GitCommit, GitStatus


class FileSystemSourceWorkspaceAdapter:
    """Read and atomically replace source files within one SafePath root."""

    def __init__(
        self,
        root: Path,
        *,
        fault_injector: Callable[[str, int], None] | None = None,
    ) -> None:
        requested_root = root.absolute()
        if requested_root.exists() and requested_root.is_symlink():
            raise EngineeringError(
                EngineeringErrorCode.SANDBOX_VIOLATION,
                "Source workspace root must not be a symlink",
                details={"workspace": str(requested_root)},
            )
        self._root = requested_root.resolve(strict=False)
        self._guard = SafePath(self._root)
        self._fault_injector = fault_injector
        self.ensure_exists()

    @property
    def root(self) -> Path:
        return self._root

    def ensure_exists(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, path: str) -> Path:
        try:
            return self._guard.resolve(path)
        except ValueError as exc:
            raise EngineeringError(
                EngineeringErrorCode.SANDBOX_VIOLATION,
                "Source path escapes the project workspace",
                details={"path": path},
            ) from exc

    def read_bytes(self, path: str) -> bytes:
        target = self._path(path)
        if not target.is_file():
            raise EngineeringError(
                EngineeringErrorCode.SOURCE_FILE_NOT_FOUND,
                "Source file does not exist",
                details={"path": path},
            )
        return target.read_bytes()

    def list_files(self) -> Mapping[str, bytes]:
        self.ensure_exists()
        files: dict[str, bytes] = {}
        for candidate in self._root.rglob("*"):
            if ".git" in candidate.relative_to(self._root).parts:
                continue
            if not candidate.is_file():
                continue
            relative = candidate.relative_to(self._root).as_posix()
            # Resolve every discovered path so a symlink/junction escape is
            # rejected even when the caller only asks for workspace status.
            self._path(relative)
            files[relative] = candidate.read_bytes()
        return files

    def atomic_replace(self, files: Mapping[str, bytes]) -> None:
        if not files:
            return
        staged: dict[str, Path] = {}
        originals: dict[str, bytes | None] = {}
        replaced: list[str] = []
        try:
            for relative, content in files.items():
                target = self._path(relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                originals[relative] = target.read_bytes() if target.is_file() else None
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=target.parent,
                    prefix=".eea-source-tmp-",
                    delete=False,
                ) as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                    staged[relative] = Path(stream.name)
            for index, relative in enumerate(files, start=1):
                target = self._path(relative)
                os.replace(staged[relative], target)
                replaced.append(relative)
                if self._fault_injector is not None:
                    self._fault_injector("after_replace", index)
        except Exception:
            for relative in reversed(replaced):
                target = self._path(relative)
                original = originals[relative]
                if original is None:
                    with suppress(OSError):
                        target.unlink(missing_ok=True)
                else:
                    rollback = target.parent / f".eea-source-tmp-{uuid4().hex}"
                    rollback.write_bytes(original)
                    os.replace(rollback, target)
            raise
        finally:
            for temporary in staged.values():
                temporary.unlink(missing_ok=True)

    def cleanup_temporary(self) -> None:
        for candidate in self._root.rglob(".eea-source-tmp-*"):
            if candidate.is_file():
                candidate.unlink(missing_ok=True)


class GitCliWorkspaceAdapter:
    """A deliberately small Git adapter with no remote or destructive commands."""

    def __init__(self, root: Path, *, timeout_seconds: float = 20.0) -> None:
        self._root = root.resolve(strict=False)
        self._timeout_seconds = timeout_seconds

    def _run(self, *argv: str, check: bool = True) -> str:
        try:
            result = subprocess.run(
                ["git", *argv],
                cwd=self._root,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise EngineeringError(
                EngineeringErrorCode.CAPABILITY_UNAVAILABLE,
                "Git adapter could not execute the bounded Git operation",
                details={"operation": argv[0] if argv else "git"},
            ) from exc
        output = result.stdout.strip()
        if check and result.returncode != 0:
            raise EngineeringError(
                EngineeringErrorCode.CAPABILITY_UNAVAILABLE,
                "Git operation failed",
                details={"operation": argv[0] if argv else "git", "stderr": result.stderr.strip()},
            )
        return output

    def status(self) -> GitStatus:
        inside = self._run("rev-parse", "--is-inside-work-tree", check=False)
        if inside != "true":
            return GitStatus(
                repository_id=f"workspace:{self._root}",
                commit_sha=None,
                base_commit=None,
                branch=None,
                dirty=True,
            )
        commit = self._run("rev-parse", "HEAD", check=False) or None
        branch = self._run("symbolic-ref", "--quiet", "--short", "HEAD", check=False) or None
        dirty = bool(self._run("status", "--porcelain", "--untracked-files=all", check=False))
        repository_root = self._run("rev-parse", "--show-toplevel", check=False) or str(self._root)
        return GitStatus(
            repository_id=f"git:{repository_root}",
            commit_sha=commit,
            base_commit=commit,
            branch=branch,
            dirty=dirty,
        )

    def commit(self, message: str, *, actor: str) -> GitCommit:
        if not message.strip() or len(message) > 500:
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR,
                "Commit message must be non-empty and at most 500 characters",
            )
        current = self.status()
        if current.commit_sha is None:
            raise EngineeringError(
                EngineeringErrorCode.CAPABILITY_UNAVAILABLE,
                "Source workspace is not a Git working tree",
            )
        if current.dirty:
            name = actor.strip() or "EEA"
            self._run("add", "--all", "--", ".")
            self._run(
                "-c",
                f"user.name={name}",
                "-c",
                "user.email=eea@localhost",
                "commit",
                "-m",
                message,
            )
        commit_sha = self._run("rev-parse", "HEAD")
        tree_hash = self._run("rev-parse", "HEAD^{tree}")
        return GitCommit(commit_sha=commit_sha, tree_hash=tree_hash)


__all__ = ["FileSystemSourceWorkspaceAdapter", "GitCliWorkspaceAdapter"]
