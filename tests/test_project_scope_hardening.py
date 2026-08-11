"""Cross-project isolation acceptance tests for Documents, DocumentIR, and Evidence."""

import base64
from uuid import UUID

import pytest
from eea_application.intelligence import DocumentService
from eea_backend.document_repositories import (
    SqlAlchemyDocumentIRRepository,
    SqlAlchemyDocumentRepository,
)
from eea_backend.repositories import SqlAlchemyEvidenceRepository
from eea_core.entities import Evidence
from eea_core.enums import DocumentType, EngineeringErrorCode, EvidenceType
from eea_core.errors import EngineeringError
from eea_core.intelligence import DocumentIR
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _project(client: TestClient, name: str) -> UUID:
    response = client.post("/api/v1/projects", json={"name": name})
    assert response.status_code == 201
    return UUID(response.json()["data"]["id"])


def _upload(
    client: TestClient, project_id: UUID, filename: str, content: bytes
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/projects/{project_id}/documents",
        json={
            "filename": filename,
            "content_base64": base64.b64encode(content).decode(),
            "document_type": DocumentType.USER_DOCUMENT.value,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_document_read_is_project_scoped(client: TestClient) -> None:
    project_a = _project(client, "scope A")
    project_b = _project(client, "scope B")
    document = _upload(client, project_a, "a.pdf", b"private A")

    allowed = client.get(f"/api/v1/projects/{project_a}/documents/{document['id']}")
    assert allowed.status_code == 200
    denied = client.get(f"/api/v1/projects/{project_b}/documents/{document['id']}")
    assert denied.status_code == 400
    assert denied.json()["error"]["code"] == EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED.value

    unknown = client.get(f"/api/v1/projects/{project_a}/documents/{UUID(int=0)}")
    assert unknown.status_code == 400
    assert unknown.json()["error"]["code"] == EngineeringErrorCode.DOCUMENT_PARSE_FAILED.value


def test_evidence_read_is_project_scoped(client: TestClient) -> None:
    project_a = _project(client, "evidence A")
    project_b = _project(client, "evidence B")
    created = client.post(
        f"/api/v1/projects/{project_a}/evidence",
        json={
            "evidence_type": EvidenceType.DOCUMENT.value,
            "locator": {"filename": "private.pdf"},
        },
    )
    assert created.status_code == 201, created.text
    evidence_id = created.json()["data"]["id"]

    allowed = client.get(f"/api/v1/projects/{project_a}/evidence/{evidence_id}")
    assert allowed.status_code == 200
    denied = client.get(f"/api/v1/projects/{project_b}/evidence/{evidence_id}")
    assert denied.status_code == 400
    assert denied.json()["error"]["code"] == EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED.value


def test_same_content_creates_distinct_project_documents(client: TestClient) -> None:
    project_a = _project(client, "same bytes A")
    project_b = _project(client, "same bytes B")
    first = _upload(client, project_a, "a.pdf", b"same bytes")
    second = _upload(client, project_b, "b.pdf", b"same bytes")

    assert first["id"] != second["id"]
    assert first["project_id"] == str(project_a)
    assert second["project_id"] == str(project_b)
    assert first["content_hash"] == second["content_hash"]
    assert first["storage_uri"] == second["storage_uri"]


def test_repository_and_service_scope_checks_apply_without_http(client: TestClient) -> None:
    project_a = _project(client, "direct A")
    project_b = _project(client, "direct B")
    document_data = _upload(client, project_a, "a.pdf", b"direct private")
    document_id = UUID(str(document_data["id"]))

    with Session(client.app.state.engine) as session:
        documents = SqlAlchemyDocumentRepository(session)
        assert documents.get(document_id, project_id=project_a) is not None
        assert documents.get(document_id, project_id=project_b) is None

        ir = DocumentIR(document_id=document_id, parser="fixture", parser_version="1")
        SqlAlchemyDocumentIRRepository(session).add(ir)
        assert (
            SqlAlchemyDocumentIRRepository(session).get_for_document(
                document_id, project_id=project_b
            )
            is None
        )

        evidence = SqlAlchemyEvidenceRepository(session).add(
            Evidence(
                project_id=project_a,
                evidence_type=EvidenceType.DOCUMENT,
                locator={"filename": "a.pdf"},
            )
        )
        evidence_repository = SqlAlchemyEvidenceRepository(session)
        assert evidence_repository.get(evidence.id, project_id=project_b) is None

        service = DocumentService(documents, client.app.state.settings.data_dir)
        with pytest.raises(EngineeringError) as error:
            service.get(document_id, project_id=project_b)
        assert error.value.code is EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED
