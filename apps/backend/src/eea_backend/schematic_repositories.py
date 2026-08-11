"""SQLAlchemy persistence adapters for M10 schematic artifacts and ERC reports."""

from typing import Any, cast
from uuid import UUID

from eea_core.entities import Artifact, utc_now
from eea_core.schematic import ErcReport, SchematicBundle, SchematicIR
from sqlalchemy import desc, select, update
from sqlalchemy.orm import Session

from eea_backend.models import (
    ArtifactRecord,
    ErcReportRecord,
    SchematicArtifactRecord,
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


class SqlAlchemySchematicRepository:
    """Persist schematic artifacts and the latest ERC report per artifact."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, bundle: SchematicBundle, *, commit: bool = True) -> SchematicBundle:
        artifact = bundle.artifact
        schematic = bundle.schematic
        self._mark_current_stale(schematic.project_id)
        artifact_record = ArtifactRecord(
            id=str(artifact.id),
            schema_version=artifact.schema_version,
            revision=artifact.revision,
            created_at=artifact.created_at,
            updated_at=artifact.updated_at,
            entity_metadata=artifact.metadata,
            project_id=str(artifact.project_id),
            logical_name=artifact.logical_name,
            artifact_type=artifact.artifact_type,
            version_label=artifact.version_label,
            content_hash=artifact.content_hash,
            input_hash=artifact.input_hash,
            storage_uri=artifact.storage_uri,
            parent_artifact_id=(
                str(artifact.parent_artifact_id) if artifact.parent_artifact_id else None
            ),
            dependency_ids=[str(value) for value in artifact.dependency_ids],
            dependency_hashes=artifact.dependency_hashes,
            created_by=artifact.created_by,
            source_job_id=str(artifact.source_job_id) if artifact.source_job_id else None,
            generator_version=artifact.generator_version,
            tool_versions=artifact.tool_versions,
            knowledge_snapshot=artifact.knowledge_snapshot,
            status=artifact.status.value,
        )
        serialized = schematic.model_dump(mode="json")
        schematic_record = SchematicArtifactRecord(
            id=str(schematic.id),
            schema_version=schematic.schema_version,
            revision=schematic.revision,
            created_at=schematic.created_at,
            updated_at=schematic.updated_at,
            entity_metadata=schematic.metadata,
            artifact_id=str(artifact.id),
            project_id=str(schematic.project_id),
            circuit_id=str(schematic.circuit_id),
            circuit_revision=schematic.circuit_revision,
            hardware_ir_id=str(schematic.hardware_ir_id),
            hardware_ir_revision=schematic.hardware_ir_revision,
            format=schematic.format,
            components=cast(list[dict[str, Any]], serialized["components"]),
            nets=cast(list[dict[str, Any]], serialized["nets"]),
            power_nets=cast(list[dict[str, Any]], serialized["power_nets"]),
            constraints=cast(list[dict[str, Any]], serialized["constraints"]),
            netlist_text=schematic.netlist_text,
            content_hash=schematic.content_hash,
            input_hash=schematic.input_hash,
            preflight_results=cast(list[dict[str, Any]], serialized["preflight_results"]),
            requirement_ids=[str(value) for value in schematic.requirement_ids],
            evidence_ids=[str(value) for value in schematic.evidence_ids],
            pin_assignment_revisions=schematic.pin_assignment_revisions,
        )
        self._session.add(artifact_record)
        self._session.flush()
        self._session.add(schematic_record)
        self._session.flush()
        self._session.add(self._erc_record(bundle.erc_report))
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        return self.get(schematic.id, project_id=schematic.project_id) or bundle

    def get(self, schematic_id: UUID, *, project_id: UUID | None = None) -> SchematicBundle | None:
        statement = select(SchematicArtifactRecord).where(
            SchematicArtifactRecord.id == str(schematic_id)
        )
        if project_id is not None:
            statement = statement.where(SchematicArtifactRecord.project_id == str(project_id))
        record = self._session.scalar(statement)
        return self._to_bundle(record) if record else None

    def latest_for_project(self, project_id: UUID) -> SchematicBundle | None:
        statement = (
            select(SchematicArtifactRecord)
            .join(ArtifactRecord, ArtifactRecord.id == SchematicArtifactRecord.artifact_id)
            .where(
                SchematicArtifactRecord.project_id == str(project_id),
                ArtifactRecord.status == "CURRENT",
            )
            .order_by(desc(SchematicArtifactRecord.created_at), desc(SchematicArtifactRecord.id))
            .limit(1)
        )
        record = self._session.scalar(statement)
        return self._to_bundle(record) if record else None

    def save_erc_report(self, report: ErcReport, *, commit: bool = True) -> ErcReport:
        self._session.add(self._erc_record(report))
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        return self._latest_erc_report(report.schematic_id) or report

    def mark_stale_for_circuit(
        self, project_id: UUID, current_circuit_id: UUID, *, commit: bool = True
    ) -> None:
        artifact_ids = list(
            self._session.scalars(
                select(SchematicArtifactRecord.artifact_id).where(
                    SchematicArtifactRecord.project_id == str(project_id),
                    SchematicArtifactRecord.circuit_id != str(current_circuit_id),
                )
            )
        )
        if artifact_ids:
            self._session.execute(
                update(ArtifactRecord)
                .where(
                    ArtifactRecord.id.in_(artifact_ids),
                    ArtifactRecord.status == "CURRENT",
                )
                .values(status="STALE", updated_at=utc_now())
            )
        if commit:
            self._session.commit()
        else:
            self._session.flush()

    def _to_bundle(self, record: SchematicArtifactRecord) -> SchematicBundle:
        artifact_record = self._session.scalar(
            select(ArtifactRecord).where(ArtifactRecord.id == record.artifact_id)
        )
        if artifact_record is None:
            raise ValueError("schematic artifact metadata is missing")
        artifact = Artifact.model_validate(
            {
                **_entity_kwargs(artifact_record),
                "project_id": UUID(artifact_record.project_id),
                "logical_name": artifact_record.logical_name,
                "artifact_type": artifact_record.artifact_type,
                "version_label": artifact_record.version_label,
                "content_hash": artifact_record.content_hash,
                "input_hash": artifact_record.input_hash,
                "storage_uri": artifact_record.storage_uri,
                "parent_artifact_id": artifact_record.parent_artifact_id,
                "dependency_ids": artifact_record.dependency_ids,
                "dependency_hashes": artifact_record.dependency_hashes,
                "created_by": artifact_record.created_by,
                "source_job_id": artifact_record.source_job_id,
                "generator_version": artifact_record.generator_version,
                "tool_versions": artifact_record.tool_versions,
                "knowledge_snapshot": artifact_record.knowledge_snapshot,
                "status": artifact_record.status,
            }
        )
        schematic = SchematicIR.model_validate(
            {
                **_entity_kwargs(record),
                "project_id": UUID(record.project_id),
                "artifact_id": UUID(record.artifact_id),
                "circuit_id": UUID(record.circuit_id),
                "circuit_revision": record.circuit_revision,
                "hardware_ir_id": UUID(record.hardware_ir_id),
                "hardware_ir_revision": record.hardware_ir_revision,
                "format": record.format,
                "components": record.components,
                "nets": record.nets,
                "power_nets": record.power_nets,
                "constraints": record.constraints,
                "netlist_text": record.netlist_text,
                "content_hash": record.content_hash,
                "input_hash": record.input_hash,
                "preflight_results": record.preflight_results,
                "requirement_ids": record.requirement_ids,
                "evidence_ids": record.evidence_ids,
                "pin_assignment_revisions": record.pin_assignment_revisions,
            }
        )
        report = self._latest_erc_report(schematic.id)
        if report is None:
            raise ValueError("schematic ERC report is missing")
        return SchematicBundle(artifact=artifact, schematic=schematic, erc_report=report)

    def _latest_erc_report(self, schematic_id: UUID) -> ErcReport | None:
        statement = (
            select(ErcReportRecord)
            .where(ErcReportRecord.schematic_id == str(schematic_id))
            .order_by(desc(ErcReportRecord.created_at), desc(ErcReportRecord.id))
            .limit(1)
        )
        record = self._session.scalar(statement)
        if record is None:
            return None
        return ErcReport.model_validate(
            {
                **_entity_kwargs(record),
                "project_id": UUID(record.project_id),
                "schematic_id": UUID(record.schematic_id),
                "schematic_revision": record.schematic_revision,
                "circuit_id": UUID(record.circuit_id),
                "circuit_revision": record.circuit_revision,
                "status": record.status,
                "tool_name": record.tool_name,
                "tool_version": record.tool_version,
                "executed": record.executed,
                "issues": record.issues,
                "source_revision_snapshot": record.source_revision_snapshot,
                "evidence_ids": record.evidence_ids,
                "recommendation": record.recommendation,
            }
        )

    @staticmethod
    def _erc_record(report: ErcReport) -> ErcReportRecord:
        serialized = report.model_dump(mode="json")
        return ErcReportRecord(
            id=str(report.id),
            schema_version=report.schema_version,
            revision=report.revision,
            created_at=report.created_at,
            updated_at=report.updated_at,
            entity_metadata=report.metadata,
            project_id=str(report.project_id),
            schematic_id=str(report.schematic_id),
            schematic_revision=report.schematic_revision,
            circuit_id=str(report.circuit_id),
            circuit_revision=report.circuit_revision,
            status=report.status,
            tool_name=report.tool_name,
            tool_version=report.tool_version,
            executed=report.executed,
            issues=cast(list[dict[str, Any]], serialized["issues"]),
            source_revision_snapshot=report.source_revision_snapshot,
            evidence_ids=[str(value) for value in report.evidence_ids],
            recommendation=report.recommendation,
        )

    def _mark_current_stale(self, project_id: UUID) -> None:
        self._session.execute(
            update(ArtifactRecord)
            .where(
                ArtifactRecord.project_id == str(project_id),
                ArtifactRecord.artifact_type == "SCHEMATIC_NETLIST",
                ArtifactRecord.status == "CURRENT",
            )
            .values(status="STALE", updated_at=utc_now())
        )


__all__ = ["SqlAlchemySchematicRepository"]
