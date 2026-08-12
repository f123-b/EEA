"""Deterministic M17 TestIR generation and safe executor services."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from eea_core.requirements import Requirement
from eea_core.testing import (
    AutomationLevel,
    RequirementTestSnapshot,
    TestCase,
    TestCaseResult,
    TestExecutionStatus,
    TestIR,
    TestRun,
    TestType,
    acceptance_criteria_hash,
    deterministic_case_id,
)


class TestExecutor(Protocol):
    executor_id: str
    controlled: bool

    def execute(self, case: TestCase) -> TestCaseResult: ...


class TestExecutorRegistry:
    """Registry for structured, application-owned executors only."""

    def __init__(self, executors: tuple[TestExecutor, ...] = ()) -> None:
        self._executors: dict[str, TestExecutor] = {}
        self._project_executors: dict[UUID, dict[str, TestExecutor]] = {}
        for executor in executors:
            self.register(executor)

    def register(self, executor: TestExecutor) -> None:
        if not getattr(executor, "controlled", False):
            raise ValueError("only structured controlled executors may be registered")
        if not executor.executor_id or executor.executor_id in self._executors:
            raise ValueError("executor_id must be unique and non-empty")
        self._executors[executor.executor_id] = executor

    def register_for_project(self, project_id: UUID, executor: TestExecutor) -> None:
        if not getattr(executor, "controlled", False):
            raise ValueError("only structured controlled executors may be registered")
        project_registry = self._project_executors.setdefault(project_id, {})
        if not executor.executor_id or executor.executor_id in project_registry:
            raise ValueError("project executor_id must be unique and non-empty")
        project_registry[executor.executor_id] = executor

    def ensure_project(self, project_id: UUID) -> None:
        if project_id not in self._project_executors:
            self._project_executors[project_id] = {
                ControlledRequirementExecutor.executor_id: ControlledRequirementExecutor(project_id)
            }

    def execute(self, case: TestCase, *, project_id: UUID | None = None) -> TestCaseResult:
        if case.automation_level is AutomationLevel.MANUAL:
            return TestCaseResult(
                id=uuid4(),
                test_case_id=case.id,
                test_case_code=case.code,
                status=TestExecutionStatus.BLOCKED,
                message="Trusted manual evidence is required",
                executor_id=case.executor_id,
            )
        executors = self._project_executors.get(project_id, {}) if project_id else self._executors
        if case.executor_id is None or case.executor_id not in executors:
            return TestCaseResult(
                id=uuid4(),
                test_case_id=case.id,
                test_case_code=case.code,
                status=TestExecutionStatus.BLOCKED,
                message="Test executor is not registered",
                executor_id=case.executor_id,
            )
        result = executors[case.executor_id].execute(case)
        if result.test_case_id != case.id:
            raise ValueError("executor returned a result for a different test case")
        return result


class ControlledRequirementExecutor:
    """A deterministic, project-scoped contract executor with no code execution."""

    executor_id = "controlled.requirement.contract.v1"
    controlled = True

    def __init__(self, project_id: UUID) -> None:
        self.project_id = project_id

    def execute(self, case: TestCase) -> TestCaseResult:
        if (
            case.executor_config.get("fact") != "requirement.acceptance_criteria_present"
            or case.executor_config.get("expected") is not True
        ):
            return TestCaseResult(
                id=uuid4(),
                test_case_id=case.id,
                test_case_code=case.code,
                status=TestExecutionStatus.BLOCKED,
                message="Controlled executor requires its structured fact contract",
                executor_id=self.executor_id,
            )
        valid = bool(case.requirement_ids and case.expected and case.required)
        return TestCaseResult(
            id=uuid4(),
            test_case_id=case.id,
            test_case_code=case.code,
            status=TestExecutionStatus.PASS if valid else TestExecutionStatus.BLOCKED,
            message="Structured TestCase contract verified"
            if valid
            else "TestCase contract is incomplete",
            executor_id=self.executor_id,
        )


class TestGenerationResult:
    def __init__(self, test_ir: TestIR, coverage_gaps: tuple[UUID, ...]) -> None:
        self.test_ir = test_ir
        self.coverage_gaps = coverage_gaps


class TestGenerationService:
    """Generate declarative test skeletons without an LLM or fabricated result."""

    def generate(self, project_id: UUID, requirements: list[Requirement]) -> TestGenerationResult:
        cases: list[TestCase] = []
        gaps: list[UUID] = []
        requirement_ids = tuple(item.id for item in requirements)
        for requirement in sorted(requirements, key=lambda item: str(item.id)):
            if not requirement.acceptance_criteria:
                gaps.append(requirement.id)
                continue
            for index, criterion in enumerate(requirement.acceptance_criteria, start=1):
                case_id = deterministic_case_id(
                    project_id, requirement.id, requirement.revision, index
                )
                cases.append(
                    TestCase(
                        id=case_id,
                        code=f"REQ_{requirement.code}_{index}",
                        title=f"Verify {requirement.code} acceptance criterion {index}",
                        type=TestType.REQUIREMENT,
                        requirement_ids=(requirement.id,),
                        expected=(criterion,),
                        pass_condition=criterion,
                        automation_level=AutomationLevel.AUTOMATED,
                        executor_id=ControlledRequirementExecutor.executor_id,
                        executor_config={
                            "fact": "requirement.acceptance_criteria_present",
                            "expected": True,
                        },
                        required=True,
                    )
                )
        snapshots = tuple(
            RequirementTestSnapshot(
                requirement_id=requirement.id,
                revision=requirement.revision,
                priority=requirement.priority.value,
                status=requirement.status.value,
                acceptance_criteria_hash=acceptance_criteria_hash(requirement.acceptance_criteria),
            )
            for requirement in sorted(requirements, key=lambda item: str(item.id))
        )
        test_ir = TestIR.build(
            project_id=project_id,
            requirement_ids=requirement_ids,
            requirement_revisions={item.id: item.revision for item in requirements},
            requirement_snapshots=snapshots,
            cases=tuple(cases),
        )
        return TestGenerationResult(test_ir, tuple(gaps))


class TestRunService:
    def __init__(self, registry: TestExecutorRegistry) -> None:
        self.registry = registry

    def run(
        self,
        *,
        project_id: UUID,
        test_ir: TestIR,
        source_revision_id: UUID,
        tool_versions: dict[str, str] | None = None,
    ) -> TestRun:
        started = datetime.now(UTC)
        results = tuple(
            self.registry.execute(case, project_id=project_id) for case in test_ir.cases
        )
        finished = datetime.now(UTC)
        return TestRun(
            project_id=project_id,
            test_ir_id=test_ir.id,
            test_ir_revision=test_ir.revision,
            test_input_hash=test_ir.input_hash,
            source_revision_id=source_revision_id,
            status=TestRun.aggregate_status(results),
            started_at=started,
            finished_at=finished,
            case_results=results,
            tool_versions=tool_versions or {},
        )


__all__ = [
    "ControlledRequirementExecutor",
    "TestExecutor",
    "TestExecutorRegistry",
    "TestGenerationResult",
    "TestGenerationService",
    "TestRunService",
]
