# M22R Test Report

## Scope

M22R closes the parser-backed Existing Project Import boundary without executing imported build,
test, install, or code-generation scripts. The implementation is based on local HEAD
`988ef4d530ed1e1e8b5786e1bd7095fab87b6f6e` and adds migration `0036_m22r_import_candidates`.

## Verified contracts

- STM32CubeMX `.ioc`: MCU/package/core, clocks, pins, peripherals, DMA, malformed-line UNKNOWN.
- KiCad S-expression: symbols, `lib_id`, properties, nets, labels, footprints/pads, parse UNKNOWN.
- DBC: standard/extended CAN IDs, DLC, Intel/Motorola byte order, signedness, scaling/range,
  duplicate/malformed UNKNOWN.
- Candidate rows retain parser/version, source file/location, evidence IDs, confidence, semantic
  key, scan revision, and candidate status.
- Review uses expected-revision CAS. Apply requires accepted/edited candidate status, current
  SourceRevision, explicit preview semantics, and never silently overwrites a differing canonical
  entity; conflicts create `ImportConflictRecord` and an import issue.
- Rescan keeps the previous SourceRevision immutable and returns `added`, `modified`, `removed`,
  `unchanged`, plus Changed/Affected/Stale/Blocked dependency-impact buckets.
- Native folder/archive selection is user-mediated through Tauri dialog commands; no renderer
  filesystem, shell, process, or HTTP permission was added.

## Local gates

| Check | Result |
|---|---|
| M22/M22R/M23 focused tests | **15 passed**, 1 warning |
| Full pytest | **523 passed, 31 skipped, 13 warnings** |
| Coverage | **82.30%**, above the configured 80% gate |
| Mypy | **161 source files passed** |
| Ruff / format | **Passed** repository check and format check |
| Alembic clean upgrade/check | **Passed** on a temporary clean database |
| OpenAPI export/check | **Passed** |
| Desktop typecheck/lint/unit tests | **Passed**, 8 unit tests |
| Desktop production build | **Passed** |
| Targeted Playwright M22R flow | **1 passed** |
| Tauri cargo check/test | **Passed**, 3 Rust tests |
| Tauri MSI bundle | **Passed** with CI-only numeric version/icon override; default all-target build still has the pre-existing dev-version/NSIS packaging limitation |
| Remote CI on final local HEAD | Not run; final commits are not pushed |
