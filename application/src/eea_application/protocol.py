"""Deterministic M16 ProtocolIR generators.

All targets are rendered from one validated ProtocolIR and carry the same
semantic input hash.  The generated Python and C codecs are standalone and do
not import EEA runtime modules.
"""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from typing import Final

from eea_core.protocol import (
    PROTOCOL_GENERATOR_VERSION,
    GeneratedProtocolOutput,
    ProtocolField,
    ProtocolGenerationBundle,
    ProtocolIR,
    ProtocolMessage,
    ProtocolTransport,
    ProtocolValidationResult,
    canonical_fields,
    canonical_messages,
    canonical_transports,
    field_wire_bits,
    validate_protocol,
)

_C_IDENTIFIER_RE: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9_]")
_C_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "auto",
        "break",
        "case",
        "char",
        "const",
        "continue",
        "default",
        "do",
        "double",
        "else",
        "enum",
        "extern",
        "float",
        "for",
        "goto",
        "if",
        "inline",
        "int",
        "long",
        "register",
        "restrict",
        "return",
        "short",
        "signed",
        "sizeof",
        "static",
        "struct",
        "switch",
        "typedef",
        "union",
        "unsigned",
        "void",
        "volatile",
        "while",
    }
)


class ProtocolGenerationError(ValueError):
    """Raised when a protocol cannot be safely rendered."""


def _identifier(value: str, *, fallback: str = "value") -> str:
    normalized = _C_IDENTIFIER_RE.sub("_", value).strip("_") or fallback
    if normalized[0].isdigit():
        normalized = f"_{normalized}"
    normalized = normalized.lower()
    if normalized in _C_KEYWORDS:
        normalized = f"eea_{normalized}"
    return normalized


class GeneratedIdentifierRegistry:
    """Stable, target-safe names shared by every M16 generator."""

    def __init__(self, protocol: ProtocolIR) -> None:
        self._message_names: dict[int, str] = {}
        self._field_names: dict[tuple[int, int], str] = {}
        message_used: set[str] = set()
        for message_index, message in enumerate(canonical_messages(protocol)):
            message_name = self._allocate(
                _identifier(message.name, fallback=f"message_{message_index}"),
                message_used,
            )
            self._message_names[id(message)] = message_name
            field_used: set[str] = set()
            for field_index, field in enumerate(canonical_fields(message)):
                field_name = self._allocate(
                    _identifier(field.name, fallback=f"field_{field_index}"),
                    field_used,
                )
                self._field_names[(id(message), id(field))] = field_name

    @staticmethod
    def _allocate(base: str, used: set[str]) -> str:
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base}_{suffix}"
            suffix += 1
        used.add(candidate)
        return candidate

    def message(self, message: ProtocolMessage) -> str:
        return self._message_names[id(message)]

    def field(self, message: ProtocolMessage, field: ProtocolField) -> str:
        return self._field_names[(id(message), id(field))]


def _header(protocol: ProtocolIR, target: str) -> str:
    return (
        f"/* EEA M16 ProtocolIR {target}; protocol_id={protocol.id}; "
        f"revision={protocol.revision}; input_hash={protocol.input_hash}; "
        f"generator={PROTOCOL_GENERATOR_VERSION} */"
    )


def _transport(protocol: ProtocolIR, message: ProtocolMessage) -> ProtocolTransport:
    for item in protocol.transports:
        if item.transport_id == message.transport_ref:
            return item
    raise ProtocolGenerationError(f"unresolved transport reference: {message.transport_ref}")


