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
            input_file = workspace.path("m19-circuit.kicad_sch")
            input_file.write_text(self._modern_schematic(circuit), encoding="utf-8", newline="")
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
                erc_returncode=erc.returncode,
                erc_stdout=erc.stdout[:4000],
                erc_stderr=erc.stderr[:4000],
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
    def _modern_schematic(circuit: CircuitIR) -> str:
        """Generate a self-contained KiCad schematic with real passive pins."""

        uuid_index = 0

        def make_uuid() -> str:
            nonlocal uuid_index
            uuid_index += 1
            return f"00000000-0000-4000-8000-{uuid_index:012x}"

        def mm(mils: int | float) -> str:
            value = float(mils) * 0.0254
            return f"{value:.4f}".rstrip("0").rstrip(".")

        lines = [
            "(kicad_sch (version 20210621) (generator eeschema)",
            f'  (uuid "{make_uuid()}")',
            '  (paper "A4")',
            "  (title_block",
            '    (title "EEA M19 CircuitIR ERC Gate")',
            '    (comment 1 "Generated from persisted CircuitIR; no hardware execution")',
            "  )",
            "  (lib_symbols",
            '    (symbol "PORT"',
            "      (pin_numbers hide)",
            "      (pin_names (offset 0.762))",
            "      (in_bom yes)",
            "      (on_board yes)",
            '      (property "Reference" "J" (id 0) (at 0 2.54 0)',
            "        (effects (font (size 1.27 1.27)))",
            "      )",
            '      (property "Value" "PORT" (id 1) (at 0 -2.54 0)',
            "        (effects (font (size 1.27 1.27)))",
            "      )",
            '      (property "Footprint" "" (id 2) (at 0 0 0)',
            "        (effects (font (size 1.27 1.27)) hide)",
            "      )",
            '      (property "Datasheet" "~" (id 3) (at 0 0 0)',
            "        (effects (font (size 1.27 1.27)) hide)",
            "      )",
            '      (symbol "PORT_0_1"',
            "        (rectangle (start -1.27 1.27) (end 1.27 -1.27)",
            "          (stroke (width 0) (type default))",
            "          (fill (type background))",
            "        )",
            "      )",
            '      (symbol "PORT_1_1"',
            "        (pin passive line (at -2.54 0 0) (length 2.54)",
            '          (name "P" (effects (font (size 1.27 1.27))))',
            '          (number "1" (effects (font (size 1.27 1.27))))',
            "        )",
            "      )",
            "    )",
            "  )",
        ]
        component_index = 1
        instance_records: list[tuple[str, str]] = []
        for net_index, net in enumerate(
            sorted(circuit.nets, key=lambda item: (item.name, str(item.id)))
        ):
            y_mils = 1800 + net_index * 650
            y = mm(y_mils)
            pin_positions: list[str] = []
            for endpoint_index, endpoint in enumerate(net.endpoints):
                x_mils = 2600 + endpoint_index * 1400
                x = mm(x_mils)
                pin_x = mm(x_mils - 100)
                symbol_uuid = make_uuid()
                pin_uuid = make_uuid()
                reference = f"J{component_index}"
                endpoint_label = f"{endpoint.component_ref}:{endpoint.pin_ref}"
                reference_property = (
                    f'    (property "Reference" "{reference}" (id 0) (at {x} {mm(y_mils + 105)} 0)'
                )
                value_property = (
                    f'    (property "Value" "{endpoint_label}" (id 1) (at {x} {mm(y_mils - 105)} 0)'
                )
                component_index += 1
                instance_records.append((symbol_uuid, reference))
                lines.extend(
                    [
                        f'  (symbol (lib_id "PORT") (at {x} {y} 0) (unit 1)',
                        "    (in_bom yes) (on_board yes) (fields_autoplaced)",
                        f'    (uuid "{symbol_uuid}")',
                        reference_property,
                        "      (effects (font (size 1.27 1.27)) (justify left))",
                        "    )",
                        value_property,
                        "      (effects (font (size 1.27 1.27)) (justify left))",
                        "    )",
                        f'    (property "Footprint" "" (id 2) (at {x} {y} 0)',
                        "      (effects (font (size 1.27 1.27)) hide)",
                        "    )",
                        f'    (property "Datasheet" "~" (id 3) (at {x} {y} 0)',
                        "      (effects (font (size 1.27 1.27)) hide)",
                        "    )",
                        f'    (pin "1" (uuid "{pin_uuid}"))',
                        "  )",
                    ]
                )
                pin_positions.append(pin_x)
            if len(pin_positions) > 1:
                wire_start = min(float(position) for position in pin_positions)
                wire_end = max(float(position) for position in pin_positions)
                wire_mid = (wire_start + wire_end) / 2
                wire_start_text = f"{wire_start:.4f}".rstrip("0").rstrip(".")
                wire_end_text = f"{wire_end:.4f}".rstrip("0").rstrip(".")
                wire_mid_text = f"{wire_mid:.4f}".rstrip("0").rstrip(".")
                lines.extend(
                    [
                        f"  (wire (pts (xy {wire_start_text} {y}) (xy {wire_mid_text} {y}))",
                        "    (stroke (width 0) (type solid) (color 0 0 0 0))",
                        f'    (uuid "{make_uuid()}")',
                        "  )",
                        f"  (wire (pts (xy {wire_mid_text} {y}) (xy {wire_end_text} {y}))",
                        "    (stroke (width 0) (type solid) (color 0 0 0 0))",
                        f'    (uuid "{make_uuid()}")',
                        "  )",
                        f"  (junction (at {wire_mid_text} {y}) (diameter 0) (color 0 0 0 0)",
                        f'    (uuid "{make_uuid()}")',
                        "  )",
                        f'  (text "NET: {net.name}" (exclude_from_sim no) '
                        f"(at {wire_mid_text} {mm(y_mils - 100)} 0)",
                        "    (effects (font (size 1.27 1.27)))",
                        f'    (uuid "{make_uuid()}")',
                        "  )",
                    ]
                )
        lines.extend(
            [
                "  (sheet_instances",
                '    (path "/" (page "1"))',
                "  )",
                "  (symbol_instances",
            ]
        )
        for symbol_uuid, reference in instance_records:
            lines.extend(
                [
                    f'    (path "/{symbol_uuid}"',
                    f'      (reference "{reference}") (unit 1) (value "PORT") (footprint "")',
                    "    )",
                ]
            )
        lines.extend(["  )", ")", ""])
        return "\n".join(lines)


__all__ = ["KiCadErcAdapter"]
