# M23R Knowledge & Memory Trust Model

M23R keeps `KnowledgeEntry` as a derived projection. Canonical Claims,
Evidence, and SourceRevision rows remain authoritative; memory text never
becomes a second source of truth.

## Identity and scope

Every memory request resolves a server-owned `IdentityContext` from the
authenticated principal and persisted identity rows. Renderer fields such as
`actor_ref`, `owner_ref`, `organization_ref`, authority, verification, and
freshness are compatibility fields only and cannot grant access or trust.

| Scope | Required server-owned context | Boundary |
|---|---|---|
| `GLOBAL_PUBLIC` | trusted publisher capability | no caller-selected owner |
| `USER_PRIVATE` | authenticated user id | owner is written from the context |
| `PROJECT_PRIVATE` | project role permission | project id is checked against the role |
| `ORGANIZATION_PRIVATE` | organization membership | organization id is written from membership |
| `TASK_ONLY` | server-bound task id | request task fields are ignored |

The local desktop installation has one explicit `local:single-user` principal
with the publisher capability. Team principals must have persisted project or
organization permissions; missing context fails closed.

## Authority and trust

`ACCEPT` produces only `USER_CONFIRMED`. `VERIFY` requires backend-loaded,
current Evidence and a requested verification level. Tool and hardware
verification cannot be created by the client evidence allowlist. Strict
provenance requires producer, producer version, timestamp, and source revision;
hardware evidence additionally requires hardware identity, probe identity,
commissioning session, configuration, and measurement.

Trust is conservative: open conflicts, stale source/evidence, and missing
verification keep a projection `UNTRUSTED`. A resolved conflict transitions the
projection to `CANDIDATE`; it never silently restores previous trust.

## Lifecycle, freshness, and propagation

The lifecycle policy is centralized in `MemoryLifecyclePolicy`. `ACTIVE`,
`TRUSTED`, or `CANDIDATE` projections become `STALE` when a source/evidence or
claim revision changes, and become `CONFLICTED` when an open canonical conflict
is present. `ARCHIVED`, `REJECTED`, and `DEPRECATED` are excluded from normal
recall. History requires the explicit `include_non_active` switch.

The exact semantic propagation events are:

`ClaimChanged`, `ClaimConflictOpened`, `ClaimConflictResolved`,
`EvidenceInvalidated`, `EvidenceSuperseded`, and `SourceRevisionChanged`.

Canonical API mutations reconcile impacted memory entries in the same
transaction and enqueue a deterministic outbox event. The recovery dispatcher
replays the same reconciliation idempotently after a crash. Every transition
records before/after state, reason, principal, user, session, and request id in
the append-only `knowledge_audits` table.

## Recall and concurrency

Recall applies identity-derived scopes, project/task/org visibility, lifecycle
filtering, deterministic ranking, and a recall audit record. Memory edits,
review transitions, evidence lifecycle changes, and conflict resolution use
revision compare-and-set; a stale expected revision returns
`REVISION_CONFLICT` without overwriting the winner.

## Compatibility and non-goals

Existing M23 wire fields remain accepted where needed by the desktop client,
but are ignored for authorization and trust. M23R does not begin M24, does not
replace canonical engineering records, and does not execute hardware from a
renderer request.
