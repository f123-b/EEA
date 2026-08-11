# Next Phase — M7 Persistence and M8 System Architecture

## Objective

Complete the durable part of M7 and make M8 consume one authoritative pin-plan result.

## Planned scope

- Persist project-scoped pin assignments, locks, rule results, revisions, and traceability.
- Add explicit lock, unlock, and re-plan APIs with deterministic stale-revision handling.
- Preserve `UNKNOWN` and `FAIL` outcomes through persistence and downstream architecture generation.
- Define the M8 HardwareIR/SystemArchitecture input boundary over M7 assignments only.
- Add migration, repository, API, OpenAPI, and desktop contract coverage for the durable flow.

## Constraints

- M8 must not reconstruct or invent a second pin-assignment source of truth.
- Canonical M6 requirement and claim repositories remain authoritative.
- M5 remains the prerequisite for any repository/archive/build execution.
