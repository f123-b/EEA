# M22R Known Issues

- Native Git credential-provider UX remains follow-up work. Embedded credentials are rejected and
  Git materialization remains bounded to the existing safe clone/checkout contract.
- KiCad and DBC parsers intentionally stop at structural evidence. They do not claim ERC,
  electrical correctness, protocol validation, or datasheet verification.
- The local branch still contains the user-owned untracked `main.c`; it is intentionally not part
  of the M22R changes.
- PR #15 remains Draft/Open. Local M22R commits have not been pushed and no merge operation was
  attempted.
- The existing local `.eea/eea.db` historical revision issue remains preserved; clean temporary
  migration gates pass.

No new P0 or requested-scope P1 defect is known from the local M22R gates.

