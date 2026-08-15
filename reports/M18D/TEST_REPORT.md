# M18D Hardware Commissioning & Safety — Test Report

## Implementation identity

- Repository: `f123-b/EEA`
- Branch: `codex/m18d-hardware-commissioning-safety`
- Base SHA: `43e37011b5154736a2df48a3c90e39c5a801c4a4`
- M18D implementation commit: `0fb0df1d17674d0635d0e6994c69e4dfe92a4236`
- Commit subject: `feat(m18d): implement hardware commissioning safety`
- Scope: Hardware Commissioning & Safety only; M18E was not started.

## Focused verification

Focused M18D and regression commands covered:

```text
tests/test_m18d_hardware_commissioning.py
tests/test_m18_api.py
tests/test_m18_dependency_graph.py
tests/test_m18a_reliability.py
tests/test_m18b_domain_composition.py
tests/test_m18br_composition_authority.py
tests/test_m18c_source_authority.py
tests/test_m18r_real_benchmarks.py
tests/test_m12_firmware.py
tests/test_m12a_escr.py
tests/test_m15_motor_control.py
tests/test_m17_api.py
tests/test_m17_test_traceability_review.py
tests/test_architecture.py
```

Result: **174 passed, 1 skipped**.

The 13 M18D regression tests cover safe defaults and source binding, permission/lock/identity
and artifact/hash gates, flash-without-actuator enablement, safe-state failure, illegal
transitions, sensor/overcurrent/overspeed failures, watchdog and lock loss, cancellation and
idempotent emergency stop, CAS/stale approval, monotonic limits, durable evidence/outbox replay,
and the CAS-protected API surface.

## Full verification

- Command: `.venv/Scripts/pytest.exe -q`
- Result: **386 passed, 4 skipped**.
- Two existing M5 sandbox tests fail only in the current Windows sandbox environment:
  `test_structured_command_is_allowlisted_and_shell_free` and
  `test_structured_command_enforces_timeout_output_and_secret_boundaries`.
- Classification: `PRE-EXISTING / ENVIRONMENT-SPECIFIC / NON-BLOCKING`.
- Coverage: **84.46%**.

## Quality gates

- Ruff check: PASS
- Ruff format `--check`: PASS
- mypy: PASS
- Clean Alembic upgrade through `0028_m18d_hardware_commissioning_safety`: PASS
- Clean-database `alembic check`: PASS
- OpenAPI export/check: PASS
- TypeScript contract export/check: PASS
- Desktop lint: PASS
- Desktop typecheck: PASS
- Desktop build: PASS
- GitHub CI: pending Draft PR push

## M18D contract summary

- Core owns the explicit commissioning state machine and exceptional fail-closed states.
- `SAFE_COMMISSIONING` is the only built-in profile; limits use canonical EngineeringValue
  units and can only tighten.
- The adapter exposes only bounded identify/probe/flash/safe-state/fault/sensor/watchdog/e-stop
  operations; no arbitrary shell, PWM, motor, or production-enable operation is exposed.
- FLASH, DEBUG, HARDWARE_CONTROL, and ACTUATOR_ENABLE remain separate permissions.
- Target identity, probe identity, active HardwareTarget lock, capability verification, watchdog,
  source/build/artifact binding, and CAS revision are checked before mutation.
- In-flight operations fail safe; cancellation, crash, timeout, watchdog loss, lock loss, and
  emergency stop do not become warnings or successful commissioning.
- Evidence and safety events use the existing M18A Outbox/Recovery/SideEffectJournal path.
- MotorControl contributes additive commissioning rules and observations only; Core retains
  commissioning authority.

## State

```text
M18C = ACCEPTED_AND_MERGED
M18D = IMPLEMENTED
READY_FOR_M18D_FINAL_REVIEW = YES
M18E = NOT_STARTED
```
