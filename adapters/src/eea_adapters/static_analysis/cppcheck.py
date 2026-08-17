"""Offline, structured-command Cppcheck adapter."""

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from eea_core.enums import StaticAnalysisStatus
from eea_core.errors import EngineeringError
from eea_core.sandbox import CommandSpec, SandboxPolicy, SandboxWorkspace
from eea_core.static_analysis import StaticAnalysisToolResult

from eea_adapters.sandbox import (
    StructuredCommandExecutor,
    release_tool_policy_network_access,
)


class CppcheckAdapter:
    """Run Cppcheck inside the existing no-shell, no-network sandbox."""

    provider_id = "cppcheck"

    def __init__(self, executor: StructuredCommandExecutor | None = None) -> None:
        self._executor = executor or StructuredCommandExecutor()

    def analyze(
        self, files: tuple[tuple[str, str], ...], workspace: Path
    ) -> StaticAnalysisToolResult:
        executable = shutil.which("cppcheck")
        if executable is None:
            return StaticAnalysisToolResult(
                tool_id=self.provider_id,
                version="UNAVAILABLE",
                status=StaticAnalysisStatus.UNKNOWN,
                diagnostics=["Cppcheck executable is not installed."],
            )

        sandbox = SandboxWorkspace.from_root(workspace)
        for relative, content in sorted(files, key=lambda item: item[0]):
            target = sandbox.path(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="")
        policy = SandboxPolicy(
            allowed_executables=(executable,),
            network_access=release_tool_policy_network_access(),
        )
        environment = {"TEMP": str(sandbox.root), "TMP": str(sandbox.root)}
        try:
            version_result = self._executor.execute(
                CommandSpec(
                    argv=(executable, "--version"),
                    environment=environment,
                ),
                sandbox.root,
                policy,
            )
            if version_result.returncode != 0 or version_result.output_truncated:
                return self._unknown("Cppcheck version command did not complete cleanly.")
            version_output = version_result.stdout or version_result.stderr
            version = next(
                (line.strip() for line in version_output.splitlines() if line.strip()),
                "UNKNOWN",
            )
            result = self._executor.execute(
                CommandSpec(
                    argv=(
                        executable,
                        "--enable=warning,style,performance,portability",
                        "--inconclusive",
                        "--xml",
                        "--xml-version=2",
                        ".",
                    ),
                    environment=environment,
                ),
                sandbox.root,
                policy,
            )
        except EngineeringError as error:
            return self._unknown(f"Cppcheck execution unavailable: {error.message}")

        if result.output_truncated:
            return self._unknown("Cppcheck XML output was truncated by the sandbox.")
        xml_payload = result.stderr or result.stdout
        try:
            root = ET.fromstring(xml_payload)
        except (ET.ParseError, UnicodeError):
            return self._unknown("Cppcheck returned malformed or incomplete XML.")
        if root.tag != "results" or root.attrib.get("version") != "2":
            return self._unknown("Cppcheck XML root/schema is incomplete.")
        errors = root.find("errors")
        if errors is None or any(child.tag != "error" for child in errors):
            return self._unknown("Cppcheck XML diagnostics container is incomplete.")
        diagnostics = [
            ":".join(
                value
                for value in (
                    error.attrib.get("file", ""),
                    error.attrib.get("line", ""),
                    error.attrib.get("id", ""),
                    error.attrib.get("msg", ""),
                )
                if value
            )
            for error in errors
        ]
        if diagnostics:
            status = StaticAnalysisStatus.FAIL
        elif result.returncode != 0:
            return self._unknown("Cppcheck XML was clean but the tool exited abnormally.")
        else:
            status = StaticAnalysisStatus.PASS
        return StaticAnalysisToolResult(
            tool_id=self.provider_id,
            version=version,
            status=status,
            duration_ms=version_result.duration_ms + result.duration_ms,
            diagnostics=diagnostics,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def _unknown(self, diagnostic: str) -> StaticAnalysisToolResult:
        return StaticAnalysisToolResult(
            tool_id=self.provider_id,
            version="UNKNOWN",
            status=StaticAnalysisStatus.UNKNOWN,
            diagnostics=[diagnostic],
        )


__all__ = ["CppcheckAdapter"]