def _c_header(protocol: ProtocolIR, registry: GeneratedIdentifierRegistry) -> str:
    guard = "EEA_M16_PROTOCOL_H"
    lines = [
        _header(protocol, "C11"),
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        "#include <stdbool.h>",
        "#include <stddef.h>",
        "#include <stdint.h>",
        "",
        f'#define EEA_PROTOCOL_INPUT_HASH "{protocol.input_hash}"',
        f"#define EEA_PROTOCOL_REVISION {protocol.revision}u",
        "",
    ]
    for message in canonical_messages(protocol):
        message_id = registry.message(message)
        field_ids = [registry.field(message, field) for field in canonical_fields(message)]
        lines.extend([f"typedef struct eea_{message_id}_values {{"])
        if field_ids:
            for field_id in field_ids:
                lines.append(f"    double {field_id};")
        else:
            lines.append("    uint8_t eea_reserved;")
        lines.extend(
            [
                f"}} eea_{message_id}_values_t;",
                f"typedef struct eea_{message_id}_raw_values {{",
            ]
        )
        if field_ids:
            for field, field_id in zip(canonical_fields(message), field_ids, strict=True):
                lines.append(f"    {'int64_t' if field.signed else 'uint64_t'} {field_id};")
        else:
            lines.append("    uint8_t eea_reserved;")
        lines.extend(
            [
                f"}} eea_{message_id}_raw_values_t;",
                f"bool eea_{message_id}_encode(",
                f"    const eea_{message_id}_values_t *values,",
                "    uint8_t *payload,",
                "    size_t payload_length",
                ");",
                f"bool eea_{message_id}_decode(",
                "    const uint8_t *payload,",
                "    size_t payload_length,",
                f"    eea_{message_id}_values_t *values",
                ");",
                f"bool eea_{message_id}_encode_raw(",
                f"    const eea_{message_id}_raw_values_t *values,",
                "    uint8_t *payload,",
                "    size_t payload_length",
                ");",
                f"bool eea_{message_id}_decode_raw(",
                "    const uint8_t *payload,",
                "    size_t payload_length,",
                f"    eea_{message_id}_raw_values_t *values",
                ");",
                "",
            ]
        )
    lines.extend([f"#endif /* {guard} */", ""])
    return "\n".join(lines)


