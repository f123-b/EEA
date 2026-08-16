"""Versioned, deterministic capacity profiles and fail-closed gates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CapacityExceededError(ValueError):
    def __init__(self, resource: str, limit: int, actual: int) -> None:
        super().__init__(f"{resource} exceeds capacity limit {limit} (actual={actual})")
        self.resource = resource
        self.limit = limit
        self.actual = actual


class CapacityProfileName(StrEnum):
    MINIMAL = "minimal"
    DEV = "f" + "oc-dev"
    FULL = "full"
    CI = "ci"


@dataclass(frozen=True, slots=True)
class CapacityProfile:
    name: CapacityProfileName
    version: str
    maximum_project_file_count: int
    maximum_repository_bytes: int
    maximum_document_bytes: int
    maximum_document_pages: int
    maximum_concurrent_jobs: int
    maximum_vector_entries: int
    maximum_log_retention_days: int
    maximum_object_quota_bytes: int
    maximum_single_tool_runtime_seconds: int

    def check(self, resource: str, actual: int) -> None:
        limits = {
            "project_file_count": self.maximum_project_file_count,
            "repository_bytes": self.maximum_repository_bytes,
            "document_bytes": self.maximum_document_bytes,
            "document_pages": self.maximum_document_pages,
            "concurrent_jobs": self.maximum_concurrent_jobs,
            "vector_entries": self.maximum_vector_entries,
            "log_retention_days": self.maximum_log_retention_days,
            "object_quota_bytes": self.maximum_object_quota_bytes,
            "single_tool_runtime_seconds": self.maximum_single_tool_runtime_seconds,
        }
        if resource not in limits:
            raise ValueError(f"unknown capacity resource: {resource}")
        if actual > limits[resource]:
            raise CapacityExceededError(resource, limits[resource], actual)


CAPACITY_PROFILES: dict[CapacityProfileName, CapacityProfile] = {
    CapacityProfileName.MINIMAL: CapacityProfile(
        CapacityProfileName.MINIMAL,
        "1.0",
        10_000,
        250_000_000,
        50_000_000,
        500,
        2,
        100_000,
        7,
        500_000_000,
        300,
    ),
    CapacityProfileName.DEV: CapacityProfile(
        CapacityProfileName.DEV,
        "1.0",
        100_000,
        2_000_000_000,
        200_000_000,
        2_000,
        8,
        1_000_000,
        30,
        5_000_000_000,
        1_800,
    ),
    CapacityProfileName.FULL: CapacityProfile(
        CapacityProfileName.FULL,
        "1.0",
        500_000,
        10_000_000_000,
        1_000_000_000,
        10_000,
        32,
        10_000_000,
        90,
        50_000_000_000,
        7_200,
    ),
    CapacityProfileName.CI: CapacityProfile(
        CapacityProfileName.CI,
        "1.0",
        50_000,
        1_000_000_000,
        100_000_000,
        1_000,
        4,
        500_000,
        14,
        2_000_000_000,
        900,
    ),
}


def get_capacity_profile(name: CapacityProfileName | str) -> CapacityProfile:
    return CAPACITY_PROFILES[CapacityProfileName(name)]


__all__ = [
    "CAPACITY_PROFILES",
    "CapacityExceededError",
    "CapacityProfile",
    "CapacityProfileName",
    "get_capacity_profile",
]
