"""Framework-free ports for sandbox materialization and command execution."""

from pathlib import Path
from typing import Protocol


class ArchiveMaterializer(Protocol):
    name: str

    def extract(self, archive: Path, destination: Path, policy: object) -> object: ...


class CommandExecutor(Protocol):
    name: str

    def execute(self, spec: object, workspace: Path, policy: object) -> object: ...
