"""Local-route UI metadata; no remote JavaScript or executable renderer payloads."""

from eea_core.domain_extensions import DomainUIContribution

from plugins.builtin.motor_control.schemas.ir import MotorControlConfiguration

MOTOR_CONTROL_CONFIGURATION_SCHEMA: dict[str, object] = {
    "$id": "plugin://org.eea.motor_control/schema/configuration/1.0.0",
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    **MotorControlConfiguration.model_json_schema(),
}

MOTOR_CONTROL_UI_EXTENSIONS: tuple[DomainUIContribution, ...] = (
    DomainUIContribution(
        extension_id="org.eea.motor_control.navigation",
        kind="navigation",
        label="Motor Control",
        route="/projects/{project_id}/motor-control",
    ),
    DomainUIContribution(
        extension_id="org.eea.motor_control.configuration",
        kind="form",
        label="Motor Control Configuration",
        route="/projects/{project_id}/domains/org.eea.motor_control/configuration",
        schema=MOTOR_CONTROL_CONFIGURATION_SCHEMA,
    ),
    DomainUIContribution(
        extension_id="org.eea.motor_control.validate",
        kind="action",
        label="Validate Motor Control",
        route="/projects/{project_id}/domains/org.eea.motor_control/validate",
        action="domain.validate",
    ),
)

__all__ = ["MOTOR_CONTROL_CONFIGURATION_SCHEMA", "MOTOR_CONTROL_UI_EXTENSIONS"]