def _c_runtime_helpers() -> list[str]:
    return [
        "static uint64_t eea_mask(size_t width) {",
        "    return width >= 64u ? UINT64_MAX : ((UINT64_C(1) << width) - UINT64_C(1));",
        "}",
        "",
        "static uint64_t eea_read_raw(",
        "    const uint8_t *payload, size_t payload_length,",
        "    const size_t *bits, size_t width, bool *ok) {",
        "    uint64_t raw = UINT64_C(0);",
        "    if (width == 0u || width > 64u) { *ok = false; return 0u; }",
        "    for (size_t index = 0u; index < width; ++index) {",
        "        size_t bit = bits[index];",
        "        if (bit / 8u >= payload_length) { *ok = false; return 0u; }",
        "        if ((payload[bit / 8u] & (uint8_t)(UINT8_C(1) << (bit % 8u))) != 0u) {",
        "            raw |= UINT64_C(1) << index;",
        "        }",
        "    }",
        "    *ok = true;",
        "    return raw;",
        "}",
        "",
        "static bool eea_write_raw(",
        "    uint8_t *payload, size_t payload_length,",
        "    const size_t *bits, size_t width, uint64_t raw) {",
        "    if (width == 0u || width > 64u || (raw & ~eea_mask(width)) != 0u) { return false; }",
        "    for (size_t index = 0u; index < width; ++index) {",
        "        size_t bit = bits[index];",
        "        if (bit / 8u >= payload_length) { return false; }",
        "        uint8_t mask = (uint8_t)(UINT8_C(1) << (bit % 8u));",
        "        if ((raw & (UINT64_C(1) << index)) != 0u) { payload[bit / 8u] |= mask; }",
        "        else { payload[bit / 8u] &= (uint8_t)~mask; }",
        "    }",
        "    return true;",
        "}",
        "",
        "static bool eea_signed_to_raw(int64_t value, size_t width, uint64_t *raw) {",
        "    if (raw == NULL || width == 0u || width > 64u) { return false; }",
        "    if (width < 64u) {",
        "        int64_t minimum = -(INT64_C(1) << (width - 1u));",
        "        int64_t maximum = (INT64_C(1) << (width - 1u)) - 1;",
        "        if (value < minimum || value > maximum) { return false; }",
        "    }",
        (
            "    *raw = (value < 0 ? UINT64_MAX - (uint64_t)(-(value + 1)) "
            ": (uint64_t)value) & eea_mask(width);"
        ),
        "    return true;",
        "}",
        "",
        "static bool eea_raw_to_signed(uint64_t raw, size_t width, int64_t *value) {",
        "    if (value == NULL || width == 0u || width > 64u) { return false; }",
        "    raw &= eea_mask(width);",
        "    if ((raw & (UINT64_C(1) << (width - 1u))) == 0u) {",
        "        *value = (int64_t)raw;",
        "        return true;",
        "    }",
        "    uint64_t magnitude = ((~raw) & eea_mask(width)) + UINT64_C(1);",
        "    if (magnitude == (UINT64_C(1) << 63u)) {",
        "        *value = INT64_MIN;",
        "        return true;",
        "    }",
        "    *value = -(int64_t)magnitude;",
        "    return true;",
        "}",
        "",
        "static bool eea_encode_value(",
        "    double value, double scale, double offset, bool signed_value,",
        "    double minimum, bool has_minimum, double maximum, bool has_maximum,",
        "    size_t width, const size_t *bits, size_t bit_count,",
        "    uint8_t *payload, size_t payload_length) {",
        "    if (value != value || scale <= 0.0 || width != bit_count ||",
        "        width == 0u || width > 64u) {",
        "        return false;",
        "    }",
        "    if ((has_minimum && value < minimum) || (has_maximum && value > maximum)) {",
        "        return false;",
        "    }",
        "    double quantized = (value - offset) / scale;",
        "    if (quantized != quantized || quantized > 9007199254740992.0 ||",
        "        quantized < -9007199254740992.0) { return false; }",
        "    double rounded = quantized >= 0.0 ? quantized + 0.5 : quantized - 0.5;",
        "    if (rounded > 9007199254740992.0 || rounded < -9007199254740992.0) { return false; }",
        "    if (signed_value) {",
        "        int64_t signed_raw = (int64_t)rounded;",
        "        uint64_t raw = UINT64_C(0);",
        "        if (!eea_signed_to_raw(signed_raw, width, &raw)) { return false; }",
        "        return eea_write_raw(payload, payload_length, bits, width, raw);",
        "    }",
        "    if (rounded < 0.0) { return false; }",
        "    uint64_t raw = (uint64_t)rounded;",
        "    return eea_write_raw(payload, payload_length, bits, width, raw);",
        "}",
        "",
        "static bool eea_decode_value(",
        "    const uint8_t *payload, size_t payload_length, bool signed_value,",
        "    size_t width, const size_t *bits, size_t bit_count,",
        "    double scale, double offset, double *value) {",
        "    bool ok = false;",
        "    uint64_t raw = eea_read_raw(payload, payload_length, bits, width, &ok);",
        "    if (!ok || width != bit_count || scale <= 0.0 || value == NULL) { return false; }",
        "    if (signed_value) {",
        "        int64_t signed_raw = INT64_C(0);",
        "        if (!eea_raw_to_signed(raw, width, &signed_raw) ||",
        "            signed_raw > INT64_C(9007199254740992) ||",
        "            signed_raw < -INT64_C(9007199254740992)) { return false; }",
        "        *value = (double)signed_raw * scale + offset;",
        "    } else {",
        "        if (raw > UINT64_C(9007199254740992)) { return false; }",
        "        *value = (double)raw * scale + offset;",
        "    }",
        "    return true;",
        "}",
        "",
        "static bool eea_encode_raw_value(",
        "    uint8_t *payload, size_t payload_length, const size_t *bits,",
        "    size_t width, uint64_t raw) {",
        "    return eea_write_raw(payload, payload_length, bits, width, raw);",
        "}",
        "",
        "static bool eea_decode_raw_value(",
        "    const uint8_t *payload, size_t payload_length, const size_t *bits,",
        "    size_t width, uint64_t *raw) {",
        "    bool ok = false;",
        "    uint64_t value = eea_read_raw(payload, payload_length, bits, width, &ok);",
        "    if (!ok || raw == NULL) { return false; }",
        "    *raw = value;",
        "    return true;",
        "}",
        "",
    ]


