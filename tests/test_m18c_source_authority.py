"""M18C Source Authority, Workspace, and Git contract regressions."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from eea_adapters.source import FileSystemSourceWorkspaceAdapter, GitCliWorkspaceAdapter
from eea_application.reliability import EventOutboxService
from eea_application.source_workspace import SourceWorkspaceService
from eea_backend.models import OutboxEventRecord, SourceMutationJournalRecord, SourceWorkspaceRecord
from eea_backend.reliability_repositories import SqlAlchemyOutboxRepository
from eea_backend.source_repositories import SqlAlchemySourceRepository
from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_core.reliability import OutboxEventStatus
from eea_core.source import GeneratedSourceCandidate
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session


def _project(client: TestClient, name: str = "M18C source") -> UUID:
    response = client.post("/api/v1/projects", json={"name": name})
    assert response.status_code == 201
    return UUID(response.json()["data"]["id"])


def _revision(client: TestClient, project_id: UUID) -> dict[str, object]:
    response = client.get(f"/api/v1/projects/{project_id}/source/revision")
    assert response.status_code == 200
    return response.json()["data"]


def _proposal(
    client: TestClient,
    project_id: UUID,
    revision: dict[str, object],
    edits: dict[str, str],
    *,
    expected: dict[str, str | None] | None = None,
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/projects/{project_id}/source/patch-proposals",
        json={
            "base_source_revision_id": revision["id"],
            "base_workspace_revision": revision["workspace_revision"],
            "affected_files": list(edits),
            "expected_file_hashes": expected or {},
            "structured_edits": edits,
            "rationale": "M18C regression",
            "created_by": "m18c-test",
        },
    )
    assert response.status_code == 201
    return response.json()["data"]


def test_empty_workspace_revision_is_deterministic_after_restart(client: TestClient) -> None:
    project_id = _project(client)
    first = _revision(client, project_id)
    status = client.get(f"/api/v1/projects/{project_id}/source/status")
    assert status.status_code == 200
    second = _revision(client, project_id)
    assert first["id"] == second["id"]
    assert first["source_manifest_hash"] == second["source_manifest_hash"]
    assert status.json()["data"]["file_count"] == 0


def test_read_apply_revision_etag_and_durable_source_changed(client: TestClient) -> None:
    project_id = _project(client)
    base = _revision(client, project_id)
    proposal = _proposal(client, project_id, base, {"src/main.c": "int main(void) { return 0; }\n"})
    diff = client.get(f"/api/v1/patch-proposals/{proposal['id']}/diff")
    assert diff.status_code == 200
    assert "src/main.c" in diff.json()["data"]["diff"]
    applied = client.post(f"/api/v1/patch-proposals/{proposal['id']}/apply", json={})
    assert applied.status_code == 200
    current = applied.json()["data"]["source_revision"]
    read = client.get(
        f"/api/v1/projects/{project_id}/source/files/content", params={"path": "src/main.c"}
    )
    assert read.status_code == 200
    assert read.json()["data"]["source_revision_id"] == current["id"]
    assert read.headers["ETag"] == read.json()["data"]["etag"]
    assert (
        client.get(
            f"/api/v1/projects/{project_id}/source/files/content",
            params={"path": "src/main.c"},
            headers={"If-Match": '"' + "0" * 64 + '"'},
        ).status_code
        == 409
    )
    with Session(client.app.state.engine) as session:
        event = session.scalar(
            select(OutboxEventRecord).where(
                OutboxEventRecord.event_type == "source.changed",
                OutboxEventRecord.project_id == str(project_id),
            )
        )
        assert event is not None
        assert event.status in {
            OutboxEventStatus.PENDING.value,
            OutboxEventStatus.PROCESSING.value,
            OutboxEventStatus.PROCESSED.value,
        }


def test_stale_two_writer_and_content_hash_conflicts(client: TestClient) -> None:
    project_id = _project(client)
    base = _revision(client, project_id)
    first = _proposal(client, project_id, base, {"src/a.c": "a\n"})
    second = _proposal(client, project_id, base, {"src/a.c": "b\n"})
    assert client.post(f"/api/v1/patch-proposals/{first['id']}/apply", json={}).status_code == 200
    conflict = client.post(f"/api/v1/patch-proposals/{second['id']}/apply", json={})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == EngineeringErrorCode.SOURCE_REVISION_CONFLICT.value
    assert client.get(f"/api/v1/patch-proposals/{second['id']}").json()["data"]["status"] == "STALE"


def test_safe_path_rejects_traversal_and_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    adapter = FileSystemSourceWorkspaceAdapter(root)
    with pytest.raises(EngineeringError) as traversal:
        adapter.read_bytes("../outside.c")
    assert traversal.value.code is EngineeringErrorCode.SANDBOX_VIOLATION
    with pytest.raises(EngineeringError) as absolute:
        adapter.read_bytes(str(tmp_path / "outside.c"))
    assert absolute.value.code is EngineeringErrorCode.SANDBOX_VIOLATION
    (root / "src").mkdir(parents=True)
    (root / "src" / "inside.c").write_text("inside\n", encoding="utf-8")
    internal_link = root / "src" / "alias.c"
    try:
        internal_link.symlink_to(root / "src" / "inside.c")
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    assert adapter.read_bytes("src/alias.c") == b"inside\n"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.c").write_text("secret", encoding="utf-8")
    link = root / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    with pytest.raises(EngineeringError):
        adapter.read_bytes("linked/secret.c")


def test_reconcile_recovers_after_filesystem_replace_before_sql_finalize(
    client: TestClient,
) -> None:
    project_id = _project(client)
    base = _revision(client, project_id)
    proposal = _proposal(client, project_id, base, {"crash.c": "recovered\n"})
    root = client.app.state.settings.data_dir / "projects" / str(project_id) / "workspace"
    with Session(client.app.state.engine) as session:
        repository = SqlAlchemySourceRepository(session)
        operation_id = uuid4()
        repository.claim_source_mutation(
            project_id, operation_id, UUID(str(base["id"])), int(base["workspace_revision"])
        )
        bundle = FileSystemSourceWorkspaceAdapter(root).prepare_recovery_bundle(
            operation_id,
            {"crash.c": None},
            {"crash.c": b"recovered\n"},
            metadata={"project_id": str(project_id), "proposal_id": str(proposal["id"])},
        )
        journal_id = repository.begin_source_journal(
            project_id,
            UUID(str(proposal["id"])),
            UUID(str(base["id"])),
            ["crash.c"],
            operation_id=operation_id,
            before_manifest=dict(bundle.before_manifest),
            after_manifest=dict(bundle.after_manifest),
            recovery_bundle_path=str(bundle.path),
        )
        repository.commit()
        session.execute(
            update(SourceWorkspaceRecord)
            .where(SourceWorkspaceRecord.project_id == str(project_id))
            .values(active_mutation_started_at=datetime.now(UTC) - timedelta(hours=1))
        )
        session.commit()
        FileSystemSourceWorkspaceAdapter(root).atomic_replace({"crash.c": b"recovered\n"})
        service = SourceWorkspaceService(
            project_id,
            repository,
            FileSystemSourceWorkspaceAdapter(root),
            git=GitCliWorkspaceAdapter(root),
            source_changed=EventOutboxService(SqlAlchemyOutboxRepository(session)),
        )
        recovered = service.reconcile()
        journal = session.get(SourceMutationJournalRecord, str(journal_id))
        recovered_proposal = repository.get_proposal(UUID(str(proposal["id"])))
        assert recovered.id != UUID(str(base["id"]))
        assert journal is not None
        assert journal.status == "RECOVERED"
        assert recovered_proposal is not None
        assert recovered_proposal.status.value == "APPLIED"


def test_reconcile_cleans_orphaned_temporary_source_files(client: TestClient) -> None:
    project_id = _project(client)
    _revision(client, project_id)
    root = client.app.state.settings.data_dir / "projects" / str(project_id) / "workspace"
    temporary = root / ".eea-source-tmp-orphan"
    temporary.write_bytes(b"not authoritative")
    assert temporary.exists()
    with Session(client.app.state.engine) as session:
        service = SourceWorkspaceService(
            project_id,
            SqlAlchemySourceRepository(session),
            FileSystemSourceWorkspaceAdapter(root),
            git=GitCliWorkspaceAdapter(root),
            source_changed=EventOutboxService(SqlAlchemyOutboxRepository(session)),
        )
        service.reconcile()
    assert not temporary.exists()


def test_multi_file_atomic_replace_rolls_back_on_fault(client: TestClient) -> None:
    project_id = _project(client)
    base = _revision(client, project_id)
    proposal = _proposal(client, project_id, base, {"a.c": "a\n", "b.c": "b\n"})
    root = client.app.state.settings.data_dir / "projects" / str(project_id) / "workspace"

    def fail_after_first_replace(phase: str, index: int) -> None:
        if phase == "after_replace" and index == 1:
            raise RuntimeError("injected replace failure")

    with Session(client.app.state.engine) as session:
        service = SourceWorkspaceService(
            project_id,
            SqlAlchemySourceRepository(session),
            FileSystemSourceWorkspaceAdapter(root, fault_injector=fail_after_first_replace),
            git=GitCliWorkspaceAdapter(root),
            source_changed=EventOutboxService(SqlAlchemyOutboxRepository(session)),
        )
        with pytest.raises(RuntimeError):
            service.apply(UUID(str(proposal["id"])))
    assert not (root / "a.c").exists()
    assert not (root / "b.c").exists()
    assert _revision(client, project_id)["id"] == base["id"]


def test_generated_owned_file_divergence_is_fail_closed(client: TestClient) -> None:
    project_id = _project(client)
    base = _revision(client, project_id)
    root = client.app.state.settings.data_dir / "projects" / str(project_id) / "workspace"
    with Session(client.app.state.engine) as session:
        service = SourceWorkspaceService(
            project_id,
            SqlAlchemySourceRepository(session),
            FileSystemSourceWorkspaceAdapter(root),
            git=GitCliWorkspaceAdapter(root),
            source_changed=EventOutboxService(SqlAlchemyOutboxRepository(session)),
        )
        candidate = GeneratedSourceCandidate(
            id=uuid4(),
            project_id=project_id,
            generator_id="fixture-generator",
            generator_version="1",
            input_hash="a" * 64,
            files={"generated.c": "v1\n"},
            generated_owned_files=["generated.c"],
        )
        _, applied_revision = service.apply_generated_candidate(
            candidate,
            expected_source_revision_id=UUID(str(base["id"])),
            created_by="m18c-test",
        )
        assert applied_revision.dirty is True
        FileSystemSourceWorkspaceAdapter(root).atomic_replace({"generated.c": b"user\n"})
        current = service.current_revision()
        diverged = candidate.model_copy(update={"id": uuid4(), "files": {"generated.c": "v2\n"}})
        with pytest.raises(EngineeringError) as error:
            service.apply_generated_candidate(
                diverged,
                expected_source_revision_id=current.id,
                created_by="m18c-test",
            )
        assert error.value.code is EngineeringErrorCode.GENERATED_SOURCE_DIVERGED


def test_git_commit_creates_clean_source_revision(client: TestClient, tmp_path: Path) -> None:
    project_id = _project(client)
    root = tmp_path / "git-workspace"
    root.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch", "main"], cwd=root, check=True, capture_output=True
    )
    subprocess.run(["git", "config", "user.name", "M18C Test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "m18c@test.invalid"], cwd=root, check=True)
    (root / "README.md").write_text("initial\n", encoding="utf-8")
    subprocess.run(["git", "add", "--all", "--", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=root, check=True, capture_output=True)
    with Session(client.app.state.engine) as session:
        service = SourceWorkspaceService(
            project_id,
            SqlAlchemySourceRepository(session),
            FileSystemSourceWorkspaceAdapter(root),
            git=GitCliWorkspaceAdapter(root),
            source_changed=EventOutboxService(SqlAlchemyOutboxRepository(session)),
        )
        dirty = service.current_revision()
        (root / "README.md").write_text("changed\n", encoding="utf-8")
        dirty = service.current_revision()
        clean = service.commit(
            expected_source_revision_id=dirty.id,
            message="record source revision",
            actor="m18c-test",
        )
        assert clean.commit_sha is not None
        assert clean.dirty is False
        assert clean.workspace_revision > dirty.workspace_revision


def test_reconcile_after_external_replace_creates_new_revision(client: TestClient) -> None:
    project_id = _project(client)
    root = client.app.state.settings.data_dir / "projects" / str(project_id) / "workspace"
    with Session(client.app.state.engine) as session:
        service = SourceWorkspaceService(
            project_id,
            SqlAlchemySourceRepository(session),
            FileSystemSourceWorkspaceAdapter(root),
            git=GitCliWorkspaceAdapter(root),
            source_changed=EventOutboxService(SqlAlchemyOutboxRepository(session)),
        )
        first = service.current_revision()
        FileSystemSourceWorkspaceAdapter(root).atomic_replace({"external.c": b"external\n"})
        second = service.reconcile()
        assert second.id != first.id
        assert second.file_manifest["external.c"]
        assert second.workspace_revision == first.workspace_revision + 1
