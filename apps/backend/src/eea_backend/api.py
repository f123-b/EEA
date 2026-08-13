"""M1 versioned API routes."""

import re
from base64 import b64decode
from binascii import Error as Base64Error
from collections.abc import Iterator
from typing import Annotated, Any, cast
from uuid import UUID, uuid4

from eea_adapters.devices import Stm32G431FixtureProvider
from eea_application.ai import PromptRegistry, StructuredGenerationService
from eea_application.architecture import ArchitectureService
from eea_application.circuit import CircuitService
from eea_application.components import ComponentMaterializer, ComponentRegistryService
from eea_application.dependency_graph import DependencyGraphService
from eea_application.domains import DomainExtensionService
from eea_application.firmware import FirmwareBuildService, FirmwareService
from eea_application.intelligence import DocumentService, MultiSourceDeviceProvider
from eea_application.mcu_config import MCUConfigService
from eea_application.pin_planner import PinPlannerService
from eea_application.projects import ProjectService
from eea_application.protocol import ProtocolGenerationError, ProtocolGenerator
from eea_application.reliability import CrashPoint, EventOutboxService
from eea_application.requirements import (
    RequirementAnalysisService,
    RequirementProfileRegistry,
)
from eea_application.review import ReviewEngine, TestCoverageService
from eea_application.schematic import SchematicService
from eea_application.static_analysis import FirmwareStaticAnalysisService
from eea_application.testing import TestGenerationService, TestRunService
from eea_core.architecture import ArchitectureBundle
from eea_core.build import BuildRun
from eea_core.circuit import CircuitBundle
from eea_core.components import (
    ComponentMaterialization,
    DependencyLock,
    SoftwareComponentDescriptor,
)
from eea_core.entities import Evidence, Project, TraceabilityEdge, utc_now
from eea_core.enums import (
    ArtifactStatus,
    ChangeObservation,
    ClaimConflictStatus,
    ClaimConflictStrategy,
    ClaimConflictType,
    ClaimLifecycle,
    DecisionStatus,
    DependencyKind,
    DependencyNodeStatus,
    DeviceCategory,
    DeviceMergeConflictType,
    DocumentParseStatus,
    DocumentType,
    DomainActivationStatus,
    EngineeringDimension,
    EngineeringErrorCode,
    EvidenceType,
    ImpactAction,
    InvalidationPolicy,
    IssueSeverity,
    IssueStatus,
    JobStatus,
    Permission,
    ProjectStatus,
    RequirementFieldStatus,
    RequirementPriority,
    RequirementStatus,
    RequirementType,
    RequirementValueType,
    StaticAnalysisStatus,
    TraceabilityRelation,
    VerificationLevel,
)
from eea_core.errors import EngineeringError
from eea_core.firmware import FirmwareBundle
from eea_core.intelligence import Device, DevicePin, Document
from eea_core.mcu_config import MCUConfigBundle
from eea_core.pin_planner import PinAssignment, PinLock, PinPlan, PinRequirement
from eea_core.protocol import ProtocolGenerationBundle, ProtocolIR, ProtocolValidationResult
from eea_core.reliability import OutboxEventStatus, payload_sha256, stable_event_key
from eea_core.requirements import RequirementProfile
from eea_core.review import ReviewPolicy, ReviewRun
from eea_core.schema_registry import create_core_schema_registry
from eea_core.schematic import SchematicBundle
from eea_core.static_analysis import FirmwareStaticAnalysis
from eea_core.testing import (
    AutomationLevel,
    TestExecutionStatus,
    TestIR,
    TestRun,
    TestType,
)
from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from eea_backend.architecture_repositories import SqlAlchemyArchitectureRepository
from eea_backend.build_repositories import SqlAlchemyBuildRunRepository
from eea_backend.circuit_repositories import SqlAlchemyCircuitRepository
from eea_backend.claim_repositories import SqlAlchemyEngineeringClaimRepository
from eea_backend.component_repositories import (
    SqlAlchemyComponentMaterializationRepository,
    SqlAlchemyComponentRepository,
    SqlAlchemyDependencyLockRepository,
)
from eea_backend.dependency_providers import build_dependency_provider_registry
from eea_backend.dependency_repositories import SqlAlchemyDependencyGraphRepository
from eea_backend.document_repositories import SqlAlchemyDocumentRepository
from eea_backend.domain_repositories import SqlAlchemyDomainActivationRepository
from eea_backend.firmware_repositories import SqlAlchemyFirmwareRepository
from eea_backend.m17_repositories import (
    SqlAlchemyIssueRepository,
    SqlAlchemyReviewRepository,
    SqlAlchemyTestRepository,
    SqlAlchemyTraceabilityRepository,
)
from eea_backend.mcu_config_repositories import SqlAlchemyMCUConfigRepository
from eea_backend.models import (
    ArtifactRecord,
    GeneratedProtocolOutputRecord,
    JobRecord,
    SideEffectJournalRecord,
)
from eea_backend.pin_planner_repositories import SqlAlchemyPinPlanRepository
from eea_backend.protocol_repositories import SqlAlchemyProtocolRepository
from eea_backend.recovery import RecoveryService
from eea_backend.reliability_repositories import SqlAlchemyOutboxRepository
from eea_backend.repositories import (
    SqlAlchemyAIUsageRepository,
    SqlAlchemyArtifactRepository,
    SqlAlchemyEvidenceRepository,
    SqlAlchemyProjectRepository,
    SqlAlchemyPromptRepository,
)
from eea_backend.requirement_repositories import (
    SqlAlchemyRequirementAnalysisRepository,
    SqlAlchemyRequirementProfileRepository,
    SqlAlchemyRequirementRepository,
    persist_requirement_analysis_bundle,
)
from eea_backend.schemas import (
    ApiEnvelope,
    ArchitectureBundleData,
    ArchitectureGenerateRequest,
    ArtifactData,
    ArtifactDependenciesData,
    ArtifactListData,
    ArtifactRevalidateData,
    ArtifactRevalidateRequest,
    BuildListData,
    BuildRequest,
    BuildRunData,
    CircuitBundleData,
    CircuitGenerateRequest,
    CircuitValidateRequest,
    CircuitValidationData,
    ClaimLifecycleMutationRequest,
    ComponentCatalogData,
    ComponentDetailData,
    ComponentMaterializationData,
    ComponentMaterializeRequest,
    ComponentReleaseData,
    ComponentResolveRequest,
    CoverageData,
    DependencyEdgeData,
    DependencyListData,
    DependencyLockData,
    DependencyNodeStateData,
    DeviceData,
    DevicePinData,
    DevicePinQueryData,
    DocumentData,
    DocumentUploadRequest,
    DomainActivationData,
    DomainActivationListData,
    DomainActivationRequest,
    DomainArtifactsData,
    DomainAvailableData,
    DomainAvailableListData,
    DomainCompositionData,
    DomainDescriptorData,
    DomainSchemaData,
    DomainUIExtensionsData,
    DomainValidationRequest,
    EnumCatalogData,
    EnumValues,
    ErcImportRequest,
    EvidenceCreateRequest,
    EvidenceData,
    FirmwareBundleData,
    FirmwareGenerateRequest,
    FirmwareStaticAnalysisData,
    ImpactAnalysisData,
    IssueData,
    IssueListData,
    IssueMutationRequest,
    MCUConfigBundleData,
    MCUConfigGenerateRequest,
    MCUConfigValidateRequest,
    MCUConfigValidationData,
    OutboxStatusData,
    PinAssignmentData,
    PinAssignmentMutationData,
    PinAssignmentMutationRequest,
    PinLockData,
    PinPlanData,
    PinPlannerGenerateRequest,
    PinPlanValidationData,
    PinPlanValidationRequest,
    ProjectCreate,
    ProjectData,
    ProjectListData,
    ProjectUpdate,
    ProtocolCreateRequest,
    ProtocolGenerateRequest,
    ProtocolUpdateRequest,
    ProtocolValidateRequest,
    RecoveryReconcileData,
    RecoveryReconcileRequest,
    RecoveryStatusData,
    RequirementAnalysisData,
    RequirementData,
    RequirementNaturalLanguageAnalysisRequest,
    RequirementProfileData,
    RequirementStructuredAnalysisRequest,
    RequirementUpdateRequest,
    ReviewListData,
    ReviewRequest,
    SchemaData,
    SchemaDescriptorData,
    SchemaListData,
    SchematicBundleData,
    SchematicGenerateRequest,
    SchematicValidateRequest,
    SoftwareComponentData,
    StaticAnalysisListData,
    StaticAnalysisRequest,
    TestCaseListData,
    TestGenerateRequest,
    TestGenerationData,
    TestIRListData,
    TestRunListData,
    TestRunRequest,
    TraceabilityData,
)
from eea_backend.schematic_repositories import SqlAlchemySchematicRepository
from eea_backend.static_analysis_repositories import SqlAlchemyFirmwareStaticAnalysisRepository

router = APIRouter()
schema_registry = create_core_schema_registry()
device_provider = MultiSourceDeviceProvider([Stm32G431FixtureProvider()])
ETAG_PATTERN = re.compile(r'^(?:W/)?"(?P<revision>[1-9][0-9]*)"$')


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


SessionDependency = Annotated[Session, Depends(get_session)]


def _service(session: Session) -> ProjectService:
    return ProjectService(SqlAlchemyProjectRepository(session))


def _recovery_service(request: Request) -> RecoveryService:
    return RecoveryService(
        lambda: Session(request.app.state.engine),
        crash_injector=request.app.state.crash_injector,
    )


def _project_data(project: Project) -> ProjectData:
    return ProjectData.model_validate(project, from_attributes=True)


def _document_data(document: Document) -> DocumentData:
    return DocumentData.model_validate(document.model_dump(mode="json"))


def _evidence_data(evidence: Evidence) -> EvidenceData:
    return EvidenceData.model_validate(evidence.model_dump(mode="json"))


def _artifact_data(artifact: object, session: Session | None = None) -> ArtifactData:
    payload = artifact.model_dump(mode="json") if hasattr(artifact, "model_dump") else artifact
    if session is not None and isinstance(payload, dict):
        state = SqlAlchemyDependencyGraphRepository(session).get_node_state(
            UUID(str(payload["project_id"])), "Artifact", str(payload["id"])
        )
        if state is not None:
            stored = ArtifactStatus(payload["status"])
            if stored in {ArtifactStatus.DEPRECATED, ArtifactStatus.ARCHIVED}:
                return ArtifactData.model_validate(payload)
            projected = {
                DependencyNodeStatus.CURRENT: ArtifactStatus.CURRENT,
                DependencyNodeStatus.STALE: ArtifactStatus.STALE,
                DependencyNodeStatus.INVALID: ArtifactStatus.INVALID,
            }.get(state.status)
            if projected is not None:
                precedence = {
                    ArtifactStatus.CURRENT: 0,
                    ArtifactStatus.STALE: 1,
                    ArtifactStatus.INVALID: 2,
                }
                if precedence[projected] > precedence[stored]:
                    payload = {**payload, "status": projected.value}
    return ArtifactData.model_validate(payload)


def _dependency_service(session: Session) -> DependencyGraphService:
    return DependencyGraphService(
        SqlAlchemyDependencyGraphRepository(session),
        build_dependency_provider_registry(session),
    )


def _dependency_edge_data(edge: object) -> object:
    return {"edge": edge}


@router.get(
    "/system/outbox/status",
    response_model=ApiEnvelope[OutboxStatusData],
    tags=["system", "reliability"],
)
def outbox_status(request: Request, session: SessionDependency) -> ApiEnvelope[OutboxStatusData]:
    rows = SqlAlchemyOutboxRepository(session).list()
    counts = {
        status: sum(item.status.value == status for item in rows)
        for status in ("PENDING", "PROCESSING", "RETRY", "PROCESSED", "DEAD_LETTER")
    }
    data = OutboxStatusData(
        pending=counts["PENDING"],
        processing=counts["PROCESSING"],
        retry=counts["RETRY"],
        processed=counts["PROCESSED"],
        dead_letter=counts["DEAD_LETTER"],
        total=len(rows),
    )
    return ApiEnvelope(data=data, request_id=_request_id(request))


@router.get(
    "/system/recovery/status",
    response_model=ApiEnvelope[RecoveryStatusData],
    tags=["system", "reliability"],
)
def recovery_status(
    request: Request, session: SessionDependency
) -> ApiEnvelope[RecoveryStatusData]:
    rows = SqlAlchemyOutboxRepository(session).list()
    reconcile_required = sum(
        1
        for row in session.scalars(
            select(SideEffectJournalRecord).where(
                SideEffectJournalRecord.status == "RECONCILE_REQUIRED"
            )
        )
    )
    interrupted_jobs = sum(
        1
        for row in session.scalars(
            select(JobRecord).where(JobRecord.status == JobStatus.FAILED_NEEDS_RECONCILE.value)
        )
    )
    data = RecoveryStatusData(
        status="RECOVERY_REQUIRED"
        if any(item.status is not OutboxEventStatus.PROCESSED for item in rows)
        or reconcile_required > 0
        or interrupted_jobs > 0
        else "CLEAN",
        pending=sum(item.status is OutboxEventStatus.PENDING for item in rows),
        retry=sum(item.status is OutboxEventStatus.RETRY for item in rows),
        dead_letter=sum(item.status is OutboxEventStatus.DEAD_LETTER for item in rows),
        reconcile_required=reconcile_required,
        interrupted_jobs=interrupted_jobs,
    )
    return ApiEnvelope(data=data, request_id=_request_id(request))


@router.post(
    "/system/recovery/reconcile",
    response_model=ApiEnvelope[RecoveryReconcileData],
    tags=["system", "reliability"],
)
def reconcile_recovery(
    payload: RecoveryReconcileRequest,
    request: Request,
) -> ApiEnvelope[RecoveryReconcileData]:
    service = _recovery_service(request)
    reclaimed = service.recover_expired_outbox_leases(limit=payload.limit)
    dispatched = service.dispatch_ready_events(limit=payload.limit)
    reconcile_required = service.reconcile_side_effects(limit=payload.limit)
    project = None
    if payload.project_id is not None:
        status_data = service.reconcile_project(payload.project_id)
        project = RecoveryStatusData.model_validate(status_data)
    return ApiEnvelope(
        data=RecoveryReconcileData(
            reclaimed=reclaimed,
            dispatched=dispatched,
            reconcile_required=reconcile_required,
            project=project,
        ),
        request_id=_request_id(request),
    )


