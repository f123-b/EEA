"""Framework-independent M2 prompt, budget, and usage domain models."""

from decimal import Decimal
from string import Formatter
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from eea_core.entities import EntityBase
from eea_core.enums import EngineeringErrorCode


class ModelPolicy(BaseModel):
    """Provider-neutral model selection policy declared by a prompt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(min_length=1, max_length=200)
    temperature: float = Field(default=0, ge=0, le=2)


class BudgetPolicy(BaseModel):
    """Hard limits applied to one structured generation request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_tokens: int = Field(gt=0)
    max_llm_cost: Decimal = Field(ge=0)
    max_runtime_seconds: float = Field(gt=0)


class PromptDefinition(EntityBase):
    """Versioned prompt contract; templates never contain credentials."""

    name: str = Field(min_length=1, max_length=200, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    prompt_version: str = Field(min_length=1, max_length=50)
    purpose: str = Field(min_length=1, max_length=2000)
    system_template: str = Field(min_length=1, max_length=20000)
    user_template: str = Field(default="{input_json}", min_length=1, max_length=20000)
    model_policy: ModelPolicy
    allowed_tools: list[str] = Field(default_factory=list)
    input_schema: dict[str, object]
    output_schema: dict[str, object]
    evidence_requirements: list[str] = Field(default_factory=list)
    fallback: dict[str, object] = Field(default_factory=dict)
    max_steps: int = Field(default=1, ge=1)
    budget_policy: BudgetPolicy
    active: bool = True

    @model_validator(mode="after")
    def templates_must_not_request_secrets(self) -> "PromptDefinition":
        forbidden = ("api_key", "password", "private_key", "secret_value", "access_token")
        combined = f"{self.system_template}\n{self.user_template}".lower()
        if any(term in combined for term in forbidden):
            raise ValueError("prompt templates must not request or interpolate secrets")
        try:
            fields = {
                field_name
                for _, field_name, _, _ in Formatter().parse(self.user_template)
                if field_name is not None
            }
        except ValueError:
            raise ValueError("user_template has invalid format syntax") from None
        if fields - {"input_json"}:
            raise ValueError("user_template may only interpolate {input_json}")
        return self


class AIUsage(BaseModel):
    """Provider-reported usage normalized for budget enforcement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    llm_cost: Decimal = Field(default=Decimal(0), ge=0)

    @model_validator(mode="after")
    def total_must_cover_components(self) -> "AIUsage":
        if self.total_tokens < self.input_tokens + self.output_tokens:
            raise ValueError("total_tokens cannot be less than input_tokens + output_tokens")
        return self


class AIUsageRecord(EntityBase):
    """Auditable accounting record without prompt or response content."""

    request_id: UUID = Field(default_factory=uuid4)
    prompt_definition_id: UUID
    project_id: UUID | None = None
    job_id: UUID | None = None
    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=200)
    usage: AIUsage = Field(default_factory=AIUsage)
    duration_ms: int = Field(ge=0)
    succeeded: bool
    error_code: EngineeringErrorCode | None = None

    @model_validator(mode="after")
    def outcome_matches_error(self) -> "AIUsageRecord":
        if self.succeeded and self.error_code is not None:
            raise ValueError("successful usage records cannot contain an error code")
        return self
