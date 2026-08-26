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
from eea_application.knowledge_identity import IdentityContext
from eea_application.knowledge_memory import (
    InvalidMemoryTransition,
    KnowledgeMemoryService,
    MemoryLifecyclePolicy,
    RecallContext,
    claim_memory_state,
)
from eea_core.entities import Evidence, KnowledgeEntry, utc_now
from eea_core.enums import (
    AuthorityLevel,
    ClaimConflictStatus,
    ClaimConflictType,
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
from sqlalchemy import or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from eea_backend.identity_repositories import IdentityRepository
from eea_backend.knowledge_propagation import (
    enqueue_memory_event,
    reconcile_memory_entries,
)
from eea_backend.knowledge_repositories import (
    SqlAlchemyKnowledgeAuditRepository,
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


class MemoryEntryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    expected_revision: int = Field(ge=1)
    scope: KnowledgeScope | None = None
    task_ref: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    summary: str | None = Field(default=None, max_length=12000)
    tags: list[str] | None = Field(default=None, max_length=50)
    applicability: dict[str, object] | None = None
    source_ref: str | None = Field(default=None, max_length=2000)
    source_version: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=2000)


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
    include_non_active: bool = False


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


class EvidenceLifecycleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)
    replacement_evidence_id: UUID | None = None


class ClaimConflictCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_a_id: UUID
    claim_b_id: UUID
    conflict_type: ClaimConflictType = ClaimConflictType.VALUE_MISMATCH
    overlapping_applicability: dict[str, object] = Field(default_factory=dict)
    resolver: str = Field(default="manual-review", min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=4000)


class ClaimConflictResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    expected_revision: int = Field(ge=1)
    selected_claim_id: UUID
    reason: str = Field(min_length=1, max_length=4000)


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
    data = cast(dict[str, object], entry.model_dump(mode="json"))
    metadata = entry.metadata
    freshness_status = metadata.get("freshness_status")
    if not isinstance(freshness_status, str):
        freshness_status = (
            "UNKNOWN" if not entry.source_revision_id and not entry.evidence_ids else "CURRENT"
        )
    data["freshness"] = {
        "status": freshness_status,
        "score": entry.freshness_score,
        "reason": metadata.get("freshness_reason"),
    }
    data["provenance"] = {
        "canonical_claim_ids": [str(value) for value in entry.claim_ids],
        "evidence_ids": [str(value) for value in entry.evidence_ids],
        "source_revision_id": (
            str(entry.source_revision_id) if entry.source_revision_id is not None else None
        ),
        "source_ref": entry.source_ref,
        "origin": metadata.get("origin", "manual"),
    }
    return data


def _principal(request: Request) -> AuthenticatedPrincipal:
    """Get identity only from the authenticated backend request context."""

    return authenticated_principal(request)


def _identity(request: Request, session: Session, *, task_id: str | None = None) -> IdentityContext:
    principal = _principal(request)
    return IdentityRepository(session).load_context(
        principal_id=principal.actor_id,
        user_id=principal.user_id,
        session_id=principal.session_id,
        authentication_source=principal.authentication_source,
        task_id=task_id if task_id is not None else principal.task_id,
    )


def _authorize_project(context: IdentityContext, project_id: UUID, *, action: str = "read") -> None:
    if not context.can_project(str(project_id), action):
        raise _error(
            "Project access is not granted by the authenticated identity",
            code=EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            project_id=str(project_id),
            action=action,
        )