@router.get(
    "/projects/{project_id}/consistency",
    response_model=ApiEnvelope[RecoveryStatusData],
    tags=["projects", "reliability"],
)
def project_consistency(
    project_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[RecoveryStatusData]:
    _service(session).get(project_id)
    data = RecoveryStatusData.model_validate(
        _recovery_service(request).reconcile_project(project_id)
    )
    return ApiEnvelope(data=data, request_id=_request_id(request))


@router.post(
    "/claims/{claim_id}/lifecycle",
    response_model=ApiEnvelope[dict[str, object]],
    tags=["claims", "dependency-graph"],
)
def mutate_claim_lifecycle(
    claim_id: UUID,
    payload: ClaimLifecycleMutationRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[dict[str, object]]:
    _service(session).get(payload.project_id)
    claims = SqlAlchemyEngineeringClaimRepository(session)
    claim = claims.get(claim_id)
    if claim is None or (claim.project_id is not None and claim.project_id != payload.project_id):
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Claim is not available for this project",
        )
    if claim.project_id is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Global Claim lifecycle mutation requires the authoritative internal path",
        )
    if claim.revision != payload.expected_revision:
        raise EngineeringError(
            EngineeringErrorCode.REVISION_CONFLICT, "Claim revision does not match"
        )
    before = build_dependency_provider_registry(session).resolve(
        payload.project_id, "Claim", str(claim_id)
    )
    updated = claim.model_copy(
        update={
            "lifecycle": payload.lifecycle,
            "revision": claim.revision + 1,
            "updated_at": utc_now(),
        }
    )
    saved = claims.save(updated, expected_revision=claim.revision, commit=False)
    if saved is None:
        raise EngineeringError(
            EngineeringErrorCode.REVISION_CONFLICT, "Claim changed during update"
        )
    after = build_dependency_provider_registry(session).resolve(
        payload.project_id, "Claim", str(claim_id)
    )
    plan = _dependency_service(session).propagate(payload.project_id, before, after, commit=False)
    session.commit()
    return ApiEnvelope(
        data={"claim": saved.model_dump(mode="json"), "impact_plan": plan.model_dump(mode="json")},
        request_id=_request_id(request),
    )


@router.patch(
    "/projects/{project_id}/requirements/{requirement_id}",
    response_model=ApiEnvelope[RequirementData],
    tags=["requirements", "dependency-graph"],
)
def update_requirement(
    project_id: UUID,
    requirement_id: UUID,
    payload: RequirementUpdateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[RequirementData]:
    _service(session).get(project_id)
    repository = SqlAlchemyRequirementRepository(session)
    current = repository.get(requirement_id, project_id=project_id)
    if current is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Requirement is not available for this project",
            details={"requirement_id": str(requirement_id), "project_id": str(project_id)},
        )
    if current.revision != payload.expected_revision:
        raise EngineeringError(
            EngineeringErrorCode.REVISION_CONFLICT,
            "Requirement revision does not match the requested optimistic-concurrency revision",
        )
    before = build_dependency_provider_registry(session).resolve(
        project_id, "Requirement", str(requirement_id)
    )
    snapshot = current.model_dump(mode="json")
    snapshot.update(payload.model_dump(exclude={"expected_revision"}, exclude_unset=True))
    snapshot["revision"] = current.revision + 1
    snapshot["updated_at"] = utc_now()
    updated = current.__class__.model_validate(snapshot)
    saved = repository.save(updated, expected_revision=current.revision, commit=False)
    if saved is None:
        raise EngineeringError(
            EngineeringErrorCode.REVISION_CONFLICT,
            "Requirement changed during update",
        )
    after = build_dependency_provider_registry(session).resolve(
        project_id, "Requirement", str(requirement_id)
    )
    _dependency_service(session).propagate(project_id, before, after, commit=False)
    session.commit()
    return ApiEnvelope(
        data=RequirementData.model_validate(saved.model_dump(mode="json")),
        request_id=_request_id(request),
    )


@router.post(
    "/entities/{entity_type}/{entity_id}/impact-analysis",
    response_model=ApiEnvelope[ImpactAnalysisData],
    tags=["dependency-graph"],
)
def dependency_impact_analysis(
    entity_type: str,
    entity_id: str,
    request: Request,
    project_id: UUID,
    session: SessionDependency,
) -> ApiEnvelope[ImpactAnalysisData]:
    _service(session).get(project_id)
    if not _dependency_service(session).providers.supports(entity_type):
        raise EngineeringError(
            EngineeringErrorCode.CAPABILITY_UNAVAILABLE,
            "Dependency node type is not registered",
            details={"entity_type": entity_type},
        )
    plan = _dependency_service(session).impact_analysis(project_id, entity_type, entity_id)
    return ApiEnvelope(data=ImpactAnalysisData(plan=plan), request_id=_request_id(request))


@router.get(
    "/entities/{entity_type}/{entity_id}/dependencies",
    response_model=ApiEnvelope[DependencyListData],
    tags=["dependency-graph"],
)
def entity_dependencies(
    entity_type: str,
    entity_id: str,
    project_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DependencyListData]:
    _service(session).get(project_id)
    service = _dependency_service(session)
    if not service.providers.supports(entity_type):
        raise EngineeringError(
            EngineeringErrorCode.CAPABILITY_UNAVAILABLE,
            "Dependency node type is not registered",
            details={"entity_type": entity_type},
        )
    repository = SqlAlchemyDependencyGraphRepository(session)
    items = [
        DependencyEdgeData(edge=edge)
        for edge in repository.list_dependencies(project_id, entity_type, entity_id)
    ]
    return ApiEnvelope(data=DependencyListData(items=items), request_id=_request_id(request))


@router.get(
    "/entities/{entity_type}/{entity_id}/dependents",
    response_model=ApiEnvelope[DependencyListData],
    tags=["dependency-graph"],
)
def entity_dependents(
    entity_type: str,
    entity_id: str,
    project_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DependencyListData]:
    _service(session).get(project_id)
    service = _dependency_service(session)
    if not service.providers.supports(entity_type):
        raise EngineeringError(
            EngineeringErrorCode.CAPABILITY_UNAVAILABLE,
            "Dependency node type is not registered",
            details={"entity_type": entity_type},
        )
    repository = SqlAlchemyDependencyGraphRepository(session)
    items = [
        DependencyEdgeData(edge=edge)
        for edge in repository.list_dependents(project_id, entity_type, entity_id)
    ]
    return ApiEnvelope(data=DependencyListData(items=items), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/artifacts",
    response_model=ApiEnvelope[ArtifactListData],
    tags=["artifacts"],
)
def list_artifacts(
    project_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[ArtifactListData]:
    _service(session).get(project_id)
    artifacts = SqlAlchemyArtifactRepository(session).list_for_project(project_id)
    return ApiEnvelope(
        data=ArtifactListData(items=[_artifact_data(item, session) for item in artifacts]),
        request_id=_request_id(request),
    )


@router.get(
    "/artifacts/{artifact_id}",
    response_model=ApiEnvelope[ArtifactData],
    tags=["artifacts"],
)
def get_artifact(
    artifact_id: UUID,
    project_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[ArtifactData]:
    _service(session).get(project_id)
    artifact = SqlAlchemyArtifactRepository(session).get(artifact_id, project_id=project_id)
    if artifact is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Artifact is not available for this project",
        )
    return ApiEnvelope(data=_artifact_data(artifact, session), request_id=_request_id(request))


@router.get(
    "/artifacts/{artifact_id}/versions",
    response_model=ApiEnvelope[ArtifactListData],
    tags=["artifacts"],
)
def artifact_versions(
    artifact_id: UUID,
    project_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[ArtifactListData]:
    _service(session).get(project_id)
    repository = SqlAlchemyArtifactRepository(session)
    artifact = repository.get(artifact_id, project_id=project_id)
    if artifact is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Artifact is not available for this project",
        )
    return ApiEnvelope(
        data=ArtifactListData(
            items=[_artifact_data(item, session) for item in repository.list_versions(artifact)]
        ),
        request_id=_request_id(request),
    )


@router.get(
    "/artifacts/{artifact_id}/dependencies",
    response_model=ApiEnvelope[ArtifactDependenciesData],
    tags=["artifacts"],
)
def artifact_dependencies(
    artifact_id: UUID,
    project_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[ArtifactDependenciesData]:
    _service(session).get(project_id)
    artifact = SqlAlchemyArtifactRepository(session).get(artifact_id, project_id=project_id)
    if artifact is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Artifact is not available for this project",
        )
    repository = SqlAlchemyDependencyGraphRepository(session)
    return ApiEnvelope(
        data=ArtifactDependenciesData(
            artifact=_artifact_data(artifact, session),
            dependencies=[
                DependencyEdgeData(edge=edge)
                for edge in repository.list_dependencies(project_id, "Artifact", str(artifact_id))
            ],
            dependents=[
                DependencyEdgeData(edge=edge)
                for edge in repository.list_dependents(project_id, "Artifact", str(artifact_id))
            ],
        ),
        request_id=_request_id(request),
    )


@router.get(
    "/projects/{project_id}/artifacts/stale",
    response_model=ApiEnvelope[ArtifactListData],
    tags=["artifacts"],
)
def stale_artifacts(
    project_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[ArtifactListData]:
    _service(session).get(project_id)
    repository = SqlAlchemyArtifactRepository(session)
    graph = SqlAlchemyDependencyGraphRepository(session)
    stale_ids = {
        state.entity_id
        for state in graph.list_node_states(project_id)
        if state.entity_type == "Artifact"
        and state.status in {DependencyNodeStatus.STALE, DependencyNodeStatus.INVALID}
    }
    artifacts = [
        item
        for item in repository.list_for_project(project_id)
        if str(item.id) in stale_ids or item.status == ArtifactStatus.STALE
    ]
    return ApiEnvelope(
        data=ArtifactListData(items=[_artifact_data(item, session) for item in artifacts]),
        request_id=_request_id(request),
    )


@router.post(
    "/artifacts/{artifact_id}/revalidate",
    response_model=ApiEnvelope[ArtifactRevalidateData],
    tags=["artifacts"],
)
def revalidate_artifact(
    artifact_id: UUID,
    payload: ArtifactRevalidateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[ArtifactRevalidateData]:
    project_id = payload.project_id
    if project_id is None:
        artifact_record = session.scalar(
            select(ArtifactRecord).where(ArtifactRecord.id == str(artifact_id))
        )
        project_id = UUID(artifact_record.project_id) if artifact_record else None
    if project_id is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED, "Artifact is not available"
        )
    _service(session).get(project_id)
    artifact_repository = SqlAlchemyArtifactRepository(session)
    artifact = artifact_repository.get(artifact_id, project_id=project_id)
    if artifact is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Artifact is not available for this project",
        )
    service = _dependency_service(session)
    state = service.revalidate(project_id, "Artifact", str(artifact_id))
    projection = artifact.status
    if projection not in {ArtifactStatus.DEPRECATED, ArtifactStatus.ARCHIVED}:
        projection = (
            ArtifactStatus.CURRENT
            if state.status is DependencyNodeStatus.CURRENT
            else (
                ArtifactStatus.INVALID
                if state.status is DependencyNodeStatus.INVALID
                else ArtifactStatus.STALE
            )
        )
    artifact = artifact_repository.save_status_projection(artifact, projection)
    return ApiEnvelope(
        data=ArtifactRevalidateData(
            artifact=_artifact_data(artifact, session),
            state=DependencyNodeStateData(state=state),
        ),
        request_id=_request_id(request),
    )


def _pin_data(pin: DevicePin) -> DevicePinData:
    return DevicePinData.model_validate(pin.model_dump(mode="json"))


def _device_data(device: Device) -> DeviceData:
    return DeviceData.model_validate(device.model_dump(mode="json"))


def _pin_plan_data(plan: PinPlan) -> PinPlanData:
    return PinPlanData.model_validate(plan.model_dump(mode="json"))


def _pin_assignment_data(assignment: PinAssignment) -> PinAssignmentData:
    return PinAssignmentData.model_validate(assignment.model_dump(mode="json"))


def _pin_lock_data(lock: PinLock | None) -> PinLockData | None:
    if lock is None:
        return None
    return PinLockData.model_validate(lock.model_dump(mode="json"))


def _architecture_bundle_data(bundle: ArchitectureBundle) -> ArchitectureBundleData:
    return ArchitectureBundleData.model_validate(bundle.model_dump(mode="json"))


def _circuit_bundle_data(bundle: CircuitBundle) -> CircuitBundleData:
    return CircuitBundleData.model_validate(bundle.model_dump(mode="json"))


def _schematic_bundle_data(bundle: SchematicBundle) -> SchematicBundleData:
    return SchematicBundleData.model_validate(bundle.model_dump(mode="json"))


def _mcu_config_bundle_data(bundle: MCUConfigBundle) -> MCUConfigBundleData:
    return MCUConfigBundleData.model_validate(bundle.model_dump(mode="json"))


def _firmware_bundle_data(bundle: FirmwareBundle) -> FirmwareBundleData:
    return FirmwareBundleData.model_validate(bundle.model_dump(mode="json"))


def _build_run_data(build: BuildRun) -> BuildRunData:
    return BuildRunData.model_validate(build.model_dump(mode="json"))


def _static_analysis_data(analysis: FirmwareStaticAnalysis) -> FirmwareStaticAnalysisData:
    return FirmwareStaticAnalysisData.model_validate(analysis.model_dump(mode="json"))


def _coverage_data(coverage: Any) -> CoverageData:
    return CoverageData.model_validate(
        {
            "total_requirements": coverage.total_requirements,
            "release_critical_requirements": coverage.release_critical_requirements,
            "covered_requirements": coverage.covered_requirements,
            "verified_requirements": coverage.verified_requirements,
            "design_coverage_ratio": coverage.design_coverage_ratio,
            "verification_coverage_ratio": coverage.verification_coverage_ratio,
            "uncovered_requirement_ids": coverage.uncovered_requirement_ids,
            "unexecuted_requirement_ids": coverage.unexecuted_requirement_ids,
            "failing_requirement_ids": coverage.failing_requirement_ids,
            "blocked_requirement_ids": coverage.blocked_requirement_ids,
            "unknown_requirement_ids": coverage.unknown_requirement_ids,
            "stale_requirement_ids": coverage.stale_requirement_ids,
            "stale_test_run": coverage.stale_test_run,
            "source_revision_id": coverage.source_revision_id,
        }
    )


def _issue_data(issue: object) -> IssueData:
    return IssueData.model_validate(cast(Any, issue).model_dump(mode="json"))


def _source_revision_exists(session: Session, project_id: UUID, source_revision_id: UUID) -> bool:
    from eea_backend.models import SourceRevisionRecord

    return (
        session.scalar(
            select(SourceRevisionRecord.id).where(
                SourceRevisionRecord.id == str(source_revision_id),
                SourceRevisionRecord.project_id == str(project_id),
            )
        )
        is not None
    )


def _latest_source_revision_id(session: Session, project_id: UUID) -> UUID | None:
    from eea_backend.models import SourceRevisionRecord

    value = session.scalar(
        select(SourceRevisionRecord.id)
        .where(SourceRevisionRecord.project_id == str(project_id))
        .order_by(SourceRevisionRecord.created_at.desc(), SourceRevisionRecord.id.desc())
        .limit(1)
    )
    return UUID(value) if value else None


def _select_test_ir(session: Session, project_id: UUID, test_ir_id: UUID | None) -> TestIR | None:
    repository = SqlAlchemyTestRepository(session)
    if test_ir_id is not None:
        return repository.get_test_ir(test_ir_id, project_id=project_id)
    items = repository.list_test_irs(project_id)
    return items[0] if items else None


def _component_data(
    descriptor: SoftwareComponentDescriptor,
    releases: list[object],
) -> dict[str, object]:
    return {
        "descriptor": descriptor.model_dump(mode="json"),
        "releases": [cast(Any, release).model_dump(mode="json") for release in releases],
    }


def _dependency_lock_data(lock: DependencyLock) -> DependencyLockData:
    return DependencyLockData.model_validate(lock.model_dump(mode="json"))


def _materialization_data(
    materialization: ComponentMaterialization,
) -> ComponentMaterializationData:
    return ComponentMaterializationData.model_validate(materialization.model_dump(mode="json"))


def _domain_service(request: Request, session: Session) -> DomainExtensionService:
    return DomainExtensionService(
        request.app.state.domain_registry,
        SqlAlchemyDomainActivationRepository(session),
        SqlAlchemyProjectRepository(session),
    )


def _domain_descriptor_data(descriptor: object) -> DomainDescriptorData:
    return DomainDescriptorData.model_validate(
        cast(Any, descriptor).model_dump(mode="json", by_alias=True)
    )


def _domain_activation_data(activation: object) -> DomainActivationData:
    return DomainActivationData.model_validate(cast(Any, activation).model_dump(mode="json"))


def _domain_composition_data(composition: object) -> DomainCompositionData:
    return DomainCompositionData.model_validate(cast(Any, composition).model_dump(mode="json"))


def _domain_validation_inputs(
    project_id: UUID, payload: DomainValidationRequest, session: Session
) -> dict[str, object]:
    inputs: dict[str, object] = {}
    if payload.domain_ir is not None:
        inputs["domain_ir"] = payload.domain_ir
    if payload.mcu_config_id is not None:
        bundle = SqlAlchemyMCUConfigRepository(session).get(
            payload.mcu_config_id, project_id=project_id
        )
        if bundle is None:
            raise EngineeringError(
                EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
                "MCUConfigIR is not available for this project",
                details={
                    "mcu_config_id": str(payload.mcu_config_id),
                    "project_id": str(project_id),
                },
            )
        _ensure_current_mcu_config_sources(session, project_id, bundle)
        inputs["mcu_config"] = bundle.config
    return inputs


def _ensure_latest_hardware(session: Session, project_id: UUID, hardware_id: UUID) -> None:
    latest = SqlAlchemyArchitectureRepository(session).latest_for_project(project_id)
    if latest is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "No current HardwareIR is available for schematic generation",
            details={"project_id": str(project_id)},
        )
    if latest.hardware.id != hardware_id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Schematic source HardwareIR is stale",
            details={
                "reason": "STALE_HARDWARE_IR",
                "hardware_ir_id": str(hardware_id),
                "latest_hardware_ir_id": str(latest.hardware.id),
            },
        )


