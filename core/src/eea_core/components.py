"""Core-neutral embedded software component and dependency-lock contracts."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from eea_core.entities import EntityBase, Sha256
from eea_core.enums import (
    ComponentAuthority,
    ComponentMaterializationStatus,
    ComponentRevisionKind,
    ComponentSourceType,
    DependencyLockStatus,
    SoftwareComponentRole,
)


class ComponentCompatibility(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    architectures: list[str] = Field(default_factory=list)
    device_families: list[str] = Field(default_factory=list)
    device_patterns: list[str] = Field(default_factory=list)
    toolchain_ids: list[str] = Field(default_factory=list)
    build_systems: list[str] = Field(default_factory=list)
    rtos: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    forbidden_capabilities: list[str] = Field(default_factory=list)


class ComponentDependencySpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    component_key: str = Field(min_length=1, max_length=200)
    version_constraint: str | None = Field(default=None, max_length=100)
    required: bool = True


class SoftwareComponentDescriptor(EntityBase):
    component_key: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    vendor: str = Field(min_length=1, max_length=200)
    role: SoftwareComponentRole
    authority: ComponentAuthority
    provider_id: str = Field(min_length=1, max_length=200)
    source_type: ComponentSourceType
    source_uri: str | None = Field(default=None, max_length=2000)
    capabilities: list[str] = Field(default_factory=list)
    compatibility: ComponentCompatibility = Field(default_factory=ComponentCompatibility)
    license_expression: str | None = Field(default=None, max_length=200)
    license_text_hash: Sha256 | None = None
    dependencies: list[ComponentDependencySpec] = Field(default_factory=list)
    production_eligible: bool = True
    reference_only: bool = False

    @model_validator(mode="after")
    def reference_cannot_be_production(self) -> SoftwareComponentDescriptor:
        if self.reference_only and self.production_eligible:
            raise ValueError("reference-only components cannot be production eligible")
        return self


class ComponentRelease(EntityBase):
    component_id: UUID
    version: str = Field(min_length=1, max_length=100)
    revision_kind: ComponentRevisionKind
    source_revision: str = Field(min_length=1, max_length=200)
    manifest_hash: Sha256
    content_hash: Sha256 | None = None
    files: list[str] = Field(default_factory=list)
    submodule_commit_map: dict[str, str] = Field(default_factory=dict)
    source_uri: str | None = Field(default=None, max_length=2000)
    yanked: bool = False
    verified: bool = False

    @model_validator(mode="after")
    def reject_floating_revision(self) -> ComponentRelease:
        if self.source_revision.lower() in {"main", "master", "develop", "latest", "head"}:
            raise ValueError("production component releases cannot use floating revisions")
        return self


class ComponentRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    capability: str = Field(min_length=1, max_length=200)
    component_key: str | None = Field(default=None, max_length=200)
    version_constraint: str | None = Field(default=None, max_length=100)
    required: bool = True
    reason: str = Field(min_length=1, max_length=2000)
    source_requirement_ids: list[UUID] = Field(default_factory=list)
    source_claim_ids: list[UUID] = Field(default_factory=list)
    source_domain_refs: list[str] = Field(default_factory=list)


class ResolvedComponent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    component_id: UUID
    component_key: str = Field(min_length=1, max_length=200)
    release_id: UUID
    version: str = Field(min_length=1, max_length=100)
    revision: str = Field(min_length=1, max_length=200)
    manifest_hash: Sha256
    content_hash: Sha256
    files: list[str] = Field(default_factory=list)
    provider_id: str = Field(min_length=1, max_length=200)
    authority: ComponentAuthority
    license_expression: str
    dependencies: list[str] = Field(default_factory=list)
    source_uri: str | None = Field(default=None, max_length=2000)


class DependencyLock(EntityBase):
    project_id: UUID
    mcu_config_id: UUID
    mcu_config_revision: int = Field(ge=1)
    requirements: list[ComponentRequirement] = Field(default_factory=list)
    resolved_components: list[ResolvedComponent] = Field(default_factory=list)
    resolution_policy_version: str = Field(min_length=1, max_length=100)
    resolver_version: str = Field(min_length=1, max_length=100)
    lock_hash: Sha256
    status: DependencyLockStatus = DependencyLockStatus.DRAFT


class ComponentMaterialization(EntityBase):
    project_id: UUID
    component_id: UUID
    release_id: UUID
    owner: str = Field(min_length=1, max_length=30)
    cache_key: str = Field(min_length=1, max_length=200)
    manifest_hash: Sha256
    content_hash: Sha256
    storage_uri: str = Field(min_length=1, max_length=2000)
    status: ComponentMaterializationStatus = ComponentMaterializationStatus.PENDING
    network_used: bool = False


__all__ = [
    "ComponentCompatibility",
    "ComponentDependencySpec",
    "ComponentMaterialization",
    "ComponentRelease",
    "ComponentRequirement",
    "DependencyLock",
    "ResolvedComponent",
    "SoftwareComponentDescriptor",
]
