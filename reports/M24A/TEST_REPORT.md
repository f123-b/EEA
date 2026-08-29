# M24A Test Report

## Scope

This report covers the M24A requirement intake, deterministic context assembly, structured plan
generation, provenance/freshness, impact output, review/CAS boundary, and desktop review-only
surface. It does not authorize M24B execution.

## Focused coverage

- `tests/test_m24a_planning.py`: provider scenarios for CAN heartbeat, MCU pin change, and FOC
  stability investigation; strict schema; source prompt-injection labeling; stale memory
  filtering; and no-execution policy.
- `tests/test_m24a_planning_api.py`: requirement/plan/context/impact round trip, review revision,
  CAS conflict, missing-context handling, project scope, and execution-authority denial.
- `apps/desktop/tests/m24a-planning.test.ts`: planning controls and the absence of execute/apply/
  run/deploy/flash buttons.

## Required evidence

The final local evidence for this branch is:

- Full backend suite: **536 passed, 31 skipped**, coverage **82.53%**.
- M24A/API/version/OpenAPI focused suite: **11 passed**; M24A contract/API subset: **9 passed**.
- Ruff: **PASS**; Mypy: **PASS** for 166 source files.
- Fresh migration upgrade through `0041_m24a_engineering_planning` and explicit `alembic check`:
  **PASS**.
- OpenAPI export check and TypeScript contract check: **PASS**.
- Desktop lint, typecheck, build, and unit tests: **PASS**, **9 tests**.
- Tauri `cargo check` and `cargo test`: **PASS**, **3 tests**.
- Playwright `@ui`: **PASS**, **4 tests**, including the M24A planning panel flow.

The matching remote CI run and final head SHA are recorded in `FINAL_ACCEPTANCE.md`. A focused
failure is a release blocker until corrected; a passing focused suite is not a substitute for
full backend, desktop, packaging, and migration checks.
