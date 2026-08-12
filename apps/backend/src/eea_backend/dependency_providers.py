"""Explicit SQLAlchemy-backed node providers for the M18 graph."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any
from uuid import UUID

from eea_application.dependency_graph import (
    CallbackDependencyNodeProvider,
    DependencyNodeProviderRegistry,
    DependencyNodeSnapshot,
)
from eea_core.dependency_graph import DependencyNodeRef, canonical_semantic_hash
from eea_core.enums import ImpactAction
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from eea_backend.models import (
    ArtifactRecord,
    BuildRunRecord,
    CircuitRecord,
    EngineeringClaimRecord,
    FirmwareRecord,
    FirmwareStaticAnalysisRecord,
    HardwareIRRecord,
    MCUConfigRecord,
    PinAssignmentRecord,
    ProtocolRecord,
    RequirementRecord,
    ReviewRunRecord,
    SourceRevisionRecord,
    SystemArchitectureRecord,
    TestIRRecord,
    TestRunRecord,
)


def _snapshot(
    entity_type: str,
    record: Any,
    fields: Iterable[str],
    *,
    valid: bool = True,
    recovery_action: ImpactAction = ImpactAction.MANUAL_REVIEW,
) -> DependencyNodeSnapshot:
    payload = {name: getattr(record, name) for name in fields}
    return DependencyNodeSnapshot(
        ref=DependencyNodeRef(
            entity_type=entity_type,
            entity_id=str(record.id),
            revision=record.revision,
            semantic_hash=canonical_semantic_hash(payload),
        ),
        valid=valid,
        recovery_action=recovery_action,
    )


def _record_provider(
    session: Session,
    entity_type: str,
    record_type: type[Any],
    fields: tuple[str, ...],
    *,
    recovery_action: ImpactAction,
    validity: Callable[[Any], bool] | None = None,
    global_claim: bool = False,
) -> CallbackDependencyNodeProvider:
    def resolve(project_id: UUID, entity_id: str) -> DependencyNodeSnapshot | None:
        statement = select(record_type).where(record_type.id == entity_id)
        if hasattr(record_type, "project_id"):
            if global_claim:
                statement = statement.where(
                    or_(record_type.project_id == str(project_id), record_type.project_id.is_(None))
                )
            else:
                statement = statement.where(record_type.project_id == str(project_id))
        if record_type is ProtocolRecord:
            statement = statement.order_by(desc(record_type.revision))
        record = session.scalar(statement.limit(1))
        if record is None:
            return None
        return _snapshot(
            entity_type,
            record,
            fields,
            valid=validity(record) if validity else True,
            recovery_action=recovery_action,
        )

    return CallbackDependencyNodeProvider(entity_type, resolve)


def build_dependency_provider_registry(session: Session) -> DependencyNodeProviderRegistry:
    """Build the fixed provider allow-list for one SQLAlchemy session."""

    def current_or_valid(record: Any) -> bool:
        return getattr(record, "status", "CURRENT") not in {
            "INVALID",
            "DEPRECATED",
            "ARCHIVED",
            "REJECTED",
            "SUPERSEDED",
            "CONFLICTED",
        }

    def claim_valid(record: Any) -> bool:
        return bool(record.lifecycle not in {"REJECTED", "SUPERSEDED", "DEPRECATED", "ARCHIVED"})

    def requirement_valid(record: Any) -> bool:
        return bool(record.status != "REJECTED")

    providers = [
        _record_provider(
            session,
            "Artifact",
            ArtifactRecord,
            (
                "logical_name",
                "artifact_type",
                "version_label",
                "content_hash",
                "input_hash",
                "storage_uri",
                "parent_artifact_id",
                "dependency_ids",
                "dependency_hashes",
                "created_by",
                "generator_version",
                "tool_versions",
                "knowledge_snapshot",
            ),
            recovery_action=ImpactAction.REVALIDATE,
            validity=current_or_valid,
        ),
        _record_provider(
            session,
            "Requirement",
            RequirementRecord,
            (
                "code",
                "title",
                "requirement_type",
                "priority",
                "statement",
                "rationale",
                "acceptance_criteria",
                "status",
            ),
            recovery_action=ImpactAction.REGENERATE,
            validity=requirement_valid,
        ),
        _record_provider(
            session,
            "Claim",
            EngineeringClaimRecord,
            (
                "subject_ref",
                "predicate",
                "value_schema_ref",
                "value_json",
                "applicability",
                "source_priority",
                "source_version",
                "lifecycle",
            ),
            recovery_action=ImpactAction.MANUAL_REVIEW,
            validity=claim_valid,
            global_claim=True,
        ),
        _record_provider(
            session,
            "PinAssignment",
            PinAssignmentRecord,
            (
                "requirement_id",
                "device_ref",
                "package",
                "pin_name",
                "function",
                "locked",
                "claim_ids",
            ),
            recovery_action=ImpactAction.REGENERATE,
        ),
        _record_provider(
            session,
            "SystemArchitectureIR",
            SystemArchitectureRecord,
            (
                "pin_plan_id",
                "pin_plan_revision",
                "blocks",
                "interfaces",
                "decisions",
                "requirement_ids",
                "source_artifact_ids",
                "pin_assignment_revisions",
            ),
            recovery_action=ImpactAction.REGENERATE,
        ),
        _record_provider(
            session,
            "HardwareIR",
            HardwareIRRecord,
            (
                "architecture_id",
                "pin_plan_id",
                "pin_plan_revision",
                "modules",
                "device_instances",
                "power_domains",
                "interfaces",
                "pin_requirements",
                "constraints",
                "requirement_ids",
                "pin_assignment_revisions",
            ),
            recovery_action=ImpactAction.REGENERATE,
        ),
        _record_provider(
            session,
            "CircuitIR",
            CircuitRecord,
            (
                "hardware_ir_id",
                "hardware_ir_revision",
                "components",
                "nets",
                "power_nets",
                "constraints",
                "requirement_ids",
                "pin_assignment_revisions",
            ),
            recovery_action=ImpactAction.REGENERATE,
        ),
        _record_provider(
            session,
            "MCUConfigIR",
            MCUConfigRecord,
            (
                "hardware_ir_id",
                "hardware_ir_revision",
                "circuit_id",
                "circuit_revision",
                "schematic_id",
                "schematic_revision",
                "device_instance_id",
                "clock",
                "gpio",
                "peripherals",
                "dma",
                "interrupts",
                "memory",
                "debug",
                "capability_snapshot",
                "requirement_ids",
                "pin_assignment_revisions",
            ),
            recovery_action=ImpactAction.REGENERATE,
            validity=current_or_valid,
        ),
        _record_provider(
            session,
            "FirmwareIR",
            FirmwareRecord,
            (
                "mcu_config_id",
                "mcu_config_revision",
                "hardware_ir_id",
                "hardware_ir_revision",
                "circuit_id",
                "circuit_revision",
                "schematic_id",
                "schematic_revision",
                "source_revision_id",
                "dependency_lock_id",
                "dependency_lock_hash",
                "component_refs",
                "platform_adapter_id",
                "platform_adapter_version",
                "layers",
                "modules",
                "tasks",
                "interrupts",
                "shared_resources",
                "startup",
                "clock_tree",
                "peripheral_drivers",
                "memory_layout",
                "bsp",
                "build_target",
                "rule_results",
                "requirement_ids",
                "input_hash",
            ),
            recovery_action=ImpactAction.REGENERATE,
            validity=current_or_valid,
        ),
        _record_provider(
            session,
            "ProtocolIR",
            ProtocolRecord,
            ("version_label", "transports", "messages", "requirement_ids", "input_hash"),
            recovery_action=ImpactAction.REGENERATE,
            validity=current_or_valid,
        ),
        _record_provider(
            session,
            "SourceRevision",
            SourceRevisionRecord,
            (
                "repository_id",
                "commit_sha",
                "tree_hash",
                "dirty",
                "base_commit",
                "workspace_revision",
                "source_manifest_hash",
                "file_manifest",
            ),
            recovery_action=ImpactAction.REBUILD,
        ),
        _record_provider(
            session,
            "TestIR",
            TestIRRecord,
            (
                "requirement_ids",
                "requirement_revisions",
                "requirement_snapshots",
                "cases",
                "input_hash",
                "generator_version",
                "policy_version",
            ),
            recovery_action=ImpactAction.REGENERATE,
        ),
        _record_provider(
            session,
            "TestRun",
            TestRunRecord,
            (
                "test_ir_id",
                "test_ir_revision",
                "test_input_hash",
                "source_revision_id",
                "case_results",
                "tool_versions",
            ),
            recovery_action=ImpactAction.RERUN_TEST,
        ),
        _record_provider(
            session,
            "ReviewRun",
            ReviewRunRecord,
            (
                "source_revision_id",
                "policy_version",
                "input_hash",
                "build_run_id",
                "static_analysis_id",
                "test_run_id",
                "test_ir_id",
                "protocol_id",
                "status",
                "findings",
            ),
            recovery_action=ImpactAction.RERUN_REVIEW,
        ),
        _record_provider(
            session,
            "BuildRun",
            BuildRunRecord,
            (
                "source_revision_id",
                "firmware_id",
                "build_input_snapshot_id",
                "status",
                "build_input_hash",
                "diagnostics",
            ),
            recovery_action=ImpactAction.REBUILD,
        ),
        _record_provider(
            session,
            "StaticAnalysis",
            FirmwareStaticAnalysisRecord,
            (
                "firmware_id",
                "firmware_revision",
                "source_revision_id",
                "build_input_snapshot_id",
                "input_hash",
                "ruleset_version",
                "status",
                "tool_results",
            ),
            recovery_action=ImpactAction.RERUN_REVIEW,
        ),
    ]
    return DependencyNodeProviderRegistry(providers)


__all__ = ["build_dependency_provider_registry"]
