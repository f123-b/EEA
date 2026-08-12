# M18 Engineering Dependency and Impact Graph Test Report

Date: 2026-08-12

Repository: `f123-b/EEA`

Branch: `codex/m18-dependency-impact-graph`

Base: `main` at `532d095b912cfa4926474bc0295c84990dde21e5`

Migration: `0024_m18_engineering_dependency_graph`

## Scope

This implementation adds the core-neutral engineering dependency graph, explicit
provider allowlist, semantic SHA-256 hashing, project-scoped edge persistence,
bound upstream revision/hash snapshots, deterministic impact analysis, status
precedence, invalidation propagation, cycle rejection, revalidation/rebinding,
bootstrap reconciliation, artifact dependency APIs, claim lifecycle propagation,
and synchronized OpenAPI/TypeScript contracts.

The graph remains separate from `TraceabilityEdge`. Dependency edges are uniform
upstream-to-downstream relations and are persisted with explicit dependency kind,
required flag, invalidation policy, evidence, and reason.

## Verification

Focused M18/M17/API/migration/OpenAPI tests: **46 passed**.

Repository verification under the authoritative Python 3.12.13 interpreter:

- `pytest -q`: **287 passed, 3 skipped**, coverage **83.16%**
- `pytest -q --no-cov`: **287 passed, 3 skipped**
- `ruff check .`: **PASS**
- `ruff format --check .`: **PASS**
- `mypy core/src application/src apps/backend/src`: **PASS**
- clean database upgrade twice: **PASS**
- clean database + `alembic check`: **PASS**
- `eea openapi export --check`: **PASS**
- `eea openapi typescript --check`: **PASS**
- `pnpm lint`: **PASS**
- `pnpm typecheck`: **PASS**
- `pnpm build`: **PASS**

The focused suite covers hash invariance, change observation, deterministic
diamond-graph BFS and deduplication, invalidation precedence, cycle rejection,
unknown-provider fail-closed behavior, project isolation, claim lifecycle CAS,
artifact routes, M17 source selection, review freshness, migration integrity,
and generated contract synchronization.

## Status

`M18 = IMPLEMENTED`

`READY_FOR_M18_REVIEW = YES`

`M18A = NOT_STARTED`

This report records implementation and automated verification. Human review is
now the remaining gate before M18 closure.
