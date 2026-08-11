"""M16 ProtocolIR contract, generator, and codec tests.

Generator, persistence, and API cases are added below this core contract section
as those layers become available.
"""

import shutil
import subprocess
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from eea_application.protocol import ProtocolGenerationError, ProtocolGenerator
from eea_backend.database import create_database_engine
from eea_backend.protocol_repositories import SqlAlchemyProtocolRepository
from eea_core.protocol import (
    CANTransportConfig,
    ProtocolCodecError,
    ProtocolField,
    ProtocolIR,
    ProtocolMessage,
    ProtocolTransport,
    ReferenceProtocolCodec,
    field_occupied_bits,
    field_wire_bits,
    validate_protocol,
)
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")
MESSAGE_ID = UUID("00000000-0000-0000-0000-000000000002")


def protocol_with(
    *,
    messages: list[ProtocolMessage] | None = None,
    transports: list[ProtocolTransport] | None = None,
) -> ProtocolIR:
    return ProtocolIR(
        id=UUID("00000000-0000-0000-0000-000000000010"),
        project_id=PROJECT_ID,
        transports=transports
        or [
            ProtocolTransport(
                transport_id="can0",
                name="CAN 0",
                can=CANTransportConfig(nominal_bitrate=500_000),
            )
        ],
        messages=messages
        or [
            ProtocolMessage(
                message_id=MESSAGE_ID,
                name="Status",
                transport_ref="can0",
                can_id=0x201,
                payload_length_bytes=8,
                fields=[ProtocolField(name="counter", bit_offset=0, bit_length=8)],
            )
        ],
    )


def diagnostic_map(protocol: ProtocolIR) -> dict[str, str]:
    return {
        diagnostic.rule_id: diagnostic.status
        for diagnostic in validate_protocol(protocol).diagnostics
    }


def test_valid_classic_protocol_passes_all_frozen_rules() -> None:
    result = validate_protocol(protocol_with())

    assert result.status == "PASS"
    assert {diagnostic.status for diagnostic in result.diagnostics} == {"PASS"}
    assert len(result.diagnostics) == 12