def _ensure_current_mcu_config_sources(
    session: Session, project_id: UUID, bundle: MCUConfigBundle
) -> None:
    hardware = SqlAlchemyArchitectureRepository(session).latest_for_project(project_id)
    circuit = SqlAlchemyCircuitRepository(session).latest_for_project(project_id)
    schematic = SqlAlchemySchematicRepository(session).latest_for_project(project_id)
    if hardware is None or circuit is None or schematic is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "MCUConfigIR source snapshots are not available",
            details={"config_id": str(bundle.config.id)},
        )
    config = bundle.config
    if (
        config.hardware_ir_id != hardware.hardware.id
        or config.hardware_ir_revision != hardware.hardware.revision
        or config.circuit_id != circuit.circuit.id
        or config.circuit_revision != circuit.circuit.revision
        or config.schematic_id != schematic.schematic.id
        or config.schematic_revision != schematic.schematic.revision
    ):
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "MCUConfigIR source snapshot is stale",
            details={"reason": "STALE_MCU_CONFIG_SOURCE", "config_id": str(config.id)},
        )


def _ensure_current_firmware_mcu_config(
    session: Session, project_id: UUID, bundle: FirmwareBundle
) -> None:
    latest = SqlAlchemyMCUConfigRepository(session).latest_for_project(project_id)
    if latest is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "No current MCUConfigIR is available for firmware generation",
            details={"project_id": str(project_id)},
        )
    if (
        latest.config.id != bundle.firmware.mcu_config_id
        or latest.config.revision != bundle.firmware.mcu_config_revision
    ):
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Firmware source MCUConfigIR is stale",
            details={
                "reason": "STALE_MCU_CONFIG_IR",
                "mcu_config_id": str(bundle.firmware.mcu_config_id),
                "latest_mcu_config_id": str(latest.config.id),
            },
        )


def _requirement_profile_repository(session: Session) -> SqlAlchemyRequirementProfileRepository:
    return SqlAlchemyRequirementProfileRepository(session)


def _requirement_profile_data(profile: RequirementProfile) -> RequirementProfileData:
    return RequirementProfileData.model_validate(profile.model_dump(mode="json"))


def _request_id(request: Request) -> str:
    return str(request.state.request_id)


def _component_providers(request: Request) -> list[object]:
    return list(getattr(request.app.state, "component_providers", []))


def _component_descriptor_data(descriptor: SoftwareComponentDescriptor) -> SoftwareComponentData:
    return SoftwareComponentData.model_validate(descriptor.model_dump(mode="json"))


@router.get("/components", response_model=ApiEnvelope[ComponentCatalogData], tags=["components"])
def list_components(
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[ComponentCatalogData]:
    providers = _component_providers(request)
    descriptors = SqlAlchemyComponentRepository(session).list_descriptors()
    for provider in providers:
        descriptors.extend(cast(Any, provider).descriptors())
    by_key = {descriptor.component_key: descriptor for descriptor in descriptors}
    data = ComponentCatalogData(
        components=[_component_descriptor_data(by_key[key]) for key in sorted(by_key)]
    )
    return ApiEnvelope(data=data, request_id=_request_id(request))


@router.get(
    "/components/{component_key}",
    response_model=ApiEnvelope[ComponentDetailData],
    tags=["components"],
)
def get_component(
    component_key: str,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[ComponentDetailData]:
    descriptor = SqlAlchemyComponentRepository(session).get(component_key)
    releases: list[object] = []
    for provider in _component_providers(request):
        for candidate in cast(Any, provider).descriptors():
            if candidate.component_key == component_key:
                descriptor = candidate
                releases.extend(cast(Any, provider).releases(candidate.id))
    if descriptor is None:
        raise EngineeringError(
            EngineeringErrorCode.COMPONENT_UNAVAILABLE,
            "Software component is not registered.",
            details={"component_key": component_key},
        )
    data = ComponentDetailData(
        descriptor=_component_descriptor_data(descriptor),
        releases=[
            ComponentReleaseData.model_validate(cast(Any, release).model_dump(mode="json"))
            for release in releases
        ],
    )
    return ApiEnvelope(data=data, request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/dependencies/resolve",
    response_model=ApiEnvelope[DependencyLockData],
    status_code=status.HTTP_201_CREATED,
    tags=["components"],
)
def resolve_dependencies(
    project_id: UUID,
    payload: ComponentResolveRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DependencyLockData]:
    _service(session).get(project_id)
    config = SqlAlchemyMCUConfigRepository(session).get(
        payload.mcu_config_id, project_id=project_id
    )
    if config is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "MCUConfigIR is not available for dependency resolution.",
            details={"mcu_config_id": str(payload.mcu_config_id)},
        )
    providers = _component_providers(request)
    if not providers:
        raise EngineeringError(
            EngineeringErrorCode.COMPONENT_UNAVAILABLE,
            "No ESCR component provider is installed.",
        )
    lock = ComponentRegistryService(cast(list[Any], providers)).resolve(
        project_id=project_id,
        mcu_config_id=config.config.id,
        mcu_config_revision=config.config.revision,
        requirements=payload.requirements,
        architecture=payload.architecture,
        device=payload.device,
        toolchain_id=payload.toolchain_id,
        build_system=payload.build_system,
        capabilities=payload.capabilities,
        rtos=payload.rtos,
    )
    saved = SqlAlchemyDependencyLockRepository(session).add(lock)
    return ApiEnvelope(data=_dependency_lock_data(saved), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/dependencies",
    response_model=ApiEnvelope[DependencyLockData],
    tags=["components"],
)
def get_latest_dependencies(
    project_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DependencyLockData]:
    _service(session).get(project_id)
    lock = SqlAlchemyDependencyLockRepository(session).latest_for_project(project_id)
    if lock is None:
        raise EngineeringError(
            EngineeringErrorCode.DEPENDENCY_LOCK_REQUIRED,
            "No dependency lock exists for this project.",
        )
    return ApiEnvelope(data=_dependency_lock_data(lock), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/dependency-locks/{lock_id}",
    response_model=ApiEnvelope[DependencyLockData],
    tags=["components"],
)
def get_dependency_lock(
    project_id: UUID,
    lock_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DependencyLockData]:
    _service(session).get(project_id)
    lock = SqlAlchemyDependencyLockRepository(session).get(lock_id, project_id=project_id)
    if lock is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "DependencyLock is not available for this project.",
            details={"lock_id": str(lock_id)},
        )
    return ApiEnvelope(data=_dependency_lock_data(lock), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/dependencies/materialize",
    response_model=ApiEnvelope[list[ComponentMaterializationData]],
    status_code=status.HTTP_201_CREATED,
    tags=["components"],
)
def materialize_dependencies(
    project_id: UUID,
    payload: ComponentMaterializeRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[list[ComponentMaterializationData]]:
    _service(session).get(project_id)
    lock = SqlAlchemyDependencyLockRepository(session).get(payload.lock_id, project_id=project_id)
    if lock is None:
        raise EngineeringError(
            EngineeringErrorCode.DEPENDENCY_LOCK_REQUIRED,
            "DependencyLock is not available for materialization.",
        )
    providers = cast(list[Any], _component_providers(request))
    if not providers:
        raise EngineeringError(
            EngineeringErrorCode.COMPONENT_UNAVAILABLE, "No ESCR provider is installed."
        )
    records = ComponentMaterializer(
        request.app.state.settings.data_dir / "component-cache"
    ).materialize(lock, providers, project_id=project_id)
    repository = SqlAlchemyComponentMaterializationRepository(session)
    saved = [
        repository.add(record.model_copy(update={"project_id": project_id}), commit=False)
        for record in records
    ]
    session.commit()
    return ApiEnvelope(
        data=[_materialization_data(record) for record in saved], request_id=_request_id(request)
    )


def _set_etag(response: Response, revision: int) -> None:
    response.headers["ETag"] = f'W/"{revision}"'


def _expected_revision(if_match: str | None, body_revision: int | None) -> int:
    header_revision: int | None = None
    if if_match is not None:
        match = ETAG_PATTERN.fullmatch(if_match.strip())
        if match is None:
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR,
                "If-Match must contain a numeric ETag",
                details={"if_match": if_match},
            )
        header_revision = int(match.group("revision"))
    if (
        header_revision is not None
        and body_revision is not None
        and header_revision != body_revision
    ):
        raise EngineeringError(
            EngineeringErrorCode.VALIDATION_ERROR,
            "If-Match and expected_revision disagree",
        )
    revision = header_revision if header_revision is not None else body_revision
    if revision is None:
        raise EngineeringError(
            EngineeringErrorCode.VALIDATION_ERROR,
            "If-Match or expected_revision is required",
        )
    return revision


@router.get("/meta/enums", response_model=ApiEnvelope[EnumCatalogData], tags=["meta"])
def enums(request: Request) -> ApiEnvelope[EnumCatalogData]:
    catalog = {
        enum_type.__name__: [member.value for member in enum_type]
        for enum_type in (
            ArtifactStatus,
            ClaimConflictStatus,
            ClaimConflictStrategy,
            ClaimConflictType,
            ClaimLifecycle,
            ChangeObservation,
            DecisionStatus,
            DependencyKind,
            DependencyNodeStatus,
            DeviceCategory,
            DeviceMergeConflictType,
            DocumentParseStatus,
            DocumentType,
            EngineeringDimension,
            EngineeringErrorCode,
            EvidenceType,
            IssueSeverity,
            IssueStatus,
            ImpactAction,
            InvalidationPolicy,
            JobStatus,
            Permission,
            ProjectStatus,
            RequirementFieldStatus,
            RequirementPriority,
            RequirementStatus,
            RequirementType,
            RequirementValueType,
            StaticAnalysisStatus,
            TraceabilityRelation,
            AutomationLevel,
            TestExecutionStatus,
            TestType,
            VerificationLevel,
        )
    }
    return ApiEnvelope(
        data=EnumCatalogData(enums=EnumValues.model_validate(catalog)),
        request_id=_request_id(request),
    )


@router.get("/schemas", response_model=ApiEnvelope[SchemaListData], tags=["schemas"])
def schemas(request: Request) -> ApiEnvelope[SchemaListData]:
    items = [
        SchemaDescriptorData(name=item.name, schema_version=item.version)
        for item in schema_registry.list()
    ]
    return ApiEnvelope(data=SchemaListData(items=items), request_id=_request_id(request))


@router.get("/schemas/{schema_name}", response_model=ApiEnvelope[SchemaData], tags=["schemas"])
def schema(schema_name: str, request: Request) -> ApiEnvelope[SchemaData]:
    registration = schema_registry.get(schema_name)
    json_schema = schema_registry.json_schema(schema_name)
    if registration is None or json_schema is None:
        raise EngineeringError(
            EngineeringErrorCode.SCHEMA_VERSION_UNSUPPORTED,
            "Schema is not registered",
            details={"schema_name": schema_name},
        )
    data = SchemaData(
        name=registration.name,
        schema_version=registration.version,
        json_schema=json_schema,
    )
    return ApiEnvelope(data=data, request_id=_request_id(request))


