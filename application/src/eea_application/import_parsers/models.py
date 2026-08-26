"""Parser-backed, non-trusted import observations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ParserCandidate:
    """A normalized parser observation; it is never a trusted canonical fact."""

    candidate_type: str
    semantic_key: str
    proposed_value: dict[str, Any]
    confidence: float
    source_kind: str
    source_ref: str
    source_file: str
    source_location: dict[str, int]
    evidence: tuple[dict[str, Any], ...]
    parser_name: str
    parser_version: str
    status: str = "DETECTED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_type": self.candidate_type,
            "semantic_key": self.semantic_key,
            "proposed_value": self.proposed_value,
            "confidence": self.confidence,
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "source_file": self.source_file,
            "source_location": self.source_location,
            "evidence": list(self.evidence),
            "parser_name": self.parser_name,
            "parser_version": self.parser_version,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class ParserResult:
    parser_name: str
    parser_version: str
    status: str
    candidates: tuple[ParserCandidate, ...]
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "parser_name": self.parser_name,
            "parser_version": self.parser_version,
            "status": self.status,
            "candidates": [item.as_dict() for item in self.candidates],
            "warnings": list(self.warnings),
        }


def evidence(
    source_file: str,
    line: int,
    *,
    column: int = 1,
    excerpt: str | None = None,
) -> dict[str, Any]:
    return {
        "source_file": source_file,
        "source_location": {"line": line, "column": column},
        "excerpt": excerpt,
    }


__all__ = ["ParserCandidate", "ParserResult", "evidence"]
