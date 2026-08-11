# Next Phase — M9 CircuitIR + Electrical Rules

## Objective

Build CircuitIR and deterministic electrical validation over the persisted M8 HardwareIR.

## Planned scope

- Define Core-neutral circuit components, nets, power nets, endpoints, protection, filters, and
  constraints.
- Consume M8 HardwareIR modules, device instances, interfaces, and locked pin assignments only.
- Add deterministic voltage, current, rating, ADC range, gate-driver, CAN transceiver, and
  termination rules with explicit `UNKNOWN` outcomes.
- Persist CircuitIR and rule results with M8 traceability and revision references.
- Add project-scoped generate/get/validate API and OpenAPI/desktop contract coverage.

## Constraints

- M9 must not invent a second pin map or silently reinterpret M7 assignments.
- M8 architecture and HardwareIR remain immutable generated snapshots; regeneration creates a new
  revision tied to the selected upstream IR.
- M5 remains the prerequisite for any repository/archive/build execution.
