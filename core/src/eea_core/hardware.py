"""Core-neutral hardware commissioning and safety contracts.

This module intentionally contains no concrete domain-plugin or adapter implementation.  It
owns the fail-closed state machine and the data required to prove that a bounded adapter
operated on the intended target under an immutable safety snapshot.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from eea_core.claims import EngineeringValue
from eea_core.entities import EntityBase, Sha256, utc_now
from eea_core.enums import EngineeringDimension, Permission


class CommissioningState(StrEnum):
    CREATED = "CREATED"
    PREFLIGHT = "PREFLIGHT"
    FLASHED_SAFE = "FLASHED_SAFE"
    SENSOR_CHECK = "SENSOR_CHECK"
    LOW_POWER = "LOW_POWER"
    CLOSED_LOOP_LIMITED = "CLOSED_LOOP_LIMITED"
    USER_APPROVAL = "USER_APPROVAL"
    NORMAL_OPERATION = "NORMAL_OPERATION"
    BLOCKED = "BLOCKED"
    ABORTED = "ABORTED"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    FAULTED = "FAULTED"
    ROLLBACK_REQUIRED = "ROLLBACK_REQUIRED"


class CommissioningStepStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    ABORTED = "ABORTED"


class EmergencyStopSource(StrEnum):
    USER = "USER"
    HARDWARE_FAULT = "HARDWARE_FAULT"
    WATCHDOG = "WATCHDOG"
    RULE_ENGINE = "RULE_ENGINE"
    SAFETY_MONITOR = "SAFETY_MONITOR"
    TOOL_ADAPTER = "TOOL_ADAPTER"
    AGENT_POLICY = "AGENT_POLICY"
    LOCK_LOSS = "LOCK_LOSS"
    TIMEOUT = "TIMEOUT"
    CANCELLATION = "CANCELLATION"


class EmergencyStopState(StrEnum):
    INACTIVE = "INACTIVE"
    REQUESTED = "REQUESTED"
    ACTIVE = "ACTIVE"
    UNKNOWN = "UNKNOWN"


class CapabilityVerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    SUPPORTED_UNVERIFIED = "SUPPORTED_UNVERIFIED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    UNKNOWN = "UNKNOWN"


class ResourceType(StrEnum):
    DEBUG_PROBE = "DebugProbe"
    SERIAL_PORT = "SerialPort"
    CAN_INTERFACE = "CANInterface"
    INSTRUMENT = "Instrument"
    SIMULATOR_INSTANCE = "SimulatorInstance"
    HARDWARE_TARGET = "HardwareTarget"


class ResourceLockStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"
    QUARANTINED = "QUARANTINED"


class HardwareIdentity(BaseModel):
    """Stable identity evidence; a port name alone is not sufficient."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    probe_serial: str | None = Field(default=None, max_length=200)
    target_identifier: str | None = Field(default=None, max_length=200)
    detected_mcu: str | None = Field(default=None, max_length=200)
    usb_vid_pid: str | None = Field(default=None, max_length=50)
    port_path: str | None = Field(default=None, max_length=500)
    board_revision: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def require_stable_identity(self) -> HardwareIdentity:
        if not any(
            value
            for value in (
                self.probe_serial,
                self.target_identifier,
                self.detected_mcu,
                self.usb_vid_pid,
            )
        ):
            raise ValueError("hardware identity requires at least one stable identifier")
        return self

    def has_commissioning_identity(self) -> bool:
        """Return whether the identity has the independent fields needed for hardware use."""

        return all(
            value
            for value in (
                self.probe_serial,
                self.target_identifier,
                self.detected_mcu,
                self.usb_vid_pid,
                self.port_path,
            )
        )


class ProbeIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    serial: str = Field(min_length=1, max_length=200)
    transport: str = Field(default="debug", min_length=1, max_length=50)
    port_path: str | None = Field(default=None, max_length=500)
    firmware_version: str | None = Field(default=None, max_length=100)


