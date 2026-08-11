"""OS keyring-backed SecretService adapter."""

from importlib import import_module
from typing import Protocol, cast

from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_ports.secrets import SecretReference, SecretValue


class KeyringBackend(Protocol):
    def get_password(self, service_name: str, username: str) -> str | None: ...

    def set_password(self, service_name: str, username: str, password: str) -> None: ...

    def delete_password(self, service_name: str, username: str) -> None: ...


class KeyringSecretService:
    """Store only opaque references outside the operating-system keyring."""

    def __init__(
        self,
        service_name: str = "embedded-engineering-agent",
        *,
        backend: KeyringBackend | None = None,
    ) -> None:
        self._service_name = service_name
        self._backend = backend

    def is_configured(self, reference: SecretReference) -> bool:
        return self._keyring().get_password(self._service_name, reference.name) is not None

    def get(self, reference: SecretReference) -> SecretValue:
        value = self._keyring().get_password(self._service_name, reference.name)
        if value is None:
            raise EngineeringError(
                EngineeringErrorCode.CAPABILITY_UNAVAILABLE,
                "Required secret is not configured",
                details={"secret_reference": reference.name},
            )
        return SecretValue(value)

    def set(self, reference: SecretReference, value: SecretValue) -> None:
        self._keyring().set_password(self._service_name, reference.name, value.reveal())

    def delete(self, reference: SecretReference) -> None:
        if self.is_configured(reference):
            self._keyring().delete_password(self._service_name, reference.name)

    def _keyring(self) -> KeyringBackend:
        if self._backend is not None:
            return self._backend
        try:
            self._backend = cast(KeyringBackend, import_module("keyring"))
        except ImportError:
            raise EngineeringError(
                EngineeringErrorCode.CAPABILITY_UNAVAILABLE,
                "OS keyring adapter is not installed",
                details={"install_extra": "ai"},
            ) from None
        return self._backend
