"""AI provider and persistence ports without provider SDK dependencies."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class AIMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class AIProviderRequest:
    model: str
    messages: tuple[AIMessage, ...]
    response_schema: dict[str, object]
    temperature: float
    max_output_tokens: int
    timeout_seconds: float
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    llm_cost: Decimal = Decimal(0)


@dataclass(frozen=True, slots=True)
class AIProviderResponse:
    content: str
    model: str
    usage: ProviderUsage


class AIProvider(Protocol):
    name: str

    async def generate(self, request: AIProviderRequest) -> AIProviderResponse: ...
