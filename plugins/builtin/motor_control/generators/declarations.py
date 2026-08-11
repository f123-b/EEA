"""Deterministic generator declarations; no hardware side effects are performed here."""

from eea_core.domain_extensions import DomainGeneratorContribution

MOTOR_CONTROL_GENERATORS: tuple[DomainGeneratorContribution, ...] = (
    DomainGeneratorContribution(
        generator_id="motor_control.ir.contract",
        version="1.0.0",
        consumes=["DomainIREnvelope", "HardwareIR", "MCUConfigIR"],
        produces=["motor_control.ir.contract"],
        deterministic=True,
        side_effects=False,
    ),
    DomainGeneratorContribution(
        generator_id="motor_control.validation.report",
        version="1.0.0",
        consumes=["motor_control.ir.contract", "MCUConfigIR"],
        produces=["motor_control.validation.report"],
        after=["motor_control.ir.contract"],
        deterministic=True,
        side_effects=False,
    ),
)

__all__ = ["MOTOR_CONTROL_GENERATORS"]
