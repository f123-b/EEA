"""Core build diagnostics and immutable BuildRun records."""

from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field

from eea_core.entities import EntityBase, Sha256
from eea_core.enums import BuildProfile, BuildStatus, EngineeringErrorCode, IssueSeverity


class BuildDiagnostic(EntityBase):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    severity: IssueSeverity
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=4000)
    file: str | None = Field(default=None, max_length=1000)
    line: int | None = Field(default=None, ge=1)
    column: int | None = Field(default=None, ge=1)
    phase: Literal["TOOLCHAIN", "CONFIGURE", "COMPILE", "LINK", "ARTIFACT"]


class BuildRun(EntityBase):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    firmware_id: UUID
    firmware_revision: int = Field(ge=1)
    source_revision_id: UUID
    build_input_snapshot_id: UUID
    status: BuildStatus
    profile: BuildProfile = BuildProfile.HOST_SMOKE
    toolchain_id: str = Field(min_length=1, max_length=200)
    toolchain_version: str = Field(default="UNKNOWN", max_length=200)
    environment_profile_hash: Sha256
    build_input_hash: Sha256
    command: list[str] = Field(default_factory=list)
    diagnostics: list[BuildDiagnostic] = Field(default_factory=list)
    stdout: str = Field(default="", max_length=200_000)
    stderr: str = Field(default="", max_length=200_000)
    artifact_hash: Sha256 | None = None
    error_code: EngineeringErrorCode | None = None
    duration_ms: int = Field(default=0, ge=0)


__all__ = ["BuildDiagnostic", "BuildRun"]
