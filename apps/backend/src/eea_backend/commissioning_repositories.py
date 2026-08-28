"""SQLAlchemy adapters for the M18D commissioning contracts."""

from __future__ import annotations

from datetime import UTC, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from eea_application.reliability import EventOutboxService
from eea_core.entities import Evidence, utc_now
from eea_core.hardware import (
    CommissioningProfile,
    CommissioningState,
    CommissioningStepResult,
    EmergencyStopEvent,
    HardwareActionIntent,
    HardwareCommissioningSession,
    ResourceLock,
    ResourceLockStatus,
    ResourceType,
    TargetSafetyCapability,
)
from eea_core.reliability import (
    SideEffectJournal,
    SideEffectStatus,
)
from eea_core.security import (
    PermissionToken,
    PermissionVerificationContext,
    ValidatedPermissionGrant,
)
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from eea_backend.models import (
    ArtifactRecord,
    BuildInputSnapshotRecord,
    BuildRunRecord,
    CommissioningProfileRecord,
    CommissioningSessionRecord,
    CommissioningStepResultRecord,
    EmergencyStopEventRecord,
    PermissionTokenRecord,
    ResourceLockRecord,
    SafetyLimitRecord,
    SideEffectJournalRecord,
    SourceRevisionRecord,
    TargetSafetyCapabilityRecord,
)
from eea_backend.reliability_repositories import (
    SqlAlchemyOutboxRepository,
    SqlAlchemySideEffectJournalRepository,
)
from eea_backend.repositories import SqlAlchemyEvidenceRepository


def _profile(record: CommissioningProfileRecord) -> CommissioningProfile:
    return CommissioningProfile.model_validate(
        {
            "id": record.id,
            "schema_version": record.schema_version,
            "revision": record.revision,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "metadata": record.entity_metadata,
            "name": record.name,
            "version": record.version,
            "applicable_target_types": record.applicable_target_types,
            "applicable_domains": record.applicable_domains,
            "required_steps": record.required_steps,
            "required_permissions": record.required_permissions,
            "user_approval_required": record.user_approval_required,
            "safety_limits": record.safety_limits,
            "required_safety_capabilities": record.required_safety_capabilities,
            "watchdog_policy": record.watchdog_policy,
            "emergency_stop_policy": record.emergency_stop_policy,
            "safe_state_policy": record.safe_state_policy,
        }
    )


def _step(record: CommissioningStepResultRecord) -> CommissioningStepResult:
    return CommissioningStepResult.model_validate(
        {
            "id": record.id,
            "schema_version": record.schema_version,
            "revision": record.revision,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "metadata": record.entity_metadata,
            "session_id": record.session_id,
            "step_id": record.step_id,
            "status": record.status,
            "started_at": record.started_at,
            "completed_at": record.completed_at,
            "measurements": record.measurements,
            "thresholds": record.thresholds,
            "evidence_ids": record.evidence_ids,
            "tool_version": record.tool_version,
            "rule_version": record.rule_version,
            "operator": record.operator,
            "failure_reason": record.failure_reason,
        }
    )


def _session(
    record: CommissioningSessionRecord, steps: list[CommissioningStepResult]
) -> HardwareCommissioningSession:
    return HardwareCommissioningSession.model_validate(
        {
            "id": record.id,
            "schema_version": record.schema_version,
            "revision": record.revision,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "metadata": record.entity_metadata,
            "project_id": record.project_id,
            "target_id": record.target_id,
            "firmware_artifact_id": record.firmware_artifact_id,
            "firmware_hash": record.firmware_hash,
            "build_run_id": record.build_run_id,
            "source_revision_id": record.source_revision_id,
            "build_input_snapshot_id": record.build_input_snapshot_id,
            "hardware_identity": record.hardware_identity,
            "probe_identity": record.probe_identity,
            "board_revision": record.board_revision,
            "commissioning_profile_id": record.commissioning_profile_id,
            "state": record.state,
            "current_step": record.current_step,
            "started_by": record.started_by,
            "approved_by": record.approved_by,
            "safety_limits_snapshot": record.safety_limits_snapshot,
            "preflight_results": record.preflight_results,
            "step_results": steps,
            "evidence_ids": record.evidence_ids,
            "emergency_stop_state": record.emergency_stop_state,
            "watchdog_state": record.watchdog_state,
            "resource_lock_ids": record.resource_lock_ids,
            "permission_token_ids": record.permission_token_ids,
            "approval_snapshot": record.approval_snapshot,
            "completed_at": record.completed_at,
            "aborted_at": record.aborted_at,
            "active_action_id": record.active_action_id,
            "active_action_kind": record.active_action_kind,
            "active_action_started_at": record.active_action_started_at,
            "active_action_expected_revision": record.active_action_expected_revision,
            "active_action_request_hash": record.active_action_request_hash,
            "active_action_journal_id": record.active_action_journal_id,
        }
    )


