"""Deterministic M10 schematic generation and ERC result handling."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from collections.abc import Iterable, Sequence
from uuid import UUID

from eea_core.circuit import CircuitIR
from eea_core.entities import Artifact
from eea_core.enums import ArtifactStatus, EngineeringErrorCode, IssueSeverity
from eea_core.errors import EngineeringError
from eea_core.pin_planner import RuleResult
from eea_core.schematic import ErcIssue, ErcReport, SchematicBundle, SchematicIR


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_hash(value: object) -> str:
    return _sha256(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")))


def _unique(values: Iterable[UUID]) -> list[UUID]:
    result: list[UUID] = []
    seen: set[UUID] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


class SchematicService:
    """Build an editable netlist without introducing a new pin source of truth."""

    generator_version = "m10.1"
    rule_version = "1.0"

    def generate(self, circuit: CircuitIR) -> SchematicBundle:
        preflight = self.preflight(circuit)
        netlist_text = self._netlist_text(circuit)
        input_hash = _json_hash(circuit.model_dump(mode="json"))
        content_hash = _sha256(netlist_text)
        artifact = Artifact(
            project_id=circuit.project_id,
            logical_name=f"schematic-{circuit.project_id}",
            artifact_type="SCHEMATIC_NETLIST",
            version_label=f"circuit-{circuit.id}-r{circuit.revision}",
            content_hash=content_hash,
            input_hash=input_hash,
            storage_uri="inline://schematic/pending",
            dependency_ids=[circuit.id, circuit.hardware_ir_id],
            dependency_hashes={
                "circuit": input_hash,
                "hardware_ir": _json_hash(
                    {
                        "id": str(circuit.hardware_ir_id),
                        "revision": circuit.hardware_ir_revision,
                        "pin_assignment_revisions": circuit.pin_assignment_revisions,
                    }
                ),
            },
            created_by="eea:m10",
            generator_version=self.generator_version,
            status=ArtifactStatus.CURRENT,
        )
        schematic = SchematicIR(
            project_id=circuit.project_id,
            artifact_id=artifact.id,
            circuit_id=circuit.id,
            circuit_revision=circuit.revision,
            hardware_ir_id=circuit.hardware_ir_id,
            hardware_ir_revision=circuit.hardware_ir_revision,
            components=list(circuit.components),
            nets=list(circuit.nets),
            power_nets=list(circuit.power_nets),
            constraints=list(circuit.constraints),
            netlist_text=netlist_text,
            content_hash=content_hash,
            input_hash=input_hash,
            preflight_results=preflight,
            requirement_ids=list(circuit.requirement_ids),
            evidence_ids=list(circuit.evidence_ids),
            pin_assignment_revisions=dict(circuit.pin_assignment_revisions),
        )
        artifact.storage_uri = f"inline://schematic/{schematic.id}"
        return SchematicBundle(
            artifact=artifact,
            schematic=schematic,
            erc_report=self._preflight_report(schematic, preflight),
        )

    def preflight(self, circuit: CircuitIR) -> list[RuleResult]:
        results: list[RuleResult] = []
        references = [component.reference for component in circuit.components]
        for reference, count in Counter(references).items():
            if count > 1:
                results.append(
                    self._rule(
                        circuit,
                        "SCHEMATIC_COMPONENT_REFERENCE_DUPLICATE",
                        "FAIL",
                        IssueSeverity.HIGH,
                        [reference],
                        recommendation="Use one unique schematic reference for each component.",
                    )
                )
        net_names = [net.name for net in circuit.nets]
        for name, count in Counter(net_names).items():
            if count > 1:
                results.append(
                    self._rule(
                        circuit,
                        "SCHEMATIC_NET_NAME_DUPLICATE",
                        "FAIL",
                        IssueSeverity.HIGH,
                        [name],
                        recommendation="Use one unique net name for each schematic net.",
                    )
                )
        if not circuit.components:
            results.append(
                self._rule(
                    circuit,
                    "SCHEMATIC_COMPONENT_REQUIRED",
                    "FAIL",
                    IssueSeverity.HIGH,
                    [str(circuit.id)],
                    recommendation=(
                        "Add at least one CircuitIR component before schematic generation."
                    ),
                )
            )
        if not circuit.nets:
            results.append(
                self._rule(
                    circuit,
                    "SCHEMATIC_NET_REQUIRED",
                    "FAIL",
                    IssueSeverity.HIGH,
                    [str(circuit.id)],
                    recommendation="Add CircuitIR nets before schematic generation.",
                )
            )
        known_references = set(references)
        known_net_ids = {net.id for net in circuit.nets}
        known_component_ids = {component.id for component in circuit.components}
        for net in circuit.nets:
            if not net.endpoints:
                results.append(
                    self._rule(
                        circuit,
                        "SCHEMATIC_NET_ENDPOINT_REQUIRED",
                        "FAIL",
                        IssueSeverity.HIGH,
                        [net.name],
                        recommendation="Connect every schematic net to at least one endpoint.",
                    )
                )
            for endpoint in net.endpoints:
                if endpoint.component_ref not in known_references:
                    results.append(
                        self._rule(
                            circuit,
                            "SCHEMATIC_NET_COMPONENT_MISSING",
                            "FAIL",
                            IssueSeverity.HIGH,
                            [net.name, endpoint.component_ref],
                            recommendation=(
                                "Add the endpoint component to CircuitIR before generation."
                            ),
                        )
                    )
        for power_net in circuit.power_nets:
            for component_id in power_net.source_component_ids:
                if component_id not in known_component_ids:
                    results.append(
                        self._rule(
                            circuit,
                            "SCHEMATIC_POWER_SOURCE_COMPONENT_INVALID",
                            "FAIL",
                            IssueSeverity.HIGH,
                            [power_net.name, str(component_id)],
                            recommendation=(
                                "Reference only components present in the same CircuitIR snapshot."
                            ),
                        )
                    )
            for net_id in power_net.net_ids:
                if net_id not in known_net_ids:
                    results.append(
                        self._rule(
                            circuit,
                            "SCHEMATIC_POWER_NET_REFERENCE_INVALID",
                            "FAIL",
                            IssueSeverity.HIGH,
                            [power_net.name, str(net_id)],
                            recommendation=(
                                "Reference only nets present in the same CircuitIR snapshot."
                            ),
                        )
                    )
        for source_result in circuit.rule_results:
            if source_result.status in {"FAIL", "UNKNOWN"}:
                status = source_result.status
                results.append(
                    self._rule(
                        circuit,
                        "SCHEMATIC_SOURCE_CIRCUIT_RULE_NOT_PASS",
                        status,
                        IssueSeverity.HIGH,
                        source_result.affected_refs or [source_result.rule_id],
                        recommendation="Resolve or review the source CircuitIR rule before ERC.",
                    )
                )
        if not results:
            results.append(
                self._rule(
                    circuit,
                    "SCHEMATIC_PREFLIGHT_NOT_APPLICABLE",
                    "NOT_APPLICABLE",
                    IssueSeverity.INFO,
                    [str(circuit.id)],
                    recommendation="No deterministic schematic preflight issue was applicable.",
                )
            )
        return results

    def validate(self, schematic: SchematicIR, circuit: CircuitIR) -> ErcReport:
        self._assert_source(schematic, circuit)
        preflight = self.preflight(circuit)
        return self._preflight_report(schematic, preflight)

    def import_erc(
        self,
        schematic: SchematicIR,
        circuit: CircuitIR,
        *,
        status: str,
        tool_name: str,
        tool_version: str,
        issues: Sequence[ErcIssue] = (),
        evidence_ids: Sequence[UUID] = (),
    ) -> ErcReport:
        self._assert_source(schematic, circuit)
        if status not in {"PASS", "FAIL"}:
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR,
                "Imported ERC status must be PASS or FAIL",
                details={"status": status},
            )
        if not tool_name.strip() or not tool_version.strip():
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR,
                "Imported ERC results require tool name and version",
            )
        return ErcReport(
            project_id=schematic.project_id,
            schematic_id=schematic.id,
            schematic_revision=schematic.revision,
            circuit_id=circuit.id,
            circuit_revision=circuit.revision,
            status=status,  # type: ignore[arg-type]
            tool_name=tool_name,
            tool_version=tool_version,
            executed=True,
            issues=list(issues),
            source_revision_snapshot=self._source_snapshot(schematic, circuit),
            evidence_ids=_unique(evidence_ids),
            recommendation=(
                "Review imported ERC failures before release."
                if status == "FAIL"
                else "ERC passed for the imported tool result."
            ),
        )

    @staticmethod
    def _assert_source(schematic: SchematicIR, circuit: CircuitIR) -> None:
        if (
            schematic.circuit_id != circuit.id
            or schematic.circuit_revision != circuit.revision
            or schematic.hardware_ir_id != circuit.hardware_ir_id
            or schematic.hardware_ir_revision != circuit.hardware_ir_revision
        ):
            raise EngineeringError(
                EngineeringErrorCode.INVALID_REQUIREMENT,
                "Schematic source revision does not match the selected CircuitIR",
                details={"reason": "SOURCE_REVISION_MISMATCH"},
            )

    def _preflight_report(self, schematic: SchematicIR, results: Sequence[RuleResult]) -> ErcReport:
        failures = [result for result in results if result.status == "FAIL"]
        issues = [
            ErcIssue(
                code=result.rule_id,
                title=result.rule_id,
                description=result.recommendation,
                severity=result.severity,
                affected_refs=result.affected_refs,
                evidence_ids=result.evidence_ids,
            )
            for result in results
            if result.status in {"FAIL", "UNKNOWN"}
        ]
        tool_available = shutil.which("kicad-cli") is not None
        status = "FAIL" if failures else "UNKNOWN"
        recommendation = (
            "Resolve deterministic schematic preflight failures before ERC."
            if failures
            else "KiCad ERC execution is unavailable; this report is not ERC verified."
        )
        if tool_available and not failures:
            recommendation = "KiCad is installed but the M10 execution adapter is not configured."
        return ErcReport(
            project_id=schematic.project_id,
            schematic_id=schematic.id,
            schematic_revision=schematic.revision,
            circuit_id=schematic.circuit_id,
            circuit_revision=schematic.circuit_revision,
            status=status,  # type: ignore[arg-type]
            tool_name="kicad-cli" if tool_available else None,
            executed=False,
            issues=issues,
            source_revision_snapshot={
                "schematic_id": str(schematic.id),
                "schematic_revision": schematic.revision,
                "circuit_id": str(schematic.circuit_id),
                "circuit_revision": schematic.circuit_revision,
                "hardware_ir_id": str(schematic.hardware_ir_id),
                "hardware_ir_revision": schematic.hardware_ir_revision,
            },
            evidence_ids=list(schematic.evidence_ids),
            recommendation=recommendation,
        )

    @staticmethod
    def _source_snapshot(schematic: SchematicIR, circuit: CircuitIR) -> dict[str, object]:
        return {
            "circuit_id": str(circuit.id),
            "circuit_revision": circuit.revision,
            "hardware_ir_id": str(circuit.hardware_ir_id),
            "hardware_ir_revision": circuit.hardware_ir_revision,
            "schematic_id": str(schematic.id),
            "schematic_revision": schematic.revision,
        }

    @staticmethod
    def _netlist_text(circuit: CircuitIR) -> str:
        lines = [
            "EEA-NETLIST-V1",
            f"SOURCE|circuit={circuit.id}|revision={circuit.revision}",
            f"SOURCE|hardware_ir={circuit.hardware_ir_id}|revision={circuit.hardware_ir_revision}",
        ]
        for component in sorted(
            circuit.components, key=lambda item: (item.reference, str(item.id))
        ):
            lines.append(
                "COMPONENT|"
                + json.dumps(
                    {
                        "id": str(component.id),
                        "reference": component.reference,
                        "kind": component.kind,
                        "device_ref": component.device_ref,
                        "package": component.package,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        for net in sorted(circuit.nets, key=lambda item: (item.name, str(item.id))):
            endpoints = sorted(
                net.endpoints,
                key=lambda item: (item.component_ref, item.pin_ref, str(item.pin_assignment_id)),
            )
            lines.append(
                "NET|"
                + json.dumps(
                    {
                        "id": str(net.id),
                        "name": net.name,
                        "signal_type": net.signal_type,
                        "voltage_domain": net.voltage_domain,
                        "criticality": net.criticality,
                        "endpoints": [endpoint.model_dump(mode="json") for endpoint in endpoints],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        for power_net in sorted(circuit.power_nets, key=lambda item: (item.name, str(item.id))):
            lines.append(
                "POWER_NET|"
                + json.dumps(
                    power_net.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
                )
            )
        return "\n".join(lines) + "\n"

    def _rule(
        self,
        circuit: CircuitIR,
        rule_id: str,
        status: str,
        severity: IssueSeverity,
        affected_refs: list[str],
        *,
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
            evidence_ids=list(circuit.evidence_ids),
            recommendation=recommendation,
            input_snapshot={"circuit_id": str(circuit.id)},
        )


__all__ = ["SchematicService"]
