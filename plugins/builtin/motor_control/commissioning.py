"""MotorControl-owned commissioning contributions.

These declarations add deterministic observations to the Core commissioning gate.  They do not
own permission, resource-lock, emergency-stop, or state-transition authority.
"""

from dataclasses import dataclass

from eea_core.domain_extensions import CommissioningRuleContribution


@dataclass(frozen=True, slots=True)
class MotorControlCommissioningRule:
    rule_id: str
    measurement: str
    safety_critical: bool = True


MOTOR_CONTROL_COMMISSIONING_RULES = (
    MotorControlCommissioningRule("motor.encoder.direction", "encoder_direction"),
    MotorControlCommissioningRule("motor.encoder.zero_wrap_plausibility", "encoder_plausibility"),
    MotorControlCommissioningRule("motor.electrical_angle.sign", "electrical_angle_sign"),
    MotorControlCommissioningRule("motor.phase_sequence", "phase_sequence"),
    MotorControlCommissioningRule("motor.current_sense.polarity_mapping", "current_sense"),
    MotorControlCommissioningRule("motor.adc.sampling_window", "adc_sampling_window"),
    MotorControlCommissioningRule("motor.pwm.polarity_deadtime_break", "pwm_output_safety"),
    MotorControlCommissioningRule("motor.speed_feedback.sign", "speed_feedback_sign"),
    MotorControlCommissioningRule("motor.loop.pi_saturation", "pi_saturation"),
    MotorControlCommissioningRule("motor.startup.alignment", "startup_alignment"),
    MotorControlCommissioningRule("motor.current_offset", "current_offset"),
    MotorControlCommissioningRule("motor.bus_voltage", "bus_voltage"),
    MotorControlCommissioningRule("motor.gate_driver.fault", "gate_driver_fault"),
    MotorControlCommissioningRule("motor.watchdog", "watchdog"),
    MotorControlCommissioningRule("motor.emergency_stop", "emergency_stop"),
)


def motor_control_commissioning_contributions() -> tuple[CommissioningRuleContribution, ...]:
    return tuple(
        CommissioningRuleContribution(
            rule_id=rule.rule_id,
            version="motor-control-m18dr-1",
            required_before_state="CLOSED_LOOP_LIMITED",
            measurement_key=rule.measurement,
            safety_critical=rule.safety_critical,
        )
        for rule in MOTOR_CONTROL_COMMISSIONING_RULES
    )


__all__ = [
    "MOTOR_CONTROL_COMMISSIONING_RULES",
    "MotorControlCommissioningRule",
    "motor_control_commissioning_contributions",
]
