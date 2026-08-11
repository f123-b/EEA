"""Framework-independent core domain for EEA."""

from eea_core.domain_extensions import (
    DomainActivation,
    DomainCompositionPlan,
    DomainDescriptor,
    DomainIREnvelope,
    DomainIRRef,
)

__all__ = [
    "DomainActivation",
    "DomainCompositionPlan",
    "DomainDescriptor",
    "DomainIREnvelope",
    "DomainIRRef",
]

from eea_core.entities import (
    Artifact,
    EngineeringDecision,
    EntityBase,
    Evidence,
    Issue,
    Job,
    PermissionAuditRecord,
    Project,
    TraceabilityEdge,
)
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
    RequirementFieldStatus,
    RequirementPriority,
    RequirementStatus,
    RequirementType,
    RequirementValueType,
    TraceabilityRelation,
)

__all__ = [
    "Artifact",
    "ArtifactStatus",
    "DecisionStatus",
    "EngineeringDecision",
    "EngineeringErrorCode",
    "EntityBase",
    "Evidence",
    "EvidenceType",
    "Issue",
    "IssueSeverity",
    "IssueStatus",
    "Job",
    "JobStatus",
    "Permission",
    "PermissionAuditRecord",
    "Project",
    "ProjectStatus",
    "RequirementFieldStatus",
    "RequirementPriority",
    "RequirementStatus",
    "RequirementType",
    "RequirementValueType",
    "TraceabilityEdge",
    "TraceabilityRelation",
]
