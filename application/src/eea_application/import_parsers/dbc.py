"""Minimal real DBC message/signal parser with explicit UNKNOWN outcomes."""

from __future__ import annotations

import re
from typing import Any

from .models import ParserCandidate, ParserResult, evidence

PARSER_NAME = "can-dbc"
PARSER_VERSION = "1.0.0"
_WIRE_RE = re.compile(r"^(\d+)\|(\d+)@([01])([+-])$")
_VALUE_RE = re.compile(r"^\(([^,]+),([^\)]+)\)$")
_RANGE_RE = re.compile(r"^\[([^|]+)\|([^\]]+)\]$")


def _number(value: str) -> float | int:
    parsed = float(value)
    return int(parsed) if parsed.is_integer() else parsed


def _candidate(
    *,
    semantic_key: str,
    value: dict[str, Any],
    source_file: str,
    line: int,
    excerpt: str,
    status: str = "DETECTED",
    confidence: float = 0.95,
) -> ParserCandidate:
    return ParserCandidate(
        candidate_type="PROTOCOL",
        semantic_key=semantic_key,
        proposed_value=value,
        confidence=confidence,
        source_kind="DBC",
        source_ref=source_file,
        source_file=source_file,
        source_location={"line": line, "column": 1},
        evidence=(evidence(source_file, line, excerpt=excerpt),),
        parser_name=PARSER_NAME,
        parser_version=PARSER_VERSION,
        status=status,
    )


def parse_dbc(text: str, *, source_file: str) -> ParserResult:
    messages: dict[int, dict[str, Any]] = {}
    candidates: list[ParserCandidate] = []
    warnings: list[str] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("//") or line.startswith(";"):
            continue
        if line.startswith("BO_"):
            try:
                header, sender = line[3:].strip().split(":", 1)
                header_parts = header.split()
                sender_parts = sender.strip().split()
                can_id = int(header_parts[0], 0)
                name = header_parts[1]
                dlc = int(sender_parts[0])
                if can_id in messages:
                    raise ValueError("duplicate message id")
                messages[can_id] = {
                    "can_id": can_id & 0x1FFFFFFF,
                    "extended_id": bool(can_id & 0x80000000) or can_id > 0x7FF,
                    "name": name,
                    "payload_length_bytes": dlc,
                    "sender": " ".join(sender_parts[1:]),
                    "signals": [],
                    "line": line_number,
                }
            except (IndexError, ValueError) as error:
                warnings.append(f"line {line_number}: malformed message: {error}")
                candidates.append(
                    _candidate(
                        semantic_key=f"dbc.message:{line_number}",
                        value={"status": "UNKNOWN", "raw": line},
                        source_file=source_file,
                        line=line_number,
                        excerpt=raw_line[:500],
                        status="UNKNOWN",
                        confidence=0.0,
                    )
                )
            continue
        if line.startswith("SG_"):
            try:
                body = line[3:].strip()
                name, remainder = body.split(":", 1)
                tokens = remainder.strip().split()
                message = max(
                    (item for item in messages.values() if item["line"] < line_number),
                    key=lambda item: int(item["line"]),
                    default=None,
                )
                if message is None or len(tokens) < 5:
                    raise ValueError("signal has no preceding message")
                wire = _WIRE_RE.match(tokens[0])
                scale = _VALUE_RE.match(tokens[1])
                limits = _RANGE_RE.match(tokens[2])
                if wire is None or scale is None or limits is None:
                    raise ValueError("signal wire, scale, or range is malformed")
                signal = {
                    "name": name.strip(),
                    "start_bit": int(wire.group(1)),
                    "length": int(wire.group(2)),
                    "byte_order": (
                        "LITTLE_ENDIAN" if wire.group(3) == "1" else "MOTOROLA_BIG_ENDIAN"
                    ),
                    "signed": wire.group(4) == "-",
                    "factor": _number(scale.group(1)),
                    "offset": _number(scale.group(2)),
                    "minimum": _number(limits.group(1)),
                    "maximum": _number(limits.group(2)),
                    "unit": tokens[3].strip('"'),
                    "receiver": tokens[4:],
                    "line": line_number,
                }
                if any(item["name"] == signal["name"] for item in message["signals"]):
                    raise ValueError("duplicate signal name")
                message["signals"].append(signal)
            except (IndexError, ValueError) as error:
                warnings.append(f"line {line_number}: malformed signal: {error}")
                candidates.append(
                    _candidate(
                        semantic_key=f"dbc.signal:{line_number}",
                        value={"status": "UNKNOWN", "raw": line, "reason": str(error)},
                        source_file=source_file,
                        line=line_number,
                        excerpt=raw_line[:500],
                        status="UNKNOWN",
                        confidence=0.0,
                    )
                )

    for message in sorted(
        messages.values(), key=lambda item: (int(item["can_id"]), str(item["name"]))
    ):
        value = {key: item for key, item in message.items() if key != "line"}
        candidates.append(
            _candidate(
                semantic_key=f"dbc.message:{message['can_id']}",
                value=value,
                source_file=source_file,
                line=int(message["line"]),
                excerpt=f"BO_ {message['can_id']} {message['name']}",
            )
        )
    if not candidates:
        candidates.append(
            _candidate(
                semantic_key="dbc.document",
                value={"status": "UNKNOWN", "reason": "no BO_ or SG_ records"},
                source_file=source_file,
                line=1,
                excerpt="empty or unsupported DBC",
                status="UNKNOWN",
                confidence=0.0,
            )
        )
    return ParserResult(
        PARSER_NAME,
        PARSER_VERSION,
        "UNKNOWN" if warnings else "PASS",
        tuple(candidates),
        tuple(warnings),
    )


__all__ = ["PARSER_NAME", "PARSER_VERSION", "parse_dbc"]
