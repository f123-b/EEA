"""Deterministic plugin-owned checks against Core MCUConfigIR."""

from math import isfinite
from typing import Literal

from eea_core.domain_extensions import DomainValidationDiagnostic
from eea_core.mcu_config import ADCConfig, MCUConfigIR, PWMConfig
from eea_ports.domain_extensions import DomainValidationContext
from pydantic import ValidationError

from plugins.builtin.motor_control.schemas.ir import MotorControlIR

ValidationStatus = Literal["PASS", "FAIL", "UNKNOWN", "BLOCKED"]

_RULE_IDS: tuple[str, ...] = (
    "COMPLEMENTARY_PWM",
    "DEADTIME_REQUIRED",
    "CURRENT_SENSE_ADC_RANGE",
    "ADC_TRIGGER_ALIGNMENT",
    "CURRENT_LOOP_TIMING_BUDGET",
    "SIGN_CONVENTION_COMPLETE",
    "SPEED_FEEDBACK_SIGN_CONSISTENT",
    "ELECTRICAL_ANGLE_DIRECTION_CONSISTENT",
    "PI_OUTPUT_SATURATION_LIMIT",
    "STARTUP_ALIGNMENT_REQUIRED",
    "MOTOR_REQUIREMENT_MCUCONFIG_MISMATCH",
)


class MotorControlDiagnostic(DomainValidationDiagnostic):
    """A plugin diagnostic; UNKNOWN/BLOCKED never become PASS."""


def _diagnostic(
    rule_id: str,
    status: ValidationStatus,
    message: str,
    **details: object,
) -> MotorControlDiagnostic:
    return MotorControlDiagnostic(rule_id=rule_id, status=status, message=message, details=details)


def _pwm_configs(config: MCUConfigIR) -> list[PWMConfig]:
    return [pwm for peripheral in config.peripherals for pwm in peripheral.pwm]


def _adc_configs(config: MCUConfigIR) -> list[ADCConfig]:
    return [adc for peripheral in config.peripherals for adc in peripheral.adc]


def _same_value(left: object, right: object) -> bool:
    if left is None or right is None:
        return False
    left_dimension = getattr(left, "dimension", None)
    right_dimension = getattr(right, "dimension", None)
    left_nominal = getattr(left, "normalized_nominal", None)
    right_nominal = getattr(right, "normalized_nominal", None)
    return (
        left_dimension is not None
        and left_dimension is right_dimension
        and left_nominal is not None
        and right_nominal is not None
        and abs(left_nominal - right_nominal) <= 1e-12
    )


def _normalized(value: object) -> float | None:
    normalized = getattr(value, "normalized_nominal", None)
    return normalized if isinstance(normalized, (int, float)) else None


def _find_pwm(config: MCUConfigIR, ref: str | None) -> PWMConfig | None:
    if ref is None:
        return None
    return next(
        (item for item in _pwm_configs(config) if item.timer == ref or str(item.id) == ref),
        None,
    )


def _find_adc(config: MCUConfigIR, ref: str) -> ADCConfig | None:
    return next(
        (item for item in _adc_configs(config) if item.instance == ref or str(item.id) == ref),
        None,
    )


def _missing_reference_status(reference: str | None) -> ValidationStatus:
    return "BLOCKED" if reference is None else "FAIL"


def _evaluate_complementary_pwm(
    ir: MotorControlIR, pwm: PWMConfig | None
) -> MotorControlDiagnostic:
    requirement = ir.pwm_requirement
    if not requirement.complementary_required:
        return _diagnostic("COMPLEMENTARY_PWM", "PASS", "Complementary PWM is not required")
    if pwm is None:
        return _diagnostic(
            "COMPLEMENTARY_PWM",
            _missing_reference_status(ir.mcu_config_refs.pwm),
            "Required PWM reference does not resolve in MCUConfigIR",
            pwm_ref=ir.mcu_config_refs.pwm,
        )
    return _diagnostic(
        "COMPLEMENTARY_PWM",
        "PASS" if pwm.complementary_channel else "FAIL",
        "Complementary PWM channel requirement checked",
        timer=pwm.timer,
        complementary_channel=pwm.complementary_channel,
    )


