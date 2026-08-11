# Next Phase — M7 Pin Planner + Core Rule Engine (not started)

## Objective

Consume M6 requirements, M3 canonical units, and M4 device facts to produce deterministic pin
requirements, candidate assignments, locks, and pre-generation rule results. M7 remains gated on
green remote CI for the M6 review-fix commit.

## Planned scope

- Generic `PinRequirement`, candidate, assignment, and lock contracts in Core.
- Device/package/peripheral capability queries through the existing M4 provider boundary.
- Deterministic constraint checks for pin conflicts, alternate functions, voltage domains, PWM,
  ADC, and debug-pin conflicts.
- Explicit `UNKNOWN` results for missing or unverifiable inputs; no guessed `PASS`.
- Rule result evidence and requirement/claim traceability.

## M7 acceptance focus

- M6 requirement claims are consumed without duplicating device facts or canonical units.
- M7 consumes `RequirementAnalysis.requirement_ids` / `claim_ids` and the canonical repositories.
- M7 MUST NOT treat embedded `RequirementAnalysis.requirements` / `claims` snapshots as the
  authoritative source of truth.
- Invalid AF, package, voltage, PWM, and ADC conditions are rejected deterministically.
- Missing device facts produce `UNKNOWN`, not an inferred assignment.
- Core remains usable without loading any concrete domain plugin.

## Constraints and sequencing

- M5 remains the hard prerequisite for any future repository/archive/build execution.
- M8 SystemArchitecture/HardwareIR must consume M7 assignments rather than inventing a second pin
  source of truth.
- FIX-03 remains due before M12, and FIX-09 remains due before raw hardware adapters.
