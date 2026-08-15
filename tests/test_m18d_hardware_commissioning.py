"""M18D Hardware Commissioning & Safety contract and recovery regressions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from eea_adapters.hardware import FakeHardwareCommissioningAdapter
from eea_application.commissioning import CommissioningService, build_safe_commissioning_profile
from eea_application.reliability import EventOutboxService
from eea_backend.commissioning_repositories import SqlAlchemyCommissioningRepository
from eea_backend.database import create_database_engine
from eea_backend.main import create_app
from eea_backend.models import (
    ResourceLockRecord,
    TargetSafetyCapabilityRecord,
)
from eea_backend.recovery import RecoveryService
from eea_backend.reliability_repositories import SqlAlchemyOutboxRepository
from eea_backend.repositories import SqlAlchemyArtifactRepository, SqlAlchemyProjectRepository
from eea_backend.settings import Settings
from eea_core.entities import Artifact, Project
from eea_core.enums import ArtifactStatus, EngineeringErrorCode, Permission
from eea_core.errors import EngineeringError
from eea_core.hardware import (
    CapabilityVerificationStatus,
    CommissioningState,
    EmergencyStopSource,
    HardwareIdentity,
    ProbeIdentity,
    ResourceLock,
    ResourceLockStatus,
    ResourceType,
    SafetyLimit,
    TargetSafetyCapability,
)
from eea_core.reliability import OutboxEventStatus
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

PERMISSIONS = {Permission.FLASH, Permission.DEBUG, Permission.HARDWARE_CONTROL}
ACTUATOR_PERMISSIONS = PERMISSIONS | {Permission.ACTUATOR_ENABLE}


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
    with Session(engine) as session:
        repo = SqlAlchemyCommissioningRepository(session)
        service = CommissioningService(
            repo,
            adapter,
            outbox=EventOutboxService(SqlAlchemyOutboxRepository(session)),
            artifact_hash=repo.artifact_hash,
            lock_lookup=repo.get_lock,
            capability_lookup=repo.get_capability,
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
        ),
    )


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
    db_session, _, service = _service_for(engine, adapter)
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
