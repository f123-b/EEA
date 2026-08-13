# M18A Transactional Outbox & Recovery Test Report

Date: 2026-08-13

Repository: `f123-b/EEA`

Branch: `codex/m18a-transactional-outbox-recovery`

Base: `main` at `0d127e2e40dc3e73a9ef41b1aa276391357d7cf4`

Migration: `0025_m18a_transactional_outbox_recovery`

## Scope

M18A implements a durable transactional outbox and conservative recovery
boundary. It does not implement M18B or any later milestone.

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
default consumers are deterministic and idempotent. Startup recovery reclaims
expired leases, marks stale RUNNING jobs as `FAILED_NEEDS_RECONCILE`, and
dispatches a bounded batch.

## Verification

Focused M18A tests: **12 passed**.

Focused M18/M18R/M18A regression set: **36 passed**.

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

Repository verification on the local Windows Python 3.12.4 environment:

- `pytest --no-cov -x -q`: **243 passed, 1 skipped, then 1 pre-existing M5
  Windows sandbox subprocess failure**.
- `pytest --cov --cov-report=term-missing --cov-report=json -q
  --ignore=tests/test_m5_sandbox.py`: **306 passed**; total coverage
  **84.91%**.
- M18A implementation-file coverage: core reliability **84.96%**,
  application reliability **91.78%**, backend recovery **89.47%**, and
  backend reliability repositories **90.91%**.
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

`READY_FOR_M18A_REVIEW = YES`

`M18B = NOT_STARTED`

This report records implementation verification only. M18A remains in Draft
PR review and has not been merged or accepted.
