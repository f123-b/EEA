"""SQLAlchemy persistence adapters for M12 FirmwareIR and source candidates."""

from typing import Any, cast
from uuid import UUID

from eea_core.firmware import FirmwareBundle, FirmwareIR, FirmwareSourceFile
from eea_core.source import SourceRevision
from sqlalchemy import desc, select, update
from sqlalchemy.orm import Session

from eea_backend.component_repositories import SqlAlchemyDependencyLockRepository
from eea_backend.models import (
    FirmwareRecord,
    FirmwareSourceFileRecord,
    SourceRevisionRecord,
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


def _to_source_revision(record: SourceRevisionRecord) -> SourceRevision:
    return SourceRevision.model_validate(
        {
            **_entity_kwargs(record),
            "project_id": UUID(record.project_id),
            "repository_id": record.repository_id,
            "commit_sha": record.commit_sha,
            "tree_hash": record.tree_hash,
            "dirty": record.dirty,
            "base_commit": record.base_commit,
            "workspace_revision": record.workspace_revision,
            "source_manifest_hash": record.source_manifest_hash,
            "file_manifest": record.file_manifest,
            "created_by": record.created_by,
        }
    )


class SqlAlchemyFirmwareRepository:
    """Persist FirmwareIR with its candidate source files and source snapshot."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, bundle: FirmwareBundle, *, commit: bool = True) -> FirmwareBundle:
        firmware = bundle.firmware
        self._session.execute(
            update(FirmwareRecord)
            .where(
                FirmwareRecord.project_id == str(firmware.project_id),
                FirmwareRecord.status == "CURRENT",
            )
            .values(status="STALE")
        )
        source = bundle.source_revision
        if bundle.dependency_lock is not None:
            SqlAlchemyDependencyLockRepository(self._session).add(
                bundle.dependency_lock, commit=False
            )
        source_record = SourceRevisionRecord(
            id=str(source.id),
            schema_version=source.schema_version,
            revision=source.revision,
            created_at=source.created_at,
            updated_at=source.updated_at,
            entity_metadata=source.metadata,
            project_id=str(source.project_id),
            repository_id=source.repository_id,
            commit_sha=source.commit_sha,
            tree_hash=source.tree_hash,
            dirty=source.dirty,
            base_commit=source.base_commit,
            workspace_revision=source.workspace_revision,
            source_manifest_hash=source.source_manifest_hash,
            file_manifest=source.file_manifest,
            created_by=source.created_by,
        )
        serialized = firmware.model_dump(mode="json")
        record = FirmwareRecord(
            id=str(firmware.id),
            schema_version=firmware.schema_version,
            revision=firmware.revision,
            created_at=firmware.created_at,
            updated_at=firmware.updated_at,
            entity_metadata=firmware.metadata,
            project_id=str(firmware.project_id),
            mcu_config_id=str(firmware.mcu_config_id),
            mcu_config_revision=firmware.mcu_config_revision,
            hardware_ir_id=str(firmware.hardware_ir_id),
            hardware_ir_revision=firmware.hardware_ir_revision,
            circuit_id=str(firmware.circuit_id),
            circuit_revision=firmware.circuit_revision,
            schematic_id=str(firmware.schematic_id),
            schematic_revision=firmware.schematic_revision,
            source_revision_id=str(firmware.source_revision_id),
            dependency_lock_id=(
                str(firmware.dependency_lock_id) if firmware.dependency_lock_id else None
            ),
            dependency_lock_hash=firmware.dependency_lock_hash,
            component_refs=firmware.component_refs,
            platform_adapter_id=firmware.platform_adapter_id,
            platform_adapter_version=firmware.platform_adapter_version,
            layers=firmware.layers,
            modules=cast(list[dict[str, Any]], serialized["modules"]),
            tasks=cast(list[dict[str, Any]], serialized["tasks"]),
            interrupts=cast(list[dict[str, Any]], serialized["interrupts"]),
            shared_resources=cast(list[dict[str, Any]], serialized["shared_resources"]),
            startup=cast(dict[str, Any], serialized["startup"]),
            clock_tree=cast(dict[str, Any], serialized["clock_tree"]),
            peripheral_drivers=cast(list[dict[str, Any]], serialized["peripheral_drivers"]),
            memory_layout=cast(dict[str, Any], serialized["memory_layout"]),
            bsp=cast(dict[str, Any], serialized["bsp"]),
            build_target=cast(dict[str, Any], serialized["build_target"]),
            rule_results=cast(list[dict[str, Any]], serialized["rule_results"]),
            requirement_ids=[str(value) for value in firmware.requirement_ids],
            evidence_ids=[str(value) for value in firmware.evidence_ids],
            input_hash=firmware.input_hash,
            status=firmware.status.value,
        )
        self._session.add(source_record)
        self._session.flush()
        self._session.add(record)
        self._session.flush()
        for item in bundle.files:
            self._session.add(
                FirmwareSourceFileRecord(
                    id=str(item.id),
                    schema_version=item.schema_version,
                    revision=item.revision,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                    entity_metadata=item.metadata,
                    project_id=str(firmware.project_id),
                    firmware_id=str(firmware.id),
                    path=item.path,
                    content=item.content,
                    content_hash=item.content_hash,
                    input_hash=item.input_hash,
                    generated_owned=item.generated_owned,
                    generator_version=item.generator_version,
                )
            )
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        return self.get(firmware.id, project_id=firmware.project_id) or bundle

    def get(self, firmware_id: UUID, *, project_id: UUID | None = None) -> FirmwareBundle | None:
        statement = select(FirmwareRecord).where(FirmwareRecord.id == str(firmware_id))
        if project_id is not None:
            statement = statement.where(FirmwareRecord.project_id == str(project_id))
        record = self._session.scalar(statement)
        return self._to_bundle(record) if record else None

    def latest_for_project(self, project_id: UUID) -> FirmwareBundle | None:
        statement = (
            select(FirmwareRecord)
            .where(
                FirmwareRecord.project_id == str(project_id),
                FirmwareRecord.status == "CURRENT",
            )
            .order_by(desc(FirmwareRecord.created_at), desc(FirmwareRecord.id))
            .limit(1)
        )
        record = self._session.scalar(statement)
        return self._to_bundle(record) if record else None

    def _to_bundle(self, record: FirmwareRecord) -> FirmwareBundle:
        source_record = self._session.scalar(
            select(SourceRevisionRecord).where(SourceRevisionRecord.id == record.source_revision_id)
        )
        if source_record is None:
            raise ValueError("firmware source revision is missing")
        files = list(
            self._session.scalars(
                select(FirmwareSourceFileRecord)
                .where(FirmwareSourceFileRecord.firmware_id == record.id)
                .order_by(FirmwareSourceFileRecord.path)
            )
        )
        firmware = FirmwareIR.model_validate(
            {
                **_entity_kwargs(record),
                "project_id": UUID(record.project_id),
                "mcu_config_id": UUID(record.mcu_config_id),
                "mcu_config_revision": record.mcu_config_revision,
                "hardware_ir_id": UUID(record.hardware_ir_id),
                "hardware_ir_revision": record.hardware_ir_revision,
                "circuit_id": UUID(record.circuit_id),
                "circuit_revision": record.circuit_revision,
                "schematic_id": UUID(record.schematic_id),
                "schematic_revision": record.schematic_revision,
                "source_revision_id": UUID(record.source_revision_id),
                "dependency_lock_id": (
                    UUID(record.dependency_lock_id) if record.dependency_lock_id else None
                ),
                "dependency_lock_hash": record.dependency_lock_hash,
                "component_refs": record.component_refs or [],
                "platform_adapter_id": record.platform_adapter_id or "legacy-m12",
                "platform_adapter_version": record.platform_adapter_version or "m12.1",
                "layers": record.layers,
                "modules": record.modules,
                "tasks": record.tasks,
                "interrupts": record.interrupts,
                "shared_resources": record.shared_resources,
                "startup": record.startup,
                "clock_tree": record.clock_tree,
                "peripheral_drivers": record.peripheral_drivers,
                "memory_layout": record.memory_layout,
                "bsp": record.bsp,
                "build_target": record.build_target,
                "rule_results": record.rule_results,
                "requirement_ids": record.requirement_ids,
                "evidence_ids": record.evidence_ids,
                "input_hash": record.input_hash,
                "status": record.status,
            }
        )
        source = _to_source_revision(source_record)
        dependency_lock = None
        if record.dependency_lock_id:
            dependency_lock = SqlAlchemyDependencyLockRepository(self._session).get(
                UUID(record.dependency_lock_id), project_id=UUID(record.project_id)
            )
        return FirmwareBundle(
            firmware=firmware,
            source_revision=source,
            files=[
                FirmwareSourceFile.model_validate(
                    {
                        **_entity_kwargs(item),
                        "path": item.path,
                        "content": item.content,
                        "content_hash": item.content_hash,
                        "input_hash": item.input_hash,
                        "generated_owned": item.generated_owned,
                        "generator_version": item.generator_version,
                    }
                )
                for item in files
            ],
            dependency_lock=dependency_lock,
        )


__all__ = ["SqlAlchemyFirmwareRepository"]
