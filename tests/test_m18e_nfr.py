"""M18E renderer, NFR, backup, failure and identity regression coverage."""

from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from eea_application.backup import BackupOperationError, BackupRecord, ProjectBackupService
from eea_backend.main import create_app
from eea_backend.settings import Settings
from eea_core.backup import BackupSecretPolicy, BackupValidationError, manifest_from_json
from eea_core.capacity import CapacityExceededError, CapacityProfileName, get_capacity_profile
from eea_core.claims import EngineeringValue
from eea_core.enums import EngineeringDimension
from eea_core.failure_injection import (
    FailureInjectionHarness,
    FailureInjectionPoint,
    FailureOutcome,
    FailurePlan,
    FailureScenario,
    InjectedFailure,
    baseline_failure_plans,
)
from eea_core.identity import IdentityMode, local_single_user
from eea_core.observability import ObservabilityContext, redact_sensitive
from eea_core.renderer_security import (
    RendererContentRejected,
    RendererSecurityPolicy,
    default_renderer_csp,
    sanitize_untrusted_content,
)
from eea_core.units import UnitNormalizationError, UnitNormalizationService
from fastapi.testclient import TestClient


def test_renderer_security_is_plain_text_and_navigation_isolated() -> None:
    content = sanitize_untrusted_content(
        "<img src=x onerror=alert(1)><script>alert(1)</script>"
        '<a href="javascript:alert(1)">javascript:alert(1)</a><iframe src="https://evil"></iframe>'
    )
    assert "<script" not in content.lower()
    assert "onerror" not in content.lower()
    assert "[blocked-url]" in content
    policy = RendererSecurityPolicy(allowed_external_hosts=frozenset({"docs.example.com"}))
    assert policy.validate_external_link("https://docs.example.com/spec")
    with pytest.raises(RendererContentRejected):
        policy.validate_external_link("javascript:alert(1)")
    with pytest.raises(RendererContentRejected):
        policy.validate_external_link("https://evil.example/spec")
    policy.validate_csp(default_renderer_csp())


def test_backup_roundtrip_hash_tamper_and_path_traversal_fail_closed(tmp_path: Path) -> None:
    project_id = uuid4()
    service = ProjectBackupService()
    archive = tmp_path / "project.eea.zip"
    manifest = service.export_project(
        project_id,
        archive,
        (BackupRecord("records/project.json", b'{"id":"project"}', "project"),),
    )
    restored = tmp_path / "restored"
    result = service.restore_project(
        archive,
        restored,
        authorized_project_id=project_id,
        actor_id="local:single-user",
        authorize=lambda expected, actor: expected == project_id and actor == "local:single-user",
    )
    assert result.manifest_hash == manifest.manifest_hash
    assert (restored / "records" / "project.json").read_bytes() == b'{"id":"project"}'

    tampered = tmp_path / "tampered.eea.zip"
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(tampered, "w") as target:
        for item in source.infolist():
            target.writestr(
                item.filename,
                b"tampered" if item.filename != "manifest.json" else source.read(item),
            )
    with pytest.raises((BackupValidationError, BackupOperationError)):
        service.restore_project(
            tampered,
            tmp_path / "tampered-restore",
            authorized_project_id=project_id,
            actor_id="local:single-user",
            authorize=lambda _expected, _actor: True,
        )
    traversal = tmp_path / "traversal.eea.zip"
    with zipfile.ZipFile(traversal, "w") as target:
        target.writestr("../escape", b"unsafe")
    with pytest.raises((BackupValidationError, zipfile.BadZipFile)):
        service.restore_project(
            traversal,
            tmp_path / "traversal-restore",
            authorized_project_id=project_id,
            actor_id="local:single-user",
            authorize=lambda _expected, _actor: True,
        )


