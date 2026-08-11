"""M1 versioned API routes."""

import re
from base64 import b64decode
from binascii import Error as Base64Error
from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from eea_adapters.devices import Stm32G431FixtureProvider
from eea_application.ai import PromptRegistry, StructuredGenerationService
from eea_application.intelligence import DocumentService, MultiSourceDeviceProvider
from eea_application.pin_planner import PinPlannerService
from eea_application.projects import ProjectService
from eea_application.requirements import (
    RequirementAnalysisService,
    RequirementProfileRegistry,
)
from eea_core.entities import Evidence, Project
from eea_core.enums import (
    ArtifactStatus,
    ClaimConflictStatus,
    ClaimConflictStrategy,
    ClaimConflictType,
    ClaimLifecycle,
    DecisionStatus,
    DeviceCategory,
    DeviceMergeConflictType,
    DocumentParseStatus,
    DocumentType,
    EngineeringDimension,
    EngineeringErrorCode,
    EvidenceType,
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
    TraceabilityRelation,
    VerificationLevel,
)
from eea_core.errors import EngineeringError
from eea_core.intelligence import Device, DevicePin, Document
from eea_core.pin_planner import PinAssignment, PinLock, PinPlan, PinRequirement
from eea_core.requirements import RequirementProfile
from eea_core.schema_registry import create_core_schema_registry
from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy.orm import Session

from eea_backend.claim_repositories import SqlAlchemyEngineeringClaimRepository
from eea_backend.document_repositories import SqlAlchemyDocumentRepository
from eea_backend.pin_planner_repositories import SqlAlchemyPinPlanRepository
from eea_backend.repositories import (
    SqlAlchemyAIUsageRepository,
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
    DeviceData,
    DevicePinData,
    DevicePinQueryData,
    DocumentData,
    DocumentUploadRequest,
    EnumCatalogData,
    EnumValues,
    EvidenceCreateRequest,
    EvidenceData,
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
    RequirementAnalysisData,
    RequirementNaturalLanguageAnalysisRequest,
    RequirementProfileData,
    RequirementStructuredAnalysisRequest,
    SchemaData,
    SchemaDescriptorData,
    SchemaListData,
)

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


def _project_data(project: Project) -> ProjectData:
    return ProjectData.model_validate(project, from_attributes=True)


def _document_data(document: Document) -> DocumentData:
    return DocumentData.model_validate(document.model_dump(mode="json"))


def _evidence_data(evidence: Evidence) -> EvidenceData:
    return EvidenceData.model_validate(evidence.model_dump(mode="json"))


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


def _requirement_profile_repository(session: Session) -> SqlAlchemyRequirementProfileRepository:
    return SqlAlchemyRequirementProfileRepository(session)


def _requirement_profile_data(profile: RequirementProfile) -> RequirementProfileData:
    return RequirementProfileData.model_validate(profile.model_dump(mode="json"))


def _request_id(request: Request) -> str:
    return str(request.state.request_id)


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
            DecisionStatus,
            DeviceCategory,
            DeviceMergeConflictType,
            DocumentParseStatus,
            DocumentType,
            EngineeringDimension,
            EngineeringErrorCode,
            EvidenceType,
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
            TraceabilityRelation,
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
    plan = SqlAlchemyPinPlanRepository(session).add(plan)
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
    saved_lock = repository.add_lock(lock, commit=False)
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
    "/evidence",
    response_model=ApiEnvelope[EvidenceData],
    status_code=status.HTTP_201_CREATED,
    tags=["evidence"],
)
def register_evidence(
    payload: EvidenceCreateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[EvidenceData]:
    _service(session).get(payload.project_id)
    evidence = SqlAlchemyEvidenceRepository(session).add(
        Evidence(
            project_id=payload.project_id,
            evidence_type=payload.evidence_type,
            locator=payload.locator,
            source_uri=payload.source_uri,
            content_hash=payload.content_hash,
            summary=payload.summary,
        )
    )
    return ApiEnvelope(data=_evidence_data(evidence), request_id=_request_id(request))


@router.get("/evidence/{evidence_id}", response_model=ApiEnvelope[EvidenceData], tags=["evidence"])
def get_evidence(
    evidence_id: UUID,
    request: Request,
    session: SessionDependency,
    project_id: UUID | None = None,
) -> ApiEnvelope[EvidenceData]:
    evidence = SqlAlchemyEvidenceRepository(session).get(evidence_id)
    if evidence is None:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Evidence was not found",
            details={"evidence_id": str(evidence_id)},
        )
    if project_id is not None and evidence.project_id != project_id:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Evidence belongs to a different project",
            details={"evidence_id": str(evidence_id), "project_id": str(project_id)},
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
    "/documents",
    response_model=ApiEnvelope[DocumentData],
    status_code=status.HTTP_201_CREATED,
    tags=["documents"],
)
def upload_document(
    payload: DocumentUploadRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DocumentData]:
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
        project_id=payload.project_id,
        document_type=payload.document_type,
        vendor=payload.vendor,
        product=payload.product,
        version_label=payload.version_label,
    )
    return ApiEnvelope(data=_document_data(document), request_id=_request_id(request))


@router.get(
    "/documents/{document_id}",
    response_model=ApiEnvelope[DocumentData],
    tags=["documents"],
)
def get_document(
    document_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[DocumentData]:
    document = DocumentService(
        SqlAlchemyDocumentRepository(session), request.app.state.settings.data_dir
    ).get(document_id)
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
    project = _service(session).create(**payload.model_dump())
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
