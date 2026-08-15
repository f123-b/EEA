"""Deterministic fake hardware adapter used by the M18D safety tests.

The fake deliberately exposes only the bounded commissioning contract.  There is no generic
shell command, PWM setter, or arbitrary motor command in this adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from eea_core.hardware import (
    HardwareAdapterResult,
    HardwareCommissioningAdapter,
    HardwareIdentity,
    ProbeIdentity,
    SafetyLimit,
)


@dataclass
class FakeHardwareCommissioningAdapter(HardwareCommissioningAdapter):
    identity: HardwareIdentity
    probe: ProbeIdentity
    failures: set[str] = field(default_factory=set)
    measurements: dict[str, dict[str, object]] = field(default_factory=dict)
    name: str = "fake-hardware-commissioning"
    version: str = "1.0"
    pwm_enabled: bool = False
    actuator_enabled: bool = False
    last_flash_hash: str | None = None
    safe_state_calls: int = 0
    emergency_stop_calls: int = 0

    def _result(
        self, operation: str, *, measurements: dict[str, object] | None = None
    ) -> HardwareAdapterResult:
        if operation in self.failures:
            return HardwareAdapterResult(
                ok=False,
                failure_reason=f"injected adapter failure: {operation}",
                measurements=measurements or {},
            )
        return HardwareAdapterResult(ok=True, measurements=measurements or {})

    def identify_target(self) -> HardwareIdentity:
        if "identity" in self.failures:
            return HardwareIdentity(target_identifier="mismatch")
        return self.identity

    def verify_probe(self, expected: ProbeIdentity) -> HardwareAdapterResult:
        if "probe_identity" in self.failures or self.probe != expected:
            return HardwareAdapterResult(ok=False, failure_reason="probe identity mismatch")
        return self._result("verify_probe", measurements={"serial": self.probe.serial})

    def flash(self, firmware_hash: str) -> HardwareAdapterResult:
        result = self._result("flash")
        if result.ok:
            self.last_flash_hash = firmware_hash
            # Flash never enables output.  This is an invariant of the fake as well as the
            # real port contract.
            self.pwm_enabled = False
            self.actuator_enabled = False
        return result

    def verify_flash(self, firmware_hash: str) -> HardwareAdapterResult:
        if "verify_flash" in self.failures or self.last_flash_hash != firmware_hash:
            return HardwareAdapterResult(ok=False, failure_reason="flashed firmware hash mismatch")
        return self._result("verify_flash", measurements={"firmware_hash": firmware_hash})

    def reset_to_safe_state(self) -> HardwareAdapterResult:
        self.safe_state_calls += 1
        result = self._result("reset_to_safe_state")
        if result.ok:
            self.pwm_enabled = False
            self.actuator_enabled = False
            result = result.model_copy(update={"safe_state_verified": True})
        return result

    def enter_safe_state(self) -> HardwareAdapterResult:
        self.safe_state_calls += 1
        result = self._result("safe_state")
        if result.ok:
            self.pwm_enabled = False
            self.actuator_enabled = False
            result = result.model_copy(update={"safe_state_verified": True})
        return result

    def read_fault_state(self) -> HardwareAdapterResult:
        return self._result("fault_state", measurements=self.measurements.get("fault_state", {}))

    def sensor_sanity_check(self) -> HardwareAdapterResult:
        return self._result("sensor", measurements=self.measurements.get("sensor", {}))

    def watchdog_status(self) -> HardwareAdapterResult:
        if "watchdog" in self.failures or "watchdog_timeout" in self.failures:
            return HardwareAdapterResult(ok=False, failure_reason="watchdog is not armed")
        return self._result("watchdog", measurements={"armed": True, "status": "OK"})

    def emergency_stop(self) -> HardwareAdapterResult:
        self.emergency_stop_calls += 1
        result = self._result("emergency_stop")
        if result.ok:
            self.pwm_enabled = False
            self.actuator_enabled = False
            result = result.model_copy(update={"safe_state_verified": True})
        return result

    def execute_limited_step(self, step_id: str, limits: SafetyLimit) -> HardwareAdapterResult:
        operation = step_id.lower()
        if "overcurrent" in self.failures and step_id == "LOW_POWER":
            return HardwareAdapterResult(
                ok=True,
                measurements={
                    "phase_current": limits.max_phase_current.require_normalized_nominal() * 2
                }
                if limits.max_phase_current
                else {"phase_current": 2.0},
            )
        if "overspeed" in self.failures and step_id == "CLOSED_LOOP_LIMITED":
            return HardwareAdapterResult(
                ok=True,
                measurements={"speed": limits.max_speed.require_normalized_nominal() * 2}
                if limits.max_speed
                else {"speed": 2.0},
            )
        default_measurements: dict[str, object] = {}
        if step_id == "LOW_POWER":
            default_measurements = {"phase_current": 0.1, "duty_cycle": 0.05}
        elif step_id == "CLOSED_LOOP_LIMITED":
            default_measurements = {"phase_current": 0.1, "speed": 0.5, "duty_cycle": 0.05}
        result = self._result(
            operation,
            measurements=self.measurements.get(step_id, default_measurements),
        )
        if not result.ok:
            return result
        return result


__all__ = ["FakeHardwareCommissioningAdapter"]
