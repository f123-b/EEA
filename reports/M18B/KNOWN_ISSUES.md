# M18B/M18BR Known Issues

## Non-blocking pre-existing environment issue

Two existing M5 sandbox tests fail only in the current Windows sandbox environment:

- `test_structured_command_is_allowlisted_and_shell_free`
- `test_structured_command_enforces_timeout_output_and_secret_boundaries`

Classification: `PRE-EXISTING / ENVIRONMENT-SPECIFIC / NON-BLOCKING`.
No M18B/M18BR code, test, or contract change was made to hide or reclassify these failures.

## Acceptance boundary

No M18B/M18BR implementation blocker remains after the local and GitHub verification
listed in `TEST_REPORT.md`. The public apply contract requires both preview tokens;
runtime composition rejects persisted-state drift; migration compatibility is
fail-closed; and real SQL rollback/CAS paths are covered. The final human review
accepted M18B and M18BR at reviewed final HEAD
`6131b0339fc7a92e9b0c1665a9c0edf18d193ef5`.

M18B and M18BR are accepted. M18C Source Authority and all later milestones are not
started. The two M5 Windows sandbox failures remain
`PRE-EXISTING / ENVIRONMENT-SPECIFIC / NON-BLOCKING`.
