"""Stable additive MotorControl rule contributions."""

from eea_core.domain_extensions import DomainRuleContribution
from eea_core.enums import DomainRulePhase, IssueSeverity

MOTOR_CONTROL_RULES: tuple[DomainRuleContribution, ...] = (
    DomainRuleContribution(
        rule_id="COMPLEMENTARY_PWM",
        rule_version="1.0.0",
        phase=DomainRulePhase.PRE_GENERATION,
        inputs=["MotorControlIR.pwm_requirement", "MCUConfigIR.peripherals[].pwm"],
        severity=IssueSeverity.HIGH,
        priority=100,
    ),
    DomainRuleContribution(
        rule_id="DEADTIME_REQUIRED",
        rule_version="1.0.0",
        phase=DomainRulePhase.PRE_GENERATION,
        inputs=["MotorControlIR.pwm_requirement.deadtime", "MCUConfigIR.peripherals[].pwm"],
        severity=IssueSeverity.CRITICAL,
        priority=100,
    ),
    DomainRuleContribution(
        rule_id="CURRENT_SENSE_ADC_RANGE",
        rule_version="1.0.0",
        phase=DomainRulePhase.PRE_GENERATION,
        inputs=["MotorControlIR.current_sense_ref", "MCUConfigIR.peripherals[].adc"],
        severity=IssueSeverity.HIGH,
        priority=90,
    ),
    DomainRuleContribution(
        rule_id="ADC_TRIGGER_ALIGNMENT",
        rule_version="1.0.0",
        phase=DomainRulePhase.PRE_GENERATION,
        inputs=["MotorControlIR.adc_sampling_requirement", "MCUConfigIR.peripherals[].adc"],
        severity=IssueSeverity.HIGH,
        priority=90,
    ),
    DomainRuleContribution(
        rule_id="CURRENT_LOOP_TIMING_BUDGET",
        rule_version="1.0.0",
        phase=DomainRulePhase.RELEASE_GATE,
        inputs=["MotorControlIR.current_loop", "MCUConfigIR"],
        severity=IssueSeverity.CRITICAL,
        priority=100,
    ),
    DomainRuleContribution(
        rule_id="SIGN_CONVENTION_COMPLETE",
        rule_version="1.0.0",
        phase=DomainRulePhase.RELEASE_GATE,
        inputs=["MotorControlIR.sign_convention", "MotorControlIR.electrical_angle"],
        severity=IssueSeverity.CRITICAL,
        priority=100,
    ),
    DomainRuleContribution(
        rule_id="SPEED_FEEDBACK_SIGN_CONSISTENT",
        rule_version="1.0.0",
        phase=DomainRulePhase.RELEASE_GATE,
        inputs=["MotorControlIR.sign_convention.speed_feedback_sign", "MotorControlIR.encoder_ref"],
        severity=IssueSeverity.HIGH,
        priority=90,
    ),
    DomainRuleContribution(
        rule_id="ELECTRICAL_ANGLE_DIRECTION_CONSISTENT",
        rule_version="1.0.0",
        phase=DomainRulePhase.RELEASE_GATE,
        inputs=["MotorControlIR.electrical_angle", "MotorControlIR.sign_convention"],
        severity=IssueSeverity.HIGH,
        priority=90,
    ),
    DomainRuleContribution(
        rule_id="PI_OUTPUT_SATURATION_LIMIT",
        rule_version="1.0.0",
        phase=DomainRulePhase.RELEASE_GATE,
        inputs=["MotorControlIR.current_loop", "MotorControlIR.velocity_loop"],
        severity=IssueSeverity.HIGH,
        priority=90,
    ),
    DomainRuleContribution(
        rule_id="STARTUP_ALIGNMENT_REQUIRED",
        rule_version="1.0.0",
        phase=DomainRulePhase.PRE_EXECUTION,
        inputs=["MotorControlIR.startup", "MotorControlIR.encoder_ref"],
        severity=IssueSeverity.CRITICAL,
        priority=100,
    ),
    DomainRuleContribution(
        rule_id="MOTOR_REQUIREMENT_MCUCONFIG_MISMATCH",
        rule_version="1.0.0",
        phase=DomainRulePhase.PRE_GENERATION,
        inputs=[
            "MotorControlIR.pwm_requirement",
            "MotorControlIR.adc_sampling_requirement",
            "MCUConfigIR",
        ],
        severity=IssueSeverity.CRITICAL,
        priority=100,
    ),
)

__all__ = ["MOTOR_CONTROL_RULES"]
