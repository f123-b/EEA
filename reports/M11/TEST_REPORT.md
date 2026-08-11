# M11 Test Report — MCUConfigIR

## Outcome

M11 is implemented and locally verified. `MCUConfigIR` consumes the current M8 HardwareIR,
M9 CircuitIR, and M10 SchematicIR revisions, persists configuration snapshots and deterministic
rule results, and exposes project-scoped generate/get/validate endpoints.

## Validation evidence

| Check | Result |
|---|---|
| `ruff check .` | PASS |
| `mypy core/src application/src apps/backend/src` | PASS; 48 source files |
| M7–M11, migration, and OpenAPI acceptance tests | PASS; 23 passed |
| Full pytest suite | PASS; 128 passed, 1 skipped |
| Full coverage | PASS; 88.70% |
| OpenAPI export and committed-schema comparison | PASS |
| Alembic upgrade/check and M11 downgrade/upgrade path | PASS |

## Delivered surface

- Core-neutral clock, GPIO, peripheral, PWM, ADC, DMA, interrupt, memory, and debug models.
- Deterministic PinMap, clock-source, timer-channel/frequency, complementary-PWM, ADC-channel/
  trigger, DMA-request, and IRQ conflict rules with auditable `RuleResult` snapshots.
- SQLAlchemy `mcu_configs` and `mcu_config_rule_results` persistence with source IDs/revisions.
- `POST /projects/{project_id}/mcu-config/generate`, `GET /projects/{project_id}/mcu-config`,
  and `POST /projects/{project_id}/mcu-config/validate`.
- OpenAPI and generated desktop contract refreshed.
