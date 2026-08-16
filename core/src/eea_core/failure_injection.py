"""Deterministic failure-injection contracts used by reliability tests."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FailureInjectionPoint(StrEnum):
    SQL_COMMIT = "sql.commit"
    OUTBOX_DISPATCH = "outbox.dispatch"
    SOURCE_OBJECT_WRITE = "source.object_write"
    ARTIFACT_OBJECT_WRITE = "artifact.object_write"
    SANDBOX_EXECUTION = "sandbox.execution"
    DESKTOP_BACKEND_CONNECT = "desktop.backend_connect"
    VECTOR_QUERY = "vector.query"
    LLM_REQUEST = "llm.request"
    TOOL_EXECUTION = "tool.execution"
    WEBSOCKET_REPLAY = "websocket.replay"


class FailureScenario(StrEnum):
    PROCESS_KILL = "process_kill"
    DB_LOCKED = "db_locked"
    DISK_FULL = "disk_full"
    OBJECT_WRITE_FAILURE = "object_write_failure"
    VECTOR_UNAVAILABLE = "vector_unavailable"
    LLM_TIMEOUT = "llm_timeout"
    LLM_RATE_LIMIT = "llm_rate_limit"
    TOOL_MISSING = "tool_missing"
    SANDBOX_CRASH = "sandbox_crash"
    CORRUPT_CACHE = "corrupt_cache"
    NETWORK_UNAVAILABLE = "network_unavailable"
    LOCK_HOLDER_CRASH = "lock_holder_crash"
    WS_DISCONNECT = "ws_disconnect"
    WS_REPLAY_FAILURE = "ws_replay_failure"


class FailureOutcome(StrEnum):
    RETRYABLE = "RETRYABLE"
    RECOVERABLE = "RECOVERABLE"
    FAILED_CLOSED = "FAILED_CLOSED"
    DEGRADED = "DEGRADED"


@dataclass(frozen=True, slots=True)
class FailurePlan:
    point: FailureInjectionPoint
    scenario: FailureScenario
    outcome: FailureOutcome
    message: str


class InjectedFailureError(RuntimeError):
    def __init__(self, plan: FailurePlan) -> None:
        super().__init__(plan.message)
        self.plan = plan


InjectedFailure = InjectedFailureError


class FailureInjectionHarness:
    """A one-shot deterministic plan; production code can receive a no-op instance."""

    def __init__(self, plans: tuple[FailurePlan, ...] = ()) -> None:
        self._plans = {plan.point: plan for plan in plans}

    def inject(self, point: FailureInjectionPoint) -> None:
        plan = self._plans.pop(point, None)
        if plan is not None:
            raise InjectedFailure(plan)

    def has_plan(self, point: FailureInjectionPoint) -> bool:
        return point in self._plans


def baseline_failure_plans() -> tuple[FailurePlan, ...]:
    """Return one deterministic representative plan for every release-gate scenario."""

    return (
        FailurePlan(
            FailureInjectionPoint.SQL_COMMIT,
            FailureScenario.DB_LOCKED,
            FailureOutcome.RETRYABLE,
            "database is locked",
        ),
        FailurePlan(
            FailureInjectionPoint.OUTBOX_DISPATCH,
            FailureScenario.PROCESS_KILL,
            FailureOutcome.RECOVERABLE,
            "dispatcher process stopped before acknowledgement",
        ),
        FailurePlan(
            FailureInjectionPoint.SOURCE_OBJECT_WRITE,
            FailureScenario.DISK_FULL,
            FailureOutcome.RECOVERABLE,
            "disk capacity exhausted",
        ),
        FailurePlan(
            FailureInjectionPoint.ARTIFACT_OBJECT_WRITE,
            FailureScenario.OBJECT_WRITE_FAILURE,
            FailureOutcome.RECOVERABLE,
            "object write failed",
        ),
        FailurePlan(
            FailureInjectionPoint.ARTIFACT_OBJECT_WRITE,
            FailureScenario.OBJECT_WRITE_FAILURE,
            FailureOutcome.RECOVERABLE,
            "object store rejected the write",
        ),
        FailurePlan(
            FailureInjectionPoint.SOURCE_OBJECT_WRITE,
            FailureScenario.LOCK_HOLDER_CRASH,
            FailureOutcome.RECOVERABLE,
            "source lock holder crashed",
        ),
        FailurePlan(
            FailureInjectionPoint.VECTOR_QUERY,
            FailureScenario.VECTOR_UNAVAILABLE,
            FailureOutcome.DEGRADED,
            "vector index unavailable",
        ),
        FailurePlan(
            FailureInjectionPoint.LLM_REQUEST,
            FailureScenario.LLM_TIMEOUT,
            FailureOutcome.RETRYABLE,
            "LLM request timed out",
        ),
        FailurePlan(
            FailureInjectionPoint.LLM_REQUEST,
            FailureScenario.LLM_RATE_LIMIT,
            FailureOutcome.RETRYABLE,
            "LLM request was rate limited",
        ),
        FailurePlan(
            FailureInjectionPoint.TOOL_EXECUTION,
            FailureScenario.TOOL_MISSING,
            FailureOutcome.FAILED_CLOSED,
            "tool is unavailable",
        ),
        FailurePlan(
            FailureInjectionPoint.SANDBOX_EXECUTION,
            FailureScenario.SANDBOX_CRASH,
            FailureOutcome.RECOVERABLE,
            "sandbox crashed",
        ),
        FailurePlan(
            FailureInjectionPoint.SANDBOX_EXECUTION,
            FailureScenario.CORRUPT_CACHE,
            FailureOutcome.RECOVERABLE,
            "sandbox cache failed integrity validation",
        ),
        FailurePlan(
            FailureInjectionPoint.DESKTOP_BACKEND_CONNECT,
            FailureScenario.NETWORK_UNAVAILABLE,
            FailureOutcome.RETRYABLE,
            "desktop backend connection is unavailable",
        ),
        FailurePlan(
            FailureInjectionPoint.WEBSOCKET_REPLAY,
            FailureScenario.WS_REPLAY_FAILURE,
            FailureOutcome.DEGRADED,
            "event replay requires resync",
        ),
        FailurePlan(
            FailureInjectionPoint.WEBSOCKET_REPLAY,
            FailureScenario.WS_DISCONNECT,
            FailureOutcome.DEGRADED,
            "websocket disconnected during replay",
        ),
    )


__all__ = [
    "FailureInjectionHarness",
    "FailureInjectionPoint",
    "FailureOutcome",
    "FailurePlan",
    "FailureScenario",
    "InjectedFailure",
    "baseline_failure_plans",
]
