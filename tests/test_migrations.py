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
        "circuits",
        "circuit_rule_results",
        "schematic_artifacts",
        "erc_reports",
        "mcu_configs",
        "mcu_config_rule_results",
        "source_revisions",
        "firmware_irs",
        "firmware_source_files",
        "build_input_snapshots",
        "build_runs",
        "software_components",
        "software_component_releases",
        "dependency_locks",
        "dependency_lock_components",
        "component_materializations",
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

    command.downgrade(config, "0010_m8_architecture_ir")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    assert not {"circuits", "circuit_rule_results"} & set(inspect(engine).get_table_names())
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    assert {"circuits", "circuit_rule_results"} <= set(inspect(engine).get_table_names())
    engine.dispose()

    command.downgrade(config, "0011_m9_circuit_ir")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    assert not {"schematic_artifacts", "erc_reports"} & set(inspect(engine).get_table_names())
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    assert {"schematic_artifacts", "erc_reports"} <= set(inspect(engine).get_table_names())
    engine.dispose()

    command.downgrade(config, "0012_m10_schematic")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    assert not {"mcu_configs", "mcu_config_rule_results"} & set(inspect(engine).get_table_names())
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    assert {"mcu_configs", "mcu_config_rule_results"} <= set(inspect(engine).get_table_names())
    engine.dispose()

    command.downgrade(config, "0013_m11_mcu_config")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    assert not {
        "source_revisions",
        "firmware_irs",
        "firmware_source_files",
        "build_input_snapshots",
        "build_runs",
    } & set(inspect(engine).get_table_names())
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    assert {
        "source_revisions",
        "firmware_irs",
        "firmware_source_files",
        "build_input_snapshots",
        "build_runs",
    } <= set(inspect(engine).get_table_names())
    engine.dispose()

    command.downgrade(config, "0014_m12_firmware_build")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    assert not {
        "software_components",
        "software_component_releases",
        "dependency_locks",
        "dependency_lock_components",
        "component_materializations",
    } & set(inspect(engine).get_table_names())
    engine.dispose()

    command.upgrade(config, "head")

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
