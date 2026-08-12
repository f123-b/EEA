"""M18R real-database and HTTP closure benchmarks."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from eea_application.dependency_graph import DependencyGraphService, _merge_with_retry
from eea_application.requirements import RequirementAnalysisService, RequirementProfileRegistry
from eea_backend.claim_repositories import SqlAlchemyEngineeringClaimRepository
from eea_backend.dependency_bootstrap import reconcile_project_dependencies
from eea_backend.dependency_providers import build_dependency_provider_registry
from eea_backend.dependency_repositories import SqlAlchemyDependencyGraphRepository
from eea_backend.models import (
    ArtifactRecord,
    EngineeringDependencyEdgeRecord,
    EngineeringDependencyNodeStateRecord,
    GeneratedProtocolOutputRecord,
    SourceRevisionRecord,
)
from eea_backend.repositories import SqlAlchemyArtifactRepository, SqlAlchemyEvidenceRepository
from eea_backend.requirement_repositories import (
    SqlAlchemyRequirementProfileRepository,
    persist_requirement_analysis_bundle,
)
from eea_core.claims import EngineeringClaim
from eea_core.dependency_graph import DependencyNodeState
from eea_core.entities import utc_now
from eea_core.enums import (
    ClaimLifecycle,
    DependencyNodeStatus,
    EngineeringErrorCode,
    RequirementPriority,
    RequirementStatus,
    RequirementType,
)
from eea_core.errors import EngineeringError
from eea_core.requirements import (
    Requirement,
    RequirementAnalysisDraft,
    RequirementClaimDraft,
    RequirementDraft,
)
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


def _project(client: TestClient, name: str) -> UUID:
    response = client.post("/api/v1/projects", json={"name": name})
    assert response.status_code == 201, response.text
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
                repository_id="m18r-fixture",
                commit_sha="a" * 40,
                tree_hash="b" * 64,
                dirty=False,
                base_commit=None,
                workspace_revision=1,
                source_manifest_hash="c" * 64,
                file_manifest={},
                created_by="m18r-test",
            )
        )
        session.commit()
    return source_id


def _artifact(
    project_id: UUID,
    *,
    artifact_id: UUID | None = None,
    logical_name: str = "fixture",
    content_hash: str | None = None,
    dependency_ids: list[UUID] | None = None,
    dependency_hashes: dict[str, str] | None = None,
) -> ArtifactRecord:
    now = utc_now()
    return ArtifactRecord(
        id=str(artifact_id or uuid4()),
        schema_version="1.0",
        revision=1,
        created_at=now,
        updated_at=now,
        entity_metadata={},
        project_id=str(project_id),
        logical_name=logical_name,
        artifact_type="M18R_FIXTURE",
        version_label="1",
        content_hash=content_hash or ("1" * 64),
        input_hash="2" * 64,
        storage_uri="inline://m18r",
        parent_artifact_id=None,
        dependency_ids=[str(value) for value in dependency_ids or []],
        dependency_hashes=dependency_hashes or {},
        created_by="m18r-test",
        source_job_id=None,
        generator_version="m18r-fixture",
        tool_versions={},
        knowledge_snapshot=None,
        status="CURRENT",
    )


def _requirement(project_id: UUID, *, acceptance: list[str]) -> Requirement:
    return Requirement(
        project_id=project_id,
        code="REQ-M18R",
        title="M18R requirement",
        requirement_type=RequirementType.FUNCTIONAL,
        priority=RequirementPriority.MUST,
        statement="The generated chain shall remain fresh.",
        rationale="M18R real mutation benchmark.",
        acceptance_criteria=acceptance,
        status=RequirementStatus.ACCEPTED,
    )


def test_real_requirement_mutation_stales_test_review_chain(client: TestClient) -> None:
    project_id = _project(client, "M18R requirement chain")
    source_id = _source(client, project_id)
    with Session(client.app.state.engine) as session:
        from eea_backend.requirement_repositories import SqlAlchemyRequirementRepository

        requirement = SqlAlchemyRequirementRepository(session).add(
            _requirement(project_id, acceptance=["A"])
        )

    generated = client.post(f"/api/v1/projects/{project_id}/tests/generate", json={})
    assert generated.status_code == 201, generated.text
    test_ir = generated.json()["data"]["test_ir"]
    run = client.post(
        f"/api/v1/projects/{project_id}/tests/run",
        json={"test_ir_id": test_ir["id"], "source_revision_id": str(source_id)},
    )
    assert run.status_code == 201, run.text
    test_run = run.json()["data"]
    review = client.post(
        f"/api/v1/projects/{project_id}/review",
        json={
            "source_revision_id": str(source_id),
            "test_ir_id": test_ir["id"],
            "test_run_id": test_run["id"],
        },
    )
    assert review.status_code == 201, review.text
    review_id = review.json()["data"]["id"]

    updated = client.patch(
        f"/api/v1/projects/{project_id}/requirements/{requirement.id}",
        json={"expected_revision": 1, "acceptance_criteria": ["B"]},
    )
    assert updated.status_code == 200, updated.text

    with Session(client.app.state.engine) as session:
        states = {
            (item.entity_type, item.entity_id): item.status
            for item in session.scalars(
                select(EngineeringDependencyNodeStateRecord).where(
                    EngineeringDependencyNodeStateRecord.project_id == str(project_id)
                )
            )
        }
    assert states[("TestIR", test_ir["id"])] == DependencyNodeStatus.STALE.value
    assert states[("TestRun", test_run["id"])] == DependencyNodeStatus.STALE.value
    assert states[("ReviewRun", review_id)] == DependencyNodeStatus.STALE.value


def test_real_runtime_errata_chain_and_unrelated_pin(client: TestClient) -> None:
    project_id = _project(client, "M18R errata chain")
    with Session(client.app.state.engine) as session:
        profiles = SqlAlchemyRequirementProfileRepository(session)
        profile = profiles.get("foc-benchmark", "1.0")
        assert profile is not None
        analysis = RequirementAnalysisService(
            RequirementProfileRegistry(profiles),
            evidence_repository=SqlAlchemyEvidenceRepository(session),
        ).complete_draft(
            project_id=project_id,
            profile_name=profile.profile_name,
            profile_version=profile.profile_version,
            draft=RequirementAnalysisDraft(
                profile_name=profile.profile_name,
                profile_version=profile.profile_version,
                requirements=[
                    RequirementDraft(
                        code="REQ-ERRATA",
                        title="Errata pin",
                        statement="The errata-sensitive pin shall remain mapped.",
                    ),
                    RequirementDraft(
                        code="REQ-UNRELATED",
                        title="Unrelated pin",
                        statement="The unrelated pin shall remain mapped.",
                    ),
                ],
                claims=[
                    RequirementClaimDraft(
                        subject_ref="device:STM32G431",
                        predicate="target.device",
                        value="STM32G431",
                    )
                ],
            ),
        )
        saved_analysis = persist_requirement_analysis_bundle(session, analysis)
    pin_payload = {
        "analysis_id": str(saved_analysis.id),
        "device_ref": "STM32G431",
        "package": "UFQFPN48",
        "requirements": [
            {
                "signal_name": "errata-pwm",
                "required_peripheral": "TIM1",
                "required_function": "CH1",
                "requirement_ids": [str(saved_analysis.requirement_ids[0])],
                "claim_ids": [str(saved_analysis.claim_ids[0])],
            },
            {
                "signal_name": "unrelated-pwm",
                "required_peripheral": "FDCAN1",
                "required_function": "RX",
                "requirement_ids": [str(saved_analysis.requirement_ids[1])],
            },
        ],
    }
    plan_response = client.post(
        f"/api/v1/projects/{project_id}/pin-planner/generate", json=pin_payload
    )
    assert plan_response.status_code == 201, plan_response.text
    plan = plan_response.json()["data"]
    assignment_ids = [item["id"] for item in plan["assignments"]]
    assert len(assignment_ids) == 2
    errata_assignment_id = next(
        item["id"]
        for item in plan["assignments"]
        if str(saved_analysis.claim_ids[0]) in item["claim_ids"]
    )
    unrelated_assignment_id = next(
        item["id"] for item in plan["assignments"] if item["id"] != errata_assignment_id
    )
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/pin-planner/assignments/{errata_assignment_id}/lock",
            headers={"If-Match": 'W/"1"'},
            json={"actor": "m18r", "reason": "errata benchmark"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/pin-planner/assignments/{unrelated_assignment_id}/lock",
            headers={"If-Match": 'W/"1"'},
            json={"actor": "m18r", "reason": "unrelated benchmark"},
        ).status_code
        == 200
    )
    architecture = client.post(
        f"/api/v1/projects/{project_id}/architecture/generate",
        json={"pin_plan_id": plan["id"]},
    )
    assert architecture.status_code == 201, architecture.text
    hardware = architecture.json()["data"]["hardware"]
    circuit = client.post(
        f"/api/v1/projects/{project_id}/circuit/generate",
        json={
            "hardware_ir_id": hardware["id"],
            "components": [
                {"reference": "MCU", "kind": "MCU"},
                {"reference": "R1", "kind": "RESISTOR"},
            ],
            "nets": [
                {
                    "name": "pwm",
                    "endpoints": [
                        {
                            "component_ref": "MCU",
                            "pin_ref": "PA8",
                            "pin_assignment_id": errata_assignment_id,
                        },
                        {"component_ref": "R1", "pin_ref": "1"},
                    ],
                }
            ],
        },
    )
    assert circuit.status_code == 201, circuit.text
    circuit_data = circuit.json()["data"]["circuit"]
    schematic = client.post(
        f"/api/v1/projects/{project_id}/schematic/generate",
        json={"circuit_id": circuit_data["id"]},
    )
    assert schematic.status_code == 201, schematic.text
    schematic_data = schematic.json()["data"]["schematic"]
    mcu = client.post(
        f"/api/v1/projects/{project_id}/mcu-config/generate",
        json={
            "hardware_ir_id": hardware["id"],
            "circuit_id": circuit_data["id"],
            "schematic_id": schematic_data["id"],
            "device_instance_id": hardware["device_instances"][0]["id"],
            "clock": {"source": "HSE"},
        },
    )
    assert mcu.status_code == 201, mcu.text
    mcu_id = mcu.json()["data"]["config"]["id"]
    firmware = client.post(
        f"/api/v1/projects/{project_id}/firmware/generate",
        json={"mcu_config_id": mcu_id},
    )
    assert firmware.status_code == 201, firmware.text
    firmware_id = firmware.json()["data"]["firmware"]["id"]

    claim_id = saved_analysis.claim_ids[0]
    mutation = client.post(
        f"/api/v1/claims/{claim_id}/lifecycle",
        json={
            "project_id": str(project_id),
            "expected_revision": 1,
            "lifecycle": ClaimLifecycle.SUPERSEDED.value,
        },
    )
    assert mutation.status_code == 200, mutation.text
    impact = mutation.json()["data"]["impact_plan"]["impacts"]
    by_node = {(item["node"]["entity_type"], item["node"]["entity_id"]): item for item in impact}
    assert by_node[("PinAssignment", errata_assignment_id)]["depth"] == 1
    assert by_node[("MCUConfigIR", mcu_id)]["depth"] == 2
    assert by_node[("FirmwareIR", firmware_id)]["depth"] == 3
    assert all(item["node"]["entity_id"] != unrelated_assignment_id for item in impact)

    dependencies = client.get(
        f"/api/v1/entities/PinAssignment/{errata_assignment_id}/dependencies",
        params={"project_id": str(project_id)},
    )
    dependents = client.get(
        f"/api/v1/entities/MCUConfigIR/{mcu_id}/dependents",
        params={"project_id": str(project_id)},
    )
    assert dependencies.status_code == 200 and dependencies.json()["data"]["items"]
    assert dependents.status_code == 200 and dependents.json()["data"]["items"]


def test_protocol_outputs_are_persistent_and_stale_on_update(client: TestClient) -> None:
    project_id = _project(client, "M18R protocol outputs")
    payload = {
        "version_label": "1.0.0",
        "transports": [{"transport_id": "can0", "name": "CAN 0"}],
        "messages": [
            {
                "name": "Status",
                "transport_ref": "can0",
                "can_id": 513,
                "payload_length_bytes": 8,
                "fields": [{"name": "counter", "bit_offset": 0, "bit_length": 8}],
            }
        ],
    }
    created = client.post(f"/api/v1/projects/{project_id}/protocol", json=payload)
    assert created.status_code == 201, created.text
    protocol = created.json()["data"]
    generated = client.post(
        f"/api/v1/projects/{project_id}/protocol/generate", json={"protocol_id": protocol["id"]}
    )
    assert generated.status_code == 200, generated.text
    with Session(client.app.state.engine) as session:
        outputs = list(
            session.scalars(
                select(GeneratedProtocolOutputRecord).where(
                    GeneratedProtocolOutputRecord.project_id == str(project_id)
                )
            )
        )
        edges = list(
            session.scalars(
                select(EngineeringDependencyEdgeRecord).where(
                    EngineeringDependencyEdgeRecord.project_id == str(project_id),
                    EngineeringDependencyEdgeRecord.downstream_type == "GeneratedProtocolOutput",
                )
            )
        )
    assert {item.target for item in outputs} == {"C", "PYTHON", "DBC", "MARKDOWN"}
    assert len(edges) == 4
    update = client.patch(
        f"/api/v1/projects/{project_id}/protocol",
        json={**payload, "version_label": "1.0.1", "expected_revision": 1},
    )
    assert update.status_code == 200, update.text
    with Session(client.app.state.engine) as session:
        states = list(
            session.scalars(
                select(EngineeringDependencyNodeStateRecord).where(
                    EngineeringDependencyNodeStateRecord.project_id == str(project_id),
                    EngineeringDependencyNodeStateRecord.entity_type == "GeneratedProtocolOutput",
                )
            )
        )
    assert states and all(item.status == DependencyNodeStatus.STALE.value for item in states)


def test_artifact_storage_revision_is_nonsemantic_and_historical_hash_is_stale(
    client: TestClient,
) -> None:
    project_id = _project(client, "M18R artifact freshness")
    first_id = uuid4()
    with Session(client.app.state.engine) as session:
        first = _artifact(project_id, artifact_id=first_id, content_hash="a" * 64)
        second = _artifact(
            project_id,
            logical_name="dependent",
            dependency_ids=[first_id],
            dependency_hashes={str(first_id): "a" * 64},
        )
        session.add_all([first, second])
        session.commit()
        result = reconcile_project_dependencies(session, project_id)
        assert result["created_edges"] == 1
        first_record = session.get(ArtifactRecord, str(first_id))
        assert first_record is not None
        before = build_dependency_provider_registry(session).resolve(
            project_id, "Artifact", str(first_id)
        )
        first_record.storage_uri = "inline://m18r/changed-location"
        first_record.revision = 2
        first_record.updated_at = utc_now()
        after = build_dependency_provider_registry(session).resolve(
            project_id, "Artifact", str(first_id)
        )
        plan = DependencyGraphService(
            SqlAlchemyDependencyGraphRepository(session),
            build_dependency_provider_registry(session),
        ).propagate(project_id, before, after, commit=False)
        assert plan.impacts == []
        first_record.content_hash = "b" * 64
        first_record.revision = 3
        first_record.updated_at = utc_now()
        session.commit()
        result = reconcile_project_dependencies(session, project_id)
        assert result["existing_edges"] >= 1
        dependent = SqlAlchemyArtifactRepository(session).get(second.id, project_id=project_id)
        assert dependent is not None
    fetched = client.get(f"/api/v1/artifacts/{second.id}", params={"project_id": str(project_id)})
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["data"]["status"] == "STALE"
    stale = client.get(f"/api/v1/projects/{project_id}/artifacts/stale")
    assert stale.status_code == 200
    assert stale.json()["data"]["items"][0]["status"] == "STALE"


def test_two_session_node_state_retry_unions_evidence_and_precedence(client: TestClient) -> None:
    project_id = _project(client, "M18R concurrency")
    artifact_id = uuid4()
    with Session(client.app.state.engine) as setup:
        setup.add(_artifact(project_id, artifact_id=artifact_id))
        setup.commit()
        repository = SqlAlchemyDependencyGraphRepository(setup)
        initial = repository.replace_revalidated_state(
            DependencyNodeState(
                project_id=project_id,
                entity_type="Artifact",
                entity_id=str(artifact_id),
                observed_revision=1,
                observed_semantic_hash="1" * 64,
                status=DependencyNodeStatus.CURRENT,
            )
        )
        initial_revision = initial.revision
    first_session = Session(client.app.state.engine)
    second_session = Session(client.app.state.engine)
    try:
        first_repository = SqlAlchemyDependencyGraphRepository(first_session)
        second_repository = SqlAlchemyDependencyGraphRepository(second_session)
        observed = second_repository.get_node_state(project_id, "Artifact", str(artifact_id))
        assert observed is not None and observed.revision == initial_revision
        first_repository.merge_invalidation_state(
            DependencyNodeState(
                project_id=project_id,
                entity_type="Artifact",
                entity_id=str(artifact_id),
                observed_revision=2,
                observed_semantic_hash="2" * 64,
                status=DependencyNodeStatus.STALE,
                invalidated_by=["A"],
                reason_codes=["SEMANTIC_CHANGED"],
            ),
            expected_revision=initial_revision,
        )
        final = _merge_with_retry(
            second_repository,
            DependencyNodeState(
                project_id=project_id,
                entity_type="Artifact",
                entity_id=str(artifact_id),
                observed_revision=3,
                observed_semantic_hash="3" * 64,
                status=DependencyNodeStatus.INVALID,
                invalidated_by=["B"],
                reason_codes=["SOURCE_INVALID"],
            ),
            expected_revision=initial_revision,
            commit=True,
        )
        assert final.status is DependencyNodeStatus.INVALID
        assert set(final.invalidated_by) == {"A", "B"}
        assert set(final.reason_codes) == {"SEMANTIC_CHANGED", "SOURCE_INVALID"}
    finally:
        first_session.close()
        second_session.close()


def test_bootstrap_is_complete_idempotent_and_does_not_swallow_cycle(client: TestClient) -> None:
    project_id = _project(client, "M18R bootstrap")
    with Session(client.app.state.engine) as session:
        first_id = uuid4()
        second_id = uuid4()
        session.add_all(
            [
                _artifact(
                    project_id,
                    artifact_id=first_id,
                    logical_name="cycle-a",
                    dependency_ids=[second_id],
                    dependency_hashes={str(second_id): "1" * 64},
                ),
                _artifact(
                    project_id,
                    artifact_id=second_id,
                    logical_name="cycle-b",
                    dependency_ids=[first_id],
                    dependency_hashes={str(first_id): "1" * 64},
                ),
            ]
        )
        session.commit()
        with pytest.raises(EngineeringError) as error:
            reconcile_project_dependencies(session, project_id)
        assert error.value.code is EngineeringErrorCode.DEPENDENCY_CYCLE

    isolated = _project(client, "M18R bootstrap idempotence")
    with Session(client.app.state.engine) as session:
        source = _artifact(project_id=isolated, logical_name="source")
        dependent = _artifact(
            project_id=isolated,
            logical_name="dependent",
            dependency_ids=[UUID(source.id)],
            dependency_hashes={source.id: source.content_hash},
        )
        session.add_all([source, dependent])
        session.commit()
        first = reconcile_project_dependencies(session, isolated)
        second = reconcile_project_dependencies(session, isolated)
        assert first["created_edges"] == 1
        assert second["created_edges"] == 0
        assert second["existing_edges"] >= 1


def test_global_claim_and_unknown_dependency_type_fail_closed(client: TestClient) -> None:
    project_id = _project(client, "M18R scope")
    claim = EngineeringClaim(
        subject_ref="global:fixture",
        predicate="target.device",
        value="STM32G431",
        confidence=1,
        source_priority=1,
        lifecycle=ClaimLifecycle.ACTIVE,
    )
    with Session(client.app.state.engine) as session:
        saved = SqlAlchemyEngineeringClaimRepository(session).add(claim)
    global_mutation = client.post(
        f"/api/v1/claims/{saved.id}/lifecycle",
        json={
            "project_id": str(project_id),
            "expected_revision": 1,
            "lifecycle": ClaimLifecycle.SUPERSEDED.value,
        },
    )
    assert global_mutation.status_code == 400
    assert (
        global_mutation.json()["error"]["code"] == EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED.value
    )
    unknown = client.get(
        "/api/v1/entities/NotRegistered/node/dependencies",
        params={"project_id": str(project_id)},
    )
    assert unknown.status_code == 400
    assert unknown.json()["error"]["code"] == EngineeringErrorCode.CAPABILITY_UNAVAILABLE.value