@pytest.mark.parametrize(
    ("rule_id", "protocol_factory"),
    [
        (
            "TRANSPORT_REFERENCE_VALID",
            lambda: protocol_with(
                messages=[
                    ProtocolMessage(
                        message_id=MESSAGE_ID,
                        name="Status",
                        transport_ref="missing",
                        can_id=1,
                        payload_length_bytes=8,
                    )
                ]
            ),
        ),
        (
            "CAN_ID_VALID",
            lambda: protocol_with(
                messages=[
                    ProtocolMessage(
                        message_id=MESSAGE_ID,
                        name="Status",
                        transport_ref="can0",
                        can_id=0x800,
                        payload_length_bytes=8,
                    )
                ]
            ),
        ),
        (
            "CAN_PAYLOAD_LENGTH_VALID",
            lambda: protocol_with(
                messages=[
                    ProtocolMessage(
                        message_id=MESSAGE_ID,
                        name="Status",
                        transport_ref="can0",
                        can_id=1,
                        payload_length_bytes=9,
                    )
                ]
            ),
        ),
        (
            "MESSAGE_NAME_UNIQUE",
            lambda: protocol_with(
                messages=[
                    ProtocolMessage(
                        message_id=MESSAGE_ID,
                        name="Status",
                        transport_ref="can0",
                        can_id=1,
                        payload_length_bytes=8,
                    ),
                    ProtocolMessage(
                        message_id=uuid4(),
                        name="Status",
                        transport_ref="can0",
                        can_id=2,
                        payload_length_bytes=8,
                    ),
                ]
            ),
        ),
        (
            "MESSAGE_ID_UNIQUE",
            lambda: protocol_with(
                messages=[
                    ProtocolMessage(
                        message_id=MESSAGE_ID,
                        name="A",
                        transport_ref="can0",
                        can_id=1,
                        payload_length_bytes=8,
                    ),
                    ProtocolMessage(
                        message_id=MESSAGE_ID,
                        name="B",
                        transport_ref="can0",
                        can_id=2,
                        payload_length_bytes=8,
                    ),
                ]
            ),
        ),
        (
            "FIELD_NAME_UNIQUE",
            lambda: protocol_with(
                messages=[
                    ProtocolMessage(
                        message_id=MESSAGE_ID,
                        name="Status",
                        transport_ref="can0",
                        can_id=1,
                        payload_length_bytes=8,
                        fields=[
                            ProtocolField(name="value", bit_offset=0, bit_length=8),
                            ProtocolField(name="value", bit_offset=8, bit_length=8),
                        ],
                    )
                ]
            ),
        ),
        (
            "FIELD_LENGTH_VALID",
            lambda: protocol_with(
                messages=[
                    ProtocolMessage(
                        message_id=MESSAGE_ID,
                        name="Status",
                        transport_ref="can0",
                        can_id=1,
                        payload_length_bytes=8,
                        fields=[ProtocolField(name="value", bit_offset=60, bit_length=8)],
                    )
                ]
            ),
        ),
        (
            "FIELD_BOUNDS_VALID",
            lambda: protocol_with(
                messages=[
                    ProtocolMessage(
                        message_id=MESSAGE_ID,
                        name="Status",
                        transport_ref="can0",
                        can_id=1,
                        payload_length_bytes=8,
                        fields=[
                            ProtocolField(
                                name="value",
                                bit_offset=0,
                                bit_length=8,
                                minimum=5,
                                maximum=2,
                            )
                        ],
                    )
                ]
            ),
        ),
        (
            "FIELD_OVERLAP",
            lambda: protocol_with(
                messages=[
                    ProtocolMessage(
                        message_id=MESSAGE_ID,
                        name="Status",
                        transport_ref="can0",
                        can_id=1,
                        payload_length_bytes=8,
                        fields=[
                            ProtocolField(name="a", bit_offset=0, bit_length=8),
                            ProtocolField(name="b", bit_offset=4, bit_length=8),
                        ],
                    )
                ]
            ),
        ),
        (
            "FIELD_SCALE_VALID",
            lambda: protocol_with(
                messages=[
                    ProtocolMessage(
                        message_id=MESSAGE_ID,
                        name="Status",
                        transport_ref="can0",
                        can_id=1,
                        payload_length_bytes=8,
                        fields=[ProtocolField(name="value", bit_offset=0, bit_length=8, scale=0)],
                    )
                ]
            ),
        ),
        (
            "FIELD_PHYSICAL_RANGE_VALID",
            lambda: protocol_with(
                messages=[
                    ProtocolMessage(
                        message_id=MESSAGE_ID,
                        name="Status",
                        transport_ref="can0",
                        can_id=1,
                        payload_length_bytes=8,
                        fields=[
                            ProtocolField(
                                name="value",
                                bit_offset=0,
                                bit_length=8,
                                maximum=256,
                            )
                        ],
                    )
                ]
            ),
        ),
        (
            "FIELD_ENDIAN_VALID",
            lambda: protocol_with(
                messages=[
                    ProtocolMessage(
                        message_id=MESSAGE_ID,
                        name="Status",
                        transport_ref="can0",
                        can_id=1,
                        payload_length_bytes=8,
                        fields=[
                            ProtocolField(
                                name="value",
                                bit_offset=0,
                                bit_length=8,
                                endian="MIDDLE",
                            )
                        ],
                    )
                ]
            ),
        ),
    ],
)
def test_each_frozen_rule_fails_closed(rule_id: str, protocol_factory: object) -> None:
    protocol = protocol_factory()  # type: ignore[operator]

    assert diagnostic_map(protocol)[rule_id] in {"FAIL", "BLOCKED"}


def test_fd_payload_lengths_are_deterministic() -> None:
    transport = ProtocolTransport(
        transport_id="canfd",
        name="CAN FD",
        can=CANTransportConfig(frame_kind="FD", nominal_bitrate=500_000),
    )
    valid = protocol_with(
        transports=[transport],
        messages=[
            ProtocolMessage(
                message_id=MESSAGE_ID,
                name="FdStatus",
                transport_ref="canfd",
                can_id=1,
                payload_length_bytes=12,
            )
        ],
    )
    invalid = valid.model_copy(deep=True)
    invalid.messages[0].payload_length_bytes = 10

    assert diagnostic_map(valid)["CAN_PAYLOAD_LENGTH_VALID"] == "PASS"
    assert diagnostic_map(invalid)["CAN_PAYLOAD_LENGTH_VALID"] == "FAIL"


