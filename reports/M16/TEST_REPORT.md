# M16 ProtocolIR Test Report

Date: 2026-08-11
Repository: `f123-b/EEA`
Branch: `codex/m16-protocolir`
Base: `cfd6877bc6617f9798422031205c15ab5dea8602`
Migration: `0022_m16_protocol_ir`

## Scope

M16 implements only the Core-neutral, deterministic CAN ProtocolIR contract:

- classic CAN and CAN FD transport definitions;
- CAN messages and DBC-compatible little-endian/Motorola bit layouts;
- signed raw values, scale/offset conversion, declared physical bounds, and
  round-half-away-from-zero encoding;
- deterministic validation for all 12 frozen M16 rules;
- canonical semantic SHA-256 input hash;
- standalone C11, Python, DBC, and Markdown generation bound to the same
  protocol revision and input hash;
- project-scoped persistence, revision history, optimistic concurrency, and
  validate/generate API routes;
- synchronized OpenAPI and TypeScript contracts.

M17 Test/Traceability/Review, M18 dependency graph, M19 FOC E2E and hardware
commissioning, M21 Desktop UI, Agent Runtime, UART/SPI/I2C, and ProtocolIR
multiplexing are not implemented here.

## Focused verification

```text
uv run --extra dev pytest --no-cov tests/test_m16_protocol.py -q
```

Result: **30 passed**.

The focused suite covers schema/layout boundaries, all 12 validation rules,
signed/scaled values, canonical hash behavior, Python and C golden vectors,
DBC/Markdown output, persistence/revision conflicts, API project isolation,
OpenAPI routes, and migration head presence.

## Final local repository gate

```text
pytest                                  PASS (232 passed, 3 skipped)
coverage                                PASS (84.86%)
ruff check .                            PASS
ruff format --check .                   PASS (232 files)
mypy                                    PASS (109 source files)
database upgrade                        PASS
clean database + alembic check          PASS (no new upgrade operations)
eea openapi export --check              PASS
eea openapi typescript --check          PASS
pnpm lint                               PASS
pnpm typecheck                          PASS
pnpm build                              PASS
generated C11 codec compile/execute     PASS (gcc -std=c11 -Wall -Wextra -Werror)
cross-language golden vector            PASS (Python reference/standalone/C)
```

The standard venv redirector on this Windows host maps child process launches
to the base Python path and causes two existing M5 Job Object tests to fail;
the same full suite with the actual Python 3.12 base executable and the venv
site-packages passed with the result above. No M5 source or safety policy was
changed.

## Acceptance gate state

Final GitHub CI: Run `31507669491` for PR #3 — **PASS** (backend and desktop).

This report records implementation and review readiness; it does not declare
M16 accepted or authorize merge:

```text
M16 = IMPLEMENTED
READY_FOR_M16_REVIEW = YES
```

The report must not be interpreted as M16 acceptance or as permission to merge
the Draft PR.
