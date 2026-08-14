# M18A / M18AR Known Issues

## Status

`M18A = IMPLEMENTED`

`M18AR = IMPLEMENTED`

`M18AR.1 = IMPLEMENTED`

`READY_FOR_M18A_FINAL_ACCEPTANCE = YES`

`READY_FOR_M18A_FINAL_REVIEW = YES`

`M18B = NOT_STARTED`

`READY_FOR_M18B = NO`

## Non-blocking environment note

- On this Windows checkout, the existing M5 sandbox subprocess tests can fail
  with code `101` or miss the expected timeout boundary because the local
  interpreter redirector does not provide the runtime behavior expected by
  those pre-existing tests. The same full suite excluding that
  environment-specific test passes with 333 tests and 82.38% coverage. This
  is not an M18A or M18AR failure and no M5 code was changed.

## Deliberate M18A boundaries

- The reference dispatcher is bounded and in-process. A distributed broker
  such as Redis or NATS is outside this milestone.
- M18AR.1 does not broaden the M18A contract: transactional replay, CAS
  recovery, bounded worker-thread dispatch, and diagnostics closure are the
  complete scope of this increment.
- Hardware control, flashing, actuator enablement, and other unsafe external
  effects are not automatically replayed. Unknown external outcomes remain
  `RECONCILE_REQUIRED` for explicit operator reconciliation.
- `RecoveryService` reports reconcile-required journal rows; it does not
  fabricate a successful external result.
- M18B and later milestones are not implemented. M18AR is limited to the
  dispatcher, lease identity, transactional race closure, scoped recovery,
  diagnostic APIs, and safe reconciliation required to complete M18A.

These are planned scope boundaries or environment notes, not M18A acceptance
blockers. M18A remains pending human final acceptance; M18B remains
NOT_STARTED.
