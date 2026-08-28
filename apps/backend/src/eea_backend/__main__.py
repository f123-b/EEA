"""Run the API with safe local defaults and desktop-runtime overrides."""

import os
import sys
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config

from eea_backend.settings import Settings


def _migration_directory() -> Path:
    """Locate migrations in either a PyInstaller bundle or the source tree."""

    bundle_root = getattr(sys, "_MEIPASS", None)
    roots = ([Path(bundle_root)] if bundle_root else []) + list(Path(__file__).resolve().parents)
    roots.append(Path.cwd())
    for root in roots:
        candidate = root / "migrations"
        if (candidate / "env.py").is_file():
            return candidate
    raise RuntimeError("EEA desktop runtime migrations are unavailable")


def _upgrade_desktop_database() -> None:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    config = Config()
    config.set_main_option("script_location", str(_migration_directory()))
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    command.upgrade(config, "head")


def main() -> None:
    """Start the backend on loopback."""

    if os.environ.get("EEA_DESKTOP_AUTO_MIGRATE") == "1":
        _upgrade_desktop_database()
    host = os.environ.get("EEA_RUNTIME_HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "::1"}:
        raise RuntimeError("EEA runtime backend must bind to loopback")
    port = int(os.environ.get("EEA_RUNTIME_PORT", "8000"))
    if not 0 <= port <= 65535:
        raise RuntimeError("EEA runtime backend port is invalid")
    uvicorn.run("eea_backend.main:app", host=host, port=port)


if __name__ == "__main__":
    main()
