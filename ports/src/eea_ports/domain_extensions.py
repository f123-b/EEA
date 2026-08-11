"""Framework-neutral plugin contracts for Domain Extension Infrastructure."""

from collections.abc import Sequence
from typing import Any, Protocol


class DomainPlugin(Protocol):
    """A plugin supplies validated descriptor data and declarative contributions."""

    descriptor: object

    def rules(self) -> Sequence[object]: ...

    def generators(self) -> Sequence[object]: ...

    def contexts(self) -> Sequence[object]: ...

    def ui_extensions(self) -> Sequence[object]: ...

    def schema(self) -> dict[str, object]: ...

    def artifacts(self) -> Sequence[dict[str, Any]]: ...


__all__ = ["DomainPlugin"]