def test_backup_writer_failure_leaves_no_success_archive(tmp_path: Path) -> None:
    project_id = uuid4()
    service = ProjectBackupService(
        failure_injector=FailureInjectionHarness(
            (
                FailurePlan(
                    FailureInjectionPoint.ARTIFACT_OBJECT_WRITE,
                    FailureScenario.DISK_FULL,
                    FailureOutcome.RECOVERABLE,
                    "disk full",
                ),
            )
        )
    )
    target = tmp_path / "not-created.eea.zip"
    with pytest.raises(InjectedFailure):
        service.export_project(project_id, target, (BackupRecord("record.json", b"{}"),))
    assert not target.exists()


def test_capacity_profiles_have_deterministic_boundary_behavior() -> None:
    profile = get_capacity_profile(CapacityProfileName.CI)
    profile.check("project_file_count", profile.maximum_project_file_count)
    with pytest.raises(CapacityExceededError):
        profile.check("project_file_count", profile.maximum_project_file_count + 1)
    with pytest.raises(ValueError):
        profile.check("unknown", 1)


def test_failure_baseline_identity_and_redaction_are_stable() -> None:
    plans = baseline_failure_plans()
    assert {plan.scenario for plan in plans} == set(FailureScenario)
    assert {plan.point for plan in plans} >= {
        FailureInjectionPoint.SQL_COMMIT,
        FailureInjectionPoint.OUTBOX_DISPATCH,
        FailureInjectionPoint.SOURCE_OBJECT_WRITE,
        FailureInjectionPoint.ARTIFACT_OBJECT_WRITE,
        FailureInjectionPoint.SANDBOX_EXECUTION,
        FailureInjectionPoint.DESKTOP_BACKEND_CONNECT,
    }
    first = local_single_user()
    second = local_single_user()
    assert first.id == second.id
    assert first.mode is IdentityMode.LOCAL_SINGLE_USER
    context = ObservabilityContext(project_id="project-1", request_id="request-1")
    assert context.as_dict() == {"request_id": "request-1", "project_id": "project-1"}
    safe = redact_sensitive(
        {"Authorization": "Bearer abc", "value": "normal", "nested": {"api_key": "x"}}
    )
    assert safe == {
        "Authorization": "[REDACTED]",
        "value": "normal",
        "nested": {"api_key": "[REDACTED]"},
    }


@pytest.mark.parametrize(
    ("left", "right", "dimension"),
    (
        ((1000, "mV"), (1, "V"), EngineeringDimension.VOLTAGE),
        ((1000, "mA"), (1, "A"), EngineeringDimension.CURRENT),
        ((180, "deg"), (3.141592653589793, "rad"), EngineeringDimension.ANGLE),
        ((60, "rpm"), (2 * 3.141592653589793, "rad/s"), EngineeringDimension.ANGULAR_VELOCITY),
        (
            (60, "rpm/s"),
            (2 * 3.141592653589793, "rad/s²"),
            EngineeringDimension.ANGULAR_ACCELERATION,
        ),
        ((1000, "mA/s"), (1, "A/s"), EngineeringDimension.CURRENT_RATE),
        ((1000, "ms"), (1, "s"), EngineeringDimension.TIME),
        ((0, "C"), (273.15, "K"), EngineeringDimension.TEMPERATURE),
    ),
)
def test_canonical_units_close_cross_unit_comparisons(left, right, dimension) -> None:
    first = EngineeringValue(unit=left[1], dimension=dimension, nominal=left[0])
    second = EngineeringValue(unit=right[1], dimension=dimension, nominal=right[0])
    assert UnitNormalizationService.compare(first, second, "==")


def test_canonical_units_reject_wrong_dimension() -> None:
    with pytest.raises(ValueError):
        EngineeringValue(unit="A", dimension=EngineeringDimension.VOLTAGE, nominal=1)
    voltage = EngineeringValue(unit="V", dimension=EngineeringDimension.VOLTAGE, nominal=1)
    current = EngineeringValue(unit="A", dimension=EngineeringDimension.CURRENT, nominal=1)
    with pytest.raises(UnitNormalizationError):
        UnitNormalizationService.compare(voltage, current, "==")


def test_m18e_api_exposes_renderer_and_identity_contract(client) -> None:
    renderer = client.get("/api/v1/renderer/security-policy")
    assert renderer.status_code == 200
    assert renderer.json()["data"]["remote_javascript_allowed"] is False
    identity = client.get("/api/v1/identity/local")
    assert identity.status_code == 200
    assert identity.json()["data"]["stable_actor_id"] == "local:single-user"
    assert client.get("/api/v1/capacity/profiles").status_code == 200


def test_remote_origin_is_denied(client) -> None:
    response = client.get(
        "/api/v1/renderer/security-policy",
        headers={"Origin": "https://remote.example"},
    )
    assert response.status_code == 403


def test_local_backend_launch_auth_rejects_missing_and_wrong_bearer(tmp_path: Path) -> None:
    with TestClient(
        create_app(Settings(data_dir=tmp_path, local_auth_required=True))
    ) as local_client:
        assert local_client.get("/api/v1/renderer/security-policy").status_code == 401
        assert (
            local_client.get(
                "/api/v1/renderer/security-policy", headers={"Authorization": "Bearer wrong"}
            ).status_code
            == 401
        )
        token = local_client.app.state.local_session_token.get_secret_value()
        assert (
            local_client.get(
                "/api/v1/renderer/security-policy", headers={"Authorization": f"Bearer {token}"}
            ).status_code
            == 200
        )


def test_manifest_serialization_has_final_hash(tmp_path: Path) -> None:
    project_id = uuid4()
    service = ProjectBackupService()
    path = tmp_path / "manifest.eea.zip"
    manifest = service.export_project(
        project_id, path, (BackupRecord("record.json", json.dumps({"id": "x"}).encode()),)
    )
    with zipfile.ZipFile(path) as archive:
        assert (
            manifest_from_json(archive.read("manifest.json")).manifest_hash
            == manifest.manifest_hash
        )


@pytest.mark.parametrize(
    "payload",
    (
        {"metadata": {"api_key": "hidden"}},
        {"metadata": {"nested": {"token": "hidden"}}},
        {"password": "hidden"},
        {"Authorization": "Bearer abcdefgh"},
        {"private_key": "-----BEGIN PRIVATE KEY-----"},
        {"credential": "sk-abcdefgh"},
    ),
)
def test_backup_structured_secret_policy_rejects_nested_secret_payloads(
    tmp_path: Path, payload: dict[str, object]
) -> None:
    with pytest.raises(BackupValidationError):
        ProjectBackupService().export_project(
            uuid4(),
            tmp_path / "secret.zip",
            (BackupRecord("record.json", json.dumps(payload).encode()),),
        )


def test_backup_secret_policy_allows_normal_metadata(tmp_path: Path) -> None:
    payload = {"metadata": {"owner": "engineering", "note": "normal"}}
    BackupSecretPolicy.assert_safe(payload)
    archive = tmp_path / "normal.zip"
    ProjectBackupService().export_project(
        uuid4(), archive, (BackupRecord("record.json", json.dumps(payload).encode()),)
    )
    assert archive.is_file()


def test_production_backend_is_fail_closed_and_tokens_are_per_session(tmp_path: Path) -> None:
    first = Settings(data_dir=tmp_path / "first", env="production")
    second = Settings(data_dir=tmp_path / "second", env="production")
    with (
        TestClient(create_app(first)) as first_client,
        TestClient(create_app(second)) as second_client,
    ):
        assert first_client.get("/api/v1/renderer/security-policy").status_code == 401
        first_token = first_client.app.state.local_session_token.get_secret_value()
        second_token = second_client.app.state.local_session_token.get_secret_value()
        assert first_token != second_token
        assert (
            first_client.get(
                "/api/v1/renderer/security-policy",
                headers={"Authorization": "Bearer wrong"},
            ).status_code
            == 401
        )
        assert (
            first_client.get(
                "/api/v1/renderer/security-policy",
                headers={"Authorization": f"Bearer {first_token}"},
            ).status_code
            == 200
        )


