"""Operational CLI for the M0 backend foundation."""

import json
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from alembic import command
from alembic.config import Config
from eea_backend.database import check_database, create_database_engine
from eea_backend.main import create_app
from eea_backend.settings import Settings
from eea_backend.version import __version__

app = typer.Typer(help="Embedded Engineering Agent developer CLI.", no_args_is_help=True)
db_app = typer.Typer(help="Manage the EEA SQL schema.")
openapi_app = typer.Typer(help="Export and validate the OpenAPI contract.")
app.add_typer(db_app, name="db")
app.add_typer(openapi_app, name="openapi")


def _alembic_config(settings: Settings) -> Config:
    config_path = Path("alembic.ini")
    if not config_path.is_file():
        raise typer.BadParameter(
            "alembic.ini was not found; run this command from the repository root"
        )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    config = Config(str(config_path))
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    return config


def _render_openapi() -> str:
    schema = create_app(Settings()).openapi()
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


@app.command()
def version() -> None:
    """Print the product version."""

    typer.echo(__version__)


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Bind address.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535)] = 8000,
    reload: Annotated[bool, typer.Option(help="Reload on source changes.")] = False,
) -> None:
    """Run the FastAPI service."""

    uvicorn.run("eea_backend.main:app", host=host, port=port, reload=reload)


@app.command()
def health() -> None:
    """Check direct database connectivity for the configured profile."""

    settings = Settings()
    engine = create_database_engine(settings)
    try:
        check_database(engine)
    finally:
        engine.dispose()
    typer.echo(json.dumps({"status": "ok", "database": "ok", "version": __version__}))


@db_app.command("upgrade")
def db_upgrade(revision: Annotated[str, typer.Argument()] = "head") -> None:
    """Upgrade the database to a target Alembic revision."""

    command.upgrade(_alembic_config(Settings()), revision)


@db_app.command("downgrade")
def db_downgrade(revision: Annotated[str, typer.Argument()] = "-1") -> None:
    """Downgrade the database by one revision or to a target revision."""

    command.downgrade(_alembic_config(Settings()), revision)


@openapi_app.command("export")
def openapi_export(
    output: Annotated[Path, typer.Option(help="Generated schema path.")] = Path(
        "schemas/openapi.json"
    ),
    check: Annotated[
        bool, typer.Option(help="Fail if the generated schema is out of date.")
    ] = False,
) -> None:
    """Export the backend OpenAPI document deterministically."""

    rendered = _render_openapi()
    if check:
        if not output.is_file() or output.read_text(encoding="utf-8") != rendered:
            typer.echo(f"OpenAPI schema is out of date: {output}", err=True)
            raise typer.Exit(code=1)
        typer.echo(f"OpenAPI schema is current: {output}")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8", newline="\n")
    typer.echo(f"OpenAPI schema written to {output}")


if __name__ == "__main__":
    app()
