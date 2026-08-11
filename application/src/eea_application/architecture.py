"""M8 architecture generation over a gated, persisted M7 pin plan."""

from collections.abc import Iterable
from uuid import UUID

from eea_core.architecture import (
    ArchitectureBlock,
    ArchitectureBundle,
    ArchitectureDecision,
    ArchitectureInterface,
    HardwareDeviceInstance,
    HardwareInterface,
    HardwareIR,
    HardwareModule,
    SystemArchitectureIR,
)
from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_core.pin_planner import PinPlan


def _unique(values: Iterable[UUID]) -> list[UUID]:
    result: list[UUID] = []
    seen: set[UUID] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


class ArchitectureService:
    """Create architecture IR without reconstructing a second pin source of truth."""

    def generate(self, plan: PinPlan, *, latest_plan_id: UUID) -> ArchitectureBundle:
        self._validate_prerequisites(plan, latest_plan_id=latest_plan_id)
        requirement_by_id = {requirement.id: requirement for requirement in plan.requirements}
        requirement_ids = _unique(
            requirement_id
            for requirement in plan.requirements
            for requirement_id in requirement.requirement_ids
        )
        evidence_ids = _unique(
            evidence_id
            for requirement in plan.requirements
            for evidence_id in requirement.evidence_ids
        )
        evidence_ids = _unique(
            [*evidence_ids]
            + [
                evidence_id
                for assignment in plan.assignments
                for evidence_id in assignment.evidence_ids
            ]
            + [evidence_id for result in plan.rule_results for evidence_id in result.evidence_ids]
        )
        assignment_revisions = {
            str(assignment.id): assignment.revision for assignment in plan.assignments
        }

        block = ArchitectureBlock(
            name="compute-unit",
            kind="compute",
            description="The device boundary selected by the persisted pin plan.",
            attributes={"device_ref": plan.device_ref, "package": plan.package},
            requirement_ids=requirement_ids,
            evidence_ids=evidence_ids,
        )
        module = HardwareModule(
            name="compute-unit",
            kind="device-module",
            attributes={"device_ref": plan.device_ref, "package": plan.package},
            requirement_ids=requirement_ids,
            evidence_ids=evidence_ids,
        )
        device_instance = HardwareDeviceInstance(
            name="compute-device",
            device_ref=plan.device_ref,
            package=plan.package,
            module_ref=module.id,
            pin_assignment_ids=[assignment.id for assignment in plan.assignments],
            evidence_ids=evidence_ids,
        )

        architecture_interfaces: list[ArchitectureInterface] = []
        hardware_interfaces: list[HardwareInterface] = []
        for assignment in plan.assignments:
            requirement = requirement_by_id.get(assignment.requirement_id)
            if requirement is None:
                raise EngineeringError(
                    EngineeringErrorCode.INVALID_REQUIREMENT,
                    "Pin assignment does not reference a plan requirement",
                    details={"assignment_id": str(assignment.id)},
                )
            signal_ref = f"external:{requirement.signal_name}"
            function = assignment.function.model_dump(mode="json")
            attributes = {
                "pin_name": assignment.pin_name,
                "function": function,
                "assignment_revision": assignment.revision,
            }
            architecture_interfaces.append(
                ArchitectureInterface(
                    name=requirement.signal_name,
                    interface_type=assignment.function.peripheral,
                    source_ref=str(device_instance.id),
                    target_ref=signal_ref,
                    attributes=attributes,
                    pin_assignment_ids=[assignment.id],
                    requirement_ids=requirement.requirement_ids,
                    evidence_ids=[*requirement.evidence_ids, *assignment.evidence_ids],
                )
            )
            hardware_interfaces.append(
                HardwareInterface(
                    name=requirement.signal_name,
                    interface_type=assignment.function.peripheral,
                    endpoint_refs=[str(device_instance.id), signal_ref],
                    attributes=attributes,
                    pin_assignment_ids=[assignment.id],
                    requirement_ids=requirement.requirement_ids,
                    evidence_ids=[*requirement.evidence_ids, *assignment.evidence_ids],
                )
            )

        decision = ArchitectureDecision(
            title="Use the persisted M7 pin map",
            decision="Architecture interfaces shall consume the locked M7 assignments.",
            rationale="A later architecture stage must not infer or replace physical pin facts.",
            requirement_ids=requirement_ids,
            evidence_ids=evidence_ids,
        )
        constraints: list[dict[str, object]] = [
            {
                "rule_id": result.rule_id,
                "rule_version": result.rule_version,
                "status": result.status,
                "severity": result.severity.value,
                "affected_refs": result.affected_refs,
            }
            for result in plan.rule_results
        ]
        architecture = SystemArchitectureIR(
            project_id=plan.project_id,
            pin_plan_id=plan.id,
            pin_plan_revision=plan.revision,
            blocks=[block],
            interfaces=architecture_interfaces,
            decisions=[decision],
            requirement_ids=requirement_ids,
            evidence_ids=evidence_ids,
            pin_assignment_revisions=assignment_revisions,
        )
        hardware = HardwareIR(
            project_id=plan.project_id,
            architecture_id=architecture.id,
            pin_plan_id=plan.id,
            pin_plan_revision=plan.revision,
            modules=[module],
            device_instances=[device_instance],
            interfaces=hardware_interfaces,
            pin_requirements=list(plan.requirements),
            constraints=constraints,
            requirement_ids=requirement_ids,
            evidence_ids=evidence_ids,
            pin_assignment_revisions=assignment_revisions,
        )
        return ArchitectureBundle(system_architecture=architecture, hardware=hardware)

    @staticmethod
    def _validate_prerequisites(plan: PinPlan, *, latest_plan_id: UUID) -> None:
        if plan.id != latest_plan_id:
            raise EngineeringError(
                EngineeringErrorCode.INVALID_REQUIREMENT,
                "The selected pin plan is stale; replan before generating architecture",
                details={"reason": "STALE_PIN_PLAN", "plan_id": str(plan.id)},
            )
        if plan.analysis_id is None:
            raise EngineeringError(
                EngineeringErrorCode.INVALID_REQUIREMENT,
                "The pin plan is missing its canonical requirement analysis",
                details={"reason": "MISSING_ANALYSIS", "plan_id": str(plan.id)},
            )
        if not plan.assignments:
            raise EngineeringError(
                EngineeringErrorCode.INVALID_REQUIREMENT,
                "Architecture requires at least one pin assignment",
                details={"reason": "MISSING_ASSIGNMENTS", "plan_id": str(plan.id)},
            )
        unlocked = [str(assignment.id) for assignment in plan.assignments if not assignment.locked]
        if unlocked:
            raise EngineeringError(
                EngineeringErrorCode.INVALID_REQUIREMENT,
                "All pin assignments must be locked before architecture generation",
                details={"reason": "UNLOCKED_ASSIGNMENTS", "assignment_ids": unlocked},
            )
        blocked = [
            result.rule_id for result in plan.rule_results if result.status in {"FAIL", "UNKNOWN"}
        ]
        if blocked:
            raise EngineeringError(
                EngineeringErrorCode.INVALID_REQUIREMENT,
                "Architecture prerequisites contain a failed or unknown M7 rule",
                details={"reason": "M7_RULE_GATE_FAILED", "rule_ids": blocked},
            )
        if not plan.rule_results:
            raise EngineeringError(
                EngineeringErrorCode.INVALID_REQUIREMENT,
                "Architecture requires persisted M7 rule results",
                details={"reason": "MISSING_RULE_RESULTS", "plan_id": str(plan.id)},
            )


__all__ = ["ArchitectureService"]
