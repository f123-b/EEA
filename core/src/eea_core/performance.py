"""Versioned performance baselines without flaky absolute CI assertions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PerformanceMetric:
    name: str
    value_ms: float
    sample_count: int = 1


@dataclass(frozen=True, slots=True)
class PerformanceBaseline:
    version: str
    profile: str
    metrics: dict[str, PerformanceMetric]
    tolerance_ratio: float = 1.25

    def compare(self, current: dict[str, PerformanceMetric]) -> PerformanceRegressionResult:
        regressions: dict[str, tuple[float, float]] = {}
        for name, baseline in self.metrics.items():
            observed = current.get(name)
            if (
                observed is not None
                and observed.value_ms > baseline.value_ms * self.tolerance_ratio
            ):
                regressions[name] = (baseline.value_ms, observed.value_ms)
        return PerformanceRegressionResult(not regressions, regressions)


@dataclass(frozen=True, slots=True)
class PerformanceRegressionResult:
    passed: bool
    regressions: dict[str, tuple[float, float]]


__all__ = ["PerformanceBaseline", "PerformanceMetric", "PerformanceRegressionResult"]
