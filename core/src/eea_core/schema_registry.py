"""Versioned Core schema registry."""

from dataclasses import dataclass

from pydantic import BaseModel

from eea_core.ai import AIUsageRecord, PromptDefinition
from eea_core.architecture import (
    ArchitectureBlock,
    ArchitectureDecision,
    ArchitectureInterface,
    HardwareDeviceInstance,
    HardwareInterface,
    HardwareIR,
    HardwareModule,
    PowerDomain,
    SystemArchitectureIR,
)
from eea_core.build import BuildDiagnostic, BuildRun
from eea_core.circuit import (
    CircuitBundle,
    CircuitComponent,
    CircuitConstraint,
    CircuitEndpoint,
    CircuitIR,
    CircuitNet,
    PowerNet,
)
from eea_core.claims import (
    ClaimConflict,
    ClaimPredicateDefinition,
    EngineeringClaim,
    EngineeringValue,
)
from eea_core.components import (
    ComponentCompatibility,
    ComponentDependencySpec,
    ComponentMaterialization,
    ComponentRelease,
    ComponentRequirement,
    DependencyLock,
    ResolvedComponent,
    SoftwareComponentDescriptor,
)
from eea_core.domain_extensions import (
    DomainActivation,
    DomainCompositionPlan,
    DomainContextContribution,
    DomainDescriptor,
    DomainGeneratorContribution,
    DomainIREnvelope,
    DomainIRRef,
    DomainRuleContribution,
    DomainUIContribution,
)
from eea_core.entities import (
    Artifact,
    EngineeringDecision,
    Evidence,
    Issue,
    Job,
    PermissionAuditRecord,
    Project,
    TraceabilityEdge,
)
from eea_core.firmware import (
    BSPConfig,
    FirmwareBuildTarget,
    FirmwareBundle,
    FirmwareInterrupt,
    FirmwareIR,
    FirmwareModule,
    FirmwareSourceFile,
    FirmwareTask,
    MemoryLayout,
    PeripheralDriverConfig,
    SharedResource,
    StartupConfig,
)
from eea_core.intelligence import (
    Device,
    DeviceMergeConflict,
    DeviceMergeResult,
    DevicePin,
    Document,
    DocumentFigure,
    DocumentIR,
    DocumentPage,
    DocumentSection,
    DocumentTable,
    PinFunction,
)
from eea_core.mcu_config import (
    DMAIR,
    ADCConfig,
    ClockIR,
    DebugConfigIR,
    GPIOConfig,
    InterruptConfigIR,
    MCUConfigBundle,
    MCUConfigIR,
    MemoryConfigIR,
    PeripheralConfigIR,
    PWMConfig,
)
from eea_core.pin_planner import (
    PinAssignment,
    PinCandidate,
    PinLock,
    PinPlan,
    PinRequirement,
    RuleResult,
)
from eea_core.requirements import (
    FollowUpQuestion,
    Requirement,
    RequirementAnalysis,
    RequirementAnalysisDraft,
    RequirementClaimDraft,
    RequirementCompleteness,
    RequirementDraft,
    RequirementEvidenceContract,
    RequirementFieldObservation,
    RequirementFieldSpec,
    RequirementIssueDraft,
    RequirementProfile,
)
from eea_core.review import ReviewFinding, ReviewPolicy, ReviewRun
from eea_core.sandbox import (
    ArchiveExtractionReport,
    CommandResult,
    CommandSpec,
    SandboxPolicy,
)
from eea_core.schematic import ErcIssue, ErcReport, SchematicBundle, SchematicIR
from eea_core.source import BuildInputSnapshot, SourceRevision
from eea_core.static_analysis import FirmwareStaticAnalysis, StaticAnalysisToolResult
from eea_core.testing import TestCase, TestCaseResult, TestIR, TestRun


@dataclass(frozen=True, slots=True)
class SchemaRegistration:
    name: str
    version: str
    model: type[BaseModel]