def test_wire_bit_traversal_is_shared_and_explicit() -> None:
    little = ProtocolField(name="little", bit_offset=3, bit_length=5, endian="LITTLE")
    big = ProtocolField(name="big", bit_offset=7, bit_length=12, endian="BIG")

    assert field_wire_bits(little) == (3, 4, 5, 6, 7)
    assert field_wire_bits(big) == (12, 13, 14, 15, 0, 1, 2, 3, 4, 5, 6, 7)
    assert field_occupied_bits(big) == {
        0,
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        12,
        13,
        14,
        15,
    }


def test_reference_codec_handles_signed_scaled_and_non_byte_aligned_fields() -> None:
    message = ProtocolMessage(
        message_id=MESSAGE_ID,
        name="Scaled",
        transport_ref="can0",
        can_id=1,
        payload_length_bytes=3,
        fields=[
            ProtocolField(name="signed", bit_offset=0, bit_length=8, signed=True),
            ProtocolField(
                name="temperature",
                bit_offset=15,
                bit_length=12,
                endian="BIG",
                signed=True,
                scale=0.5,
                offset=-10,
                minimum=-10,
                maximum=194.5,
            ),
        ],
    )
    protocol = protocol_with(messages=[message])
    codec = ReferenceProtocolCodec(protocol)

    payload = codec.encode("Scaled", {"signed": -2, "temperature": -5.0})
    decoded = codec.decode("Scaled", payload)

    assert payload[0] == 0xFE
    assert decoded["signed"] == -2
    assert decoded["temperature"] == -5.0


@pytest.mark.parametrize("value", [-128, -1, 0, 1, 127])
def test_signed_eight_bit_boundaries(value: int) -> None:
    message = ProtocolMessage(
        message_id=MESSAGE_ID,
        name="Signed",
        transport_ref="can0",
        can_id=1,
        payload_length_bytes=1,
        fields=[ProtocolField(name="value", bit_offset=0, bit_length=8, signed=True)],
    )
    codec = ReferenceProtocolCodec(protocol_with(messages=[message]))

    assert codec.decode("Signed", codec.encode("Signed", {"value": value}))["value"] == value


def test_reference_codec_rejects_missing_and_unrepresentable_values() -> None:
    message = ProtocolMessage(
        message_id=MESSAGE_ID,
        name="Limited",
        transport_ref="can0",
        can_id=1,
        payload_length_bytes=1,
        fields=[ProtocolField(name="value", bit_offset=0, bit_length=4, minimum=0, maximum=10)],
    )
    codec = ReferenceProtocolCodec(protocol_with(messages=[message]))

    with pytest.raises(ProtocolCodecError):
        codec.encode("Limited", {})
    with pytest.raises(ProtocolCodecError):
        codec.encode("Limited", {"value": 11})
    with pytest.raises(ProtocolCodecError):
        codec.decode("Limited", b"\x00\x00")


def test_semantic_hash_excludes_entity_revision_but_changes_with_protocol_content() -> None:
    original = protocol_with()
    revised = original.model_copy(update={"revision": 2, "metadata": {"note": "history"}})
    changed = original.model_copy(deep=True)
    changed.messages[0].fields[0].bit_length = 7
    changed = ProtocolIR.model_validate(changed.model_dump(mode="json"))

    assert revised.input_hash == original.input_hash
    assert changed.input_hash != original.input_hash
    assert revised.revision == 2


def motor_status_protocol() -> ProtocolIR:
    return protocol_with(
        messages=[
            ProtocolMessage(
                message_id=MESSAGE_ID,
                name="MotorStatus",
                transport_ref="can0",
                can_id=0x201,
                payload_length_bytes=8,
                fields=[
                    ProtocolField(
                        name="rpm",
                        bit_offset=0,
                        bit_length=16,
                        scale=0.25,
                        minimum=0,
                        maximum=16383.75,
                        unit="rpm",
                    ),
                    ProtocolField(
                        name="current",
                        bit_offset=16,
                        bit_length=12,
                        signed=True,
                        scale=0.5,
                        offset=-20,
                        minimum=-1044,
                        maximum=1003.5,
                        unit="A",
                    ),
                    ProtocolField(name="flags", bit_offset=32, bit_length=4),
                ],
            )
        ]
    )


