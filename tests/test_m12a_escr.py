"""M12A ESCR resolver, lock, policy, and offline materialization tests."""

import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid5

import pytest
from eea_adapters.components import StaticComponentProvider
from eea_application.components import ComponentMaterializer, ComponentRegistryService
from eea_core.components import (
    ComponentCompatibility,
    ComponentDependencySpec,
    ComponentRelease,
    ComponentRequirement,
    SoftwareComponentDescriptor,
)
from eea_core.enums import (
    ComponentAuthority,
    ComponentRevisionKind,
    ComponentSourceType,
    EngineeringErrorCode,
    SoftwareComponentRole,
)
from eea_core.errors import EngineeringError

PROJECT_ID = UUID(int=1300)
MCU_CONFIG_ID = UUID(int=1301)
COMPONENT_NAMESPACE = UUID("5b2ca8b9-1f04-45fc-8a95-438146ef20a8")


def _descriptor(
    key: str,
    capability: str,
    *,
    reference_only: bool = False,
    license_expression: str | None = "MIT",
    dependencies: tuple[ComponentDependencySpec, ...] = (),
) -> SoftwareComponentDescriptor:
    return SoftwareComponentDescriptor(
        id=uuid5(COMPONENT_NAMESPACE, key),
        component_key=key,
        name=key,
        vendor="fixture",
        role=SoftwareComponentRole.LIBRARY,
        authority=(
            ComponentAuthority.REFERENCE_ONLY if reference_only else ComponentAuthority.EEA_CURATED
        ),
        provider_id="fixture",
        source_type=ComponentSourceType.CURATED,
        capabilities=[capability, key],
        compatibility=ComponentCompatibility(
            architectures=["Cortex-M4"],
            device_patterns=[r"STM32G431.*"],
            toolchain_ids=["arm-none-eabi-gcc"],
            build_systems=["CMAKE"],
        ),
        license_expression=license_expression,
        dependencies=list(dependencies),
        production_eligible=not reference_only,
        reference_only=reference_only,
    )


def _release(
    descriptor: SoftwareComponentDescriptor, *, files: list[str] | None = None
) -> ComponentRelease:
    return ComponentRelease(
        id=uuid5(COMPONENT_NAMESPACE, f"{descriptor.component_key}:1.0.0"),
        component_id=descriptor.id,
        version="1.0.0",
        revision_kind=ComponentRevisionKind.GIT_COMMIT,
        source_revision="a" * 40,
        manifest_hash="1" * 64,
        content_hash="2" * 64,
        files=files or [],
        verified=True,
    )


def _service(descriptors: list[SoftwareComponentDescriptor]) -> ComponentRegistryService:
    return ComponentRegistryService(
        [
            StaticComponentProvider(
                "fixture",
                tuple(descriptors),
                tuple(_release(descriptor) for descriptor in descriptors),
            )
        ]
    )


def _requirement(capability: str, *, component_key: str | None = None) -> ComponentRequirement:
    return ComponentRequirement(
        capability=capability,
        component_key=component_key,
        reason="M12A fixture requirement",
    )


def test_escr_resolves_freertos_and_cmsis_dsp_deterministically() -> None:
    service = _service(
        [
            _descriptor("freertos.kernel", "rtos.kernel"),
            _descriptor("arm.cmsis-dsp", "dsp.math"),
        ]
    )
    requirements = [_requirement("rtos.kernel"), _requirement("dsp.math")]
    first = service.resolve(
        project_id=PROJECT_ID,
        mcu_config_id=MCU_CONFIG_ID,
        mcu_config_revision=1,
        requirements=requirements,
        architecture="Cortex-M4",
        device="STM32G431KB",
        toolchain_id="arm-none-eabi-gcc",
        build_system="CMAKE",
    )
    second = service.resolve(
        project_id=PROJECT_ID,
        mcu_config_id=MCU_CONFIG_ID,
        mcu_config_revision=1,
        requirements=requirements,
        architecture="Cortex-M4",
        device="STM32G431KB",
        toolchain_id="arm-none-eabi-gcc",
        build_system="CMAKE",
    )
    assert first.lock_hash == second.lock_hash
    assert [item.component_key for item in first.resolved_components] == [
        "arm.cmsis-dsp",
        "freertos.kernel",
    ]
    assert first.status.value == "LOCKED"


