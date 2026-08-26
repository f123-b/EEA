"""M22 existing-project import API.

The router exposes the five wizard states as durable API data.  The scan path
never invokes imported build/test/install scripts and all materialized bytes
live below the configured EEA data directory.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, cast
from uuid import UUID, uuid4

from eea_adapters.source import FileSystemSourceWorkspaceAdapter, GitCliWorkspaceAdapter
from eea_application.dependency_graph import DependencyGraphService
from eea_application.project_import import (
    ImportReviewAction,
    ImportSourceType,
    ImportStatus,
    apply_review_action,
    copy_materialized_tree,
    materialize_import,
    scan_import,
)
from eea_application.projects import ProjectService
from eea_application.source_workspace import SourceWorkspaceService
from eea_core.entities import utc_now
from eea_core.enums import (
    DependencyKind,
    EngineeringErrorCode,
    InvalidationPolicy,
)
from eea_core.errors import EngineeringError
from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from eea_backend.dependency_providers import build_dependency_provider_registry
from eea_backend.dependency_repositories import SqlAlchemyDependencyGraphRepository
from eea_backend.m22_candidates import (
    apply_one_candidate,
    bind_candidates_to_workspace,
    candidate_data,
    list_candidates,
    persist_scan_candidates,
    preview_candidate,
    review_candidate,
)
from eea_backend.models import (
    ArtifactRecord,
    BuildRunRecord,
    CircuitRecord,
    FirmwareRecord,
    GeneratedProtocolOutputRecord,
    HardwareIRRecord,
    ImportCandidateRecord,
    ImportConflictRecord,
    ImportSessionRecord,
    MCUConfigRecord,
    ProtocolRecord,
    ReviewRunRecord,
    SchematicArtifactRecord,
    SourceWorkspaceRecord,
    TestIRRecord,
    TestRunRecord,
)
from eea_backend.repositories import SqlAlchemyProjectRepository
from eea_backend.schemas import ApiEnvelope
from eea_backend.security import authenticated_principal
from eea_backend.source_repositories import SqlAlchemySourceRepository

router = APIRouter()


def _request_id(request: Request) -> str:
    return str(request.state.request_id)


def _session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


SessionDependency = Annotated[Session, Depends(_session)]


def _record(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _finding_key(item: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(item.get("category", "")),
        str(item.get("title", "")),
        str(item.get("source_path", item.get("path", ""))),
    )


def _candidate_key(item: dict[str, object]) -> str:
    semantic_key = str(item.get("semantic_key", "UNKNOWN"))
    source_file = str(item.get("source_file", "UNKNOWN"))
    if semantic_key.startswith(f"{source_file}::"):
        return semantic_key
    return f"{source_file}::{semantic_key}"


def _candidate_evidence(item: dict[str, object]) -> object:
    evidence = item.get("evidence")
    if isinstance(evidence, list):
        return evidence
    return {
        "source_file": item.get("source_file"),
        "source_location": item.get("source_location", {}),
    }


def _candidate_buckets(
    previous_candidates: list[dict[str, object]],
    next_candidates: list[dict[str, object]],
    previous_manifest: dict[str, str],
    next_manifest: dict[str, str],
) -> dict[str, list[dict[str, object]]]:
    old = {_candidate_key(item): item for item in previous_candidates}
    new = {_candidate_key(item): item for item in next_candidates}
    buckets: dict[str, list[dict[str, object]]] = {
        "added": [],
        "modified": [],
        "removed": [],
        "unchanged": [],
    }
    for key in sorted(set(old) | set(new)):
        before, after = old.get(key), new.get(key)
        if before is None:
            bucket = "added"
        elif after is None:
            bucket = "removed"
        elif before.get("proposed_value") != after.get("proposed_value"):
            bucket = "modified"
        else:
            bucket = "unchanged"
        current = after or before or {}
        buckets[bucket].append(
            {
                "semantic_key": key,
                "before": before,
                "after": after,
                "source_evidence": _candidate_evidence(current),
            }
        )
    for path in sorted(set(previous_manifest) | set(next_manifest)):
        before_hash, after_hash = previous_manifest.get(path), next_manifest.get(path)
        if before_hash is None:
            bucket = "added"
        elif after_hash is None:
            bucket = "removed"
        elif before_hash != after_hash:
            bucket = "modified"
        else:
            bucket = "unchanged"
        buckets[bucket].append(
            {
                "semantic_key": f"file:{path}",
                "before": {"hash": before_hash} if before_hash else None,
                "after": {"hash": after_hash} if after_hash else None,
                "source_evidence": {"source_file": path},
            }
        )
    return buckets


def _rescan_diff(
    previous_findings: list[dict[str, object]],
    next_findings: list[dict[str, object]],
    previous_manifest: dict[str, str],
    next_manifest: dict[str, str],
    previous_candidates: list[dict[str, object]] | None = None,
    next_candidates: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Compare immutable scan projections without mutating old SourceRevision data."""

    old = {_finding_key(item): item for item in previous_findings}
    new = {_finding_key(item): item for item in next_findings}
    changes: list[dict[str, object]] = []
    for key in sorted(set(old) | set(new)):
        before, after = old.get(key), new.get(key)
        if before is None:
            kind = "ADDED"
        elif after is None:
            kind = "REMOVED"
        elif before != after:
            kind = "MODIFIED"
        else:
            kind = "UNCHANGED"
        changes.append(
            {
                "kind": kind,
                "finding_id": (after or before or {}).get("id"),
                "finding": after or before,
                "previous": before,
            }
        )
    for path in sorted(set(previous_manifest) | set(next_manifest)):
        before_hash, after_hash = previous_manifest.get(path), next_manifest.get(path)
        if before_hash == after_hash:
            continue
        changes.append(
            {
                "kind": "ADDED"
                if before_hash is None
                else "REMOVED"
                if after_hash is None
                else "MODIFIED",
                "file": path,
                "previous_hash": before_hash,
                "hash": after_hash,
            }
        )
    buckets = _candidate_buckets(
        previous_candidates or [],
        next_candidates or [],
        previous_manifest,
        next_manifest,
    )
    return {
        "changes": changes,
        "added": buckets["added"],
        "modified": buckets["modified"],
        "removed": buckets["removed"],
        "unchanged": buckets["unchanged"],
        "summary": {
            "ADDED": sum(item["kind"] == "ADDED" for item in changes),
            "MODIFIED": sum(item["kind"] == "MODIFIED" for item in changes),
            "REMOVED": sum(item["kind"] == "REMOVED" for item in changes),
            "UNCHANGED": sum(item["kind"] == "UNCHANGED" for item in changes),
            "CANDIDATES_ADDED": len(buckets["added"]),
            "CANDIDATES_MODIFIED": len(buckets["modified"]),
            "CANDIDATES_REMOVED": len(buckets["removed"]),
            "CANDIDATES_UNCHANGED": len(buckets["unchanged"]),
        },
        "affected_artifact_ids": [
            str(item["finding_id"])
            for item in changes
            if item.get("finding_id") and item["kind"] != "UNCHANGED"
        ],
    }


