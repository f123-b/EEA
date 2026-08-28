# M23L Final Acceptance

## Decision

`M23L=ACCEPTED` — M21, M22/M22R, and M23/M23R landed sequentially in `main` with normal
merge commits. `M24=NOT_STARTED`; `READY_FOR_M24=YES`.

## Sequential landing

| PR | Scope | Head | Base | Merge commit | Pre-merge CI |
|---|---|---|---|---|---|
| #16 | M21 Desktop Workbench | `d345b833f1d7db9879399724071b601a7a399b0a` | `main` | `f06dac6fb6fdf5505e9fd5133f2461315cc9fdf9` | run `32980213780` PASS |
| #17 | M22/M22R Existing Project Import | `a09cd1ab9e4279dfa3c17bb391b643840df214c2` | retargeted to `main` | `d854a53224ae30ca968fa7ec0f71afe59f2c5f13` | run `33139849241` PASS |
| #18 | M23/M23R Knowledge, Memory, and Trust | `3bc2cc31e22511d37b42e55c5f198d7cc9b47694` | retargeted to `main` | `1988ecf019492ac44cf3936e24836fb6b9bd9458` | run `33142168482` PASS |

All three landings used merge commits. No squash, rebase, force-push, history rewrite, or
administrative bypass was used. The historical integrated snapshot remains preserved at
`archive/m23r-integrated-e3b7203` -> `e3b720340e219a52ff1098693591d74da2d1f3ad`.

## Main post-merge verification

- Main merge head after PR #18: `1988ecf019492ac44cf3936e24836fb6b9bd9458`.
- Exact main push CI: run `33192702132`, head `1988ecf019492ac44cf3936e24836fb6b9bd9458`,
  **PASS**.
- The full main run passed backend, desktop web, desktop Tauri, Playwright/UI, package smoke,
  Linux AppImage, Windows NSIS, release artifact, and M19/M20/M21 release gates.
- Backend regression: **531 passed, 27 skipped, 13 warnings**; coverage **82.17%** against the
  configured 80% threshold.

## Functional and security smoke

- M21 immediate smoke: backend import/start and health, OpenAPI consistency, clean Alembic
  migration, and desktop build — **PASS**.
- M22/M22R immediate smoke: focused import/parser suite **9 passed**; clean migration through
  `0038_m23l_m22r_import_candidates` — **PASS**; imported scripts remain non-executing by test
  contract.
- M23/M23R focused security and propagation suite: **10 passed**; clean migration through
  `0040_m23l_m23r_memory_trust_closure` and `alembic check` — **PASS**.
- Functional UI evidence covers desktop launch, authenticated backend sidecar, project create/open,
  import, scan/review/apply/rescan, dependency impact, memory recall, and canonical provenance;
  exact-head Playwright/UI and package smoke gates — **PASS**.
- Trust controls verified: server-owned identity, scope authorization, evidence authority,
  freshness/conflict propagation, append-only audit, CAS mutation protection, and provenance
  filtering — **PASS**.

## Issues and gates

- `P0=0`; `P1=0`.
- `P2=2`: local all-target MSI/dev-prerelease packaging limitation; release-size baseline manual
  review warning. Required NSIS/AppImage and artifact validation gates pass.
- `INFRA=3`: preserved local database references unavailable historical revision `0028`; local
  Windows workstation lacks cargo; GitHub reports non-blocking Node.js action runtime warnings.
  None affects the exact-head remote acceptance gates.
- `MAIN_PROTECTION`: not configured (GitHub API returned HTTP 404); recommended **YES**,
  configured **NO**. No uncertain protection configuration was changed.
- `PR #15`: historical integrated snapshot only; closed after the three landing PRs, never merged.

## Final state

```text
M21_IN_MAIN=YES
M22R_IN_MAIN=YES
M23R_IN_MAIN=YES
M23L_ACCEPTED=YES
MAIN_POST_MERGE_CI=PASS
READY_FOR_M24=YES
M24_STARTED=NO
```
