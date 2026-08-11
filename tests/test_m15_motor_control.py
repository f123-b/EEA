"""M15R MotorControl contract, executable validation, and integration tests."""

from pathlib import Path
from uuid import UUID

import pytest
from eea_application.domains import DomainExtensionRegistry
from eea_core.claims import EngineeringValue
from eea_core.domain_extensions import DomainValidationResult
from eea_core.enums import EngineeringDimension
from eea_core.mcu_config import (
    ADCConfig,
    ClockIR,
    MCUConfigIR,
    PeripheralConfigIR,
    PWMConfig,
)
from eea_ports.domain_extensions import DomainValidationContext

from plugins.builtin.motor_control import (
    MotorControlConfiguration,
    MotorControlIR,
    build_motor_control_plugin,
    validate_against_mcu_config,
)
from plugins.builtin.motor_control.rules.validation import validate_domain_context
from plugins.builtin.motor_control.schemas.ir import (
    ADCSamplingRequirement,
    CurrentLoopRequirement,
    ElectricalAngle,
    MCUConfigReferences,
    MotorParameters,
    PositionLoopRequirement,
    PWMRequirement,
    SignConvention,
    StartupCalibration,
    StartupStep,
    VelocityLoopRequirement,
)
from plugins.builtin.motor_control.ui.metadata import MOTOR_CONTROL_CONFIGURATION_SCHEMA


def _value(value: float, unit: str, dimension: EngineeringDimension) -> EngineeringValue:
    return EngineeringValue(unit=unit, dimension=dimension, nominal=value)


def _frequency(value: float, unit: str = "Hz") -> EngineeringValue:
    return _value(value, unit, EngineeringDimension.FREQUENCY)


def _time(value: float, unit: str = "s") -> EngineeringValue:
    return _value(value, unit, EngineeringDimension.TIME)


def _current(value: float, unit: str = "A") -> EngineeringValue:
    return _value(value, unit, EngineeringDimension.CURRENT)


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
                        deadtime=_time(500, "ns"),
                        polarity="ACTIVE_HIGH",
                        break_input="BKIN",
                        update_event="TIM1_UP",
                    )
                ],
            ),
            PeripheralConfigIR(
                instance="ADC1",
                mode="REGULAR",
                adc=[
                    ADCConfig(
                        instance="ADC1",
                        channels=["IS_U", "IS_V"],
                        trigger_source="TIM1_UP",
                        dma_ref="DMA1",
                        expected_range={"IS_U": _current(20), "IS_V": _current(20)},
                    )
                ],
            ),
        ],
    )


def _motor_control_ir(**overrides: object) -> MotorControlIR:
    values: dict[str, object] = {
        "motor_ref": "hardware:motor-1",
        "motor_parameters": MotorParameters(
            poles=8,
            pole_pairs=4,
            rated_voltage=_value(48, "V", EngineeringDimension.VOLTAGE),
            rated_current=_current(10),
            rated_speed=_value(3000, "rpm", EngineeringDimension.ANGULAR_VELOCITY),
        ),
        "inverter_ref": "hardware:inverter-1",
        "encoder_ref": "hardware:encoder-1",
        "current_sense_ref": "hardware:current-sense-1",
        "pwm_requirement": PWMRequirement(
            target_frequency=_frequency(20, "kHz"),
            center_aligned_required=True,
            complementary_required=True,
            deadtime_required=True,
            deadtime=_time(500, "ns"),
            polarity="ACTIVE_HIGH",
            break_input_required=True,
        ),
        "adc_sampling_requirement": ADCSamplingRequirement(
            current_channels=["IS_U", "IS_V"],
            trigger_source_ref="TIM1_UP",
            sampling_window=_time(2, "us"),
            synchronized_to_pwm=True,
            dma_required=True,
            sample_to_actuation_latency=_time(5, "us"),
        ),
        "mcu_config_refs": MCUConfigReferences(pwm="TIM1", adc=["ADC1"], dma=["DMA1"]),
        "electrical_angle": ElectricalAngle(
            mechanical_direction="CW",
            electrical_angle_direction="POSITIVE",
            phase_sequence="ABC",
            zero_offset=_value(0, "deg", EngineeringDimension.ANGLE),
        ),
        "sign_convention": SignConvention(
            positive_torque_current="POSITIVE_IQ",
            speed_feedback_sign="POSITIVE_FORWARD",
            encoder_direction="CW",
            park_convention="PARK_ABC",
            svpwm_phase_mapping="ABC",
        ),
        "startup": StartupCalibration(
            alignment_required=True,
            steps=[
                StartupStep(
                    name="encoder_alignment",
                    current_limit=_current(2),
                    voltage_limit=_value(12, "V", EngineeringDimension.VOLTAGE),
                    timeout=_time(1, "s"),
                    failure_behavior="SAFE_STATE",
                )
            ],
            current_sensor_offset_required=True,
            encoder_zero_required=True,
            test_result="PASS",
        ),
        "current_loop": CurrentLoopRequirement(
            frequency=_frequency(10, "kHz"),
            period=_time(100, "us"),
            id_target=_current(0),
            iq_target=_current(0),
            kp=0.1,
            ki=0.01,
            output_limit=1.0,
            anti_windup="CLAMP",
            sample_to_actuation_latency=_time(5, "us"),
            cpu_budget=_time(20, "us"),
        ),
        "velocity_loop": VelocityLoopRequirement(
            frequency=_frequency(1, "kHz"),
            period=_time(1, "ms"),
            kp=0.2,
            ki=0.02,
            output_limit=10.0,
            speed_limit=_value(3000, "rpm", EngineeringDimension.ANGULAR_VELOCITY),
            acceleration_limit=_value(100, "rad/s2", EngineeringDimension.ANGULAR_ACCELERATION),
            current_limit=_current(10),
            feedback_source="encoder-1",
        ),
        "position_loop": PositionLoopRequirement(
            frequency=_frequency(100, "Hz"),
            period=_time(10, "ms"),
            kp=0.3,
            output_limit=360.0,
            controller="PI",
            wrap_handling="MODULO",
            position_limit=_value(360, "deg", EngineeringDimension.ANGLE),
            velocity_limit=_value(3000, "rpm", EngineeringDimension.ANGULAR_VELOCITY),
        ),
    }
    values.update(overrides)
    return MotorControlIR.model_validate(values)


