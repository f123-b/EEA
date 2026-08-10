"""Versioned API request and response schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

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
from pydantic import BaseModel, ConfigDict, Field


class ApiEnvelope[DataT](BaseModel):
    """Successful response envelope required by the V1 API contract."""

    model_config = ConfigDict(frozen=True)

    success: Literal[True] = True
    data: DataT
    request_id: str


class VersionData(BaseModel):
    """Version and compatibility metadata."""

    product: str
    version: str
    api_version: str
    milestone: str


class HealthResponse(BaseModel):
    """Process and database health response."""

    status: Literal["ok"]
    version: str
    database: Literal["ok"]


class ErrorData(BaseModel):
    code: EngineeringErrorCode
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    success: Literal[False] = False
    error: ErrorData
    request_id: str


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    metadata: dict[str, object] = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    status: ProjectStatus | None = None
    metadata: dict[str, object] | None = None


class ProjectData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    name: str
    description: str
    status: ProjectStatus


class ProjectListData(BaseModel):
    items: list[ProjectData]
    next_cursor: str | None = None


class EnumValues(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    artifact_status: list[ArtifactStatus] = Field(alias="ArtifactStatus")
    decision_status: list[DecisionStatus] = Field(alias="DecisionStatus")
    engineering_error_code: list[EngineeringErrorCode] = Field(alias="EngineeringErrorCode")
    evidence_type: list[EvidenceType] = Field(alias="EvidenceType")
    issue_severity: list[IssueSeverity] = Field(alias="IssueSeverity")
    issue_status: list[IssueStatus] = Field(alias="IssueStatus")
    job_status: list[JobStatus] = Field(alias="JobStatus")
    permission: list[Permission] = Field(alias="Permission")
    project_status: list[ProjectStatus] = Field(alias="ProjectStatus")
    traceability_relation: list[TraceabilityRelation] = Field(alias="TraceabilityRelation")


class EnumCatalogData(BaseModel):
    enums: EnumValues


class SchemaDescriptorData(BaseModel):
    name: str
    schema_version: str


class SchemaListData(BaseModel):
    items: list[SchemaDescriptorData]


class SchemaData(BaseModel):
    name: str
    schema_version: str
    json_schema: dict[str, object]
