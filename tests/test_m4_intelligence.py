"""M4 Document + Device Intelligence acceptance tests."""

import base64
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from eea_adapters.devices import Stm32G431FixtureProvider
from eea_adapters.documents import DeterministicClaimExtractor, DoclingDocumentParser
from eea_application.intelligence import (
    DeviceMergeService,
    DocumentClaimExtractionService,
    DocumentService,
)
from eea_backend.database import create_database_engine
from eea_backend.document_repositories import (
    SqlAlchemyDocumentIRRepository,
    SqlAlchemyDocumentRepository,
)
from eea_backend.settings import Settings
from eea_core.claims import EngineeringClaim
from eea_core.enums import (
    ClaimLifecycle,
    DeviceMergeConflictType,
    DocumentType,
    EngineeringErrorCode,
    VerificationLevel,
)
from eea_core.errors import EngineeringError
from eea_core.intelligence import Document, DocumentIR, DocumentPage, PinFunction
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


class MemoryDocumentRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, object] = {}

    def add(self, document: object) -> object:
        self.items[document.id] = document  # type: ignore[attr-defined]
        return document

    def get(self, document_id: UUID) -> object | None:
        return self.items.get(document_id)


class MemoryDocumentIRRepository:
    def __init__(self) -> None:
        self.item: DocumentIR | None = None

    def add(self, document_ir: DocumentIR) -> DocumentIR:
        self.item = document_ir
        return document_ir

    def get_for_document(self, document_id: UUID) -> DocumentIR | None:
        return self.item if self.item and self.item.document_id == document_id else None


def test_docling_adapter_and_upload_preserve_document_locations(tmp_path: Path) -> None:
    documents = MemoryDocumentRepository()
    irs = MemoryDocumentIRRepository()
    service = DocumentService(cast(object, documents), tmp_path)
    document = service.upload(
        b"datasheet content",
        filename="stm32.pdf",
        document_type=DocumentType.DATASHEET,
        vendor="STMicroelectronics",
        product="STM32G431",
        version_label="Rev A",
    )
    parser = DoclingDocumentParser(
        lambda _document, _content: {
            "pages": [{"page_number": 1, "text": "PA8 TIM1_CH1"}],
            "sections": [
                {
                    "section_id": "s1",
                    "title": "Alternate functions",
                    "page_start": 1,
                    "page_end": 1,
                    "text": "PA8 TIM1_CH1",
                }
            ],
        }
    )
    parsed = service.parse(document, parser, cast(object, irs))

    assert parsed.document_id == document.id
    assert parsed.pages[0].page_number == 1
    assert parsed.sections[0].title == "Alternate functions"
    assert irs.get_for_document(document.id) == parsed


def test_docling_adapter_reports_missing_optional_runtime() -> None:
    document = next(iter(MemoryDocumentRepository().items.values()), None)
    assert document is None
    with pytest.raises(EngineeringError) as error:
        DoclingDocumentParser()._load_converter()
    assert error.value.code in {
        EngineeringErrorCode.CAPABILITY_UNAVAILABLE,
        EngineeringErrorCode.DOCUMENT_PARSE_FAILED,
    }


def test_document_claim_extraction_preserves_claim_contract() -> None:
    document_ir = DocumentIR(parser="fixture", parser_version="1", document_id=UUID(int=1))
    claim = EngineeringClaim(
        subject_ref="document:1",
        predicate="device.model",
        value="STM32G431",
        confidence=0.9,
        source_priority=100,
        lifecycle=ClaimLifecycle.CANDIDATE,
    )
    extractor = DeterministicClaimExtractor({document_ir.document_id: [claim]})
    result = DocumentClaimExtractionService(extractor).extract(document_ir)
    assert result == [claim]

    verified = claim.model_copy(
        update={"verification_levels": [VerificationLevel.DOCUMENT_VERIFIED]}
    )
    with pytest.raises(ValueError, match="evidence"):
        EngineeringClaim.model_validate(verified.model_dump())


