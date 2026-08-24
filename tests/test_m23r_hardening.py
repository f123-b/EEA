"""M23R authority, identity, freshness, and generic-workflow regressions."""

from uuid import uuid4

from eea_application.knowledge_authority import (
    EvidenceContext,
    KnowledgeFreshnessService,
    VerificationAuthorityResolver,
)
from eea_core.entities import KnowledgeEntry
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


def _project(client: TestClient, name: str = "M23R project") -> str:
    response = client.post("/api/v1/projects", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def _entry(client: TestClient, project_id: str, **extra: object) -> dict[str, object]:
    response = client.post(
        "/api/v1/memory/entries",
        json={
            "project_id": project_id,
            "scope": "PROJECT_PRIVATE",
            "knowledge_type": "PATTERN",
            "title": "Authority test entry",
            "summary": "backend authority regression",
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_client_identity_and_verification_claims_are_ignored_or_blocked(
    client: TestClient,
) -> None:
    project_id = _project(client)
    entry = _entry(
        client,
        project_id,
        scope="USER_PRIVATE",
        owner_ref="forged-user",
        authority_level="T0_OFFICIAL",
        verification_levels=["HARDWARE_VERIFIED"],
        freshness_score=0,
    )
    assert entry["owner_ref"] == "local:single-user"
    assert entry["authority_level"] == "T6_AI_INFERENCE"
    assert entry["verification_levels"] == []
    assert entry["freshness_score"] == 1.0

    fake_verify = client.post(
        f"/api/v1/memory/entries/{entry['id']}/review",
        json={
            "project_id": project_id,
            "actor_ref": "forged-reviewer",
            "expected_revision": entry["revision"],
            "action": "VERIFY",
            "verification_level": "HARDWARE_VERIFIED",
        },
    )
    assert fake_verify.status_code == 422, fake_verify.text

    accepted = client.post(
        f"/api/v1/memory/entries/{entry['id']}/review",
        json={
            "project_id": project_id,
            "actor_ref": "forged-reviewer",
            "expected_revision": entry["revision"],
            "action": "ACCEPT",
        },
    )
    assert accepted.status_code == 200, accepted.text
    accepted_data = accepted.json()["data"]
    assert accepted_data["verification_levels"] == ["USER_CONFIRMED"]
    assert accepted_data["trust_level"] == "MEDIUM"
    assert accepted_data["reviewed_by"] == "local:single-user"


def test_organization_scope_fails_closed_without_authenticated_organization(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/memory/entries",
        json={
            "scope": "ORGANIZATION_PRIVATE",
            "organization_ref": "forged-org",
            "knowledge_type": "NOTE",
            "title": "must not be created",
        },
    )
    assert response.status_code == 400


def test_workflow_descriptor_is_backend_owned(client: TestClient) -> None:
    response = client.get("/api/v1/workflows/descriptor")
    assert response.status_code == 200, response.text
    descriptor = response.json()["data"]
    assert descriptor["workflow_id"] == "generic_embedded_release"
    assert descriptor["stages"][0]["capability"] == "requirements.analyze"


def test_authority_resolver_and_freshness_service_fail_closed() -> None:
    source = uuid4()
    entry = KnowledgeEntry(
        project_id=uuid4(),
        scope=KnowledgeScope.PROJECT_PRIVATE,
        knowledge_type=KnowledgeType.PATTERN,
        title="entry",
        source_revision_id=source,
        authority_level=AuthorityLevel.T6_AI_INFERENCE,
        trust_level=TrustLevel.UNTRUSTED,
        lifecycle=KnowledgeLifecycle.CANDIDATE,
    )
    resolver = VerificationAuthorityResolver()
    fake_hardware = resolver.resolve(
        entry,
        "VERIFY",
        VerificationLevel.HARDWARE_VERIFIED,
        (
            EvidenceContext(
                evidence_id=uuid4(),
                project_id=entry.project_id,
                evidence_type=EvidenceType.HARDWARE_TEST,
                locator={"status": "PASS"},
            ),
        ),
    )
    assert not fake_hardware.allowed

    tool = resolver.resolve(
        entry,
        "VERIFY",
        VerificationLevel.TOOL_VERIFIED,
        (
            EvidenceContext(
                evidence_id=uuid4(),
                project_id=entry.project_id,
                evidence_type=EvidenceType.TOOL,
                locator={"status": "PASS", "source_revision_id": str(source)},
                source_revision_id=source,
            ),
        ),
        current_source_revision_id=source,
    )
    assert tool.allowed
    assert tool.verification_levels == (VerificationLevel.TOOL_VERIFIED,)

    stale, decision = KnowledgeFreshnessService().reconcile(
        entry, current_source_revision_id=uuid4(), conflict_open=False
    )
    assert decision.status == "STALE"
    assert stale.lifecycle is KnowledgeLifecycle.STALE
    assert stale.trust_level is TrustLevel.UNTRUSTED
