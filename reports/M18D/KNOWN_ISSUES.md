# M18D Known Issues

## Non-blocking pre-existing environment issue

Two existing M5 sandbox tests fail only in the current Windows sandbox environment:

- `test_structured_command_is_allowlisted_and_shell_free`
- `test_structured_command_enforces_timeout_output_and_secret_boundaries`

Classification: `PRE-EXISTING / ENVIRONMENT-SPECIFIC / NON-BLOCKING`.
No M18D code or contract change was made to hide, weaken, or reclassify these failures.

## M18DR verification identity

- Reviewed M18D HEAD before repair: `2fc232825d07294ef474a8d308c004927765c363`
- M18DR implementation commit: `c5308ec95b6e38c9e757b5aa59ef78523a834c67`
- GitHub PR CI `31894738013`: backend PASS, desktop PASS.
- GitHub push CI `31894735902`: backend PASS, desktop PASS.

## Local database note

The repository's default local `.eea/eea.db` may still contain the superseded pre-M18CR PR #9
revision. M18D verification used a clean temporary database and passed upgrade/check through
`0030_m18d_hardware_commissioning_safety`; the stale local database was not rewritten.

## Acceptance boundary

M18D and M18DR are implemented and ready for human final review. PR #11 remains OPEN and Draft;
it is not accepted or merged by this implementation task. M18E remains explicitly not started.