def test_stm32_provider_covers_m4_queries_and_rejects_invalid_af() -> None:
    provider = Stm32G431FixtureProvider()
    device = provider.get_device("STM32G431", package="UFQFPN48")
    assert device is not None
    assert {"TIM1", "FDCAN1", "ADC1", "DMA1"} <= set(device.peripherals)

    pwm_pin = provider.query_pin("STM32G431", "PA8", peripheral="TIM1", signal="CH1")
    assert pwm_pin.functions[0].alternate_function == "AF6"
    complementary = provider.query_pin("STM32G431", "PB13", peripheral="TIM1", signal="CH1N")
    assert complementary.functions[0].signal == "CH1N"
    assert provider.query_pin("STM32G431", "PA11", peripheral="FDCAN1", signal="RX")
    assert provider.query_pin("STM32G431", "PA0", peripheral="ADC1", signal="IN1")

    with pytest.raises(EngineeringError) as error:
        provider.query_pin("STM32G431", "PA8", peripheral="TIM1", signal="CH2")
    assert error.value.code is EngineeringErrorCode.PIN_FUNCTION_INVALID


def test_document_and_document_ir_sql_roundtrip(settings: Settings) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    command.upgrade(config, "head")
    engine = create_database_engine(settings)
    try:
        document = Document(
            filename="roundtrip.pdf",
            content_hash="a" * 64,
            storage_uri="D:/data/roundtrip.pdf",
        )
        with Session(engine) as session:
            saved = SqlAlchemyDocumentRepository(session).add(document)
            ir = DocumentIR(
                document_id=saved.id,
                parser="fixture",
                parser_version="1",
                pages=[DocumentPage(page_number=1, text="content")],
            )
            SqlAlchemyDocumentIRRepository(session).add(ir)
            assert SqlAlchemyDocumentRepository(session).get(saved.id) == saved
            loaded_ir = SqlAlchemyDocumentIRRepository(session).get_for_document(saved.id)
            assert loaded_ir is not None
            assert loaded_ir.pages[0].text == "content"
    finally:
        engine.dispose()


def test_multi_source_merge_retains_conflicts_and_unions_functions() -> None:
    first = Stm32G431FixtureProvider().get_device("STM32G431")
    assert first is not None
    second = first.model_copy(
        update={
            "source_refs": ["vendor-structured/v2"],
            "pins": [
                pin.model_copy(
                    update={
                        "functions": [
                            *pin.functions,
                            PinFunction(peripheral="GPIOA", signal="IO", alternate_function=None),
                        ],
                        "source_refs": ["vendor-structured/v2"],
                    }
                )
                if pin.name == "PA8"
                else pin
                for pin in first.pins
            ],
        }
    )
    result = DeviceMergeService().merge([first, second])
    assert result.device.source_refs == ["stm32-structured-fixture/v1", "vendor-structured/v2"]
    pa8 = next(pin for pin in result.device.pins if pin.name == "PA8")
    assert {function.signal for function in pa8.functions} == {"CH1", "IO"}
    assert any(
        conflict.conflict_type is DeviceMergeConflictType.PIN_FUNCTION_MISMATCH
        for conflict in result.conflicts
    )


def test_api_document_upload_and_device_query(client: TestClient) -> None:
    response = client.post(
        "/api/v1/documents",
        json={
            "filename": "fixture.pdf",
            "content_base64": base64.b64encode(b"fixture").decode(),
            "document_type": "DATASHEET",
        },
    )
    assert response.status_code == 201
    document = response.json()["data"]
    assert document["parse_status"] == "UPLOADED"
    fetched = client.get(f"/api/v1/documents/{document['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["content_hash"] == document["content_hash"]

    pin = client.get(
        "/api/v1/devices/STM32G431/pins/PA8",
        params={"package": "UFQFPN48", "peripheral": "TIM1", "signal": "CH1"},
    )
    assert pin.status_code == 200
    assert pin.json()["data"]["pin"]["name"] == "PA8"

    invalid = client.get(
        "/api/v1/devices/STM32G431/pins/PA8",
        params={"peripheral": "TIM1", "signal": "CH2"},
    )
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "PIN_FUNCTION_INVALID"
