"""SQLAlchemy persistence adapters for M13 firmware static analysis."""

from typing import Any, cast
from uuid import UUID

from eea_core.pin_planner import RuleResult
from eea_core.static_analysis import FirmwareStaticAnalysis, StaticAnalysisToolResult
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from eea_backend.models import (
    FirmwareStaticAnalysisRecord,
    FirmwareStaticAnalysisResultRecord,
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


def _to_rule(record: FirmwareStaticAnalysisResultRecord) -> RuleResult:
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


class SqlAlchemyFirmwareStaticAnalysisRepository:
    """Persist immutable, repeatable analysis results and normalized rule rows."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self, analysis: FirmwareStaticAnalysis, *, commit: bool = True
    ) -> FirmwareStaticAnalysis:
        existing = self.get(analysis.id, project_id=analysis.project_id)
        if existing is not None:
            return existing
        serialized = analysis.model_dump(mode="json")
        self._session.add(
            FirmwareStaticAnalysisRecord(
                id=str(analysis.id),
                schema_version=analysis.schema_version,
                revision=analysis.revision,
                created_at=analysis.created_at,
                updated_at=analysis.updated_at,
                entity_metadata=analysis.metadata,
                project_id=str(analysis.project_id),
                firmware_id=str(analysis.firmware_id),
                firmware_revision=analysis.firmware_revision,
                source_revision_id=str(analysis.source_revision_id),
                build_input_snapshot_id=(
                    str(analysis.build_input_snapshot_id)
                    if analysis.build_input_snapshot_id
                    else None
                ),
                input_hash=analysis.input_hash,
                ruleset_version=analysis.ruleset_version,
                status=analysis.status.value,
                tool_results=cast(list[dict[str, Any]], serialized["tool_results"]),
            )
        )
        for result in analysis.rule_results:
            result_data = result.model_dump(mode="json")
            self._session.add(
                FirmwareStaticAnalysisResultRecord(
                    id=str(result.id),
                    schema_version=result.schema_version,
                    revision=result.revision,
                    created_at=result.created_at,
                    updated_at=result.updated_at,
                    entity_metadata=result.metadata,
                    project_id=str(result.project_id),
                    analysis_id=str(analysis.id),
                    rule_id=result.rule_id,
                    rule_version=result.rule_version,
                    stage=result.stage,
                    status=result.status,
                    severity=result.severity.value,
                    affected_refs=result.affected_refs,
                    measured=result_data["measured"],
                    threshold=result_data["threshold"],
                    evidence_ids=[str(value) for value in result.evidence_ids],
                    claim_ids=[str(value) for value in result.claim_ids],
                    recommendation=result.recommendation,
                    input_snapshot=cast(dict[str, object], result_data["input_snapshot"]),
                )
            )
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        return self.get(analysis.id, project_id=analysis.project_id) or analysis

    def get(
        self, analysis_id: UUID, *, project_id: UUID | None = None
    ) -> FirmwareStaticAnalysis | None:
        statement = select(FirmwareStaticAnalysisRecord).where(
            FirmwareStaticAnalysisRecord.id == str(analysis_id)
        )
        if project_id is not None:
            statement = statement.where(FirmwareStaticAnalysisRecord.project_id == str(project_id))
        record = self._session.scalar(statement)
        return self._to_analysis(record) if record else None

    def list_for_project(self, project_id: UUID) -> list[FirmwareStaticAnalysis]:
        statement = (
            select(FirmwareStaticAnalysisRecord)
            .where(FirmwareStaticAnalysisRecord.project_id == str(project_id))
            .order_by(
                desc(FirmwareStaticAnalysisRecord.created_at),
                desc(FirmwareStaticAnalysisRecord.id),
            )
        )
        return [self._to_analysis(record) for record in self._session.scalars(statement)]

    def list_for_firmware(
        self, firmware_id: UUID, *, project_id: UUID | None = None
    ) -> list[FirmwareStaticAnalysis]:
        statement = select(FirmwareStaticAnalysisRecord).where(
            FirmwareStaticAnalysisRecord.firmware_id == str(firmware_id)
        )
        if project_id is not None:
            statement = statement.where(FirmwareStaticAnalysisRecord.project_id == str(project_id))
        statement = statement.order_by(
            desc(FirmwareStaticAnalysisRecord.created_at),
            desc(FirmwareStaticAnalysisRecord.id),
        )
        return [self._to_analysis(record) for record in self._session.scalars(statement)]

    def _to_analysis(self, record: FirmwareStaticAnalysisRecord) -> FirmwareStaticAnalysis:
        rules = self._session.scalars(
            select(FirmwareStaticAnalysisResultRecord)
            .where(FirmwareStaticAnalysisResultRecord.analysis_id == record.id)
            .order_by(FirmwareStaticAnalysisResultRecord.rule_id)
        )
        return FirmwareStaticAnalysis.model_validate(
            {
                **_entity_kwargs(record),
                "project_id": UUID(record.project_id),
                "firmware_id": UUID(record.firmware_id),
                "firmware_revision": record.firmware_revision,
                "source_revision_id": UUID(record.source_revision_id),
                "build_input_snapshot_id": (
                    UUID(record.build_input_snapshot_id) if record.build_input_snapshot_id else None
                ),
                "input_hash": record.input_hash,
                "ruleset_version": record.ruleset_version,
                "status": record.status,
                "rule_results": [_to_rule(item) for item in rules],
                "tool_results": [
                    StaticAnalysisToolResult.model_validate(item) for item in record.tool_results
                ],
            }
        )


__all__ = ["SqlAlchemyFirmwareStaticAnalysisRepository"]
