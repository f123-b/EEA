"""M22 existing-project import, reverse-engineering, and isolation gates."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient


def test_local_import_review_workspace_and_rescan(client: TestClient, tmp_path: Path) -> None:
    source = tmp_path / "legacy-controller"
    source.mkdir()
    (source / "CMakeLists.txt").write_text("project(legacy)", encoding="utf-8")
    (source / "main.c").write_text(
        '#include "board.h"\nint main(void) { HAL_GPIO_Init(GPIOA, 0); return 0; }\n',
        encoding="utf-8",
    )
    (source / "board.h").write_text("#define BOARD_PA1 PA1\n", encoding="utf-8")
    (source / "board.ioc").write_text(
        "Mcu.Name=STM32G431CBUx\nPA0.Signal=GPIO_Output\n", encoding="utf-8"
    )
    (source / "controller.kicad_sch").write_text("(kicad_sch)", encoding="utf-8")
    (source / "messages.dbc").write_text("BO_ 1 FRAME: 8 ECU\n", encoding="utf-8")

    created = client.post(
        "/api/v1/imports",
        json={
            "source_type": "LOCAL_FOLDER",
            "source_path": str(source),
            "project_name": "Legacy controller",
        },
    )
    assert created.status_code == 201
    import_id = created.json()["data"]["id"]

    scanned = client.post(f"/api/v1/imports/{import_id}/scan")
    assert scanned.status_code == 200
    scan = scanned.json()["data"]
    assert scan["status"] == "SCANNED"
    assert scan["summary"]["platform"] == ["STM32G431CBUX"]
    assert "CMake" in scan["summary"]["build"]
    assert scan["build_executed"] is False
    assert any(issue["code"] == "CONFIG_SOURCE_MISMATCH" for issue in scan["issues"])
    assert scan["candidates"]["hardware"][0]["status"] == "CANDIDATE"
    assert scan["candidates"]["protocol"][0]["status"] == "CANDIDATE"
    finding = next(item for item in scan["findings"] if item["category"] == "platform")
    assert finding["confidence"] in {"HIGH", "MEDIUM"}
    assert finding["evidence"]

    reviewed = client.patch(
        f"/api/v1/imports/{import_id}/findings/{finding['id']}",
        json={"action": "ACCEPT", "note": "Reviewed against the board handoff"},
    )
    assert reviewed.status_code == 200
    reviewed_finding = next(
        item for item in reviewed.json()["data"]["findings"] if item["id"] == finding["id"]
    )
    assert reviewed_finding["review_status"] == "ACCEPTED_CANDIDATE"

    workspace = client.post(f"/api/v1/imports/{import_id}/create-workspace")
    assert workspace.status_code == 201
    project = workspace.json()["data"]["project"]
    first_revision = workspace.json()["data"]["source_revision"]["id"]
    source_revision = client.get(f"/api/v1/projects/{project['id']}/source/revision")
    assert source_revision.status_code == 200
    assert source_revision.json()["data"]["id"] == first_revision

    rescanned = client.post(f"/api/v1/imports/{import_id}/rescan")
    assert rescanned.status_code == 200
    assert rescanned.json()["data"]["source_revision"]["id"] != first_revision


def test_archive_import_rejects_traversal(client: TestClient, tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with ZipFile(archive, "w") as stream:
        stream.writestr("../escape.c", "int main(void) { return 0; }")

    created = client.post(
        "/api/v1/imports",
        json={"source_type": "ARCHIVE", "source_path": str(archive)},
    )
    assert created.status_code == 201
    import_id = created.json()["data"]["id"]
    scanned = client.post(f"/api/v1/imports/{import_id}/scan")
    assert scanned.status_code == 400
    assert scanned.json()["error"]["code"] == "ARCHIVE_UNSAFE"


def test_import_workspaces_are_project_isolated(client: TestClient, tmp_path: Path) -> None:
    first_source = tmp_path / "first"
    second_source = tmp_path / "second"
    first_source.mkdir()
    second_source.mkdir()
    (first_source / "first.c").write_text('const char *name = "first";', encoding="utf-8")
    (second_source / "second.c").write_text('const char *name = "second";', encoding="utf-8")

    workspaces: list[dict[str, object]] = []
    for source in (first_source, second_source):
        created = client.post(
            "/api/v1/imports",
            json={"source_type": "LOCAL_FOLDER", "source_path": str(source)},
        )
        assert created.status_code == 201
        import_id = created.json()["data"]["id"]
        assert client.post(f"/api/v1/imports/{import_id}/scan").status_code == 200
        workspace = client.post(
            f"/api/v1/imports/{import_id}/create-workspace",
            json={"project_name": source.name},
        )
        assert workspace.status_code == 201
        workspaces.append(workspace.json()["data"])

    first = workspaces[0]
    second = workspaces[1]
    assert first["project"]["id"] != second["project"]["id"]
    assert first["import"]["workspace_path"] != second["import"]["workspace_path"]
