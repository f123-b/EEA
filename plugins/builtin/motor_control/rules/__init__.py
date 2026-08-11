"""Deterministic MotorControl rule declarations and cross-validation."""

from plugins.builtin.motor_control.rules.catalog import MOTOR_CONTROL_RULES
from plugins.builtin.motor_control.rules.validation import (
    MotorControlDiagnostic,
    validate_against_mcu_config,
    validate_domain_context,
)

__all__ = [
    "MOTOR_CONTROL_RULES",
    "MotorControlDiagnostic",
    "validate_against_mcu_config",
    "validate_domain_context",
]
