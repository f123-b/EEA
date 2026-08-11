"""M2 LiteLLM and OS keyring adapter contract tests."""

import asyncio
from typing import Any

import pytest
from eea_adapters.ai.litellm import LiteLLMProvider
from eea_adapters.secrets import KeyringSecretService
from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_ports.ai import AIMessage, AIProviderRequest
from eea_ports.secrets import SecretReference, SecretValue


class FakeKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service_name: str, username: str) -> str | None:
        return self.values.get((service_name, username))

    def set_password(self, service_name: str, username: str, password: str) -> None:
        self.values[(service_name, username)] = password

    def delete_password(self, service_name: str, username: str) -> None:
        del self.values[(service_name, username)]


def test_keyring_secret_service_uses_opaque_references_and_redacted_values() -> None:
    backend = FakeKeyring()
    service = KeyringSecretService(backend=backend)
    reference = SecretReference("provider.default")
    secret = SecretValue("sk-private-value")

    assert service.is_configured(reference) is False
    service.set(reference, secret)
    assert service.is_configured(reference) is True
    resolved = service.get(reference)
    assert resolved.reveal() == "sk-private-value"
    assert str(resolved) == "***"
    assert repr(resolved) == "SecretValue(***)"
    service.delete(reference)
    assert service.is_configured(reference) is False

    with pytest.raises(EngineeringError) as captured:
        service.get(reference)
    assert captured.value.code is EngineeringErrorCode.CAPABILITY_UNAVAILABLE


def test_litellm_adapter_injects_secret_only_in_sdk_argument() -> None:
    backend = FakeKeyring()
    secrets = KeyringSecretService(backend=backend)
    reference = SecretReference("provider.default")
    secrets.set(reference, SecretValue("sk-private-value"))
    captured: dict[str, Any] = {}

    async def completion(**kwargs: object) -> object:
        captured.update(kwargs)
        return {
            "model": "resolved-model",
            "choices": [{"message": {"content": '{"answer":42}'}}],
            "usage": {
                "prompt_tokens": 7,
                "completion_tokens": 3,
                "total_tokens": 10,
                "cost": 0.05,
            },
        }

    provider = LiteLLMProvider(
        secrets,
        reference,
        model_map={"requested-model": "concrete-model"},
        completion=completion,
    )
    response = asyncio.run(
        provider.generate(
            AIProviderRequest(
                model="requested-model",
                messages=(
                    AIMessage(role="system", content="Return JSON"),
                    AIMessage(role="user", content='{"question":"test"}'),
                ),
                response_schema={"type": "object"},
                temperature=0,
                max_output_tokens=50,
                timeout_seconds=2,
                metadata={"prompt_name": "test.structured"},
            )
        )
    )

    assert captured["api_key"] == "sk-private-value"
    assert "sk-private-value" not in repr(captured["messages"])
    assert "sk-private-value" not in repr(captured["response_format"])
    assert response.content == '{"answer":42}'
    assert response.model == "resolved-model"
    assert response.usage.total_tokens == 10


def test_litellm_adapter_sanitizes_provider_exceptions() -> None:
    backend = FakeKeyring()
    secrets = KeyringSecretService(backend=backend)
    reference = SecretReference("provider.default")
    secrets.set(reference, SecretValue("sk-private-value"))

    async def completion(**_: object) -> object:
        raise RuntimeError("provider echoed sk-private-value")

    provider = LiteLLMProvider(
        secrets,
        reference,
        model_map={"model": "concrete-model"},
        completion=completion,
    )
    request = AIProviderRequest(
        model="model",
        messages=(AIMessage(role="user", content="safe"),),
        response_schema={"type": "object"},
        temperature=0,
        max_output_tokens=10,
        timeout_seconds=1,
    )

    with pytest.raises(EngineeringError) as captured:
        asyncio.run(provider.generate(request))

    assert captured.value.code is EngineeringErrorCode.AI_PROVIDER_UNAVAILABLE
    assert "sk-private-value" not in str(captured.value)
    assert "sk-private-value" not in repr(captured.value.details)
