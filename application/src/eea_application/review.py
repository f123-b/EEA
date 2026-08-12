"""Deterministic M17 coverage and review services."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from eea_core.build import BuildRun
from eea_core.enums import IssueSeverity, RequirementPriority, RequirementStatus
from eea_core.pin_planner import RuleResult
from eea_core.requirements import Requirement
from eea_core.review import ReviewFinding, ReviewPolicy, ReviewRun, aggregate_status
from eea_core.schematic import ErcReport
from eea_core.static_analysis import FirmwareStaticAnalysis
from eea_core.testing import TestExecutionStatus, TestIR, TestRun


class CoverageResult:
    def __init__(
        self,
        *,
        total_requirements: int,
        release_critical_requirements: int,
        covered_requirements: int,
        verified_requirements: int,
        uncovered_requirement_ids: tuple[UUID, ...],
        unexecuted_requirement_ids: tuple[UUID, ...],
        failing_requirement_ids: tuple[UUID, ...],
        blocked_requirement_ids: tuple[UUID, ...],
        unknown_requirement_ids: tuple[UUID, ...],
    ) -> None:
        self.total_requirements = total_requirements
        self.release_critical_requirements = release_critical_requirements
        self.covered_requirements = covered_requirements
        self.verified_requirements = verified_requirements
        self.uncovered_requirement_ids = uncovered_requirement_ids
        self.unexecuted_requirement_ids = unexecuted_requirement_ids
        self.failing_requirement_ids = failing_requirement_ids
        self.blocked_requirement_ids = blocked_requirement_ids
        self.unknown_requirement_ids = unknown_requirement_ids
        self.design_coverage_ratio = (
            covered_requirements / total_requirements if total_requirements else 1.0
        )
        self.verification_coverage_ratio = (
            verified_requirements / total_requirements if total_requirements else 1.0
        )


class TestCoverageService:
    def calculate(
        self,
        requirements: list[Requirement],
        test_ir: TestIR | None,
        test_run: TestRun | None,
    ) -> CoverageResult:
        cases = test_ir.cases if test_ir else ()
        results = (
            {result.test_case_id: result for result in test_run.case_results} if test_run else {}
        )
        covered: set[UUID] = set()
        verified: set[UUID] = set()
        failing: set[UUID] = set()
        blocked: set[UUID] = set()
        unknown: set[UUID] = set()
        unexecuted: set[UUID] = set()
        for requirement in requirements:
            required_cases = [
                case for case in cases if requirement.id in case.requirement_ids and case.required
            ]
            if required_cases:
                covered.add(requirement.id)
            statuses = [results[case.id].status for case in required_cases if case.id in results]
            if len(statuses) != len(required_cases):
                unexecuted.add(requirement.id)
            if required_cases and len(statuses) == len(required_cases):
                if all(status is TestExecutionStatus.PASS for status in statuses):
                    verified.add(requirement.id)
                if TestExecutionStatus.FAIL in statuses:
                    failing.add(requirement.id)
                if TestExecutionStatus.BLOCKED in statuses:
                    blocked.add(requirement.id)
                if (
                    TestExecutionStatus.UNKNOWN in statuses
                    or TestExecutionStatus.SKIPPED in statuses
                ):
                    unknown.add(requirement.id)
        release = [
            item
            for item in requirements
            if item.priority is RequirementPriority.MUST
            and item.status is RequirementStatus.ACCEPTED
        ]
        return CoverageResult(
            total_requirements=len(requirements),
            release_critical_requirements=len(release),
            covered_requirements=len(covered),
            verified_requirements=len(verified),
            uncovered_requirement_ids=tuple(
                item.id for item in requirements if item.id not in covered
            ),
            unexecuted_requirement_ids=tuple(sorted(unexecuted, key=str)),
            failing_requirement_ids=tuple(sorted(failing, key=str)),
            blocked_requirement_ids=tuple(sorted(blocked, key=str)),
            unknown_requirement_ids=tuple(sorted(unknown, key=str)),
        )


class ReviewEngine:
    """Pure deterministic review engine. It has no MotorControl or AI dependency."""

    def review(
        self,
        *,
        project_id: UUID,
        source_revision_id: UUID,
        requirements: list[Requirement],
        test_ir: TestIR | None = None,
        test_run: TestRun | None = None,
        build_run: BuildRun | None = None,
        static_analysis: FirmwareStaticAnalysis | None = None,
        erc_report: ErcReport | None = None,
        rule_results: list[RuleResult] | None = None,
        policy: ReviewPolicy | None = None,
    ) -> ReviewRun:
        policy = ReviewPolicy.model_validate(policy or ReviewPolicy())
        findings: list[ReviewFinding] = []
        statuses: list[TestExecutionStatus] = []

        def add(
            code: str,
            title: str,
            message: str,
            kind: str,
            ref: str,
            status: TestExecutionStatus,
            severity: IssueSeverity,
            affected: tuple[str, ...] = (),
        ) -> None:
            finding = ReviewFinding(
                code=code,
                title=title,
                message=message,
                source_kind=kind,
                source_ref=ref,
                status=status,
                severity=severity,
                affected_refs=affected,
            ).with_dedupe_key(project_id)
            findings.append(finding)
            statuses.append(status)

        release_requirements = [
            item
            for item in requirements
            if item.priority is RequirementPriority.MUST
            and item.status is RequirementStatus.ACCEPTED
        ]
        cases = test_ir.cases if test_ir else ()
        for requirement in release_requirements:
            required_cases = [
                case for case in cases if requirement.id in case.requirement_ids and case.required
            ]
            if not required_cases:
                add(
                    "P0_TEST_MISSING",
                    "Release-critical requirement has no test",
                    f"{requirement.code} has no required TestCase",
                    "Requirement",
                    str(requirement.id),
                    TestExecutionStatus.FAIL,
                    IssueSeverity.CRITICAL,
                    (requirement.code,),
                )

        if policy.require_tests:
            if test_run is None:
                add(
                    "MISSING_REQUIRED_INPUT",
                    "Required test execution is missing",
                    "A required TestRun is not available",
                    "TestRun",
                    str(test_ir.id) if test_ir else "missing",
                    TestExecutionStatus.BLOCKED,
                    IssueSeverity.CRITICAL,
                )
            elif (
                test_ir is None
                or test_run.test_ir_id != test_ir.id
                or test_run.test_input_hash != test_ir.input_hash
            ):
                add(
                    "TEST_IR_MISMATCH",
                    "Test execution is stale",
                    "TestRun does not match the selected TestIR revision or hash",
                    "TestRun",
                    str(test_run.id),
                    TestExecutionStatus.BLOCKED,
                    IssueSeverity.CRITICAL,
                )
            elif test_run.source_revision_id != source_revision_id:
                add(
                    "SOURCE_REVISION_MISMATCH",
                    "Source revision mismatch",
                    "TestRun source revision differs from review source revision",
                    "TestRun",
                    str(test_run.id),
                    TestExecutionStatus.BLOCKED,
                    IssueSeverity.CRITICAL,
                )
            else:
                for test_result in test_run.case_results:
                    if test_result.status is not TestExecutionStatus.PASS:
                        add(
                            "TEST_RESULT_" + test_result.status.value,
                            "Test case is not PASS",
                            test_result.message
                            or f"Test case status is {test_result.status.value}",
                            "TestCaseResult",
                            test_result.test_case_code,
                            test_result.status,
                            IssueSeverity.CRITICAL,
                        )
                statuses.append(test_run.status)

        def source_status(status: object) -> TestExecutionStatus:
            value = getattr(status, "value", status)
            return TestExecutionStatus(str(value))

        if policy.require_build:
            if build_run is None:
                add(
                    "MISSING_REQUIRED_INPUT",
                    "Required build is missing",
                    "No BuildRun is available",
                    "BuildRun",
                    "missing",
                    TestExecutionStatus.BLOCKED,
                    IssueSeverity.CRITICAL,
                )
            else:
                build_status = source_status(build_run.status)
                statuses.append(build_status)
                if build_status is not TestExecutionStatus.PASS:
                    add(
                        "BUILD_" + build_status.value,
                        "Build gate is not PASS",
                        f"BuildRun status is {build_status.value}",
                        "BuildRun",
                        str(build_run.id),
                        build_status,
                        IssueSeverity.CRITICAL,
                    )
                if build_run.source_revision_id != source_revision_id:
                    add(
                        "SOURCE_REVISION_MISMATCH",
                        "Source revision mismatch",
                        "BuildRun source revision differs from review source revision",
                        "BuildRun",
                        str(build_run.id),
                        TestExecutionStatus.BLOCKED,
                        IssueSeverity.CRITICAL,
                    )

        if policy.require_static_analysis:
            if static_analysis is None:
                add(
                    "MISSING_REQUIRED_INPUT",
                    "Required static analysis is missing",
                    "No analysis is available",
                    "FirmwareStaticAnalysis",
                    "missing",
                    TestExecutionStatus.BLOCKED,
                    IssueSeverity.CRITICAL,
                )
            else:
                analysis_status = source_status(static_analysis.status)
                statuses.append(analysis_status)
                if analysis_status is not TestExecutionStatus.PASS:
                    add(
                        "STATIC_ANALYSIS_" + analysis_status.value,
                        "Static analysis gate is not PASS",
                        f"Static analysis status is {analysis_status.value}",
                        "FirmwareStaticAnalysis",
                        str(static_analysis.id),
                        analysis_status,
                        IssueSeverity.CRITICAL,
                    )
                for static_rule in static_analysis.rule_results:
                    if static_rule.status in {"FAIL", "UNKNOWN"}:
                        rule_status = TestExecutionStatus(static_rule.status)
                        add(
                            "RULE_" + static_rule.status,
                            "Static analysis rule is not PASS",
                            f"Rule {static_rule.rule_id} status is {static_rule.status}",
                            "RuleResult",
                            static_rule.rule_id,
                            rule_status,
                            static_rule.severity,
                            tuple(static_rule.affected_refs),
                        )
                if static_analysis.source_revision_id != source_revision_id:
                    add(
                        "SOURCE_REVISION_MISMATCH",
                        "Source revision mismatch",
                        (
                            "FirmwareStaticAnalysis source revision differs from "
                            "review source revision"
                        ),
                        "FirmwareStaticAnalysis",
                        str(static_analysis.id),
                        TestExecutionStatus.BLOCKED,
                        IssueSeverity.CRITICAL,
                    )

        for rule in rule_results or []:
            if rule.status in {"FAIL", "UNKNOWN"}:
                rule_status = TestExecutionStatus(rule.status)
                add(
                    "RULE_" + rule.status,
                    "Deterministic rule is not PASS",
                    f"Rule {rule.rule_id} status is {rule.status}",
                    "RuleResult",
                    rule.rule_id,
                    rule_status,
                    rule.severity,
                    tuple(rule.affected_refs),
                )

        if policy.require_erc:
            if erc_report is None:
                add(
                    "MISSING_REQUIRED_INPUT",
                    "Required ERC report is missing",
                    "No ERC report is available",
                    "ErcReport",
                    "missing",
                    TestExecutionStatus.BLOCKED,
                    IssueSeverity.CRITICAL,
                )
            else:
                erc_status = source_status(erc_report.status)
                statuses.append(erc_status)
                if erc_status is not TestExecutionStatus.PASS:
                    add(
                        "ERC_" + erc_status.value,
                        "ERC gate is not PASS",
                        f"ERC status is {erc_status.value}",
                        "ErcReport",
                        str(erc_report.id),
                        erc_status,
                        IssueSeverity.CRITICAL,
                    )
                for issue in erc_report.issues:
                    if issue.severity.value in {"CRITICAL", "HIGH"}:
                        add(
                            "ERC_ISSUE",
                            issue.title,
                            issue.description or issue.title,
                            "ErcIssue",
                            issue.code,
                            TestExecutionStatus.FAIL,
                            issue.severity,
                            tuple(issue.affected_refs),
                        )

        if not statuses:
            statuses.append(TestExecutionStatus.UNKNOWN)
        status = aggregate_status(statuses)
        input_hash = hashlib.sha256(
            json.dumps(
                {
                    "project_id": str(project_id),
                    "source_revision_id": str(source_revision_id),
                    "requirements": sorted(str(item.id) for item in requirements),
                    "test_ir": str(test_ir.id) if test_ir else None,
                    "test_run": str(test_run.id) if test_run else None,
                    "build": str(build_run.id) if build_run else None,
                    "static": str(static_analysis.id) if static_analysis else None,
                    "erc": str(erc_report.id) if erc_report else None,
                    "policy": policy.model_dump(mode="json"),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        return ReviewRun(
            project_id=project_id,
            source_revision_id=source_revision_id,
            policy_version=policy.version,
            input_hash=input_hash,
            build_run_id=build_run.id if build_run else None,
            static_analysis_id=static_analysis.id if static_analysis else None,
            test_run_id=test_run.id if test_run else None,
            test_ir_id=test_ir.id if test_ir else None,
            test_ir_revision=test_ir.revision if test_ir else None,
            status=status,
            findings=tuple(findings),
        )


__all__ = ["CoverageResult", "ReviewEngine", "TestCoverageService"]
