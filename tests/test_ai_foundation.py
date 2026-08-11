"""M2 structured generation, failure, timeout, budget, and secret-leak gates."""

import asyncio
from decimal import Decimal
from uuid import UUID

import pytest
from eea_application.ai import PromptRegistry, StructuredGenerationService
from eea_core.ai import AIUsage, AIUsageRecord, BudgetPolicy, ModelPolicy, PromptDefinition
from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_ports.ai import AIProviderRequest, AIProviderResponse, ProviderUsage
from eea_ports.secrets import SecretReference, SecretValue
from pydantic import BaseModel, Field, ValidationError


class ResultModel(BaseModel):
    answer: int = Field(gt=0)


class AlternateResultModel(BaseModel):
    text: str


class MemoryPromptRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], PromptDefinition] = {}

    def add(self, definition: PromptDefinition) -> PromptDefinition:
        key = (definition.name, definition.prompt_version)
        if key in self.items:
            raise ValueError("duplicate prompt")
        self.items[key] = definition
        return definition

    def get(self, name: str, version: str | None = None) -> PromptDefinition | None:
        matches = [item for key, item in self.items.items() if key[0] == name]
        if version is not None:
            return self.items.get((name, version))
        active = [item for item in matches if item.active]
        return sorted(active, key=lambda item: item.prompt_version)[-1] if active else None


class MemoryUsageRepository:
    def __init__(self) -> None:
        self.items: list[AIUsageRecord] = []

    def add(self, record: AIUsageRecord) -> AIUsageRecord:
        self.items.append(record)
        return record

    def list_for_request(self, request_id: object) -> list[AIUsageRecord]:
        return [item for item in self.items if str(item.request_id) == str(request_id)]


class FakeProvider:
    name = "fake"

    def __init__(
        self,
        response: AIProviderResponse | None = None,
        *,
        failure: Exception | None = None,
        delay: float = 0,
    ) -> None:
        self.response = response
        self.failure = failure
        self.delay = delay
        self.requests: list[AIProviderRequest] = []

    async def generate(self, request: AIProviderRequest) -> AIProviderResponse:
        self.requests.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.failure:
            raise self.failure
        if self.response is None:
            raise AssertionError("test provider has no response")
        return self.response


def make_definition(
    *,
    max_tokens: int = 100,
    max_cost: str = "1.00",
    timeout: float = 1,
) -> PromptDefinition:
    return PromptDefinition(
        name="test.structured",
        prompt_version="1.0",
        purpose="Return a validated test result",
        system_template="Return only JSON matching the supplied schema.",
        model_policy=ModelPolicy(model="test-model"),
        input_schema={"type": "object"},
        output_schema=ResultModel.model_json_schema(),
        budget_policy=BudgetPolicy(
            max_tokens=max_tokens,
            max_llm_cost=Decimal(max_cost),
            max_runtime_seconds=timeout,
        ),
    )


def make_service(
    provider: FakeProvider,
    definition: PromptDefinition | None = None,
) -> tuple[StructuredGenerationService, MemoryUsageRepository]:
    prompt_repository = MemoryPromptRepository()
    registry = PromptRegistry(prompt_repository)
    registry.register(definition or make_definition())
    usage_repository = MemoryUsageRepository()
    return StructuredGenerationService(provider, registry, usage_repository), usage_repository


def test_structured_generation_validates_output_and_accounts_usage() -> None:
    provider = FakeProvider(
        AIProviderResponse(
            content='{"answer":42}',
            model="resolved-model",
            usage=ProviderUsage(
                input_tokens=8,
                output_tokens=4,
                total_tokens=12,
                llm_cost=Decimal("0.02"),
            ),
        )
    )
    service, usage_repository = make_service(provider)

    result = asyncio.run(
        service.generate(
            prompt_name="test.structured",
            input_data={"question": "six times seven"},
            output_model=ResultModel,
        )
    )

    assert result.answer == 42
    assert provider.requests[0].response_schema == ResultModel.model_json_schema()
    assert provider.requests[0].max_output_tokens == 100
    assert usage_repository.items[0].succeeded is True
    assert usage_repository.items[0].usage.total_tokens == 12
    assert usage_repository.items[0].model == "resolved-model"


@pytest.mark.parametrize(
    ("response", "expected_code"),
    [
        (
            AIProviderResponse(
                content='{"answer":0}',
                model="test-model",
                usage=ProviderUsage(total_tokens=1),
            ),
            EngineeringErrorCode.VALIDATION_ERROR,
        ),
        (
            AIProviderResponse(
                content='{"answer":1}',
                model="test-model",
                usage=ProviderUsage(total_tokens=101),
            ),
            EngineeringErrorCode.BUDGET_EXCEEDED,
        ),
        (
            AIProviderResponse(
                content='{"answer":1}',
                model="test-model",
                usage=ProviderUsage(total_tokens=1, llm_cost=Decimal("1.01")),
            ),
            EngineeringErrorCode.BUDGET_EXCEEDED,
        ),
    ],
)
def test_invalid_output_and_postflight_budget_fail_closed(
    response: AIProviderResponse,
    expected_code: EngineeringErrorCode,
) -> None:
    service, usage_repository = make_service(FakeProvider(response))

    with pytest.raises(EngineeringError) as captured:
        asyncio.run(
            service.generate(
                prompt_name="test.structured",
                input_data={"question": "test"},
                output_model=ResultModel,
            )
        )

    assert captured.value.code is expected_code
    assert usage_repository.items[0].succeeded is False
    assert usage_repository.items[0].error_code is expected_code


