"""Generated OpenAPI contract synchronization test."""

import json
from pathlib import Path

from eea_backend.main import create_app
from eea_backend.settings import Settings


def test_committed_openapi_matches_backend() -> None:
    committed = json.loads(Path("schemas/openapi.json").read_text(encoding="utf-8"))
    generated = create_app(Settings()).openapi()

    assert committed == generated
