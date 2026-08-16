# M18E Known Issues

## PRE-EXISTING / ENVIRONMENT-SPECIFIC / NON-BLOCKING

Two existing M5 Windows sandbox tests fail in this local environment:

- `test_structured_command_is_allowlisted_and_shell_free`
- `test_structured_command_enforces_timeout_output_and_secret_boundaries`

The failures are unrelated to M18E changes and reproduce the previously recorded Windows
sandbox/toolchain behavior. The full run still reaches **84.28%** coverage and all M18E/M18ER-
focused tests pass.

The local ignored `.eea/eea.db` also contains a stale historical Alembic version pointing to the
removed `0028_m18d_hardware_commissioning_safety` revision. It is not used for the clean M18E
database gate: a fresh database upgraded through `0032_m18er_reliability_closure` and checked
with Alembic passes.

Rust/Tauri cargo checks were unavailable locally because `cargo` is not installed on this
workstation. GitHub CI is authoritative and the final M18ER run executed `cargo check`, `cargo
test`, and `tauri build --ci` successfully.

## Scope boundary

No M19 implementation was started. M18E remains unmerged and awaits final human acceptance.

## Final CI history

Two superseded M18ER CI attempts failed before the final packaging closure because the Tauri
icon input was absent. The final runs `31946613210` (push) and `31946616696` (Draft PR) are
green across backend, desktop-web, and desktop-tauri; no M18ER blocker remains.
