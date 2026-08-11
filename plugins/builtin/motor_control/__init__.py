"""The bundled MotorControl Domain Plugin."""

from plugins.builtin.motor_control.plugin import (
    MotorControlPlugin,
    Plugin,
    build_motor_control_plugin,
)
from plugins.builtin.motor_control.rules.validation import (
    MotorControlDiagnostic,
    validate_against_mcu_config,
)
from plugins.builtin.motor_control.schemas.ir import (
    MotorControlConfiguration,
    MotorControlIR,
)

__all__ = [
    "MotorControlConfiguration",
    "MotorControlDiagnostic",
    "MotorControlIR",
    "MotorControlPlugin",
    "Plugin",
    "build_motor_control_plugin",
    "validate_against_mcu_config",
]