def _c_source(protocol: ProtocolIR, registry: GeneratedIdentifierRegistry) -> str:
    lines = [_header(protocol, "C11"), '#include "protocol.h"', ""]
    if any(message.fields for message in protocol.messages):
        lines.extend(_c_runtime_helpers())
    for message in canonical_messages(protocol):
        message_id = registry.message(message)
        ordered_fields = canonical_fields(message)
        field_ids = [registry.field(message, field) for field in ordered_fields]
        bit_names: list[str] = []
        for index, field in enumerate(ordered_fields):
            bit_name = f"eea_{message_id}_field_{index}_bits"
            bit_names.append(bit_name)
            bits = ", ".join(str(bit) + "u" for bit in field_wire_bits(field))
            lines.extend(
                [
                    f"static const size_t {bit_name}[] = {{ {bits} }};",
                ]
            )
        lines.append("")
        lines.extend(
            [
                f"bool eea_{message_id}_encode(",
                f"    const eea_{message_id}_values_t *values,",
                "    uint8_t *payload,",
                "    size_t payload_length) {",
                "    if (values == NULL || payload == NULL ||",
                f"        payload_length != {message.payload_length_bytes}u) {{",
                "        return false;",
                "    }",
                f"    for (size_t index = 0u; index < {message.payload_length_bytes}u; ++index) {{",
                "        payload[index] = 0u;",
                "    }",
            ]
        )
        for _index, (field, field_id, bit_name) in enumerate(
            zip(ordered_fields, field_ids, bit_names, strict=True)
        ):
            minimum = field.minimum if field.minimum is not None else 0.0
            maximum = field.maximum if field.maximum is not None else 0.0
            lines.append(
                f"    if (!eea_encode_value(values->{field_id}, {field.scale!r}, {field.offset!r}, "
                f"{'true' if field.signed else 'false'}, {minimum!r}, "
                f"{'true' if field.minimum is not None else 'false'}, {maximum!r}, "
                f"{'true' if field.maximum is not None else 'false'}, {field.bit_length}u, "
                f"{bit_name}, {field.bit_length}u, payload, payload_length)) {{ return false; }}"
            )
        lines.extend(["    return true;", "}", ""])
        lines.extend(
            [
                f"bool eea_{message_id}_decode(",
                "    const uint8_t *payload,",
                "    size_t payload_length,",
                f"    eea_{message_id}_values_t *values) {{",
                "    if (payload == NULL || values == NULL ||",
                f"        payload_length != {message.payload_length_bytes}u) {{",
                "        return false;",
                "    }",
            ]
        )
        for field, field_id, bit_name in zip(ordered_fields, field_ids, bit_names, strict=True):
            lines.append(
                f"    if (!eea_decode_value(payload, payload_length, "
                f"{'true' if field.signed else 'false'}, {field.bit_length}u, {bit_name}, "
                f"{field.bit_length}u, {field.scale!r}, {field.offset!r}, "
                f"&values->{field_id})) {{ return false; }}"
            )
        lines.extend(["    return true;", "}", ""])
        lines.extend(
            [
                f"bool eea_{message_id}_encode_raw(",
                f"    const eea_{message_id}_raw_values_t *values,",
                "    uint8_t *payload,",
                "    size_t payload_length) {",
                "    if (values == NULL || payload == NULL ||",
                f"        payload_length != {message.payload_length_bytes}u) {{",
                "        return false;",
                "    }",
                f"    for (size_t index = 0u; index < {message.payload_length_bytes}u; ++index) {{",
                "        payload[index] = 0u;",
                "    }",
            ]
        )
        for field, field_id, bit_name in zip(ordered_fields, field_ids, bit_names, strict=True):
            if field.signed:
                lines.extend(
                    [
                        "    {",
                        "        uint64_t raw = UINT64_C(0);",
                        (
                            f"        if (!eea_signed_to_raw(values->{field_id}, "
                            f"{field.bit_length}u, &raw) ||"
                        ),
                        f"            !eea_encode_raw_value(payload, payload_length, {bit_name}, "
                        f"{field.bit_length}u, raw)) {{ return false; }}",
                        "    }",
                    ]
                )
            else:
                lines.append(
                    f"    if (!eea_encode_raw_value(payload, payload_length, {bit_name}, "
                    f"{field.bit_length}u, values->{field_id})) {{ return false; }}"
                )
        lines.extend(["    return true;", "}", ""])
        lines.extend(
            [
                f"bool eea_{message_id}_decode_raw(",
                "    const uint8_t *payload,",
                "    size_t payload_length,",
                f"    eea_{message_id}_raw_values_t *values) {{",
                "    if (payload == NULL || values == NULL ||",
                f"        payload_length != {message.payload_length_bytes}u) {{",
                "        return false;",
                "    }",
            ]
        )
        for field, field_id, bit_name in zip(ordered_fields, field_ids, bit_names, strict=True):
            if field.signed:
                lines.extend(
                    [
                        "    {",
                        "        uint64_t raw = UINT64_C(0);",
                        f"        if (!eea_decode_raw_value(payload, payload_length, {bit_name}, "
                        f"{field.bit_length}u, &raw) || !eea_raw_to_signed(raw, "
                        f"{field.bit_length}u, &values->{field_id})) {{ return false; }}",
                        "    }",
                    ]
                )
            else:
                lines.append(
                    f"    if (!eea_decode_raw_value(payload, payload_length, {bit_name}, "
                    f"{field.bit_length}u, &values->{field_id})) {{ return false; }}"
                )
        lines.extend(["    return true;", "}", ""])
    return "\n".join(lines)


