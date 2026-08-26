# M22R Known Issues

- Native Git credential-provider UX remains follow-up work. Embedded credentials are rejected and
  Git materialization remains bounded to the existing safe clone/checkout contract.
- KiCad and DBC parsers intentionally stop at structural evidence. They do not claim ERC,
  electrical correctness, protocol validation, or datasheet verification.
- The local branch still contains the user-owned untracked `main.c`; it is intentionally not part
  of the M22R changes.
- PR #15 remains Draft/Open. The combined M21/M22/M23/M22R history is not a safe direct-merge
  boundary, so no merge operation was attempted and direct merge remains `NO`.
- The existing local `.eea/eea.db` historical revision issue remains preserved; clean temporary
  migration gates pass.
- The default local all-target Tauri developer packaging command retains its pre-existing
  dev-version/NSIS limitation. Formal CI packaging is green for the required Windows NSIS and
  Linux AppImage artifacts, so this is a local-only P2 follow-up, not a release blocker.
- The release-size report has no previous baseline and requests manual growth review; artifact
  validation and secret scanning passed.

No P0 or requested-scope P1 defect is known after the final CI rerun. The only open items are the
local-only packaging follow-up, the size-baseline review warning, and normal human PR review.
