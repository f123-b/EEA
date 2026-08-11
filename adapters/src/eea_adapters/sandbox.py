"""M5 archive and structured-command adapters.

These adapters deliberately expose no shell-string API. Archive extraction is
manual and validates every member before writing it through ``SafePath``.
"""

import os
import re
import stat
import subprocess
import tarfile
import time
import zipfile
from pathlib import Path
from typing import BinaryIO, cast

from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_core.sandbox import (
    ArchiveExtractionReport,
    CommandResult,
    CommandSpec,
    SafePath,
    SandboxPolicy,
    SandboxWorkspace,
)


class SafeArchiveMaterializer:
    """Extract ZIP/TAR content while rejecting traversal, links, and bombs."""

    name = "safe-archive-materializer/v1"

    def extract(
        self, archive: Path, destination: Path, policy: SandboxPolicy
    ) -> ArchiveExtractionReport:
        source = archive.resolve(strict=False)
        if archive.is_symlink() or not source.is_file():
            raise EngineeringError(
                EngineeringErrorCode.ARCHIVE_UNSAFE,
                "Archive must be a regular, non-symlink file",
                details={"archive": str(archive)},
            )
        if destination.exists() and destination.is_symlink():
            raise EngineeringError(
                EngineeringErrorCode.SANDBOX_VIOLATION,
                "Extraction destination must not be a symlink",
                details={"destination": str(destination)},
            )
        workspace = SandboxWorkspace.from_root(destination)
        if zipfile.is_zipfile(source):
            return self._extract_zip(source, workspace, policy)
        try:
            with tarfile.open(source, mode="r:*") as archive_file:
                return self._extract_tar(source, archive_file, workspace, policy)
        except tarfile.ReadError:
            raise EngineeringError(
                EngineeringErrorCode.ARCHIVE_UNSAFE,
                "Archive format is not supported",
                details={"archive": source.name},
            ) from None

    def _extract_zip(
        self, source: Path, workspace: SandboxWorkspace, policy: SandboxPolicy
    ) -> ArchiveExtractionReport:
        extracted: list[str] = []
        seen: set[str] = set()
        total = 0
        with zipfile.ZipFile(source) as archive:
            members = archive.infolist()
            self._check_member_count(len(members), policy)
            for info in members:
                name = self._validate_member_name(info.filename, workspace.path_guard, seen)
                if self._zip_is_symlink(info):
                    self._unsafe("archive symlink members are not allowed", name=name)
                target = workspace.path_guard.resolve(name)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                self._check_size(info.file_size, policy)
                compressed = max(info.compress_size, 1)
                if info.file_size / compressed > policy.max_compression_ratio:
                    self._unsafe("archive compression ratio exceeds policy", name=name)
                total = self._check_total(total, info.file_size, policy)
                self._prepare_new_file(target, name)
                source_stream = cast(BinaryIO, archive.open(info, "r"))
                with source_stream, target.open("xb") as output:
                    self._copy_limited(
                        source_stream, output, info.file_size, policy.max_member_bytes
                    )
                extracted.append(name)
        return ArchiveExtractionReport(
            archive_name=source.name, extracted_files=tuple(extracted), total_bytes=total
        )

    def _extract_tar(
        self,
        source: Path,
        archive: tarfile.TarFile,
        workspace: SandboxWorkspace,
        policy: SandboxPolicy,
    ) -> ArchiveExtractionReport:
        extracted: list[str] = []
        seen: set[str] = set()
        total = 0
        members = archive.getmembers()
        self._check_member_count(len(members), policy)
        for member in members:
            name = self._validate_member_name(member.name, workspace.path_guard, seen)
            if member.issym() or member.islnk():
                self._unsafe("archive links are not allowed", name=name)
            target = workspace.path_guard.resolve(name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isreg():
                self._unsafe("archive special files are not allowed", name=name)
            self._check_size(member.size, policy)
            total = self._check_total(total, member.size, policy)
            self._prepare_new_file(target, name)
            stream = archive.extractfile(member)
            if stream is None:
                self._unsafe("archive member could not be read", name=name)
            source_stream = cast(BinaryIO, stream)
            with source_stream, target.open("xb") as output:
                self._copy_limited(source_stream, output, member.size, policy.max_member_bytes)
            extracted.append(name)
        return ArchiveExtractionReport(
            archive_name=source.name, extracted_files=tuple(extracted), total_bytes=total
        )

    @staticmethod
    def _check_member_count(count: int, policy: SandboxPolicy) -> None:
        if count > policy.max_archive_members:
            raise EngineeringError(
                EngineeringErrorCode.RESOURCE_LIMIT_EXCEEDED,
                "Archive contains too many members",
                details={"members": count, "limit": policy.max_archive_members},
            )

    @staticmethod
    def _check_size(size: int, policy: SandboxPolicy) -> None:
        if size > policy.max_member_bytes:
            raise EngineeringError(
                EngineeringErrorCode.RESOURCE_LIMIT_EXCEEDED,
                "Archive member exceeds the size limit",
                details={"size": size, "limit": policy.max_member_bytes},
            )

    @staticmethod
    def _check_total(total: int, size: int, policy: SandboxPolicy) -> int:
        updated = total + size
        if updated > policy.max_archive_bytes:
            raise EngineeringError(
                EngineeringErrorCode.RESOURCE_LIMIT_EXCEEDED,
                "Archive exceeds the total extraction limit",
                details={"bytes": updated, "limit": policy.max_archive_bytes},
            )
        return updated

    @staticmethod
    def _validate_member_name(name: str, guard: SafePath, seen: set[str]) -> str:
        normalized = name.replace("\\", "/").strip("/")
        try:
            target = guard.resolve(normalized)
        except ValueError as exc:
            raise EngineeringError(
                EngineeringErrorCode.ARCHIVE_UNSAFE,
                "Archive member escapes the workspace",
                details={"member": name},
            ) from exc
        relative = target.relative_to(guard.root).as_posix()
        if not relative or relative in seen:
            raise EngineeringError(
                EngineeringErrorCode.ARCHIVE_UNSAFE,
                "Archive contains an empty or duplicate member",
                details={"member": name},
            )
        seen.add(relative)
        return relative

    @staticmethod
    def _zip_is_symlink(info: zipfile.ZipInfo) -> bool:
        mode = (info.external_attr >> 16) & 0xFFFF
        return stat.S_ISLNK(mode)

    @staticmethod
    def _prepare_new_file(target: Path, name: str) -> None:
        if target.exists() or target.is_symlink():
            raise EngineeringError(
                EngineeringErrorCode.ARCHIVE_UNSAFE,
                "Archive extraction would overwrite an existing path",
                details={"member": name},
            )
        target.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _copy_limited(source: BinaryIO, target: BinaryIO, expected_size: int, limit: int) -> None:
        copied = 0
        while True:
            chunk = source.read(min(1024 * 1024, limit - copied + 1))
            if not chunk:
                break
            copied += len(chunk)
            if copied > limit:
                raise EngineeringError(
                    EngineeringErrorCode.RESOURCE_LIMIT_EXCEEDED,
                    "Archive member expanded beyond the size limit",
                    details={"limit": limit},
                )
            target.write(chunk)
        if copied != expected_size:
            raise EngineeringError(
                EngineeringErrorCode.ARCHIVE_UNSAFE,
                "Archive member size did not match its declared size",
                details={"declared": expected_size, "actual": copied},
            )

    @staticmethod
    def _unsafe(message: str, *, name: str) -> None:
        raise EngineeringError(
            EngineeringErrorCode.ARCHIVE_UNSAFE, message, details={"member": name}
        )


class StructuredCommandExecutor:
    """Execute a policy-allowlisted argv without shell expansion or secret env."""

    name = "structured-command-executor/v1"
    _secret_pattern = re.compile(
        r"(?i)(api[_-]?key|token|password|secret|private[_-]?key)=([^\s]+)"
    )

    def execute(self, spec: CommandSpec, workspace: Path, policy: SandboxPolicy) -> CommandResult:
        guard = SafePath(workspace)
        try:
            cwd = guard.resolve(spec.cwd)
        except ValueError as exc:
            raise EngineeringError(
                EngineeringErrorCode.SANDBOX_VIOLATION,
                "Command working directory escapes the workspace",
                details={"cwd": spec.cwd},
            ) from exc
        executable = Path(spec.argv[0]).name.lower()
        allowed = {Path(value).name.lower() for value in policy.allowed_executables}
        if executable not in allowed:
            raise EngineeringError(
                EngineeringErrorCode.COMMAND_NOT_ALLOWED,
                "Executable is not allowlisted by the sandbox policy",
                details={"executable": executable},
            )
        if spec.network_required and not policy.network_access:
            raise EngineeringError(
                EngineeringErrorCode.NETWORK_DENIED,
                "Network access is denied by the sandbox policy",
            )
        if any(self._secret_pattern.search(value) for value in spec.argv):
            raise EngineeringError(
                EngineeringErrorCode.SANDBOX_VIOLATION,
                "Secrets are not allowed in command arguments",
            )
        environment = self._environment(spec, policy)
        timeout = min(
            policy.max_runtime_seconds, spec.timeout_seconds or policy.max_runtime_seconds
        )
        started = time.monotonic()
        process = self._start_process(spec, cwd, environment, policy)
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            process.kill()
            stdout, stderr = process.communicate()
            raise EngineeringError(
                EngineeringErrorCode.RESOURCE_LIMIT_EXCEEDED,
                "Command exceeded the runtime limit",
                details={
                    "timeout_seconds": timeout,
                    "stdout": self._redact(self._bounded(stdout)),
                    "stderr": self._redact(self._bounded(stderr)),
                },
            ) from exc
        duration_ms = int((time.monotonic() - started) * 1000)
        output_truncated = (
            len(stdout) > policy.max_output_bytes or len(stderr) > policy.max_output_bytes
        )
        if output_truncated:
            raise EngineeringError(
                EngineeringErrorCode.RESOURCE_LIMIT_EXCEEDED,
                "Command output exceeded the limit",
                details={"limit": policy.max_output_bytes},
            )
        return CommandResult(
            argv=spec.argv,
            returncode=process.returncode,
            stdout=self._redact(stdout),
            stderr=self._redact(stderr),
            duration_ms=duration_ms,
            timed_out=timed_out,
            output_truncated=output_truncated,
        )

    @staticmethod
    def _environment(spec: CommandSpec, policy: SandboxPolicy) -> dict[str, str]:
        allowed = set(policy.allowed_environment)
        if any(key not in allowed for key in spec.environment):
            raise EngineeringError(
                EngineeringErrorCode.SANDBOX_VIOLATION,
                "Command environment contains a key outside the allowlist",
            )
        environment = {
            key: os.environ[key]
            for key in allowed
            if key in os.environ and key not in {"TEMP", "TMP"}
        }
        environment.update(spec.environment)
        return environment

    @staticmethod
    def _start_process(
        spec: CommandSpec,
        cwd: Path,
        environment: dict[str, str],
        policy: SandboxPolicy,
    ) -> subprocess.Popen[bytes]:
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        try:
            return subprocess.Popen(
                list(spec.argv),
                cwd=cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                creationflags=creationflags,
                start_new_session=os.name != "nt",
            )
        except OSError as exc:
            raise EngineeringError(
                EngineeringErrorCode.TOOL_UNAVAILABLE,
                "Allowlisted command could not be started",
                details={"reason": type(exc).__name__},
            ) from None

    @classmethod
    def _redact(cls, value: bytes) -> str:
        text = value.decode("utf-8", errors="replace")
        return cls._secret_pattern.sub(r"\1=[REDACTED]", text)

    @staticmethod
    def _bounded(value: bytes, limit: int = 4096) -> bytes:
        return value[:limit]
