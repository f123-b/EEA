# M18A Known Issues

## Status

`M18A = IMPLEMENTED`

`READY_FOR_M18A_REVIEW = YES`

`M18B = NOT_STARTED`

## Non-blocking environment note

- On this Windows checkout, the existing M5 sandbox subprocess test can return
  code `101` because the local interpreter redirector does not provide the
  runtime behavior expected by that pre-existing test. The same full suite
  excluding that environment-specific test passes with 306 tests and 84.91%
  coverage. This is not an M18A failure and no M5 code was changed.

## Deliberate M18A boundaries

- The reference dispatcher is bounded and in-process. A distributed broker
  such as Redis or NATS is outside this milestone.
- Hardware control, flashing, actuator enablement, and other unsafe external
  effects are not automatically replayed. Unknown external outcomes remain
  `RECONCILE_REQUIRED` for explicit operator reconciliation.
- `RecoveryService` reports reconcile-required journal rows; it does not
  fabricate a successful external result.
- M18B Domain Composition Contract, M18C Source Workspace, M18D commissioning,
  and M18E NFR/fault-matrix work are not implemented.

These are planned scope boundaries or environment notes, not M18A acceptance
blockers.
