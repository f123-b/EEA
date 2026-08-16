"""Shared pytest fixtures."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from eea_backend.main import create_app
from eea_backend.settings import Settings
from fastapi.testclient import TestClient

os.environ.setdefault("EEA_INSECURE_LOCAL_DEV", "true")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path, insecure_local_dev=True)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    command.upgrade(config, "head")
    with TestClient(create_app(settings)) as test_client:
        yield test_client
