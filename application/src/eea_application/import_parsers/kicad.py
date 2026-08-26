"""Minimal structural KiCad S-expression parser.

This intentionally parses the file structure instead of treating a KiCad file
extension as proof of a HardwareIR.  Results stay candidate-scoped.
"""

from __future__ import annotations

from typing import Any

from .models import ParserCandidate, ParserResult, evidence

PARSER_NAME = "kicad-sexpr"
PARSER_VERSION = "1.0.0"


def _tokens(text: str) -> list[str]:
    result: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char == ";":
            newline = text.find("\n", index)
            index = len(text) if newline == -1 else newline + 1
            continue
        if char in "()":
            result.append(char)
            index += 1
            continue
        if char == '"':
            index += 1
            value: list[str] = []
            while index < len(text):
                if text[index] == "\\" and index + 1 < len(text):
                    value.append(text[index + 1])
                    index += 2
                elif text[index] == '"':
                    index += 1
                    break
                else:
                    value.append(text[index])
                    index += 1
            else:
                raise ValueError("unterminated KiCad string")
            result.append('"' + "".join(value) + '"')
            continue
        start = index
        while index < len(text) and not text[index].isspace() and text[index] not in "();":
            index += 1
        result.append(text[start:index])
    return result


def _unquote(value: object) -> str:
    text = str(value)
    return text[1:-1] if len(text) >= 2 and text[0] == '"' and text[-1] == '"' else text


def _parse(text: str) -> list[Any]:
    tokens = _tokens(text)
    index = 0

    def parse_node() -> Any:
        nonlocal index
        if index >= len(tokens) or tokens[index] != "(":
            raise ValueError("KiCad expression must start with '('")
        index += 1
        node: list[Any] = []
        while index < len(tokens) and tokens[index] != ")":
            if tokens[index] == "(":
                node.append(parse_node())
            else:
                node.append(tokens[index])
                index += 1
        if index >= len(tokens):
            raise ValueError("unbalanced KiCad expression")
        index += 1
        return node

    roots: list[Any] = []
    while index < len(tokens):
        roots.append(parse_node())
    return roots


def _walk(node: Any, tag: str) -> list[list[Any]]:
    found: list[list[Any]] = []
    if isinstance(node, list):
        if node and node[0] == tag:
            found.append(node)
        for child in node:
            found.extend(_walk(child, tag))
    return found


def _first(node: list[Any], tag: str) -> list[Any] | None:
    return next(
        (child for child in node[1:] if isinstance(child, list) and child and child[0] == tag),
        None,
    )


def _property_map(node: list[Any]) -> dict[str, str]:
    properties: dict[str, str] = {}
    for item in _walk(node, "property"):
        if len(item) >= 3:
            properties[_unquote(item[1])] = _unquote(item[2])
    return properties


def _component_kind(reference: str, value: str, lib_id: str) -> str:
    text = f"{reference} {value} {lib_id}".upper()
    if "MCU" in text or "STM32" in text or "ESP32" in text:
        return "MCU"
    if "CONNECTOR" in text or reference.upper().startswith(("J", "CON")):
        return "CONNECTOR"
    if "DRIVER" in text or "DRV" in text or (reference.upper().startswith("U") and "MOTOR" in text):
        return "DRIVER_IC"
    if "SENSOR" in text or reference.upper().startswith(("B", "S")):
        return "SENSOR_IC"
    return "COMPONENT"


def _candidate(
    *,
    semantic_key: str,
    value: dict[str, Any],
    source_file: str,
    status: str = "DETECTED",
    confidence: float = 0.9,
) -> ParserCandidate:
    item_evidence = (evidence(source_file, 1, excerpt="KiCad structural parse"),)
    return ParserCandidate(
        candidate_type="HARDWARE",
        semantic_key=semantic_key,
        proposed_value=value,
        confidence=confidence,
        source_kind="KICAD_SEXPR",
        source_ref=source_file,
        source_file=source_file,
        source_location={"line": 1, "column": 1},
        evidence=item_evidence,
        parser_name=PARSER_NAME,
        parser_version=PARSER_VERSION,
        status=status,
    )


