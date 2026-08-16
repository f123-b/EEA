"""The bundled MotorControl Domain Plugin."""

from plugins.builtin.motor_control.commissioning import (
    MOTOR_CONTROL_COMMISSIONING_RULES,
    MotorControlCommissioningRule,
)
from plugins.builtin.motor_control.plugin import (
    MotorControlPlugin,
    Plugin,
    build_motor_control_plugin,
)
from plugins.builtin.motor_control.rules.validation import (
    MotorControlDiagnostic,
    validate_against_mcu_config,
    validate_domain_context,
)
from plugins.builtin.motor_control.schemas.ir import (
    MotorControlConfiguration,
    MotorControlIR,
)

__all__ = [
    "MOTOR_CONTROL_COMMISSIONING_RULES",
    "MotorControlCommissioningRule",
    "MotorControlConfiguration",
    "MotorControlDiagnostic",
    "MotorControlIR",
    "MotorControlPlugin",
    "Plugin",
    "build_motor_control_plugin",
    "validate_against_mcu_config",
    "validate_domain_context",
]
