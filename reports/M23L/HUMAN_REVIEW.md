# M23L Human Review Checklists

## M21

- [ ] Desktop launches
- [ ] Backend sidecar starts/stops correctly
- [ ] Session auth works
- [ ] Chinese default
- [ ] Language persistence
- [ ] DEVICE workflow works
- [ ] Build/static/ERC/TestRun surfaces work
- [ ] Traceability/review evidence works
- [ ] Domain activate/deactivate works

## M22/M22R

- [ ] Folder import
- [ ] Git import
- [ ] Archive import
- [ ] `.ioc` parsing
- [ ] KiCad parsing
- [ ] DBC parsing
- [ ] Candidate review
- [ ] Conflict handling
- [ ] Canonical apply
- [ ] Rescan
- [ ] Dependency impact
- [ ] Source revision immutable
- [ ] Imported scripts never execute

## M23/M23R

- [ ] Memory create
- [ ] Recall
- [ ] User-private isolation
- [ ] Project isolation
- [ ] Organization fail-closed
- [ ] Task isolation
- [ ] Fake identity blocked
- [ ] Fake verification blocked
- [ ] Stale propagation
- [ ] Conflict propagation
- [ ] Audit
- [ ] CAS

Human review and explicit per-PR landing confirmation remain required.

Automated preflight is complete: PR #16 final-head CI passed at
`d345b833f1d7db9879399724071b601a7a399b0a`, PR #17 final-head CI passed at
`a09cd1ab9e4279dfa3c17bb391b643840df214c2`, and synchronized PR #18 final-head
CI passed at `0766ae14c2f3debc17b4c4d9959eb72a29be9153`. This checklist is
still intentionally unchecked because human review and explicit sequential
landing approval are required.
