"""M23R trust, identity, freshness, propagation, and audit closure tests."""

from uuid import uuid4

from eea_application.knowledge_authority import EvidenceContext, VerificationAuthorityResolver
from eea_application.knowledge_identity import IdentityContext
from eea_backend.models import EngineeringClaimRecord
from eea_core.entities import KnowledgeEntry, utc_now
from eea_core.enums import (
    AuthorityLevel,
    EvidenceType,
    KnowledgeLifecycle,
    KnowledgeScope,
    KnowledgeType,
    TrustLevel,
    VerificationLevel,
)
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _project(client: TestClient, name: str = "M23R closure") -> str:
    response = client.post("/api/v1/projects", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def test_identity_scope_policy_fails_closed_for_team_context() -> None:
    context = IdentityContext(
        principal_id="user:viewer",
        user_id="user:viewer",
        authentication_source="team",
        project_permissions={"project-1": frozenset({"read"})},
    )
    assert context.can_project("project-1", "read")
    assert not context.can_project("project-2", "read")
    assert not context.can_publish_global()
    assert "PROJECT_PRIVATE" in context.allowed_scopes(project_id="project-1")
    assert "PROJECT_PRIVATE" not in context.allowed_scopes(project_id="project-2")
    assert "TASK_ONLY" not in context.allowed_scopes(project_id="project-1")


def test_strict_tool_and_hardware_provenance_is_backend_only() -> None:
    source = uuid4()
    entry = KnowledgeEntry(
        project_id=uuid4(),
        scope=KnowledgeScope.PROJECT_PRIVATE,
        knowledge_type=KnowledgeType.PATTERN,
        title="strict evidence",
        source_revision_id=source,
        authority_level=AuthorityLevel.T6_AI_INFERENCE,
        trust_level=TrustLevel.UNTRUSTED,
        lifecycle=KnowledgeLifecycle.CANDIDATE,
    )
    resolver = VerificationAuthorityResolver()
    tool_locator = {
        "status": "PASS",
        "source_revision_id": str(source),
        "producer": "eea.rule-engine",
        "producer_version": "1.0.0",
        "timestamp": utc_now().isoformat(),
    }
    tool = resolver.resolve(
        entry,
        "VERIFY",
        VerificationLevel.TOOL_VERIFIED,
        (
            EvidenceContext(
                evidence_id=uuid4(),
                project_id=entry.project_id,
                evidence_type=EvidenceType.TOOL,
                locator=tool_locator,
                source_revision_id=source,
            ),
        ),
        current_source_revision_id=source,
        strict_provenance=True,
    )
    assert tool.allowed
    hardware = resolver.resolve(
        entry,
        "VERIFY",
        VerificationLevel.HARDWARE_VERIFIED,
        (
            EvidenceContext(
                evidence_id=uuid4(),
                project_id=entry.project_id,
                evidence_type=EvidenceType.HARDWARE_TEST,
                locator={
                    **tool_locator,
                    "hardware_identity": "board-1",
                    "probe_identity": "probe-1",
                },
                source_revision_id=source,
            ),
        ),
        current_source_revision_id=source,
        strict_provenance=True,
    )
    assert not hardware.allowed


def test_evidence_invalidation_filters_memory_and_memory_edit_uses_cas(
    client: TestClient,
) -> None:
    project_id = _project(client, "M23R evidence propagation")
    evidence = client.post(
        f"/api/v1/projects/{project_id}/evidence",
        json={"evidence_type": "DOCUMENT", "locator": {"producer": "manual"}},
    )
    assert evidence.status_code == 201, evidence.text
    evidence_data = evidence.json()["data"]
    created = client.post(
        "/api/v1/memory/entries",
        json={
            "project_id": project_id,
            "scope": "PROJECT_PRIVATE",
            "knowledge_type": "NOTE",
            "title": "Evidence-backed note",
            "evidence_ids": [evidence_data["id"]],
        },
    )
    assert created.status_code == 201, created.text
    entry = created.json()["data"]
    assert entry["provenance"]["evidence_ids"] == [evidence_data["id"]]

    invalidated = client.post(
        f"/api/v1/projects/{project_id}/evidence/{evidence_data['id']}/invalidate",
        json={
            "project_id": project_id,
            "expected_revision": evidence_data["revision"],
            "reason": "document hash no longer matches the source",
        },
    )
    assert invalidated.status_code == 200, invalidated.text

    recalled = client.post(
        "/api/v1/memory/recall",
        json={
            "project_id": project_id,
            "scope_context": ["PROJECT_PRIVATE"],
            "query": "Evidence-backed",
        },
    )
    assert recalled.status_code == 200, recalled.text
    assert recalled.json()["data"]["items"] == []
    history = client.post(
        "/api/v1/memory/recall",
        json={
            "project_id": project_id,
            "scope_context": ["PROJECT_PRIVATE"],
            "query": "Evidence-backed",
            "include_non_active": True,
        },
    )
    assert history.status_code == 200, history.text
    assert history.json()["data"]["items"][0]["entry"]["lifecycle"] == "STALE"

    edited = client.patch(
        f"/api/v1/memory/entries/{entry['id']}",
        json={
            "project_id": project_id,
            "expected_revision": history.json()["data"]["items"][0]["entry"]["revision"],
            "title": "Edited stale note",
            "note": "Keep the stale projection for audit history",
        },
    )
    assert edited.status_code == 200, edited.text
    stale_revision = edited.json()["data"]["revision"]
    conflict = client.patch(
        f"/api/v1/memory/entries/{entry['id']}",
        json={"project_id": project_id, "expected_revision": stale_revision - 1, "title": "lost"},
    )
    assert conflict.status_code == 409, conflict.text


def test_conflict_resolution_requires_explicit_memory_revalidation(
    client: TestClient,
) -> None:
    project_id = _project(client, "M23R conflict propagation")
    claim_ids = [uuid4(), uuid4()]
    with Session(client.app.state.engine) as session:
        now = utc_now()
        for claim_id in claim_ids:
            session.add(
                EngineeringClaimRecord(
                    id=str(claim_id),
                    schema_version="1.0",
                    revision=1,
                    created_at=now,
                    updated_at=now,
                    entity_metadata={},
                    project_id=project_id,
                    subject_ref="board:1",
                    predicate="bus.termination",
                    value_schema_ref="eea.test.v1",
                    value_json={"value": str(claim_id)},
                    applicability={},
                    evidence_ids=[],
                    verification_levels=[],
                    confidence=0.5,
                    source_priority=100,
                    source_version="test",
                    lifecycle="CANDIDATE",
                )
            )
        session.commit()

    opened = client.post(
        f"/api/v1/projects/{project_id}/claims/conflicts",
        json={
            "claim_a_id": str(claim_ids[0]),
            "claim_b_id": str(claim_ids[1]),
            "reason": "two canonical values overlap",
        },
    )
    assert opened.status_code == 201, opened.text
    conflict_id = opened.json()["data"]["conflict_id"]
    created = client.post(
        "/api/v1/memory/entries",
        json={
            "project_id": project_id,
            "scope": "PROJECT_PRIVATE",
            "knowledge_type": "CLAIM_SET",
            "title": "conflicted claim projection",
            "claim_ids": [str(value) for value in claim_ids],
        },
    )
    assert created.status_code == 201, created.text
    entry = created.json()["data"]
    assert entry["lifecycle"] == "CONFLICTED"

    resolved = client.post(
        f"/api/v1/claims/conflicts/{conflict_id}/resolve",
        json={
            "project_id": project_id,
            "expected_revision": 1,
            "selected_claim_id": str(claim_ids[0]),
            "reason": "selected the higher-priority canonical claim",
        },
    )
    assert resolved.status_code == 200, resolved.text
    recalled = client.post(
        "/api/v1/memory/recall",
        json={
            "project_id": project_id,
            "scope_context": ["PROJECT_PRIVATE"],
            "query": "conflicted",
        },
    )
    assert recalled.status_code == 200, recalled.text
    assert recalled.json()["data"]["items"] == []

    current = client.get(f"/api/v1/memory/entries/{entry['id']}?project_id={project_id}")
    assert current.status_code == 200, current.text
    revalidated = client.post(
        f"/api/v1/memory/entries/{entry['id']}/review",
        json={
            "project_id": project_id,
            "expected_revision": current.json()["data"]["revision"],
            "action": "RESOLVE_CONFLICT",
            "note": "Canonical conflict was resolved; revalidate next.",
        },
    )
    assert revalidated.status_code == 200, revalidated.text
    assert revalidated.json()["data"]["lifecycle"] == "CANDIDATE"
