"""M23 Knowledge & Memory scope, review, and M22 promotion acceptance."""

from pathlib import Path

from fastapi.testclient import TestClient


def _project(client: TestClient, name: str) -> str:
    response = client.post("/api/v1/projects", json={"name": name, "description": "M23 test"})
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _memory(client: TestClient, project_id: str, title: str, **extra: object) -> dict[str, object]:
    response = client.post(
        "/api/v1/memory/entries",
        json={
            "project_id": project_id,
            "scope": "PROJECT_PRIVATE",
            "knowledge_type": "PATTERN",
            "title": title,
            "summary": f"Summary for {title}",
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_memory_recall_is_scope_filtered_and_review_is_revisioned(client: TestClient) -> None:
    first = _project(client, "first")
    second = _project(client, "second")

    global_response = client.post(
        "/api/v1/memory/entries",
        json={
            "scope": "GLOBAL_PUBLIC",
            "knowledge_type": "REFERENCE_ARCHITECTURE",
            "title": "Official CAN termination guide",
            "summary": "Use the vendor reference when selecting bus termination.",
            "authority_level": "T1_VENDOR",
        },
    )
    assert global_response.status_code == 201, global_response.text
    project_entry = _memory(client, first, "First project CAN pattern", tags=["can", "termination"])
    _memory(client, second, "Second project private pattern")

    recalled = client.post(
        "/api/v1/memory/recall",
        json={
            "project_id": first,
            "actor_ref": "desktop:test",
            "scope_context": ["GLOBAL_PUBLIC", "PROJECT_PRIVATE"],
            "query": "CAN termination",
            "limit": 20,
        },
    )
    assert recalled.status_code == 200, recalled.text
    data = recalled.json()["data"]
    titles = [item["entry"]["title"] for item in data["items"]]
    assert "Official CAN termination guide" in titles
    assert "First project CAN pattern" in titles
    assert "Second project private pattern" not in titles
    assert data["audit_id"]

    accepted = client.post(
        f"/api/v1/memory/entries/{project_entry['id']}/review",
        json={
            "project_id": first,
            "actor_ref": "desktop:test",
            "expected_revision": project_entry["revision"],
            "action": "ACCEPT",
            "note": "Confirmed with the project review",
        },
    )
    assert accepted.status_code == 200, accepted.text
    accepted_data = accepted.json()["data"]
    assert accepted_data["lifecycle"] == "ACTIVE"
    assert accepted_data["trust_level"] == "MEDIUM"
    assert "USER_CONFIRMED" in accepted_data["verification_levels"]

    conflict = client.post(
        f"/api/v1/memory/entries/{project_entry['id']}/review",
        json={
            "project_id": first,
            "actor_ref": "desktop:test",
            "expected_revision": project_entry["revision"],
            "action": "ARCHIVE",
        },
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["error"]["code"] == "REVISION_CONFLICT"


def test_m22_reviewed_finding_becomes_project_memory(client: TestClient, tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    (source / "board.ioc").write_text("Mcu.Name=STM32G431CBUx\n", encoding="utf-8")
    (source / "main.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")

    created = client.post(
        "/api/v1/imports",
        json={"source_type": "LOCAL_FOLDER", "source_path": str(source)},
    )
    assert created.status_code == 201, created.text
    import_id = created.json()["data"]["id"]
    scanned = client.post(f"/api/v1/imports/{import_id}/scan")
    assert scanned.status_code == 200, scanned.text
    finding = next(
        item for item in scanned.json()["data"]["findings"] if item["category"] == "platform"
    )
    reviewed = client.patch(
        f"/api/v1/imports/{import_id}/findings/{finding['id']}",
        json={"action": "ACCEPT", "note": "Reviewed"},
    )
    assert reviewed.status_code == 200, reviewed.text
    workspace = client.post(f"/api/v1/imports/{import_id}/create-workspace")
    assert workspace.status_code == 201, workspace.text
    project_id = workspace.json()["data"]["project"]["id"]

    promoted = client.post(
        f"/api/v1/imports/{import_id}/memory-entry",
        json={
            "project_id": project_id,
            "finding_ids": [finding["id"]],
            "title": "Imported platform evidence",
        },
    )
    assert promoted.status_code == 201, promoted.text
    data = promoted.json()["data"]
    assert data["entry"]["scope"] == "PROJECT_PRIVATE"
    assert data["entry"]["knowledge_type"] == "PROJECT_EXPERIENCE"
    assert data["entry"]["verification_levels"] == ["IMPORT_VERIFIED"]
    assert len(data["entry"]["evidence_ids"]) == 1