def test_explicit_insecure_dev_mode_is_the_only_anonymous_fallback(tmp_path: Path) -> None:
    with TestClient(create_app(Settings(data_dir=tmp_path, insecure_local_dev=True))) as dev_client:
        assert dev_client.get("/api/v1/renderer/security-policy").status_code == 200


def test_desktop_backend_client_token_boundary_is_static_and_loopback_only() -> None:
    source = Path("apps/desktop/src/api/client.ts").read_text(encoding="utf-8")
    assert "validateLoopbackBaseUrl" in source
    assert '"127.0.0.1"' in source and '"localhost"' in source and '"[::1]"' in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source
    assert "?token=" in source and "#token=" in source
    assert "console.log" not in source


def _upgrade_database(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", Settings(data_dir=path).database_url)
    command.upgrade(config, "head")


def test_backup_service_uses_real_profile_and_preflight_limits(tmp_path: Path) -> None:
    service = ProjectBackupService()
    assert service.profile.name.value == "foc-dev"
    project_id = uuid4()
    archive = tmp_path / "valid.zip"
    service.export_project(project_id, archive, (BackupRecord("record.json", b"{}"),))
    with pytest.raises(BackupOperationError):
        ProjectBackupService(
            profile=replace(service.profile, maximum_backup_member_bytes=1)
        ).validate_archive(archive)
    with pytest.raises(BackupOperationError):
        ProjectBackupService(
            profile=replace(service.profile, maximum_backup_manifest_bytes=10)
        ).validate_archive(archive)


def test_backup_preflight_rejects_total_size_and_compression_ratio(tmp_path: Path) -> None:
    project_id = uuid4()
    archive = tmp_path / "large.zip"
    ProjectBackupService().export_project(
        project_id, archive, (BackupRecord("record.json", b"a" * 100_000),)
    )
    service = ProjectBackupService(
        profile=replace(
            get_capacity_profile(CapacityProfileName.CI),
            maximum_backup_uncompressed_bytes=10,
        )
    )
    with pytest.raises(BackupOperationError):
        service.validate_archive(archive)
    ratio_service = ProjectBackupService(
        profile=replace(
            get_capacity_profile(CapacityProfileName.CI),
            maximum_backup_compression_ratio=1.0,
        )
    )
    with pytest.raises(BackupOperationError):
        ratio_service.validate_archive(archive)


def test_backup_preflight_rejects_excess_members_duplicates_and_undeclared(tmp_path: Path) -> None:
    project_id = uuid4()
    archive = tmp_path / "valid.zip"
    ProjectBackupService().export_project(
        project_id, archive, (BackupRecord("record.json", b"{}"),)
    )
    with pytest.raises(BackupOperationError):
        ProjectBackupService(
            profile=replace(
                get_capacity_profile(CapacityProfileName.CI), maximum_backup_member_count=1
            )
        ).validate_archive(archive)

    duplicate = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(duplicate, "w") as target:
        for info in source.infolist():
            target.writestr(info.filename, source.read(info))
        target.writestr("record.json", b"{}")
    with pytest.raises(BackupValidationError):
        ProjectBackupService().validate_archive(duplicate)

    undeclared = tmp_path / "undeclared.zip"
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(undeclared, "w") as target:
        for info in source.infolist():
            target.writestr(info.filename, source.read(info))
        target.writestr("extra.json", b"{}")
    with pytest.raises(BackupValidationError):
        ProjectBackupService().validate_archive(undeclared)


def test_restore_streaming_hash_and_partial_failure_never_activate(tmp_path: Path) -> None:
    project_id = uuid4()
    archive = tmp_path / "stream.zip"
    content = bytes(range(256)) * 4_096
    ProjectBackupService().export_project(
        project_id, archive, (BackupRecord("records/object.bin", content),)
    )
    destination = tmp_path / "activated"
    result = ProjectBackupService().restore_project(
        archive,
        destination,
        authorized_project_id=project_id,
        actor_id="local:single-user",
        authorize=lambda expected, actor: expected == project_id and actor == "local:single-user",
    )
    assert result.state.value == "ACTIVATED"
    assert (destination / "records/object.bin").read_bytes() == content

    failed_destination = tmp_path / "failed"
    failing_service = ProjectBackupService(
        failure_injector=FailureInjectionHarness(
            (
                FailurePlan(
                    FailureInjectionPoint.ARTIFACT_OBJECT_WRITE,
                    FailureScenario.DISK_FULL,
                    FailureOutcome.RECOVERABLE,
                    "disk full",
                ),
            )
        )
    )
    with pytest.raises(InjectedFailure):
        failing_service.restore_project(
            archive,
            failed_destination,
            authorized_project_id=project_id,
            actor_id="local:single-user",
            authorize=lambda _expected, _actor: True,
        )
    assert not failed_destination.exists()
    assert not list(tmp_path.glob(".failed.*.staging"))


def test_restore_validate_collision_and_transaction_failure_are_closed(tmp_path: Path) -> None:
    project_id = uuid4()
    archive = tmp_path / "valid.zip"
    ProjectBackupService().export_project(
        project_id, archive, (BackupRecord("records/project.json", b"{}"),)
    )
    assert not (tmp_path / "not-activated").exists()
    assert ProjectBackupService().validate_archive(archive).project_id == project_id
    collision = tmp_path / "collision"
    collision.mkdir()
    with pytest.raises(BackupOperationError):
        ProjectBackupService().restore_project(
            archive,
            collision,
            authorized_project_id=project_id,
            actor_id="local:single-user",
            authorize=lambda _expected, _actor: True,
        )
    failed = tmp_path / "transaction-failed"
    with pytest.raises(RuntimeError):
        ProjectBackupService().restore_project(
            archive,
            failed,
            authorized_project_id=project_id,
            actor_id="local:single-user",
            authorize=lambda _expected, _actor: True,
            before_activate=lambda _staging, _manifest: (_ for _ in ()).throw(
                RuntimeError("transaction failed")
            ),
        )
    assert not failed.exists()


def test_api_clean_database_restore_reopens_project(tmp_path: Path) -> None:
    source_root = tmp_path / "source-db"
    _upgrade_database(source_root)
    source_settings = Settings(data_dir=source_root, insecure_local_dev=True)
    with TestClient(create_app(source_settings)) as source_client:
        created = source_client.post("/api/v1/projects", json={"name": "portable project"})
        assert created.status_code == 201
        project_id = created.json()["data"]["id"]
        exported = source_client.post(
            f"/api/v1/projects/{project_id}/exports",
            json={"destination": "exports/portable.zip"},
        )
        assert exported.status_code == 200
        source_archive = Path(exported.json()["data"]["archive_path"])

    clean_root = tmp_path / "clean-db"
    _upgrade_database(clean_root)
    clean_settings = Settings(data_dir=clean_root, insecure_local_dev=True)
    clean_root.mkdir(parents=True, exist_ok=True)
    target_archive = clean_root / "restore.zip"
    shutil.copy2(source_archive, target_archive)
    with TestClient(create_app(clean_settings)) as clean_client:
        validation = clean_client.post(
            "/api/v1/projects/restore/validate",
            json={"archive_path": "restore.zip", "project_id": project_id},
        )
        assert validation.status_code == 200
        assert validation.json()["data"]["state"] == "VALIDATED"
        restored = clean_client.post(
            "/api/v1/projects/restore",
            json={"archive_path": "restore.zip", "project_id": project_id},
        )
        assert restored.status_code == 200
        assert restored.json()["data"]["state"] == "ACTIVATED"
        reopened = clean_client.get(f"/api/v1/projects/{project_id}")
        assert reopened.status_code == 200
        assert reopened.json()["data"]["name"] == "portable project"
