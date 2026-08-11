"""Deterministic M7 Pin Planner and pre-generation rule checks."""

from collections.abc import Sequence
from uuid import UUID

from eea_core.claims import EngineeringValue
from eea_core.entities import utc_now
from eea_core.enums import EngineeringErrorCode, IssueSeverity
from eea_core.errors import EngineeringError
from eea_core.intelligence import Device, DevicePin, PinFunction
from eea_core.pin_planner import (
    PinAssignment,
    PinCandidate,
    PinLock,
    PinPlan,
    PinRequirement,
    RuleResult,
)
from eea_core.requirements import RequirementAnalysis
from eea_ports.intelligence import DeviceProvider


class PinPlannerService:
    """Plan only from explicit requirements and provider-owned device facts."""

    rule_version = "1.0"

    def plan_from_analysis(
        self,
        *,
        analysis: RequirementAnalysis,
        device_ref: str,
        package: str | None,
        requirements: Sequence[PinRequirement],
        device_provider: DeviceProvider,
        locked_assignments: Sequence[PinAssignment] = (),
        locks: Sequence[PinLock] = (),
    ) -> PinPlan:
        """Plan only when every PinRequirement points to M6 canonical refs."""

        known_requirement_ids = set(analysis.requirement_ids)
        known_claim_ids = set(analysis.claim_ids)
        for requirement in requirements:
            if not set(requirement.requirement_ids) <= known_requirement_ids:
                raise EngineeringError(
                    EngineeringErrorCode.INVALID_REQUIREMENT,
                    "Pin requirement references a requirement outside the selected analysis",
                    details={"signal_name": requirement.signal_name},
                )
            if not set(requirement.claim_ids) <= known_claim_ids:
                raise EngineeringError(
                    EngineeringErrorCode.INVALID_REQUIREMENT,
                    "Pin requirement references a claim outside the selected analysis",
                    details={"signal_name": requirement.signal_name},
                )
        plan = self.plan(
            project_id=analysis.project_id,
            device_ref=device_ref,
            package=package,
            requirements=requirements,
            device_provider=device_provider,
            locked_assignments=locked_assignments,
            locks=locks,
        )
        return plan.model_copy(update={"analysis_id": analysis.id})

    def plan(
        self,
        *,
        project_id: UUID,
        device_ref: str,
        package: str | None,
        requirements: Sequence[PinRequirement],
        device_provider: DeviceProvider,
        locked_assignments: Sequence[PinAssignment] = (),
        locks: Sequence[PinLock] = (),
    ) -> PinPlan:
        device = device_provider.get_device(device_ref)
        candidates: list[PinCandidate] = []
        assignments = list(locked_assignments)
        rule_results: list[RuleResult] = []
        used_pins = {(item.package, item.pin_name) for item in assignments}
        locked_requirement_ids = {item.requirement_id for item in assignments if item.locked}

        if device is None or not isinstance(device, Device):
            for requirement in requirements:
                rule_results.append(
                    self._rule(
                        project_id,
                        requirement,
                        "DEVICE_FACTS_UNAVAILABLE",
                        "UNKNOWN",
                        IssueSeverity.HIGH,
                        "Device facts are unavailable; no pin assignment was inferred.",
                    )
                )
            return PinPlan(
                project_id=project_id,
                device_ref=device_ref,
                package=package,
                requirements=list(requirements),
                candidates=candidates,
                assignments=assignments,
                locks=list(locks),
                rule_results=rule_results,
            )

        if package is not None and package not in device.packages:
            for requirement in requirements:
                rule_results.append(
                    self._rule(
                        project_id,
                        requirement,
                        "PIN_PACKAGE_MISSING",
                        "FAIL",
                        IssueSeverity.HIGH,
                        "The requested package is not present in the device facts.",
                        threshold=package,
                    )
                )
            return PinPlan(
                project_id=project_id,
                device_ref=device_ref,
                package=package,
                requirements=list(requirements),
                candidates=candidates,
                assignments=assignments,
                locks=list(locks),
                rule_results=rule_results,
            )

        selected_device = device
        if package is not None:
            packaged = device_provider.get_device(device_ref, package=package)
            if not isinstance(packaged, Device):
                for requirement in requirements:
                    rule_results.append(
                        self._rule(
                            project_id,
                            requirement,
                            "DEVICE_FACTS_UNAVAILABLE",
                            "UNKNOWN",
                            IssueSeverity.HIGH,
                            "The provider could not verify facts for the requested package.",
                        )
                    )
                return PinPlan(
                    project_id=project_id,
                    device_ref=device_ref,
                    package=package,
                    requirements=list(requirements),
                    candidates=candidates,
                    assignments=assignments,
                    locks=list(locks),
                    rule_results=rule_results,
                )
            selected_device = packaged

        available_pins = [
            pin for pin in selected_device.pins if package is None or pin.package in {None, package}
        ]
        for requirement in requirements:
            if requirement.id in locked_requirement_ids:
                rule_results.append(
                    self._rule(
                        project_id,
                        requirement,
                        "PIN_LOCK_RETAINED",
                        "PASS",
                        IssueSeverity.INFO,
                        "The existing locked assignment was retained.",
                    )
                )
                continue

            matching = [
                (pin, function)
                for pin in available_pins
                for function in pin.functions
                if function.peripheral == requirement.required_peripheral
                and function.signal == requirement.required_function
            ]
            if not matching:
                rule_id = self._missing_function_rule(requirement)
                rule_results.append(
                    self._rule(
                        project_id,
                        requirement,
                        rule_id,
                        "FAIL",
                        IssueSeverity.HIGH,
                        "No device pin exposes the required peripheral function.",
                        threshold={
                            "peripheral": requirement.required_peripheral,
                            "signal": requirement.required_function,
                        },
                    )
                )
                continue

            for pin, function in matching:
                candidates.append(
                    PinCandidate(
                        project_id=project_id,
                        requirement_id=requirement.id,
                        device_ref=device_ref,
                        package=package,
                        pin_name=pin.name,
                        function=function,
                        score=self._score(requirement, pin),
                        source_refs=pin.source_refs,
                    )
                )

            viable: list[tuple[DevicePin, PinFunction, float]] = []
            rejected: list[tuple[str, str, str]] = []
            for pin, function in matching:
                outcome = self._hard_constraint_outcome(requirement, pin, selected_device)
                if outcome is None:
                    viable.append((pin, function, self._score(requirement, pin)))
                else:
                    rejected.append(outcome)
            if not viable:
                if any(status == "UNKNOWN" for _, status, _ in rejected):
                    rule_id, _, message = next(item for item in rejected if item[1] == "UNKNOWN")
                    rule_results.append(
                        self._rule(
                            project_id,
                            requirement,
                            rule_id,
                            "UNKNOWN",
                            IssueSeverity.HIGH,
                            message,
                        )
                    )
                else:
                    rule_id, _, message = rejected[0]
                    rule_results.append(
                        self._rule(
                            project_id,
                            requirement,
                            rule_id,
                            "FAIL",
                            IssueSeverity.HIGH,
                            message,
                        )
                    )
                continue

            viable.sort(key=lambda item: (-item[2], item[0].name, item[1].signal))
            selected = next(
                (item for item in viable if (package, item[0].name) not in used_pins), None
            )
            if selected is None:
                rule_results.append(
                    self._rule(
                        project_id,
                        requirement,
                        "PIN_CONFLICT",
                        "FAIL",
                        IssueSeverity.HIGH,
                        "All viable pins are already assigned to another requirement.",
                    )
                )
                continue

            pin, function, score = selected
            assignment = PinAssignment(
                project_id=project_id,
                requirement_id=requirement.id,
                device_ref=device_ref,
                package=package,
                pin_name=pin.name,
                function=function,
                score=score,
                claim_ids=requirement.claim_ids,
                evidence_ids=requirement.evidence_ids,
            )
            assignments.append(assignment)
            used_pins.add((package, pin.name))
            rule_results.append(
                self._rule(
                    project_id,
                    requirement,
                    "PIN_ASSIGNMENT_VALID",
                    "PASS",
                    IssueSeverity.INFO,
                    "The selected pin satisfies the declared hard constraints.",
                    affected_refs=[pin.name],
                )
            )

        return PinPlan(
            project_id=project_id,
            device_ref=device_ref,
            package=package,
            requirements=list(requirements),
            candidates=candidates,
            assignments=assignments,
            locks=list(locks),
            rule_results=rule_results,
        )

    def validate(self, plan: PinPlan, device_provider: DeviceProvider) -> list[RuleResult]:
        """Validate existing assignments without silently repairing them."""

        device = device_provider.get_device(plan.device_ref, package=plan.package)
        if not isinstance(device, Device):
            return [
                RuleResult(
                    project_id=plan.project_id,
                    rule_id="DEVICE_FACTS_UNAVAILABLE",
                    rule_version=self.rule_version,
                    stage="PRE_GENERATION",
                    status="UNKNOWN",
                    severity=IssueSeverity.HIGH,
                    recommendation="Obtain verifiable device/package facts before validating.",
                )
            ]
        results: list[RuleResult] = []
        seen: set[tuple[str | None, str]] = set()
        for assignment in plan.assignments:
            key = (assignment.package, assignment.pin_name)
            if key in seen:
                results.append(
                    RuleResult(
                        project_id=plan.project_id,
                        rule_id="PIN_CONFLICT",
                        rule_version=self.rule_version,
                        stage="PRE_GENERATION",
                        status="FAIL",
                        severity=IssueSeverity.HIGH,
                        affected_refs=[assignment.pin_name],
                        recommendation="Assign each physical pin to at most one requirement.",
                    )
                )
                continue
            seen.add(key)
            pin = next((item for item in device.pins if item.name == assignment.pin_name), None)
            if pin is None or assignment.function not in pin.functions:
                results.append(
                    RuleResult(
                        project_id=plan.project_id,
                        rule_id="PIN_FUNCTION_INVALID",
                        rule_version=self.rule_version,
                        stage="PRE_GENERATION",
                        status="FAIL",
                        severity=IssueSeverity.HIGH,
                        affected_refs=[assignment.pin_name],
                        recommendation="Select a pin/function present in the device facts.",
                    )
                )
                continue
            results.append(
                RuleResult(
                    project_id=plan.project_id,
                    rule_id="PIN_ASSIGNMENT_VALID",
                    rule_version=self.rule_version,
                    stage="PRE_GENERATION",
                    status="PASS",
                    severity=IssueSeverity.INFO,
                    affected_refs=[assignment.pin_name],
                )
            )
        return results

    def lock_assignment(
        self, assignment: PinAssignment, *, locked_by: str, reason: str
    ) -> tuple[PinAssignment, PinLock]:
        if not locked_by.strip() or not reason.strip():
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR,
                "A pin lock requires an actor and reason",
            )
        if assignment.locked:
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR,
                "The pin assignment is already locked",
                details={"assignment_id": str(assignment.id)},
            )
        locked = assignment.model_copy(
            update={"locked": True, "revision": assignment.revision + 1, "updated_at": utc_now()}
        )
        lock = PinLock(
            project_id=assignment.project_id,
            assignment_id=assignment.id,
            locked_by=locked_by,
            reason=reason,
        )
        return locked, lock

    def unlock_assignment(
        self, assignment: PinAssignment, *, unlocked_by: str, reason: str
    ) -> PinAssignment:
        if not unlocked_by.strip() or not reason.strip():
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR,
                "An unlock requires an actor and reason",
            )
        if not assignment.locked:
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR,
                "The pin assignment is not locked",
                details={"assignment_id": str(assignment.id)},
            )
        return assignment.model_copy(
            update={"locked": False, "revision": assignment.revision + 1, "updated_at": utc_now()}
        )

    def _hard_constraint_outcome(
        self, requirement: PinRequirement, pin: DevicePin, device: Device
    ) -> tuple[str, str, str] | None:
        if requirement.hard_constraints.get("five_v_tolerant") is True:
            if pin.five_v_tolerant is None:
                return (
                    "FIVE_V_TOLERANCE_INVALID",
                    "UNKNOWN",
                    "The device facts do not state five-volt tolerance for this pin.",
                )
            if not pin.five_v_tolerant:
                return (
                    "FIVE_V_TOLERANCE_INVALID",
                    "FAIL",
                    "The candidate pin is not five-volt tolerant.",
                )

        if requirement.hard_constraints.get("avoid_debug") is True:
            debug_pins = device.electrical.get("debug_pins")
            if not isinstance(debug_pins, list):
                return (
                    "DEBUG_PIN_CONFLICT",
                    "UNKNOWN",
                    "The device facts do not identify reserved debug pins.",
                )
            if pin.name in debug_pins:
                return (
                    "DEBUG_PIN_CONFLICT",
                    "FAIL",
                    "The candidate pin is reserved for debug access.",
                )

        voltage = requirement.hard_constraints.get("voltage")
        if voltage is not None:
            requested = EngineeringValue.model_validate(voltage)
            available_raw = device.electrical.get("io_voltage")
            if available_raw is None:
                return (
                    "GPIO_VOLTAGE_EXCEEDED",
                    "UNKNOWN",
                    "The device facts do not provide a canonical I/O voltage.",
                )
            try:
                available = EngineeringValue.model_validate(available_raw)
            except ValueError:
                return (
                    "GPIO_VOLTAGE_EXCEEDED",
                    "UNKNOWN",
                    "The device I/O voltage is not a canonical EngineeringValue.",
                )
            if requested.dimension is not available.dimension:
                return (
                    "GPIO_VOLTAGE_EXCEEDED",
                    "UNKNOWN",
                    "The requirement and device I/O voltage dimensions cannot be compared.",
                )
            if requested.require_normalized_nominal() > available.require_normalized_nominal():
                return (
                    "GPIO_VOLTAGE_EXCEEDED",
                    "FAIL",
                    "The requested voltage exceeds the device I/O voltage fact.",
                )

        if requirement.hard_constraints.get("complementary_pwm") is True:
            paired_signal = (
                requirement.required_function[:-1]
                if requirement.required_function.endswith("N")
                else requirement.required_function + "N"
            )
            if not any(
                function.signal == paired_signal
                for candidate_pin in device.pins
                for function in candidate_pin.functions
            ):
                return (
                    "COMPLEMENTARY_PWM_MISSING",
                    "FAIL",
                    "The device facts do not expose the required complementary PWM function.",
                )
        return None

    @staticmethod
    def _missing_function_rule(requirement: PinRequirement) -> str:
        if "adc_channel" in requirement.hard_constraints:
            return "ADC_CHANNEL_INVALID"
        if requirement.hard_constraints.get("pwm_required") is True:
            return "PWM_CAPABILITY_MISSING"
        return "PIN_FUNCTION_INVALID"

    @staticmethod
    def _score(requirement: PinRequirement, pin: DevicePin) -> float:
        preferred_domain = requirement.preferred_constraints.get("voltage_domain")
        if preferred_domain is not None and pin.voltage_domain == preferred_domain:
            return 1.0
        preferred_pin = requirement.preferred_constraints.get("pin_name")
        if preferred_pin is not None and pin.name == preferred_pin:
            return 1.0
        return 0.5

    def _rule(
        self,
        project_id: UUID,
        requirement: PinRequirement,
        rule_id: str,
        status: str,
        severity: IssueSeverity,
        recommendation: str,
        *,
        affected_refs: list[str] | None = None,
        threshold: object | None = None,
    ) -> RuleResult:
        return RuleResult(
            project_id=project_id,
            rule_id=rule_id,
            rule_version=self.rule_version,
            stage="PRE_GENERATION",
            status=status,  # type: ignore[arg-type]
            severity=severity,
            affected_refs=affected_refs or [requirement.signal_name],
            threshold=threshold,
            claim_ids=requirement.claim_ids,
            evidence_ids=requirement.evidence_ids,
            recommendation=recommendation,
            input_snapshot={
                "signal_name": requirement.signal_name,
                "required_peripheral": requirement.required_peripheral,
                "required_function": requirement.required_function,
            },
        )


__all__ = ["PinPlannerService"]
