# M19 FOC Minimal E2E — Final Gate Report

## Implementation identity

- Repository: `f123-b/EEA`
- Branch: `codex/m19-foc-minimal-e2e`
- Final implementation HEAD before acceptance docs: `f8d3352100ef54a37d771e4625f3a2c30cc9a5cd`
- Final PR HEAD: `e9b947e1d21202ea568c65af49a866f4961c6cc1`
- Base/main after merge: `7573e1f3525c54cd5fb1155f634b77034d74b255`
- PR: [#13](https://github.com/f123-b/EEA/pull/13), MERGED by merge commit
  `7573e1f3525c54cd5fb1155f634b77034d74b255` at `2026-08-17T14:25:12Z`
- Acceptance PR CI: `32038057014`; acceptance push CI: `32038052903`; post-merge main CI:
  `32038973317`
- M19A: ACCEPTED_AND_MERGED; M19B: BLOCKED_HARDWARE

## Release-gate posture

M19A is **IMPLEMENTED** and **FINAL_GATE_CLOSED**. The dedicated `m19-release` job ran the
normal API/Application/repository vertical slice in GitHub Actions with real release tools. It
does not claim a real motor run, actuator enable, or hardware commissioning success.

Its uploaded artifact is `m19-release-evidence` from the green release runs; the post-merge
main gate also completed successfully.

## Implemented vertical slice

The test drives one FOC benchmark project through:

```text
Project → Requirement → Evidence → Claim/Device → PinMap → HardwareIR → CircuitIR
→ Schematic/ERC → MCUConfigIR → MotorControl activation/validation → FirmwareIR
→ SourceRevision → BuildRun → Cppcheck/Firmware rules → ProtocolIR/codecs
→ TestIR/TestRun → Traceability → Review → Dependency impact
```

The benchmark facts are the frozen STM32G431 + DRV8323 + AS5047 + 24 V + 10 A + PMSM + FOC +
CAN/UART profile. Verified fixture pins are consumed from the existing device provider; the test
does not guess pins or create a second planner/configuration system. MotorControl remains in
`plugins/builtin/motor_control`; timer, PWM, ADC, DMA, IRQ, and pin facts remain in MCUConfigIR,
while inverter, encoder, and current-sense facts remain in HardwareIR/CircuitIR.

## Verification performed

- M19 strict release gate: **20 passed, 4 deselected, 1 warning** (PR CI `32021782056`).
- DEVICE Build: **PASS** with real `eea_device.elf` (30,780 bytes), SHA-256
  `c9c706a236bf624bd2fc9a9bbe6d37fac857f71d6173d94afc85993da438b6db`, ARM GCC `13.2.1`,
  CMake `3.31.6`, and a persisted BuildInputSnapshot.
- Cppcheck: **PASS**, executed version `2.13.0`, zero diagnostics.
- Four M13 release rules: **PASS** overall; three PASS and `APP_DIRECT_HAL_CALL` explicitly
  NOT_APPLICABLE; zero UNKNOWN and zero FAIL.
- KiCad ERC: **PASS**, executed `kicad-cli 9.0.9`, return code 0, zero violations.
- Software TestRun: **PASS**; all 9 deterministic server-owned release facts PASS.
- ReviewRun: **PASS**; Build, static analysis, ERC, and TestRun were required; findings `[]`.
- Full backend, desktop-web, and desktop-tauri PR CI: **PASS**.
- Failure paths: missing critical requirement, pin conflict, invalid AF, electrical violation,
  unavailable tools, and stale downstream propagation all remain fail-closed.
- Static-analysis API now binds the analysis to the matching BuildInputSnapshot; release facts
  are computed from persisted engineering results and are not client-supplied.
- Local full pytest retains the two pre-existing Windows M5 sandbox failures listed in
  `KNOWN_ISSUES.md`; local ARM/KiCad/Cargo/hardware limitations remain environment gates.

## Gate-by-gate result

| Gate | Result | Evidence |
|---|---|---|
| Requirement completeness/evidence | PASS | FOC profile and one P0 traceable requirement are created through the API |
| Claim/Device | PASS | Device claim is persisted through the normal requirements path |
| PinMap | PASS | Five verified assignments lock successfully; no fabricated pin is accepted |
| Hardware/Circuit | PASS | HardwareIR/CircuitIR and electrical constraints are validated |
| Schematic/ERC | PASS | Real KiCad 9.0.9 CLI executed; zero violations |
| MCUConfigIR | PASS | TIM1, ADC1, DMA1, FDCAN1, IRQ and capability snapshot are persisted/validated |
| MotorControl plugin | PASS/UNKNOWN diagnostics only | Domain activation/validation uses the built-in plugin and MCUConfigIR references |
| Firmware/source | PASS | FirmwareIR, generated C source, SourceRevision and manifest are bound |
| Real Build/ELF | PASS | Real ARM DEVICE ELF, BuildInputSnapshot, source binding, size and hash persisted |
| Static analysis | PASS | Cppcheck 2.13.0 plus all four M13 release rules; zero UNKNOWN/FAIL |
| Protocol | PASS | One ProtocolIR generates C, Python, DBC and Markdown outputs |
| TestIR/Review | PASS | 9 authorized software release facts PASS; required ReviewRun PASS |
| Traceability | PASS | No uncovered requirement IDs in the generated traceability result |
| Dependency/impact | PASS | Stale propagation reaches the downstream engineering chain only |
| Hardware safety | BLOCKED_HARDWARE | No probe, board, motor, flash, or actuator-enable operation was attempted |

## State

```text
M18D = ACCEPTED_AND_MERGED
M18DR = ACCEPTED_AND_MERGED
M18E = ACCEPTED_AND_MERGED
M18ER = ACCEPTED_AND_MERGED
M18ER.1 = ACCEPTED_AND_MERGED
M19A = ACCEPTED
M19B = BLOCKED_HARDWARE
M19_P0 = 0
M19_P1 = 0
M20 = NOT_STARTED
M21 = NOT_STARTED
PR_13 = MERGED
M19_MERGE_SHA = 7573e1f3525c54cd5fb1155f634b77034d74b255
MAIN_CI = GREEN
M20 = IN_PROGRESS_ON_CODEX_M20_BRANCH
```
