"""M23 Knowledge & Memory API.

Memory entries are intentionally a projection over canonical Claims, Evidence,
and SourceRevision records.  The API never accepts lifecycle or trust as user
input; those fields move only through explicit review transitions.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Literal, cast
from uuid import UUID, uuid4

from eea_application.knowledge_authority import (
    EvidenceContext,
    KnowledgeFreshnessService,
    VerificationAuthorityResolver,
    VerificationDecision,
)
from eea_application.knowledge_memory import (
    KnowledgeMemoryService,
    RecallContext,
    claim_memory_state,
)
from eea_core.entities import Evidence, KnowledgeEntry, utc_now
from eea_core.enums import (
    AuthorityLevel,
    ClaimLifecycle,
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
    DocumentRecord,
    EngineeringClaimRecord,
    EvidenceRecord,
    ImportSessionRecord,
    KnowledgeEntryRecord,
    ProjectRecord,
    SourceRevisionRecord,
    SourceWorkspaceRecord,
)
from eea_backend.repositories import SqlAlchemyEvidenceRepository
from eea_backend.schemas import ApiEnvelope
from eea_backend.security import AuthenticatedPrincipal, authenticated_principal

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
    owner_ref: str | None = Field(
        default=None,
        max_length=200,
        description="Deprecated compatibility field; ignored by backend",
    )
    organization_ref: str | None = Field(
        default=None,
        max_length=200,
        description="Deprecated compatibility field; ignored by backend",
    )
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
    authority_level: AuthorityLevel = Field(
        default=AuthorityLevel.T6_AI_INFERENCE,
        description="Deprecated compatibility field; authority is backend-derived",
    )
    verification_levels: list[VerificationLevel] = Field(
        default_factory=list,
        description="Deprecated compatibility field; verification is backend-derived",
    )
    confidence: float = Field(default=0, ge=0, le=1)
    freshness_score: float = Field(default=1, ge=0, le=1)
    license_ref: str | None = Field(default=None, max_length=500)
    usage_policy: str | None = Field(default=None, max_length=2000)
    related_entry_ids: list[UUID] = Field(default_factory=list)
    actor_ref: str = Field(
        default="desktop:m23",
        min_length=1,
        max_length=200,
        description="Deprecated compatibility field; ignored for authorization",
    )


class MemoryRecallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    actor_ref: str = Field(
        default="desktop:m23",
        min_length=1,
        max_length=200,
        description="Deprecated compatibility field; ignored for authorization",
    )
    scope_context: list[KnowledgeScope] = Field(
        default_factory=lambda: [KnowledgeScope.GLOBAL_PUBLIC, KnowledgeScope.PROJECT_PRIVATE]
    )
    query: str = Field(default="", max_length=2000)
    limit: int = Field(default=20, ge=1, le=100)
    task_ref: str | None = Field(default=None, max_length=200)
    organization_ref: str | None = Field(
        default=None, max_length=200, description="Deprecated compatibility field; ignored"
    )


class MemoryReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    actor_ref: str = Field(
        default="desktop:m23",
        min_length=1,
        max_length=200,
        description="Deprecated compatibility field; ignored for authorization",
    )
    expected_revision: int = Field(ge=1)
    action: Literal["ACCEPT", "VERIFY", "REJECT", "ARCHIVE", "DEPRECATE", "RESOLVE_CONFLICT"]
    verification_level: VerificationLevel | None = Field(
        default=None,
        description="Requested level is only an assertion; backend evidence must authorize it",
    )
    note: str | None = Field(default=None, max_length=2000)
    task_ref: str | None = Field(default=None, max_length=200)
    organization_ref: str | None = Field(
        default=None, max_length=200, description="Deprecated compatibility field; ignored"
    )


class ImportMemoryEntryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    actor_ref: str = Field(
        default="desktop:m23",
        min_length=1,
        max_length=200,
        description="Deprecated compatibility field; ignored for authorization",
    )
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


def _principal(request: Request) -> AuthenticatedPrincipal:
    """Get identity only from the authenticated backend request context."""

    return authenticated_principal(request)


def _current_source_revision_id(session: Session, project_id: UUID) -> UUID | None:
    value = session.scalar(
        select(SourceWorkspaceRecord.current_source_revision_id).where(
            SourceWorkspaceRecord.project_id == str(project_id)
        )
    )
    return UUID(value) if value else None


def _evidence_contexts(session: Session, entry: KnowledgeEntry) -> tuple[EvidenceContext, ...]:
    if not entry.evidence_ids:
        return ()
    records = list(
        session.scalars(
            select(EvidenceRecord).where(
                EvidenceRecord.id.in_([str(value) for value in entry.evidence_ids])
            )
        )
    )
    contexts: list[EvidenceContext] = []
    for record in records:
        locator = dict(record.locator)
        evidence_type = EvidenceType(record.evidence_type)
        if evidence_type is EvidenceType.DOCUMENT:
            document_id = locator.get("document_id")
            document = session.get(DocumentRecord, str(document_id)) if document_id else None
            if (
                document is None
                or document.parse_status != "PARSED"
                or document.project_id not in {None, record.project_id}
                or (
                    locator.get("content_hash") is not None
                    and locator.get("content_hash") != document.content_hash
                )
            ):
                locator["valid"] = False
            else:
                locator["parse_status"] = document.parse_status
        source_revision = locator.get("source_revision_id")
        contexts.append(
            EvidenceContext(
                evidence_id=UUID(record.id),
                project_id=UUID(record.project_id) if record.project_id else None,
                evidence_type=evidence_type,
                locator=locator,
                source_revision_id=UUID(str(source_revision)) if source_revision else None,
            )
        )
    return tuple(contexts)


def _open_conflict(session: Session, claim_ids: list[UUID]) -> bool:
    if not claim_ids:
        return False
    return (
        session.scalar(
            select(ClaimConflictRecord.id)
            .where(
                ClaimConflictRecord.status == "OPEN",
                or_(
                    ClaimConflictRecord.claim_a_id.in_([str(value) for value in claim_ids]),
                    ClaimConflictRecord.claim_b_id.in_([str(value) for value in claim_ids]),
                ),
            )
            .limit(1)
        )
        is not None
    )


def _stale_evidence_ids(
    entry: KnowledgeEntry, contexts: tuple[EvidenceContext, ...]
) -> tuple[UUID, ...]:
    stale: list[UUID] = []
    for evidence in contexts:
        locator = evidence.locator
        if (
            locator.get("valid") is False
            or locator.get("stale") is True
            or str(locator.get("status", "PASS")).upper() in {"STALE", "INVALID"}
            or (
                locator.get("source_revision_id")
                and entry.source_revision_id
                and str(locator["source_revision_id"]) != str(entry.source_revision_id)
            )
        ):
            stale.append(evidence.evidence_id)
    return tuple(stale)


def _reconcile_entry(
    session: Session, entry: KnowledgeEntry
) -> tuple[KnowledgeEntry, str, str | None]:
    contexts = _evidence_contexts(session, entry)
    decision_service = KnowledgeFreshnessService()
    current_source = (
        _current_source_revision_id(session, entry.project_id)
        if entry.project_id is not None
        else None
    )
    loaded_ids = {item.evidence_id for item in contexts}
    stale_ids = _stale_evidence_ids(entry, contexts) + tuple(
        value for value in entry.evidence_ids if value not in loaded_ids
    )
    updated, decision = decision_service.reconcile(
        entry,
        current_source_revision_id=current_source,
        conflict_open=_open_conflict(session, entry.claim_ids),
        stale_evidence_ids=stale_ids,
    )
    if updated.revision != entry.revision:
        saved = SqlAlchemyKnowledgeEntryRepository(session).save(
            updated, expected_revision=entry.revision
        )
        if saved is not None:
            entry = saved
    return entry, decision.status, decision.reason


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
    principal = _principal(request)
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
    owner_ref = principal.user_id if payload.scope is KnowledgeScope.USER_PRIVATE else None
    organization_ref = (
        principal.organization_id if payload.scope is KnowledgeScope.ORGANIZATION_PRIVATE else None
    )
    if payload.scope is KnowledgeScope.ORGANIZATION_PRIVATE and organization_ref is None:
        raise _error(
            "organization-private memory requires an authenticated organization",
            code=EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
        )
    entry = KnowledgeEntry(
        project_id=payload.project_id,
        scope=payload.scope,
        owner_ref=owner_ref,
        organization_ref=organization_ref,
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
        authority_level=AuthorityLevel.T6_AI_INFERENCE,
        verification_levels=[],
        trust_level=trust,
        lifecycle=lifecycle,
        confidence=payload.confidence,
        freshness_score=1.0,
        license_ref=payload.license_ref,
        usage_policy=payload.usage_policy,
        related_entry_ids=payload.related_entry_ids,
        created_by=principal.actor_id,
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
    principal = _principal(request)
    entry = _get_entry(session, entry_id)
    entry, _, _ = _reconcile_entry(session, entry)
    _ensure_visible(
        entry,
        project_id=project_id,
        actor_ref=principal.user_id,
        task_ref=task_ref,
        organization_ref=principal.organization_id,
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
    principal = _principal(request)
    _project_exists(session, payload.project_id)
    entries = []
    freshness: dict[str, tuple[str, str | None]] = {}
    repository = SqlAlchemyKnowledgeEntryRepository(session)
    for candidate in repository.list_for_recall():
        if candidate.project_id not in {None, payload.project_id}:
            continue
        reconciled, freshness_status, stale_reason = _reconcile_entry(session, candidate)
        entries.append(reconciled)
        freshness[str(reconciled.id)] = (freshness_status, stale_reason)
    context = _context(
        project_id=payload.project_id,
        actor_ref=principal.user_id,
        scopes=payload.scope_context,
        task_ref=payload.task_ref,
        organization_ref=principal.organization_id,
        query=payload.query,
        limit=payload.limit,
    )
    matches = KnowledgeMemoryService().recall(entries, context)
    audit_id = SqlAlchemyKnowledgeRecallAuditRepository(session).add(
        project_id=payload.project_id,
        actor_ref=principal.actor_id,
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
                    "freshness_status": freshness.get(str(match.entry.id), ("UNKNOWN", None))[0],
                    "stale_reason": freshness.get(str(match.entry.id), ("UNKNOWN", None))[1],
                    "authority_reason": (
                        "backend authority metadata is enforced"
                        if match.entry.verification_levels
                        else "no verification authority evidence attached"
                    ),
                    "verification_reason": (
                        "; ".join(value.value for value in match.entry.verification_levels)
                        if match.entry.verification_levels
                        else "not verified"
                    ),
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
    principal = _principal(request)
    entry = _get_entry(session, entry_id)
    entry, freshness_status, _ = _reconcile_entry(session, entry)
    _ensure_visible(
        entry,
        project_id=payload.project_id,
        actor_ref=principal.user_id,
        task_ref=payload.task_ref,
        organization_ref=principal.organization_id,
    )
    if entry.revision != payload.expected_revision:
        raise _error(
            "Knowledge entry revision changed; reload before reviewing",
            code=EngineeringErrorCode.REVISION_CONFLICT,
            entry_id=str(entry_id),
            expected_revision=payload.expected_revision,
            actual_revision=entry.revision,
        )
    if payload.action == "RESOLVE_CONFLICT" and not payload.note:
        raise _error("RESOLVE_CONFLICT requires a note")
    if (
        payload.action in {"ACCEPT", "VERIFY", "RESOLVE_CONFLICT"}
        and entry.lifecycle is KnowledgeLifecycle.CONFLICTED
    ):
        if payload.action != "RESOLVE_CONFLICT":
            raise _error("Conflicted memory must be explicitly resolved before acceptance")
        if _open_conflict(session, entry.claim_ids):
            raise _error("Claim conflicts remain open; resolve canonical claims first")

    contexts = _evidence_contexts(session, entry)
    if payload.action in {"ACCEPT", "VERIFY", "RESOLVE_CONFLICT"}:
        authority_decision = VerificationAuthorityResolver().resolve(
            entry,
            cast(Literal["ACCEPT", "VERIFY", "RESOLVE_CONFLICT"], payload.action),
            payload.verification_level,
            contexts,
            current_source_revision_id=(
                _current_source_revision_id(session, entry.project_id)
                if entry.project_id is not None
                else None
            ),
            conflict_open=_open_conflict(session, entry.claim_ids),
        )
    else:
        authority_decision = VerificationDecision(
            allowed=True,
            verification_levels=(),
            trust_level=entry.trust_level,
            authority_level=entry.authority_level,
            evidence_ids=(),
            reason="lifecycle action does not grant verification authority",
        )
    if not authority_decision.allowed:
        raise _error(
            "Knowledge verification is not authorized by backend evidence",
            code=EngineeringErrorCode.VALIDATION_ERROR,
            reason=authority_decision.reason,
            requested_level=(
                payload.verification_level.value if payload.verification_level is not None else None
            ),
        )

    verification_levels = list(entry.verification_levels)
    lifecycle = entry.lifecycle
    trust = entry.trust_level
    confidence = entry.confidence
    last_verified_at = entry.last_verified_at
    if payload.action == "ACCEPT":
        for level in authority_decision.verification_levels:
            if level not in verification_levels:
                verification_levels.append(level)
        lifecycle, trust = KnowledgeLifecycle.ACTIVE, authority_decision.trust_level
        if freshness_status != "CURRENT":
            lifecycle, trust = KnowledgeLifecycle.STALE, TrustLevel.UNTRUSTED
        confidence = max(confidence, 0.6)
        last_verified_at = utc_now()
    elif payload.action == "VERIFY":
        for level in authority_decision.verification_levels:
            if level not in verification_levels:
                verification_levels.append(level)
        lifecycle = KnowledgeLifecycle.ACTIVE
        trust = authority_decision.trust_level
        confidence = max(confidence, 0.75)
        last_verified_at = utc_now()
    elif payload.action == "RESOLVE_CONFLICT":
        lifecycle, trust = KnowledgeLifecycle.CANDIDATE, TrustLevel.UNTRUSTED
        confidence = min(confidence, 0.6)
        last_verified_at = None
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
            "authority_level": authority_decision.authority_level,
            "confidence": confidence,
            "last_verified_at": last_verified_at,
            "reviewed_by": principal.actor_id,
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


def _promote_import_findings(
    session: Session,
    row: ImportSessionRecord,
    selected: list[dict[str, object]],
    *,
    project_id: UUID,
    evidence_id: UUID,
    principal: AuthenticatedPrincipal,
) -> tuple[list[UUID], list[dict[str, object]]]:
    """Create canonical candidate claims with immutable import provenance."""

    claim_ids: list[UUID] = []
    provenance: list[dict[str, object]] = []
    now = utc_now()
    source_revision_id = row.summary.get("source_revision_id")
    for finding in selected:
        finding_id = str(finding["id"])
        category = str(finding.get("category", "unknown")).lower().replace(" ", "-")
        predicate = f"import.{category}"[:200]
        subject_ref = f"import:{row.id}:finding:{finding_id}"
        existing = session.scalar(
            select(EngineeringClaimRecord).where(
                EngineeringClaimRecord.project_id == str(project_id),
                EngineeringClaimRecord.subject_ref == subject_ref,
                EngineeringClaimRecord.predicate == predicate,
            )
        )
        source_path = finding.get("source_path", finding.get("path"))
        source_hash = (
            finding.get("source_hash")
            or (row.file_manifest.get(str(source_path)) if source_path else None)
            or row.source_manifest_hash
        )
        raw_confidence = finding.get("confidence", 0.6)
        confidence = (
            float(raw_confidence)
            if isinstance(raw_confidence, (int, float))
            else {"HIGH": 0.85, "MEDIUM": 0.6, "LOW": 0.3}.get(str(raw_confidence), 0.6)
        )
        item_provenance = {
            "import_id": str(row.id),
            "finding_id": finding_id,
            "source_revision_id": source_revision_id,
            "evidence_id": str(evidence_id),
            "review_actor": principal.actor_id,
            "review_time": now.isoformat(),
            "confidence": confidence,
            "source_path": source_path,
            "source_hash": source_hash,
        }
        if existing is None:
            record = EngineeringClaimRecord(
                id=str(uuid4()),
                schema_version="1.0",
                revision=1,
                created_at=now,
                updated_at=now,
                entity_metadata={"m22_promotion": item_provenance},
                project_id=str(project_id),
                subject_ref=subject_ref,
                predicate=predicate,
                value_schema_ref="eea.import.finding.v1",
                value_json={
                    "title": finding.get("title"),
                    "value": finding.get("value"),
                    "category": finding.get("category"),
                    "source_path": source_path,
                },
                applicability={"import_id": str(row.id), "finding_id": finding_id},
                evidence_ids=[str(evidence_id)],
                verification_levels=[VerificationLevel.IMPORT_VERIFIED.value],
                confidence=confidence,
                source_priority=500,
                source_version=row.resolved_commit or row.source_manifest_hash,
                lifecycle=ClaimLifecycle.CANDIDATE.value,
            )
            session.add(record)
            existing = record
        claim_id = UUID(existing.id)
        claim_ids.append(claim_id)
        provenance.append(item_provenance)
    session.flush()
    return claim_ids, provenance


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
    principal = _principal(request)
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
        locator={
            "import_session_id": str(import_id),
            "finding_ids": finding_ids,
            "status": "PASS",
            "review_actor": principal.actor_id,
            "review_time": utc_now().isoformat(),
            "source_revision_id": row.summary.get("source_revision_id"),
        },
        source_uri=f"import://{import_id}",
        content_hash=row.source_manifest_hash,
        summary=f"M22 reviewed findings from import {import_id}",
    )
    evidence = SqlAlchemyEvidenceRepository(session).add(evidence, commit=False)
    claim_ids, provenance = _promote_import_findings(
        session,
        row,
        selected,
        project_id=payload.project_id,
        evidence_id=evidence.id,
        principal=principal,
    )
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
        claim_ids=claim_ids,
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
        created_by=principal.actor_id,
        metadata={"m22_promotion_provenance": provenance},
    )
    stored = SqlAlchemyKnowledgeEntryRepository(session).add(entry, commit=False)
    session.commit()
    return ApiEnvelope(
        data={
            "entry": _as_data(stored),
            "evidence_id": str(evidence.id),
            "finding_ids": finding_ids,
            "claim_ids": [str(value) for value in claim_ids],
            "provenance": provenance,
        },
        request_id=_request_id(request),
    )


__all__ = ["router"]
