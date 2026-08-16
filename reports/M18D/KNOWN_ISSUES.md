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
- Reviewed M18DR HEAD before Final Closure: `2757832435253a0f81b51d0b4902f3e731c35385`
- M18DR Final Closure implementation commit: `6afeec383f767634ea45b8453fb7490d45f66ebe`
- Reviewed final acceptance HEAD: `7dd86a3080b253010cf18f64accee3e2ca665a28`
- GitHub PR CI `31925059142`: backend PASS, desktop PASS.
- GitHub push CI `31925057389`: backend PASS, desktop PASS.

## Local database note

The repository's default local `.eea/eea.db` may still contain the superseded pre-M18CR PR #9
revision. M18D verification used a clean temporary database and passed upgrade/check through
`0030_m18d_hardware_commissioning_safety`; the stale local database was not rewritten.

## Acceptance status

M18D = ACCEPTED
M18DR = ACCEPTED
READY_FOR_M18E = YES
M18E = NOT_STARTED

Human final acceptance is complete at the reviewed final HEAD above. PR #11 merge closure remains
the next repository operation; M18E remains explicitly not started until the merged main branch
and its CI are verified.
