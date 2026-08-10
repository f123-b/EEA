"""M1 Core entity, enum, and schema-registry tests."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from eea_core.entities import Artifact, EntityBase, Job, Project
from eea_core.enums import EngineeringErrorCode, JobStatus, Permission
from eea_core.schema_registry import SchemaRegistration, SchemaRegistry, create_core_schema_registry
from pydantic import ValidationError


def test_entity_base_rejects_invalid_revision_and_timestamp_order() -> None:
    with pytest.raises(ValidationError):
        EntityBase(revision=0)

    now = datetime.now(UTC)
    with pytest.raises(ValidationError, match="updated_at cannot precede"):
        EntityBase(created_at=now, updated_at=now - timedelta(seconds=1))


def test_artifact_requires_sha256_hashes_and_isolated_collections() -> None:
    first = Artifact(
        project_id=uuid4(),
        logical_name="firmware",
        artifact_type="source_snapshot",
        version_label="1",
        content_hash="a" * 64,
        input_hash="b" * 64,
        storage_uri="objects/aa/hash",
        created_by="test-user",
    )
    second = Artifact(
        project_id=uuid4(),
        logical_name="firmware",
        artifact_type="source_snapshot",
        version_label="1",
        content_hash="c" * 64,
        input_hash="d" * 64,
        storage_uri="objects/cc/hash",
        created_by="test-user",
    )

    first.dependency_ids.append(uuid4())
    assert second.dependency_ids == []
    with pytest.raises(ValidationError):
        Artifact(
            project_id=uuid4(),
            logical_name="invalid",
            artifact_type="report",
            version_label="1",
            content_hash="not-a-hash",
            input_hash="b" * 64,
            storage_uri="objects/report",
            created_by="test-user",
        )


def test_fix_08_job_and_permission_enums_are_canonical() -> None:
    assert [status.value for status in JobStatus] == [
        "QUEUED",
        "RUNNING",
        "BLOCKED_PERMISSION",
        "BLOCKED_RESOURCE",
        "RECOVERING",
        "SUCCESS",
        "FAILED",
        "FAILED_NEEDS_RECONCILE",
        "CANCELLED",
    ]
    assert Permission.ACTUATOR_ENABLE in Permission
    assert Permission.FLASH != Permission.ACTUATOR_ENABLE
    assert EngineeringErrorCode.COMMISSIONING_BLOCKED.value == "COMMISSIONING_BLOCKED"
    assert Job(job_type="document_parse", progress=0.5).status is JobStatus.QUEUED
    with pytest.raises(ValidationError):
        Job(job_type="invalid", progress=1.1)


def test_schema_registry_is_sorted_versioned_and_rejects_duplicates() -> None:
    registry = create_core_schema_registry()

    assert [item.name for item in registry.list()] == sorted(item.name for item in registry.list())
    assert registry.get("Project") is not None
    assert registry.json_schema("Project")["title"] == "Project"  # type: ignore[index]
    assert registry.get("Unknown") is None
    assert registry.json_schema("Unknown") is None

    duplicate_registry = SchemaRegistry()
    registration = SchemaRegistration("Project", "1.0", Project)
    duplicate_registry.register(registration)
    with pytest.raises(ValueError, match="already registered"):
        duplicate_registry.register(registration)
