"""Core-neutral ProtocolIR, deterministic CAN validation, and reference codec.

M16 deliberately keeps protocol semantics independent from any domain plugin.  The
same bit traversal helpers are used by validation and the reference codec; code
generators consume these frozen semantics rather than re-interpreting them.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from eea_core.entities import EntityBase, Sha256

PROTOCOL_SCHEMA_VERSION = "1.0.0"
PROTOCOL_GENERATOR_VERSION = "m16.1"
ZERO_SHA256 = "0" * 64

ValidationStatus = Literal["PASS", "FAIL", "UNKNOWN", "BLOCKED"]
ProtocolOutputTarget = Literal["C", "PYTHON", "DBC", "MARKDOWN"]


class ProtocolModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CANTransportConfig(ProtocolModel):
    nominal_bitrate: int = Field(default=500_000)
    frame_kind: str = "CLASSIC"
    data_bitrate: int | None = None
    fd_brs: bool | None = None


class ProtocolTransport(ProtocolModel):
    transport_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    transport_type: str = "CAN"
    can: CANTransportConfig = Field(default_factory=CANTransportConfig)


class ProtocolField(ProtocolModel):
    field_id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=100)
    bit_offset: int
    bit_length: int
    endian: str = "LITTLE"
    signed: bool = False
    scale: float = 1.0
    offset: float = 0.0
    unit: str = ""
    minimum: float | None = None
    maximum: float | None = None


class ProtocolMessage(ProtocolModel):
    message_id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    transport_ref: str = Field(min_length=1, max_length=100)
    can_id: int
    extended_id: bool = False
    payload_length_bytes: int
    fields: list[ProtocolField] = Field(default_factory=list)
    requirement_ids: list[UUID] = Field(default_factory=list)
    description: str = ""


class ProtocolDefinition(ProtocolModel):
    """User-owned protocol content accepted by create/update API operations."""

    version_label: str = Field(default="1.0.0", min_length=1, max_length=100)
    transports: list[ProtocolTransport] = Field(default_factory=list)
    messages: list[ProtocolMessage] = Field(default_factory=list)
    requirement_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class ProtocolIR(EntityBase):
    """Versioned, project-scoped CAN protocol contract.

    ``input_hash`` is derived from semantic content.  Entity identity, timestamps,
    revision, metadata, and the hash itself are intentionally excluded so that
    generated artifacts bind to content rather than persistence details.
    """

    schema_version: str = PROTOCOL_SCHEMA_VERSION
    project_id: UUID
    version_label: str = Field(default="1.0.0", min_length=1, max_length=100)
    transports: list[ProtocolTransport] = Field(default_factory=list)
    messages: list[ProtocolMessage] = Field(default_factory=list)
    requirement_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    input_hash: Sha256 = ZERO_SHA256

    @model_validator(mode="after")
    def derive_input_hash(self) -> ProtocolIR:
        object.__setattr__(self, "input_hash", protocol_input_hash(self))
        return self


class ProtocolValidationDiagnostic(ProtocolModel):
    rule_id: str
    status: ValidationStatus
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class ProtocolValidationResult(ProtocolModel):
    protocol_id: UUID
    protocol_revision: int
    input_hash: Sha256
    diagnostics: list[ProtocolValidationDiagnostic] = Field(default_factory=list)

    @property
    def status(self) -> ValidationStatus:
        statuses = {diagnostic.status for diagnostic in self.diagnostics}
        if "FAIL" in statuses:
            return "FAIL"
        if "BLOCKED" in statuses:
            return "BLOCKED"
        if "UNKNOWN" in statuses:
            return "UNKNOWN"
        return "PASS"


class GeneratedProtocolOutput(ProtocolModel):
    target: ProtocolOutputTarget
    path: str
    content: str
    content_hash: Sha256
    input_hash: Sha256
    protocol_revision: int
    generator_version: str


class ProtocolGenerationBundle(ProtocolModel):
    protocol_id: UUID
    protocol_revision: int
    input_hash: Sha256
    generator_version: str
    outputs: list[GeneratedProtocolOutput] = Field(default_factory=list)


def _stable_uuid(value: UUID) -> str:
    return str(value)


def canonical_transports(
    protocol: ProtocolIR | ProtocolDefinition,
) -> list[ProtocolTransport]:
    """Return transports in the same order used by semantic hashing."""

    return sorted(
        protocol.transports,
        key=lambda item: (item.transport_id, item.name),
    )


def canonical_messages(protocol: ProtocolIR | ProtocolDefinition) -> list[ProtocolMessage]:
    """Return messages in the same order used by semantic hashing."""

    return sorted(
        protocol.messages,
        key=lambda item: (_stable_uuid(item.message_id), item.name),
    )


def canonical_fields(message: ProtocolMessage) -> list[ProtocolField]:
    """Return fields in the same order used by semantic hashing."""

    return sorted(
        message.fields,
        key=lambda item: (_stable_uuid(item.field_id), item.name),
    )


def canonical_protocol_dict(protocol: ProtocolIR | ProtocolDefinition) -> dict[str, object]:
    """Return the semantically relevant, stably ordered protocol representation."""

    value = protocol.model_dump(
        mode="json",
        exclude={"id", "revision", "created_at", "updated_at", "metadata", "input_hash"},
    )
    transports = value.get("transports", [])
    messages = value.get("messages", [])
    if isinstance(transports, list):
        value["transports"] = sorted(
            transports,
            key=lambda item: (str(item.get("transport_id", "")), str(item.get("name", ""))),
        )
    if isinstance(messages, list):
        normalized_messages: list[dict[str, object]] = []
        for message in messages:
            fields = message.get("fields", [])
            if isinstance(fields, list):
                message["fields"] = sorted(
                    fields,
                    key=lambda item: (
                        str(item.get("field_id", "")),
                        str(item.get("name", "")),
                    ),
                )
            normalized_messages.append(message)
        value["messages"] = sorted(
            normalized_messages,
            key=lambda item: (
                str(item.get("message_id", "")),
                str(item.get("name", "")),
            ),
        )
    return value


def canonical_protocol_json(protocol: ProtocolIR | ProtocolDefinition) -> str:
    return json.dumps(
        canonical_protocol_dict(protocol),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def protocol_input_hash(protocol: ProtocolIR | ProtocolDefinition) -> str:
    return hashlib.sha256(canonical_protocol_json(protocol).encode("utf-8")).hexdigest()


def can_fd_valid_lengths(frame_kind: str) -> set[int]:
    if frame_kind.upper() == "FD":
        return {0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64}
    return set(range(9))


def field_wire_bits(field: ProtocolField) -> tuple[int, ...]:
    """Return wire bit positions in least-significant-raw-bit order.

    Internal numbering is byte 0 bit 0 as the first position.  LITTLE fields
    increment normally.  BIG fields use the CAN/DBC Motorola walk, while the
    returned tuple remains ordered from raw LSB to raw MSB for codec symmetry.
    """

    if field.bit_length <= 0:
        return ()
    if field.endian.upper() == "LITTLE":
        return tuple(field.bit_offset + index for index in range(field.bit_length))
    positions: list[int] = []
    current = field.bit_offset
    for _ in range(field.bit_length):
        positions.append(current)
        current = current - 1 if current % 8 else current + 15
    return tuple(reversed(positions))


def field_occupied_bits(field: ProtocolField) -> set[int]:
    return set(field_wire_bits(field))


def _raw_bounds(field: ProtocolField) -> tuple[int, int]:
    if field.bit_length <= 0:
        return (0, -1)
    if field.signed:
        return (-(1 << (field.bit_length - 1)), (1 << (field.bit_length - 1)) - 1)
    return (0, (1 << field.bit_length) - 1)


def _physical_bounds(field: ProtocolField) -> tuple[float, float]:
    raw_min, raw_max = _raw_bounds(field)
    return (raw_min * field.scale + field.offset, raw_max * field.scale + field.offset)


def _diagnostic(
    rule_id: str,
    status: ValidationStatus,
    message: str,
    **details: object,
) -> ProtocolValidationDiagnostic:
    return ProtocolValidationDiagnostic(
        rule_id=rule_id,
        status=status,
        message=message,
        details=details,
    )


def _protocol_transports(protocol: ProtocolIR | ProtocolDefinition) -> dict[str, ProtocolTransport]:
    # Keep the first deterministic candidate.  Validation rejects duplicate IDs;
    # this prevents lookup behavior from silently depending on dict overwrite.
    transports: dict[str, ProtocolTransport] = {}
    for transport in canonical_transports(protocol):
        transports.setdefault(transport.transport_id, transport)
    return transports


def validate_protocol(protocol: ProtocolIR) -> ProtocolValidationResult:
    """Evaluate all frozen M16 rules in stable order.

    Rule statuses are deterministic.  Missing references are BLOCKED because a
    protocol with unresolved execution context is not silently accepted.
    """

    transports = _protocol_transports(protocol)
    transport_id_groups: dict[str, list[str]] = {}
    for transport in protocol.transports:
        transport_id_groups.setdefault(transport.transport_id, []).append(transport.name)
    duplicate_transport_ids = {
        transport_id: names for transport_id, names in transport_id_groups.items() if len(names) > 1
    }
    transport_errors: list[dict[str, object]] = []
    for transport in protocol.transports:
        if transport.transport_type.upper() != "CAN":
            transport_errors.append(
                {"transport_id": transport.transport_id, "reason": "CAN_REQUIRED"}
            )
        if transport.can.frame_kind.upper() not in {"CLASSIC", "FD"}:
            transport_errors.append(
                {"transport_id": transport.transport_id, "reason": "FRAME_KIND_INVALID"}
            )
        if transport.can.nominal_bitrate <= 0:
            transport_errors.append(
                {"transport_id": transport.transport_id, "reason": "BITRATE_MUST_BE_POSITIVE"}
            )
    for message in protocol.messages:
        message_transport = transports.get(message.transport_ref)
        if message_transport is None:
            transport_errors.append(
                {"message": message.name, "transport_ref": message.transport_ref}
            )
    diagnostics: list[ProtocolValidationDiagnostic] = [
        _diagnostic(
            "TRANSPORT_REFERENCE_VALID",
            "FAIL" if duplicate_transport_ids else ("PASS" if not transport_errors else "BLOCKED"),
            "All message transport references resolve to valid CAN transports."
            if not transport_errors
            else (
                "Transport identifiers must be unique."
                if duplicate_transport_ids
                else "A message transport reference or transport configuration is unresolved."
            ),
            errors=transport_errors,
            duplicates=duplicate_transport_ids,
        )
    ]

    can_id_errors: list[dict[str, object]] = [
        {"message": message.name, "can_id": message.can_id, "extended": message.extended_id}
        for message in protocol.messages
        if message.can_id < 0 or message.can_id > (0x1FFFFFFF if message.extended_id else 0x7FF)
    ]
    arbitration_groups: dict[tuple[str, bool, int], list[str]] = {}
    for message in protocol.messages:
        key = (message.transport_ref, message.extended_id, message.can_id)
        arbitration_groups.setdefault(key, []).append(message.name)
    duplicate_arbitration_ids = {
        f"{transport}:{'extended' if extended else 'standard'}:{can_id:#x}": names
        for (transport, extended, can_id), names in arbitration_groups.items()
        if len(names) > 1
    }
    can_id_errors.extend(
        {
            "transport_ref": transport,
            "extended": extended,
            "can_id": can_id,
            "messages": names,
            "reason": "DUPLICATE_ARBITRATION_ID",
        }
        for (transport, extended, can_id), names in arbitration_groups.items()
        if len(names) > 1
    )
    diagnostics.append(
        _diagnostic(
            "CAN_ID_VALID",
            "PASS" if not can_id_errors else "FAIL",
            "All CAN identifiers fit their selected identifier format."
            if not can_id_errors
            else "One or more CAN identifiers are outside the allowed range.",
            errors=can_id_errors,
            duplicate_arbitration_ids=duplicate_arbitration_ids,
        )
    )

    payload_errors: list[dict[str, object]] = []
    for message in protocol.messages:
        message_transport = transports.get(message.transport_ref)
        if message_transport is None:
            continue
        if message.payload_length_bytes not in can_fd_valid_lengths(
            message_transport.can.frame_kind
        ):
            payload_errors.append(
                {
                    "message": message.name,
                    "length": message.payload_length_bytes,
                    "frame_kind": message_transport.can.frame_kind,
                }
            )
    diagnostics.append(
        _diagnostic(
            "CAN_PAYLOAD_LENGTH_VALID",
            "PASS" if not payload_errors else "FAIL",
            "All payload lengths are valid for their CAN frame kind."
            if not payload_errors
            else "A payload length is invalid for its CAN frame kind.",
            errors=payload_errors,
        )
    )

    message_names: dict[str, list[str]] = {}
    for message in protocol.messages:
        message_names.setdefault(message.name, []).append(str(message.message_id))
    duplicate_message_names = {name: ids for name, ids in message_names.items() if len(ids) > 1}
    diagnostics.append(
        _diagnostic(
            "MESSAGE_NAME_UNIQUE",
            "PASS" if not duplicate_message_names else "FAIL",
            "Message names are unique."
            if not duplicate_message_names
            else "Message names must be unique.",
            duplicates=duplicate_message_names,
        )
    )

    message_ids: dict[str, list[str]] = {}
    for message in protocol.messages:
        message_ids.setdefault(str(message.message_id), []).append(message.name)
    duplicate_message_ids = {key: names for key, names in message_ids.items() if len(names) > 1}
    diagnostics.append(
        _diagnostic(
            "MESSAGE_ID_UNIQUE",
            "PASS" if not duplicate_message_ids else "FAIL",
            "Message identifiers are unique."
            if not duplicate_message_ids
            else "Message identifiers must be unique.",
            duplicates=duplicate_message_ids,
        )
    )

    field_name_errors: list[dict[str, object]] = []
    for message in protocol.messages:
        names = [field.name for field in message.fields]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            field_name_errors.append({"message": message.name, "duplicates": duplicates})
    diagnostics.append(
        _diagnostic(
            "FIELD_NAME_UNIQUE",
            "PASS" if not field_name_errors else "FAIL",
            "Field names are unique within each message."
            if not field_name_errors
            else "Field names must be unique within each message.",
            errors=field_name_errors,
        )
    )

    length_errors: list[dict[str, object]] = []
    for message in protocol.messages:
        payload_bits = message.payload_length_bytes * 8
        for field in message.fields:
            bits = field_wire_bits(field)
            if (
                field.bit_length < 1
                or field.bit_length > 64
                or not bits
                or any(bit < 0 or bit >= payload_bits for bit in bits)
            ):
                length_errors.append(
                    {
                        "message": message.name,
                        "field": field.name,
                        "bit_offset": field.bit_offset,
                        "bit_length": field.bit_length,
                        "payload_bits": payload_bits,
                    }
                )
    diagnostics.append(
        _diagnostic(
            "FIELD_LENGTH_VALID",
            "PASS" if not length_errors else "FAIL",
            "All fields fit their message payloads."
            if not length_errors
            else "A field length or position is invalid.",
            errors=length_errors,
        )
    )

    bounds_errors: list[dict[str, object]] = []
    for message in protocol.messages:
        for field in message.fields:
            if (
                (field.minimum is not None and not math.isfinite(field.minimum))
                or (field.maximum is not None and not math.isfinite(field.maximum))
                or (
                    field.minimum is not None
                    and field.maximum is not None
                    and field.minimum > field.maximum
                )
            ):
                bounds_errors.append({"message": message.name, "field": field.name})
    diagnostics.append(
        _diagnostic(
            "FIELD_BOUNDS_VALID",
            "PASS" if not bounds_errors else "FAIL",
            "Declared physical bounds are finite and ordered."
            if not bounds_errors
            else "A declared physical bound is invalid.",
            errors=bounds_errors,
        )
    )

    overlap_errors: list[dict[str, object]] = []
    for message in protocol.messages:
        occupied: dict[int, str] = {}
        for field in message.fields:
            for bit in field_wire_bits(field):
                previous = occupied.get(bit)
                if previous is not None:
                    overlap_errors.append(
                        {
                            "message": message.name,
                            "field": field.name,
                            "overlaps": previous,
                            "bit": bit,
                        }
                    )
                occupied[bit] = field.name
    diagnostics.append(
        _diagnostic(
            "FIELD_OVERLAP",
            "PASS" if not overlap_errors else "FAIL",
            "Fields do not overlap."
            if not overlap_errors
            else "Fields overlap in the wire layout.",
            errors=overlap_errors,
        )
    )

    scale_errors: list[dict[str, object]] = []
    for message in protocol.messages:
        for field in message.fields:
            if (
                not math.isfinite(field.scale)
                or field.scale <= 0
                or not math.isfinite(field.offset)
            ):
                scale_errors.append(
                    {
                        "message": message.name,
                        "field": field.name,
                        "scale": field.scale,
                        "offset": field.offset,
                    }
                )
    diagnostics.append(
        _diagnostic(
            "FIELD_SCALE_VALID",
            "PASS" if not scale_errors else "FAIL",
            "All field scales are finite and positive."
            if not scale_errors
            else "A field scale or offset is invalid.",
            errors=scale_errors,
        )
    )

    physical_errors: list[dict[str, object]] = []
    for message in protocol.messages:
        for field in message.fields:
            if (
                not math.isfinite(field.scale)
                or field.scale <= 0
                or not math.isfinite(field.offset)
            ):
                continue
            representable_min, representable_max = _physical_bounds(field)
            if (field.minimum is not None and field.minimum < representable_min) or (
                field.maximum is not None and field.maximum > representable_max
            ):
                physical_errors.append(
                    {
                        "message": message.name,
                        "field": field.name,
                        "representable_min": representable_min,
                        "representable_max": representable_max,
                        "declared_min": field.minimum,
                        "declared_max": field.maximum,
                    }
                )
    diagnostics.append(
        _diagnostic(
            "FIELD_PHYSICAL_RANGE_VALID",
            "PASS" if not physical_errors else "FAIL",
            "Declared ranges fit field encoding."
            if not physical_errors
            else "A declared range exceeds field encoding.",
            errors=physical_errors,
        )
    )

    endian_errors: list[dict[str, object]] = []
    for message in protocol.messages:
        for field in message.fields:
            if field.endian.upper() not in {"LITTLE", "BIG"}:
                endian_errors.append(
                    {"message": message.name, "field": field.name, "endian": field.endian}
                )
    diagnostics.append(
        _diagnostic(
            "FIELD_ENDIAN_VALID",
            "PASS" if not endian_errors else "FAIL",
            "All field endianness values are supported."
            if not endian_errors
            else "A field endian value is invalid.",
            errors=endian_errors,
        )
    )

    return ProtocolValidationResult(
        protocol_id=protocol.id,
        protocol_revision=protocol.revision,
        input_hash=protocol.input_hash,
        diagnostics=diagnostics,
    )


class ProtocolCodecError(ValueError):
    """Raised when a value cannot be represented without silent coercion."""


def _round_half_away_from_zero(value: float) -> int:
    return math.floor(value + 0.5) if value >= 0 else math.ceil(value - 0.5)


def _field_by_ref(protocol: ProtocolIR, message_ref: str | UUID) -> ProtocolMessage:
    reference = str(message_ref)
    for message in protocol.messages:
        if str(message.message_id) == reference or message.name == reference:
            return message
    raise ProtocolCodecError(f"unknown protocol message: {reference}")


def _write_raw(payload: bytearray, field: ProtocolField, raw_value: int) -> None:
    raw_min, raw_max = _raw_bounds(field)
    if raw_value < raw_min or raw_value > raw_max:
        raise ProtocolCodecError(f"raw value out of range for field {field.name}")
    unsigned = raw_value if raw_value >= 0 else (1 << field.bit_length) + raw_value
    for raw_index, wire_bit in enumerate(field_wire_bits(field)):
        if unsigned & (1 << raw_index):
            payload[wire_bit // 8] |= 1 << (wire_bit % 8)
        else:
            payload[wire_bit // 8] &= ~(1 << (wire_bit % 8))


def _read_raw(payload: bytes, field: ProtocolField) -> int:
    unsigned = 0
    for raw_index, wire_bit in enumerate(field_wire_bits(field)):
        if payload[wire_bit // 8] & (1 << (wire_bit % 8)):
            unsigned |= 1 << raw_index
    if field.signed and unsigned & (1 << (field.bit_length - 1)):
        return unsigned - (1 << field.bit_length)
    return unsigned


def _decimal_value(value: float | int, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ProtocolCodecError(f"field {field_name} requires a finite value") from error


def _safe_physical_float(value: Decimal, field_name: str) -> float:
    converted = float(value)
    if not math.isfinite(converted) or Decimal(str(converted)) != value:
        raise ProtocolCodecError(
            f"decoded physical value for field {field_name} is not exactly representable; "
            "use raw_values=True"
        )
    return converted


def _encode_field_value(field: ProtocolField, value: float | int, *, raw_value: bool) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolCodecError(f"field {field.name} requires a numeric value")
    if raw_value:
        if not isinstance(value, int):
            raise ProtocolCodecError(
                f"raw value for field {field.name} must be an exact Python int"
            )
        raw = value
    else:
        if not math.isfinite(field.scale) or field.scale <= 0:
            raise ProtocolCodecError(f"field {field.name} has invalid scale")
        if isinstance(value, float) and (not math.isfinite(value) or abs(value) > float(1 << 53)):
            raise ProtocolCodecError(
                f"physical value for field {field.name} exceeds exact IEEE-754 integer safety; "
                "use raw_values=True"
            )
        numeric = _decimal_value(value, field.name)
        if field.minimum is not None and numeric < _decimal_value(field.minimum, field.name):
            raise ProtocolCodecError(f"field {field.name} is below declared minimum")
        if field.maximum is not None and numeric > _decimal_value(field.maximum, field.name):
            raise ProtocolCodecError(f"field {field.name} is above declared maximum")
        raw_decimal = (
            (numeric - _decimal_value(field.offset, field.name))
            / _decimal_value(field.scale, field.name)
        ).to_integral_value(rounding=ROUND_HALF_UP)
        raw = int(raw_decimal)
        if abs(raw) > (1 << 53):
            raise ProtocolCodecError(
                f"physical conversion for field {field.name} exceeds exact IEEE-754 "
                "integer safety; use raw_values=True"
            )
    raw_min, raw_max = _raw_bounds(field)
    if raw < raw_min or raw > raw_max:
        raise ProtocolCodecError(f"field {field.name} cannot represent value")
    return raw


def encode_message(
    protocol: ProtocolIR,
    message_ref: str | UUID,
    values: Mapping[str, float | int],
    *,
    raw_values: bool = False,
) -> bytes:
    message = _field_by_ref(protocol, message_ref)
    payload = bytearray(message.payload_length_bytes)
    for field in message.fields:
        if field.name not in values:
            raise ProtocolCodecError(f"missing value for field {field.name}")
        _write_raw(
            payload,
            field,
            _encode_field_value(field, values[field.name], raw_value=raw_values),
        )
    return bytes(payload)


def decode_message(
    protocol: ProtocolIR,
    message_ref: str | UUID,
    payload: bytes | bytearray,
    *,
    raw_values: bool = False,
) -> dict[str, float | int]:
    message = _field_by_ref(protocol, message_ref)
    if len(payload) != message.payload_length_bytes:
        raise ProtocolCodecError(
            f"payload length for {message.name} must be {message.payload_length_bytes}"
        )
    decoded: dict[str, float | int] = {}
    for field in message.fields:
        raw = _read_raw(bytes(payload), field)
        if raw_values:
            decoded[field.name] = raw
            continue
        if abs(raw) > (1 << 53):
            raise ProtocolCodecError(
                f"physical value for field {field.name} exceeds exact IEEE-754 integer "
                "safety; use raw_values=True"
            )
        physical = Decimal(raw) * _decimal_value(field.scale, field.name) + _decimal_value(
            field.offset, field.name
        )
        decoded[field.name] = _safe_physical_float(physical, field.name)
    return decoded


@dataclass(frozen=True)
class ReferenceProtocolCodec:
    """Small object wrapper used by applications and golden-vector tests."""

    protocol: ProtocolIR

    def encode(
        self,
        message_ref: str | UUID,
        values: Mapping[str, float | int],
        *,
        raw_values: bool = False,
    ) -> bytes:
        return encode_message(self.protocol, message_ref, values, raw_values=raw_values)

    def decode(
        self,
        message_ref: str | UUID,
        payload: bytes | bytearray,
        *,
        raw_values: bool = False,
    ) -> dict[str, float | int]:
        return decode_message(self.protocol, message_ref, payload, raw_values=raw_values)


__all__ = [
    "PROTOCOL_GENERATOR_VERSION",
    "PROTOCOL_SCHEMA_VERSION",
    "CANTransportConfig",
    "GeneratedProtocolOutput",
    "ProtocolCodecError",
    "ProtocolDefinition",
    "ProtocolField",
    "ProtocolGenerationBundle",
    "ProtocolIR",
    "ProtocolMessage",
    "ProtocolTransport",
    "ProtocolValidationDiagnostic",
    "ProtocolValidationResult",
    "ReferenceProtocolCodec",
    "can_fd_valid_lengths",
    "canonical_fields",
    "canonical_messages",
    "canonical_protocol_dict",
    "canonical_protocol_json",
    "canonical_transports",
    "decode_message",
    "encode_message",
    "field_occupied_bits",
    "field_wire_bits",
    "protocol_input_hash",
    "validate_protocol",
]
