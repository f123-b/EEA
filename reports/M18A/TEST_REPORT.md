# M18A / M18AR Transactional Outbox & Recovery Test Report

Date: 2026-08-13

Repository: `f123-b/EEA`

Branch: `codex/m18a-transactional-outbox-recovery`

Base: `main` at `0d127e2e40dc3e73a9ef41b1aa276391357d7cf4`

Migration: `0025_m18a_transactional_outbox_recovery`

## Scope

M18A implements a durable transactional outbox and conservative recovery
boundary. M18AR closes the normal-runtime dispatcher, lease identity,
transactional race, artifact authority, scoped recovery, and diagnostic
contracts. It does not implement M18B or any later milestone.

The persistence contract contains:

- `outbox_events`: immutable event envelope, canonical SHA-256 payload hash,
  unique producer `event_key`, status, bounded attempts, availability time,
  lease owner/expiry, last error, processed time, and revision.
- `processed_events`: unique `(event_id, consumer_id)` markers with the event
  payload hash and optional result reference/hash.
- `side_effect_journal`: unique `(event_id, consumer_id, effect_key)` records
  with request hash, PREPARED/APPLIED/FAILED/RECONCILE_REQUIRED status, and
  result/error projection.

Delivery is at-least-once. Claims are compare-and-set updates with a bounded
lease. Retry uses deterministic exponential backoff capped at 60 seconds;
exhausted attempts become `DEAD_LETTER`. Unknown event types or unsupported
versions are rejected by the explicit handler allowlist and follow the same
retry/dead-letter path. External side effects with unknown outcomes remain
`RECONCILE_REQUIRED`; they are not guessed or replayed blindly.

Production integration publishes `project.created`, `artifact.created`, and
`build.completed` in the same SQL transaction as their business writes. The
default consumers are deterministic and idempotent. The lifecycle-owned
dispatcher performs bounded startup recovery, wake-triggered dispatch, and
polling fallback. Worker identity is unique per app start and shared by all
recovery paths in that app. Marker/journal/producer identity races use
savepoints and bounded SQLite busy retry; outer transactions survive expected
unique-key races. Artifact consumers require the authoritative Artifact row and
never fabricate it. Recovery and consistency APIs are project-scoped where
requested and separate transactional recovery from engineering freshness.

## Verification

Focused M18A/M18AR tests: **31 passed**.

Focused M18/M18R/M18A/M18AR regression set: **55 passed**.

The focused M18A assertions cover:

- canonical payload hashing and stable producer keys;
- API business-row plus outbox atomicity and pre-commit rollback;
- SQL commit followed by crash and startup replay;
- consumer-effect commit followed by crash and replay without duplicate
  `ArtifactRecord`;
- producer idempotency and payload-hash mismatch rejection;
- CAS claim/lease ownership, two-worker isolation, expiry reclaim, retry
  backoff, multi-consumer partial progress, and dead-letter behavior;
- SideEffectJournal request-hash mismatch and preservation of
  `RECONCILE_REQUIRED`;
- interrupted Job recovery to `FAILED_NEEDS_RECONCILE`.
- normal-runtime dispatcher delivery without manual reconciliation;
- unique app worker identity and lease renewal/takeover protection;
- producer, ProcessedEvent, SideEffectJournal, and derived Artifact concurrent
  identity races;
- savepoint survival for outer transactions and fail-closed payload/hash
  mismatches;
- authoritative Artifact enforcement and replay without duplicate artifacts;
- project-scoped recovery/reconciliation and ProjectConsistencyData status
  separation;
- bounded injectable SQLite busy retry and safe side-effect reconciler allowlist.

Repository verification on the local Windows Python 3.12.4 environment:

- `pytest --no-cov -x -q`: **262 passed, 1 skipped, then 1 pre-existing M5
  Windows sandbox subprocess failure**.
- `pytest --cov --cov-report=term-missing --cov-report=json -q
  --ignore=tests/test_m5_sandbox.py`: **325 passed**; total coverage
  **84.96%**.
- M18AR implementation-file coverage: core reliability **89%**,
  application reliability **92%**, backend recovery **86%**, and backend
  reliability repositories **74%**.
- `ruff check .`: **PASS**.
- `ruff format --check .`: **PASS**.
- `mypy`: **PASS**.
- Clean database upgrade through migration `0025` plus `alembic check`:
  **PASS** (`No new upgrade operations detected`).
- `eea openapi export --check`: **PASS**.
- `eea openapi typescript --check`: **PASS**.
- `pnpm lint`: **PASS**.
- `pnpm typecheck`: **PASS**.
- `pnpm build`: **PASS**.
- GitHub Linux CI is the final cross-platform acceptance gate after this
  implementation commit is pushed.

The existing Windows M5 sandbox subprocess environment note is retained as an
environment-specific issue and is not an M18A failure.

## Status

`M18A = IMPLEMENTED`

`M18AR = IMPLEMENTED`

`READY_FOR_M18A_FINAL_REVIEW = YES`

`READY_FOR_M18B = NO`

`M18B = NOT_STARTED`

This report records implementation verification only. M18A remains in Draft
PR review and has not been merged or accepted. M18B implementation has not
started.
