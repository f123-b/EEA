"""Docling boundary adapter.

The optional Docling SDK is loaded only at the adapter boundary. Tests and
offline deployments can inject a deterministic converter returning the small
mapping documented by ``_coerce_ir``.
"""

from collections.abc import Callable, Mapping
from importlib import import_module
from typing import cast
from uuid import UUID

from eea_core.entities import utc_now
from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_core.intelligence import Document, DocumentIR

Converter = Callable[[Document, bytes], object]


class DoclingDocumentParser:
    """Translate a Docling conversion result into the versioned DocumentIR."""

    name = "docling"
    version = "adapter-v1"

    def __init__(self, converter: Converter | None = None) -> None:
        self._converter = converter

    def parse(self, document: Document, content: bytes) -> DocumentIR:
        converter = self._converter or self._load_converter()
        try:
            raw = converter(document, content)
            return self._coerce_ir(document, raw)
        except EngineeringError:
            raise
        except (TypeError, ValueError, KeyError) as exc:
            raise EngineeringError(
                EngineeringErrorCode.DOCUMENT_PARSE_FAILED,
                "Docling output could not be converted to DocumentIR",
                details={"reason": type(exc).__name__},
            ) from None

    @staticmethod
    def _load_converter() -> Converter:
        try:
            import_module("docling")
        except ImportError:
            raise EngineeringError(
                EngineeringErrorCode.CAPABILITY_UNAVAILABLE,
                "Docling adapter is not installed",
                details={"install_extra": "documents"},
            ) from None
        raise EngineeringError(
            EngineeringErrorCode.DOCUMENT_PARSE_FAILED,
            "Docling runtime requires an application-configured converter",
        )

    @staticmethod
    def _coerce_ir(document: Document, raw: object) -> DocumentIR:
        if isinstance(raw, DocumentIR):
            if raw.document_id != document.id:
                raise ValueError("DocumentIR document_id does not match source document")
            return raw
        if not isinstance(raw, Mapping):
            raise TypeError("converter must return DocumentIR or a mapping")
        payload = dict(cast(Mapping[str, object], raw))
        payload.setdefault("document_id", document.id)
        payload.setdefault("parser", DoclingDocumentParser.name)
        payload.setdefault("parser_version", DoclingDocumentParser.version)
        payload.setdefault("id", document.id)
        payload.setdefault("schema_version", "1.0")
        payload.setdefault("revision", 1)
        payload.setdefault("created_at", utc_now())
        payload.setdefault("updated_at", utc_now())
        payload.setdefault("metadata", {})
        return DocumentIR.model_validate(payload)


class DeterministicClaimExtractor:
    """Extract claim payloads supplied by a deterministic document fixture.

    A production extractor can replace this adapter with M2 structured
    generation while preserving the same claim/evidence boundary.
    """

    name = "document-claim-fixture/v1"

    def __init__(self, claims_by_document: Mapping[UUID, list[object]]) -> None:
        self._claims_by_document = claims_by_document

    def extract(self, document_ir: object) -> list[object]:
        if not isinstance(document_ir, DocumentIR):
            raise TypeError("claim extraction requires DocumentIR")
        return list(self._claims_by_document.get(document_ir.document_id, []))