class SafeState(BaseModel):
    """A proof-shaped representation of the only acceptable default output state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pwm_disabled: bool = True
    actuator_disabled: bool = True
    torque_command_zero: bool = True
    gate_enable_disabled: bool = True
    relay_contactor_state: str = Field(default="OPEN", min_length=1, max_length=50)
    gpio_safe_outputs: dict[str, bool | int | str] = Field(default_factory=dict)
    brake_policy: str = Field(default="ENGAGED", min_length=1, max_length=100)
    watchdog_behavior: str = Field(default="TRIP_TO_SAFE_STATE", min_length=1, max_length=100)

    @model_validator(mode="after")
    def fail_closed(self) -> SafeState:
        if not self.pwm_disabled or not self.actuator_disabled:
            raise ValueError("SafeState cannot enable PWM or an actuator")
        if not self.torque_command_zero or not self.gate_enable_disabled:
            raise ValueError("SafeState must remove torque and gate enable")
        if self.relay_contactor_state.upper() in {"CLOSED", "ON", "UNKNOWN"}:
            raise ValueError("SafeState relay/contactor must be open or explicitly safe")
        return self


class TargetSafetyCapability(BaseModel):
    """Verifiable target-local safety support; UNKNOWN is never treated as safe."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    command_heartbeat_supported: bool = False
    command_heartbeat_timeout: EngineeringValue | None = None
    control_loop_watchdog_supported: bool = False
    control_loop_deadline: EngineeringValue | None = None
    local_current_trip_supported: bool = False
    local_voltage_trip_supported: bool = False
    local_overspeed_trip_supported: bool = False
    encoder_fault_trip_supported: bool = False
    gate_driver_fault_supported: bool = False
    timer_break_supported: bool = False
    hardware_enable_default_safe: bool = True
    physical_estop_supported: bool = False
    fault_latch_supported: bool = False
    requires_manual_rearm: bool = True
    verification_status: CapabilityVerificationStatus = CapabilityVerificationStatus.UNKNOWN


class HardwareTarget(EntityBase):
    """Core target declaration; adapters provide observations, never arbitrary commands."""

    project_id: UUID
    name: str = Field(min_length=1, max_length=200)
    identity: HardwareIdentity
    safe_state: SafeState = Field(default_factory=SafeState)
    safety_capability: TargetSafetyCapability = Field(default_factory=TargetSafetyCapability)
    safety_critical: bool = True


class DebugProbe(EntityBase):
    project_id: UUID
    name: str = Field(min_length=1, max_length=200)
    identity: ProbeIdentity


class ResourceLock(EntityBase):
    """The single lease contract used by hardware commissioning and other jobs."""

    project_id: UUID | None = None
    resource_type: ResourceType
    resource_id: str = Field(min_length=1, max_length=500)
    owner_job_id: UUID | None = None
    owner_session: UUID | None = None
    acquired_at: datetime = Field(default_factory=utc_now)
    heartbeat_at: datetime = Field(default_factory=utc_now)
    lease_expires_at: datetime
    status: ResourceLockStatus = ResourceLockStatus.ACTIVE

    def is_active(
        self,
        now: datetime | None = None,
        *,
        heartbeat_timeout: timedelta | None = None,
    ) -> bool:
        current = now or utc_now()
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        lease_expires = self.lease_expires_at
        if lease_expires.tzinfo is None:
            lease_expires = lease_expires.replace(tzinfo=UTC)
        heartbeat = self.heartbeat_at
        if heartbeat.tzinfo is None:
            heartbeat = heartbeat.replace(tzinfo=UTC)
        heartbeat_valid = heartbeat_timeout is None or heartbeat + heartbeat_timeout > current
        return (
            self.status is ResourceLockStatus.ACTIVE and lease_expires > current and heartbeat_valid
        )


def _ev(value: float, unit: str, dimension: EngineeringDimension) -> EngineeringValue:
    return EngineeringValue(unit=unit, dimension=dimension, nominal=value)


