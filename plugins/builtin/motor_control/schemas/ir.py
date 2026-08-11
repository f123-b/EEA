"""Plugin-owned MotorControl IR.

The models in this module intentionally contain requirements and references. Realized timer,
PWM, ADC, DMA, and IRQ configuration remains owned by ``MCUConfigIR``; hardware facts remain
owned by ``HardwareIR``.
"""

from typing import Literal
from uuid import UUID, uuid4

from eea_core.claims import EngineeringValue
from pydantic import BaseModel, ConfigDict, Field, model_validator

MOTOR_CONTROL_SCHEMA_VERSION = "1.0.0"


class MotorControlConfiguration(BaseModel):
    """Project activation configuration for the bundled plugin."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    control_mode: Literal["FOC"] = "FOC"
    benchmark_profile: Literal["REFERENCE", "PRODUCTION"] = "REFERENCE"
    generation_profile: Literal["DECLARATIVE_ONLY"] = "DECLARATIVE_ONLY"


class MotorParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    poles: int | None = Field(default=None, ge=1)
    pole_pairs: int | None = Field(default=None, ge=1)
    rated_voltage: EngineeringValue | None = None
    rated_current: EngineeringValue | None = None
    rated_speed: EngineeringValue | None = None

    @model_validator(mode="after")
    def reject_inconsistent_pole_counts(self) -> "MotorParameters":
        if (
            self.poles is not None
            and self.pole_pairs is not None
            and self.poles != 2 * self.pole_pairs
        ):
            raise ValueError("poles must equal two times pole_pairs when both are supplied")
        return self


class PWMRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target_frequency: EngineeringValue | None = None
    center_aligned_required: bool = True
    complementary_required: bool = True
    deadtime_required: bool = True
    deadtime: EngineeringValue | None = None
    polarity: Literal["ACTIVE_HIGH", "ACTIVE_LOW"] | None = None
    break_input_required: bool = True


class ADCSamplingRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    current_channels: list[str] = Field(default_factory=list, max_length=16)
    trigger_source_ref: str | None = Field(default=None, max_length=200)
    sampling_window: EngineeringValue | None = None
    synchronized_to_pwm: bool = True
    dma_required: bool = True
    sample_to_actuation_latency: EngineeringValue | None = None


class MCUConfigReferences(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pwm: str | None = Field(default=None, max_length=200)
    adc: list[str] = Field(default_factory=list, max_length=16)
    dma: list[str] = Field(default_factory=list, max_length=16)
    irq: list[str] = Field(default_factory=list, max_length=16)


class ElectricalAngle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mechanical_direction: Literal["CW", "CCW"] | None = None
    electrical_angle_direction: Literal["POSITIVE", "NEGATIVE"] | None = None
    phase_sequence: str | None = Field(default=None, max_length=100)
    zero_offset: EngineeringValue | None = None


class SignConvention(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    positive_torque_current: Literal["POSITIVE_IQ", "NEGATIVE_IQ"] | None = None
    speed_feedback_sign: Literal["POSITIVE_FORWARD", "NEGATIVE_FORWARD"] | None = None
    encoder_direction: Literal["CW", "CCW"] | None = None
    park_convention: str | None = Field(default=None, max_length=100)
    svpwm_phase_mapping: str | None = Field(default=None, max_length=100)


class LoopRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    frequency: EngineeringValue | None = None
    kp: float | None = None
    ki: float | None = None
    output_limit: float | None = Field(default=None, ge=0)
    anti_windup: str | None = Field(default=None, max_length=100)
    decoupling: bool = False
    sample_to_actuation_latency: EngineeringValue | None = None
    cpu_budget: EngineeringValue | None = None


class StartupStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=100)
    prerequisites: list[str] = Field(default_factory=list, max_length=30)
    current_limit: EngineeringValue | None = None
    voltage_limit: EngineeringValue | None = None
    timeout: EngineeringValue | None = None
    failure_behavior: Literal["BLOCK", "SAFE_STATE", "RETRY", "LATCH"] = "BLOCK"


class StartupCalibration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    alignment_required: bool = True
    steps: list[StartupStep] = Field(default_factory=list, max_length=32)
    current_sensor_offset_required: bool = True
    encoder_zero_required: bool = True


class FaultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fault: Literal[
        "OVERCURRENT",
        "BUS_UNDERVOLTAGE",
        "BUS_OVERVOLTAGE",
        "DRIVER_FAULT",
        "ENCODER_LOSS",
        "OVERSPEED",
        "STALL",
        "CURRENT_SENSE_INVALID",
        "CONTROL_OVERRUN",
    ]
    action: Literal["DISABLE_PWM", "SAFE_STATE", "RETRY", "LATCH", "LOG"]
    retry_limit: int = Field(default=0, ge=0)


class FaultPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    responses: list[FaultResponse] = Field(default_factory=list, max_length=32)


class MotorControlIR(BaseModel):
    """Domain-owned control requirements and references for one project revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ir_id: UUID = Field(default_factory=uuid4)
    schema_version: Literal["1.0.0"] = "1.0.0"
    motor_ref: str | None = Field(default=None, max_length=200)
    motor_parameters: MotorParameters | None = None
    inverter_ref: str | None = Field(default=None, max_length=200)
    encoder_ref: str | None = Field(default=None, max_length=200)
    current_sense_ref: str | None = Field(default=None, max_length=200)
    pwm_requirement: PWMRequirement = Field(default_factory=PWMRequirement)
    adc_sampling_requirement: ADCSamplingRequirement = Field(default_factory=ADCSamplingRequirement)
    mcu_config_refs: MCUConfigReferences = Field(default_factory=MCUConfigReferences)
    electrical_angle: ElectricalAngle = Field(default_factory=ElectricalAngle)
    sign_convention: SignConvention = Field(default_factory=SignConvention)
    startup: StartupCalibration = Field(default_factory=StartupCalibration)
    current_loop: LoopRequirement | None = None
    velocity_loop: LoopRequirement | None = None
    position_loop: LoopRequirement | None = None
    limits: dict[str, EngineeringValue] = Field(default_factory=dict, max_length=32)
    fault_policy: FaultPolicy = Field(default_factory=FaultPolicy)


__all__ = [
    "MOTOR_CONTROL_SCHEMA_VERSION",
    "ADCSamplingRequirement",
    "ElectricalAngle",
    "FaultPolicy",
    "FaultResponse",
    "LoopRequirement",
    "MCUConfigReferences",
    "MotorControlConfiguration",
    "MotorControlIR",
    "MotorParameters",
    "PWMRequirement",
    "SignConvention",
    "StartupCalibration",
    "StartupStep",
]
