# M15 MotorControl Built-in Domain Plugin Test Report

Date: 2026-08-11
Repository: `f123-b/EEA`
Implementation commit: `e247a12`
Python: `3.12.13`
Node: `v24.14.0`
pnpm: `11.16.0`
Migration head: `0021_m14_domain_configuration_error_catalog`
Database migration added: **NO**

## Scope

M15 implements the first frozen built-in Domain Plugin under
`plugins/builtin/motor_control/`. The plugin uses the M14 DomainPlugin contract and contributes
MotorControlIR requirements/references, configuration schema, deterministic additive rules,
generator declarations, context metadata, UI metadata, agent metadata, artifacts, and default
bundled-registry integration.

The implementation preserves the Architecture Freeze invariants:

- Core remains domain-neutral and contains no MotorControl/FOC schema or import.
- MotorControlIR stores requirements and references; realized Timer/PWM/ADC/DMA/IRQ data remains
  in Core-owned MCUConfigIR.
- Inverter, encoder, and current-sense facts are references to HardwareIR-owned facts rather than
  duplicated plugin facts.
- Plugin rules are additive and cannot lower Core safety rules.
- Plugin disable/activation remains project-scoped through the existing M14 persistence contract.
- No commissioning runtime, E-stop runtime, flash orchestration, EdgeAI, EngineeringScope,
  Component DB, Outbox, or new database table was added.

## Implementation evidence

- `plugins/builtin/motor_control/manifest.yaml` matches the frozen bundled manifest identity
  `org.eea.motor_control`, API version `1`, bundled trust tier, capabilities, permissions, and
  entrypoint.
- `MotorControlIR` covers motor/inverter/encoder/current-sense references, PWM and ADC sampling
  requirements, MCUConfig references, electrical angle, sign convention, startup/calibration,
  current/velocity/position loops, limits, and fault policy.
- The rule catalog contains all 11 frozen MotorControl rule IDs with stable versions, phases,
  inputs, severities, and `ADDITIVE` safety mode.
- Declarative generators are deterministic and side-effect free. The validation generator is
  ordered after the IR contract generator by the M14 composition DAG.
- Default application composition discovers the bundled plugin, while a caller-provided empty
  registry remains respected for Core-neutral projects and tests.
- Plugin-owned cross-validation detects PWM reference/frequency, complementary channel, deadtime,
  and ADC trigger mismatches against MCUConfigIR. Missing MCUConfigIR is reported as `UNKNOWN`,
  never as `PASS`.

## Focused verification

```text
python -m pytest tests/test_m15_motor_control.py -q --no-cov
```

Result: **5 passed**.

Compatibility verification:

```text
python -m pytest tests/test_m15_motor_control.py tests/test_m14_domain_extensions.py -q --no-cov
```

Result: **22 passed**.

## Full regression and repository gates

```text
python -m pytest
```

Result: **180 passed, 3 skipped**, coverage **84.31%**; the 80% repository gate passed. The only
warning is the pre-existing Starlette/httpx deprecation warning.

```text
ruff check .                         PASS
ruff format --check .                PASS (221 files)
python -m mypy                       PASS (106 source files)
eea openapi export --check           PASS
eea openapi typescript --check       PASS
pnpm lint                            PASS
pnpm typecheck                       PASS
pnpm build                           PASS
clean db upgrade + alembic check     PASS
```

No OpenAPI shape or TypeScript type changed; the committed OpenAPI `info.version` was synchronized
to `1.3.1.dev15` after the milestone version update.

## Acceptance state

M15 plugin-scope acceptance: **ACCEPTED**
M14 compatibility: **PASS**
Core neutrality: **PASS**
Migration/API schema change: **NONE**
M19 real FOC E2E: **NOT STARTED / RESERVED FOR M19**
M19 hardware commissioning and production loop enable: **NOT STARTED / RESERVED**
READY_FOR_M16: **YES**
