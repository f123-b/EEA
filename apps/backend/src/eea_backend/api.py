"""M1 versioned API routes."""

import re
from base64 import b64decode
from binascii import Error as Base64Error
from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from eea_adapters.devices import Stm32G431FixtureProvider
from eea_application.intelligence import DocumentService, MultiSourceDeviceProvider
from eea_application.projects import ProjectService
from eea_application.requirements import (
    RequirementAnalysisService,
    RequirementProfileRegistry,
    build_foc_benchmark_profile,
)
from eea_core.entities import Project
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
from eea_core.requirements import RequirementProfile
from eea_core.schema_registry import create_core_schema_registry
from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy.orm import Session

from eea_backend.document_repositories import SqlAlchemyDocumentRepository
from eea_backend.repositories import SqlAlchemyProjectRepository
from eea_backend.requirement_repositories import (
    SqlAlchemyRequirementAnalysisRepository,
    SqlAlchemyRequirementProfileRepository,
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
    ProjectCreate,
    ProjectData,
    ProjectListData,
    ProjectUpdate,
    RequirementAnalysisData,
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


def _pin_data(pin: DevicePin) -> DevicePinData:
    return DevicePinData.model_validate(pin.model_dump(mode="json"))


def _device_data(device: Device) -> DeviceData:
    return DeviceData.model_validate(device.model_dump(mode="json"))


def _requirement_profile_repository(session: Session) -> SqlAlchemyRequirementProfileRepository:
    return SqlAlchemyRequirementProfileRepository(session)


def _ensure_builtin_profile(
    repository: SqlAlchemyRequirementProfileRepository,
    profile_name: str,
    profile_version: str,
) -> RequirementProfile | None:
    profile = repository.get(profile_name, profile_version)
    if profile is None and (profile_name, profile_version) == ("foc-benchmark", "1.0"):
        profile = repository.add(build_foc_benchmark_profile())
    return profile


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
    profile = _ensure_builtin_profile(
        _requirement_profile_repository(session), profile_name, profile_version
    )
    if profile is None:
        raise EngineeringError(
            EngineeringErrorCode.SCHEMA_VERSION_UNSUPPORTED,
            "Requirement profile version is not registered",
            details={"profile_name": profile_name, "profile_version": profile_version},
        )
    return ApiEnvelope(data=_requirement_profile_data(profile), request_id=_request_id(request))


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
    _ensure_builtin_profile(repository, payload.profile_name, payload.profile_version)
    analysis = RequirementAnalysisService(
        RequirementProfileRegistry(repository)
    ).analyze_structured(
        project_id=payload.project_id,
        profile_name=payload.profile_name,
        profile_version=payload.profile_version,
        values=payload.values,
        evidence_refs=payload.evidence_refs,
    )
    saved = SqlAlchemyRequirementAnalysisRepository(session).add(analysis)
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
