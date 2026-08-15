# M18D Known Issues

## Non-blocking pre-existing environment issue

Two existing M5 sandbox tests fail only in the current Windows sandbox environment:

- `test_structured_command_is_allowlisted_and_shell_free`
- `test_structured_command_enforces_timeout_output_and_secret_boundaries`

Classification: `PRE-EXISTING / ENVIRONMENT-SPECIFIC / NON-BLOCKING`.
No M18D code or contract change was made to hide, weaken, or reclassify these failures.

## Local database note

The repository's default local `.eea/eea.db` may still contain the superseded pre-M18CR PR #9
revision. M18D verification used a clean temporary database and passed upgrade/check through
`0030_m18d_hardware_commissioning_safety`; the stale local database was not rewritten.

## Acceptance boundary

M18D is implemented and ready for human final review. It is not accepted or merged by this
implementation task. M18E remains explicitly not started.
