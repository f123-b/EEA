# M19 FOC Minimal E2E — Test Report

## Implementation identity

- Repository: `f123-b/EEA`
- Branch: `codex/m19-foc-minimal-e2e`
- Base green main: `b572fc6b820925ea623a46c6104982efc33a705c`
- Implementation commit: `82e0943` — `feat(m19): add foc minimal e2e vertical slice`
- Status/docs commit before CI evidence update: `a3da006` — `docs(m19): record foc e2e release status`
- Draft PR: `#13`, base `main`, currently OPEN/DRAFT/UNMERGED
- M19 scope: M19A software E2E; M19B hardware commissioning remains hardware-gated

## Release-gate posture

M19 is **IMPLEMENTED** and **READY_FOR_M19_FINAL_REVIEW**. The implementation proves the
software vertical slice through the normal API/Application/repository path without direct SQL
state fabrication. It does not claim a real motor run, actuator enable, or hardware commissioning
success.

The local machine has CMake and Cppcheck, but the Windows runtime cannot prove the required
network-isolated command boundary; therefore the real Build endpoint records `UNKNOWN` with a
diagnostic instead of manufacturing a PASS. `arm-none-eabi-gcc`, KiCad CLI, Cargo, and hardware
probe access are unavailable locally. These are recorded as environment/hardware gates, not
converted to success.

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

- M19 focused suite: **4 passed** (`tests/test_m19_foc_minimal_e2e.py`)
- Cross-milestone M18/M19 suite: **197 passed, 1 skipped**.
- Local full pytest: **485 passed, 4 skipped, 2 failed**; coverage **84.25%**. The two failures
  are the pre-existing Windows M5 sandbox tests listed in `KNOWN_ISSUES.md`.
- Valid vertical slice: PASS through all normal API stages; Build is fail-closed UNKNOWN under
  the local sandbox capability boundary; TestRun is BLOCKED because the built-in executor is
  contract-only and is not authorized to claim behavioral motor verification.
- Failure paths: missing critical requirement, pin conflict, invalid AF, and electrical violation
  all fail closed.
- Tool boundary: absent/unavailable Cppcheck or KiCad cannot become PASS.
- Impact propagation: Claim lifecycle mutation reaches PinAssignment, MCUConfigIR, FirmwareIR,
  BuildRun, and StaticAnalysis; unrelated PinAssignment entities are not included.
- Ruff check on changed implementation/test files: PASS.
- Ruff format check on changed implementation/test files: PASS.
- Full Ruff check: PASS; full Ruff format check: PASS.
- Full mypy: PASS (`146` source files).
- Clean Alembic upgrade through `0033_m18er1_atomic_restore_runtime`: PASS; Alembic check:
  PASS using the clean database URL.
- OpenAPI export/check: PASS; TypeScript contract export/check: PASS.
- Desktop-web lint: PASS; typecheck: PASS; production build: PASS.
- Cargo/Tauri local gates: NOT RUN because `cargo` is not installed on this workstation. The
  authoritative M18E main CI already executed cargo check, cargo test, and tauri build; M19 PR
  CI is required to execute the same gates in GitHub.
- GitHub push CI `31957259756`: backend PASS, desktop-web PASS, desktop-tauri PASS.
- GitHub Draft PR CI `31957274885`: backend PASS, desktop-web PASS, desktop-tauri PASS. The
  desktop-tauri job executed `cargo check`, `cargo test`, and `tauri build --ci`; backend executed
  pytest, the generated M16 C codec, OpenAPI export/check, and TypeScript contract check.

## Gate-by-gate result

| Gate | Result | Evidence |
|---|---|---|
| Requirement completeness/evidence | PASS | FOC profile and one P0 traceable requirement are created through the API |
| Claim/Device | PASS | Device claim is persisted through the normal requirements path |
| PinMap | PASS | Five verified assignments lock successfully; no fabricated pin is accepted |
| Hardware/Circuit | PASS | HardwareIR/CircuitIR and electrical constraints are validated |
| Schematic/ERC | UNKNOWN when KiCad is unavailable | No text artifact is promoted as a real KiCad/ERC PASS |
| MCUConfigIR | PASS | TIM1, ADC1, DMA1, FDCAN1, IRQ and capability snapshot are persisted/validated |
| MotorControl plugin | PASS/UNKNOWN diagnostics only | Domain activation/validation uses the built-in plugin and MCUConfigIR references |
| Firmware/source | PASS | FirmwareIR, generated C source, SourceRevision and manifest are bound |
| Real Build/ELF | UNKNOWN locally | No ARM toolchain or provable network-isolated executor; no fake ELF/hash |
| Static analysis | Executed fail-closed | Cppcheck and firmware-rule results are persisted; missing tool maps to UNKNOWN |
| Protocol | PASS | One ProtocolIR generates C, Python, DBC and Markdown outputs |
| TestIR/Review | BLOCKED as appropriate | Contract-level cases pass, aggregate stays BLOCKED without behavioral authority |
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
M19 = IMPLEMENTED
M19_P0 = 0
M19_P1 = 0
READY_FOR_M19_FINAL_REVIEW = YES
M20 = NOT_STARTED
M21 = NOT_STARTED
```
