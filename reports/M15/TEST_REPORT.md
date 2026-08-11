# M15R MotorControl Integration & Contract Closure Test Report

Date: 2026-08-11
Repository: `f123-b/EEA`
Branch: `codex/eea`
Pull Request: `#2` (`codex/eea -> main`)
Migration head: `0021_m14_domain_configuration_error_catalog`
Database migration added: **NO**

## Scope

M15R closes the integration and contract gaps in the M15 bundled MotorControl Domain Plugin. It does
not implement M16 ProtocolIR, M17, M19 FOC E2E, or M21 Desktop UI Vertical Slice.

The accepted M15 scope is **MotorControl Plugin Contract Acceptance** only:

- Core-neutral Domain executable-validation contract using opaque inputs;
- project-scoped `MotorControlIR` and current `MCUConfigIR` validation inputs;
- actual `POST /projects/{project_id}/domains/{domain_id}/validate` execution;
- deterministic evaluation of all 11 frozen MotorControl rules;
- explicit `PASS`, `FAIL`, `UNKNOWN`, and `BLOCKED` statuses;
- MotorControlIR 1.0.0 loop, startup/calibration, and engineering-dimension closure;
- manifest, descriptor, configuration schema, UI schema, and artifact parity.

## Architecture and safety evidence

- `eea_core` contains only generic `DomainValidationDiagnostic` and `DomainValidationResult` models.
- `eea_ports` defines `DomainValidationContext` and the executable validator protocol.
- `eea_application` invokes the plugin-provided callable without importing MotorControl or FOC types.
- The backend loads `MCUConfigIR` by `project_id` and `mcu_config_id`, verifies current source snapshots,
  and passes the realized Core IR to the plugin validator.
- Missing `MotorControlIR` is `BLOCKED`; missing `MCUConfigIR` is `UNKNOWN`; neither is converted to
  `PASS`.
- No new database table, migration, runtime commissioning path, actuator-enable path, or hardware
  execution path was added.

## MotorControlIR 1.0.0 closure

- CurrentLoop now carries `frequency`, `period`, `Id/Iq target`, PI parameters, output limit,
  anti-windup, decoupling, sample-to-actuation latency, and CPU budget.
- VelocityLoop now carries speed, angular-acceleration, and current limits plus feedback source.
- PositionLoop now carries controller, wrap handling, position limit, and velocity limit.
- Startup steps carry current/voltage/timeout limits and explicit `test_result`.
- Rated voltage/current/speed, PWM frequency, deadtime, sampling window/latency, loop values,
  zero offset, startup limits, and named MotorControl limits enforce their required dimensions.
- Angular acceleration is a generic Core engineering dimension with canonical `rad/s²` units.
- Realized timer/PWM/ADC/DMA/IRQ facts remain owned by Core `MCUConfigIR`; MotorControlIR retains
  requirements and references only.

## Rule evaluation policy

All 11 frozen rules have deterministic evaluators for the M15 input surface:

| Rule | M15R result policy |
|---|---|
| `COMPLEMENTARY_PWM` | PASS/FAIL from realized complementary channel |
| `DEADTIME_REQUIRED` | PASS/FAIL/BLOCKED from required and realized deadtime |
| `CURRENT_SENSE_ADC_RANGE` | PASS/FAIL/BLOCKED from current channels and ADC expected range |
| `ADC_TRIGGER_ALIGNMENT` | PASS/FAIL/BLOCKED from ADC/PWM trigger references |
| `CURRENT_LOOP_TIMING_BUDGET` | FAIL for arithmetic violations; UNKNOWN without runtime budget evidence |
| `SIGN_CONVENTION_COMPLETE` | PASS/FAIL/BLOCKED from explicit sign fields |
| `SPEED_FEEDBACK_SIGN_CONSISTENT` | PASS/FAIL from explicit encoder/mechanical sign semantics |
| `ELECTRICAL_ANGLE_DIRECTION_CONSISTENT` | UNKNOWN until canonical phase-map evidence exists |
| `PI_OUTPUT_SATURATION_LIMIT` | PASS/FAIL/BLOCKED from loop limits |
| `STARTUP_ALIGNMENT_REQUIRED` | PASS/FAIL/BLOCKED/UNKNOWN from contract and test result |
| `MOTOR_REQUIREMENT_MCUCONFIG_MISMATCH` | PASS/FAIL/BLOCKED from requirement/reference comparison |

Runtime execution, canonical phase-map evidence, and hardware calibration remain fail-closed
`UNKNOWN`/`BLOCKED`; no future milestone capability is represented as PASS.

## Focused verification

```text
uv run --extra dev pytest --no-cov -q tests/test_m14_domain_extensions.py tests/test_m15_motor_control.py
```

Result: **37 passed**, one pre-existing Starlette/httpx deprecation warning.

Coverage is intentionally disabled for focused runs; the full repository gate is the acceptance gate.

## Repository gate

The complete repository gate is required before this report may declare `M15R = ACCEPTED` or
`READY_FOR_M16 = YES`:

```text
pytest
ruff check
ruff format --check
mypy
database upgrade
alembic check
OpenAPI export --check
OpenAPI TypeScript --check
pnpm lint
pnpm typecheck
pnpm build
```

Final gate result:

```text
pytest                                  PASS (195 passed, 3 skipped)
coverage                                PASS (84.32%)
ruff check                              PASS
ruff format --check                     PASS (224 files)
mypy                                    PASS (106 source files)
database upgrade                        PASS
clean database + alembic check          PASS (no new upgrade operations)
OpenAPI export --check                  PASS
OpenAPI TypeScript --check              PASS
pnpm lint                               PASS
pnpm typecheck                          PASS
pnpm build                              PASS
```

The pre-existing workspace `.eea/eea.db` reports historical constraint/type drift under a direct
`alembic check`; a clean database reports no operations. M15R does not add an unrelated migration or
rewrite that historical local artifact.

On this Windows host, the `uv run --extra dev pytest` wrapper passes the venv redirector path into
two existing M5 child-process tests, which is incompatible with the Windows Job Object boundary.
The same full suite was rerun with the actual base Python executable for child processes and passed
195 tests; no M5 source or safety policy was changed.

## Acceptance state

M15 Plugin Contract Acceptance: **ACCEPTED**
M15R executable validation closure: **IMPLEMENTED**
M19 FOC Minimal E2E: **NOT STARTED / RESERVED FOR M19**
M21 Desktop UI Vertical Slice: **NOT STARTED / RESERVED FOR M21**
READY_FOR_M16: **YES**
