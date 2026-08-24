# M23R Known Issues

## Product boundaries

- M22 parser depth, native import pickers, and full generic workflow rendering remain bounded
  follow-up work. They are not silently promoted into M24 here.
- Hardware and tool verification remain evidence-gated. A client cannot manufacture a hardware,
  tool, or document verification level through the API payload.

## Environment and delivery

- The checked-out branch is still named `codex/m21-desktop-ui-vertical-slice` even though its
  recorded logical boundary now reaches M23R. The safe PR split is documented in
  `docs/MILESTONE_BOUNDARIES.md`; remote branch/PR mutation requires an explicit delivery action.
- The developer-local `.eea/eea.db` points at an unavailable historical Alembic revision `0028`.
  A clean temporary database upgrades, downgrades, upgrades again, and reports no pending
  operations. The existing local DB was deliberately preserved.
- Native Tauri build and remote CI were not executed in this local closeout and remain delivery
  gates for a release candidate.

There is no known P0 or requested-scope P1 defect left open from this closeout.
