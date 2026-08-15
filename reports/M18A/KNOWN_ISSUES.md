# M18A / M18AR Known Issues

## Status

`M18A = ACCEPTED`

`M18AR = ACCEPTED`

`M18AR.1 = ACCEPTED`

`READY_FOR_M18B = YES`

`M18B = NOT_STARTED`

## PRE-EXISTING / ENVIRONMENT-SPECIFIC / NON-BLOCKING

- Local full pytest reports **345 passed, 3 skipped**, with **2 existing
  Windows M5 sandbox environment failures**. The failures are caused by the
  local interpreter redirector/runtime behavior and are not an M18A, M18AR,
  or M18AR.1 failure. No M5 code was changed.

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
blockers. M18A, M18AR, and M18AR.1 are accepted. M18B remains
`NOT_STARTED`.
