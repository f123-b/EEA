"""Filesystem and bounded Git adapters for Source Authority."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from contextlib import suppress
from pathlib import Path
from uuid import UUID, uuid4

from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_core.sandbox import SafePath
from eea_ports.source import GitCommit, GitStatus, RecoveryBundle


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
            relative_parts = candidate.relative_to(self._root).parts
            if ".git" in relative_parts or ".eea" in relative_parts:
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

    @staticmethod
    def _hash(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _recovery_root(self) -> Path:
        root = self._root / ".eea" / "source-recovery"
        root.mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        try:
            descriptor = os.open(path, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        except OSError:
            pass
        finally:
            os.close(descriptor)

    @classmethod
    def _write_fsync(cls, path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        cls._fsync_directory(path.parent)

    def prepare_recovery_bundle(
        self,
        operation_id: UUID,
        before_files: Mapping[str, bytes | None],
        after_files: Mapping[str, bytes],
        *,
        metadata: Mapping[str, object],
    ) -> RecoveryBundle:
        operation_uuid = operation_id
        bundle_path = self._recovery_root() / str(operation_uuid)
        if bundle_path.exists():
            raise EngineeringError(
                EngineeringErrorCode.RECOVERY_REQUIRED,
                "Recovery bundle operation id already exists",
                details={"operation_id": str(operation_uuid)},
            )
        before_manifest: dict[str, str | None] = {}
        after_manifest: dict[str, str] = {}
        for relative, content in before_files.items():
            self._path(relative)
            before_manifest[relative.replace("\\", "/")] = (
                self._hash(content) if content is not None else None
            )
        for relative, content in after_files.items():
            normalized = relative.replace("\\", "/")
            self._path(normalized)
            after_manifest[normalized] = self._hash(content)
        for relative, content in before_files.items():
            if content is not None:
                self._write_fsync(bundle_path / "before" / relative, content)
        for relative, content in after_files.items():
            self._write_fsync(bundle_path / "staged" / relative, content)
        manifest = {
            "operation_id": str(operation_uuid),
            "metadata": dict(metadata),
            "files": {
                path: {
                    "before_hash": before_manifest[path],
                    "before_exists": before_manifest[path] is not None,
                    "after_hash": after_manifest[path],
                    "after_exists": True,
                }
                for path in sorted(after_manifest)
            },
        }
        manifest_path = bundle_path / "manifest.json"
        self._write_fsync(
            manifest_path,
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        )
        self._fsync_directory(bundle_path)
        return RecoveryBundle(
            operation_id=operation_uuid,
            path=bundle_path,
            before_manifest=before_manifest,
            after_manifest=after_manifest,
        )

    def _read_recovery_manifest(self, bundle_path: str) -> dict[str, object]:
        candidate = Path(bundle_path).absolute()
        recovery_root = self._recovery_root().absolute()
        try:
            candidate.relative_to(recovery_root)
        except ValueError as exc:
            raise EngineeringError(
                EngineeringErrorCode.SANDBOX_VIOLATION,
                "Recovery bundle is outside the workspace recovery directory",
            ) from exc
        try:
            loaded = json.loads((candidate / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EngineeringError(
                EngineeringErrorCode.RECOVERY_REQUIRED,
                "Recovery bundle manifest is unreadable",
                details={"bundle_path": str(candidate)},
            ) from exc
        if not isinstance(loaded, dict) or not isinstance(loaded.get("files"), dict):
            raise EngineeringError(
                EngineeringErrorCode.RECOVERY_REQUIRED,
                "Recovery bundle manifest is invalid",
            )
        return loaded

    def classify_recovery_bundle(self, bundle_path: str) -> str:
        bundle = Path(bundle_path).absolute()
        manifest = self._read_recovery_manifest(str(bundle))
        files = manifest["files"]
        assert isinstance(files, dict)
        before = True
        after = True
        for relative, raw in files.items():
            if not isinstance(relative, str) or not isinstance(raw, dict):
                return "UNKNOWN"
            target = self._path(relative)
            actual = self._hash(target.read_bytes()) if target.is_file() else None
            before = before and actual == raw.get("before_hash")
            after = after and actual == raw.get("after_hash")
        if after:
            return "AFTER"
        if before:
            return "BEFORE"
        if any(
            self._hash(self._path(relative).read_bytes()) == raw.get("after_hash")
            for relative, raw in files.items()
            if (
                isinstance(relative, str)
                and isinstance(raw, dict)
                and self._path(relative).is_file()
            )
        ):
            return "PARTIAL"
        return "UNKNOWN"

    def restore_recovery_bundle(self, bundle_path: str, target: str) -> None:
        if target not in {"BEFORE", "AFTER"}:
            raise EngineeringError(
                EngineeringErrorCode.RECOVERY_REQUIRED,
                "Recovery target must be BEFORE or AFTER",
            )
        bundle = Path(bundle_path).absolute()
        manifest = self._read_recovery_manifest(str(bundle))
        files = manifest["files"]
        assert isinstance(files, dict)
        source_dir = bundle / ("before" if target == "BEFORE" else "staged")
        replacements: dict[str, bytes] = {}
        missing: list[str] = []
        for relative, raw in files.items():
            if not isinstance(relative, str) or not isinstance(raw, dict):
                raise EngineeringError(
                    EngineeringErrorCode.RECOVERY_REQUIRED, "Invalid recovery file"
                )
            exists = raw.get("before_exists") if target == "BEFORE" else raw.get("after_exists")
            source = source_dir / relative
            if exists:
                try:
                    content = source.read_bytes()
                except OSError as exc:
                    raise EngineeringError(
                        EngineeringErrorCode.RECOVERY_REQUIRED,
                        "Recovery bundle file is missing",
                        details={"path": relative},
                    ) from exc
                expected_hash = (
                    raw.get("before_hash") if target == "BEFORE" else raw.get("after_hash")
                )
                if self._hash(content) != expected_hash:
                    raise EngineeringError(
                        EngineeringErrorCode.RECOVERY_REQUIRED,
                        "Recovery bundle file hash is invalid",
                        details={"path": relative},
                    )
                replacements[relative] = content
            else:
                missing.append(relative)
        self.atomic_replace(replacements)
        for relative in missing:
            self._path(relative).unlink(missing_ok=True)
        if self.classify_recovery_bundle(str(bundle)) != target:
            raise EngineeringError(
                EngineeringErrorCode.RECOVERY_REQUIRED,
                "Recovery bundle restore did not reach a consistent state",
                details={"target": target},
            )

    def cleanup_recovery_bundle(self, bundle_path: str) -> None:
        bundle = Path(bundle_path).absolute()
        recovery_root = self._recovery_root().absolute()
        try:
            bundle.relative_to(recovery_root)
        except ValueError as exc:
            raise EngineeringError(
                EngineeringErrorCode.SANDBOX_VIOLATION,
                "Recovery bundle is outside the workspace recovery directory",
            ) from exc
        if bundle != recovery_root:
            shutil.rmtree(bundle, ignore_errors=False)


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
