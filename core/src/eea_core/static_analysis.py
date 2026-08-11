"""Auditable firmware static-analysis contracts."""

from uuid import UUID

from pydantic import ConfigDict, Field

from eea_core.entities import EntityBase, Sha256
from eea_core.enums import StaticAnalysisStatus
from eea_core.pin_planner import RuleResult


class StaticAnalysisToolResult(EntityBase):
    """Bounded output from one static-analysis tool invocation."""

    model_config = ConfigDict(extra="forbid")

    tool_id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=200)
    status: StaticAnalysisStatus
    duration_ms: int = Field(default=0, ge=0)
    diagnostics: list[str] = Field(default_factory=list)
    stdout: str = Field(default="", max_length=200_000)
    stderr: str = Field(default="", max_length=200_000)


class FirmwareStaticAnalysis(EntityBase):
    """Immutable analysis result tied to a firmware and source revision."""

    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    firmware_id: UUID
    firmware_revision: int = Field(ge=1)
    source_revision_id: UUID
    build_input_snapshot_id: UUID | None = None
    input_hash: Sha256
    ruleset_version: str = Field(min_length=1, max_length=100)
    status: StaticAnalysisStatus
    rule_results: list[RuleResult] = Field(default_factory=list)
    tool_results: list[StaticAnalysisToolResult] = Field(default_factory=list)


__all__ = ["FirmwareStaticAnalysis", "StaticAnalysisToolResult"]
