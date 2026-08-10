"""Project REST contract and optimistic-concurrency tests."""

from uuid import uuid4

from fastapi.testclient import TestClient


def test_project_crud_uses_envelopes_etags_and_soft_delete(client: TestClient) -> None:
    created_response = client.post(
        "/api/v1/projects",
        json={"name": "FOC Controller", "description": "Reference benchmark"},
    )

    assert created_response.status_code == 201
    assert created_response.headers["ETag"] == 'W/"1"'
    project = created_response.json()["data"]
    project_id = project["id"]

    list_response = client.get("/api/v1/projects")
    assert [item["id"] for item in list_response.json()["data"]["items"]] == [project_id]

    get_response = client.get(f"/api/v1/projects/{project_id}")
    assert get_response.status_code == 200
    assert get_response.headers["ETag"] == 'W/"1"'

    update_response = client.patch(
        f"/api/v1/projects/{project_id}",
        headers={"If-Match": 'W/"1"'},
        json={"description": "Updated"},
    )
    assert update_response.status_code == 200
    assert update_response.headers["ETag"] == 'W/"2"'
    assert update_response.json()["data"]["revision"] == 2

    delete_response = client.delete(
        f"/api/v1/projects/{project_id}",
        headers={"If-Match": 'W/"2"'},
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["data"]["status"] == "ARCHIVED"
    assert client.get(f"/api/v1/projects/{project_id}").status_code == 404
    assert client.get("/api/v1/projects").json()["data"]["items"] == []


def test_revision_conflicts_are_structured(client: TestClient) -> None:
    created = client.post("/api/v1/projects", json={"name": "Revision test"}).json()["data"]

    stale = client.patch(
        f"/api/v1/projects/{created['id']}",
        headers={"If-Match": 'W/"2"'},
        json={"name": "stale"},
    )
    missing_precondition = client.patch(
        f"/api/v1/projects/{created['id']}", json={"name": "unsafe"}
    )
    conflicting_preconditions = client.patch(
        f"/api/v1/projects/{created['id']}",
        headers={"If-Match": 'W/"1"'},
        json={"expected_revision": 2, "name": "conflict"},
    )

    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "REVISION_CONFLICT"
    assert missing_precondition.status_code == 422
    assert missing_precondition.json()["error"]["code"] == "VALIDATION_ERROR"
    assert conflicting_preconditions.status_code == 422


def test_unknown_and_invalid_projects_use_stable_errors(client: TestClient) -> None:
    missing = client.get(f"/api/v1/projects/{uuid4()}")
    invalid = client.post("/api/v1/projects", json={"name": ""})

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "PROJECT_NOT_FOUND"
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"


def test_meta_enums_and_schema_registry_are_exposed(client: TestClient) -> None:
    enum_response = client.get("/api/v1/meta/enums")
    schema_list = client.get("/api/v1/schemas")
    project_schema = client.get("/api/v1/schemas/Project")
    missing_schema = client.get("/api/v1/schemas/Unknown")

    assert "ACTUATOR_ENABLE" in enum_response.json()["data"]["enums"]["Permission"]
    assert "RECOVERING" in enum_response.json()["data"]["enums"]["JobStatus"]
    assert "EngineeringErrorCode" in enum_response.json()["data"]["enums"]
    assert "Project" in [item["name"] for item in schema_list.json()["data"]["items"]]
    assert project_schema.json()["data"]["json_schema"]["title"] == "Project"
    assert missing_schema.status_code == 400
    assert missing_schema.json()["error"]["code"] == "SCHEMA_VERSION_UNSUPPORTED"