def _current_source_revision_id(session: Session, project_id: UUID | None) -> UUID | None:
    if project_id is None:
        return None
    value = session.scalar(
        select(SourceWorkspaceRecord.current_source_revision_id).where(
            SourceWorkspaceRecord.project_id == str(project_id)
        )
    )
    return UUID(value) if value else None


def _dependency_impact(
    session: Session,
    project_id: UUID | None,
    source_revision_id: UUID | None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "changed": [],
        "affected": [],
        "stale": [],
        "blocked": [],
    }
    if project_id is None or source_revision_id is None:
        return result
    graph = DependencyGraphService(
        SqlAlchemyDependencyGraphRepository(session),
        build_dependency_provider_registry(session),
    )
    downstream_types: tuple[tuple[str, type[Any]], ...] = (
        ("Artifact", ArtifactRecord),
        ("HardwareIR", HardwareIRRecord),
        ("CircuitIR", CircuitRecord),
        ("SchematicIR", SchematicArtifactRecord),
        ("MCUConfigIR", MCUConfigRecord),
        ("FirmwareIR", FirmwareRecord),
        ("ProtocolIR", ProtocolRecord),
        ("GeneratedProtocolOutput", GeneratedProtocolOutputRecord),
        ("TestIR", TestIRRecord),
        ("TestRun", TestRunRecord),
        ("ReviewRun", ReviewRunRecord),
        ("BuildRun", BuildRunRecord),
    )
    for entity_type, record_type in downstream_types:
        for record in session.scalars(
            select(record_type).where(record_type.project_id == str(project_id))
        ):
            if getattr(record, "status", "CURRENT") in {
                "STALE",
                "INVALID",
                "REJECTED",
                "ARCHIVED",
                "DEPRECATED",
                "SUPERSEDED",
            }:
                continue
            try:
                graph.bind(
                    project_id,
                    upstream_type="SourceRevision",
                    upstream_id=str(source_revision_id),
                    downstream_type=entity_type,
                    downstream_id=str(record.id),
                    dependency_kind=DependencyKind.INPUT,
                    required=True,
                    invalidation_policy=(
                        InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID
                    ),
                    reason="M22R import rescan source revision",
                    commit=False,
                )
            except EngineeringError:
                continue
    try:
        plan = graph.impact_analysis(
            project_id,
            "SourceRevision",
            str(source_revision_id),
        )
    except EngineeringError as error:
        result["error"] = error.message
        return result
    serialized_impacts = [item.model_dump(mode="json") for item in plan.impacts]
    result["changed"] = [plan.source.model_dump(mode="json")]
    result["affected"] = serialized_impacts
    result["stale"] = [
        item for item in serialized_impacts if item.get("projected_status") == "STALE"
    ]
    result["blocked"] = [
        item for item in serialized_impacts if item.get("projected_status") == "INVALID"
    ]
    result["plan"] = plan.model_dump(mode="json")
    return result


class ImportCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: ImportSourceType
    source_path: str | None = Field(default=None, max_length=2000)
    repository_url: str | None = Field(default=None, max_length=2000)
    branch_tag_commit: str | None = Field(default=None, max_length=300)
    project_name: str | None = Field(default=None, min_length=1, max_length=200)
    project_description: str = Field(default="", max_length=4000)
    actor: str = Field(default="desktop:m22", min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_locator(self) -> ImportCreateRequest:
        if self.source_type is ImportSourceType.GIT_REPOSITORY:
            if not self.repository_url:
                raise ValueError("repository_url is required for Git imports")
            if self.source_path:
                raise ValueError("source_path is not used for Git imports")
        elif not self.source_path:
            raise ValueError("source_path is required for local folder and archive imports")
        elif self.repository_url:
            raise ValueError("repository_url is only used for Git imports")
        return self


class ImportReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ImportReviewAction
    value: object | None = None
    note: str | None = Field(default=None, max_length=2000)


class ImportReviewBulkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: dict[str, ImportReviewRequest]


class ImportWorkspaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_name: str | None = Field(default=None, min_length=1, max_length=200)
    project_description: str = Field(default="", max_length=4000)


class CandidateReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    action: ImportReviewAction
    value: dict[str, object] | None = None
    note: str | None = Field(default=None, max_length=2000)


class CandidateApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_ids: list[UUID] = Field(min_length=1, max_length=500)
    expected_revisions: dict[str, int]


def _not_found(import_id: UUID) -> EngineeringError:
    return EngineeringError(
        EngineeringErrorCode.VALIDATION_ERROR,
        "Import session was not found",
        details={"import_id": str(import_id)},
    )


def _get_import(session: Session, import_id: UUID) -> ImportSessionRecord:
    row = session.get(ImportSessionRecord, str(import_id))
    if row is None:
        raise _not_found(import_id)
    return row


def _as_data(row: ImportSessionRecord, session: Session | None = None) -> dict[str, object]:
    scan = _record(row.scan_result)
    normalized_candidates = (
        list_candidates(session, UUID(row.id))
        if session is not None
        else _list(scan.get("normalized_candidates"))
    )
    return {
        "id": row.id,
        "schema_version": row.schema_version,
        "revision": row.revision,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "status": row.status,
        "project_id": row.project_id,
        "source_type": row.source_type,
        "source_locator": dict(row.source_locator),
        "requested_ref": row.requested_ref,
        "resolved_commit": row.resolved_commit,
        "staging_path": row.staging_path,
        "workspace_path": row.workspace_path,
        "scan_revision": row.scan_revision,
        "source_manifest_hash": row.source_manifest_hash,
        "file_manifest": dict(row.file_manifest),
        "findings": list(row.findings),
        "issues": list(row.issues),
        "summary": dict(row.summary),
        "candidates": _record(scan.get("candidates")),
        "normalized_candidates": normalized_candidates,
        "parser_stages": _list(scan.get("parser_stages")),
        "classifications": _record(scan.get("classifications")),
        "modules": _list(scan.get("modules")),
        "dependency_edges": _list(scan.get("dependency_edges")),
        "stages": _list(scan.get("stages")),
        "unknown_count": scan.get("unknown_count", 0),
        "build_executed": bool(scan.get("build_executed", False)),
        "created_by": row.created_by,
        "last_scanned_at": row.last_scanned_at.isoformat() if row.last_scanned_at else None,
    }


def _locator(payload: ImportCreateRequest) -> dict[str, str]:
    if payload.source_type is ImportSourceType.GIT_REPOSITORY:
        assert payload.repository_url is not None
        return {"url": payload.repository_url}
    assert payload.source_path is not None
    return {"path": payload.source_path}


def _staging_path(request: Request, import_id: UUID, scan_revision: int) -> Path:
    data_dir = cast(Path, request.app.state.settings.data_dir)
    root = (data_dir / "imports" / str(import_id)).resolve()
    allowed = data_dir.resolve()
    try:
        root.relative_to(allowed)
    except ValueError as exc:
        raise EngineeringError(
            EngineeringErrorCode.SANDBOX_VIOLATION,
            "Import staging path escapes the EEA data directory",
        ) from exc
    return root / f"scan-{scan_revision}"


def _save_scan(
    row: ImportSessionRecord,
    result: dict[str, object],
    *,
    resolved_commit: str | None,
    staging_path: Path,
) -> None:
    row.revision += 1
    row.updated_at = utc_now()
    row.status = ImportStatus.SCANNED.value
    row.scan_revision = cast(int, result["scan_revision"])
    row.resolved_commit = resolved_commit
    row.staging_path = str(staging_path)
    row.source_manifest_hash = str(result["source_manifest_hash"])
    row.file_manifest = cast(dict[str, str], result["file_manifest"])
    row.findings = cast(list[dict[str, object]], result["findings"])
    row.issues = cast(list[dict[str, object]], result["issues"])
    row.summary = cast(dict[str, object], result["summary"])
    row.scan_result = result
    row.last_scanned_at = datetime.now(UTC)


@router.post(
    "/imports",
    response_model=ApiEnvelope[dict[str, object]],
    status_code=status.HTTP_201_CREATED,
    tags=["imports"],
)
def create_import(
    payload: ImportCreateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[dict[str, object]]:
    import_id = uuid4()
    staging = _staging_path(request, import_id, 1)
    now = utc_now()
    row = ImportSessionRecord(
        id=str(import_id),
        schema_version="1.0",
        revision=1,
        created_at=now,
        updated_at=now,
        entity_metadata={"m22": True, "build_executed": False},
        source_type=payload.source_type.value,
        source_locator=_locator(payload),
        requested_ref=payload.branch_tag_commit,
        staging_path=str(staging),
        status=ImportStatus.CREATED.value,
        scan_revision=0,
        file_manifest={},
        findings=[],
        issues=[],
        summary={},
        scan_result={"stages": [], "build_executed": False},
        created_by=payload.actor,
    )
    session.add(row)
    session.commit()
    return ApiEnvelope(data=_as_data(row, session), request_id=_request_id(request))


@router.get(
    "/imports/{import_id}",
    response_model=ApiEnvelope[dict[str, object]],
    tags=["imports"],
)
def get_import(
    import_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[dict[str, object]]:
    return ApiEnvelope(
        data=_as_data(_get_import(session, import_id), session), request_id=_request_id(request)
    )


@router.post(
    "/imports/{import_id}/scan",
    response_model=ApiEnvelope[dict[str, object]],
    tags=["imports"],
)
def scan_existing_import(
    import_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[dict[str, object]]:
    row = _get_import(session, import_id)
    scan_revision = row.scan_revision + 1
    staging = _staging_path(request, import_id, scan_revision)
    materialized = materialize_import(
        ImportSourceType(row.source_type),
        row.source_locator,
        staging,
        requested_ref=row.requested_ref,
    )
    result = scan_import(
        materialized.root,
        session_id=import_id,
        source_type=ImportSourceType(row.source_type),
        resolved_commit=materialized.resolved_commit,
        scan_revision=scan_revision,
    )
    result["normalized_candidates"] = persist_scan_candidates(
        session,
        import_id=import_id,
        project_id=UUID(row.project_id) if row.project_id else None,
        scan_revision=scan_revision,
        file_manifest=cast(dict[str, str], result["file_manifest"]),
        candidates=cast(list[dict[str, object]], result.get("normalized_candidates", [])),
        actor_id=authenticated_principal(request).actor_id,
    )
    _save_scan(row, result, resolved_commit=materialized.resolved_commit, staging_path=staging)
    session.commit()
    return ApiEnvelope(data=_as_data(row, session), request_id=_request_id(request))


@router.patch(
    "/imports/{import_id}/findings/{finding_id}",
    response_model=ApiEnvelope[dict[str, object]],
    tags=["imports"],
)
def review_import_finding(
    import_id: UUID,
    finding_id: str,
    payload: ImportReviewRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[dict[str, object]]:
    row = _get_import(session, import_id)
    row.findings = apply_review_action(
        list(row.findings),
        finding_id,
        payload.action,
        value=payload.value,
        note=payload.note,
    )
    row.revision += 1
    row.updated_at = utc_now()
    row.status = ImportStatus.REVIEWED.value
    session.commit()
    return ApiEnvelope(data=_as_data(row, session), request_id=_request_id(request))


@router.post(
    "/imports/{import_id}/review",
    response_model=ApiEnvelope[dict[str, object]],
    tags=["imports"],
)
def review_import(
    import_id: UUID,
    payload: ImportReviewBulkRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[dict[str, object]]:
    row = _get_import(session, import_id)
    findings = list(row.findings)
    for finding_id, decision in payload.decisions.items():
        findings = apply_review_action(
            findings,
            finding_id,
            decision.action,
            value=decision.value,
            note=decision.note,
        )
    row.findings = findings
    row.revision += 1
    row.updated_at = utc_now()
    row.status = ImportStatus.REVIEWED.value
    session.commit()
    return ApiEnvelope(data=_as_data(row, session), request_id=_request_id(request))


def _get_candidate(
    session: Session,
    row: ImportSessionRecord,
    candidate_id: UUID,
) -> ImportCandidateRecord:
    candidate = session.scalar(
        select(ImportCandidateRecord).where(
            ImportCandidateRecord.id == str(candidate_id),
            ImportCandidateRecord.import_id == row.id,
        )
    )
    if candidate is None:
        raise EngineeringError(
            EngineeringErrorCode.VALIDATION_ERROR,
            "Import candidate was not found",
            details={"candidate_id": str(candidate_id)},
        )
    if row.project_id and candidate.project_id not in {None, row.project_id}:
        raise EngineeringError(
            EngineeringErrorCode.VALIDATION_ERROR,
            "Import candidate is outside the import project scope",
            details={"candidate_id": str(candidate_id)},
        )
    return candidate


@router.get(
    "/imports/{import_id}/candidates",
    response_model=ApiEnvelope[list[dict[str, object]]],
    tags=["imports"],
)
def get_import_candidates(
    import_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[list[dict[str, object]]]:
    row = _get_import(session, import_id)
    candidates = [
        candidate
        for candidate in session.scalars(
            select(ImportCandidateRecord).where(ImportCandidateRecord.import_id == row.id)
        )
        if row.project_id is None or candidate.project_id in {None, row.project_id}
    ]
    return ApiEnvelope(
        data=[candidate_data(candidate) for candidate in candidates],
        request_id=_request_id(request),
    )


@router.patch(
    "/imports/{import_id}/candidates/{candidate_id}",
    response_model=ApiEnvelope[dict[str, object]],
    tags=["imports"],
)
def review_import_candidate(
    import_id: UUID,
    candidate_id: UUID,
    payload: CandidateReviewRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[dict[str, object]]:
    row = _get_import(session, import_id)
    _get_candidate(session, row, candidate_id)
    reviewed = review_candidate(
        session,
        import_id=import_id,
        candidate_id=candidate_id,
        expected_revision=payload.expected_revision,
        action=payload.action.value,
        actor_id=authenticated_principal(request).actor_id,
        value=payload.value,
        note=payload.note,
    )
    row.status = ImportStatus.REVIEWED.value
    row.revision += 1
    row.updated_at = utc_now()
    session.commit()
    return ApiEnvelope(data=candidate_data(reviewed), request_id=_request_id(request))


@router.post(
    "/imports/{import_id}/candidates/apply/preview",
    response_model=ApiEnvelope[list[dict[str, object]]],
    tags=["imports"],
)
def preview_import_candidates(
    import_id: UUID,
    payload: CandidateApplyRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[list[dict[str, object]]]:
    row = _get_import(session, import_id)
    current_source_revision_id = _current_source_revision_id(
        session,
        UUID(row.project_id) if row.project_id else None,
    )
    previews: list[dict[str, object]] = []
    for candidate_id in payload.candidate_ids:
        candidate = _get_candidate(session, row, candidate_id)
        expected = payload.expected_revisions.get(str(candidate_id))
        if expected is None or expected != candidate.revision:
            raise EngineeringError(
                EngineeringErrorCode.REVISION_CONFLICT,
                "Import candidate revision does not match",
                details={"candidate_id": str(candidate_id)},
            )
        previews.append(
            preview_candidate(
                session,
                candidate,
                current_source_revision_id=current_source_revision_id,
            )
        )
    return ApiEnvelope(data=previews, request_id=_request_id(request))


@router.post(
    "/imports/{import_id}/candidates/apply",
    response_model=ApiEnvelope[dict[str, object]],
    tags=["imports"],
)
def apply_import_candidates(
    import_id: UUID,
    payload: CandidateApplyRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[dict[str, object]]:
    row = _get_import(session, import_id)
    if row.project_id is None:
        raise EngineeringError(
            EngineeringErrorCode.VALIDATION_ERROR,
            "Create a workspace before applying import candidates",
        )
    current_source_revision_id = _current_source_revision_id(session, UUID(row.project_id))
    results: list[dict[str, object]] = []
    for candidate_id in payload.candidate_ids:
        candidate = _get_candidate(session, row, candidate_id)
        expected = payload.expected_revisions.get(str(candidate_id))
        if expected is None:
            raise EngineeringError(
                EngineeringErrorCode.REVISION_CONFLICT,
                "Expected revision is required for every candidate",
                details={"candidate_id": str(candidate_id)},
            )
        results.append(
            apply_one_candidate(
                session,
                candidate=candidate,
                expected_revision=expected,
                current_source_revision_id=current_source_revision_id,
            )
        )
    row.status = ImportStatus.REVIEWED.value
    row.revision += 1
    row.updated_at = utc_now()
    session.commit()
    conflicts = [
        {
            "id": conflict.id,
            "candidate_id": conflict.candidate_id,
            "canonical_ref": conflict.canonical_ref,
            "status": conflict.status,
            "reason": conflict.reason,
        }
        for conflict in session.scalars(
            select(ImportConflictRecord).where(
                ImportConflictRecord.import_id == row.id,
                ImportConflictRecord.status == "OPEN",
            )
        )
    ]
    return ApiEnvelope(
        data={"results": results, "conflicts": conflicts},
        request_id=_request_id(request),
    )


def _workspace_root(request: Request, project_id: UUID) -> Path:
    data_dir = cast(Path, request.app.state.settings.data_dir)
    root = (data_dir / "projects" / str(project_id) / "workspace").resolve()
    allowed = (data_dir / "projects").resolve()
    try:
        root.relative_to(allowed)
    except ValueError as exc:
        raise EngineeringError(
            EngineeringErrorCode.SANDBOX_VIOLATION,
            "Project workspace path escapes the EEA data directory",
        ) from exc
    return root


def _remove_tree(path: Path) -> None:
    """Remove imported workspace content even when Git objects are read-only."""

    for candidate in path.rglob("*"):
        with suppress(OSError):
            os.chmod(candidate, stat.S_IWRITE | stat.S_IREAD)
    import shutil

    shutil.rmtree(path)


def _create_workspace_for_import(
    row: ImportSessionRecord,
    request: Request,
    session: Session,
    *,
    project_name: str | None,
    project_description: str,
) -> dict[str, object]:
    if row.scan_revision < 1:
        raise EngineeringError(
            EngineeringErrorCode.VALIDATION_ERROR,
            "Import must be scanned before creating a workspace",
        )
    project_service = ProjectService(SqlAlchemyProjectRepository(session))
    title = project_name or Path(row.source_locator.get("path", "")).stem or "Imported Project"
    project = project_service.create(
        name=title,
        description=project_description,
        metadata={
            "import": {
                "import_session_id": row.id,
                "source_type": row.source_type,
                "resolved_commit": row.resolved_commit,
                "source_manifest_hash": row.source_manifest_hash,
                "candidate_only": True,
            }
        },
        commit=False,
    )
    workspace_root = _workspace_root(request, project.id)
    if workspace_root.exists() and any(workspace_root.iterdir()):
        raise EngineeringError(
            EngineeringErrorCode.SANDBOX_VIOLATION,
            "Project workspace is not empty",
            details={"path": str(workspace_root)},
        )
    copy_materialized_tree(
        Path(row.staging_path),
        workspace_root,
        preserve_git=row.source_type == ImportSourceType.GIT_REPOSITORY.value,
    )
    workspace = FileSystemSourceWorkspaceAdapter(workspace_root)
    source_service = SourceWorkspaceService(
        project.id,
        SqlAlchemySourceRepository(session),
        workspace,
        git=GitCliWorkspaceAdapter(workspace_root),
    )
    source_revision = source_service.reconcile(created_by="eea:m22-import")
    import_metadata = cast(dict[str, object], project.metadata["import"])
    import_metadata["source_revision_id"] = str(source_revision.id)
    import_metadata["file_count"] = len(source_revision.file_manifest)
    import_metadata["issues"] = len(row.issues)
    import_metadata["unknown_count"] = cast(int, row.scan_result.get("unknown_count", 0))
    bind_candidates_to_workspace(
        session,
        import_id=UUID(row.id),
        project_id=project.id,
        source_revision_id=source_revision.id,
        scan_revision=row.scan_revision,
    )
    row.summary = {**row.summary, "source_revision_id": str(source_revision.id)}
    row.project_id = str(project.id)
    row.workspace_path = str(workspace_root)
    row.status = ImportStatus.WORKSPACE_CREATED.value
    row.revision += 1
    row.updated_at = utc_now()
    session.commit()
    return {
        "project": project.model_dump(mode="json"),
        "source_revision": source_revision.model_dump(mode="json"),
        "import": _as_data(row, session),
    }


@router.post(
    "/imports/{import_id}/create-workspace",
    response_model=ApiEnvelope[dict[str, object]],
    status_code=status.HTTP_201_CREATED,
    tags=["imports"],
)
def create_import_workspace(
    import_id: UUID,
    request: Request,
    session: SessionDependency,
    payload: ImportWorkspaceRequest | None = None,
) -> ApiEnvelope[dict[str, object]]:
    row = _get_import(session, import_id)
    data = _create_workspace_for_import(
        row,
        request,
        session,
        project_name=payload.project_name if payload else None,
        project_description=payload.project_description if payload else "",
    )
    return ApiEnvelope(data=data, request_id=_request_id(request))


@router.post(
    "/imports/{import_id}/rescan",
    response_model=ApiEnvelope[dict[str, object]],
    tags=["imports"],
)
def rescan_import(
    import_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[dict[str, object]]:
    row = _get_import(session, import_id)
    previous_findings = list(row.findings)
    previous_manifest = dict(row.file_manifest)
    previous_candidates = [
        candidate_data(record)
        for record in session.scalars(
            select(ImportCandidateRecord).where(
                ImportCandidateRecord.import_id == str(import_id),
                ImportCandidateRecord.source_scan_revision == row.scan_revision,
            )
        )
    ]
    previous_project_id = UUID(row.project_id) if row.project_id else None
    next_revision = row.scan_revision + 1
    staging = _staging_path(request, import_id, next_revision)
    materialized = materialize_import(
        ImportSourceType(row.source_type),
        row.source_locator,
        staging,
        requested_ref=row.requested_ref,
    )
    result = scan_import(
        materialized.root,
        session_id=import_id,
        source_type=ImportSourceType(row.source_type),
        resolved_commit=materialized.resolved_commit,
        scan_revision=next_revision,
    )
    next_candidates = persist_scan_candidates(
        session,
        import_id=import_id,
        project_id=previous_project_id,
        scan_revision=next_revision,
        file_manifest=cast(dict[str, str], result["file_manifest"]),
        candidates=cast(list[dict[str, object]], result.get("normalized_candidates", [])),
        actor_id=authenticated_principal(request).actor_id,
    )
    result["normalized_candidates"] = next_candidates
    diff = _rescan_diff(
        previous_findings,
        cast(list[dict[str, object]], result["findings"]),
        previous_manifest,
        cast(dict[str, str], result["file_manifest"]),
        previous_candidates,
        next_candidates,
    )
    result["rescan_diff"] = diff
    _save_scan(row, result, resolved_commit=materialized.resolved_commit, staging_path=staging)
    source_revision_data: dict[str, object] | None = None
    if previous_project_id is not None and row.workspace_path:
        workspace_root = Path(row.workspace_path).resolve()
        expected_root = _workspace_root(request, previous_project_id)
        if workspace_root != expected_root:
            raise EngineeringError(
                EngineeringErrorCode.SANDBOX_VIOLATION,
                "Stored project workspace is outside its project boundary",
            )
        for child in workspace_root.iterdir() if workspace_root.exists() else ():
            if child.name == ".eea":
                continue
            if child.is_dir() and not child.is_symlink():
                _remove_tree(child)
            else:
                child.unlink(missing_ok=True)
        copy_materialized_tree(
            materialized.root,
            workspace_root,
            preserve_git=row.source_type == ImportSourceType.GIT_REPOSITORY.value,
        )
        source_service = SourceWorkspaceService(
            previous_project_id,
            SqlAlchemySourceRepository(session),
            FileSystemSourceWorkspaceAdapter(workspace_root),
            git=GitCliWorkspaceAdapter(workspace_root),
        )
        source_revision = source_service.reconcile(
            created_by="eea:m22-rescan",
            force_new_revision=True,
        )
        source_revision_data = source_revision.model_dump(mode="json")
        bind_candidates_to_workspace(
            session,
            import_id=import_id,
            project_id=previous_project_id,
            source_revision_id=source_revision.id,
            scan_revision=next_revision,
        )
        diff["dependency_impact"] = _dependency_impact(
            session,
            previous_project_id,
            source_revision.id,
        )
    else:
        diff["dependency_impact"] = _dependency_impact(
            session,
            previous_project_id,
            None,
        )
    session.commit()
    return ApiEnvelope(
        data={
            "import": _as_data(row, session),
            "source_revision": source_revision_data,
            "rescan_diff": diff,
        },
        request_id=_request_id(request),
    )


__all__ = ["router"]