def _python_runtime() -> list[str]:
    return [
        "def _mask(width: int) -> int:",
        "    return (1 << width) - 1",
        "",
        "def _write_raw(payload: bytearray, bits: tuple[int, ...], width: int, raw: int) -> None:",
        "    if raw < 0: raw = (1 << width) + raw",
        "    if raw < 0 or raw > _mask(width): raise ValueError('raw value out of range')",
        "    for index, bit in enumerate(bits):",
        "        if raw & (1 << index): payload[bit // 8] |= 1 << (bit % 8)",
        "        else: payload[bit // 8] &= ~(1 << (bit % 8))",
        "",
        "def _read_raw(payload: bytes, bits: tuple[int, ...], width: int, signed: bool) -> int:",
        "    raw = 0",
        "    for index, bit in enumerate(bits):",
        "        if payload[bit // 8] & (1 << (bit % 8)): raw |= 1 << index",
        "    if signed and raw & (1 << (width - 1)): return raw - (1 << width)",
        "    return raw",
        "",
        "def _raw_bounds(width: int, signed: bool) -> tuple[int, int]:",
        (
            "    return ((-(1 << (width - 1)), (1 << (width - 1)) - 1) "
            "if signed else (0, _mask(width)))"
        ),
        "",
        "def _encode_value(value: float, scale: float, offset: float,",
        "                  signed: bool, width: int, minimum: float | None,",
        "                  maximum: float | None) -> int:",
        "    if not isinstance(value, (int, float)) or isinstance(value, bool):",
        "        raise ValueError('numeric value required')",
        "    import math",
        "    from decimal import Decimal, ROUND_HALF_UP",
        "    if isinstance(value, float) and (not math.isfinite(value) or abs(value) > 2**53):",
        (
            "        raise ValueError('physical value exceeds exact IEEE-754 integer "
            "safety; use raw codec')"
        ),
        "    if scale <= 0: raise ValueError('scale must be positive')",
        "    if minimum is not None and value < minimum: raise ValueError('below minimum')",
        "    if maximum is not None and value > maximum: raise ValueError('above maximum')",
        (
            "    raw = int(((Decimal(str(value)) - Decimal(str(offset))) / "
            "Decimal(str(scale))).to_integral_value(rounding=ROUND_HALF_UP))"
        ),
        (
            "    if abs(raw) > 2**53: raise ValueError('physical conversion exceeds "
            "exact IEEE-754 integer safety; use raw codec')"
        ),
        "    minimum, maximum = _raw_bounds(width, signed)",
        "    if raw < minimum or raw > maximum: raise ValueError('value out of range')",
        "    return raw",
        "",
        "def _encode_raw_value(value: int, width: int, signed: bool) -> int:",
        (
            "    if not isinstance(value, int) or isinstance(value, bool): "
            "raise ValueError('exact integer raw value required')"
        ),
        "    minimum, maximum = _raw_bounds(width, signed)",
        "    if value < minimum or value > maximum: raise ValueError('raw value out of range')",
        "    return value",
        "",
        "def _decode_value(payload: bytes, bits: tuple[int, ...], width: int,",
        "                  signed: bool, scale: float, offset: float) -> float:",
        "    from decimal import Decimal",
        "    raw = _read_raw(payload, bits, width, signed)",
        (
            "    if abs(raw) > 2**53: raise ValueError('physical value exceeds exact "
            "IEEE-754 integer safety; use raw codec')"
        ),
        ("    physical = Decimal(raw) * Decimal(str(scale)) + Decimal(str(offset))"),
        "    value = float(physical)",
        (
            "    if Decimal(str(value)) != physical: raise ValueError('physical value "
            "is not exactly representable; use raw codec')"
        ),
        "    return value",
        "",
        (
            "def _decode_raw_value(payload: bytes, bits: tuple[int, ...], width: int, "
            "signed: bool) -> int:"
        ),
        "    return _read_raw(payload, bits, width, signed)",
        "",
    ]


