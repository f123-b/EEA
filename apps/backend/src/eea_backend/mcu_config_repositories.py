"""SQLAlchemy persistence adapters for M11 MCUConfigIR snapshots."""

from typing import Any, cast
from uuid import UUID

from eea_core.mcu_config import MCUConfigBundle, MCUConfigIR
from eea_core.pin_planner import RuleResult
from sqlalchemy import desc, select, update
from sqlalchemy.orm import Session

from eea_backend.models import MCUConfigRecord, MCUConfigRuleResultRecord


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


def _to_rule_result(record: MCUConfigRuleResultRecord) -> RuleResult:
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


class SqlAlchemyMCUConfigRepository:
    """Persist one current MCU configuration and its auditable rule results."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, bundle: MCUConfigBundle, *, commit: bool = True) -> MCUConfigBundle:
        config = bundle.config
        self._mark_current_stale(config.project_id)
        serialized = config.model_dump(mode="json")
        record = MCUConfigRecord(
            id=str(config.id),
            schema_version=config.schema_version,
            revision=config.revision,
            created_at=config.created_at,
            updated_at=config.updated_at,
            entity_metadata=config.metadata,
            project_id=str(config.project_id),
            hardware_ir_id=str(config.hardware_ir_id),
            hardware_ir_revision=config.hardware_ir_revision,
            circuit_id=str(config.circuit_id),
            circuit_revision=config.circuit_revision,
            schematic_id=str(config.schematic_id),
            schematic_revision=config.schematic_revision,
            device_instance_id=str(config.device_instance_id),
            clock=cast(dict[str, Any], serialized["clock"]),
            gpio=cast(list[dict[str, Any]], serialized["gpio"]),
            peripherals=cast(list[dict[str, Any]], serialized["peripherals"]),
            dma=cast(list[dict[str, Any]], serialized["dma"]),
            interrupts=cast(list[dict[str, Any]], serialized["interrupts"]),
            memory=cast(dict[str, Any] | None, serialized["memory"]),
            debug=cast(dict[str, Any] | None, serialized["debug"]),
            capability_snapshot=cast(dict[str, Any], serialized["capability_snapshot"]),
            requirement_ids=[str(value) for value in config.requirement_ids],
            evidence_ids=[str(value) for value in config.evidence_ids],
            pin_assignment_revisions=config.pin_assignment_revisions,
            status=config.status.value,
        )
        self._session.add(record)
        self._session.flush()
        for result in bundle.rule_results:
            self._session.add(self._rule_record(config.id, result))
        if commit:
            self._session.commit()
            self._session.refresh(record)
        else:
            self._session.flush()
        return self.get(config.id, project_id=config.project_id) or bundle

    def get(self, config_id: UUID, *, project_id: UUID | None = None) -> MCUConfigBundle | None:
        statement = select(MCUConfigRecord).where(MCUConfigRecord.id == str(config_id))
        if project_id is not None:
            statement = statement.where(MCUConfigRecord.project_id == str(project_id))
        record = self._session.scalar(statement)
        return self._to_bundle(record) if record else None

    def latest_for_project(self, project_id: UUID) -> MCUConfigBundle | None:
        statement = (
            select(MCUConfigRecord)
            .where(
                MCUConfigRecord.project_id == str(project_id),
                MCUConfigRecord.status == "CURRENT",
            )
            .order_by(desc(MCUConfigRecord.created_at), desc(MCUConfigRecord.id))
            .limit(1)
        )
        record = self._session.scalar(statement)
        return self._to_bundle(record) if record else None

    def _to_bundle(self, record: MCUConfigRecord) -> MCUConfigBundle:
        results = self._rules(UUID(record.id))
        config = MCUConfigIR.model_validate(
            {
                **_entity_kwargs(record),
                "project_id": UUID(record.project_id),
                "hardware_ir_id": UUID(record.hardware_ir_id),
                "hardware_ir_revision": record.hardware_ir_revision,
                "circuit_id": UUID(record.circuit_id),
                "circuit_revision": record.circuit_revision,
                "schematic_id": UUID(record.schematic_id),
                "schematic_revision": record.schematic_revision,
                "device_instance_id": UUID(record.device_instance_id),
                "clock": record.clock,
                "gpio": record.gpio,
                "peripherals": record.peripherals,
                "dma": record.dma,
                "interrupts": record.interrupts,
                "memory": record.memory,
                "debug": record.debug,
                "capability_snapshot": record.capability_snapshot,
                "rule_results": results,
                "requirement_ids": record.requirement_ids,
                "evidence_ids": record.evidence_ids,
                "pin_assignment_revisions": record.pin_assignment_revisions,
                "status": record.status,
            }
        )
        return MCUConfigBundle(config=config, rule_results=results)

    def _rules(self, config_id: UUID) -> list[RuleResult]:
        statement = (
            select(MCUConfigRuleResultRecord)
            .where(MCUConfigRuleResultRecord.mcu_config_id == str(config_id))
            .order_by(MCUConfigRuleResultRecord.created_at, MCUConfigRuleResultRecord.id)
        )
        return [_to_rule_result(record) for record in self._session.scalars(statement)]

    @staticmethod
    def _rule_record(config_id: UUID, result: RuleResult) -> MCUConfigRuleResultRecord:
        serialized = result.model_dump(mode="json")
        return MCUConfigRuleResultRecord(
            id=str(result.id),
            schema_version=result.schema_version,
            revision=result.revision,
            created_at=result.created_at,
            updated_at=result.updated_at,
            entity_metadata=result.metadata,
            project_id=str(result.project_id),
            mcu_config_id=str(config_id),
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

    def _mark_current_stale(self, project_id: UUID) -> None:
        self._session.execute(
            update(MCUConfigRecord)
            .where(
                MCUConfigRecord.project_id == str(project_id),
                MCUConfigRecord.status == "CURRENT",
            )
            .values(status="STALE")
        )


__all__ = ["SqlAlchemyMCUConfigRepository"]
