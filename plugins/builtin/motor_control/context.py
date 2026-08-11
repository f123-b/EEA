"""Namespaced context contribution metadata for MotorControl reasoning."""

from eea_core.domain_extensions import DomainContextContribution

MOTOR_CONTROL_CONTEXTS: tuple[DomainContextContribution, ...] = (
    DomainContextContribution(
        context_id="org.eea.motor_control.context",
        keys=[
            "motor_control_ir",
            "mcu_config_refs",
            "hardware_refs",
            "sign_convention",
            "fault_policy",
        ],
        description=(
            "MotorControl requirements and references, with Core IR facts resolved by the caller"
        ),
    ),
)

__all__ = ["MOTOR_CONTROL_CONTEXTS"]
