"""SQLAlchemy persistence adapters for the durable M7 pin planner."""

from typing import Any, cast
from uuid import UUID

from eea_core.entities import utc_now
from eea_core.pin_planner import PinAssignment, PinLock, PinPlan, RuleResult
from sqlalchemy import desc, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from eea_backend.models import (
    PinAssignmentRecord,
    PinLockRecord,
    PinPlanRecord,
    PinRuleResultRecord,
)


def _entity_kwargs(record: object) -> dict[str, Any]:
    typed = cast(Any, record)
    return {
        "id": UUID(typed.id),
        "schema_version": typed.schema_version,
        "revision": typed.revision,
        "created_at": typed.created_at,
        "updated_at": typed.updated_at,
        "metadata": typed.entity_metadata,
    }


def _to_assignment(record: PinAssignmentRecord) -> PinAssignment:
    return PinAssignment.model_validate(
        {
            **_entity_kwargs(record),
            "project_id": UUID(record.project_id),
            "requirement_id": UUID(record.requirement_id),
            "device_ref": record.device_ref,
            "package": record.package,
            "pin_name": record.pin_name,
            "function": record.function,
            "locked": record.locked,
            "score": record.score,
            "claim_ids": record.claim_ids,
            "evidence_ids": record.evidence_ids,
        }
    )


def _to_lock(record: PinLockRecord) -> PinLock:
    return PinLock.model_validate(
        {
            **_entity_kwargs(record),
            "project_id": UUID(record.project_id),
            "assignment_id": UUID(record.assignment_id),
            "locked_by": record.locked_by,
            "reason": record.reason,
        }
    )


def _to_rule_result(record: PinRuleResultRecord) -> RuleResult:
    return RuleResult.model_validate(
        {
            **_entity_kwargs(record),
            "project_id": UUID(record.project_id),
            "rule_id": record.rule_id,
            "rule_version": record.rule_version,
            "stage": record.stage,
            "status": record.status,
            "severity": record.severity,
            "affected_refs": record.affected_refs,
            "measured": record.measured,
            "threshold": record.threshold,
            "evidence_ids": record.evidence_ids,
            "claim_ids": record.claim_ids,
            "recommendation": record.recommendation,
            "input_snapshot": record.input_snapshot,
        }
    )


