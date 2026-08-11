"""Framework-free M5 sandbox contracts and path boundary primitives."""

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SafePath:
    """Resolve a user/archive path without allowing workspace escape or symlink escape."""

    __slots__ = ("_root",)

    def __init__(self, root: Path) -> None:
        self._root = root.resolve(strict=False)

    @property
    def root(self) -> Path:
        return self._root

    def resolve(self, relative: str | Path) -> Path:
        raw = os.fspath(relative)
        if not raw or "\x00" in raw:
            raise ValueError("path must be a non-empty, NUL-free relative path")
        # Validate both path grammars before using the host's Path implementation.
        # This keeps Windows drive/UNC inputs blocked when tests or services run on Linux.
        posix = PurePosixPath(raw.replace("\\", "/"))
        windows = PureWindowsPath(raw.replace("/", "\\"))
        if posix.is_absolute() or windows.is_absolute() or windows.root or windows.drive:
            raise ValueError("absolute, UNC, and drive-qualified paths are not allowed")
        if any(part == ".." for part in posix.parts) or any(part == ".." for part in windows.parts):
            raise ValueError("parent traversal is not allowed")
        candidate_path = Path(raw.replace("\\", os.sep))
        candidate = (self._root / candidate_path).resolve(strict=False)
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise ValueError("path resolves outside the workspace") from exc
        return candidate


class SandboxPolicy(BaseModel):
    """Explicit resource and capability policy for one isolated execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_archive_members: int = Field(default=10_000, ge=1)
    max_archive_bytes: int = Field(default=256 * 1024 * 1024, ge=1)
    max_member_bytes: int = Field(default=64 * 1024 * 1024, ge=1)
    max_compression_ratio: float = Field(default=100.0, gt=0)
    max_runtime_seconds: float = Field(default=30.0, gt=0)
    max_output_bytes: int = Field(default=1 * 1024 * 1024, ge=1)
    max_processes: int = Field(default=1, ge=1)
    max_memory_bytes: int = Field(default=512 * 1024 * 1024, ge=1)
    network_access: bool = False
    allowed_executables: tuple[str, ...] = ()
    allowed_environment: tuple[str, ...] = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")

    @field_validator("allowed_executables", "allowed_environment")
    @classmethod
    def normalize_names(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(value.strip() for value in values if value.strip())


class CommandSpec(BaseModel):
    """Structured argv command; shell syntax is intentionally not represented."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    argv: tuple[str, ...] = Field(min_length=1, max_length=128)
    cwd: str = "."
    environment: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float | None = Field(default=None, gt=0)
    network_required: bool = False

    @field_validator("argv")
    @classmethod
    def argv_is_nul_free(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value or "\x00" in value for value in values):
            raise ValueError("argv entries must be non-empty and NUL-free")
        return values

    @field_validator("cwd")
    @classmethod
    def cwd_is_relative(cls, value: str) -> str:
        if not value or "\x00" in value:
            raise ValueError("cwd must be a non-empty, NUL-free relative path")
        return value


class CommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int = Field(ge=0)
    timed_out: bool = False
    output_truncated: bool = False


class ArchiveExtractionReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    archive_name: str
    extracted_files: tuple[str, ...]
    total_bytes: int = Field(ge=0)


@dataclass(frozen=True, slots=True)
class SandboxWorkspace:
    """A named workspace whose every path operation goes through SafePath."""

    root: Path
    path_guard: SafePath

    @classmethod
    def from_root(cls, root: Path) -> "SandboxWorkspace":
        root.mkdir(parents=True, exist_ok=True)
        resolved = root.resolve(strict=True)
        return cls(root=resolved, path_guard=SafePath(resolved))

    def path(self, relative: str | Path = ".") -> Path:
        if os.fspath(relative) == ".":
            return self.root
        return self.path_guard.resolve(relative)

    def child(self, relative: str | Path) -> "SandboxWorkspace":
        child = self.path(relative)
        child.mkdir(parents=True, exist_ok=True)
        return SandboxWorkspace.from_root(child)
