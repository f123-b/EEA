"""Versioned API request and response schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from eea_core.circuit import CircuitComponent, CircuitConstraint, CircuitNet, PowerNet
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
from eea_core.mcu_config import (
    DMAIR,
    ClockIR,
    DebugConfigIR,
    GPIOConfig,
    InterruptConfigIR,
    MemoryConfigIR,
    PeripheralConfigIR,
)
from eea_core.schematic import ErcIssue
from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class EvidenceCreateRequest(BaseModel):
    """Minimal client registration bridge for evidence usable by M6 analysis."""

    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    evidence_type: EvidenceType
    locator: dict[str, object] = Field(default_factory=dict)
    source_uri: str | None = Field(default=None, max_length=2000)
    content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    summary: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def enforce_client_allowlist(self) -> "EvidenceCreateRequest":
        if self.evidence_type not in {
            EvidenceType.DOCUMENT,
            EvidenceType.USER_CONFIRMATION,
            EvidenceType.DEVICE_DB,
        }:
            raise ValueError("this evidence type must be produced by a trusted execution path")
        return self


class EvidenceData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID | None
    evidence_type: EvidenceType
    locator: dict[str, object]
    source_uri: str | None
    content_hash: str | None
    summary: str


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
    requirement_field_status: list[RequirementFieldStatus] = Field(alias="RequirementFieldStatus")
    requirement_priority: list[RequirementPriority] = Field(alias="RequirementPriority")
    requirement_status: list[RequirementStatus] = Field(alias="RequirementStatus")
    requirement_type: list[RequirementType] = Field(alias="RequirementType")
    requirement_value_type: list[RequirementValueType] = Field(alias="RequirementValueType")
    traceability_relation: list[TraceabilityRelation] = Field(alias="TraceabilityRelation")
    verification_level: list[VerificationLevel] = Field(alias="VerificationLevel")


class EnumCatalogData(BaseModel):
    enums: EnumValues


class SchemaDescriptorData(BaseModel):
    name: str
    schema_version: str


class SchemaListData(BaseModel):
    items: list[SchemaDescriptorData]


class RequirementProfileData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    profile_name: str
    profile_version: str
    purpose: str
    fields: list[dict[str, object]]
    evidence_contracts: list[dict[str, object]]
    active: bool


class RequirementStructuredAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    profile_name: str = Field(min_length=1, max_length=120)
    profile_version: str = Field(min_length=1, max_length=50)
    values: dict[str, object] = Field(default_factory=dict)
    evidence_refs: dict[str, UUID] = Field(default_factory=dict)


class RequirementNaturalLanguageAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    profile_name: str = Field(min_length=1, max_length=120)
    profile_version: str = Field(min_length=1, max_length=50)
    source_text: str = Field(min_length=1, max_length=100_000)
    evidence_refs: dict[str, UUID] = Field(default_factory=dict)


class RequirementCompletenessData(BaseModel):
    status: RequirementStatus
    score: float
    required_field_keys: list[str]
    missing_field_keys: list[str]
    ambiguous_field_keys: list[str]
    missing_evidence_keys: list[str]


class RequirementAnalysisData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID
    profile_name: str
    profile_version: str
    requirements: list[dict[str, object]]
    field_observations: list[dict[str, object]]
    claims: list[dict[str, object]]
    issues: list[dict[str, object]]
    follow_up_questions: list[dict[str, object]]
    completeness: RequirementCompletenessData
    requirement_ids: list[UUID]
    claim_ids: list[UUID]


class PinRequirementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_name: str = Field(min_length=1, max_length=200)
    required_peripheral: str = Field(min_length=1, max_length=100)
    required_function: str = Field(min_length=1, max_length=100)
    direction: str = Field(default="UNKNOWN", min_length=1, max_length=30)
    electrical_requirements: dict[str, object] = Field(default_factory=dict)
    hard_constraints: dict[str, object] = Field(default_factory=dict)
    preferred_constraints: dict[str, object] = Field(default_factory=dict)
    timing_constraints: dict[str, object] = Field(default_factory=dict)
    requirement_ids: list[UUID] = Field(default_factory=list)
    claim_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class PinPlannerGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_id: UUID
    device_ref: str = Field(min_length=1, max_length=200)
    package: str | None = Field(default=None, max_length=100)
    requirements: list[PinRequirementCreate] = Field(min_length=1)


class PinPlanData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID
    analysis_id: UUID | None
    device_ref: str
    package: str | None
    requirements: list[dict[str, object]]
    candidates: list[dict[str, object]]
    assignments: list[dict[str, object]]
    locks: list[dict[str, object]]
    rule_results: list[dict[str, object]]


class PinAssignmentData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID
    requirement_id: UUID
    device_ref: str
    package: str | None
    pin_name: str
    function: dict[str, str]
    locked: bool
    score: float
    claim_ids: list[UUID]
    evidence_ids: list[UUID]


class PinLockData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID
    assignment_id: UUID
    locked_by: str
    reason: str


class PinAssignmentMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int | None = Field(default=None, ge=1)
    actor: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=2000)


class PinAssignmentMutationData(BaseModel):
    assignment: PinAssignmentData
    lock: PinLockData | None = None


class PinPlanValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: UUID


class PinPlanValidationData(BaseModel):
    plan_id: UUID
    plan_revision: int
    rule_results: list[dict[str, object]]


class ArchitectureGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pin_plan_id: UUID


class SystemArchitectureData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID
    pin_plan_id: UUID
    pin_plan_revision: int
    blocks: list[dict[str, object]]
    interfaces: list[dict[str, object]]
    decisions: list[dict[str, object]]
    requirement_ids: list[UUID]
    evidence_ids: list[UUID]
    source_artifact_ids: list[UUID]
    pin_assignment_revisions: dict[str, int]


class HardwareIRData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID
    architecture_id: UUID
    pin_plan_id: UUID
    pin_plan_revision: int
    modules: list[dict[str, object]]
    device_instances: list[dict[str, object]]
    power_domains: list[dict[str, object]]
    interfaces: list[dict[str, object]]
    pin_requirements: list[dict[str, object]]
    constraints: list[dict[str, object]]
    requirement_ids: list[UUID]
    evidence_ids: list[UUID]
    pin_assignment_revisions: dict[str, int]


class ArchitectureBundleData(BaseModel):
    system_architecture: SystemArchitectureData
    hardware: HardwareIRData


class CircuitGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hardware_ir_id: UUID
    components: list[CircuitComponent] = Field(default_factory=list)
    nets: list[CircuitNet] = Field(default_factory=list)
    power_nets: list[PowerNet] = Field(default_factory=list)
    constraints: list[CircuitConstraint] = Field(default_factory=list)


class CircuitData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID
    hardware_ir_id: UUID
    hardware_ir_revision: int
    components: list[dict[str, object]]
    nets: list[dict[str, object]]
    power_nets: list[dict[str, object]]
    constraints: list[dict[str, object]]
    rule_results: list[dict[str, object]]
    requirement_ids: list[UUID]
    evidence_ids: list[UUID]
    pin_assignment_revisions: dict[str, int]


class CircuitBundleData(BaseModel):
    circuit: CircuitData
    rule_results: list[dict[str, object]]


class CircuitValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    circuit_id: UUID


class CircuitValidationData(BaseModel):
    circuit_id: UUID
    circuit_revision: int
    rule_results: list[dict[str, object]]


class SchematicGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    circuit_id: UUID


class ArtifactData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID
    logical_name: str
    artifact_type: str
    version_label: str
    content_hash: str
    input_hash: str
    storage_uri: str
    parent_artifact_id: UUID | None
    dependency_ids: list[UUID]
    dependency_hashes: dict[str, str]
    created_by: str
    source_job_id: UUID | None
    generator_version: str | None
    tool_versions: dict[str, str]
    knowledge_snapshot: str | None
    status: ArtifactStatus


class SchematicData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID
    artifact_id: UUID
    circuit_id: UUID
    circuit_revision: int
    hardware_ir_id: UUID
    hardware_ir_revision: int
    format: str
    components: list[dict[str, object]]
    nets: list[dict[str, object]]
    power_nets: list[dict[str, object]]
    constraints: list[dict[str, object]]
    netlist_text: str
    content_hash: str
    input_hash: str
    preflight_results: list[dict[str, object]]
    requirement_ids: list[UUID]
    evidence_ids: list[UUID]
    pin_assignment_revisions: dict[str, int]


class ErcReportData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID
    schematic_id: UUID
    schematic_revision: int
    circuit_id: UUID
    circuit_revision: int
    status: Literal["PASS", "FAIL", "UNKNOWN"]
    tool_name: str | None
    tool_version: str | None
    executed: bool
    issues: list[dict[str, object]]
    source_revision_snapshot: dict[str, object]
    evidence_ids: list[UUID]
    recommendation: str


class SchematicBundleData(BaseModel):
    artifact: ArtifactData
    schematic: SchematicData
    erc_report: ErcReportData


class SchematicValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schematic_id: UUID


class MCUConfigGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hardware_ir_id: UUID
    circuit_id: UUID
    schematic_id: UUID
    device_instance_id: UUID
    clock: ClockIR
    gpio: list[GPIOConfig] = Field(default_factory=list)
    peripherals: list[PeripheralConfigIR] = Field(default_factory=list)
    dma: list[DMAIR] = Field(default_factory=list)
    interrupts: list[InterruptConfigIR] = Field(default_factory=list)
    memory: MemoryConfigIR | None = None
    debug: DebugConfigIR | None = None
    capability_snapshot: dict[str, object] = Field(default_factory=dict)


class MCUConfigData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID
    hardware_ir_id: UUID
    hardware_ir_revision: int
    circuit_id: UUID
    circuit_revision: int
    schematic_id: UUID
    schematic_revision: int
    device_instance_id: UUID
    clock: ClockIR
    gpio: list[GPIOConfig]
    peripherals: list[PeripheralConfigIR]
    dma: list[DMAIR]
    interrupts: list[InterruptConfigIR]
    memory: MemoryConfigIR | None
    debug: DebugConfigIR | None
    capability_snapshot: dict[str, object]
    rule_results: list[dict[str, object]]
    requirement_ids: list[UUID]
    evidence_ids: list[UUID]
    pin_assignment_revisions: dict[str, int]
    status: ArtifactStatus


class MCUConfigBundleData(BaseModel):
    config: MCUConfigData
    rule_results: list[dict[str, object]]


class MCUConfigValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_id: UUID


class MCUConfigValidationData(BaseModel):
    config_id: UUID
    config_revision: int
    rule_results: list[dict[str, object]]


class ErcImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schematic_id: UUID
    status: Literal["PASS", "FAIL"]
    tool_name: str = Field(min_length=1, max_length=100)
    tool_version: str = Field(min_length=1, max_length=100)
    issues: list[ErcIssue] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


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
