# M18D Hardware Commissioning & Safety — Test Report

## Implementation identity

- Repository: `f123-b/EEA`
- Branch: `codex/m18d-hardware-commissioning-safety`
- Clean branch base and merge-base: `97d62e47c7bf287627d051197e6ef756abf89523`
- Reviewed M18D HEAD before repair: `2fc232825d07294ef474a8d308c004927765c363`
- M18DR implementation commit: `c5308ec95b6e38c9e757b5aa59ef78523a834c67`
- Reviewed M18DR HEAD before Final Closure: `2757832435253a0f81b51d0b4902f3e731c35385`
- M18DR Final Closure implementation commit: `6afeec383f767634ea45b8453fb7490d45f66ebe`
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

`ResourceLock` validation checks project, owner session, resource type/id, lease and heartbeat
freshness; database acquisition has an ACTIVE partial unique constraint and an atomic claim path.
E-stop and watchdog loss invoke the adapter safe-state path and quarantine every session lock;
failure to verify either safe state or lock quarantine remains `ROLLBACK_REQUIRED`. The Fake
adapter is bounded and fault-injectable for identity mismatch, flash/sensor/safe-state,
overcurrent/overspeed/watchdog/operation-specific timeout and E-stop paths.

M18DR closes the final safety authority and side-effect gaps: API permission fields are ignored,
server-issued `PermissionToken` records are verified against exact actor/project/session/target
scope, dangerous actions claim the session revision before adapter access, and the existing M18A
`OutboxEvent` + `SideEffectJournal` is used for durable hardware intents. Startup recovery marks
unknown prepared hardware outcomes `RECONCILE_REQUIRED`, quarantines locks, and never retries a
dangerous adapter action blindly. Final Closure additionally makes missing `PermissionAuthority`
fail closed, gives EmergencyStop/SafeState an atomic safety-preemption path for stale
`RECONCILE_REQUIRED` actions, permits safe-action retry after a crashed E-stop, and guarantees an
unverified SafeState is `ROLLBACK_REQUIRED`/`UNKNOWN` rather than `EMERGENCY_STOP`. Core-neutral
commissioning contributions now gate `CLOSED_LOOP_LIMITED`, and limited-operation measurements
are canonicalized and checked for unit, dimension, runtime, PWM-enable duration, current-ramp
rate, speed-ramp rate, current, dq-current, speed, voltage, temperature, duty, and applicable
position limits. `CURRENT_RATE` uses canonical `A/s`; speed ramp uses
`ANGULAR_ACCELERATION` with `rpm/s` normalization.

## M18CR and recovery integration

Commissioning preflight binds the session to the exact project-scoped artifact hash and the exact
`BuildRun → SourceRevision + BuildInputSnapshot` IDs. It rejects missing, failed, cross-project,
or drifted bindings. The service emits durable commissioning events through the existing M18A
outbox and recovery/journal path; it does not create a second side-effect or recovery authority.

MotorControl contributes commissioning rules and bounded steps additively through the plugin
boundary; Core owns the safety state machine and final actuator-enable gate.

## Final Closure regression coverage

- Missing `PermissionAuthority` cannot authorize dangerous permissions, even when a request
  supplies a raw permission set; application tests explicitly inject `FakePermissionAuthority`.
- Recovered prepared `FLASH`, `LOW_POWER`, and `EMERGENCY_STOP` actions exercise atomic safety
  preemption; dangerous actions are not replayed and safety actions can retry.
- Limit violations verify `EMERGENCY_STOP/ACTIVE` only after SafeState is proven, and
  `ROLLBACK_REQUIRED/UNKNOWN` when SafeState verification fails.
- Missing or excessive PWM-enable duration, current-ramp rate, and speed-ramp rate fail closed;
  `rpm/s` normalizes to angular acceleration; max test runtime and max PWM duration are tested as
  independent limits.

## Verification

Focused command covered M18/M18R/M18A/M18AR/M18AR.1/M18B/M18BR/M18C/M18CR/M18D, including the
M18DR authority, lock exclusivity, action-claim/journal recovery, state machine, permission
separation and scope, identity binding, safety limits, SafeState, lock heartbeat loss/quarantine,
E-stop/watchdog recovery, exact source/build binding, Fake adapter faults, MotorControl
contributions, and existing CAS/outbox/recovery regressions.

Result: **159 passed, 1 skipped**.
The M18D/M18DR commissioning regression module itself reports **57 passed**.

Local full verification:

- `.venv/Scripts/python.exe -m pytest -q`: **435 passed, 4 skipped**; two existing M5 sandbox
  tests fail only in the Windows sandbox environment.
- Coverage: **84.19%**.
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

GitHub CI:

- PR run `31924721927`: backend PASS, desktop PASS.
- Push run `31924719464`: backend PASS, desktop PASS.

## State

```text
M18C = ACCEPTED_AND_MERGED
M18CR = ACCEPTED_AND_MERGED
M18D = IMPLEMENTED
M18DR = IMPLEMENTED
READY_FOR_M18D_FINAL_REVIEW = YES
M18E = NOT_STARTED
```

M18D/M18DR remain unmerged and await human final review. PR #11 remains OPEN and Draft. No M18E
implementation was started.
