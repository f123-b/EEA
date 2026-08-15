# M18B Domain Composition Contract — Test Report

## Implementation identity

- Repository: `f123-b/EEA`
- Branch: `codex/m18b-domain-composition-contract`
- Base SHA: `39831c111d7be554500acba8fa1b812e0dd5b044`
- Implementation commit: `fa2c22ee20b9f6ebbf1b78df7124987c6d4e8391`
- Scope: M18B only; M18C and later milestones were not started.

## Focused verification

Command scope:

```text
tests/test_m14_domain_extensions.py
tests/test_m15_motor_control.py
tests/test_m18_api.py
tests/test_m18_dependency_graph.py
tests/test_m18a_reliability.py
tests/test_m18r_real_benchmarks.py
tests/test_m18b_domain_composition.py
```

Result: **122 passed**.

M18B regression coverage includes 0/1/2/3 Domain compositions, duplicate capability
providers, registration-order determinism, missing/conflicting/cyclic resolution,
atomic failure rollback, CAS, stale preview, restart persistence, migration dry-run,
disable/enable configuration preservation, and API preview/apply/current-state flows.

## Full verification

- Command: `.venv/Scripts/python.exe -m pytest`
- Result: **354 passed, 3 skipped**
- Coverage: **84.40%**
- Two failures remain in existing M5 Windows sandbox tests and are recorded as
  `PRE-EXISTING / ENVIRONMENT-SPECIFIC / NON-BLOCKING`.

## Quality gates

- Ruff check: PASS
- Ruff format --check: PASS
- mypy: PASS
- Clean Alembic upgrade: PASS
- Clean `alembic check`: PASS
- OpenAPI export/check: PASS
- TypeScript contract export/check: PASS
- Desktop lint: PASS
- Desktop typecheck: PASS
- Desktop build: PASS
- GitHub CI: pending Draft PR push at report creation; update with the final run.

## State

```text
M18A = ACCEPTED_AND_MERGED
M18AR = ACCEPTED_AND_MERGED
M18AR.1 = ACCEPTED_AND_MERGED
READY_FOR_M18B = YES
M18B = IMPLEMENTED
READY_FOR_M18B_FINAL_REVIEW = YES
M18B = ACCEPTED = NOT_CLAIMED
M18C = NOT_STARTED
```
