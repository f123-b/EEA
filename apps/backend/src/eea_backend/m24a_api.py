"""M24A Engineering Planning Copilot API.

This boundary accepts requirements and persists reviewable plans only.  It
never exposes an execution primitive, accepts a patch, or delegates source
content as instructions to a provider.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Protocol
from uuid import UUID, uuid4

from eea_application.planning import (
    DeterministicPlanningProvider,
    EngineeringPlanningService,
    PlanningResult,
)
from eea_core.entities import EntityBase, utc_now
from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_core.m24a_planning import (
    EngineeringPlan,
    EngineeringPlanStatus,
    EngineeringRequirement,
    EngineeringRequirementPriority,
    EngineeringRequirementStatus,
    EngineeringRequirementType,
    PlanReviewAction,
    PlanReviewStatus,
)
from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from eea_backend.identity_repositories import IdentityRepository
from eea_backend.models import (
    BuildRunRecord,
    ClaimConflictRecord,
    EngineeringClaimRecord,
    EngineeringDependencyEdgeRecord,
    EngineeringDependencyNodeStateRecord,
    EngineeringPlanAcceptanceMappingRecord,
    EngineeringPlanAssumptionRecord,
    EngineeringPlanChangeRecord,
    EngineeringPlanningAuditRecord,
    EngineeringPlanRecord,
    EngineeringPlanReviewCommentRecord,
    EngineeringPlanReviewRecord,
    EngineeringPlanRiskRecord,
    EngineeringPlanStepRecord,
    EngineeringPlanUnknownRecord,
    EngineeringPlanVerificationRecord,
    EngineeringRequirementRecord,
    ErcReportRecord,
    EvidenceRecord,
    FirmwareRecord,
    FirmwareStaticAnalysisRecord,
    HardwareIRRecord,
    IssueRecord,
    KnowledgeEntryRecord,
    PlanningContextSnapshotRecord,
    ProjectRecord,
    ProtocolRecord,
    SourceRevisionRecord,
    SourceWorkspaceRecord,
    TestRunRecord,
)
from eea_backend.schemas import ApiEnvelope
from eea_backend.security import AuthenticatedPrincipal, authenticated_principal

router = APIRouter()


class _RevisionRecord(Protocol):
    id: str
    revision: int


class RequirementCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20_000)
    requirement_type: EngineeringRequirementType = EngineeringRequirementType.INVESTIGATION
    priority: EngineeringRequirementPriority = EngineeringRequirementPriority.UNKNOWN
    constraints: list[str] = Field(default_factory=list, max_length=100)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=100)
    source: dict[str, object] = Field(default_factory=dict)
    source_revision_id: UUID | None = None
    created_by: str | None = Field(
        default=None,
        max_length=200,
        description="Deprecated compatibility field; identity is server-owned",
    )


class RequirementUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20_000)
    requirement_type: EngineeringRequirementType | None = None
    priority: EngineeringRequirementPriority | None = None
    constraints: list[str] | None = Field(default=None, max_length=100)
    acceptance_criteria: list[str] | None = Field(default=None, max_length=100)
    source: dict[str, object] | None = None
    source_revision_id: UUID | None = None


class PlanCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_revision_id: UUID | None = None
    provider: str = Field(default="deterministic", min_length=1, max_length=100)
    supersedes_plan_id: UUID | None = None


class PlanReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    action: PlanReviewAction
    comment: str = Field(default="", max_length=8_000)


class PlanCommentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_kind: str = Field(min_length=1, max_length=100)
    target_ref: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=8_000)


def _session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


SessionDependency = Annotated[Session, Depends(_session)]


def _jsonable(value: object) -> object:
    if isinstance(value, (UUID, datetime, date)):
        return str(value) if isinstance(value, UUID) else value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    return value


def _record_dict(record: object) -> dict[str, object]:
    table = getattr(record, "__table__", None)
    if table is None:
        return {}
    return {
        column.name: _jsonable(
            getattr(record, "entity_metadata" if column.name == "metadata" else column.name)
        )
        for column in table.columns
    }


def _json_mapping(value: Mapping[str, object]) -> dict[str, object]:
    serialized = _jsonable(value)
    return dict(serialized) if isinstance(serialized, Mapping) else {}


def _request_id(request: Request) -> str:
    return str(request.state.request_id)


def _principal(request: Request) -> AuthenticatedPrincipal:
    return authenticated_principal(request)


def _authorize_project(
    request: Request, session: Session, project_id: UUID, *, action: str = "read"
) -> AuthenticatedPrincipal:
    project = session.get(ProjectRecord, str(project_id))
    if project is None or project.deleted_at is not None:
        raise EngineeringError(
            EngineeringErrorCode.PROJECT_NOT_FOUND,
            "Project was not found",
            details={"project_id": str(project_id)},
        )
    principal = _principal(request)
    context = IdentityRepository(session).load_context(
        principal_id=principal.actor_id,
        user_id=principal.user_id,
        session_id=principal.session_id,
        authentication_source=principal.authentication_source,
        task_id=principal.task_id,
    )
    if not context.can_project(str(project_id), action):
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Project access is not granted by the authenticated identity",
            details={"project_id": str(project_id), "action": action},
        )
    return principal


def _requirement_record(session: Session, requirement_id: UUID) -> EngineeringRequirementRecord:
    record = session.get(EngineeringRequirementRecord, str(requirement_id))
    if record is None:
        raise EngineeringError(
            EngineeringErrorCode.VALIDATION_ERROR,
            "Engineering requirement was not found",
            details={"requirement_id": str(requirement_id)},
        )
    return record


def _plan_record(session: Session, plan_id: UUID) -> EngineeringPlanRecord:
    record = session.get(EngineeringPlanRecord, str(plan_id))
    if record is None:
        raise EngineeringError(
            EngineeringErrorCode.VALIDATION_ERROR,
            "Engineering plan was not found",
            details={"plan_id": str(plan_id)},
        )
    return record


def _check_revision(record: _RevisionRecord, expected: int) -> None:
    current = int(record.revision)
    if current != expected:
        raise EngineeringError(
            EngineeringErrorCode.REVISION_CONFLICT,
            "The engineering object changed after it was read",
            details={
                "entity_id": str(record.id),
                "expected_revision": expected,
                "current_revision": current,
            },
        )


def _audit(
    session: Session,
    request: Request,
    principal: AuthenticatedPrincipal,
    *,
    project_id: UUID,
    action: str,
    reason: str,
    before: Mapping[str, object] | None = None,
    after: Mapping[str, object] | None = None,
    requirement_id: UUID | None = None,
    plan_id: UUID | None = None,
) -> None:
    now = utc_now()
    session.add(
        EngineeringPlanningAuditRecord(
            id=str(uuid4()),
            schema_version="1.0",
            revision=1,
            created_at=now,
            updated_at=now,
            entity_metadata={},
            project_id=str(project_id),
            requirement_id=str(requirement_id) if requirement_id else None,
            plan_id=str(plan_id) if plan_id else None,
            principal_id=principal.actor_id,
            user_id=principal.user_id,
            session_id=principal.session_id,
            request_id=_request_id(request),
            action=action,
            before=_json_mapping(before or {}),
            after=_json_mapping(after or {}),
            reason=reason,
        )
    )


def _source_revision(
    session: Session, project_id: UUID, requested_id: UUID | None
) -> SourceRevisionRecord | None:
    if requested_id is not None:
        record = session.get(SourceRevisionRecord, str(requested_id))
        if record is None or record.project_id != str(project_id):
            raise EngineeringError(
                EngineeringErrorCode.SOURCE_REVISION_CONFLICT,
                "Source revision is not available in this project",
                details={"source_revision_id": str(requested_id), "project_id": str(project_id)},
            )
        return record
    workspace = session.scalar(
        select(SourceWorkspaceRecord).where(SourceWorkspaceRecord.project_id == str(project_id))
    )
    if workspace is not None and workspace.current_source_revision_id:
        current = session.get(SourceRevisionRecord, workspace.current_source_revision_id)
        if current is not None:
            return current
    return session.scalar(
        select(SourceRevisionRecord)
        .where(SourceRevisionRecord.project_id == str(project_id))
        .order_by(SourceRevisionRecord.created_at.desc(), SourceRevisionRecord.id.desc())
        .limit(1)
    )


def _scoped_rows[T](
    session: Session, model: type[T], project_id: UUID, *, include_global: bool = False
) -> list[dict[str, object]]:
    project_column = getattr(model, "project_id", None)
    if project_column is None:
        return []
    condition = project_column == str(project_id)
    if include_global:
        condition = or_(condition, project_column.is_(None))
    rows = session.scalars(select(model).where(condition).limit(200))
    return [_record_dict(row) for row in rows]


def _planning_inputs(
    session: Session, project_id: UUID, source_id: UUID | None
) -> tuple[SourceRevisionRecord | None, dict[str, list[dict[str, object]]]]:
    source = _source_revision(session, project_id, source_id)
    inputs = {
        "claims": _scoped_rows(session, EngineeringClaimRecord, project_id),
        "hardware": _scoped_rows(session, HardwareIRRecord, project_id),
        "protocols": _scoped_rows(session, ProtocolRecord, project_id),
        "firmware": _scoped_rows(session, FirmwareRecord, project_id),
        "dependencies": _scoped_rows(session, EngineeringDependencyEdgeRecord, project_id),
        "issues": _scoped_rows(session, IssueRecord, project_id),
        "builds": _scoped_rows(session, BuildRunRecord, project_id),
        "static_analysis": _scoped_rows(session, FirmwareStaticAnalysisRecord, project_id),
        "erc": _scoped_rows(session, ErcReportRecord, project_id),
        "test_runs": _scoped_rows(session, TestRunRecord, project_id),
        "evidence": _scoped_rows(session, EvidenceRecord, project_id, include_global=True),
        "memories": _scoped_rows(session, KnowledgeEntryRecord, project_id, include_global=True),
    }
    return source, inputs


def _requirement_model(record: EngineeringRequirementRecord) -> EngineeringRequirement:
    return EngineeringRequirement.model_validate(
        {
            "id": record.id,
            "schema_version": record.schema_version,
            "revision": record.revision,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "metadata": record.entity_metadata or {},
            "project_id": record.project_id,
            "title": record.title,
            "description": record.description,
            "requirement_type": record.requirement_type,
            "priority": record.priority,
            "constraints": record.constraints or [],
            "acceptance_criteria": record.acceptance_criteria or [],
            "source": record.source or {},
            "created_by": record.created_by,
            "status": record.status,
        }
    )


def _context_record(session: Session, context_id: UUID) -> PlanningContextSnapshotRecord:
    record = session.get(PlanningContextSnapshotRecord, str(context_id))
    if record is None:
        raise EngineeringError(
            EngineeringErrorCode.VALIDATION_ERROR,
            "Planning context snapshot was not found",
            details={"context_snapshot_id": str(context_id)},
        )
    return record


def _plan_model(session: Session, record: EngineeringPlanRecord) -> EngineeringPlan:
    steps = list(
        session.scalars(
            select(EngineeringPlanStepRecord)
            .where(EngineeringPlanStepRecord.plan_id == record.id)
            .order_by(EngineeringPlanStepRecord.step_order)
        )
    )
    changes = list(
        session.scalars(
            select(EngineeringPlanChangeRecord).where(
                EngineeringPlanChangeRecord.plan_id == record.id
            )
        )
    )
    risks = list(
        session.scalars(
            select(EngineeringPlanRiskRecord).where(EngineeringPlanRiskRecord.plan_id == record.id)
        )
    )
    assumptions = list(
        session.scalars(
            select(EngineeringPlanAssumptionRecord).where(
                EngineeringPlanAssumptionRecord.plan_id == record.id
            )
        )
    )
    unknowns = list(
        session.scalars(
            select(EngineeringPlanUnknownRecord).where(
                EngineeringPlanUnknownRecord.plan_id == record.id
            )
        )
    )
    mappings = list(
        session.scalars(
            select(EngineeringPlanAcceptanceMappingRecord).where(
                EngineeringPlanAcceptanceMappingRecord.plan_id == record.id
            )
        )
    )
    verifications = list(
        session.scalars(
            select(EngineeringPlanVerificationRecord).where(
                EngineeringPlanVerificationRecord.plan_id == record.id
            )
        )
    )
    return EngineeringPlan.model_validate(
        {
            "id": record.id,
            "schema_version": record.schema_version,
            "revision": record.revision,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "metadata": record.entity_metadata or {},
            "project_id": record.project_id,
            "requirement_id": record.requirement_id,
            "source_revision_id": record.source_revision_id,
            "context_snapshot_id": record.context_snapshot_id,
            "status": record.status,
            "summary": record.summary,
            "assumptions": [
                {
                    "description": item.description,
                    "basis": item.basis,
                    "confidence": item.confidence,
                    "evidence_refs": item.evidence_refs or [],
                    "validation_required": item.validation_required,
                }
                for item in assumptions
            ],
            "unknowns": [
                {
                    "question": item.question,
                    "why_needed": item.why_needed,
                    "blocking": item.blocking,
                    "recommended_resolution": item.recommended_resolution,
                    "related_refs": item.related_refs or [],
                }
                for item in unknowns
            ],
            "risks": [
                {
                    "id": item.id,
                    "category": item.category,
                    "severity": item.severity,
                    "likelihood": item.likelihood,
                    "description": item.description,
                    "affected_ref": item.affected_ref,
                    "mitigation": item.mitigation,
                    "verification": item.verification,
                    "reason": item.reason,
                    "evidence_refs": item.evidence_refs or [],
                }
                for item in risks
            ],
            "steps": [
                {
                    "id": item.id,
                    "order": item.step_order,
                    "title": item.title,
                    "description": item.description,
                    "action_type": item.action_type,
                    "target_type": item.target_type,
                    "target_ref": item.target_ref,
                    "reason": item.reason,
                    "dependencies": item.dependencies or [],
                    "preconditions": item.preconditions or [],
                    "expected_result": item.expected_result,
                    "verification_plan": item.verification_plan or [],
                    "risk_level": item.risk_level,
                    "evidence_refs": item.evidence_refs or [],
                }
                for item in steps
            ],
            "proposed_changes": [
                {
                    "id": item.id,
                    "change_type": item.change_type,
                    "target_kind": item.target_kind,
                    "target_ref": item.target_ref,
                    "current_state": item.current_state,
                    "proposed_state": item.proposed_state,
                    "reason": item.reason,
                    "impact": item.impact,
                    "risk": item.risk,
                    "evidence_refs": item.evidence_refs or [],
                    "confidence": item.confidence,
                    "status": item.status,
                    "expected_diff_intent": item.expected_diff_intent,
                }
                for item in changes
            ],
            "affected_components": record.affected_components or [],
            "evidence_refs": record.evidence_refs or [],
            "memory_refs": record.memory_refs or [],
            "acceptance_criteria_mapping": [
                {
                    "criterion": item.criterion,
                    "step_ids": item.step_ids or [],
                    "verification_refs": item.verification_refs or [],
                }
                for item in mappings
            ],
            "verification_plans": [
                {
                    "id": item.id,
                    "change_id": item.change_id,
                    "method": item.method,
                    "expected_result": item.expected_result,
                    "execution_allowed_in_m24a": item.execution_allowed_in_m24a,
                }
                for item in verifications
            ],
            "provider": record.provider,
            "model_version": record.model_version,
            "prompt_template_version": record.prompt_template_version,
            "planning_policy_version": record.planning_policy_version,
            "created_by": record.created_by,
            "supersedes_plan_id": record.supersedes_plan_id,
        }
    )


def _requirement_data(record: EngineeringRequirementRecord) -> dict[str, object]:
    data = _record_dict(record)
    data["source_revision_id"] = (record.source or {}).get("source_revision_id")
    return data


def _plan_data(session: Session, record: EngineeringPlanRecord) -> dict[str, object]:
    data = _plan_model(session, record).model_dump(mode="json")
    data.update(
        {
            "validation_issues": list(record.validation_issues or []),
            "quality_issues": list(record.quality_issues or []),
            "plan_only": bool(record.plan_only),
        }
    )
    return data


def _context_data(record: PlanningContextSnapshotRecord) -> dict[str, object]:
    return _record_dict(record)


def _entity_values(
    entity: EntityBase, *, metadata: Mapping[str, object] | None = None
) -> dict[str, object]:
    now = utc_now()
    return {
        "id": str(entity.id),
        "schema_version": entity.schema_version,
        "revision": entity.revision,
        "created_at": entity.created_at or now,
        "updated_at": entity.updated_at or now,
        "entity_metadata": dict(metadata or entity.metadata or {}),
    }


def _child_values(entity: BaseModel) -> dict[str, object]:
    values = entity.model_dump(mode="python")
    now = utc_now()
    return {
        "id": str(values.get("id", uuid4())),
        "schema_version": "1.0",
        "revision": 1,
        "created_at": now,
        "updated_at": now,
        "entity_metadata": {},
    }


def _save_context(session: Session, result: PlanningResult) -> PlanningContextSnapshotRecord:
    context = result.context
    record = PlanningContextSnapshotRecord(
        **_entity_values(context),
        project_id=str(context.project_id),
        source_revision_id=str(context.source_revision_id) if context.source_revision_id else None,
        selected_context=[item.model_dump(mode="json") for item in context.selected_context],
        excluded_context=[item.model_dump(mode="json") for item in context.excluded_context],
        selection_reason=context.selection_reason,
        claim_revisions=context.claim_revisions,
        evidence_revisions=context.evidence_revisions,
        memory_refs=[str(value) for value in context.memory_refs],
        evidence_refs=[str(value) for value in context.evidence_refs],
        source_content_is_untrusted=context.source_content_is_untrusted,
    )
    session.add(record)
    session.flush()
    return record


def _save_plan(session: Session, result: PlanningResult) -> EngineeringPlanRecord:
    plan = result.plan
    validation_issues = list(result.validation.issues)
    quality_issues = list(result.validation.quality_issues)
    record = EngineeringPlanRecord(
        **_entity_values(plan),
        project_id=str(plan.project_id),
        requirement_id=str(plan.requirement_id),
        source_revision_id=str(plan.source_revision_id) if plan.source_revision_id else None,
        context_snapshot_id=str(plan.context_snapshot_id),
        status=plan.status.value,
        summary=plan.summary,
        affected_components=list(plan.affected_components),
        evidence_refs=[str(value) for value in plan.evidence_refs],
        memory_refs=[str(value) for value in plan.memory_refs],
        provider=plan.provider,
        model_version=plan.model_version,
        prompt_template_version=plan.prompt_template_version,
        planning_policy_version=plan.planning_policy_version,
        created_by=plan.created_by,
        supersedes_plan_id=str(plan.supersedes_plan_id) if plan.supersedes_plan_id else None,
        validation_issues=validation_issues,
        quality_issues=quality_issues,
        plan_only=True,
    )
    session.add(record)
    session.flush()
    for step in plan.steps:
        session.add(
            EngineeringPlanStepRecord(
                **_child_values(step),
                plan_id=str(plan.id),
                step_order=step.order,
                title=step.title,
                description=step.description,
                action_type=step.action_type.value,
                target_type=step.target_type.value,
                target_ref=step.target_ref,
                reason=step.reason,
                dependencies=list(step.dependencies),
                preconditions=list(step.preconditions),
                expected_result=step.expected_result,
                verification_plan=list(step.verification_plan),
                risk_level=step.risk_level.value,
                evidence_refs=[str(value) for value in step.evidence_refs],
            )
        )
    for change in plan.proposed_changes:
        session.add(
            EngineeringPlanChangeRecord(
                **_child_values(change),
                plan_id=str(plan.id),
                change_type=change.change_type.value,
                target_kind=change.target_kind.value,
                target_ref=change.target_ref,
                current_state=change.current_state,
                proposed_state=change.proposed_state,
                reason=change.reason,
                impact=change.impact,
                risk=change.risk.value,
                evidence_refs=[str(value) for value in change.evidence_refs],
                confidence=change.confidence.value,
                status=change.status.value,
                expected_diff_intent=change.expected_diff_intent,
            )
        )
    for risk in plan.risks:
        session.add(
            EngineeringPlanRiskRecord(
                **_child_values(risk),
                plan_id=str(plan.id),
                category=risk.category.value,
                severity=risk.severity.value,
                likelihood=risk.likelihood.value,
                description=risk.description,
                affected_ref=risk.affected_ref,
                mitigation=risk.mitigation,
                verification=risk.verification,
                reason=risk.reason,
                evidence_refs=[str(value) for value in risk.evidence_refs],
            )
        )
    for assumption in plan.assumptions:
        session.add(
            EngineeringPlanAssumptionRecord(
                **_child_values(assumption),
                plan_id=str(plan.id),
                description=assumption.description,
                basis=assumption.basis,
                confidence=assumption.confidence.value,
                evidence_refs=[str(value) for value in assumption.evidence_refs],
                validation_required=assumption.validation_required,
            )
        )
    for unknown in plan.unknowns:
        session.add(
            EngineeringPlanUnknownRecord(
                **_child_values(unknown),
                plan_id=str(plan.id),
                question=unknown.question,
                why_needed=unknown.why_needed,
                blocking=unknown.blocking,
                recommended_resolution=unknown.recommended_resolution,
                related_refs=list(unknown.related_refs),
            )
        )
    for mapping in plan.acceptance_criteria_mapping:
        session.add(
            EngineeringPlanAcceptanceMappingRecord(
                **_child_values(mapping),
                plan_id=str(plan.id),
                criterion=mapping.criterion,
                step_ids=[str(value) for value in mapping.step_ids],
                verification_refs=list(mapping.verification_refs),
            )
        )
    for verification in plan.verification_plans:
        session.add(
            EngineeringPlanVerificationRecord(
                **_child_values(verification),
                plan_id=str(plan.id),
                change_id=str(verification.change_id),
                method=verification.method,
                expected_result=verification.expected_result,
                execution_allowed_in_m24a=False,
            )
        )
    session.flush()
    return record


def _create_plan(
    session: Session,
    project_id: UUID,
    requirement: EngineeringRequirementRecord,
    *,
    source_revision_id: UUID | None,
    provider_name: str,
    created_by: str,
    supersedes_plan_id: UUID | None = None,
    revision: int = 1,
) -> tuple[PlanningResult, EngineeringPlanRecord]:
    if provider_name != "deterministic":
        raise EngineeringError(
            EngineeringErrorCode.VALIDATION_ERROR,
            "M24A only exposes the deterministic provider boundary",
            details={"provider": provider_name},
        )
    source, inputs = _planning_inputs(session, project_id, source_revision_id)
    service = EngineeringPlanningService(provider=DeterministicPlanningProvider())
    result = service.generate(
        _requirement_model(requirement),
        source_revision_id=UUID(source.id) if source is not None else None,
        source_revision=_record_dict(source) if source is not None else None,
        **inputs,
        created_by=created_by,
        supersedes_plan_id=supersedes_plan_id,
    )
    if revision != result.plan.revision:
        result = PlanningResult(
            plan=result.plan.model_copy(update={"revision": revision}),
            context=result.context,
            validation=result.validation,
        )
    _save_context(session, result)
    record = _save_plan(session, result)
    requirement.status = (
        EngineeringRequirementStatus.NEEDS_INPUT.value
        if result.plan.status is EngineeringPlanStatus.NEEDS_INPUT
        else EngineeringRequirementStatus.PLANNED.value
    )
    requirement.revision += 1
    requirement.updated_at = utc_now()
    return result, record


def _refresh_staleness(
    session: Session,
    request: Request,
    principal: AuthenticatedPrincipal,
    record: EngineeringPlanRecord,
) -> bool:
    if record.status in {
        EngineeringPlanStatus.STALE.value,
        EngineeringPlanStatus.SUPERSEDED.value,
    }:
        return False
    reasons: list[str] = []
    latest_source = _source_revision(session, UUID(record.project_id), None)
    if (
        record.source_revision_id is not None
        and latest_source is not None
        and record.source_revision_id != latest_source.id
    ):
        reasons.append("SOURCE_REVISION_CHANGED")
    context = session.get(PlanningContextSnapshotRecord, record.context_snapshot_id)
    if context is not None:
        claim_ids = list((context.claim_revisions or {}).keys())
        if claim_ids:
            current = {
                str(row.id): int(row.revision)
                for row in session.scalars(
                    select(EngineeringClaimRecord).where(EngineeringClaimRecord.id.in_(claim_ids))
                )
            }
            if any(current.get(key) != value for key, value in context.claim_revisions.items()):
                reasons.append("CLAIM_REVISION_CHANGED")
            if session.scalar(
                select(ClaimConflictRecord.id).where(
                    or_(
                        ClaimConflictRecord.claim_a_id.in_(claim_ids),
                        ClaimConflictRecord.claim_b_id.in_(claim_ids),
                    ),
                    ClaimConflictRecord.status == "OPEN",
                )
            ):
                reasons.append("CLAIM_CONFLICT_OPEN")
        evidence_ids = list((context.evidence_revisions or {}).keys())
        if evidence_ids:
            current_evidence = {
                str(row.id): int(row.revision)
                for row in session.scalars(
                    select(EvidenceRecord).where(EvidenceRecord.id.in_(evidence_ids))
                )
            }
            if any(
                current_evidence.get(key) != value
                for key, value in context.evidence_revisions.items()
            ):
                reasons.append("EVIDENCE_REVISION_CHANGED")
    if not reasons:
        return False
    before = {"status": record.status, "revision": record.revision}
    record.status = EngineeringPlanStatus.STALE.value
    record.revision += 1
    record.updated_at = utc_now()
    metadata = dict(record.entity_metadata or {})
    metadata["stale_reasons"] = sorted(set(reasons))
    record.entity_metadata = metadata
    _audit(
        session,
        request,
        principal,
        project_id=UUID(record.project_id),
        requirement_id=UUID(record.requirement_id),
        plan_id=UUID(record.id),
        action="plan.stale",
        reason="authoritative context no longer matches the planning snapshot",
        before=before,
        after={"status": record.status, "revision": record.revision, "reasons": reasons},
    )
    return True


@router.post(
    "/projects/{project_id}/engineering-requirements",
    response_model=ApiEnvelope[dict[str, object]],
    status_code=status.HTTP_201_CREATED,
    tags=["m24a-planning"],
)
def create_requirement(
    project_id: UUID,
    payload: RequirementCreateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[dict[str, object]]:
    principal = _authorize_project(request, session, project_id, action="write")
    if payload.source_revision_id is not None:
        _source_revision(session, project_id, payload.source_revision_id)
    now = utc_now()
    source = dict(payload.source)
    if payload.source_revision_id is not None:
        source["source_revision_id"] = str(payload.source_revision_id)
    record = EngineeringRequirementRecord(
        id=str(uuid4()),
        schema_version="1.0",
        revision=1,
        created_at=now,
        updated_at=now,
        entity_metadata={"m24a_plan_only": True},
        project_id=str(project_id),
        title=payload.title,
        description=payload.description,
        requirement_type=payload.requirement_type.value,
        priority=payload.priority.value,
        constraints=list(payload.constraints),
        acceptance_criteria=list(payload.acceptance_criteria),
        source=source,
        created_by=principal.actor_id,
        status=EngineeringRequirementStatus.DRAFT.value,
    )
    session.add(record)
    session.flush()
    _audit(
        session,
        request,
        principal,
        project_id=project_id,
        requirement_id=UUID(record.id),
        action="requirement.create",
        reason="server-owned M24A engineering requirement intake",
        after=_requirement_data(record),
    )
    session.commit()
    return ApiEnvelope(data=_requirement_data(record), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/engineering-requirements",
    response_model=ApiEnvelope[list[dict[str, object]]],
    tags=["m24a-planning"],
)
def list_requirements(
    project_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[list[dict[str, object]]]:
    _authorize_project(request, session, project_id)
    records = session.scalars(
        select(EngineeringRequirementRecord)
        .where(EngineeringRequirementRecord.project_id == str(project_id))
        .order_by(EngineeringRequirementRecord.created_at.desc())
    )
    return ApiEnvelope(
        data=[_requirement_data(record) for record in records], request_id=_request_id(request)
    )


@router.get(
    "/engineering-requirements/{requirement_id}",
    response_model=ApiEnvelope[dict[str, object]],
    tags=["m24a-planning"],
)
def get_requirement(
    requirement_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[dict[str, object]]:
    record = _requirement_record(session, requirement_id)
    _authorize_project(request, session, UUID(record.project_id))
    return ApiEnvelope(data=_requirement_data(record), request_id=_request_id(request))


@router.patch(
    "/engineering-requirements/{requirement_id}",
    response_model=ApiEnvelope[dict[str, object]],
    tags=["m24a-planning"],
)
def update_requirement(
    requirement_id: UUID,
    payload: RequirementUpdateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[dict[str, object]]:
    record = _requirement_record(session, requirement_id)
    principal = _authorize_project(request, session, UUID(record.project_id), action="write")
    _check_revision(record, payload.expected_revision)
    before = _requirement_data(record)
    updates = payload.model_dump(exclude_unset=True)
    updates.pop("expected_revision", None)
    source_revision_id = updates.pop("source_revision_id", None)
    if source_revision_id is not None:
        _source_revision(session, UUID(record.project_id), source_revision_id)
        updates.setdefault("source", dict(record.source or {}))
        updates["source"]["source_revision_id"] = str(source_revision_id)
    for key, value in updates.items():
        if isinstance(value, StrEnum):
            value = value.value
        setattr(record, key, value)
    record.revision += 1
    record.updated_at = utc_now()
    _audit(
        session,
        request,
        principal,
        project_id=UUID(record.project_id),
        requirement_id=requirement_id,
        action="requirement.update",
        reason="optimistic-concurrency guarded requirement update",
        before=before,
        after=_requirement_data(record),
    )
    session.commit()
    return ApiEnvelope(data=_requirement_data(record), request_id=_request_id(request))


@router.post(
    "/engineering-requirements/{requirement_id}/plans",
    response_model=ApiEnvelope[dict[str, object]],
    status_code=status.HTTP_201_CREATED,
    tags=["m24a-planning"],
)
def create_plan(
    requirement_id: UUID,
    payload: PlanCreateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[dict[str, object]]:
    requirement = _requirement_record(session, requirement_id)
    principal = _authorize_project(request, session, UUID(requirement.project_id), action="write")
    if payload.supersedes_plan_id is not None:
        superseded = _plan_record(session, payload.supersedes_plan_id)
        if superseded.project_id != requirement.project_id:
            raise EngineeringError(
                EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
                "A plan revision must remain within the requirement project",
                details={"plan_id": str(payload.supersedes_plan_id)},
            )
    before = {
        "requirement_status": requirement.status,
        "requirement_revision": requirement.revision,
    }
    _audit(
        session,
        request,
        principal,
        project_id=UUID(requirement.project_id),
        requirement_id=requirement_id,
        action="planning.start",
        reason="deterministic bounded context assembly requested",
        before=before,
        after={
            "provider": payload.provider,
            "source_revision_id": (
                str(payload.source_revision_id) if payload.source_revision_id else None
            ),
        },
    )
    result, record = _create_plan(
        session,
        UUID(requirement.project_id),
        requirement,
        source_revision_id=payload.source_revision_id,
        provider_name=payload.provider,
        created_by=principal.actor_id,
        supersedes_plan_id=payload.supersedes_plan_id,
    )
    _audit(
        session,
        request,
        principal,
        project_id=UUID(requirement.project_id),
        requirement_id=requirement_id,
        plan_id=UUID(record.id),
        action="plan.generated",
        reason="structured M24A plan persisted without execution authority",
        after={
            "status": result.plan.status.value,
            "revision": result.plan.revision,
            "plan_only": True,
        },
    )
    session.commit()
    return ApiEnvelope(data=_plan_data(session, record), request_id=_request_id(request))


@router.get(
    "/engineering-plans/{plan_id}",
    response_model=ApiEnvelope[dict[str, object]],
    tags=["m24a-planning"],
)
def get_plan(
    plan_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[dict[str, object]]:
    record = _plan_record(session, plan_id)
    principal = _authorize_project(request, session, UUID(record.project_id))
    if _refresh_staleness(session, request, principal, record):
        session.commit()
    return ApiEnvelope(data=_plan_data(session, record), request_id=_request_id(request))


@router.get(
    "/engineering-plans/{plan_id}/context",
    response_model=ApiEnvelope[dict[str, object]],
    tags=["m24a-planning"],
)
def get_plan_context(
    plan_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[dict[str, object]]:
    plan = _plan_record(session, plan_id)
    _authorize_project(request, session, UUID(plan.project_id))
    context = _context_record(session, UUID(plan.context_snapshot_id))
    return ApiEnvelope(data=_context_data(context), request_id=_request_id(request))


@router.get(
    "/engineering-plans/{plan_id}/impact",
    response_model=ApiEnvelope[dict[str, object]],
    tags=["m24a-planning"],
)
def get_plan_impact(
    plan_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[dict[str, object]]:
    plan = _plan_record(session, plan_id)
    _authorize_project(request, session, UUID(plan.project_id))
    model = _plan_model(session, plan)
    direct = [
        {
            "change_id": str(change.id),
            "target_kind": change.target_kind.value,
            "target_ref": change.target_ref,
            "impact": change.impact,
            "risk": change.risk.value,
        }
        for change in model.proposed_changes
    ]
    seeds = {change.target_ref for change in model.proposed_changes}
    edges = list(
        session.scalars(
            select(EngineeringDependencyEdgeRecord).where(
                EngineeringDependencyEdgeRecord.project_id == plan.project_id
            )
        )
    )
    adjacency: dict[str, set[str]] = {}
    edge_data: list[dict[str, object]] = []
    for edge in edges:
        adjacency.setdefault(edge.upstream_id, set()).add(edge.downstream_id)
        adjacency.setdefault(edge.downstream_id, set()).add(edge.upstream_id)
        if edge.upstream_id in seeds or edge.downstream_id in seeds:
            edge_data.append(_record_dict(edge))
    transitive: set[str] = set()
    frontier = list(seeds)
    while frontier and len(transitive) < 200:
        node = frontier.pop(0)
        for neighbour in sorted(adjacency.get(node, set())):
            if neighbour not in seeds and neighbour not in transitive:
                transitive.add(neighbour)
                frontier.append(neighbour)
    stale_states = list(
        session.scalars(
            select(EngineeringDependencyNodeStateRecord).where(
                EngineeringDependencyNodeStateRecord.project_id == plan.project_id,
                EngineeringDependencyNodeStateRecord.status.in_(["STALE", "INVALID"]),
            )
        )
    )
    data = {
        "plan_id": str(plan.id),
        "direct_impact": direct,
        "transitive_impact": sorted(transitive),
        "affected_components": list(model.affected_components),
        "dependency_edges": edge_data,
        "stale_dependencies": [_record_dict(item) for item in stale_states],
        "verification_impact": [item.model_dump(mode="json") for item in model.verification_plans],
        "plan_only": True,
    }
    return ApiEnvelope(data=data, request_id=_request_id(request))


@router.post(
    "/engineering-plans/{plan_id}/review",
    response_model=ApiEnvelope[dict[str, object]],
    tags=["m24a-planning"],
)
def review_plan(
    plan_id: UUID,
    payload: PlanReviewRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[dict[str, object]]:
    plan = _plan_record(session, plan_id)
    principal = _authorize_project(request, session, UUID(plan.project_id), action="review")
    _check_revision(plan, payload.expected_revision)
    if _refresh_staleness(session, request, principal, plan):
        session.commit()
        raise EngineeringError(
            EngineeringErrorCode.REVISION_CONFLICT,
            "The plan became stale while it was being reviewed",
            details={
                "plan_id": str(plan_id),
                "current_status": plan.status,
                "current_revision": plan.revision,
            },
        )
    before = {"status": plan.status, "revision": plan.revision}
    if payload.action is PlanReviewAction.APPROVE:
        if plan.status != EngineeringPlanStatus.READY_FOR_REVIEW.value:
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR,
                "Only a complete READY_FOR_REVIEW plan may be approved",
                details={"status": plan.status},
            )
        if plan.validation_issues or plan.quality_issues:
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR,
                "A plan with validation or quality issues cannot be approved",
                details={
                    "validation_issues": plan.validation_issues,
                    "quality_issues": plan.quality_issues,
                },
            )
        plan.status = EngineeringPlanStatus.APPROVED.value
        review_status = PlanReviewStatus.APPROVED.value
    elif payload.action is PlanReviewAction.REJECT:
        plan.status = EngineeringPlanStatus.REJECTED.value
        review_status = PlanReviewStatus.REJECTED.value
    else:
        old_requirement = _requirement_record(session, UUID(plan.requirement_id))
        _result, new_record = _create_plan(
            session,
            UUID(plan.project_id),
            old_requirement,
            source_revision_id=UUID(plan.source_revision_id) if plan.source_revision_id else None,
            provider_name="deterministic",
            created_by=principal.actor_id,
            supersedes_plan_id=plan_id,
            revision=plan.revision + 1,
        )
        plan.status = EngineeringPlanStatus.SUPERSEDED.value
        review_status = PlanReviewStatus.REVISION_REQUESTED.value
        plan.revision += 1
        plan.updated_at = utc_now()
        session.add(
            EngineeringPlanReviewRecord(
                id=str(uuid4()),
                schema_version="1.0",
                revision=1,
                created_at=utc_now(),
                updated_at=utc_now(),
                entity_metadata={},
                plan_id=str(plan.id),
                action=payload.action.value,
                status=review_status,
                expected_plan_revision=payload.expected_revision,
                comment=payload.comment,
                reviewed_by=principal.actor_id,
                execution_authorized=False,
            )
        )
        _audit(
            session,
            request,
            principal,
            project_id=UUID(plan.project_id),
            requirement_id=UUID(plan.requirement_id),
            plan_id=plan_id,
            action="plan.revision_requested",
            reason="reviewer requested a new plan revision; no change was executed",
            before=before,
            after={"status": plan.status, "revision": plan.revision, "new_plan_id": new_record.id},
        )
        session.commit()
        return ApiEnvelope(
            data={
                "review_status": review_status,
                "plan": _plan_data(session, new_record),
                "superseded_plan_id": str(plan_id),
                "execution_authorized": False,
            },
            request_id=_request_id(request),
        )
    plan.revision += 1
    plan.updated_at = utc_now()
    session.add(
        EngineeringPlanReviewRecord(
            id=str(uuid4()),
            schema_version="1.0",
            revision=1,
            created_at=utc_now(),
            updated_at=utc_now(),
            entity_metadata={},
            plan_id=str(plan.id),
            action=payload.action.value,
            status=review_status,
            expected_plan_revision=payload.expected_revision,
            comment=payload.comment,
            reviewed_by=principal.actor_id,
            execution_authorized=False,
        )
    )
    _audit(
        session,
        request,
        principal,
        project_id=UUID(plan.project_id),
        requirement_id=UUID(plan.requirement_id),
        plan_id=plan_id,
        action="plan.review",
        reason="human review recorded; M24A never grants execution authority",
        before=before,
        after={"status": plan.status, "revision": plan.revision, "execution_authorized": False},
    )
    session.commit()
    return ApiEnvelope(
        data={
            "review_status": review_status,
            "plan": _plan_data(session, plan),
            "execution_authorized": False,
        },
        request_id=_request_id(request),
    )


@router.post(
    "/engineering-plans/{plan_id}/comments",
    response_model=ApiEnvelope[dict[str, object]],
    status_code=status.HTTP_201_CREATED,
    tags=["m24a-planning"],
)
def comment_plan(
    plan_id: UUID,
    payload: PlanCommentRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[dict[str, object]]:
    plan = _plan_record(session, plan_id)
    principal = _authorize_project(request, session, UUID(plan.project_id), action="review")
    now = utc_now()
    comment = EngineeringPlanReviewCommentRecord(
        id=str(uuid4()),
        schema_version="1.0",
        revision=1,
        created_at=now,
        updated_at=now,
        entity_metadata={},
        plan_id=str(plan.id),
        target_kind=payload.target_kind,
        target_ref=payload.target_ref,
        body=payload.body,
        created_by=principal.actor_id,
    )
    session.add(comment)
    _audit(
        session,
        request,
        principal,
        project_id=UUID(plan.project_id),
        requirement_id=UUID(plan.requirement_id),
        plan_id=plan_id,
        action="plan.comment",
        reason="human review comment appended to the plan audit trail",
        after={
            "comment_id": comment.id,
            "target_kind": payload.target_kind,
            "target_ref": payload.target_ref,
        },
    )
    session.commit()
    return ApiEnvelope(data=_record_dict(comment), request_id=_request_id(request))


__all__ = ["router"]
