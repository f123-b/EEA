"""M18A focused acceptance coverage: durable events, recovery, and idempotency."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from eea_application.reliability import (
    CrashPoint,
    EventOutboxService,
    HandlerRegistration,
    InjectedCrashError,
    OutboxHandlerRegistry,
)
from eea_backend.database import create_database_engine
from eea_backend.main import create_app
from eea_backend.models import (
    ArtifactRecord,
    JobRecord,
    OutboxEventRecord,
    ProcessedEventRecord,
    ProjectRecord,
    SideEffectJournalRecord,
)
from eea_backend.recovery import RecoveryService
from eea_backend.reliability_repositories import (
    SqlAlchemyOutboxRepository,
    SqlAlchemySideEffectJournalRepository,
)
from eea_backend.settings import Settings
from eea_core.entities import Project
from eea_core.enums import JobStatus
from eea_core.reliability import (
    OutboxEventStatus,
    SideEffectJournal,
    SideEffectStatus,
    payload_sha256,
    stable_event_key,
)
from fastapi.testclient import TestClient
from sqlalchemy import select, update
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
    with TestClient(create_app(settings)) as client:
        created = client.post("/api/v1/projects", json={"name": "replay"}).json()["data"]
        assert client.get("/api/v1/system/outbox/status").json()["data"]["pending"] == 1
        result = client.post("/api/v1/system/recovery/reconcile", json={"limit": 100})
        assert result.status_code == 200
        status = client.get("/api/v1/system/outbox/status").json()["data"]
        assert status["processed"] == 1
        assert (
            client.get(f"/api/v1/projects/{created['id']}/consistency").json()["data"]["status"]
            == "CLEAN"
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
    _, event = _project_and_event(engine, event_type="artifact.created", payload=payload)
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
    assert RecoveryService(lambda: Session(engine)).reconcile_side_effects() == 1


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
