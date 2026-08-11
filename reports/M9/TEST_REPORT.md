# M9 Test Report — CircuitIR + Electrical Rules

**Assessment date:** 2026-08-11

**Baseline:** EEA V1.3.1 candidate

**Result:** LOCAL IMPLEMENTATION COMPLETE — local M9 gates pass; remote CI evidence is pending.

## Delivered scope

- Core-neutral `CircuitIR`, components, endpoints, nets, power nets, constraints, and rule-result
  contracts.
- Circuit generation consumes one persisted M8 `HardwareIR` snapshot and its M7 assignment IDs and
  revisions; generation rejects pin references outside that snapshot.
- Deterministic `MOSFET_VDS_MARGIN`, `ADC_RANGE`, `GATE_DRIVER_VOLTAGE`, `CAN_TRANSCEIVER`, and
  `TERMINATION` validation with explicit `UNKNOWN` and `NOT_APPLICABLE` outcomes.
- Durable `circuits` and `circuit_rule_results` records with project scope, source HardwareIR
  revision, traceability, and rule input snapshots.
- Project-scoped circuit generate/get/validate API, OpenAPI snapshot, migration `0011_m9_circuit_ir`,
  and M7 → M8 → M9 integration coverage.

## Acceptance evidence

| Check | Result |
|---|---|
| Ruff lint | PASS — 128 files |
| Ruff format | PASS — 128 files |
| Mypy | PASS — 54 source files |
| M9 rule/API/migration tests | PASS |
| Full Pytest | PASS — 122 passed, 1 skipped |
| Branch-aware Python coverage | PASS — 89.15% total |
| Migration forward/downgrade/re-upgrade | PASS — `0011_m9_circuit_ir` |
| Circuit persistence round-trip | PASS — CircuitIR and rule results reload |
| Stale HardwareIR gate | PASS — stale circuit source rejected |
| OpenAPI snapshot | PASS — current backend contract |
| Desktop validation | PASS locally — lint, typecheck, and production build |

## Intentional limits

- M9 stops at persisted CircuitIR and deterministic pre-generation electrical checks; schematic,
  KiCad, ERC, and editable netlist output belong to M10.
- Device/component facts remain fixture-backed and no live vendor-data validation was performed.
- Extensible component/net attributes remain versioned JSON bags until later stable schemas exist.
- No remote GitHub Actions run was available for this local change set.
