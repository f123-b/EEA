# M18C Source Authority / Workspace / Git Contract — Test Report

## Implementation identity

- Repository: `f123-b/EEA`
- Branch: `codex/m18c-source-authority`
- Base SHA: `2327ea12588b4c0d1facbb3669aed94ae69465d1`
- M18C implementation commit: `c9f2644 feat(m18c): implement source authority workspace contract`
- Reviewed M18B/M18BR main history remains in the base commit above.
- Scope: Source Authority, filesystem workspace, PatchProposal, generated ownership,
  bounded Git contract, source-change recovery, and no M18D work.

## Focused verification

Command scope:

```text
tests/test_m12_firmware.py
tests/test_m12a_escr.py
tests/test_m17_api.py
tests/test_m17_test_traceability_review.py
tests/test_m18_api.py
tests/test_m18_dependency_graph.py
tests/test_m18a_reliability.py
tests/test_m18b_domain_composition.py
tests/test_m18br_composition_authority.py
tests/test_m18c_source_authority.py
```

Result: **123 passed, 1 skipped**.

M18C regression coverage includes deterministic empty workspaces, file reads and ETags,
normal and stale patch application, optimistic two-writer conflicts, traversal and absolute
path rejection, internal and escaping symlink handling, multi-file atomic rollback,
generated-owned divergence, Git status/commit, durable SourceChanged outbox publication,
filesystem-replace/SQL-finalize recovery, temporary-file cleanup, external reconciliation,
and restart-safe current revision recovery.

## Full verification

- Command: `.venv/Scripts/python.exe -m pytest`
- Result: **373 passed, 4 skipped**.
- Two failures remain in existing M5 sandbox tests and are recorded as
  `PRE-EXISTING / ENVIRONMENT-SPECIFIC / NON-BLOCKING`.
- Coverage: **84.42%**.

## Quality gates

- Ruff check: PASS
- Ruff format --check: PASS
- mypy: PASS
- Clean Alembic upgrade through `0027_m18c_source_authority`: PASS
- `alembic check`: PASS
- OpenAPI export/check: PASS
- TypeScript contract export/check: PASS
- Desktop lint: PASS
- Desktop typecheck: PASS
- Desktop build: PASS
- GitHub CI push run `31871424363`: backend PASS, desktop PASS
- GitHub CI pull request run `31871451429`: backend PASS, desktop PASS

## State

```text
M18A = ACCEPTED_AND_MERGED
M18AR = ACCEPTED_AND_MERGED
M18AR.1 = ACCEPTED_AND_MERGED
READY_FOR_M18B = YES
M18B = ACCEPTED_AND_MERGED
M18BR = ACCEPTED_AND_MERGED
M18C = IMPLEMENTED
READY_FOR_M18C_FINAL_REVIEW = YES
M18D = NOT_STARTED
```
