"""Plugin-owned MotorControl configuration and IR schemas."""

from plugins.builtin.motor_control.schemas.ir import (
    ADCSamplingRequirement,
    CurrentLoopRequirement,
    ElectricalAngle,
    MotorControlConfiguration,
    MotorControlIR,
    PositionLoopRequirement,
    VelocityLoopRequirement,
)

__all__ = [
    "ADCSamplingRequirement",
    "CurrentLoopRequirement",
    "ElectricalAngle",
    "MotorControlConfiguration",
    "MotorControlIR",
    "PositionLoopRequirement",
    "VelocityLoopRequirement",
]
