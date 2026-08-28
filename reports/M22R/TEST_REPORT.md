# M22R Test Report

## Scope

M22R closes the parser-backed Existing Project Import boundary without executing imported build,
test, install, or code-generation scripts. The final implementation code was verified at
the M22R implementation range and adds landing migration `0038_m23l_m22r_import_candidates`.

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
| M22/M22R focused tests | **19 passed**, 1 warning |
| Final CI pytest | **527 passed, 27 skipped, 13 warnings** |
| Final CI coverage | **82.09%**, above the configured 80% gate |
| Mypy | **161 source files passed** |
| Ruff / format | **Passed** repository check and format check |
| Alembic clean upgrade/check | **Passed** on a temporary clean database |
| OpenAPI export/check | **Passed** |
| Desktop typecheck/lint/unit tests | **Passed**, 8 unit tests |
| Desktop production build | **Passed** |
| Playwright UI release flow | **2 passed** in `desktop-ui-test`; **1 passed** in `m21-ui-release` |
| Tauri cargo check/test/build | **Passed**, 3 Rust tests |
| Desktop package smoke | **Passed**, bundled backend and renderer reached ready |
| Release packaging | **Passed**, Windows NSIS and Linux AppImage |

## Final CI evidence

- Push CI `32952283021` and Draft PR CI `32952288652` both completed successfully at the final
  implementation HEAD above.
- Required jobs passed: `backend`, `desktop-web`, `desktop-tauri`, `desktop-ui-test`,
  `desktop-package-smoke`, `m19-release`, `m20-release`, `m21-ui-release`, both release build
  matrix entries, and `desktop-release-artifact`.
- The push-run release manifest is bound to `0dee9bb` and reports:
  - Linux AppImage: `125946360` bytes,
    `0ca065d4b900932ac45d97f2df3e8e257d2e126cf84664ccd652a0ec47bd078e`
  - Windows NSIS: `27366034` bytes,
    `f7b3d78b6f4829a0e822676bb09a8674728346dda32d7889e9ed8609c493ef10`
- The release-size report has no previous baseline; this is a manual-review warning only.
