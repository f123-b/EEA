"""M18ER.1 object-integrity, source portability, and restore recovery tests."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from eea_application.backup import BackupRecord, ProjectBackupService
from eea_backend.main import create_app
from eea_backend.models import ArtifactRecord, RestoreOperationRecord
from eea_backend.restore_service import RestoreCoordinator
from eea_backend.settings import Settings
from eea_core.backup import BackupValidationError, RestoreOperationState
from eea_core.failure_injection import (
    FailureInjectionHarness,
    FailureInjectionPoint,
    FailureOutcome,
    FailurePlan,
    FailureScenario,
    InjectedFailure,
)
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


def _upgrade(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", Settings(data_dir=path).database_url)
    command.upgrade(config, "head")


def _tampered_archive(source: Path, target: Path, *, truncate: bool = False) -> None:
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, "w") as changed:
        for info in original.infolist():
            content = original.read(info)
            if info.filename != "manifest.json":
                content = content[:-1] if truncate else bytes([content[0] ^ 0xFF]) + content[1:]
            changed.writestr(info, content)


def test_validate_streams_and_rejects_same_size_tamper(tmp_path: Path) -> None:
    project_id = uuid4()
    original = tmp_path / "original.zip"
    tampered = tmp_path / "tampered.zip"
    ProjectBackupService().export_project(
        project_id,
        original,
        (BackupRecord("records/object.bin", b"authoritative-bytes"),),
    )
    _tampered_archive(original, tampered)
    with pytest.raises(BackupValidationError):
        ProjectBackupService().validate_archive(tampered)


def test_validate_rejects_truncated_object_and_accepts_valid_archive(tmp_path: Path) -> None:
    project_id = uuid4()
    original = tmp_path / "original.zip"
    truncated = tmp_path / "truncated.zip"
    ProjectBackupService().export_project(
        project_id,
        original,
        (BackupRecord("records/object.bin", b"authoritative-bytes"),),
    )
    assert ProjectBackupService().validate_archive(original).project_id == project_id
    _tampered_archive(original, truncated, truncate=True)
    with pytest.raises(BackupValidationError):
        ProjectBackupService().validate_archive(truncated)


def test_api_validate_rejects_same_size_tamper_as_backup_invalid(tmp_path: Path) -> None:
    _upgrade(tmp_path)
    project_id = uuid4()
    original = tmp_path / "original.zip"
    tampered = tmp_path / "tampered.zip"
    ProjectBackupService().export_project(
        project_id,
        original,
        (BackupRecord("records/projects.json", json.dumps({"id": str(project_id)}).encode()),),
    )
    _tampered_archive(original, tampered)
    settings = Settings(data_dir=tmp_path, insecure_local_dev=True)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/projects/restore/validate",
            json={"archive_path": tampered.name, "project_id": str(project_id)},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BACKUP_INVALID"


def _failure(point: FailureInjectionPoint) -> FailureInjectionHarness:
    return FailureInjectionHarness(
        (
            FailurePlan(
                point,
                FailureScenario.PROCESS_KILL,
                FailureOutcome.RECOVERABLE,
                "injected restore crash",
            ),
        )
    )


def _source_archive(tmp_path: Path) -> tuple[Path, Path, UUID]:
    source_root = tmp_path / "source"
    _upgrade(source_root)
    source_settings = Settings(data_dir=source_root, insecure_local_dev=True)
    with TestClient(create_app(source_settings)) as client:
        created = client.post("/api/v1/projects", json={"name": "source portable"})
        assert created.status_code == 201
        project_id = UUID(created.json()["data"]["id"])
        workspace = source_root / "projects" / str(project_id) / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "main.c").write_text('const char *name = "token";\n', encoding="utf-8")
        (workspace / "motor.c").write_text("void motor(void) {}\n", encoding="utf-8")
        (workspace / "CMakeLists.txt").write_text("project(restored)\n", encoding="utf-8")
        status = client.get(f"/api/v1/projects/{project_id}/source/status")
        assert status.status_code == 200
        exported = client.post(
            f"/api/v1/projects/{project_id}/exports",
            json={"destination": "exports/source.zip"},
        )
        assert exported.status_code == 200
        archive = Path(exported.json()["data"]["archive_path"])
    clean_root = tmp_path / "clean"
    _upgrade(clean_root)
    target = clean_root / "source.zip"
    shutil.copy2(archive, target)
    return clean_root, target, project_id


def test_source_bytes_restore_and_reconcile_consistency(tmp_path: Path) -> None:
    clean_root, archive, project_id = _source_archive(tmp_path)
    settings = Settings(data_dir=clean_root, insecure_local_dev=True)
    with TestClient(create_app(settings)) as client:
        restored = client.post(
            "/api/v1/projects/restore",
            json={"archive_path": archive.name, "project_id": str(project_id)},
        )
        assert restored.status_code == 200, restored.text
        source = clean_root / "restored" / str(project_id) / "source"
        assert (source / "main.c").read_text(encoding="utf-8").startswith("const char")
        assert (source / "motor.c").is_file()
        assert (source / "CMakeLists.txt").is_file()
        revision = client.get(f"/api/v1/projects/{project_id}/source/revision")
        assert revision.status_code == 200, revision.text
        data = revision.json()["data"]
        manifest = {
            path.relative_to(source).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in source.rglob("*")
            if path.is_file()
        }
        assert data["file_manifest"] == manifest
        assert client.get(f"/api/v1/projects/{project_id}/source/status").status_code == 200


def test_recovery_after_prepared_commit_is_idempotent(tmp_path: Path) -> None:
    clean_root, archive, project_id = _source_archive(tmp_path)
    settings = Settings(data_dir=clean_root, insecure_local_dev=True)
    with TestClient(create_app(settings)) as client:
        coordinator = RestoreCoordinator(
            lambda: Session(client.app.state.engine),
            settings,
            failure_injector=_failure(FailureInjectionPoint.RESTORE_AFTER_PREPARE_COMMIT),
        )
        with pytest.raises(InjectedFailure):
            coordinator.restore(
                archive,
                project_id=project_id,
                actor_id="local:single-user",
                authorize=lambda _project, actor: actor == "local:single-user",
            )
        recovery = RestoreCoordinator(lambda: Session(client.app.state.engine), settings)
        assert recovery.recover_pending()["recovered"] == 1
        assert recovery.recover_pending()["recovered"] == 0
        with Session(client.app.state.engine) as session:
            operation = session.scalar(
                select(RestoreOperationRecord).where(
                    RestoreOperationRecord.project_id == str(project_id)
                )
            )
            assert operation is not None
            assert operation.state == RestoreOperationState.ACTIVATED.value


def test_recovery_after_staging_crash_activates_durable_tree(tmp_path: Path) -> None:
    clean_root, archive, project_id = _source_archive(tmp_path)
    settings = Settings(data_dir=clean_root, insecure_local_dev=True)
    with TestClient(create_app(settings)) as client:
        coordinator = RestoreCoordinator(
            lambda: Session(client.app.state.engine),
            settings,
            failure_injector=_failure(FailureInjectionPoint.RESTORE_AFTER_STAGE),
        )
        with pytest.raises(InjectedFailure):
            coordinator.restore(
                archive,
                project_id=project_id,
                actor_id="local:single-user",
                authorize=lambda _project, actor: actor == "local:single-user",
            )
        assert not (clean_root / "restored" / str(project_id)).exists()
        recovery = RestoreCoordinator(lambda: Session(client.app.state.engine), settings)
        assert recovery.recover_pending()["recovered"] == 1
        assert recovery.recover_pending()["recovered"] == 0
        assert (clean_root / "restored" / str(project_id) / "source" / "main.c").is_file()


def test_recovery_after_filesystem_activation_finalizes_records(tmp_path: Path) -> None:
    clean_root, archive, project_id = _source_archive(tmp_path)
    settings = Settings(data_dir=clean_root, insecure_local_dev=True)
    with TestClient(create_app(settings)) as client:
        coordinator = RestoreCoordinator(
            lambda: Session(client.app.state.engine),
            settings,
            failure_injector=_failure(FailureInjectionPoint.RESTORE_AFTER_FS_ACTIVATE),
        )
        with pytest.raises(InjectedFailure):
            coordinator.restore(
                archive,
                project_id=project_id,
                actor_id="local:single-user",
                authorize=lambda _project, actor: actor == "local:single-user",
            )
        assert (clean_root / "restored" / str(project_id) / "source" / "main.c").is_file()
        recovery = RestoreCoordinator(lambda: Session(client.app.state.engine), settings)
        assert recovery.recover_pending()["recovered"] == 1
        assert recovery.recover_pending()["recovered"] == 0


def test_finalize_window_failure_never_reports_activated(tmp_path: Path) -> None:
    clean_root, archive, project_id = _source_archive(tmp_path)
    settings = Settings(data_dir=clean_root, insecure_local_dev=True)
    with TestClient(create_app(settings)) as client:
        coordinator = RestoreCoordinator(
            lambda: Session(client.app.state.engine),
            settings,
            failure_injector=_failure(FailureInjectionPoint.RESTORE_BEFORE_DB_FINALIZE),
        )
        with pytest.raises(InjectedFailure):
            coordinator.restore(
                archive,
                project_id=project_id,
                actor_id="local:single-user",
                authorize=lambda _project, actor: actor == "local:single-user",
            )
        with Session(client.app.state.engine) as session:
            operation = session.scalar(
                select(RestoreOperationRecord).where(
                    RestoreOperationRecord.project_id == str(project_id)
                )
            )
            assert operation is not None
            assert operation.state == RestoreOperationState.FS_ACTIVATED.value
        assert (
            RestoreCoordinator(
                lambda: Session(client.app.state.engine), settings
            ).recover_pending()["recovered"]
            == 1
        )


def test_same_restore_operation_does_not_duplicate_authority(tmp_path: Path) -> None:
    clean_root, archive, project_id = _source_archive(tmp_path)
    settings = Settings(data_dir=clean_root, insecure_local_dev=True)
    with TestClient(create_app(settings)) as client:
        first = client.post(
            "/api/v1/projects/restore",
            json={"archive_path": archive.name, "project_id": str(project_id)},
        )
        second = client.post(
            "/api/v1/projects/restore",
            json={"archive_path": archive.name, "project_id": str(project_id)},
        )
        assert first.status_code == second.status_code == 200
        assert first.json()["data"]["state"] == second.json()["data"]["state"] == "ACTIVATED"
        with Session(client.app.state.engine) as session:
            assert session.query(RestoreOperationRecord).count() == 1
            assert session.query(ArtifactRecord).count() == 0


def test_portable_artifact_bytes_restore_with_verified_uri(tmp_path: Path) -> None:
    source_root = tmp_path / "artifact-source"
    _upgrade(source_root)
    settings = Settings(data_dir=source_root, insecure_local_dev=True)
    artifact_bytes = b"hello"
    artifact_path = source_root / "artifact.bin"
    artifact_path.write_bytes(artifact_bytes)
    with TestClient(create_app(settings)) as client:
        created = client.post("/api/v1/projects", json={"name": "artifact portable"})
        assert created.status_code == 201
        project_id = UUID(created.json()["data"]["id"])
        now = datetime.now(UTC)
        with Session(client.app.state.engine) as session:
            session.add(
                ArtifactRecord(
                    id=str(uuid4()),
                    schema_version="1.0",
                    revision=1,
                    created_at=now,
                    updated_at=now,
                    entity_metadata={},
                    project_id=str(project_id),
                    logical_name="hello",
                    artifact_type="portable",
                    version_label="v1",
                    content_hash=hashlib.sha256(artifact_bytes).hexdigest(),
                    input_hash="a" * 64,
                    storage_uri=str(artifact_path),
                    parent_artifact_id=None,
                    dependency_ids=[],
                    dependency_hashes={},
                    created_by="test",
                    source_job_id=None,
                    generator_version=None,
                    tool_versions={},
                    knowledge_snapshot=None,
                    status="CURRENT",
                )
            )
            session.commit()
        exported = client.post(
            f"/api/v1/projects/{project_id}/exports",
            json={"destination": "exports/artifact.zip"},
        )
        assert exported.status_code == 200, exported.text
        archive = Path(exported.json()["data"]["archive_path"])
    clean_root = tmp_path / "artifact-clean"
    _upgrade(clean_root)
    shutil.copy2(archive, clean_root / archive.name)
    clean_settings = Settings(data_dir=clean_root, insecure_local_dev=True)
    with TestClient(create_app(clean_settings)) as client:
        restored = client.post(
            "/api/v1/projects/restore",
            json={"archive_path": archive.name, "project_id": str(project_id)},
        )
        assert restored.status_code == 200, restored.text
        with Session(client.app.state.engine) as session:
            artifact = session.query(ArtifactRecord).one()
            restored_path = Path(artifact.storage_uri)
            assert restored_path.read_bytes() == artifact_bytes
            assert artifact.content_hash == hashlib.sha256(artifact_bytes).hexdigest()
            assert artifact.status == "CURRENT"
