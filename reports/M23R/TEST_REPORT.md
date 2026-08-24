# M23R Test Report

## Scope

M23R closes the M23 Knowledge / Memory hardening boundary: backend-owned identity and verification
authority, freshness and conflict reconciliation, M22 rescan diffs and reviewed-finding promotion,
explicit desktop data states, workflow descriptor exposure, milestone SSOT, and generated contract
alignment.

Base implementation: `7726a328c8a991840bff00a337c97e8f28da4e9c`.
M23R implementation boundary: `42bc9e4`.

## Local evidence

| Check | Result |
|---|---|
| `py -3.12 -m pytest -q --no-cov` | **517 passed, 31 skipped, 13 warnings** |
| Focused M23/M22/API/version suite | **20 passed**; the full suite above also covers the final rescan assertion |
| `py -3.12 -m mypy` | **Passed**, 155 source files |
| Ruff check on changed backend/application/tests | **Passed** |
| Ruff format check on changed Python files | **Passed** |
| Desktop typecheck | **Passed** |
| Desktop lint | **Passed** |
| Desktop unit tests | **Passed**, 8 tests |
| OpenAPI export check | **Passed** |
| TypeScript contract export check | **Passed** |
| Clean Alembic upgrade/downgrade/upgrade and `alembic check` | **Passed** on a temporary clean database |
| Default `.eea/eea.db` Alembic check | **Environmental issue**: local DB references unknown historical revision `0028_m18d_hardware_commissioning_safety`; the DB was not modified |
| Tauri native build | Not run in this closeout |
| Remote CI / GitHub PR checks | Not run or mutated in this local closeout |

The pytest warnings are existing collection/deprecation warnings plus the intentional archive test
warning; they do not fail the configured suite.

## Migration and contract result

- Latest migration remains `0035_m23_knowledge_memory`.
- No historical migration was modified.
- No new M23R migration was required.
- `schemas/openapi.json` is synchronized with the backend routes and response fields.

## Acceptance decision

- P0: none identified.
- P1 in the requested M23R scope: cleared by the local gates above.
- M24: not started.
