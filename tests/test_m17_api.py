"""M17 API integration tests for persistence, scope, and review closure."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from eea_backend.models import SourceRevisionRecord
from eea_backend.requirement_repositories import SqlAlchemyRequirementRepository
from eea_core.enums import RequirementPriority, RequirementStatus, RequirementType
from eea_core.requirements import Requirement
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _project(client: TestClient, name: str) -> dict[str, object]:
    response = client.post("/api/v1/projects", json={"name": name})
    assert response.status_code == 201
    return response.json()["data"]


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
                created_by="m17-test",
            )
        )
        session.commit()
    return source_id


def _requirement(client: TestClient, project_id: UUID) -> UUID:
    requirement = Requirement(
        project_id=project_id,
        code="REQ-M17-001",
        title="The release test is traceable",
        requirement_type=RequirementType.FUNCTIONAL,
        priority=RequirementPriority.MUST,
        statement="The release test must be traceable.",
        acceptance_criteria=["A deterministic test case exists."],
        status=RequirementStatus.ACCEPTED,
    )
    with Session(client.app.state.engine) as session:
        saved = SqlAlchemyRequirementRepository(session).add(requirement)
    return saved.id


def test_m17_api_persists_traceability_and_fails_closed_execution(client: TestClient) -> None:
    project = _project(client, "M17 primary")
    project_id = UUID(str(project["id"]))
    source_id = _source(client, project_id)
    _requirement(client, project_id)

    generated = client.post(f"/api/v1/projects/{project_id}/tests/generate", json={})
    assert generated.status_code == 201
    test_ir = generated.json()["data"]["test_ir"]
    assert len(test_ir["cases"]) == 1

    repeated = client.post(f"/api/v1/projects/{project_id}/tests/generate", json={})
    assert repeated.status_code == 201
    assert repeated.json()["data"]["test_ir"]["id"] == test_ir["id"]

    run = client.post(
        f"/api/v1/projects/{project_id}/tests/run",
        json={"test_ir_id": test_ir["id"], "source_revision_id": str(source_id)},
    )
    assert run.status_code == 201
    assert run.json()["data"]["status"] == "BLOCKED"

    coverage = client.get(f"/api/v1/projects/{project_id}/tests/coverage")
    assert coverage.status_code == 200
    assert coverage.json()["data"]["design_coverage_ratio"] == 1.0
    assert coverage.json()["data"]["verification_coverage_ratio"] == 0.0

    traceability = client.get(f"/api/v1/projects/{project_id}/traceability")
    assert traceability.status_code == 200
    assert len(traceability.json()["data"]["edges"]) == 3

    review = client.post(
        f"/api/v1/projects/{project_id}/review",
        json={"source_revision_id": str(source_id), "test_ir_id": test_ir["id"]},
    )
    assert review.status_code == 201
    assert review.json()["data"]["status"] == "BLOCKED"
    issue_ids = review.json()["data"]["issue_ids"]
    assert len(issue_ids) == 1

    repeated_review = client.post(
        f"/api/v1/projects/{project_id}/review",
        json={"source_revision_id": str(source_id), "test_ir_id": test_ir["id"]},
    )
    assert repeated_review.status_code == 201
    issues = client.get(f"/api/v1/projects/{project_id}/issues").json()["data"]["items"]
    assert len(issues) == 1
    assert issues[0]["id"] == issue_ids[0]
    assert issues[0]["occurrence_count"] == 2

    stale = client.post(
        f"/api/v1/issues/{issue_ids[0]}/resolve",
        headers={"If-Match": 'W/"1"'},
        json={"project_id": str(project_id), "reason": "stale", "expected_revision": 1},
    )
    assert stale.status_code == 409


def test_m17_api_rejects_cross_project_test_and_issue_reads(client: TestClient) -> None:
    first = _project(client, "M17 first")
    second = _project(client, "M17 second")
    first_id = UUID(str(first["id"]))
    second_id = UUID(str(second["id"]))
    source_id = _source(client, first_id)
    _requirement(client, first_id)
    generated = client.post(f"/api/v1/projects/{first_id}/tests/generate", json={})
    test_ir_id = generated.json()["data"]["test_ir"]["id"]

    cross_run = client.post(
        f"/api/v1/projects/{second_id}/tests/run",
        json={"test_ir_id": test_ir_id, "source_revision_id": str(source_id)},
    )
    assert cross_run.status_code == 400
    assert cross_run.json()["error"]["code"] == "KNOWLEDGE_SCOPE_DENIED"

    review = client.post(
        f"/api/v1/projects/{first_id}/review",
        json={"source_revision_id": str(source_id), "test_ir_id": test_ir_id},
    )
    issue_id = review.json()["data"]["issue_ids"][0]
    cross_issue = client.get(f"/api/v1/issues/{issue_id}", params={"project_id": str(second_id)})
    assert cross_issue.status_code == 400
    assert cross_issue.json()["error"]["code"] == "KNOWLEDGE_SCOPE_DENIED"


def test_m17_api_rejects_cross_project_review_inputs(client: TestClient) -> None:
    first = _project(client, "M17 review first")
    second = _project(client, "M17 review second")
    first_id = UUID(str(first["id"]))
    second_id = UUID(str(second["id"]))
    first_source = _source(client, first_id)
    second_source = _source(client, second_id)
    _requirement(client, first_id)
    generated = client.post(f"/api/v1/projects/{first_id}/tests/generate", json={})
    test_ir_id = generated.json()["data"]["test_ir"]["id"]

    response = client.post(
        f"/api/v1/projects/{second_id}/review",
        json={"source_revision_id": str(second_source), "test_ir_id": test_ir_id},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "KNOWLEDGE_SCOPE_DENIED"

    valid_review = client.post(
        f"/api/v1/projects/{first_id}/review",
        json={"source_revision_id": str(first_source), "test_ir_id": test_ir_id},
    )
    assert valid_review.status_code == 201
