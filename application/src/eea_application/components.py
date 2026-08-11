"""Deterministic ESCR resolver and content-addressed materialization service."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from eea_core.components import (
    ComponentMaterialization,
    ComponentRelease,
    ComponentRequirement,
    DependencyLock,
    ResolvedComponent,
    SoftwareComponentDescriptor,
)
from eea_core.enums import (
    ComponentMaterializationStatus,
    ComponentRevisionKind,
    DependencyLockStatus,
    EngineeringErrorCode,
)
from eea_core.errors import EngineeringError
from eea_ports.components import ComponentProvider


def _hash_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _version_key(version: str) -> tuple[str, ...]:
    return tuple(
        f"0{int(part):019d}" if part.isdigit() else f"1{part}"
        for part in re.split(r"[.-]", version)
    )


def _satisfies(version: str, constraint: str | None) -> bool:
    if not constraint or constraint in {"*", "latest"}:
        return constraint != "latest"
    if constraint.startswith("=="):
        return version == constraint[2:]
    if constraint.startswith("^"):
        prefix_major = constraint[1:].split(".", 1)[0]
        return version.split(".", 1)[0] == prefix_major
    if constraint.startswith("~"):
        prefix_minor = constraint[1:].split(".")[:2]
        return version.split(".")[:2] == prefix_minor
    return version == constraint


class ComponentRegistryService:
    """Resolve only verified, immutable and production-eligible components."""

    resolver_version = "escr-resolver/v1"
    resolution_policy_version = "escr-policy/v1"

    def __init__(self, providers: list[ComponentProvider]) -> None:
        self._providers = tuple(sorted(providers, key=lambda provider: provider.provider_id))

    def descriptors(self) -> list[SoftwareComponentDescriptor]:
        descriptors: dict[str, SoftwareComponentDescriptor] = {}
        for provider in self._providers:
            for descriptor in provider.descriptors():
                existing = descriptors.get(descriptor.component_key)
                if existing is not None and existing.model_dump(
                    mode="json"
                ) != descriptor.model_dump(mode="json"):
                    raise EngineeringError(
                        EngineeringErrorCode.DEPENDENCY_CONFLICT,
                        "Multiple providers declared conflicting component metadata.",
                        details={"component_key": descriptor.component_key},
                    )
                descriptors[descriptor.component_key] = descriptor
        return [descriptors[key] for key in sorted(descriptors)]

    def resolve(
        self,
        *,
        project_id: UUID,
        mcu_config_id: UUID,
        mcu_config_revision: int,
        requirements: list[ComponentRequirement],
        architecture: str,
        device: str,
        toolchain_id: str,
        build_system: str,
        capabilities: set[str] | None = None,
        rtos: str | None = None,
    ) -> DependencyLock:
        descriptors = {item.component_key: item for item in self.descriptors()}
        resolved: dict[str, ResolvedComponent] = {}
        visiting: list[str] = []

        def resolve_requirement(requirement: ComponentRequirement) -> None:
            candidates = [
                descriptor
                for descriptor in descriptors.values()
                if self._matches_requirement(descriptor, requirement)
                and descriptor.production_eligible
                and not descriptor.reference_only
                and self._compatible(
                    descriptor,
                    architecture=architecture,
                    device=device,
                    toolchain_id=toolchain_id,
                    build_system=build_system,
                    capabilities=capabilities or set(),
                    rtos=rtos,
                )
            ]
            if not candidates:
                code = (
                    EngineeringErrorCode.COMPONENT_REFERENCE_ONLY
                    if any(
                        descriptor.reference_only or not descriptor.production_eligible
                        for descriptor in descriptors.values()
                        if self._matches_requirement(descriptor, requirement)
                    )
                    else EngineeringErrorCode.COMPONENT_UNAVAILABLE
                )
                raise EngineeringError(
                    code,
                    "No production-eligible component satisfies the requirement.",
                    details={
                        "capability": requirement.capability,
                        "component_key": requirement.component_key,
                    },
                )
            candidates.sort(key=lambda value: (value.component_key, value.provider_id))
            descriptor = candidates[0]
            if not descriptor.license_expression or descriptor.license_expression.upper() in {
                "UNKNOWN",
                "NOASSERTION",
            }:
                raise EngineeringError(
                    EngineeringErrorCode.COMPONENT_LICENSE_BLOCKED,
                    "Production dependency has no approved license expression.",
                    details={"component_key": descriptor.component_key},
                )
            if descriptor.component_key in visiting:
                cycle = [*visiting, descriptor.component_key]
                raise EngineeringError(
                    EngineeringErrorCode.DEPENDENCY_CYCLE,
                    "Component dependency cycle detected.",
                    details={"cycle": cycle},
                )
            provider = next(
                provider
                for provider in self._providers
                if provider.provider_id == descriptor.provider_id
            )
            releases = [
                release
                for release in provider.releases(descriptor.id)
                if not release.yanked
                and release.verified
                and release.content_hash is not None
                and _satisfies(release.version, requirement.version_constraint)
            ]
            if not releases:
                raise EngineeringError(
                    EngineeringErrorCode.COMPONENT_VERSION_UNRESOLVED,
                    "No verified immutable release satisfies the component requirement.",
                    details={"component_key": descriptor.component_key},
                )
            release = sorted(releases, key=lambda value: _version_key(value.version), reverse=True)[
                0
            ]
            previous = resolved.get(descriptor.component_key)
            if previous is not None:
                if previous.release_id != release.id:
                    raise EngineeringError(
                        EngineeringErrorCode.DEPENDENCY_CONFLICT,
                        "The dependency graph requires incompatible component releases.",
                        details={"component_key": descriptor.component_key},
                    )
                return
            visiting.append(descriptor.component_key)
            for dependency in sorted(
                descriptor.dependencies, key=lambda value: value.component_key
            ):
                resolve_requirement(
                    ComponentRequirement(
                        capability=dependency.component_key,
                        component_key=dependency.component_key,
                        version_constraint=dependency.version_constraint,
                        required=dependency.required,
                        reason=f"dependency of {descriptor.component_key}",
                    )
                )
            visiting.pop()
            resolved[descriptor.component_key] = ResolvedComponent(
                component_id=descriptor.id,
                component_key=descriptor.component_key,
                release_id=release.id,
                version=release.version,
                revision=release.source_revision,
                manifest_hash=release.manifest_hash,
                content_hash=release.content_hash or ("0" * 64),
                files=list(release.files),
                provider_id=descriptor.provider_id,
                authority=descriptor.authority,
                license_expression=descriptor.license_expression or "UNKNOWN",
                dependencies=sorted(
                    dependency.component_key for dependency in descriptor.dependencies
                ),
                source_uri=release.source_uri or descriptor.source_uri,
            )

        for requirement in sorted(
            requirements, key=lambda value: (value.component_key or "", value.capability)
        ):
            if requirement.required:
                resolve_requirement(requirement)

        resolved_items = [resolved[key] for key in sorted(resolved)]
        lock_hash = _hash_json(
            {
                "requirements": [
                    item.model_dump(mode="json")
                    for item in sorted(
                        requirements,
                        key=lambda value: (value.component_key or "", value.capability),
                    )
                ],
                "resolved_components": [item.model_dump(mode="json") for item in resolved_items],
                "policy": self.resolution_policy_version,
                "resolver": self.resolver_version,
                "mcu_config_id": str(mcu_config_id),
                "mcu_config_revision": mcu_config_revision,
            }
        )
        return DependencyLock(
            project_id=project_id,
            mcu_config_id=mcu_config_id,
            mcu_config_revision=mcu_config_revision,
            requirements=requirements,
            resolved_components=resolved_items,
            resolution_policy_version=self.resolution_policy_version,
            resolver_version=self.resolver_version,
            lock_hash=lock_hash,
            status=DependencyLockStatus.LOCKED,
        )

    @staticmethod
    def _matches_requirement(
        descriptor: SoftwareComponentDescriptor, requirement: ComponentRequirement
    ) -> bool:
        return (
            requirement.component_key is None
            or descriptor.component_key == requirement.component_key
        ) and (
            requirement.capability in descriptor.capabilities
            or descriptor.component_key == requirement.capability
        )

    @staticmethod
    def _compatible(
        descriptor: SoftwareComponentDescriptor,
        *,
        architecture: str,
        device: str,
        toolchain_id: str,
        build_system: str,
        capabilities: set[str],
        rtos: str | None,
    ) -> bool:
        compatibility = descriptor.compatibility
        if compatibility.architectures and architecture not in compatibility.architectures:
            return False
        if compatibility.device_families and not any(
            device.startswith(prefix) for prefix in compatibility.device_families
        ):
            return False
        if compatibility.device_patterns and not any(
            re.fullmatch(pattern.replace("*", ".*"), device)
            for pattern in compatibility.device_patterns
        ):
            return False
        if compatibility.toolchain_ids and toolchain_id not in compatibility.toolchain_ids:
            return False
        if compatibility.build_systems and build_system.upper() not in {
            value.upper() for value in compatibility.build_systems
        }:
            return False
        if compatibility.rtos and (rtos is None or rtos not in compatibility.rtos):
            return False
        return set(compatibility.required_capabilities) <= capabilities and not (
            set(compatibility.forbidden_capabilities) & capabilities
        )


class ComponentMaterializer:
    """Materialize a locked closure into immutable cache entries, never during build."""

    def __init__(self, cache_root: Path) -> None:
        self.cache_root = cache_root

    def materialize(
        self,
        lock: DependencyLock,
        providers: list[ComponentProvider],
        *,
        project_id: UUID,
    ) -> list[ComponentMaterialization]:
        if lock.project_id != project_id or lock.status is not DependencyLockStatus.LOCKED:
            raise EngineeringError(
                EngineeringErrorCode.DEPENDENCY_LOCK_STALE,
                "Only a current locked dependency closure can be materialized.",
            )
        provider_map = {provider.provider_id: provider for provider in providers}
        records: list[ComponentMaterialization] = []
        self.cache_root.mkdir(parents=True, exist_ok=True)
        for component in lock.resolved_components:
            provider = provider_map.get(component.provider_id)
            if provider is None:
                raise EngineeringError(
                    EngineeringErrorCode.COMPONENT_UNAVAILABLE,
                    "Component provider is not installed.",
                    details={"provider_id": component.provider_id},
                )
            cache_key = f"{component.content_hash}/{component.manifest_hash}"
            destination = self.cache_root / cache_key
            if destination.exists():
                records.append(
                    ComponentMaterialization(
                        project_id=project_id,
                        component_id=component.component_id,
                        release_id=component.release_id,
                        owner="PUBLIC_CACHE",
                        cache_key=cache_key,
                        manifest_hash=component.manifest_hash,
                        content_hash=component.content_hash,
                        storage_uri=str(destination),
                        status=ComponentMaterializationStatus.MATERIALIZED,
                    )
                )
                continue
            with TemporaryDirectory(dir=self.cache_root) as staging:
                staging_path = Path(staging) / "component"
                result = provider.materialize(
                    ComponentRelease(
                        id=component.release_id,
                        component_id=component.component_id,
                        version=component.version,
                        revision_kind=ComponentRevisionKind.CONTENT_HASH,
                        source_revision=component.revision,
                        manifest_hash=component.manifest_hash,
                        content_hash=component.content_hash,
                        source_uri=component.source_uri,
                        verified=True,
                    ),
                    staging_path,
                )
                if result.content_hash != component.content_hash:
                    raise EngineeringError(
                        EngineeringErrorCode.COMPONENT_HASH_MISMATCH,
                        "Materialized component content hash does not match the lock.",
                        details={"component_key": component.component_key},
                    )
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(staging_path), str(destination))
            records.append(
                result.model_copy(
                    update={"project_id": project_id, "storage_uri": str(destination)}
                )
            )
        return records


__all__ = ["ComponentMaterializer", "ComponentRegistryService"]