class SchemaRegistry:
    """Rejects unknown or duplicate schemas and exports JSON Schema."""

    def __init__(self) -> None:
        self._registrations: dict[str, SchemaRegistration] = {}

    def register(self, registration: SchemaRegistration) -> None:
        if registration.name in self._registrations:
            raise ValueError(f"Schema is already registered: {registration.name}")
        self._registrations[registration.name] = registration

    def list(self) -> list[SchemaRegistration]:
        return sorted(self._registrations.values(), key=lambda item: item.name)

    def get(self, name: str) -> SchemaRegistration | None:
        return self._registrations.get(name)

    def json_schema(self, name: str) -> dict[str, object] | None:
        registration = self.get(name)
        if registration is None:
            return None
        return registration.model.model_json_schema()


def create_core_schema_registry() -> SchemaRegistry:
    registry = SchemaRegistry()
    for model in (
        AIUsageRecord,
        ArchiveExtractionReport,
        ArchitectureBlock,
        ArchitectureDecision,
        ArchitectureInterface,
        Artifact,
        BuildDiagnostic,
        BuildInputSnapshot,
        BuildRun,
        ComponentCompatibility,
        ComponentDependencySpec,
        ComponentMaterialization,
        ComponentRelease,
        ComponentRequirement,
        ADCConfig,
        ClockIR,
        CircuitBundle,
        CircuitComponent,
        CircuitConstraint,
        CircuitEndpoint,
        CircuitIR,
        CircuitNet,
        ClaimConflict,
        ClaimPredicateDefinition,
        CommandResult,
        CommandSpec,
        Device,
        DeviceMergeConflict,
        DeviceMergeResult,
        DevicePin,
        DomainActivation,
        DomainCompositionPlan,
        DomainContextContribution,
        DomainDescriptor,
        DomainGeneratorContribution,
        DomainIREnvelope,
        DomainIRRef,
        DomainRuleContribution,
        DomainUIContribution,
        DebugConfigIR,
        DMAIR,
        EngineeringDecision,
        EngineeringClaim,
        EngineeringValue,
        ErcIssue,
        ErcReport,
        BSPConfig,
        Document,
        DocumentFigure,
        DocumentIR,
        DocumentPage,
        DocumentSection,
        DocumentTable,
        DependencyLock,
        Evidence,
        HardwareDeviceInstance,
        HardwareIR,
        HardwareInterface,
        HardwareModule,
        FirmwareBuildTarget,
        FirmwareBundle,
        FirmwareIR,
        FirmwareInterrupt,
        FirmwareModule,
        FirmwareSourceFile,
        FirmwareTask,
        FirmwareStaticAnalysis,
        GPIOConfig,
        InterruptConfigIR,
        Issue,
        Job,
        PermissionAuditRecord,
        MCUConfigBundle,
        MCUConfigIR,
        MemoryConfigIR,
        PeripheralConfigIR,
        PWMConfig,
        PromptDefinition,
        Project,
        SandboxPolicy,
        SchematicBundle,
        SchematicIR,
        TraceabilityEdge,
        PinFunction,
        PinAssignment,
        PinCandidate,
        PinLock,
        PinPlan,
        PinRequirement,
        PowerNet,
        PowerDomain,
        RuleResult,
        SharedResource,
        SourceRevision,
        StartupConfig,
        StaticAnalysisToolResult,
        TestCase,
        TestCaseResult,
        TestIR,
        TestRun,
        MemoryLayout,
        ReviewFinding,
        ReviewPolicy,
        ReviewRun,
        PeripheralDriverConfig,
        FollowUpQuestion,
        Requirement,
        RequirementAnalysis,
        RequirementAnalysisDraft,
        RequirementClaimDraft,
        RequirementCompleteness,
        RequirementDraft,
        RequirementEvidenceContract,
        RequirementFieldObservation,
        RequirementFieldSpec,
        RequirementIssueDraft,
        RequirementProfile,
        ResolvedComponent,
        SystemArchitectureIR,
        SoftwareComponentDescriptor,
    ):
        registry.register(SchemaRegistration(model.__name__, "1.0", model))
    return registry
