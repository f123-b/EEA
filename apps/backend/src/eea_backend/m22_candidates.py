"""M22R candidate persistence, review, preview, and canonical apply contracts."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID, uuid4, uuid5

from eea_core.entities import utc_now
from eea_core.enums import (
    ClaimLifecycle,
    EngineeringErrorCode,
    EvidenceType,
    IssueSeverity,
    IssueStatus,
)
from eea_core.errors import EngineeringError
from eea_core.protocol import ProtocolField, ProtocolIR, ProtocolMessage, ProtocolTransport
from sqlalchemy import select
from sqlalchemy.orm import Session

from eea_backend.models import (
    ArtifactRecord,
    CircuitRecord,
    EngineeringClaimRecord,
    EvidenceRecord,
    HardwareIRRecord,
    ImportCandidateRecord,
    ImportConflictRecord,
    ImportReviewRecord,
    IssueRecord,
    MCUConfigRecord,
    PinPlanRecord,
    ProtocolRecord,
    SchematicArtifactRecord,
    SystemArchitectureRecord,
)
from eea_backend.protocol_repositories import SqlAlchemyProtocolRepository


def candidate_data(record: ImportCandidateRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "schema_version": record.schema_version,
        "revision": record.revision,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "import_id": record.import_id,
        "project_id": record.project_id,
        "source_scan_revision": record.source_scan_revision,
        "source_revision_id": record.source_revision_id,
        "candidate_type": record.candidate_type,
        "semantic_key": record.semantic_key,
        "proposed_value": record.proposed_value,
        "confidence": record.confidence,
        "source_kind": record.source_kind,
        "source_ref": record.source_ref,
        "source_file": record.source_file,
        "source_location": record.source_location,
        "evidence_ids": list(record.evidence_ids),
        "parser_name": record.parser_name,
        "parser_version": record.parser_version,
        "status": record.status,
        "canonical_ref": record.canonical_ref,
        "apply_revision": record.apply_revision,
        "apply_evidence": list(record.apply_evidence),
        "created_by": record.created_by,
    }


def list_candidates(session: Session, import_id: UUID) -> list[dict[str, object]]:
    records = session.scalars(
        select(ImportCandidateRecord)
        .where(ImportCandidateRecord.import_id == str(import_id))
        .order_by(ImportCandidateRecord.source_scan_revision, ImportCandidateRecord.semantic_key)
    )
    return [candidate_data(record) for record in records]


def _candidate_uuid(import_id: UUID, scan_revision: int, semantic_key: str) -> UUID:
    return uuid5(import_id, f"m22r-candidate:{scan_revision}:{semantic_key}")


def _evidence_uuid(candidate_id: UUID, item: dict[str, Any]) -> UUID:
    return uuid5(
        candidate_id,
        (
            f"{item.get('source_file', '')}:{item.get('source_location', {})}:"
            f"{item.get('excerpt', '')}"
        ),
    )


def persist_scan_candidates(
    session: Session,
    *,
    import_id: UUID,
    project_id: UUID | None,
    scan_revision: int,
    file_manifest: dict[str, str],
    candidates: list[dict[str, Any]],
    actor_id: str,
) -> list[dict[str, object]]:
    """Persist parser observations and their source evidence for one scan."""

    old_records = session.scalars(
        select(ImportCandidateRecord).where(
            ImportCandidateRecord.import_id == str(import_id),
            ImportCandidateRecord.source_scan_revision < scan_revision,
            ImportCandidateRecord.status.in_(
                ["DETECTED", "UNKNOWN", "ACCEPTED_CANDIDATE", "EDITED_CANDIDATE"]
            ),
        )
    )
    now = utc_now()
    for record in old_records:
        record.status = "STALE"
        record.revision += 1
        record.updated_at = now

    persisted: list[dict[str, object]] = []
    for raw in candidates:
        source_file = str(raw.get("source_file", "UNKNOWN"))
        semantic_key = f"{source_file}::{raw.get('semantic_key', 'UNKNOWN')}"
        candidate_id = _candidate_uuid(import_id, scan_revision, semantic_key)
        evidence_ids: list[str] = []
        raw_evidence = raw.get("evidence", [])
        evidence_items = raw_evidence if isinstance(raw_evidence, list) else []
        for raw_item in evidence_items:
            item = raw_item if isinstance(raw_item, dict) else {}
            evidence_id = _evidence_uuid(candidate_id, item)
            evidence_ids.append(str(evidence_id))
            if session.get(EvidenceRecord, str(evidence_id)) is None:
                locator = {
                    "import_session_id": str(import_id),
                    "candidate_id": str(candidate_id),
                    "source_file": source_file,
                    "source_location": item.get("source_location", {}),
                    "parser_name": raw.get("parser_name", "UNKNOWN"),
                    "parser_version": raw.get("parser_version", "UNKNOWN"),
                    "status": "PASS" if raw.get("status") == "DETECTED" else "UNKNOWN",
                }
                session.add(
                    EvidenceRecord(
                        id=str(evidence_id),
                        schema_version="1.0",
                        revision=1,
                        created_at=now,
                        updated_at=now,
                        entity_metadata={"m22r": True, "candidate_only": True},
                        project_id=str(project_id) if project_id else None,
                        evidence_type=EvidenceType.IMPORTED_PROJECT.value,
                        locator=locator,
                        source_uri=source_file,
                        content_hash=file_manifest.get(source_file),
                        summary=str(item.get("excerpt") or "Parser-backed import evidence"),
                    )
                )
        status = str(raw.get("status", "UNKNOWN"))
        if status not in {"DETECTED", "UNKNOWN", "CONFLICTED"}:
            status = "UNKNOWN"
        record = ImportCandidateRecord(
            id=str(candidate_id),
            schema_version="1.0",
            revision=1,
            created_at=now,
            updated_at=now,
            entity_metadata={"m22r": True, "candidate_only": True},
            import_id=str(import_id),
            project_id=str(project_id) if project_id else None,
            source_scan_revision=scan_revision,
            source_revision_id=None,
            candidate_type=str(raw.get("candidate_type", "CLAIM")),
            semantic_key=semantic_key,
            proposed_value=(
                raw.get("proposed_value", {})
                if isinstance(raw.get("proposed_value"), dict)
                else {"value": raw.get("proposed_value")}
            ),
            confidence=float(raw.get("confidence", 0.0)),
            source_kind=str(raw.get("source_kind", "UNKNOWN")),
            source_ref=str(raw.get("source_ref", source_file)),
            source_file=source_file,
            source_location=(
                raw.get("source_location", {})
                if isinstance(raw.get("source_location"), dict)
                else {}
            ),
            evidence_ids=sorted(set(evidence_ids)),
            parser_name=str(raw.get("parser_name", "UNKNOWN")),
            parser_version=str(raw.get("parser_version", "UNKNOWN")),
            status=status,
            canonical_ref=None,
            apply_revision=None,
            apply_evidence=[],
            created_by=actor_id,
        )
        session.add(record)
        persisted.append(candidate_data(record))
    session.flush()
    return persisted


def bind_candidates_to_workspace(
    session: Session,
    *,
    import_id: UUID,
    project_id: UUID,
    source_revision_id: UUID,
    scan_revision: int | None = None,
) -> None:
    statement = select(ImportCandidateRecord).where(
        ImportCandidateRecord.import_id == str(import_id)
    )
    if scan_revision is not None:
        statement = statement.where(ImportCandidateRecord.source_scan_revision == scan_revision)
    candidates = session.scalars(statement)
    for candidate in candidates:
        candidate.project_id = str(project_id)
        candidate.source_revision_id = str(source_revision_id)
        candidate.revision += 1
        candidate.updated_at = utc_now()
        for evidence_id in candidate.evidence_ids:
            evidence = session.get(EvidenceRecord, evidence_id)
            if evidence is not None:
                evidence.project_id = str(project_id)
                evidence.locator = {
                    **evidence.locator,
                    "source_revision_id": str(source_revision_id),
                }
                evidence.revision += 1
                evidence.updated_at = utc_now()


def review_candidate(
    session: Session,
    *,
    import_id: UUID,
    candidate_id: UUID,
    expected_revision: int,
    action: str,
    actor_id: str,
    value: object | None = None,
    note: str | None = None,
) -> ImportCandidateRecord:
    candidate = session.scalar(
        select(ImportCandidateRecord).where(
            ImportCandidateRecord.id == str(candidate_id),
            ImportCandidateRecord.import_id == str(import_id),
        )
    )
    if candidate is None:
        raise EngineeringError(
            EngineeringErrorCode.VALIDATION_ERROR,
            "Import candidate was not found",
        )
    if candidate.revision != expected_revision:
        raise EngineeringError(
            EngineeringErrorCode.REVISION_CONFLICT,
            "Import candidate revision does not match",
            details={"candidate_id": str(candidate_id), "expected_revision": expected_revision},
        )
    if candidate.status in {"APPLIED", "STALE"}:
        raise EngineeringError(
            EngineeringErrorCode.REVISION_CONFLICT,
            "Applied or stale candidates cannot be reviewed",
            details={"candidate_id": str(candidate_id), "status": candidate.status},
        )
    normalized_action = action.upper()
    allowed = {"ACCEPT", "EDIT", "REJECT", "UNKNOWN"}
    if normalized_action not in allowed:
        raise EngineeringError(
            EngineeringErrorCode.VALIDATION_ERROR,
            "Unsupported candidate review action",
        )
    previous = candidate.status
    if normalized_action == "ACCEPT":
        next_status = "ACCEPTED_CANDIDATE"
    elif normalized_action == "EDIT":
        if not isinstance(value, dict):
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR,
                "Candidate EDIT requires a structured object value",
            )
        candidate.proposed_value = value
        next_status = "EDITED_CANDIDATE"
    elif normalized_action == "REJECT":
        next_status = "REJECTED"
    else:
        next_status = "UNKNOWN"
    candidate.status = next_status
    candidate.revision += 1
    candidate.updated_at = utc_now()
    review_id = uuid4()
    session.add(
        ImportReviewRecord(
            id=str(review_id),
            schema_version="1.0",
            revision=1,
            created_at=utc_now(),
            updated_at=utc_now(),
            entity_metadata={"m22r": True},
            import_id=str(import_id),
            candidate_id=str(candidate_id),
            expected_candidate_revision=expected_revision,
            action=normalized_action,
            from_status=previous,
            to_status=next_status,
            value=value,
            note=note,
            actor_id=actor_id,
        )
    )
    session.flush()
    return candidate


def _metadata(candidate: ImportCandidateRecord) -> dict[str, Any]:
    return {
        "m22r": True,
        "candidate_only": True,
        "candidate_id": candidate.id,
        "semantic_key": candidate.semantic_key,
        "proposed_value": candidate.proposed_value,
    }


def _canonical_records(session: Session, candidate: ImportCandidateRecord) -> list[Any]:
    project_id = candidate.project_id
    if project_id is None:
        return []
    mapping: dict[str, type[Any]] = {
        "HARDWARE": HardwareIRRecord,
        "MCU_CONFIG": MCUConfigRecord,
        "PROTOCOL": ProtocolRecord,
    }
    record_type = mapping.get(candidate.candidate_type)
    if record_type is None:
        return list(
            session.scalars(
                select(EngineeringClaimRecord).where(
                    EngineeringClaimRecord.project_id == project_id,
                    EngineeringClaimRecord.subject_ref == candidate.semantic_key,
                )
            )
        )
    statement = select(record_type).where(record_type.project_id == project_id)
    if record_type is ProtocolRecord:
        statement = statement.where(record_type.status == "CURRENT")
    elif hasattr(record_type, "status"):
        statement = statement.where(record_type.status.not_in(["STALE", "INVALID", "REJECTED"]))
    return list(session.scalars(statement))


def _record_metadata(record: Any) -> dict[str, Any]:
    value = getattr(record, "entity_metadata", {})
    return value if isinstance(value, dict) else {}


def preview_candidate(
    session: Session,
    candidate: ImportCandidateRecord,
    *,
    current_source_revision_id: UUID | None,
) -> dict[str, object]:
    if candidate.status not in {"ACCEPTED_CANDIDATE", "EDITED_CANDIDATE"}:
        return {
            "candidate_id": candidate.id,
            "comparison": "STALE" if candidate.status == "STALE" else "DIFFERENT",
            "apply": "BLOCKED",
            "reason": f"candidate status {candidate.status} is not accepted",
        }
    if current_source_revision_id is not None and candidate.source_revision_id != str(
        current_source_revision_id
    ):
        return {
            "candidate_id": candidate.id,
            "comparison": "STALE",
            "apply": "BLOCKED",
            "reason": "candidate source revision is not current",
        }
    records = _canonical_records(session, candidate)
    if not records:
        return {
            "candidate_id": candidate.id,
            "comparison": "NEW",
            "apply": "ALLOW",
            "reason": "no canonical entity exists for this semantic key",
        }
    proposed = candidate.proposed_value
    for record in records:
        metadata = _record_metadata(record)
        if (
            metadata.get("semantic_key") == candidate.semantic_key
            and metadata.get("proposed_value") == proposed
        ):
            return {
                "candidate_id": candidate.id,
                "comparison": "SAME",
                "apply": "ALLOW",
                "canonical_ref": f"{candidate.candidate_type}:{record.id}",
                "reason": "canonical entity already represents the same candidate",
            }
    record = records[0]
    return {
        "candidate_id": candidate.id,
        "comparison": "CONFLICT",
        "apply": "BLOCKED",
        "canonical_ref": f"{candidate.candidate_type}:{record.id}",
        "before": _record_metadata(record),
        "after": proposed,
        "reason": "canonical entity differs; silent overwrite is forbidden",
    }


def _hash_value(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _apply_claim(session: Session, candidate: ImportCandidateRecord) -> str:
    claim_id = uuid4()
    session.add(
        EngineeringClaimRecord(
            id=str(claim_id),
            schema_version="1.0",
            revision=1,
            created_at=utc_now(),
            updated_at=utc_now(),
            entity_metadata=_metadata(candidate),
            project_id=candidate.project_id,
            subject_ref=candidate.semantic_key,
            predicate="import.candidate",
            value_schema_ref="m22r.import-candidate.v1",
            value_json=candidate.proposed_value,
            applicability={"import_id": candidate.import_id, "candidate_id": candidate.id},
            evidence_ids=list(candidate.evidence_ids),
            verification_levels=[],
            confidence=candidate.confidence,
            source_priority=100,
            source_version=candidate.source_revision_id,
            lifecycle=ClaimLifecycle.CANDIDATE.value,
        )
    )
    session.flush()
    return f"EngineeringClaim:{claim_id}"


def _apply_hardware(session: Session, candidate: ImportCandidateRecord) -> str:
    hardware_id = uuid4()
    architecture_id = uuid4()
    pin_plan_id = uuid4()
    value = candidate.proposed_value
    symbols = value.get("symbols", []) if isinstance(value, dict) else []
    devices = [
        {
            "id": str(uuid5(hardware_id, f"device:{index}")),
            "name": str(item.get("reference", f"U{index + 1}")),
            "device_ref": str(item.get("value", "UNKNOWN")),
            "package": item.get("footprint"),
            "module_ref": str(uuid5(hardware_id, "module:0")),
            "attributes": {"origin": "M22R"},
        }
        for index, item in enumerate(symbols)
        if isinstance(item, dict)
    ]
    session.add(
        PinPlanRecord(
            id=str(pin_plan_id),
            schema_version="1.0",
            revision=1,
            created_at=utc_now(),
            updated_at=utc_now(),
            entity_metadata=_metadata(candidate),
            project_id=candidate.project_id,
            analysis_id=None,
            device_ref=str(value.get("mcu", "UNKNOWN")) if isinstance(value, dict) else "UNKNOWN",
            package=None,
            requirements=[],
            candidates=[],
        )
    )
    session.flush()
    session.add(
        SystemArchitectureRecord(
            id=str(architecture_id),
            schema_version="1.0",
            revision=1,
            created_at=utc_now(),
            updated_at=utc_now(),
            entity_metadata=_metadata(candidate),
            project_id=candidate.project_id,
            pin_plan_id=str(pin_plan_id),
            pin_plan_revision=1,
            blocks=[],
            interfaces=[],
            decisions=[],
            requirement_ids=[],
            evidence_ids=list(candidate.evidence_ids),
            source_artifact_ids=[],
            pin_assignment_revisions={},
        )
    )
    session.flush()
    session.add(
        HardwareIRRecord(
            id=str(hardware_id),
            schema_version="1.0",
            revision=1,
            created_at=utc_now(),
            updated_at=utc_now(),
            entity_metadata=_metadata(candidate),
            project_id=candidate.project_id,
            architecture_id=str(architecture_id),
            pin_plan_id=str(pin_plan_id),
            pin_plan_revision=1,
            modules=[
                {
                    "id": str(uuid5(hardware_id, "module:0")),
                    "name": "imported",
                    "kind": "CANDIDATE",
                }
            ],
            device_instances=devices,
            power_domains=[],
            interfaces=[],
            pin_requirements=[],
            constraints=[
                {
                    "status": "UNKNOWN",
                    "reason": "import parser does not infer constraints",
                }
            ],
            requirement_ids=[],
            evidence_ids=list(candidate.evidence_ids),
            pin_assignment_revisions={},
        )
    )
    session.flush()
    return f"HardwareIR:{hardware_id}"


def _apply_mcu_config(session: Session, candidate: ImportCandidateRecord) -> str:
    hardware_ref = _apply_hardware(session, candidate)
    hardware_id = UUID(hardware_ref.split(":", 1)[1])
    circuit_id = uuid4()
    artifact_id = uuid4()
    schematic_id = uuid4()
    config_id = uuid4()
    value = candidate.proposed_value if isinstance(candidate.proposed_value, dict) else {}
    raw_json = _hash_value(value)
    session.add(
        CircuitRecord(
            id=str(circuit_id),
            schema_version="1.0",
            revision=1,
            created_at=utc_now(),
            updated_at=utc_now(),
            entity_metadata=_metadata(candidate),
            project_id=candidate.project_id,
            hardware_ir_id=str(hardware_id),
            hardware_ir_revision=1,
            components=[],
            nets=[],
            power_nets=[],
            constraints=[],
            requirement_ids=[],
            evidence_ids=list(candidate.evidence_ids),
            pin_assignment_revisions={},
        )
    )
    session.add(
        ArtifactRecord(
            id=str(artifact_id),
            schema_version="1.0",
            revision=1,
            created_at=utc_now(),
            updated_at=utc_now(),
            entity_metadata=_metadata(candidate),
            project_id=candidate.project_id,
            logical_name="m22r-import-schematic",
            artifact_type="SCHEMATIC",
            version_label="candidate-1",
            content_hash=raw_json,
            input_hash=raw_json,
            storage_uri=f"import://{candidate.import_id}/{candidate.source_file}",
            parent_artifact_id=None,
            dependency_ids=[str(hardware_id), str(circuit_id)],
            dependency_hashes={},
            created_by=candidate.created_by,
            source_job_id=None,
            generator_version="m22r-import-1",
            tool_versions={},
            knowledge_snapshot=None,
            status="STALE",
        )
    )
    session.flush()
    session.add(
        SchematicArtifactRecord(
            id=str(schematic_id),
            schema_version="1.0",
            revision=1,
            created_at=utc_now(),
            updated_at=utc_now(),
            entity_metadata=_metadata(candidate),
            artifact_id=str(artifact_id),
            project_id=candidate.project_id,
            circuit_id=str(circuit_id),
            circuit_revision=1,
            hardware_ir_id=str(hardware_id),
            hardware_ir_revision=1,
            format="IMPORT_CANDIDATE",
            components=[],
            nets=[],
            power_nets=[],
            constraints=[],
            netlist_text="UNKNOWN",
            content_hash=raw_json,
            input_hash=raw_json,
            preflight_results=[{"status": "UNKNOWN", "reason": "not generated by a trusted tool"}],
            requirement_ids=[],
            evidence_ids=list(candidate.evidence_ids),
            pin_assignment_revisions={},
        )
    )
    session.flush()
    session.add(
        MCUConfigRecord(
            id=str(config_id),
            schema_version="1.0",
            revision=1,
            created_at=utc_now(),
            updated_at=utc_now(),
            entity_metadata=_metadata(candidate),
            project_id=candidate.project_id,
            hardware_ir_id=str(hardware_id),
            hardware_ir_revision=1,
            circuit_id=str(circuit_id),
            circuit_revision=1,
            schematic_id=str(schematic_id),
            schematic_revision=1,
            device_instance_id=str(uuid5(config_id, "device-instance")),
            clock={"source": "UNKNOWN", "parameters": value.get("clocks", {})},
            gpio=value.get("pins", []),
            peripherals=value.get("peripherals", []),
            dma=value.get("dma", []),
            interrupts=[],
            memory=None,
            debug=None,
            capability_snapshot={"status": "UNKNOWN", "origin": "M22R_IMPORT"},
            requirement_ids=[],
            evidence_ids=list(candidate.evidence_ids),
            pin_assignment_revisions={},
            status="STALE",
        )
    )
    session.flush()
    return f"MCUConfigIR:{config_id}"


def _apply_protocol(session: Session, candidate: ImportCandidateRecord) -> str:
    value = candidate.proposed_value if isinstance(candidate.proposed_value, dict) else {}
    raw_messages = value.get("messages", [])
    messages: list[ProtocolMessage] = []
    for index, raw in enumerate(raw_messages if isinstance(raw_messages, list) else []):
        if not isinstance(raw, dict):
            continue
        fields: list[ProtocolField] = []
        for field in raw.get("signals", []) if isinstance(raw.get("signals"), list) else []:
            if not isinstance(field, dict):
                continue
            fields.append(
                ProtocolField(
                    name=str(field.get("name", f"signal_{index}")),
                    bit_offset=int(field.get("start_bit", 0)),
                    bit_length=int(field.get("length", 0)),
                    endian=("LITTLE" if field.get("byte_order") == "LITTLE_ENDIAN" else "BIG"),
                    signed=bool(field.get("signed", False)),
                    scale=float(field.get("factor", 1)),
                    offset=float(field.get("offset", 0)),
                    unit=str(field.get("unit", "")),
                    minimum=field.get("minimum"),
                    maximum=field.get("maximum"),
                )
            )
        messages.append(
            ProtocolMessage(
                name=str(raw.get("name", f"message_{index}")),
                transport_ref="can",
                can_id=int(raw.get("can_id", 0)),
                extended_id=bool(raw.get("extended_id", False)),
                payload_length_bytes=int(raw.get("payload_length_bytes", 0)),
                fields=fields,
                description="M22R parser candidate; review required",
            )
        )
    protocol = ProtocolIR(
        id=uuid4(),
        project_id=UUID(candidate.project_id or "00000000-0000-0000-0000-000000000000"),
        metadata=_metadata(candidate),
        version_label="import-candidate-1",
        transports=[ProtocolTransport(transport_id="can", name="CAN", transport_type="CAN")],
        messages=messages,
        evidence_ids=[UUID(value) for value in candidate.evidence_ids],
    )
    SqlAlchemyProtocolRepository(session).add(protocol, commit=False)
    return f"ProtocolIR:{protocol.id}"


def apply_candidate(session: Session, candidate: ImportCandidateRecord) -> str:
    if candidate.candidate_type == "CLAIM":
        return _apply_claim(session, candidate)
    if candidate.candidate_type == "HARDWARE":
        return _apply_hardware(session, candidate)
    if candidate.candidate_type == "MCU_CONFIG":
        return _apply_mcu_config(session, candidate)
    if candidate.candidate_type == "PROTOCOL":
        return _apply_protocol(session, candidate)
    raise EngineeringError(
        EngineeringErrorCode.VALIDATION_ERROR,
        "Unsupported import candidate type",
        details={"candidate_type": candidate.candidate_type},
    )


def block_conflict(
    session: Session,
    *,
    candidate: ImportCandidateRecord,
    preview: dict[str, object],
) -> ImportConflictRecord:
    canonical_ref = preview.get("canonical_ref")
    conflict = ImportConflictRecord(
        id=str(uuid4()),
        schema_version="1.0",
        revision=1,
        created_at=utc_now(),
        updated_at=utc_now(),
        entity_metadata={"m22r": True},
        import_id=candidate.import_id,
        project_id=candidate.project_id or "",
        candidate_id=candidate.id,
        conflict_kind="CANONICAL_DIFFERENT",
        canonical_type=candidate.candidate_type,
        canonical_ref=str(canonical_ref) if canonical_ref else None,
        before_value=preview.get("before"),
        after_value=preview.get("after", candidate.proposed_value),
        source_revision_id=candidate.source_revision_id,
        status="OPEN",
        reason=str(preview.get("reason", "canonical entity differs")),
    )
    session.add(conflict)
    dedupe = hashlib.sha256(f"m22r:{candidate.id}:{canonical_ref}".encode()).hexdigest()
    if (
        candidate.project_id
        and session.scalar(
            select(IssueRecord).where(
                IssueRecord.project_id == candidate.project_id,
                IssueRecord.dedupe_key == dedupe,
            )
        )
        is None
    ):
        session.add(
            IssueRecord(
                id=str(uuid4()),
                schema_version="1.0",
                revision=1,
                created_at=utc_now(),
                updated_at=utc_now(),
                entity_metadata={"m22r": True},
                project_id=candidate.project_id,
                code="IMPORT_CANONICAL_CONFLICT",
                title="Imported candidate conflicts with canonical entity",
                description=str(preview.get("reason", "canonical entity differs")),
                severity=IssueSeverity.HIGH.value,
                status=IssueStatus.OPEN.value,
                claim_ids=[],
                evidence_ids=list(candidate.evidence_ids),
                resolution=None,
                dedupe_key=dedupe,
                source_kind="M22R_IMPORT",
                source_ref=candidate.id,
                affected_refs=(
                    [candidate.id, str(canonical_ref)] if canonical_ref else [candidate.id]
                ),
                first_seen_at=utc_now(),
                last_seen_at=utc_now(),
                occurrence_count=1,
                last_review_id=None,
            )
        )
    candidate.status = "CONFLICTED"
    candidate.revision += 1
    candidate.updated_at = utc_now()
    session.flush()
    return conflict


def apply_one_candidate(
    session: Session,
    *,
    candidate: ImportCandidateRecord,
    expected_revision: int,
    current_source_revision_id: UUID | None,
) -> dict[str, object]:
    if candidate.project_id is None:
        raise EngineeringError(
            EngineeringErrorCode.VALIDATION_ERROR,
            "Create a workspace before applying import candidates",
            details={"candidate_id": candidate.id},
        )
    if candidate.revision != expected_revision:
        raise EngineeringError(
            EngineeringErrorCode.REVISION_CONFLICT,
            "Import candidate changed before apply",
            details={"candidate_id": candidate.id, "expected_revision": expected_revision},
        )
    plan = preview_candidate(
        session,
        candidate,
        current_source_revision_id=current_source_revision_id,
    )
    if plan.get("apply") != "ALLOW":
        if plan.get("comparison") == "CONFLICT":
            conflict = block_conflict(session, candidate=candidate, preview=plan)
            return {"plan": plan, "status": "BLOCKED", "conflict_id": conflict.id}
        if plan.get("comparison") == "STALE":
            candidate.status = "STALE"
            candidate.revision += 1
            candidate.updated_at = utc_now()
        return {"plan": plan, "status": "BLOCKED"}
    if plan.get("comparison") == "SAME":
        canonical_ref = str(plan["canonical_ref"])
    else:
        canonical_ref = apply_candidate(session, candidate)
    candidate.status = "APPLIED"
    candidate.canonical_ref = canonical_ref
    candidate.apply_revision = candidate.revision + 1
    candidate.apply_evidence = list(candidate.evidence_ids)
    candidate.revision += 1
    candidate.updated_at = utc_now()
    session.flush()
    return {
        "plan": plan,
        "status": "APPLIED",
        "canonical_ref": canonical_ref,
        "candidate": candidate_data(candidate),
    }


__all__ = [
    "apply_one_candidate",
    "bind_candidates_to_workspace",
    "candidate_data",
    "list_candidates",
    "persist_scan_candidates",
    "preview_candidate",
    "review_candidate",
]