def _evaluate_deadtime(ir: MotorControlIR, pwm: PWMConfig | None) -> MotorControlDiagnostic:
    requirement = ir.pwm_requirement
    if not requirement.deadtime_required:
        return _diagnostic("DEADTIME_REQUIRED", "PASS", "PWM deadtime is not required")
    if requirement.deadtime is None:
        return _diagnostic(
            "DEADTIME_REQUIRED", "BLOCKED", "A required PWM deadtime value is missing"
        )
    if pwm is None:
        return _diagnostic(
            "DEADTIME_REQUIRED",
            _missing_reference_status(ir.mcu_config_refs.pwm),
            "Required PWM reference does not resolve in MCUConfigIR",
            pwm_ref=ir.mcu_config_refs.pwm,
        )
    if pwm.deadtime is None:
        return _diagnostic(
            "DEADTIME_REQUIRED", "FAIL", "MCUConfigIR does not realize the required deadtime"
        )
    return _diagnostic(
        "DEADTIME_REQUIRED",
        "PASS" if _same_value(requirement.deadtime, pwm.deadtime) else "FAIL",
        "PWM deadtime requirement checked against realized configuration",
        timer=pwm.timer,
    )


def _evaluate_current_sense(
    ir: MotorControlIR, mcu_config: MCUConfigIR, adc: ADCConfig | None
) -> MotorControlDiagnostic:
    if ir.current_sense_ref is None:
        return _diagnostic(
            "CURRENT_SENSE_ADC_RANGE",
            "BLOCKED",
            "Current-sense hardware reference is required",
        )
    if not ir.mcu_config_refs.adc:
        return _diagnostic(
            "CURRENT_SENSE_ADC_RANGE",
            "BLOCKED",
            "At least one ADC reference is required for current-sense validation",
        )
    if adc is None:
        return _diagnostic(
            "CURRENT_SENSE_ADC_RANGE",
            "FAIL",
            "Current-sense ADC reference does not resolve in MCUConfigIR",
            adc_ref=ir.mcu_config_refs.adc[0],
        )
    required_channels = set(ir.adc_sampling_requirement.current_channels)
    if required_channels and not required_channels.issubset(set(adc.channels)):
        return _diagnostic(
            "CURRENT_SENSE_ADC_RANGE",
            "FAIL",
            "Current-sense channels are not realized by the referenced ADC",
            required_channels=sorted(required_channels),
            realized_channels=adc.channels,
        )
    if not adc.expected_range:
        return _diagnostic(
            "CURRENT_SENSE_ADC_RANGE",
            "BLOCKED",
            "ADC expected range is required to close current-sense range validation",
            adc_instance=adc.instance,
        )
    del mcu_config
    return _diagnostic(
        "CURRENT_SENSE_ADC_RANGE",
        "PASS",
        "Current-sense ADC channels and expected range are available",
        adc_instance=adc.instance,
    )


def _evaluate_adc_trigger(
    ir: MotorControlIR, mcu_config: MCUConfigIR, adc: ADCConfig | None, pwm: PWMConfig | None
) -> MotorControlDiagnostic:
    if not ir.mcu_config_refs.adc:
        return _diagnostic(
            "ADC_TRIGGER_ALIGNMENT", "BLOCKED", "At least one ADC reference is required"
        )
    if adc is None:
        return _diagnostic(
            "ADC_TRIGGER_ALIGNMENT",
            "FAIL",
            "ADC reference does not resolve in MCUConfigIR",
            adc_ref=ir.mcu_config_refs.adc[0],
        )
    required_trigger = ir.adc_sampling_requirement.trigger_source_ref
    if required_trigger is None or adc.trigger_source is None:
        return _diagnostic(
            "ADC_TRIGGER_ALIGNMENT",
            "BLOCKED",
            "Both required and realized ADC trigger sources are needed",
            adc_instance=adc.instance,
        )
    if adc.trigger_source != required_trigger:
        return _diagnostic(
            "ADC_TRIGGER_ALIGNMENT",
            "FAIL",
            "ADC trigger source does not match MotorControl requirement",
            required_trigger=required_trigger,
            realized_trigger=adc.trigger_source,
        )
    if ir.adc_sampling_requirement.synchronized_to_pwm:
        if pwm is None or ir.mcu_config_refs.pwm is None:
            return _diagnostic(
                "ADC_TRIGGER_ALIGNMENT",
                "BLOCKED",
                "PWM reference is required for synchronized ADC validation",
            )
        if pwm.update_event is not None and pwm.update_event != required_trigger:
            return _diagnostic(
                "ADC_TRIGGER_ALIGNMENT",
                "FAIL",
                "ADC trigger is not aligned with the realized PWM update event",
                pwm_update_event=pwm.update_event,
                required_trigger=required_trigger,
            )
    del mcu_config
    return _diagnostic("ADC_TRIGGER_ALIGNMENT", "PASS", "ADC trigger alignment requirement checked")


