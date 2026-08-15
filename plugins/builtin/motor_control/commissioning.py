"""MotorControl-owned commissioning contributions.

These declarations add deterministic observations to the Core commissioning gate.  They do not
own permission, resource-lock, emergency-stop, or state-transition authority.
"""

from dataclasses import dataclass


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


__all__ = ["MOTOR_CONTROL_COMMISSIONING_RULES", "MotorControlCommissioningRule"]