def test_all_generators_share_revision_and_input_hash() -> None:
    protocol = motor_status_protocol()
    bundle = ProtocolGenerator().generate(protocol)

    assert len(bundle.outputs) == 5
    assert {output.input_hash for output in bundle.outputs} == {protocol.input_hash}
    assert {output.protocol_revision for output in bundle.outputs} == {protocol.revision}
    assert all(output.content_hash for output in bundle.outputs)
    assert "EEA_PROTOCOL_INPUT_HASH" in next(
        output.content for output in bundle.outputs if output.path == "protocol.h"
    )
    assert "PROTOCOL_INPUT_HASH" in next(
        output.content for output in bundle.outputs if output.path == "protocol_codec.py"
    )


def test_generation_is_fail_closed_for_invalid_protocol() -> None:
    invalid = protocol_with(
        messages=[
            ProtocolMessage(
                message_id=MESSAGE_ID,
                name="Invalid",
                transport_ref="can0",
                can_id=0x800,
                payload_length_bytes=8,
            )
        ]
    )

    with pytest.raises(ProtocolGenerationError):
        ProtocolGenerator().generate(invalid)


def test_generated_python_codec_matches_reference_golden_vector(tmp_path: Path) -> None:
    protocol = motor_status_protocol()
    bundle = ProtocolGenerator().generate(protocol)
    python_output = next(output for output in bundle.outputs if output.path == "protocol_codec.py")
    module_path = tmp_path / python_output.path
    module_path.write_text(python_output.content, encoding="utf-8")
    namespace: dict[str, object] = {}
    exec(compile(python_output.content, str(module_path), "exec"), namespace)

    values = {"rpm": 100, "current": -21, "flags": 5}
    expected = bytes.fromhex("90 01 FE 0F 05 00 00 00")
    reference = ReferenceProtocolCodec(protocol).encode("MotorStatus", values)
    generated = namespace["encode_motorstatus"](values)  # type: ignore[operator]

    assert reference == expected
    assert generated == expected
    assert namespace["decode_motorstatus"](expected)["current"] == -21  # type: ignore[index,operator]


