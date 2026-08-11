# M7 Test Report — Pin Planner + Core Rule Engine

**Assessment date:** 2026-08-11

**Baseline:** EEA V1.3.1 candidate

**Result:** LOCAL IMPLEMENTATION COMPLETE — durable M7 gates pass; remote CI evidence is pending.

## Delivered scope

- Core-neutral `PinRequirement`, candidate, assignment, lock, plan, and `RuleResult` contracts.
- Deterministic planning through the existing M4 device-provider boundary.
- Alternate-function, package, voltage, five-volt tolerance, debug-pin, PWM, ADC, and physical
  pin-conflict checks.
- Explicit `UNKNOWN` results when required device facts are absent or unverifiable.
- M6 traceability through canonical `requirement_ids` and `claim_ids`; embedded analysis snapshots
  are not used as the source of truth.
- A controlled backend generate endpoint and regression coverage for canonical-reference validation.
- Durable `pin_plans`, `pin_assignments`, `pin_locks`, and `pin_rule_results` persistence with
  Alembic `0009_m7_pin_planner`.
- Project-scoped map/validate endpoints, explicit lock/unlock endpoints, ETags, stale-revision
  rejection, and a replan route that creates a new plan rather than mutating history.
- OpenAPI snapshot regeneration and Core schema registration for the new contracts.

## Acceptance evidence

| Check | Result |
|---|---|
| Ruff lint | PASS |
| Ruff format | PASS — 112 files |
| Mypy | PASS — 48 source files |
| Targeted M7 tests | PASS — 10 passed |
| Full Pytest | PASS — 117 passed, 1 skipped |
| Branch-aware Python coverage | PASS — 88.51% total |
| Migration forward/downgrade/re-upgrade | PASS — `0009_m7_pin_planner` |
| Core domain boundary | PASS — no concrete product-domain types in Core |
| OpenAPI snapshot | PASS — committed snapshot matches backend |
| Canonical M6 reference enforcement | PASS — non-canonical requirement and claim refs rejected |
| Desktop validation | PASS locally — lint, typecheck, and production build |

## Intentional limits

- M8 SystemArchitecture/HardwareIR is not part of this change and must consume persisted M7 plans.
- The device provider remains a deterministic fixture-backed boundary. No live vendor database or
  hardware validation was performed.
- No remote GitHub Actions run was available for this local change set.
