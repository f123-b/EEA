"""Opaque secret references and the SecretService port."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SecretReference:
    name: str

    def __post_init__(self) -> None:
        if not self.name or len(self.name) > 200:
            raise ValueError("secret reference name must contain 1..200 characters")


class SecretValue:
    """A deliberately non-serializable value whose display is always redacted."""

    __slots__ = ("__value",)

    def __init__(self, value: str) -> None:
        if not value:
            raise ValueError("secret value cannot be empty")
        self.__value = value

    def reveal(self) -> str:
        """Reveal only at the final adapter call boundary."""

        return self.__value

    def __repr__(self) -> str:
        return "SecretValue(***)"

    def __str__(self) -> str:
        return "***"


class SecretService(Protocol):
    def is_configured(self, reference: SecretReference) -> bool: ...

    def get(self, reference: SecretReference) -> SecretValue: ...

    def set(self, reference: SecretReference, value: SecretValue) -> None: ...

    def delete(self, reference: SecretReference) -> None: ...
