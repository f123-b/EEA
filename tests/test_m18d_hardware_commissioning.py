"""M18D Hardware Commissioning & Safety contract and recovery regressions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from eea_adapters.hardware import FakeHardwareCommissioningAdapter
from eea_application.commissioning import CommissioningService, build_safe_commissioning_profile
from eea_application.reliability import EventOutboxService
from eea_application.resource_locks import ResourceLockService
from eea_backend.commissioning_repositories import (
    SqlAlchemyCommissioningRepository,
    SqlAlchemyPermissionAuthority,
)
from eea_backend.database import create_database_engine
from eea_backend.main import create_app
from eea_backend.models import (
    CommissioningSessionRecord,
    ResourceLockRecord,
    SideEffectJournalRecord,
    TargetSafetyCapabilityRecord,
)
from eea_backend.recovery import RecoveryService
from eea_backend.reliability_repositories import SqlAlchemyOutboxRepository
from eea_backend.repositories import SqlAlchemyArtifactRepository, SqlAlchemyProjectRepository
from eea_backend.settings import Settings
from eea_core.domain_extensions import CommissioningRuleContribution
from eea_core.entities import Artifact, Project
from eea_core.enums import ArtifactStatus, EngineeringDimension, EngineeringErrorCode, Permission
from eea_core.errors import EngineeringError
from eea_core.hardware import (
    CapabilityVerificationStatus,
    CommissioningState,
    EmergencyStopSource,
    HardwareAdapterResult,
    HardwareIdentity,
    ProbeIdentity,
    ResourceLock,
    ResourceLockStatus,
    ResourceType,
    SafetyLimit,
    TargetSafetyCapability,
)
from eea_core.reliability import OutboxEventStatus, SideEffectStatus, payload_sha256
from eea_core.security import (
    PermissionToken,
    PermissionTokenStatus,
    PermissionVerificationContext,
    ValidatedPermissionGrant,
)
from eea_core.units import UnitNormalizationService
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

PERMISSIONS = {Permission.FLASH, Permission.DEBUG, Permission.HARDWARE_CONTROL}
ACTUATOR_PERMISSIONS = PERMISSIONS | {Permission.ACTUATOR_ENABLE}


class FakePermissionAuthority:
    """Explicit test-only authority; production never trusts request permissions."""

    def verify(self, context: PermissionVerificationContext) -> ValidatedPermissionGrant:
        return ValidatedPermissionGrant(
            token_id=context.token_id,
            actor_id=context.actor_id,
            project_id=context.project_id,
            permission=context.permission,
            resource_type=context.resource_type,
            resource_id=context.resource_id,
            session_id=context.session_id,
        )


def _migrate(settings: Settings) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    command.upgrade(config, "head")


def _fixture(tmp_path: Path, *, with_lock: bool = True, failures: set[str] | None = None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    engine = create_database_engine(settings)
    project = Project(name="M18D hardware")
    artifact = Artifact(
        project_id=project.id,
        logical_name="firmware",
        artifact_type="ELF",
        version_label="1",
        content_hash="a" * 64,
        input_hash="b" * 64,
        storage_uri="memory://firmware.elf",
        created_by="test",
        status=ArtifactStatus.CURRENT,
    )
    profile = build_safe_commissioning_profile()
    identity = HardwareIdentity(
        probe_serial="probe-1",
        target_identifier="target-1",
        detected_mcu="STM32G431",
        usb_vid_pid="0483:3748",
        port_path="debug://probe-1",
        board_revision="A1",
    )
    probe = ProbeIdentity(serial="probe-1", port_path="debug://probe-1")
    capability = TargetSafetyCapability(
        command_heartbeat_supported=True,
        control_loop_watchdog_supported=True,
        hardware_enable_default_safe=True,
        fault_latch_supported=True,
        physical_estop_supported=True,
        verification_status=CapabilityVerificationStatus.VERIFIED,
    )
    lock = ResourceLock(
        project_id=project.id,
        resource_type=ResourceType.HARDWARE_TARGET,
        resource_id="target-1",
        owner_session=None,
        acquired_at=datetime.now(UTC),
        heartbeat_at=datetime.now(UTC),
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        status=ResourceLockStatus.ACTIVE,
    )
    with Session(engine) as session:
        SqlAlchemyProjectRepository(session).add(project, commit=False)
        SqlAlchemyArtifactRepository(session).add(artifact, commit=False)
        repo = SqlAlchemyCommissioningRepository(session)
        repo.add_profile(profile, commit=False)
        session.add(
            TargetSafetyCapabilityRecord(
                id=str(uuid4()),
                schema_version="1.0",
                revision=1,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                entity_metadata={},
                target_id="target-1",
                capability=capability.model_dump(mode="json"),
                verification_status=capability.verification_status.value,
            )
        )
        if with_lock:
            session.add(
                ResourceLockRecord(
                    id=str(lock.id),
                    schema_version=lock.schema_version,
                    revision=lock.revision,
                    created_at=lock.created_at,
                    updated_at=lock.updated_at,
                    entity_metadata={},
                    project_id=str(project.id),
                    resource_type=lock.resource_type.value,
                    resource_id=lock.resource_id,
                    owner_job_id=None,
                    owner_session=None,
                    acquired_at=lock.acquired_at,
                    heartbeat_at=lock.heartbeat_at,
                    lease_expires_at=lock.lease_expires_at,
                    status=lock.status.value,
                )
            )
        session.commit()
    adapter = FakeHardwareCommissioningAdapter(identity, probe, failures=failures or set())
    test_permission_token_ids = [str(uuid4()) for _ in ACTUATOR_PERMISSIONS]
    with Session(engine) as session:
        repo = SqlAlchemyCommissioningRepository(session)
        service = CommissioningService(
            repo,
            adapter,
            outbox=EventOutboxService(SqlAlchemyOutboxRepository(session)),
            artifact_hash=repo.artifact_hash,
            lock_lookup=repo.get_lock,
            capability_lookup=repo.get_capability,
            permission_authority=FakePermissionAuthority(),
        )
        session_entity = service.create_session(
            project_id=project.id,
            target_id="target-1",
            firmware_artifact_id=artifact.id,
            firmware_hash=artifact.content_hash,
            hardware_identity=identity,
            probe_identity=probe,
            commissioning_profile=profile,
            started_by="operator",
            build_run_id=uuid4(),
            source_revision_id=uuid4(),
            build_input_snapshot_id=uuid4(),
            resource_lock_ids=[lock.id] if with_lock else [],
            permission_token_ids=test_permission_token_ids,
        )
        yield settings, engine, project, artifact, adapter, session_entity


def _service_for(engine, adapter):
    session = Session(engine)
    repo = SqlAlchemyCommissioningRepository(session)
    return (
        session,
        repo,
        CommissioningService(
            repo,
            adapter,
            outbox=EventOutboxService(SqlAlchemyOutboxRepository(session)),
            artifact_hash=repo.artifact_hash,
            lock_lookup=repo.get_lock,
            capability_lookup=repo.get_capability,
            permission_authority=FakePermissionAuthority(),
        ),
    )


class _CountingAdapter(FakeHardwareCommissioningAdapter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.flash_calls = 0
        self.limited_step_calls = 0

    def flash(self, firmware_hash: str) -> HardwareAdapterResult:
        self.flash_calls += 1
        return super().flash(firmware_hash)

    def execute_limited_step(self, step_id: str, limits: SafetyLimit) -> HardwareAdapterResult:
        self.limited_step_calls += 1
        return super().execute_limited_step(step_id, limits)


def _authority_service(engine, adapter):
    session = Session(engine)
    repository = SqlAlchemyCommissioningRepository(session)
    return (
        session,
        repository,
        CommissioningService(
            repository,
            adapter,
            outbox=EventOutboxService(SqlAlchemyOutboxRepository(session)),
            artifact_hash=repository.artifact_hash,
            lock_lookup=repository.get_lock,
            capability_lookup=repository.get_capability,
            permission_authority=SqlAlchemyPermissionAuthority(session),
        ),
    )


def _issue_tokens(
    engine,
    created,
    permissions: set[Permission],
    *,
    actor: str = "operator",
    project_id=None,
    resource_id: str | None = None,
    expires_at: datetime | None = None,
    status: PermissionTokenStatus = PermissionTokenStatus.ACTIVE,
) -> list[str]:
    with Session(engine) as session:
        authority = SqlAlchemyPermissionAuthority(session)
        token_ids: list[str] = []
        for permission in permissions:
            token = PermissionToken(
                project_id=project_id or created.project_id,
                actor_id=actor,
                permission=permission,
                resource_type="HardwareTarget",
                resource_id=resource_id or created.target_id,
                expires_at=expires_at or datetime.now(UTC) + timedelta(hours=1),
                status=status,
                session_id=created.id,
            )
            authority.issue(token, commit=False)
            token_ids.append(str(token.id))
        record = session.get(CommissioningSessionRecord, str(created.id))
        assert record is not None
        record.permission_token_ids = token_ids
        session.commit()
        return token_ids


def _full_limited_measurements(*, iq: float = 0.1, id_value: float = 0.1) -> dict[str, object]:
    return {
        "phase_current": {"value": 0.1, "unit": "A", "dimension": "CURRENT"},
        "iq": {"value": iq, "unit": "A", "dimension": "CURRENT"},
        "id": {"value": id_value, "unit": "A", "dimension": "CURRENT"},
        "speed": {"value": 0.5, "unit": "rpm", "dimension": "ANGULAR_VELOCITY"},
        "duty_cycle": 0.05,
        "bus_voltage": {"value": 12, "unit": "V", "dimension": "VOLTAGE"},
        "temperature": {"value": 25, "unit": "C", "dimension": "TEMPERATURE"},
        "pwm_enable_duration": {"value": 0.1, "unit": "s", "dimension": "TIME"},
        "current_ramp_rate": {"value": 0.1, "unit": "A/s", "dimension": "CURRENT_RATE"},
        "speed_ramp_rate": {
            "value": 10,
            "unit": "rpm/s",
            "dimension": "ANGULAR_ACCELERATION",
        },
        "encoder_direction": True,
        "encoder_plausibility": True,
        "electrical_angle_sign": True,
        "phase_sequence": True,
        "current_sense": True,
        "adc_sampling_window": True,
        "pwm_output_safety": True,
        "speed_feedback_sign": True,
        "pi_saturation": True,
        "startup_alignment": True,
        "current_offset": True,
        "gate_driver_fault": True,
        "watchdog": True,
        "emergency_stop": True,
    }


def _reach_user_approval(tmp_path: Path):
    fixture, db_session, service, sensor = _reach_low_power(tmp_path)
    low = service.execute_step(
        sensor.id,
        "LOW_POWER",
        expected_revision=sensor.revision,
        permissions=ACTUATOR_PERMISSIONS,
        operator="operator",
    )
    closed = service.execute_step(
        low.id,
        "CLOSED_LOOP_LIMITED",
        expected_revision=low.revision,
        permissions=ACTUATOR_PERMISSIONS,
        operator="operator",
    )
    approved = service.approve(
        closed.id,
        expected_revision=closed.revision,
        actor="operator",
        permissions=ACTUATOR_PERMISSIONS,
    )
    return fixture, db_session, service, approved


def test_session_defaults_safe_and_binds_source_authority(tmp_path: Path) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, _, artifact, _, created = fixture
    assert created.state is CommissioningState.CREATED
    assert created.safety_limits_snapshot.safe_output_state.pwm_disabled
    assert created.safety_limits_snapshot.safe_output_state.actuator_disabled
    assert created.source_revision_id is not None
    assert created.build_input_snapshot_id is not None
    with Session(engine) as session:
        stored = SqlAlchemyCommissioningRepository(session).get_session(created.id)
        assert stored is not None
        assert stored.firmware_hash == artifact.content_hash


def test_source_authority_binding_is_exact_and_session_isolation_is_preserved(
    tmp_path: Path,
) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, project, _, adapter, created = fixture
    assert created.build_run_id is not None
    assert created.source_revision_id is not None
    assert created.build_input_snapshot_id is not None
    db_session, repo, _ = _service_for(engine, adapter)

    def build_binding(build_run_id):
        if build_run_id != created.build_run_id:
            return None
        return {
            "status": "PASS",
            "project_id": str(project.id),
            "source_revision_id": str(created.source_revision_id),
            "build_input_snapshot_id": str(created.build_input_snapshot_id),
            "source_revision_project_id": str(project.id),
            "build_input_project_id": str(project.id),
            "build_input_source_revision_id": str(created.source_revision_id),
            # A newer workspace revision is allowed to exist; the session remains bound to
            # the exact immutable source/build snapshot used by its firmware artifact.
            "current_source_revision_id": str(uuid4()),
        }

    service = CommissioningService(
        repo,
        adapter,
        artifact_hash=repo.artifact_hash,
        artifact_binding=repo.artifact_binding,
        build_binding=build_binding,
        lock_lookup=repo.get_lock,
        capability_lookup=repo.get_capability,
        permission_authority=FakePermissionAuthority(),
    )
    preflight = service.preflight(
        created.id, expected_revision=created.revision, permissions=PERMISSIONS
    )
    assert preflight.state is CommissioningState.PREFLIGHT
    db_session.close()

    fixture2 = next(_fixture(tmp_path / "mismatched-build"))
    _, engine2, _, _, adapter2, created2 = fixture2
    db_session2, repo2, _ = _service_for(engine2, adapter2)
    assert created2.source_revision_id is not None
    assert created2.build_input_snapshot_id is not None
    mismatch = {
        "status": "PASS",
        "project_id": str(project.id),
        "source_revision_id": str(uuid4()),
        "build_input_snapshot_id": str(created2.build_input_snapshot_id),
        "source_revision_project_id": str(project.id),
        "build_input_project_id": str(project.id),
        "build_input_source_revision_id": str(uuid4()),
    }
    service2 = CommissioningService(
        repo2,
        adapter2,
        artifact_hash=repo2.artifact_hash,
        artifact_binding=repo2.artifact_binding,
        build_binding=lambda _: mismatch,
        lock_lookup=repo2.get_lock,
        capability_lookup=repo2.get_capability,
        permission_authority=FakePermissionAuthority(),
    )
    with pytest.raises(EngineeringError):
        service2.preflight(
            created2.id, expected_revision=created2.revision, permissions=PERMISSIONS
        )
    assert service2.get(created2.id).state is CommissioningState.BLOCKED
    db_session2.close()


def test_lock_heartbeat_loss_fails_closed_and_emergency_stop_quarantines_lock(
    tmp_path: Path,
) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, _, _, adapter, created = fixture
    _issue_tokens(engine, created, PERMISSIONS)
    db_session, _, service = _authority_service(engine, adapter)
    assert created.resource_lock_ids
    lock_record = db_session.get(ResourceLockRecord, str(created.resource_lock_ids[0]))
    assert lock_record is not None
    lock_record.heartbeat_at = datetime.now(UTC) - timedelta(minutes=10)
    db_session.commit()
    with pytest.raises(EngineeringError):
        service.preflight(created.id, expected_revision=created.revision, permissions=PERMISSIONS)
    assert service.get(created.id).state is CommissioningState.BLOCKED
    db_session.close()

    fixture2 = next(_fixture(tmp_path / "quarantine"))
    _, engine2, _, _, adapter2, created2 = fixture2
    db_session2, repo2, service2 = _service_for(engine2, adapter2)
    stopped = service2.emergency_stop(
        created2.id,
        expected_revision=created2.revision,
        permissions={Permission.HARDWARE_CONTROL},
        source=EmergencyStopSource.USER,
        actor="operator",
    )
    assert stopped.state is CommissioningState.EMERGENCY_STOP
    lock = db_session2.get(ResourceLockRecord, str(created2.resource_lock_ids[0]))
    assert lock is not None and lock.status == ResourceLockStatus.QUARANTINED.value
    assert repo2.get_lock(created2.resource_lock_ids[0]).status is ResourceLockStatus.QUARANTINED
    db_session2.close()


def test_missing_permission_and_lock_fail_closed(tmp_path: Path) -> None:
    fixture = next(_fixture(tmp_path, with_lock=False))
    _, engine, _, _, adapter, created = fixture
    db_session, _, service = _service_for(engine, adapter)
    with pytest.raises(EngineeringError) as error:
        service.preflight(created.id, expected_revision=created.revision, permissions=set())
    assert error.value.code is EngineeringErrorCode.COMMISSIONING_BLOCKED
    assert service.get(created.id).state is CommissioningState.BLOCKED
    db_session.close()


def test_flash_permission_does_not_enable_actuator_and_safe_failure_is_not_success(
    tmp_path: Path,
) -> None:
    settings, engine, _, _, adapter, created = next(_fixture(tmp_path))
    del settings
    db_session, _, service = _service_for(engine, adapter)
    preflight = service.preflight(
        created.id, expected_revision=created.revision, permissions=PERMISSIONS
    )
    flashed = service.flash(
        preflight.id, expected_revision=preflight.revision, permissions=PERMISSIONS
    )
    assert flashed.state is CommissioningState.FLASHED_SAFE
    assert not adapter.pwm_enabled and not adapter.actuator_enabled
    db_session.close()

    settings2, engine2, _, _, adapter2, created2 = next(
        _fixture(tmp_path / "safe-fail", failures={"safe_state"})
    )
    del settings2
    db_session2, _, service2 = _service_for(engine2, adapter2)
    preflight2 = service2.preflight(
        created2.id, expected_revision=created2.revision, permissions=PERMISSIONS
    )
    failed = service2.flash(
        preflight2.id, expected_revision=preflight2.revision, permissions=PERMISSIONS
    )
    assert failed.state is CommissioningState.ROLLBACK_REQUIRED
    db_session2.close()


def test_identity_and_hash_drift_block_preflight(tmp_path: Path) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, _, _, adapter, created = fixture
    adapter.identity = adapter.identity.model_copy(update={"target_identifier": "other-target"})
    db_session, _, service = _service_for(engine, adapter)
    with pytest.raises(EngineeringError):
        service.preflight(created.id, expected_revision=created.revision, permissions=PERMISSIONS)
    assert service.get(created.id).state is CommissioningState.BLOCKED
    db_session.close()


def test_illegal_transition_and_sensor_failure_block_low_power(tmp_path: Path) -> None:
    fixture = next(_fixture(tmp_path, failures={"sensor"}))
    _, engine, _, _, adapter, created = fixture
    with pytest.raises(ValueError):
        created.transition(CommissioningState.NORMAL_OPERATION)
    db_session, _, service = _service_for(engine, adapter)
    preflight = service.preflight(
        created.id, expected_revision=created.revision, permissions=PERMISSIONS
    )
    flashed = service.flash(
        preflight.id, expected_revision=preflight.revision, permissions=PERMISSIONS
    )
    with pytest.raises(EngineeringError):
        service.execute_step(
            flashed.id,
            "SENSOR_CHECK",
            expected_revision=flashed.revision,
            permissions=PERMISSIONS,
            operator="operator",
        )
    assert service.get(created.id).state is CommissioningState.BLOCKED
    db_session.close()


def _reach_low_power(tmp_path: Path, failures: set[str] | None = None):
    fixture = next(_fixture(tmp_path, failures=failures))
    _, engine, _, _, adapter, created = fixture
    db_session, _, service = _service_for(engine, adapter)
    preflight = service.preflight(
        created.id, expected_revision=created.revision, permissions=PERMISSIONS
    )
    flashed = service.flash(
        preflight.id, expected_revision=preflight.revision, permissions=PERMISSIONS
    )
    sensor = service.execute_step(
        flashed.id,
        "SENSOR_CHECK",
        expected_revision=flashed.revision,
        permissions=PERMISSIONS,
        operator="operator",
    )
    return fixture, db_session, service, sensor


def test_low_power_and_closed_loop_require_actuator_permission(tmp_path: Path) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, _, _, adapter, created = fixture
    _issue_tokens(engine, created, PERMISSIONS)
    db_session, _, service = _authority_service(engine, adapter)
    preflight = service.preflight(
        created.id, expected_revision=created.revision, permissions=PERMISSIONS
    )
    flashed = service.flash(
        preflight.id, expected_revision=preflight.revision, permissions=PERMISSIONS
    )
    sensor = service.execute_step(
        flashed.id,
        "SENSOR_CHECK",
        expected_revision=flashed.revision,
        permissions=PERMISSIONS,
        operator="operator",
    )
    with pytest.raises(EngineeringError) as error:
        service.execute_step(
            sensor.id,
            "LOW_POWER",
            expected_revision=sensor.revision,
            permissions=PERMISSIONS,
            operator="operator",
        )
    assert error.value.code is EngineeringErrorCode.PERMISSION_REQUIRED
    db_session.close()


@pytest.mark.parametrize("failure", ["overcurrent", "overspeed"])
def test_limit_violation_enters_emergency_stop(tmp_path: Path, failure: str) -> None:
    fixture, db_session, service, sensor = _reach_low_power(tmp_path, {failure})
    _, _, _, _, adapter, _ = fixture
    if failure == "overcurrent":
        with pytest.raises(EngineeringError) as error:
            service.execute_step(
                sensor.id,
                "LOW_POWER",
                expected_revision=sensor.revision,
                permissions=ACTUATOR_PERMISSIONS,
                operator="operator",
            )
        assert error.value.code is EngineeringErrorCode.SAFETY_LIMIT_VIOLATION
    else:
        low_power = service.execute_step(
            sensor.id,
            "LOW_POWER",
            expected_revision=sensor.revision,
            permissions=ACTUATOR_PERMISSIONS,
            operator="operator",
        )
        with pytest.raises(EngineeringError) as error:
            service.execute_step(
                low_power.id,
                "CLOSED_LOOP_LIMITED",
                expected_revision=low_power.revision,
                permissions=ACTUATOR_PERMISSIONS,
                operator="operator",
            )
        assert error.value.code is EngineeringErrorCode.SAFETY_LIMIT_VIOLATION
    assert service.get(sensor.id).state is CommissioningState.EMERGENCY_STOP
    assert adapter.emergency_stop_calls == 1
    db_session.close()


def test_watchdog_loss_and_lock_loss_are_not_warnings(tmp_path: Path) -> None:
    fixture = next(_fixture(tmp_path, failures={"watchdog"}))
    _, engine, _, _, adapter, created = fixture
    db_session, _, service = _service_for(engine, adapter)
    with pytest.raises(EngineeringError):
        service.preflight(created.id, expected_revision=created.revision, permissions=PERMISSIONS)
    assert service.get(created.id).state is CommissioningState.BLOCKED
    db_session.close()


def test_cancel_and_emergency_stop_are_safe_and_idempotent(tmp_path: Path) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, _, _, adapter, created = fixture
    db_session, _, service = _service_for(engine, adapter)
    aborted = service.abort(
        created.id,
        expected_revision=created.revision,
        permissions={Permission.HARDWARE_CONTROL},
        actor="operator",
    )
    assert aborted.state is CommissioningState.ABORTED
    with pytest.raises(EngineeringError):
        service.emergency_stop(
            aborted.id,
            expected_revision=aborted.revision,
            permissions={Permission.HARDWARE_CONTROL},
            source=EmergencyStopSource.USER,
            actor="operator",
        )
    db_session.close()

    fixture2 = next(_fixture(tmp_path / "estop"))
    _, engine2, _, _, adapter2, created2 = fixture2
    db_session2, _, service2 = _service_for(engine2, adapter2)
    stopped = service2.emergency_stop(
        created2.id,
        expected_revision=created2.revision,
        permissions={Permission.HARDWARE_CONTROL},
        actor="operator",
    )
    repeated = service2.emergency_stop(
        stopped.id,
        expected_revision=stopped.revision,
        permissions={Permission.HARDWARE_CONTROL},
        actor="operator",
    )
    assert repeated.state is CommissioningState.EMERGENCY_STOP
    assert adapter2.emergency_stop_calls == 1
    db_session2.close()


def test_cas_stale_approval_and_limit_monotonicity(tmp_path: Path) -> None:
    fixture, db_session, service, sensor = _reach_low_power(tmp_path)
    _, _, _, _, _, _ = fixture
    low = service.execute_step(
        sensor.id,
        "LOW_POWER",
        expected_revision=sensor.revision,
        permissions=ACTUATOR_PERMISSIONS,
        operator="operator",
    )
    closed = service.execute_step(
        low.id,
        "CLOSED_LOOP_LIMITED",
        expected_revision=low.revision,
        permissions=ACTUATOR_PERMISSIONS,
        operator="operator",
    )
    approved = service.approve(
        closed.id,
        expected_revision=closed.revision,
        actor="human",
        permissions=ACTUATOR_PERMISSIONS,
    )
    with pytest.raises(EngineeringError) as error:
        service.enable_normal_operation(
            approved.id,
            expected_revision=closed.revision,
            permissions=ACTUATOR_PERMISSIONS,
            actor="human",
        )
    assert error.value.code is EngineeringErrorCode.REVISION_CONFLICT
    tighter = SafetyLimit.safe_commissioning().model_copy(
        update={"max_phase_current": SafetyLimit.safe_commissioning().max_phase_current}
    )
    assert tighter.is_equal_or_more_conservative_than(SafetyLimit.safe_commissioning())
    db_session.close()


def test_outbox_event_is_replayed_idempotently_and_evidence_persists(tmp_path: Path) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, _, _, adapter, created = fixture
    db_session, repo, service = _service_for(engine, adapter)
    stopped = service.emergency_stop(
        created.id,
        expected_revision=created.revision,
        permissions={Permission.HARDWARE_CONTROL},
        source=EmergencyStopSource.USER,
        actor="operator",
    )
    db_session.close()
    recovery = RecoveryService(lambda: Session(engine))
    summary = recovery.dispatch_ready_events(limit=100)
    assert summary["processed"] >= 1
    with Session(engine) as session:
        events = SqlAlchemyOutboxRepository(session).list(project_id=stopped.project_id)
        assert any(event.status is OutboxEventStatus.PROCESSED for event in events)
        stored = SqlAlchemyCommissioningRepository(session).get_session(stopped.id)
        assert stored is not None and stored.evidence_ids
        assert stored.state is CommissioningState.EMERGENCY_STOP
        assert repo is not None


def test_api_exposes_cas_commissioning_routes_and_keeps_default_safe(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    with TestClient(create_app(settings)) as client:
        project = client.post("/api/v1/projects", json={"name": "api commissioning"}).json()["data"]
        profiles = client.get(f"/api/v1/projects/{project['id']}/commissioning/profiles")
        assert profiles.status_code == 200
        assert profiles.json()["data"][0]["name"] == "SAFE_COMMISSIONING"
        response = client.post(
            f"/api/v1/projects/{project['id']}/commissioning/sessions",
            json={
                "target_id": "unconfigured-target",
                "firmware_artifact_id": str(uuid4()),
                "firmware_hash": "a" * 64,
                "hardware_identity": {"target_identifier": "unconfigured-target"},
                "probe_identity": {"serial": "unconfigured-probe"},
                "started_by": "api-test",
            },
        )
        assert response.status_code == 201
        assert response.json()["data"]["state"] == "CREATED"


def test_api_permission_spoof_is_ignored_and_dangerous_call_is_denied(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    with TestClient(create_app(settings)) as client:
        project = client.post("/api/v1/projects", json={"name": "spoof"}).json()["data"]
        created = client.post(
            f"/api/v1/projects/{project['id']}/commissioning/sessions",
            json={
                "target_id": "target-1",
                "firmware_artifact_id": str(uuid4()),
                "firmware_hash": "a" * 64,
                "hardware_identity": {"target_identifier": "target-1"},
                "probe_identity": {"serial": "probe-1"},
                "started_by": "spoofed-client-actor",
            },
        )
        assert created.status_code == 201
        session_id = created.json()["data"]["id"]
        denied = client.post(
            f"/api/v1/commissioning/sessions/{session_id}/preflight",
            json={
                "expected_revision": created.json()["data"]["revision"],
                "permissions": [permission.value for permission in ACTUATOR_PERMISSIONS],
            },
        )
        assert denied.status_code != 200


def test_permission_authority_enforces_token_separation_and_zero_flash_without_grant(
    tmp_path: Path,
) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, _, _, adapter, created = fixture
    db_session, _, service = _authority_service(engine, adapter)
    with pytest.raises(EngineeringError) as denied:
        service.preflight(
            created.id,
            expected_revision=created.revision,
            permissions=ACTUATOR_PERMISSIONS,
        )
    assert denied.value.code is EngineeringErrorCode.COMMISSIONING_BLOCKED
    assert adapter.pwm_enabled is False
    db_session.close()

    fixture2 = next(_fixture(tmp_path / "valid-tokens"))
    _, engine2, _, _, adapter2, created2 = fixture2
    _issue_tokens(engine2, created2, PERMISSIONS)
    db_session, _, service = _authority_service(engine2, adapter2)
    preflight = service.preflight(
        created2.id, expected_revision=created2.revision, permissions=set()
    )
    flashed = service.flash(preflight.id, expected_revision=preflight.revision, permissions=set())
    sensor = service.execute_step(
        flashed.id,
        "SENSOR_CHECK",
        expected_revision=flashed.revision,
        permissions=set(),
        operator="operator",
    )
    with pytest.raises(EngineeringError) as missing_actuator:
        service.execute_step(
            sensor.id,
            "LOW_POWER",
            expected_revision=sensor.revision,
            permissions=set(),
            operator="operator",
        )
    assert missing_actuator.value.code is EngineeringErrorCode.PERMISSION_REQUIRED
    assert adapter2.pwm_enabled is False
    db_session.close()


def test_actuator_token_cannot_authorize_flash(tmp_path: Path) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, _, _, adapter, created = fixture
    _issue_tokens(engine, created, {Permission.ACTUATOR_ENABLE})
    db_session, _, service = _authority_service(engine, adapter)
    with pytest.raises(EngineeringError) as denied:
        service.preflight(created.id, expected_revision=created.revision, permissions=set())
    assert denied.value.code is EngineeringErrorCode.COMMISSIONING_BLOCKED
    assert adapter.pwm_enabled is False
    db_session.close()


@pytest.mark.parametrize(
    ("permission", "project_id", "resource_id", "expires_at", "expected"),
    [
        (Permission.FLASH, None, "target-1", datetime.now(UTC) - timedelta(seconds=1), False),
        (Permission.FLASH, uuid4(), "target-1", None, False),
        (Permission.FLASH, None, "other-target", None, False),
    ],
)
def test_permission_token_scope_expiry_and_target_are_exact(
    tmp_path: Path,
    permission: Permission,
    project_id,
    resource_id: str,
    expires_at: datetime | None,
    expected: bool,
) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, project, _, _, created = fixture
    token_ids = _issue_tokens(
        engine,
        created,
        {permission},
        project_id=project.id,
        resource_id=resource_id,
        expires_at=expires_at,
    )
    with Session(engine) as session:
        grant = SqlAlchemyPermissionAuthority(session).verify(
            PermissionVerificationContext(
                token_id=UUID(token_ids[0]),
                actor_id="operator",
                project_id=project_id or project.id,
                permission=permission,
                resource_type="HardwareTarget",
                resource_id="target-1",
                session_id=created.id,
            )
        )
        assert (grant is not None) is expected


def test_resource_lock_acquisition_is_exclusive_across_sessions(tmp_path: Path) -> None:
    fixture = next(_fixture(tmp_path, with_lock=False))
    _, engine, project, _, _, created = fixture
    first_session = Session(engine)
    second_session = Session(engine)
    first = ResourceLockService(SqlAlchemyCommissioningRepository(first_session)).acquire(
        project_id=project.id,
        resource_type=ResourceType.HARDWARE_TARGET,
        resource_id="atomic-target",
        owner_session=created.id,
    )
    assert first.owner_session == created.id
    second_repo = SqlAlchemyCommissioningRepository(second_session)
    assert (
        second_repo.acquire_lock(
            project_id=project.id,
            resource_type=ResourceType.HARDWARE_TARGET,
            resource_id="atomic-target",
            owner_session=uuid4(),
        )
        is None
    )
    first_session.close()
    second_session.close()


def test_lock_from_other_session_and_wrong_resource_type_fail_closed(tmp_path: Path) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, project, artifact, adapter, created = fixture
    db_session, _repo, service = _service_for(engine, adapter)
    session_b = service.create_session(
        project_id=project.id,
        target_id=created.target_id,
        firmware_artifact_id=artifact.id,
        firmware_hash=artifact.content_hash,
        hardware_identity=created.hardware_identity,
        probe_identity=created.probe_identity,
        commissioning_profile=build_safe_commissioning_profile(),
        started_by="operator-b",
        resource_lock_ids=[],
    )
    record_b = db_session.get(CommissioningSessionRecord, str(session_b.id))
    assert record_b is not None and created.resource_lock_ids
    record_b.resource_lock_ids = [str(created.resource_lock_ids[0])]
    db_session.commit()
    with pytest.raises(EngineeringError):
        service.preflight(
            session_b.id, expected_revision=session_b.revision, permissions=PERMISSIONS
        )
    assert adapter.pwm_enabled is False

    lock = db_session.get(ResourceLockRecord, str(created.resource_lock_ids[0]))
    assert lock is not None
    lock.resource_type = ResourceType.DEBUG_PROBE.value
    db_session.commit()
    with pytest.raises(EngineeringError):
        service.preflight(created.id, expected_revision=created.revision, permissions=PERMISSIONS)
    db_session.close()


def test_concurrent_flash_claim_allows_one_adapter_call(tmp_path: Path) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, _, _, original_adapter, created = fixture
    adapter = _CountingAdapter(
        identity=original_adapter.identity,
        probe=original_adapter.probe,
    )
    session_a, _, service_a = _service_for(engine, adapter)
    preflight = service_a.preflight(
        created.id, expected_revision=created.revision, permissions=PERMISSIONS
    )
    session_b, _, service_b = _service_for(engine, adapter)
    flashed = service_a.flash(
        created.id, expected_revision=preflight.revision, permissions=PERMISSIONS
    )
    with pytest.raises(EngineeringError) as loser:
        service_b.flash(created.id, expected_revision=preflight.revision, permissions=PERMISSIONS)
    assert loser.value.code in {
        EngineeringErrorCode.REVISION_CONFLICT,
        EngineeringErrorCode.COMMISSIONING_BLOCKED,
    }
    assert flashed.state is CommissioningState.FLASHED_SAFE
    assert adapter.flash_calls == 1
    session_a.close()
    session_b.close()


def test_concurrent_low_power_claim_allows_one_adapter_call(tmp_path: Path) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, _, _, original_adapter, created = fixture
    adapter = _CountingAdapter(
        identity=original_adapter.identity,
        probe=original_adapter.probe,
    )
    session_a, _, service_a = _service_for(engine, adapter)
    preflight = service_a.preflight(
        created.id, expected_revision=created.revision, permissions=PERMISSIONS
    )
    flashed = service_a.flash(
        created.id, expected_revision=preflight.revision, permissions=PERMISSIONS
    )
    sensor = service_a.execute_step(
        flashed.id,
        "SENSOR_CHECK",
        expected_revision=flashed.revision,
        permissions=PERMISSIONS,
        operator="operator",
    )
    session_b, _, service_b = _service_for(engine, adapter)
    low = service_a.execute_step(
        sensor.id,
        "LOW_POWER",
        expected_revision=sensor.revision,
        permissions=ACTUATOR_PERMISSIONS,
        operator="operator",
    )
    with pytest.raises(EngineeringError) as loser:
        service_b.execute_step(
            sensor.id,
            "LOW_POWER",
            expected_revision=sensor.revision,
            permissions=ACTUATOR_PERMISSIONS,
            operator="operator",
        )
    assert loser.value.code is EngineeringErrorCode.REVISION_CONFLICT
    assert low.state is CommissioningState.LOW_POWER
    assert adapter.limited_step_calls == 1
    session_a.close()
    session_b.close()


def test_prepared_hardware_action_is_reconciled_without_blind_retry(tmp_path: Path) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, _, _, adapter, created = fixture
    db_session, repo, service = _service_for(engine, adapter)
    preflight = service.preflight(
        created.id, expected_revision=created.revision, permissions=PERMISSIONS
    )
    payload = {
        "project_id": str(created.project_id),
        "firmware_hash": created.firmware_hash,
        "resource_lock_ids": [str(item) for item in created.resource_lock_ids],
    }
    intent = repo.claim_hardware_action(
        session_id=created.id,
        expected_revision=preflight.revision,
        expected_state=CommissioningState.PREFLIGHT,
        action="FLASH",
        request_hash=payload_sha256(payload),
        payload=payload,
    )
    assert intent is not None
    db_session.commit()
    db_session.close()

    recovery = RecoveryService(lambda: Session(engine))
    summary = recovery.startup_recover(batch_limit=100)
    assert summary["hardware_actions"] == 1
    assert adapter.pwm_enabled is False
    with Session(engine) as session:
        journal = session.get(SideEffectJournalRecord, str(intent.journal_id))
        stored = SqlAlchemyCommissioningRepository(session).get_session(created.id)
        assert journal is not None
        assert journal.status == SideEffectStatus.RECONCILE_REQUIRED.value
        assert stored is not None
        assert stored.state is CommissioningState.ROLLBACK_REQUIRED


@pytest.mark.parametrize("failure", ["flash", "verify_flash", "flash_timeout"])
def test_flash_failure_verify_and_timeout_attempt_safe_state(tmp_path: Path, failure: str) -> None:
    fixture = next(_fixture(tmp_path, failures={failure}))
    _, engine, _, _, adapter, created = fixture
    db_session, _, service = _service_for(engine, adapter)
    preflight = service.preflight(
        created.id, expected_revision=created.revision, permissions=PERMISSIONS
    )
    failed = service.flash(
        preflight.id, expected_revision=preflight.revision, permissions=PERMISSIONS
    )
    assert failed.state in {
        CommissioningState.FAULTED,
        CommissioningState.ROLLBACK_REQUIRED,
    }
    assert adapter.safe_state_calls > 0
    assert adapter.emergency_stop_calls > 0
    assert adapter.pwm_enabled is False and adapter.actuator_enabled is False
    db_session.close()


@pytest.mark.parametrize("step", ["LOW_POWER", "CLOSED_LOOP_LIMITED"])
def test_limited_step_timeout_attempts_emergency_stop_and_safe_state(
    tmp_path: Path, step: str
) -> None:
    fixture, db_session, service, sensor = _reach_low_power(tmp_path)
    _, _, _, _, adapter, _ = fixture
    if step == "LOW_POWER":
        adapter.failures.add("low_power_timeout")
        expected_revision = sensor.revision
        source_id = sensor.id
    else:
        low = service.execute_step(
            sensor.id,
            "LOW_POWER",
            expected_revision=sensor.revision,
            permissions=ACTUATOR_PERMISSIONS,
            operator="operator",
        )
        adapter.failures.add("closed_loop_limited_timeout")
        expected_revision = low.revision
        source_id = low.id
    with pytest.raises(EngineeringError) as error:
        service.execute_step(
            source_id,
            step,
            expected_revision=expected_revision,
            permissions=ACTUATOR_PERMISSIONS,
            operator="operator",
        )
    failed = service.get(source_id)
    assert error.value.code is EngineeringErrorCode.COMMISSIONING_BLOCKED
    assert failed.state in {
        CommissioningState.FAULTED,
        CommissioningState.ROLLBACK_REQUIRED,
    }
    assert adapter.safe_state_calls > 0 and adapter.emergency_stop_calls > 0
    assert not adapter.pwm_enabled and not adapter.actuator_enabled
    db_session.close()


def test_safe_state_failure_requires_rollback_and_quarantines_lock(tmp_path: Path) -> None:
    fixture = next(_fixture(tmp_path, failures={"safe_state"}))
    _, engine, _, _, adapter, created = fixture
    db_session, _, service = _service_for(engine, adapter)
    preflight = service.preflight(
        created.id, expected_revision=created.revision, permissions=PERMISSIONS
    )
    failed = service.flash(
        preflight.id, expected_revision=preflight.revision, permissions=PERMISSIONS
    )
    assert failed.state is CommissioningState.ROLLBACK_REQUIRED
    lock = db_session.get(ResourceLockRecord, str(created.resource_lock_ids[0]))
    assert lock is not None and lock.status == ResourceLockStatus.QUARANTINED.value
    db_session.close()


def test_normal_operation_and_watchdog_estop_are_reachable(tmp_path: Path) -> None:
    fixture, db_session, service, approved = _reach_user_approval(tmp_path)
    _, _, _, _, adapter, _ = fixture
    normal = service.enable_normal_operation(
        approved.id,
        expected_revision=approved.revision,
        permissions=ACTUATOR_PERMISSIONS,
        actor="operator",
    )
    stopped = service.emergency_stop(
        normal.id,
        expected_revision=normal.revision,
        permissions=set(),
        source=EmergencyStopSource.USER,
        actor="operator",
    )
    assert stopped.state is CommissioningState.EMERGENCY_STOP
    assert adapter.emergency_stop_calls >= 1
    db_session.close()

    _fixture2, db_session2, service2, approved2 = _reach_user_approval(tmp_path / "watchdog")
    normal2 = service2.enable_normal_operation(
        approved2.id,
        expected_revision=approved2.revision,
        permissions=ACTUATOR_PERMISSIONS,
        actor="operator",
    )
    stopped2 = service2.handle_watchdog_loss(
        normal2.id,
        expected_revision=normal2.revision,
        permissions=set(),
    )
    assert stopped2.state is CommissioningState.EMERGENCY_STOP
    db_session2.close()


def test_rollback_required_can_retry_emergency_stop_and_estop_is_idempotent(
    tmp_path: Path,
) -> None:
    fixture = next(_fixture(tmp_path, failures={"safe_state"}))
    _, engine, _, _, adapter, created = fixture
    db_session, _, service = _service_for(engine, adapter)
    preflight = service.preflight(
        created.id, expected_revision=created.revision, permissions=PERMISSIONS
    )
    failed = service.flash(
        preflight.id, expected_revision=preflight.revision, permissions=PERMISSIONS
    )
    adapter.failures.clear()
    retried = service.emergency_stop(
        failed.id,
        expected_revision=failed.revision,
        permissions=set(),
        source=EmergencyStopSource.USER,
    )
    repeated = service.emergency_stop(
        retried.id,
        expected_revision=retried.revision,
        permissions=set(),
        source=EmergencyStopSource.USER,
    )
    assert retried.state is CommissioningState.EMERGENCY_STOP
    assert repeated.state is CommissioningState.EMERGENCY_STOP
    db_session.close()


def test_lock_expiry_during_action_cannot_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, db_session, service, sensor = _reach_low_power(tmp_path)
    _, engine, _, _, adapter, _ = fixture
    original = adapter.execute_limited_step

    def expire_lock(step_id: str, limits: SafetyLimit) -> HardwareAdapterResult:
        with Session(engine) as other_session:
            lock = other_session.get(ResourceLockRecord, str(sensor.resource_lock_ids[0]))
            assert lock is not None
            lock.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            other_session.commit()
        return original(step_id, limits)

    monkeypatch.setattr(adapter, "execute_limited_step", expire_lock)
    failed = service.execute_step(
        sensor.id,
        "LOW_POWER",
        expected_revision=sensor.revision,
        permissions=ACTUATOR_PERMISSIONS,
        operator="operator",
    )
    assert failed.state in {
        CommissioningState.FAULTED,
        CommissioningState.ROLLBACK_REQUIRED,
    }
    assert adapter.emergency_stop_calls > 0
    db_session.close()


def test_watchdog_loss_during_action_cannot_pass(tmp_path: Path) -> None:
    _fixture, db_session, service, sensor = _reach_low_power(tmp_path)
    _, _, _, _, adapter, _ = _fixture
    adapter.failures.add("watchdog")
    failed = service.execute_step(
        sensor.id,
        "LOW_POWER",
        expected_revision=sensor.revision,
        permissions=ACTUATOR_PERMISSIONS,
        operator="operator",
    )
    failed = service.get(sensor.id)
    assert failed.state in {
        CommissioningState.FAULTED,
        CommissioningState.ROLLBACK_REQUIRED,
    }
    assert adapter.emergency_stop_calls > 0
    db_session.close()


def test_active_motor_control_missing_rule_blocks_closed_loop(tmp_path: Path) -> None:
    fixture, db_session, service, sensor = _reach_low_power(tmp_path)
    _, _, _, _, adapter, _ = fixture
    service.composition_lookup = lambda _: (
        CommissioningRuleContribution(
            rule_id="motor-control.encoder-direction",
            version="test-1",
            measurement_key="missing_encoder_rule",
        ),
    )
    low = service.execute_step(
        sensor.id,
        "LOW_POWER",
        expected_revision=sensor.revision,
        permissions=ACTUATOR_PERMISSIONS,
        operator="operator",
    )
    failed = service.execute_step(
        low.id,
        "CLOSED_LOOP_LIMITED",
        expected_revision=low.revision,
        permissions=ACTUATOR_PERMISSIONS,
        operator="operator",
    )
    assert failed.state in {
        CommissioningState.FAULTED,
        CommissioningState.ROLLBACK_REQUIRED,
    }
    assert adapter.emergency_stop_calls > 0
    db_session.close()


def test_active_motor_control_passing_rule_allows_closed_loop(tmp_path: Path) -> None:
    _fixture, db_session, service, sensor = _reach_low_power(tmp_path)
    service.composition_lookup = lambda _: (
        CommissioningRuleContribution(
            rule_id="motor-control.encoder-direction",
            version="test-1",
            measurement_key="encoder_direction",
        ),
    )
    low = service.execute_step(
        sensor.id,
        "LOW_POWER",
        expected_revision=sensor.revision,
        permissions=ACTUATOR_PERMISSIONS,
        operator="operator",
    )
    closed = service.execute_step(
        low.id,
        "CLOSED_LOOP_LIMITED",
        expected_revision=low.revision,
        permissions=ACTUATOR_PERMISSIONS,
        operator="operator",
    )
    assert closed.state is CommissioningState.CLOSED_LOOP_LIMITED
    db_session.close()


def test_missing_mandatory_measurement_fails_closed(tmp_path: Path) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, _, _, adapter, created = fixture
    adapter.measurements["LOW_POWER"] = {
        "phase_current": {"value": 0.1, "unit": "A", "dimension": "CURRENT"}
    }
    db_session, _, service = _service_for(engine, adapter)
    preflight = service.preflight(
        created.id, expected_revision=created.revision, permissions=PERMISSIONS
    )
    flashed = service.flash(
        preflight.id, expected_revision=preflight.revision, permissions=PERMISSIONS
    )
    sensor = service.execute_step(
        flashed.id,
        "SENSOR_CHECK",
        expected_revision=flashed.revision,
        permissions=PERMISSIONS,
        operator="operator",
    )
    with pytest.raises(EngineeringError) as error:
        service.execute_step(
            sensor.id,
            "LOW_POWER",
            expected_revision=sensor.revision,
            permissions=ACTUATOR_PERMISSIONS,
            operator="operator",
        )
    failed = service.get(sensor.id)
    assert error.value.code is EngineeringErrorCode.SAFETY_LIMIT_VIOLATION
    assert failed.state in {
        CommissioningState.EMERGENCY_STOP,
        CommissioningState.FAULTED,
        CommissioningState.ROLLBACK_REQUIRED,
    }
    db_session.close()


def test_unit_mismatch_and_bus_voltage_breach_trigger_safe_stop(tmp_path: Path) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, _, _, adapter, created = fixture
    measurements = _full_limited_measurements()
    measurements["phase_current"] = {"value": 0.1, "unit": "V", "dimension": "VOLTAGE"}
    measurements["bus_voltage"] = {"value": 100, "unit": "V", "dimension": "VOLTAGE"}
    adapter.measurements["LOW_POWER"] = measurements
    db_session, _, service = _service_for(engine, adapter)
    preflight = service.preflight(
        created.id, expected_revision=created.revision, permissions=PERMISSIONS
    )
    flashed = service.flash(
        preflight.id, expected_revision=preflight.revision, permissions=PERMISSIONS
    )
    sensor = service.execute_step(
        flashed.id,
        "SENSOR_CHECK",
        expected_revision=flashed.revision,
        permissions=PERMISSIONS,
        operator="operator",
    )
    with pytest.raises(EngineeringError) as error:
        service.execute_step(
            sensor.id,
            "LOW_POWER",
            expected_revision=sensor.revision,
            permissions=ACTUATOR_PERMISSIONS,
            operator="operator",
        )
    failed = service.get(sensor.id)
    assert error.value.code is EngineeringErrorCode.SAFETY_LIMIT_VIOLATION
    assert failed.state in {
        CommissioningState.EMERGENCY_STOP,
        CommissioningState.FAULTED,
        CommissioningState.ROLLBACK_REQUIRED,
    }
    assert adapter.emergency_stop_calls > 0
    db_session.close()


@pytest.mark.parametrize("field", ["iq", "id"])
def test_dq_current_breach_triggers_safe_stop(tmp_path: Path, field: str) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, _, _, adapter, created = fixture
    limits = created.safety_limits_snapshot
    high = (
        limits.max_iq.require_normalized_nominal() * 2
        if field == "iq"
        else limits.max_id.require_normalized_nominal() * 2
    )
    measurements = (
        _full_limited_measurements(iq=high)
        if field == "iq"
        else _full_limited_measurements(id_value=high)
    )
    adapter.measurements["CLOSED_LOOP_LIMITED"] = measurements
    db_session, _, service = _service_for(engine, adapter)
    preflight = service.preflight(
        created.id, expected_revision=created.revision, permissions=PERMISSIONS
    )
    flashed = service.flash(
        preflight.id, expected_revision=preflight.revision, permissions=PERMISSIONS
    )
    sensor = service.execute_step(
        flashed.id,
        "SENSOR_CHECK",
        expected_revision=flashed.revision,
        permissions=PERMISSIONS,
        operator="operator",
    )
    low = service.execute_step(
        sensor.id,
        "LOW_POWER",
        expected_revision=sensor.revision,
        permissions=ACTUATOR_PERMISSIONS,
        operator="operator",
    )
    with pytest.raises(EngineeringError) as error:
        service.execute_step(
            low.id,
            "CLOSED_LOOP_LIMITED",
            expected_revision=low.revision,
            permissions=ACTUATOR_PERMISSIONS,
            operator="operator",
        )
    assert error.value.code is EngineeringErrorCode.SAFETY_LIMIT_VIOLATION
    assert adapter.emergency_stop_calls > 0
    db_session.close()


def test_runtime_safety_limit_breach_triggers_safe_stop(tmp_path: Path) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, _, _, adapter, created = fixture
    measurements = _full_limited_measurements()
    measurements["runtime_seconds"] = (
        created.safety_limits_snapshot.max_test_runtime.require_normalized_nominal() + 1
    )
    adapter.measurements["CLOSED_LOOP_LIMITED"] = measurements
    db_session, _, service = _service_for(engine, adapter)
    preflight = service.preflight(
        created.id, expected_revision=created.revision, permissions=PERMISSIONS
    )
    flashed = service.flash(
        preflight.id, expected_revision=preflight.revision, permissions=PERMISSIONS
    )
    sensor = service.execute_step(
        flashed.id,
        "SENSOR_CHECK",
        expected_revision=flashed.revision,
        permissions=PERMISSIONS,
        operator="operator",
    )
    low = service.execute_step(
        sensor.id,
        "LOW_POWER",
        expected_revision=sensor.revision,
        permissions=ACTUATOR_PERMISSIONS,
        operator="operator",
    )
    with pytest.raises(EngineeringError) as error:
        service.execute_step(
            low.id,
            "CLOSED_LOOP_LIMITED",
            expected_revision=low.revision,
            permissions=ACTUATOR_PERMISSIONS,
            operator="operator",
        )
    assert error.value.code is EngineeringErrorCode.SAFETY_LIMIT_VIOLATION
    assert adapter.emergency_stop_calls > 0
    db_session.close()


def test_approval_binding_becomes_stale_when_snapshot_changes(tmp_path: Path) -> None:
    fixture, db_session, service, approved = _reach_user_approval(tmp_path)
    approved.approval_snapshot = {
        **(approved.approval_snapshot or {}),
        "firmware_hash": "b" * 64,
    }
    assert db_session is not None
    assert service.repository.save_session(
        approved, expected_revision=approved.revision, commit=True
    )
    with pytest.raises(EngineeringError) as error:
        service.enable_normal_operation(
            approved.id,
            expected_revision=approved.revision,
            permissions=ACTUATOR_PERMISSIONS,
            actor="operator",
        )
    assert error.value.code is EngineeringErrorCode.COMMISSIONING_BLOCKED
    fixture[4].pwm_enabled = False
    db_session.close()


def test_missing_permission_authority_fails_closed_even_with_requested_permissions(
    tmp_path: Path,
) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, _, _, adapter, created = fixture
    session = Session(engine)
    repository = SqlAlchemyCommissioningRepository(session)
    service = CommissioningService(
        repository,
        adapter,
        artifact_hash=repository.artifact_hash,
        lock_lookup=repository.get_lock,
        capability_lookup=repository.get_capability,
        permission_authority=None,
    )
    with pytest.raises(EngineeringError) as error:
        service.preflight(
            created.id,
            expected_revision=created.revision,
            permissions=ACTUATOR_PERMISSIONS,
        )
    assert error.value.code is EngineeringErrorCode.COMMISSIONING_BLOCKED
    assert adapter.pwm_enabled is False and adapter.actuator_enabled is False
    session.close()


def test_explicit_fake_permission_authority_is_the_application_test_dependency(
    tmp_path: Path,
) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, _, _, adapter, created = fixture
    db_session, _, service = _service_for(engine, adapter)
    passed = service.preflight(
        created.id,
        expected_revision=created.revision,
        permissions=PERMISSIONS,
    )
    assert passed.state is CommissioningState.PREFLIGHT
    db_session.close()


def test_recovered_prepared_flash_is_preempted_by_estop_without_flash_retry(
    tmp_path: Path,
) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, _, _, original_adapter, created = fixture
    adapter = _CountingAdapter(identity=original_adapter.identity, probe=original_adapter.probe)
    db_session, repository, service = _service_for(engine, adapter)
    preflight = service.preflight(
        created.id,
        expected_revision=created.revision,
        permissions=PERMISSIONS,
    )
    intent = repository.claim_hardware_action(
        session_id=created.id,
        expected_revision=preflight.revision,
        expected_state=CommissioningState.PREFLIGHT,
        action="FLASH",
        request_hash=payload_sha256({"action": "FLASH", "session_id": str(created.id)}),
        payload={"project_id": str(created.project_id), "resource_lock_ids": []},
    )
    assert intent is not None
    db_session.commit()
    db_session.close()

    summary = RecoveryService(lambda: Session(engine)).startup_recover(batch_limit=100)
    assert summary["hardware_actions"] == 1
    recovery_session, _, recovery_service = _service_for(engine, adapter)
    recovered = recovery_service.get(created.id)
    stopped = recovery_service.emergency_stop(
        recovered.id,
        expected_revision=recovered.revision,
        permissions=set(),
        source=EmergencyStopSource.USER,
    )
    assert stopped.state is CommissioningState.EMERGENCY_STOP
    assert stopped.emergency_stop_state.value == "ACTIVE"
    assert adapter.flash_calls == 0
    assert adapter.emergency_stop_calls == 1
    assert intent is not None
    with Session(engine) as check:
        old_journal = check.get(SideEffectJournalRecord, str(intent.journal_id))
        assert old_journal is not None
        assert old_journal.status == SideEffectStatus.RECONCILE_REQUIRED.value
    recovery_session.close()


def test_recovered_prepared_low_power_is_preempted_without_limited_step_retry(
    tmp_path: Path,
) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, _, _, original_adapter, created = fixture
    adapter = _CountingAdapter(identity=original_adapter.identity, probe=original_adapter.probe)
    db_session, repository, service = _service_for(engine, adapter)
    preflight = service.preflight(
        created.id,
        expected_revision=created.revision,
        permissions=PERMISSIONS,
    )
    flashed = service.flash(
        preflight.id,
        expected_revision=preflight.revision,
        permissions=PERMISSIONS,
    )
    sensor = service.execute_step(
        flashed.id,
        "SENSOR_CHECK",
        expected_revision=flashed.revision,
        permissions=PERMISSIONS,
        operator="operator",
    )
    intent = repository.claim_hardware_action(
        session_id=created.id,
        expected_revision=sensor.revision,
        expected_state=CommissioningState.SENSOR_CHECK,
        action="LOW_POWER",
        request_hash=payload_sha256({"action": "LOW_POWER", "session_id": str(created.id)}),
        payload={"project_id": str(created.project_id), "resource_lock_ids": []},
    )
    assert intent is not None
    db_session.commit()
    db_session.close()

    summary = RecoveryService(lambda: Session(engine)).startup_recover(batch_limit=100)
    assert summary["hardware_actions"] == 1
    recovery_session, _, recovery_service = _service_for(engine, adapter)
    recovered = recovery_service.get(created.id)
    stopped = recovery_service.emergency_stop(
        recovered.id,
        expected_revision=recovered.revision,
        permissions=set(),
        source=EmergencyStopSource.USER,
    )
    assert stopped.state is CommissioningState.EMERGENCY_STOP
    assert adapter.limited_step_calls == 0
    assert adapter.emergency_stop_calls == 1
    recovery_session.close()


def test_recovered_prepared_emergency_stop_can_retry_safety_action(
    tmp_path: Path,
) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, _, _, original_adapter, created = fixture
    adapter = _CountingAdapter(identity=original_adapter.identity, probe=original_adapter.probe)
    db_session, repository, service = _service_for(engine, adapter)
    preflight = service.preflight(
        created.id,
        expected_revision=created.revision,
        permissions=PERMISSIONS,
    )
    intent = repository.claim_hardware_action(
        session_id=created.id,
        expected_revision=preflight.revision,
        expected_state=CommissioningState.PREFLIGHT,
        action="EMERGENCY_STOP",
        request_hash=payload_sha256({"action": "EMERGENCY_STOP", "session_id": str(created.id)}),
        payload={"project_id": str(created.project_id), "resource_lock_ids": []},
    )
    assert intent is not None
    db_session.commit()
    db_session.close()

    RecoveryService(lambda: Session(engine)).startup_recover(batch_limit=100)
    recovery_session, _, recovery_service = _service_for(engine, adapter)
    recovered = recovery_service.get(created.id)
    retried = recovery_service.emergency_stop(
        recovered.id,
        expected_revision=recovered.revision,
        permissions=set(),
        source=EmergencyStopSource.USER,
    )
    assert retried.state is CommissioningState.EMERGENCY_STOP
    assert adapter.emergency_stop_calls == 1
    recovery_session.close()


def test_unverified_safe_state_on_limit_violation_is_rollback_unknown(
    tmp_path: Path,
) -> None:
    fixture, db_session, service, sensor = _reach_low_power(tmp_path)
    _, _, _, _, adapter, _ = fixture
    adapter.failures.update({"overcurrent", "safe_state"})
    with pytest.raises(EngineeringError) as error:
        service.execute_step(
            sensor.id,
            "LOW_POWER",
            expected_revision=sensor.revision,
            permissions=ACTUATOR_PERMISSIONS,
            operator="operator",
        )
    failed = service.get(sensor.id)
    assert error.value.code is EngineeringErrorCode.SAFETY_LIMIT_VIOLATION
    assert failed.state is CommissioningState.ROLLBACK_REQUIRED
    assert failed.emergency_stop_state.value == "UNKNOWN"
    db_session.close()


def test_verified_safe_state_on_limit_violation_is_active_emergency_stop(
    tmp_path: Path,
) -> None:
    fixture, db_session, service, sensor = _reach_low_power(tmp_path, {"overcurrent"})
    _, _, _, _, adapter, _ = fixture
    with pytest.raises(EngineeringError):
        service.execute_step(
            sensor.id,
            "LOW_POWER",
            expected_revision=sensor.revision,
            permissions=ACTUATOR_PERMISSIONS,
            operator="operator",
        )
    failed = service.get(sensor.id)
    assert failed.state is CommissioningState.EMERGENCY_STOP
    assert failed.emergency_stop_state.value == "ACTIVE"
    assert adapter.pwm_enabled is False and adapter.actuator_enabled is False
    db_session.close()


@pytest.mark.parametrize(
    "field",
    ["pwm_enable_duration", "current_ramp_rate"],
)
def test_missing_low_power_safety_measurement_fails_closed(tmp_path: Path, field: str) -> None:
    fixture = next(_fixture(tmp_path))
    _, engine, _, _, adapter, created = fixture
    measurements = {
        "phase_current": {"value": 0.1, "unit": "A", "dimension": "CURRENT"},
        "duty_cycle": 0.05,
        "bus_voltage": {"value": 12, "unit": "V", "dimension": "VOLTAGE"},
        "temperature": {"value": 25, "unit": "C", "dimension": "TEMPERATURE"},
        "pwm_enable_duration": {"value": 0.1, "unit": "s", "dimension": "TIME"},
        "current_ramp_rate": {
            "value": 0.1,
            "unit": "A/s",
            "dimension": "CURRENT_RATE",
        },
    }
    measurements.pop(field)
    adapter.measurements["LOW_POWER"] = measurements
    db_session, _, service = _service_for(engine, adapter)
    preflight = service.preflight(
        created.id, expected_revision=created.revision, permissions=PERMISSIONS
    )
    flashed = service.flash(
        preflight.id, expected_revision=preflight.revision, permissions=PERMISSIONS
    )
    sensor = service.execute_step(
        flashed.id,
        "SENSOR_CHECK",
        expected_revision=flashed.revision,
        permissions=PERMISSIONS,
        operator="operator",
    )
    with pytest.raises(EngineeringError) as error:
        service.execute_step(
            sensor.id,
            "LOW_POWER",
            expected_revision=sensor.revision,
            permissions=ACTUATOR_PERMISSIONS,
            operator="operator",
        )
    assert error.value.code is EngineeringErrorCode.SAFETY_LIMIT_VIOLATION
    assert service.get(sensor.id).state is CommissioningState.EMERGENCY_STOP
    db_session.close()


def test_pwm_enable_duration_and_current_ramp_limit_breaches_stop_safely(
    tmp_path: Path,
) -> None:
    fixture, db_session, service, sensor = _reach_low_power(tmp_path)
    _, _, _, _, adapter, _ = fixture
    adapter.measurements["LOW_POWER"] = {
        "phase_current": {"value": 0.1, "unit": "A", "dimension": "CURRENT"},
        "duty_cycle": 0.05,
        "bus_voltage": {"value": 12, "unit": "V", "dimension": "VOLTAGE"},
        "temperature": {"value": 25, "unit": "C", "dimension": "TEMPERATURE"},
        "pwm_enable_duration": {"value": 2, "unit": "s", "dimension": "TIME"},
        "current_ramp_rate": {"value": 2, "unit": "A/s", "dimension": "CURRENT_RATE"},
    }
    with pytest.raises(EngineeringError) as error:
        service.execute_step(
            sensor.id,
            "LOW_POWER",
            expected_revision=sensor.revision,
            permissions=ACTUATOR_PERMISSIONS,
            operator="operator",
        )
    assert error.value.code is EngineeringErrorCode.SAFETY_LIMIT_VIOLATION
    assert service.get(sensor.id).emergency_stop_state.value == "ACTIVE"
    db_session.close()


def test_missing_or_excessive_closed_loop_speed_ramp_fails_closed(
    tmp_path: Path,
) -> None:
    fixture, db_session, service, sensor = _reach_low_power(tmp_path)
    _, _, _, _, adapter, _ = fixture
    low = service.execute_step(
        sensor.id,
        "LOW_POWER",
        expected_revision=sensor.revision,
        permissions=ACTUATOR_PERMISSIONS,
        operator="operator",
    )
    measurements = _full_limited_measurements()
    measurements.pop("speed_ramp_rate")
    adapter.measurements["CLOSED_LOOP_LIMITED"] = measurements
    with pytest.raises(EngineeringError) as missing_error:
        service.execute_step(
            low.id,
            "CLOSED_LOOP_LIMITED",
            expected_revision=low.revision,
            permissions=ACTUATOR_PERMISSIONS,
            operator="operator",
        )
    assert missing_error.value.code is EngineeringErrorCode.SAFETY_LIMIT_VIOLATION

    fixture2, db_session2, service2, sensor2 = _reach_low_power(tmp_path / "excessive")
    _, _, _, _, adapter2, _ = fixture2
    low2 = service2.execute_step(
        sensor2.id,
        "LOW_POWER",
        expected_revision=sensor2.revision,
        permissions=ACTUATOR_PERMISSIONS,
        operator="operator",
    )
    excessive = _full_limited_measurements()
    excessive["speed_ramp_rate"] = {
        "value": 1000,
        "unit": "rpm/s",
        "dimension": "ANGULAR_ACCELERATION",
    }
    adapter2.measurements["CLOSED_LOOP_LIMITED"] = excessive
    with pytest.raises(EngineeringError) as excessive_error:
        service2.execute_step(
            low2.id,
            "CLOSED_LOOP_LIMITED",
            expected_revision=low2.revision,
            permissions=ACTUATOR_PERMISSIONS,
            operator="operator",
        )
    assert excessive_error.value.code is EngineeringErrorCode.SAFETY_LIMIT_VIOLATION
    db_session.close()
    db_session2.close()


def test_test_runtime_and_pwm_enable_duration_are_independent_limits(tmp_path: Path) -> None:
    fixture, db_session, service, sensor = _reach_low_power(tmp_path)
    _, _, _, _, adapter, _ = fixture
    low_measurements = {
        **_full_limited_measurements(),
        "runtime_seconds": 2.0,
        "pwm_enable_duration": {"value": 0.5, "unit": "s", "dimension": "TIME"},
    }
    adapter.measurements["LOW_POWER"] = low_measurements
    low = service.execute_step(
        sensor.id,
        "LOW_POWER",
        expected_revision=sensor.revision,
        permissions=ACTUATOR_PERMISSIONS,
        operator="operator",
    )
    assert low.state is CommissioningState.LOW_POWER
    closed_measurements = {
        **_full_limited_measurements(),
        "runtime_seconds": 2.0,
        "pwm_enable_duration": {"value": 1.5, "unit": "s", "dimension": "TIME"},
    }
    adapter.measurements["CLOSED_LOOP_LIMITED"] = closed_measurements
    with pytest.raises(EngineeringError) as error:
        service.execute_step(
            low.id,
            "CLOSED_LOOP_LIMITED",
            expected_revision=low.revision,
            permissions=ACTUATOR_PERMISSIONS,
            operator="operator",
        )
    assert error.value.code is EngineeringErrorCode.SAFETY_LIMIT_VIOLATION
    assert service.get(low.id).state is CommissioningState.EMERGENCY_STOP
    db_session.close()


def test_rpm_per_second_normalizes_to_angular_acceleration() -> None:
    assert UnitNormalizationService.normalize(
        60,
        "rpm/s",
        EngineeringDimension.ANGULAR_ACCELERATION,
    ) == pytest.approx(2 * 3.141592653589793)