def _python_source(protocol: ProtocolIR, registry: GeneratedIdentifierRegistry) -> str:
    lines = [
        _header(protocol, "standalone Python").replace("/* ", "# ").replace(" */", ""),
        "from collections.abc import Mapping",
        "",
        f"PROTOCOL_ID = {str(protocol.id)!r}",
        f"PROTOCOL_REVISION = {protocol.revision}",
        f"PROTOCOL_INPUT_HASH = {protocol.input_hash!r}",
        f"GENERATOR_VERSION = {PROTOCOL_GENERATOR_VERSION!r}",
        "",
    ]
    lines.extend(_python_runtime())
    for message in canonical_messages(protocol):
        message_id = registry.message(message)
        ordered_fields = canonical_fields(message)
        field_ids = [registry.field(message, field) for field in ordered_fields]
        lines.append(f"def encode_{message_id}(values: Mapping[str, float | int]) -> bytes:")
        lines.append(f"    payload = bytearray({message.payload_length_bytes})")
        for index, (field, _field_id) in enumerate(zip(ordered_fields, field_ids, strict=True)):
            bits = tuple(field_wire_bits(field))
            lines.append(f"    _bits_{message_id}_{index} = {bits!r}")
            lines.append(
                f"    _write_raw(payload, _bits_{message_id}_{index}, {field.bit_length}, "
                f"_encode_value(values[{field.name!r}], {field.scale!r}, {field.offset!r}, "
                f"{field.signed!r}, {field.bit_length}, {field.minimum!r}, {field.maximum!r}))"
            )
        lines.extend(["    return bytes(payload)", ""])
        lines.append(f"def decode_{message_id}(payload: bytes) -> dict[str, float]:")
        lines.append(
            f"    if len(payload) != {message.payload_length_bytes}: "
            "raise ValueError('invalid payload length')"
        )
        lines.append("    return {")
        for _index, (field, _) in enumerate(zip(ordered_fields, field_ids, strict=True)):
            bits = tuple(field_wire_bits(field))
            lines.append(
                f"        {field.name!r}: _decode_value(payload, {bits!r}, {field.bit_length}, "
                f"{field.signed!r}, {field.scale!r}, {field.offset!r}),"
            )
        lines.extend(["    }", ""])
        lines.append(f"def encode_{message_id}_raw(values: Mapping[str, int]) -> bytes:")
        lines.append(f"    payload = bytearray({message.payload_length_bytes})")
        for index, field in enumerate(ordered_fields):
            bits = tuple(field_wire_bits(field))
            lines.append(f"    _bits_{message_id}_{index} = {bits!r}")
            lines.append(
                f"    _write_raw(payload, _bits_{message_id}_{index}, {field.bit_length}, "
                f"_encode_raw_value(values[{field.name!r}], {field.bit_length}, {field.signed!r}))"
            )
        lines.extend(["    return bytes(payload)", ""])
        lines.append(f"def decode_{message_id}_raw(payload: bytes) -> dict[str, int]:")
        lines.append(
            f"    if len(payload) != {message.payload_length_bytes}: "
            "raise ValueError('invalid payload length')"
        )
        lines.append("    return {")
        for _index, field in enumerate(ordered_fields):
            bits = tuple(field_wire_bits(field))
            lines.append(
                f"        {field.name!r}: _decode_raw_value(payload, {bits!r}, "
                f"{field.bit_length}, {field.signed!r}),"
            )
        lines.extend(["    }", ""])
    return "\n".join(lines)


