"""M18CR database ownership and crash-recovery regressions."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from eea_adapters.source import FileSystemSourceWorkspaceAdapter, GitCliWorkspaceAdapter
from eea_application.reliability import EventOutboxService
from eea_application.source_workspace import SourceWorkspaceService
from eea_backend.models import SourceMutationJournalRecord, SourceWorkspaceRecord
from eea_backend.reliability_repositories import SqlAlchemyOutboxRepository
from eea_backend.source_repositories import SqlAlchemySourceRepository
from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session


def _project(client: TestClient, name: str) -> UUID:
    response = client.post("/api/v1/projects", json={"name": name})
    assert response.status_code == 201
    return UUID(response.json()["data"]["id"])


def _revision(client: TestClient, project_id: UUID) -> dict[str, object]:
    response = client.get(f"/api/v1/projects/{project_id}/source/revision")
    assert response.status_code == 200
    return response.json()["data"]


def _service(
    client: TestClient,
    project_id: UUID,
    session: Session,
    root: Path,
) -> SourceWorkspaceService:
    return SourceWorkspaceService(
        project_id,
        SqlAlchemySourceRepository(session),
        FileSystemSourceWorkspaceAdapter(root),
        git=GitCliWorkspaceAdapter(root),
        source_changed=EventOutboxService(SqlAlchemyOutboxRepository(session)),
    )


def test_two_sessions_only_one_database_owner_and_cas_winner(client: TestClient) -> None:
    project_id = _project(client, "M18CR two sessions")
    base = _revision(client, project_id)
    root = client.app.state.settings.data_dir / "projects" / str(project_id) / "workspace"
    operation_a = uuid4()
    operation_b = uuid4()
    with (
        Session(client.app.state.engine) as session_a,
        Session(client.app.state.engine) as session_b,
    ):
        repository_a = SqlAlchemySourceRepository(session_a)
        repository_b = SqlAlchemySourceRepository(session_b)
        repository_a.claim_source_mutation(
            project_id, operation_a, UUID(str(base["id"])), int(base["workspace_revision"])
        )
        with pytest.raises(EngineeringError) as busy:
            repository_b.claim_source_mutation(
                project_id, operation_b, UUID(str(base["id"])), int(base["workspace_revision"])
            )
        assert busy.value.code is EngineeringErrorCode.RESOURCE_BUSY
        assert not (root / "winner.c").exists()

        adapter = FileSystemSourceWorkspaceAdapter(root)
        bundle = adapter.prepare_recovery_bundle(
            operation_a,
            {"winner.c": None},
            {"winner.c": b"winner\n"},
            metadata={"project_id": str(project_id)},
        )
        journal_id = repository_a.begin_source_journal(
            project_id,
            None,
            UUID(str(base["id"])),
            ["winner.c"],
            operation_id=operation_a,
            before_manifest=dict(bundle.before_manifest),
            after_manifest=dict(bundle.after_manifest),
            recovery_bundle_path=str(bundle.path),
        )
        repository_a.commit()
        adapter.atomic_replace({"winner.c": b"winner\n"})
        service_a = _service(client, project_id, session_a, root)
        after = service_a._snapshot(
            adapter.list_files(),
            workspace_revision=int(base["workspace_revision"]) + 1,
            created_by="m18cr-test",
            git_status=service_a._git_status(),
        )
        repository_a.save_revision(after, commit=False)
        repository_a.finish_source_journal(journal_id, "COMPLETED")
        repository_a.finalize_source_mutation(
            project_id,
            operation_a,
            UUID(str(base["id"])),
            int(base["workspace_revision"]),
            after.id,
            after.workspace_revision,
            after.base_commit,
            commit=True,
        )
        adapter.cleanup_recovery_bundle(str(bundle.path))
        with pytest.raises(EngineeringError) as stale:
            repository_b.claim_source_mutation(
                project_id, operation_b, UUID(str(base["id"])), int(base["workspace_revision"])
            )
        assert stale.value.code is EngineeringErrorCode.SOURCE_REVISION_CONFLICT
        assert (root / "winner.c").read_text(encoding="utf-8") == "winner\n"


def test_cross_service_loser_never_reaches_filesystem_replace(client: TestClient) -> None:
    project_id = _project(client, "M18CR cross service")
    base = _revision(client, project_id)
    proposal_response = client.post(
        f"/api/v1/projects/{project_id}/source/patch-proposals",
        json={
            "base_source_revision_id": base["id"],
            "base_workspace_revision": base["workspace_revision"],
            "affected_files": ["loser.c"],
            "structured_edits": {"loser.c": "loser\n"},
            "rationale": "M18CR cross-service CAS",
            "created_by": "m18cr-test",
        },
    )
    assert proposal_response.status_code == 201
    proposal_id = UUID(proposal_response.json()["data"]["id"])
    root = client.app.state.settings.data_dir / "projects" / str(project_id) / "workspace"
    operation_a = uuid4()
    with (
        Session(client.app.state.engine) as session_a,
        Session(client.app.state.engine) as session_b,
    ):
        repository_a = SqlAlchemySourceRepository(session_a)
        repository_a.claim_source_mutation(
            project_id, operation_a, UUID(str(base["id"])), int(base["workspace_revision"])
        )
        service_b = _service(client, project_id, session_b, root)
        with pytest.raises(EngineeringError) as busy:
            service_b.apply(proposal_id)
        assert busy.value.code is EngineeringErrorCode.RESOURCE_BUSY
        assert not (root / "loser.c").exists()
        repository_a.release_source_mutation(project_id, operation_a)


def test_reconcile_during_valid_active_mutation_does_not_authorize_partial_files(
    client: TestClient,
) -> None:
    project_id = _project(client, "M18CR active reconcile")
    base = _revision(client, project_id)
    root = client.app.state.settings.data_dir / "projects" / str(project_id) / "workspace"
    operation_id = uuid4()
    with Session(client.app.state.engine) as session_a:
        repository_a = SqlAlchemySourceRepository(session_a)
        repository_a.claim_source_mutation(
            project_id, operation_id, UUID(str(base["id"])), int(base["workspace_revision"])
        )
        adapter = FileSystemSourceWorkspaceAdapter(root)
        bundle = adapter.prepare_recovery_bundle(
            operation_id,
            {"partial-a.c": None, "partial-b.c": None},
            {"partial-a.c": b"a\n", "partial-b.c": b"b\n"},
            metadata={"project_id": str(project_id)},
        )
        repository_a.begin_source_journal(
            project_id,
            None,
            UUID(str(base["id"])),
            ["partial-a.c", "partial-b.c"],
            operation_id=operation_id,
            before_manifest=dict(bundle.before_manifest),
            after_manifest=dict(bundle.after_manifest),
            recovery_bundle_path=str(bundle.path),
        )
        repository_a.commit()
        adapter.atomic_replace({"partial-a.c": b"a\n"})

        with Session(client.app.state.engine) as session_b:
            service_b = _service(client, project_id, session_b, root)
            observed = service_b.current_revision()
            assert observed.id == UUID(str(base["id"]))
            assert observed.workspace_revision == int(base["workspace_revision"])
        adapter.restore_recovery_bundle(str(bundle.path), "BEFORE")
        journal = session_a.scalar(
            select(SourceMutationJournalRecord).where(
                SourceMutationJournalRecord.operation_id == str(operation_id)
            )
        )
        assert journal is not None
        repository_a.finish_source_journal(UUID(journal.id), "ROLLED_BACK")
        repository_a.release_source_mutation(project_id, operation_id)
        adapter.cleanup_recovery_bundle(str(bundle.path))


def test_expired_partial_bundle_recovers_to_one_complete_after_state(client: TestClient) -> None:
    project_id = _project(client, "M18CR hard crash")
    base = _revision(client, project_id)
    root = client.app.state.settings.data_dir / "projects" / str(project_id) / "workspace"
    operation_id = uuid4()
    with Session(client.app.state.engine) as session:
        repository = SqlAlchemySourceRepository(session)
        repository.claim_source_mutation(
            project_id, operation_id, UUID(str(base["id"])), int(base["workspace_revision"])
        )
        adapter = FileSystemSourceWorkspaceAdapter(root)
        bundle = adapter.prepare_recovery_bundle(
            operation_id,
            {"crash-a.c": None, "crash-b.c": None},
            {"crash-a.c": b"A\n", "crash-b.c": b"B\n"},
            metadata={"project_id": str(project_id)},
        )
        journal_id = repository.begin_source_journal(
            project_id,
            None,
            UUID(str(base["id"])),
            ["crash-a.c", "crash-b.c"],
            operation_id=operation_id,
            before_manifest=dict(bundle.before_manifest),
            after_manifest=dict(bundle.after_manifest),
            recovery_bundle_path=str(bundle.path),
        )
        repository.commit()
        adapter.atomic_replace({"crash-a.c": b"A\n"})
        session.execute(
            update(SourceWorkspaceRecord)
            .where(SourceWorkspaceRecord.project_id == str(project_id))
            .values(active_mutation_started_at=datetime.now(UTC) - timedelta(hours=1))
        )
        session.commit()

    with Session(client.app.state.engine) as fresh_session:
        service = _service(client, project_id, fresh_session, root)
        recovered = service.reconcile()
        assert recovered.workspace_revision == int(base["workspace_revision"]) + 1
        assert recovered.file_manifest["crash-a.c"]
        assert recovered.file_manifest["crash-b.c"]
        journal = fresh_session.get(SourceMutationJournalRecord, str(journal_id))
        assert journal is not None
        assert journal.status == "RECOVERED"
        state = SqlAlchemySourceRepository(fresh_session).get_workspace(project_id)
        assert state is not None
        assert state.active_mutation_id is None
    assert (root / "crash-a.c").read_text(encoding="utf-8") == "A\n"
    assert (root / "crash-b.c").read_text(encoding="utf-8") == "B\n"


def test_git_commit_is_also_blocked_by_source_mutation_claim(
    client: TestClient, tmp_path: Path
) -> None:
    project_id = _project(client, "M18CR Git claim")
    root = tmp_path / "git-workspace"
    root.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch", "main"], cwd=root, check=True, capture_output=True
    )
    subprocess.run(["git", "config", "user.name", "M18CR Test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "m18cr@test.invalid"], cwd=root, check=True)
    (root / "README.md").write_text("initial\n", encoding="utf-8")
    subprocess.run(["git", "add", "--all", "--", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=root, check=True, capture_output=True)
    with Session(client.app.state.engine) as session_a:
        service_a = _service(client, project_id, session_a, root)
        current = service_a.current_revision()
        operation_id = uuid4()
        SqlAlchemySourceRepository(session_a).claim_source_mutation(
            project_id, operation_id, current.id, current.workspace_revision
        )
        before_head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()
        with Session(client.app.state.engine) as session_b:
            service_b = _service(client, project_id, session_b, root)
            with pytest.raises(EngineeringError) as busy:
                service_b.commit(
                    expected_source_revision_id=current.id,
                    message="loser commit",
                    actor="m18cr-test",
                )
            assert busy.value.code is EngineeringErrorCode.RESOURCE_BUSY
        after_head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()
        assert before_head == after_head
        SqlAlchemySourceRepository(session_a).release_source_mutation(project_id, operation_id)
