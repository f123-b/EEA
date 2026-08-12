"""M18 explicit-reference graph reconciliation."""

from __future__ import annotations

from uuid import UUID

from eea_application.dependency_graph import DependencyGraphService
from eea_core.enums import DependencyKind, InvalidationPolicy
from sqlalchemy import select
from sqlalchemy.orm import Session

from eea_backend.dependency_providers import build_dependency_provider_registry
from eea_backend.dependency_repositories import SqlAlchemyDependencyGraphRepository
from eea_backend.models import (
    ArtifactRecord,
    FirmwareRecord,
    MCUConfigRecord,
    PinAssignmentRecord,
    ReviewRunRecord,
    TestIRRecord,
    TestRunRecord,
)


def reconcile_project_dependencies(session: Session, project_id: UUID) -> int:
    """Persist deterministic edges from explicit durable references.

    A missing or unsupported reference is left absent and therefore remains
    visible as UNKNOWN to callers; this function never guesses an edge.
    """

    service = DependencyGraphService(
        SqlAlchemyDependencyGraphRepository(session),
        build_dependency_provider_registry(session),
    )
    count = 0

    artifacts = session.scalars(
        select(ArtifactRecord)
        .where(ArtifactRecord.project_id == str(project_id))
        .order_by(ArtifactRecord.created_at, ArtifactRecord.id)
    )
    for artifact in artifacts:
        for dependency_id in sorted(set(artifact.dependency_ids or [])):
            if dependency_id not in (artifact.dependency_hashes or {}):
                continue
            try:
                service.bind(
                    project_id,
                    upstream_type="Artifact",
                    upstream_id=dependency_id,
                    downstream_type="Artifact",
                    downstream_id=artifact.id,
                    dependency_kind=DependencyKind.INPUT,
                    required=True,
                    invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
                    reason="Artifact dependency_ids/dependency_hashes",
                    commit=False,
                )
            except Exception:
                # A missing declared node is intentionally not converted to a
                # guessed edge or a cross-project edge.
                continue
            count += 1

    pins = session.scalars(
        select(PinAssignmentRecord)
        .where(PinAssignmentRecord.project_id == str(project_id))
        .order_by(PinAssignmentRecord.created_at, PinAssignmentRecord.id)
    )
    for pin in pins:
        for claim_id in sorted(set(pin.claim_ids or [])):
            try:
                service.bind(
                    project_id,
                    upstream_type="Claim",
                    upstream_id=claim_id,
                    downstream_type="PinAssignment",
                    downstream_id=pin.id,
                    dependency_kind=DependencyKind.SELECTION,
                    required=True,
                    invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
                    reason="PinAssignment claim_ids",
                    commit=False,
                )
            except Exception:
                continue
            count += 1

    configs = session.scalars(
        select(MCUConfigRecord)
        .where(MCUConfigRecord.project_id == str(project_id))
        .order_by(MCUConfigRecord.created_at, MCUConfigRecord.id)
    )
    for config in configs:
        for pin_id in sorted(set((config.pin_assignment_revisions or {}).keys())):
            try:
                service.bind(
                    project_id,
                    upstream_type="PinAssignment",
                    upstream_id=pin_id,
                    downstream_type="MCUConfigIR",
                    downstream_id=config.id,
                    dependency_kind=DependencyKind.CONFIGURATION,
                    required=True,
                    invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
                    reason="MCUConfigIR pin_assignment_revisions",
                    commit=False,
                )
            except Exception:
                continue
            count += 1

    firmwares = session.scalars(
        select(FirmwareRecord)
        .where(FirmwareRecord.project_id == str(project_id))
        .order_by(FirmwareRecord.created_at, FirmwareRecord.id)
    )
    for firmware in firmwares:
        for upstream_type, upstream_id, kind, reason in (
            (
                "MCUConfigIR",
                firmware.mcu_config_id,
                DependencyKind.GENERATION,
                "FirmwareIR mcu_config_id",
            ),
            (
                "SourceRevision",
                firmware.source_revision_id,
                DependencyKind.INPUT,
                "FirmwareIR source_revision_id",
            ),
        ):
            try:
                service.bind(
                    project_id,
                    upstream_type=upstream_type,
                    upstream_id=upstream_id,
                    downstream_type="FirmwareIR",
                    downstream_id=firmware.id,
                    dependency_kind=kind,
                    required=True,
                    invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
                    reason=reason,
                    commit=False,
                )
            except Exception:
                continue
            count += 1

    for test_ir in session.scalars(
        select(TestIRRecord)
        .where(TestIRRecord.project_id == str(project_id))
        .order_by(TestIRRecord.created_at, TestIRRecord.id)
    ):
        for requirement_id in sorted(set(test_ir.requirement_ids or [])):
            try:
                service.bind(
                    project_id,
                    upstream_type="Requirement",
                    upstream_id=requirement_id,
                    downstream_type="TestIR",
                    downstream_id=test_ir.id,
                    dependency_kind=DependencyKind.VERIFICATION,
                    required=True,
                    invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
                    reason="TestIR requirement_ids",
                    commit=False,
                )
            except Exception:
                continue
            count += 1

    for test_run in session.scalars(
        select(TestRunRecord)
        .where(TestRunRecord.project_id == str(project_id))
        .order_by(TestRunRecord.created_at, TestRunRecord.id)
    ):
        try:
            service.bind(
                project_id,
                upstream_type="TestIR",
                upstream_id=test_run.test_ir_id,
                downstream_type="TestRun",
                downstream_id=test_run.id,
                dependency_kind=DependencyKind.VERIFICATION,
                required=True,
                invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
                reason="TestRun test_ir_id",
                commit=False,
            )
            count += 1
        except Exception:
            pass

    for review in session.scalars(
        select(ReviewRunRecord)
        .where(ReviewRunRecord.project_id == str(project_id))
        .order_by(ReviewRunRecord.created_at, ReviewRunRecord.id)
    ):
        for upstream_type, candidate_id in (
            ("TestRun", review.test_run_id),
            ("TestIR", review.test_ir_id),
        ):
            if candidate_id is None:
                continue
            upstream_id = str(candidate_id)
            try:
                service.bind(
                    project_id,
                    upstream_type=upstream_type,
                    upstream_id=upstream_id,
                    downstream_type="ReviewRun",
                    downstream_id=review.id,
                    dependency_kind=DependencyKind.VERIFICATION,
                    required=True,
                    invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
                    reason="ReviewRun explicit input reference",
                    commit=False,
                )
                count += 1
            except Exception:
                continue

    session.commit()
    return count


__all__ = ["reconcile_project_dependencies"]