def _evaluate_current_loop_timing(ir: MotorControlIR) -> MotorControlDiagnostic:
    loop = ir.current_loop
    if loop is None:
        return _diagnostic(
            "CURRENT_LOOP_TIMING_BUDGET", "BLOCKED", "Current-loop timing requirements are missing"
        )
    frequency = _normalized(loop.frequency)
    period = _normalized(loop.period)
    if frequency is None or period is None or frequency <= 0 or period <= 0:
        return _diagnostic(
            "CURRENT_LOOP_TIMING_BUDGET",
            "BLOCKED",
            "Current-loop frequency and period are required",
        )
    expected_period = 1.0 / frequency
    if abs(period - expected_period) > max(1e-12, expected_period * 1e-6):
        return _diagnostic(
            "CURRENT_LOOP_TIMING_BUDGET",
            "FAIL",
            "Current-loop period does not match the declared frequency",
            expected_period_seconds=expected_period,
            period_seconds=period,
        )
    for name, value in (
        ("sample_to_actuation_latency", loop.sample_to_actuation_latency),
        ("cpu_budget", loop.cpu_budget),
    ):
        normalized = _normalized(value)
        if normalized is not None and normalized > period:
            return _diagnostic(
                "CURRENT_LOOP_TIMING_BUDGET",
                "FAIL",
                f"Current-loop {name} exceeds the declared period",
                period_seconds=period,
                value_seconds=normalized,
            )
    return _diagnostic(
        "CURRENT_LOOP_TIMING_BUDGET",
        "UNKNOWN",
        "Static timing arithmetic is valid; runtime execution budget evidence is unavailable",
        runtime_evidence_required=True,
    )


def _evaluate_sign_convention(ir: MotorControlIR) -> MotorControlDiagnostic:
    values = (
        ir.electrical_angle.mechanical_direction,
        ir.electrical_angle.electrical_angle_direction,
        ir.electrical_angle.phase_sequence,
        ir.electrical_angle.zero_offset,
        ir.sign_convention.positive_torque_current,
        ir.sign_convention.speed_feedback_sign,
        ir.sign_convention.encoder_direction,
        ir.sign_convention.park_convention,
        ir.sign_convention.svpwm_phase_mapping,
    )
    present = sum(value is not None for value in values)
    if present == 0:
        status: ValidationStatus = "BLOCKED"
    elif present != len(values):
        status = "FAIL"
    else:
        status = "PASS"
    return _diagnostic(
        "SIGN_CONVENTION_COMPLETE",
        status,
        "Sign and electrical-angle convention completeness checked",
        present_fields=present,
        required_fields=len(values),
    )


def _evaluate_speed_feedback(ir: MotorControlIR) -> MotorControlDiagnostic:
    if (
        ir.encoder_ref is None
        or ir.electrical_angle.mechanical_direction is None
        or ir.sign_convention.encoder_direction is None
        or ir.sign_convention.speed_feedback_sign is None
    ):
        return _diagnostic(
            "SPEED_FEEDBACK_SIGN_CONSISTENT",
            "BLOCKED",
            (
                "Encoder reference, mechanical direction, encoder direction, and speed sign "
                "are required"
            ),
        )
    same_direction = (
        ir.sign_convention.encoder_direction == ir.electrical_angle.mechanical_direction
    )
    expected_same = ir.sign_convention.speed_feedback_sign == "POSITIVE_FORWARD"
    return _diagnostic(
        "SPEED_FEEDBACK_SIGN_CONSISTENT",
        "PASS" if same_direction == expected_same else "FAIL",
        "Speed feedback sign consistency checked against encoder direction",
        same_direction=same_direction,
        expected_same_direction=expected_same,
    )


