# Next Phase — M11 MCUConfigIR

## Objective

Define the Core-neutral MCU configuration IR that consumes the locked pin assignments and persisted
CircuitIR without duplicating hardware mappings.

## Planned scope

- Add `MCUConfigIR` for clock, GPIO, PWM, ADC, DMA, and interrupt configuration with canonical
  engineering values and source revisions.
- Add deterministic timer/channel, ADC trigger, DMA request, IRQ, and PinMap compatibility rules.
- Persist configuration snapshots and rule results with CircuitIR/Schematic traceability.
- Add project-scoped generate/get/validate API and desktop contract coverage.

## Constraints

- M11 is the sole fact source for timer/PWM/ADC/DMA/IRQ configuration.
- It must consume M7 assignments, M8 HardwareIR, M9 CircuitIR, and M10 schematic source revisions;
  it must not reinterpret or reassign pins.
- Missing device facts remain `UNKNOWN` or blocked; no inferred configuration may be reported as
  verified.
