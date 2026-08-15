"""Application service for the fail-closed hardware commissioning workflow."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

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
    HardwareCommissioningAdapter,
    HardwareCommissioningSession,
    HardwareIdentity,
    ProbeIdentity,
    ResourceLock,
    SafetyLimit,
    TargetSafetyCapability,
    WatchdogState,
)

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

    def commit(self) -> None: ...


ArtifactHashLookup = Callable[[UUID], str | None]
BuildBindingLookup = Callable[[UUID], dict[str, object] | None]
LockLookup = Callable[[UUID], ResourceLock | None]
CapabilityLookup = Callable[[str], TargetSafetyCapability | None]

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
        build_binding: BuildBindingLookup | None = None,
        lock_lookup: LockLookup | None = None,
        capability_lookup: CapabilityLookup | None = None,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self.repository = repository
        self.adapter = adapter
        self.outbox = outbox
        self.artifact_hash = artifact_hash
        self.build_binding = build_binding
        self.lock_lookup = lock_lookup
        self.capability_lookup = capability_lookup
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
        )
        self.repository.add_session(session, commit=False)
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

        self._check_permission_set(permissions, profile.required_permissions, failures)
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
            permissions, {Permission.FLASH, Permission.DEBUG, Permission.HARDWARE_CONTROL}
        )
        failures: list[dict[str, object]] = []
        self._check_identity(session, failures)
        self._check_lock_set(session, failures)
        if failures:
            raise _engineering_error(
                EngineeringErrorCode.COMMISSIONING_BLOCKED, "flash gate blocked", failures=failures
            )
        result = self.adapter.flash(session.firmware_hash)
        if not result.ok:
            return self._fault(
                session, expected_revision, "flash", result.failure_reason or "flash failed"
            )
        verified_flash = self.adapter.verify_flash(session.firmware_hash)
        if not verified_flash.ok:
            return self._fault(
                session,
                expected_revision,
                "flash",
                verified_flash.failure_reason or "flash verification failed",
            )
        reset = self.adapter.reset_to_safe_state()
        safe = self.adapter.enter_safe_state()
        if not reset.ok or not safe.ok or safe.safe_state_verified is not True:
            return self._fault(
                session,
                expected_revision,
                "flash",
                (
                    safe.failure_reason or "safe state entry failed"
                    if not safe.ok
                    else "safe state could not be proven"
                ),
                rollback=True,
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
            session, expected_revision, "commissioning.flash.safe", {"pwm_disabled": True}
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
        self._require_permissions(permissions, required)
        failures: list[dict[str, object]] = []
        self._check_identity(session, failures)
        self._check_lock_set(session, failures)
        if failures:
            self._block_and_persist(session, expected_revision, step, failures)
            raise _engineering_error(
                EngineeringErrorCode.COMMISSIONING_BLOCKED, "step gate blocked", failures=failures
            )
        if step == "SENSOR_CHECK":
            result = self.adapter.sensor_sanity_check()
        else:
            result = self.adapter.execute_limited_step(step, session.safety_limits_snapshot)
        if not result.ok:
            self._block_and_persist(
                session,
                expected_revision,
                step,
                [{"check": step, "reason": result.failure_reason or "adapter failure"}],
            )
            raise _engineering_error(
                EngineeringErrorCode.COMMISSIONING_BLOCKED,
                f"{step} failed",
                session_id=str(session.id),
            )
        if step in {"LOW_POWER", "CLOSED_LOOP_LIMITED"}:
            violation = self._limit_violation(
                step, result.measurements, session.safety_limits_snapshot
            )
            if violation is not None:
                self.emergency_stop(
                    session.id,
                    expected_revision=expected_revision,
                    permissions=permissions,
                    source=EmergencyStopSource.SAFETY_MONITOR,
                    reason=violation,
                    actor=operator,
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
            session, step, CommissioningStepStatus.PASS, result.measurements, operator=operator
        )
        self._persist(
            session,
            expected_revision,
            f"commissioning.step.{step.lower()}.passed",
            result.measurements,
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
        self._require_permissions(permissions, {Permission.ACTUATOR_ENABLE})
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
        self._require_permissions(permissions, {Permission.ACTUATOR_ENABLE})
        if (
            session.approval_snapshot is None
            or session.approval_snapshot.get("session_revision") != expected_revision
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
        if source is EmergencyStopSource.USER:
            self._require_permissions(permissions, {Permission.HARDWARE_CONTROL})
        if session.state in {
            CommissioningState.ABORTED,
            CommissioningState.ROLLBACK_REQUIRED,
            CommissioningState.NORMAL_OPERATION,
        }:
            raise _engineering_error(
                EngineeringErrorCode.COMMISSIONING_BLOCKED,
                "terminal commissioning state cannot be mutated",
                state=session.state.value,
            )
        stop = self.adapter.emergency_stop()
        safe = self.adapter.enter_safe_state()
        verified = stop.ok and safe.ok and safe.safe_state_verified is True
        session.emergency_stop_state = (
            EmergencyStopState.ACTIVE if verified else EmergencyStopState.UNKNOWN
        )
        session.transition(
            CommissioningState.EMERGENCY_STOP if verified else CommissioningState.ROLLBACK_REQUIRED
        )
        evidence = self._evidence(
            session,
            "Emergency stop attempt",
            {"source": source.value, "reason": reason, "verified": verified},
        )
        event = EmergencyStopEvent(
            session_id=session.id,
            source=source,
            reason=reason,
            safe_state_attempted=True,
            safe_state_verified=verified,
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
        self.repository.save_session(session, expected_revision=expected_revision, commit=False)
        self._emit(
            session,
            "commissioning.emergency_stop",
            {"event_id": str(event.id), "verified": verified},
        )
        self.repository.commit()
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
        self._require_permissions(permissions, {Permission.HARDWARE_CONTROL})
        safe = self.adapter.enter_safe_state()
        session.transition(
            CommissioningState.ABORTED
            if safe.ok and safe.safe_state_verified
            else CommissioningState.ROLLBACK_REQUIRED
        )
        session.aborted_at = self.now()
        self._step(
            session,
            "ABORT",
            CommissioningStepStatus.PASS if safe.ok else CommissioningStepStatus.FAIL,
            {"safe": safe.ok},
            operator=actor,
        )
        self._persist(
            session, expected_revision, "commissioning.session.aborted", {"safe": safe.ok}
        )
        return session

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
            elif build.get("source_revision_id") != str(session.source_revision_id) or build.get(
                "build_input_snapshot_id"
            ) != str(session.build_input_snapshot_id):
                failures.append(
                    {"check": "build", "reason": "BuildRun source/input binding drifted"}
                )

    def _check_identity(
        self, session: HardwareCommissioningSession, failures: list[dict[str, object]]
    ) -> None:
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
        locks = [self.lock_lookup(lock_id) for lock_id in session.resource_lock_ids]
        if any(lock is None or not lock.is_active(now) for lock in locks):
            failures.append(
                {"check": "resource_lock", "reason": "lock lease is missing or expired"}
            )
        elif not any(lock.resource_id == session.target_id for lock in locks if lock is not None):
            failures.append(
                {"check": "resource_lock", "reason": "HardwareTarget lock is not bound"}
            )

    @staticmethod
    def _check_permission_set(
        permissions: set[Permission],
        required: Sequence[Permission],
        failures: list[dict[str, object]],
    ) -> None:
        missing = sorted(
            permission.value for permission in required if permission not in permissions
        )
        if missing:
            failures.append(
                {"check": "permission", "reason": "required permission missing", "missing": missing}
            )

    @staticmethod
    def _require_permissions(permissions: set[Permission], required: set[Permission]) -> None:
        missing = sorted(
            permission.value for permission in required if permission not in permissions
        )
        if missing:
            raise _engineering_error(
                EngineeringErrorCode.PERMISSION_REQUIRED,
                "hardware permission is missing; permissions are not escalated by the agent",
                missing=missing,
            )

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
    ) -> None:
        if not self.repository.save_session(
            session, expected_revision=expected_revision, commit=False
        ):
            raise _engineering_error(
                EngineeringErrorCode.REVISION_CONFLICT, "commissioning CAS failed"
            )
        self._emit(session, event_type, payload)
        self.repository.commit()

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
    ) -> HardwareCommissioningSession:
        session.transition(
            CommissioningState.ROLLBACK_REQUIRED if rollback else CommissioningState.FAULTED
        )
        self._step(session, step_id, CommissioningStepStatus.FAIL, {"reason": reason})
        self._persist(
            session, expected_revision, "commissioning.session.faulted", {"reason": reason}
        )
        return session

    def _block_and_persist(
        self,
        session: HardwareCommissioningSession,
        expected_revision: int,
        step_id: str,
        failures: list[dict[str, object]],
    ) -> None:
        session.transition(CommissioningState.BLOCKED)
        self._step(session, step_id, CommissioningStepStatus.BLOCKED, {"failures": failures})
        self._persist(
            session, expected_revision, "commissioning.step.blocked", {"failures": failures}
        )

    @staticmethod
    def _limit_violation(
        step: str, measurements: dict[str, object], limits: SafetyLimit
    ) -> str | None:
        numeric = {
            key: value for key, value in measurements.items() if isinstance(value, int | float)
        }
        checks: list[tuple[str, float | None, float | None]] = []
        current = (
            limits.max_phase_current.require_normalized_nominal()
            if limits.max_phase_current
            else None
        )
        speed = limits.max_speed.require_normalized_nominal() if limits.max_speed else None
        checks.extend(
            (
                (
                    "phase_current",
                    current,
                    float(numeric["phase_current"]) if "phase_current" in numeric else None,
                ),
                (
                    "iq",
                    limits.max_iq.require_normalized_nominal() if limits.max_iq else None,
                    float(numeric["iq"]) if "iq" in numeric else None,
                ),
                ("speed", speed, float(numeric["speed"]) if "speed" in numeric else None),
                (
                    "duty_cycle",
                    limits.max_duty_cycle,
                    float(numeric["duty_cycle"]) if "duty_cycle" in numeric else None,
                ),
            )
        )
        required = {
            "LOW_POWER": {"phase_current", "duty_cycle"},
            "CLOSED_LOOP_LIMITED": {"phase_current", "speed", "duty_cycle"},
        }[step]
        if not required.issubset(numeric):
            return f"{step} did not produce all mandatory safety measurements"
        for name, ceiling, observed in checks:
            if ceiling is not None and observed is not None and observed > ceiling + 1e-12:
                return f"{name} exceeded safety limit ({observed} > {ceiling})"
        return None


__all__ = [
    "SAFE_COMMISSIONING_PROFILE_ID",
    "CommissioningRepository",
    "CommissioningService",
    "build_safe_commissioning_profile",
]
