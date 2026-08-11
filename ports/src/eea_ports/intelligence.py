"""Framework-free ports for document and device adapters."""

from typing import Protocol


class DocumentParser(Protocol):
    name: str
    version: str

    def parse(self, document: object, content: bytes) -> object: ...


class ClaimExtractor(Protocol):
    name: str

    def extract(self, document_ir: object) -> list[object]: ...


class DeviceProvider(Protocol):
    name: str

    def get_device(self, device_ref: str, *, package: str | None = None) -> object | None: ...

    def query_pin(
        self,
        device_ref: str,
        pin_name: str,
        *,
        package: str | None = None,
        peripheral: str | None = None,
        signal: str | None = None,
    ) -> object: ...