def _dbc_number(value: Decimal | float | int) -> str:
    if isinstance(value, Decimal):
        rendered = format(value, "f")
        if "." in rendered:
            rendered = rendered.rstrip("0").rstrip(".")
        return rendered or "0"
    return format(float(value), ".15g")


def _dbc_source(protocol: ProtocolIR, registry: GeneratedIdentifierRegistry) -> str:
    lines = [
        _header(protocol, "DBC"),
        'VERSION ""',
        "NS_ :",
        "    NS_DESC_",
        "BS_:",
        "BU_: Vector__XXX",
        "",
    ]
    arbitration_keys: set[int] = set()
    for message in canonical_messages(protocol):
        transport = next(
            item for item in protocol.transports if item.transport_id == message.transport_ref
        )
        if transport.transport_type.upper() != "CAN":
            continue
        can_id = message.can_id | (0x80000000 if message.extended_id else 0)
        if can_id in arbitration_keys:
            raise ProtocolGenerationError(
                "DBC cannot represent duplicate arbitration keys across transports"
            )
        arbitration_keys.add(can_id)
        lines.append(
            f"BO_ {can_id} {registry.message(message)}: {message.payload_length_bytes} Vector__XXX"
        )
        for field in canonical_fields(message):
            minimum = field.minimum if field.minimum is not None else _physical_min(field)
            maximum = field.maximum if field.maximum is not None else _physical_max(field)
            endian = 1 if field.endian.upper() == "LITTLE" else 0
            sign = "-" if field.signed else "+"
            lines.append(
                f" SG_ {registry.field(message, field)} : {field.bit_offset}|{field.bit_length}"
                f"@{endian}{sign} "
                f"({_dbc_number(field.scale)},{_dbc_number(field.offset)}) "
                f'[{_dbc_number(minimum)}|{_dbc_number(maximum)}] "{field.unit}" Vector__XXX'
            )
        lines.append("")
    return "\n".join(lines)


def _physical_min(field: ProtocolField) -> Decimal:
    raw_min = -(1 << (field.bit_length - 1)) if field.signed else 0
    return Decimal(raw_min) * Decimal(str(field.scale)) + Decimal(str(field.offset))


def _physical_max(field: ProtocolField) -> Decimal:
    raw_max = (1 << (field.bit_length - 1)) - 1 if field.signed else (1 << field.bit_length) - 1
    return Decimal(raw_max) * Decimal(str(field.scale)) + Decimal(str(field.offset))


