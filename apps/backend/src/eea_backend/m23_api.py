"""M23 Knowledge & Memory API.

Memory entries are intentionally a projection over canonical Claims, Evidence,
and SourceRevision records.  The API never accepts lifecycle or trust as user
input; those fields move only through explicit review transitions.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Literal, cast
from uuid import UUID

from eea_application.knowledge_memory import (
    KnowledgeMemoryService,
    RecallContext,
    claim_memory_state,
)
from eea_core.entities import Evidence, KnowledgeEntry, utc_now
from eea_core.enums import (
    AuthorityLevel,
    EngineeringErrorCode,
    EvidenceType,
    KnowledgeLifecycle,
    KnowledgeScope,
    KnowledgeType,
    TrustLevel,
    VerificationLevel,
)
from eea_core.errors import EngineeringError
from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from eea_backend.knowledge_repositories import (
    SqlAlchemyKnowledgeEntryRepository,
    SqlAlchemyKnowledgeRecallAuditRepository,
)
from eea_backend.models import (
    ClaimConflictRecord,
    EngineeringClaimRecord,
    EvidenceRecord,
    ImportSessionRecord,
    KnowledgeEntryRecord,
    ProjectRecord,
    SourceRevisionRecord,
)
from eea_backend.repositories import SqlAlchemyEvidenceRepository
from eea_backend.schemas import ApiEnvelope

router = APIRouter()


def _request_id(request: Request) -> str:
    return str(request.state.request_id)


def _session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


SessionDependency = Annotated[Session, Depends(_session)]


class MemoryEntryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID | None = None
    scope: KnowledgeScope = KnowledgeScope.PROJECT_PRIVATE
    owner_ref: str | None = Field(default=None, max_length=200)
    organization_ref: str | None = Field(default=None, max_length=200)
    task_ref: str | None = Field(default=None, max_length=200)
    knowledge_type: KnowledgeType
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(default="", max_length=12000)
    tags: list[str] = Field(default_factory=list, max_length=50)
    applicability: dict[str, object] = Field(default_factory=dict)
    claim_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    source_revision_id: UUID | None = None
    source_ref: str | None = Field(default=None, max_length=2000)
    source_version: str | None = Field(default=None, max_length=200)
    authority_level: AuthorityLevel = AuthorityLevel.T6_AI_INFERENCE
    verification_levels: list[VerificationLevel] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)
    freshness_score: float = Field(default=1, ge=0, le=1)
    license_ref: str | None = Field(default=None, max_length=500)
    usage_policy: str | None = Field(default=None, max_length=2000)
    related_entry_ids: list[UUID] = Field(default_factory=list)
    actor_ref: str = Field(default="desktop:m23", min_length=1, max_length=200)


class MemoryRecallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    actor_ref: str = Field(default="desktop:m23", min_length=1, max_length=200)
    scope_context: list[KnowledgeScope] = Field(
        default_factory=lambda: [KnowledgeScope.GLOBAL_PUBLIC, KnowledgeScope.PROJECT_PRIVATE]
    )
    query: str = Field(default="", max_length=2000)
    limit: int = Field(default=20, ge=1, le=100)
    task_ref: str | None = Field(default=None, max_length=200)
    organization_ref: str | None = Field(default=None, max_length=200)


class MemoryReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    actor_ref: str = Field(default="desktop:m23", min_length=1, max_length=200)
    expected_revision: int = Field(ge=1)
    action: Literal["ACCEPT", "VERIFY", "REJECT", "ARCHIVE", "DEPRECATE", "RESOLVE_CONFLICT"]
    verification_level: VerificationLevel | None = None
    note: str | None = Field(default=None, max_length=2000)
    task_ref: str | None = Field(default=None, max_length=200)
    organization_ref: str | None = Field(default=None, max_length=200)


class ImportMemoryEntryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    actor_ref: str = Field(default="desktop:m23", min_length=1, max_length=200)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    summary: str | None = Field(default=None, max_length=12000)
    finding_ids: list[str] = Field(default_factory=list, max_length=100)
    tags: list[str] = Field(default_factory=lambda: ["m22-import"], max_length=50)


def _error(
    message: str,
    *,
    code: EngineeringErrorCode = EngineeringErrorCode.VALIDATION_ERROR,
    **details: object,
) -> EngineeringError:
    return EngineeringError(code, message, details=details)


def _get_entry(session: Session, entry_id: UUID) -> KnowledgeEntry:
    entry = SqlAlchemyKnowledgeEntryRepository(session).get(entry_id)
    if entry is None:
        raise _error("Knowledge entry was not found", entry_id=str(entry_id))
    return entry


def _project_exists(session: Session, project_id: UUID) -> None:
    if (
        session.scalar(
            select(ProjectRecord.id).where(
                ProjectRecord.id == str(project_id), ProjectRecord.deleted_at.is_(None)
            )
        )
        is None
    ):
        raise _error("Project was not found", project_id=str(project_id))


def _as_data(entry: KnowledgeEntry) -> dict[str, object]:
    return cast(dict[str, object], entry.model_dump(mode="json"))


def _context(
    *,
    project_id: UUID,
    actor_ref: str,
    scopes: list[KnowledgeScope] | tuple[KnowledgeScope, ...],
    task_ref: str | None = None,
    organization_ref: str | None = None,
    query: str = "",
    limit: int = 1,
) -> RecallContext:
    return RecallContext(
        project_id=project_id,
        actor_ref=actor_ref,
        scope_context=tuple(scopes),
        query=query,
        limit=limit,
        task_ref=task_ref,
        organization_ref=organization_ref,
    )


def _ensure_visible(
    entry: KnowledgeEntry,
    *,
    project_id: UUID,
    actor_ref: str,
    task_ref: str | None = None,
    organization_ref: str | None = None,
) -> None:
    context = _context(
        project_id=project_id,
        actor_ref=actor_ref,
        scopes=tuple(KnowledgeScope),
        task_ref=task_ref,
        organization_ref=organization_ref,
    )
    if not KnowledgeMemoryService().visible(entry, context):
        raise _error(
            "Knowledge scope is not available to this actor",
            code=EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            entry_id=str(entry.id),
            project_id=str(project_id),
        )


def _validate_references(session: Session, payload: MemoryEntryCreateRequest) -> None:
    project_id = str(payload.project_id) if payload.project_id else None
    if payload.project_id:
        _project_exists(session, payload.project_id)

    if payload.claim_ids:
        records = list(
            session.scalars(
                select(EngineeringClaimRecord).where(
                    EngineeringClaimRecord.id.in_([str(value) for value in payload.claim_ids])
                )
            )
        )
        found = {record.id for record in records}
        missing = [str(value) for value in payload.claim_ids if str(value) not in found]
        if missing:
            raise _error("Knowledge entry references missing claims", missing_claim_ids=missing)
        if any(record.project_id not in {None, project_id} for record in records):
            raise _error("Knowledge entry crosses project claim scope")

    if payload.evidence_ids:
        records = list(
            session.scalars(
                select(EvidenceRecord).where(
                    EvidenceRecord.id.in_([str(value) for value in payload.evidence_ids])
                )
            )
        )
        found = {record.id for record in records}
        missing = [str(value) for value in payload.evidence_ids if str(value) not in found]
        if missing:
            raise _error(
                "Knowledge entry references missing evidence", missing_evidence_ids=missing
            )
        if any(record.project_id not in {None, project_id} for record in records):
            raise _error("Knowledge entry crosses project evidence scope")

    if payload.source_revision_id:
        revision = session.get(SourceRevisionRecord, str(payload.source_revision_id))
        if revision is None or (
            payload.project_id is not None and revision.project_id != str(payload.project_id)
        ):
            raise _error("Knowledge entry source revision is unavailable")

    if payload.related_entry_ids:
        entry_records = list(
            session.scalars(
                select(KnowledgeEntryRecord).where(
                    KnowledgeEntryRecord.id.in_([str(value) for value in payload.related_entry_ids])
                )
            )
        )
        found = {record.id for record in entry_records}
        missing = [str(value) for value in payload.related_entry_ids if str(value) not in found]
        if missing:
            raise _error(
                "Knowledge entry references missing related entries", missing_entry_ids=missing
            )
        if any(record.project_id not in {None, project_id} for record in entry_records):
            raise _error("Knowledge entry crosses related memory scope")


@router.post(
    "/memory/entries",
    response_model=ApiEnvelope[dict[str, object]],
    status_code=status.HTTP_201_CREATED,
    tags=["knowledge-memory"],
)
def create_memory_entry(
    payload: MemoryEntryCreateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[dict[str, object]]:
    _validate_references(session, payload)
    open_conflict = False
    if payload.claim_ids:
        open_conflict = (
            session.scalar(
                select(ClaimConflictRecord.id)
                .where(
                    ClaimConflictRecord.status == "OPEN",
                    or_(
                        ClaimConflictRecord.claim_a_id.in_(
                            [str(value) for value in payload.claim_ids]
                        ),
                        ClaimConflictRecord.claim_b_id.in_(
                            [str(value) for value in payload.claim_ids]
                        ),
                    ),
                )
                .limit(1)
            )
            is not None
        )
    lifecycle, trust = claim_memory_state(open_conflict)
    entry = KnowledgeEntry(
        project_id=payload.project_id,
        scope=payload.scope,
        owner_ref=payload.owner_ref,
        organization_ref=payload.organization_ref,
        task_ref=payload.task_ref,
        knowledge_type=payload.knowledge_type,
        title=payload.title,
        summary=payload.summary,
        tags=payload.tags,
        applicability=payload.applicability,
        claim_ids=payload.claim_ids,
        evidence_ids=payload.evidence_ids,
        source_revision_id=payload.source_revision_id,
        source_ref=payload.source_ref,
        source_version=payload.source_version,
        authority_level=payload.authority_level,
        verification_levels=payload.verification_levels,
        trust_level=trust,
        lifecycle=lifecycle,
        confidence=payload.confidence,
        freshness_score=payload.freshness_score,
        license_ref=payload.license_ref,
        usage_policy=payload.usage_policy,
        related_entry_ids=payload.related_entry_ids,
        created_by=payload.actor_ref,
    )
    stored = SqlAlchemyKnowledgeEntryRepository(session).add(entry)
    return ApiEnvelope(data=_as_data(stored), request_id=_request_id(request))


@router.get(
    "/memory/entries/{entry_id}",
    response_model=ApiEnvelope[dict[str, object]],
    tags=["knowledge-memory"],
)
def get_memory_entry(
    entry_id: UUID,
    project_id: UUID,
    request: Request,
    session: SessionDependency,
    actor_ref: str = Query(default="desktop:m23", min_length=1, max_length=200),
    task_ref: str | None = Query(default=None, max_length=200),
    organization_ref: str | None = Query(default=None, max_length=200),
) -> ApiEnvelope[dict[str, object]]:
    entry = _get_entry(session, entry_id)
    _ensure_visible(
        entry,
        project_id=project_id,
        actor_ref=actor_ref,
        task_ref=task_ref,
        organization_ref=organization_ref,
    )
    return ApiEnvelope(data=_as_data(entry), request_id=_request_id(request))


@router.post(
    "/memory/recall",
    response_model=ApiEnvelope[dict[str, object]],
    tags=["knowledge-memory"],
)
def recall_memory(
    payload: MemoryRecallRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[dict[str, object]]:
    _project_exists(session, payload.project_id)
    context = _context(
        project_id=payload.project_id,
        actor_ref=payload.actor_ref,
        scopes=payload.scope_context,
        task_ref=payload.task_ref,
        organization_ref=payload.organization_ref,
        query=payload.query,
        limit=payload.limit,
    )
    matches = KnowledgeMemoryService().recall(
        SqlAlchemyKnowledgeEntryRepository(session).list_for_recall(), context
    )
    audit_id = SqlAlchemyKnowledgeRecallAuditRepository(session).add(
        project_id=payload.project_id,
        actor_ref=payload.actor_ref,
        query=payload.query,
        scope_context=payload.scope_context,
        result_ids=[match.entry.id for match in matches],
        request_id=_request_id(request),
    )
    return ApiEnvelope(
        data={
            "query": payload.query,
            "scope_context": [value.value for value in payload.scope_context],
            "items": [
                {
                    "entry": _as_data(match.entry),
                    "score": match.score,
                    "matched_tokens": list(match.matched_tokens),
                    "reasons": list(match.reasons),
                }
                for match in matches
            ],
            "audit_id": str(audit_id),
        },
        request_id=_request_id(request),
    )


@router.post(
    "/memory/entries/{entry_id}/review",
    response_model=ApiEnvelope[dict[str, object]],
    tags=["knowledge-memory"],
)
def review_memory_entry(
    entry_id: UUID,
    payload: MemoryReviewRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[dict[str, object]]:
    entry = _get_entry(session, entry_id)
    _ensure_visible(
        entry,
        project_id=payload.project_id,
        actor_ref=payload.actor_ref,
        task_ref=payload.task_ref,
        organization_ref=payload.organization_ref,
    )
    if entry.revision != payload.expected_revision:
        raise _error(
            "Knowledge entry revision changed; reload before reviewing",
            code=EngineeringErrorCode.REVISION_CONFLICT,
            entry_id=str(entry_id),
            expected_revision=payload.expected_revision,
            actual_revision=entry.revision,
        )
    if payload.action == "VERIFY" and payload.verification_level is None:
        raise _error("VERIFY requires verification_level")
    if payload.action == "RESOLVE_CONFLICT" and not payload.note:
        raise _error("RESOLVE_CONFLICT requires a note")
    if (
        payload.action in {"ACCEPT", "VERIFY", "RESOLVE_CONFLICT"}
        and entry.lifecycle is KnowledgeLifecycle.CONFLICTED
    ):
        if payload.action != "RESOLVE_CONFLICT":
            raise _error("Conflicted memory must be explicitly resolved before acceptance")
        open_conflict = session.scalar(
            select(ClaimConflictRecord.id)
            .where(
                ClaimConflictRecord.status == "OPEN",
                or_(
                    ClaimConflictRecord.claim_a_id.in_([str(value) for value in entry.claim_ids]),
                    ClaimConflictRecord.claim_b_id.in_([str(value) for value in entry.claim_ids]),
                ),
            )
            .limit(1)
        )
        if open_conflict is not None:
            raise _error("Claim conflicts remain open; resolve canonical claims first")

    verification_levels = list(entry.verification_levels)
    lifecycle = entry.lifecycle
    trust = entry.trust_level
    confidence = entry.confidence
    last_verified_at = entry.last_verified_at
    if payload.action == "ACCEPT":
        verification_levels.append(VerificationLevel.USER_CONFIRMED)
        lifecycle, trust = KnowledgeLifecycle.ACTIVE, TrustLevel.MEDIUM
        confidence = max(confidence, 0.6)
        last_verified_at = utc_now()
    elif payload.action == "VERIFY":
        assert payload.verification_level is not None
        if payload.verification_level not in verification_levels:
            verification_levels.append(payload.verification_level)
        lifecycle = KnowledgeLifecycle.ACTIVE
        trust = (
            TrustLevel.HIGH
            if payload.verification_level
            in {
                VerificationLevel.DOCUMENT_VERIFIED,
                VerificationLevel.TOOL_VERIFIED,
                VerificationLevel.HARDWARE_VERIFIED,
                VerificationLevel.USER_CONFIRMED,
            }
            else TrustLevel.MEDIUM
        )
        confidence = max(confidence, 0.75 if trust is TrustLevel.HIGH else 0.6)
        last_verified_at = utc_now()
    elif payload.action == "RESOLVE_CONFLICT":
        lifecycle, trust = KnowledgeLifecycle.ACTIVE, TrustLevel.MEDIUM
        confidence = max(confidence, 0.6)
        last_verified_at = utc_now()
    elif payload.action == "REJECT":
        lifecycle = KnowledgeLifecycle.REJECTED
    elif payload.action == "ARCHIVE":
        lifecycle = KnowledgeLifecycle.ARCHIVED
    elif payload.action == "DEPRECATE":
        lifecycle = KnowledgeLifecycle.DEPRECATED

    now = utc_now()
    updated = KnowledgeEntry.model_validate(
        {
            **_as_data(entry),
            "revision": entry.revision + 1,
            "updated_at": now,
            "verification_levels": verification_levels,
            "lifecycle": lifecycle,
            "trust_level": trust,
            "confidence": confidence,
            "last_verified_at": last_verified_at,
            "reviewed_by": payload.actor_ref,
            "reviewed_at": now,
        }
    )
    stored = SqlAlchemyKnowledgeEntryRepository(session).save(
        updated, expected_revision=payload.expected_revision
    )
    if stored is None:
        raise _error(
            "Knowledge entry revision changed; reload before reviewing",
            code=EngineeringErrorCode.REVISION_CONFLICT,
            entry_id=str(entry_id),
        )
    return ApiEnvelope(data=_as_data(stored), request_id=_request_id(request))


def _selected_findings(row: ImportSessionRecord, requested: list[str]) -> list[dict[str, object]]:
    findings = list(row.findings)
    selected = (
        [item for item in findings if item.get("id") in requested]
        if requested
        else [
            item
            for item in findings
            if item.get("review_status") in {"ACCEPTED_CANDIDATE", "EDITED_CANDIDATE"}
        ]
    )
    if requested and len(selected) != len(requested):
        raise _error("One or more import findings were not found")
    if not selected:
        raise _error("At least one accepted import finding is required")
    if any(
        item.get("review_status") not in {"ACCEPTED_CANDIDATE", "EDITED_CANDIDATE"}
        for item in selected
    ):
        raise _error("Only accepted or edited import findings can become memory")
    return selected


@router.post(
    "/imports/{import_id}/memory-entry",
    response_model=ApiEnvelope[dict[str, object]],
    status_code=status.HTTP_201_CREATED,
    tags=["knowledge-memory"],
)
def create_import_memory_entry(
    import_id: UUID,
    payload: ImportMemoryEntryRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[dict[str, object]]:
    row = session.get(ImportSessionRecord, str(import_id))
    if row is None:
        raise _error("Import session was not found", import_id=str(import_id))
    if row.project_id != str(payload.project_id) or row.status != "WORKSPACE_CREATED":
        raise _error("Import workspace must belong to the requested project")
    _project_exists(session, payload.project_id)
    selected = _selected_findings(row, payload.finding_ids)
    finding_ids = [str(item["id"]) for item in selected]
    evidence = Evidence(
        project_id=payload.project_id,
        evidence_type=EvidenceType.IMPORTED_PROJECT,
        locator={"import_session_id": str(import_id), "finding_ids": finding_ids},
        source_uri=f"import://{import_id}",
        content_hash=row.source_manifest_hash,
        summary=f"M22 reviewed findings from import {import_id}",
    )
    evidence = SqlAlchemyEvidenceRepository(session).add(evidence, commit=False)
    summary = payload.summary or "; ".join(
        f"{item.get('title', item.get('category', 'finding'))}: {item.get('value', '')}"
        for item in selected
    )
    source_revision_ref = row.summary.get("source_revision_id")
    entry = KnowledgeEntry(
        project_id=payload.project_id,
        scope=KnowledgeScope.PROJECT_PRIVATE,
        knowledge_type=KnowledgeType.PROJECT_EXPERIENCE,
        title=payload.title or f"Imported project findings ({len(selected)})",
        summary=summary,
        tags=payload.tags,
        applicability={"import_session_id": str(import_id), "finding_ids": finding_ids},
        evidence_ids=[evidence.id],
        source_revision_id=UUID(source_revision_ref)
        if isinstance(source_revision_ref, str)
        else None,
        source_ref=f"import://{import_id}",
        source_version=row.resolved_commit or row.source_manifest_hash,
        authority_level=AuthorityLevel.T4_PROJECT,
        verification_levels=[VerificationLevel.IMPORT_VERIFIED],
        confidence=0.6,
        freshness_score=1.0,
        created_by=payload.actor_ref,
    )
    stored = SqlAlchemyKnowledgeEntryRepository(session).add(entry, commit=False)
    session.commit()
    return ApiEnvelope(
        data={
            "entry": _as_data(stored),
            "evidence_id": str(evidence.id),
            "finding_ids": finding_ids,
        },
        request_id=_request_id(request),
    )


__all__ = ["router"]