class SafetyLimit(BaseModel):
    """Structured, canonical-unit safety ceiling; all automated changes are tightening-only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_bus_voltage: EngineeringValue | None = None
    max_phase_current: EngineeringValue | None = None
    max_iq: EngineeringValue | None = None
    max_id: EngineeringValue | None = None
    max_speed: EngineeringValue | None = None
    max_position_delta: EngineeringValue | None = None
    max_duty_cycle: float | None = Field(default=None, ge=0, le=1)
    max_pwm_enable_duration: EngineeringValue | None = None
    max_temperature: EngineeringValue | None = None
    max_test_runtime: EngineeringValue | None = None
    watchdog_timeout: EngineeringValue | None = None
    current_ramp_rate: EngineeringValue | None = None
    speed_ramp_rate: EngineeringValue | None = None
    safe_brake_policy: str = Field(default="ENGAGED", min_length=1, max_length=100)
    safe_output_state: SafeState = Field(default_factory=SafeState)

    @classmethod
    def safe_commissioning(cls) -> SafetyLimit:
        return cls(
            max_bus_voltage=_ev(24, "V", EngineeringDimension.VOLTAGE),
            max_phase_current=_ev(1, "A", EngineeringDimension.CURRENT),
            max_iq=_ev(1, "A", EngineeringDimension.CURRENT),
            max_id=_ev(1, "A", EngineeringDimension.CURRENT),
            max_speed=_ev(100, "rpm", EngineeringDimension.ANGULAR_VELOCITY),
            max_position_delta=_ev(5, "deg", EngineeringDimension.ANGLE),
            max_duty_cycle=0.1,
            max_pwm_enable_duration=_ev(1, "s", EngineeringDimension.TIME),
            max_temperature=_ev(60, "C", EngineeringDimension.TEMPERATURE),
            max_test_runtime=_ev(10, "s", EngineeringDimension.TIME),
            watchdog_timeout=_ev(0.5, "s", EngineeringDimension.TIME),
            current_ramp_rate=_ev(1, "A", EngineeringDimension.CURRENT),
            speed_ramp_rate=_ev(100, "rpm", EngineeringDimension.ANGULAR_VELOCITY),
        )

    def complete_for_actuator(self) -> bool:
        return all(
            getattr(self, name) is not None
            for name in (
                "max_bus_voltage",
                "max_phase_current",
                "max_iq",
                "max_id",
                "max_speed",
                "max_duty_cycle",
                "max_pwm_enable_duration",
                "max_temperature",
                "max_test_runtime",
                "watchdog_timeout",
                "current_ramp_rate",
                "speed_ramp_rate",
            )
        )

    def is_equal_or_more_conservative_than(self, baseline: SafetyLimit) -> bool:
        for name in (
            "max_bus_voltage",
            "max_phase_current",
            "max_iq",
            "max_id",
            "max_speed",
            "max_position_delta",
            "max_pwm_enable_duration",
            "max_temperature",
            "max_test_runtime",
            "watchdog_timeout",
            "current_ramp_rate",
            "speed_ramp_rate",
        ):
            old = getattr(baseline, name)
            new = getattr(self, name)
            if old is not None:
                if new is None or new.dimension is not old.dimension:
                    return False
                if new.require_normalized_nominal() > old.require_normalized_nominal() + 1e-12:
                    return False
        if baseline.max_duty_cycle is not None and (
            self.max_duty_cycle is None or self.max_duty_cycle > baseline.max_duty_cycle + 1e-12
        ):
            return False
        return self.safe_brake_policy == baseline.safe_brake_policy and (
            self.safe_output_state == baseline.safe_output_state
        )


class CommissioningProfile(EntityBase):
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=50)
    applicable_target_types: list[str] = Field(default_factory=list)
    applicable_domains: list[str] = Field(default_factory=list)
    required_steps: list[str] = Field(default_factory=list)
    required_permissions: list[Permission] = Field(default_factory=list)
    user_approval_required: bool = True
    safety_limits: SafetyLimit
    required_safety_capabilities: list[str] = Field(default_factory=list)
    watchdog_policy: dict[str, object] = Field(default_factory=dict)
    emergency_stop_policy: dict[str, object] = Field(default_factory=dict)
    safe_state_policy: SafeState = Field(default_factory=SafeState)

    @classmethod
    def safe_commissioning(cls) -> CommissioningProfile:
        return cls(
            name="SAFE_COMMISSIONING",
            version="1.0",
            required_steps=["SENSOR_CHECK", "LOW_POWER", "CLOSED_LOOP_LIMITED"],
            required_permissions=[
                Permission.FLASH,
                Permission.DEBUG,
                Permission.HARDWARE_CONTROL,
            ],
            safety_limits=SafetyLimit.safe_commissioning(),
            required_safety_capabilities=[
                "command_heartbeat_supported",
                "control_loop_watchdog_supported",
                "hardware_enable_default_safe",
                "fault_latch_supported",
            ],
            watchdog_policy={
                "armed_before_actuator": True,
                "loss_action": "SAFE_STATE",
                "lock_heartbeat_timeout_seconds": 30.0,
            },
            emergency_stop_policy={"manual_rearm": True, "auto_resume": False},
        )


class WatchdogState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    armed: bool = False
    heartbeat_at: datetime | None = None
    timeout: EngineeringValue | None = None
    expected_safe_action: str = "SAFE_STATE"
    last_observed_status: str = "UNKNOWN"


class CommissioningStepResult(EntityBase):
    session_id: UUID
    step_id: str = Field(min_length=1, max_length=100)
    status: CommissioningStepStatus = CommissioningStepStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    measurements: dict[str, object] = Field(default_factory=dict)
    thresholds: dict[str, object] = Field(default_factory=dict)
    evidence_ids: list[UUID] = Field(default_factory=list)
    tool_version: str = "unknown"
    rule_version: str = "core-m18d-1"
    operator: str = Field(default="system", min_length=1, max_length=200)
    failure_reason: str | None = None


class HardwareCommissioningSession(EntityBase):
    project_id: UUID
    target_id: str = Field(min_length=1, max_length=500)
    firmware_artifact_id: UUID
    firmware_hash: Sha256
    build_run_id: UUID | None = None
    source_revision_id: UUID | None = None
    build_input_snapshot_id: UUID | None = None
    hardware_identity: HardwareIdentity
    probe_identity: ProbeIdentity
    board_revision: str | None = Field(default=None, max_length=100)
    commissioning_profile_id: UUID
    state: CommissioningState = CommissioningState.CREATED
    current_step: str | None = None
    started_by: str = Field(min_length=1, max_length=200)
    approved_by: str | None = Field(default=None, max_length=200)
    safety_limits_snapshot: SafetyLimit
    preflight_results: list[dict[str, object]] = Field(default_factory=list)
    step_results: list[CommissioningStepResult] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    emergency_stop_state: EmergencyStopState = EmergencyStopState.INACTIVE
    watchdog_state: WatchdogState = Field(default_factory=WatchdogState)
    resource_lock_ids: list[UUID] = Field(default_factory=list)
    permission_token_ids: list[str] = Field(default_factory=list)
    approval_snapshot: dict[str, object] | None = None
    completed_at: datetime | None = None
    aborted_at: datetime | None = None
    active_action_id: UUID | None = None
    active_action_kind: str | None = None
    active_action_started_at: datetime | None = None
    active_action_expected_revision: int | None = None
    active_action_request_hash: Sha256 | None = None
    active_action_journal_id: UUID | None = None

    def transition(self, target: CommissioningState) -> None:
        allowed: dict[CommissioningState, set[CommissioningState]] = {
            CommissioningState.CREATED: {CommissioningState.PREFLIGHT},
            CommissioningState.PREFLIGHT: {CommissioningState.FLASHED_SAFE},
            CommissioningState.FLASHED_SAFE: {CommissioningState.SENSOR_CHECK},
            CommissioningState.SENSOR_CHECK: {CommissioningState.LOW_POWER},
            CommissioningState.LOW_POWER: {CommissioningState.CLOSED_LOOP_LIMITED},
            CommissioningState.CLOSED_LOOP_LIMITED: {CommissioningState.USER_APPROVAL},
            CommissioningState.USER_APPROVAL: {CommissioningState.NORMAL_OPERATION},
            CommissioningState.NORMAL_OPERATION: set(),
            CommissioningState.BLOCKED: set(),
            CommissioningState.ABORTED: set(),
            CommissioningState.EMERGENCY_STOP: set(),
            CommissioningState.FAULTED: set(),
            CommissioningState.ROLLBACK_REQUIRED: set(),
        }
        exceptional = {
            CommissioningState.BLOCKED,
            CommissioningState.ABORTED,
            CommissioningState.EMERGENCY_STOP,
            CommissioningState.FAULTED,
            CommissioningState.ROLLBACK_REQUIRED,
        }
        emergency_stop_allowed = (
            target is CommissioningState.EMERGENCY_STOP
            and self.state is not CommissioningState.EMERGENCY_STOP
        )
        exceptional_allowed = (
            target in exceptional
            and target is not CommissioningState.EMERGENCY_STOP
            and self.state
            not in {CommissioningState.NORMAL_OPERATION, CommissioningState.EMERGENCY_STOP}
        )
        if (
            target not in allowed[self.state]
            and not emergency_stop_allowed
            and not exceptional_allowed
        ):
            raise ValueError(f"illegal commissioning transition {self.state} -> {target}")
        self.state = target
        self.revision += 1
        self.updated_at = utc_now()


class EmergencyStopEvent(EntityBase):
    session_id: UUID
    source: EmergencyStopSource
    reason: str = Field(min_length=1, max_length=4000)
    safe_state_attempted: bool = False
    safe_state_verified: bool = False
    quarantined_resource_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    idempotency_key: str = Field(min_length=1, max_length=300)
    actor: str = Field(min_length=1, max_length=200)


class HardwareAdapterResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    measurements: dict[str, object] = Field(default_factory=dict)
    raw_result_ref: str | None = None
    failure_reason: str | None = None
    safe_state_verified: bool | None = None


class HardwareActionIntent(BaseModel):
    """Durable claim returned before a hardware side effect is allowed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action_id: UUID
    session_id: UUID
    action: str = Field(min_length=1, max_length=100)
    expected_revision: int = Field(ge=1)
    claimed_revision: int = Field(ge=1)
    request_hash: Sha256
    event_id: UUID
    journal_id: UUID
    started_at: datetime


