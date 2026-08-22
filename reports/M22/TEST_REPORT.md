# M22 Existing Project Import — Vertical Slice Report

## Scope and identity

- Milestone: `M22 Existing Project Import & Reverse Engineering`
- State: `IMPLEMENTED_VERTICAL_SLICE`
- Source boundary: existing M18 Source Authority / SourceRevision
- Import boundary: isolated EEA data directory; imported build/test/install scripts are never executed
- Candidate policy: scan findings and HardwareIR/ProtocolIR outputs remain `CANDIDATE` until explicit review

## Implemented

- Local Folder, Git Repository, and ZIP/TAR Archive materialization.
- Git imports bind the exact resolved commit to the staged tree and resulting SourceRevision.
- Archive traversal, symlink, member-count, per-file-size, total-size, and compression-ratio checks reuse the M5 safe materializer.
- Eight scan stages: file reading, build detection, MCU/SoC detection, generated/configuration/hardware detection, source classification, and dependency index.
- C/C++, CMake, Makefile, PlatformIO, STM32Cube `.ioc`, KiCad, DeviceTree, Zephyr, FreeRTOS, HAL/LL/CMSIS, linker/protocol hints, MCU resources, modules, entry points, and dependency edges are reported with confidence/source/evidence.
- `.ioc` versus source pin differences produce `CONFIG_SOURCE_MISMATCH` instead of silently choosing one side.
- Review API and Desktop wizard support Accept/Edit/Reject/Unknown; Accept remains `ACCEPTED_CANDIDATE`, never `TRUSTED`.
- Create Workspace copies source into a project-scoped workspace and creates the initial SourceRevision.
- Rescan creates a new SourceRevision and keeps the previous revision immutable.
- Import sessions, findings, issues, classifications, candidates, manifests, and scan results are durable through migration `0034_m22_existing_project_import`.

## Verification

- M22 focused tests: **3 passed**.
- Source Authority regression plus M22: **16 passed, 1 skipped**.
- Full pytest suite: **511 passed, 31 skipped**, 13 warnings, **83% coverage** (80% required).
- Mypy: **149 source files passed**.
- Ruff: full repository check passed.
- Alembic clean upgrade through `0034_m22_existing_project_import`: passed.
- Desktop lint, TypeScript typecheck, and production build: passed.
- OpenAPI export/check: regenerated after adding the M22 routes; TypeScript contract remains current.
- `git diff --check`: passed.
- Git smoke: exact commit binding and rescan revision change passed.

## Acceptance status

The vertical slice covers the core M22 import safety and review flow. Final M22 closure still requires the full backend/desktop CI matrix, a deeper parser-backed KiCad/.ioc/resource candidate review, a production-native Tauri folder/archive picker, and explicit diff/impact presentation for rescan changes.
