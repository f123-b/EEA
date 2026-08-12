"""Core-neutral, deterministic test design and execution contracts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from eea_core.entities import EntityBase, Sha256

TEST_SCHEMA_VERSION = "1.0.0"
TEST_GENERATOR_VERSION = "m17-deterministic-1"
TEST_POLICY_VERSION = "m17-review-1"


def acceptance_criteria_hash(criteria: list[str]) -> str:
    """Hash the ordered acceptance-criteria facts without interpreting their text."""

    return hashlib.sha256(
        json.dumps(criteria, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


class TestType(StrEnum):
    REQUIREMENT = "REQUIREMENT"
    BUILD = "BUILD"
    STATIC_ANALYSIS = "STATIC_ANALYSIS"
    ERC = "ERC"
    PROTOCOL = "PROTOCOL"
    INTEGRATION = "INTEGRATION"
    MANUAL = "MANUAL"


class AutomationLevel(StrEnum):
    AUTOMATED = "AUTOMATED"
    SEMI_AUTOMATED = "SEMI_AUTOMATED"
    MANUAL = "MANUAL"


class TestExecutionStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


class RequirementTestSnapshot(BaseModel):
    """The requirement facts used when a TestIR was generated."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requirement_id: UUID
    revision: int = Field(ge=1)
    priority: str
    status: str
    acceptance_criteria_hash: Sha256


