"""Repository-layout and dependency-direction guardrails."""

import ast
from pathlib import Path

EXPECTED_ROOT_DIRECTORIES = {
    "adapters",
    "agents",
    "application",
    "apps",
    "benchmarks",
    "core",
    "discovery",
    "domain",
    "examples",
    "importers",
    "knowledge",
    "memory",
    "migrations",
    "plugins",
    "ports",
    "rules",
    "runtimes",
    "schemas",
    "tests",
}

FORBIDDEN_DOMAIN_IMPORTS = {
    "alembic",
    "fastapi",
    "litellm",
    "qdrant_client",
    "sqlalchemy",
}


def test_frozen_repository_layout_exists() -> None:
    missing = [directory for directory in EXPECTED_ROOT_DIRECTORIES if not Path(directory).is_dir()]

    assert not missing, f"Missing architecture directories: {missing}"


def test_domain_layer_has_no_framework_imports() -> None:
    violations: list[str] = []
    for source_file in Path("domain").rglob("*.py"):
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                root = name.split(".", maxsplit=1)[0]
                if root in FORBIDDEN_DOMAIN_IMPORTS:
                    violations.append(f"{source_file}: {name}")

    assert not violations, "Domain imports infrastructure frameworks: " + ", ".join(violations)
