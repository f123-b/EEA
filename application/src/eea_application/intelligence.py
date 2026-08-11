"""M4 document ingestion, claim extraction, and multi-source device merging."""

import hashlib
from collections.abc import Iterable
from pathlib import Path
from typing import cast
from uuid import UUID

from eea_core.claims import EngineeringClaim
from eea_core.enums import DeviceMergeConflictType, DocumentType, EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_core.intelligence import (
    Device,
    DeviceMergeConflict,
    DeviceMergeResult,
    DevicePin,
    Document,
    DocumentIR,
)
from eea_core.repositories import DocumentIRRepository, DocumentRepository
from eea_ports.intelligence import ClaimExtractor, DeviceProvider, DocumentParser


class DocumentService:
    """Store source bytes under a content-addressed, application-owned directory."""

    def __init__(self, repository: DocumentRepository, storage_root: Path) -> None:
        self._repository = repository
        self._storage_root = storage_root

    def upload(
        self,
        content: bytes,
        *,
        filename: str,
        project_id: UUID | None = None,
        document_type: DocumentType = DocumentType.UNKNOWN,
        vendor: str | None = None,
        product: str | None = None,
        version_label: str | None = None,
    ) -> Document:
        if not content:
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR,
                "Uploaded document must not be empty",
            )
        digest = hashlib.sha256(content).hexdigest()
        directory = self._storage_root / "documents"
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{digest}.bin"
        if not target.exists():
            target.write_bytes(content)
        document = Document(
            project_id=project_id,
            filename=filename,
            document_type=document_type,
            vendor=vendor,
            product=product,
            version_label=version_label,
            content_hash=digest,
            storage_uri=str(target),
        )
        return self._repository.add(document)

    def get(self, document_id: UUID) -> Document:
        document = self._repository.get(document_id)
        if document is None:
            raise EngineeringError(
                EngineeringErrorCode.DOCUMENT_PARSE_FAILED,
                "Document was not found",
                details={"document_id": str(document_id)},
            )
        return document

    def parse(
        self,
        document: Document,
        parser: DocumentParser,
        ir_repository: DocumentIRRepository,
    ) -> DocumentIR:
        try:
            content = Path(document.storage_uri).read_bytes()
            parsed = parser.parse(document, content)
            document_ir = cast(DocumentIR, parsed)
            if document_ir.document_id != document.id:
                raise ValueError("parser returned an IR for another document")
            return ir_repository.add(document_ir)
        except EngineeringError:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise EngineeringError(
                EngineeringErrorCode.DOCUMENT_PARSE_FAILED,
                "Document parsing failed",
                details={"reason": type(exc).__name__},
            ) from None


class DocumentClaimExtractionService:
    """Validate adapter-produced claims before they enter the Claim Core."""

    def __init__(self, extractor: ClaimExtractor) -> None:
        self._extractor = extractor

    def extract(self, document_ir: DocumentIR) -> list[EngineeringClaim]:
        raw_claims = self._extractor.extract(document_ir)
        claims: list[EngineeringClaim] = []
        for raw in raw_claims:
            if not isinstance(raw, EngineeringClaim):
                raise EngineeringError(
                    EngineeringErrorCode.VALIDATION_ERROR,
                    "Claim extractor returned an invalid claim",
                    details={"extractor": self._extractor.name},
                )
            claims.append(raw)
        return claims


