"""M18 explicit-reference graph reconciliation."""

from __future__ import annotations

from uuid import UUID

from eea_application.dependency_graph import DependencyGraphService
from eea_core.enums import DependencyKind, EngineeringErrorCode, InvalidationPolicy
from eea_core.errors import EngineeringError
from sqlalchemy import select
from sqlalchemy.orm import Session

from eea_backend.dependency_providers import build_dependency_provider_registry
from eea_backend.dependency_repositories import SqlAlchemyDependencyGraphRepository
from eea_backend.models import (
    ArtifactRecord,
    BuildRunRecord,
    CircuitRecord,
    FirmwareRecord,
    FirmwareStaticAnalysisRecord,
    GeneratedProtocolOutputRecord,
    HardwareIRRecord,
    MCUConfigRecord,
    PinAssignmentRecord,
    ReviewRunRecord,
    SchematicArtifactRecord,
    SystemArchitectureRecord,
    TestIRRecord,
    TestRunRecord,
)


def reconcile_project_dependencies(session: Session, project_id: UUID) -> dict[str, object]:
    """Persist deterministic edges from explicit durable references.

    A missing or unsupported reference is left absent and therefore remains
    visible as UNKNOWN to callers; this function never guesses an edge.
    """

    service = DependencyGraphService(
        SqlAlchemyDependencyGraphRepository(session),
        build_dependency_provider_registry(session),
    )
    created_edges = 0
    existing_edges = 0
    gaps: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []

    def bind_explicit(
        *,
        upstream_type: str,
        upstream_id: str | None,
        downstream_type: str,
        downstream_id: str,
        dependency_kind: DependencyKind,
        reason: str,
        bound_hash: str | None = None,
    ) -> None:
        nonlocal created_edges, existing_edges
        if upstream_id is None:
            gaps.append({"downstream": f"{downstream_type}:{downstream_id}", "reason": reason})
            return
        before = service.repository.list_edges(project_id)
        try:
            service.bind(
                project_id,
                upstream_type=upstream_type,
                upstream_id=str(upstream_id),
                downstream_type=downstream_type,
                downstream_id=downstream_id,
                dependency_kind=dependency_kind,
                required=True,
                invalidation_policy=InvalidationPolicy.SEMANTIC_CHANGE_STALE_SOURCE_INVALID_INVALID,
                reason=reason,
                bound_upstream_semantic_hash=bound_hash,
                commit=False,
            )
        except EngineeringError as error:
            if error.code is EngineeringErrorCode.VALIDATION_ERROR:
                gaps.append(
                    {
                        "upstream": f"{upstream_type}:{upstream_id}",
                        "downstream": f"{downstream_type}:{downstream_id}",
                        "reason": reason,
                        "code": error.code.value,
                    }
                )
                return
            errors.append({"reason": reason, "code": error.code.value, "message": error.message})
            raise
        service.revalidate(project_id, downstream_type, downstream_id, commit=False)
        after = service.repository.list_edges(project_id)
        if len(after) > len(before):
            created_edges += 1
        else:
            existing_edges += 1

    artifacts = session.scalars(
        select(ArtifactRecord)
        .where(ArtifactRecord.project_id == str(project_id))
        .order_by(ArtifactRecord.created_at, ArtifactRecord.id)
    )
    for artifact in artifacts:
        for dependency_id in sorted(set(artifact.dependency_ids or [])):
            dependency_hashes = artifact.dependency_hashes or {}
            bound_hash = dependency_hashes.get(dependency_id)
            if bound_hash is None:
                bound_hash = dependency_hashes.get(str(dependency_id))
            if bound_hash is None:
                continue
            bind_explicit(
                upstream_type="Artifact",
                upstream_id=dependency_id,
                downstream_type="Artifact",
                downstream_id=artifact.id,
                dependency_kind=DependencyKind.INPUT,
                reason="Artifact dependency_ids/dependency_hashes",
                bound_hash=bound_hash,
            )

    pins = session.scalars(
        select(PinAssignmentRecord)
        .where(PinAssignmentRecord.project_id == str(project_id))
        .order_by(PinAssignmentRecord.created_at, PinAssignmentRecord.id)
    )
    for pin in pins:
        for claim_id in sorted(set(pin.claim_ids or [])):
            bind_explicit(
                upstream_type="Claim",
                upstream_id=claim_id,
                downstream_type="PinAssignment",
                downstream_id=pin.id,
                dependency_kind=DependencyKind.SELECTION,
                reason="PinAssignment claim_ids",
            )

    for architecture in session.scalars(
        select(SystemArchitectureRecord)
        .where(SystemArchitectureRecord.project_id == str(project_id))
        .order_by(SystemArchitectureRecord.created_at, SystemArchitectureRecord.id)
    ):
        for assignment_id in sorted((architecture.pin_assignment_revisions or {}).keys()):
            bind_explicit(
                upstream_type="PinAssignment",
                upstream_id=assignment_id,
                downstream_type="SystemArchitectureIR",
                downstream_id=architecture.id,
                dependency_kind=DependencyKind.GENERATION,
                reason="SystemArchitectureIR pin_assignment_revisions",
            )

    for hardware in session.scalars(
        select(HardwareIRRecord)
        .where(HardwareIRRecord.project_id == str(project_id))
        .order_by(HardwareIRRecord.created_at, HardwareIRRecord.id)
    ):
        bind_explicit(
            upstream_type="SystemArchitectureIR",
            upstream_id=hardware.architecture_id,
            downstream_type="HardwareIR",
            downstream_id=hardware.id,
            dependency_kind=DependencyKind.GENERATION,
            reason="HardwareIR architecture_id",
        )

    for circuit in session.scalars(
        select(CircuitRecord)
        .where(CircuitRecord.project_id == str(project_id))
        .order_by(CircuitRecord.created_at, CircuitRecord.id)
    ):
        bind_explicit(
            upstream_type="HardwareIR",
            upstream_id=circuit.hardware_ir_id,
            downstream_type="CircuitIR",
            downstream_id=circuit.id,
            dependency_kind=DependencyKind.GENERATION,
            reason="CircuitIR hardware_ir_id",
        )

    for schematic in session.scalars(
        select(SchematicArtifactRecord)
        .where(SchematicArtifactRecord.project_id == str(project_id))
        .order_by(SchematicArtifactRecord.created_at, SchematicArtifactRecord.id)
    ):
        for upstream_type, upstream_id, reason in (
            ("CircuitIR", schematic.circuit_id, "SchematicIR circuit_id"),
            ("HardwareIR", schematic.hardware_ir_id, "SchematicIR hardware_ir_id"),
        ):
            bind_explicit(
                upstream_type=upstream_type,
                upstream_id=upstream_id,
                downstream_type="SchematicIR",
                downstream_id=schematic.id,
                dependency_kind=DependencyKind.GENERATION,
                reason=reason,
            )

    configs = session.scalars(
        select(MCUConfigRecord)
        .where(MCUConfigRecord.project_id == str(project_id))
        .order_by(MCUConfigRecord.created_at, MCUConfigRecord.id)
    )
    for config in configs:
        for pin_id in sorted(set((config.pin_assignment_revisions or {}).keys())):
            bind_explicit(
                upstream_type="PinAssignment",
                upstream_id=pin_id,
                downstream_type="MCUConfigIR",
                downstream_id=config.id,
                dependency_kind=DependencyKind.CONFIGURATION,
                reason="MCUConfigIR pin_assignment_revisions",
            )

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
            (
                "HardwareIR",
                firmware.hardware_ir_id,
                DependencyKind.GENERATION,
                "FirmwareIR hardware_ir_id",
            ),
            (
                "CircuitIR",
                firmware.circuit_id,
                DependencyKind.GENERATION,
                "FirmwareIR circuit_id",
            ),
            (
                "SchematicIR",
                firmware.schematic_id,
                DependencyKind.GENERATION,
                "FirmwareIR schematic_id",
            ),
        ):
            bind_explicit(
                upstream_type=upstream_type,
                upstream_id=upstream_id,
                downstream_type="FirmwareIR",
                downstream_id=firmware.id,
                dependency_kind=kind,
                reason=reason,
            )

    for test_ir in session.scalars(
        select(TestIRRecord)
        .where(TestIRRecord.project_id == str(project_id))
        .order_by(TestIRRecord.created_at, TestIRRecord.id)
    ):
        for requirement_id in sorted(set(test_ir.requirement_ids or [])):
            bind_explicit(
                upstream_type="Requirement",
                upstream_id=requirement_id,
                downstream_type="TestIR",
                downstream_id=test_ir.id,
                dependency_kind=DependencyKind.VERIFICATION,
                reason="TestIR requirement_ids",
            )

    for test_run in session.scalars(
        select(TestRunRecord)
        .where(TestRunRecord.project_id == str(project_id))
        .order_by(TestRunRecord.created_at, TestRunRecord.id)
    ):
        bind_explicit(
            upstream_type="TestIR",
            upstream_id=test_run.test_ir_id,
            downstream_type="TestRun",
            downstream_id=test_run.id,
            dependency_kind=DependencyKind.VERIFICATION,
            reason="TestRun test_ir_id",
        )
        bind_explicit(
            upstream_type="SourceRevision",
            upstream_id=test_run.source_revision_id,
            downstream_type="TestRun",
            downstream_id=test_run.id,
            dependency_kind=DependencyKind.INPUT,
            reason="TestRun source_revision_id",
        )

    for build in session.scalars(
        select(BuildRunRecord)
        .where(BuildRunRecord.project_id == str(project_id))
        .order_by(BuildRunRecord.created_at, BuildRunRecord.id)
    ):
        bind_explicit(
            upstream_type="SourceRevision",
            upstream_id=build.source_revision_id,
            downstream_type="BuildRun",
            downstream_id=build.id,
            dependency_kind=DependencyKind.INPUT,
            reason="BuildRun source_revision_id",
        )

    for analysis in session.scalars(
        select(FirmwareStaticAnalysisRecord)
        .where(FirmwareStaticAnalysisRecord.project_id == str(project_id))
        .order_by(FirmwareStaticAnalysisRecord.created_at, FirmwareStaticAnalysisRecord.id)
    ):
        bind_explicit(
            upstream_type="SourceRevision",
            upstream_id=analysis.source_revision_id,
            downstream_type="StaticAnalysis",
            downstream_id=analysis.id,
            dependency_kind=DependencyKind.INPUT,
            reason="StaticAnalysis source_revision_id",
        )
        bind_explicit(
            upstream_type="FirmwareIR",
            upstream_id=analysis.firmware_id,
            downstream_type="StaticAnalysis",
            downstream_id=analysis.id,
            dependency_kind=DependencyKind.GENERATION,
            reason="StaticAnalysis firmware_id",
        )

    for output in session.scalars(
        select(GeneratedProtocolOutputRecord)
        .where(GeneratedProtocolOutputRecord.project_id == str(project_id))
        .order_by(GeneratedProtocolOutputRecord.created_at, GeneratedProtocolOutputRecord.id)
    ):
        bind_explicit(
            upstream_type="ProtocolIR",
            upstream_id=output.protocol_id,
            downstream_type="GeneratedProtocolOutput",
            downstream_id=output.id,
            dependency_kind=DependencyKind.GENERATION,
            reason="Generated protocol output from ProtocolIR",
        )

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
            bind_explicit(
                upstream_type=upstream_type,
                upstream_id=upstream_id,
                downstream_type="ReviewRun",
                downstream_id=review.id,
                dependency_kind=DependencyKind.VERIFICATION,
                reason="ReviewRun explicit input reference",
            )
        bind_explicit(
            upstream_type="BuildRun",
            upstream_id=review.build_run_id,
            downstream_type="ReviewRun",
            downstream_id=review.id,
            dependency_kind=DependencyKind.VERIFICATION,
            reason="ReviewRun build_run_id",
        )
        bind_explicit(
            upstream_type="StaticAnalysis",
            upstream_id=review.static_analysis_id,
            downstream_type="ReviewRun",
            downstream_id=review.id,
            dependency_kind=DependencyKind.VERIFICATION,
            reason="ReviewRun static_analysis_id",
        )
        bind_explicit(
            upstream_type="SourceRevision",
            upstream_id=review.source_revision_id,
            downstream_type="ReviewRun",
            downstream_id=review.id,
            dependency_kind=DependencyKind.INPUT,
            reason="ReviewRun source_revision_id",
        )

    session.commit()
    return {
        "created_edges": created_edges,
        "existing_edges": existing_edges,
        "gaps": gaps,
        "errors": errors,
    }


__all__ = ["reconcile_project_dependencies"]
