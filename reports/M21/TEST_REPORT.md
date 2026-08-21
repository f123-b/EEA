# M21 Desktop UI Vertical Slice — Final Gate Report

## Scope and identity

- Repository: `f123-b/EEA`
- Branch: `codex/m21-desktop-ui-vertical-slice`
- Base SHA: `67c7e3ea42d00f67cc473b2041929555764a3daf` (green post-M20 main)
- Final implementation HEAD: `ea0a0a8d0d33581ea30f01e83739ec3857c8443a`
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
- AppImage SHA-256: `cb11ecf681c4bff0be08b85db23167fcb5999ab3336906ee2b6100d92cb676a0`
- Bundled sidecar: `usr/lib/Embedded Engineering Agent/resources/eea-api/eea-api`
- Bundled sidecar SHA-256: `9e4bccf9734861e61ea916af1ab6aa36e2bdd2784c3cfdaf7727f623754d6251`
- Packaged executable launch: `PASS`
- Sidecar source: `BUNDLED_RESOURCE`; development-path executable: `null`
- Sidecar auto-start: `PASS`; backend loopback endpoint: `http://127.0.0.1:36967`
- Authenticated request: `PASS`; unauthenticated request rejected: `PASS`
- Renderer ready: `PASS`; workbench ready: `PASS`; runtime session source: `TAURI_IPC`
- URL/storage/DOM clean: `PASS`; token leak scan: `PASS`
- Clean desktop termination: `PASS`; backend closed after exit: `PASS`

The Tauri runtime starts the bundled backend in a dedicated Unix process group and cleans the
group before smoke exit, covering the PyInstaller supervisor/worker lifecycle.

## P1-3 — Desktop release artifact upload and Chinese default

The final `desktop-release-artifact` job assembled and uploaded one unified Actions artifact named
`desktop-release-artifact`. The artifact-producing push CI rerun is
[`32496409227`](https://github.com/f123-b/EEA/actions/runs/32496409227); the matching Draft PR
verification is [`32496414796`](https://github.com/f123-b/EEA/actions/runs/32496414796). The
download contains only the normalized release directory:

- `release/EEA-Desktop-v1.3.1-linux-x64.AppImage`: 125,684,216 bytes;
  SHA-256 `6c2f6752a17ee867293c6960fc725781ac6c0a731767e82d209461c2f4d5aa40`
- `release/EEA-Desktop-v1.3.1-windows-x64.exe`: 27,147,136 bytes;
  SHA-256 `e9a620be56d5585c9c65011c90f9a8e548648684d5fb171cd06a4d94e5f534e9`
- `release/SHA256SUMS.txt`
- `release/release-manifest.json`
- `release/release-size-report.json`

The manifest records product `Embedded Engineering Agent`, version `1.3.1`, source commit
`1b82e332babfea0da84e95a39a3b33c6d01ecd2a`, both platforms, real package hashes/sizes, and
`backend.bundled=true` with source `BUNDLED_RESOURCE`. Artifact validation and the release secret
scan both passed. The size report records 306,651 frontend bytes, 47,481,256 backend bytes, and
152,831,352 total package bytes; it also emits the intentional manual-review warning that no
previous-release baseline was supplied.

The Desktop default locale is `zh-CN`. Settings switches between Chinese and English and persists
the choice in `localStorage` under `eea.locale`; the UI E2E verifies the default, switch, and
persistence path.

## Regression and final CI

- Backend: `512 passed, 27 skipped`, coverage `83.04%`
- Ruff check/format: `PASS`; mypy: `PASS`
- Alembic upgrade/check: `PASS`
- OpenAPI export and TypeScript contract checks: `PASS`
- Desktop lint/typecheck/build: `PASS`
- Desktop unit tests: `8 passed`
- Desktop Playwright: release workflow `1 passed`; UI workflow `2 passed`
- Rust `cargo check`: `PASS`
- Rust `cargo test`: `PASS` (`3 passed`)
- Tauri build: `PASS`
- M19 release: `PASS`
- M20 release: `PASS`

## CI evidence

Final artifact-producing push CI rerun is [`32496409227`](https://github.com/f123-b/EEA/actions/runs/32496409227).
Final artifact-producing Draft PR CI is [`32496414796`](https://github.com/f123-b/EEA/actions/runs/32496414796).
Both runs passed `backend`, `desktop-web`, `desktop-tauri`, `desktop-ui-test`,
`desktop-package-smoke`, `m19-release`, `m20-release`, `m21-ui-release`, and
`desktop-release-artifact`.

M19 and M20 release coverage remains retained in the workflow. M20 was formally merged in PR
#14 at merge SHA `67c7e3ea42d00f67cc473b2041929555764a3daf`; post-merge main CI run
[`32098839155`](https://github.com/f123-b/EEA/actions/runs/32098839155) was green.

## Final disposition

P1-1 and P1-2 are closed with real CI evidence. PR #15 remains a Draft and Open for human final
review. No merge was performed and no M22 work was started.
