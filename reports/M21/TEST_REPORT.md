# M21 Desktop UI Vertical Slice — Implementation Report

## Scope and identity

- Repository: `f123-b/EEA`
- Branch: `codex/m21-desktop-ui-vertical-slice`
- Base SHA: `67c7e3ea42d00f67cc473b2041929555764a3daf` (green post-M20 main)
- Final implementation HEAD: `331acf883cb5f6d64124574cbb4f699d9a812ea6`
- M21 state: `IMPLEMENTED`
- `READY_FOR_M21_FINAL_REVIEW=YES`
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
  the developer PATH.

## Local verification

- `pnpm install --frozen-lockfile`: PASS.
- Desktop typecheck, ESLint (`--max-warnings 0`), production build: PASS.
- Desktop UI unit tests: **4 passed**.
- Playwright renderer E2E: **2 passed** — M20 generic workflow and dynamic MotorControl
  activation/deactivation.
- Packaged sidecar smoke: PASS — authenticated version request returned 200 and unauthenticated
  request was rejected.
- `py -3.12 -m ruff check .` and `py -3.12 -m ruff format --check .`: PASS.
- Local Windows Rust/Tauri execution was not available because `cargo` is not installed; the
  Linux `cargo check`, `cargo test`, and `tauri build --ci` gates are in CI.

## CI evidence

Push CI run [`32104485567`](https://github.com/f123-b/EEA/actions/runs/32104485567) validates the
backend, existing desktop web gate, Tauri sidecar/package path, new `desktop-ui-test` job, and
new `desktop-package-smoke` job. The final result is recorded after the run completes.

M19 and M20 release coverage remains retained in the workflow. M20 was formally merged in PR
#14 at merge SHA `67c7e3ea42d00f67cc473b2041929555764a3daf`; post-merge main CI run
[`32098839155`](https://github.com/f123-b/EEA/actions/runs/32098839155) was green.
