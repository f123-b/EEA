"""Framework-free ports for sandbox materialization and command execution."""

from pathlib import Path
from typing import Any, Protocol


class ArchiveMaterializer(Protocol):
    name: str

    def extract(self, archive: Path, destination: Path, policy: object) -> object: ...


class CommandExecutor(Protocol):
    name: str

    def capabilities(self) -> Any: ...

    def execute(self, spec: object, workspace: Path, policy: object) -> Any: ...


class SandboxRuntime(CommandExecutor, Protocol):
    """Runtime boundary for OS-specific sandbox enforcement adapters."""
