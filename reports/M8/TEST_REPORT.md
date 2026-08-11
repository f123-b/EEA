# M8 Test Report — SystemArchitectureIR + HardwareIR

**Assessment date:** 2026-08-11

**Baseline:** EEA V1.3.1 candidate

**Result:** LOCAL IMPLEMENTATION COMPLETE — local M8 gates pass; remote CI evidence is pending.

## Delivered scope

- Core-neutral `SystemArchitectureIR` and `HardwareIR` contracts with generic blocks, interfaces,
  modules, device instances, power domains, constraints, and traceability fields.
- Architecture generation consumes the persisted M7 PinPlan as the only pin-assignment source of
  truth and records PinPlan and assignment revisions.
- Deterministic prerequisite gate rejects stale plans, missing analysis, unlocked assignments, and
  persisted M7 `UNKNOWN`/`FAIL` rule results.
- Durable `system_architectures` and `hardware_irs` records with atomic bundle persistence.
- Project-scoped architecture generate/get API, OpenAPI snapshot, and migration `0010_m8_architecture_ir`.

## Acceptance evidence

| Check | Result |
|---|---|
| Ruff lint | PASS |
| Ruff format | PASS — 117 files |
| Mypy | PASS — 51 source files |
| M8 gate/API tests | PASS — 2 M8 tests |
| Full Pytest | PASS — 119 passed, 1 skipped |
| Branch-aware Python coverage | PASS — 88.88% total |
| Migration forward/downgrade/re-upgrade | PASS — `0010_m8_architecture_ir` |
| Architecture stale/lock gate | PASS — unlocked and stale plans rejected |
| IR persistence round-trip | PASS — architecture and hardware bundle reloads |
| OpenAPI snapshot | PASS — current backend contract |
| Desktop validation | PASS locally — lint, typecheck, and production build |

## Intentional limits

- M8 does not yet define CircuitIR, component selection, electrical rules, schematic generation, or
  EDA output; those belong to later milestones.
- Device facts remain fixture-backed and no live hardware validation was performed.
- No remote GitHub Actions run was available for this local change set.
