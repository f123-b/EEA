"""SQLAlchemy adapters for M4 document and DocumentIR persistence."""

from typing import Any, cast
from uuid import UUID

from eea_core.enums import DocumentParseStatus, DocumentType
from eea_core.intelligence import (
    Document,
    DocumentFigure,
    DocumentIR,
    DocumentPage,
    DocumentSection,
    DocumentTable,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from eea_backend.models import DocumentIRRecord, DocumentRecord


def _entity_kwargs(record: DocumentRecord | DocumentIRRecord) -> dict[str, Any]:
    return {
        "id": UUID(record.id),
        "schema_version": record.schema_version,
        "revision": record.revision,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "metadata": record.entity_metadata,
    }


def _to_document(record: DocumentRecord) -> Document:
    return Document(
        **_entity_kwargs(record),
        project_id=UUID(record.project_id) if record.project_id else None,
        filename=record.filename,
        document_type=DocumentType(record.document_type),
        vendor=record.vendor,
        product=record.product,
        version_label=record.version_label,
        content_hash=record.content_hash,
        storage_uri=record.storage_uri,
        parse_status=DocumentParseStatus(record.parse_status),
        parse_error=record.parse_error,
    )


class SqlAlchemyDocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, document: Document) -> Document:
        record = DocumentRecord(
            id=str(document.id),
            schema_version=document.schema_version,
            revision=document.revision,
            created_at=document.created_at,
            updated_at=document.updated_at,
            entity_metadata=document.metadata,
            project_id=str(document.project_id) if document.project_id else None,
            filename=document.filename,
            document_type=document.document_type.value,
            vendor=document.vendor,
            product=document.product,
            version_label=document.version_label,
            content_hash=document.content_hash,
            storage_uri=document.storage_uri,
            parse_status=document.parse_status.value,
            parse_error=document.parse_error,
        )
        self._session.add(record)
        try:
            self._session.commit()
        except IntegrityError:
            self._session.rollback()
            existing = self._session.scalar(
                select(DocumentRecord).where(DocumentRecord.content_hash == document.content_hash)
            )
            if existing is None:
                raise
            return _to_document(existing)
        self._session.refresh(record)
        return _to_document(record)

    def get(self, document_id: UUID) -> Document | None:
        record = self._session.get(DocumentRecord, str(document_id))
        return _to_document(record) if record else None


def _to_document_ir(record: DocumentIRRecord) -> DocumentIR:
    return DocumentIR(
        **_entity_kwargs(record),
        document_id=UUID(record.document_id),
        parser=record.parser,
        parser_version=record.parser_version,
        pages=[DocumentPage.model_validate(item) for item in record.pages],
        sections=[DocumentSection.model_validate(item) for item in record.sections],
        tables=[DocumentTable.model_validate(item) for item in record.tables],
        figures=[DocumentFigure.model_validate(item) for item in record.figures],
        extracted_claim_ids=[UUID(value) for value in record.extracted_claim_ids],
    )


class SqlAlchemyDocumentIRRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, document_ir: DocumentIR) -> DocumentIR:
        payload = document_ir.model_dump(mode="json")
        record = self._session.scalar(
            select(DocumentIRRecord).where(
                DocumentIRRecord.document_id == str(document_ir.document_id)
            )
        )
        if record is None:
            record = DocumentIRRecord(
                id=str(document_ir.id),
                schema_version=document_ir.schema_version,
                revision=document_ir.revision,
                created_at=document_ir.created_at,
                updated_at=document_ir.updated_at,
                entity_metadata=document_ir.metadata,
                document_id=str(document_ir.document_id),
                parser=document_ir.parser,
                parser_version=document_ir.parser_version,
                pages=cast(list[dict[str, Any]], payload["pages"]),
                sections=cast(list[dict[str, Any]], payload["sections"]),
                tables=cast(list[dict[str, Any]], payload["tables"]),
                figures=cast(list[dict[str, Any]], payload["figures"]),
                extracted_claim_ids=[str(value) for value in document_ir.extracted_claim_ids],
            )
            self._session.add(record)
        else:
            record.revision = document_ir.revision
            record.updated_at = document_ir.updated_at
            record.entity_metadata = document_ir.metadata
            record.parser = document_ir.parser
            record.parser_version = document_ir.parser_version
            record.pages = cast(list[dict[str, Any]], payload["pages"])
            record.sections = cast(list[dict[str, Any]], payload["sections"])
            record.tables = cast(list[dict[str, Any]], payload["tables"])
            record.figures = cast(list[dict[str, Any]], payload["figures"])
            record.extracted_claim_ids = [str(value) for value in document_ir.extracted_claim_ids]
        self._session.commit()
        self._session.refresh(record)
        return _to_document_ir(record)

    def get_for_document(self, document_id: UUID) -> DocumentIR | None:
        record = self._session.scalar(
            select(DocumentIRRecord).where(DocumentIRRecord.document_id == str(document_id))
        )
        return _to_document_ir(record) if record else None