@router.get(
    "/requirement-profiles/{profile_name}/{profile_version}",
    response_model=ApiEnvelope[RequirementProfileData],
    tags=["requirements"],
)
def get_requirement_profile(
    profile_name: str,
    profile_version: str,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[RequirementProfileData]:
    profile = _requirement_profile_repository(session).get(profile_name, profile_version)
    if profile is None:
        raise EngineeringError(
            EngineeringErrorCode.SCHEMA_VERSION_UNSUPPORTED,
            "Requirement profile version is not registered",
            details={"profile_name": profile_name, "profile_version": profile_version},
        )
    return ApiEnvelope(data=_requirement_profile_data(profile), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/pin-planner/generate",
    response_model=ApiEnvelope[PinPlanData],
    status_code=status.HTTP_201_CREATED,
    tags=["pin-planner"],
)
@router.post(
    "/projects/{project_id}/pin-planner/replan",
    response_model=ApiEnvelope[PinPlanData],
    status_code=status.HTTP_201_CREATED,
    tags=["pin-planner"],
)
def generate_pin_plan(
    project_id: UUID,
    payload: PinPlannerGenerateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[PinPlanData]:
    _service(session).get(project_id)
    analysis = SqlAlchemyRequirementAnalysisRepository(session).get(payload.analysis_id)
    if analysis is None or analysis.project_id != project_id:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Requirement analysis is not available for this project",
            details={"analysis_id": str(payload.analysis_id), "project_id": str(project_id)},
        )
    canonical_requirement_ids = {
        item.id for item in SqlAlchemyRequirementRepository(session).list_for_project(project_id)
    }
    canonical_claims = SqlAlchemyEngineeringClaimRepository(session)
    for requirement in payload.requirements:
        if not set(requirement.requirement_ids) <= canonical_requirement_ids:
            raise EngineeringError(
                EngineeringErrorCode.INVALID_REQUIREMENT,
                "Pin requirement references a non-canonical requirement",
                details={"signal_name": requirement.signal_name},
            )
        for claim_id in requirement.claim_ids:
            claim = canonical_claims.get(claim_id)
            if claim is None or (claim.project_id is not None and claim.project_id != project_id):
                raise EngineeringError(
                    EngineeringErrorCode.INVALID_REQUIREMENT,
                    "Pin requirement references a non-canonical claim",
                    details={"signal_name": requirement.signal_name},
                )
    pin_requirements = [
        PinRequirement(project_id=project_id, **item.model_dump()) for item in payload.requirements
    ]
    plan = PinPlannerService().plan_from_analysis(
        analysis=analysis,
        device_ref=payload.device_ref,
        package=payload.package,
        requirements=pin_requirements,
        device_provider=device_provider,
    )
    plan = SqlAlchemyPinPlanRepository(session).add(plan, commit=False)
    dependency_service = _dependency_service(session)
    for assignment in plan.assignments:
        for claim_id in assignment.claim_ids:
            dependency_service.bind(
                project_id,
                upstream_type="Claim",
                upstream_id=str(claim_id),
                downstream_type="PinAssignment",
                downstream_id=str(assignment.id),
                dependency_kind=DependencyKind.SELECTION,
                required=True,
                invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
                reason="PinAssignment generated claim reference",
                commit=False,
            )
    session.commit()
    return ApiEnvelope(
        data=_pin_plan_data(plan),
        request_id=_request_id(request),
    )


@router.get(
    "/projects/{project_id}/pin-planner/map",
    response_model=ApiEnvelope[PinPlanData],
    tags=["pin-planner"],
)
def get_pin_map(
    project_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[PinPlanData]:
    _service(session).get(project_id)
    plan = SqlAlchemyPinPlanRepository(session).latest_for_project(project_id)
    if plan is None:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "No pin plan has been generated for this project",
            details={"project_id": str(project_id)},
        )
    return ApiEnvelope(data=_pin_plan_data(plan), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/pin-planner/validate",
    response_model=ApiEnvelope[PinPlanValidationData],
    tags=["pin-planner"],
)
def validate_pin_plan(
    project_id: UUID,
    payload: PinPlanValidationRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[PinPlanValidationData]:
    _service(session).get(project_id)
    plan = SqlAlchemyPinPlanRepository(session).get(payload.plan_id, project_id=project_id)
    if plan is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Pin plan is not available for this project",
            details={"plan_id": str(payload.plan_id), "project_id": str(project_id)},
        )
    results = PinPlannerService().validate(plan, device_provider)
    data = PinPlanValidationData(
        plan_id=plan.id,
        plan_revision=plan.revision,
        rule_results=[result.model_dump(mode="json") for result in results],
    )
    return ApiEnvelope(data=data, request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/pin-planner/assignments/{assignment_id}/lock",
    response_model=ApiEnvelope[PinAssignmentMutationData],
    tags=["pin-planner"],
)
def lock_pin_assignment(
    project_id: UUID,
    assignment_id: UUID,
    payload: PinAssignmentMutationRequest,
    request: Request,
    response: Response,
    session: SessionDependency,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ApiEnvelope[PinAssignmentMutationData]:
    _service(session).get(project_id)
    repository = SqlAlchemyPinPlanRepository(session)
    context = repository.get_assignment(assignment_id, project_id=project_id)
    if context is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Pin assignment is not available for this project",
            details={"assignment_id": str(assignment_id), "project_id": str(project_id)},
        )
    current, _ = context
    expected_revision = _expected_revision(if_match, payload.expected_revision)
    if current.revision != expected_revision:
        raise EngineeringError(
            EngineeringErrorCode.REVISION_CONFLICT,
            "The pin assignment changed after it was read",
            details={"entity_id": str(assignment_id), "expected_revision": expected_revision},
        )
    before = build_dependency_provider_registry(session).resolve(
        project_id, "PinAssignment", str(current.id)
    )
    locked, lock = PinPlannerService().lock_assignment(
        current, locked_by=payload.actor, reason=payload.reason
    )
    saved = repository.save_assignment(locked, expected_revision=expected_revision, commit=False)
    if saved is None:
        session.rollback()
        raise EngineeringError(
            EngineeringErrorCode.REVISION_CONFLICT,
            "The pin assignment changed after it was read",
            details={"entity_id": str(assignment_id), "expected_revision": expected_revision},
        )
    after = build_dependency_provider_registry(session).resolve(
        project_id, "PinAssignment", str(saved.id)
    )
    saved_lock = repository.add_lock(lock, commit=False)
    _dependency_service(session).propagate(
        project_id,
        before,
        after,
        commit=False,
    )
    session.commit()
    _set_etag(response, saved.revision)
    return ApiEnvelope(
        data=PinAssignmentMutationData(
            assignment=_pin_assignment_data(saved),
            lock=_pin_lock_data(saved_lock),
        ),
        request_id=_request_id(request),
    )


@router.post(
    "/projects/{project_id}/pin-planner/assignments/{assignment_id}/unlock",
    response_model=ApiEnvelope[PinAssignmentMutationData],
    tags=["pin-planner"],
)
def unlock_pin_assignment(
    project_id: UUID,
    assignment_id: UUID,
    payload: PinAssignmentMutationRequest,
    request: Request,
    response: Response,
    session: SessionDependency,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ApiEnvelope[PinAssignmentMutationData]:
    _service(session).get(project_id)
    repository = SqlAlchemyPinPlanRepository(session)
    context = repository.get_assignment(assignment_id, project_id=project_id)
    if context is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Pin assignment is not available for this project",
            details={"assignment_id": str(assignment_id), "project_id": str(project_id)},
        )
    current, _ = context
    expected_revision = _expected_revision(if_match, payload.expected_revision)
    if current.revision != expected_revision:
        raise EngineeringError(
            EngineeringErrorCode.REVISION_CONFLICT,
            "The pin assignment changed after it was read",
            details={"entity_id": str(assignment_id), "expected_revision": expected_revision},
        )
    before = build_dependency_provider_registry(session).resolve(
        project_id, "PinAssignment", str(current.id)
    )
    unlocked = PinPlannerService().unlock_assignment(
        current, unlocked_by=payload.actor, reason=payload.reason
    )
    saved = repository.save_assignment(unlocked, expected_revision=expected_revision, commit=False)
    if saved is None:
        session.rollback()
        raise EngineeringError(
            EngineeringErrorCode.REVISION_CONFLICT,
            "The pin assignment changed after it was read",
            details={"entity_id": str(assignment_id), "expected_revision": expected_revision},
        )
    after = build_dependency_provider_registry(session).resolve(
        project_id, "PinAssignment", str(saved.id)
    )
    if not repository.release_lock(
        assignment_id,
        project_id=project_id,
        released_by=payload.actor,
        reason=payload.reason,
        commit=False,
    ):
        session.rollback()
        raise EngineeringError(
            EngineeringErrorCode.VALIDATION_ERROR,
            "The active pin lock was not found",
            details={"assignment_id": str(assignment_id)},
        )
    _dependency_service(session).propagate(
        project_id,
        before,
        after,
        commit=False,
    )
    session.commit()
    _set_etag(response, saved.revision)
    return ApiEnvelope(
        data=PinAssignmentMutationData(
            assignment=_pin_assignment_data(saved),
            lock=None,
        ),
        request_id=_request_id(request),
    )


@router.post(
    "/projects/{project_id}/architecture/generate",
    response_model=ApiEnvelope[ArchitectureBundleData],
    status_code=status.HTTP_201_CREATED,
    tags=["architecture"],
)
def generate_architecture(
    project_id: UUID,
    payload: ArchitectureGenerateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[ArchitectureBundleData]:
    _service(session).get(project_id)
    pin_plans = SqlAlchemyPinPlanRepository(session)
    plan = pin_plans.get(payload.pin_plan_id, project_id=project_id)
    latest = pin_plans.latest_for_project(project_id)
    if plan is None or latest is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Pin plan is not available for architecture generation",
            details={"pin_plan_id": str(payload.pin_plan_id), "project_id": str(project_id)},
        )
    bundle = ArchitectureService().generate(plan, latest_plan_id=latest.id)
    saved = SqlAlchemyArchitectureRepository(session).add(bundle, commit=False)
    dependency_service = _dependency_service(session)
    for assignment_id in saved.system_architecture.pin_assignment_revisions:
        dependency_service.bind(
            project_id,
            upstream_type="PinAssignment",
            upstream_id=str(assignment_id),
            downstream_type="SystemArchitectureIR",
            downstream_id=str(saved.system_architecture.id),
            dependency_kind=DependencyKind.GENERATION,
            required=True,
            invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
            reason="SystemArchitectureIR pin_assignment_revisions",
            commit=False,
        )
    dependency_service.bind(
        project_id,
        upstream_type="SystemArchitectureIR",
        upstream_id=str(saved.system_architecture.id),
        downstream_type="HardwareIR",
        downstream_id=str(saved.hardware.id),
        dependency_kind=DependencyKind.GENERATION,
        required=True,
        invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
        reason="HardwareIR architecture_id",
        commit=False,
    )
    session.commit()
    return ApiEnvelope(data=_architecture_bundle_data(saved), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/architecture",
    response_model=ApiEnvelope[ArchitectureBundleData],
    tags=["architecture"],
)
def get_architecture(
    project_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[ArchitectureBundleData]:
    _service(session).get(project_id)
    bundle = SqlAlchemyArchitectureRepository(session).latest_for_project(project_id)
    if bundle is None:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "No architecture has been generated for this project",
            details={"project_id": str(project_id)},
        )
    return ApiEnvelope(data=_architecture_bundle_data(bundle), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/circuit/generate",
    response_model=ApiEnvelope[CircuitBundleData],
    status_code=status.HTTP_201_CREATED,
    tags=["circuit"],
)
def generate_circuit(
    project_id: UUID,
    payload: CircuitGenerateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[CircuitBundleData]:
    _service(session).get(project_id)
    architectures = SqlAlchemyArchitectureRepository(session)
    selected = architectures.get_by_hardware_id(payload.hardware_ir_id, project_id=project_id)
    latest = architectures.latest_for_project(project_id)
    if selected is None or latest is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "HardwareIR is not available for circuit generation",
            details={"hardware_ir_id": str(payload.hardware_ir_id), "project_id": str(project_id)},
        )
    if selected.hardware.id != latest.hardware.id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Selected HardwareIR is stale",
            details={
                "reason": "STALE_HARDWARE_IR",
                "hardware_ir_id": str(payload.hardware_ir_id),
                "latest_hardware_ir_id": str(latest.hardware.id),
            },
        )
    bundle = CircuitService().generate(
        selected.hardware,
        components=payload.components,
        nets=payload.nets,
        power_nets=payload.power_nets,
        constraints=payload.constraints,
    )
    saved = SqlAlchemyCircuitRepository(session).add(bundle, commit=False)
    _dependency_service(session).bind(
        project_id,
        upstream_type="HardwareIR",
        upstream_id=str(saved.circuit.hardware_ir_id),
        downstream_type="CircuitIR",
        downstream_id=str(saved.circuit.id),
        dependency_kind=DependencyKind.GENERATION,
        required=True,
        invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
        reason="CircuitIR hardware_ir_id",
        commit=False,
    )
    session.commit()
    SqlAlchemySchematicRepository(session).mark_stale_for_circuit(project_id, saved.circuit.id)
    return ApiEnvelope(data=_circuit_bundle_data(saved), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/circuit",
    response_model=ApiEnvelope[CircuitBundleData],
    tags=["circuit"],
)
def get_circuit(
    project_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[CircuitBundleData]:
    _service(session).get(project_id)
    bundle = SqlAlchemyCircuitRepository(session).latest_for_project(project_id)
    if bundle is None:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "No circuit has been generated for this project",
            details={"project_id": str(project_id)},
        )
    return ApiEnvelope(data=_circuit_bundle_data(bundle), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/circuit/validate",
    response_model=ApiEnvelope[CircuitValidationData],
    tags=["circuit"],
)
def validate_circuit(
    project_id: UUID,
    payload: CircuitValidateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[CircuitValidationData]:
    _service(session).get(project_id)
    circuits = SqlAlchemyCircuitRepository(session)
    bundle = circuits.get(payload.circuit_id, project_id=project_id)
    if bundle is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Circuit is not available for this project",
            details={"circuit_id": str(payload.circuit_id), "project_id": str(project_id)},
        )
    architectures = SqlAlchemyArchitectureRepository(session)
    hardware_bundle = architectures.get_by_hardware_id(
        bundle.circuit.hardware_ir_id, project_id=project_id
    )
    latest = architectures.latest_for_project(project_id)
    if hardware_bundle is None or latest is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Circuit source HardwareIR is not available",
            details={"hardware_ir_id": str(bundle.circuit.hardware_ir_id)},
        )
    if hardware_bundle.hardware.id != latest.hardware.id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Circuit source HardwareIR is stale",
            details={
                "reason": "STALE_HARDWARE_IR",
                "hardware_ir_id": str(bundle.circuit.hardware_ir_id),
                "latest_hardware_ir_id": str(latest.hardware.id),
            },
        )
    results = CircuitService().validate(bundle.circuit, hardware_bundle.hardware)
    data = CircuitValidationData(
        circuit_id=bundle.circuit.id,
        circuit_revision=bundle.circuit.revision,
        rule_results=[result.model_dump(mode="json") for result in results],
    )
    return ApiEnvelope(data=data, request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/schematic/generate",
    response_model=ApiEnvelope[SchematicBundleData],
    status_code=status.HTTP_201_CREATED,
    tags=["schematic"],
)
def generate_schematic(
    project_id: UUID,
    payload: SchematicGenerateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[SchematicBundleData]:
    _service(session).get(project_id)
    circuits = SqlAlchemyCircuitRepository(session)
    selected = circuits.get(payload.circuit_id, project_id=project_id)
    latest = circuits.latest_for_project(project_id)
    if selected is None or latest is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Circuit is not available for schematic generation",
            details={"circuit_id": str(payload.circuit_id), "project_id": str(project_id)},
        )
    if selected.circuit.id != latest.circuit.id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Selected CircuitIR is stale",
            details={
                "reason": "STALE_CIRCUIT_IR",
                "circuit_id": str(payload.circuit_id),
                "latest_circuit_id": str(latest.circuit.id),
            },
        )
    _ensure_latest_hardware(session, project_id, selected.circuit.hardware_ir_id)
    bundle = SchematicService().generate(selected.circuit)
    saved = SqlAlchemySchematicRepository(session).add(bundle, commit=False)
    event_payload = {
        "project_id": str(project_id),
        "artifact_id": str(saved.artifact.id),
        "logical_name": saved.artifact.logical_name,
        "artifact_type": saved.artifact.artifact_type,
        "version_label": saved.artifact.version_label,
        "content_hash": saved.artifact.content_hash,
        "input_hash": saved.artifact.input_hash,
    }
    EventOutboxService(SqlAlchemyOutboxRepository(session)).enqueue(
        event_type="artifact.created",
        aggregate_type="Artifact",
        aggregate_id=str(saved.artifact.id),
        aggregate_revision=saved.artifact.revision,
        event_key=stable_event_key(
            "artifact.created", "Artifact", saved.artifact.id, saved.artifact.revision
        ),
        payload=event_payload,
        payload_hash=payload_sha256(event_payload),
        project_id=project_id,
        commit=False,
    )
    dependency_service = _dependency_service(session)
    for upstream_type, upstream_id, reason in (
        ("CircuitIR", saved.schematic.circuit_id, "SchematicIR circuit_id"),
        ("HardwareIR", saved.schematic.hardware_ir_id, "SchematicIR hardware_ir_id"),
    ):
        dependency_service.bind(
            project_id,
            upstream_type=upstream_type,
            upstream_id=str(upstream_id),
            downstream_type="SchematicIR",
            downstream_id=str(saved.schematic.id),
            dependency_kind=DependencyKind.GENERATION,
            required=True,
            invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
            reason=reason,
            commit=False,
        )
    dependency_service.bind_artifact_input(
        project_id,
        upstream_type="CircuitIR",
        upstream_id=str(saved.schematic.circuit_id),
        downstream_id=str(saved.artifact.id),
        bound_upstream_semantic_hash=saved.artifact.dependency_hashes.get("circuit"),
        reason="Schematic artifact circuit dependency",
        commit=False,
    )
    dependency_service.bind_artifact_input(
        project_id,
        upstream_type="HardwareIR",
        upstream_id=str(saved.schematic.hardware_ir_id),
        downstream_id=str(saved.artifact.id),
        bound_upstream_semantic_hash=saved.artifact.dependency_hashes.get("hardware_ir"),
        reason="Schematic artifact hardware dependency",
        commit=False,
    )
    session.commit()
    return ApiEnvelope(data=_schematic_bundle_data(saved), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/schematic",
    response_model=ApiEnvelope[SchematicBundleData],
    tags=["schematic"],
)
def get_schematic(
    project_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[SchematicBundleData]:
    _service(session).get(project_id)
    bundle = SqlAlchemySchematicRepository(session).latest_for_project(project_id)
    if bundle is None:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "No current schematic has been generated for this project",
            details={"project_id": str(project_id)},
        )
    return ApiEnvelope(data=_schematic_bundle_data(bundle), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/schematic/validate",
    response_model=ApiEnvelope[SchematicBundleData],
    tags=["schematic"],
)
def validate_schematic(
    project_id: UUID,
    payload: SchematicValidateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[SchematicBundleData]:
    _service(session).get(project_id)
    schematics = SqlAlchemySchematicRepository(session)
    bundle = schematics.get(payload.schematic_id, project_id=project_id)
    if bundle is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Schematic is not available for this project",
            details={"schematic_id": str(payload.schematic_id), "project_id": str(project_id)},
        )
    circuits = SqlAlchemyCircuitRepository(session)
    circuit_bundle = circuits.get(bundle.schematic.circuit_id, project_id=project_id)
    latest = circuits.latest_for_project(project_id)
    if circuit_bundle is None or latest is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Schematic source CircuitIR is not available",
            details={"circuit_id": str(bundle.schematic.circuit_id)},
        )
    if circuit_bundle.circuit.id != latest.circuit.id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Schematic source CircuitIR is stale",
            details={
                "reason": "STALE_CIRCUIT_IR",
                "circuit_id": str(bundle.schematic.circuit_id),
                "latest_circuit_id": str(latest.circuit.id),
            },
        )
    _ensure_latest_hardware(session, project_id, circuit_bundle.circuit.hardware_ir_id)
    report = SchematicService().validate(bundle.schematic, circuit_bundle.circuit)
    schematics.save_erc_report(report)
    refreshed = schematics.get(bundle.schematic.id, project_id=project_id) or bundle
    return ApiEnvelope(data=_schematic_bundle_data(refreshed), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/schematic/erc/import",
    response_model=ApiEnvelope[SchematicBundleData],
    tags=["schematic"],
)
def import_schematic_erc(
    project_id: UUID,
    payload: ErcImportRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[SchematicBundleData]:
    _service(session).get(project_id)
    schematics = SqlAlchemySchematicRepository(session)
    bundle = schematics.get(payload.schematic_id, project_id=project_id)
    if bundle is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Schematic is not available for this project",
            details={"schematic_id": str(payload.schematic_id), "project_id": str(project_id)},
        )
    circuits = SqlAlchemyCircuitRepository(session)
    circuit_bundle = circuits.get(bundle.schematic.circuit_id, project_id=project_id)
    latest = circuits.latest_for_project(project_id)
    if circuit_bundle is None or latest is None or circuit_bundle.circuit.id != latest.circuit.id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Schematic source CircuitIR is stale or unavailable",
            details={"reason": "STALE_CIRCUIT_IR", "circuit_id": str(bundle.schematic.circuit_id)},
        )
    _ensure_latest_hardware(session, project_id, circuit_bundle.circuit.hardware_ir_id)
    report = SchematicService().import_erc(
        bundle.schematic,
        circuit_bundle.circuit,
        status=payload.status,
        tool_name=payload.tool_name,
        tool_version=payload.tool_version,
        issues=payload.issues,
        evidence_ids=payload.evidence_ids,
    )
    schematics.save_erc_report(report)
    refreshed = schematics.get(bundle.schematic.id, project_id=project_id) or bundle
    return ApiEnvelope(data=_schematic_bundle_data(refreshed), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/mcu-config/generate",
    response_model=ApiEnvelope[MCUConfigBundleData],
    status_code=status.HTTP_201_CREATED,
    tags=["mcu-config"],
)
def generate_mcu_config(
    project_id: UUID,
    payload: MCUConfigGenerateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[MCUConfigBundleData]:
    _service(session).get(project_id)
    architectures = SqlAlchemyArchitectureRepository(session)
    hardware_bundle = architectures.get_by_hardware_id(
        payload.hardware_ir_id, project_id=project_id
    )
    latest_hardware = architectures.latest_for_project(project_id)
    if hardware_bundle is None or latest_hardware is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "HardwareIR is not available for MCUConfigIR generation",
            details={"hardware_ir_id": str(payload.hardware_ir_id), "project_id": str(project_id)},
        )
    if hardware_bundle.hardware.id != latest_hardware.hardware.id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Selected HardwareIR is stale",
            details={
                "reason": "STALE_HARDWARE_IR",
                "hardware_ir_id": str(payload.hardware_ir_id),
                "latest_hardware_ir_id": str(latest_hardware.hardware.id),
            },
        )

    circuits = SqlAlchemyCircuitRepository(session)
    circuit_bundle = circuits.get(payload.circuit_id, project_id=project_id)
    latest_circuit = circuits.latest_for_project(project_id)
    if circuit_bundle is None or latest_circuit is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "CircuitIR is not available for MCUConfigIR generation",
            details={"circuit_id": str(payload.circuit_id), "project_id": str(project_id)},
        )
    if circuit_bundle.circuit.id != latest_circuit.circuit.id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Selected CircuitIR is stale",
            details={
                "reason": "STALE_CIRCUIT_IR",
                "circuit_id": str(payload.circuit_id),
                "latest_circuit_id": str(latest_circuit.circuit.id),
            },
        )

    schematics = SqlAlchemySchematicRepository(session)
    schematic_bundle = schematics.get(payload.schematic_id, project_id=project_id)
    latest_schematic = schematics.latest_for_project(project_id)
    if schematic_bundle is None or latest_schematic is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "SchematicIR is not available for MCUConfigIR generation",
            details={"schematic_id": str(payload.schematic_id), "project_id": str(project_id)},
        )
    if schematic_bundle.schematic.id != latest_schematic.schematic.id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Selected SchematicIR is stale",
            details={
                "reason": "STALE_SCHEMATIC_IR",
                "schematic_id": str(payload.schematic_id),
                "latest_schematic_id": str(latest_schematic.schematic.id),
            },
        )
    bundle = MCUConfigService().generate(
        hardware_bundle.hardware,
        circuit_bundle.circuit,
        schematic_bundle.schematic,
        device_instance_id=payload.device_instance_id,
        clock=payload.clock,
        gpio=payload.gpio,
        peripherals=payload.peripherals,
        dma=payload.dma,
        interrupts=payload.interrupts,
        memory=payload.memory,
        debug=payload.debug,
        capability_snapshot=payload.capability_snapshot,
    )
    saved = SqlAlchemyMCUConfigRepository(session).add(bundle, commit=False)
    dependency_service = _dependency_service(session)
    for upstream_type, upstream_id, reason in (
        ("HardwareIR", saved.config.hardware_ir_id, "MCUConfigIR hardware_ir_id"),
        ("CircuitIR", saved.config.circuit_id, "MCUConfigIR circuit_id"),
        ("SchematicIR", saved.config.schematic_id, "MCUConfigIR schematic_id"),
    ):
        if dependency_service.providers.supports(upstream_type):
            dependency_service.bind(
                project_id,
                upstream_type=upstream_type,
                upstream_id=str(upstream_id),
                downstream_type="MCUConfigIR",
                downstream_id=str(saved.config.id),
                dependency_kind=DependencyKind.GENERATION,
                required=True,
                invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
                reason=reason,
                commit=False,
            )
    for assignment_id in saved.config.pin_assignment_revisions:
        dependency_service.bind(
            project_id,
            upstream_type="PinAssignment",
            upstream_id=str(assignment_id),
            downstream_type="MCUConfigIR",
            downstream_id=str(saved.config.id),
            dependency_kind=DependencyKind.CONFIGURATION,
            required=True,
            invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
            reason="MCUConfigIR pin_assignment_revisions",
            commit=False,
        )
    session.commit()
    return ApiEnvelope(data=_mcu_config_bundle_data(saved), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/mcu-config",
    response_model=ApiEnvelope[MCUConfigBundleData],
    tags=["mcu-config"],
)
def get_mcu_config(
    project_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[MCUConfigBundleData]:
    _service(session).get(project_id)
    bundle = SqlAlchemyMCUConfigRepository(session).latest_for_project(project_id)
    if bundle is None:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "No current MCUConfigIR has been generated for this project",
            details={"project_id": str(project_id)},
        )
    _ensure_current_mcu_config_sources(session, project_id, bundle)
    return ApiEnvelope(data=_mcu_config_bundle_data(bundle), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/mcu-config/validate",
    response_model=ApiEnvelope[MCUConfigValidationData],
    tags=["mcu-config"],
)
def validate_mcu_config(
    project_id: UUID,
    payload: MCUConfigValidateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[MCUConfigValidationData]:
    _service(session).get(project_id)
    repository = SqlAlchemyMCUConfigRepository(session)
    bundle = repository.get(payload.config_id, project_id=project_id)
    if bundle is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "MCUConfigIR is not available for this project",
            details={"config_id": str(payload.config_id), "project_id": str(project_id)},
        )
    architectures = SqlAlchemyArchitectureRepository(session)
    hardware_bundle = architectures.get_by_hardware_id(
        bundle.config.hardware_ir_id, project_id=project_id
    )
    circuits = SqlAlchemyCircuitRepository(session)
    circuit_bundle = circuits.get(bundle.config.circuit_id, project_id=project_id)
    schematics = SqlAlchemySchematicRepository(session)
    schematic_bundle = schematics.get(bundle.config.schematic_id, project_id=project_id)
    latest_hardware = architectures.latest_for_project(project_id)
    latest_circuit = circuits.latest_for_project(project_id)
    latest_schematic = schematics.latest_for_project(project_id)
    if (
        hardware_bundle is None
        or circuit_bundle is None
        or schematic_bundle is None
        or latest_hardware is None
        or latest_circuit is None
        or latest_schematic is None
    ):
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "MCUConfigIR source snapshots are not available",
            details={"config_id": str(payload.config_id)},
        )
    if (
        hardware_bundle.hardware.id != latest_hardware.hardware.id
        or circuit_bundle.circuit.id != latest_circuit.circuit.id
        or schematic_bundle.schematic.id != latest_schematic.schematic.id
    ):
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "MCUConfigIR source snapshot is stale",
            details={"reason": "STALE_MCU_CONFIG_SOURCE", "config_id": str(payload.config_id)},
        )
    results = MCUConfigService().validate(
        bundle.config,
        hardware_bundle.hardware,
        circuit_bundle.circuit,
        schematic_bundle.schematic,
    )
    data = MCUConfigValidationData(
        config_id=bundle.config.id,
        config_revision=bundle.config.revision,
        rule_results=[result.model_dump(mode="json") for result in results],
    )
    return ApiEnvelope(data=data, request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/protocol",
    response_model=ApiEnvelope[ProtocolIR],
    status_code=status.HTTP_201_CREATED,
    tags=["protocol"],
)
def create_protocol(
    project_id: UUID,
    payload: ProtocolCreateRequest,
    request: Request,
    response: Response,
    session: SessionDependency,
) -> ApiEnvelope[ProtocolIR]:
    _service(session).get(project_id)
    protocol = ProtocolIR(project_id=project_id, **payload.model_dump())
    saved = SqlAlchemyProtocolRepository(session).add(protocol, commit=False)
    session.commit()
    _set_etag(response, saved.revision)
    return ApiEnvelope(data=saved, request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/protocol",
    response_model=ApiEnvelope[ProtocolIR],
    tags=["protocol"],
)
def get_protocol(
    project_id: UUID,
    request: Request,
    response: Response,
    session: SessionDependency,
) -> ApiEnvelope[ProtocolIR]:
    _service(session).get(project_id)
    protocol = SqlAlchemyProtocolRepository(session).latest_for_project(project_id)
    if protocol is None:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "No current ProtocolIR has been persisted for this project",
            details={"project_id": str(project_id)},
        )
    _set_etag(response, protocol.revision)
    return ApiEnvelope(data=protocol, request_id=_request_id(request))


