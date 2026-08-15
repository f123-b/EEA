# M18C / M18CR Source Mutation Closure — Test Report

## Implementation identity

- Repository: `f123-b/EEA`
- Branch: `codex/m18c-source-authority`
- Reviewed M18C review HEAD: `6cc9b7057c5c210396ae4b2fcfdf5c5e6cd4baac`
- M18CR implementation commit: `25ba1a23da6a5057fa7722f41be2f40ede90f747`
- Scope: targeted closure of cross-session database CAS and hard-crash-safe multi-file source
  mutation. No M18D implementation or migration was started.

## Root blockers closed

1. `SqlAlchemySourceRepository` now claims and finalizes source mutations with conditional SQL
   updates keyed by project, expected SourceRevision, workspace revision, and active operation
   id. A failed claim returns `RESOURCE_BUSY` for an active owner or
   `SOURCE_REVISION_CONFLICT` for stale state; a losing session cannot touch the filesystem.
2. PatchProposal/generated apply and recovery use a durable PREPARED journal plus a controlled
   `.eea/source-recovery/<operation_id>/before|staged/manifest.json` bundle. The service verifies
   all AFTER hashes before creating SourceRevision N+1, marking a proposal APPLIED, publishing
   `source.changed`, finalizing the journal, and clearing ownership. Partial states roll forward
   from a valid staged bundle; unknown states fail closed as `RECOVERY_REQUIRED`.

## Focused verification

The focused command covered M12 source/build, M17 test/review, M18 dependency, M18A recovery/
outbox, M18B composition, M18BR composition authority, M18C source authority, M18CR source
mutation CAS, and M18R real benchmarks.

Result: **139 passed, 1 skipped**.

M18CR regression coverage includes real SQLAlchemy Session A/B ownership, cross-Service loser
exclusion, reconcile during a valid active PREPARED mutation, deterministic partial hard-crash
recovery to a complete AFTER state, and Git commit claim serialization. Existing SafePath,
symlink/traversal, ETag, stale proposal, generated-owned, bounded Git, outbox, dependency, and
exception-rollback regressions remain covered.

## Full verification

- Command: `.venv/Scripts/pytest.exe -q`
- Result: **378 passed, 4 skipped**.
- Two existing M5 sandbox tests fail only in the Windows sandbox environment and remain
  classified as `PRE-EXISTING / ENVIRONMENT-SPECIFIC / NON-BLOCKING`.
- Coverage: **84.07%**.

## Quality gates

- Ruff check: PASS
- Ruff format --check: PASS
- mypy: PASS
- Clean Alembic upgrade through `0029_m18cr_source_mutation_cas_recovery`: PASS
- `alembic check`: PASS
- OpenAPI export/check: PASS
- TypeScript contract export/check: PASS
- Desktop lint: PASS
- Desktop typecheck: PASS
- Desktop build: PASS
- GitHub CI: pending push of the M18CR closure commits

## State

```text
M18C = IMPLEMENTED
M18CR = IMPLEMENTED
READY_FOR_M18C_FINAL_REVIEW = YES
M18D = NOT_STARTED
```
