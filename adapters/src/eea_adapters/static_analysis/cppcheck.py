"""Offline, structured-command Cppcheck adapter."""

import re
import shutil
from pathlib import Path

from eea_core.enums import StaticAnalysisStatus
from eea_core.errors import EngineeringError
from eea_core.sandbox import CommandSpec, SandboxPolicy, SandboxWorkspace
from eea_core.static_analysis import StaticAnalysisToolResult

from eea_adapters.sandbox import StructuredCommandExecutor


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
            network_access=False,
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
            version = version_result.stdout.splitlines()[0].strip() or "UNKNOWN"
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
            return StaticAnalysisToolResult(
                tool_id=self.provider_id,
                version="UNKNOWN",
                status=StaticAnalysisStatus.UNKNOWN,
                diagnostics=[f"Cppcheck execution unavailable: {error.message}"],
            )

        output = f"{result.stdout}\n{result.stderr}"
        failed = (
            result.returncode != 0
            or re.search(r"<error(?:\s|>)", output, re.IGNORECASE) is not None
        )
        return StaticAnalysisToolResult(
            tool_id=self.provider_id,
            version=version,
            status=StaticAnalysisStatus.FAIL if failed else StaticAnalysisStatus.PASS,
            duration_ms=version_result.duration_ms + result.duration_ms,
            diagnostics=(["Cppcheck reported one or more diagnostics."] if failed else []),
            stdout=result.stdout,
            stderr=result.stderr,
        )


__all__ = ["CppcheckAdapter"]
