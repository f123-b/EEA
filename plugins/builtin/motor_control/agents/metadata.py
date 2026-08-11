"""MotorControlAgent declaration without an implicit LLM or hardware execution path."""

from pydantic import BaseModel, ConfigDict, Field


class MotorControlAgent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str = "org.eea.motor_control.agent"
    input_schema_ref: str = "plugin://org.eea.motor_control/schema/MotorControlIR/1.0.0"
    output_schema_ref: str = "plugin://org.eea.motor_control/schema/ValidationReport/1.0.0"
    allowed_tools: list[str] = Field(default_factory=list)
    required_knowledge_domains: list[str] = Field(
        default_factory=lambda: [
            "Motor Control",
            "Power Electronics",
            "Embedded Firmware Architecture",
        ]
    )
    prompt_version: str = "1.0.0"
    budget_profile: str = "motor-control-review"


__all__ = ["MotorControlAgent"]
