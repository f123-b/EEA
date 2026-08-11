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
        "permissions_audit",
        "prompt_definitions",
        "projects",
        "schema_registry",
        "system_metadata",
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

    command.downgrade(config, "base")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    assert "system_metadata" not in inspect(engine).get_table_names()
    engine.dispose()
