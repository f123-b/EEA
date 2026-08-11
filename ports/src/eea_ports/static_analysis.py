"""Framework-free port for firmware static-analysis providers."""

from pathlib import Path
from typing import Any, Protocol


class StaticAnalysisProvider(Protocol):
    provider_id: str

    def analyze(self, files: tuple[tuple[str, str], ...], workspace: Path) -> Any: ...


__all__ = ["StaticAnalysisProvider"]
