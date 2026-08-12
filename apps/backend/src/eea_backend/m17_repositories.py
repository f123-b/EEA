"""Project-scoped M17 persistence adapters."""

from __future__ import annotations

from time import sleep
from typing import Any, cast
from uuid import UUID, uuid5

from eea_core.entities import Issue, TraceabilityEdge, utc_now
from eea_core.enums import IssueStatus
from eea_core.review import ReviewFinding, ReviewRun
from eea_core.testing import TestIR, TestRun
from sqlalchemy import case, desc, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from eea_backend.models import (
    IssueRecord,
    ReviewRunRecord,
    TestIRRecord,
    TestRunRecord,
    TraceabilityEdgeRecord,
)


def _entity_kwargs(record: object) -> dict[str, Any]:
    value = cast(Any, record)
    return {
        "id": UUID(value.id),
        "schema_version": value.schema_version,
        "revision": value.revision,
        "created_at": value.created_at,
        "updated_at": value.updated_at,
        "metadata": value.entity_metadata,
    }


class SqlAlchemyTestRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_test_ir(self, test_ir: TestIR, *, commit: bool = True) -> TestIR:
        existing = self.get_test_ir_by_hash(test_ir.project_id, test_ir.input_hash)
        if existing is not None:
            return existing
        serialized = test_ir.model_dump(mode="json")
        self.session.add(
            TestIRRecord(
                id=str(test_ir.id),
                schema_version=test_ir.schema_version,
                revision=test_ir.revision,
                created_at=test_ir.created_at,
                updated_at=test_ir.updated_at,
                entity_metadata=test_ir.metadata,
                project_id=str(test_ir.project_id),
                requirement_ids=[str(item) for item in test_ir.requirement_ids],
                requirement_revisions={
                    str(key): value for key, value in test_ir.requirement_revisions.items()
                },
                requirement_snapshots=cast(
                    list[dict[str, Any]], serialized["requirement_snapshots"]
                ),
                cases=cast(list[dict[str, Any]], serialized["cases"]),
                input_hash=test_ir.input_hash,
                generator_version=test_ir.generator_version,
                policy_version=test_ir.policy_version,
                evidence_ids=[str(item) for item in test_ir.evidence_ids],
            )
        )
        if commit:
            try:
                self.session.commit()
            except IntegrityError:
                self.session.rollback()
                existing = self.get_test_ir_by_hash(test_ir.project_id, test_ir.input_hash)
                if existing is None:
                    raise
                return existing
        else:
            self.session.flush()
        return self.get_test_ir(test_ir.id, project_id=test_ir.project_id) or test_ir

    def get_test_ir(self, test_ir_id: UUID, *, project_id: UUID) -> TestIR | None:
        record = self.session.scalar(
            select(TestIRRecord).where(
                TestIRRecord.id == str(test_ir_id), TestIRRecord.project_id == str(project_id)
            )
        )
        return self._to_test_ir(record) if record else None

    def get_test_ir_by_hash(self, project_id: UUID, input_hash: str) -> TestIR | None:
        record = self.session.scalar(
            select(TestIRRecord).where(
                TestIRRecord.project_id == str(project_id), TestIRRecord.input_hash == input_hash
            )
        )
        return self._to_test_ir(record) if record else None

    def list_test_irs(self, project_id: UUID) -> list[TestIR]:
        records = self.session.scalars(
            select(TestIRRecord)
            .where(TestIRRecord.project_id == str(project_id))
            .order_by(desc(TestIRRecord.created_at), desc(TestIRRecord.id))
        )
        converted = [self._to_test_ir(item) for item in records]
        return [item for item in converted if item is not None]

    def add_test_run(self, test_run: TestRun, *, commit: bool = True) -> TestRun:
        serialized = test_run.model_dump(mode="json")
        self.session.add(
            TestRunRecord(
                id=str(test_run.id),
                schema_version=test_run.schema_version,
                revision=test_run.revision,
                created_at=test_run.created_at,
                updated_at=test_run.updated_at,
                entity_metadata=test_run.metadata,
                project_id=str(test_run.project_id),
                test_ir_id=str(test_run.test_ir_id),
                test_ir_revision=test_run.test_ir_revision,
                test_input_hash=test_run.test_input_hash,
                source_revision_id=str(test_run.source_revision_id),
                status=test_run.status.value,
                started_at=test_run.started_at,
                finished_at=test_run.finished_at,
                case_results=cast(list[dict[str, Any]], serialized["case_results"]),
                tool_versions=test_run.tool_versions,
                evidence_ids=[str(item) for item in test_run.evidence_ids],
            )
        )
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return self.get_test_run(test_run.id, project_id=test_run.project_id) or test_run

    def get_test_run(self, run_id: UUID, *, project_id: UUID) -> TestRun | None:
        record = self.session.scalar(
            select(TestRunRecord).where(
                TestRunRecord.id == str(run_id), TestRunRecord.project_id == str(project_id)
            )
        )
        return self._to_test_run(record) if record else None

    def latest_test_run(
        self,
        project_id: UUID,
        *,
        test_ir_id: UUID | None = None,
        source_revision_id: UUID | None = None,
    ) -> TestRun | None:
        statement = select(TestRunRecord).where(TestRunRecord.project_id == str(project_id))
        if test_ir_id is not None:
            statement = statement.where(TestRunRecord.test_ir_id == str(test_ir_id))
        if source_revision_id is not None:
            statement = statement.where(TestRunRecord.source_revision_id == str(source_revision_id))
        record = self.session.scalar(statement.order_by(desc(TestRunRecord.created_at)).limit(1))
        return self._to_test_run(record) if record else None

    def list_test_runs(self, project_id: UUID) -> list[TestRun]:
        records = self.session.scalars(
            select(TestRunRecord)
            .where(TestRunRecord.project_id == str(project_id))
            .order_by(desc(TestRunRecord.created_at), desc(TestRunRecord.id))
        )
        converted = [self._to_test_run(item) for item in records]
        return [item for item in converted if item is not None]

    @staticmethod
    def _to_test_ir(record: TestIRRecord | None) -> TestIR | None:
        if record is None:
            return None
        return TestIR.model_validate(
            {
                **_entity_kwargs(record),
                "project_id": UUID(record.project_id),
                "requirement_ids": record.requirement_ids,
                "requirement_revisions": {
                    UUID(key): value for key, value in record.requirement_revisions.items()
                },
                "requirement_snapshots": record.requirement_snapshots,
                "cases": record.cases,
                "input_hash": record.input_hash,
                "generator_version": record.generator_version,
                "policy_version": record.policy_version,
                "evidence_ids": record.evidence_ids,
            }
        )

    @staticmethod
    def _to_test_run(record: TestRunRecord | None) -> TestRun | None:
        if record is None:
            return None
        return TestRun.model_validate(
            {
                **_entity_kwargs(record),
                "project_id": UUID(record.project_id),
                "test_ir_id": UUID(record.test_ir_id),
                "test_ir_revision": record.test_ir_revision,
                "test_input_hash": record.test_input_hash,
                "source_revision_id": UUID(record.source_revision_id),
                "status": record.status,
                "started_at": record.started_at,
                "finished_at": record.finished_at,
                "case_results": record.case_results,
                "tool_versions": record.tool_versions,
                "evidence_ids": record.evidence_ids,
            }
        )


class SqlAlchemyTraceabilityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, edge: TraceabilityEdge, *, commit: bool = True) -> TraceabilityEdge:
        for attempt in range(3):
            try:
                return self._add_once(edge, commit=commit)
            except OperationalError as exc:
                self.session.rollback()
                if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                    raise
                if attempt == 2:
                    raise RuntimeError(
                        "traceability edge upsert remained database-busy after controlled retries"
                    ) from exc
                sleep(0.02 * (attempt + 1))
        raise AssertionError("unreachable")

    def _add_once(self, edge: TraceabilityEdge, *, commit: bool) -> TraceabilityEdge:
        identity = (
            TraceabilityEdgeRecord.project_id == str(edge.project_id),
            TraceabilityEdgeRecord.source_type == edge.source_type,
            TraceabilityEdgeRecord.source_id == str(edge.source_id),
            TraceabilityEdgeRecord.target_type == edge.target_type,
            TraceabilityEdgeRecord.target_id == str(edge.target_id),
            TraceabilityEdgeRecord.relation == edge.relation.value,
        )
        existing = self.session.scalar(select(TraceabilityEdgeRecord).where(*identity))
        if existing is not None:
            existing.evidence_ids = sorted(
                set(existing.evidence_ids) | {str(item) for item in edge.evidence_ids}
            )
            if commit:
                self.session.commit()
            return self._to_edge(existing)
        candidate = TraceabilityEdgeRecord(
            id=str(edge.id),
            schema_version=edge.schema_version,
            revision=edge.revision,
            created_at=edge.created_at,
            updated_at=edge.updated_at,
            entity_metadata=edge.metadata,
            project_id=str(edge.project_id),
            source_type=edge.source_type,
            source_id=str(edge.source_id),
            target_type=edge.target_type,
            target_id=str(edge.target_id),
            relation=edge.relation.value,
            evidence_ids=[str(item) for item in edge.evidence_ids],
        )
        try:
            with self.session.begin_nested():
                self.session.add(candidate)
                self.session.flush()
        except IntegrityError:
            existing = self.session.scalar(select(TraceabilityEdgeRecord).where(*identity))
            if existing is None:
                raise
            existing.evidence_ids = sorted(
                set(existing.evidence_ids) | {str(item) for item in edge.evidence_ids}
            )
        if commit:
            self.session.commit()
        return self._to_edge(existing or candidate)

    def list_for_project(self, project_id: UUID) -> list[TraceabilityEdge]:
        records = self.session.scalars(
            select(TraceabilityEdgeRecord)
            .where(TraceabilityEdgeRecord.project_id == str(project_id))
            .order_by(TraceabilityEdgeRecord.source_type, TraceabilityEdgeRecord.source_id)
        )
        return [self._to_edge(item) for item in records]

    @staticmethod
    def _to_edge(record: TraceabilityEdgeRecord) -> TraceabilityEdge:
        return TraceabilityEdge.model_validate(
            {
                **_entity_kwargs(record),
                "project_id": UUID(record.project_id),
                "source_type": record.source_type,
                "source_id": UUID(record.source_id),
                "target_type": record.target_type,
                "target_id": UUID(record.target_id),
                "relation": record.relation,
                "evidence_ids": record.evidence_ids,
            }
        )


class SqlAlchemyReviewRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, review: ReviewRun, *, commit: bool = True) -> ReviewRun:
        serialized = review.model_dump(mode="json")
        self.session.add(
            ReviewRunRecord(
                id=str(review.id),
                schema_version=review.schema_version,
                revision=review.revision,
                created_at=review.created_at,
                updated_at=review.updated_at,
                entity_metadata=review.metadata,
                project_id=str(review.project_id),
                source_revision_id=str(review.source_revision_id),
                policy_version=review.policy_version,
                input_hash=review.input_hash,
                build_run_id=str(review.build_run_id) if review.build_run_id else None,
                static_analysis_id=str(review.static_analysis_id)
                if review.static_analysis_id
                else None,
                test_run_id=str(review.test_run_id) if review.test_run_id else None,
                test_ir_id=str(review.test_ir_id) if review.test_ir_id else None,
                test_ir_revision=review.test_ir_revision,
                protocol_id=str(review.protocol_id) if review.protocol_id else None,
                protocol_revision=review.protocol_revision,
                status=review.status.value,
                findings=cast(list[dict[str, Any]], serialized["findings"]),
                issue_ids=[str(item) for item in review.issue_ids],
            )
        )
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return self.get(review.id, project_id=review.project_id) or review

    def get(self, review_id: UUID, *, project_id: UUID) -> ReviewRun | None:
        record = self.session.scalar(
            select(ReviewRunRecord).where(
                ReviewRunRecord.id == str(review_id), ReviewRunRecord.project_id == str(project_id)
            )
        )
        return self._to_review(record) if record else None

    def list_for_project(self, project_id: UUID) -> list[ReviewRun]:
        records = self.session.scalars(
            select(ReviewRunRecord)
            .where(ReviewRunRecord.project_id == str(project_id))
            .order_by(desc(ReviewRunRecord.created_at), desc(ReviewRunRecord.id))
        )
        converted = [self._to_review(item) for item in records]
        return [item for item in converted if item is not None]

    @staticmethod
    def _to_review(record: ReviewRunRecord | None) -> ReviewRun | None:
        if record is None:
            return None
        return ReviewRun.model_validate(
            {
                **_entity_kwargs(record),
                "project_id": UUID(record.project_id),
                "source_revision_id": UUID(record.source_revision_id),
                "policy_version": record.policy_version,
                "input_hash": record.input_hash,
                "build_run_id": record.build_run_id,
                "static_analysis_id": record.static_analysis_id,
                "test_run_id": record.test_run_id,
                "test_ir_id": record.test_ir_id,
                "test_ir_revision": record.test_ir_revision,
                "protocol_id": record.protocol_id,
                "protocol_revision": record.protocol_revision,
                "status": record.status,
                "findings": record.findings,
                "issue_ids": record.issue_ids,
            }
        )


class SqlAlchemyIssueRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_or_update(
        self, project_id: UUID, finding: ReviewFinding, *, review_id: UUID, commit: bool = False
    ) -> Issue:
        for attempt in range(3):
            try:
                return self._add_or_update_once(
                    project_id, finding, review_id=review_id, commit=commit
                )
            except OperationalError as exc:
                self.session.rollback()
                if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                    raise
                if attempt == 2:
                    raise RuntimeError(
                        "issue upsert remained database-busy after controlled retries"
                    ) from exc
                sleep(0.02 * (attempt + 1))
        raise AssertionError("unreachable")

    def _add_or_update_once(
        self, project_id: UUID, finding: ReviewFinding, *, review_id: UUID, commit: bool
    ) -> Issue:
        now = utc_now()
        identity = (
            IssueRecord.project_id == str(project_id),
            IssueRecord.dedupe_key == finding.dedupe_key,
        )
        existing = self.session.scalar(select(IssueRecord).where(*identity))
        if existing is None:
            issue_id = uuid5(project_id, f"m17-issue:{finding.dedupe_key}")
            candidate = IssueRecord(
                id=str(issue_id),
                schema_version="1.0",
                revision=1,
                created_at=now,
                updated_at=now,
                entity_metadata={},
                project_id=str(project_id),
                code=finding.code,
                title=finding.title,
                description=finding.message,
                severity=finding.severity.value,
                status=IssueStatus.OPEN.value,
                claim_ids=[],
                evidence_ids=[str(item) for item in finding.evidence_ids],
                resolution=None,
                dedupe_key=finding.dedupe_key,
                source_kind=finding.source_kind,
                source_ref=finding.source_ref,
                affected_refs=list(finding.affected_refs),
                first_seen_at=now,
                last_seen_at=now,
                occurrence_count=1,
                last_review_id=str(review_id),
            )
            try:
                with self.session.begin_nested():
                    self.session.add(candidate)
                    self.session.flush()
                record = candidate
            except IntegrityError:
                existing = self.session.scalar(select(IssueRecord).where(*identity))
                if existing is None:
                    raise
        if existing is not None:
            self.session.execute(
                update(IssueRecord)
                .where(*identity)
                .values(
                    revision=IssueRecord.revision + 1,
                    updated_at=now,
                    last_seen_at=now,
                    last_review_id=str(review_id),
                    occurrence_count=IssueRecord.occurrence_count + 1,
                    status=case(
                        (IssueRecord.status == IssueStatus.RESOLVED.value, IssueStatus.OPEN.value),
                        else_=IssueRecord.status,
                    ),
                    resolution=case(
                        (IssueRecord.status == IssueStatus.RESOLVED.value, None),
                        else_=IssueRecord.resolution,
                    ),
                )
            )
            existing = self.session.scalar(select(IssueRecord).where(*identity))
            if existing is None:
                raise RuntimeError("issue disappeared during atomic update")
            expected_revision = existing.revision
            merged_evidence = sorted(
                set(existing.evidence_ids) | {str(item) for item in finding.evidence_ids}
            )
            merged_refs = sorted(set(existing.affected_refs) | set(finding.affected_refs))
            evidence_result = cast(
                CursorResult[Any],
                self.session.execute(
                    update(IssueRecord)
                    .where(*identity, IssueRecord.revision == expected_revision)
                    .values(evidence_ids=merged_evidence, affected_refs=merged_refs)
                ),
            )
            if evidence_result.rowcount != 1:
                self.session.refresh(existing)
                self.session.execute(
                    update(IssueRecord)
                    .where(*identity, IssueRecord.revision == existing.revision)
                    .values(
                        evidence_ids=sorted(
                            set(existing.evidence_ids)
                            | {str(item) for item in finding.evidence_ids}
                        ),
                        affected_refs=sorted(
                            set(existing.affected_refs) | set(finding.affected_refs)
                        ),
                    )
                )
            existing = self.session.scalar(select(IssueRecord).where(*identity))
            if existing is None:
                raise RuntimeError("issue disappeared during evidence merge")
            record = existing
        if commit:
            self.session.commit()
        return self._to_issue(record)

    def get(self, issue_id: UUID, *, project_id: UUID) -> Issue | None:
        record = self.session.scalar(
            select(IssueRecord).where(
                IssueRecord.id == str(issue_id), IssueRecord.project_id == str(project_id)
            )
        )
        return self._to_issue(record) if record else None

    def list_for_project(self, project_id: UUID) -> list[Issue]:
        records = self.session.scalars(
            select(IssueRecord)
            .where(IssueRecord.project_id == str(project_id))
            .order_by(IssueRecord.created_at)
        )
        return [self._to_issue(item) for item in records]

    def update_status(
        self, issue: Issue, *, status: IssueStatus, reason: str, expected_revision: int
    ) -> Issue | None:
        result = cast(
            CursorResult[Any],
            self.session.execute(
                update(IssueRecord)
                .where(
                    IssueRecord.id == str(issue.id),
                    IssueRecord.project_id == str(issue.project_id),
                    IssueRecord.revision == expected_revision,
                )
                .values(
                    status=status.value,
                    resolution=reason,
                    revision=expected_revision + 1,
                    updated_at=utc_now(),
                )
            ),
        )
        if result.rowcount != 1:
            self.session.rollback()
            return None
        self.session.commit()
        return self.get(issue.id, project_id=issue.project_id)

    @staticmethod
    def _to_issue(record: IssueRecord) -> Issue:
        return Issue.model_validate(
            {
                **_entity_kwargs(record),
                "project_id": UUID(record.project_id),
                "code": record.code,
                "title": record.title,
                "description": record.description,
                "severity": record.severity,
                "status": record.status,
                "claim_ids": record.claim_ids,
                "evidence_ids": record.evidence_ids,
                "resolution": record.resolution,
                "dedupe_key": record.dedupe_key,
                "source_kind": record.source_kind,
                "source_ref": record.source_ref,
                "affected_refs": record.affected_refs or [],
                "first_seen_at": record.first_seen_at,
                "last_seen_at": record.last_seen_at,
                "occurrence_count": record.occurrence_count,
                "last_review_id": record.last_review_id,
            }
        )


__all__ = [
    "SqlAlchemyIssueRepository",
    "SqlAlchemyReviewRepository",
    "SqlAlchemyTestRepository",
    "SqlAlchemyTraceabilityRepository",
]
