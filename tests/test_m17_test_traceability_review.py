"""M17 focused tests for deterministic tests, review gates, and dedupe keys."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from eea_application.review import ReviewEngine, TestCoverageService
from eea_application.testing import (
    ControlledRequirementExecutor,
)
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
from eea_core.pin_planner import RuleResult
from eea_core.requirements import Requirement
from eea_core.review import ReviewFinding, ReviewStatus
from eea_core.schematic import ErcReport
from eea_core.static_analysis import FirmwareStaticAnalysis
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
        requirement_revisions=generated.requirement_revisions,
        requirement_snapshots=generated.requirement_snapshots,
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


def test_gap_requirement_revision_is_in_test_ir_hash_even_without_criteria() -> None:
    first = _requirement(criteria=[])
    first_ir = GenerationService().generate(PROJECT, [first]).test_ir
    second_ir = (
        GenerationService().generate(PROJECT, [first.model_copy(update={"revision": 2})]).test_ir
    )
    assert first_ir.cases == second_ir.cases == ()
    assert first_ir.input_hash != second_ir.input_hash


class _PassExecutor:
    executor_id = "structured.pass"
    controlled = True

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


def test_default_controlled_requirement_executor_is_project_scoped_and_exact() -> None:
    registry = ExecutorRegistry()
    registry.ensure_project(PROJECT)
    case = TestCase(
        id=uuid4(),
        code="T1",
        title="structured",
        pass_condition="pass",
        requirement_ids=(uuid4(),),
        expected=("fact",),
        executor_id=ControlledRequirementExecutor.executor_id,
        executor_config={"fact": "requirement.acceptance_criteria_present", "expected": True},
    )
    assert registry.execute(case, project_id=PROJECT).status is TestExecutionStatus.PASS
    assert registry.execute(case, project_id=uuid4()).status is TestExecutionStatus.BLOCKED
    arbitrary = case.model_copy(update={"executor_config": {"command": "echo PASS"}})
    assert registry.execute(arbitrary, project_id=PROJECT).status is TestExecutionStatus.BLOCKED


def test_coverage_rejects_stale_snapshot_test_run_source_and_missing_result() -> None:
    requirement = _requirement(criteria=["one", "two"])
    test_ir = GenerationService().generate(PROJECT, [requirement]).test_ir
    registry = ExecutorRegistry()
    registry.ensure_project(PROJECT)
    run = RunService(registry).run(project_id=PROJECT, test_ir=test_ir, source_revision_id=SOURCE)
    current = TestCoverageService().calculate(
        [requirement], test_ir, run, source_revision_id=SOURCE
    )
    assert current.verified_requirements == 1
    stale_requirement = requirement.model_copy(update={"revision": 2})
    stale = TestCoverageService().calculate(
        [stale_requirement], test_ir, run, source_revision_id=SOURCE
    )
    assert stale.verified_requirements == 0
    assert stale.stale_requirement_ids == (requirement.id,)
    stale_run = run.model_copy(update={"test_ir_revision": run.test_ir_revision + 1})
    assert (
        TestCoverageService()
        .calculate([requirement], test_ir, stale_run, source_revision_id=SOURCE)
        .verified_requirements
        == 0
    )
    assert (
        TestCoverageService()
        .calculate([requirement], test_ir, run, source_revision_id=uuid4())
        .verified_requirements
        == 0
    )
    incomplete = run.model_copy(update={"case_results": run.case_results[:1]})
    assert (
        TestCoverageService()
        .calculate([requirement], test_ir, incomplete, source_revision_id=SOURCE)
        .verified_requirements
        == 0
    )


def test_review_missing_or_duplicate_required_results_is_blocked() -> None:
    requirement = _requirement(criteria=["one", "two"])
    test_ir = GenerationService().generate(PROJECT, [requirement]).test_ir
    registry = ExecutorRegistry()
    registry.ensure_project(PROJECT)
    run = RunService(registry).run(project_id=PROJECT, test_ir=test_ir, source_revision_id=SOURCE)
    missing = run.model_copy(update={"case_results": run.case_results[:1]})
    duplicate = run.model_copy(update={"case_results": (*run.case_results, run.case_results[0])})
    for candidate in (missing, duplicate):
        review = ReviewEngine().review(
            project_id=PROJECT,
            source_revision_id=SOURCE,
            requirements=[requirement],
            test_ir=test_ir,
            test_run=candidate,
        )
        assert review.status is ReviewStatus.BLOCKED
        assert any(item.code == "MISSING_REQUIRED_TEST_RESULT" for item in review.findings)


def test_skipped_required_result_maps_to_blocked_review() -> None:
    requirement = _requirement()
    test_ir = GenerationService().generate(PROJECT, [requirement]).test_ir
    registry = ExecutorRegistry()
    registry.ensure_project(PROJECT)
    run = RunService(registry).run(project_id=PROJECT, test_ir=test_ir, source_revision_id=SOURCE)
    skipped = run.case_results[0].model_copy(update={"status": TestExecutionStatus.SKIPPED})
    review = ReviewEngine().review(
        project_id=PROJECT,
        source_revision_id=SOURCE,
        requirements=[requirement],
        test_ir=test_ir,
        test_run=run.model_copy(
            update={"status": TestExecutionStatus.SKIPPED, "case_results": (skipped,)}
        ),
    )
    assert review.status is ReviewStatus.BLOCKED
    assert review.status.value != "SKIPPED"


def test_deterministic_failures_are_not_policy_bypassable() -> None:
    requirement = _requirement()
    firmware_id = uuid4()
    build_kwargs = {
        "project_id": PROJECT,
        "firmware_id": firmware_id,
        "firmware_revision": 1,
        "source_revision_id": SOURCE,
        "build_input_snapshot_id": uuid4(),
        "profile": BuildProfile.HOST_SMOKE,
        "toolchain_id": "fixture",
        "environment_profile_hash": "0" * 64,
        "build_input_hash": "1" * 64,
    }
    failing_build = BuildRun(status=BuildStatus.FAIL, **build_kwargs)
    assert (
        ReviewEngine()
        .review(
            project_id=PROJECT,
            source_revision_id=SOURCE,
            requirements=[requirement],
            build_run=failing_build,
            policy={"require_build": False, "require_tests": False},
        )
        .status
        is ReviewStatus.FAIL
    )
    static = FirmwareStaticAnalysis(
        project_id=PROJECT,
        firmware_id=firmware_id,
        firmware_revision=1,
        source_revision_id=SOURCE,
        input_hash="2" * 64,
        ruleset_version="r1",
        status="FAIL",
    )
    assert (
        ReviewEngine()
        .review(
            project_id=PROJECT,
            source_revision_id=SOURCE,
            requirements=[requirement],
            static_analysis=static,
            policy={"require_static_analysis": False, "require_tests": False},
        )
        .status
        is ReviewStatus.FAIL
    )
    erc = ErcReport(
        project_id=PROJECT,
        schematic_id=uuid4(),
        schematic_revision=1,
        circuit_id=uuid4(),
        circuit_revision=1,
        status="FAIL",
    )
    assert (
        ReviewEngine()
        .review(
            project_id=PROJECT,
            source_revision_id=SOURCE,
            requirements=[requirement],
            erc_report=erc,
            policy={"require_erc": False, "require_tests": False},
        )
        .status
        is ReviewStatus.FAIL
    )


def test_build_pending_and_running_are_blocked() -> None:
    requirement = _requirement(priority=RequirementPriority.SHOULD)
    for build_status in (BuildStatus.PENDING, BuildStatus.RUNNING):
        build = BuildRun(
            project_id=PROJECT,
            firmware_id=uuid4(),
            firmware_revision=1,
            source_revision_id=SOURCE,
            build_input_snapshot_id=uuid4(),
            status=build_status,
            profile=BuildProfile.HOST_SMOKE,
            toolchain_id="fixture",
            environment_profile_hash="0" * 64,
            build_input_hash="1" * 64,
        )
        review = ReviewEngine().review(
            project_id=PROJECT,
            source_revision_id=SOURCE,
            requirements=[requirement],
            build_run=build,
            policy={"require_tests": False},
        )
        assert review.status is ReviewStatus.BLOCKED


def test_review_hash_changes_with_requirement_priority_and_status() -> None:
    requirement = _requirement()
    engine = ReviewEngine()
    base = engine.review(
        project_id=PROJECT,
        source_revision_id=SOURCE,
        requirements=[requirement],
        policy={"require_tests": False},
    )
    priority = engine.review(
        project_id=PROJECT,
        source_revision_id=SOURCE,
        requirements=[requirement.model_copy(update={"priority": RequirementPriority.SHOULD})],
        policy={"require_tests": False},
    )
    status = engine.review(
        project_id=PROJECT,
        source_revision_id=SOURCE,
        requirements=[requirement.model_copy(update={"status": RequirementStatus.CANDIDATE})],
        policy={"require_tests": False},
    )
    assert base.input_hash != priority.input_hash
    assert base.input_hash != status.input_hash


def test_rule_result_evidence_propagates_to_review_finding() -> None:
    evidence_id = uuid4()
    rule = RuleResult(
        project_id=PROJECT,
        rule_id="RULE_M17",
        rule_version="1",
        stage="RELEASE_GATE",
        status="FAIL",
        severity=IssueSeverity.HIGH,
        evidence_ids=[evidence_id],
    )
    review = ReviewEngine().review(
        project_id=PROJECT,
        source_revision_id=SOURCE,
        requirements=[_requirement()],
        rule_results=[rule],
        policy={"require_tests": False},
    )
    finding = next(item for item in review.findings if item.code == "RULE_FAIL")
    assert finding.evidence_ids == (evidence_id,)


def test_test_run_aggregate_never_promotes_non_pass() -> None:
    generated = GenerationService().generate(PROJECT, [_requirement()]).test_ir
    registry = ExecutorRegistry()
    registry.register_for_project(PROJECT, _PassExecutor())
    executable = generated.cases[0].model_copy(update={"executor_id": "structured.pass"})
    generated = TestIR.build(
        project_id=PROJECT,
        requirement_ids=generated.requirement_ids,
        requirement_revisions=generated.requirement_revisions,
        requirement_snapshots=generated.requirement_snapshots,
        cases=(executable,),
    )
    run = RunService(registry).run(project_id=PROJECT, test_ir=generated, source_revision_id=SOURCE)
    assert run.status is TestExecutionStatus.PASS
    blocked = generated.cases[0].model_copy(update={"executor_id": "missing"})
    blocked_ir = TestIR.build(
        project_id=PROJECT,
        requirement_ids=generated.requirement_ids,
        requirement_revisions=generated.requirement_revisions,
        requirement_snapshots=generated.requirement_snapshots,
        cases=(blocked,),
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
    assert review.status is ReviewStatus.FAIL
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
    registry = ExecutorRegistry()
    registry.register_for_project(PROJECT, _PassExecutor())
    executable = test_ir.cases[0].model_copy(update={"executor_id": "structured.pass"})
    test_ir = TestIR.build(
        project_id=PROJECT,
        requirement_ids=test_ir.requirement_ids,
        requirement_revisions=test_ir.requirement_revisions,
        requirement_snapshots=test_ir.requirement_snapshots,
        cases=(executable,),
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
    assert review.status is ReviewStatus.FAIL
    blocked = ReviewEngine().review(
        project_id=PROJECT,
        source_revision_id=uuid4(),
        requirements=[requirement],
        test_ir=test_ir,
        test_run=test_run,
    )
    assert blocked.status is ReviewStatus.BLOCKED
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
