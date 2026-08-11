"""M2 prompt registry, budget gate, and structured generation service."""

import asyncio
import json
from collections.abc import Mapping
from time import monotonic
from typing import TypeVar
from uuid import UUID, uuid4

from eea_core.ai import AIUsage, AIUsageRecord, BudgetPolicy, PromptDefinition
from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_core.repositories import AIUsageRepository, PromptRepository
from eea_ports.ai import (
    AIMessage,
    AIProvider,
    AIProviderRequest,
)
from eea_ports.secrets import SecretReference, SecretValue
from pydantic import BaseModel, ValidationError

OutputT = TypeVar("OutputT", bound=BaseModel)

_SECRET_FIELD_MARKERS = (
    "api_key",
    "password",
    "private_key",
    "secret",
    "token",
    "credential",
)


class PromptRegistry:
    """Versioned registry backed by a persistence port."""

    def __init__(self, repository: PromptRepository) -> None:
        self._repository = repository

    def register(self, definition: PromptDefinition) -> PromptDefinition:
        return self._repository.add(definition)

    def require(self, name: str, version: str | None = None) -> PromptDefinition:
        definition = self._repository.get(name, version)
        if definition is None or not definition.active:
            raise EngineeringError(
                EngineeringErrorCode.CAPABILITY_UNAVAILABLE,
                "Prompt definition is not available",
                details={"prompt": name, "version": version},
            )
        return definition


class BudgetGuard:
    """Checks preflight request bounds and provider-reported consumption."""

    @staticmethod
    def check_request(policy: BudgetPolicy) -> None:
        if policy.max_tokens <= 0 or policy.max_runtime_seconds <= 0:
            raise EngineeringError(
                EngineeringErrorCode.BUDGET_EXCEEDED,
                "Generation budget does not permit execution",
            )

    @staticmethod
    def check_usage(policy: BudgetPolicy, usage: AIUsage) -> None:
        exceeded: dict[str, object] = {}
        if usage.total_tokens > policy.max_tokens:
            exceeded["tokens"] = {"used": usage.total_tokens, "limit": policy.max_tokens}
        if usage.llm_cost > policy.max_llm_cost:
            exceeded["llm_cost"] = {
                "used": str(usage.llm_cost),
                "limit": str(policy.max_llm_cost),
            }
        if exceeded:
            raise EngineeringError(
                EngineeringErrorCode.BUDGET_EXCEEDED,
                "AI generation exceeded its budget",
                details=exceeded,
            )


class StructuredGenerationService:
    """The only M2 application entry point for schema-validated LLM output."""

    def __init__(
        self,
        provider: AIProvider,
        prompt_registry: PromptRegistry,
        usage_repository: AIUsageRepository,
    ) -> None:
        self._provider = provider
        self._prompt_registry = prompt_registry
        self._usage_repository = usage_repository

    async def generate(
        self,
        *,
        prompt_name: str,
        input_data: Mapping[str, object],
        output_model: type[OutputT],
        prompt_version: str | None = None,
        project_id: UUID | None = None,
        job_id: UUID | None = None,
        request_id: UUID | None = None,
    ) -> OutputT:
        definition = self._prompt_registry.require(prompt_name, prompt_version)
        self._validate_contract(definition, output_model)
        self._reject_secret_material(input_data)
        BudgetGuard.check_request(definition.budget_policy)
        effective_request_id = request_id or uuid4()
        request = self._build_request(definition, input_data)
        started = monotonic()
        usage = AIUsage()
        model = definition.model_policy.model
        error_code: EngineeringErrorCode | None = None
        try:
            async with asyncio.timeout(definition.budget_policy.max_runtime_seconds):
                response = await self._provider.generate(request)
            usage = AIUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                total_tokens=response.usage.total_tokens,
                llm_cost=response.usage.llm_cost,
            )
            model = response.model
            BudgetGuard.check_usage(definition.budget_policy, usage)
            try:
                return output_model.model_validate_json(response.content)
            except ValidationError as exc:
                error_code = EngineeringErrorCode.VALIDATION_ERROR
                raise EngineeringError(
                    error_code,
                    "AI provider returned output that does not match the registered schema",
                    details={"validation_errors": exc.error_count()},
                ) from None
        except TimeoutError:
            error_code = EngineeringErrorCode.AI_PROVIDER_UNAVAILABLE
            raise EngineeringError(
                error_code,
                "AI provider request timed out",
                details={"provider": self._provider.name, "reason": "timeout"},
            ) from None
        except EngineeringError as exc:
            error_code = exc.code
            raise
        except Exception as exc:
            error_code = EngineeringErrorCode.AI_PROVIDER_UNAVAILABLE
            raise EngineeringError(
                error_code,
                "AI provider request failed",
                details={"provider": self._provider.name, "reason": type(exc).__name__},
            ) from None
        finally:
            duration_ms = max(0, int((monotonic() - started) * 1000))
            self._usage_repository.add(
                AIUsageRecord(
                    request_id=effective_request_id,
                    prompt_definition_id=definition.id,
                    project_id=project_id,
                    job_id=job_id,
                    provider=self._provider.name,
                    model=model,
                    usage=usage,
                    duration_ms=duration_ms,
                    succeeded=error_code is None,
                    error_code=error_code,
                )
            )

    @staticmethod
    def _validate_contract(definition: PromptDefinition, output_model: type[BaseModel]) -> None:
        if definition.output_schema != output_model.model_json_schema():
            raise EngineeringError(
                EngineeringErrorCode.SCHEMA_VERSION_UNSUPPORTED,
                "Output model does not match the registered prompt schema",
                details={"prompt": definition.name, "version": definition.prompt_version},
            )

    @classmethod
    def _reject_secret_material(cls, value: object, path: str = "input") -> None:
        if isinstance(value, (SecretReference, SecretValue)):
            raise EngineeringError(
                EngineeringErrorCode.PERMISSION_REQUIRED,
                "Secret material is not allowed in AI input",
                details={"path": path},
            )
        if isinstance(value, Mapping):
            for key, child in value.items():
                normalized = str(key).lower()
                if any(marker in normalized for marker in _SECRET_FIELD_MARKERS):
                    raise EngineeringError(
                        EngineeringErrorCode.PERMISSION_REQUIRED,
                        "Secret-like fields are not allowed in AI input",
                        details={"path": f"{path}.{key}"},
                    )
                cls._reject_secret_material(child, f"{path}.{key}")
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                cls._reject_secret_material(child, f"{path}[{index}]")

    @staticmethod
    def _build_request(
        definition: PromptDefinition, input_data: Mapping[str, object]
    ) -> AIProviderRequest:
        try:
            input_json = json.dumps(
                input_data,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            user_content = definition.user_template.format(input_json=input_json)
        except (KeyError, TypeError, ValueError):
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR,
                "AI input cannot be rendered as registered prompt JSON",
                details={"prompt": definition.name},
            ) from None
        return AIProviderRequest(
            model=definition.model_policy.model,
            messages=(
                AIMessage(role="system", content=definition.system_template),
                AIMessage(role="user", content=user_content),
            ),
            response_schema=definition.output_schema,
            temperature=definition.model_policy.temperature,
            max_output_tokens=definition.budget_policy.max_tokens,
            timeout_seconds=definition.budget_policy.max_runtime_seconds,
            metadata={
                "prompt_name": definition.name,
                "prompt_version": definition.prompt_version,
            },
        )
