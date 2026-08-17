"""Pinned STM32CubeG4 provider with manifest-verified materialization."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from uuid import UUID, uuid5

from eea_core.components import (
    ComponentCompatibility,
    ComponentDependencySpec,
    ComponentMaterialization,
    ComponentRelease,
    SoftwareComponentDescriptor,
)
from eea_core.enums import (
    ComponentAuthority,
    ComponentMaterializationStatus,
    ComponentRevisionKind,
    ComponentSourceType,
    EngineeringErrorCode,
    SoftwareComponentRole,
)
from eea_core.errors import EngineeringError

_NAMESPACE = UUID("6d06e0b7-f8ec-4b7d-9e11-df0d7b9e1b12")
STM32CUBEG4_COMMIT = "d11b194a9f05d1b143d154771f3dbc282c8052a5"
STM32CUBEG4_TAG = "v1.6.3"
STM32CUBEG4_URI = "https://github.com/STMicroelectronics/STM32CubeG4.git"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Stm32CubeG4Provider:
    """Provider for the official STM32CubeG4 tag and its pinned submodules."""

    provider_id = "st.stm32cubeg4"

    def __init__(
        self,
        root: Path,
        *,
        revision: str = STM32CUBEG4_COMMIT,
        version: str = STM32CUBEG4_TAG,
    ) -> None:
        self.root = root.resolve()
        self.revision = revision
        self.version = version
        self._descriptor_cache: tuple[SoftwareComponentDescriptor, ...] | None = None
        self._release_files: dict[UUID, tuple[str, ...]] = {}
        self._release_cache: dict[UUID, ComponentRelease] = {}
        self._validate_checkout()

    def descriptors(self) -> tuple[SoftwareComponentDescriptor, ...]:
        if self._descriptor_cache is None:
            compatibility = ComponentCompatibility(
                architectures=["Cortex-M4"],
                device_families=["STM32G4"],
                device_patterns=[r"STM32G431.*"],
                toolchain_ids=["arm-none-eabi-gcc", "arm-none-eabi"],
                build_systems=["CMAKE"],
            )
            self._descriptor_cache = (
                self._descriptor(
                    "st.stm32g4.cmsis-core",
                    "STM32G4 CMSIS Core",
                    SoftwareComponentRole.CMSIS_CORE,
                    ["cmsis.core"],
                    compatibility,
                    "Apache-2.0",
                    (),
                ),
                self._descriptor(
                    "st.stm32g4.cmsis-device",
                    "STM32G4 CMSIS Device",
                    SoftwareComponentRole.CMSIS_DEVICE,
                    ["cmsis.device", "mcu.startup"],
                    compatibility,
                    "Apache-2.0",
                    (ComponentDependencySpec(component_key="st.stm32g4.cmsis-core"),),
                ),
                self._descriptor(
                    "st.stm32g4.hal",
                    "STM32G4 HAL",
                    SoftwareComponentRole.HAL,
                    ["mcu.sdk", "stm32.hal", "stm32.ll"],
                    compatibility,
                    "LicenseRef-STMicroelectronics-HAL",
                    (
                        ComponentDependencySpec(component_key="st.stm32g4.cmsis-device"),
                        ComponentDependencySpec(component_key="st.stm32g4.cmsis-core"),
                    ),
                ),
                self._descriptor(
                    "freertos.kernel",
                    "FreeRTOS kernel",
                    SoftwareComponentRole.RTOS,
                    ["rtos.kernel", "freertos"],
                    compatibility,
                    "MIT",
                    (ComponentDependencySpec(component_key="st.stm32g4.cmsis-device"),),
                ),
            )
        return self._descriptor_cache

    def releases(self, component_id: object) -> tuple[ComponentRelease, ...]:
        descriptor = next((item for item in self.descriptors() if item.id == component_id), None)
        if descriptor is None:
            return ()
        release_id = uuid5(_NAMESPACE, f"{descriptor.component_key}:{self.revision}")
        if release_id not in self._release_cache:
            files = self._files_for(descriptor.component_key)
            manifest = {path: _sha256((self.root / path).read_bytes()) for path in files}
            manifest_hash = _sha256(
                json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
            )
            content = b"".join(
                path.encode("utf-8") + b"\0" + (self.root / path).read_bytes() for path in files
            )
            release = ComponentRelease(
                id=release_id,
                component_id=descriptor.id,
                version=self.version,
                revision_kind=ComponentRevisionKind.GIT_COMMIT,
                source_revision=self.revision,
                manifest_hash=manifest_hash,
                content_hash=_sha256(content),
                files=list(files),
                submodule_commit_map=self._submodule_map(),
                source_uri=STM32CUBEG4_URI,
                verified=True,
            )
            self._release_files[release_id] = files
            self._release_cache[release_id] = release
        return (self._release_cache[release_id],)

    def materialize(self, release: ComponentRelease, destination: Path) -> ComponentMaterialization:
        files = self._release_files.get(release.id)
        if files is None:
            raise EngineeringError(
                EngineeringErrorCode.COMPONENT_UNAVAILABLE,
                "STM32CubeG4 release is not registered by this provider instance.",
            )
        destination.mkdir(parents=True, exist_ok=True)
        manifest: dict[str, str] = {}
        for relative in files:
            source = self.root / relative
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            manifest[relative] = _sha256(source.read_bytes())
        manifest_hash = _sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        content = b"".join(
            path.encode("utf-8") + b"\0" + (destination / path).read_bytes() for path in files
        )
        content_hash = _sha256(content)
        if manifest_hash != release.manifest_hash or content_hash != release.content_hash:
            raise EngineeringError(
                EngineeringErrorCode.COMPONENT_HASH_MISMATCH,
                "Materialized STM32CubeG4 content does not match the pinned release.",
                details={"revision": release.source_revision},
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

    def component_files(self, component_key: str) -> tuple[str, ...]:
        return self._files_for(component_key)

    def _descriptor(
        self,
        key: str,
        name: str,
        role: SoftwareComponentRole,
        capabilities: list[str],
        compatibility: ComponentCompatibility,
        license_expression: str,
        dependencies: tuple[ComponentDependencySpec, ...],
    ) -> SoftwareComponentDescriptor:
        return SoftwareComponentDescriptor(
            id=uuid5(_NAMESPACE, key),
            component_key=key,
            name=name,
            vendor="STMicroelectronics",
            role=role,
            authority=ComponentAuthority.VENDOR_OFFICIAL,
            provider_id=self.provider_id,
            source_type=ComponentSourceType.VENDOR_SDK,
            source_uri=STM32CUBEG4_URI,
            capabilities=capabilities,
            compatibility=compatibility,
            license_expression=license_expression,
            dependencies=list(dependencies),
            production_eligible=True,
        )

    def _validate_checkout(self) -> None:
        if not self.root.is_dir():
            raise EngineeringError(
                EngineeringErrorCode.COMPONENT_UNAVAILABLE,
                "Pinned STM32CubeG4 checkout is not available.",
                details={"root": str(self.root)},
            )
        try:
            result = subprocess.run(
                ["git", "-C", str(self.root), "rev-parse", "HEAD"],
                capture_output=True,
                check=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise EngineeringError(
                EngineeringErrorCode.COMPONENT_UNAVAILABLE,
                "Pinned STM32CubeG4 checkout identity could not be verified.",
                details={"root": str(self.root), "reason": type(error).__name__},
            ) from error
        if result.stdout.strip() != self.revision:
            raise EngineeringError(
                EngineeringErrorCode.COMPONENT_HASH_MISMATCH,
                "STM32CubeG4 checkout is not at the pinned commit.",
                details={"expected": self.revision, "actual": result.stdout.strip()},
            )

    def _files_for(self, component_key: str) -> tuple[str, ...]:
        if component_key == "st.stm32g4.cmsis-core":
            roots = ["Drivers/CMSIS/Include"]
        elif component_key == "st.stm32g4.cmsis-device":
            roots = [
                "Drivers/CMSIS/Device/ST/STM32G4xx/Include",
                "Drivers/CMSIS/Device/ST/STM32G4xx/Source",
                "Projects/NUCLEO-G431KB/Applications/FreeRTOS/FreeRTOS_ThreadCreation/STM32CubeIDE/STM32G431KBTX_FLASH.ld",
            ]
        elif component_key == "st.stm32g4.hal":
            roots = [
                "Drivers/STM32G4xx_HAL_Driver/Inc",
                "Drivers/STM32G4xx_HAL_Driver/Src",
            ]
        elif component_key == "freertos.kernel":
            source_root = "Middlewares/Third_Party/FreeRTOS/Source"
            roots = [
                f"{source_root}/include",
                f"{source_root}/portable/GCC/ARM_CM4F/port.c",
                f"{source_root}/portable/GCC/ARM_CM4F/portmacro.h",
            ]
        else:
            raise EngineeringError(
                EngineeringErrorCode.COMPONENT_UNAVAILABLE,
                "Unknown STM32CubeG4 component key.",
                details={"component_key": component_key},
            )
        paths: list[Path] = []
        for root in roots:
            candidate = self.root / root
            if candidate.is_file():
                paths.append(candidate)
            else:
                paths.extend(
                    path
                    for path in candidate.rglob("*")
                    if path.is_file() and path.suffix.lower() in {".c", ".h", ".s", ".S"}
                )
        if component_key == "freertos.kernel":
            kernel_source = self.root / "Middlewares/Third_Party/FreeRTOS/Source"
            paths.extend(path for path in kernel_source.glob("*.c") if path.is_file())
            port_root = kernel_source / "portable/GCC/ARM_CM4F"
            paths.extend(path for path in port_root.glob("port.*") if path.is_file())
        files = sorted(path.relative_to(self.root).as_posix() for path in paths)
        if component_key == "st.stm32g4.cmsis-device":
            files = [
                path
                for path in files
                if not path.lower().endswith(".s")
                or path.endswith(
                    "Drivers/CMSIS/Device/ST/STM32G4xx/Source/Templates/gcc/startup_stm32g431xx.s"
                )
            ]
        if not files:
            raise EngineeringError(
                EngineeringErrorCode.COMPONENT_UNAVAILABLE,
                "Pinned STM32CubeG4 component contains no source files.",
                details={"component_key": component_key},
            )
        return tuple(files)

    def _submodule_map(self) -> dict[str, str]:
        result = subprocess.run(
            ["git", "-C", str(self.root), "submodule", "status"],
            capture_output=True,
            check=True,
            text=True,
        )
        submodules: dict[str, str] = {}
        for line in result.stdout.splitlines():
            match = re.match(r"[-+ ]?([0-9a-f]{40})\s+(.+)$", line.strip())
            if match:
                submodules[match.group(2).strip()] = match.group(1)
        return dict(sorted(submodules.items()))


__all__ = [
    "STM32CUBEG4_COMMIT",
    "STM32CUBEG4_TAG",
    "Stm32CubeG4Provider",
]
