# M1 Test Report

## Milestone

- Milestone: M1 Core Domain
- Corrected architecture baseline: EEA V1.3.1 candidate
- Implementation version: 1.3.1.dev0
- Date: 2026-08-11
- Result: PASS

## Implemented scope

- Framework-independent Core entities: Project, Artifact, Evidence, Issue, EngineeringDecision,
  Job, PermissionAuditRecord, and TraceabilityEdge
- Stable UUID, schema version, revision, timestamps, and metadata contract
- Canonical Core enums and deterministic engineering errors
- Project application service and SQLAlchemy repository adapter
- Project create/list/read/update/soft-delete REST lifecycle
- ETag/If-Match and expected-revision optimistic concurrency
- Versioned schema registry and JSON Schema endpoints
- Alembic `0002_m1` migration with constraints and forward/reverse coverage
- Deterministic OpenAPI and TypeScript contract generation
- V1.3.1 FIX-01 and FIX-08 invariants relevant to the current milestone

## Acceptance results

| Check | Result | Evidence |
|---|---:|---|
| Python lint | PASS | `ruff check .` |
| Strict type checking | PASS | mypy; 24 source files |
| Python tests | PASS | 30 passed |
| Overall coverage | PASS | 96.74% branch-aware coverage |
| Core Domain coverage | PASS | 100%, exceeding the 80% M1 gate |
| Migration forward/reverse | PASS | Empty DB through M0→M1 and downgrade to base |
| Migration drift | PASS | Alembic `check` reports no pending schema operations |
| Real-process smoke | PASS | Fresh migration, Uvicorn health, project create 201, and If-Match update 200 |
| Project lifecycle | PASS | Create/list/read/update/soft-delete |
| Optimistic locking | PASS | Stale and racing revisions return deterministic conflict |
| API envelopes/errors | PASS | Success/error envelopes and request IDs verified |
| OpenAPI synchronization | PASS | Committed schema equals runtime schema |
| TypeScript synchronization | PASS | Generated contract equals Core enums |
| Frontend enum handling | PASS | Exhaustive JobStatus record type-checks |
| FIX-01 Core boundary | PASS | Named MotorControl definition/import invariants |
| FIX-08 enum/error synchronization | PASS | Named DB/OpenAPI/TypeScript/frontend invariants |
| Frontend lint/typecheck/build | PASS | ESLint, TypeScript, and Vite production build |
| Native Tauri build | SKIP | Rust/Cargo unavailable; not an M1 hard gate |
| Hosted GitHub Actions | SKIP | No remote repository or runner was supplied |

Skipped integrations are not represented as passing results.

## Benchmark delta

No engineering-domain benchmark applies at M1. The new regression baseline is 30 tests with
96.74% overall and 100% Core Domain coverage.

## Budget usage

Not applicable. AI Provider and budget accounting begin at M2.
