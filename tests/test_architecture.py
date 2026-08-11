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

FORBIDDEN_CORE_DOMAIN_TERMS = {
    "foc",
    "motorcontrol",
    "motor_control",
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


def test_core_must_not_define_motor_control() -> None:
    """CORE_MUST_NOT_DEFINE_MOTOR_CONTROL."""

    violations: list[str] = []
    for path in Path("core").rglob("*"):
        if not path.is_file() or path.suffix not in {
            ".json",
            ".md",
            ".py",
            ".toml",
            ".yaml",
            ".yml",
        }:
            continue
        normalized_name = path.name.lower()
        content = path.read_text(encoding="utf-8").lower()
        if any(term in normalized_name or term in content for term in FORBIDDEN_CORE_DOMAIN_TERMS):
            violations.append(str(path))

    assert not violations, "Core defines a concrete MotorControl/FOC concept: " + ", ".join(
        violations
    )


def test_core_must_not_import_motor_control_plugin() -> None:
    """CORE_MUST_NOT_IMPORT_MOTOR_CONTROL_PLUGIN."""

    violations: list[str] = []
    for source_file in Path("core").rglob("*.py"):
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            else:
                names = []
            if any(name.startswith("plugins.builtin.motor_control") for name in names):
                violations.append(str(source_file))

    assert not violations, "Core imports the MotorControl plugin: " + ", ".join(violations)


def test_provider_sdks_are_confined_to_adapters() -> None:
    violations: list[str] = []
    for root in ("core", "domain", "ports", "application"):
        for source_file in Path(root).rglob("*.py"):
            content = source_file.read_text(encoding="utf-8")
            if "import litellm" in content or "from litellm" in content:
                violations.append(str(source_file))

    assert not violations, "Provider SDK escaped the adapter boundary: " + ", ".join(violations)


def test_ports_do_not_depend_on_core_or_frameworks() -> None:
    violations: list[str] = []
    forbidden_roots = {"eea_adapters", "eea_application", "eea_backend", "eea_core", "pydantic"}
    for source_file in Path("ports").rglob("*.py"):
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            else:
                names = []
            if any(name.split(".", maxsplit=1)[0] in forbidden_roots for name in names):
                violations.append(str(source_file))

    assert not violations, "Ports depend on Core or frameworks: " + ", ".join(violations)
