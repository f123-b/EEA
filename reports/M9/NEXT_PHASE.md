# Next Phase — M10 Schematic / KiCad / ERC

## Objective

Generate an editable schematic/netlist from the persisted M9 CircuitIR and validate it with KiCad
ERC when the toolchain is available.

## Planned scope

- Build a schematic/netlist adapter that consumes CircuitIR components, endpoints, nets, and power
  constraints without redefining pin assignments.
- Add deterministic pre-generation completeness checks and KiCad ERC result import with artifact,
  issue, evidence, and source-revision traceability.
- Persist generated schematic artifacts and mark them stale when the source CircuitIR changes.
- Add a project-scoped schematic generate/validate API and desktop contract coverage.

## Constraints

- M10 must consume the selected CircuitIR and its HardwareIR/M7 source revisions only.
- Missing tools or facts must produce explicit degraded/unknown results; they must never be reported
  as ERC-verified.
- M7 remains the only pin assignment source of truth, and M8/M9 snapshots remain immutable.
