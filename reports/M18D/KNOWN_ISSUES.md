# M18D Known Issues

## Non-blocking pre-existing environment issue

Two existing M5 sandbox tests fail only in the current Windows sandbox environment:

- `test_structured_command_is_allowlisted_and_shell_free`
- `test_structured_command_enforces_timeout_output_and_secret_boundaries`

Classification: `PRE-EXISTING / ENVIRONMENT-SPECIFIC / NON-BLOCKING`.
No M18D code or contract change was made to hide, weaken, or reclassify these failures.

## Local database note

The clean temporary database used for M18D verification upgrades through migration `0028` and
passes `alembic check`. The pre-existing workspace `.eea/eea.db` contains historical schema
drift from earlier local runs; it was not used as the clean migration gate and was not modified
or deleted by this task.

## Acceptance boundary

M18D is implemented and ready for human final review. It is not marked accepted here. M18E has
not started.
