# M17 Known Issues

## Status

`M17 = ACCEPTED`

`M17R = ACCEPTED`

`M17R.1 = ACCEPTED`

`READY_FOR_M17_FINAL_REVIEW = YES`

`READY_FOR_M18 = YES`

## Known limitations

- The default HTTP test-run route registers one project-scoped contract
  executor and one project-fact executor for the validated source-revision
  existence fact. Contract-only results remain `BLOCKED` for verification;
  unknown, manual, malformed, or arbitrary command-shaped cases remain
  `BLOCKED`; a client cannot submit `PASS` as a substitute for execution.
- Manual or external test outcomes require trusted, project-scoped,
  traceable evidence before they can be used as acceptance evidence. Hardware
  commissioning remains outside M17 and belongs to the later M19 scope.
- The standard `uv run pytest` path on this Windows checkout uses a broken
  interpreter redirector for the existing M5 subprocess tests. The authoritative
  Python 3.12.13 run passes the complete suite and the M5 tests (`8 passed,
  3 skipped`).
- Cross-milestone dependency invalidation is intentionally deferred to M18.
- M19 FOC/commissioning and M21 Desktop UI are not implemented or accepted.

## Non-blocking M18 carry-over

- Traceability and Test Coverage endpoints currently use different default
  source-selection paths; M18 should unify current-source and target-source
  semantics once the dependency/freshness graph exists.
- Review API automatic record selection currently chooses the latest record and
  then fails closed on SourceRevision mismatch; M18 can choose the latest
  eligible record for the target SourceRevision.

These P2 items are future hardening and are not M17 acceptance blockers.

These limitations do not change the fail-closed behavior of the M17 review
engine or its project-scope checks.
