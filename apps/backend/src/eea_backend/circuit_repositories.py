"""SQLAlchemy persistence adapters for M9 CircuitIR."""

from typing import Any, cast
from uuid import UUID

from eea_core.circuit import CircuitBundle, CircuitIR
from eea_core.pin_planner import RuleResult
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from eea_backend.models import CircuitRecord, CircuitRuleResultRecord


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


def _to_rule_result(record: CircuitRuleResultRecord) -> RuleResult:
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


class SqlAlchemyCircuitRepository:
    """Persist CircuitIR and its deterministic rule results as one snapshot."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, bundle: CircuitBundle, *, commit: bool = True) -> CircuitBundle:
        circuit = bundle.circuit
        serialized = circuit.model_dump(mode="json")
        record = CircuitRecord(
            id=str(circuit.id),
            schema_version=circuit.schema_version,
            revision=circuit.revision,
            created_at=circuit.created_at,
            updated_at=circuit.updated_at,
            entity_metadata=circuit.metadata,
            project_id=str(circuit.project_id),
            hardware_ir_id=str(circuit.hardware_ir_id),
            hardware_ir_revision=circuit.hardware_ir_revision,
            components=cast(list[dict[str, Any]], serialized["components"]),
            nets=cast(list[dict[str, Any]], serialized["nets"]),
            power_nets=cast(list[dict[str, Any]], serialized["power_nets"]),
            constraints=cast(list[dict[str, Any]], serialized["constraints"]),
            requirement_ids=[str(value) for value in circuit.requirement_ids],
            evidence_ids=[str(value) for value in circuit.evidence_ids],
            pin_assignment_revisions=circuit.pin_assignment_revisions,
        )
        self._session.add(record)
        self._session.flush()
        for result in bundle.rule_results:
            self._session.add(self._rule_record(circuit.id, result))
        if commit:
            self._session.commit()
            self._session.refresh(record)
        else:
            self._session.flush()
        return self.get(circuit.id, project_id=circuit.project_id) or bundle

    def get(self, circuit_id: UUID, *, project_id: UUID | None = None) -> CircuitBundle | None:
        statement = select(CircuitRecord).where(CircuitRecord.id == str(circuit_id))
        if project_id is not None:
            statement = statement.where(CircuitRecord.project_id == str(project_id))
        record = self._session.scalar(statement)
        return self._to_bundle(record) if record else None

    def latest_for_project(self, project_id: UUID) -> CircuitBundle | None:
        statement = (
            select(CircuitRecord)
            .where(CircuitRecord.project_id == str(project_id))
            .order_by(desc(CircuitRecord.created_at), desc(CircuitRecord.id))
            .limit(1)
        )
        record = self._session.scalar(statement)
        return self._to_bundle(record) if record else None

    def _to_bundle(self, record: CircuitRecord) -> CircuitBundle:
        rules = self._rules(UUID(record.id))
        circuit = CircuitIR.model_validate(
            {
                **_entity_kwargs(record),
                "project_id": UUID(record.project_id),
                "hardware_ir_id": UUID(record.hardware_ir_id),
                "hardware_ir_revision": record.hardware_ir_revision,
                "components": record.components,
                "nets": record.nets,
                "power_nets": record.power_nets,
                "constraints": record.constraints,
                "rule_results": rules,
                "requirement_ids": record.requirement_ids,
                "evidence_ids": record.evidence_ids,
                "pin_assignment_revisions": record.pin_assignment_revisions,
            }
        )
        return CircuitBundle(circuit=circuit, rule_results=rules)

    def _rules(self, circuit_id: UUID) -> list[RuleResult]:
        statement = (
            select(CircuitRuleResultRecord)
            .where(CircuitRuleResultRecord.circuit_id == str(circuit_id))
            .order_by(CircuitRuleResultRecord.created_at, CircuitRuleResultRecord.id)
        )
        return [_to_rule_result(record) for record in self._session.scalars(statement)]

    @staticmethod
    def _rule_record(circuit_id: UUID, result: RuleResult) -> CircuitRuleResultRecord:
        serialized = result.model_dump(mode="json")
        return CircuitRuleResultRecord(
            id=str(result.id),
            schema_version=result.schema_version,
            revision=result.revision,
            created_at=result.created_at,
            updated_at=result.updated_at,
            entity_metadata=result.metadata,
            project_id=str(result.project_id),
            circuit_id=str(circuit_id),
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


__all__ = ["SqlAlchemyCircuitRepository"]
