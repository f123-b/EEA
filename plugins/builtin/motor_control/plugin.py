"""Bundled MotorControl DomainPlugin implementation."""

from collections.abc import Sequence
from typing import Any

from eea_core.domain_extensions import (
    DomainContextContribution,
    DomainDescriptor,
    DomainGeneratorContribution,
    DomainRuleContribution,
    DomainUIContribution,
)
from eea_core.enums import DomainRulePhase, DomainTrustTier, Permission
from eea_ports.domain_extensions import DomainPlugin

from plugins.builtin.motor_control.agents import MotorControlAgent
from plugins.builtin.motor_control.context import MOTOR_CONTROL_CONTEXTS
from plugins.builtin.motor_control.generators import MOTOR_CONTROL_GENERATORS
from plugins.builtin.motor_control.rules import MOTOR_CONTROL_RULES
from plugins.builtin.motor_control.schemas.ir import (
    MOTOR_CONTROL_SCHEMA_VERSION,
    MotorControlIR,
)
from plugins.builtin.motor_control.ui import (
    MOTOR_CONTROL_CONFIGURATION_SCHEMA,
    MOTOR_CONTROL_UI_EXTENSIONS,
)


class MotorControlPlugin(DomainPlugin):
    """Official bundled plugin; it contributes declarations and pure validation only."""

    descriptor = DomainDescriptor(
        id="org.eea.motor_control",
        plugin_id="org.eea.motor_control",
        name="Motor Control",
        version="1.3.0",
        api_version="1",
        schema_version=MOTOR_CONTROL_SCHEMA_VERSION,
        trust_tier=DomainTrustTier.BUNDLED,
        entrypoint="plugins.builtin.motor_control.plugin:Plugin",
        capabilities=["motor_control.ir", "motor_control.review", "motor_control.codegen"],
        priority=100,
        rule_phases=[
            DomainRulePhase.PRE_GENERATION,
            DomainRulePhase.PRE_EXECUTION,
            DomainRulePhase.RELEASE_GATE,
        ],
        generator_phases=["PRE_GENERATION", "POST_GENERATION"],
        context_contributions=[item.context_id for item in MOTOR_CONTROL_CONTEXTS],
        ui_contributions=[item.extension_id for item in MOTOR_CONTROL_UI_EXTENSIONS],
        permissions=[Permission.READ, Permission.WRITE, Permission.BUILD],
    )
    agent = MotorControlAgent()
    ir_type = MotorControlIR

    def rules(self) -> Sequence[DomainRuleContribution]:
        return MOTOR_CONTROL_RULES

    def generators(self) -> Sequence[DomainGeneratorContribution]:
        return MOTOR_CONTROL_GENERATORS

    def contexts(self) -> Sequence[DomainContextContribution]:
        return MOTOR_CONTROL_CONTEXTS

    def ui_extensions(self) -> Sequence[DomainUIContribution]:
        return MOTOR_CONTROL_UI_EXTENSIONS

    def schema(self) -> dict[str, object]:
        return dict(MOTOR_CONTROL_CONFIGURATION_SCHEMA)

    def artifacts(self) -> Sequence[dict[str, Any]]:
        return (
            {
                "artifact_id": "org.eea.motor_control.ir",
                "kind": "DOMAIN_IR",
                "schema_ref": "plugin://org.eea.motor_control/schema/MotorControlIR/1.0.0",
                "schema_version": MOTOR_CONTROL_SCHEMA_VERSION,
                "ownership": "plugin",
            },
            {
                "artifact_id": "org.eea.motor_control.validation",
                "kind": "DOMAIN_VALIDATION_REPORT",
                "schema_ref": "plugin://org.eea.motor_control/schema/ValidationReport/1.0.0",
                "schema_version": "1.0.0",
                "ownership": "plugin",
            },
        )


Plugin = MotorControlPlugin


def build_motor_control_plugin() -> MotorControlPlugin:
    """Return a fresh bundled plugin instance for an application composition root."""

    return MotorControlPlugin()


__all__ = ["MotorControlPlugin", "Plugin", "build_motor_control_plugin"]