def _markdown_source(protocol: ProtocolIR, registry: GeneratedIdentifierRegistry) -> str:
    lines = [
        f"# ProtocolIR {protocol.version_label}",
        "",
        _header(protocol, "Markdown").replace("/* ", "<!-- ").replace(" */", " -->"),
        "",
        f"- Protocol ID: `{protocol.id}`",
        f"- Revision: `{protocol.revision}`",
        f"- Input hash: `{protocol.input_hash}`",
        f"- Generator: `{PROTOCOL_GENERATOR_VERSION}`",
        "",
        "## Transports",
        "",
        "| ID | Name | Type | Frame | Nominal bitrate | Data bitrate | BRS |",
        "| --- | --- | --- | --- | ---: | ---: | --- |",
    ]
    for transport in canonical_transports(protocol):
        lines.append(
            f"| `{transport.transport_id}` | {transport.name} | {transport.transport_type} | "
            f"{transport.can.frame_kind} | {transport.can.nominal_bitrate} | "
            f"{transport.can.data_bitrate or ''} | "
            f"{transport.can.fd_brs if transport.can.fd_brs is not None else ''} |"
        )
    lines.extend(
        [
            "",
            "## Messages and fields",
            "",
            "| Message | CAN ID | DLC | Field | Start bit | Length | Endian | "
            "Signed | Scale | Offset | Unit |",
            "| --- | ---: | ---: | --- | ---: | ---: | --- | --- | ---: | ---: | --- |",
        ]
    )
    for message in canonical_messages(protocol):
        if not message.fields:
            lines.append(
                f"| `{message.name}` | `{message.can_id:#x}` | "
                f"{message.payload_length_bytes} | | | | | | | | |"
            )
            continue
        for field in canonical_fields(message):
            lines.append(
                f"| `{message.name}` | `{message.can_id:#x}` | {message.payload_length_bytes} | "
                f"`{field.name}` | {field.bit_offset} | {field.bit_length} | {field.endian} | "
                f"{field.signed} | {_dbc_number(field.scale)} | "
                f"{_dbc_number(field.offset)} | {field.unit} |"
            )
    lines.extend(
        [
            "",
            "## Conversion",
            "",
            "Physical value = raw value x scale + offset. Encoding uses "
            "round-half-away-from-zero and never clamps.",
            "",
        ]
    )
    return "\n".join(lines)


class ProtocolGenerator:
    """Render all M16 targets from one validated ProtocolIR."""

    def validate(self, protocol: ProtocolIR) -> ProtocolValidationResult:
        return validate_protocol(protocol)

    def generate(self, protocol: ProtocolIR) -> ProtocolGenerationBundle:
        validation = self.validate(protocol)
        if validation.status != "PASS":
            raise ProtocolGenerationError(
                f"ProtocolIR validation status is {validation.status}; generation is fail-closed"
            )
        registry = GeneratedIdentifierRegistry(protocol)
        contents = [
            ("C", "protocol.h", _c_header(protocol, registry)),
            ("C", "protocol.c", _c_source(protocol, registry)),
            ("PYTHON", "protocol_codec.py", _python_source(protocol, registry)),
            ("DBC", "protocol.dbc", _dbc_source(protocol, registry)),
            ("MARKDOWN", "protocol.md", _markdown_source(protocol, registry)),
        ]
        outputs = [
            GeneratedProtocolOutput(
                target=target,  # type: ignore[arg-type]
                path=path,
                content=content,
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                input_hash=protocol.input_hash,
                protocol_revision=protocol.revision,
                generator_version=PROTOCOL_GENERATOR_VERSION,
            )
            for target, path, content in contents
        ]
        return ProtocolGenerationBundle(
            protocol_id=protocol.id,
            protocol_revision=protocol.revision,
            input_hash=protocol.input_hash,
            generator_version=PROTOCOL_GENERATOR_VERSION,
            outputs=outputs,
        )


__all__ = ["ProtocolGenerationError", "ProtocolGenerator"]
