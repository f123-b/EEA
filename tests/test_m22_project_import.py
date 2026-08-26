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

    (source / "main.c").write_text(
        '#include "board.h"\nint main(void) { HAL_GPIO_Init(GPIOB, 1); return 0; }\n',
        encoding="utf-8",
    )
    rescanned = client.post(f"/api/v1/imports/{import_id}/rescan")
    assert rescanned.status_code == 200
    rescan_data = rescanned.json()["data"]
    assert rescan_data["source_revision"]["id"] != first_revision
    assert rescan_data["rescan_diff"]["summary"]["MODIFIED"] >= 1
    assert {
        "added",
        "modified",
        "removed",
        "unchanged",
    }.issubset(rescan_data["rescan_diff"])
    assert {
        "changed",
        "affected",
        "stale",
        "blocked",
    }.issubset(rescan_data["rescan_diff"]["dependency_impact"])


def test_m22r_candidates_are_evidenced_reviewed_and_applied_with_cas(
    client: TestClient, tmp_path: Path
) -> None:
    source = tmp_path / "m22r-candidate"
    source.mkdir()
    (source / "board.ioc").write_text(
        "Mcu.Name=STM32G431CBUx\nMcu.Package=LQFP48\n", encoding="utf-8"
    )
    created = client.post(
        "/api/v1/imports",
        json={"source_type": "LOCAL_FOLDER", "source_path": str(source)},
    )
    assert created.status_code == 201
    import_id = created.json()["data"]["id"]

    scanned = client.post(f"/api/v1/imports/{import_id}/scan")
    assert scanned.status_code == 200
    candidates = scanned.json()["data"]["normalized_candidates"]
    assert candidates
    candidate = next(item for item in candidates if item["semantic_key"].endswith("ioc.mcu"))
    assert candidate["status"] == "DETECTED"
    assert candidate["evidence_ids"]

    reviewed = client.patch(
        f"/api/v1/imports/{import_id}/candidates/{candidate['id']}",
        json={"expected_revision": candidate["revision"], "action": "ACCEPT"},
    )
    assert reviewed.status_code == 200
    accepted = reviewed.json()["data"]
    assert accepted["status"] == "ACCEPTED_CANDIDATE"

    stale = client.patch(
        f"/api/v1/imports/{import_id}/candidates/{candidate['id']}",
        json={"expected_revision": candidate["revision"], "action": "REJECT"},
    )
    assert stale.status_code == 409

    workspace = client.post(f"/api/v1/imports/{import_id}/create-workspace")
    assert workspace.status_code == 201
    current = next(
        item
        for item in client.get(f"/api/v1/imports/{import_id}/candidates").json()["data"]
        if item["id"] == candidate["id"]
    )
    applied = client.post(
        f"/api/v1/imports/{import_id}/candidates/apply",
        json={
            "candidate_ids": [candidate["id"]],
            "expected_revisions": {candidate["id"]: current["revision"]},
        },
    )
    assert applied.status_code == 200
    assert applied.json()["data"]["results"][0]["status"] == "APPLIED"


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


def test_import_scan_never_executes_imported_scripts(client: TestClient, tmp_path: Path) -> None:
    source = tmp_path / "untrusted-build"
    source.mkdir()
    marker = tmp_path / "should-not-exist"
    (source / "CMakeLists.txt").write_text(
        f'execute_process(COMMAND python -c "open(\\"{marker}\\", \\"w\\").write(\\"bad\\")")',
        encoding="utf-8",
    )
    (source / "build.py").write_text(
        f'from pathlib import Path\nPath(r"{marker}").write_text("bad")',
        encoding="utf-8",
    )
    created = client.post(
        "/api/v1/imports",
        json={"source_type": "LOCAL_FOLDER", "source_path": str(source)},
    )
    import_id = created.json()["data"]["id"]
    scanned = client.post(f"/api/v1/imports/{import_id}/scan")
    assert scanned.status_code == 200
    assert scanned.json()["data"]["build_executed"] is False
    assert not marker.exists()


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