class TestCase(BaseModel):
    """A declarative test case.  Steps are data and are never executable code."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    code: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    type: TestType = TestType.REQUIREMENT
    requirement_ids: tuple[UUID, ...] = ()
    preconditions: tuple[str, ...] = ()
    setup: tuple[str, ...] = ()
    inputs: dict[str, object] = Field(default_factory=dict)
    steps: tuple[str, ...] = ()
    expected: tuple[str, ...] = ()
    timeout: str = "UNKNOWN"
    pass_condition: str = Field(min_length=1, max_length=2000)
    cleanup: tuple[str, ...] = ()
    automation_level: AutomationLevel = AutomationLevel.AUTOMATED
    executor_id: str | None = Field(default=None, max_length=100)
    executor_config: dict[str, object] = Field(default_factory=dict)
    required: bool = True
    evidence_ids: tuple[UUID, ...] = ()


class TestIR(EntityBase):
    """Test design SSOT; the canonical hash excludes entity timestamps."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: UUID
    requirement_ids: tuple[UUID, ...] = ()
    requirement_revisions: dict[UUID, int] = Field(default_factory=dict)
    requirement_snapshots: tuple[RequirementTestSnapshot, ...] = ()
    cases: tuple[TestCase, ...] = ()
    input_hash: Sha256
    generator_version: str = TEST_GENERATOR_VERSION
    policy_version: str = TEST_POLICY_VERSION
    evidence_ids: tuple[UUID, ...] = ()

    @classmethod
    def build(
        cls,
        *,
        project_id: UUID,
        requirement_ids: tuple[UUID, ...],
        cases: tuple[TestCase, ...],
        requirement_revisions: dict[UUID, int] | None = None,
        requirement_snapshots: tuple[RequirementTestSnapshot, ...] = (),
        generator_version: str = TEST_GENERATOR_VERSION,
        policy_version: str = TEST_POLICY_VERSION,
        evidence_ids: tuple[UUID, ...] = (),
        **kwargs: Any,
    ) -> TestIR:
        input_hash = cls.compute_input_hash(
            project_id=project_id,
            requirement_ids=requirement_ids,
            cases=cases,
            requirement_revisions=requirement_revisions or {},
            requirement_snapshots=requirement_snapshots,
            generator_version=generator_version,
            policy_version=policy_version,
            evidence_ids=evidence_ids,
        )
        return cls(
            id=uuid5(project_id, f"m17-test-ir:{input_hash}"),
            project_id=project_id,
            requirement_ids=requirement_ids,
            requirement_revisions=requirement_revisions or {},
            requirement_snapshots=requirement_snapshots,
            cases=cases,
            input_hash=input_hash,
            generator_version=generator_version,
            policy_version=policy_version,
            evidence_ids=evidence_ids,
            **kwargs,
        )

    @staticmethod
    def canonical_case(case: TestCase) -> dict[str, object]:
        return case.model_dump(mode="json", exclude_none=True)

    @classmethod
    def canonical_payload(
        cls,
        *,
        project_id: UUID,
        requirement_ids: tuple[UUID, ...],
        cases: tuple[TestCase, ...],
        requirement_revisions: dict[UUID, int] | None,
        requirement_snapshots: tuple[RequirementTestSnapshot, ...],
        generator_version: str,
        policy_version: str,
        evidence_ids: tuple[UUID, ...],
    ) -> dict[str, object]:
        return {
            "project_id": str(project_id),
            "requirement_ids": sorted(str(item) for item in requirement_ids),
            "requirement_revisions": {
                str(key): value
                for key, value in sorted(
                    (requirement_revisions or {}).items(), key=lambda item: str(item[0])
                )
            },
            "requirement_snapshots": sorted(
                (item.model_dump(mode="json") for item in requirement_snapshots),
                key=lambda item: str(item["requirement_id"]),
            ),
            "cases": sorted(
                (cls.canonical_case(item) for item in cases), key=lambda item: str(item["id"])
            ),
            "generator_version": generator_version,
            "policy_version": policy_version,
            "evidence_ids": sorted(str(item) for item in evidence_ids),
        }

    @classmethod
    def compute_input_hash(
        cls,
        *,
        project_id: UUID,
        requirement_ids: tuple[UUID, ...],
        cases: tuple[TestCase, ...],
        requirement_revisions: dict[UUID, int] | None = None,
        requirement_snapshots: tuple[RequirementTestSnapshot, ...] = (),
        generator_version: str,
        policy_version: str,
        evidence_ids: tuple[UUID, ...],
    ) -> str:
        serialized = json.dumps(
            cls.canonical_payload(
                project_id=project_id,
                requirement_ids=requirement_ids,
                cases=cases,
                requirement_revisions=requirement_revisions,
                requirement_snapshots=requirement_snapshots,
                generator_version=generator_version,
                policy_version=policy_version,
                evidence_ids=evidence_ids,
            ),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(serialized).hexdigest()


class TestCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    test_case_id: UUID
    test_case_code: str
    status: TestExecutionStatus
    duration_ms: int = Field(default=0, ge=0)
    message: str = ""
    observed: object | None = None
    expected: object | None = None
    evidence_ids: tuple[UUID, ...] = ()
    executor_id: str | None = None
    failure: dict[str, object] | None = None


class TestRun(EntityBase):
    """Immutable execution record bound to a TestIR and SourceRevision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: UUID
    test_ir_id: UUID
    test_ir_revision: int = Field(ge=1)
    test_input_hash: Sha256
    source_revision_id: UUID
    status: TestExecutionStatus
    started_at: datetime
    finished_at: datetime | None = None
    case_results: tuple[TestCaseResult, ...] = ()
    tool_versions: dict[str, str] = Field(default_factory=dict)
    evidence_ids: tuple[UUID, ...] = ()

    @classmethod
    def aggregate_status(cls, results: tuple[TestCaseResult, ...]) -> TestExecutionStatus:
        statuses = {result.status for result in results}
        for status in (
            TestExecutionStatus.FAIL,
            TestExecutionStatus.BLOCKED,
            TestExecutionStatus.UNKNOWN,
            TestExecutionStatus.SKIPPED,
        ):
            if status in statuses:
                return status
        return TestExecutionStatus.PASS if results else TestExecutionStatus.UNKNOWN


def deterministic_case_id(
    project_id: UUID,
    requirement_id: UUID,
    requirement_revision: int,
    criterion_index: int,
    generator_version: str = TEST_GENERATOR_VERSION,
) -> UUID:
    return uuid5(
        project_id,
        f"{requirement_id}:{requirement_revision}:{criterion_index}:{generator_version}",
    )


__all__ = [
    "TEST_GENERATOR_VERSION",
    "TEST_POLICY_VERSION",
    "TEST_SCHEMA_VERSION",
    "AutomationLevel",
    "RequirementTestSnapshot",
    "TestCase",
    "TestCaseResult",
    "TestExecutionStatus",
    "TestIR",
    "TestRun",
    "TestType",
    "acceptance_criteria_hash",
    "deterministic_case_id",
]
