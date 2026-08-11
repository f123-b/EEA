"""Small deterministic provider used for curated and fixture component catalogs."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from uuid import UUID

from eea_core.components import (
    ComponentMaterialization,
    ComponentRelease,
    SoftwareComponentDescriptor,
)
from eea_core.enums import ComponentMaterializationStatus, EngineeringErrorCode
from eea_core.errors import EngineeringError


class StaticComponentProvider:
    """Provider backed by explicit descriptors/releases; it never resolves the network."""

    def __init__(
        self,
        provider_id: str,
        descriptors: tuple[SoftwareComponentDescriptor, ...],
        releases: tuple[ComponentRelease, ...],
        roots: dict[UUID, Path] | None = None,
    ) -> None:
        self.provider_id = provider_id
        self._descriptors = descriptors
        self._releases = {release.id: release for release in releases}
        self._roots = roots or {}

    def descriptors(self) -> tuple[SoftwareComponentDescriptor, ...]:
        return self._descriptors

    def releases(self, component_id: object) -> tuple[ComponentRelease, ...]:
        return tuple(
            release for release in self._releases.values() if release.component_id == component_id
        )

    def materialize(self, release: ComponentRelease, destination: Path) -> ComponentMaterialization:
        source = self._roots.get(release.id)
        if source is None or not source.is_dir():
            raise EngineeringError(
                EngineeringErrorCode.COMPONENT_MATERIALIZATION_FAILED,
                "Static component provider has no materialization root.",
                details={"release_id": str(release.id)},
            )
        destination.mkdir(parents=True, exist_ok=True)
        for item in source.rglob("*"):
            if item.is_file():
                target = destination / item.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(item, target)
        content = b"".join(
            path.relative_to(destination).as_posix().encode("utf-8") + b"\0" + path.read_bytes()
            for path in sorted(destination.rglob("*"))
            if path.is_file()
        )
        content_hash = hashlib.sha256(content).hexdigest()
        if content_hash != release.content_hash:
            raise EngineeringError(
                EngineeringErrorCode.COMPONENT_HASH_MISMATCH,
                "Static component materialization does not match the release hash.",
            )
        manifest = {
            path.relative_to(destination).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(destination.rglob("*"))
            if path.is_file()
        }
        manifest_hash = hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if manifest_hash != release.manifest_hash:
            raise EngineeringError(
                EngineeringErrorCode.COMPONENT_HASH_MISMATCH,
                "Static component manifest does not match the release hash.",
            )
        return ComponentMaterialization(
            project_id=UUID(int=0),
            component_id=release.component_id,
            release_id=release.id,
            owner="PUBLIC_CACHE",
            cache_key=f"{release.content_hash}/{release.manifest_hash}",
            manifest_hash=manifest_hash,
            content_hash=content_hash,
            storage_uri=str(destination),
            status=ComponentMaterializationStatus.MATERIALIZED,
        )


__all__ = ["StaticComponentProvider"]