def _scope_context(
    context: IdentityContext, requested: list[KnowledgeScope], *, project_id: UUID
) -> tuple[KnowledgeScope, ...]:
    allowed = context.allowed_scopes(project_id=str(project_id))
    return tuple(value for value in requested if value.value in allowed)


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
                producer=str(locator["producer"]) if locator.get("producer") else None,
                producer_version=(
                    str(locator["producer_version"]) if locator.get("producer_version") else None
                ),
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
    session: Session,
    entry: KnowledgeEntry,
    *,
    audit_context: IdentityContext | None = None,
    request_id: str = "memory-reconcile",
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
    claim_changed = False
    snapshot = entry.metadata.get("claim_revision_snapshot")
    claim_records = list(
        session.scalars(
            select(EngineeringClaimRecord).where(
                EngineeringClaimRecord.id.in_([str(value) for value in entry.claim_ids])
            )
        )
    )
    if isinstance(snapshot, dict):
        claim_changed = any(
            str(record.revision) != str(snapshot.get(record.id)) for record in claim_records
        ) or len(claim_records) != len(entry.claim_ids)
    updated, decision = decision_service.reconcile(
        entry,
        current_source_revision_id=current_source,
        conflict_open=_open_conflict(session, entry.claim_ids),
        stale_evidence_ids=stale_ids or ((entry.id,) if claim_changed else ()),
    )
    if updated.revision != entry.revision:
        metadata = dict(updated.metadata)
        metadata.update(
            {
                "freshness_status": decision.status,
                "freshness_reason": decision.reason or "canonical dependency changed",
                "last_propagation_event": "read_reconcile",
            }
        )
        updated = updated.model_copy(update={"metadata": metadata})
        saved = SqlAlchemyKnowledgeEntryRepository(session).save(
            updated, expected_revision=entry.revision
        )
        if saved is not None:
            if audit_context is not None:
                SqlAlchemyKnowledgeAuditRepository(session).add(
                    entry_id=saved.id,
                    project_id=saved.project_id,
                    principal_id=audit_context.principal_id,
                    user_id=audit_context.user_id,
                    session_id=audit_context.session_id,
                    request_id=request_id,
                    action=decision.status.lower() + "_transition",
                    before=_as_data(entry),
                    after=_as_data(saved),
                    reason=decision.reason or "canonical dependency changed",
                    commit=False,
                )
            entry = saved
    return entry, decision.status, decision.reason


def _context(
    *,
    project_id: UUID,
    actor_ref: str,
    scopes: list[KnowledgeScope] | tuple[KnowledgeScope, ...],
    task_ref: str | None = None,
    organization_ref: str | None = None,
    organization_ids: frozenset[str] = frozenset(),
    query: str = "",
    limit: int = 1,
    include_non_active: bool = False,
) -> RecallContext:
    return RecallContext(
        project_id=project_id,
        actor_ref=actor_ref,
        scope_context=tuple(scopes),
        query=query,
        limit=limit,
        task_ref=task_ref,
        organization_ref=organization_ref,
        organization_ids=organization_ids,
        include_non_active=include_non_active,
    )


