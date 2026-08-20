# M21 Desktop UI Vertical Slice — Final Gate Report

## Scope and identity

- Repository: `f123-b/EEA`
- Branch: `codex/m21-desktop-ui-vertical-slice`
- Base SHA: `67c7e3ea42d00f67cc473b2041929555764a3daf` (green post-M20 main)
- Final implementation HEAD: `a47d2d3efee866f14791a28e26d92640b86671e5`
- M21 state: `IMPLEMENTED_AND_FINAL_GATE_CLOSED`
- `P0=0`
- `P1=0`
- `READY_FOR_M21_FINAL_REVIEW=YES`
- `APPROVED_TO_MERGE=NO` (PR #15 remains Draft/Open and is not merged)
- `M22=NOT_STARTED`

M21 adds a Desktop/Tauri engineering workbench over the existing authenticated backend API.
The renderer is a state view and action surface; it does not recreate requirement, pin,
HardwareIR, MCUConfigIR, FirmwareIR, Build, ERC, ProtocolIR, TestRun, traceability, or Review
business rules.

## Implemented surfaces

- Core navigation: Dashboard, Projects, Requirements, Documents, Pin Planner, Hardware / Circuit,
  Schematic / ERC, MCUConfigIR, Firmware / Source / Build / Static, Protocol, Tests, Review,
  Domains, Settings, and controlled AI Panel.
- M20 generic benchmark path: project creation, evidence registration, requirement analysis,
  pin generation/lock, HardwareIR, CircuitIR, schematic/ERC, MCUConfigIR, FirmwareIR,
  SourceRevision, DEVICE build, static analysis, ProtocolIR outputs, software TestRun,
  traceability, and deterministic Review.
- Domain UI is metadata-driven through `/ui/extensions`. Active domains contribute generic
  navigation and extension pages from backend descriptors. MotorControl is absent from Core
  navigation until activated and disappears after deactivation.
- Tauri release packaging builds a platform-native PyInstaller `eea-api` sidecar, bundles it as a
  resource, starts it on an authenticated loopback port, and performs a version handshake before
  the renderer is shown. Production packaging does not require Python or a backend executable on
  the developer PATH; the final package gate also verifies clean sidecar termination.

## P1-1 — real DEVICE UI workflow

The release job executed the real M20 benchmark through the renderer using the `DEVICE` profile.
The workflow passed through Build, Static, executed KiCad ERC, software TestRun, traceability,
and Review. The final evidence records:

- Dependency lock ID: `eb656541-ec40-4b57-adfe-d63b92c5b69e`
- Dependency lock hash: `02bcc1de935fb1ad990bfdff4f790fcf38c9bb5adc8e8942c817df701836f158`
- SourceRevision: `236a0aad-814c-48e2-81a1-945cbc2d1924`
- BuildInputSnapshot: `4e91b2f4-24da-456a-bec6-70142fa2ba4c`
- Profile: `DEVICE`
- Toolchain: `arm-none-eabi-gcc 13.2.1`
- Target triple: `arm-none-eabi`
- Artifact: `eea_device.elf`, 57,988 bytes
- ELF SHA-256: `fc9e3a9203dba5d7716fa1d32f9e7aa2101af7304ce53793527e1525b66c156b`
- ELF machine: `EM_ARM (0x28)`
- Cppcheck: `PASS`
- Firmware rules: `ISR_BLOCKING_API=PASS`, `DRIVER_DEPENDENCY_CYCLE=PASS`,
  `MCUCONFIG_FIRMWARE_MISMATCH=PASS`, `APP_DIRECT_HAL_CALL=NOT_APPLICABLE`
- Build: `PASS`; Static: `PASS`; ERC: `PASS` and executed
- TestRun: `PASS`, `9/9 PASS`
- Traceability: `PASS`; Review: `PASS`
- Total M21 DEVICE release gate: `PASS`

The real release Playwright workflow passed `1` test. The desktop UI regression job also passed
`6` unit tests and `1` domain activation/deactivation Playwright test.

## P1-2 — real packaged Tauri AppImage launch

The final package job built and launched the actual AppImage with an isolated PATH. The package
smoke evidence confirms:

- Tauri package: `Embedded Engineering Agent_1.3.1-dev.6_amd64.AppImage`
- AppImage SHA-256: `74b0d8b79a6d2dc483ac215ab011da4f390919073840b4c50448e2f247b89166`
- Bundled sidecar: `usr/lib/Embedded Engineering Agent/resources/eea-api/eea-api`
- Bundled sidecar SHA-256: `8bf7c1b118afa94c8ae054527f4abbff3cb76de39659ee8c1a8062b757e951f6`
- Packaged executable launch: `PASS`
- Sidecar source: `BUNDLED_RESOURCE`; development-path executable: `null`
- Sidecar auto-start: `PASS`; backend loopback endpoint: `http://127.0.0.1:38567`
- Authenticated request: `PASS`; unauthenticated request rejected: `PASS`
- Renderer ready: `PASS`; workbench ready: `PASS`; runtime session source: `TAURI_IPC`
- URL/storage/DOM clean: `PASS`; token leak scan: `PASS`
- Clean desktop termination: `PASS`; backend closed after exit: `PASS`

The Tauri runtime starts the bundled backend in a dedicated Unix process group and cleans the
group before smoke exit, covering the PyInstaller supervisor/worker lifecycle.

## Regression and final CI

- Backend: `510 passed, 27 skipped`, coverage `83.04%`
- Ruff check/format: `PASS`; mypy: `PASS`
- Alembic upgrade/check: `PASS`
- OpenAPI export and TypeScript contract checks: `PASS`
- Desktop lint/typecheck/build: `PASS`
- Desktop unit tests: `6 passed`
- Desktop Playwright: release workflow `1 passed`; domain UI workflow `1 passed`
- Rust `cargo check`: `PASS`
- Rust `cargo test`: `PASS` (`3 passed`)
- Tauri build: `PASS`
- M19 release: `PASS`
- M20 release: `PASS`

## CI evidence

Final push CI is run [`32329951312`](https://github.com/f123-b/EEA/actions/runs/32329951312).
Final Draft PR CI is run [`32329955310`](https://github.com/f123-b/EEA/actions/runs/32329955310).
Both runs passed `backend`, `desktop-web`, `desktop-tauri`, `desktop-ui-test`,
`desktop-package-smoke`, `m19-release`, `m20-release`, and `m21-ui-release`.

M19 and M20 release coverage remains retained in the workflow. M20 was formally merged in PR
#14 at merge SHA `67c7e3ea42d00f67cc473b2041929555764a3daf`; post-merge main CI run
[`32098839155`](https://github.com/f123-b/EEA/actions/runs/32098839155) was green.

## Final disposition

P1-1 and P1-2 are closed with real CI evidence. PR #15 remains a Draft and Open for human final
review. No merge was performed and no M22 work was started.
