# M20 Core Neutrality Smoke Gate — Implementation Report

## Scope and identity

- Repository: `f123-b/EEA`
- Branch: `codex/m20-core-neutrality-smoke`
- Base SHA: `7573e1f3525c54cd5fb1155f634b77034d74b255` (green post-merge main)
- Implementation HEAD covered by release evidence: `59477be150d7a37bdbc1f00102e341c68c407079`
- Benchmark: `STM32G431 + UART + CAN + SPI Sensor + FreeRTOS`
- MotorControl activation: `NONE`; no MotorControlIR is used
- M20 state: `IMPLEMENTED_READY_FOR_FINAL_REVIEW`

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
- Local ARM GCC and KiCad CLI are unavailable; real-tool evidence is supplied by the dedicated
  release job below.

## Release evidence

The dedicated push run [`32045405744`](https://github.com/f123-b/EEA/actions/runs/32045405744)
and the duplicate Draft PR run [`32045408851`](https://github.com/f123-b/EEA/actions/runs/32045408851)
are green across `backend`, `desktop-web`, `desktop-tauri`, `m19-release`, and `m20-release`.

- Real DEVICE build: **PASS**; build run `299b16fb-1795-4d57-91f8-58d86d9d34ac`; build input
  snapshot `4e1d42e2-6413-46ab-a3a5-62c4840aa585`; source revision
  `0929bd4c-d9a6-4f6d-9748-265da4c46707`.
- ARM ELF: 57,988 bytes, SHA-256
  `fc9e3a9203dba5d7716fa1d32f9e7aa2101af7304ce53793527e1525b66c156b`; ELF32 ARM hard-float
  validation passed. Build input hash is
  `157c97bb208a9f8432a2a1512b13fb1ccffe2d400ec399c6bc877585b604e2d0`.
- Toolchain: ARM GCC `13.2.1`, CMake `3.31.6`, Cppcheck `2.13.0`, KiCad `9.0.9`.
- Cppcheck and Firmware Rules: **PASS**, with no `UNKNOWN` or `FAIL`; ERC executed with KiCad
  and **PASS**, with no issues.
- Software TestRun: **PASS**, all 9 required cases passed. Review: **PASS**, required build,
  static, ERC, and TestRun evidence present; findings and issue IDs empty.
- Release summary: `motor_control_active=false`, `P0=0`, `P1=0`.

M20 is implementation-complete and ready for final human review. It remains `IMPLEMENTED`, never
`ACCEPTED` or approved to merge, until that review is explicitly recorded.