def _evaluate_electrical_angle(ir: MotorControlIR) -> MotorControlDiagnostic:
    values = (
        ir.electrical_angle.mechanical_direction,
        ir.electrical_angle.electrical_angle_direction,
        ir.electrical_angle.phase_sequence,
        ir.electrical_angle.zero_offset,
        ir.sign_convention.park_convention,
        ir.sign_convention.svpwm_phase_mapping,
    )
    present = sum(value is not None for value in values)
    if present == 0:
        status: ValidationStatus = "BLOCKED"
    elif present != len(values):
        status = "FAIL"
    else:
        status = "UNKNOWN"
    return _diagnostic(
        "ELECTRICAL_ANGLE_DIRECTION_CONSISTENT",
        status,
        (
            "Electrical-angle fields are explicit; canonical phase-map evidence is required "
            "for consistency closure"
            if status == "UNKNOWN"
            else "Electrical-angle direction inputs are incomplete"
        ),
        canonical_phase_map_evidence_required=status == "UNKNOWN",
    )


def _evaluate_saturation(ir: MotorControlIR) -> MotorControlDiagnostic:
    if ir.current_loop is None or ir.velocity_loop is None:
        return _diagnostic(
            "PI_OUTPUT_SATURATION_LIMIT",
            "BLOCKED",
            "Current-loop and velocity-loop output limits are both required",
        )
    limits = (ir.current_loop.output_limit, ir.velocity_loop.output_limit)
    if any(value is None for value in limits):
        return _diagnostic(
            "PI_OUTPUT_SATURATION_LIMIT",
            "FAIL",
            "Every PI loop must declare an output saturation limit",
        )
    if any(not isfinite(value) or value < 0 for value in limits if value is not None):
        return _diagnostic(
            "PI_OUTPUT_SATURATION_LIMIT",
            "FAIL",
            "PI output saturation limits must be finite and non-negative",
        )
    return _diagnostic(
        "PI_OUTPUT_SATURATION_LIMIT", "PASS", "PI output saturation limits are explicit"
    )


def _evaluate_startup(ir: MotorControlIR) -> MotorControlDiagnostic:
    startup = ir.startup
    if ir.encoder_ref is None:
        return _diagnostic(
            "STARTUP_ALIGNMENT_REQUIRED", "BLOCKED", "Encoder reference is required for alignment"
        )
    if not startup.alignment_required or not startup.current_sensor_offset_required:
        return _diagnostic(
            "STARTUP_ALIGNMENT_REQUIRED",
            "FAIL",
            "Alignment and current-sensor offset are mandatory",
        )
    if not startup.steps:
        return _diagnostic(
            "STARTUP_ALIGNMENT_REQUIRED",
            "FAIL",
            "At least one startup/calibration step is required",
        )
    if any(
        step.current_limit is None or step.voltage_limit is None or step.timeout is None
        for step in startup.steps
    ):
        return _diagnostic(
            "STARTUP_ALIGNMENT_REQUIRED",
            "BLOCKED",
            "Every startup step requires current, voltage, and timeout limits",
        )
    if startup.test_result is None:
        return _diagnostic(
            "STARTUP_ALIGNMENT_REQUIRED",
            "UNKNOWN",
            "Startup/calibration execution result is not available",
            execution_evidence_required=True,
        )
    return _diagnostic(
        "STARTUP_ALIGNMENT_REQUIRED",
        startup.test_result,
        "Startup/calibration test result propagated without changing its safety status",
    )