def test_escr_rejects_reference_only_unknown_license_and_incompatible_device() -> None:
    reference = _descriptor("simplefoc.reference", "motor.control", reference_only=True)
    with pytest.raises(EngineeringError) as reference_error:
        _service([reference]).resolve(
            project_id=PROJECT_ID,
            mcu_config_id=MCU_CONFIG_ID,
            mcu_config_revision=1,
            requirements=[_requirement("motor.control")],
            architecture="Cortex-M4",
            device="STM32G431KB",
            toolchain_id="arm-none-eabi-gcc",
            build_system="CMAKE",
        )
    assert reference_error.value.code is EngineeringErrorCode.COMPONENT_REFERENCE_ONLY

    unknown_license = _descriptor("unknown.license", "unknown.license", license_expression=None)
    with pytest.raises(EngineeringError) as license_error:
        _service([unknown_license]).resolve(
            project_id=PROJECT_ID,
            mcu_config_id=MCU_CONFIG_ID,
            mcu_config_revision=1,
            requirements=[_requirement("unknown.license")],
            architecture="Cortex-M4",
            device="STM32G431KB",
            toolchain_id="arm-none-eabi-gcc",
            build_system="CMAKE",
        )
    assert license_error.value.code is EngineeringErrorCode.COMPONENT_LICENSE_BLOCKED


def test_escr_detects_dependency_cycle_and_floating_revision() -> None:
    first = _descriptor(
        "cycle.a", "cycle.a", dependencies=(ComponentDependencySpec(component_key="cycle.b"),)
    )
    second = _descriptor(
        "cycle.b", "cycle.b", dependencies=(ComponentDependencySpec(component_key="cycle.a"),)
    )
    with pytest.raises(EngineeringError) as cycle_error:
        _service([first, second]).resolve(
            project_id=PROJECT_ID,
            mcu_config_id=MCU_CONFIG_ID,
            mcu_config_revision=1,
            requirements=[_requirement("cycle.a")],
            architecture="Cortex-M4",
            device="STM32G431KB",
            toolchain_id="arm-none-eabi-gcc",
            build_system="CMAKE",
        )
    assert cycle_error.value.code is EngineeringErrorCode.DEPENDENCY_CYCLE

    with pytest.raises(ValueError):
        ComponentRelease(
            component_id=first.id,
            version="1.0.0",
            revision_kind=ComponentRevisionKind.GIT_COMMIT,
            source_revision="main",
            manifest_hash="1" * 64,
        )


def test_escr_materializes_content_addressed_cache_offline(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    file_path = source / "include" / "fixture.h"
    file_path.parent.mkdir()
    file_path.write_text("#define FIXTURE 1\n", encoding="utf-8")
    manifest = {"include/fixture.h": hashlib.sha256(file_path.read_bytes()).hexdigest()}
    content = b"include/fixture.h\0" + file_path.read_bytes()
    descriptor = _descriptor("fixture.component", "fixture.component")
    release = _release(descriptor, files=["include/fixture.h"]).model_copy(
        update={
            "manifest_hash": hashlib.sha256(
                json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "content_hash": hashlib.sha256(content).hexdigest(),
        }
    )
    provider = StaticComponentProvider(
        "fixture",
        (descriptor,),
        (release,),
        roots={release.id: source},
    )
    lock = ComponentRegistryService([provider]).resolve(
        project_id=PROJECT_ID,
        mcu_config_id=MCU_CONFIG_ID,
        mcu_config_revision=1,
        requirements=[_requirement("fixture.component")],
        architecture="Cortex-M4",
        device="STM32G431KB",
        toolchain_id="arm-none-eabi-gcc",
        build_system="CMAKE",
    )
    records = ComponentMaterializer(tmp_path / "cache").materialize(
        lock, [provider], project_id=PROJECT_ID
    )
    assert records[0].project_id == PROJECT_ID
    assert (Path(records[0].storage_uri) / "include/fixture.h").is_file()
