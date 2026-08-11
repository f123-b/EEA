"""Framework-free C/C++ syntax-analysis port contracts."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CppCall:
    """A call expression resolved from a C/C++ syntax tree."""

    name: str
    line: int


@dataclass(frozen=True, slots=True)
class CppFunction:
    """A function definition and its syntax-tree-resolved call expressions."""

    name: str
    line: int
    calls: tuple[CppCall, ...]


@dataclass(frozen=True, slots=True)
class CppSourceAnalysis:
    """Parser result; parse uncertainty is explicit and never a clean result."""

    path: str
    parse_ok: bool
    diagnostics: tuple[str, ...]
    calls: tuple[CppCall, ...]
    functions: tuple[CppFunction, ...]


class CppSourceAnalyzer(Protocol):
    """Syntax-tree provider used by deterministic firmware rules."""

    name: str

    def analyze(self, path: Path | str, source: str) -> CppSourceAnalysis: ...


__all__ = [
    "CppCall",
    "CppFunction",
    "CppSourceAnalysis",
    "CppSourceAnalyzer",
]
