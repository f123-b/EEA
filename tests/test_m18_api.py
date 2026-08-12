"""M18 API and real mutation-path smoke tests."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from eea_backend.claim_repositories import SqlAlchemyEngineeringClaimRepository
from eea_backend.models import SourceRevisionRecord
from eea_core.claims import EngineeringClaim
from eea_core.enums import ClaimLifecycle
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _project(client: TestClient, name: str) -> UUID:
    response = client.post("/api/v1/projects", json={"name": name})
    assert response.status_code == 201
    return UUID(response.json()["data"]["id"])


def _source(client: TestClient, project_id: UUID) -> UUID:
    source_id = uuid4()
    now = datetime.now(UTC)
    with Session(client.app.state.engine) as session:
        session.add(
            SourceRevisionRecord(
                id=str(source_id),
                schema_version="1.0",
                revision=1,
                created_at=now,
                updated_at=now,
                entity_metadata={},
                project_id=str(project_id),
                repository_id="fixture",
                commit_sha="a" * 40,
                tree_hash="b" * 64,
                dirty=False,
                base_commit=None,
                workspace_revision=0,
                source_manifest_hash="c" * 64,
                file_manifest={},
                created_by="m18-test",
            )
        )
        session.commit()
    return source_id


def test_m18_impact_dependencies_and_project_isolation(client: TestClient) -> None:
    project_id = _project(client, "M18 graph")
    other_id = _project(client, "M18 other")
    _source(client, project_id)
    claim = EngineeringClaim(
        project_id=project_id,
        subject_ref="device:fixture",
        predicate="device.errata",
        value={"id": "ERR-1", "text": "pin errata"},
        confidence=1,
        source_priority=100,
        lifecycle=ClaimLifecycle.ACTIVE,
    )
    with Session(client.app.state.engine) as session:
        saved = SqlAlchemyEngineeringClaimRepository(session).add(claim)
    missing = client.get(
        f"/api/v1/entities/Claim/{saved.id}/dependencies",
        params={"project_id": str(other_id)},
    )
    assert missing.status_code == 200
    assert missing.json()["data"]["items"] == []
    impact = client.post(
        f"/api/v1/entities/Claim/{saved.id}/impact-analysis",
        params={"project_id": str(project_id)},
    )
    assert impact.status_code == 200
    assert impact.json()["data"]["plan"]["source"]["entity_id"] == str(saved.id)


def test_m18_claim_lifecycle_real_mutation_is_cas_protected(client: TestClient) -> None:
    project_id = _project(client, "M18 claim mutation")
    claim = EngineeringClaim(
        project_id=project_id,
        subject_ref="device:fixture",
        predicate="device.errata",
        value={"id": "ERR-2"},
        confidence=1,
        source_priority=100,
        lifecycle=ClaimLifecycle.ACTIVE,
    )
    with Session(client.app.state.engine) as session:
        saved = SqlAlchemyEngineeringClaimRepository(session).add(claim)
    response = client.post(
        f"/api/v1/claims/{saved.id}/lifecycle",
        json={
            "project_id": str(project_id),
            "expected_revision": 1,
            "lifecycle": ClaimLifecycle.SUPERSEDED.value,
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["claim"]["lifecycle"] == ClaimLifecycle.SUPERSEDED.value
    conflict = client.post(
        f"/api/v1/claims/{saved.id}/lifecycle",
        json={
            "project_id": str(project_id),
            "expected_revision": 1,
            "lifecycle": ClaimLifecycle.ACTIVE.value,
        },
    )
    assert conflict.status_code == 409


def test_m18_artifact_routes_are_present_and_scoped(client: TestClient) -> None:
    project_id = _project(client, "M18 artifacts")
    response = client.get(f"/api/v1/projects/{project_id}/artifacts")
    assert response.status_code == 200
    assert response.json()["data"]["items"] == []
    stale = client.get(f"/api/v1/projects/{project_id}/artifacts/stale")
    assert stale.status_code == 200
