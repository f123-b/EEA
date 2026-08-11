"""M4 document and device intelligence contracts.

The Core owns the versioned intermediate representations. Parsing and vendor data
remain adapter concerns and are intentionally represented by source references.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from eea_core.entities import EntityBase, Sha256
from eea_core.enums import (
    DeviceCategory,
    DeviceMergeConflictType,
    DocumentParseStatus,
    DocumentType,
)


class Document(EntityBase):
    """Uploaded, immutable source-document metadata."""

    project_id: UUID | None = None
    filename: str = Field(min_length=1, max_length=500)
    document_type: DocumentType = DocumentType.UNKNOWN
    vendor: str | None = Field(default=None, max_length=200)
    product: str | None = Field(default=None, max_length=200)
    version_label: str | None = Field(default=None, max_length=100)
    content_hash: Sha256
    storage_uri: str = Field(min_length=1, max_length=2000)
    parse_status: DocumentParseStatus = DocumentParseStatus.UPLOADED
    parse_error: str | None = Field(default=None, max_length=4000)


class DocumentPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1)
    text: str = ""


class DocumentSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    text: str = ""

    @model_validator(mode="after")
    def page_range_is_ordered(self) -> "DocumentSection":
        if self.page_end < self.page_start:
            raise ValueError("section page_end cannot precede page_start")
        return self


class DocumentTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_id: str = Field(min_length=1, max_length=200)
    page_number: int = Field(ge=1)
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class DocumentFigure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    figure_id: str = Field(min_length=1, max_length=200)
    page_number: int = Field(ge=1)
    caption: str = ""


class DocumentIR(EntityBase):
    """Auditable parsed document representation with source locations."""

    document_id: UUID
    parser: str = Field(min_length=1, max_length=200)
    parser_version: str = Field(min_length=1, max_length=100)
    pages: list[DocumentPage] = Field(default_factory=list)
    sections: list[DocumentSection] = Field(default_factory=list)
    tables: list[DocumentTable] = Field(default_factory=list)
    figures: list[DocumentFigure] = Field(default_factory=list)
    extracted_claim_ids: list[UUID] = Field(default_factory=list)


class PinFunction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    peripheral: str = Field(min_length=1, max_length=100)
    signal: str = Field(min_length=1, max_length=100)
    alternate_function: str | None = Field(default=None, max_length=50)


class DevicePin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=50)
    package: str | None = Field(default=None, max_length=100)
    package_pin: str | None = Field(default=None, max_length=30)
    voltage_domain: str | None = Field(default=None, max_length=50)
    five_v_tolerant: bool | None = None
    functions: list[PinFunction] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    claim_ids: list[UUID] = Field(default_factory=list)


class Device(EntityBase):
    """Vendor/device fact representation assembled from authoritative sources."""

    manufacturer: str = Field(min_length=1, max_length=200)
    family: str = Field(min_length=1, max_length=200)
    model: str = Field(min_length=1, max_length=200)
    revision_label: str | None = Field(default=None, max_length=100)
    category: DeviceCategory = DeviceCategory.UNKNOWN
    packages: list[str] = Field(default_factory=list)
    memory: dict[str, object] = Field(default_factory=dict)
    peripherals: list[str] = Field(default_factory=list)
    pins: list[DevicePin] = Field(default_factory=list)
    clocks: dict[str, object] = Field(default_factory=dict)
    dma: dict[str, object] = Field(default_factory=dict)
    interrupts: dict[str, object] = Field(default_factory=dict)
    electrical: dict[str, object] = Field(default_factory=dict)
    source_refs: list[str] = Field(default_factory=list)
    claim_ids: list[UUID] = Field(default_factory=list)


class DeviceMergeConflict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conflict_type: DeviceMergeConflictType
    field: str = Field(min_length=1, max_length=300)
    source_a: str = Field(min_length=1, max_length=300)
    source_b: str = Field(min_length=1, max_length=300)
    value_a: object
    value_b: object
    resolution: str = Field(min_length=1, max_length=1000)


class DeviceMergeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device: Device
    conflicts: list[DeviceMergeConflict] = Field(default_factory=list)
