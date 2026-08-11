"""M3 SQL persistence and cross-surface enum acceptance."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from eea_application.claims import (
    ENGINEERING_VALUE_SCHEMA_REF,
    ClaimPredicateRegistry,
    ClaimService,
)
from eea_backend.claim_repositories import (
    SqlAlchemyClaimConflictRepository,
    SqlAlchemyClaimPredicateRepository,
    SqlAlchemyEngineeringClaimRepository,
)
from eea_core.claims import ClaimPredicateDefinition, EngineeringClaim, EngineeringValue
from eea_core.enums import ClaimConflictStrategy, EngineeringDimension
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_claim_repositories_round_trip_and_keep_conflict(tmp_path: Path) -> None:
    database_path = tmp_path / "m3.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")

    with Session(engine) as session:
        predicates = SqlAlchemyClaimPredicateRepository(session)
        claims = SqlAlchemyEngineeringClaimRepository(session)
        conflicts = SqlAlchemyClaimConflictRepository(session)
        registry = ClaimPredicateRegistry(predicates)
        registry.register(
            ClaimPredicateDefinition(
                predicate="device.max-voltage",
                value_schema_ref=ENGINEERING_VALUE_SCHEMA_REF,
                unit_dimension=EngineeringDimension.VOLTAGE,
                conflict_strategy=ClaimConflictStrategy.SOURCE_PRIORITY,
            )
        )
        service = ClaimService(claims, conflicts, registry)
        first = service.create(
            EngineeringClaim(
                subject_ref="device:stm32g4",
                predicate="device.max-voltage",
                value_schema_ref=ENGINEERING_VALUE_SCHEMA_REF,
                value=EngineeringValue(
                    unit="V", dimension=EngineeringDimension.VOLTAGE, nominal=36
                ),
                applicability={"package": "LQFP64"},
                confidence=0.8,
                source_priority=100,
            )
        )
        second = service.create(
            EngineeringClaim(
                subject_ref="device:stm32g4",
                predicate="device.max-voltage",
                value_schema_ref=ENGINEERING_VALUE_SCHEMA_REF,
                value=EngineeringValue(
                    unit="mV", dimension=EngineeringDimension.VOLTAGE, nominal=30000
                ),
                applicability={"package": "LQFP64"},
                confidence=0.9,
                source_priority=200,
            )
        )

        assert first.claim.value.normalized_nominal == 36  # type: ignore[union-attr]
        assert second.claim.value.normalized_nominal == 30  # type: ignore[union-attr]
        assert len(second.conflicts) == 1
        assert conflicts.list_for_claim(second.claim.id) == list(second.conflicts)
        assert claims.list_for_subject_predicate(
            project_id=None,
            subject_ref="device:stm32g4",
            predicate="device.max-voltage",
        ) == [first.claim, second.claim]

    engine.dispose()
