# M17 Test / Traceability / Review Test Report

Date: 2026-08-12

Repository: `f123-b/EEA`

Branch: `codex/m17-test-traceability-review`

Base: `main` at `6c75c1467d6e5ba001168b98a09cbbd005361336`

Migration: `0023_m17_test_traceability_review`

## Scope

This implementation covers the M17 TestIR, deterministic test generation,
project-scoped controlled test execution, revision/source freshness, coverage
and traceability, fail-closed ReviewRun evaluation, stable issue persistence and
concurrency handling, and synchronized API/OpenAPI/TypeScript contracts.

M17 does not implement M18 dependency invalidation, M19 FOC or commissioning,
M21 Desktop UI, or any ProtocolIR changes.

## Verification

Focused M17/M17R.1 tests: **27 passed**.

Repository verification under the authoritative Python 3.12.13 interpreter:

- `pytest`: **278 passed, 3 skipped**
- coverage: **84.99%**
- `ruff check .`: **PASS**
- `ruff format --check .`: **PASS**
- `mypy`: **PASS**
- clean database upgrade twice: **PASS**
- clean database + `alembic check`: **PASS**
- `eea openapi export --check`: **PASS**
- `eea openapi typescript --check`: **PASS**
- `pnpm lint`: **PASS**
- `pnpm typecheck`: **PASS**
- `pnpm build`: **PASS**

M17R.1 focused assertions include the distinction between contract-only results
and authorized verification, a project-scoped deterministic fact executor that
can produce a real PASS, evidence-required TRUSTED_EVIDENCE, unknown/arbitrary
executor blocking, requirement and TestIR/TestRun/source freshness,
missing/duplicate result fail-closed behavior, policy bypass regressions,
SKIPPED/PENDING/RUNNING mappings, semantic review hashes, stable TestCase and
Rule source identity, stable Issue recurrence with two-session SQLite
concurrency, traceability upsert CAS concurrency, and evidence union.

No migration was added for M17R.1; the clean database gate remains at
`0023_m17_test_traceability_review`.

The repository's `uv` Windows interpreter redirector reports a process-launch
error in the existing M5 Sandbox subprocess tests. Re-running the same M5
tests with the authoritative Python 3.12.13 interpreter passes (`8 passed,
3 skipped`). No Sandbox source was changed by M17R.1.

## Status

`M17R.1 = IMPLEMENTED`

`READY_FOR_M17_FINAL_REVIEW = NO`

`READY_FOR_M18 = NO`

`M18 = NOT_STARTED`

`M19 = NOT_STARTED`

`M21 = NOT_STARTED`

This report records local implementation verification. Final review readiness
will be set to YES only after the latest pushed HEAD CI passes.
