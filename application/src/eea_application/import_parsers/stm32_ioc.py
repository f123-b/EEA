"""Small deterministic STM32CubeMX .ioc parser.

The .ioc format is a line-oriented key/value format.  The parser keeps values
explicitly typed where the format is unambiguous and leaves unknown values
visible instead of inferring them.
"""

from __future__ import annotations

import re
from typing import Any

from .models import ParserCandidate, ParserResult, evidence

PARSER_NAME = "stm32-cubemx-ioc"
PARSER_VERSION = "1.0.0"
_PIN_RE = re.compile(r"^P[A-Z]\d{1,2}$", re.IGNORECASE)
_MCU_RE = re.compile(r"^(STM32[A-Z])(\d+)", re.IGNORECASE)
_PERIPHERAL_RE = re.compile(r"^(ADC|TIM|UART|USART|SPI|I2C|CAN|FDCAN|DMA)\w*", re.I)


def _value(raw: str) -> Any:
    value = raw.strip()
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        return int(value, 0)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def _candidate(
    *,
    candidate_type: str,
    semantic_key: str,
    proposed_value: dict[str, Any],
    source_file: str,
    line: int,
    excerpt: str,
    confidence: float = 0.95,
    status: str = "DETECTED",
) -> ParserCandidate:
    item_evidence = (evidence(source_file, line, excerpt=excerpt),)
    return ParserCandidate(
        candidate_type=candidate_type,
        semantic_key=semantic_key,
        proposed_value=proposed_value,
        confidence=confidence,
        source_kind="STM32CUBEMX_IOC",
        source_ref=source_file,
        source_file=source_file,
        source_location={"line": line, "column": 1},
        evidence=item_evidence,
        parser_name=PARSER_NAME,
        parser_version=PARSER_VERSION,
        status=status,
    )


def parse_ioc(text: str, *, source_file: str) -> ParserResult:
    properties: dict[str, tuple[Any, int, str]] = {}
    warnings: list[str] = []
    malformed: list[ParserCandidate] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if "=" not in line:
            malformed.append(
                _candidate(
                    candidate_type="MCU_CONFIG",
                    semantic_key=f"ioc.malformed:{line_number}",
                    proposed_value={"status": "UNKNOWN", "raw": line},
                    source_file=source_file,
                    line=line_number,
                    excerpt=raw_line[:500],
                    confidence=0.0,
                    status="UNKNOWN",
                )
            )
            warnings.append(f"line {line_number}: expected key=value")
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            warnings.append(f"line {line_number}: empty key")
            continue
        properties[key] = (_value(raw_value), line_number, raw_line[:500])

    candidates: list[ParserCandidate] = list(malformed)
    mcu_name = properties.get("Mcu.Name")
    mcu_value = str(mcu_name[0]) if mcu_name else "UNKNOWN"
    if mcu_name is None:
        warnings.append("Mcu.Name is missing")
        candidates.append(
            _candidate(
                candidate_type="MCU_CONFIG",
                semantic_key="ioc.mcu",
                proposed_value={"part_number": "UNKNOWN", "status": "UNKNOWN"},
                source_file=source_file,
                line=1,
                excerpt="Mcu.Name is missing",
                confidence=0.0,
                status="UNKNOWN",
            )
        )
    else:
        family_match = _MCU_RE.match(mcu_value)
        mcu = {
            "part_number": mcu_value,
            "family": family_match.group(1).upper() if family_match else "UNKNOWN",
            "package": properties.get("Mcu.Package", ("UNKNOWN", 0, ""))[0],
            "core": properties.get("Mcu.Core", ("UNKNOWN", 0, ""))[0],
            "status": "DETECTED",
        }
        mcu_line, mcu_excerpt = mcu_name[1], mcu_name[2]
        candidates.append(
            _candidate(
                candidate_type="MCU_CONFIG",
                semantic_key="ioc.mcu",
                proposed_value=mcu,
                source_file=source_file,
                line=int(mcu_line),
                excerpt=str(mcu_excerpt),
            )
        )

    clocks: dict[str, Any] = {}
    pins: list[dict[str, Any]] = []
    peripherals: dict[str, dict[str, Any]] = {}
    dma: list[dict[str, Any]] = []
    for key, (value, property_line, _excerpt) in sorted(properties.items()):
        if key.startswith("RCC.") and key.endswith("Freq_Value"):
            clocks[key.removeprefix("RCC.").removesuffix("Freq_Value").lower()] = value
        parts = key.split(".")
        if parts and _PIN_RE.fullmatch(parts[0]):
            pin = next((item for item in pins if item["pin"] == parts[0].upper()), None)
            if pin is None:
                pin = {"pin": parts[0].upper()}
                pins.append(pin)
            pin[parts[-1].lower()] = value
        if parts and _PERIPHERAL_RE.match(parts[0]):
            instance = parts[0].upper()
            entry = peripherals.setdefault(instance, {"instance": instance})
            entry[".".join(parts[1:]).lower() or "value"] = value
        if parts and parts[0].upper().startswith("DMA"):
            dma.append({"key": key, "value": value, "line": property_line})

    for pin in sorted(pins, key=lambda item: str(item["pin"])):
        pin_line = next(
            (value[1] for key, value in properties.items() if key.startswith(f"{pin['pin']}.")),
            1,
        )
        candidates.append(
            _candidate(
                candidate_type="MCU_CONFIG",
                semantic_key=f"ioc.pin:{pin['pin']}",
                proposed_value=pin,
                source_file=source_file,
                line=int(pin_line),
                excerpt=f"{pin['pin']} structured configuration",
            )
        )

    for instance, value in sorted(peripherals.items()):
        peripheral_line = next(
            (item[1] for key, item in properties.items() if key.upper().startswith(f"{instance}.")),
            1,
        )
        candidates.append(
            _candidate(
                candidate_type="MCU_CONFIG",
                semantic_key=f"ioc.peripheral:{instance}",
                proposed_value=value,
                source_file=source_file,
                line=int(peripheral_line),
                excerpt=f"{instance} structured configuration",
            )
        )

    aggregate_status = "UNKNOWN" if bool(malformed) or mcu_name is None else "DETECTED"
    aggregate = {
        "mcu": mcu_value,
        "clocks": clocks,
        "pins": sorted(pins, key=lambda item: str(item["pin"])),
        "peripherals": [peripherals[key] for key in sorted(peripherals)],
        "dma": sorted(dma, key=lambda item: (str(item["key"]), int(item["line"]))),
        "status": aggregate_status,
    }
    candidates.append(
        _candidate(
            candidate_type="MCU_CONFIG",
            semantic_key="ioc.configuration",
            proposed_value=aggregate,
            source_file=source_file,
            line=1,
            excerpt="STM32CubeMX structured configuration",
            confidence=0.9 if aggregate_status == "DETECTED" else 0.0,
            status=aggregate_status,
        )
    )
    return ParserResult(
        parser_name=PARSER_NAME,
        parser_version=PARSER_VERSION,
        status="UNKNOWN" if warnings and not mcu_name else "PASS",
        candidates=tuple(candidates),
        warnings=tuple(warnings),
    )


__all__ = ["PARSER_NAME", "PARSER_VERSION", "parse_ioc"]
