"""Deterministic, Core-neutral M17 review contracts."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from eea_core.entities import EntityBase, Sha256
from eea_core.enums import IssueSeverity
from eea_core.testing import TestExecutionStatus

REVIEW_POLICY_VERSION = "m17-review-1"


class ReviewStatus(StrEnum):
    """Final review state; execution lifecycle states never leak into it."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    BLOCKED = "BLOCKED"


class ReviewPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = REVIEW_POLICY_VERSION
    require_build: bool = False
    require_static_analysis: bool = False
    require_erc: bool = False
    require_tests: bool = True


class ReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=300)
    message: str = Field(min_length=1, max_length=4000)
    source_kind: str = Field(min_length=1, max_length=100)
    source_ref: str = Field(min_length=1, max_length=300)
    severity: IssueSeverity
    status: TestExecutionStatus
    affected_refs: tuple[str, ...] = ()
    evidence_ids: tuple[UUID, ...] = ()
    deterministic: bool = True
    dedupe_key: str = ""

    def with_dedupe_key(self, project_id: UUID) -> ReviewFinding:
        payload = {
            "project_id": str(project_id),
            "code": self.code,
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "affected_refs": sorted(self.affected_refs),
        }
        key = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return self.model_copy(update={"dedupe_key": key})


class ReviewRun(EntityBase):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: UUID
    source_revision_id: UUID
    policy_version: str = REVIEW_POLICY_VERSION
    input_hash: Sha256
    build_run_id: UUID | None = None
    static_analysis_id: UUID | None = None
    test_run_id: UUID | None = None
    test_ir_id: UUID | None = None
    test_ir_revision: int | None = Field(default=None, ge=1)
    protocol_id: UUID | None = None
    protocol_revision: int | None = Field(default=None, ge=1)
    status: ReviewStatus
    findings: tuple[ReviewFinding, ...] = ()
    issue_ids: tuple[UUID, ...] = ()


def aggregate_status(statuses: list[TestExecutionStatus]) -> ReviewStatus:
    """Map execution states to the frozen four-state review result."""

    for candidate in (
        TestExecutionStatus.FAIL,
        TestExecutionStatus.BLOCKED,
        TestExecutionStatus.UNKNOWN,
    ):
        if candidate in statuses:
            return ReviewStatus(candidate.value)
    if TestExecutionStatus.SKIPPED in statuses:
        return ReviewStatus.BLOCKED
    if TestExecutionStatus.PASS in statuses:
        return ReviewStatus.PASS
    return ReviewStatus.UNKNOWN


__all__ = [
    "REVIEW_POLICY_VERSION",
    "ReviewFinding",
    "ReviewPolicy",
    "ReviewRun",
    "ReviewStatus",
    "aggregate_status",
]
