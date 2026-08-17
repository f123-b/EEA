"""Headless KiCad ERC execution for generated CircuitIR schematics."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from eea_core.circuit import CircuitIR
from eea_core.entities import utc_now
from eea_core.enums import IssueSeverity
from eea_core.sandbox import CommandSpec, SandboxPolicy, SandboxWorkspace
from eea_core.schematic import ErcIssue, ErcReport, SchematicIR

from eea_adapters.sandbox import (
    StructuredCommandExecutor,
    release_tool_policy_network_access,
)


class KiCadErcAdapter:
    """Run KiCad's own ERC against a generated, topology-preserving schematic."""

    provider_id = "kicad-cli"

    def __init__(
        self,
        executor: StructuredCommandExecutor | None = None,
        *,
        evidence_root: Path | None = None,
    ) -> None:
        self._executor = executor or StructuredCommandExecutor()
        self._evidence_root = evidence_root

    def execute(
        self, schematic: SchematicIR, circuit: CircuitIR, workspace_root: Path
    ) -> ErcReport:
        executable = shutil.which(self.provider_id)
        if executable is None:
            return self._report(
                schematic,
                circuit,
                status="UNKNOWN",
                tool_version=None,
                executed=False,
                recommendation="KiCad CLI is not installed; ERC was not executed.",
            )

        workspace_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=workspace_root) as temporary:
            workspace = SandboxWorkspace.from_root(Path(temporary))
            legacy = workspace.path("m19-circuit.sch")
            legacy.write_text(self._legacy_schematic(circuit), encoding="utf-8", newline="")
            home = workspace.path("home")
            home.mkdir(parents=True, exist_ok=True)
            config_home = home / "config"
            cache_home = home / "cache"
            config_home.mkdir(parents=True, exist_ok=True)
            cache_home.mkdir(parents=True, exist_ok=True)
            policy = SandboxPolicy(
                allowed_executables=(executable,),
                max_processes=64,
                allowed_environment=(
                    "PATH",
                    "HOME",
                    "TEMP",
                    "TMP",
                    "XDG_CONFIG_HOME",
                    "XDG_CACHE_HOME",
                ),
                network_access=release_tool_policy_network_access(),
            )
            environment = {
                "TEMP": str(workspace.root),
                "TMP": str(workspace.root),
                "HOME": str(home),
                "XDG_CONFIG_HOME": str(config_home),
                "XDG_CACHE_HOME": str(cache_home),
            }
            version_result = self._executor.execute(
                CommandSpec(argv=(executable, "version"), environment=environment),
                workspace.root,
                policy,
            )
            version_output = version_result.stdout or version_result.stderr
            tool_version = next(
                (line.strip() for line in version_output.splitlines() if line.strip()),
                "UNKNOWN",
            )
            if version_result.returncode != 0:
                return self._report(
                    schematic,
                    circuit,
                    status="FAIL",
                    tool_version=tool_version,
                    executed=True,
                    recommendation=version_result.stderr or "KiCad version command failed.",
                )

            upgrade = self._executor.execute(
                CommandSpec(
                    argv=(executable, "sch", "upgrade", "--force", str(legacy)),
                    environment=environment,
                ),
                workspace.root,
                policy,
            )
            candidates = sorted(workspace.root.rglob("*.kicad_sch"))
            input_file = candidates[0] if candidates else legacy
            report_path = workspace.path("m19-erc.json")
            erc = self._executor.execute(
                CommandSpec(
                    argv=(
                        executable,
                        "sch",
                        "erc",
                        "--format",
                        "json",
                        "--output",
                        str(report_path),
                        "--severity-all",
                        "--exit-code-violations",
                        str(input_file),
                    ),
                    environment=environment,
                ),
                workspace.root,
                policy,
            )
            status = "PASS" if erc.returncode == 0 else "FAIL"
            recommendation = (
                "KiCad ERC passed for the generated CircuitIR topology."
                if status == "PASS"
                else erc.stderr or erc.stdout or "KiCad ERC reported violations."
            )
            issues = (
                []
                if status == "PASS"
                else [
                    ErcIssue(
                        code="KICAD_ERC_VIOLATION",
                        title="KiCad ERC reported a violation",
                        description=recommendation[:4000],
                        severity=IssueSeverity.HIGH,
                    )
                ]
            )
            if self._evidence_root is not None:
                self._evidence_root.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(input_file, self._evidence_root / input_file.name)
                if report_path.is_file():
                    shutil.copyfile(report_path, self._evidence_root / "m19-erc.json")
                else:
                    (self._evidence_root / "m19-erc.json").write_text(
                        erc.stderr or erc.stdout or "", encoding="utf-8"
                    )
            return self._report(
                schematic,
                circuit,
                status=status,
                tool_version=tool_version,
                executed=True,
                issues=issues,
                recommendation=recommendation,
                source_file=str(input_file),
                upgrade_returncode=upgrade.returncode,
            )

    @staticmethod
    def _report(
        schematic: SchematicIR,
        circuit: CircuitIR,
        *,
        status: str,
        tool_version: str | None,
        executed: bool,
        recommendation: str,
        issues: list[ErcIssue] | None = None,
        **snapshot: object,
    ) -> ErcReport:
        return ErcReport(
            project_id=schematic.project_id,
            schematic_id=schematic.id,
            schematic_revision=schematic.revision,
            circuit_id=circuit.id,
            circuit_revision=circuit.revision,
            status=status,  # type: ignore[arg-type]
            tool_name=KiCadErcAdapter.provider_id if tool_version else None,
            tool_version=tool_version,
            executed=executed,
            issues=issues or [],
            source_revision_snapshot={
                "schematic_id": str(schematic.id),
                "schematic_revision": schematic.revision,
                "circuit_id": str(circuit.id),
                "circuit_revision": circuit.revision,
                "schematic_content_hash": schematic.content_hash,
                **snapshot,
            },
            evidence_ids=list(schematic.evidence_ids),
            recommendation=recommendation,
            created_at=utc_now(),
            updated_at=utc_now(),
        )

    @staticmethod
    def _legacy_schematic(circuit: CircuitIR) -> str:
        lines = [
            "EESchema Schematic File Version 4",
            "LIBS:m19-circuit-cache",
            "EELAYER 29 0",
            "EELAYER END",
            "$Descr A4 11693 8268",
            "Sheet 1 1",
            'Title "EEA M19 CircuitIR ERC Gate"',
            'Comment1 "Generated from persisted CircuitIR; no hardware execution"',
            "$EndDescr",
        ]
        component_index = 1
        for net_index, net in enumerate(
            sorted(circuit.nets, key=lambda item: (item.name, str(item.id)))
        ):
            y = 1800 + net_index * 650
            pins: list[int] = []
            for endpoint_index, endpoint in enumerate(net.endpoints):
                x = 2600 + endpoint_index * 1400
                pins.append(x - 100)
                reference = f"J{component_index}"
                component_index += 1
                uid = f"{component_index:08X}"
                lines.extend(
                    [
                        "$Comp",
                        "L Connector_Generic:Conn_01x01 " + reference,
                        f"U 1 1 {uid}",
                        f"P {x} {y}",
                        f'F 0 "{reference}" H {x + 80} {y + 42} 50  0000 L CNN',
                        (
                            f'F 1 "{endpoint.component_ref}:{endpoint.pin_ref}" '
                            f"H {x + 80} {y - 49} 50  0000 L CNN"
                        ),
                        "	1    " + str(x) + " " + str(y),
                        "	1    0    0    -1",
                        "$EndComp",
                    ]
                )
            if pins:
                lines.extend(
                    [
                        "Wire Wire Line",
                        f"\t{min(pins)} {y} {max(pins) if len(pins) > 1 else pins[0] + 200} {y}",
                        f"Connection ~ {min(pins)} {y}",
                        f"Connection ~ {max(pins) if len(pins) > 1 else pins[0] + 200} {y}",
                    ]
                )
                # Legacy KiCad labels are anchored at their declared coordinate.  Keep
                # both ends explicitly connected so the upgraded schematic has no
                # dangling-label or unconnected-wire violations.
                wire_end = max(pins) if len(pins) > 1 else pins[0] + 200
                lines.extend(
                    [
                        f"Text Label {min(pins)} {y} 0    50   ~ 0",
                        net.name,
                        f"Text Label {wire_end} {y} 2    50   ~ 0",
                        net.name,
                    ]
                )
        lines.extend(
            [
                "Text Notes 1800 700 0    80   ~ 16",
                "EEA M19 CircuitIR -> KiCad ERC",
                "$EndSCHEMATC",
                "",
            ]
        )
        return "\n".join(lines)


__all__ = ["KiCadErcAdapter"]
