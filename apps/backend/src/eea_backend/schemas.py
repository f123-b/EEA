"""Versioned API request and response schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from eea_core.circuit import CircuitComponent, CircuitConstraint, CircuitNet, PowerNet
from eea_core.components import (
    ComponentCompatibility,
    ComponentDependencySpec,
    ComponentRelease,
    ComponentRequirement,
    ResolvedComponent,
)
from eea_core.dependency_graph import (
    DependencyNodeState,
    EngineeringDependencyEdge,
    ImpactPlan,
)
from eea_core.domain_extensions import (
    DomainContextContribution,
    DomainGeneratorContribution,
    DomainRuleContribution,
    DomainUIContribution,
    DomainValidationResult,
)
from eea_core.enums import (
    ArtifactStatus,
    BuildProfile,
    BuildStatus,
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
    DomainRulePhase,
    DomainTrustTier,
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
from eea_core.firmware import (
    BSPConfig,
    FirmwareBuildTarget,
    FirmwareInterrupt,
    FirmwareModule,
    FirmwareTask,
    MemoryLayout,
    PeripheralDriverConfig,
    SharedResource,
    StartupConfig,
)
from eea_core.hardware import (
    CommissioningState,
    CommissioningStepStatus,
    EmergencyStopSource,
    EmergencyStopState,
    HardwareIdentity,
    ProbeIdentity,
    SafeState,
    SafetyLimit,
    WatchdogState,
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
from eea_core.protocol import (
    ProtocolDefinition,
    ProtocolGenerationBundle,
    ProtocolIR,
    ProtocolValidationResult,
)
from eea_core.review import ReviewRun
from eea_core.schematic import ErcIssue
from eea_core.source import PatchProposalStatus
from eea_core.static_analysis import StaticAnalysisToolResult
from eea_core.testing import (
    AutomationLevel,
    TestCase,
    TestExecutionStatus,
    TestIR,
    TestRun,
    TestType,
)
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


class OutboxStatusData(BaseModel):
    pending: int
    processing: int
    retry: int
    processed: int
    dead_letter: int
    total: int
    expired_processing_count: int
    oldest_pending_at: datetime | None = None
    oldest_pending_age_seconds: float
    side_effect_reconcile_required_count: int


class RecoveryStatusData(BaseModel):
    healthy: bool
    pending_recovery_count: int
    expired_lease_count: int
    dead_letter_count: int
    reconcile_required_effect_count: int
    interrupted_job_count: int
    startup_recovery_completed: bool
    last_recovery_summary: dict[str, object]


class TransactionalRecoveryData(BaseModel):
    pending: int
    processing: int
    retry: int
    dead_letter: int
    reconcile_required: int
    interrupted_jobs: int


class EngineeringFreshnessData(BaseModel):
    stale: int
    invalid: int


class ProjectConsistencyData(BaseModel):
    status: Literal["CONSISTENT", "DEGRADED", "RECOVERY_REQUIRED"]
    transactional_recovery: TransactionalRecoveryData
    engineering_freshness: EngineeringFreshnessData


class RecoveryReconcileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID | None = None
    limit: int = Field(default=100, ge=1, le=1000)


class RecoveryReconcileData(BaseModel):
    reclaimed: int
    interrupted_jobs: int
    reconciled_side_effects: int
    dispatched: dict[str, int]
    reconcile_required: int
    project: ProjectConsistencyData | None = None


class CommissioningProfileData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    name: str
    version: str
    applicable_target_types: list[str]
    applicable_domains: list[str]
    required_steps: list[str]
    required_permissions: list[Permission]
    user_approval_required: bool
    safety_limits: SafetyLimit
    required_safety_capabilities: list[str]
    watchdog_policy: dict[str, object]
    emergency_stop_policy: dict[str, object]
    safe_state_policy: SafeState


class CommissioningStepResultData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    session_id: UUID
    step_id: str
    status: CommissioningStepStatus
    started_at: datetime | None
    completed_at: datetime | None
    measurements: dict[str, object]
    thresholds: dict[str, object]
    evidence_ids: list[UUID]
    tool_version: str
    rule_version: str
    operator: str
    failure_reason: str | None


class CommissioningSessionData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID
    target_id: str
    firmware_artifact_id: UUID
    firmware_hash: str
    build_run_id: UUID | None
    source_revision_id: UUID | None
    build_input_snapshot_id: UUID | None
    hardware_identity: HardwareIdentity
    probe_identity: ProbeIdentity
    board_revision: str | None
    commissioning_profile_id: UUID
    state: CommissioningState
    current_step: str | None
    started_by: str
    approved_by: str | None
    safety_limits_snapshot: SafetyLimit
    preflight_results: list[dict[str, object]]
    step_results: list[CommissioningStepResultData]
    evidence_ids: list[UUID]
    emergency_stop_state: EmergencyStopState
    watchdog_state: WatchdogState
    resource_lock_ids: list[UUID]
    permission_token_ids: list[str]
    approval_snapshot: dict[str, object] | None
    completed_at: datetime | None
    aborted_at: datetime | None


class CommissioningSessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_id: str = Field(min_length=1, max_length=500)
    firmware_artifact_id: UUID
    firmware_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    hardware_identity: HardwareIdentity
    probe_identity: ProbeIdentity
    commissioning_profile_id: UUID | None = None
    started_by: str = Field(min_length=1, max_length=200)
    build_run_id: UUID | None = None
    source_revision_id: UUID | None = None
    build_input_snapshot_id: UUID | None = None
    board_revision: str | None = Field(default=None, max_length=100)
    resource_lock_ids: list[UUID] = Field(default_factory=list)
    permission_token_ids: list[str] = Field(default_factory=list)


class CommissioningRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    permissions: list[Permission] = Field(default_factory=list)


class CommissioningStepExecuteRequest(CommissioningRevisionRequest):
    operator: str = Field(default="system", min_length=1, max_length=200)


class CommissioningApproveRequest(CommissioningRevisionRequest):
    actor: str = Field(min_length=1, max_length=200)


class CommissioningEmergencyStopRequest(CommissioningRevisionRequest):
    source: EmergencyStopSource = EmergencyStopSource.USER
    reason: str = Field(default="emergency stop requested", min_length=1, max_length=4000)
    actor: str = Field(default="system", min_length=1, max_length=200)


class CommissioningAbortRequest(CommissioningRevisionRequest):
    actor: str = Field(default="system", min_length=1, max_length=200)


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
    files: list[str] = Field(default_factory=list)
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


class DomainDescriptorData(BaseModel):
    id: str
    plugin_id: str
    name: str
    version: str
    api_version: str
    schema_version: str
    trust_tier: DomainTrustTier
    entrypoint: str
    capabilities: list[str]
    required_capabilities: list[str]
    requires_domains: list[str]
    optional_domains: list[str]
    conflicts_with: list[str]
    priority: int
    rule_phases: list[DomainRulePhase]
    generator_phases: list[str]
    migration_provider: str | None
    context_contributions: list[str]
    ui_contributions: list[str]
    permissions: list[Permission]


class DomainAvailableData(BaseModel):
    descriptor: DomainDescriptorData
    active: bool


class DomainAvailableListData(BaseModel):
    items: list[DomainAvailableData]


class DomainActivationData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID
    domain_id: str
    plugin_id: str
    plugin_version: str
    domain_schema_version: str
    configuration_schema_version: str
    configuration_schema_hash: str | None
    status: DomainActivationStatus
    configuration: dict[str, object]
    activated_at: datetime
    activated_by: str
    capability_snapshot: dict[str, object]
    dependency_snapshot: dict[str, object]


class DomainActivationListData(BaseModel):
    items: list[DomainActivationData]


class DomainCompositionData(BaseModel):
    active_domain_ids: list[str]
    ordered_domain_ids: list[str]
    dependency_edges: list[list[str]]
    capability_routes: dict[str, str]
    rules: list[DomainRuleContribution]
    generators: list[DomainGeneratorContribution]
    context_contributions: list[DomainContextContribution]
    ui_contributions: list[DomainUIContribution]
    validation_results: list[DomainValidationResult]
    composition_revision: int = 0
    selected_capabilities: dict[str, str] = Field(default_factory=dict)
    domain_snapshots: list[dict[str, object]] = Field(default_factory=list)
    rule_order: list[str] = Field(default_factory=list)
    generator_order: list[str] = Field(default_factory=list)
    plan_hash: str = ""
    compatibility_results: list[dict[str, object]] = Field(default_factory=list)
    blocked_reasons: list[dict[str, object]] = Field(default_factory=list)
    project_id: UUID | None = None
    schema_version: str | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None


class DomainSchemaData(BaseModel):
    domain_id: str
    schema_version: str
    json_schema: dict[str, object]


class DomainArtifactsData(BaseModel):
    items: list[dict[str, object]]


class DomainUIExtensionsData(BaseModel):
    items: list[DomainUIContribution]


class DomainActivationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configuration: dict[str, object] | None = None
    activated_by: str = Field(default="system", min_length=1, max_length=200)


class DomainCompositionApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain_ids: list[str] = Field(default_factory=list, max_length=100)
    selected_capabilities: dict[str, str] | None = None
    configurations: dict[str, dict[str, object]] = Field(default_factory=dict)
    expected_composition_revision: int = Field(..., ge=1)
    expected_plan_hash: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    applied_by: str = Field(default="system", min_length=1, max_length=200)


class DomainValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain_ids: list[str] = Field(default_factory=list, max_length=100)
    selected_capabilities: dict[str, str] | None = None
    configurations: dict[str, dict[str, object]] = Field(default_factory=dict)
    domain_ir: dict[str, object] | None = None
    mcu_config_id: UUID | None = None


class EnumValues(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    artifact_status: list[ArtifactStatus] = Field(alias="ArtifactStatus")
    claim_conflict_status: list[ClaimConflictStatus] = Field(alias="ClaimConflictStatus")
    claim_conflict_strategy: list[ClaimConflictStrategy] = Field(alias="ClaimConflictStrategy")
    claim_conflict_type: list[ClaimConflictType] = Field(alias="ClaimConflictType")
    claim_lifecycle: list[ClaimLifecycle] = Field(alias="ClaimLifecycle")
    change_observation: list[ChangeObservation] = Field(alias="ChangeObservation")
    dependency_kind: list[DependencyKind] = Field(alias="DependencyKind")
    dependency_node_status: list[DependencyNodeStatus] = Field(alias="DependencyNodeStatus")
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
    impact_action: list[ImpactAction] = Field(alias="ImpactAction")
    invalidation_policy: list[InvalidationPolicy] = Field(alias="InvalidationPolicy")
    job_status: list[JobStatus] = Field(alias="JobStatus")
    permission: list[Permission] = Field(alias="Permission")
    project_status: list[ProjectStatus] = Field(alias="ProjectStatus")
    requirement_field_status: list[RequirementFieldStatus] = Field(alias="RequirementFieldStatus")
    requirement_priority: list[RequirementPriority] = Field(alias="RequirementPriority")
    requirement_status: list[RequirementStatus] = Field(alias="RequirementStatus")
    requirement_type: list[RequirementType] = Field(alias="RequirementType")
    requirement_value_type: list[RequirementValueType] = Field(alias="RequirementValueType")
    static_analysis_status: list[StaticAnalysisStatus] = Field(alias="StaticAnalysisStatus")
    traceability_relation: list[TraceabilityRelation] = Field(alias="TraceabilityRelation")
    automation_level: list[AutomationLevel] = Field(alias="AutomationLevel")
    test_execution_status: list[TestExecutionStatus] = Field(alias="TestExecutionStatus")
    test_type: list[TestType] = Field(alias="TestType")
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


class RequirementData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID
    code: str
    title: str
    requirement_type: RequirementType
    priority: RequirementPriority
    statement: str
    rationale: str
    acceptance_criteria: list[str]
    source_evidence_ids: list[UUID]
    status: RequirementStatus


class RequirementUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    requirement_type: RequirementType | None = None
    priority: RequirementPriority | None = None
    statement: str | None = Field(default=None, min_length=1, max_length=8000)
    rationale: str | None = Field(default=None, max_length=8000)
    acceptance_criteria: list[str] | None = Field(default=None, max_length=50)
    source_evidence_ids: list[UUID] | None = None
    status: RequirementStatus | None = None


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


class DependencyEdgeData(BaseModel):
    edge: EngineeringDependencyEdge


class DependencyNodeStateData(BaseModel):
    state: DependencyNodeState


class DependencyListData(BaseModel):
    items: list[DependencyEdgeData]


class ImpactAnalysisData(BaseModel):
    plan: ImpactPlan


class ImpactAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID


class ArtifactListData(BaseModel):
    items: list[ArtifactData]


class ArtifactDependenciesData(BaseModel):
    artifact: ArtifactData
    dependencies: list[DependencyEdgeData]
    dependents: list[DependencyEdgeData]


class ArtifactRevalidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID | None = None


class ArtifactRevalidateData(BaseModel):
    artifact: ArtifactData
    state: DependencyNodeStateData | None = None


class ClaimLifecycleMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    expected_revision: int = Field(ge=1)
    lifecycle: ClaimLifecycle


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


class ProtocolCreateRequest(ProtocolDefinition):
    """ProtocolIR semantic content for project-scoped creation."""


class ProtocolUpdateRequest(ProtocolDefinition):
    """ProtocolIR semantic content plus optimistic-concurrency input."""

    expected_revision: int | None = Field(default=None, ge=1)


class ProtocolValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_id: UUID | None = None
    revision: int | None = Field(default=None, ge=1)


class ProtocolGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_id: UUID | None = None
    revision: int | None = Field(default=None, ge=1)


ProtocolData = ProtocolIR
ProtocolValidationData = ProtocolValidationResult
ProtocolGenerationData = ProtocolGenerationBundle


class FirmwareGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mcu_config_id: UUID
    build_target: FirmwareBuildTarget = Field(default_factory=FirmwareBuildTarget)
    board_name: str = Field(default="generic-stm32", min_length=1, max_length=100)
    dependency_lock_id: UUID | None = None
    build_profile: BuildProfile | None = None

    @model_validator(mode="after")
    def synchronize_build_profile(self) -> "FirmwareGenerateRequest":
        if self.build_profile is not None and self.build_profile is not self.build_target.profile:
            raise ValueError("build_profile must match build_target.profile")
        return self


class ComponentData(BaseModel):
    descriptor: object
    releases: list[ComponentRelease]


class ComponentResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mcu_config_id: UUID
    requirements: list[ComponentRequirement] = Field(min_length=1)
    architecture: str = Field(min_length=1, max_length=100)
    device: str = Field(min_length=1, max_length=100)
    toolchain_id: str = Field(min_length=1, max_length=200)
    build_system: str = Field(default="CMAKE", min_length=1, max_length=50)
    capabilities: set[str] = Field(default_factory=set)
    rtos: str | None = Field(default=None, max_length=100)


class ComponentMaterializeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lock_id: UUID


class SoftwareComponentData(BaseModel):
    id: UUID
    component_key: str
    name: str
    vendor: str
    role: str
    authority: str
    provider_id: str
    source_type: str
    source_uri: str | None
    capabilities: list[str]
    compatibility: ComponentCompatibility
    license_expression: str | None
    license_text_hash: str | None
    dependencies: list[ComponentDependencySpec]
    production_eligible: bool
    reference_only: bool


class ComponentReleaseData(BaseModel):
    id: UUID
    component_id: UUID
    version: str
    revision_kind: str
    source_revision: str
    manifest_hash: str
    content_hash: str | None
    submodule_commit_map: dict[str, str]
    source_uri: str | None
    yanked: bool
    verified: bool


class ComponentCatalogData(BaseModel):
    components: list[SoftwareComponentData]


class ComponentDetailData(BaseModel):
    descriptor: SoftwareComponentData
    releases: list[ComponentReleaseData]


class DependencyLockData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID
    mcu_config_id: UUID
    mcu_config_revision: int
    requirements: list[ComponentRequirement]
    resolved_components: list[ResolvedComponent]
    resolution_policy_version: str
    resolver_version: str
    lock_hash: str
    status: str


class ComponentMaterializationData(BaseModel):
    id: UUID
    project_id: UUID
    component_id: UUID
    release_id: UUID
    owner: str
    cache_key: str
    manifest_hash: str
    content_hash: str
    storage_uri: str
    status: str
    network_used: bool


class SourceRevisionData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID
    repository_id: str
    commit_sha: str | None
    tree_hash: str
    dirty: bool
    base_commit: str | None
    workspace_revision: int
    source_manifest_hash: str
    file_manifest: dict[str, str]
    created_by: str


class SourceWorkspaceStatusData(BaseModel):
    project_id: UUID
    repository_id: str
    workspace_revision: int
    source_revision_id: UUID
    dirty: bool
    commit_sha: str | None
    base_commit: str | None
    tree_hash: str
    source_manifest_hash: str
    file_count: int
    generated_owned_paths: list[str]


class SourceFileContentData(BaseModel):
    path: str
    content: str
    content_hash: str
    source_revision_id: UUID
    workspace_revision: int
    etag: str


class PatchProposalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_source_revision_id: UUID
    base_workspace_revision: int = Field(ge=0)
    affected_files: list[str] = Field(min_length=1)
    expected_file_hashes: dict[str, str | None] = Field(default_factory=dict)
    patch: str | None = None
    structured_edits: dict[str, str] = Field(default_factory=dict)
    rationale: str = Field(min_length=1, max_length=20_000)
    evidence_ids: list[UUID] = Field(default_factory=list)
    expected_impact: dict[str, object] = Field(default_factory=dict)
    required_builds: list[str] = Field(default_factory=list)
    required_tests: list[str] = Field(default_factory=list)
    created_by: str = Field(min_length=1, max_length=200)


class PatchProposalApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_source_revision_id: UUID | None = None
    expected_workspace_revision: int | None = Field(default=None, ge=0)


class PatchProposalData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID
    base_source_revision_id: UUID
    base_workspace_revision: int
    affected_files: list[str]
    expected_file_hashes: dict[str, str | None]
    patch: str | None
    structured_edits: dict[str, str]
    rationale: str
    evidence_ids: list[UUID]
    expected_impact: dict[str, object]
    required_builds: list[str]
    required_tests: list[str]
    created_by: str
    status: PatchProposalStatus
    failure_reason: str | None


class PatchProposalDiffData(BaseModel):
    proposal_id: UUID
    diff: str


class SourceCommitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_source_revision_id: UUID
    commit_message: str = Field(min_length=1, max_length=500)
    actor: str = Field(min_length=1, max_length=200)


class FirmwareSourceFileData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    path: str
    content: str
    content_hash: str
    input_hash: str
    generated_owned: bool
    generator_version: str


class FirmwareData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID
    mcu_config_id: UUID
    mcu_config_revision: int
    hardware_ir_id: UUID
    hardware_ir_revision: int
    circuit_id: UUID
    circuit_revision: int
    schematic_id: UUID
    schematic_revision: int
    source_revision_id: UUID
    dependency_lock_id: UUID | None
    dependency_lock_hash: str | None
    component_refs: list[str]
    platform_adapter_id: str
    platform_adapter_version: str
    layers: list[str]
    modules: list[FirmwareModule]
    tasks: list[FirmwareTask]
    interrupts: list[FirmwareInterrupt]
    shared_resources: list[SharedResource]
    startup: StartupConfig
    clock_tree: dict[str, object]
    peripheral_drivers: list[PeripheralDriverConfig]
    memory_layout: MemoryLayout
    bsp: BSPConfig
    build_target: FirmwareBuildTarget
    rule_results: list[dict[str, object]]
    requirement_ids: list[UUID]
    evidence_ids: list[UUID]
    input_hash: str
    status: ArtifactStatus


class FirmwareBundleData(BaseModel):
    firmware: FirmwareData
    source_revision: SourceRevisionData
    files: list[FirmwareSourceFileData]


class BuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    firmware_id: UUID


class BuildInputSnapshotData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID
    source_revision_id: UUID
    tracked_file_manifest_hash: str
    allowed_untracked_input_hash: str
    generated_input_hash: str
    submodule_commit_map: dict[str, str]
    build_config_hash: str
    build_profile: BuildProfile
    toolchain_id: str
    toolchain_version: str
    environment_profile_hash: str
    source_manifest_hash: str
    dependency_lock_hash: str
    component_manifest_hash: str
    toolchain_manifest_hash: str | None
    build_input_hash: str


class BuildDiagnosticData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID
    severity: IssueSeverity
    code: str
    message: str
    file: str | None
    line: int | None
    column: int | None
    phase: str


class BuildRunData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID
    firmware_id: UUID
    firmware_revision: int
    source_revision_id: UUID
    build_input_snapshot_id: UUID
    status: BuildStatus
    profile: BuildProfile
    toolchain_id: str
    toolchain_version: str
    environment_profile_hash: str
    build_input_hash: str
    command: list[str]
    diagnostics: list[BuildDiagnosticData]
    stdout: str
    stderr: str
    artifact_hash: str | None
    error_code: EngineeringErrorCode | None
    duration_ms: int


class BuildListData(BaseModel):
    builds: list[BuildRunData]


class StaticAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    firmware_id: UUID
    run_cppcheck: bool = True


class FirmwareStaticAnalysisData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID
    firmware_id: UUID
    firmware_revision: int
    source_revision_id: UUID
    build_input_snapshot_id: UUID | None
    input_hash: str
    ruleset_version: str
    status: StaticAnalysisStatus
    rule_results: list[dict[str, object]]
    tool_results: list[StaticAnalysisToolResult]


class StaticAnalysisListData(BaseModel):
    analyses: list[FirmwareStaticAnalysisData]


class TestGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TestGenerationData(BaseModel):
    test_ir: TestIR
    coverage_gaps: list[UUID] = Field(default_factory=list)


class TestIRListData(BaseModel):
    items: list[TestIR]


class TestCaseListData(BaseModel):
    items: list[TestCase]


class TestRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_ir_id: UUID | None = None
    source_revision_id: UUID


class TestRunListData(BaseModel):
    items: list[TestRun]


class CoverageData(BaseModel):
    total_requirements: int
    release_critical_requirements: int
    covered_requirements: int
    verified_requirements: int
    design_coverage_ratio: float
    verification_coverage_ratio: float
    uncovered_requirement_ids: list[UUID]
    unexecuted_requirement_ids: list[UUID]
    failing_requirement_ids: list[UUID]
    blocked_requirement_ids: list[UUID]
    unknown_requirement_ids: list[UUID]
    stale_requirement_ids: list[UUID] = Field(default_factory=list)
    stale_test_run: bool = False
    source_revision_id: UUID | None = None


class TraceabilityData(BaseModel):
    edges: list[dict[str, object]]
    coverage: CoverageData
    orphan_tests: list[UUID]
    uncovered_requirements: list[UUID]


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_revision_id: UUID
    test_ir_id: UUID | None = None
    test_run_id: UUID | None = None
    build_run_id: UUID | None = None
    static_analysis_id: UUID | None = None
    schematic_id: UUID | None = None
    require_build: bool = False
    require_static_analysis: bool = False
    require_erc: bool = False


class ReviewListData(BaseModel):
    items: list[ReviewRun]


class IssueData(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    project_id: UUID
    code: str
    title: str
    description: str
    severity: IssueSeverity
    status: IssueStatus
    claim_ids: list[UUID]
    evidence_ids: list[UUID]
    resolution: str | None
    dedupe_key: str | None
    source_kind: str | None
    source_ref: str | None
    affected_refs: list[str]
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    occurrence_count: int
    last_review_id: UUID | None


class IssueListData(BaseModel):
    items: list[IssueData]


class IssueMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    reason: str = Field(min_length=1, max_length=8000)
    expected_revision: int | None = Field(default=None, ge=1)


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