def parse_kicad(text: str, *, source_file: str) -> ParserResult:
    try:
        roots = _parse(text)
    except ValueError as error:
        return ParserResult(
            PARSER_NAME,
            PARSER_VERSION,
            "UNKNOWN",
            (
                _candidate(
                    semantic_key="kicad.parse",
                    value={"status": "UNKNOWN", "reason": str(error)},
                    source_file=source_file,
                    status="UNKNOWN",
                    confidence=0.0,
                ),
            ),
            (str(error),),
        )

    root = roots[0] if roots else []
    symbols: list[dict[str, Any]] = []
    power_symbols: list[dict[str, Any]] = []
    for symbol in _walk(root, "symbol"):
        props = _property_map(symbol)
        lib_id = _first(symbol, "lib_id")
        reference = props.get("Reference", "UNKNOWN")
        value = props.get("Value", "UNKNOWN")
        lib_name = _unquote(lib_id[1]) if lib_id and len(lib_id) > 1 else "UNKNOWN"
        if props.get("Reference", "").startswith("#"):
            power_symbols.append({"reference": reference, "value": value, "lib_id": lib_name})
            continue
        symbols.append(
            {
                "reference": reference,
                "value": value,
                "footprint": props.get("Footprint"),
                "lib_id": lib_name,
                "kind": _component_kind(reference, value, lib_name),
            }
        )

    nets = []
    for net in _walk(root, "net"):
        if len(net) >= 3:
            nets.append({"number": _unquote(net[1]), "name": _unquote(net[2])})
    labels: list[dict[str, str]] = []
    for tag in ("label", "global_label", "hierarchical_label"):
        labels.extend(
            {"kind": tag, "name": _unquote(item[1])} for item in _walk(root, tag) if len(item) >= 2
        )

    footprints: list[dict[str, Any]] = []
    for footprint in _walk(root, "footprint"):
        layer = _first(footprint, "layer")
        pads = []
        for pad in _walk(footprint, "pad"):
            if len(pad) >= 2:
                pads.append(
                    {
                        "number": _unquote(pad[1]),
                        "kind": _unquote(pad[2]) if len(pad) > 2 else "UNKNOWN",
                    }
                )
        footprints.append(
            {
                "name": _unquote(footprint[1]) if len(footprint) > 1 else "UNKNOWN",
                "layer": _unquote(layer[1]) if layer and len(layer) > 1 else "UNKNOWN",
                "pads": pads,
            }
        )

    candidates: list[ParserCandidate] = [
        _candidate(
            semantic_key=f"kicad.symbol:{item['reference']}",
            value=item,
            source_file=source_file,
        )
        for item in sorted(symbols, key=lambda item: str(item["reference"]))
    ]
    candidates.extend(
        _candidate(semantic_key=f"kicad.net:{item['number']}", value=item, source_file=source_file)
        for item in sorted(nets, key=lambda item: str(item["number"]))
    )
    candidates.extend(
        _candidate(
            semantic_key=f"kicad.footprint:{item['name']}",
            value=item,
            source_file=source_file,
        )
        for item in sorted(footprints, key=lambda item: str(item["name"]))
    )
    candidates.append(
        _candidate(
            semantic_key="kicad.summary",
            value={
                "format": root[0] if root else "UNKNOWN",
                "symbols": symbols,
                "nets": nets,
                "labels": labels,
                "power_symbols": power_symbols,
                "footprints": footprints,
                "status": "DETECTED" if symbols or nets or footprints or labels else "UNKNOWN",
            },
            source_file=source_file,
            confidence=0.85 if symbols or nets or footprints or labels else 0.0,
            status="DETECTED" if symbols or nets or footprints or labels else "UNKNOWN",
        )
    )
    return ParserResult(
        PARSER_NAME,
        PARSER_VERSION,
        "PASS" if candidates[-1].status == "DETECTED" else "UNKNOWN",
        tuple(candidates),
    )


__all__ = ["PARSER_NAME", "PARSER_VERSION", "parse_kicad"]
