# M11 Known Issues

No critical local implementation issue is open.

| Severity | Item | Impact / next action |
|---|---|---|
| Medium | MCU capability facts currently arrive through the structured `capability_snapshot` input rather than a provider-backed device database | Missing facts remain `UNKNOWN`; connect the device-fact provider before treating a configuration as device-verified. |
| Medium | Timer frequency validation compares the requested frequency with a declared maximum and does not yet derive register prescalers, clock trees, or dead-time encodings | Add register-level realization and derived-clock checks in the firmware/generator milestone. |
| Low | M11 persists a Core-neutral configuration but does not generate startup code, linker scripts, or a buildable firmware artifact | Continue with M12 FirmwareIR and real build integration. |
| Low | KiCad CLI remains unavailable in the local environment | M10 ERC stays `UNKNOWN` until a versioned KiCad runner is configured. |
