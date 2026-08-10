"""Generated TypeScript Core contract synchronization tests."""

from pathlib import Path

from eea_cli.codegen import render_typescript_contract


def test_generated_typescript_contract_is_current() -> None:
    generated = Path("apps/desktop/src/api/generated.ts").read_text(encoding="utf-8")

    assert generated == render_typescript_contract()
    assert '"ACTUATOR_ENABLE"' in generated
    assert '"FAILED_NEEDS_RECONCILE"' in generated
    assert '"SOURCE_REVISION_CONFLICT"' in generated
