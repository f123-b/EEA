"""Deterministic M9 CircuitIR construction and electrical rule validation."""

from collections.abc import Iterable, Sequence
from uuid import UUID

from eea_core.architecture import HardwareIR
from eea_core.circuit import (
    CircuitBundle,
    CircuitComponent,
    CircuitConstraint,
    CircuitIR,
    CircuitNet,
    PowerNet,
)
from eea_core.claims import EngineeringValue
from eea_core.entities import utc_now
from eea_core.enums import EngineeringDimension, EngineeringErrorCode, IssueSeverity
from eea_core.errors import EngineeringError
from eea_core.pin_planner import RuleResult


def _unique(values: Iterable[UUID]) -> list[UUID]:
    result: list[UUID] = []
    seen: set[UUID] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


class CircuitService:
    """Create and validate circuit topology from one M8 HardwareIR snapshot."""

    rule_version = "1.0"

    def generate(
        self,
        hardware: HardwareIR,
        *,
        components: Sequence[CircuitComponent] = (),
        nets: Sequence[CircuitNet] = (),
        power_nets: Sequence[PowerNet] = (),
        constraints: Sequence[CircuitConstraint] = (),
    ) -> CircuitBundle:
        self._validate_pin_refs(hardware, nets)
        requirement_ids = _unique(
            [*hardware.requirement_ids]
            + [value for net in nets for value in net.requirement_ids]
            + [value for power_net in power_nets for value in power_net.requirement_ids]
            + [value for constraint in constraints for value in constraint.requirement_ids]
        )
        evidence_ids = _unique(
            [*hardware.evidence_ids]
            + [value for net in nets for value in net.evidence_ids]
            + [value for power_net in power_nets for value in power_net.evidence_ids]
            + [value for component in components for value in component.evidence_ids]
            + [value for constraint in constraints for value in constraint.evidence_ids]
        )
        circuit = CircuitIR(
            project_id=hardware.project_id,
            hardware_ir_id=hardware.id,
            hardware_ir_revision=hardware.revision,
            components=list(components),
            nets=list(nets),
            power_nets=list(power_nets),
            constraints=list(constraints),
            requirement_ids=requirement_ids,
            evidence_ids=evidence_ids,
            pin_assignment_revisions=dict(hardware.pin_assignment_revisions),
        )
        results = self.validate(circuit, hardware)
        return CircuitBundle(
            circuit=circuit.model_copy(update={"rule_results": results, "updated_at": utc_now()}),
            rule_results=results,
        )

    def validate(self, circuit: CircuitIR, hardware: HardwareIR) -> list[RuleResult]:
        results: list[RuleResult] = []
        known_pin_ids = {
            pin_id for interface in hardware.interfaces for pin_id in interface.pin_assignment_ids
        }
        for net in circuit.nets:
            if not net.endpoints:
                results.append(
                    self._rule(
                        circuit,
                        "NET_ENDPOINT_REQUIRED",
                        "FAIL",
                        IssueSeverity.HIGH,
                        [net.name],
                        recommendation="Connect every circuit net to at least one endpoint.",
                    )
                )
            for endpoint in net.endpoints:
                if (
                    endpoint.pin_assignment_id is not None
                    and endpoint.pin_assignment_id not in known_pin_ids
                ):
                    results.append(
                        self._rule(
                            circuit,
                            "CIRCUIT_PIN_ASSIGNMENT_INVALID",
                            "FAIL",
                            IssueSeverity.HIGH,
                            [net.name, endpoint.pin_ref],
                            recommendation=(
                                "Use a pin assignment exposed by the selected HardwareIR."
                            ),
                        )
                    )

        for constraint in circuit.constraints:
            results.append(self._validate_constraint(circuit, constraint))
        if not results:
            results.append(
                self._rule(
                    circuit,
                    "CIRCUIT_VALIDATION_NOT_APPLICABLE",
                    "NOT_APPLICABLE",
                    IssueSeverity.INFO,
                    [str(circuit.id)],
                    recommendation="No deterministic circuit rule had an applicable input.",
                )
            )
        return results

    @staticmethod
    def _validate_pin_refs(hardware: HardwareIR, nets: Sequence[CircuitNet]) -> None:
        known_pin_ids = {
            pin_id for interface in hardware.interfaces for pin_id in interface.pin_assignment_ids
        }
        invalid = [
            str(endpoint.pin_assignment_id)
            for net in nets
            for endpoint in net.endpoints
            if endpoint.pin_assignment_id is not None
            and endpoint.pin_assignment_id not in known_pin_ids
        ]
        if invalid:
            raise EngineeringError(
                EngineeringErrorCode.INVALID_REQUIREMENT,
                "Circuit input references a pin assignment outside the selected HardwareIR",
                details={"reason": "PIN_ASSIGNMENT_SOURCE_MISMATCH", "pin_assignment_ids": invalid},
            )

    def _validate_constraint(self, circuit: CircuitIR, constraint: CircuitConstraint) -> RuleResult:
        rule_id = constraint.rule_id
        if rule_id == "MOSFET_VDS_MARGIN":
            return self._validate_mosfet_vds(circuit, constraint)
        if rule_id == "ADC_RANGE":
            return self._validate_adc_range(circuit, constraint)
        if rule_id == "GATE_DRIVER_VOLTAGE":
            return self._validate_gate_driver(circuit, constraint)
        if rule_id == "CAN_TRANSCEIVER":
            return self._validate_can_transceiver(circuit, constraint)
        if rule_id == "TERMINATION":
            return self._validate_termination(circuit, constraint)
        return self._rule(
            circuit,
            rule_id,
            "NOT_APPLICABLE",
            IssueSeverity.INFO,
            [constraint.target_ref],
            claim_ids=constraint.requirement_ids,
            evidence_ids=constraint.evidence_ids,
            recommendation="No M9 deterministic implementation is registered for this rule.",
        )

    def _validate_mosfet_vds(self, circuit: CircuitIR, constraint: CircuitConstraint) -> RuleResult:
        values = self._voltage_values(
            constraint,
            ("bus_voltage", "transient_voltage", "vds_rating"),
        )
        if values is None:
            return self._unknown(
                circuit, constraint, "Provide canonical voltage facts for VDS margin."
            )
        bus_voltage, transient_voltage, vds_rating = values
        margin = constraint.parameters.get("required_margin", 1.2)
        if not isinstance(margin, (int, float)) or margin <= 0:
            return self._unknown(circuit, constraint, "Provide a positive numeric VDS margin.")
        required = max(
            bus_voltage.require_normalized_nominal(),
            transient_voltage.require_normalized_nominal(),
        ) * float(margin)
        rating = vds_rating.require_normalized_nominal()
        status = "PASS" if rating >= required else "FAIL"
        return self._rule(
            circuit,
            constraint.rule_id,
            status,
            IssueSeverity.HIGH,
            [constraint.target_ref],
            claim_ids=constraint.requirement_ids,
            evidence_ids=constraint.evidence_ids,
            measured=vds_rating,
            threshold={"required_voltage": required, "margin": margin},
            recommendation="Select a higher VDS-rated component or reduce the transient exposure."
            if status == "FAIL"
            else "VDS rating satisfies the declared margin.",
        )

    def _validate_adc_range(self, circuit: CircuitIR, constraint: CircuitConstraint) -> RuleResult:
        values = self._voltage_values(
            constraint,
            ("input_min", "input_max", "adc_min", "adc_max"),
        )
        if values is None:
            return self._unknown(
                circuit, constraint, "Provide canonical ADC and input voltage ranges."
            )
        input_min, input_max, adc_min, adc_max = values
        input_low = input_min.require_normalized_nominal()
        input_high = input_max.require_normalized_nominal()
        adc_low = adc_min.require_normalized_nominal()
        adc_high = adc_max.require_normalized_nominal()
        if input_low > input_high or adc_low > adc_high:
            status = "FAIL"
        else:
            status = "PASS" if input_low >= adc_low and input_high <= adc_high else "FAIL"
        return self._rule(
            circuit,
            constraint.rule_id,
            status,
            IssueSeverity.HIGH,
            [constraint.target_ref],
            claim_ids=constraint.requirement_ids,
            evidence_ids=constraint.evidence_ids,
            measured={"input_min": input_min, "input_max": input_max},
            threshold={"adc_min": adc_min, "adc_max": adc_max},
            recommendation="Keep the input range within the ADC-safe range."
            if status == "FAIL"
            else "Input range is within the ADC-safe range.",
        )

    def _validate_gate_driver(
        self, circuit: CircuitIR, constraint: CircuitConstraint
    ) -> RuleResult:
        values = self._voltage_values(constraint, ("driver_voltage", "gate_required"))
        if values is None:
            return self._unknown(circuit, constraint, "Provide canonical driver and gate voltages.")
        driver_voltage, gate_required = values
        status = (
            "PASS"
            if driver_voltage.require_normalized_nominal()
            >= gate_required.require_normalized_nominal()
            else "FAIL"
        )
        return self._rule(
            circuit,
            constraint.rule_id,
            status,
            IssueSeverity.HIGH,
            [constraint.target_ref],
            claim_ids=constraint.requirement_ids,
            evidence_ids=constraint.evidence_ids,
            measured=driver_voltage,
            threshold=gate_required,
            recommendation="Increase driver voltage or select a compatible gate requirement."
            if status == "FAIL"
            else "Driver voltage satisfies the gate requirement.",
        )

    def _validate_can_transceiver(
        self, circuit: CircuitIR, constraint: CircuitConstraint
    ) -> RuleResult:
        present = constraint.parameters.get("transceiver_present")
        if not isinstance(present, bool):
            return self._unknown(
                circuit, constraint, "Declare whether the CAN transceiver is present."
            )
        status = "PASS" if present else "FAIL"
        return self._rule(
            circuit,
            constraint.rule_id,
            status,
            IssueSeverity.HIGH,
            [constraint.target_ref],
            claim_ids=constraint.requirement_ids,
            evidence_ids=constraint.evidence_ids,
            measured=present,
            threshold=True,
            recommendation="Add a verified CAN transceiver to the circuit."
            if status == "FAIL"
            else "CAN transceiver presence is verified.",
        )

    def _validate_termination(
        self, circuit: CircuitIR, constraint: CircuitConstraint
    ) -> RuleResult:
        count = constraint.parameters.get("termination_count")
        required = constraint.parameters.get("required_count", 2)
        if not isinstance(count, int) or not isinstance(required, int) or required < 0:
            return self._unknown(circuit, constraint, "Provide integer termination counts.")
        status = "PASS" if count == required else "FAIL"
        return self._rule(
            circuit,
            constraint.rule_id,
            status,
            IssueSeverity.HIGH,
            [constraint.target_ref],
            claim_ids=constraint.requirement_ids,
            evidence_ids=constraint.evidence_ids,
            measured=count,
            threshold=required,
            recommendation="Match the declared termination count to the interface topology."
            if status == "FAIL"
            else "Termination count matches the declared topology.",
        )

    @staticmethod
    def _voltage_values(
        constraint: CircuitConstraint, keys: tuple[str, ...]
    ) -> tuple[EngineeringValue, ...] | None:
        values: list[EngineeringValue] = []
        for key in keys:
            raw = constraint.parameters.get(key)
            try:
                value = EngineeringValue.model_validate(raw)
            except (TypeError, ValueError):
                return None
            if value.dimension is not EngineeringDimension.VOLTAGE:
                return None
            values.append(value)
        return tuple(values)

    def _unknown(
        self, circuit: CircuitIR, constraint: CircuitConstraint, recommendation: str
    ) -> RuleResult:
        return self._rule(
            circuit,
            constraint.rule_id,
            "UNKNOWN",
            IssueSeverity.HIGH,
            [constraint.target_ref],
            claim_ids=constraint.requirement_ids,
            evidence_ids=constraint.evidence_ids,
            recommendation=recommendation,
        )

    def _rule(
        self,
        circuit: CircuitIR,
        rule_id: str,
        status: str,
        severity: IssueSeverity,
        affected_refs: list[str],
        *,
        claim_ids: Sequence[UUID] = (),
        evidence_ids: Sequence[UUID] = (),
        measured: object | None = None,
        threshold: object | None = None,
        recommendation: str,
    ) -> RuleResult:
        return RuleResult(
            project_id=circuit.project_id,
            rule_id=rule_id,
            rule_version=self.rule_version,
            stage="PRE_GENERATION",
            status=status,  # type: ignore[arg-type]
            severity=severity,
            affected_refs=affected_refs,
            measured=measured,
            threshold=threshold,
            claim_ids=list(claim_ids),
            evidence_ids=list(evidence_ids),
            recommendation=recommendation,
            input_snapshot={"circuit_id": str(circuit.id)},
        )


__all__ = ["CircuitService"]
