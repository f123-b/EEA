# Next Phase — M8 SystemArchitecture / HardwareIR

## Objective

Build the first architecture IR over one authoritative, persisted M7 pin-plan result.

## Planned scope

- Define Core-neutral `SystemArchitectureIR` and `HardwareIR` contracts without concrete domain
  plugin types.
- Load the selected persisted M7 plan and reject missing, stale, unlocked, `UNKNOWN`, or `FAIL`
  prerequisites according to the M8 gate contract.
- Preserve M7 assignment, claim, evidence, lock, and rule-result traceability in architecture IR.
- Add project-scoped persistence, API, OpenAPI, and desktop contract coverage for the architecture
  boundary.

## Constraints

- M8 must not reconstruct or invent a second pin-assignment source of truth.
- Canonical M6 requirement and claim repositories remain authoritative.
- M5 remains the prerequisite for any repository/archive/build execution.
