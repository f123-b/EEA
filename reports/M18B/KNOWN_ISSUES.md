# M18B Known Issues

## Non-blocking pre-existing environment issue

Two existing M5 sandbox tests fail only in the current Windows sandbox environment:

- `test_structured_command_is_allowlisted_and_shell_free`
- `test_structured_command_enforces_timeout_output_and_secret_boundaries`

Classification: `PRE-EXISTING / ENVIRONMENT-SPECIFIC / NON-BLOCKING`.
No M18B code, test, or contract change was made to hide or reclassify these failures.

## Acceptance boundary

M18B is implemented and submitted for human final review. It is not marked accepted.
M18C Source Authority and all later milestones are not started.
