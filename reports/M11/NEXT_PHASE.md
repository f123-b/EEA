# Next Phase — M12 FirmwareIR and Real Build

## Objective

Translate the validated M11 MCUConfigIR into a Core-neutral FirmwareIR and a reproducible,
buildable firmware artifact while retaining all source revisions and rule evidence.

## Planned scope

- Define startup, clock-tree realization, interrupt handlers, peripheral drivers, memory layout,
  linker, and board-support configuration models.
- Generate deterministic source/configuration files from a validated MCUConfigIR snapshot.
- Add toolchain discovery, compile/link checks, artifact hashes, and a project-scoped build API.
- Keep missing toolchains or device facts explicit as `UNKNOWN` or blocked states.

## Constraints

- M12 must consume the locked M11 snapshot and must not silently rewrite pin, timer, ADC, DMA, or
  IRQ decisions.
- Generated firmware remains traceable to M7 assignments, M8 HardwareIR, M9 CircuitIR, M10
  SchematicIR, and M11 rule results.