def _lock(record: ResourceLockRecord) -> ResourceLock:
    return ResourceLock.model_validate(
        {
            "id": record.id,
            "schema_version": record.schema_version,
            "revision": record.revision,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "metadata": record.entity_metadata,
            "project_id": record.project_id,
            "resource_type": record.resource_type,
            "resource_id": record.resource_id,
            "owner_job_id": record.owner_job_id,
            "owner_session": record.owner_session,
            "acquired_at": record.acquired_at,
            "heartbeat_at": record.heartbeat_at,
            "lease_expires_at": record.lease_expires_at,
            "status": record.status,
        }
    )


class SqlAlchemyPermissionAuthority:
    """Server-side verifier; request-body permission lists never reach this authority."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def issue(self, token: PermissionToken, *, commit: bool = True) -> PermissionToken:
        record = PermissionTokenRecord(
            id=str(token.id),
            schema_version=token.schema_version,
            revision=token.revision,
            created_at=token.created_at,
            updated_at=token.updated_at,
            entity_metadata=token.metadata,
            project_id=str(token.project_id),
            actor_id=token.actor_id,
            permission=token.permission.value,
            resource_type=token.resource_type,
            resource_id=token.resource_id,
            issued_at=token.issued_at,
            expires_at=token.expires_at,
            status=token.status.value,
            session_id=str(token.session_id) if token.session_id else None,
            reason=token.reason,
            evidence_ids=[str(item) for item in token.evidence_ids],
        )
        self.session.add(record)
        self.session.flush()
        if commit:
            self.session.commit()
        return token

    def verify(self, context: PermissionVerificationContext) -> ValidatedPermissionGrant | None:
        record = self.session.get(PermissionTokenRecord, str(context.token_id))
        if record is None:
            return None
        token = PermissionToken.model_validate(
            {
                "id": record.id,
                "schema_version": record.schema_version,
                "revision": record.revision,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
                "metadata": record.entity_metadata,
                "project_id": record.project_id,
                "actor_id": record.actor_id,
                "permission": record.permission,
                "resource_type": record.resource_type,
                "resource_id": record.resource_id,
                "issued_at": record.issued_at,
                "expires_at": record.expires_at,
                "status": record.status,
                "session_id": record.session_id,
                "reason": record.reason,
                "evidence_ids": record.evidence_ids,
            }
        )
        if not token.is_valid(context.now):
            return None
        if (
            token.actor_id != context.actor_id
            or token.project_id != context.project_id
            or token.permission is not context.permission
            or token.resource_type != context.resource_type
            or token.resource_id != context.resource_id
            or (token.session_id is not None and token.session_id != context.session_id)
        ):
            return None
        return ValidatedPermissionGrant(
            token_id=token.id,
            actor_id=token.actor_id,
            project_id=token.project_id,
            permission=token.permission,
            resource_type=token.resource_type,
            resource_id=token.resource_id,
            session_id=token.session_id,
            verified_at=context.now,
        )


class SqlAlchemyCommissioningRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def commit(self) -> None:
        self.session.commit()

    def add_profile(
        self, profile: CommissioningProfile, *, commit: bool = True
    ) -> CommissioningProfile:
        existing = self.session.get(CommissioningProfileRecord, str(profile.id))
        if existing is not None:
            return _profile(existing)
        record = CommissioningProfileRecord(
            id=str(profile.id),
            schema_version=profile.schema_version,
            revision=profile.revision,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
            entity_metadata=profile.metadata,
            name=profile.name,
            version=profile.version,
            applicable_target_types=profile.applicable_target_types,
            applicable_domains=profile.applicable_domains,
            required_steps=profile.required_steps,
            required_permissions=[item.value for item in profile.required_permissions],
            user_approval_required=profile.user_approval_required,
            safety_limits=profile.safety_limits.model_dump(mode="json"),
            required_safety_capabilities=profile.required_safety_capabilities,
            watchdog_policy=profile.watchdog_policy,
            emergency_stop_policy=profile.emergency_stop_policy,
            safe_state_policy=profile.safe_state_policy.model_dump(mode="json"),
        )
        self.session.add(record)
        self.session.flush()
        if commit:
            self.session.commit()
        return _profile(record)

    def get_profile(self, profile_id: UUID) -> CommissioningProfile | None:
        record = self.session.get(CommissioningProfileRecord, str(profile_id))
        return _profile(record) if record else None

    def list_profiles(self) -> list[CommissioningProfile]:
        return [
            _profile(row)
            for row in self.session.scalars(
                select(CommissioningProfileRecord).order_by(CommissioningProfileRecord.name)
            )
        ]

    def add_session(self, session: HardwareCommissioningSession, *, commit: bool) -> None:
        record = CommissioningSessionRecord(
            id=str(session.id),
            schema_version=session.schema_version,
            revision=session.revision,
            created_at=session.created_at,
            updated_at=session.updated_at,
            entity_metadata=session.metadata,
            project_id=str(session.project_id),
            target_id=session.target_id,
            firmware_artifact_id=str(session.firmware_artifact_id),
            firmware_hash=session.firmware_hash,
            build_run_id=str(session.build_run_id) if session.build_run_id else None,
            source_revision_id=str(session.source_revision_id)
            if session.source_revision_id
            else None,
            build_input_snapshot_id=str(session.build_input_snapshot_id)
            if session.build_input_snapshot_id
            else None,
            hardware_identity=session.hardware_identity.model_dump(mode="json"),
            probe_identity=session.probe_identity.model_dump(mode="json"),
            board_revision=session.board_revision,
            commissioning_profile_id=str(session.commissioning_profile_id),
            state=session.state.value,
            current_step=session.current_step,
            started_by=session.started_by,
            approved_by=session.approved_by,
            safety_limits_snapshot=session.safety_limits_snapshot.model_dump(mode="json"),
            preflight_results=session.preflight_results,
            evidence_ids=[str(item) for item in session.evidence_ids],
            emergency_stop_state=session.emergency_stop_state.value,
            watchdog_state=session.watchdog_state.model_dump(mode="json"),
            resource_lock_ids=[str(item) for item in session.resource_lock_ids],
            permission_token_ids=session.permission_token_ids,
            approval_snapshot=session.approval_snapshot,
            completed_at=session.completed_at,
            aborted_at=session.aborted_at,
            active_action_id=str(session.active_action_id) if session.active_action_id else None,
            active_action_kind=session.active_action_kind,
            active_action_started_at=session.active_action_started_at,
            active_action_expected_revision=session.active_action_expected_revision,
            active_action_request_hash=session.active_action_request_hash,
            active_action_journal_id=(
                str(session.active_action_journal_id) if session.active_action_journal_id else None
            ),
        )
        self.session.add(record)
        self.session.add(
            SafetyLimitRecord(
                id=str(session.id),
                schema_version=session.schema_version,
                revision=session.revision,
                created_at=session.created_at,
                updated_at=session.updated_at,
                entity_metadata={},
                session_id=str(session.id),
                profile_id=str(session.commissioning_profile_id),
                snapshot=session.safety_limits_snapshot.model_dump(mode="json"),
                immutable=True,
            )
        )
        self.session.flush()
        if commit:
            self.session.commit()

    def get_session(
        self, session_id: UUID, *, project_id: UUID | None = None
    ) -> HardwareCommissioningSession | None:
        statement = select(CommissioningSessionRecord).where(
            CommissioningSessionRecord.id == str(session_id)
        )
        if project_id is not None:
            statement = statement.where(CommissioningSessionRecord.project_id == str(project_id))
        record = self.session.scalar(statement)
        if record is None:
            return None
        return _session(record, self.list_steps(session_id))

    def save_session(
        self, session: HardwareCommissioningSession, *, expected_revision: int, commit: bool
    ) -> bool:
        result = cast(
            CursorResult[Any],
            self.session.execute(
                update(CommissioningSessionRecord)
                .where(
                    CommissioningSessionRecord.id == str(session.id),
                    CommissioningSessionRecord.revision == expected_revision,
                )
                .values(
                    schema_version=session.schema_version,
                    revision=session.revision,
                    updated_at=session.updated_at,
                    entity_metadata=session.metadata,
                    state=session.state.value,
                    current_step=session.current_step,
                    approved_by=session.approved_by,
                    preflight_results=session.preflight_results,
                    evidence_ids=[str(item) for item in session.evidence_ids],
                    emergency_stop_state=session.emergency_stop_state.value,
                    watchdog_state=session.watchdog_state.model_dump(mode="json"),
                    approval_snapshot=session.approval_snapshot,
                    completed_at=session.completed_at,
                    aborted_at=session.aborted_at,
                    active_action_id=(
                        str(session.active_action_id) if session.active_action_id else None
                    ),
                    active_action_kind=session.active_action_kind,
                    active_action_started_at=session.active_action_started_at,
                    active_action_expected_revision=session.active_action_expected_revision,
                    active_action_request_hash=session.active_action_request_hash,
                    active_action_journal_id=(
                        str(session.active_action_journal_id)
                        if session.active_action_journal_id
                        else None
                    ),
                ),
            ),
        )
        if not isinstance(result, CursorResult) or result.rowcount != 1:
            self.session.rollback()
            return False
        if commit:
            self.session.commit()
        return True

    def list_steps(self, session_id: UUID) -> list[CommissioningStepResult]:
        rows = self.session.scalars(
            select(CommissioningStepResultRecord)
            .where(CommissioningStepResultRecord.session_id == str(session_id))
            .order_by(CommissioningStepResultRecord.created_at, CommissioningStepResultRecord.id)
        )
        return [_step(row) for row in rows]

    def add_step(self, step: CommissioningStepResult, *, commit: bool) -> None:
        existing = self.session.scalar(
            select(CommissioningStepResultRecord).where(
                CommissioningStepResultRecord.session_id == str(step.session_id),
                CommissioningStepResultRecord.step_id == step.step_id,
            )
        )
        if existing is not None:
            return
        self.session.add(
            CommissioningStepResultRecord(
                id=str(step.id),
                schema_version=step.schema_version,
                revision=step.revision,
                created_at=step.created_at,
                updated_at=step.updated_at,
                entity_metadata=step.metadata,
                session_id=str(step.session_id),
                step_id=step.step_id,
                status=step.status.value,
                started_at=step.started_at,
                completed_at=step.completed_at,
                measurements=step.measurements,
                thresholds=step.thresholds,
                evidence_ids=[str(item) for item in step.evidence_ids],
                tool_version=step.tool_version,
                rule_version=step.rule_version,
                operator=step.operator,
                failure_reason=step.failure_reason,
            )
        )
        self.session.flush()
        if commit:
            self.session.commit()

    def add_evidence(self, evidence: Evidence, *, commit: bool) -> Evidence:
        return SqlAlchemyEvidenceRepository(self.session).add(evidence, commit=commit)

    def add_emergency_stop(self, event: EmergencyStopEvent, *, commit: bool) -> None:
        existing = self.session.scalar(
            select(EmergencyStopEventRecord).where(
                EmergencyStopEventRecord.idempotency_key == event.idempotency_key
            )
        )
        if existing is not None:
            return
        self.session.add(
            EmergencyStopEventRecord(
                id=str(event.id),
                schema_version=event.schema_version,
                revision=event.revision,
                created_at=event.created_at,
                updated_at=event.updated_at,
                entity_metadata=event.metadata,
                session_id=str(event.session_id),
                source=event.source.value,
                reason=event.reason,
                safe_state_attempted=event.safe_state_attempted,
                safe_state_verified=event.safe_state_verified,
                quarantined_resource_ids=[str(item) for item in event.quarantined_resource_ids],
                evidence_ids=[str(item) for item in event.evidence_ids],
                idempotency_key=event.idempotency_key,
                actor=event.actor,
            )
        )
        self.session.flush()
        if commit:
            self.session.commit()

    def get_lock(self, lock_id: UUID) -> ResourceLock | None:
        record = self.session.get(ResourceLockRecord, str(lock_id))
        return _lock(record) if record else None

    def bind_lock(self, lock_id: UUID, *, project_id: UUID, session_id: UUID) -> bool:
        result = self.session.execute(
            update(ResourceLockRecord)
            .where(
                ResourceLockRecord.id == str(lock_id),
                ResourceLockRecord.project_id == str(project_id),
                ResourceLockRecord.status == ResourceLockStatus.ACTIVE.value,
                ResourceLockRecord.owner_session.is_(None),
            )
            .values(owner_session=str(session_id), updated_at=utc_now())
        )
        self.session.flush()
        return bool(getattr(result, "rowcount", 0) == 1)

    def acquire_lock(
        self,
        *,
        project_id: UUID,
        resource_type: ResourceType,
        resource_id: str,
        owner_session: UUID | None,
        owner_job_id: UUID | None = None,
        lease_seconds: int = 30,
    ) -> ResourceLock | None:
        """Acquire one exclusive resource with an atomic update/insert boundary."""

        now = utc_now()
        expires = now + timedelta(seconds=lease_seconds)
        existing = self.session.scalar(
            select(ResourceLockRecord).where(
                ResourceLockRecord.resource_type == resource_type.value,
                ResourceLockRecord.resource_id == resource_id,
                ResourceLockRecord.status == ResourceLockStatus.ACTIVE.value,
            )
        )
        if existing is not None:
            if existing.owner_session == (str(owner_session) if owner_session else None):
                existing.heartbeat_at = now
                existing.lease_expires_at = expires
                existing.updated_at = now
                self.session.flush()
                return _lock(existing)
            lease_expires_at = existing.lease_expires_at
            if lease_expires_at.tzinfo is None:
                lease_expires_at = lease_expires_at.replace(tzinfo=UTC)
            if lease_expires_at >= now:
                return None
            reclaimed = self.session.execute(
                update(ResourceLockRecord)
                .where(
                    ResourceLockRecord.id == existing.id,
                    ResourceLockRecord.status == ResourceLockStatus.ACTIVE.value,
                    ResourceLockRecord.lease_expires_at < now,
                )
                .values(
                    project_id=str(project_id),
                    owner_session=str(owner_session) if owner_session else None,
                    owner_job_id=str(owner_job_id) if owner_job_id else None,
                    acquired_at=now,
                    heartbeat_at=now,
                    lease_expires_at=expires,
                    revision=ResourceLockRecord.revision + 1,
                    updated_at=now,
                )
            )
            if getattr(reclaimed, "rowcount", 0) == 1:
                self.session.flush()
                refreshed = self.session.get(ResourceLockRecord, existing.id)
                return _lock(refreshed) if refreshed is not None else None
            return None
        record = ResourceLockRecord(
            id=str(uuid4()),
            schema_version="1.0",
            revision=1,
            created_at=now,
            updated_at=now,
            entity_metadata={},
            project_id=str(project_id),
            resource_type=resource_type.value,
            resource_id=resource_id,
            owner_job_id=str(owner_job_id) if owner_job_id else None,
            owner_session=str(owner_session) if owner_session else None,
            acquired_at=now,
            heartbeat_at=now,
            lease_expires_at=expires,
            status=ResourceLockStatus.ACTIVE.value,
        )
        try:
            with self.session.begin_nested():
                self.session.add(record)
                self.session.flush()
        except (IntegrityError, OperationalError):
            return None
        return _lock(record)

    def heartbeat_lock(
        self, lock_id: UUID, *, owner_session: UUID, lease_seconds: int = 30
    ) -> bool:
        now = utc_now()
        result = self.session.execute(
            update(ResourceLockRecord)
            .where(
                ResourceLockRecord.id == str(lock_id),
                ResourceLockRecord.status == ResourceLockStatus.ACTIVE.value,
                ResourceLockRecord.owner_session == str(owner_session),
            )
            .values(heartbeat_at=now, lease_expires_at=now + timedelta(seconds=lease_seconds))
        )
        self.session.flush()
        return bool(getattr(result, "rowcount", 0) == 1)

    def release_lock(self, lock_id: UUID, *, owner_session: UUID) -> bool:
        result = self.session.execute(
            update(ResourceLockRecord)
            .where(
                ResourceLockRecord.id == str(lock_id),
                ResourceLockRecord.status == ResourceLockStatus.ACTIVE.value,
                ResourceLockRecord.owner_session == str(owner_session),
            )
            .values(status=ResourceLockStatus.RELEASED.value, updated_at=utc_now())
        )
        self.session.flush()
        return bool(getattr(result, "rowcount", 0) == 1)

    def quarantine_lock(self, lock_id: UUID, *, commit: bool) -> bool:
        existing = self.session.get(ResourceLockRecord, str(lock_id))
        if existing is None:
            return False
        if existing.status == "QUARANTINED":
            return True
        if existing.status != "ACTIVE":
            return False
        result = cast(
            CursorResult[Any],
            self.session.execute(
                update(ResourceLockRecord)
                .where(
                    ResourceLockRecord.id == str(lock_id),
                    ResourceLockRecord.status == "ACTIVE",
                )
                .values(
                    status="QUARANTINED",
                    revision=ResourceLockRecord.revision + 1,
                    updated_at=utc_now(),
                )
            ),
        )
        if not isinstance(result, CursorResult) or result.rowcount != 1:
            self.session.rollback()
            return False
        self.session.flush()
        if commit:
            self.session.commit()
        return True

    def claim_hardware_action(
        self,
        *,
        session_id: UUID,
        expected_revision: int,
        expected_state: CommissioningState,
        action: str,
        request_hash: str,
        payload: dict[str, object],
    ) -> HardwareActionIntent | None:
        """Atomically claim a session and prepare its M18A side-effect journal."""

        now = utc_now()
        action_id = uuid4()
        journal_id = uuid4()
        event_service = EventOutboxService(SqlAlchemyOutboxRepository(self.session))
        result = self.session.execute(
            update(CommissioningSessionRecord)
            .where(
                CommissioningSessionRecord.id == str(session_id),
                CommissioningSessionRecord.revision == expected_revision,
                CommissioningSessionRecord.state == expected_state.value,
                CommissioningSessionRecord.active_action_id.is_(None),
            )
            .values(
                revision=expected_revision + 1,
                active_action_id=str(action_id),
                active_action_kind=action,
                active_action_started_at=now,
                active_action_expected_revision=expected_revision,
                active_action_request_hash=request_hash,
                active_action_journal_id=str(journal_id),
                updated_at=now,
            )
        )
        if getattr(result, "rowcount", 0) != 1:
            self.session.rollback()
            return None
        event = event_service.enqueue(
            event_type="commissioning.hardware_action.requested",
            aggregate_type="HardwareCommissioningSession",
            aggregate_id=str(session_id),
            event_key=f"commissioning.hardware-action:{session_id}:{expected_revision}:{action}",
            aggregate_revision=expected_revision + 1,
            project_id=payload.get("project_id"),
            payload={
                **payload,
                "session_id": str(session_id),
                "action_id": str(action_id),
                "action": action,
                "expected_revision": expected_revision,
                "request_hash": request_hash,
                "journal_id": str(journal_id),
            },
            commit=False,
        )
        journal = SqlAlchemySideEffectJournalRepository(self.session).prepare(
            SideEffectJournal(
                id=journal_id,
                event_id=event.id,
                consumer_id="hardware-commissioning",
                effect_key=f"hardware-action:{action_id}",
                effect_type="commissioning.hardware-action",
                request_hash=request_hash,
                status=SideEffectStatus.PREPARED,
                prepared_at=now,
                updated_at=now,
            )
        )
        return HardwareActionIntent(
            action_id=action_id,
            session_id=session_id,
            action=action,
            expected_revision=expected_revision,
            claimed_revision=expected_revision + 1,
            request_hash=request_hash,
            event_id=event.id,
            journal_id=journal.id,
            started_at=now,
        )

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
    ) -> HardwareActionIntent | None:
        """Atomically preempt only an action already quarantined for reconciliation.

        A stale dangerous action remains unreplayed and visible in its original journal.  The
        safety action receives a new durable claim so EmergencyStop can be retried after a crash
        without weakening the normal single-owner hardware-action CAS.
        """

        stale_journal = self.session.get(SideEffectJournalRecord, str(stale_journal_id))
        if (
            stale_journal is None
            or stale_journal.status != SideEffectStatus.RECONCILE_REQUIRED.value
        ):
            return None
        now = utc_now()
        action_id = uuid4()
        journal_id = uuid4()
        result = self.session.execute(
            update(CommissioningSessionRecord)
            .where(
                CommissioningSessionRecord.id == str(session_id),
                CommissioningSessionRecord.revision == expected_revision,
                CommissioningSessionRecord.state == expected_state.value,
                CommissioningSessionRecord.active_action_id == str(stale_action_id),
                CommissioningSessionRecord.active_action_journal_id == str(stale_journal_id),
            )
            .values(
                revision=expected_revision + 1,
                active_action_id=str(action_id),
                active_action_kind=action,
                active_action_started_at=now,
                active_action_expected_revision=expected_revision,
                active_action_request_hash=request_hash,
                active_action_journal_id=str(journal_id),
                updated_at=now,
            )
        )
        if getattr(result, "rowcount", 0) != 1:
            self.session.rollback()
            return None
        event = EventOutboxService(SqlAlchemyOutboxRepository(self.session)).enqueue(
            event_type="commissioning.hardware_action.requested",
            aggregate_type="HardwareCommissioningSession",
            aggregate_id=str(session_id),
            event_key=f"commissioning.safety-preempt:{session_id}:{expected_revision}:{action}",
            aggregate_revision=expected_revision + 1,
            project_id=payload.get("project_id"),
            payload={
                **payload,
                "session_id": str(session_id),
                "action_id": str(action_id),
                "action": action,
                "expected_revision": expected_revision,
                "request_hash": request_hash,
                "journal_id": str(journal_id),
            },
            commit=False,
        )
        journal = SqlAlchemySideEffectJournalRepository(self.session).prepare(
            SideEffectJournal(
                id=journal_id,
                event_id=event.id,
                consumer_id="hardware-commissioning",
                effect_key=f"hardware-action:{action_id}",
                effect_type="commissioning.hardware-action",
                request_hash=request_hash,
                status=SideEffectStatus.PREPARED,
                prepared_at=now,
                updated_at=now,
            )
        )
        return HardwareActionIntent(
            action_id=action_id,
            session_id=session_id,
            action=action,
            expected_revision=expected_revision,
            claimed_revision=expected_revision + 1,
            request_hash=request_hash,
            event_id=event.id,
            journal_id=journal.id,
            started_at=now,
        )

    def finalize_hardware_action(
        self,
        intent: HardwareActionIntent,
        *,
        status: SideEffectStatus,
        result_ref: str | None = None,
        error: str | None = None,
    ) -> None:
        journal_repo = SqlAlchemySideEffectJournalRepository(self.session)
        item = journal_repo.get(
            intent.event_id, "hardware-commissioning", f"hardware-action:{intent.action_id}"
        )
        if item is None:
            raise ValueError("hardware action journal is missing")
        if status is SideEffectStatus.APPLIED:
            journal_repo.mark_applied(item, result_ref=result_ref, now=utc_now())
        elif status is SideEffectStatus.FAILED:
            journal_repo.mark_failed(item, error=error or "hardware action failed", now=utc_now())
        else:
            journal_repo.mark_reconcile_required(
                item, error=error or "hardware action outcome is unknown", now=utc_now()
            )

    def get_capability(self, target_id: str) -> TargetSafetyCapability | None:
        record = self.session.scalar(
            select(TargetSafetyCapabilityRecord).where(
                TargetSafetyCapabilityRecord.target_id == target_id
            )
        )
        if record is None:
            return None
        return TargetSafetyCapability.model_validate(record.capability)

    def artifact_hash(self, artifact_id: UUID) -> str | None:
        return self.session.scalar(
            select(ArtifactRecord.content_hash).where(ArtifactRecord.id == str(artifact_id))
        )

    def artifact_binding(self, artifact_id: UUID) -> dict[str, object] | None:
        record = self.session.get(ArtifactRecord, str(artifact_id))
        if record is None:
            return None
        return {
            "project_id": record.project_id,
            "content_hash": record.content_hash,
            "status": record.status,
        }

    def build_binding(self, build_run_id: UUID) -> dict[str, object] | None:
        record = self.session.get(BuildRunRecord, str(build_run_id))
        if record is None:
            return None
        source = self.session.get(SourceRevisionRecord, record.source_revision_id)
        snapshot = self.session.get(BuildInputSnapshotRecord, record.build_input_snapshot_id)
        return {
            "status": record.status,
            "project_id": record.project_id,
            "source_revision_id": record.source_revision_id,
            "build_input_snapshot_id": record.build_input_snapshot_id,
            "source_revision_project_id": source.project_id if source else None,
            "build_input_project_id": snapshot.project_id if snapshot else None,
            "build_input_source_revision_id": (snapshot.source_revision_id if snapshot else None),
        }


__all__ = ["SqlAlchemyCommissioningRepository"]