def _diagnostics_by_rule(ir: MotorControlIR, config: MCUConfigIR | None) -> dict[str, object]:
    return {item.rule_id: item for item in validate_against_mcu_config(ir, config)}


def _parse_simple_manifest() -> dict[str, object]:
    result: dict[str, object] = {}
    active_list: str | None = None
    for raw_line in (
        Path("plugins/builtin/motor_control/manifest.yaml").read_text(encoding="utf-8").splitlines()
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            assert active_list is not None
            value = line[2:]
            cast_list = result[active_list]
            assert isinstance(cast_list, list)
            cast_list.append(value)
            continue
        key, separator, value = line.partition(":")
        assert separator
        if value.strip() == "":
            result[key] = []
            active_list = key
        else:
            scalar = value.strip().strip('"')
            result[key] = [] if scalar == "[]" else scalar
            active_list = None
    return result


def test_motor_control_manifest_descriptor_configuration_and_ui_are_in_parity() -> None:
    manifest = _parse_simple_manifest()
    plugin = build_motor_control_plugin()
    descriptor = plugin.descriptor

    assert manifest == {
        "id": descriptor.domain_id,
        "name": descriptor.name,
        "version": descriptor.version,
        "api_version": descriptor.api_version,
        "plugin_type": "domain",
        "trust_tier": descriptor.trust_tier.value,
        "entrypoint": descriptor.entrypoint,
        "capabilities": descriptor.provided_capabilities,
        "permissions": [item.value for item in descriptor.permissions],
        "dependencies": [],
    }
    assert plugin.schema() == MOTOR_CONTROL_CONFIGURATION_SCHEMA
    form = next(item for item in plugin.ui_extensions() if item.kind == "form")
    assert form.json_schema == plugin.schema()
    artifacts = {item["artifact_id"]: item for item in plugin.artifacts()}
    assert artifacts["org.eea.motor_control.ir"]["schema_version"] == "1.0.0"
    assert artifacts["org.eea.motor_control.validation"]["schema_version"] == "1.0.0"
    assert (
        MotorControlConfiguration.model_json_schema()["properties"] == plugin.schema()["properties"]
    )


def test_motor_control_plugin_matches_frozen_composition_contract() -> None:
    plugin = build_motor_control_plugin()
    registry = DomainExtensionRegistry((plugin,))
    descriptor = registry.get_descriptor("org.eea.motor_control")
    plan = registry.resolve_composition([descriptor.domain_id])

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


def test_positive_evaluation_preserves_unknown_runtime_gates() -> None:
    diagnostics = _diagnostics_by_rule(_motor_control_ir(), _mcu_config())

    assert diagnostics["COMPLEMENTARY_PWM"].status == "PASS"
    assert diagnostics["DEADTIME_REQUIRED"].status == "PASS"
    assert diagnostics["CURRENT_SENSE_ADC_RANGE"].status == "UNKNOWN"
    assert diagnostics["CURRENT_SENSE_ADC_RANGE"].details["range_evidence_required"] is True
    assert diagnostics["ADC_TRIGGER_ALIGNMENT"].status == "PASS"
    assert diagnostics["CURRENT_LOOP_TIMING_BUDGET"].status == "UNKNOWN"
    assert diagnostics["SIGN_CONVENTION_COMPLETE"].status == "PASS"
    assert diagnostics["SPEED_FEEDBACK_SIGN_CONSISTENT"].status == "PASS"
    assert diagnostics["ELECTRICAL_ANGLE_DIRECTION_CONSISTENT"].status == "UNKNOWN"
    assert diagnostics["PI_OUTPUT_SATURATION_LIMIT"].status == "PASS"
    assert diagnostics["STARTUP_ALIGNMENT_REQUIRED"].status == "UNKNOWN"
    assert diagnostics["STARTUP_ALIGNMENT_REQUIRED"].details["execution_evidence_required"] is True
    assert diagnostics["MOTOR_REQUIREMENT_MCUCONFIG_MISMATCH"].status == "PASS"


@pytest.mark.parametrize(
    ("rule_id", "ir", "config"),
    [
        (
            "COMPLEMENTARY_PWM",
            _motor_control_ir(
                pwm_requirement=PWMRequirement(
                    target_frequency=_frequency(20, "kHz"), complementary_required=True
                )
            ),
            _mcu_config(matching=False),
        ),
        (
            "DEADTIME_REQUIRED",
            _motor_control_ir(
                pwm_requirement=PWMRequirement(
                    target_frequency=_frequency(20, "kHz"),
                    deadtime_required=True,
                    deadtime=_time(600, "ns"),
                )
            ),
            _mcu_config(),
        ),
        (
            "CURRENT_SENSE_ADC_RANGE",
            _motor_control_ir(
                adc_sampling_requirement=ADCSamplingRequirement(
                    current_channels=["IS_W"], trigger_source_ref="TIM1_UP"
                )
            ),
            _mcu_config(),
        ),
        (
            "ADC_TRIGGER_ALIGNMENT",
            _motor_control_ir(
                adc_sampling_requirement=ADCSamplingRequirement(trigger_source_ref="TIM2_UP")
            ),
            _mcu_config(),
        ),
        (
            "CURRENT_LOOP_TIMING_BUDGET",
            _motor_control_ir(
                current_loop=CurrentLoopRequirement(
                    frequency=_frequency(10, "kHz"), period=_time(200, "us")
                )
            ),
            _mcu_config(),
        ),
        (
            "SIGN_CONVENTION_COMPLETE",
            _motor_control_ir(sign_convention=SignConvention()),
            _mcu_config(),
        ),
        (
            "SPEED_FEEDBACK_SIGN_CONSISTENT",
            _motor_control_ir(
                sign_convention=SignConvention(
                    speed_feedback_sign="POSITIVE_FORWARD", encoder_direction="CCW"
                )
            ),
            _mcu_config(),
        ),
        (
            "PI_OUTPUT_SATURATION_LIMIT",
            _motor_control_ir(
                current_loop=CurrentLoopRequirement(output_limit=None),
                velocity_loop=VelocityLoopRequirement(output_limit=1),
            ),
            _mcu_config(),
        ),
        (
            "STARTUP_ALIGNMENT_REQUIRED",
            _motor_control_ir(startup=StartupCalibration(test_result="FAIL")),
            _mcu_config(),
        ),
    ],
)
def test_motor_control_negative_cases_are_fail_closed(
    rule_id: str, ir: MotorControlIR, config: MCUConfigIR
) -> None:
    diagnostics = _diagnostics_by_rule(ir, config)
    assert diagnostics[rule_id].status in {"FAIL", "BLOCKED", "UNKNOWN"}
    assert diagnostics[rule_id].status != "PASS"


def test_requirement_mcu_config_mismatch_is_negative_when_pwm_reference_is_wrong() -> None:
    diagnostics = _diagnostics_by_rule(_motor_control_ir(), _mcu_config(matching=False))
    assert diagnostics["MOTOR_REQUIREMENT_MCUCONFIG_MISMATCH"].status == "FAIL"


@pytest.mark.parametrize(
    ("test_result", "expected_status"),
    [
        ("PASS", "UNKNOWN"),
        ("FAIL", "FAIL"),
        ("BLOCKED", "BLOCKED"),
        ("UNKNOWN", "UNKNOWN"),
        (None, "UNKNOWN"),
    ],
)
def test_startup_result_requires_trusted_execution_evidence(
    test_result: str | None, expected_status: str
) -> None:
    startup = _motor_control_ir().startup.model_copy(update={"test_result": test_result})
    diagnostics = _diagnostics_by_rule(_motor_control_ir(startup=startup), _mcu_config())
    startup_diagnostic = diagnostics["STARTUP_ALIGNMENT_REQUIRED"]

    assert startup_diagnostic.status == expected_status
    if test_result in {"PASS", None}:
        assert startup_diagnostic.details["execution_evidence_required"] is True
    assert startup_diagnostic.status != "PASS" or test_result != "PASS"


def test_adc_expected_range_without_current_sense_range_evidence_is_unknown() -> None:
    diagnostics = _diagnostics_by_rule(_motor_control_ir(), _mcu_config())

    current_sense = diagnostics["CURRENT_SENSE_ADC_RANGE"]
    assert current_sense.status == "UNKNOWN"
    assert current_sense.details["range_evidence_required"] is True


def test_missing_mcu_config_returns_unknown_for_every_frozen_rule() -> None:
    diagnostics = validate_against_mcu_config(_motor_control_ir(), None)

    assert len(diagnostics) == 11
    assert {item.status for item in diagnostics} == {"UNKNOWN"}
    assert all(item.status != "PASS" for item in diagnostics)


def test_missing_domain_ir_is_blocked_by_generic_executable_contract() -> None:
    diagnostics = validate_domain_context(
        DomainValidationContext(
            project_id=UUID("00000000-0000-0000-0000-000000000001"),
            domain_id="org.eea.motor_control",
            inputs={},
        )
    )

    assert len(diagnostics) == 11
    assert {item.status for item in diagnostics} == {"BLOCKED"}


def test_registry_executes_plugin_validator_contract() -> None:
    registry = DomainExtensionRegistry((build_motor_control_plugin(),))
    result = registry.execute_validation(
        "org.eea.motor_control",
        DomainValidationContext(
            project_id=UUID("00000000-0000-0000-0000-000000000001"),
            domain_id="org.eea.motor_control",
            inputs={"domain_ir": _motor_control_ir(), "mcu_config": _mcu_config()},
        ),
    )

    assert isinstance(result, DomainValidationResult)
    assert result.domain_id == "org.eea.motor_control"
    assert len(result.diagnostics) == 11
    assert result.diagnostics[-1].rule_id == "MOTOR_REQUIREMENT_MCUCONFIG_MISMATCH"


def test_motor_control_ir_rejects_wrong_engineering_dimensions() -> None:
    with pytest.raises(ValueError, match="rated_voltage"):
        MotorParameters(rated_voltage=_current(48))
    with pytest.raises(ValueError, match=r"pwm_requirement\.target_frequency"):
        PWMRequirement(target_frequency=_current(20))
    with pytest.raises(ValueError, match=r"velocity_loop\.acceleration_limit"):
        VelocityLoopRequirement(
            acceleration_limit=_value(100, "rad/s", EngineeringDimension.ANGULAR_VELOCITY)
        )
    with pytest.raises(ValueError, match=r"limits\.zero_offset"):
        _motor_control_ir(limits={"zero_offset": _value(1, "V", EngineeringDimension.VOLTAGE)})


def test_default_application_validate_action_executes_motor_control_validator(client) -> None:
    project_id = client.post("/api/v1/projects", json={"name": "M15R validation project"}).json()[
        "data"
    ]["id"]

    response = client.post(
        f"/api/v1/projects/{project_id}/domains/org.eea.motor_control/validate",
        json={"domain_ir": _motor_control_ir().model_dump(mode="json")},
    )

    assert response.status_code == 200
    results = response.json()["data"]["validation_results"]
    assert len(results) == 1
    assert results[0]["domain_id"] == "org.eea.motor_control"
    assert len(results[0]["diagnostics"]) == 11
    assert {item["status"] for item in results[0]["diagnostics"]} == {"UNKNOWN"}


def test_default_application_resolve_composition_does_not_execute_validator(client) -> None:
    project_id = client.post("/api/v1/projects", json={"name": "M15R preview project"}).json()[
        "data"
    ]["id"]

    response = client.post(
        f"/api/v1/projects/{project_id}/domains/resolve-composition",
        json={
            "domain_ids": ["org.eea.motor_control"],
            "domain_ir": _motor_control_ir().model_dump(mode="json"),
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["validation_results"] == []


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