@router.patch(
    "/projects/{project_id}/protocol",
    response_model=ApiEnvelope[ProtocolIR],
    tags=["protocol"],
)
def update_protocol(
    project_id: UUID,
    payload: ProtocolUpdateRequest,
    request: Request,
    response: Response,
    session: SessionDependency,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ApiEnvelope[ProtocolIR]:
    expected_revision = _expected_revision(if_match, payload.expected_revision)
    repository = SqlAlchemyProtocolRepository(session)
    current = repository.latest_for_project(project_id)
    if current is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "No current ProtocolIR is available for update",
            details={"project_id": str(project_id)},
        )
    if current.revision != expected_revision:
        raise EngineeringError(
            EngineeringErrorCode.REVISION_CONFLICT,
            "ProtocolIR revision does not match the requested optimistic-concurrency revision",
            details={
                "protocol_id": str(current.id),
                "expected_revision": expected_revision,
                "current_revision": current.revision,
            },
        )
    changes = payload.model_dump(exclude={"expected_revision"}, exclude_unset=True)
    snapshot = current.model_dump(mode="json")
    snapshot.update(changes)
    snapshot["project_id"] = project_id
    snapshot["revision"] = current.revision + 1
    snapshot["updated_at"] = utc_now()
    updated = ProtocolIR.model_validate(snapshot)
    before = build_dependency_provider_registry(session).resolve(
        project_id, "ProtocolIR", str(current.id)
    )
    saved = repository.save(updated, expected_revision=expected_revision, commit=False)
    if saved is None:
        raise EngineeringError(
            EngineeringErrorCode.REVISION_CONFLICT,
            "ProtocolIR revision does not match the requested optimistic-concurrency revision",
            details={
                "protocol_id": str(current.id),
                "expected_revision": expected_revision,
                "current_revision": current.revision,
            },
        )
    after = build_dependency_provider_registry(session).resolve(
        project_id, "ProtocolIR", str(saved.id)
    )
    _dependency_service(session).propagate(project_id, before, after, commit=False)
    session.commit()
    _set_etag(response, saved.revision)
    return ApiEnvelope(data=saved, request_id=_request_id(request))


