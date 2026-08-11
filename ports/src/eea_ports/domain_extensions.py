"""Framework-neutral plugin contracts for Domain Extension Infrastructure."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DomainValidationContext:
    """Opaque inputs supplied to a plugin-owned executable validator."""

    project_id: UUID
    domain_id: str
    inputs: Mapping[str, object]


class DomainExecutableValidator(Protocol):
    """Callable contract for deterministic, plugin-owned Domain validation."""

    def __call__(self, context: DomainValidationContext) -> Sequence[object]: ...


class DomainPlugin(Protocol):
    """A plugin supplies validated descriptor data and declarative contributions."""

    descriptor: object

    def rules(self) -> Sequence[object]: ...

    def generators(self) -> Sequence[object]: ...

    def contexts(self) -> Sequence[object]: ...

    def ui_extensions(self) -> Sequence[object]: ...

    def schema(self) -> dict[str, object]: ...

    def artifacts(self) -> Sequence[dict[str, Any]]: ...

    def executable_validator(self) -> DomainExecutableValidator | None: ...


__all__ = ["DomainExecutableValidator", "DomainPlugin", "DomainValidationContext"]
