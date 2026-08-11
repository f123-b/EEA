"""Alembic forward and reverse migration acceptance tests."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_m0_migration_upgrades_and_downgrades(tmp_path: Path) -> None:
    database_path = tmp_path / "migration.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")

    command.upgrade(config, "head")
    command.check(config)

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    table_names = set(inspect(engine).get_table_names())
    assert {
        "ai_usage_records",
        "artifacts",
        "claim_conflicts",
        "claim_predicate_definitions",
        "document_irs",
        "documents",
        "engineering_decisions",
        "engineering_claims",
        "evidence",
        "issues",
        "jobs",
        "hardware_irs",
        "permissions_audit",
        "pin_assignments",
        "pin_locks",
        "pin_plans",
        "pin_rule_results",
        "prompt_definitions",
        "projects",
        "schema_registry",
        "system_metadata",
        "system_architectures",
        "traceability_edges",
    } <= table_names
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT value FROM system_metadata WHERE key = 'schema_version'")
            ).scalar_one()
            == "0001_m0"
        )
    engine.dispose()
    command.downgrade(config, "0009_m7_pin_planner")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    assert not {"hardware_irs", "system_architectures"} & set(inspect(engine).get_table_names())
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    assert {"hardware_irs", "system_architectures"} <= set(inspect(engine).get_table_names())
    engine.dispose()

    command.downgrade(config, "0008_m6_review_fixes")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    assert not {
        "pin_assignments",
        "pin_locks",
        "pin_plans",
        "pin_rule_results",
    } & set(inspect(engine).get_table_names())
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    assert {
        "pin_assignments",
        "pin_locks",
        "pin_plans",
        "pin_rule_results",
    } <= set(inspect(engine).get_table_names())
    engine.dispose()

    command.downgrade(config, "base")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    assert "system_metadata" not in inspect(engine).get_table_names()
    engine.dispose()
