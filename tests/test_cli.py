"""CLI smoke tests."""

from pathlib import Path

from eea_cli.main import app
from sqlalchemy import create_engine, inspect
from typer.testing import CliRunner
from eea_backend.version import __version__

runner = CliRunner()


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_openapi_check_detects_stale_file(tmp_path: Path) -> None:
    output = tmp_path / "openapi.json"
    output.write_text("{}", encoding="utf-8")

    result = runner.invoke(app, ["openapi", "export", "--output", str(output), "--check"])

    assert result.exit_code == 1
    assert "out of date" in result.stderr


def test_openapi_export_then_check(tmp_path: Path) -> None:
    output = tmp_path / "openapi.json"

    export_result = runner.invoke(app, ["openapi", "export", "--output", str(output)])
    check_result = runner.invoke(app, ["openapi", "export", "--output", str(output), "--check"])

    assert export_result.exit_code == 0
    assert check_result.exit_code == 0


def test_health_command_uses_configured_database(tmp_path: Path) -> None:
    result = runner.invoke(app, ["health"], env={"EEA_DATA_DIR": str(tmp_path)})

    assert result.exit_code == 0
    assert '"status": "ok"' in result.stdout


def test_db_upgrade_command(tmp_path: Path) -> None:
    result = runner.invoke(app, ["db", "upgrade"], env={"EEA_DATA_DIR": str(tmp_path)})

    assert result.exit_code == 0
    engine = create_engine(f"sqlite:///{(tmp_path / 'eea.db').as_posix()}")
    assert "system_metadata" in inspect(engine).get_table_names()
    engine.dispose()


def test_typescript_contract_export_then_check(tmp_path: Path) -> None:
    output = tmp_path / "generated.ts"

    export_result = runner.invoke(app, ["openapi", "typescript", "--output", str(output)])
    check_result = runner.invoke(app, ["openapi", "typescript", "--output", str(output), "--check"])

    assert export_result.exit_code == 0
    assert check_result.exit_code == 0
    assert "export type Permission" in output.read_text(encoding="utf-8")
