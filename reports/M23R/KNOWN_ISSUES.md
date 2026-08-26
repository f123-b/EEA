# M23R Known Issues

## Product boundaries

- M22 parser depth, native import pickers, and full generic workflow rendering remain bounded
  follow-up work. They are not silently promoted into M24 here.
- Hardware and tool verification remain evidence-gated. A client cannot manufacture a hardware,
  tool, or document verification level through the API payload.

## Environment and delivery

- The checked-out branch is still named `codex/m21-desktop-ui-vertical-slice` even though its
  recorded logical boundary now reaches M23R. The safe PR split is documented in
  `docs/MILESTONE_BOUNDARIES.md`; PR #15 remains open/draft and is not merged here.
- The developer-local `.eea/eea.db` points at an unavailable historical Alembic revision `0028`.
  A clean temporary database upgrades, downgrades, upgrades again, and reports no pending
  operations. The existing local DB was deliberately preserved.
- Remote CI remains the delivery gate until the final SHA is pushed and exact-head required checks
  are green. On Windows, an unscoped `tauri build --ci` also attempts an MSI bundle and is rejected
  by the pre-existing `1.3.1-dev.6` version because MSI requires numeric-only pre-release labels;
  the required NSIS bundle, Rust checks, and Linux CI targets are unaffected.

No P0 or requested-scope P1 defect is known from the current focused tests. Acceptance remains
pending until all final gates are recorded.
