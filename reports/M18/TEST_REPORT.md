# M18R Semantic Freshness, Runtime Binding & Recovery Test Report

Date: 2026-08-13

Repository: `f123-b/EEA`

Branch: `codex/m18-dependency-impact-graph`

Pull request: `#5` (Draft; not merged)

Base: `main` at `532d095b912cfa4926474bc0295c84990dde21e5`

Migration: `0024_m18_engineering_dependency_graph`

## Scope

M18R closes semantic freshness, runtime binding, recovery, persistence, and
fail-closed graph gaps in the existing M18 implementation. The dependency graph
is project-scoped and separate from `TraceabilityEdge`; bindings are created
from explicit durable references through an allowlisted provider registry.

## Real DB/API acceptance benchmarks

The acceptance set is implemented by
`tests/test_m18r_real_benchmarks.py` and the M18 graph suite. It covers all 27
requested categories:

1. Revision-only input changes do not propagate stale state.
2. `NONE` invalidation policy does not propagate a semantic change.
3. Ordered sequences produce different semantic hashes when reordered.
4. Set-like references normalize order before hashing.
5. Claim `verification_levels` participate in semantic identity.
6. Artifact storage-location changes are non-semantic.
7. Historical artifact dependency hash mismatch is detected as stale.
8. Successful revalidation recovers a stale node to current.
9. One-edge rebind cannot clear another mismatched incoming edge.
10. All incoming bindings matching permits current recovery.
11. Concurrent invalidation merges evidence instead of losing updates.
12. Concurrent invalid status takes precedence over stale.
13. Graph stale status is projected by artifact detail/list/stale APIs.
14. Historical dependency hash H1 versus current H2 is covered against real DB.
15. Runtime-created graph nodes work without an application restart.
16. Bootstrap persists complete explicit-reference edges.
17. Bootstrap reports gaps and does not swallow real graph errors.
18. Bootstrap is idempotent.
19. Requirement mutation stales the real TestIR → TestRun → ReviewRun chain.
20. Errata Claim → PinAssignment → MCUConfigIR → FirmwareIR propagates INVALID.
21. An unrelated PinAssignment is not included in that impact plan.
22. SourceRevision → TestRun is represented by explicit durable input.
23. SourceRevision → BuildRun and Build/StaticAnalysis → ReviewRun are explicit.
24. Persisted ProtocolIR outputs fan out to four durable output nodes and stale.
25. Global Claim lifecycle mutation is denied by project scope.
26. Unknown dependency API entity types fail closed with capability unavailable.
27. Diamond impacts are deduplicated and retain the stronger projected status.

Verification result:

- `pytest --no-cov -q tests/test_m18_dependency_graph.py tests/test_m18r_real_benchmarks.py`: **17 passed**.
- `pytest --no-cov -q tests/test_m18_dependency_graph.py tests/test_m18r_real_benchmarks.py tests/test_m18_api.py`: **20 passed**.
- `pytest -q`: **296 passed, 3 skipped, 2 pre-existing M5 failures**; coverage
  **83.99%**. The two Windows M5 sandbox subprocess failures occur because the
  local interpreter redirector does not provide the runtime behavior those tests
  assume; no M18R test fails.
- `ruff check .`: **PASS**.
- `ruff format --check .`: **PASS**.
- `mypy core/src application/src apps/backend/src`: **PASS**.
- Clean database upgrade twice plus `alembic check`: **PASS**.
- `eea openapi export --check`: **PASS**.
- `eea openapi typescript --check`: **PASS**.
- `pnpm lint`: **PASS**.
- `pnpm typecheck`: **PASS**.
- `pnpm build`: **PASS**.

## Status

`M18R = IMPLEMENTED`

`READY_FOR_M18_FINAL_REVIEW = YES`

`M18A = NOT_STARTED`

This report records implementation and automated verification on the existing
Draft PR. No merge action was performed.
