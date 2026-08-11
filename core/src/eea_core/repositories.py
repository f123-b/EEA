"""Persistence ports owned by the Core boundary."""

from typing import Protocol
from uuid import UUID

from eea_core.ai import AIUsageRecord, PromptDefinition
from eea_core.claims import ClaimConflict, ClaimPredicateDefinition, EngineeringClaim
from eea_core.entities import Project
from eea_core.intelligence import Document, DocumentIR
from eea_core.requirements import Requirement, RequirementAnalysis, RequirementProfile


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


class ClaimPredicateRepository(Protocol):
    def add(self, definition: ClaimPredicateDefinition) -> ClaimPredicateDefinition: ...

    def get(self, predicate: str) -> ClaimPredicateDefinition | None: ...


class EngineeringClaimRepository(Protocol):
    def add(self, claim: EngineeringClaim) -> EngineeringClaim: ...

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

    def get(self, document_id: UUID) -> Document | None: ...


class DocumentIRRepository(Protocol):
    def add(self, document_ir: DocumentIR) -> DocumentIR: ...

    def get_for_document(self, document_id: UUID) -> DocumentIR | None: ...


class RequirementProfileRepository(Protocol):
    def add(self, profile: RequirementProfile) -> RequirementProfile: ...

    def get(
        self, profile_name: str, profile_version: str | None = None
    ) -> RequirementProfile | None: ...


class RequirementRepository(Protocol):
    def add(self, requirement: Requirement) -> Requirement: ...

    def list_for_project(self, project_id: UUID) -> list[Requirement]: ...


class RequirementAnalysisRepository(Protocol):
    def add(self, analysis: RequirementAnalysis) -> RequirementAnalysis: ...

    def get(self, analysis_id: UUID) -> RequirementAnalysis | None: ...