def test_generated_c_codec_compiles_and_matches_python_golden_vector(tmp_path: Path) -> None:
    compiler = shutil.which("gcc") or shutil.which("clang") or shutil.which("cc")
    if compiler is None:
        pytest.fail("M16 C11 compile gate requires gcc, clang, or cc")
    protocol = motor_status_protocol()
    bundle = ProtocolGenerator().generate(protocol)
    header = next(output for output in bundle.outputs if output.path == "protocol.h")
    source = next(output for output in bundle.outputs if output.path == "protocol.c")
    (tmp_path / header.path).write_text(header.content, encoding="utf-8")
    (tmp_path / source.path).write_text(source.content, encoding="utf-8")
    harness = tmp_path / "golden.c"
    harness.write_text(
        """
#include <stdio.h>
#include "protocol.h"

int main(void) {
    eea_motorstatus_values_t values = { .rpm = 100.0, .current = -21.0, .flags = 5.0 };
    uint8_t payload[8];
    if (!eea_motorstatus_encode(&values, payload, sizeof(payload))) return 2;
    for (size_t i = 0; i < sizeof(payload); ++i) printf("%02X", payload[i]);
    eea_motorstatus_values_t decoded;
    if (!eea_motorstatus_decode(payload, sizeof(payload), &decoded)) return 3;
    if (decoded.current != -21.0) return 4;
    return 0;
}
""".strip(),
        encoding="utf-8",
    )
    executable = tmp_path / "golden.exe"
    result = subprocess.run(
        [
            compiler,
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(tmp_path / "protocol.c"),
            str(harness),
            "-o",
            str(executable),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    run = subprocess.run([str(executable)], capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stderr
    assert run.stdout == "9001FE0F05000000"


def test_dbc_and_markdown_are_deterministic_and_explicit() -> None:
    bundle = ProtocolGenerator().generate(motor_status_protocol())
    dbc = next(output.content for output in bundle.outputs if output.path == "protocol.dbc")
    markdown = next(output.content for output in bundle.outputs if output.path == "protocol.md")

    assert "BO_ 513 motorstatus: 8 Vector__XXX" in dbc
    assert "SG_ rpm : 0|16@1+ (0.25,0)" in dbc
    assert "# ProtocolIR" in markdown
    assert "Physical value = raw value x scale + offset." in markdown


def protocol_api_payload(*, field_offset: int = 0) -> dict[str, object]:
    return {
        "version_label": "motor-status-v1",
        "transports": [
            {
                "transport_id": "can0",
                "name": "CAN 0",
                "transport_type": "CAN",
                "can": {
                    "nominal_bitrate": 500000,
                    "frame_kind": "CLASSIC",
                    "data_bitrate": None,
                    "fd_brs": None,
                },
            }
        ],
        "messages": [
            {
                "name": "Status",
                "transport_ref": "can0",
                "can_id": 0x201,
                "extended_id": False,
                "payload_length_bytes": 8,
                "fields": [
                    {
                        "name": "counter",
                        "bit_offset": field_offset,
                        "bit_length": 8,
                        "endian": "LITTLE",
                        "signed": False,
                        "scale": 1,
                        "offset": 0,
                        "unit": "",
                        "minimum": 0,
                        "maximum": 255,
                    }
                ],
                "requirement_ids": [],
                "description": "status",
            }
        ],
        "requirement_ids": [],
        "evidence_ids": [],
    }


def test_protocol_api_persists_revision_history_and_generates_outputs(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "Protocol project"}).json()["data"]
    project_id = project["id"]
    created_response = client.post(
        f"/api/v1/projects/{project_id}/protocol",
        json=protocol_api_payload(),
    )

    assert created_response.status_code == 201
    assert created_response.headers["ETag"] == 'W/"1"'
    first = created_response.json()["data"]

    get_response = client.get(f"/api/v1/projects/{project_id}/protocol")
    assert get_response.status_code == 200
    assert get_response.json()["data"]["input_hash"] == first["input_hash"]

    validation = client.post(f"/api/v1/projects/{project_id}/protocol/validate", json={})
    assert validation.status_code == 200
    assert validation.json()["data"]["input_hash"] == first["input_hash"]
    assert {item["status"] for item in validation.json()["data"]["diagnostics"]} == {"PASS"}

    generated = client.post(f"/api/v1/projects/{project_id}/protocol/generate", json={})
    assert generated.status_code == 200
    generated_data = generated.json()["data"]
    assert {item["input_hash"] for item in generated_data["outputs"]} == {first["input_hash"]}
    assert {item["path"] for item in generated_data["outputs"]} == {
        "protocol.h",
        "protocol.c",
        "protocol_codec.py",
        "protocol.dbc",
        "protocol.md",
    }

    updated_response = client.patch(
        f"/api/v1/projects/{project_id}/protocol",
        headers={"If-Match": 'W/"1"'},
        json={"expected_revision": 1, "version_label": "motor-status-v2"},
    )
    assert updated_response.status_code == 200
    assert updated_response.headers["ETag"] == 'W/"2"'
    second = updated_response.json()["data"]
    assert second["revision"] == 2
    assert second["input_hash"] != first["input_hash"]

    stale = client.patch(
        f"/api/v1/projects/{project_id}/protocol",
        headers={"If-Match": 'W/"1"'},
        json={"version_label": "stale"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "REVISION_CONFLICT"

    old_revision = client.post(
        f"/api/v1/projects/{project_id}/protocol/validate",
        json={"protocol_id": first["id"], "revision": 1},
    )
    assert old_revision.status_code == 200
    assert old_revision.json()["data"]["protocol_revision"] == 1


def test_protocol_api_enforces_project_scope(client: TestClient) -> None:
    first_project = client.post("/api/v1/projects", json={"name": "First"}).json()["data"]
    second_project = client.post("/api/v1/projects", json={"name": "Second"}).json()["data"]
    created = client.post(
        f"/api/v1/projects/{first_project['id']}/protocol",
        json=protocol_api_payload(),
    ).json()["data"]

    response = client.post(
        f"/api/v1/projects/{second_project['id']}/protocol/validate",
        json={"protocol_id": created["id"]},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "KNOWLEDGE_SCOPE_DENIED"


def test_reordered_semantic_input_has_identical_hash_and_all_outputs() -> None:
    message_a = ProtocolMessage(
        message_id=UUID("00000000-0000-0000-0000-000000000101"),
        name="A",
        transport_ref="can0",
        can_id=1,
        payload_length_bytes=8,
        fields=[
            ProtocolField(
                field_id=UUID("00000000-0000-0000-0000-000000000111"),
                name="a_low",
                bit_offset=0,
                bit_length=8,
            ),
            ProtocolField(
                field_id=UUID("00000000-0000-0000-0000-000000000112"),
                name="a_high",
                bit_offset=8,
                bit_length=8,
            ),
        ],
    )
    message_b = ProtocolMessage(
        message_id=UUID("00000000-0000-0000-0000-000000000102"),
        name="B",
        transport_ref="can1",
        can_id=2,
        payload_length_bytes=8,
        fields=[ProtocolField(name="b", bit_offset=0, bit_length=8)],
    )
    transports = [
        ProtocolTransport(transport_id="can0", name="CAN 0"),
        ProtocolTransport(transport_id="can1", name="CAN 1"),
    ]
    first = protocol_with(
        transports=transports,
        messages=[message_a, message_b],
    )
    reordered = first.model_copy(deep=True)
    reordered.transports.reverse()
    reordered.messages.reverse()
    for message in reordered.messages:
        message.fields.reverse()
    reordered = ProtocolIR.model_validate(reordered.model_dump(mode="json"))

    first_bundle = ProtocolGenerator().generate(first)
    reordered_bundle = ProtocolGenerator().generate(reordered)
    first_outputs = {output.path: output.content for output in first_bundle.outputs}
    reordered_outputs = {output.path: output.content for output in reordered_bundle.outputs}
    first_hashes = {output.path: output.content_hash for output in first_bundle.outputs}
    reordered_hashes = {output.path: output.content_hash for output in reordered_bundle.outputs}

    assert first.input_hash == reordered.input_hash
    assert first_outputs == reordered_outputs
    assert first_hashes == reordered_hashes


def test_can_arbitration_id_is_unique_per_transport_and_frame_kind() -> None:
    duplicate = protocol_with(
        messages=[
            ProtocolMessage(
                message_id=MESSAGE_ID,
                name="A",
                transport_ref="can0",
                can_id=0x201,
                payload_length_bytes=8,
            ),
            ProtocolMessage(
                message_id=uuid4(),
                name="B",
                transport_ref="can0",
                can_id=0x201,
                payload_length_bytes=8,
            ),
        ]
    )
    standard_and_extended = protocol_with(
        messages=[
            ProtocolMessage(
                message_id=MESSAGE_ID,
                name="Standard",
                transport_ref="can0",
                can_id=0x201,
                payload_length_bytes=8,
            ),
            ProtocolMessage(
                message_id=uuid4(),
                name="Extended",
                transport_ref="can0",
                can_id=0x201,
                extended_id=True,
                payload_length_bytes=8,
            ),
        ]
    )

    assert diagnostic_map(duplicate)["CAN_ID_VALID"] == "FAIL"
    assert diagnostic_map(standard_and_extended)["CAN_ID_VALID"] == "PASS"

    reused_on_different_transports = protocol_with(
        transports=[
            ProtocolTransport(transport_id="can0", name="CAN 0"),
            ProtocolTransport(transport_id="can1", name="CAN 1"),
        ],
        messages=[
            ProtocolMessage(
                message_id=MESSAGE_ID,
                name="Can0Status",
                transport_ref="can0",
                can_id=0x201,
                payload_length_bytes=8,
            ),
            ProtocolMessage(
                message_id=uuid4(),
                name="Can1Status",
                transport_ref="can1",
                can_id=0x201,
                payload_length_bytes=8,
            ),
        ],
    )
    assert diagnostic_map(reused_on_different_transports)["CAN_ID_VALID"] == "PASS"
    with pytest.raises(ProtocolGenerationError, match="duplicate arbitration keys"):
        ProtocolGenerator().generate(reused_on_different_transports)


def test_duplicate_transport_id_fails_closed_instead_of_being_overwritten() -> None:
    protocol = protocol_with(
        transports=[
            ProtocolTransport(transport_id="can0", name="Classic", can=CANTransportConfig()),
            ProtocolTransport(
                transport_id="can0",
                name="FD",
                can=CANTransportConfig(frame_kind="FD"),
            ),
        ]
    )

    assert diagnostic_map(protocol)["TRANSPORT_REFERENCE_VALID"] == "FAIL"


def test_identifier_normalization_is_collision_safe_and_c11_compiles(tmp_path: Path) -> None:
    protocol = protocol_with(
        messages=[
            ProtocolMessage(
                message_id=MESSAGE_ID,
                name="A-B",
                transport_ref="can0",
                can_id=1,
                payload_length_bytes=8,
                fields=[
                    ProtocolField(name="float", bit_offset=0, bit_length=8),
                    ProtocolField(name="struct", bit_offset=8, bit_length=8),
                    ProtocolField(name="for", bit_offset=16, bit_length=8),
                ],
            ),
            ProtocolMessage(
                message_id=uuid4(),
                name="A_B",
                transport_ref="can0",
                can_id=2,
                payload_length_bytes=8,
                fields=[
                    ProtocolField(name="Speed RPM", bit_offset=0, bit_length=8),
                    ProtocolField(name="Speed-RPM", bit_offset=8, bit_length=8),
                ],
            ),
        ]
    )
    bundle = ProtocolGenerator().generate(protocol)
    header = next(output.content for output in bundle.outputs if output.path == "protocol.h")
    source = next(output.content for output in bundle.outputs if output.path == "protocol.c")
    dbc = next(output.content for output in bundle.outputs if output.path == "protocol.dbc")
    (tmp_path / "protocol.h").write_text(header, encoding="utf-8")
    (tmp_path / "protocol.c").write_text(source, encoding="utf-8")
    compiler = shutil.which("gcc") or shutil.which("clang") or shutil.which("cc")
    assert compiler is not None
    result = subprocess.run(
        [
            compiler,
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-c",
            str(tmp_path / "protocol.c"),
            "-o",
            str(tmp_path / "protocol.o"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "double float;" not in header
    assert "eea_eea_float" not in header
    assert "eea_float" in header
    assert "BO_ 1 a_b: 8" in dbc
    assert "BO_ 2 a_b_2: 8" in dbc
    assert "SG_ speed_rpm :" in dbc
    assert "SG_ speed_rpm_2 :" in dbc


def _raw_boundary_protocol(*, signed: bool) -> ProtocolIR:
    return protocol_with(
        messages=[
            ProtocolMessage(
                message_id=MESSAGE_ID,
                name="Signed64" if signed else "Unsigned64",
                transport_ref="can0",
                can_id=1,
                payload_length_bytes=8,
                fields=[
                    ProtocolField(
                        name="value",
                        bit_offset=0,
                        bit_length=64,
                        signed=signed,
                    )
                ],
            )
        ]
    )


@pytest.mark.parametrize("value", [0, 1, 2**32, 2**53, 2**63, 2**64 - 1])
def test_reference_and_standalone_python_unsigned_64_raw_boundaries(
    value: int, tmp_path: Path
) -> None:
    protocol = _raw_boundary_protocol(signed=False)
    bundle = ProtocolGenerator().generate(protocol)
    python_output = next(output for output in bundle.outputs if output.path == "protocol_codec.py")
    module_path = tmp_path / python_output.path
    module_path.write_text(python_output.content, encoding="utf-8")
    namespace: dict[str, object] = {}
    exec(compile(python_output.content, str(module_path), "exec"), namespace)

    expected = value.to_bytes(8, "little", signed=False)
    reference = ReferenceProtocolCodec(protocol)
    assert reference.encode("Unsigned64", {"value": value}, raw_values=True) == expected
    assert reference.decode("Unsigned64", expected, raw_values=True)["value"] == value
    assert namespace["encode_unsigned64_raw"]({"value": value}) == expected  # type: ignore[operator]
    assert namespace["decode_unsigned64_raw"](expected)["value"] == value  # type: ignore[operator]


@pytest.mark.parametrize("value", [-(2**63), -(2**53), -1, 0, 2**53, 2**63 - 1])
def test_reference_and_standalone_python_signed_64_raw_boundaries(
    value: int, tmp_path: Path
) -> None:
    protocol = _raw_boundary_protocol(signed=True)
    bundle = ProtocolGenerator().generate(protocol)
    python_output = next(output for output in bundle.outputs if output.path == "protocol_codec.py")
    module_path = tmp_path / python_output.path
    module_path.write_text(python_output.content, encoding="utf-8")
    namespace: dict[str, object] = {}
    exec(compile(python_output.content, str(module_path), "exec"), namespace)

    expected = value.to_bytes(8, "little", signed=True)
    reference = ReferenceProtocolCodec(protocol)
    assert reference.encode("Signed64", {"value": value}, raw_values=True) == expected
    assert reference.decode("Signed64", expected, raw_values=True)["value"] == value
    assert namespace["encode_signed64_raw"]({"value": value}) == expected  # type: ignore[operator]
    assert namespace["decode_signed64_raw"](expected)["value"] == value  # type: ignore[operator]


def test_physical_codec_fails_closed_outside_ieee754_integer_safety() -> None:
    protocol = _raw_boundary_protocol(signed=False)
    codec = ReferenceProtocolCodec(protocol)

    with pytest.raises(ProtocolCodecError, match="raw_values=True"):
        codec.encode("Unsigned64", {"value": 2**53 + 1})
    payload = codec.encode("Unsigned64", {"value": 2**53 + 1}, raw_values=True)
    with pytest.raises(ProtocolCodecError, match="raw_values=True"):
        codec.decode("Unsigned64", payload)
    assert codec.decode("Unsigned64", payload, raw_values=True)["value"] == 2**53 + 1


def test_generated_c_codec_supports_unsigned_and_signed_64_raw_boundaries(tmp_path: Path) -> None:
    compiler = shutil.which("gcc") or shutil.which("clang") or shutil.which("cc")
    assert compiler is not None
    protocol = ProtocolIR(
        id=UUID("00000000-0000-0000-0000-000000000020"),
        project_id=PROJECT_ID,
        transports=[ProtocolTransport(transport_id="can0", name="CAN 0")],
        messages=[
            _raw_boundary_protocol(signed=False).messages[0],
            ProtocolMessage(
                message_id=uuid4(),
                name="Signed64",
                transport_ref="can0",
                can_id=2,
                payload_length_bytes=8,
                fields=[ProtocolField(name="value", bit_offset=0, bit_length=64, signed=True)],
            ),
        ],
    )
    bundle = ProtocolGenerator().generate(protocol)
    for output in bundle.outputs:
        if output.path in {"protocol.h", "protocol.c"}:
            (tmp_path / output.path).write_text(output.content, encoding="utf-8")
    harness = tmp_path / "raw64.c"
    harness.write_text(
        """
#include <stdint.h>
#include "protocol.h"

int main(void) {
    eea_unsigned64_raw_values_t u = { .value = UINT64_MAX };
    uint8_t payload[8];
    if (!eea_unsigned64_encode_raw(&u, payload, sizeof(payload))) return 2;
    eea_unsigned64_raw_values_t u_decoded;
    if (!eea_unsigned64_decode_raw(payload, sizeof(payload), &u_decoded)) return 3;
    if (u_decoded.value != UINT64_MAX) return 4;
    eea_signed64_raw_values_t s = { .value = INT64_MIN };
    if (!eea_signed64_encode_raw(&s, payload, sizeof(payload))) return 5;
    eea_signed64_raw_values_t s_decoded;
    if (!eea_signed64_decode_raw(payload, sizeof(payload), &s_decoded)) return 6;
    if (s_decoded.value != INT64_MIN) return 7;
    return 0;
}
""".strip(),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            compiler,
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(tmp_path / "protocol.c"),
            str(harness),
            "-o",
            str(tmp_path / "raw64.exe"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    run = subprocess.run([str(tmp_path / "raw64.exe")], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr


def test_protocol_repository_requires_project_scope_and_cas_conflict(
    settings, client: TestClient
) -> None:
    project = client.post("/api/v1/projects", json={"name": "Repository race"}).json()["data"]
    engine = create_database_engine(settings)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    first_session = sessions()
    second_session = sessions()
    try:
        first_repository = SqlAlchemyProtocolRepository(first_session)
        second_repository = SqlAlchemyProtocolRepository(second_session)
        initial = ProtocolIR(project_id=UUID(project["id"]), **protocol_api_payload())
        saved = first_repository.add(initial)
        first_snapshot = first_repository.get(saved.id, project_id=UUID(project["id"]))
        second_snapshot = second_repository.get(saved.id, project_id=UUID(project["id"]))
        assert first_snapshot is not None
        assert second_snapshot is not None
        assert first_repository.get(saved.id, project_id=uuid4()) is None

        first_update = first_snapshot.model_copy(update={"revision": 2})
        second_update = second_snapshot.model_copy(update={"revision": 2})
        first_result = first_repository.save(first_update, expected_revision=1)
        second_result = second_repository.save(second_update, expected_revision=1)

        assert first_result is not None
        assert second_result is None
    finally:
        first_session.close()
        second_session.close()
        engine.dispose()