def _evaluate_requirement_mismatch(
    ir: MotorControlIR, mcu_config: MCUConfigIR, pwm: PWMConfig | None, adc: ADCConfig | None
) -> MotorControlDiagnostic:
    failures: list[str] = []
    blocked: list[str] = []
    requirement = ir.pwm_requirement
    if pwm is None:
        if ir.mcu_config_refs.pwm is None:
            blocked.append("pwm_reference")
        else:
            failures.append("pwm_reference")
    else:
        if requirement.target_frequency is not None:
            if pwm.realized_frequency is None:
                blocked.append("realized_frequency")
            elif not _same_value(requirement.target_frequency, pwm.realized_frequency):
                failures.append("frequency")
        if requirement.center_aligned_required and not pwm.center_aligned:
            failures.append("center_aligned")
        if requirement.complementary_required and not pwm.complementary_channel:
            failures.append("complementary_channel")
        if requirement.deadtime_required:
            if requirement.deadtime is None or pwm.deadtime is None:
                blocked.append("deadtime")
            elif not _same_value(requirement.deadtime, pwm.deadtime):
                failures.append("deadtime")
        if requirement.polarity is not None and pwm.polarity != requirement.polarity:
            failures.append("polarity")
        if requirement.break_input_required and pwm.break_input is None:
            failures.append("break_input")
    if not ir.mcu_config_refs.adc:
        blocked.append("adc_reference")
    elif adc is None:
        failures.append("adc_reference")
    else:
        required_trigger = ir.adc_sampling_requirement.trigger_source_ref
        if required_trigger is None or adc.trigger_source is None:
            blocked.append("adc_trigger")
        elif adc.trigger_source != required_trigger:
            failures.append("adc_trigger")
        if ir.adc_sampling_requirement.dma_required and adc.dma_ref is None:
            failures.append("adc_dma")
    del mcu_config
    if failures:
        status: ValidationStatus = "FAIL"
    elif blocked:
        status = "BLOCKED"
    else:
        status = "PASS"
    return _diagnostic(
        "MOTOR_REQUIREMENT_MCUCONFIG_MISMATCH",
        status,
        "MotorControl requirements compared with realized MCUConfigIR",
        failures=failures,
        blocked=blocked,
    )


def validate_against_mcu_config(
    ir: MotorControlIR, mcu_config: MCUConfigIR | None
) -> tuple[MotorControlDiagnostic, ...]:
    """Evaluate every frozen M15 rule without inventing unavailable evidence."""

    if mcu_config is None:
        return tuple(
            _diagnostic(
                rule_id,
                "UNKNOWN",
                "MCUConfigIR is required for cross-validation",
                input_required="mcu_config",
            )
            for rule_id in _RULE_IDS
        )

    pwm = _find_pwm(mcu_config, ir.mcu_config_refs.pwm)
    adc = _find_adc(mcu_config, ir.mcu_config_refs.adc[0]) if ir.mcu_config_refs.adc else None
    return (
        _evaluate_complementary_pwm(ir, pwm),
        _evaluate_deadtime(ir, pwm),
        _evaluate_current_sense(ir, mcu_config, adc),
        _evaluate_adc_trigger(ir, mcu_config, adc, pwm),
        _evaluate_current_loop_timing(ir),
        _evaluate_sign_convention(ir),
        _evaluate_speed_feedback(ir),
        _evaluate_electrical_angle(ir),
        _evaluate_saturation(ir),
        _evaluate_startup(ir),
        _evaluate_requirement_mismatch(ir, mcu_config, pwm, adc),
    )


def validate_domain_context(context: DomainValidationContext) -> tuple[MotorControlDiagnostic, ...]:
    """Adapt the generic Domain contract to MotorControl-owned IR and Core MCUConfigIR."""

    raw_ir = context.inputs.get("domain_ir")
    if raw_ir is None:
        return tuple(
            _diagnostic(
                rule_id,
                "BLOCKED",
                "MotorControlIR is required for MotorControl executable validation",
                input_required="domain_ir",
            )
            for rule_id in _RULE_IDS
        )
    try:
        ir = raw_ir if isinstance(raw_ir, MotorControlIR) else MotorControlIR.model_validate(raw_ir)
    except (TypeError, ValidationError) as exc:
        return tuple(
            _diagnostic(
                rule_id,
                "BLOCKED",
                "MotorControlIR could not be validated",
                reason=str(exc),
            )
            for rule_id in _RULE_IDS
        )
    raw_mcu_config = context.inputs.get("mcu_config")
    if raw_mcu_config is None:
        mcu_config = None
    else:
        try:
            mcu_config = (
                raw_mcu_config
                if isinstance(raw_mcu_config, MCUConfigIR)
                else MCUConfigIR.model_validate(raw_mcu_config)
            )
        except (TypeError, ValidationError) as exc:
            return tuple(
                _diagnostic(
                    rule_id,
                    "BLOCKED",
                    "MCUConfigIR could not be validated",
                    reason=str(exc),
                )
                for rule_id in _RULE_IDS
            )
    return validate_against_mcu_config(ir, mcu_config)


__all__ = ["MotorControlDiagnostic", "validate_against_mcu_config", "validate_domain_context"]