class HardwareCommissioningAdapter(Protocol):
    name: str
    version: str

    def identify_target(self) -> HardwareIdentity: ...

    def verify_probe(self, expected: ProbeIdentity) -> HardwareAdapterResult: ...

    def flash(self, firmware_hash: str) -> HardwareAdapterResult: ...

    def verify_flash(self, firmware_hash: str) -> HardwareAdapterResult: ...

    def reset_to_safe_state(self) -> HardwareAdapterResult: ...

    def enter_safe_state(self) -> HardwareAdapterResult: ...

    def read_fault_state(self) -> HardwareAdapterResult: ...

    def sensor_sanity_check(self) -> HardwareAdapterResult: ...

    def watchdog_status(self) -> HardwareAdapterResult: ...

    def emergency_stop(self) -> HardwareAdapterResult: ...

    def execute_limited_step(self, step_id: str, limits: SafetyLimit) -> HardwareAdapterResult: ...


__all__ = [
    "CapabilityVerificationStatus",
    "CommissioningProfile",
    "CommissioningState",
    "CommissioningStepResult",
    "CommissioningStepStatus",
    "DebugProbe",
    "EmergencyStopEvent",
    "EmergencyStopSource",
    "EmergencyStopState",
    "HardwareActionIntent",
    "HardwareAdapterResult",
    "HardwareCommissioningAdapter",
    "HardwareCommissioningSession",
    "HardwareIdentity",
    "HardwareTarget",
    "ProbeIdentity",
    "ResourceLock",
    "ResourceLockStatus",
    "ResourceType",
    "SafeState",
    "SafetyLimit",
    "TargetSafetyCapability",
    "WatchdogState",
]
