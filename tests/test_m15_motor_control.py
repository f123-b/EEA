"""M15 bundled MotorControl Domain Plugin contracts and validation tests."""

from pathlib import Path
from uuid import UUID

from eea_application.domains import DomainExtensionRegistry
from eea_core.claims import EngineeringValue
from eea_core.enums import EngineeringDimension
from eea_core.mcu_config import (
    ADCConfig,
    ClockIR,
    MCUConfigIR,
    PeripheralConfigIR,
    PWMConfig,
)

from plugins.builtin.motor_control import (
    MotorControlIR,
    build_motor_control_plugin,
    validate_against_mcu_config,
)
from plugins.builtin.motor_control.schemas.ir import (
    ADCSamplingRequirement,
    MCUConfigReferences,
    PWMRequirement,
)


def _frequency(value: float, unit: str = "Hz") -> EngineeringValue:
    return EngineeringValue(unit=unit, dimension=EngineeringDimension.FREQUENCY, nominal=value)


def _time(value: float, unit: str = "ns") -> EngineeringValue:
    return EngineeringValue(unit=unit, dimension=EngineeringDimension.TIME, nominal=value)


def _mcu_config(*, matching: bool = True) -> MCUConfigIR:
    return MCUConfigIR(
        project_id=UUID("00000000-0000-0000-0000-000000000001"),
        hardware_ir_id=UUID("00000000-0000-0000-0000-000000000002"),
        hardware_ir_revision=1,
        circuit_id=UUID("00000000-0000-0000-0000-000000000003"),
        circuit_revision=1,
        schematic_id=UUID("00000000-0000-0000-0000-000000000004"),
        schematic_revision=1,
        device_instance_id=UUID("00000000-0000-0000-0000-000000000005"),
        clock=ClockIR(source="HSE"),
        peripherals=[
            PeripheralConfigIR(
                instance="TIM1",
                mode="PWM",
                pwm=[
                    PWMConfig(
                        timer="TIM1" if matching else "TIM2",
                        channel="CH1",
                        complementary_channel="CH1N",
                        center_aligned=True,
                        realized_frequency=_frequency(20_000),
                        deadtime=_time(500),
                    )
                ],
            ),
            PeripheralConfigIR(
                instance="ADC1",
                mode="REGULAR",
                adc=[ADCConfig(instance="ADC1", trigger_source="TIM1_UP")],
            ),
        ],
    )


def _motor_control_ir() -> MotorControlIR:
    return MotorControlIR(
        motor_ref="hardware:motor-1",
        inverter_ref="hardware:inverter-1",
        encoder_ref="hardware:encoder-1",
        current_sense_ref="hardware:current-sense-1",
        pwm_requirement=PWMRequirement(
            target_frequency=_frequency(20, "kHz"),
            deadtime_required=True,
            deadtime=_time(500),
        ),
        adc_sampling_requirement=ADCSamplingRequirement(trigger_source_ref="TIM1_UP"),
        mcu_config_refs=MCUConfigReferences(pwm="TIM1", adc=["ADC1"]),
    )


def test_motor_control_plugin_matches_frozen_manifest_and_composition_contract() -> None:
    manifest = Path("plugins/builtin/motor_control/manifest.yaml").read_text(encoding="utf-8")
    plugin = build_motor_control_plugin()
    registry = DomainExtensionRegistry((plugin,))
    descriptor = registry.get_descriptor("org.eea.motor_control")
    plan = registry.resolve_composition([descriptor.domain_id])

    assert "id: org.eea.motor_control" in manifest
    assert "trust_tier: bundled" in manifest
    assert descriptor.provided_capabilities == [
        "motor_control.ir",
        "motor_control.review",
        "motor_control.codegen",
    ]
    assert plan.active_domain_ids == ["org.eea.motor_control"]
    assert len(plan.rules) == 11
    assert [item.generator_id for item in plan.generators] == [
        "motor_control.ir.contract",
        "motor_control.validation.report",
    ]
    assert len(plan.context_contributions) == 1
    assert {item.kind for item in plan.ui_contributions} == {"action", "form", "navigation"}
    assert {item.value for item in descriptor.permissions} == {"READ", "WRITE", "BUILD"}


def test_motor_control_ir_keeps_realized_configuration_as_references() -> None:
    fields = set(MotorControlIR.model_fields)

    assert {"pwm_requirement", "adc_sampling_requirement", "mcu_config_refs"} <= fields
    assert not {"timer", "channel", "deadtime_realized", "adc_trigger_realized"} & fields
    assert build_motor_control_plugin().ir_type is MotorControlIR


def test_motor_control_validation_detects_mcu_config_mismatch() -> None:
    matching = validate_against_mcu_config(_motor_control_ir(), _mcu_config(matching=True))
    assert {item.status for item in matching} == {"PASS"}

    mismatch = validate_against_mcu_config(_motor_control_ir(), _mcu_config(matching=False))
    assert mismatch[0].rule_id == "MOTOR_REQUIREMENT_MCUCONFIG_MISMATCH"
    assert mismatch[0].status == "FAIL"


def test_motor_control_validation_fails_closed_when_mcu_config_is_unavailable() -> None:
    diagnostics = validate_against_mcu_config(_motor_control_ir(), None)

    assert diagnostics
    assert all(item.status == "UNKNOWN" for item in diagnostics)
    assert all(item.status != "PASS" for item in diagnostics)


def test_default_application_discovers_and_activates_bundled_motor_control(client) -> None:
    project_id = client.post("/api/v1/projects", json={"name": "M15 motor project"}).json()["data"][
        "id"
    ]

    available = client.get(f"/api/v1/projects/{project_id}/domains/available")
    assert available.status_code == 200
    assert [item["descriptor"]["id"] for item in available.json()["data"]["items"]] == [
        "org.eea.motor_control"
    ]

    activated = client.post(
        f"/api/v1/projects/{project_id}/domains/org.eea.motor_control/activate",
        json={"configuration": {"benchmark_profile": "REFERENCE"}, "activated_by": "m15-test"},
    )
    assert activated.status_code == 201
    assert activated.json()["data"]["domain_id"] == "org.eea.motor_control"

    extensions = client.get(f"/api/v1/projects/{project_id}/ui/extensions")
    assert extensions.status_code == 200
    assert [item["extension_id"] for item in extensions.json()["data"]["items"]] == [
        "org.eea.motor_control.configuration",
        "org.eea.motor_control.navigation",
        "org.eea.motor_control.validate",
    ]
