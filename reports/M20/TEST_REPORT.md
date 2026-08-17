# M20 Core Neutrality Smoke Gate — Implementation Report

## Scope and identity

- Repository: `f123-b/EEA`
- Branch: `codex/m20-core-neutrality-smoke`
- Base SHA: `7573e1f3525c54cd5fb1155f634b77034d74b255` (green post-merge main)
- Benchmark: `STM32G431 + UART + CAN + SPI Sensor + FreeRTOS`
- MotorControl activation: `NONE`; no MotorControlIR is used
- M20 state: `IMPLEMENTED_PENDING_RELEASE_CI`

M20 extends the existing generic Project → Requirement → Evidence/Claim → Pin Planner →
HardwareIR → CircuitIR → Schematic/ERC → MCUConfigIR → FirmwareIR → SourceRevision → Build →
Static Analysis → ProtocolIR → TestIR/TestRun → Traceability → Review → Impact path. It does
not add a second hardware model or a domain-specific shortcut.

## Implemented gates

- Registered a generic `embedded-controller-benchmark` requirement profile, seeded beside the
  existing profile without importing the optional domain plugin.
- Added verified STM32G431 UFQFPN48 fixture facts for USART2 PA2/PA3, FDCAN1 PA11/PA12, SPI1
  PA5/PA6/PA7, and GPIO CS PB0; conflict and unsupported-function paths remain fail-closed.
- Added the official STM32CubeG4 FreeRTOS kernel component to the existing provider/lock/
  materialization path.
- Extended generic FirmwareIR generation to represent FreeRTOS tasks, queues, mutexes, and
  generated DEVICE sources/configuration; UART/SPI peripheral initialization remains sourced
  from MCUConfigIR.
- Extended the core-neutral ProtocolIR validation to accept UART alongside CAN and excludes UART
  messages from DBC arbitration semantics rather than fabricating CAN transport semantics.
- Added an explicit AST/static boundary scan and 0-active-domain smoke tests. The built-in plugin
  remains available for opt-in projects but is not active in M20.
- Added the `m20-release` GitHub Actions gate, retaining `m19-release` as a regression gate.

## Local verification

- M20 generic focused path: **18 passed** (7 release-only tests deselected).
- M19 non-release regression path: **4 passed**.
- M12A ESCR, M4 device facts, architecture, and M16 protocol tests: **66 passed**.
- Ruff check/format and mypy: **PASS**.
- Local ARM GCC and KiCad CLI are unavailable; M20 real DEVICE build/ERC remain CI gates and are
  not represented as local PASS.

## Required release evidence

The `m20-release` job runs the existing real-tool flow with pinned STM32CubeG4, ARM GCC, CMake,
Cppcheck, and KiCad. It must produce a real ARM ELF, BuildInputSnapshot, SourceRevision binding,
Cppcheck/Firmware Rules with no UNKNOWN/FAIL, executed ERC PASS, deterministic TestRun PASS, and
Review PASS with build/static/ERC/test required. M20 must remain `IMPLEMENTED`, never `ACCEPTED`,
until final human review.
