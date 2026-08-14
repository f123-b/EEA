"""M18A focused acceptance coverage: durable events, recovery, and idempotency."""

import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from time import sleep
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest
from alembic import command
from alembic.config import Config
from eea_application.reliability import (
    CrashPoint,
    EventOutboxService,
    HandlerRegistration,
    InjectedCrashError,
    OutboxHandlerRegistry,
    new_recovery_worker_id,
)
from eea_backend.database import create_database_engine
from eea_backend.main import create_app
from eea_backend.models import (
    ArtifactRecord,
    EngineeringDependencyNodeStateRecord,
    JobRecord,
    OutboxEventRecord,
    ProcessedEventRecord,
    ProjectRecord,
    SideEffectJournalRecord,
)
from eea_backend.recovery import OutboxDispatcher, RecoveryService
from eea_backend.reliability_repositories import (
    BusyRetryPolicy,
    SqlAlchemyOutboxRepository,
    SqlAlchemyProcessedEventRepository,
    SqlAlchemySideEffectJournalRepository,
)
from eea_backend.repositories import SqlAlchemyArtifactRepository
from eea_backend.settings import Settings
from eea_core.entities import Artifact, Project, utc_now
from eea_core.enums import ArtifactStatus, DependencyNodeStatus, JobStatus
from eea_core.reliability import (
    OutboxEvent,
    OutboxEventStatus,
    ProcessedEvent,
    SideEffectJournal,
    SideEffectStatus,
    payload_sha256,
    stable_event_key,
)
from fastapi.testclient import TestClient
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session


def _migrate(settings: Settings) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    command.upgrade(config, "head")


