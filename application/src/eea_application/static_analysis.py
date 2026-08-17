"""Deterministic firmware static-analysis rules and tool orchestration."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid5

from eea_core.enums import IssueSeverity, StaticAnalysisStatus
from eea_core.firmware import FirmwareBundle
from eea_core.mcu_config import MCUConfigIR
from eea_core.pin_planner import RuleResult
from eea_core.static_analysis import FirmwareStaticAnalysis, StaticAnalysisToolResult
from eea_ports.cpp_syntax import CppSourceAnalyzer
from eea_ports.static_analysis import StaticAnalysisProvider

RULESET_VERSION = "m13.2"
_RULE_NAMESPACE = UUID("2c6f9026-6951-5c36-8c53-76522cb60b6e")
_SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp"}
_HAL_CALL_NAME = re.compile(r"^(?:HAL|LL)_[A-Za-z0-9_]+$")
_BLOCKING_CALL_NAMES = {
    "HAL_Delay",
    "osDelay",
    "vTaskDelay",
    "xQueueReceive",
    "xQueueSend",
    "xSemaphoreTake",
    "xSemaphoreGive",
    "taskENTER_CRITICAL",
    "portENTER_CRITICAL",
    "vTaskSuspend",
    "sleep",
}
_EXCLUDED_APP_SEGMENTS = {"components", "drivers", "bsp", "platform", "middleware"}


def _sha256_json(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class FirmwareStaticAnalysisService:
    """Evaluate the M13 firmware gates and an optional external tool."""

    def __init__(
        self,
        provider: StaticAnalysisProvider | None = None,
        syntax_analyzer: CppSourceAnalyzer | None = None,
    ) -> None:
        self._provider = provider
        if syntax_analyzer is None:
            from eea_adapters.static_analysis import TreeSitterCppSourceAnalyzer

            syntax_analyzer = TreeSitterCppSourceAnalyzer()
        self._syntax_analyzer = syntax_analyzer

    def analyze(
        self,
        bundle: FirmwareBundle,
        *,
        mcu_config: MCUConfigIR | None = None,
        build_input_snapshot_id: UUID | None = None,
        run_cppcheck: bool = True,
    ) -> FirmwareStaticAnalysis:
        input_hash = self._input_hash(bundle, mcu_config)
        results = [
            self._direct_hal_rule(bundle, input_hash),
            self._isr_blocking_rule(bundle, input_hash),
            self._dependency_cycle_rule(bundle, input_hash),
            self._mcu_mismatch_rule(bundle, input_hash, mcu_config),
        ]
        tools: list[StaticAnalysisToolResult] = []
        if run_cppcheck:
            if self._provider is None:
                tools.append(
                    StaticAnalysisToolResult(
                        tool_id="cppcheck",
                        version="UNCONFIGURED",
                        status=StaticAnalysisStatus.UNKNOWN,
                        diagnostics=["No Cppcheck provider is configured."],
                    )
                )
            else:
                with TemporaryDirectory(prefix="eea-m13-") as temporary:
                    files = tuple(
                        (item.path, item.content)
                        for item in sorted(bundle.files, key=lambda item: item.path)
                    )
                    tool = self._provider.analyze(files, Path(temporary))
                tools.append(StaticAnalysisToolResult.model_validate(tool))

        status = self._overall_status(results, tools)
        analysis_id = uuid5(_RULE_NAMESPACE, f"analysis:{bundle.firmware.id}:{input_hash}")
        return FirmwareStaticAnalysis(
            id=analysis_id,
            project_id=bundle.firmware.project_id,
            firmware_id=bundle.firmware.id,
            firmware_revision=bundle.firmware.revision,
            source_revision_id=bundle.source_revision.id,
            build_input_snapshot_id=build_input_snapshot_id,
            input_hash=input_hash,
            ruleset_version=RULESET_VERSION,
            status=status,
            rule_results=results,
            tool_results=tools,
        )

    @staticmethod
    def _input_hash(bundle: FirmwareBundle, mcu_config: MCUConfigIR | None) -> str:
        firmware = bundle.firmware
        stable_firmware = firmware.model_dump(
            mode="json",
            exclude={
                "id",
                "schema_version",
                "revision",
                "created_at",
                "updated_at",
                "metadata",
                "rule_results",
                "status",
            },
        )
        return _sha256_json(
            {
                "firmware_id": str(firmware.id),
                "firmware_revision": firmware.revision,
                "firmware": stable_firmware,
                "source_revision": {
                    "id": str(bundle.source_revision.id),
                    "revision": bundle.source_revision.revision,
                    "tree_hash": bundle.source_revision.tree_hash,
                    "source_manifest_hash": bundle.source_revision.source_manifest_hash,
                    "file_manifest": bundle.source_revision.file_manifest,
                },
                "files": [
                    {
                        "path": item.path,
                        "content_hash": item.content_hash,
                        "input_hash": item.input_hash,
                        "content": item.content,
                        "generated_owned": item.generated_owned,
                    }
                    for item in sorted(bundle.files, key=lambda item: item.path)
                ],
                "mcu_config": (
                    None
                    if mcu_config is None
                    else {
                        "id": str(mcu_config.id),
                        "revision": mcu_config.revision,
                        "hardware_ir_id": str(mcu_config.hardware_ir_id),
                        "hardware_ir_revision": mcu_config.hardware_ir_revision,
                        "circuit_id": str(mcu_config.circuit_id),
                        "circuit_revision": mcu_config.circuit_revision,
                        "schematic_id": str(mcu_config.schematic_id),
                        "schematic_revision": mcu_config.schematic_revision,
                    }
                ),
                "ruleset_version": RULESET_VERSION,
            }
        )

    @staticmethod
    def _overall_status(
        results: list[RuleResult], tools: list[StaticAnalysisToolResult]
    ) -> StaticAnalysisStatus:
        if any(item.status == "FAIL" for item in results) or any(
            item.status is StaticAnalysisStatus.FAIL for item in tools
        ):
            return StaticAnalysisStatus.FAIL
        if any(item.status == "UNKNOWN" for item in results) or any(
            item.status is StaticAnalysisStatus.UNKNOWN for item in tools
        ):
            return StaticAnalysisStatus.UNKNOWN
        if any(item.status == "PASS" for item in results) or any(
            item.status is StaticAnalysisStatus.PASS for item in tools
        ):
            return StaticAnalysisStatus.PASS
        return StaticAnalysisStatus.UNKNOWN

    @staticmethod
    def _rule(
        bundle: FirmwareBundle,
        input_hash: str,
        rule_id: str,
        status: str,
        severity: IssueSeverity,
        *,
        affected_refs: list[str] | None = None,
        measured: object | None = None,
        threshold: object | None = None,
        recommendation: str = "",
    ) -> RuleResult:
        return RuleResult(
            id=uuid5(_RULE_NAMESPACE, f"rule:{input_hash}:{rule_id}"),
            project_id=bundle.firmware.project_id,
            rule_id=rule_id,
            rule_version="1.0",
            stage="RELEASE_GATE",
            status=status,  # type: ignore[arg-type]
            severity=severity,
            affected_refs=affected_refs or [],
            measured=measured,
            threshold=threshold,
            recommendation=recommendation,
            input_snapshot={
                "analysis_input_hash": input_hash,
                "firmware_id": str(bundle.firmware.id),
                "firmware_revision": bundle.firmware.revision,
                "source_revision_id": str(bundle.source_revision.id),
                "source_manifest_hash": bundle.source_revision.source_manifest_hash,
                "ruleset_version": RULESET_VERSION,
                "rule_id": rule_id,
            },
        )

    def _direct_hal_rule(self, bundle: FirmwareBundle, input_hash: str) -> RuleResult:
        files = [item for item in bundle.files if self._is_source(item.path)]
        if not files:
            return self._rule(
                bundle,
                input_hash,
                "APP_DIRECT_HAL_CALL",
                "UNKNOWN",
                IssueSeverity.MEDIUM,
                recommendation="Provide a traceable C/C++ source snapshot before release gating.",
            )
        candidates = [item for item in files if self._is_app_owned(item.path, item.generated_owned)]
        if not candidates:
            return self._rule(
                bundle,
                input_hash,
                "APP_DIRECT_HAL_CALL",
                "NOT_APPLICABLE",
                IssueSeverity.INFO,
                recommendation="No application-owned C/C++ source was present in this snapshot.",
            )
        analyses = [self._syntax_analyzer.analyze(item.path, item.content) for item in candidates]
        uncertain = [
            f"{analysis.path}:parser:{diagnostic}"
            for analysis in analyses
            if not analysis.parse_ok
            for diagnostic in analysis.diagnostics
        ]
        if uncertain:
            return self._rule(
                bundle,
                input_hash,
                "APP_DIRECT_HAL_CALL",
                "UNKNOWN",
                IssueSeverity.MEDIUM,
                affected_refs=sorted(uncertain),
                recommendation="Resolve C/C++ syntax-parser uncertainty before release gating.",
            )
        findings = sorted(
            f"{analysis.path}:{call.line}"
            for analysis in analyses
            for call in analysis.calls
            if _HAL_CALL_NAME.fullmatch(call.name)
        )
        if findings:
            return self._rule(
                bundle,
                input_hash,
                "APP_DIRECT_HAL_CALL",
                "FAIL",
                IssueSeverity.HIGH,
                affected_refs=sorted(findings),
                measured=len(findings),
                threshold=0,
                recommendation=(
                    "Route HAL/LL access through the generated driver or platform adapter."
                ),
            )
        return self._rule(
            bundle,
            input_hash,
            "APP_DIRECT_HAL_CALL",
            "PASS",
            IssueSeverity.INFO,
            measured=0,
            threshold=0,
        )

    def _isr_blocking_rule(self, bundle: FirmwareBundle, input_hash: str) -> RuleResult:
        files = [item for item in bundle.files if self._is_source(item.path)]
        if not files:
            return self._rule(
                bundle,
                input_hash,
                "ISR_BLOCKING_API",
                "UNKNOWN",
                IssueSeverity.MEDIUM,
                recommendation="Provide a traceable C/C++ source snapshot before ISR gating.",
            )
        analyses = [self._syntax_analyzer.analyze(item.path, item.content) for item in files]
        uncertain = [
            f"{analysis.path}:parser:{diagnostic}"
            for analysis in analyses
            if not analysis.parse_ok
            for diagnostic in analysis.diagnostics
        ]
        if uncertain:
            return self._rule(
                bundle,
                input_hash,
                "ISR_BLOCKING_API",
                "UNKNOWN",
                IssueSeverity.MEDIUM,
                affected_refs=sorted(uncertain),
                recommendation="Resolve C/C++ syntax-parser uncertainty before ISR gating.",
            )
        configured = {item.handler for item in bundle.firmware.interrupts}
        discovered = configured | {
            function.name
            for analysis in analyses
            for function in analysis.functions
            if function.name.endswith("IRQHandler")
        }
        if not discovered:
            return self._rule(
                bundle,
                input_hash,
                "ISR_BLOCKING_API",
                "NOT_APPLICABLE",
                IssueSeverity.INFO,
                recommendation="No interrupt handler was declared or found in this snapshot.",
            )
        findings: list[str] = []
        missing: list[str] = []
        for handler in sorted(discovered):
            definitions = [
                (analysis.path, function)
                for analysis in analyses
                for function in analysis.functions
                if function.name == handler
            ]
            if not definitions:
                missing.append(handler)
                continue
            for path, function in definitions:
                for call in function.calls:
                    if call.name in _BLOCKING_CALL_NAMES:
                        findings.append(f"{path}:{call.line}:{handler}")
        if missing:
            return self._rule(
                bundle,
                input_hash,
                "ISR_BLOCKING_API",
                "UNKNOWN",
                IssueSeverity.MEDIUM,
                affected_refs=sorted(missing),
                recommendation="Resolve every declared ISR to a source definition before gating.",
            )
        if findings:
            return self._rule(
                bundle,
                input_hash,
                "ISR_BLOCKING_API",
                "FAIL",
                IssueSeverity.CRITICAL,
                affected_refs=sorted(findings),
                measured=len(findings),
                threshold=0,
                recommendation="Keep ISR handlers bounded and defer blocking work to a task.",
            )
        return self._rule(
            bundle,
            input_hash,
            "ISR_BLOCKING_API",
            "PASS",
            IssueSeverity.INFO,
            measured=0,
            threshold=0,
        )

    @classmethod
    def _dependency_cycle_rule(cls, bundle: FirmwareBundle, input_hash: str) -> RuleResult:
        modules = bundle.firmware.modules
        if not modules:
            return cls._rule(
                bundle,
                input_hash,
                "DRIVER_DEPENDENCY_CYCLE",
                "UNKNOWN",
                IssueSeverity.MEDIUM,
                recommendation=(
                    "Declare the firmware module dependency graph before release gating."
                ),
            )
        resource_names = {item.name for item in bundle.firmware.shared_resources}
        names = [item.name for item in modules] + sorted(resource_names)
        if len(names) != len(set(names)):
            return cls._rule(
                bundle,
                input_hash,
                "DRIVER_DEPENDENCY_CYCLE",
                "UNKNOWN",
                IssueSeverity.MEDIUM,
                affected_refs=sorted(names),
                recommendation="Give every firmware module a unique stable name.",
            )
        graph = {item.name: sorted(item.dependencies) for item in modules}
        graph.update({name: [] for name in resource_names})
        missing = sorted(
            {
                dependency
                for values in graph.values()
                for dependency in values
                if dependency not in graph
            }
        )
        if missing:
            return cls._rule(
                bundle,
                input_hash,
                "DRIVER_DEPENDENCY_CYCLE",
                "UNKNOWN",
                IssueSeverity.MEDIUM,
                affected_refs=missing,
                recommendation="Resolve every declared module dependency before cycle analysis.",
            )
        visiting: set[str] = set()
        visited: set[str] = set()
        cycle: list[str] = []

        def visit(name: str, path: list[str]) -> bool:
            if name in visiting:
                cycle.extend([*path[path.index(name) :], name])
                return True
            if name in visited:
                return False
            visiting.add(name)
            for dependency in graph[name]:
                if visit(dependency, [*path, dependency]):
                    return True
            visiting.remove(name)
            visited.add(name)
            return False

        has_cycle = any(visit(name, [name]) for name in sorted(graph))
        if has_cycle:
            return cls._rule(
                bundle,
                input_hash,
                "DRIVER_DEPENDENCY_CYCLE",
                "FAIL",
                IssueSeverity.HIGH,
                affected_refs=cycle,
                measured=len(cycle) - 1,
                threshold=0,
                recommendation="Break the module dependency cycle before release.",
            )
        return cls._rule(
            bundle,
            input_hash,
            "DRIVER_DEPENDENCY_CYCLE",
            "PASS",
            IssueSeverity.INFO,
            measured=0,
            threshold=0,
        )

    @classmethod
    def _mcu_mismatch_rule(
        cls,
        bundle: FirmwareBundle,
        input_hash: str,
        mcu_config: MCUConfigIR | None,
    ) -> RuleResult:
        if mcu_config is None:
            return cls._rule(
                bundle,
                input_hash,
                "MCUCONFIG_FIRMWARE_MISMATCH",
                "UNKNOWN",
                IssueSeverity.HIGH,
                recommendation="Provide the locked MCUConfigIR used to generate this firmware.",
            )
        firmware = bundle.firmware
        mismatches: list[str] = []
        comparisons = (
            ("mcu_config_id", firmware.mcu_config_id, mcu_config.id),
            ("mcu_config_revision", firmware.mcu_config_revision, mcu_config.revision),
            ("hardware_ir_id", firmware.hardware_ir_id, mcu_config.hardware_ir_id),
            (
                "hardware_ir_revision",
                firmware.hardware_ir_revision,
                mcu_config.hardware_ir_revision,
            ),
            ("circuit_id", firmware.circuit_id, mcu_config.circuit_id),
            ("circuit_revision", firmware.circuit_revision, mcu_config.circuit_revision),
            ("schematic_id", firmware.schematic_id, mcu_config.schematic_id),
            ("schematic_revision", firmware.schematic_revision, mcu_config.schematic_revision),
        )
        for name, firmware_value, config_value in comparisons:
            if firmware_value != config_value:
                mismatches.append(f"{name}:{firmware_value}!={config_value}")
        if mismatches:
            return cls._rule(
                bundle,
                input_hash,
                "MCUCONFIG_FIRMWARE_MISMATCH",
                "FAIL",
                IssueSeverity.HIGH,
                affected_refs=sorted(mismatches),
                measured=len(mismatches),
                threshold=0,
                recommendation="Regenerate firmware from the exact locked MCUConfigIR snapshot.",
            )
        return cls._rule(
            bundle,
            input_hash,
            "MCUCONFIG_FIRMWARE_MISMATCH",
            "PASS",
            IssueSeverity.INFO,
            measured=0,
            threshold=0,
        )

    @staticmethod
    def _is_source(path: str) -> bool:
        return Path(path).suffix.lower() in _SOURCE_SUFFIXES

    @staticmethod
    def _is_app_owned(path: str, generated_owned: bool) -> bool:
        if generated_owned:
            return False
        normalized = path.replace("\\", "/").lower()
        parts = set(normalized.split("/"))
        return not bool(parts & _EXCLUDED_APP_SEGMENTS) and "eea_firmware_config" not in normalized


__all__ = ["RULESET_VERSION", "FirmwareStaticAnalysisService"]
