"""Persistence ports owned by the Core boundary."""

from typing import Protocol
from uuid import UUID

from eea_core.ai import AIUsageRecord, PromptDefinition
from eea_core.build import BuildRun
from eea_core.circuit import CircuitBundle
from eea_core.claims import ClaimConflict, ClaimPredicateDefinition, EngineeringClaim
from eea_core.components import (
    ComponentMaterialization,
    DependencyLock,
    SoftwareComponentDescriptor,
)
from eea_core.entities import Evidence, Project
from eea_core.firmware import FirmwareBundle
from eea_core.intelligence import Document, DocumentIR
from eea_core.mcu_config import MCUConfigBundle
from eea_core.pin_planner import PinAssignment, PinPlan
from eea_core.requirements import Requirement, RequirementAnalysis, RequirementProfile
from eea_core.schematic import SchematicBundle
from eea_core.source import BuildInputSnapshot


class ProjectRepository(Protocol):
    def add(self, project: Project) -> Project: ...

    def get(self, project_id: UUID, *, include_deleted: bool = False) -> Project | None: ...

    def list(self, *, include_deleted: bool = False) -> list[Project]: ...

    def save(self, project: Project, *, expected_revision: int) -> Project | None: ...


class PromptRepository(Protocol):
    def add(self, definition: PromptDefinition) -> PromptDefinition: ...

    def get(self, name: str, version: str | None = None) -> PromptDefinition | None: ...


class AIUsageRepository(Protocol):
    def add(self, record: AIUsageRecord) -> AIUsageRecord: ...

    def list_for_request(self, request_id: object) -> list[AIUsageRecord]: ...


class EvidenceRepository(Protocol):
    """Read-only evidence lookup used to validate requirement references."""

    def get(self, evidence_id: UUID, *, project_id: UUID | None) -> Evidence | None: ...

    def exists(self, evidence_id: UUID) -> bool: ...


class ClaimPredicateRepository(Protocol):
    def add(self, definition: ClaimPredicateDefinition) -> ClaimPredicateDefinition: ...

    def get(self, predicate: str) -> ClaimPredicateDefinition | None: ...


class EngineeringClaimRepository(Protocol):
    def add(self, claim: EngineeringClaim) -> EngineeringClaim: ...

    def get(self, claim_id: UUID) -> EngineeringClaim | None: ...

    def list_for_subject_predicate(
        self,
        *,
        project_id: UUID | None,
        subject_ref: str,
        predicate: str,
    ) -> list[EngineeringClaim]: ...


class ClaimConflictRepository(Protocol):
    def add(self, conflict: ClaimConflict) -> ClaimConflict: ...

    def list_for_claim(self, claim_id: UUID) -> list[ClaimConflict]: ...


class DocumentRepository(Protocol):
    def add(self, document: Document) -> Document: ...

    def get(self, document_id: UUID, *, project_id: UUID | None) -> Document | None: ...

    def exists(self, document_id: UUID) -> bool: ...


class DocumentIRRepository(Protocol):
    def add(self, document_ir: DocumentIR) -> DocumentIR: ...

    def get_for_document(
        self, document_id: UUID, *, project_id: UUID | None
    ) -> DocumentIR | None: ...


class RequirementProfileRepository(Protocol):
    def add(self, profile: RequirementProfile) -> RequirementProfile: ...

    def get(
        self, profile_name: str, profile_version: str | None = None
    ) -> RequirementProfile | None: ...


class RequirementRepository(Protocol):
    def add(self, requirement: Requirement) -> Requirement: ...

    def get_by_code(self, project_id: UUID, code: str) -> Requirement | None: ...

    def save(self, requirement: Requirement, *, expected_revision: int) -> Requirement | None: ...

    def list_for_project(self, project_id: UUID) -> list[Requirement]: ...


class RequirementAnalysisRepository(Protocol):
    def add(self, analysis: RequirementAnalysis) -> RequirementAnalysis: ...

    def get(self, analysis_id: UUID) -> RequirementAnalysis | None: ...


class PinPlanRepository(Protocol):
    def add(self, plan: PinPlan) -> PinPlan: ...

    def get(self, plan_id: UUID, *, project_id: UUID | None = None) -> PinPlan | None: ...

    def latest_for_project(self, project_id: UUID) -> PinPlan | None: ...

    def get_assignment(
        self, assignment_id: UUID, *, project_id: UUID
    ) -> tuple[PinAssignment, UUID] | None: ...


class CircuitRepository(Protocol):
    def add(self, bundle: CircuitBundle) -> CircuitBundle: ...

    def get(self, circuit_id: UUID, *, project_id: UUID | None = None) -> CircuitBundle | None: ...

    def latest_for_project(self, project_id: UUID) -> CircuitBundle | None: ...


class SchematicRepository(Protocol):
    def add(self, bundle: SchematicBundle) -> SchematicBundle: ...

    def get(
        self, schematic_id: UUID, *, project_id: UUID | None = None
    ) -> SchematicBundle | None: ...

    def latest_for_project(self, project_id: UUID) -> SchematicBundle | None: ...


class MCUConfigRepository(Protocol):
    def add(self, bundle: MCUConfigBundle) -> MCUConfigBundle: ...

    def get(self, config_id: UUID, *, project_id: UUID | None = None) -> MCUConfigBundle | None: ...

    def latest_for_project(self, project_id: UUID) -> MCUConfigBundle | None: ...


class FirmwareRepository(Protocol):
    def add(self, bundle: FirmwareBundle) -> FirmwareBundle: ...

    def get(
        self, firmware_id: UUID, *, project_id: UUID | None = None
    ) -> FirmwareBundle | None: ...

    def latest_for_project(self, project_id: UUID) -> FirmwareBundle | None: ...


class BuildRunRepository(Protocol):
    def add(self, snapshot: BuildInputSnapshot, build: BuildRun) -> BuildRun: ...

    def get(self, build_id: UUID, *, project_id: UUID | None = None) -> BuildRun | None: ...

    def list_for_project(self, project_id: UUID) -> list[BuildRun]: ...


class ComponentRepository(Protocol):
    def list_descriptors(self) -> list[SoftwareComponentDescriptor]: ...

    def get(self, component_key: str) -> SoftwareComponentDescriptor | None: ...


class DependencyLockRepository(Protocol):
    def add(self, lock: DependencyLock) -> DependencyLock: ...

    def get(self, lock_id: UUID, *, project_id: UUID | None = None) -> DependencyLock | None: ...

    def latest_for_project(self, project_id: UUID) -> DependencyLock | None: ...


class ComponentMaterializationRepository(Protocol):
    def add(self, materialization: ComponentMaterialization) -> ComponentMaterialization: ...