class FrozenClock:
    def __init__(self) -> None:
        self.value = datetime.now(UTC)

    def now(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


class PointCrashInjector:
    def __init__(self, point: CrashPoint) -> None:
        self.point = point

    def maybe_crash(self, point: CrashPoint) -> None:
        if point is self.point:
            raise InjectedCrashError(point.value)


def _project_and_event(
    engine, *, event_type: str = "demo.event", payload: dict[str, object] | None = None
):
    project = Project(id=uuid4(), name="reliability")
    event_payload = {**(payload or {"value": "one"}), "project_id": str(project.id)}
    with Session(engine) as session:
        from eea_backend.repositories import SqlAlchemyProjectRepository

        SqlAlchemyProjectRepository(session).add(project, commit=True)
        event = EventOutboxService(SqlAlchemyOutboxRepository(session)).enqueue(
            event_type=event_type,
            aggregate_type="Project",
            aggregate_id=str(project.id),
            aggregate_revision=1,
            payload=event_payload,
            project_id=project.id,
            commit=True,
        )
    return project, event


def test_core_hash_and_stable_key() -> None:
    payload = {"b": 2, "a": "stable"}
    assert payload_sha256(payload) == payload_sha256({"a": "stable", "b": 2})
    assert stable_event_key("project.created", "Project", "p1", 1) == "project.created:Project:p1:1"


def test_project_business_and_outbox_commit_together(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/v1/projects", json={"name": "atomic"})
        assert response.status_code == 201
        project_id = response.json()["data"]["id"]
        with Session(create_database_engine(settings)) as session:
            project = session.get(
                __import__("eea_backend.models", fromlist=["ProjectRecord"]).ProjectRecord,
                project_id,
            )
            events = SqlAlchemyOutboxRepository(session).list()
            assert project is not None
            assert len(events) == 1
            assert events[0].event_type == "project.created"


def test_project_commit_crash_replay_and_api(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    application = create_app(settings)
    with TestClient(application) as client:
        created = client.post("/api/v1/projects", json={"name": "replay"}).json()["data"]
        application.state.outbox_dispatcher.dispatch_once()
        assert client.get("/api/v1/system/outbox/status").json()["data"]["processed"] == 1
        result = client.post("/api/v1/system/recovery/reconcile", json={"limit": 100})
        assert result.status_code == 200
        status = client.get("/api/v1/system/outbox/status").json()["data"]
        assert status["processed"] == 1
        assert (
            client.get(f"/api/v1/projects/{created['id']}/consistency").json()["data"]["status"]
            == "CONSISTENT"
        )


def test_api_rolls_back_business_row_and_outbox_before_commit(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    application = create_app(settings)
    application.state.crash_injector = PointCrashInjector(
        CrashPoint.AFTER_OUTBOX_INSERT_BEFORE_COMMIT
    )
    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.post("/api/v1/projects", json={"name": "rolled-back"})
        assert response.status_code == 500
    with Session(create_database_engine(settings)) as session:
        assert (
            session.scalar(select(ProjectRecord).where(ProjectRecord.name == "rolled-back")) is None
        )
        assert session.scalar(select(OutboxEventRecord)) is None


def test_api_commit_crash_is_replayed_by_new_startup(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    application = create_app(settings)
    application.state.crash_injector = PointCrashInjector(
        CrashPoint.AFTER_BUSINESS_COMMIT_BEFORE_DISPATCH
    )
    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.post("/api/v1/projects", json={"name": "committed-before-crash"})
        assert response.status_code == 500
    with TestClient(create_app(settings)):
        pass
    with Session(create_database_engine(settings)) as session:
        assert session.scalar(
            select(ProjectRecord).where(ProjectRecord.name == "committed-before-crash")
        )
        record = session.scalar(select(OutboxEventRecord))
        assert record is not None
        assert record.status == OutboxEventStatus.PROCESSED.value
        assert session.scalar(select(ProcessedEventRecord)) is not None


def test_unknown_handler_retries_then_dead_letters(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    engine = create_database_engine(settings)
    project_id = uuid4()
    with Session(engine) as session:
        from eea_backend.repositories import SqlAlchemyProjectRepository
        from eea_core.entities import Project

        SqlAlchemyProjectRepository(session).add(Project(id=project_id, name="dead"), commit=True)
        event = EventOutboxService(SqlAlchemyOutboxRepository(session)).enqueue(
            event_type="unknown.event",
            aggregate_type="Project",
            aggregate_id=str(project_id),
            aggregate_revision=1,
            event_key="unknown:Project:" + str(project_id),
            payload={"x": 1},
            payload_hash=payload_sha256({"x": 1}),
            project_id=project_id,
            max_attempts=1,
            commit=True,
        )
    service = RecoveryService(lambda: Session(engine), registry=OutboxHandlerRegistry())
    assert service.dispatch_ready_events(limit=1)["dead_letter"] == 1
    with Session(engine) as session:
        assert (
            SqlAlchemyOutboxRepository(session).get(event.id).status
            is OutboxEventStatus.DEAD_LETTER
        )


def test_artifact_consumer_is_idempotent_on_replay(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    engine = create_database_engine(settings)
    project = Project(id=uuid4(), name="artifact")
    artifact_id = str(uuid4())
    payload = {
        "project_id": str(project.id),
        "artifact_id": artifact_id,
        "logical_name": "generated",
        "artifact_type": "firmware",
        "version_label": "v1",
        "content_hash": "a" * 64,
        "input_hash": "b" * 64,
    }
    project, event = _project_and_event(engine, event_type="artifact.created", payload=payload)
    with Session(engine) as session:
        SqlAlchemyArtifactRepository(session).add(
            Artifact(
                id=UUID(artifact_id),
                project_id=project.id,
                logical_name="generated",
                artifact_type="firmware",
                version_label="v1",
                content_hash="a" * 64,
                input_hash="b" * 64,
                storage_uri="test://artifact",
                created_by="test",
                status=ArtifactStatus.CURRENT,
            ),
            commit=True,
        )
    first = RecoveryService(
        lambda: Session(engine),
        crash_injector=PointCrashInjector(
            CrashPoint.AFTER_CONSUMER_EFFECT_COMMIT_BEFORE_OUTBOX_FINALIZE
        ),
    )
    with pytest.raises(InjectedCrashError):
        first.dispatch_ready_events(limit=1)
    with Session(engine) as session:
        session.execute(
            update(OutboxEventRecord)
            .where(OutboxEventRecord.id == str(event.id))
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        session.commit()
    second = RecoveryService(lambda: Session(engine))
    assert second.recover_expired_outbox_leases() == 1
    assert second.dispatch_ready_events(limit=1)["processed"] == 1
    with Session(engine) as session:
        assert session.scalar(select(ArtifactRecord).where(ArtifactRecord.id == artifact_id))
        assert session.scalar(
            select(ArtifactRecord).where(ArtifactRecord.logical_name == "generated")
        )
        assert len(list(session.scalars(select(ArtifactRecord)))) == 1
        assert len(list(session.scalars(select(ProcessedEventRecord)))) == 1
        assert len(list(session.scalars(select(SideEffectJournalRecord)))) == 1


def test_producer_idempotency_and_payload_mismatch(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    engine = create_database_engine(settings)
    with Session(engine) as session:
        service = EventOutboxService(SqlAlchemyOutboxRepository(session))
        first = service.enqueue(
            event_type="idempotent.event",
            aggregate_type="Project",
            aggregate_id="p1",
            aggregate_revision=1,
            payload={"value": 1},
            event_key="idempotent:p1:1",
            commit=True,
        )
        same = service.enqueue(
            event_type="idempotent.event",
            aggregate_type="Project",
            aggregate_id="p1",
            aggregate_revision=1,
            payload={"value": 1},
            event_key="idempotent:p1:1",
            commit=True,
        )
        assert same.id == first.id
        with pytest.raises(ValueError, match="payload_hash"):
            service.enqueue(
                event_type="idempotent.event",
                aggregate_type="Project",
                aggregate_id="p1",
                aggregate_revision=1,
                payload={"value": 2},
                event_key="idempotent:p1:1",
                commit=True,
            )


def test_claim_lease_is_cas_and_wrong_worker_cannot_finalize(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    engine = create_database_engine(settings)
    _, event = _project_and_event(engine)
    clock = FrozenClock()
    with Session(engine) as first_session:
        first_claim = SqlAlchemyOutboxRepository(first_session).claim(
            worker_id="worker-a", now=clock.now()
        )
        assert first_claim is not None
    with Session(engine) as second_session:
        repository = SqlAlchemyOutboxRepository(second_session)
        assert repository.claim(worker_id="worker-b", now=clock.now()) is None
        assert (
            repository.finalize(
                event.id,
                worker_id="worker-b",
                status=OutboxEventStatus.PROCESSED,
                now=clock.now(),
            )
            is False
        )
    clock.advance(31)
    with Session(engine) as session:
        assert SqlAlchemyOutboxRepository(session).reclaim_expired(now=clock.now()) == 1
    with Session(engine) as session:
        claimed = SqlAlchemyOutboxRepository(session).claim(worker_id="worker-b", now=clock.now())
        assert claimed is not None


def test_retry_backoff_and_multi_consumer_markers(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    engine = create_database_engine(settings)
    _, event = _project_and_event(engine, event_type="multi.event")
    clock = FrozenClock()
    calls = {"a": 0, "b": 0}

    def consumer_a(session: Session, current) -> str:
        del session, current
        calls["a"] += 1
        return "a-result"

    def consumer_b(session: Session, current) -> str:
        del session, current
        calls["b"] += 1
        if calls["b"] == 1:
            raise RuntimeError("transient consumer failure")
        return "b-result"

    registry = OutboxHandlerRegistry(
        (
            HandlerRegistration("consumer-a", "multi.event", frozenset({1}), consumer_a),
            HandlerRegistration("consumer-b", "multi.event", frozenset({1}), consumer_b),
        )
    )
    service = RecoveryService(lambda: Session(engine), registry=registry, clock=clock)
    assert service.dispatch_ready_events(limit=1)["retry"] == 1
    assert calls == {"a": 1, "b": 1}
    clock.advance(1)
    assert service.dispatch_ready_events(limit=1)["processed"] == 1
    assert calls == {"a": 1, "b": 2}
    with Session(engine) as session:
        assert (
            session.scalar(
                select(OutboxEventRecord).where(OutboxEventRecord.id == str(event.id))
            ).status
            == OutboxEventStatus.PROCESSED.value
        )
        assert len(list(session.scalars(select(ProcessedEventRecord)))) == 2


def test_side_effect_journal_preserves_unknown_outcome(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    engine = create_database_engine(settings)
    _, event = _project_and_event(engine)
    request_hash = payload_sha256({"request": "one"})
    with Session(engine) as session:
        repository = SqlAlchemySideEffectJournalRepository(session)
        item = repository.prepare(
            SideEffectJournal(
                event_id=event.id,
                consumer_id="external-consumer",
                effect_key="external-call",
                effect_type="external-side-effect",
                request_hash=request_hash,
            )
        )
        repository.mark_reconcile_required(item, error="outcome unknown", now=datetime.now(UTC))
        session.commit()
        assert (
            repository.get(event.id, "external-consumer", "external-call").status
            is SideEffectStatus.RECONCILE_REQUIRED
        )
        with pytest.raises(ValueError, match="request_hash"):
            repository.prepare(
                SideEffectJournal(
                    event_id=event.id,
                    consumer_id="external-consumer",
                    effect_key="external-call",
                    effect_type="external-side-effect",
                    request_hash=payload_sha256({"request": "two"}),
                )
            )
    service = RecoveryService(lambda: Session(engine))
    assert service.reconcile_side_effects() == 0
    assert service.inspect_reconcile_required() == 1


def test_interrupted_job_requires_explicit_reconciliation(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    engine = create_database_engine(settings)
    now = datetime.now(UTC)
    with Session(engine) as session:
        session.add(
            JobRecord(
                id=str(uuid4()),
                created_at=now - timedelta(hours=1),
                updated_at=now - timedelta(hours=1),
                entity_metadata={},
                job_type="firmware-build",
                status=JobStatus.RUNNING.value,
                progress=0.5,
                phase="tool",
                result_ref=None,
                error_code=None,
                error_message=None,
                budget_usage={},
                resource_lock_ids=[],
            )
        )
        session.commit()
    service = RecoveryService(lambda: Session(engine))
    assert service.reconcile_interrupted_jobs() == 1
    with Session(engine) as session:
        job = session.scalar(select(JobRecord))
        assert job.status == JobStatus.FAILED_NEEDS_RECONCILE.value
        assert "explicit reconciliation" in job.error_message


def test_normal_runtime_dispatcher_delivers_without_manual_reconcile(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    application = create_app(settings)
    with TestClient(application) as client:
        response = client.post("/api/v1/projects", json={"name": "normal-dispatch"})
        assert response.status_code == 201
        # This is the deterministic trigger helper for the lifecycle-owned
        # dispatcher; the recovery HTTP endpoint is deliberately not used.
        application.state.outbox_dispatcher.dispatch_once()
        data = client.get("/api/v1/system/outbox/status").json()["data"]
        assert data["processed"] == 1


def test_app_worker_identity_is_unique_and_reused_by_recovery_paths(tmp_path: Path) -> None:
    app_a = create_app(Settings(data_dir=tmp_path / "a"))
    app_b = create_app(Settings(data_dir=tmp_path / "b"))
    assert app_a.state.recovery_worker_id != app_b.state.recovery_worker_id
    assert app_a.state.recovery_service.worker_id == app_a.state.recovery_worker_id
    assert app_a.state.outbox_dispatcher.service.worker_id == app_a.state.recovery_worker_id
    assert new_recovery_worker_id() != new_recovery_worker_id()


def test_producer_race_same_key_same_payload_is_one_event(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    engine = create_database_engine(settings)
    barrier = Barrier(2)
    key = "race:Project:shared:1"
    payload = {"value": "same"}

    def enqueue_once() -> str:
        with Session(engine) as session:
            barrier.wait()
            event = EventOutboxService(SqlAlchemyOutboxRepository(session)).enqueue(
                event_type="race.event",
                aggregate_type="Project",
                aggregate_id="shared",
                aggregate_revision=1,
                event_key=key,
                payload=payload,
                commit=True,
            )
            return str(event.id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: enqueue_once(), range(2)))
    assert len(set(results)) == 1
    with Session(engine) as session:
        assert len(list(session.scalars(select(OutboxEventRecord)))) == 1


def test_outbox_savepoint_leaves_outer_transaction_usable_after_unique_race(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    engine = create_database_engine(settings)
    _, existing = _project_and_event(engine, event_type="outer.event", payload={"value": "same"})
    with Session(engine) as session:
        candidate = OutboxEvent(
            event_type="outer.event",
            aggregate_type="Project",
            aggregate_id="outer",
            aggregate_revision=1,
            event_key=existing.event_key,
            payload={"value": "same", "project_id": str(existing.project_id)},
            payload_hash=payload_sha256({"value": "same", "project_id": str(existing.project_id)}),
        )
        session.add(
            ProjectRecord(
                id=str(uuid4()),
                schema_version="1.0",
                revision=1,
                created_at=utc_now(),
                updated_at=utc_now(),
                entity_metadata={},
                name="outer-survives",
                description="",
                status="DRAFT",
                deleted_at=None,
            )
        )
        session.flush()
        result = SqlAlchemyOutboxRepository(session).add(candidate, commit=False)
        assert result.id == existing.id
        session.commit()
    with Session(engine) as session:
        assert session.scalar(select(ProjectRecord).where(ProjectRecord.name == "outer-survives"))


def test_event_key_different_payload_fails_closed(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    engine = create_database_engine(settings)
    with Session(engine) as session:
        service = EventOutboxService(SqlAlchemyOutboxRepository(session))
        service.enqueue(
            event_type="same-key.event",
            aggregate_type="Project",
            aggregate_id="p",
            aggregate_revision=1,
            event_key="same-key",
            payload={"value": 1},
            commit=True,
        )
        with pytest.raises(ValueError, match="payload_hash"):
            service.enqueue(
                event_type="same-key.event",
                aggregate_type="Project",
                aggregate_id="p",
                aggregate_revision=1,
                event_key="same-key",
                payload={"value": 2},
                commit=True,
            )


def test_artifact_created_missing_authority_never_fabricates(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    engine = create_database_engine(settings)
    project = Project(id=uuid4(), name="missing-authority")
    with Session(engine) as session:
        from eea_backend.repositories import SqlAlchemyProjectRepository

        SqlAlchemyProjectRepository(session).add(project, commit=True)
        event = EventOutboxService(SqlAlchemyOutboxRepository(session)).enqueue(
            event_type="artifact.created",
            aggregate_type="Artifact",
            aggregate_id=str(uuid4()),
            aggregate_revision=1,
            payload={
                "project_id": str(project.id),
                "artifact_id": str(uuid4()),
                "logical_name": "missing",
                "artifact_type": "derived",
                "version_label": "v1",
                "content_hash": "a" * 64,
                "input_hash": "b" * 64,
            },
            project_id=project.id,
            max_attempts=1,
            commit=True,
        )
    result = RecoveryService(lambda: Session(engine)).dispatch_ready_events(limit=1)
    assert result["dead_letter"] == 1
    with Session(engine) as session:
        assert len(list(session.scalars(select(ArtifactRecord)))) == 0
        assert (
            session.get(OutboxEventRecord, str(event.id)).status
            == OutboxEventStatus.DEAD_LETTER.value
        )


def _derived_artifact_handler(session: Session, event: OutboxEvent) -> str:
    artifact_id = uuid5(NAMESPACE_URL, f"derived-artifact:{event.id}")
    project_id = UUID(str(event.payload["project_id"]))
    artifact = Artifact(
        id=artifact_id,
        project_id=project_id,
        logical_name=f"derived-{event.id}",
        artifact_type="derived-test",
        version_label="v1",
        content_hash=payload_sha256({"artifact": str(artifact_id)}),
        input_hash=payload_sha256({"event": str(event.id)}),
        storage_uri=f"derived://{artifact_id}",
        created_by="test-derived-handler",
    )
    SqlAlchemyArtifactRepository(session).add(artifact, commit=False)
    journal = SqlAlchemySideEffectJournalRepository(session)
    item = journal.prepare(
        SideEffectJournal(
            event_id=event.id,
            consumer_id="test-derived-artifact.create@1",
            effect_key="derived-artifact",
            effect_type="content-addressed-db",
            request_hash=payload_sha256({"event_id": str(event.id), "artifact": str(artifact_id)}),
        )
    )
    journal.mark_applied(item, result_ref=str(artifact_id), now=utc_now())
    return str(artifact_id)


def test_derived_artifact_replayed_ten_times_is_one_logical_effect(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    engine = create_database_engine(settings)
    project, event = _project_and_event(engine, event_type="test.derived-artifact.create")
    service = RecoveryService(
        lambda: Session(engine),
        registry=OutboxHandlerRegistry(
            (
                HandlerRegistration(
                    "test-derived-artifact.create@1",
                    "test.derived-artifact.create",
                    frozenset({1}),
                    _derived_artifact_handler,
                ),
            )
        ),
    )
    assert project.id == event.project_id
    for _ in range(10):
        with Session(engine) as session:
            session.execute(
                update(OutboxEventRecord)
                .where(OutboxEventRecord.id == str(event.id))
                .values(
                    status=OutboxEventStatus.PENDING.value, lease_owner=None, lease_expires_at=None
                )
            )
            session.commit()
        assert service.dispatch_ready_events(limit=1)["processed"] == 1
    with Session(engine) as session:
        assert len(list(session.scalars(select(ArtifactRecord)))) == 1
        assert len(list(session.scalars(select(ProcessedEventRecord)))) == 1
        assert len(list(session.scalars(select(SideEffectJournalRecord)))) == 1


def test_project_scoped_reconcile_does_not_touch_other_project(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    engine = create_database_engine(settings)
    project_a, event_a = _project_and_event(engine, event_type="unsupported.a")
    project_b, event_b = _project_and_event(engine, event_type="unsupported.b")
    with Session(engine) as session:
        session.execute(
            update(OutboxEventRecord)
            .where(OutboxEventRecord.id.in_([str(event_a.id), str(event_b.id)]))
            .values(max_attempts=1)
        )
        session.commit()
    service = RecoveryService(lambda: Session(engine), registry=OutboxHandlerRegistry())
    service.recover_expired_outbox_leases(project_id=project_a.id)
    assert service.dispatch_ready_events(limit=10, project_id=project_a.id)["dead_letter"] == 1
    with Session(engine) as session:
        assert (
            session.get(OutboxEventRecord, str(event_a.id)).status
            == OutboxEventStatus.DEAD_LETTER.value
        )
        assert (
            session.get(OutboxEventRecord, str(event_b.id)).status
            == OutboxEventStatus.PENDING.value
        )
    assert project_b.id != project_a.id


def test_project_scoped_interrupted_job_reconcile_isolated(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    engine = create_database_engine(settings)
    project_a, _ = _project_and_event(engine)
    project_b, _ = _project_and_event(engine)
    now = datetime.now(UTC) - timedelta(hours=1)
    with Session(engine) as session:
        for project in (project_a, project_b):
            session.add(
                JobRecord(
                    id=str(uuid4()),
                    created_at=now,
                    updated_at=now,
                    entity_metadata={},
                    project_id=str(project.id),
                    job_type="safe-test-job",
                    status=JobStatus.RUNNING.value,
                    progress=0.1,
                    phase="running",
                    result_ref=None,
                    error_code=None,
                    error_message=None,
                    budget_usage={},
                    resource_lock_ids=[],
                )
            )
        session.commit()
    assert (
        RecoveryService(lambda: Session(engine)).reconcile_interrupted_jobs(project_id=project_a.id)
        == 1
    )
    with Session(engine) as session:
        statuses = list(session.scalars(select(JobRecord).order_by(JobRecord.project_id)))
        status_by_project = {row.project_id: row.status for row in statuses}
        assert status_by_project[str(project_a.id)] == JobStatus.FAILED_NEEDS_RECONCILE.value
        assert status_by_project[str(project_b.id)] == JobStatus.RUNNING.value


def test_processed_event_concurrent_insert_is_idempotent(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    engine = create_database_engine(settings)
    _, event = _project_and_event(engine)
    barrier = Barrier(2)

    def insert_marker() -> bool:
        with Session(engine) as session:
            barrier.wait()
            _, inserted = SqlAlchemyProcessedEventRepository(session).add_idempotent(
                ProcessedEvent(
                    event_id=event.id,
                    consumer_id="race-consumer",
                    event_payload_hash=event.payload_hash,
                )
            )
            session.commit()
            return inserted

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: insert_marker(), range(2)))
    assert sorted(results) == [False, True]
    with Session(engine) as session:
        assert len(list(session.scalars(select(ProcessedEventRecord)))) == 1


def test_side_effect_prepare_concurrent_insert_is_idempotent(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    engine = create_database_engine(settings)
    _, event = _project_and_event(engine)
    barrier = Barrier(2)
    request_hash = payload_sha256({"effect": "race"})

    def prepare_marker() -> UUID:
        with Session(engine) as session:
            barrier.wait()
            item = SqlAlchemySideEffectJournalRepository(session).prepare(
                SideEffectJournal(
                    event_id=event.id,
                    consumer_id="race-consumer",
                    effect_key="race-effect",
                    effect_type="content-addressed-db",
                    request_hash=request_hash,
                )
            )
            session.commit()
            return item.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: prepare_marker(), range(2)))
    assert results[0] == results[1]
    with Session(engine) as session:
        assert len(list(session.scalars(select(SideEffectJournalRecord)))) == 1


def test_two_recovery_workers_simultaneously_produce_one_effect(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    engine = create_database_engine(settings)
    project, event = _project_and_event(engine, event_type="test.derived-artifact.create")
    registry = OutboxHandlerRegistry(
        (
            HandlerRegistration(
                "test-derived-artifact.create@1",
                "test.derived-artifact.create",
                frozenset({1}),
                _derived_artifact_handler,
            ),
        )
    )
    barrier = Barrier(2)

    def run_worker(worker_id: str) -> dict[str, int]:
        barrier.wait()
        return RecoveryService(
            lambda: Session(engine), registry=registry, worker_id=worker_id
        ).dispatch_ready_events(limit=1)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run_worker, worker) for worker in ("A", "B")]
        results = [future.result() for future in futures]
    assert sum(result["processed"] for result in results) == 1
    with Session(engine) as session:
        assert project.id == event.project_id
        assert (
            session.get(OutboxEventRecord, str(event.id)).status
            == OutboxEventStatus.PROCESSED.value
        )
        assert len(list(session.scalars(select(ArtifactRecord)))) == 1
        assert len(list(session.scalars(select(ProcessedEventRecord)))) == 1
        assert len(list(session.scalars(select(SideEffectJournalRecord)))) == 1


def test_lease_takeover_rejects_stale_owner_finalize(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    engine = create_database_engine(settings)
    _, event = _project_and_event(engine)
    clock = FrozenClock()
    with Session(engine) as session:
        repository = SqlAlchemyOutboxRepository(session)
        assert repository.claim(worker_id="A", now=clock.now(), lease_seconds=1)
    clock.advance(2)
    with Session(engine) as session:
        assert SqlAlchemyOutboxRepository(session).reclaim_expired(now=clock.now()) == 1
        takeover = SqlAlchemyOutboxRepository(session).claim(
            worker_id="B", now=clock.now(), lease_seconds=30
        )
        assert takeover is not None
        assert (
            SqlAlchemyOutboxRepository(session).finalize(
                event.id,
                worker_id="A",
                status=OutboxEventStatus.PROCESSED,
                now=clock.now(),
            )
            is False
        )
        assert SqlAlchemyOutboxRepository(session).finalize(
            event.id,
            worker_id="B",
            status=OutboxEventStatus.PROCESSED,
            now=clock.now(),
        )


def test_unsupported_event_version_is_fail_closed(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    engine = create_database_engine(settings)
    _, event = _project_and_event(engine, event_type="versioned.event")
    with Session(engine) as session:
        session.execute(
            update(OutboxEventRecord)
            .where(OutboxEventRecord.id == str(event.id))
            .values(event_version=2, max_attempts=1)
        )
        session.commit()
    registry = OutboxHandlerRegistry(
        (
            HandlerRegistration(
                "versioned-consumer", "versioned.event", frozenset({1}), lambda _s, _e: "ok"
            ),
        )
    )
    assert (
        RecoveryService(lambda: Session(engine), registry=registry).dispatch_ready_events(limit=1)[
            "dead_letter"
        ]
        == 1
    )


def test_safe_side_effect_reconciler_applies_only_registered_effect(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    engine = create_database_engine(settings)
    _, event = _project_and_event(engine)
    with Session(engine) as session:
        journal = SqlAlchemySideEffectJournalRepository(session)
        item = journal.prepare(
            SideEffectJournal(
                event_id=event.id,
                consumer_id="safe",
                effect_key="safe-effect",
                effect_type="safe-db",
                request_hash=payload_sha256({"safe": 1}),
            )
        )
        journal.mark_reconcile_required(item, error="unknown", now=utc_now())
        session.commit()
    from eea_backend.recovery import SafeSideEffectReconcilerRegistry

    registry = SafeSideEffectReconcilerRegistry(
        {"safe-db": lambda _session, _item: "verified-result"}
    )
    service = RecoveryService(lambda: Session(engine), safe_reconcilers=registry)
    assert service.reconcile_side_effects() == 1
    assert service.inspect_reconcile_required() == 0


def test_status_diagnostics_expose_recovery_fields(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    application = create_app(settings)
    with TestClient(application) as client:
        outbox = client.get("/api/v1/system/outbox/status").json()["data"]
        recovery = client.get("/api/v1/system/recovery/status").json()["data"]
        assert {
            "pending",
            "processing",
            "retry",
            "processed",
            "dead_letter",
            "total",
            "expired_processing_count",
            "oldest_pending_at",
            "oldest_pending_age_seconds",
            "side_effect_reconcile_required_count",
        } <= set(outbox)
        assert {
            "healthy",
            "pending_recovery_count",
            "expired_lease_count",
            "dead_letter_count",
            "reconcile_required_effect_count",
            "interrupted_job_count",
            "startup_recovery_completed",
            "last_recovery_summary",
        } <= set(recovery)


def test_project_consistency_separates_recovery_from_engineering_degraded(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _migrate(settings)
    engine = create_database_engine(settings)
    project, _ = _project_and_event(engine, event_type="project.created")
    with Session(engine) as session:
        session.add(
            EngineeringDependencyNodeStateRecord(
                id=str(uuid4()),
                schema_version="1.0",
                revision=1,
                created_at=utc_now(),
                updated_at=utc_now(),
                entity_metadata={},
                project_id=str(project.id),
                entity_type="Artifact",
                entity_id="stale-artifact",
                observed_revision=1,
                observed_semantic_hash="a" * 64,
                status=DependencyNodeStatus.STALE.value,
                invalidated_by=[],
                reason_codes=["TEST"],
                stale_since=utc_now(),
            )
        )
        session.commit()
    service = RecoveryService(lambda: Session(engine))
    assert service.dispatch_ready_events(project_id=project.id, limit=1)["processed"] == 1
    data = service.reconcile_project(project.id)
    assert data["status"] == "DEGRADED"
    assert data["transactional_recovery"]["pending"] == 0
    assert data["engineering_freshness"]["stale"] == 1


def test_canonical_datetime_is_timezone_independent() -> None:
    naive = {"at": datetime(2026, 1, 1, 12, 0, 0)}
    aware = {"at": datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)}
    assert payload_sha256(naive) == payload_sha256(aware)


def test_busy_retry_policy_is_bounded_and_injectable() -> None:
    calls: list[float] = []
    policy = BusyRetryPolicy(attempts=3, delay_seconds=0.25, sleep=calls.append)
    for attempt in range(policy.attempts - 1):
        policy.sleep(policy.delay_seconds * (attempt + 1))
    assert calls == [0.25, 0.5]


def test_busy_write_replays_complete_insert_uow(settings):
    engine = create_database_engine(settings)
    _migrate(settings)
    failures = {"remaining": 1}

    def fail_first_insert(*args, **kwargs):
        statement = str(args[2]).lower() if len(args) > 2 else ""
        if "insert into outbox_events" in statement and failures["remaining"]:
            failures["remaining"] -= 1
            raise OperationalError(
                "forced busy",
                {},
                sqlite3.OperationalError("database is locked"),
            )

    sqlalchemy_event.listen(engine, "before_cursor_execute", fail_first_insert)
    try:
        with Session(engine) as session:
            repository = SqlAlchemyOutboxRepository(
                session,
                busy_retry=BusyRetryPolicy(attempts=3, delay_seconds=0),
            )
            repository.add(
                OutboxEvent(
                    event_type="busy.replay",
                    event_key="busy-replay",
                    payload={"value": 1},
                    payload_hash=payload_sha256({"value": 1}),
                    aggregate_type="test",
                    aggregate_id="busy-1",
                ),
                commit=True,
            )
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", fail_first_insert)

    with Session(engine) as session:
        assert len(session.scalars(select(OutboxEventRecord)).all()) == 1
    assert failures["remaining"] == 0


def test_busy_write_never_reports_false_success(settings):
    engine = create_database_engine(settings)
    _migrate(settings)
    failures = {"remaining": 10}

    def fail_every_insert(*args, **kwargs):
        statement = str(args[2]).lower() if len(args) > 2 else ""
        if "insert into outbox_events" in statement and failures["remaining"]:
            failures["remaining"] -= 1
            raise OperationalError(
                "forced busy",
                {},
                sqlite3.OperationalError("database is locked"),
            )

    sqlalchemy_event.listen(engine, "before_cursor_execute", fail_every_insert)
    try:
        with Session(engine) as session:
            repository = SqlAlchemyOutboxRepository(
                session,
                busy_retry=BusyRetryPolicy(attempts=2, delay_seconds=0),
            )
            with pytest.raises(OperationalError):
                repository.add(
                    OutboxEvent(
                        event_type="busy.fail",
                        event_key="busy-fail",
                        payload={"value": 1},
                        payload_hash=payload_sha256({"value": 1}),
                        aggregate_type="test",
                        aggregate_id="busy-2",
                    ),
                    commit=True,
                )
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", fail_every_insert)

    with Session(engine) as session:
        assert len(session.scalars(select(OutboxEventRecord)).all()) == 0


def test_busy_commit_replays_complete_uow(settings, monkeypatch):
    engine = create_database_engine(settings)
    _migrate(settings)
    with Session(engine) as session:
        original_commit = session.commit
        failures = {"remaining": 1}

        def fail_first_commit():
            if failures["remaining"]:
                failures["remaining"] -= 1
                raise OperationalError(
                    "forced busy",
                    {},
                    sqlite3.OperationalError("database is locked"),
                )
            original_commit()

        monkeypatch.setattr(session, "commit", fail_first_commit)
        repository = SqlAlchemyOutboxRepository(
            session,
            busy_retry=BusyRetryPolicy(attempts=3, delay_seconds=0),
        )
        repository.add(
            OutboxEvent(
                event_type="busy.commit",
                event_key="busy-commit",
                payload={"value": 1},
                payload_hash=payload_sha256({"value": 1}),
                aggregate_type="test",
                aggregate_id="busy-commit",
            ),
            commit=True,
        )

    with Session(engine) as session:
        assert len(session.scalars(select(OutboxEventRecord)).all()) == 1
    assert failures["remaining"] == 0


def test_reclaim_expired_cas_does_not_overwrite_renewed_lease(settings):
    engine = create_database_engine(settings)
    _migrate(settings)
    now = datetime.now(UTC)
    _, event = _project_and_event(engine, event_type="cas.reclaim")
    with Session(engine) as session:
        session.execute(
            update(OutboxEventRecord)
            .where(OutboxEventRecord.id == str(event.id))
            .values(
                status=OutboxEventStatus.PROCESSING.value,
                attempt_count=1,
                max_attempts=3,
                lease_owner="worker-a",
                lease_expires_at=now - timedelta(seconds=30),
                updated_at=now - timedelta(seconds=30),
            )
        )
        session.commit()
        row = session.get(OutboxEventRecord, str(event.id))
        assert row is not None
        observed_revision = row.revision
        observed_updated_at = row.updated_at
        session.execute(
            update(OutboxEventRecord)
            .where(OutboxEventRecord.id == str(event.id))
            .values(
                revision=observed_revision + 1,
                lease_owner="worker-b",
                lease_expires_at=now + timedelta(minutes=1),
                updated_at=now,
            )
        )
        session.commit()

    with Session(engine) as session:
        repository = SqlAlchemyOutboxRepository(session)
        assert repository.reclaim_expired(now=now, limit=10) == 0
        current = session.get(OutboxEventRecord, str(event.id))
        assert current is not None
        assert current.lease_owner == "worker-b"
        assert current.revision == observed_revision + 1
        assert current.updated_at == now.replace(tzinfo=None)
        assert observed_updated_at < now.replace(tzinfo=None)


def test_reconcile_interrupted_job_cas_does_not_overwrite_heartbeat(settings):
    engine = create_database_engine(settings)
    _migrate(settings)
    now = datetime.now(UTC)
    stale = now - timedelta(minutes=5)
    with Session(engine) as session:
        job = JobRecord(
            id=str(uuid4()),
            created_at=stale,
            status=JobStatus.RUNNING.value,
            revision=3,
            updated_at=stale,
            entity_metadata={},
            job_type="firmware-build",
            progress=0.5,
            phase="running",
            result_ref=None,
            error_code=None,
            error_message=None,
            budget_usage={},
            resource_lock_ids=[],
        )
        session.add(job)
        session.commit()
        job_id = job.id
        observed_revision = job.revision
        session.execute(
            update(JobRecord)
            .where(JobRecord.id == job.id)
            .values(
                status=JobStatus.SUCCESS.value,
                revision=observed_revision + 1,
                updated_at=now,
                error_message="finished by worker",
            )
        )
        session.commit()

    service = RecoveryService(lambda: Session(engine), worker_id="recovery-cas")
    assert service.reconcile_interrupted_jobs(cutoff=timedelta(seconds=60)) == 0

    with Session(engine) as session:
        current = session.get(JobRecord, job_id)
        assert current is not None
        assert current.status == JobStatus.SUCCESS.value
        assert current.revision == observed_revision + 1
        assert current.error_message == "finished by worker"


def test_lost_lease_is_not_reported_as_retry_or_dead_letter(settings):
    engine = create_database_engine(settings)
    _migrate(settings)
    _, event = _project_and_event(engine, event_type="lost.lease")
    with Session(engine) as session:
        session.execute(
            update(OutboxEventRecord)
            .where(OutboxEventRecord.id == str(event.id))
            .values(
                status=OutboxEventStatus.PROCESSING.value,
                attempt_count=1,
                lease_owner="worker-b",
                lease_expires_at=datetime.now(UTC) + timedelta(minutes=1),
            )
        )
        session.commit()
        claimed = SqlAlchemyOutboxRepository(session).get(event.id)
        assert claimed is not None

    service = RecoveryService(lambda: Session(engine), worker_id="worker-a")
    assert service._retry_or_dead(claimed, "lease lost") is None

    with Session(engine) as session:
        current = session.get(OutboxEventRecord, str(event.id))
        assert current is not None
        assert current.status == OutboxEventStatus.PROCESSING.value
        assert current.lease_owner == "worker-b"


def test_expired_processing_is_counted_once_in_recovery_diagnostics(settings):
    engine = create_database_engine(settings)
    _migrate(settings)
    now = datetime.now(UTC)
    _, _pending_event = _project_and_event(engine, event_type="diagnostics.pending")
    _, expired_event = _project_and_event(engine, event_type="diagnostics.expired")
    _, active_event = _project_and_event(engine, event_type="diagnostics.active")
    with Session(engine) as session:
        session.execute(
            update(OutboxEventRecord)
            .where(OutboxEventRecord.id == str(expired_event.id))
            .values(
                status=OutboxEventStatus.PROCESSING.value,
                lease_expires_at=now - timedelta(seconds=1),
            )
        )
        session.execute(
            update(OutboxEventRecord)
            .where(OutboxEventRecord.id == str(active_event.id))
            .values(
                status=OutboxEventStatus.PROCESSING.value,
                lease_expires_at=now + timedelta(minutes=1),
            )
        )
        session.commit()
        diagnostics = SqlAlchemyOutboxRepository(session).diagnostics(now=now)

    assert diagnostics["pending_recovery_count"] == 3
    assert diagnostics["processing_count"] == 2
    assert diagnostics["expired_processing_count"] == 1


def test_dispatcher_slow_sync_work_does_not_block_asyncio_loop(settings):
    engine = create_database_engine(settings)
    _migrate(settings)

    async def scenario():
        service = RecoveryService(lambda: Session(engine))
        dispatcher = OutboxDispatcher(
            service,
            poll_interval_seconds=60,
            graceful_timeout_seconds=2,
        )
        started = asyncio.Event()
        loop = asyncio.get_running_loop()

        def slow_dispatch():
            loop.call_soon_threadsafe(started.set)
            sleep(0.2)
            return {"processed": 0}

        dispatcher.dispatch_once = slow_dispatch
        dispatcher.start()
        await asyncio.wait_for(started.wait(), timeout=1)
        ticks = 0
        deadline = asyncio.get_running_loop().time() + 0.05
        while asyncio.get_running_loop().time() < deadline:
            ticks += 1
            await asyncio.sleep(0)
        await asyncio.wait_for(dispatcher.stop(), timeout=2)
        assert ticks > 10

    asyncio.run(scenario())
