"""Deterministic plugin-owned checks against Core MCUConfigIR."""

from typing import Literal

from eea_core.mcu_config import ADCConfig, MCUConfigIR, PWMConfig
from pydantic import BaseModel, ConfigDict, Field

from plugins.builtin.motor_control.schemas.ir import MotorControlIR


class MotorControlDiagnostic(BaseModel):
    """A plugin diagnostic; UNKNOWN/BLOCKED never become PASS."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str = Field(min_length=1, max_length=200)
    status: Literal["PASS", "FAIL", "UNKNOWN", "BLOCKED"]
    message: str = Field(min_length=1, max_length=2000)
    details: dict[str, object] = Field(default_factory=dict)


def _diagnostic(
    rule_id: str,
    status: Literal["PASS", "FAIL", "UNKNOWN", "BLOCKED"],
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


def validate_against_mcu_config(
    ir: MotorControlIR, mcu_config: MCUConfigIR | None
) -> tuple[MotorControlDiagnostic, ...]:
    """Compare domain requirements with realized Core configuration.

    This function deliberately reads MCUConfigIR and never creates or mutates a duplicate
    peripheral configuration. Missing inputs are reported as UNKNOWN or BLOCKED.
    """

    diagnostics: list[MotorControlDiagnostic] = []
    if mcu_config is None:
        for rule_id in (
            "COMPLEMENTARY_PWM",
            "DEADTIME_REQUIRED",
            "ADC_TRIGGER_ALIGNMENT",
            "MOTOR_REQUIREMENT_MCUCONFIG_MISMATCH",
        ):
            diagnostics.append(
                _diagnostic(rule_id, "UNKNOWN", "MCUConfigIR is required for cross-validation")
            )
        return tuple(diagnostics)

    pwm = _find_pwm(mcu_config, ir.mcu_config_refs.pwm)
    if pwm is None:
        diagnostics.append(
            _diagnostic(
                "MOTOR_REQUIREMENT_MCUCONFIG_MISMATCH",
                "FAIL",
                "MotorControl PWM reference does not resolve in MCUConfigIR",
                pwm_ref=ir.mcu_config_refs.pwm,
            )
        )
        return tuple(diagnostics)

    if ir.pwm_requirement.complementary_required:
        diagnostics.append(
            _diagnostic(
                "COMPLEMENTARY_PWM",
                "PASS" if pwm.complementary_channel else "FAIL",
                "Complementary PWM channel requirement checked",
                timer=pwm.timer,
                complementary_channel=pwm.complementary_channel,
            )
        )

    if ir.pwm_requirement.deadtime_required:
        deadtime_ok = (
            ir.pwm_requirement.deadtime is not None
            and pwm.deadtime is not None
            and _same_value(ir.pwm_requirement.deadtime, pwm.deadtime)
        )
        diagnostics.append(
            _diagnostic(
                "DEADTIME_REQUIRED",
                "PASS" if deadtime_ok else "FAIL",
                "PWM deadtime requirement checked against realized configuration",
                timer=pwm.timer,
            )
        )

    frequency_ok = ir.pwm_requirement.target_frequency is None or _same_value(
        ir.pwm_requirement.target_frequency, pwm.realized_frequency
    )
    diagnostics.append(
        _diagnostic(
            "MOTOR_REQUIREMENT_MCUCONFIG_MISMATCH",
            "PASS" if frequency_ok else "FAIL",
            "MotorControl PWM requirement checked against MCUConfigIR",
            timer=pwm.timer,
        )
    )

    adc_refs = ir.mcu_config_refs.adc
    if not adc_refs:
        diagnostics.append(
            _diagnostic(
                "ADC_TRIGGER_ALIGNMENT",
                "BLOCKED",
                "At least one MCUConfigIR ADC reference is required",
            )
        )
    else:
        adc = _find_adc(mcu_config, adc_refs[0])
        trigger_ok = adc is not None and (
            ir.adc_sampling_requirement.trigger_source_ref is None
            or adc.trigger_source == ir.adc_sampling_requirement.trigger_source_ref
        )
        diagnostics.append(
            _diagnostic(
                "ADC_TRIGGER_ALIGNMENT",
                "PASS" if trigger_ok else "FAIL",
                "ADC trigger requirement checked against MCUConfigIR",
                adc_ref=adc_refs[0],
            )
        )

    return tuple(diagnostics)


__all__ = ["MotorControlDiagnostic", "validate_against_mcu_config"]