def test_provider_failure_is_sanitized_and_accounted() -> None:
    raw_secret = "sk-super-secret-value"
    service, usage_repository = make_service(
        FakeProvider(failure=RuntimeError(f"upstream included {raw_secret}"))
    )

    with pytest.raises(EngineeringError) as captured:
        asyncio.run(
            service.generate(
                prompt_name="test.structured",
                input_data={"question": "test"},
                output_model=ResultModel,
            )
        )

    assert captured.value.code is EngineeringErrorCode.AI_PROVIDER_UNAVAILABLE
    assert raw_secret not in str(captured.value)
    assert raw_secret not in repr(captured.value.details)
    assert usage_repository.items[0].error_code is EngineeringErrorCode.AI_PROVIDER_UNAVAILABLE


def test_timeout_cancels_provider_and_is_accounted() -> None:
    definition = make_definition(timeout=0.01)
    service, usage_repository = make_service(FakeProvider(delay=0.1), definition)

    with pytest.raises(EngineeringError) as captured:
        asyncio.run(
            service.generate(
                prompt_name="test.structured",
                input_data={"question": "test"},
                output_model=ResultModel,
            )
        )

    assert captured.value.code is EngineeringErrorCode.AI_PROVIDER_UNAVAILABLE
    assert captured.value.details["reason"] == "timeout"
    assert usage_repository.items[0].succeeded is False


@pytest.mark.parametrize(
    "input_data",
    [
        {"api_key": "should-never-be-sent"},
        {"nested": {"access_token": "should-never-be-sent"}},
        {"value": SecretValue("should-never-be-sent")},
        {"value": SecretReference("llm-api")},
    ],
)
def test_secret_material_is_rejected_before_provider_call(
    input_data: dict[str, object],
) -> None:
    provider = FakeProvider()
    service, usage_repository = make_service(provider)

    with pytest.raises(EngineeringError) as captured:
        asyncio.run(
            service.generate(
                prompt_name="test.structured",
                input_data=input_data,
                output_model=ResultModel,
            )
        )

    assert captured.value.code is EngineeringErrorCode.PERMISSION_REQUIRED
    assert not provider.requests
    assert not usage_repository.items


def test_prompt_contract_is_versioned_and_exact() -> None:
    repository = MemoryPromptRepository()
    registry = PromptRegistry(repository)
    definition = registry.register(make_definition())

    assert registry.require(definition.name, definition.prompt_version) == definition
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(definition)

    service = StructuredGenerationService(FakeProvider(), registry, MemoryUsageRepository())
    with pytest.raises(EngineeringError) as captured:
        asyncio.run(
            service.generate(
                prompt_name=definition.name,
                input_data={"question": "test"},
                output_model=AlternateResultModel,
            )
        )
    assert captured.value.code is EngineeringErrorCode.SCHEMA_VERSION_UNSUPPORTED


def test_prompt_definition_and_usage_models_fail_closed() -> None:
    with pytest.raises(ValidationError, match="must not request"):
        PromptDefinition.model_validate(
            {**make_definition().model_dump(), "system_template": "Use {api_key}"}
        )
    with pytest.raises(ValidationError, match="only interpolate"):
        PromptDefinition.model_validate(
            {**make_definition().model_dump(), "user_template": "Use {unknown}"}
        )
    with pytest.raises(ValidationError, match="total_tokens"):
        AIUsage(input_tokens=2, output_tokens=2, total_tokens=3)
    with pytest.raises(ValidationError, match="successful"):
        AIUsageRecord(
            prompt_definition_id=make_definition().id,
            provider="fake",
            model="model",
            duration_ms=0,
            succeeded=True,
            error_code=EngineeringErrorCode.VALIDATION_ERROR,
        )


def test_usage_repository_request_filter_contract() -> None:
    repository = MemoryUsageRepository()
    request_id = UUID("00000000-0000-0000-0000-000000000001")
    definition = make_definition()
    repository.add(
        AIUsageRecord(
            request_id=request_id,
            prompt_definition_id=definition.id,
            provider="fake",
            model="model",
            duration_ms=0,
            succeeded=True,
        )
    )
    repository.add(
        AIUsageRecord(
            prompt_definition_id=definition.id,
            provider="fake",
            model="model",
            duration_ms=0,
            succeeded=True,
        )
    )

    assert len(repository.list_for_request(request_id)) == 1


def test_non_json_input_fails_before_provider_call() -> None:
    provider = FakeProvider()
    service, usage_repository = make_service(provider)

    with pytest.raises(EngineeringError) as captured:
        asyncio.run(
            service.generate(
                prompt_name="test.structured",
                input_data={"unsupported": object()},
                output_model=ResultModel,
            )
        )

    assert captured.value.code is EngineeringErrorCode.VALIDATION_ERROR
    assert not provider.requests
    assert not usage_repository.items