class SqlAlchemyPinPlanRepository:
    """Project-scoped pin-plan persistence with assignment-level optimistic locking."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, plan: PinPlan, *, commit: bool = True) -> PinPlan:
        serialized = plan.model_dump(mode="json")
        record = PinPlanRecord(
            id=str(plan.id),
            schema_version=plan.schema_version,
            revision=plan.revision,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
            entity_metadata=plan.metadata,
            project_id=str(plan.project_id),
            analysis_id=str(plan.analysis_id) if plan.analysis_id else None,
            device_ref=plan.device_ref,
            package=plan.package,
            requirements=cast(list[dict[str, Any]], serialized["requirements"]),
            candidates=cast(list[dict[str, Any]], serialized["candidates"]),
        )
        self._session.add(record)
        self._session.flush()
        for assignment in plan.assignments:
            self._session.add(self._assignment_record(plan.id, assignment))
        self._session.flush()
        for lock in plan.locks:
            self._session.add(self._lock_record(lock))
        for result in plan.rule_results:
            self._session.add(self._rule_result_record(plan.id, result))
        if commit:
            self._session.commit()
            self._session.refresh(record)
        else:
            self._session.flush()
        return self.get(plan.id, project_id=plan.project_id) or plan

    def get(self, plan_id: UUID, *, project_id: UUID | None = None) -> PinPlan | None:
        statement = select(PinPlanRecord).where(PinPlanRecord.id == str(plan_id))
        if project_id is not None:
            statement = statement.where(PinPlanRecord.project_id == str(project_id))
        record = self._session.scalar(statement)
        return self._to_plan(record) if record else None

    def latest_for_project(self, project_id: UUID) -> PinPlan | None:
        statement = (
            select(PinPlanRecord)
            .where(PinPlanRecord.project_id == str(project_id))
            .order_by(desc(PinPlanRecord.created_at), desc(PinPlanRecord.id))
            .limit(1)
        )
        record = self._session.scalar(statement)
        return self._to_plan(record) if record else None

    def get_assignment(
        self, assignment_id: UUID, *, project_id: UUID
    ) -> tuple[PinAssignment, UUID] | None:
        statement = select(PinAssignmentRecord).where(
            PinAssignmentRecord.id == str(assignment_id),
            PinAssignmentRecord.project_id == str(project_id),
        )
        record = self._session.scalar(statement)
        return (_to_assignment(record), UUID(record.plan_id)) if record else None

    def save_assignment(
        self,
        assignment: PinAssignment,
        *,
        expected_revision: int,
        commit: bool = True,
    ) -> PinAssignment | None:
        statement = (
            update(PinAssignmentRecord)
            .where(
                PinAssignmentRecord.id == str(assignment.id),
                PinAssignmentRecord.project_id == str(assignment.project_id),
                PinAssignmentRecord.revision == expected_revision,
            )
            .values(
                schema_version=assignment.schema_version,
                revision=assignment.revision,
                updated_at=assignment.updated_at,
                entity_metadata=assignment.metadata,
                device_ref=assignment.device_ref,
                package=assignment.package,
                pin_name=assignment.pin_name,
                function=assignment.function.model_dump(mode="json"),
                locked=assignment.locked,
                score=assignment.score,
                claim_ids=[str(value) for value in assignment.claim_ids],
                evidence_ids=[str(value) for value in assignment.evidence_ids],
            )
        )
        result = cast(CursorResult[Any], self._session.execute(statement))
        if result.rowcount != 1:
            if commit:
                self._session.rollback()
            return None
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        current = self.get_assignment(assignment.id, project_id=assignment.project_id)
        return current[0] if current else None

    def add_lock(self, lock: PinLock, *, commit: bool = True) -> PinLock:
        record = self._lock_record(lock)
        self._session.add(record)
        if commit:
            self._session.commit()
            self._session.refresh(record)
        else:
            self._session.flush()
        return _to_lock(record)

    def has_active_lock(self, assignment_id: UUID, *, project_id: UUID) -> bool:
        statement = select(PinLockRecord.id).where(
            PinLockRecord.assignment_id == str(assignment_id),
            PinLockRecord.project_id == str(project_id),
            PinLockRecord.active.is_(True),
        )
        return self._session.scalar(statement) is not None

    def release_lock(
        self,
        assignment_id: UUID,
        *,
        project_id: UUID,
        released_by: str,
        reason: str,
        commit: bool = True,
    ) -> bool:
        statement = (
            update(PinLockRecord)
            .where(
                PinLockRecord.assignment_id == str(assignment_id),
                PinLockRecord.project_id == str(project_id),
                PinLockRecord.active.is_(True),
            )
            .values(
                active=False,
                released_by=released_by,
                released_reason=reason,
                released_at=utc_now(),
            )
        )
        result = cast(CursorResult[Any], self._session.execute(statement))
        if result.rowcount != 1:
            if commit:
                self._session.rollback()
            return False
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        return True

    def _to_plan(self, record: PinPlanRecord) -> PinPlan:
        return PinPlan.model_validate(
            {
                **_entity_kwargs(record),
                "project_id": UUID(record.project_id),
                "analysis_id": UUID(record.analysis_id) if record.analysis_id else None,
                "device_ref": record.device_ref,
                "package": record.package,
                "requirements": record.requirements,
                "candidates": record.candidates,
                "assignments": self._assignments(UUID(record.id)),
                "locks": self._locks(UUID(record.id)),
                "rule_results": self._rule_results(UUID(record.id)),
            }
        )

    def _assignments(self, plan_id: UUID) -> list[PinAssignment]:
        statement = (
            select(PinAssignmentRecord)
            .where(PinAssignmentRecord.plan_id == str(plan_id))
            .order_by(PinAssignmentRecord.created_at, PinAssignmentRecord.id)
        )
        return [_to_assignment(record) for record in self._session.scalars(statement)]

    def _locks(self, plan_id: UUID) -> list[PinLock]:
        statement = (
            select(PinLockRecord)
            .where(
                PinLockRecord.assignment_id.in_(
                    select(PinAssignmentRecord.id).where(
                        PinAssignmentRecord.plan_id == str(plan_id)
                    )
                ),
                PinLockRecord.active.is_(True),
            )
            .order_by(PinLockRecord.created_at, PinLockRecord.id)
        )
        return [_to_lock(record) for record in self._session.scalars(statement)]

    def _rule_results(self, plan_id: UUID) -> list[RuleResult]:
        statement = (
            select(PinRuleResultRecord)
            .where(PinRuleResultRecord.plan_id == str(plan_id))
            .order_by(PinRuleResultRecord.created_at, PinRuleResultRecord.id)
        )
        return [_to_rule_result(record) for record in self._session.scalars(statement)]

    @staticmethod
    def _assignment_record(plan_id: UUID, assignment: PinAssignment) -> PinAssignmentRecord:
        return PinAssignmentRecord(
            id=str(assignment.id),
            schema_version=assignment.schema_version,
            revision=assignment.revision,
            created_at=assignment.created_at,
            updated_at=assignment.updated_at,
            entity_metadata=assignment.metadata,
            project_id=str(assignment.project_id),
            plan_id=str(plan_id),
            requirement_id=str(assignment.requirement_id),
            device_ref=assignment.device_ref,
            package=assignment.package,
            pin_name=assignment.pin_name,
            function=assignment.function.model_dump(mode="json"),
            locked=assignment.locked,
            score=assignment.score,
            claim_ids=[str(value) for value in assignment.claim_ids],
            evidence_ids=[str(value) for value in assignment.evidence_ids],
        )

    @staticmethod
    def _lock_record(lock: PinLock) -> PinLockRecord:
        return PinLockRecord(
            id=str(lock.id),
            schema_version=lock.schema_version,
            revision=lock.revision,
            created_at=lock.created_at,
            updated_at=lock.updated_at,
            entity_metadata=lock.metadata,
            project_id=str(lock.project_id),
            assignment_id=str(lock.assignment_id),
            locked_by=lock.locked_by,
            reason=lock.reason,
            active=True,
        )

    @staticmethod
    def _rule_result_record(plan_id: UUID, result: RuleResult) -> PinRuleResultRecord:
        serialized = result.model_dump(mode="json")
        return PinRuleResultRecord(
            id=str(result.id),
            schema_version=result.schema_version,
            revision=result.revision,
            created_at=result.created_at,
            updated_at=result.updated_at,
            entity_metadata=result.metadata,
            project_id=str(result.project_id),
            plan_id=str(plan_id),
            rule_id=result.rule_id,
            rule_version=result.rule_version,
            stage=result.stage,
            status=result.status,
            severity=result.severity.value,
            affected_refs=result.affected_refs,
            measured=serialized["measured"],
            threshold=serialized["threshold"],
            evidence_ids=[str(value) for value in result.evidence_ids],
            claim_ids=[str(value) for value in result.claim_ids],
            recommendation=result.recommendation,
            input_snapshot=cast(dict[str, object], serialized["input_snapshot"]),
        )


__all__ = ["SqlAlchemyPinPlanRepository"]
