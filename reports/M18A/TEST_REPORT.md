# M18A / M18AR Transactional Outbox & Recovery Test Report

Date: 2026-08-15

Repository: `f123-b/EEA`

Branch: `codex/m18a-transactional-outbox-recovery`

Base: `main` at `0d127e2e40dc3e73a9ef41b1aa276391357d7cf4`

Reviewed implementation HEAD:
`68401b60b88935e7c19bc0309c1845eab3328555`

Implementation commit:
`fix(m18a): close dispatcher shutdown lifecycle`

Migration: `0025_m18a_transactional_outbox_recovery`

## Scope

M18A implements a durable transactional outbox and conservative recovery
boundary. M18AR closes the normal-runtime dispatcher, lease identity,
transactional race, artifact authority, scoped recovery, and diagnostic
contracts. It does not implement M18B or any later milestone.

M18AR.1 closes transaction replay and recovery CAS semantics without
expanding the M18A contract. Commit-busy retries replay the complete unit of
work; reclaim, interrupted-job recovery, renew, finalize, and claim paths are
conditional mutations; synchronous dispatcher work runs in a bounded,
joinable worker lifecycle; diagnostics count each outstanding event once; and
lease-loss finalize conflicts are excluded from retry/dead-letter summaries.

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

Focused M18A/M18AR/M18AR.1 tests: **39 passed**.

Focused M18/M18R/M18A/M18AR/M18AR.1 regression set: **69 passed**.

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
- fault-injected busy during write and commit with complete unit-of-work replay;
- false-success prevention after bounded busy exhaustion;
- recovery CAS protection against renewed/taken-over leases and worker
  heartbeat/finish mutations;
- lost-lease finalize conflict accounting and exact expired-processing
  diagnostics;
- slow synchronous dispatcher work running without blocking the asyncio loop.

Repository verification on the local Windows Python 3.12.4 environment:

- Local full pytest: **345 passed, 3 skipped**, with **2 existing Windows M5
  sandbox environment failures**.
- Total coverage: **84.37%**.
- M18AR.1 implementation-file coverage: backend recovery **85%**, backend
  reliability repositories **80%**, and core/application reliability remain
  covered by the full-suite gate.
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
- GitHub CI run `31859806569`: backend **PASS**; desktop **PASS**.

The existing Windows M5 sandbox subprocess environment note is retained as
`PRE-EXISTING / ENVIRONMENT-SPECIFIC / NON-BLOCKING` and is not an M18A
failure.

## Status

`M18A = ACCEPTED`

`M18AR = ACCEPTED`

`M18AR.1 = ACCEPTED`

`READY_FOR_M18B = YES`

`M18B = NOT_STARTED`

M18A, M18AR, and M18AR.1 are accepted at the reviewed implementation HEAD.
M18B has not been implemented and remains `NOT_STARTED`.
