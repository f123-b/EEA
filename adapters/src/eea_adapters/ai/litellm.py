"""LiteLLM adapter with credential injection confined to the call boundary."""

from collections.abc import Awaitable, Callable, Mapping
from decimal import Decimal
from importlib import import_module
from typing import cast

from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_ports.ai import AIProviderRequest, AIProviderResponse, ProviderUsage
from eea_ports.secrets import SecretReference, SecretService

CompletionCallable = Callable[..., Awaitable[object]]


class LiteLLMProvider:
    """Translate the stable AIProvider contract to LiteLLM's completion API."""

    name = "litellm"

    def __init__(
        self,
        secret_service: SecretService,
        api_key_reference: SecretReference,
        *,
        completion: CompletionCallable | None = None,
    ) -> None:
        self._secret_service = secret_service
        self._api_key_reference = api_key_reference
        self._completion = completion

    async def generate(self, request: AIProviderRequest) -> AIProviderResponse:
        completion = self._completion or self._load_completion()
        try:
            secret = self._secret_service.get(self._api_key_reference)
            raw_response = await completion(
                model=request.model,
                messages=[
                    {"role": message.role, "content": message.content}
                    for message in request.messages
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": request.metadata.get("prompt_name", "structured_output"),
                        "schema": request.response_schema,
                        "strict": True,
                    },
                },
                temperature=request.temperature,
                max_tokens=request.max_output_tokens,
                timeout=request.timeout_seconds,
                api_key=secret.reveal(),
            )
            return self._translate(raw_response, fallback_model=request.model)
        except EngineeringError:
            raise
        except Exception as exc:
            raise EngineeringError(
                EngineeringErrorCode.AI_PROVIDER_UNAVAILABLE,
                "LiteLLM provider request failed",
                details={"provider": self.name, "reason": type(exc).__name__},
            ) from None

    @staticmethod
    def _load_completion() -> CompletionCallable:
        try:
            module = import_module("litellm")
            return cast(CompletionCallable, module.acompletion)
        except (ImportError, AttributeError):
            raise EngineeringError(
                EngineeringErrorCode.CAPABILITY_UNAVAILABLE,
                "LiteLLM adapter is not installed",
                details={"install_extra": "ai"},
            ) from None

    @classmethod
    def _translate(cls, raw: object, *, fallback_model: str) -> AIProviderResponse:
        content = cls._read(cls._read(cls._first(cls._read(raw, "choices")), "message"), "content")
        usage_raw = cls._read(raw, "usage", default={})
        input_tokens = cls._as_int(cls._read(usage_raw, "prompt_tokens", default=0))
        output_tokens = cls._as_int(cls._read(usage_raw, "completion_tokens", default=0))
        total_tokens = cls._as_int(
            cls._read(usage_raw, "total_tokens", default=input_tokens + output_tokens)
        )
        cost = cls._read(usage_raw, "cost", default=cls._read(raw, "_hidden_params", default={}))
        if isinstance(cost, Mapping):
            cost = cost.get("response_cost", 0)
        model = str(cls._read(raw, "model", default=fallback_model))
        return AIProviderResponse(
            content=str(content),
            model=model,
            usage=ProviderUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                llm_cost=Decimal(str(cost or 0)),
            ),
        )

    @staticmethod
    def _read(value: object, key: str, *, default: object | None = None) -> object:
        if isinstance(value, Mapping):
            return cast(Mapping[str, object], value).get(key, default)
        return getattr(value, key, default)

    @staticmethod
    def _first(value: object) -> object:
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError("provider response does not contain choices")
        return value[0]

    @staticmethod
    def _as_int(value: object) -> int:
        if not isinstance(value, (int, str, bytes, bytearray)):
            raise TypeError("provider token usage must be an integer")
        return int(value)
