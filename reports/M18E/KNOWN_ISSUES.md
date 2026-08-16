# M18E Known Issues

## PRE-EXISTING / ENVIRONMENT-SPECIFIC / NON-BLOCKING

Two existing M5 Windows sandbox tests fail in this local environment:

- `test_structured_command_is_allowlisted_and_shell_free`
- `test_structured_command_enforces_timeout_output_and_secret_boundaries`

The failures are unrelated to M18E changes and reproduce the previously recorded Windows
sandbox/toolchain behavior. The full run still reaches **83.76%** coverage and all M18E-focused
tests pass.

The local ignored `.eea/eea.db` also contains a stale historical Alembic version pointing to the
removed `0028_m18d_hardware_commissioning_safety` revision. It is not used for the clean M18E
database gate: a fresh database upgraded through `0031` and checked with Alembic passes.

Rust/Tauri cargo checks were unavailable because `cargo` is not installed on this workstation.
This is an environment limitation, not a reported Rust PASS; CI remains authoritative for any
Rust toolchain coverage.

## Scope boundary

No M19 implementation was started. M18E remains unmerged and awaits final human acceptance.
