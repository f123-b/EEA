"""Plugin-owned MotorControl IR.

The models in this module intentionally contain requirements and references. Realized timer,
PWM, ADC, DMA, and IRQ configuration remains owned by ``MCUConfigIR``; hardware facts remain
owned by ``HardwareIR``.
"""

from typing import Literal
from uuid import UUID, uuid4

from eea_core.claims import EngineeringValue
from eea_core.enums import EngineeringDimension
from pydantic import BaseModel, ConfigDict, Field, model_validator

MOTOR_CONTROL_SCHEMA_VERSION = "1.0.0"


def _require_dimension(
    value: EngineeringValue | None, expected: EngineeringDimension, field_name: str
) -> None:
    if value is not None and value.dimension is not expected:
        raise ValueError(f"{field_name} must use engineering dimension {expected.value}")


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
        _require_dimension(self.rated_voltage, EngineeringDimension.VOLTAGE, "rated_voltage")
        _require_dimension(self.rated_current, EngineeringDimension.CURRENT, "rated_current")
        _require_dimension(self.rated_speed, EngineeringDimension.ANGULAR_VELOCITY, "rated_speed")
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

    @model_validator(mode="after")
    def validate_dimensions(self) -> "PWMRequirement":
        _require_dimension(
            self.target_frequency,
            EngineeringDimension.FREQUENCY,
            "pwm_requirement.target_frequency",
        )
        _require_dimension(self.deadtime, EngineeringDimension.TIME, "pwm_requirement.deadtime")
        return self


class ADCSamplingRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    current_channels: list[str] = Field(default_factory=list, max_length=16)
    trigger_source_ref: str | None = Field(default=None, max_length=200)
    sampling_window: EngineeringValue | None = None
    synchronized_to_pwm: bool = True
    dma_required: bool = True
    sample_to_actuation_latency: EngineeringValue | None = None

    @model_validator(mode="after")
    def validate_dimensions(self) -> "ADCSamplingRequirement":
        _require_dimension(
            self.sampling_window,
            EngineeringDimension.TIME,
            "adc_sampling_requirement.sampling_window",
        )
        _require_dimension(
            self.sample_to_actuation_latency,
            EngineeringDimension.TIME,
            "adc_sampling_requirement.sample_to_actuation_latency",
        )
        return self


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

    @model_validator(mode="after")
    def validate_dimensions(self) -> "ElectricalAngle":
        _require_dimension(
            self.zero_offset, EngineeringDimension.ANGLE, "electrical_angle.zero_offset"
        )
        return self


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
    period: EngineeringValue | None = None
    kp: float | None = None
    ki: float | None = None
    output_limit: float | None = Field(default=None, ge=0)
    anti_windup: str | None = Field(default=None, max_length=100)
    decoupling: bool = False
    sample_to_actuation_latency: EngineeringValue | None = None
    cpu_budget: EngineeringValue | None = None

    @model_validator(mode="after")
    def validate_dimensions(self) -> "LoopRequirement":
        _require_dimension(self.frequency, EngineeringDimension.FREQUENCY, "loop.frequency")
        _require_dimension(self.period, EngineeringDimension.TIME, "loop.period")
        _require_dimension(
            self.sample_to_actuation_latency,
            EngineeringDimension.TIME,
            "loop.sample_to_actuation_latency",
        )
        _require_dimension(self.cpu_budget, EngineeringDimension.TIME, "loop.cpu_budget")
        return self


class CurrentLoopRequirement(LoopRequirement):
    """Current-loop semantics frozen by the MotorControl Domain specification."""

    id_target: EngineeringValue | None = None
    iq_target: EngineeringValue | None = None

    @model_validator(mode="after")
    def validate_current_dimensions(self) -> "CurrentLoopRequirement":
        _require_dimension(self.id_target, EngineeringDimension.CURRENT, "current_loop.id_target")
        _require_dimension(self.iq_target, EngineeringDimension.CURRENT, "current_loop.iq_target")
        return self


class VelocityLoopRequirement(LoopRequirement):
    """Velocity-loop limits and feedback semantics frozen by the Domain specification."""

    speed_limit: EngineeringValue | None = None
    acceleration_limit: EngineeringValue | None = None
    current_limit: EngineeringValue | None = None
    feedback_source: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_velocity_dimensions(self) -> "VelocityLoopRequirement":
        _require_dimension(
            self.speed_limit, EngineeringDimension.ANGULAR_VELOCITY, "velocity_loop.speed_limit"
        )
        _require_dimension(
            self.acceleration_limit,
            EngineeringDimension.ANGULAR_ACCELERATION,
            "velocity_loop.acceleration_limit",
        )
        _require_dimension(
            self.current_limit, EngineeringDimension.CURRENT, "velocity_loop.current_limit"
        )
        return self