class DeviceMergeService:
    """Merge same-device sources without silently losing contradictory facts."""

    def merge(self, sources: list[Device]) -> DeviceMergeResult:
        if not sources:
            raise EngineeringError(
                EngineeringErrorCode.DEVICE_NOT_FOUND,
                "At least one device source is required",
            )
        first = sources[0]
        if any(
            (source.manufacturer, source.family, source.model)
            != (first.manufacturer, first.family, first.model)
            for source in sources[1:]
        ):
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR,
                "Device sources do not identify the same device",
            )
        conflicts: list[DeviceMergeConflict] = []
        source_refs = self._unique(value for source in sources for value in source.source_refs)
        packages = self._unique(value for source in sources for value in source.packages)
        peripherals = self._unique(value for source in sources for value in source.peripherals)
        pins = self._merge_pins(sources, conflicts)
        memory = self._merge_mapping(sources, "memory", conflicts)
        clocks = self._merge_mapping(sources, "clocks", conflicts)
        dma = self._merge_mapping(sources, "dma", conflicts)
        interrupts = self._merge_mapping(sources, "interrupts", conflicts)
        electrical = self._merge_mapping(sources, "electrical", conflicts)
        merged = first.model_copy(
            update={
                "packages": packages,
                "peripherals": peripherals,
                "pins": pins,
                "memory": memory,
                "clocks": clocks,
                "dma": dma,
                "interrupts": interrupts,
                "electrical": electrical,
                "source_refs": source_refs,
                "claim_ids": self._unique_uuid(
                    value for source in sources for value in source.claim_ids
                ),
            }
        )
        return DeviceMergeResult(device=merged, conflicts=conflicts)

    @staticmethod
    def _unique(values: Iterable[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            if value not in result:
                result.append(value)
        return result

    @staticmethod
    def _unique_uuid(values: Iterable[UUID]) -> list[UUID]:
        result: list[UUID] = []
        for value in values:
            if value not in result:
                result.append(value)
        return result

    def _merge_mapping(
        self, sources: list[Device], field: str, conflicts: list[DeviceMergeConflict]
    ) -> dict[str, object]:
        merged: dict[str, object] = {}
        owners: dict[str, str] = {}
        for source in sources:
            values = cast(dict[str, object], getattr(source, field))
            source_ref = source.source_refs[0] if source.source_refs else "source"
            for key, value in values.items():
                if key in merged and merged[key] != value:
                    conflicts.append(
                        DeviceMergeConflict(
                            conflict_type=DeviceMergeConflictType.SCALAR_MISMATCH,
                            field=f"{field}.{key}",
                            source_a=owners[key],
                            source_b=source_ref,
                            value_a=merged[key],
                            value_b=value,
                            resolution="kept first source value and retained conflict",
                        )
                    )
                    continue
                merged[key] = value
                owners[key] = source_ref
        return merged

    def _merge_pins(
        self, sources: list[Device], conflicts: list[DeviceMergeConflict]
    ) -> list[DevicePin]:
        by_name: dict[str, DevicePin] = {}
        owners: dict[str, str] = {}
        for source in sources:
            source_ref = source.source_refs[0] if source.source_refs else "source"
            for pin in source.pins:
                if pin.name not in by_name:
                    by_name[pin.name] = pin
                    owners[pin.name] = source_ref
                    continue
                current = by_name[pin.name]
                functions = list(current.functions)
                for function in pin.functions:
                    if function not in functions:
                        if functions:
                            conflicts.append(
                                DeviceMergeConflict(
                                    conflict_type=DeviceMergeConflictType.PIN_FUNCTION_MISMATCH,
                                    field=f"pins.{pin.name}.functions",
                                    source_a=owners[pin.name],
                                    source_b=source_ref,
                                    value_a=[item.model_dump() for item in functions],
                                    value_b=function.model_dump(),
                                    resolution="unioned functions and retained conflict",
                                )
                            )
                        functions.append(function)
                by_name[pin.name] = current.model_copy(
                    update={
                        "functions": functions,
                        "source_refs": self._unique([*current.source_refs, *pin.source_refs]),
                    }
                )
        return list(by_name.values())


class MultiSourceDeviceProvider:
    """Query several providers and expose one merged, auditable device view."""

    name = "multi-source-device/v1"

    def __init__(
        self, providers: list[DeviceProvider], merger: DeviceMergeService | None = None
    ) -> None:
        self._providers = providers
        self._merger = merger or DeviceMergeService()

    def get_device(self, device_ref: str, *, package: str | None = None) -> Device | None:
        devices = [
            device
            for provider in self._providers
            if isinstance(device := provider.get_device(device_ref, package=package), Device)
        ]
        if not devices:
            return None
        return self._merger.merge(devices).device

    def query_pin(
        self,
        device_ref: str,
        pin_name: str,
        *,
        package: str | None = None,
        peripheral: str | None = None,
        signal: str | None = None,
    ) -> DevicePin:
        device = self.get_device(device_ref, package=package)
        if device is None:
            raise EngineeringError(
                EngineeringErrorCode.DEVICE_NOT_FOUND,
                "No provider returned the requested device",
                details={"device_ref": device_ref},
            )
        pin = next((item for item in device.pins if item.name == pin_name), None)
        if pin is None:
            raise EngineeringError(
                EngineeringErrorCode.DEVICE_NOT_FOUND,
                "Pin was not found for the merged device",
                details={"device_ref": device_ref, "pin": pin_name},
            )
        if (peripheral is not None or signal is not None) and not any(
            item.peripheral == peripheral and item.signal == signal for item in pin.functions
        ):
            raise EngineeringError(
                EngineeringErrorCode.PIN_FUNCTION_INVALID,
                "Merged device pin does not support the requested function",
                details={"pin": pin_name, "peripheral": peripheral, "signal": signal},
            )
        return pin
