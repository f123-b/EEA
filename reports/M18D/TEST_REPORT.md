# M18D Hardware Commissioning & Safety — Test Report

## Implementation identity

- Repository: `f123-b/EEA`
- Branch: `codex/m18d-hardware-commissioning-safety`
- Clean branch base and merge-base: `97d62e47c7bf287627d051197e6ef756abf89523`
- Implementation commit: `fca5962be81309e50290bf1767f03457067fc40a`
- Migration: `0030_m18d_hardware_commissioning_safety`
- Migration parent: `0029_m18cr_source_mutation_cas_recovery`
- Superseded PR #9 was closed without merge; its pre-M18CR state is preserved on
  `archive/m18d-pre-m18cr-8327ae6` at `8327ae66dbba1674139e6ed3db6b4ef2d79bf1e6`.

## Implemented safety contract

The application-owned commissioning lifecycle is:

```text
CREATED → PREFLIGHT → FLASHED_SAFE → SENSOR_CHECK → LOW_POWER
        → CLOSED_LOOP_LIMITED → USER_APPROVAL → NORMAL_OPERATION
```

Fail-closed terminal or recovery states are `BLOCKED`, `ABORTED`, `EMERGENCY_STOP`, `FAULTED`,
and `ROLLBACK_REQUIRED`. Every transition is validated by the application service and persisted
with revision-aware CAS; no plugin or adapter can bypass the state machine.

The implementation records immutable per-session `SafetyLimit` snapshots, validates conservative
limits before limited execution, requires a `SafeState` with torque/PWM/actuator gating, and
requires stable hardware identity fields (probe serial, target identifier, MCU, USB VID/PID, and
port path). Permissions are deny-by-default and separate `FLASH`, `DEBUG`, `HARDWARE_CONTROL`,
and `ACTUATOR_ENABLE` capabilities at the relevant gates.

`ResourceLock` validation checks lease and heartbeat freshness. E-stop and watchdog loss invoke
the adapter safe-state path and quarantine every session lock; failure to verify either safe state
or lock quarantine remains `ROLLBACK_REQUIRED`. The Fake adapter is bounded and fault-injectable
for identity mismatch, flash/sensor/safe-state/overcurrent/overspeed/watchdog/timeout and E-stop
paths.

## M18CR and recovery integration

Commissioning preflight binds the session to the exact project-scoped artifact hash and the exact
`BuildRun → SourceRevision + BuildInputSnapshot` IDs. It rejects missing, failed, cross-project,
or drifted bindings. The service emits durable commissioning events through the existing M18A
outbox and recovery/journal path; it does not create a second side-effect or recovery authority.

MotorControl contributes commissioning rules and bounded steps additively through the plugin
boundary; Core owns the safety state machine and final actuator-enable gate.

## Verification

Focused command covered M18/M18R/M18A/M18AR/M18AR.1/M18B/M18BR/M18C/M18CR/M18D, including the
M18D state machine, permission failures, identity binding, safety limits, SafeState, lock heartbeat
loss/quarantine, E-stop/watchdog recovery, exact source/build binding, Fake adapter faults,
MotorControl contribution, and existing CAS/outbox/recovery regressions.

Result: **179 passed, 1 skipped**.

Local full verification:

- `.venv/Scripts/python.exe -m pytest -q`: **393 passed, 4 skipped**.
- Coverage: **84.11%**.
- Two existing M5 sandbox tests fail only in the Windows sandbox environment and remain
  classified as `PRE-EXISTING / ENVIRONMENT-SPECIFIC / NON-BLOCKING`.

Quality gates:

- Ruff check: PASS
- Ruff format --check: PASS
- mypy: PASS
- Clean Alembic upgrade through `0030_m18d_hardware_commissioning_safety`: PASS
- `alembic check`: PASS
- OpenAPI export/check: PASS
- TypeScript contract export/check: PASS
- Desktop lint: PASS
- Desktop typecheck: PASS
- Desktop build: PASS

## State

```text
M18C = ACCEPTED_AND_MERGED
M18CR = ACCEPTED_AND_MERGED
M18D = IMPLEMENTED
READY_FOR_M18D_FINAL_REVIEW = YES
M18E = NOT_STARTED
```

M18D remains unmerged and awaits human final review. No M18E implementation was started.