class PositionLoopRequirement(LoopRequirement):
    """Position-loop controller and wrap/limit semantics frozen by the Domain specification."""

    controller: str | None = Field(default=None, max_length=100)
    wrap_handling: Literal["NONE", "MODULO", "CONTINUOUS"] = "NONE"
    position_limit: EngineeringValue | None = None
    velocity_limit: EngineeringValue | None = None

    @model_validator(mode="after")
    def validate_position_dimensions(self) -> "PositionLoopRequirement":
        _require_dimension(
            self.position_limit, EngineeringDimension.ANGLE, "position_loop.position_limit"
        )
        _require_dimension(
            self.velocity_limit,
            EngineeringDimension.ANGULAR_VELOCITY,
            "position_loop.velocity_limit",
        )
        return self


class StartupStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=100)
    prerequisites: list[str] = Field(default_factory=list, max_length=30)
    current_limit: EngineeringValue | None = None
    voltage_limit: EngineeringValue | None = None
    timeout: EngineeringValue | None = None
    failure_behavior: Literal["BLOCK", "SAFE_STATE", "RETRY", "LATCH"] = "BLOCK"

    @model_validator(mode="after")
    def validate_dimensions(self) -> "StartupStep":
        _require_dimension(
            self.current_limit, EngineeringDimension.CURRENT, "startup.current_limit"
        )
        _require_dimension(
            self.voltage_limit, EngineeringDimension.VOLTAGE, "startup.voltage_limit"
        )
        _require_dimension(self.timeout, EngineeringDimension.TIME, "startup.timeout")
        return self


class StartupCalibration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    alignment_required: bool = True
    steps: list[StartupStep] = Field(default_factory=list, max_length=32)
    current_sensor_offset_required: bool = True
    encoder_zero_required: bool = True
    test_result: Literal["PASS", "FAIL", "UNKNOWN", "BLOCKED"] | None = None


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
    current_loop: CurrentLoopRequirement | None = None
    velocity_loop: VelocityLoopRequirement | None = None
    position_loop: PositionLoopRequirement | None = None
    limits: dict[str, EngineeringValue] = Field(default_factory=dict, max_length=32)
    fault_policy: FaultPolicy = Field(default_factory=FaultPolicy)

    @model_validator(mode="after")
    def validate_limit_dimensions(self) -> "MotorControlIR":
        expected = {
            "rated_voltage": EngineeringDimension.VOLTAGE,
            "bus_voltage": EngineeringDimension.VOLTAGE,
            "rated_current": EngineeringDimension.CURRENT,
            "current_limit": EngineeringDimension.CURRENT,
            "rated_speed": EngineeringDimension.ANGULAR_VELOCITY,
            "speed_limit": EngineeringDimension.ANGULAR_VELOCITY,
            "acceleration_limit": EngineeringDimension.ANGULAR_ACCELERATION,
            "position_limit": EngineeringDimension.ANGLE,
            "pwm_frequency": EngineeringDimension.FREQUENCY,
            "deadtime": EngineeringDimension.TIME,
            "sampling_window": EngineeringDimension.TIME,
            "latency": EngineeringDimension.TIME,
            "zero_offset": EngineeringDimension.ANGLE,
        }
        for name, value in self.limits.items():
            required = expected.get(name)
            if required is None:
                raise ValueError(f"limits.{name} has no declared engineering dimension")
            _require_dimension(value, required, f"limits.{name}")
        return self


__all__ = [
    "MOTOR_CONTROL_SCHEMA_VERSION",
    "ADCSamplingRequirement",
    "CurrentLoopRequirement",
    "ElectricalAngle",
    "FaultPolicy",
    "FaultResponse",
    "LoopRequirement",
    "MCUConfigReferences",
    "MotorControlConfiguration",
    "MotorControlIR",
    "MotorParameters",
    "PWMRequirement",
    "PositionLoopRequirement",
    "SignConvention",
    "StartupCalibration",
    "StartupStep",
    "VelocityLoopRequirement",
]
