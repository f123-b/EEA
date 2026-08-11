"""Versioned API request and response schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

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
    TraceabilityRelation,
    VerificationLevel,
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
    claim_conflict_status: list[ClaimConflictStatus] = Field(alias="ClaimConflictStatus")
    claim_conflict_strategy: list[ClaimConflictStrategy] = Field(alias="ClaimConflictStrategy")
    claim_conflict_type: list[ClaimConflictType] = Field(alias="ClaimConflictType")
    claim_lifecycle: list[ClaimLifecycle] = Field(alias="ClaimLifecycle")
    decision_status: list[DecisionStatus] = Field(alias="DecisionStatus")
    device_category: list[DeviceCategory] = Field(alias="DeviceCategory")
    device_merge_conflict_type: list[DeviceMergeConflictType] = Field(
        alias="DeviceMergeConflictType"
    )
    document_parse_status: list[DocumentParseStatus] = Field(alias="DocumentParseStatus")
    document_type: list[DocumentType] = Field(alias="DocumentType")
    engineering_dimension: list[EngineeringDimension] = Field(alias="EngineeringDimension")
    engineering_error_code: list[EngineeringErrorCode] = Field(alias="EngineeringErrorCode")
    evidence_type: list[EvidenceType] = Field(alias="EvidenceType")
    issue_severity: list[IssueSeverity] = Field(alias="IssueSeverity")
    issue_status: list[IssueStatus] = Field(alias="IssueStatus")
    job_status: list[JobStatus] = Field(alias="JobStatus")
    permission: list[Permission] = Field(alias="Permission")
    project_status: list[ProjectStatus] = Field(alias="ProjectStatus")
    traceability_relation: list[TraceabilityRelation] = Field(alias="TraceabilityRelation")
    verification_level: list[VerificationLevel] = Field(alias="VerificationLevel")


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


class DocumentUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID | None = None
    filename: str = Field(min_length=1, max_length=500)
    content_base64: str = Field(min_length=1, max_length=20_000_000)
    document_type: DocumentType = DocumentType.UNKNOWN
    vendor: str | None = Field(default=None, max_length=200)
    product: str | None = Field(default=None, max_length=200)
    version_label: str | None = Field(default=None, max_length=100)


class DocumentData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID | None
    filename: str
    document_type: DocumentType
    vendor: str | None
    product: str | None
    version_label: str | None
    content_hash: str
    storage_uri: str
    parse_status: DocumentParseStatus
    parse_error: str | None


class DevicePinData(BaseModel):
    name: str
    package: str | None
    package_pin: str | None
    voltage_domain: str | None
    five_v_tolerant: bool | None
    functions: list[dict[str, str | None]]
    source_refs: list[str]


class DeviceData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    manufacturer: str
    family: str
    model: str
    revision_label: str | None
    category: DeviceCategory
    packages: list[str]
    memory: dict[str, object]
    peripherals: list[str]
    pins: list[DevicePinData]
    clocks: dict[str, object]
    dma: dict[str, object]
    interrupts: dict[str, object]
    electrical: dict[str, object]
    source_refs: list[str]


class DevicePinQueryData(BaseModel):
    pin: DevicePinData
    supported: bool = True


class DeviceMergeConflictData(BaseModel):
    conflict_type: DeviceMergeConflictType
    field: str
    source_a: str
    source_b: str
    value_a: object
    value_b: object
    resolution: str