def _ensure_visible(
    entry: KnowledgeEntry,
    *,
    project_id: UUID,
    actor_ref: str,
    task_ref: str | None = None,
    organization_ref: str | None = None,
    organization_ids: frozenset[str] = frozenset(),
) -> None:
    context = _context(
        project_id=project_id,
        actor_ref=actor_ref,
        scopes=tuple(KnowledgeScope),
        task_ref=task_ref,
        organization_ref=organization_ref,
        organization_ids=organization_ids,
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


def _claim_revision_snapshot(session: Session, claim_ids: list[UUID]) -> dict[str, int]:
    if not claim_ids:
        return {}
    records = session.scalars(
        select(EngineeringClaimRecord).where(
            EngineeringClaimRecord.id.in_([str(value) for value in claim_ids])
        )
    )
    return {str(record.id): record.revision for record in records}


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
    context = _identity(request, session)
    _validate_references(session, payload)
    if payload.scope is KnowledgeScope.GLOBAL_PUBLIC:
        if not context.can_publish_global():
            raise _error(
                "Global public memory creation requires a trusted publisher",
                code=EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            )
    elif payload.scope in {
        KnowledgeScope.PROJECT_PRIVATE,
        KnowledgeScope.TASK_ONLY,
    }:
        if payload.project_id is None:
            raise _error(
                "Project-private memory requires a project",
                code=EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            )
        _authorize_project(context, payload.project_id, action="write")
    elif payload.scope is KnowledgeScope.ORGANIZATION_PRIVATE and not context.organization_ids:
        raise _error(
            "Organization-private memory is unavailable without an authenticated organization",
            code=EngineeringErrorCode.ORGANIZATION_SCOPE_UNAVAILABLE,
        )
    if payload.scope is KnowledgeScope.TASK_ONLY and (
        context.task_id is None or payload.task_ref != context.task_id
    ):
        raise _error(
            "Task-only memory requires a server-bound task context",
            code=EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
        )
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
    owner_ref = context.user_id if payload.scope is KnowledgeScope.USER_PRIVATE else None
    organization_ref = (
        context.active_organization_id
        if payload.scope is KnowledgeScope.ORGANIZATION_PRIVATE
        else None
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
        task_ref=context.task_id if payload.scope is KnowledgeScope.TASK_ONLY else None,
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
        confidence=0,
        freshness_score=1.0,
        license_ref=payload.license_ref,
        usage_policy=payload.usage_policy,
        related_entry_ids=payload.related_entry_ids,
        created_by=principal.actor_id,
        metadata={
            "origin": "manual",
            "projection_version": "m23r.v1",
            "claim_revision_snapshot": _claim_revision_snapshot(session, payload.claim_ids),
            "freshness_status": "UNKNOWN" if not payload.evidence_ids else "CURRENT",
        },
    )
    stored = SqlAlchemyKnowledgeEntryRepository(session).add(entry)
    SqlAlchemyKnowledgeAuditRepository(session).add(
        entry_id=stored.id,
        project_id=stored.project_id,
        principal_id=context.principal_id,
        user_id=context.user_id,
        session_id=context.session_id,
        request_id=_request_id(request),
        action="create",
        before={},
        after=_as_data(stored),
        reason="memory entry created as an untrusted canonical projection",
        commit=True,
    )
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
    context = _identity(request, session)
    _project_exists(session, project_id)
    entry = _get_entry(session, entry_id)
    if entry.scope in {KnowledgeScope.PROJECT_PRIVATE, KnowledgeScope.TASK_ONLY}:
        _authorize_project(context, project_id, action="read")
    entry, _, _ = _reconcile_entry(
        session, entry, audit_context=context, request_id=_request_id(request)
    )
    _ensure_visible(
        entry,
        project_id=project_id,
        actor_ref=context.user_id,
        task_ref=context.task_id,
        organization_ref=context.active_organization_id,
        organization_ids=context.organization_ids,
    )
    return ApiEnvelope(data=_as_data(entry), request_id=_request_id(request))


@router.patch(
    "/memory/entries/{entry_id}",
    response_model=ApiEnvelope[dict[str, object]],
    tags=["knowledge-memory"],
)
def update_memory_entry(
    entry_id: UUID,
    payload: MemoryEntryUpdateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[dict[str, object]]:
    context = _identity(request, session)
    _authorize_project(context, payload.project_id, action="write")
    entry = _get_entry(session, entry_id)
    _ensure_visible(
        entry,
        project_id=payload.project_id,
        actor_ref=context.user_id,
        task_ref=context.task_id,
        organization_ref=context.active_organization_id,
        organization_ids=context.organization_ids,
    )
    entry, _, _ = _reconcile_entry(
        session, entry, audit_context=context, request_id=_request_id(request)
    )
    if entry.revision != payload.expected_revision:
        raise _error(
            "Knowledge entry revision changed; reload before editing",
            code=EngineeringErrorCode.REVISION_CONFLICT,
            entry_id=str(entry_id),
            expected_revision=payload.expected_revision,
            actual_revision=entry.revision,
        )

    target_scope = payload.scope or entry.scope
    if target_scope is KnowledgeScope.GLOBAL_PUBLIC:
        if not context.can_publish_global():
            raise _error(
                "Global public memory editing requires a trusted publisher",
                code=EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            )
    elif target_scope in {KnowledgeScope.PROJECT_PRIVATE, KnowledgeScope.TASK_ONLY}:
        _authorize_project(context, payload.project_id, action="write")
    if target_scope is KnowledgeScope.ORGANIZATION_PRIVATE and (
        not context.organization_ids or context.active_organization_id is None
    ):
        raise _error(
            "Organization-private memory requires an authenticated organization",
            code=EngineeringErrorCode.ORGANIZATION_SCOPE_UNAVAILABLE,
        )
    if target_scope is KnowledgeScope.TASK_ONLY and context.task_id is None:
        raise _error(
            "Task-only memory requires a server-bound task context",
            code=EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
        )

    values = payload.model_dump(
        mode="json",
        exclude_unset=True,
        exclude={"project_id", "expected_revision", "scope", "task_ref", "note"},
    )
    values["scope"] = target_scope
    values["owner_ref"] = context.user_id if target_scope is KnowledgeScope.USER_PRIVATE else None
    values["organization_ref"] = (
        context.active_organization_id
        if target_scope is KnowledgeScope.ORGANIZATION_PRIVATE
        else None
    )
    values["task_ref"] = context.task_id if target_scope is KnowledgeScope.TASK_ONLY else None
    source_changed = any(key in values for key in ("source_ref", "source_version"))
    lifecycle = entry.lifecycle
    trust = entry.trust_level
    freshness_score = entry.freshness_score
    metadata = dict(entry.metadata)
    if source_changed and lifecycle in {KnowledgeLifecycle.ACTIVE, KnowledgeLifecycle.TRUSTED}:
        lifecycle = KnowledgeLifecycle.STALE
        trust = TrustLevel.UNTRUSTED
        freshness_score = 0.0
        metadata.update(
            {
                "freshness_status": "STALE",
                "freshness_reason": "memory provenance was edited and requires revalidation",
            }
        )
    try:
        MemoryLifecyclePolicy.assert_transition(entry.lifecycle, lifecycle)
    except InvalidMemoryTransition as exc:
        raise _error(str(exc), code=EngineeringErrorCode.INVALID_MEMORY_TRANSITION) from exc
    metadata.update(
        {
            "projection_version": "m23r.v1",
            "last_edit_note": payload.note,
        }
    )
    updated = KnowledgeEntry.model_validate(
        {
            **entry.model_dump(mode="json"),
            **values,
            "metadata": metadata,
            "revision": entry.revision + 1,
            "updated_at": utc_now(),
            "lifecycle": lifecycle,
            "trust_level": trust,
            "freshness_score": freshness_score,
        }
    )
    stored = SqlAlchemyKnowledgeEntryRepository(session).save(
        updated, expected_revision=payload.expected_revision, commit=False
    )
    if stored is None:
        raise _error(
            "Knowledge entry revision changed; reload before editing",
            code=EngineeringErrorCode.REVISION_CONFLICT,
            entry_id=str(entry_id),
        )
    SqlAlchemyKnowledgeAuditRepository(session).add(
        entry_id=stored.id,
        project_id=stored.project_id,
        principal_id=context.principal_id,
        user_id=context.user_id,
        session_id=context.session_id,
        request_id=_request_id(request),
        action="update",
        before=_as_data(entry),
        after=_as_data(stored),
        reason=payload.note or "memory projection edited with optimistic concurrency",
        commit=True,
    )
    return ApiEnvelope(data=_as_data(stored), request_id=_request_id(request))


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
    context_identity = _identity(request, session)
    _project_exists(session, payload.project_id)
    if any(
        scope in {KnowledgeScope.PROJECT_PRIVATE, KnowledgeScope.TASK_ONLY}
        for scope in payload.scope_context
    ):
        _authorize_project(context_identity, payload.project_id, action="read")
    entries = []
    freshness: dict[str, tuple[str, str | None]] = {}
    repository = SqlAlchemyKnowledgeEntryRepository(session)
    for candidate in repository.list_for_recall():
        if candidate.project_id not in {None, payload.project_id}:
            continue
        reconciled, freshness_status, stale_reason = _reconcile_entry(
            session,
            candidate,
            audit_context=context_identity,
            request_id=_request_id(request),
        )
        entries.append(reconciled)
        freshness[str(reconciled.id)] = (freshness_status, stale_reason)
    context = _context(
        project_id=payload.project_id,
        actor_ref=context_identity.user_id,
        scopes=_scope_context(
            context_identity, payload.scope_context, project_id=payload.project_id
        ),
        task_ref=context_identity.task_id,
        organization_ref=context_identity.active_organization_id,
        organization_ids=context_identity.organization_ids,
        query=payload.query,
        limit=payload.limit,
        include_non_active=payload.include_non_active,
    )
    matches = KnowledgeMemoryService().recall(entries, context)
    effective_scopes = _scope_context(
        context_identity, payload.scope_context, project_id=payload.project_id
    )
    audit_id = SqlAlchemyKnowledgeRecallAuditRepository(session).add(
        project_id=payload.project_id,
        actor_ref=context_identity.principal_id,
        query=payload.query,
        scope_context=list(effective_scopes),
        result_ids=[match.entry.id for match in matches],
        request_id=_request_id(request),
        commit=False,
    )
    SqlAlchemyKnowledgeAuditRepository(session).add(
        entry_id=None,
        project_id=payload.project_id,
        principal_id=context_identity.principal_id,
        user_id=context_identity.user_id,
        session_id=context_identity.session_id,
        request_id=_request_id(request),
        action="recall",
        before={},
        after={"result_ids": [str(match.entry.id) for match in matches]},
        reason="scope-filtered memory recall",
        commit=False,
    )
    session.commit()
    return ApiEnvelope(
        data={
            "query": payload.query,
            "scope_context": [value.value for value in effective_scopes],
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
    context = _identity(request, session)
    _authorize_project(context, payload.project_id, action="review")
    entry = _get_entry(session, entry_id)
    entry, freshness_status, _ = _reconcile_entry(
        session, entry, audit_context=context, request_id=_request_id(request)
    )
    _ensure_visible(
        entry,
        project_id=payload.project_id,
        actor_ref=context.user_id,
        task_ref=context.task_id,
        organization_ref=context.active_organization_id,
        organization_ids=context.organization_ids,
    )
    if entry.revision != payload.expected_revision:
        raise _error(
            "Knowledge entry revision changed; reload before reviewing",
            code=EngineeringErrorCode.REVISION_CONFLICT,
            entry_id=str(entry_id),
            expected_revision=payload.expected_revision,
            actual_revision=entry.revision,
        )
    targets = {
        "ACCEPT": KnowledgeLifecycle.ACTIVE,
        "VERIFY": KnowledgeLifecycle.ACTIVE,
        "RESOLVE_CONFLICT": KnowledgeLifecycle.CANDIDATE,
        "REJECT": KnowledgeLifecycle.REJECTED,
        "ARCHIVE": KnowledgeLifecycle.ARCHIVED,
        "DEPRECATE": KnowledgeLifecycle.DEPRECATED,
    }
    target_lifecycle = targets[payload.action]
    try:
        MemoryLifecyclePolicy.assert_transition(entry.lifecycle, target_lifecycle)
    except InvalidMemoryTransition as exc:
        raise _error(str(exc), code=EngineeringErrorCode.INVALID_MEMORY_TRANSITION) from exc
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
            strict_provenance=True,
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
        if freshness_status not in {"CURRENT", "UNKNOWN"}:
            raise _error(
                "Stale memory must be revalidated from current canonical evidence",
                code=EngineeringErrorCode.VERIFICATION_EVIDENCE_REQUIRED,
            )
        lifecycle, trust = KnowledgeLifecycle.ACTIVE, authority_decision.trust_level
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
    metadata = dict(entry.metadata)
    metadata.update(
        {
            "freshness_status": (
                "UNKNOWN"
                if freshness_status == "UNKNOWN"
                else "CURRENT"
                if lifecycle is not KnowledgeLifecycle.STALE
                else "STALE"
            ),
            "freshness_reason": (
                "no canonical freshness anchor is attached"
                if freshness_status == "UNKNOWN"
                else None
                if lifecycle is not KnowledgeLifecycle.STALE
                else metadata.get("freshness_reason")
            ),
            "claim_revision_snapshot": _claim_revision_snapshot(session, entry.claim_ids),
            "last_review_action": payload.action,
            "last_review_note": payload.note,
        }
    )
    updated = KnowledgeEntry.model_validate(
        {
            **entry.model_dump(mode="json"),
            "revision": entry.revision + 1,
            "updated_at": now,
            "metadata": metadata,
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
    SqlAlchemyKnowledgeAuditRepository(session).add(
        entry_id=stored.id,
        project_id=stored.project_id,
        principal_id=context.principal_id,
        user_id=context.user_id,
        session_id=context.session_id,
        request_id=_request_id(request),
        action=f"review:{payload.action.lower()}",
        before=_as_data(entry),
        after=_as_data(stored),
        reason=payload.note or authority_decision.reason,
        commit=True,
    )
    return ApiEnvelope(data=_as_data(stored), request_id=_request_id(request))


def _evidence_data(
    record: EvidenceRecord, *, locator: dict[str, object] | None = None
) -> dict[str, object]:
    return {
        "id": record.id,
        "schema_version": record.schema_version,
        "revision": record.revision,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "metadata": dict(record.entity_metadata),
        "project_id": record.project_id,
        "evidence_type": record.evidence_type,
        "locator": locator if locator is not None else dict(record.locator),
        "source_uri": record.source_uri,
        "content_hash": record.content_hash,
        "summary": record.summary,
    }


def _mutate_evidence_lifecycle(
    *,
    evidence_id: UUID,
    project_id: UUID,
    payload: EvidenceLifecycleRequest,
    event_type: Literal["EvidenceInvalidated", "EvidenceSuperseded"],
    request: Request,
    session: Session,
) -> ApiEnvelope[dict[str, object]]:
    context = _identity(request, session)
    _authorize_project(context, project_id, action="write")
    _project_exists(session, project_id)
    record = session.get(EvidenceRecord, str(evidence_id))
    if record is None or record.project_id != str(project_id):
        raise _error(
            "Evidence is not available for this project",
            code=EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            evidence_id=str(evidence_id),
            project_id=str(project_id),
        )
    replacement = None
    if payload.replacement_evidence_id is not None:
        replacement = session.get(EvidenceRecord, str(payload.replacement_evidence_id))
        if replacement is None or replacement.project_id != str(project_id):
            raise _error("Replacement evidence is not available for this project")
        if replacement.id == record.id:
            raise _error("Replacement evidence must be different from the invalidated record")
    if record.revision != payload.expected_revision:
        raise _error(
            "Evidence revision does not match",
            code=EngineeringErrorCode.REVISION_CONFLICT,
            evidence_id=str(evidence_id),
            expected_revision=payload.expected_revision,
            actual_revision=record.revision,
        )
    before = _evidence_data(record)
    locator = dict(record.locator)
    locator.update(
        {
            "status": "INVALID" if event_type == "EvidenceInvalidated" else "SUPERSEDED",
            "invalidated_by": context.principal_id,
            "invalidated_at": utc_now().isoformat(),
            "invalidation_reason": payload.reason,
        }
    )
    if replacement is not None:
        locator["replacement_evidence_id"] = replacement.id
    result = cast(
        CursorResult[object],
        session.execute(
            update(EvidenceRecord)
            .where(
                EvidenceRecord.id == str(evidence_id),
                EvidenceRecord.project_id == str(project_id),
                EvidenceRecord.revision == payload.expected_revision,
            )
            .values(
                locator=locator,
                revision=payload.expected_revision + 1,
                updated_at=utc_now(),
            )
        ),
    )
    if result.rowcount != 1:
        session.rollback()
        raise _error(
            "Evidence changed during lifecycle update",
            code=EngineeringErrorCode.REVISION_CONFLICT,
            evidence_id=str(evidence_id),
        )
    session.flush()
    updated = session.get(EvidenceRecord, str(evidence_id))
    if updated is None:
        raise _error("Evidence disappeared during lifecycle update")
    reconcile_memory_entries(
        session,
        event_type=event_type,
        project_id=project_id,
        evidence_ids=[evidence_id],
        principal_id=context.principal_id,
        user_id=context.user_id,
        session_id=context.session_id,
        request_id=_request_id(request),
        reason=payload.reason,
    )
    enqueue_memory_event(
        session,
        event_type=event_type,
        aggregate_type="Evidence",
        aggregate_id=str(evidence_id),
        aggregate_revision=updated.revision,
        project_id=project_id,
        payload={
            "project_id": str(project_id),
            "evidence_id": str(evidence_id),
            "replacement_evidence_id": (
                str(payload.replacement_evidence_id)
                if payload.replacement_evidence_id is not None
                else None
            ),
            "reason": payload.reason,
        },
    )
    SqlAlchemyKnowledgeAuditRepository(session).add(
        entry_id=None,
        project_id=project_id,
        principal_id=context.principal_id,
        user_id=context.user_id,
        session_id=context.session_id,
        request_id=_request_id(request),
        action=event_type,
        before=before,
        after=_evidence_data(updated, locator=locator),
        reason=payload.reason,
        commit=False,
    )
    session.commit()
    return ApiEnvelope(
        data={"evidence": _evidence_data(updated, locator=locator)},
        request_id=_request_id(request),
    )


@router.post(
    "/projects/{project_id}/evidence/{evidence_id}/invalidate",
    response_model=ApiEnvelope[dict[str, object]],
    tags=["evidence", "knowledge-memory"],
)
def invalidate_evidence(
    project_id: UUID,
    evidence_id: UUID,
    payload: EvidenceLifecycleRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[dict[str, object]]:
    if payload.project_id != project_id:
        raise _error("Evidence lifecycle project does not match the route project")
    return _mutate_evidence_lifecycle(
        evidence_id=evidence_id,
        project_id=project_id,
        payload=payload,
        event_type="EvidenceInvalidated",
        request=request,
        session=session,
    )


@router.post(
    "/projects/{project_id}/evidence/{evidence_id}/supersede",
    response_model=ApiEnvelope[dict[str, object]],
    tags=["evidence", "knowledge-memory"],
)
def supersede_evidence(
    project_id: UUID,
    evidence_id: UUID,
    payload: EvidenceLifecycleRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[dict[str, object]]:
    if payload.project_id != project_id:
        raise _error("Evidence lifecycle project does not match the route project")
    return _mutate_evidence_lifecycle(
        evidence_id=evidence_id,
        project_id=project_id,
        payload=payload,
        event_type="EvidenceSuperseded",
        request=request,
        session=session,
    )


def _project_claim(session: Session, claim_id: UUID, project_id: UUID) -> EngineeringClaimRecord:
    claim = session.get(EngineeringClaimRecord, str(claim_id))
    if claim is None or claim.project_id != str(project_id):
        raise _error(
            "Claim is not available for this project",
            code=EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            claim_id=str(claim_id),
            project_id=str(project_id),
        )
    return claim


@router.post(
    "/projects/{project_id}/claims/conflicts",
    response_model=ApiEnvelope[dict[str, object]],
    status_code=status.HTTP_201_CREATED,
    tags=["claims", "knowledge-memory"],
)
def open_claim_conflict(
    project_id: UUID,
    payload: ClaimConflictCreateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[dict[str, object]]:
    context = _identity(request, session)
    _authorize_project(context, project_id, action="write")
    _project_exists(session, project_id)
    if payload.claim_a_id == payload.claim_b_id:
        raise _error("A claim conflict requires two different claims")
    claim_a = _project_claim(session, payload.claim_a_id, project_id)
    claim_b = _project_claim(session, payload.claim_b_id, project_id)
    now = utc_now()
    conflict = ClaimConflictRecord(
        id=str(uuid4()),
        schema_version="1.0",
        revision=1,
        created_at=now,
        updated_at=now,
        entity_metadata={},
        claim_a_id=claim_a.id,
        claim_b_id=claim_b.id,
        conflict_type=payload.conflict_type.value,
        overlapping_applicability=payload.overlapping_applicability,
        resolver=payload.resolver,
        resolution=None,
        selected_claim_id=None,
        reason=payload.reason,
        status=ClaimConflictStatus.OPEN.value,
    )
    session.add(conflict)
    session.flush()
    reconcile_memory_entries(
        session,
        event_type="ClaimConflictOpened",
        project_id=project_id,
        claim_ids=[payload.claim_a_id, payload.claim_b_id],
        principal_id=context.principal_id,
        user_id=context.user_id,
        session_id=context.session_id,
        request_id=_request_id(request),
        reason=payload.reason,
    )
    enqueue_memory_event(
        session,
        event_type="ClaimConflictOpened",
        aggregate_type="ClaimConflict",
        aggregate_id=conflict.id,
        aggregate_revision=conflict.revision,
        project_id=project_id,
        payload={
            "project_id": str(project_id),
            "claim_ids": [claim_a.id, claim_b.id],
            "conflict_id": conflict.id,
            "reason": payload.reason,
        },
    )
    SqlAlchemyKnowledgeAuditRepository(session).add(
        entry_id=None,
        project_id=project_id,
        principal_id=context.principal_id,
        user_id=context.user_id,
        session_id=context.session_id,
        request_id=_request_id(request),
        action="ClaimConflictOpened",
        before={},
        after={"conflict_id": conflict.id, "claim_ids": [claim_a.id, claim_b.id]},
        reason=payload.reason,
        commit=False,
    )
    session.commit()
    return ApiEnvelope(
        data={
            "conflict_id": conflict.id,
            "revision": conflict.revision,
            "status": conflict.status,
            "claim_ids": [claim_a.id, claim_b.id],
        },
        request_id=_request_id(request),
    )


@router.post(
    "/claims/conflicts/{conflict_id}/resolve",
    response_model=ApiEnvelope[dict[str, object]],
    tags=["claims", "knowledge-memory"],
)
def resolve_claim_conflict(
    conflict_id: UUID,
    payload: ClaimConflictResolveRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[dict[str, object]]:
    context = _identity(request, session)
    _authorize_project(context, payload.project_id, action="review")
    conflict = session.get(ClaimConflictRecord, str(conflict_id))
    if conflict is None:
        raise _error("Claim conflict was not found")
    claim_a = _project_claim(session, UUID(conflict.claim_a_id), payload.project_id)
    claim_b = _project_claim(session, UUID(conflict.claim_b_id), payload.project_id)
    if payload.selected_claim_id not in {UUID(claim_a.id), UUID(claim_b.id)}:
        raise _error("Selected claim must be one side of the conflict")
    if conflict.status != ClaimConflictStatus.OPEN.value:
        raise _error("Claim conflict is already resolved")
    if conflict.revision != payload.expected_revision:
        raise _error(
            "Claim conflict revision does not match",
            code=EngineeringErrorCode.REVISION_CONFLICT,
            conflict_id=str(conflict_id),
            expected_revision=payload.expected_revision,
            actual_revision=conflict.revision,
        )
    result = cast(
        CursorResult[object],
        session.execute(
            update(ClaimConflictRecord)
            .where(
                ClaimConflictRecord.id == str(conflict_id),
                ClaimConflictRecord.revision == payload.expected_revision,
                ClaimConflictRecord.status == ClaimConflictStatus.OPEN.value,
            )
            .values(
                status=ClaimConflictStatus.RESOLVED.value,
                selected_claim_id=str(payload.selected_claim_id),
                resolution=payload.reason,
                revision=payload.expected_revision + 1,
                updated_at=utc_now(),
            )
        ),
    )
    if result.rowcount != 1:
        session.rollback()
        raise _error(
            "Claim conflict changed during resolution",
            code=EngineeringErrorCode.REVISION_CONFLICT,
            conflict_id=str(conflict_id),
        )
    session.flush()
    reconcile_memory_entries(
        session,
        event_type="ClaimConflictResolved",
        project_id=payload.project_id,
        claim_ids=[UUID(claim_a.id), UUID(claim_b.id)],
        principal_id=context.principal_id,
        user_id=context.user_id,
        session_id=context.session_id,
        request_id=_request_id(request),
        reason=payload.reason,
    )
    enqueue_memory_event(
        session,
        event_type="ClaimConflictResolved",
        aggregate_type="ClaimConflict",
        aggregate_id=str(conflict_id),
        aggregate_revision=payload.expected_revision + 1,
        project_id=payload.project_id,
        payload={
            "project_id": str(payload.project_id),
            "claim_ids": [claim_a.id, claim_b.id],
            "conflict_id": str(conflict_id),
            "selected_claim_id": str(payload.selected_claim_id),
            "reason": payload.reason,
        },
    )
    SqlAlchemyKnowledgeAuditRepository(session).add(
        entry_id=None,
        project_id=payload.project_id,
        principal_id=context.principal_id,
        user_id=context.user_id,
        session_id=context.session_id,
        request_id=_request_id(request),
        action="ClaimConflictResolved",
        before={"conflict_id": str(conflict_id), "status": ClaimConflictStatus.OPEN.value},
        after={
            "conflict_id": str(conflict_id),
            "status": ClaimConflictStatus.RESOLVED.value,
            "selected_claim_id": str(payload.selected_claim_id),
        },
        reason=payload.reason,
        commit=False,
    )
    session.commit()
    return ApiEnvelope(
        data={
            "conflict_id": str(conflict_id),
            "revision": payload.expected_revision + 1,
            "status": ClaimConflictStatus.RESOLVED.value,
            "selected_claim_id": str(payload.selected_claim_id),
        },
        request_id=_request_id(request),
    )


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
    context = _identity(request, session)
    _authorize_project(context, payload.project_id, action="write")
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
            "producer": "m22r.import-review",
            "producer_version": "1.0",
            "timestamp": utc_now().isoformat(),
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
        metadata={
            "origin": "m22-import",
            "projection_version": "m23r.v1",
            "m22_promotion_provenance": provenance,
            "claim_revision_snapshot": _claim_revision_snapshot(session, claim_ids),
            "freshness_status": "CURRENT",
        },
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
