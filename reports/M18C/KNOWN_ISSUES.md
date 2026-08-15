# M18C / M18CR Known Issues

## Non-blocking pre-existing environment issue

Two existing M5 sandbox tests fail only in the current Windows sandbox environment:

- `test_structured_command_is_allowlisted_and_shell_free`
- `test_structured_command_enforces_timeout_output_and_secret_boundaries`

Classification: `PRE-EXISTING / ENVIRONMENT-SPECIFIC / NON-BLOCKING`.
No M18CR code or contract change was made to hide, weaken, or reclassify these failures.

## M18CR acceptance boundary

The M18C review HEAD `6cc9b7057c5c210396ae4b2fcfdf5c5e6cd4baac` exposed two P1 root blockers:

- Blocker A: cross-session source mutation CAS was not a database atomic reservation.
- Blocker B: Python exception rollback did not provide hard-crash-safe multi-file recovery.

Both are closed by implementation commit `25ba1a23da6a5057fa7722f41be2f40ede90f747` and the
focused regression evidence in `TEST_REPORT.md`. The repository retains only source metadata,
manifests, journals, and temporary recovery evidence in SQL/workspace-internal storage; the
editable source workspace remains the sole source-byte authority.

The execution environment already had PR #8 merged before this M18CR continuation began. This
closure did not merge a PR, create a replacement PR, start M18D, or modify M18D code. The state
labels below are the maximum M18CR implementation state required by this task and do not assert
human final acceptance.
