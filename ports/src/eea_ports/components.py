"""Framework-free ports for embedded software component providers."""

from pathlib import Path
from typing import Any, Protocol


class ComponentProvider(Protocol):
    provider_id: str

    def descriptors(self) -> tuple[Any, ...]: ...

    def releases(self, component_id: object) -> tuple[Any, ...]: ...

    def materialize(self, release: Any, destination: Path) -> Any: ...


__all__ = ["ComponentProvider"]
