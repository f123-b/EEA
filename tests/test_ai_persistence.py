"""M2 SQL prompt registry and AI usage accounting tests."""

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from eea_backend.repositories import SqlAlchemyAIUsageRepository, SqlAlchemyPromptRepository
from eea_core.ai import AIUsage, AIUsageRecord, BudgetPolicy, ModelPolicy, PromptDefinition
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def migrate_database(path: Path) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    command.upgrade(config, "head")


def make_prompt(version: str = "1.0") -> PromptDefinition:
    return PromptDefinition(
        name="persistence.test",
        prompt_version=version,
        purpose="Test durable prompt definitions",
        system_template="Return structured JSON.",
        model_policy=ModelPolicy(model="test-model"),
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        evidence_requirements=["source reference"],
        fallback={"mode": "degraded"},
        budget_policy=BudgetPolicy(
            max_tokens=100,
            max_llm_cost=Decimal("0.50"),
            max_runtime_seconds=10,
        ),
    )


def test_prompt_and_usage_repositories_round_trip(tmp_path: Path) -> None:
    database_path = tmp_path / "m2.db"
    migrate_database(database_path)
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")

    with Session(engine) as session:
        prompts = SqlAlchemyPromptRepository(session)
        usage = SqlAlchemyAIUsageRepository(session)
        first = prompts.add(make_prompt())
        second = prompts.add(make_prompt("2.0"))

        assert prompts.get(first.name, "1.0") == first
        assert prompts.get(second.name) == second
        with pytest.raises(ValueError, match="already registered"):
            prompts.add(make_prompt("2.0"))

        request_id = uuid4()
        stored = usage.add(
            AIUsageRecord(
                request_id=request_id,
                prompt_definition_id=second.id,
                provider="fake",
                model="test-model",
                usage=AIUsage(
                    input_tokens=10,
                    output_tokens=5,
                    total_tokens=15,
                    llm_cost=Decimal("0.125"),
                ),
                duration_ms=25,
                succeeded=True,
            )
        )

        assert stored.usage.llm_cost == Decimal("0.125")
        assert usage.list_for_request(request_id) == [stored]

    engine.dispose()
