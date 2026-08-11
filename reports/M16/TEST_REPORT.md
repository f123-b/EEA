# M16 ProtocolIR Test Report

Date: 2026-08-12
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
- one canonical ordering for transports, messages, and fields shared by every
  generated target;
- fail-closed CAN arbitration-key and transport-identifier uniqueness;
- deterministic C11/DBC-safe identifier normalization and collision handling;
- exact 1..64-bit signed/unsigned raw integer codecs, with explicit
  IEEE-754 physical-value limits;
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

Result: **49 passed**.

The focused suite covers schema/layout boundaries, all 12 validation rules,
signed/scaled values, semantic reorder determinism, duplicate CAN arbitration
IDs, duplicate transport IDs, reserved-keyword and normalized-symbol C11
compilation, DBC symbols, Python/reference/C raw 64-bit boundaries, physical
precision fail-closed behavior, persistence/revision conflicts, API project
isolation, OpenAPI routes, and migration head presence.

## Final local repository gate

```text
pytest                                  PASS (251 passed, 3 skipped; authoritative Python 3.12)
coverage                                PASS (84.98%)
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
generated C11 codec compile/execute     PASS (gcc -std=c11 -Wall -Wextra -Werror; golden + identifier + raw64)
cross-language golden vector            PASS (Python reference/standalone/C)
repository CAS conflict                 PASS (two sessions; one success, one conflict)
```

The standard venv redirector on this Windows host maps child process launches
to the base Python path. Its direct `uv run pytest` check reported two existing
M5 Job Object failures; the same full suite with the actual Python 3.12 base
executable and the venv site-packages passed with the authoritative result
above. No M5 source or safety policy was changed.

## Acceptance gate state

The previous PR #3 CI passed before this M16R delta. A new remote CI run is
required after the updated branch is pushed; GitHub PR checks are the final
remote evidence for this revision.

This report records implementation and review readiness; it does not declare
M16 accepted or authorize merge:

```text
M16R = IMPLEMENTED
READY_FOR_M16_FINAL_REVIEW = YES
```

The report must not be interpreted as M16 acceptance or as permission to merge
the Draft PR.
