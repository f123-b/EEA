"""Core-neutral contracts for Domain Extension Infrastructure (M14).

The models in this module deliberately contain opaque payloads and references only. Concrete
domains must live in plugins and must not add domain-specific fields to Core schemas.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from eea_core.entities import EntityBase, Sha256, utc_now
from eea_core.enums import (
    DomainActivationStatus,
    DomainRulePhase,
    DomainTrustTier,
    IssueSeverity,
    Permission,
)


class DomainUIContribution(BaseModel):
    """Metadata-only UI contribution; arbitrary remote JavaScript is not representable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    extension_id: str = Field(min_length=1, max_length=200)
    kind: Literal["navigation", "action", "form"]
    label: str = Field(min_length=1, max_length=200)
    route: str = Field(min_length=1, max_length=500)
    json_schema: dict[str, object] = Field(default_factory=dict, alias="schema")
    action: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def reject_remote_targets(self) -> "DomainUIContribution":
        if self.route.startswith(("http://", "https://", "javascript:")):
            raise ValueError("UI contributions must use local metadata routes")
        return self


class DomainContextContribution(BaseModel):
    """A namespaced, declarative context contribution exposed to a Domain plugin."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    context_id: str = Field(min_length=1, max_length=200)
    keys: list[str] = Field(default_factory=list)
    description: str = Field(default="", max_length=1000)


class DomainRuleContribution(BaseModel):
    """A deterministic additive rule contribution.

    ``safety_mode`` is intentionally restricted to ADDITIVE. Domain rules cannot replace,
    disable, or downgrade Core safety rules.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str = Field(min_length=1, max_length=200)
    rule_version: str = Field(min_length=1, max_length=50)
    phase: DomainRulePhase
    inputs: list[str] = Field(default_factory=list)
    severity: IssueSeverity = IssueSeverity.MEDIUM
    priority: int = 0
    safety_mode: Literal["ADDITIVE"] = "ADDITIVE"


class DomainGeneratorContribution(BaseModel):
    """A deterministic generator declaration used to construct a composition DAG."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    generator_id: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=50)
    consumes: list[str] = Field(default_factory=list)
    produces: list[str] = Field(default_factory=list)
    requires_capabilities: list[str] = Field(default_factory=list)
    before: list[str] = Field(default_factory=list)
    after: list[str] = Field(default_factory=list)
    deterministic: bool = True
    side_effects: bool = False


class DomainDescriptor(BaseModel):
    """Validated, Core-neutral descriptor for one Domain plugin."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, populate_by_name=True, str_strip_whitespace=True
    )

    domain_id: str = Field(alias="id", min_length=1, max_length=200)
    plugin_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=100)
    api_version: str = Field(min_length=1, max_length=30)
    schema_version: str = Field(default="1.0", min_length=1, max_length=30)
    trust_tier: DomainTrustTier = DomainTrustTier.BUNDLED
    entrypoint: str = Field(default="", max_length=300)
    provided_capabilities: list[str] = Field(
        default_factory=list, alias="capabilities", max_length=100
    )
    required_capabilities: list[str] = Field(default_factory=list, max_length=100)
    requires_domains: list[str] = Field(default_factory=list, max_length=100)
    optional_domains: list[str] = Field(default_factory=list, max_length=100)
    conflicts_with: list[str] = Field(default_factory=list, max_length=100)
    priority: int = Field(default=0, ge=-1000, le=1000)
    rule_phases: list[DomainRulePhase] = Field(default_factory=list, max_length=20)
    generator_phases: list[str] = Field(default_factory=list, max_length=20)
    migration_provider: str | None = Field(default=None, max_length=300)
    context_contributions: list[str] = Field(default_factory=list, max_length=100)
    ui_contributions: list[str] = Field(default_factory=list, max_length=100)
    permissions: list[Permission] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_relationships(self) -> "DomainDescriptor":
        if self.domain_id in self.requires_domains:
            raise ValueError("a domain cannot require itself")
        if self.domain_id in self.conflicts_with:
            raise ValueError("a domain cannot conflict with itself")
        if set(self.provided_capabilities) & set(self.required_capabilities):
            raise ValueError("a descriptor cannot both require and provide the same capability")
        return self


class DomainIRRef(BaseModel):
    """Reference to plugin-owned IR without importing the plugin's Python type."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain_id: str = Field(min_length=1, max_length=200)
    entity_type: str = Field(min_length=1, max_length=200)
    entity_id: UUID
    schema_version: str = Field(min_length=1, max_length=30)
    revision: int = Field(default=1, ge=1)


class DomainIREnvelope(EntityBase):
    """Opaque project-scoped IR envelope owned by a plugin."""

    project_id: UUID
    domain_id: str = Field(min_length=1, max_length=200)
    plugin_id: str = Field(min_length=1, max_length=200)
    domain_schema_version: str = Field(min_length=1, max_length=30)
    payload: dict[str, object] = Field(default_factory=dict)
    refs: list[DomainIRRef] = Field(default_factory=list)
    content_hash: Sha256 | None = None


class DomainActivation(EntityBase):
    """Durable project activation state; disabling never deletes plugin data."""

    project_id: UUID
    domain_id: str = Field(min_length=1, max_length=200)
    plugin_id: str = Field(min_length=1, max_length=200)
    plugin_version: str = Field(min_length=1, max_length=100)
    domain_schema_version: str = Field(min_length=1, max_length=30)
    configuration_schema_version: str = Field(min_length=1, max_length=30)
    configuration_schema_hash: Sha256 | None = None
    status: DomainActivationStatus = DomainActivationStatus.ACTIVE
    configuration: dict[str, object] = Field(default_factory=dict)
    activated_at: datetime = Field(default_factory=utc_now)
    activated_by: str = Field(default="system", min_length=1, max_length=200)
    capability_snapshot: dict[str, object] = Field(default_factory=dict)
    dependency_snapshot: dict[str, object] = Field(default_factory=dict)


class DomainCompositionPlan(BaseModel):
    """Deterministic resolved composition returned by the registry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    active_domain_ids: list[str] = Field(default_factory=list)
    ordered_domain_ids: list[str] = Field(default_factory=list)
    dependency_edges: list[list[str]] = Field(default_factory=list)
    capability_routes: dict[str, str] = Field(default_factory=dict)
    rules: list[DomainRuleContribution] = Field(default_factory=list)
    generators: list[DomainGeneratorContribution] = Field(default_factory=list)
    context_contributions: list[DomainContextContribution] = Field(default_factory=list)
    ui_contributions: list[DomainUIContribution] = Field(default_factory=list)


__all__ = [
    "DomainActivation",
    "DomainCompositionPlan",
    "DomainContextContribution",
    "DomainDescriptor",
    "DomainGeneratorContribution",
    "DomainIREnvelope",
    "DomainIRRef",
    "DomainRuleContribution",
    "DomainUIContribution",
]
