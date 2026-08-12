# M17 Known Issues

## Status

`M17 = IMPLEMENTED`

`M17R = PENDING_REVIEW`

`READY_FOR_M18 = NO`

## Known limitations

- The default HTTP test-run route has no registered server-side arbitrary
  executor. Requests that cannot be executed by a controlled executor return
  `BLOCKED`; a client cannot submit `PASS` as a substitute for execution.
- Manual or external test outcomes require trusted, project-scoped,
  traceable evidence before they can be used as acceptance evidence. Hardware
  commissioning remains outside M17 and belongs to the later M19 scope.
- The standard `uv run pytest` path on this Windows checkout uses a broken
  interpreter redirector for the existing M5 subprocess tests. The authoritative
  Python 3.12.4 run passes the complete suite and the M5 tests (`8 passed,
  3 skipped`).
- Cross-milestone dependency invalidation is intentionally deferred to M18.
- M19 FOC/commissioning and M21 Desktop UI are not implemented or accepted.

These limitations do not change the fail-closed behavior of the M17 review
engine or its project-scope checks.
