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
from eea_core.testing import (
    TestExecutionStatus,
    TestIR,
    TestResultAuthority,
    TestRun,
    acceptance_criteria_hash,
)


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
        stale_requirement_ids: tuple[UUID, ...] = (),
        stale_test_run: bool = False,
        source_revision_id: UUID | None = None,
        invalid_result_case_ids: tuple[UUID, ...] = (),
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
        self.stale_requirement_ids = stale_requirement_ids
        self.stale_test_run = stale_test_run
        self.source_revision_id = source_revision_id
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
        *,
        source_revision_id: UUID | None = None,
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
        stale: set[UUID] = set()
        invalid_result_case_ids: set[UUID] = set()
        snapshot_map = {
            item.requirement_id: item for item in (test_ir.requirement_snapshots if test_ir else ())
        }
        for requirement in requirements:
            required_cases = [
                case for case in cases if requirement.id in case.requirement_ids and case.required
            ]
            if required_cases:
                covered.add(requirement.id)
            snapshot = snapshot_map.get(requirement.id)
            snapshot_is_stale = snapshot is not None and (
                snapshot.revision != requirement.revision
                or snapshot.priority != requirement.priority.value
                or snapshot.status != requirement.status.value
                or snapshot.acceptance_criteria_hash
                != acceptance_criteria_hash(requirement.acceptance_criteria)
            )
            revision_is_stale = snapshot is None and (
                test_ir is None
                or test_ir.requirement_revisions.get(requirement.id) != requirement.revision
            )
            if snapshot_is_stale or revision_is_stale:
                stale.add(requirement.id)
            statuses = [results[case.id].status for case in required_cases if case.id in results]
            result_counts = {
                case.id: sum(result.test_case_id == case.id for result in test_run.case_results)
                if test_run
                else 0
                for case in required_cases
            }
            invalid_for_requirement = {
                case_id for case_id, count in result_counts.items() if count != 1
            }
            invalid_result_case_ids.update(invalid_for_requirement)
            if len(statuses) != len(required_cases) or invalid_for_requirement:
                unexecuted.add(requirement.id)
            if TestExecutionStatus.FAIL in statuses:
                failing.add(requirement.id)
            if TestExecutionStatus.BLOCKED in statuses or TestExecutionStatus.SKIPPED in statuses:
                blocked.add(requirement.id)
            if any(
                not results[case.id].verification_authorized
                for case in required_cases
                if case.id in results
            ):
                blocked.add(requirement.id)
            if TestExecutionStatus.UNKNOWN in statuses:
                unknown.add(requirement.id)
            if (
                required_cases
                and len(statuses) == len(required_cases)
                and not invalid_for_requirement
                and not stale.intersection({requirement.id})
                and all(
                    results[case.id].status is TestExecutionStatus.PASS
                    and results[case.id].verification_authorized
                    for case in required_cases
                )
            ):
                verified.add(requirement.id)
        stale_test_run = bool(
            test_run
            and (
                test_ir is None
                or test_run.test_ir_id != test_ir.id
                or test_run.test_ir_revision != test_ir.revision
                or test_run.test_input_hash != test_ir.input_hash
                or (
                    source_revision_id is not None
                    and test_run.source_revision_id != source_revision_id
                )
            )
        )
        if stale_test_run:
            verified.clear()
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
            stale_requirement_ids=tuple(sorted(stale, key=str)),
            stale_test_run=stale_test_run,
            source_revision_id=source_revision_id
            or (test_run.source_revision_id if test_run else None),
            invalid_result_case_ids=tuple(sorted(invalid_result_case_ids, key=str)),
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
            evidence_ids: tuple[UUID, ...] = (),
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
                evidence_ids=evidence_ids,
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
            if not [
                case for case in cases if requirement.id in case.requirement_ids and case.required
            ]:
                add(
                    "P0_TEST_MISSING",
                    "Release-critical requirement has no test",
                    f"{requirement.code} has no required TestCase",
                    "Requirement",
                    str(requirement.id),
                    TestExecutionStatus.FAIL,
                    IssueSeverity.CRITICAL,
                    (requirement.code,),
                    tuple(requirement.source_evidence_ids),
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
                or test_run.test_ir_revision != test_ir.revision
                or test_run.test_input_hash != test_ir.input_hash
            ):
                add(
                    "STALE_TEST_IR",
                    "Test execution is stale",
                    "TestRun does not match the selected TestIR id, revision, or hash",
                    "TestRun",
                    str(test_ir.id) if test_ir else "missing",
                    TestExecutionStatus.BLOCKED,
                    IssueSeverity.CRITICAL,
                )
            elif test_run.source_revision_id != source_revision_id:
                add(
                    "SOURCE_REVISION_MISMATCH",
                    "Source revision mismatch",
                    "TestRun source revision differs from review source revision",
                    "TestRun",
                    f"{test_ir.id if test_ir else 'missing'}:{source_revision_id}",
                    TestExecutionStatus.BLOCKED,
                    IssueSeverity.CRITICAL,
                )
            else:
                required_ids = {case.id for case in cases if case.required}
                result_map = {result.test_case_id: result for result in test_run.case_results}
                missing = sorted(required_ids - result_map.keys(), key=str)
                counts = {
                    case_id: sum(result.test_case_id == case_id for result in test_run.case_results)
                    for case_id in required_ids
                }
                duplicate = sorted(
                    (case_id for case_id, count in counts.items() if count > 1), key=str
                )
                if missing or duplicate:
                    add(
                        "MISSING_REQUIRED_TEST_RESULT",
                        "Required test result is missing",
                        "TestRun does not contain exactly one result for every required TestCase",
                        "TestRun",
                        str(test_ir.id),
                        TestExecutionStatus.BLOCKED,
                        IssueSeverity.CRITICAL,
                        tuple(str(item) for item in (*missing, *duplicate)),
                    )
                for result in test_run.case_results:
                    if result.test_case_id in required_ids and (
                        result.status is not TestExecutionStatus.PASS
                        or not result.verification_authorized
                    ):
                        code = (
                            "TEST_RESULT_" + result.status.value
                            if result.status is not TestExecutionStatus.PASS
                            else (
                                "TEST_RESULT_CONTRACT_ONLY"
                                if result.result_authority is TestResultAuthority.CONTRACT_ONLY
                                else "TEST_RESULT_TRUSTED_EVIDENCE_MISSING"
                            )
                        )
                        add(
                            code,
                            "Test case is not PASS",
                            result.message
                            or (
                                "Test result has no verification authority"
                                if result.result_authority is TestResultAuthority.CONTRACT_ONLY
                                else "Trusted evidence is required for this result authority"
                            ),
                            "TestCaseResult",
                            result.test_case_code,
                            TestExecutionStatus.BLOCKED
                            if not result.verification_authorized
                            else result.status,
                            IssueSeverity.CRITICAL,
                            evidence_ids=result.evidence_ids,
                        )
                statuses.append(test_run.status)

        def source_status(value: object) -> TestExecutionStatus:
            raw = str(getattr(value, "value", value))
            if raw in {"PENDING", "RUNNING"}:
                return TestExecutionStatus.BLOCKED
            return TestExecutionStatus(raw)

        def build_finding(run: BuildRun) -> None:
            status = source_status(run.status)
            statuses.append(status)
            if status is not TestExecutionStatus.PASS:
                add(
                    "BUILD_" + str(run.status.value),
                    "Build gate is not PASS",
                    f"BuildRun status is {run.status.value}",
                    "BuildRun",
                    f"{run.firmware_id}:{run.profile.value}",
                    status,
                    IssueSeverity.CRITICAL,
                    (str(run.firmware_id), run.profile.value),
                )
            if run.source_revision_id != source_revision_id:
                add(
                    "SOURCE_REVISION_MISMATCH",
                    "Source revision mismatch",
                    "BuildRun source revision differs from review source revision",
                    "BuildRun",
                    f"{run.firmware_id}:{run.profile.value}",
                    TestExecutionStatus.BLOCKED,
                    IssueSeverity.CRITICAL,
                    (str(run.source_revision_id), str(source_revision_id)),
                )

        if build_run is None:
            if policy.require_build:
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
            build_finding(build_run)

        def analysis_finding(analysis: FirmwareStaticAnalysis) -> None:
            analysis_status = source_status(analysis.status)
            statuses.append(analysis_status)
            if analysis_status is not TestExecutionStatus.PASS:
                add(
                    "STATIC_ANALYSIS_" + analysis.status.value,
                    "Static analysis gate is not PASS",
                    f"Static analysis status is {analysis.status.value}",
                    "FirmwareStaticAnalysis",
                    f"{analysis.firmware_id}:{analysis.ruleset_version}",
                    analysis_status,
                    IssueSeverity.CRITICAL,
                )
            for rule in analysis.rule_results:
                if rule.status in {"FAIL", "UNKNOWN"}:
                    add(
                        "RULE_" + rule.status,
                        "Static analysis rule is not PASS",
                        f"Rule {rule.rule_id} status is {rule.status}",
                        "RuleResult",
                        f"{analysis.firmware_id}:{rule.rule_id}",
                        TestExecutionStatus(rule.status),
                        rule.severity,
                        tuple(rule.affected_refs),
                        tuple(rule.evidence_ids),
                    )
            if analysis.source_revision_id != source_revision_id:
                add(
                    "SOURCE_REVISION_MISMATCH",
                    "Source revision mismatch",
                    "FirmwareStaticAnalysis source revision differs from review source revision",
                    "FirmwareStaticAnalysis",
                    f"{analysis.firmware_id}:{analysis.ruleset_version}",
                    TestExecutionStatus.BLOCKED,
                    IssueSeverity.CRITICAL,
                )

        if static_analysis is None:
            if policy.require_static_analysis:
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
            analysis_finding(static_analysis)

        for rule in rule_results or []:
            if rule.status in {"FAIL", "UNKNOWN"}:
                add(
                    "RULE_" + rule.status,
                    "Deterministic rule is not PASS",
                    f"Rule {rule.rule_id} status is {rule.status}",
                    "RuleResult",
                    rule.rule_id,
                    TestExecutionStatus(rule.status),
                    rule.severity,
                    tuple(rule.affected_refs),
                    tuple(rule.evidence_ids),
                )

        if erc_report is None:
            if policy.require_erc:
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
                    "ERC_" + erc_report.status,
                    "ERC gate is not PASS",
                    f"ERC status is {erc_report.status}",
                    "ErcReport",
                    f"{erc_report.schematic_id}:{erc_report.schematic_revision}",
                    erc_status,
                    IssueSeverity.CRITICAL,
                    evidence_ids=tuple(erc_report.evidence_ids),
                )
            for issue in erc_report.issues:
                if issue.severity.value in {"CRITICAL", "HIGH"}:
                    add(
                        "ERC_ISSUE",
                        issue.title,
                        issue.description or issue.title,
                        "ErcIssue",
                        f"{erc_report.schematic_id}:{issue.code}",
                        TestExecutionStatus.FAIL,
                        issue.severity,
                        tuple(issue.affected_refs),
                        tuple(issue.evidence_ids),
                    )

        if test_ir:
            snapshots = {item.requirement_id: item for item in test_ir.requirement_snapshots}
            stale = [
                item
                for item in requirements
                if (
                    (
                        snapshots.get(item.id) is not None
                        and (
                            snapshots[item.id].revision != item.revision
                            or snapshots[item.id].priority != item.priority.value
                            or snapshots[item.id].status != item.status.value
                            or snapshots[item.id].acceptance_criteria_hash
                            != acceptance_criteria_hash(item.acceptance_criteria)
                        )
                    )
                    or (
                        snapshots.get(item.id) is None
                        and test_ir.requirement_revisions.get(item.id) != item.revision
                    )
                )
            ]
            if stale:
                add(
                    "STALE_TEST_IR",
                    "TestIR requirement snapshot is stale",
                    "Requirement revision, priority, or status differs from the TestIR snapshot",
                    "TestIR",
                    str(test_ir.id),
                    TestExecutionStatus.BLOCKED,
                    IssueSeverity.CRITICAL,
                    tuple(item.code for item in stale),
                    tuple(
                        evidence_id for item in stale for evidence_id in item.source_evidence_ids
                    ),
                )

        if not statuses:
            statuses.append(TestExecutionStatus.UNKNOWN)
        input_payload = {
            "project_id": str(project_id),
            "source_revision_id": str(source_revision_id),
            "requirements": sorted(
                (
                    {
                        "id": str(item.id),
                        "revision": item.revision,
                        "priority": item.priority.value,
                        "status": item.status.value,
                        "acceptance_criteria_hash": acceptance_criteria_hash(
                            item.acceptance_criteria
                        ),
                        "source_evidence_ids": sorted(
                            str(value) for value in item.source_evidence_ids
                        ),
                    }
                    for item in requirements
                ),
                key=lambda item: item["id"],
            ),
            "test_ir": {
                "id": str(test_ir.id),
                "revision": test_ir.revision,
                "input_hash": test_ir.input_hash,
            }
            if test_ir
            else None,
            "test_run": {
                "id": str(test_run.id),
                "test_ir_revision": test_run.test_ir_revision,
                "test_input_hash": test_run.test_input_hash,
                "source_revision_id": str(test_run.source_revision_id),
                "status": test_run.status.value,
                "case_results": sorted(
                    (item.model_dump(mode="json") for item in test_run.case_results),
                    key=lambda item: str(item["test_case_id"]),
                ),
            }
            if test_run
            else None,
            "build": {
                "id": str(build_run.id),
                "source_revision_id": str(build_run.source_revision_id),
                "status": build_run.status.value,
                "build_input_hash": build_run.build_input_hash,
            }
            if build_run
            else None,
            "static": {
                "id": str(static_analysis.id),
                "source_revision_id": str(static_analysis.source_revision_id),
                "input_hash": static_analysis.input_hash,
                "status": static_analysis.status.value,
                "ruleset_version": static_analysis.ruleset_version,
                "rule_results": sorted(
                    (item.model_dump(mode="json") for item in static_analysis.rule_results),
                    key=lambda item: item["rule_id"],
                ),
            }
            if static_analysis
            else None,
            "erc": {
                "id": str(erc_report.id),
                "schematic_id": str(erc_report.schematic_id),
                "schematic_revision": erc_report.schematic_revision,
                "status": erc_report.status,
                "issues": sorted(
                    (item.model_dump(mode="json") for item in erc_report.issues),
                    key=lambda item: item["code"],
                ),
            }
            if erc_report
            else None,
            "policy": policy.model_dump(mode="json"),
            "rule_results": sorted(
                (
                    {
                        "rule_id": item.rule_id,
                        "rule_version": item.rule_version,
                        "stage": item.stage,
                        "status": item.status,
                        "severity": item.severity.value,
                        "affected_refs": sorted(item.affected_refs),
                        "evidence_ids": sorted(str(value) for value in item.evidence_ids),
                    }
                    for item in (rule_results or [])
                ),
                key=lambda item: item["rule_id"],
            ),
        }
        input_hash = hashlib.sha256(
            json.dumps(input_payload, sort_keys=True, separators=(",", ":")).encode()
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
            status=aggregate_status(statuses),
            findings=tuple(findings),
        )


__all__ = ["CoverageResult", "ReviewEngine", "TestCoverageService"]
