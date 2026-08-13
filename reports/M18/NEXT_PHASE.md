# M18R Next Phase

Date: 2026-08-13

## Acceptance complete

M18, M18R, and M18R.1 acceptance is complete.

Reviewed implementation HEAD:

`2cce5b7ac9facf12ff2ef8f7c743446ec8cb368e`

`M18 = ACCEPTED`

`M18R = ACCEPTED`

`M18R.1 = ACCEPTED`

`READY_FOR_M18_FINAL_REVIEW = YES`

`READY_FOR_M18A = YES`

`M18A = NOT_STARTED`

## Next milestone: M18A Transactional Outbox & Recovery

M18A scope is frozen for the next phase only:

- Transactional Outbox
- processed events
- SideEffectJournal
- RecoveryService
- crash injection
- SQL commit → crash 后可重放
- repeated consumption 不产生 duplicate Artifact

This acceptance commit does not implement M18A.

## Follow-up candidates

- Add explicit providers and bindings for artifact families introduced after
  the M18 baseline.
- Add operator-facing graph inspection and remediation workflows.
- Add production-scale latency and graph-size measurements once deployment
  infrastructure is available.
- Define the next milestone only after M18R final review.
