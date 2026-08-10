"""Shared pytest fixtures."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from eea_backend.main import create_app
from eea_backend.settings import Settings
from fastapi.testclient import TestClient


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client
