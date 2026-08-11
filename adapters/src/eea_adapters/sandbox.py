"""M5 archive and structured-command adapters.

These adapters deliberately expose no shell-string API. Archive extraction is
manual and validates every member before writing it through ``SafePath``.
"""

import os
import re
import shutil
import signal
import stat
import subprocess
import tarfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, BinaryIO, Protocol, cast

from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_core.sandbox import (
    ArchiveExtractionReport,
    CommandResult,
    CommandSpec,
    SafePath,
    SandboxCapabilities,
    SandboxExecutionTrust,
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


class _OutputCapture:
    """Bounded, thread-safe byte capture shared by stdout and stderr readers."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._lock = threading.Lock()
        self._chunks: list[bytes] = []
        self._total = 0
        self.overflowed = False

    def read_size(self) -> int:
        with self._lock:
            return max(1, min(8192, self._limit - self._total + 1))

    def append(self, chunk: bytes) -> None:
        with self._lock:
            remaining = max(0, self._limit + 1 - self._total)
            accepted = chunk[:remaining]
            self._chunks.append(accepted)
            self._total += len(accepted)
            if len(chunk) > len(accepted) or self._total > self._limit:
                self.overflowed = True

    def value(self) -> bytes:
        with self._lock:
            return b"".join(self._chunks)


class _JobHandle(Protocol):
    def assign(self, process: subprocess.Popen[bytes]) -> None: ...

    def resume(self, process: subprocess.Popen[bytes]) -> None: ...

    def terminate(self) -> None: ...

    def close(self) -> None: ...


def _windows_job_supported() -> bool:
    if os.name != "nt":
        return False
    from eea_adapters.windows_job import WindowsJob

    return WindowsJob.supported()


def _create_windows_job(policy: SandboxPolicy) -> _JobHandle:
    from eea_adapters.windows_job import WindowsJob

    return WindowsJob(policy)


class StructuredCommandExecutor:
    """Execute argv through a runtime that enforces, or rejects, its policy."""

    name = "structured-command-executor/v2"
    _secret_pattern = re.compile(
        r"(?i)(api[_-]?key|token|password|secret|private[_-]?key)=([^\s]+)"
    )

    def capabilities(self) -> SandboxCapabilities:
        windows_job = _windows_job_supported()
        return SandboxCapabilities(
            network_isolation=False,
            memory_limit=windows_job,
            process_limit=windows_job,
            process_tree_kill=windows_job or (os.name != "nt" and hasattr(os, "killpg")),
            streaming_output_limit=True,
            filesystem_isolation=False,
            strong_isolation=False,
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
        environment = self._environment(spec, policy)
        executable = self._resolve_executable(spec.argv[0], environment)
        allowed = self._canonical_allowed_executables(policy.allowed_executables)
        if executable not in allowed:
            raise EngineeringError(
                EngineeringErrorCode.COMMAND_NOT_ALLOWED,
                "Executable is not allowlisted by its canonical path",
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
        self._require_capabilities(spec, policy)
        timeout = min(
            policy.max_runtime_seconds, spec.timeout_seconds or policy.max_runtime_seconds
        )
        started = time.monotonic()
        process, job = self._start_process((executable, *spec.argv[1:]), cwd, environment, policy)
        stdout_capture = _OutputCapture(policy.max_output_bytes)
        stderr_capture = _OutputCapture(policy.max_output_bytes)
        overflow = threading.Event()
        readers = [
            threading.Thread(
                target=self._read_stream,
                args=(cast(BinaryIO, process.stdout), stdout_capture, overflow),
                daemon=True,
            ),
            threading.Thread(
                target=self._read_stream,
                args=(cast(BinaryIO, process.stderr), stderr_capture, overflow),
                daemon=True,
            ),
        ]
        for reader in readers:
            reader.start()
        timed_out = False
        try:
            deadline = started + timeout
            while process.poll() is None:
                if overflow.is_set():
                    self._terminate(process, job)
                    raise EngineeringError(
                        EngineeringErrorCode.RESOURCE_LIMIT_EXCEEDED,
                        "Command output exceeded the limit",
                        details={"limit": policy.max_output_bytes},
                    )
                if time.monotonic() >= deadline:
                    timed_out = True
                    self._terminate(process, job)
                    raise EngineeringError(
                        EngineeringErrorCode.RESOURCE_LIMIT_EXCEEDED,
                        "Command exceeded the runtime limit",
                        details={
                            "timeout_seconds": timeout,
                            "stdout": self._redact(self._bounded(stdout_capture.value())),
                            "stderr": self._redact(self._bounded(stderr_capture.value())),
                        },
                    )
                time.sleep(0.005)
            if overflow.is_set():
                raise EngineeringError(
                    EngineeringErrorCode.RESOURCE_LIMIT_EXCEEDED,
                    "Command output exceeded the limit",
                    details={"limit": policy.max_output_bytes},
                )
        finally:
            if timed_out or overflow.is_set():
                self._terminate(process, job)
            for reader in readers:
                reader.join(timeout=1)
            if process.poll() is None:
                self._terminate(process, job)
                process.wait(timeout=1)
            if job is not None:
                job.close()
        stdout = stdout_capture.value()
        stderr = stderr_capture.value()
        duration_ms = int((time.monotonic() - started) * 1000)
        return CommandResult(
            argv=(executable, *spec.argv[1:]),
            returncode=process.returncode,
            stdout=self._redact(stdout),
            stderr=self._redact(stderr),
            duration_ms=duration_ms,
            timed_out=timed_out,
            output_truncated=stdout_capture.overflowed or stderr_capture.overflowed,
        )

    def _require_capabilities(self, spec: CommandSpec, policy: SandboxPolicy) -> None:
        capabilities = self.capabilities()
        missing: list[str] = []
        if not policy.network_access and not capabilities.network_isolation:
            missing.append("network_isolation")
        if not capabilities.memory_limit:
            missing.append("memory_limit")
        if not capabilities.process_limit:
            missing.append("process_limit")
        if not capabilities.process_tree_kill:
            missing.append("process_tree_kill")
        if not capabilities.streaming_output_limit:
            missing.append("streaming_output_limit")
        if spec.trust_level is SandboxExecutionTrust.UNTRUSTED_CODE:
            for capability in ("strong_isolation", "filesystem_isolation"):
                if not getattr(capabilities, capability):
                    missing.append(capability)
        if missing:
            raise EngineeringError(
                EngineeringErrorCode.CAPABILITY_UNAVAILABLE,
                "Sandbox runtime cannot prove the requested execution boundary",
                details={"missing_capabilities": sorted(set(missing))},
            )

    @classmethod
    def _resolve_executable(cls, requested: str, environment: dict[str, str]) -> str:
        try:
            if any(separator in requested for separator in ("/", "\\")):
                resolved = Path(requested).resolve(strict=True)
            else:
                found = shutil.which(requested, path=environment.get("PATH"))
                if found is None:
                    raise FileNotFoundError(requested)
                resolved = Path(found).resolve(strict=True)
        except (FileNotFoundError, OSError, RuntimeError) as exc:
            raise EngineeringError(
                EngineeringErrorCode.COMMAND_NOT_ALLOWED,
                "Requested executable could not be resolved to a canonical file",
                details={"executable": requested},
            ) from exc
        if not resolved.is_file():
            raise EngineeringError(
                EngineeringErrorCode.COMMAND_NOT_ALLOWED,
                "Requested executable is not a regular file",
                details={"executable": requested},
            )
        return os.path.normcase(str(resolved))

    @classmethod
    def _canonical_allowed_executables(cls, values: tuple[str, ...]) -> set[str]:
        allowed: set[str] = set()
        for value in values:
            candidate = Path(value)
            if not candidate.is_absolute():
                continue
            try:
                resolved = candidate.resolve(strict=True)
            except (OSError, RuntimeError):
                continue
            if resolved.is_file():
                allowed.add(os.path.normcase(str(resolved)))
        return allowed

    @staticmethod
    def _read_stream(stream: BinaryIO, capture: _OutputCapture, overflow: threading.Event) -> None:
        try:
            while True:
                chunk = stream.read(capture.read_size())
                if not chunk:
                    return
                capture.append(chunk)
                if capture.overflowed:
                    overflow.set()
                    return
        except (OSError, ValueError):
            return

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
        argv: tuple[str, ...],
        cwd: Path,
        environment: dict[str, str],
        policy: SandboxPolicy,
    ) -> tuple[subprocess.Popen[bytes], _JobHandle | None]:
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        job: _JobHandle | None = None
        if os.name == "nt":
            job = _create_windows_job(policy)
            creationflags |= getattr(subprocess, "CREATE_SUSPENDED", 0x00000004)
        try:
            process = subprocess.Popen(
                list(argv),
                cwd=cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                creationflags=creationflags,
                start_new_session=os.name != "nt",
            )
            if job is not None:
                try:
                    job.assign(process)
                    job.resume(process)
                except (OSError, AttributeError) as exc:
                    job.terminate()
                    process.kill()
                    process.wait()
                    raise EngineeringError(
                        EngineeringErrorCode.CAPABILITY_UNAVAILABLE,
                        "Sandbox process could not be attached to its Windows Job Object",
                        details={"reason": type(exc).__name__},
                    ) from None
            return process, job
        except OSError as exc:
            if job is not None:
                job.close()
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
    def _terminate(process: subprocess.Popen[bytes], job: _JobHandle | None) -> None:
        if job is not None:
            job.terminate()
            return
        killpg = cast(Any, getattr(os, "killpg", None))
        sigkill = getattr(signal, "SIGKILL", None)
        if os.name != "nt" and killpg is not None and sigkill is not None:
            try:
                killpg(process.pid, sigkill)
                return
            except (OSError, AttributeError):
                pass
        process.kill()

    @staticmethod
    def _bounded(value: bytes, limit: int = 4096) -> bytes:
        return value[:limit]
