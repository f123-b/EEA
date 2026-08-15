"""SQLAlchemy adapters for the M18D commissioning contracts."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from eea_core.entities import Evidence
from eea_core.hardware import (
    CommissioningProfile,
    CommissioningStepResult,
    EmergencyStopEvent,
    HardwareCommissioningSession,
    ResourceLock,
    TargetSafetyCapability,
)
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from eea_backend.models import (
    CommissioningProfileRecord,
    CommissioningSessionRecord,
    CommissioningStepResultRecord,
    EmergencyStopEventRecord,
    ResourceLockRecord,
    SafetyLimitRecord,
    TargetSafetyCapabilityRecord,
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
                ),
            ),
        )
        if result.rowcount != 1:
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
        from eea_backend.models import ArtifactRecord

        return self.session.scalar(
            select(ArtifactRecord.content_hash).where(ArtifactRecord.id == str(artifact_id))
        )

    def build_binding(self, build_run_id: UUID) -> dict[str, object] | None:
        from eea_backend.models import BuildRunRecord

        record = self.session.get(BuildRunRecord, str(build_run_id))
        if record is None:
            return None
        return {
            "status": record.status,
            "source_revision_id": record.source_revision_id,
            "build_input_snapshot_id": record.build_input_snapshot_id,
        }


__all__ = ["SqlAlchemyCommissioningRepository"]
