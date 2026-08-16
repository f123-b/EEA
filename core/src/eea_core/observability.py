"""Structured correlation context and secret redaction for logs and telemetry."""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from typing import Any


@dataclass(frozen=True, slots=True)
class ObservabilityContext:
    request_id: str | None = None
    project_id: str | None = None
    job_id: str | None = None
    agent_run_id: str | None = None
    tool_run_id: str | None = None
    import_run_id: str | None = None
    commissioning_session_id: str | None = None
    event_id: str | None = None
    source_revision: str | None = None

    def as_dict(self) -> dict[str, str]:
        return {field.name: value for field in fields(self) if (value := getattr(self, field.name))}


_SECRET_KEY = re.compile(
    r"(?:bearer|authorization|api[_-]?key|secret|password|passwd|private[_-]?key|token|cookie|env)",
    re.I,
)
_SECRET_VALUE = re.compile(
    r"(?:bearer\s+[A-Za-z0-9._~+/=-]+|sk-[A-Za-z0-9_-]+|-----BEGIN [A-Z ]+PRIVATE KEY-----)",
    re.I,
)


def redact_sensitive(value: Any, *, key: str | None = None) -> Any:
    """Recursively redact secret-shaped keys and values before logging."""

    if key and _SECRET_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): redact_sensitive(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(redact_sensitive(item) for item in value)
    if isinstance(value, str):
        return _SECRET_VALUE.sub("[REDACTED]", value)
    return value


__all__ = ["ObservabilityContext", "redact_sensitive"]
