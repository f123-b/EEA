"""SQLAlchemy persistence adapters for M8 architecture IR."""

from typing import Any, cast
from uuid import UUID

from eea_core.architecture import ArchitectureBundle, HardwareIR, SystemArchitectureIR
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from eea_backend.models import HardwareIRRecord, SystemArchitectureRecord


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


def _to_system_architecture(record: SystemArchitectureRecord) -> SystemArchitectureIR:
    return SystemArchitectureIR.model_validate(
        {
            **_entity_kwargs(record),
            "project_id": UUID(record.project_id),
            "pin_plan_id": UUID(record.pin_plan_id),
            "pin_plan_revision": record.pin_plan_revision,
            "blocks": record.blocks,
            "interfaces": record.interfaces,
            "decisions": record.decisions,
            "requirement_ids": record.requirement_ids,
            "evidence_ids": record.evidence_ids,
            "source_artifact_ids": record.source_artifact_ids,
            "pin_assignment_revisions": record.pin_assignment_revisions,
        }
    )


def _to_hardware(record: HardwareIRRecord) -> HardwareIR:
    return HardwareIR.model_validate(
        {
            **_entity_kwargs(record),
            "project_id": UUID(record.project_id),
            "architecture_id": UUID(record.architecture_id),
            "pin_plan_id": UUID(record.pin_plan_id),
            "pin_plan_revision": record.pin_plan_revision,
            "modules": record.modules,
            "device_instances": record.device_instances,
            "power_domains": record.power_domains,
            "interfaces": record.interfaces,
            "pin_requirements": record.pin_requirements,
            "constraints": record.constraints,
            "requirement_ids": record.requirement_ids,
            "evidence_ids": record.evidence_ids,
            "pin_assignment_revisions": record.pin_assignment_revisions,
        }
    )


class SqlAlchemyArchitectureRepository:
    """Persist architecture and hardware IR as one project-scoped bundle."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, bundle: ArchitectureBundle, *, commit: bool = True) -> ArchitectureBundle:
        architecture = bundle.system_architecture
        hardware = bundle.hardware
        serialized_architecture = architecture.model_dump(mode="json")
        architecture_record = SystemArchitectureRecord(
            id=str(architecture.id),
            schema_version=architecture.schema_version,
            revision=architecture.revision,
            created_at=architecture.created_at,
            updated_at=architecture.updated_at,
            entity_metadata=architecture.metadata,
            project_id=str(architecture.project_id),
            pin_plan_id=str(architecture.pin_plan_id),
            pin_plan_revision=architecture.pin_plan_revision,
            blocks=cast(list[dict[str, Any]], serialized_architecture["blocks"]),
            interfaces=cast(list[dict[str, Any]], serialized_architecture["interfaces"]),
            decisions=cast(list[dict[str, Any]], serialized_architecture["decisions"]),
            requirement_ids=[str(value) for value in architecture.requirement_ids],
            evidence_ids=[str(value) for value in architecture.evidence_ids],
            source_artifact_ids=[str(value) for value in architecture.source_artifact_ids],
            pin_assignment_revisions=architecture.pin_assignment_revisions,
        )
        serialized_hardware = hardware.model_dump(mode="json")
        hardware_record = HardwareIRRecord(
            id=str(hardware.id),
            schema_version=hardware.schema_version,
            revision=hardware.revision,
            created_at=hardware.created_at,
            updated_at=hardware.updated_at,
            entity_metadata=hardware.metadata,
            project_id=str(hardware.project_id),
            architecture_id=str(hardware.architecture_id),
            pin_plan_id=str(hardware.pin_plan_id),
            pin_plan_revision=hardware.pin_plan_revision,
            modules=cast(list[dict[str, Any]], serialized_hardware["modules"]),
            device_instances=cast(list[dict[str, Any]], serialized_hardware["device_instances"]),
            power_domains=cast(list[dict[str, Any]], serialized_hardware["power_domains"]),
            interfaces=cast(list[dict[str, Any]], serialized_hardware["interfaces"]),
            pin_requirements=cast(list[dict[str, Any]], serialized_hardware["pin_requirements"]),
            constraints=cast(list[dict[str, Any]], serialized_hardware["constraints"]),
            requirement_ids=[str(value) for value in hardware.requirement_ids],
            evidence_ids=[str(value) for value in hardware.evidence_ids],
            pin_assignment_revisions=hardware.pin_assignment_revisions,
        )
        self._session.add(architecture_record)
        self._session.flush()
        self._session.add(hardware_record)
        if commit:
            self._session.commit()
            self._session.refresh(architecture_record)
        else:
            self._session.flush()
        return self.get(architecture.id, project_id=architecture.project_id) or bundle

    def get(
        self, architecture_id: UUID, *, project_id: UUID | None = None
    ) -> ArchitectureBundle | None:
        statement = select(SystemArchitectureRecord).where(
            SystemArchitectureRecord.id == str(architecture_id)
        )
        if project_id is not None:
            statement = statement.where(SystemArchitectureRecord.project_id == str(project_id))
        architecture_record = self._session.scalar(statement)
        if architecture_record is None:
            return None
        hardware_record = self._session.scalar(
            select(HardwareIRRecord).where(
                HardwareIRRecord.architecture_id == str(architecture_id),
                HardwareIRRecord.project_id == architecture_record.project_id,
            )
        )
        if hardware_record is None:
            return None
        return ArchitectureBundle(
            system_architecture=_to_system_architecture(architecture_record),
            hardware=_to_hardware(hardware_record),
        )

    def latest_for_project(self, project_id: UUID) -> ArchitectureBundle | None:
        statement = (
            select(SystemArchitectureRecord)
            .where(SystemArchitectureRecord.project_id == str(project_id))
            .order_by(desc(SystemArchitectureRecord.created_at), desc(SystemArchitectureRecord.id))
            .limit(1)
        )
        record = self._session.scalar(statement)
        return self.get(UUID(record.id), project_id=project_id) if record else None


__all__ = ["SqlAlchemyArchitectureRepository"]