def _select_protocol(
    project_id: UUID,
    protocol_id: UUID | None,
    revision: int | None,
    session: Session,
) -> ProtocolIR:
    repository = SqlAlchemyProtocolRepository(session)
    protocol = (
        repository.latest_for_project(project_id)
        if protocol_id is None
        else repository.get(protocol_id, project_id=project_id, revision=revision)
    )
    if protocol is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "ProtocolIR is not available for this project",
            details={
                "protocol_id": str(protocol_id) if protocol_id is not None else None,
                "revision": revision,
                "project_id": str(project_id),
            },
        )
    return protocol


@router.post(
    "/projects/{project_id}/protocol/validate",
    response_model=ApiEnvelope[ProtocolValidationResult],
    tags=["protocol"],
)
def validate_protocol_ir(
    project_id: UUID,
    payload: ProtocolValidateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[ProtocolValidationResult]:
    _service(session).get(project_id)
    protocol = _select_protocol(project_id, payload.protocol_id, payload.revision, session)
    result = ProtocolGenerator().validate(protocol)
    return ApiEnvelope(data=result, request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/protocol/generate",
    response_model=ApiEnvelope[ProtocolGenerationBundle],
    tags=["protocol"],
)
def generate_protocol(
    project_id: UUID,
    payload: ProtocolGenerateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[ProtocolGenerationBundle]:
    _service(session).get(project_id)
    protocol = _select_protocol(project_id, payload.protocol_id, payload.revision, session)
    try:
        bundle = ProtocolGenerator().generate(protocol)
    except ProtocolGenerationError as error:
        raise EngineeringError(
            EngineeringErrorCode.VALIDATION_ERROR,
            "ProtocolIR generation is blocked by validation failures",
            details={"protocol_id": str(protocol.id), "reason": str(error)},
        ) from error
    dependency_service = _dependency_service(session)
    for output in bundle.outputs:
        output_target = str(output.target)
        record = session.scalar(
            select(GeneratedProtocolOutputRecord).where(
                GeneratedProtocolOutputRecord.project_id == str(project_id),
                GeneratedProtocolOutputRecord.protocol_id == str(protocol.id),
                GeneratedProtocolOutputRecord.target == output_target,
            )
        )
        if record is None:
            record = GeneratedProtocolOutputRecord(
                id=str(uuid4()),
                schema_version="1.0",
                revision=1,
                created_at=utc_now(),
                updated_at=utc_now(),
                entity_metadata={},
                project_id=str(project_id),
                protocol_id=str(protocol.id),
                protocol_revision=protocol.revision,
                target=output_target,
                path=output.path,
                content=output.content,
                content_hash=output.content_hash,
                input_hash=output.input_hash,
                generator_version=output.generator_version,
            )
            session.add(record)
            session.flush()
        else:
            record.revision += 1
            record.updated_at = utc_now()
            record.protocol_revision = protocol.revision
            record.path = output.path
            record.content = output.content
            record.content_hash = output.content_hash
            record.input_hash = output.input_hash
            record.generator_version = output.generator_version
        session.flush()
        dependency_service.bind(
            project_id,
            upstream_type="ProtocolIR",
            upstream_id=str(protocol.id),
            downstream_type="GeneratedProtocolOutput",
            downstream_id=str(record.id),
            dependency_kind=DependencyKind.GENERATION,
            required=True,
            invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
            reason="Generated protocol output from ProtocolIR",
            commit=False,
        )
        dependency_service.rebind(
            project_id,
            upstream_type="ProtocolIR",
            upstream_id=str(protocol.id),
            downstream_type="GeneratedProtocolOutput",
            downstream_id=str(record.id),
            dependency_kind=DependencyKind.GENERATION,
            commit=False,
        )
    session.commit()
    return ApiEnvelope(data=bundle, request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/firmware/generate",
    response_model=ApiEnvelope[FirmwareBundleData],
    status_code=status.HTTP_201_CREATED,
    tags=["firmware"],
)
def generate_firmware(
    project_id: UUID,
    payload: FirmwareGenerateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[FirmwareBundleData]:
    _service(session).get(project_id)
    configs = SqlAlchemyMCUConfigRepository(session)
    selected = configs.get(payload.mcu_config_id, project_id=project_id)
    latest = configs.latest_for_project(project_id)
    if selected is None or latest is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "MCUConfigIR is not available for firmware generation",
            details={"mcu_config_id": str(payload.mcu_config_id), "project_id": str(project_id)},
        )
    if selected.config.id != latest.config.id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Selected MCUConfigIR is stale",
            details={
                "reason": "STALE_MCU_CONFIG_IR",
                "mcu_config_id": str(payload.mcu_config_id),
                "latest_mcu_config_id": str(latest.config.id),
            },
        )
    _ensure_current_mcu_config_sources(session, project_id, selected)
    dependency_lock = None
    if payload.dependency_lock_id is not None:
        dependency_lock = SqlAlchemyDependencyLockRepository(session).get(
            payload.dependency_lock_id, project_id=project_id
        )
        if dependency_lock is None:
            raise EngineeringError(
                EngineeringErrorCode.DEPENDENCY_LOCK_REQUIRED,
                "Requested DependencyLock is not available for this project.",
                details={"lock_id": str(payload.dependency_lock_id)},
            )
    bundle = FirmwareService().generate(
        selected.config,
        build_target=payload.build_target,
        board_name=payload.board_name,
        dependency_lock=dependency_lock,
    )
    saved = SqlAlchemyFirmwareRepository(session).add(bundle, commit=False)
    dependency_service = _dependency_service(session)
    for upstream_type, upstream_id, reason in (
        ("MCUConfigIR", saved.firmware.mcu_config_id, "FirmwareIR mcu_config_id"),
        ("SourceRevision", saved.firmware.source_revision_id, "FirmwareIR source_revision_id"),
    ):
        dependency_service.bind(
            project_id,
            upstream_type=upstream_type,
            upstream_id=str(upstream_id),
            downstream_type="FirmwareIR",
            downstream_id=str(saved.firmware.id),
            dependency_kind=DependencyKind.GENERATION,
            required=True,
            invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
            reason=reason,
            commit=False,
        )
    session.commit()
    return ApiEnvelope(data=_firmware_bundle_data(saved), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/firmware",
    response_model=ApiEnvelope[FirmwareBundleData],
    tags=["firmware"],
)
def get_firmware(
    project_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[FirmwareBundleData]:
    _service(session).get(project_id)
    bundle = SqlAlchemyFirmwareRepository(session).latest_for_project(project_id)
    if bundle is None:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "No current FirmwareIR has been generated for this project",
            details={"project_id": str(project_id)},
        )
    _ensure_current_firmware_mcu_config(session, project_id, bundle)
    return ApiEnvelope(data=_firmware_bundle_data(bundle), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/build",
    response_model=ApiEnvelope[BuildRunData],
    status_code=status.HTTP_201_CREATED,
    tags=["build"],
)
def build_firmware(
    project_id: UUID,
    payload: BuildRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[BuildRunData]:
    _service(session).get(project_id)
    firmwares = SqlAlchemyFirmwareRepository(session)
    bundle = firmwares.get(payload.firmware_id, project_id=project_id)
    latest = firmwares.latest_for_project(project_id)
    if bundle is None or latest is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "FirmwareIR is not available for build",
            details={"firmware_id": str(payload.firmware_id), "project_id": str(project_id)},
        )
    if bundle.firmware.id != latest.firmware.id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Selected FirmwareIR is stale",
            details={
                "reason": "STALE_FIRMWARE_IR",
                "firmware_id": str(payload.firmware_id),
                "latest_firmware_id": str(latest.firmware.id),
            },
        )
    _ensure_current_firmware_mcu_config(session, project_id, bundle)
    snapshot, build = FirmwareBuildService().build(
        bundle,
        request.app.state.settings.data_dir / "m12-builds" / str(project_id),
        component_cache_root=request.app.state.settings.data_dir / "component-cache",
    )
    saved = SqlAlchemyBuildRunRepository(session).add(snapshot, build, commit=False)
    event_payload = {
        "project_id": str(project_id),
        "build_run_id": str(saved.id),
        "firmware_id": str(saved.firmware_id),
        "source_revision_id": str(saved.source_revision_id),
        "status": saved.status.value,
        "build_input_hash": saved.build_input_hash,
    }
    EventOutboxService(SqlAlchemyOutboxRepository(session)).enqueue(
        event_type="build.completed",
        aggregate_type="BuildRun",
        aggregate_id=str(saved.id),
        aggregate_revision=saved.revision,
        event_key=stable_event_key("build.completed", "BuildRun", saved.id, saved.revision),
        payload=event_payload,
        payload_hash=payload_sha256(event_payload),
        project_id=project_id,
        commit=False,
    )
    dependency_service = _dependency_service(session)
    for upstream_type, upstream_id, dependency_kind, reason in (
        (
            "FirmwareIR",
            saved.firmware_id,
            DependencyKind.GENERATION,
            "BuildRun firmware_id",
        ),
        (
            "SourceRevision",
            saved.source_revision_id,
            DependencyKind.INPUT,
            "BuildRun source_revision_id",
        ),
    ):
        dependency_service.bind(
            project_id,
            upstream_type=upstream_type,
            upstream_id=str(upstream_id),
            downstream_type="BuildRun",
            downstream_id=str(saved.id),
            dependency_kind=dependency_kind,
            required=True,
            invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
            reason=reason,
            commit=False,
        )
    session.commit()
    return ApiEnvelope(data=_build_run_data(saved), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/builds",
    response_model=ApiEnvelope[BuildListData],
    tags=["build"],
)
def list_builds(
    project_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[BuildListData]:
    _service(session).get(project_id)
    builds = SqlAlchemyBuildRunRepository(session).list_for_project(project_id)
    return ApiEnvelope(
        data=BuildListData(builds=[_build_run_data(build) for build in builds]),
        request_id=_request_id(request),
    )


@router.get(
    "/projects/{project_id}/builds/{build_id}",
    response_model=ApiEnvelope[BuildRunData],
    tags=["build"],
)
def get_build(
    project_id: UUID,
    build_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[BuildRunData]:
    _service(session).get(project_id)
    build = SqlAlchemyBuildRunRepository(session).get(build_id, project_id=project_id)
    if build is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "BuildRun is not available for this project",
            details={"build_id": str(build_id), "project_id": str(project_id)},
        )
    return ApiEnvelope(data=_build_run_data(build), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/analysis/static",
    response_model=ApiEnvelope[FirmwareStaticAnalysisData],
    status_code=status.HTTP_201_CREATED,
    tags=["analysis"],
)
def analyze_firmware_static(
    project_id: UUID,
    payload: StaticAnalysisRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[FirmwareStaticAnalysisData]:
    _service(session).get(project_id)
    firmwares = SqlAlchemyFirmwareRepository(session)
    bundle = firmwares.get(payload.firmware_id, project_id=project_id)
    latest = firmwares.latest_for_project(project_id)
    if bundle is None or latest is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "FirmwareIR is not available for static analysis",
            details={"firmware_id": str(payload.firmware_id), "project_id": str(project_id)},
        )
    if bundle.firmware.id != latest.firmware.id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Selected FirmwareIR is stale",
            details={
                "reason": "STALE_FIRMWARE_IR",
                "firmware_id": str(payload.firmware_id),
                "latest_firmware_id": str(latest.firmware.id),
            },
        )
    _ensure_current_firmware_mcu_config(session, project_id, bundle)
    config_bundle = SqlAlchemyMCUConfigRepository(session).get(
        bundle.firmware.mcu_config_id, project_id=project_id
    )
    analysis = FirmwareStaticAnalysisService(
        getattr(request.app.state, "static_analysis_provider", None)
    ).analyze(
        bundle,
        mcu_config=config_bundle.config if config_bundle is not None else None,
        run_cppcheck=payload.run_cppcheck,
    )
    saved = SqlAlchemyFirmwareStaticAnalysisRepository(session).add(analysis, commit=False)
    dependency_service = _dependency_service(session)
    for upstream_type, upstream_id, dependency_kind, reason in (
        (
            "FirmwareIR",
            saved.firmware_id,
            DependencyKind.GENERATION,
            "StaticAnalysis firmware_id",
        ),
        (
            "SourceRevision",
            saved.source_revision_id,
            DependencyKind.INPUT,
            "StaticAnalysis source_revision_id",
        ),
    ):
        dependency_service.bind(
            project_id,
            upstream_type=upstream_type,
            upstream_id=str(upstream_id),
            downstream_type="StaticAnalysis",
            downstream_id=str(saved.id),
            dependency_kind=dependency_kind,
            required=True,
            invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
            reason=reason,
            commit=False,
        )
    session.commit()
    return ApiEnvelope(data=_static_analysis_data(saved), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/analysis/static",
    response_model=ApiEnvelope[StaticAnalysisListData],
    tags=["analysis"],
)
def list_firmware_static_analyses(
    project_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[StaticAnalysisListData]:
    _service(session).get(project_id)
    analyses = SqlAlchemyFirmwareStaticAnalysisRepository(session).list_for_project(project_id)
    return ApiEnvelope(
        data=StaticAnalysisListData(
            analyses=[_static_analysis_data(analysis) for analysis in analyses]
        ),
        request_id=_request_id(request),
    )


@router.get(
    "/projects/{project_id}/analysis/static/{analysis_id}",
    response_model=ApiEnvelope[FirmwareStaticAnalysisData],
    tags=["analysis"],
)
def get_firmware_static_analysis(
    project_id: UUID,
    analysis_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[FirmwareStaticAnalysisData]:
    _service(session).get(project_id)
    analysis = SqlAlchemyFirmwareStaticAnalysisRepository(session).get(
        analysis_id, project_id=project_id
    )
    if analysis is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Firmware static analysis is not available for this project",
            details={"analysis_id": str(analysis_id), "project_id": str(project_id)},
        )
    return ApiEnvelope(data=_static_analysis_data(analysis), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/evidence",
    response_model=ApiEnvelope[EvidenceData],
    status_code=status.HTTP_201_CREATED,
    tags=["evidence"],
)
def register_evidence(
    project_id: UUID,
    payload: EvidenceCreateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[EvidenceData]:
    _service(session).get(project_id)
    evidence = SqlAlchemyEvidenceRepository(session).add(
        Evidence(
            project_id=project_id,
            evidence_type=payload.evidence_type,
            locator=payload.locator,
            source_uri=payload.source_uri,
            content_hash=payload.content_hash,
            summary=payload.summary,
        )
    )
    return ApiEnvelope(data=_evidence_data(evidence), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/evidence/{evidence_id}",
    response_model=ApiEnvelope[EvidenceData],
    tags=["evidence"],
)
def get_evidence(
    project_id: UUID,
    evidence_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[EvidenceData]:
    _service(session).get(project_id)
    repository = SqlAlchemyEvidenceRepository(session)
    evidence = repository.get(evidence_id, project_id=project_id)
    if evidence is None:
        if repository.exists(evidence_id):
            raise EngineeringError(
                EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
                "Evidence belongs to a different project",
                details={"evidence_id": str(evidence_id), "project_id": str(project_id)},
            )
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Evidence was not found",
            details={"evidence_id": str(evidence_id)},
        )
    return ApiEnvelope(data=_evidence_data(evidence), request_id=_request_id(request))


@router.post(
    "/requirements/analyze/structured",
    response_model=ApiEnvelope[RequirementAnalysisData],
    status_code=status.HTTP_201_CREATED,
    tags=["requirements"],
)
def analyze_structured_requirements(
    payload: RequirementStructuredAnalysisRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[RequirementAnalysisData]:
    _service(session).get(payload.project_id)
    repository = _requirement_profile_repository(session)
    analysis = RequirementAnalysisService(
        RequirementProfileRegistry(repository),
        evidence_repository=SqlAlchemyEvidenceRepository(session),
    ).analyze_structured(
        project_id=payload.project_id,
        profile_name=payload.profile_name,
        profile_version=payload.profile_version,
        values=payload.values,
        evidence_refs=payload.evidence_refs,
    )
    saved = persist_requirement_analysis_bundle(session, analysis)
    return ApiEnvelope(
        data=RequirementAnalysisData.model_validate(saved.model_dump(mode="json")),
        request_id=_request_id(request),
    )


@router.post(
    "/requirements/analyze/natural-language",
    response_model=ApiEnvelope[RequirementAnalysisData],
    status_code=status.HTTP_201_CREATED,
    tags=["requirements"],
)
async def analyze_natural_language_requirements(
    payload: RequirementNaturalLanguageAnalysisRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[RequirementAnalysisData]:
    _service(session).get(payload.project_id)
    repository = _requirement_profile_repository(session)
    provider = getattr(request.app.state, "ai_provider", None)
    generation = None
    if provider is not None:
        generation = StructuredGenerationService(
            provider,
            PromptRegistry(SqlAlchemyPromptRepository(session)),
            SqlAlchemyAIUsageRepository(session),
        )
    analysis = await RequirementAnalysisService(
        RequirementProfileRegistry(repository),
        structured_generation=generation,
        evidence_repository=SqlAlchemyEvidenceRepository(session),
    ).analyze_natural_language(
        project_id=payload.project_id,
        profile_name=payload.profile_name,
        profile_version=payload.profile_version,
        source_text=payload.source_text,
        evidence_refs=payload.evidence_refs,
    )
    saved = persist_requirement_analysis_bundle(session, analysis)
    return ApiEnvelope(
        data=RequirementAnalysisData.model_validate(saved.model_dump(mode="json")),
        request_id=_request_id(request),
    )


@router.post(
    "/projects/{project_id}/documents",
    response_model=ApiEnvelope[DocumentData],
    status_code=status.HTTP_201_CREATED,
    tags=["documents"],
)
def upload_document(
    project_id: UUID,
    payload: DocumentUploadRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DocumentData]:
    _service(session).get(project_id)
    try:
        content = b64decode(payload.content_base64, validate=True)
    except (Base64Error, ValueError):
        raise EngineeringError(
            EngineeringErrorCode.VALIDATION_ERROR,
            "content_base64 is not valid base64",
        ) from None
    document = DocumentService(
        SqlAlchemyDocumentRepository(session), request.app.state.settings.data_dir
    ).upload(
        content,
        filename=payload.filename,
        project_id=project_id,
        document_type=payload.document_type,
        vendor=payload.vendor,
        product=payload.product,
        version_label=payload.version_label,
    )
    return ApiEnvelope(data=_document_data(document), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/documents/{document_id}",
    response_model=ApiEnvelope[DocumentData],
    tags=["documents"],
)
def get_document(
    project_id: UUID, document_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[DocumentData]:
    _service(session).get(project_id)
    document = DocumentService(
        SqlAlchemyDocumentRepository(session), request.app.state.settings.data_dir
    ).get(document_id, project_id=project_id)
    return ApiEnvelope(data=_document_data(document), request_id=_request_id(request))


@router.get("/devices/{device_ref}", response_model=ApiEnvelope[DeviceData], tags=["devices"])
def get_device(
    device_ref: str,
    request: Request,
    package: str | None = None,
) -> ApiEnvelope[DeviceData]:
    device = device_provider.get_device(device_ref, package=package)
    if device is None:
        raise EngineeringError(
            EngineeringErrorCode.DEVICE_NOT_FOUND,
            "Device or package was not found",
            details={"device_ref": device_ref, "package": package},
        )
    return ApiEnvelope(data=_device_data(device), request_id=_request_id(request))


@router.get(
    "/devices/{device_ref}/pins/{pin_name}",
    response_model=ApiEnvelope[DevicePinQueryData],
    tags=["devices"],
)
def query_device_pin(
    device_ref: str,
    pin_name: str,
    request: Request,
    package: str | None = None,
    peripheral: str | None = None,
    signal: str | None = None,
) -> ApiEnvelope[DevicePinQueryData]:
    pin = device_provider.query_pin(
        device_ref,
        pin_name,
        package=package,
        peripheral=peripheral,
        signal=signal,
    )
    return ApiEnvelope(data=DevicePinQueryData(pin=_pin_data(pin)), request_id=_request_id(request))


@router.post(
    "/projects",
    response_model=ApiEnvelope[ProjectData],
    status_code=status.HTTP_201_CREATED,
    tags=["projects"],
)
def create_project(
    payload: ProjectCreate,
    request: Request,
    response: Response,
    session: SessionDependency,
) -> ApiEnvelope[ProjectData]:
    project = _service(session).create(**payload.model_dump(), commit=False)
    event_payload = {
        "project_id": str(project.id),
        "name": project.name,
        "revision": project.revision,
    }
    EventOutboxService(SqlAlchemyOutboxRepository(session)).enqueue(
        event_type="project.created",
        aggregate_type="Project",
        aggregate_id=str(project.id),
        aggregate_revision=project.revision,
        event_key=stable_event_key("project.created", "Project", project.id, project.revision),
        payload=event_payload,
        payload_hash=payload_sha256(event_payload),
        project_id=project.id,
        commit=False,
    )
    request.app.state.crash_injector.maybe_crash(CrashPoint.AFTER_OUTBOX_INSERT_BEFORE_COMMIT)
    session.commit()
    request.app.state.crash_injector.maybe_crash(CrashPoint.AFTER_BUSINESS_COMMIT_BEFORE_DISPATCH)
    _set_etag(response, project.revision)
    return ApiEnvelope(data=_project_data(project), request_id=_request_id(request))


@router.get("/projects", response_model=ApiEnvelope[ProjectListData], tags=["projects"])
def list_projects(request: Request, session: SessionDependency) -> ApiEnvelope[ProjectListData]:
    items = [_project_data(project) for project in _service(session).list()]
    return ApiEnvelope(data=ProjectListData(items=items), request_id=_request_id(request))


@router.get("/projects/{project_id}", response_model=ApiEnvelope[ProjectData], tags=["projects"])
def get_project(
    project_id: UUID,
    request: Request,
    response: Response,
    session: SessionDependency,
) -> ApiEnvelope[ProjectData]:
    project = _service(session).get(project_id)
    _set_etag(response, project.revision)
    return ApiEnvelope(data=_project_data(project), request_id=_request_id(request))


@router.patch("/projects/{project_id}", response_model=ApiEnvelope[ProjectData], tags=["projects"])
def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    request: Request,
    response: Response,
    session: SessionDependency,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ApiEnvelope[ProjectData]:
    expected_revision = _expected_revision(if_match, payload.expected_revision)
    changes = payload.model_dump(exclude={"expected_revision"}, exclude_unset=True)
    project = _service(session).update(
        project_id,
        expected_revision=expected_revision,
        **changes,
    )
    _set_etag(response, project.revision)
    return ApiEnvelope(data=_project_data(project), request_id=_request_id(request))


@router.delete("/projects/{project_id}", response_model=ApiEnvelope[ProjectData], tags=["projects"])
def delete_project(
    project_id: UUID,
    request: Request,
    response: Response,
    session: SessionDependency,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    expected_revision: int | None = None,
) -> ApiEnvelope[ProjectData]:
    revision = _expected_revision(if_match, expected_revision)
    project = _service(session).delete(project_id, expected_revision=revision)
    _set_etag(response, project.revision)
    return ApiEnvelope(data=_project_data(project), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/domains",
    response_model=ApiEnvelope[DomainActivationListData],
    tags=["domains"],
)
def list_domain_activations(
    project_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[DomainActivationListData]:
    items = [
        _domain_activation_data(item)
        for item in _domain_service(request, session).list_activations(project_id)
    ]
    return ApiEnvelope(data=DomainActivationListData(items=items), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/domains/available",
    response_model=ApiEnvelope[DomainAvailableListData],
    tags=["domains"],
)
def list_available_domains(
    project_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[DomainAvailableListData]:
    available = _domain_service(request, session).available(project_id)
    items = [
        DomainAvailableData(
            descriptor=_domain_descriptor_data(descriptor),
            active=active,
        )
        for descriptor, active in available
    ]
    return ApiEnvelope(data=DomainAvailableListData(items=items), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/domains/resolve-composition",
    response_model=ApiEnvelope[DomainCompositionData],
    tags=["domains"],
)
def resolve_domain_composition(
    project_id: UUID,
    payload: DomainValidationRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DomainCompositionData]:
    composition = _domain_service(request, session).resolve(
        project_id,
        payload.domain_ids,
        selected_capabilities=payload.selected_capabilities,
    )
    return ApiEnvelope(data=_domain_composition_data(composition), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/domains/{domain_id}/activate",
    response_model=ApiEnvelope[DomainActivationData],
    status_code=status.HTTP_201_CREATED,
    tags=["domains"],
)
def activate_domain(
    project_id: UUID,
    domain_id: str,
    payload: DomainActivationRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DomainActivationData]:
    activation = _domain_service(request, session).activate(
        project_id,
        domain_id,
        configuration=payload.configuration,
        activated_by=payload.activated_by,
    )
    return ApiEnvelope(data=_domain_activation_data(activation), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/domains/{domain_id}/deactivate",
    response_model=ApiEnvelope[DomainActivationData],
    tags=["domains"],
)
def deactivate_domain(
    project_id: UUID,
    domain_id: str,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DomainActivationData]:
    activation = _domain_service(request, session).deactivate(project_id, domain_id)
    return ApiEnvelope(data=_domain_activation_data(activation), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/domains/{domain_id}/state",
    response_model=ApiEnvelope[DomainActivationData],
    tags=["domains"],
)
def get_domain_state(
    project_id: UUID,
    domain_id: str,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DomainActivationData]:
    activation = _domain_service(request, session).state(project_id, domain_id)
    return ApiEnvelope(data=_domain_activation_data(activation), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/domains/{domain_id}/schema",
    response_model=ApiEnvelope[DomainSchemaData],
    tags=["domains"],
)
def get_domain_schema(
    project_id: UUID,
    domain_id: str,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DomainSchemaData]:
    service = _domain_service(request, session)
    service.ensure_project(project_id)
    descriptor = service.registry.get_descriptor(domain_id)
    return ApiEnvelope(
        data=DomainSchemaData(
            domain_id=domain_id,
            schema_version=descriptor.schema_version,
            json_schema=service.registry.schema(domain_id),
        ),
        request_id=_request_id(request),
    )


@router.post(
    "/projects/{project_id}/domains/{domain_id}/validate",
    response_model=ApiEnvelope[DomainCompositionData],
    tags=["domains"],
)
def validate_domain_composition(
    project_id: UUID,
    domain_id: str,
    payload: DomainValidationRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DomainCompositionData]:
    service = _domain_service(request, session)
    composition = service.validate(
        project_id,
        [domain_id, *payload.domain_ids],
        selected_capabilities=payload.selected_capabilities,
        validation_inputs=_domain_validation_inputs(project_id, payload, session),
    )
    return ApiEnvelope(data=_domain_composition_data(composition), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/domains/{domain_id}/artifacts",
    response_model=ApiEnvelope[DomainArtifactsData],
    tags=["domains"],
)
def list_domain_artifacts(
    project_id: UUID,
    domain_id: str,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DomainArtifactsData]:
    service = _domain_service(request, session)
    service.ensure_project(project_id)
    return ApiEnvelope(
        data=DomainArtifactsData(items=service.registry.artifacts(domain_id)),
        request_id=_request_id(request),
    )


@router.get(
    "/projects/{project_id}/ui/extensions",
    response_model=ApiEnvelope[DomainUIExtensionsData],
    tags=["domains"],
)
def list_domain_ui_extensions(
    project_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[DomainUIExtensionsData]:
    service = _domain_service(request, session)
    active = [
        item.domain_id
        for item in service.list_activations(project_id)
        if item.status is DomainActivationStatus.ACTIVE
    ]
    return ApiEnvelope(
        data=DomainUIExtensionsData(items=service.registry.ui_extensions(active)),
        request_id=_request_id(request),
    )


@router.post(
    "/projects/{project_id}/tests/generate",
    response_model=ApiEnvelope[TestGenerationData],
    status_code=status.HTTP_201_CREATED,
    tags=["tests"],
)
def generate_tests(
    project_id: UUID,
    _: TestGenerateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[TestGenerationData]:
    _service(session).get(project_id)
    requirements = SqlAlchemyRequirementRepository(session).list_for_project(project_id)
    generated = TestGenerationService().generate(project_id, requirements)
    tests = SqlAlchemyTestRepository(session)
    saved = tests.add_test_ir(generated.test_ir, commit=False)
    dependency_service = _dependency_service(session)
    for requirement_id in saved.requirement_ids:
        dependency_service.bind(
            project_id,
            upstream_type="Requirement",
            upstream_id=str(requirement_id),
            downstream_type="TestIR",
            downstream_id=str(saved.id),
            dependency_kind=DependencyKind.VERIFICATION,
            required=True,
            invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
            reason="TestIR requirement snapshot",
            commit=False,
        )
    edges = SqlAlchemyTraceabilityRepository(session)
    for case in saved.cases:
        for requirement_id in case.requirement_ids:
            edges.add(
                TraceabilityEdge(
                    project_id=project_id,
                    source_type="Requirement",
                    source_id=requirement_id,
                    relation=TraceabilityRelation.VERIFIED_BY,
                    target_type="TestCase",
                    target_id=case.id,
                ),
                commit=False,
            )
    for requirement_id in saved.requirement_ids:
        edges.add(
            TraceabilityEdge(
                project_id=project_id,
                source_type="TestIR",
                source_id=saved.id,
                relation=TraceabilityRelation.GENERATED_FROM,
                target_type="Requirement",
                target_id=requirement_id,
            ),
            commit=False,
        )
    session.commit()
    return ApiEnvelope(
        data=TestGenerationData(test_ir=saved, coverage_gaps=list(generated.coverage_gaps)),
        request_id=_request_id(request),
    )


@router.get(
    "/projects/{project_id}/tests",
    response_model=ApiEnvelope[TestIRListData],
    tags=["tests"],
)
def list_tests(
    project_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[TestIRListData]:
    _service(session).get(project_id)
    return ApiEnvelope(
        data=TestIRListData(items=SqlAlchemyTestRepository(session).list_test_irs(project_id)),
        request_id=_request_id(request),
    )


@router.get(
    "/projects/{project_id}/tests/cases",
    response_model=ApiEnvelope[TestCaseListData],
    tags=["tests"],
)
def list_test_cases(
    project_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[TestCaseListData]:
    _service(session).get(project_id)
    test_ir = _select_test_ir(session, project_id, None)
    return ApiEnvelope(
        data=TestCaseListData(items=list(test_ir.cases) if test_ir else []),
        request_id=_request_id(request),
    )


@router.post(
    "/projects/{project_id}/tests/run",
    response_model=ApiEnvelope[TestRun],
    status_code=status.HTTP_201_CREATED,
    tags=["tests"],
)
def run_tests(
    project_id: UUID,
    payload: TestRunRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[TestRun]:
    _service(session).get(project_id)
    if not _source_revision_exists(session, project_id, payload.source_revision_id):
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "SourceRevision is not available for this project",
            details={"source_revision_id": str(payload.source_revision_id)},
        )
    test_ir = _select_test_ir(session, project_id, payload.test_ir_id)
    if test_ir is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "TestIR is not available for this project",
            details={"test_ir_id": str(payload.test_ir_id) if payload.test_ir_id else None},
        )
    registry = request.app.state.test_executor_registry
    registry.ensure_project(project_id, facts={"source_revision.exists": True})
    test_run = TestRunService(registry).run(
        project_id=project_id, test_ir=test_ir, source_revision_id=payload.source_revision_id
    )
    saved = SqlAlchemyTestRepository(session).add_test_run(test_run, commit=False)
    dependency_service = _dependency_service(session)
    dependency_service.bind(
        project_id,
        upstream_type="TestIR",
        upstream_id=str(saved.test_ir_id),
        downstream_type="TestRun",
        downstream_id=str(saved.id),
        dependency_kind=DependencyKind.VERIFICATION,
        required=True,
        invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
        reason="TestRun executes TestIR",
        commit=False,
    )
    dependency_service.bind(
        project_id,
        upstream_type="SourceRevision",
        upstream_id=str(saved.source_revision_id),
        downstream_type="TestRun",
        downstream_id=str(saved.id),
        dependency_kind=DependencyKind.INPUT,
        required=True,
        invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
        reason="TestRun source snapshot",
        commit=False,
    )
    edges = SqlAlchemyTraceabilityRepository(session)
    for result in saved.case_results:
        edges.add(
            TraceabilityEdge(
                project_id=project_id,
                source_type="TestCase",
                source_id=result.test_case_id,
                relation=TraceabilityRelation.VERIFIED_BY,
                target_type="TestCaseResult",
                target_id=result.id,
            ),
            commit=False,
        )
    session.commit()
    return ApiEnvelope(data=saved, request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/tests/results",
    response_model=ApiEnvelope[TestRunListData],
    tags=["tests"],
)
def list_test_results(
    project_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[TestRunListData]:
    _service(session).get(project_id)
    return ApiEnvelope(
        data=TestRunListData(items=SqlAlchemyTestRepository(session).list_test_runs(project_id)),
        request_id=_request_id(request),
    )


@router.get(
    "/projects/{project_id}/tests/coverage",
    response_model=ApiEnvelope[CoverageData],
    tags=["tests"],
)
def get_test_coverage(
    project_id: UUID,
    request: Request,
    session: SessionDependency,
    source_revision_id: UUID | None = None,
) -> ApiEnvelope[CoverageData]:
    _service(session).get(project_id)
    tests = SqlAlchemyTestRepository(session)
    test_ir = _select_test_ir(session, project_id, None)
    if source_revision_id is None:
        source_revision_id = _latest_source_revision_id(session, project_id)
    elif not _source_revision_exists(session, project_id, source_revision_id):
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "SourceRevision is not available for this project",
            details={"source_revision_id": str(source_revision_id)},
        )
    test_run = tests.latest_test_run(
        project_id,
        test_ir_id=test_ir.id if test_ir else None,
        source_revision_id=source_revision_id,
    )
    coverage = TestCoverageService().calculate(
        SqlAlchemyRequirementRepository(session).list_for_project(project_id),
        test_ir,
        test_run,
        source_revision_id=source_revision_id,
    )
    return ApiEnvelope(data=_coverage_data(coverage), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/traceability",
    response_model=ApiEnvelope[TraceabilityData],
    tags=["traceability"],
)
def get_traceability(
    project_id: UUID,
    request: Request,
    session: SessionDependency,
    source_revision_id: UUID | None = None,
) -> ApiEnvelope[TraceabilityData]:
    _service(session).get(project_id)
    if source_revision_id is None:
        source_revision_id = _latest_source_revision_id(session, project_id)
    elif not _source_revision_exists(session, project_id, source_revision_id):
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "SourceRevision is not available for this project",
        )
    tests = SqlAlchemyTestRepository(session)
    test_ir = _select_test_ir(session, project_id, None)
    test_run = tests.latest_test_run(
        project_id,
        test_ir_id=test_ir.id if test_ir else None,
        source_revision_id=source_revision_id,
    )
    requirements = SqlAlchemyRequirementRepository(session).list_for_project(project_id)
    coverage = TestCoverageService().calculate(
        requirements,
        test_ir,
        test_run,
        source_revision_id=source_revision_id,
    )
    orphan_tests = [
        case.id for case in (test_ir.cases if test_ir else ()) if not case.requirement_ids
    ]
    edges = SqlAlchemyTraceabilityRepository(session).list_for_project(project_id)
    return ApiEnvelope(
        data=TraceabilityData(
            edges=[edge.model_dump(mode="json") for edge in edges],
            coverage=_coverage_data(coverage),
            orphan_tests=orphan_tests,
            uncovered_requirements=list(coverage.uncovered_requirement_ids),
        ),
        request_id=_request_id(request),
    )


@router.post(
    "/projects/{project_id}/review",
    response_model=ApiEnvelope[ReviewRun],
    status_code=status.HTTP_201_CREATED,
    tags=["review"],
)
def create_review(
    project_id: UUID,
    payload: ReviewRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[ReviewRun]:
    _service(session).get(project_id)
    if not _source_revision_exists(session, project_id, payload.source_revision_id):
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "SourceRevision is not available for this project",
            details={"source_revision_id": str(payload.source_revision_id)},
        )
    tests = SqlAlchemyTestRepository(session)
    test_ir = _select_test_ir(session, project_id, payload.test_ir_id)
    if payload.test_ir_id is not None and test_ir is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "TestIR is not available for this project",
        )
    test_run = (
        tests.get_test_run(payload.test_run_id, project_id=project_id)
        if payload.test_run_id
        else None
    )
    if payload.test_run_id is not None and test_run is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED, "TestRun is not available for this project"
        )
    if test_ir is None and test_run is not None:
        test_ir = tests.get_test_ir(test_run.test_ir_id, project_id=project_id)
        if test_ir is None:
            raise EngineeringError(
                EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
                "TestIR bound to TestRun is not available for this project",
            )
    if test_run is None and test_ir is not None:
        test_run = tests.latest_test_run(
            project_id,
            test_ir_id=test_ir.id,
            source_revision_id=payload.source_revision_id,
        )
    builds = SqlAlchemyBuildRunRepository(session).list_for_project(project_id)
    build = next(
        (
            item
            for item in builds
            if payload.build_run_id is not None and item.id == payload.build_run_id
        ),
        None,
    )
    if payload.build_run_id is None:
        build = next(
            (item for item in builds if item.source_revision_id == payload.source_revision_id),
            None,
        )
    elif build is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "BuildRun is not available for this project",
        )
    analyses = SqlAlchemyFirmwareStaticAnalysisRepository(session).list_for_project(project_id)
    static = next(
        (
            item
            for item in analyses
            if payload.static_analysis_id is not None and item.id == payload.static_analysis_id
        ),
        None,
    )
    if payload.static_analysis_id is None:
        static = next(
            (item for item in analyses if item.source_revision_id == payload.source_revision_id),
            None,
        )
    elif static is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "FirmwareStaticAnalysis is not available for this project",
        )
    schematic = None
    if payload.schematic_id is not None:
        schematic = SqlAlchemySchematicRepository(session).get(
            payload.schematic_id, project_id=project_id
        )
        if schematic is None:
            raise EngineeringError(
                EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
                "Schematic is not available for this project",
            )
    review = ReviewEngine().review(
        project_id=project_id,
        source_revision_id=payload.source_revision_id,
        requirements=SqlAlchemyRequirementRepository(session).list_for_project(project_id),
        test_ir=test_ir,
        test_run=test_run,
        build_run=build,
        static_analysis=static,
        erc_report=schematic.erc_report if schematic else None,
        policy=ReviewPolicy(
            require_build=payload.require_build,
            require_static_analysis=payload.require_static_analysis,
            require_erc=payload.require_erc,
        ),
    )
    issue_repository = SqlAlchemyIssueRepository(session)
    issue_ids: list[UUID] = []
    for finding in review.findings:
        if finding.status is not TestExecutionStatus.PASS:
            issue_ids.append(
                issue_repository.add_or_update(project_id, finding, review_id=review.id).id
            )
    saved = SqlAlchemyReviewRepository(session).add(
        review.model_copy(update={"issue_ids": tuple(issue_ids)}), commit=False
    )
    dependency_service = _dependency_service(session)
    if saved.test_run_id is not None:
        dependency_service.bind(
            project_id,
            upstream_type="TestRun",
            upstream_id=str(saved.test_run_id),
            downstream_type="ReviewRun",
            downstream_id=str(saved.id),
            dependency_kind=DependencyKind.VERIFICATION,
            required=True,
            invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
            reason="ReviewRun consumes TestRun",
            commit=False,
        )
    if saved.test_ir_id is not None:
        dependency_service.bind(
            project_id,
            upstream_type="TestIR",
            upstream_id=str(saved.test_ir_id),
            downstream_type="ReviewRun",
            downstream_id=str(saved.id),
            dependency_kind=DependencyKind.VERIFICATION,
            required=True,
            invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
            reason="ReviewRun consumes TestIR",
            commit=False,
        )
    dependency_service.bind(
        project_id,
        upstream_type="SourceRevision",
        upstream_id=str(saved.source_revision_id),
        downstream_type="ReviewRun",
        downstream_id=str(saved.id),
        dependency_kind=DependencyKind.INPUT,
        required=True,
        invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
        reason="ReviewRun source snapshot",
        commit=False,
    )
    if saved.build_run_id is not None:
        dependency_service.bind(
            project_id,
            upstream_type="BuildRun",
            upstream_id=str(saved.build_run_id),
            downstream_type="ReviewRun",
            downstream_id=str(saved.id),
            dependency_kind=DependencyKind.VERIFICATION,
            required=True,
            invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
            reason="ReviewRun consumes BuildRun",
            commit=False,
        )
    if saved.static_analysis_id is not None:
        dependency_service.bind(
            project_id,
            upstream_type="StaticAnalysis",
            upstream_id=str(saved.static_analysis_id),
            downstream_type="ReviewRun",
            downstream_id=str(saved.id),
            dependency_kind=DependencyKind.VERIFICATION,
            required=True,
            invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
            reason="ReviewRun consumes StaticAnalysis",
            commit=False,
        )
    session.commit()
    return ApiEnvelope(data=saved, request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/reviews",
    response_model=ApiEnvelope[ReviewListData],
    tags=["review"],
)
def list_reviews(
    project_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[ReviewListData]:
    _service(session).get(project_id)
    return ApiEnvelope(
        data=ReviewListData(items=SqlAlchemyReviewRepository(session).list_for_project(project_id)),
        request_id=_request_id(request),
    )


@router.get(
    "/projects/{project_id}/issues",
    response_model=ApiEnvelope[IssueListData],
    tags=["issues"],
)
def list_issues(
    project_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[IssueListData]:
    _service(session).get(project_id)
    return ApiEnvelope(
        data=IssueListData(
            items=[
                _issue_data(item)
                for item in SqlAlchemyIssueRepository(session).list_for_project(project_id)
            ]
        ),
        request_id=_request_id(request),
    )


@router.get(
    "/issues/{issue_id}",
    response_model=ApiEnvelope[IssueData],
    tags=["issues"],
)
def get_issue(
    issue_id: UUID,
    project_id: UUID,
    request: Request,
    response: Response,
    session: SessionDependency,
) -> ApiEnvelope[IssueData]:
    _service(session).get(project_id)
    issue = SqlAlchemyIssueRepository(session).get(issue_id, project_id=project_id)
    if issue is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED, "Issue is not available for this project"
        )
    _set_etag(response, issue.revision)
    return ApiEnvelope(data=_issue_data(issue), request_id=_request_id(request))


def _mutate_issue(
    issue_id: UUID,
    payload: IssueMutationRequest,
    request: Request,
    response: Response,
    session: Session,
    target: IssueStatus,
) -> ApiEnvelope[IssueData]:
    _service(session).get(payload.project_id)
    repository = SqlAlchemyIssueRepository(session)
    issue = repository.get(issue_id, project_id=payload.project_id)
    if issue is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED, "Issue is not available for this project"
        )
    expected = _expected_revision(request.headers.get("If-Match"), payload.expected_revision)
    if issue.revision != expected:
        raise EngineeringError(
            EngineeringErrorCode.REVISION_CONFLICT, "Issue revision does not match"
        )
    saved = repository.update_status(
        issue, status=target, reason=payload.reason, expected_revision=expected
    )
    if saved is None:
        raise EngineeringError(
            EngineeringErrorCode.REVISION_CONFLICT, "Issue changed during update"
        )
    _set_etag(response, saved.revision)
    return ApiEnvelope(data=_issue_data(saved), request_id=_request_id(request))


@router.post("/issues/{issue_id}/resolve", response_model=ApiEnvelope[IssueData], tags=["issues"])
def resolve_issue(
    issue_id: UUID,
    payload: IssueMutationRequest,
    request: Request,
    response: Response,
    session: SessionDependency,
) -> ApiEnvelope[IssueData]:
    return _mutate_issue(issue_id, payload, request, response, session, IssueStatus.RESOLVED)


@router.post("/issues/{issue_id}/ignore", response_model=ApiEnvelope[IssueData], tags=["issues"])
def ignore_issue(
    issue_id: UUID,
    payload: IssueMutationRequest,
    request: Request,
    response: Response,
    session: SessionDependency,
) -> ApiEnvelope[IssueData]:
    return _mutate_issue(issue_id, payload, request, response, session, IssueStatus.IGNORED)
