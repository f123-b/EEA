"""M1 versioned API routes."""

import re
from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from eea_application.projects import ProjectService
from eea_core.entities import Project
from eea_core.enums import (
    ArtifactStatus,
    DecisionStatus,
    EngineeringErrorCode,
    EvidenceType,
    IssueSeverity,
    IssueStatus,
    JobStatus,
    Permission,
    ProjectStatus,
    TraceabilityRelation,
)
from eea_core.errors import EngineeringError
from eea_core.schema_registry import create_core_schema_registry
from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy.orm import Session

from eea_backend.repositories import SqlAlchemyProjectRepository
from eea_backend.schemas import (
    ApiEnvelope,
    EnumCatalogData,
    EnumValues,
    ProjectCreate,
    ProjectData,
    ProjectListData,
    ProjectUpdate,
    SchemaData,
    SchemaDescriptorData,
    SchemaListData,
)

router = APIRouter()
schema_registry = create_core_schema_registry()
ETAG_PATTERN = re.compile(r'^(?:W/)?"(?P<revision>[1-9][0-9]*)"$')


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


SessionDependency = Annotated[Session, Depends(get_session)]


def _service(session: Session) -> ProjectService:
    return ProjectService(SqlAlchemyProjectRepository(session))


def _project_data(project: Project) -> ProjectData:
    return ProjectData.model_validate(project, from_attributes=True)


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
            DecisionStatus,
            EngineeringErrorCode,
            EvidenceType,
            IssueSeverity,
            IssueStatus,
            JobStatus,
            Permission,
            ProjectStatus,
            TraceabilityRelation,
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
