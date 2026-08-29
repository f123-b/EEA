"""M24A API safety, provenance and review regression tests."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from eea_backend.models import EvidenceRecord, SourceRevisionRecord
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _seed_source_and_evidence(client: TestClient, project_id: UUID) -> UUID:
    source_id = uuid4()
    evidence_id = uuid4()
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
                repository_id="test/repository",
                commit_sha="a" * 40,
                tree_hash="b" * 64,
                dirty=False,
                base_commit=None,
                workspace_revision=1,
                source_manifest_hash="c" * 64,
                file_manifest={"src/can.c": "d" * 64, "include/can.h": "e" * 64},
                created_by="test",
            )
        )
        session.add(
            EvidenceRecord(
                id=str(evidence_id),
                schema_version="1.0",
                revision=1,
                created_at=now,
                updated_at=now,
                entity_metadata={},
                project_id=str(project_id),
                evidence_type="USER_CONFIRMATION",
                locator={"source_revision_id": str(source_id)},
                source_uri="test://m24a/can-heartbeat",
                content_hash="f" * 64,
                summary="CAN heartbeat acceptance evidence",
            )
        )
        session.commit()
    return source_id


def _project(client: TestClient) -> UUID:
    response = client.post("/api/v1/projects", json={"name": "M24A planning project"})
    assert response.status_code == 201
    return UUID(response.json()["data"]["id"])


def test_m24a_plan_round_trip_is_structured_and_plan_only(client: TestClient) -> None:
    project_id = _project(client)
    source_id = _seed_source_and_evidence(client, project_id)
    requirement = client.post(
        f"/api/v1/projects/{project_id}/engineering-requirements",
        json={
            "title": "Trace CAN heartbeat timing",
            "description": "Investigate a CAN heartbeat timing requirement.",
            "requirement_type": "INVESTIGATION",
            "priority": "MUST",
            "constraints": ["Do not change the source automatically"],
            "acceptance_criteria": ["Heartbeat timing is measured against the stated interval"],
        },
    )
    assert requirement.status_code == 201, requirement.text
    requirement_id = requirement.json()["data"]["id"]

    generated = client.post(
        f"/api/v1/engineering-requirements/{requirement_id}/plans",
        json={"source_revision_id": str(source_id), "provider": "deterministic"},
    )
    assert generated.status_code == 201, generated.text
    plan = generated.json()["data"]
    assert plan["status"] == "READY_FOR_REVIEW"
    assert plan["plan_only"] is True
    assert plan["proposed_changes"]
    assert plan["steps"]
    assert plan["verification_plans"]
    assert plan["evidence_refs"]
    assert all(item["execution_allowed_in_m24a"] is False for item in plan["verification_plans"])
    assert all("apply patch" not in str(item).lower() for item in plan["proposed_changes"])

    context = client.get(f"/api/v1/engineering-plans/{plan['id']}/context")
    assert context.status_code == 200
    context_data = context.json()["data"]
    assert context_data["source_content_is_untrusted"] is True
    assert any(item["authority"] == "UNTRUSTED_SOURCE" for item in context_data["selected_context"])
    assert context_data["evidence_refs"]

    impact = client.get(f"/api/v1/engineering-plans/{plan['id']}/impact")
    assert impact.status_code == 200
    assert impact.json()["data"]["plan_only"] is True
    assert impact.json()["data"]["direct_impact"]


def test_m24a_review_cas_and_revision_request_never_authorize_execution(
    client: TestClient,
) -> None:
    project_id = _project(client)
    source_id = _seed_source_and_evidence(client, project_id)
    requirement = client.post(
        f"/api/v1/projects/{project_id}/engineering-requirements",
        json={
            "title": "Plan CAN heartbeat investigation",
            "description": (
                "Investigate CAN heartbeat timing without changing source automatically."
            ),
            "requirement_type": "INVESTIGATION",
            "acceptance_criteria": ["A measurement experiment is defined"],
        },
    ).json()["data"]
    plan = client.post(
        f"/api/v1/engineering-requirements/{requirement['id']}/plans",
        json={"source_revision_id": str(source_id)},
    ).json()["data"]

    revised = client.post(
        f"/api/v1/engineering-plans/{plan['id']}/review",
        json={
            "expected_revision": plan["revision"],
            "action": "REQUEST_REVISION",
            "comment": "Clarify the measurement boundary before review.",
        },
    )
    assert revised.status_code == 200, revised.text
    new_plan = revised.json()["data"]["plan"]
    assert new_plan["revision"] == plan["revision"] + 1
    assert new_plan["supersedes_plan_id"] == plan["id"]
    assert revised.json()["data"]["execution_authorized"] is False

    stale_review = client.post(
        f"/api/v1/engineering-plans/{plan['id']}/review",
        json={
            "expected_revision": plan["revision"],
            "action": "APPROVE",
            "comment": "This must fail the CAS check.",
        },
    )
    assert stale_review.status_code == 409, stale_review.text

    approved = client.post(
        f"/api/v1/engineering-plans/{new_plan['id']}/review",
        json={
            "expected_revision": new_plan["revision"],
            "action": "APPROVE",
            "comment": "Approved as a plan only.",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["plan"]["status"] == "APPROVED"
    assert approved.json()["data"]["execution_authorized"] is False


def test_m24a_rejects_unknown_request_fields_and_exposes_missing_context_as_input(
    client: TestClient,
) -> None:
    project_id = _project(client)
    invalid = client.post(
        f"/api/v1/projects/{project_id}/engineering-requirements",
        json={"title": "Unknown field", "execute": True},
    )
    assert invalid.status_code == 422

    requirement = client.post(
        f"/api/v1/projects/{project_id}/engineering-requirements",
        json={"title": "Plan with no source snapshot"},
    ).json()["data"]
    plan = client.post(
        f"/api/v1/engineering-requirements/{requirement['id']}/plans", json={}
    )
    assert plan.status_code == 201, plan.text
    assert plan.json()["data"]["status"] == "NEEDS_INPUT"
    assert plan.json()["data"]["plan_only"] is True
