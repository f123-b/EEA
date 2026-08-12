# M17 Next Phase

M17, M17R, and M17R.1 acceptance is complete at the reviewed implementation
head. The next milestone may be M18, but M18 implementation has not started.

M17 acceptance verified the TestIR/TestRun contracts, deterministic generation,
fail-closed execution and review gates, project-scoped traceability and issue
deduplication, migration parity, and generated API contracts.

`M17 = ACCEPTED`

`M17R = ACCEPTED`

`M17R.1 = ACCEPTED`

`READY_FOR_M17_FINAL_REVIEW = YES`

`READY_FOR_M18 = YES`

`M18 = NOT_STARTED`

`M19 = NOT_STARTED`

`M21 = NOT_STARTED`

## Non-blocking M18 carry-over

These are P2/future-hardening items, not M17 acceptance blockers:

- `GET /projects/{project_id}/traceability` currently derives default coverage
  from the latest TestRun SourceRevision, while
  `GET /projects/{project_id}/tests/coverage` defaults to the latest project
  SourceRevision. M18's dependency/freshness graph should unify current-source
  and target-source selection semantics.
- Review API requests without explicit `test_run_id`, `build_run_id`, or
  `static_analysis_id` currently select the latest record and then fail closed
  on SourceRevision mismatch. M18 can unify this into latest eligible record
  selection for the target SourceRevision.

M18A through M18E, M19, and M21 remain not started.
