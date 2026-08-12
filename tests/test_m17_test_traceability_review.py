"""M17 focused tests for deterministic tests, review gates, and dedupe keys."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from eea_application.review import ReviewEngine, TestCoverageService
from eea_application.testing import (
    TestExecutorRegistry as ExecutorRegistry,
)
from eea_application.testing import (
    TestGenerationService as GenerationService,
)
from eea_application.testing import (
    TestRunService as RunService,
)
from eea_core.build import BuildRun
from eea_core.enums import (
    BuildProfile,
    BuildStatus,
    IssueSeverity,
    RequirementPriority,
    RequirementStatus,
)
from eea_core.requirements import Requirement
from eea_core.review import ReviewFinding
from eea_core.testing import (
    AutomationLevel,
    TestCase,
    TestCaseResult,
    TestExecutionStatus,
    TestIR,
)

PROJECT = UUID("00000000-0000-0000-0000-000000000017")
SOURCE = UUID("00000000-0000-0000-0000-000000000018")


def _requirement(
    *,
    code: str = "REQ-SAFE-001",
    priority: RequirementPriority = RequirementPriority.MUST,
    status: RequirementStatus = RequirementStatus.ACCEPTED,
    criteria: list[str] | None = None,
) -> Requirement:
    return Requirement(
        project_id=PROJECT,
        code=code,
        title=code,
        statement="The system shall be safe.",
        priority=priority,
        status=status,
        acceptance_criteria=criteria if criteria is not None else ["observed state is safe"],
    )


def test_deterministic_generation_and_case_ids() -> None:
    requirement = _requirement()
    service = GenerationService()
    first = service.generate(PROJECT, [requirement]).test_ir
    second = service.generate(PROJECT, [requirement]).test_ir
    assert first.input_hash == second.input_hash
    assert first.cases[0].id == second.cases[0].id
    assert first.cases[0].code == "REQ_REQ-SAFE-001_1"


def test_test_ir_hash_is_order_invariant_and_revision_sensitive() -> None:
    requirement = _requirement()
    generated = GenerationService().generate(PROJECT, [requirement]).test_ir
    reordered = TestIR.build(
        project_id=PROJECT,
        requirement_ids=tuple(reversed(generated.requirement_ids)),
        cases=tuple(reversed(generated.cases)),
    )
    assert generated.input_hash == reordered.input_hash
    changed = requirement.model_copy(update={"revision": 2})
    changed_ir = GenerationService().generate(PROJECT, [changed]).test_ir
    assert generated.input_hash != changed_ir.input_hash


def test_missing_acceptance_criteria_is_a_gap_not_a_fabricated_test() -> None:
    result = GenerationService().generate(PROJECT, [_requirement(criteria=[])])
    assert result.test_ir.cases == ()
    assert result.coverage_gaps == (result.test_ir.requirement_ids[0],)


class _PassExecutor:
    executor_id = "structured.pass"

    def execute(self, case: TestCase) -> TestCaseResult:
        return TestCaseResult(
            id=uuid4(),
            test_case_id=case.id,
            test_case_code=case.code,
            status=TestExecutionStatus.PASS,
            executor_id=self.executor_id,
        )


def test_executor_registry_is_controlled_and_manual_is_fail_closed() -> None:
    registry = ExecutorRegistry((_PassExecutor(),))
    case = TestCase(
        id=uuid4(),
        code="T1",
        title="structured",
        pass_condition="pass",
        executor_id="structured.pass",
    )
    assert registry.execute(case).status is TestExecutionStatus.PASS
    unknown = case.model_copy(update={"executor_id": "unknown"})
    assert registry.execute(unknown).status is TestExecutionStatus.BLOCKED
    manual = case.model_copy(update={"automation_level": AutomationLevel.MANUAL})
    manual_result = registry.execute(manual)
    assert manual_result.status is TestExecutionStatus.BLOCKED
    assert "evidence" in manual_result.message.lower()


def test_test_run_aggregate_never_promotes_non_pass() -> None:
    generated = GenerationService().generate(PROJECT, [_requirement()]).test_ir
    registry = ExecutorRegistry((_PassExecutor(),))
    executable = generated.cases[0].model_copy(update={"executor_id": "structured.pass"})
    generated = TestIR.build(
        project_id=PROJECT, requirement_ids=generated.requirement_ids, cases=(executable,)
    )
    run = RunService(registry).run(project_id=PROJECT, test_ir=generated, source_revision_id=SOURCE)
    assert run.status is TestExecutionStatus.PASS
    blocked = generated.cases[0].model_copy(update={"executor_id": "missing"})
    blocked_ir = TestIR.build(
        project_id=PROJECT, requirement_ids=generated.requirement_ids, cases=(blocked,)
    )
    blocked_run = RunService(registry).run(
        project_id=PROJECT, test_ir=blocked_ir, source_revision_id=SOURCE
    )
    assert blocked_run.status is TestExecutionStatus.BLOCKED


def test_p0_missing_test_is_release_critical_fail() -> None:
    requirement = _requirement(criteria=[])
    review = ReviewEngine().review(
        project_id=PROJECT, source_revision_id=SOURCE, requirements=[requirement]
    )
    assert review.status is TestExecutionStatus.FAIL
    finding = next(item for item in review.findings if item.code == "P0_TEST_MISSING")
    assert finding.severity is IssueSeverity.CRITICAL
    assert finding.status is TestExecutionStatus.FAIL


def test_coverage_design_is_not_verification_until_all_required_pass() -> None:
    requirement = _requirement(criteria=["one", "two"])
    test_ir = GenerationService().generate(PROJECT, [requirement]).test_ir
    coverage = TestCoverageService().calculate([requirement], test_ir, None)
    assert coverage.covered_requirements == 1
    assert coverage.verified_requirements == 0
    results = tuple(
        TestCaseResult(
            id=uuid4(),
            test_case_id=case.id,
            test_case_code=case.code,
            status=TestExecutionStatus.PASS if index == 0 else TestExecutionStatus.UNKNOWN,
        )
        for index, case in enumerate(test_ir.cases)
    )
    from eea_core.testing import TestRun

    run = TestRun(
        project_id=PROJECT,
        test_ir_id=test_ir.id,
        test_ir_revision=test_ir.revision,
        test_input_hash=test_ir.input_hash,
        source_revision_id=SOURCE,
        status=TestExecutionStatus.UNKNOWN,
        started_at=datetime.now(UTC),
        case_results=results,
    )
    coverage = TestCoverageService().calculate([requirement], test_ir, run)
    assert coverage.verified_requirements == 0
    assert coverage.unknown_requirement_ids == (requirement.id,)


def test_review_failure_precedence_and_source_revision_mismatch() -> None:
    requirement = _requirement()
    test_ir = GenerationService().generate(PROJECT, [requirement]).test_ir
    registry = ExecutorRegistry((_PassExecutor(),))
    executable = test_ir.cases[0].model_copy(update={"executor_id": "structured.pass"})
    test_ir = TestIR.build(
        project_id=PROJECT, requirement_ids=test_ir.requirement_ids, cases=(executable,)
    )
    test_run = RunService(registry).run(
        project_id=PROJECT, test_ir=test_ir, source_revision_id=SOURCE
    )
    build = BuildRun(
        project_id=PROJECT,
        firmware_id=uuid4(),
        firmware_revision=1,
        source_revision_id=SOURCE,
        build_input_snapshot_id=uuid4(),
        status=BuildStatus.FAIL,
        profile=BuildProfile.HOST_SMOKE,
        toolchain_id="fixture",
        environment_profile_hash="0" * 64,
        build_input_hash="1" * 64,
    )
    review = ReviewEngine().review(
        project_id=PROJECT,
        source_revision_id=SOURCE,
        requirements=[requirement],
        test_ir=test_ir,
        test_run=test_run,
        build_run=build,
        policy={"require_build": True},
    )
    assert review.status is TestExecutionStatus.FAIL
    blocked = ReviewEngine().review(
        project_id=PROJECT,
        source_revision_id=uuid4(),
        requirements=[requirement],
        test_ir=test_ir,
        test_run=test_run,
    )
    assert blocked.status is TestExecutionStatus.BLOCKED
    assert any(item.code == "SOURCE_REVISION_MISMATCH" for item in blocked.findings)


def test_finding_dedupe_key_is_stable_and_affected_ref_sensitive() -> None:
    base = ReviewFinding(
        code="BUILD_FAIL",
        title="build",
        message="failed",
        source_kind="BuildRun",
        source_ref="build-1",
        severity=IssueSeverity.CRITICAL,
        status=TestExecutionStatus.FAIL,
        affected_refs=("a", "b"),
    )
    same = base.with_dedupe_key(PROJECT)
    reordered = base.model_copy(update={"affected_refs": ("b", "a")}).with_dedupe_key(PROJECT)
    different = base.model_copy(update={"affected_refs": ("a", "c")}).with_dedupe_key(PROJECT)
    assert same.dedupe_key == reordered.dedupe_key
    assert same.dedupe_key != different.dedupe_key
