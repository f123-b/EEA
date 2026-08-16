"""Application service for the fail-closed hardware commissioning workflow."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from typing import Protocol, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from eea_core.claims import EngineeringValue
from eea_core.domain_extensions import CommissioningRuleContribution
from eea_core.entities import Evidence, utc_now
from eea_core.enums import EngineeringErrorCode, EvidenceType, Permission
from eea_core.errors import EngineeringError
from eea_core.hardware import (
    CapabilityVerificationStatus,
    CommissioningProfile,
    CommissioningState,
    CommissioningStepResult,
    CommissioningStepStatus,
    EmergencyStopEvent,
    EmergencyStopSource,
    EmergencyStopState,
    HardwareActionIntent,
    HardwareAdapterResult,
    HardwareCommissioningAdapter,
    HardwareCommissioningSession,
    HardwareIdentity,
    ProbeIdentity,
    ResourceLock,
    SafetyLimit,
    TargetSafetyCapability,
    WatchdogState,
)
from eea_core.reliability import SideEffectStatus, payload_sha256
from eea_core.security import PermissionVerificationContext, ValidatedPermissionGrant

from eea_application.reliability import EventOutboxService


class CommissioningRepository(Protocol):
    def add_session(self, session: HardwareCommissioningSession, *, commit: bool) -> None: ...

    def get_session(
        self, session_id: UUID, *, project_id: UUID | None = None
    ) -> HardwareCommissioningSession | None: ...

    def save_session(
        self, session: HardwareCommissioningSession, *, expected_revision: int, commit: bool
    ) -> bool: ...

    def list_steps(self, session_id: UUID) -> list[CommissioningStepResult]: ...

    def add_step(self, step: CommissioningStepResult, *, commit: bool) -> None: ...

    def add_evidence(self, evidence: Evidence, *, commit: bool) -> Evidence: ...

    def add_emergency_stop(self, event: EmergencyStopEvent, *, commit: bool) -> None: ...

    def get_profile(self, profile_id: UUID) -> CommissioningProfile | None: ...

    def quarantine_lock(self, lock_id: UUID, *, commit: bool) -> bool: ...

    def bind_lock(self, lock_id: UUID, *, project_id: UUID, session_id: UUID) -> bool: ...

    def claim_hardware_action(
        self,
        *,
        session_id: UUID,
        expected_revision: int,
        expected_state: CommissioningState,
        action: str,
        request_hash: str,
        payload: dict[str, object],
    ) -> HardwareActionIntent | None: ...

    def claim_safety_action(
        self,
        *,
        session_id: UUID,
        expected_revision: int,
        expected_state: CommissioningState,
        action: str,
        request_hash: str,
        payload: dict[str, object],
        stale_action_id: UUID,
        stale_journal_id: UUID,
    ) -> HardwareActionIntent | None: ...

    def finalize_hardware_action(
        self,
        intent: HardwareActionIntent,
        *,
        status: SideEffectStatus,
        result_ref: str | None = None,
        error: str | None = None,
    ) -> None: ...

    def commit(self) -> None: ...


ArtifactHashLookup = Callable[[UUID], str | None]
ArtifactBindingLookup = Callable[[UUID], dict[str, object] | None]
BuildBindingLookup = Callable[[UUID], dict[str, object] | None]
LockLookup = Callable[[UUID], ResourceLock | None]
CapabilityLookup = Callable[[str], TargetSafetyCapability | None]
CompositionLookup = Callable[[UUID], Sequence[CommissioningRuleContribution]]


class PermissionAuthority(Protocol):
    def verify(self, context: PermissionVerificationContext) -> ValidatedPermissionGrant | None: ...


SAFE_COMMISSIONING_PROFILE_ID = uuid5(
    NAMESPACE_URL, "https://eea.local/commissioning-profile/SAFE_COMMISSIONING/1.0"
)


def build_safe_commissioning_profile() -> CommissioningProfile:
    """Return the deterministic first profile; it is never a production/unlimited profile."""

    return CommissioningProfile.safe_commissioning().model_copy(
        update={"id": SAFE_COMMISSIONING_PROFILE_ID}
    )


def _engineering_error(
    code: EngineeringErrorCode, message: str, **details: object
) -> EngineeringError:
    return EngineeringError(code, message, details=details)


class CommissioningService:
    """Own all safety gates; plugins may supply observations but cannot transition sessions."""

    def __init__(
        self,
        repository: CommissioningRepository,
        adapter: HardwareCommissioningAdapter,
        *,
        outbox: EventOutboxService | None = None,
        artifact_hash: ArtifactHashLookup | None = None,
        artifact_binding: ArtifactBindingLookup | None = None,
        build_binding: BuildBindingLookup | None = None,
        lock_lookup: LockLookup | None = None,
        capability_lookup: CapabilityLookup | None = None,
        permission_authority: PermissionAuthority | None = None,
        composition_lookup: CompositionLookup | None = None,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self.repository = repository
        self.adapter = adapter
        self.outbox = outbox
        self.artifact_hash = artifact_hash
        self.artifact_binding = artifact_binding
        self.build_binding = build_binding
        self.lock_lookup = lock_lookup
        self.capability_lookup = capability_lookup
        self.permission_authority = permission_authority
        self.composition_lookup = composition_lookup
        self.now = now

    def create_session(
        self,
        *,
        project_id: UUID,
        target_id: str,
        firmware_artifact_id: UUID,
        firmware_hash: str,
        hardware_identity: HardwareIdentity,
        probe_identity: ProbeIdentity,
        commissioning_profile: CommissioningProfile,
        started_by: str,
        build_run_id: UUID | None = None,
        source_revision_id: UUID | None = None,
        build_input_snapshot_id: UUID | None = None,
        board_revision: str | None = None,
        resource_lock_ids: Sequence[UUID] = (),
        permission_token_ids: Sequence[str] = (),
    ) -> HardwareCommissioningSession:
        session = HardwareCommissioningSession(
            project_id=project_id,
            target_id=target_id,
            firmware_artifact_id=firmware_artifact_id,
            firmware_hash=firmware_hash,
            build_run_id=build_run_id,
            source_revision_id=source_revision_id,
            build_input_snapshot_id=build_input_snapshot_id,
            hardware_identity=hardware_identity,
            probe_identity=probe_identity,
            board_revision=board_revision,
            commissioning_profile_id=commissioning_profile.id,
            started_by=started_by,
            safety_limits_snapshot=commissioning_profile.safety_limits,
            watchdog_state=WatchdogState(
                timeout=commissioning_profile.safety_limits.watchdog_timeout
            ),
            resource_lock_ids=list(resource_lock_ids),
            permission_token_ids=list(permission_token_ids),
            metadata={
                "lock_heartbeat_timeout_seconds": float(
                    str(
                        commissioning_profile.watchdog_policy.get(
                            "lock_heartbeat_timeout_seconds", 30.0
                        )
                    )
                )
            },
        )
        self.repository.add_session(session, commit=False)
        for lock_id in session.resource_lock_ids:
            binder = getattr(self.repository, "bind_lock", None)
            if binder is not None and not binder(
                lock_id, project_id=project_id, session_id=session.id
            ):
                raise _engineering_error(
                    EngineeringErrorCode.RESOURCE_BUSY,
                    "resource lock is owned by another session or unavailable",
                    lock_id=str(lock_id),
                )
        self._emit(session, "commissioning.session.created", {"started_by": started_by})
        self.repository.commit()
        return session

    def get(
        self, session_id: UUID, *, project_id: UUID | None = None
    ) -> HardwareCommissioningSession:
        session = self.repository.get_session(session_id, project_id=project_id)
        if session is None:
            raise _engineering_error(
                EngineeringErrorCode.COMMISSIONING_REQUIRED,
                "commissioning session was not found",
                session_id=str(session_id),
            )
        return session

    def preflight(
        self,
        session_id: UUID,
        *,
        expected_revision: int,
        permissions: set[Permission],
    ) -> HardwareCommissioningSession:
        session = self.get(session_id)
        self._check_revision(session, expected_revision)
        if session.state is not CommissioningState.CREATED:
            raise _engineering_error(
                EngineeringErrorCode.COMMISSIONING_BLOCKED,
                "preflight is only valid for a newly created session",
                state=session.state.value,
            )
        profile = self._profile(session)
        session.transition(CommissioningState.PREFLIGHT)
        checks: list[dict[str, object]] = []
        failures: list[dict[str, object]] = []

        self._check_permission_set(
            session,
            permissions,
            profile.required_permissions,
            actor=session.started_by,
            failures=failures,
            action="PREFLIGHT",
        )
        self._check_binding(session, failures)
        self._check_identity(session, failures)
        self._check_lock_set(session, failures)
        if not session.safety_limits_snapshot.complete_for_actuator():
            failures.append(
                {"check": "safety_limits", "reason": "complete limit snapshot required"}
            )
        capability = self.capability_lookup(session.target_id) if self.capability_lookup else None
        if capability is None:
            failures.append(
                {"check": "target_safety_capability", "reason": "capability is unknown"}
            )
        else:
            if capability.verification_status is not CapabilityVerificationStatus.VERIFIED:
                failures.append(
                    {
                        "check": "target_safety_capability",
                        "reason": capability.verification_status.value,
                    }
                )
            for name in profile.required_safety_capabilities:
                if not bool(getattr(capability, name, False)):
                    failures.append(
                        {"check": name, "reason": "required capability is not verified"}
                    )
        watchdog = self.adapter.watchdog_status()
        checks.append({"check": "watchdog", "ok": watchdog.ok, **watchdog.measurements})
        if not watchdog.ok:
            failures.append({"check": "watchdog", "reason": watchdog.failure_reason or "not armed"})
        fault = self.adapter.read_fault_state()
        checks.append({"check": "fault_state", "ok": fault.ok, **fault.measurements})
        if not fault.ok:
            failures.append(
                {"check": "fault_state", "reason": fault.failure_reason or "fault unknown"}
            )

        checks.append(
            {
                "check": "permissions",
                "ok": not any(item["check"] == "permission" for item in failures),
            }
        )
        checks.append(
            {"check": "identity", "ok": not any(item["check"] == "identity" for item in failures)}
        )
        checks.append(
            {
                "check": "resource_lock",
                "ok": not any(item["check"] == "resource_lock" for item in failures),
            }
        )
        checks.append(
            {
                "check": "firmware_binding",
                "ok": not any(item["check"] == "firmware" for item in failures),
            }
        )
        session.preflight_results = [*checks, {"check": "failures", "items": failures}]
        session.metadata["granted_permissions"] = sorted(
            permission.value for permission in permissions
        )
        if failures:
            session.transition(CommissioningState.BLOCKED)
            if not self.repository.save_session(
                session, expected_revision=expected_revision, commit=False
            ):
                raise _engineering_error(
                    EngineeringErrorCode.REVISION_CONFLICT, "commissioning CAS failed"
                )
            self._emit(session, "commissioning.preflight.blocked", {"failures": failures})
            self.repository.commit()
            raise _engineering_error(
                EngineeringErrorCode.COMMISSIONING_BLOCKED,
                "commissioning preflight failed closed",
                session_id=str(session.id),
                failures=failures,
            )
        self._persist(
            session, expected_revision, "commissioning.preflight.passed", {"checks": checks}
        )
        return session

    def flash(
        self,
        session_id: UUID,
        *,
        expected_revision: int,
        permissions: set[Permission],
    ) -> HardwareCommissioningSession:
        session = self.get(session_id)
        self._check_revision(session, expected_revision)
        if session.state is not CommissioningState.PREFLIGHT:
            raise _engineering_error(
                EngineeringErrorCode.COMMISSIONING_BLOCKED,
                "flash requires a passing preflight",
                state=session.state.value,
            )
        self._require_permissions(
            session,
            permissions,
            {Permission.FLASH, Permission.DEBUG, Permission.HARDWARE_CONTROL},
            actor=session.started_by,
            action="FLASH",
        )
        failures: list[dict[str, object]] = []
        self._check_identity(session, failures)
        self._check_lock_set(session, failures)
        if failures:
            raise _engineering_error(
                EngineeringErrorCode.COMMISSIONING_BLOCKED, "flash gate blocked", failures=failures
            )
        action, claimed_revision = self._claim_action(
            session,
            expected_revision=expected_revision,
            action="FLASH",
            expected_state=CommissioningState.PREFLIGHT,
        )
        try:
            result = self.adapter.flash(session.firmware_hash)
        except Exception as exc:  # adapter failures are safety failures, never ordinary errors
            return self._fault(
                session,
                claimed_revision,
                "FLASH",
                f"adapter exception: {type(exc).__name__}",
                rollback=True,
                action=action,
            )
        if not result.ok:
            return self._fault(
                session,
                claimed_revision,
                "flash",
                result.failure_reason or "flash failed",
                action=action,
            )
        try:
            verified_flash = self.adapter.verify_flash(session.firmware_hash)
        except Exception as exc:
            return self._fault(
                session,
                claimed_revision,
                "flash",
                f"verify adapter exception: {type(exc).__name__}",
                rollback=True,
                action=action,
            )
        if not verified_flash.ok:
            return self._fault(
                session,
                claimed_revision,
                "flash",
                verified_flash.failure_reason or "flash verification failed",
                action=action,
            )
        reset = self._safe_adapter_call("reset_to_safe_state")
        safe = self._safe_adapter_call("enter_safe_state")
        if (
            reset is None
            or not reset.ok
            or safe is None
            or not safe.ok
            or safe.safe_state_verified is not True
        ):
            return self._fault(
                session,
                claimed_revision,
                "flash",
                (
                    "safe state could not be proven"
                    if safe is None or not safe.ok
                    else safe.failure_reason or "safe state entry failed"
                ),
                rollback=True,
                action=action,
            )
        session.transition(CommissioningState.FLASHED_SAFE)
        session.watchdog_state = session.watchdog_state.model_copy(
            update={"armed": True, "heartbeat_at": self.now(), "last_observed_status": "OK"}
        )
        self._step(
            session,
            "FLASH",
            CommissioningStepStatus.PASS,
            {"flash": "verified", "pwm_disabled": True},
        )
        self._persist(
            session,
            claimed_revision,
            "commissioning.flash.safe",
            {"pwm_disabled": True},
            action=action,
        )
        return session

    def execute_step(
        self,
        session_id: UUID,
        step_id: str,
        *,
        expected_revision: int,
        permissions: set[Permission],
        operator: str,
    ) -> HardwareCommissioningSession:
        session = self.get(session_id)
        self._check_revision(session, expected_revision)
        step = step_id.upper()
        expected_state = {
            "SENSOR_CHECK": CommissioningState.FLASHED_SAFE,
            "LOW_POWER": CommissioningState.SENSOR_CHECK,
            "CLOSED_LOOP_LIMITED": CommissioningState.LOW_POWER,
        }.get(step)
        if expected_state is None or session.state is not expected_state:
            raise _engineering_error(
                EngineeringErrorCode.COMMISSIONING_BLOCKED,
                "step is not legal for the current state",
                step_id=step,
                state=session.state.value,
            )
        if any(
            item.step_id == step and item.status is CommissioningStepStatus.PASS
            for item in session.step_results
        ):
            return session
        required = {Permission.DEBUG, Permission.HARDWARE_CONTROL}
        if step in {"LOW_POWER", "CLOSED_LOOP_LIMITED"}:
            required.add(Permission.ACTUATOR_ENABLE)
        self._require_permissions(session, permissions, required, actor=operator, action=step)
        failures: list[dict[str, object]] = []
        self._check_identity(session, failures)
        self._check_lock_set(session, failures)
        if failures:
            self._block_and_persist(session, expected_revision, step, failures)
            raise _engineering_error(
                EngineeringErrorCode.COMMISSIONING_BLOCKED, "step gate blocked", failures=failures
            )
        action, claimed_revision = self._claim_action(
            session,
            expected_revision=expected_revision,
            action=step,
            expected_state=expected_state,
        )
        started = time.monotonic()
        try:
            if step == "SENSOR_CHECK":
                result = self.adapter.sensor_sanity_check()
            else:
                result = self.adapter.execute_limited_step(step, session.safety_limits_snapshot)
        except Exception as exc:
            return self._fault(
                session,
                claimed_revision,
                step,
                f"adapter exception: {type(exc).__name__}",
                rollback=step != "SENSOR_CHECK",
                action=action,
            )
        duration = time.monotonic() - started
        result_measurements = {
            **result.measurements,
            "duration_seconds": duration,
            "runtime_seconds": result.measurements.get("runtime_seconds", duration),
        }
        if not result.ok:
            if step == "SENSOR_CHECK":
                self._block_and_persist(
                    session,
                    claimed_revision,
                    step,
                    [{"check": step, "reason": result.failure_reason or "adapter failure"}],
                    action=action,
                )
            else:
                self._fault(
                    session,
                    claimed_revision,
                    step,
                    result.failure_reason or "adapter failure",
                    action=action,
                )
            raise _engineering_error(
                EngineeringErrorCode.COMMISSIONING_BLOCKED,
                f"{step} failed",
                session_id=str(session.id),
            )
        if step in {"LOW_POWER", "CLOSED_LOOP_LIMITED"}:
            runtime_violation = self._runtime_violation(duration, session.safety_limits_snapshot)
            if runtime_violation is not None:
                return self._fault(
                    session,
                    claimed_revision,
                    step,
                    runtime_violation,
                    action=action,
                    rollback=True,
                    requires_emergency_stop=True,
                )
            post_failures: list[dict[str, object]] = []
            self._check_identity(session, post_failures)
            self._check_lock_set(session, post_failures)
            try:
                watchdog_result = self.adapter.watchdog_status()
            except Exception:
                watchdog_result = None
            if watchdog_result is None or not watchdog_result.ok:
                post_failures.append({"check": "watchdog", "reason": "watchdog lost during action"})
            elif "duration_seconds" in watchdog_result.measurements:
                watchdog_duration = self._duration_seconds(
                    watchdog_result.measurements["duration_seconds"],
                    session.safety_limits_snapshot.watchdog_timeout,
                )
                watchdog_limit = session.safety_limits_snapshot.watchdog_timeout
                if (
                    watchdog_duration is None
                    or watchdog_limit is None
                    or watchdog_duration > watchdog_limit.require_normalized_nominal() + 1e-12
                ):
                    post_failures.append(
                        {
                            "check": "watchdog",
                            "reason": "watchdog duration is unknown or exceeded its safety limit",
                        }
                    )
            if post_failures:
                return self._fault(
                    session,
                    claimed_revision,
                    step,
                    "post-action safety validation failed",
                    rollback=True,
                    action=action,
                )
            domain_failures = self._check_composition_rules(session, result_measurements, step)
            if domain_failures:
                return self._fault(
                    session,
                    claimed_revision,
                    step,
                    "commissioning domain safety rule failed",
                    rollback=True,
                    action=action,
                    details={"domain_rules": domain_failures},
                )
            violation = self._limit_violation(
                step, result_measurements, session.safety_limits_snapshot
            )
            if violation is not None:
                self._fault(
                    session,
                    claimed_revision,
                    step,
                    violation,
                    rollback=True,
                    action=action,
                    state_override=CommissioningState.EMERGENCY_STOP,
                    requires_emergency_stop=True,
                )
                raise _engineering_error(EngineeringErrorCode.SAFETY_LIMIT_VIOLATION, violation)
        next_state = {
            "SENSOR_CHECK": CommissioningState.SENSOR_CHECK,
            "LOW_POWER": CommissioningState.LOW_POWER,
            "CLOSED_LOOP_LIMITED": CommissioningState.CLOSED_LOOP_LIMITED,
        }[step]
        session.transition(next_state)
        session.current_step = step
        self._step(
            session, step, CommissioningStepStatus.PASS, result_measurements, operator=operator
        )
        self._persist(
            session,
            claimed_revision,
            f"commissioning.step.{step.lower()}.passed",
            result_measurements,
            action=action,
        )
        return session

    def approve(
        self,
        session_id: UUID,
        *,
        expected_revision: int,
        actor: str,
        permissions: set[Permission],
    ) -> HardwareCommissioningSession:
        session = self.get(session_id)
        self._check_revision(session, expected_revision)
        if session.state is not CommissioningState.CLOSED_LOOP_LIMITED:
            raise _engineering_error(
                EngineeringErrorCode.COMMISSIONING_BLOCKED,
                "approval requires limited closed-loop pass",
            )
        grants = self._require_permissions(
            session,
            permissions,
            {Permission.ACTUATOR_ENABLE},
            actor=actor,
            action="APPROVE",
        )
        if not all(
            any(
                step.step_id == name and step.status is CommissioningStepStatus.PASS
                for step in session.step_results
            )
            for name in ("SENSOR_CHECK", "LOW_POWER", "CLOSED_LOOP_LIMITED")
        ):
            raise _engineering_error(
                EngineeringErrorCode.COMMISSIONING_BLOCKED,
                "mandatory commissioning steps are incomplete",
            )
        session.transition(CommissioningState.USER_APPROVAL)
        session.approved_by = actor
        session.approval_snapshot = {
            "actor": actor,
            "session_revision": session.revision,
            "firmware_hash": session.firmware_hash,
            "target_id": session.target_id,
            "hardware_identity": session.hardware_identity.model_dump(mode="json"),
            "safety_limits": session.safety_limits_snapshot.model_dump(mode="json"),
            "profile_id": str(session.commissioning_profile_id),
            "profile_version": self._profile(session).version,
            "source_revision_id": str(session.source_revision_id)
            if session.source_revision_id
            else None,
            "build_input_snapshot_id": str(session.build_input_snapshot_id)
            if session.build_input_snapshot_id
            else None,
            "permission_token_ids": [str(item.token_id) for item in grants],
            "step_ids": [
                step.step_id
                for step in session.step_results
                if step.status is CommissioningStepStatus.PASS
            ],
        }
        self._persist(
            session, expected_revision, "commissioning.approval.recorded", {"actor": actor}
        )
        return session

    def enable_normal_operation(
        self,
        session_id: UUID,
        *,
        expected_revision: int,
        permissions: set[Permission],
        actor: str,
    ) -> HardwareCommissioningSession:
        session = self.get(session_id)
        self._check_revision(session, expected_revision)
        if session.state is not CommissioningState.USER_APPROVAL:
            raise _engineering_error(
                EngineeringErrorCode.COMMISSIONING_REQUIRED, "explicit approval is required"
            )
        self._require_permissions(
            session,
            permissions,
            {Permission.ACTUATOR_ENABLE},
            actor=actor,
            action="ENABLE_NORMAL_OPERATION",
        )
        if (
            session.approval_snapshot is None
            or session.approval_snapshot.get("session_revision") != expected_revision
            or session.approval_snapshot.get("firmware_hash") != session.firmware_hash
            or session.approval_snapshot.get("target_id") != session.target_id
            or session.approval_snapshot.get("source_revision_id")
            != (str(session.source_revision_id) if session.source_revision_id else None)
            or session.approval_snapshot.get("build_input_snapshot_id")
            != (str(session.build_input_snapshot_id) if session.build_input_snapshot_id else None)
            or session.approval_snapshot.get("profile_id") != str(session.commissioning_profile_id)
        ):
            raise _engineering_error(
                EngineeringErrorCode.COMMISSIONING_BLOCKED, "approval is stale"
            )
        failures: list[dict[str, object]] = []
        self._check_identity(session, failures)
        self._check_lock_set(session, failures)
        if failures:
            raise _engineering_error(
                EngineeringErrorCode.COMMISSIONING_BLOCKED,
                "normal-operation safety gate is blocked",
                failures=failures,
            )
        session.transition(CommissioningState.NORMAL_OPERATION)
        session.completed_at = self.now()
        self._emit(session, "commissioning.session.normal_operation", {"actor": actor})
        if not self.repository.save_session(
            session, expected_revision=expected_revision, commit=False
        ):
            raise _engineering_error(
                EngineeringErrorCode.REVISION_CONFLICT, "commissioning CAS failed"
            )
        self.repository.commit()
        return session

    def emergency_stop(
        self,
        session_id: UUID,
        *,
        expected_revision: int,
        permissions: set[Permission],
        source: EmergencyStopSource = EmergencyStopSource.USER,
        reason: str = "emergency stop requested",
        actor: str = "system",
    ) -> HardwareCommissioningSession:
        session = self.get(session_id)
        if session.state is CommissioningState.EMERGENCY_STOP:
            return session
        self._check_revision(session, expected_revision)
        if session.state is CommissioningState.ABORTED:
            raise _engineering_error(
                EngineeringErrorCode.COMMISSIONING_BLOCKED,
                "an explicitly safe aborted session requires a new commissioning session",
            )
        action, claimed_revision = self._claim_action(
            session,
            expected_revision=expected_revision,
            action="EMERGENCY_STOP",
            expected_state=session.state,
            safety_preemption=session.active_action_id is not None,
        )
        # E-stop is a safety action and must remain reachable even when a grant is unavailable.
        stop = self._safe_adapter_call("emergency_stop")
        safe = self._safe_adapter_call("enter_safe_state")
        quarantined, quarantine_failures = self._quarantine_locks(session)
        verified = (
            stop is not None
            and stop.ok
            and safe is not None
            and safe.ok
            and safe.safe_state_verified is True
            and not quarantine_failures
        )
        session.emergency_stop_state = (
            EmergencyStopState.ACTIVE if verified else EmergencyStopState.UNKNOWN
        )
        session.transition(
            CommissioningState.EMERGENCY_STOP if verified else CommissioningState.ROLLBACK_REQUIRED
        )
        evidence = self._evidence(
            session,
            "Emergency stop attempt",
            {
                "source": source.value,
                "reason": reason,
                "verified": verified,
                "quarantined_resource_ids": [str(item) for item in quarantined],
                "quarantine_failures": quarantine_failures,
            },
        )
        event = EmergencyStopEvent(
            session_id=session.id,
            source=source,
            reason=reason,
            safe_state_attempted=True,
            safe_state_verified=verified,
            quarantined_resource_ids=quarantined,
            evidence_ids=[evidence.id],
            idempotency_key=f"emergency-stop:{session.id}:{source.value}",
            actor=actor,
        )
        self.repository.add_emergency_stop(event, commit=False)
        session.evidence_ids.append(evidence.id)
        self._step(
            session,
            "EMERGENCY_STOP",
            CommissioningStepStatus.PASS if verified else CommissioningStepStatus.FAIL,
            {"verified": verified},
            operator=actor,
        )
        self._persist(
            session,
            claimed_revision,
            "commissioning.emergency_stop",
            {"event_id": str(event.id), "verified": verified},
            action=action,
            action_status=(
                SideEffectStatus.APPLIED if verified else SideEffectStatus.RECONCILE_REQUIRED
            ),
        )
        return session

    def handle_watchdog_loss(
        self, session_id: UUID, *, expected_revision: int, permissions: set[Permission]
    ) -> HardwareCommissioningSession:
        return self.emergency_stop(
            session_id,
            expected_revision=expected_revision,
            permissions=permissions,
            source=EmergencyStopSource.WATCHDOG,
            reason="target watchdog heartbeat was lost",
        )

    def handle_lock_loss(
        self, session_id: UUID, *, expected_revision: int, permissions: set[Permission]
    ) -> HardwareCommissioningSession:
        return self.emergency_stop(
            session_id,
            expected_revision=expected_revision,
            permissions=permissions,
            source=EmergencyStopSource.LOCK_LOSS,
            reason="resource lock lease was lost",
        )

    def safe_cancel(
        self, session_id: UUID, *, expected_revision: int, permissions: set[Permission], actor: str
    ) -> HardwareCommissioningSession:
        return self.emergency_stop(
            session_id,
            expected_revision=expected_revision,
            permissions=permissions,
            source=EmergencyStopSource.CANCELLATION,
            reason="commissioning cancellation requested",
            actor=actor,
        )

    def abort(
        self,
        session_id: UUID,
        *,
        expected_revision: int,
        permissions: set[Permission],
        actor: str,
    ) -> HardwareCommissioningSession:
        session = self.get(session_id)
        self._check_revision(session, expected_revision)
        self._require_permissions(
            session,
            permissions,
            {Permission.HARDWARE_CONTROL},
            actor=actor,
            action="ABORT",
        )
        safe = self._safe_adapter_call("enter_safe_state")
        quarantined, quarantine_failures = self._quarantine_locks(session)
        safe_verified = (
            safe is not None
            and safe.ok
            and safe.safe_state_verified is True
            and not quarantine_failures
        )
        session.transition(
            CommissioningState.ABORTED if safe_verified else CommissioningState.ROLLBACK_REQUIRED
        )
        session.aborted_at = self.now()
        self._step(
            session,
            "ABORT",
            CommissioningStepStatus.PASS if safe_verified else CommissioningStepStatus.FAIL,
            {
                "safe": safe_verified,
                "quarantined_resource_ids": [str(item) for item in quarantined],
                "quarantine_failures": quarantine_failures,
            },
            operator=actor,
        )
        self._persist(
            session, expected_revision, "commissioning.session.aborted", {"safe": safe_verified}
        )
        return session

    def _quarantine_locks(
        self, session: HardwareCommissioningSession
    ) -> tuple[list[UUID], list[str]]:
        quarantined: list[UUID] = []
        failures: list[str] = []
        for lock_id in session.resource_lock_ids:
            if self.repository.quarantine_lock(lock_id, commit=False):
                quarantined.append(lock_id)
            else:
                failures.append(f"resource lock {lock_id} could not be quarantined")
        return quarantined, failures

    def _profile(self, session: HardwareCommissioningSession) -> CommissioningProfile:
        profile = self.repository.get_profile(session.commissioning_profile_id)
        if profile is None:
            raise _engineering_error(
                EngineeringErrorCode.COMMISSIONING_BLOCKED, "commissioning profile is missing"
            )
        return profile

    def _check_revision(self, session: HardwareCommissioningSession, expected: int) -> None:
        if session.revision != expected:
            raise _engineering_error(
                EngineeringErrorCode.REVISION_CONFLICT,
                "commissioning session revision conflict",
                session_id=str(session.id),
                expected_revision=expected,
                actual_revision=session.revision,
            )

    def _check_binding(
        self, session: HardwareCommissioningSession, failures: list[dict[str, object]]
    ) -> None:
        if self.artifact_binding is not None:
            artifact = self.artifact_binding(session.firmware_artifact_id)
            if artifact is None:
                failures.append({"check": "firmware", "reason": "firmware artifact is missing"})
            else:
                if artifact.get("project_id") != str(session.project_id):
                    failures.append(
                        {"check": "firmware", "reason": "firmware artifact project scope drifted"}
                    )
                if artifact.get("content_hash") != session.firmware_hash:
                    failures.append(
                        {"check": "firmware", "reason": "firmware artifact hash mismatch"}
                    )
        if self.artifact_hash is not None:
            actual = self.artifact_hash(session.firmware_artifact_id)
            if actual is None or actual != session.firmware_hash:
                failures.append({"check": "firmware", "reason": "firmware artifact hash mismatch"})
        if session.source_revision_id is None or session.build_input_snapshot_id is None:
            failures.append(
                {
                    "check": "firmware",
                    "reason": "SourceRevision and BuildInputSnapshot are required",
                }
            )
        if session.build_run_id is None:
            failures.append({"check": "build", "reason": "BuildRun binding is required"})
        elif self.build_binding is not None:
            build = self.build_binding(session.build_run_id)
            if build is None or build.get("status") != "PASS":
                failures.append({"check": "build", "reason": "BuildRun is not a valid PASS result"})
            else:
                if build.get("project_id") != str(session.project_id):
                    failures.append({"check": "build", "reason": "BuildRun project scope drifted"})
                if build.get("source_revision_id") != str(session.source_revision_id):
                    failures.append(
                        {"check": "build", "reason": "BuildRun SourceRevision binding drifted"}
                    )
                if build.get("build_input_snapshot_id") != str(session.build_input_snapshot_id):
                    failures.append(
                        {"check": "build", "reason": "BuildRun BuildInputSnapshot binding drifted"}
                    )
                if build.get("source_revision_project_id") != str(session.project_id):
                    failures.append(
                        {"check": "build", "reason": "SourceRevision project scope drifted"}
                    )
                if build.get("build_input_project_id") != str(session.project_id):
                    failures.append(
                        {"check": "build", "reason": "BuildInputSnapshot project scope drifted"}
                    )
                if build.get("build_input_source_revision_id") != str(session.source_revision_id):
                    failures.append(
                        {
                            "check": "build",
                            "reason": "BuildInputSnapshot SourceRevision binding drifted",
                        }
                    )

    def _check_identity(
        self, session: HardwareCommissioningSession, failures: list[dict[str, object]]
    ) -> None:
        if not session.hardware_identity.has_commissioning_identity():
            failures.append(
                {
                    "check": "identity",
                    "reason": "target identity is incomplete for commissioning",
                }
            )
        actual = self.adapter.identify_target()
        if actual != session.hardware_identity:
            failures.append({"check": "identity", "reason": "target identity drift"})
        probe = self.adapter.verify_probe(session.probe_identity)
        if not probe.ok:
            failures.append(
                {"check": "identity", "reason": probe.failure_reason or "probe identity mismatch"}
            )

    def _check_lock_set(
        self, session: HardwareCommissioningSession, failures: list[dict[str, object]]
    ) -> None:
        if not session.resource_lock_ids or self.lock_lookup is None:
            failures.append(
                {"check": "resource_lock", "reason": "active HardwareTarget lock is required"}
            )
            return
        now = self.now()
        timeout_seconds = session.metadata.get("lock_heartbeat_timeout_seconds", 30.0)
        try:
            heartbeat_timeout = timedelta(seconds=float(str(timeout_seconds)))
        except (TypeError, ValueError):
            heartbeat_timeout = timedelta(seconds=30.0)
        locks = [self.lock_lookup(lock_id) for lock_id in session.resource_lock_ids]
        if any(
            lock is None or not lock.is_active(now, heartbeat_timeout=heartbeat_timeout)
            for lock in locks
        ):
            failures.append(
                {"check": "resource_lock", "reason": "lock lease is missing or expired"}
            )
            return
        for lock in (item for item in locks if item is not None):
            if lock.project_id != session.project_id:
                failures.append(
                    {"check": "resource_lock", "reason": "lock project scope is not bound"}
                )
            if lock.owner_session != session.id:
                failures.append(
                    {"check": "resource_lock", "reason": "lock owner session is not bound"}
                )
        if not any(
            lock.resource_type.value == "HardwareTarget" and lock.resource_id == session.target_id
            for lock in locks
            if lock is not None
        ):
            failures.append(
                {"check": "resource_lock", "reason": "HardwareTarget lock is not bound"}
            )
        for lock in (item for item in locks if item is not None):
            if lock.resource_type.value == "DebugProbe" and lock.resource_id not in {
                session.probe_identity.serial,
                session.probe_identity.port_path,
            }:
                failures.append(
                    {"check": "resource_lock", "reason": "DebugProbe lock is not bound"}
                )

    def _check_permission_set(
        self,
        session: HardwareCommissioningSession,
        permissions: set[Permission],
        required: Sequence[Permission],
        *,
        actor: str,
        failures: list[dict[str, object]],
        action: str,
    ) -> None:
        try:
            self._validated_permissions(
                session, permissions, set(required), actor=actor, action=action
            )
        except EngineeringError as exc:
            failures.append({"check": "permission", "reason": exc.message, **exc.details})

    def _require_permissions(
        self,
        session: HardwareCommissioningSession,
        permissions: set[Permission],
        required: set[Permission],
        *,
        actor: str,
        action: str,
    ) -> list[ValidatedPermissionGrant]:
        return self._validated_permissions(
            session, permissions, required, actor=actor, action=action
        )

    def _validated_permissions(
        self,
        session: HardwareCommissioningSession,
        requested: set[Permission],
        required: set[Permission],
        *,
        actor: str,
        action: str,
    ) -> list[ValidatedPermissionGrant]:
        if self.permission_authority is None:
            raise _engineering_error(
                EngineeringErrorCode.PERMISSION_REQUIRED,
                "a PermissionAuthority is required; requested permissions are never trusted",
                action=action,
                required_permissions=sorted(item.value for item in required),
            )
        grants: list[ValidatedPermissionGrant] = []
        for permission in sorted(required, key=lambda value: value.value):
            verified: ValidatedPermissionGrant | None = None
            for raw_id in session.permission_token_ids:
                try:
                    token_id = UUID(raw_id)
                except ValueError:
                    continue
                grant = self.permission_authority.verify(
                    PermissionVerificationContext(
                        token_id=token_id,
                        actor_id=actor,
                        project_id=session.project_id,
                        permission=permission,
                        resource_type="HardwareTarget",
                        resource_id=session.target_id,
                        session_id=session.id,
                        now=self.now(),
                    )
                )
                if grant is not None:
                    verified = grant
                    break
            if verified is None:
                raise _engineering_error(
                    EngineeringErrorCode.PERMISSION_REQUIRED,
                    "server-side permission token is missing, expired, or out of scope",
                    action=action,
                    permission=permission.value,
                )
            grants.append(verified)
        session.metadata["validated_permission_token_ids"] = [str(item.token_id) for item in grants]
        return grants

    def _step(
        self,
        session: HardwareCommissioningSession,
        step_id: str,
        status: CommissioningStepStatus,
        measurements: dict[str, object],
        *,
        operator: str = "system",
    ) -> CommissioningStepResult:
        now = self.now()
        evidence = self._evidence(session, f"Commissioning step {step_id}", measurements)
        result = CommissioningStepResult(
            session_id=session.id,
            step_id=step_id,
            status=status,
            started_at=now,
            completed_at=now,
            measurements=measurements,
            thresholds=session.safety_limits_snapshot.model_dump(mode="json"),
            evidence_ids=[evidence.id],
            tool_version=self.adapter.version,
            operator=operator,
        )
        session.step_results.append(result)
        session.evidence_ids.append(evidence.id)
        self.repository.add_step(result, commit=False)
        return result

    def _evidence(
        self, session: HardwareCommissioningSession, summary: str, measurements: dict[str, object]
    ) -> Evidence:
        evidence = Evidence(
            project_id=session.project_id,
            evidence_type=EvidenceType.HARDWARE_TEST,
            locator={
                "session_id": str(session.id),
                "firmware_hash": session.firmware_hash,
                "source_revision_id": str(session.source_revision_id)
                if session.source_revision_id
                else None,
                "target_identity": session.hardware_identity.model_dump(mode="json"),
                "probe_identity": session.probe_identity.model_dump(mode="json"),
                "safety_limits": session.safety_limits_snapshot.model_dump(mode="json"),
                "permission_token_ids": list(
                    cast(
                        list[object],
                        session.metadata.get(
                            "validated_permission_token_ids", session.permission_token_ids
                        ),
                    )
                ),
                "measurements": measurements,
                "tool": self.adapter.name,
                "tool_version": self.adapter.version,
                "timestamp": self.now().isoformat(),
            },
            summary=summary,
        )
        return self.repository.add_evidence(evidence, commit=False)

    def _persist(
        self,
        session: HardwareCommissioningSession,
        expected_revision: int,
        event_type: str,
        payload: dict[str, object],
        *,
        action: HardwareActionIntent | None = None,
        action_status: SideEffectStatus = SideEffectStatus.APPLIED,
    ) -> None:
        if action is not None:
            session.active_action_id = None
            session.active_action_kind = None
            session.active_action_started_at = None
            session.active_action_expected_revision = None
            session.active_action_request_hash = None
            session.active_action_journal_id = None
            self.repository.finalize_hardware_action(
                action,
                status=action_status,
                result_ref=str(session.id),
                error=(
                    cast(str, payload["reason"])
                    if action_status is not SideEffectStatus.APPLIED
                    and isinstance(payload.get("reason"), str)
                    else None
                ),
            )
        if not self.repository.save_session(
            session, expected_revision=expected_revision, commit=False
        ):
            raise _engineering_error(
                EngineeringErrorCode.REVISION_CONFLICT, "commissioning CAS failed"
            )
        self._emit(session, event_type, payload)
        self.repository.commit()

    def _claim_action(
        self,
        session: HardwareCommissioningSession,
        *,
        expected_revision: int,
        action: str,
        expected_state: CommissioningState,
        safety_preemption: bool = False,
    ) -> tuple[HardwareActionIntent | None, int]:
        stale_action_id = session.active_action_id
        stale_journal_id = session.active_action_journal_id
        if stale_action_id is not None and not safety_preemption:
            raise _engineering_error(
                EngineeringErrorCode.RECOVERY_REQUIRED,
                "a previous hardware action has not been reconciled",
                action_id=str(stale_action_id),
            )
        if safety_preemption and (stale_action_id is None or stale_journal_id is None):
            raise _engineering_error(
                EngineeringErrorCode.RECOVERY_REQUIRED,
                "safety preemption requires a durable stale action journal",
            )
        claimer = getattr(self.repository, "claim_hardware_action", None)
        if safety_preemption:
            claimer = getattr(self.repository, "claim_safety_action", None)
            if claimer is None:
                raise _engineering_error(
                    EngineeringErrorCode.RECOVERY_REQUIRED,
                    "repository does not support atomic safety preemption",
                )
        if claimer is None:
            return None, expected_revision
        payload = {
            "project_id": str(session.project_id),
            "firmware_hash": session.firmware_hash,
            "target_identity": session.hardware_identity.model_dump(mode="json"),
            "probe_identity": session.probe_identity.model_dump(mode="json"),
            "safety_limits": session.safety_limits_snapshot.model_dump(mode="json"),
            "resource_lock_ids": [str(item) for item in session.resource_lock_ids],
            "permission_token_ids": [str(item) for item in session.permission_token_ids],
        }
        if safety_preemption:
            payload.update(
                {
                    "preempted_action_id": str(stale_action_id),
                    "preempted_journal_id": str(stale_journal_id),
                }
            )
        request_hash = payload_sha256(
            {
                "session_id": str(session.id),
                "revision": expected_revision,
                "action": action,
                **payload,
            }
        )
        if safety_preemption:
            assert stale_action_id is not None
            assert stale_journal_id is not None
            intent = claimer(
                session_id=session.id,
                expected_revision=expected_revision,
                expected_state=expected_state,
                action=action,
                request_hash=request_hash,
                payload=payload,
                stale_action_id=stale_action_id,
                stale_journal_id=stale_journal_id,
            )
        else:
            intent = claimer(
                session_id=session.id,
                expected_revision=expected_revision,
                expected_state=expected_state,
                action=action,
                request_hash=request_hash,
                payload=payload,
            )
        if intent is None:
            raise _engineering_error(
                EngineeringErrorCode.RESOURCE_BUSY,
                "another service owns this commissioning action or recovery is required",
                session_id=str(session.id),
                action=action,
            )
        session.active_action_id = intent.action_id
        session.active_action_kind = intent.action
        session.active_action_started_at = intent.started_at
        session.active_action_expected_revision = intent.expected_revision
        session.active_action_request_hash = intent.request_hash
        session.active_action_journal_id = intent.journal_id
        session.revision = intent.claimed_revision
        self.repository.commit()
        return intent, intent.claimed_revision

    def _emit(
        self, session: HardwareCommissioningSession, event_type: str, payload: dict[str, object]
    ) -> None:
        if self.outbox is None:
            return
        self.outbox.enqueue(
            event_type=event_type,
            aggregate_type="HardwareCommissioningSession",
            aggregate_id=str(session.id),
            aggregate_revision=session.revision,
            project_id=session.project_id,
            payload={"session_id": str(session.id), "state": session.state.value, **payload},
            commit=False,
        )

    def _fault(
        self,
        session: HardwareCommissioningSession,
        expected_revision: int,
        step_id: str,
        reason: str,
        *,
        rollback: bool = False,
        action: HardwareActionIntent | None = None,
        details: dict[str, object] | None = None,
        state_override: CommissioningState | None = None,
        requires_emergency_stop: bool = False,
    ) -> HardwareCommissioningSession:
        stop = self._safe_adapter_call("emergency_stop")
        safe = self._safe_adapter_call("enter_safe_state")
        quarantined, quarantine_failures = self._quarantine_locks(session)
        safe_proven = (
            stop is not None
            and stop.ok
            and safe is not None
            and safe.ok
            and safe.safe_state_verified is True
            and not quarantine_failures
        )
        if not safe_proven:
            final_state = CommissioningState.ROLLBACK_REQUIRED
            session.emergency_stop_state = EmergencyStopState.UNKNOWN
        elif requires_emergency_stop or state_override is CommissioningState.EMERGENCY_STOP:
            final_state = CommissioningState.EMERGENCY_STOP
            session.emergency_stop_state = EmergencyStopState.ACTIVE
        else:
            final_state = state_override or (
                CommissioningState.ROLLBACK_REQUIRED if rollback else CommissioningState.FAULTED
            )
        session.transition(final_state)
        measurements: dict[str, object] = {
            "reason": reason,
            "safe_state_proven": safe_proven,
            "quarantined_resource_ids": [str(item) for item in quarantined],
            "quarantine_failures": quarantine_failures,
        }
        if details:
            measurements.update(details)
        self._step(session, step_id, CommissioningStepStatus.FAIL, measurements)
        self._persist(
            session,
            expected_revision,
            "commissioning.session.faulted",
            measurements,
            action=action,
            action_status=(
                SideEffectStatus.FAILED if safe_proven else SideEffectStatus.RECONCILE_REQUIRED
            ),
        )
        return session

    def _block_and_persist(
        self,
        session: HardwareCommissioningSession,
        expected_revision: int,
        step_id: str,
        failures: list[dict[str, object]],
        *,
        action: HardwareActionIntent | None = None,
    ) -> None:
        session.transition(CommissioningState.BLOCKED)
        self._step(session, step_id, CommissioningStepStatus.BLOCKED, {"failures": failures})
        self._persist(
            session,
            expected_revision,
            "commissioning.step.blocked",
            {"failures": failures},
            action=action,
            action_status=SideEffectStatus.FAILED,
        )

    def _safe_adapter_call(self, operation: str) -> HardwareAdapterResult | None:
        try:
            result = cast(HardwareAdapterResult, getattr(self.adapter, operation)())
        except Exception:
            return None
        if (
            result.ok
            and operation in {"emergency_stop", "enter_safe_state"}
            and result.safe_state_verified is True
        ):
            return result
        return result

    def _runtime_violation(self, duration: float, limits: SafetyLimit) -> str | None:
        if limits.max_test_runtime is None:
            return "max_test_runtime is required for limited operation"
        ceiling = limits.max_test_runtime.require_normalized_nominal()
        return (
            f"runtime exceeded safety limit ({duration} > {ceiling})"
            if duration > ceiling
            else None
        )

    def _check_composition_rules(
        self,
        session: HardwareCommissioningSession,
        measurements: dict[str, object],
        step: str,
    ) -> list[dict[str, object]]:
        if step != "CLOSED_LOOP_LIMITED" or self.composition_lookup is None:
            return []
        failures: list[dict[str, object]] = []
        results: list[dict[str, object]] = []
        for contribution in self.composition_lookup(session.project_id):
            value = measurements.get(contribution.measurement_key)
            passed = (
                value is True
                or value == "PASS"
                or (isinstance(value, dict) and value.get("status") == "PASS")
            )
            results.append(
                {
                    "rule_id": contribution.rule_id,
                    "status": "PASS" if passed else "UNKNOWN",
                }
            )
            if contribution.safety_critical and not passed:
                failures.append(
                    {
                        "rule_id": contribution.rule_id,
                        "measurement": contribution.measurement_key,
                        "reason": "mandatory domain safety contribution is missing or not PASS",
                    }
                )
        session.metadata["commissioning_rule_results"] = results
        return failures

    @staticmethod
    def _limit_violation(
        step: str, measurements: dict[str, object], limits: SafetyLimit
    ) -> str | None:
        dimensions = {
            "phase_current": limits.max_phase_current,
            "iq": limits.max_iq,
            "id": limits.max_id,
            "speed": limits.max_speed,
            "bus_voltage": limits.max_bus_voltage,
            "temperature": limits.max_temperature,
            "pwm_enable_duration": limits.max_pwm_enable_duration,
            "current_ramp_rate": limits.current_ramp_rate,
            "speed_ramp_rate": limits.speed_ramp_rate,
            "position_delta": limits.max_position_delta,
        }
        required = {
            "LOW_POWER": {
                "phase_current",
                "duty_cycle",
                "bus_voltage",
                "temperature",
                "pwm_enable_duration",
                "current_ramp_rate",
            },
            "CLOSED_LOOP_LIMITED": {
                "phase_current",
                "iq",
                "id",
                "speed",
                "duty_cycle",
                "bus_voltage",
                "temperature",
                "pwm_enable_duration",
                "current_ramp_rate",
                "speed_ramp_rate",
            },
        }[step]
        if measurements.get("position_control_active") is True:
            required.add("position_delta")
        if not required.issubset(measurements):
            return f"{step} did not produce all mandatory safety measurements"
        normalized: dict[str, float] = {}
        for name, ceiling in dimensions.items():
            if name not in required:
                continue
            if ceiling is None:
                return f"{step} safety limit {name} is not configured"
            value = CommissioningService._canonical_measurement(measurements[name], ceiling)
            if value is None:
                return f"{step} measurement {name} is missing, unknown, or dimension-mismatched"
            normalized[name] = value
        if "runtime_seconds" not in measurements:
            return f"{step} did not produce mandatory runtime measurement"
        runtime_raw = measurements["runtime_seconds"]
        if not isinstance(runtime_raw, (int, float, str)) or isinstance(runtime_raw, bool):
            return f"{step} runtime measurement is unknown"
        try:
            runtime = float(runtime_raw)
        except (TypeError, ValueError):
            return f"{step} runtime measurement is unknown"
        if limits.max_test_runtime is None:
            return f"{step} max_test_runtime is not configured"
        if runtime > limits.max_test_runtime.require_normalized_nominal() + 1e-12:
            runtime_ceiling = limits.max_test_runtime.require_normalized_nominal()
            return f"runtime exceeded safety limit ({runtime} > {runtime_ceiling})"
        if limits.max_duty_cycle is not None:
            duty_raw = measurements["duty_cycle"]
            if not isinstance(duty_raw, (int, float, str)) or isinstance(duty_raw, bool):
                return f"{step} duty_cycle measurement is unknown"
            try:
                duty = float(duty_raw)
            except (TypeError, ValueError):
                return f"{step} duty_cycle measurement is unknown"
            if not 0 <= duty <= limits.max_duty_cycle + 1e-12:
                return f"duty_cycle exceeded safety limit ({duty} > {limits.max_duty_cycle})"
        for name, observed in normalized.items():
            limit_value = dimensions[name]
            if (
                limit_value is not None
                and observed > limit_value.require_normalized_nominal() + 1e-12
            ):
                maximum = limit_value.require_normalized_nominal()
                return f"{name} exceeded safety limit ({observed} > {maximum})"
        return None

    @staticmethod
    def _canonical_measurement(raw: object, ceiling: EngineeringValue) -> float | None:
        value: EngineeringValue | None = None
        if isinstance(raw, EngineeringValue):
            value = raw
        elif isinstance(raw, dict):
            candidate = raw.get("engineering_value", raw)
            if isinstance(candidate, dict) and {
                "value",
                "unit",
                "dimension",
            }.issubset(candidate):
                try:
                    value = EngineeringValue(
                        unit=str(candidate["unit"]),
                        dimension=candidate["dimension"],
                        nominal=float(candidate["value"]),
                    )
                except (TypeError, ValueError):
                    return None
        if value is None or value.dimension is not ceiling.dimension:
            return None
        return value.require_normalized_nominal()

    @staticmethod
    def _duration_seconds(raw: object, limit: EngineeringValue | None) -> float | None:
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            return float(raw)
        if limit is None:
            return None
        return CommissioningService._canonical_measurement(raw, limit)


__all__ = [
    "SAFE_COMMISSIONING_PROFILE_ID",
    "CommissioningRepository",
    "CommissioningService",
    "build_safe_commissioning_profile",
]
