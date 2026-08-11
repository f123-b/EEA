"""Lightweight product milestone and version metadata consistency checks."""

import json
import re
from pathlib import Path

from eea_backend.version import __version__


def test_current_version_metadata_is_aligned() -> None:
    root = Path(__file__).parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    desktop = json.loads((root / "apps/desktop/package.json").read_text(encoding="utf-8"))
    readme = (root / "README.md").read_text(encoding="utf-8")

    assert re.search(rf'version = "{re.escape(__version__)}"', pyproject)
    assert desktop["version"] == __version__.replace(".dev", "-dev.")
    assert "M15 MotorControl Built-in Domain Plugin" in readme
