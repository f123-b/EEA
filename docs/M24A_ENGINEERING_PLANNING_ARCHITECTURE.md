# M24A Engineering Planning Copilot Architecture

M24A adds a project-scoped, reviewable planning surface. It converts a user-owned
`EngineeringRequirement` into a reproducible `PlanningContextSnapshot` and a structured
`EngineeringPlan`. The milestone is deliberately plan-only: a plan is evidence for human
review, never a source patch, command, build, test run, deployment, flash, or hardware action.

## Requirement

`EngineeringRequirement` is the intake boundary. It records the project scope, title,
description, type, priority, constraints, acceptance criteria, source metadata, creator, and
revision. The API derives identity and project authorization from the authenticated server
principal; caller-supplied identity fields are not authorization. Unknown request fields are
rejected.

## Context Assembly

`EngineeringContextAssembler` builds a bounded context snapshot from the current project source
revision and project-scoped claims, hardware/protocol/firmware records, dependencies, issues,
build/static/ERC/test evidence, and memory. Selection is deterministic: requirement and current
source are seeded, relevance is scored from stable text, and selected/excluded records retain a
reason. Selection, evidence references, source revision, claim revisions, evidence revisions,
and memory references are persisted with the plan.

The assembler is bounded at 120 selected and 120 excluded items. The selected source manifest is
represented as data paths only; source content is never treated as instructions. Current,
trusted memory may provide context, but stale, draft, or otherwise untrusted memory is excluded
from planning authority.

## Authority

Canonical project records and backend-derived verification evidence are authoritative for facts.
The user requirement is authoritative for the question being planned. Memory is contextual
recall, not canonical truth. Source files are untrusted data. Derived analysis is explanatory and
must retain its references. The planner may identify an unresolved target or unknown, but it may
not invent a verified pin, protocol identifier, measurement, or execution result.

## LLM Boundary

`PlanningModelProvider` is a provider-neutral protocol with a strict structured output boundary.
The provider receives the requirement, bounded context, and immutable policy constraints and
returns `PlanningModelOutput` or a mapping validated into it. The deterministic provider is the
CI and offline reference implementation. A future hosted model can implement the same boundary
without acquiring filesystem, shell, build, test, canonical mutation, or hardware capability.

## Plan Model

`EngineeringPlan` contains:

- ordered `EngineeringPlanStep` records with action/target, dependencies, preconditions,
  expected result, future verification, risk level, and evidence references;
- `ProposedEngineeringChange` records describing intent, current/proposed state, impact, risk,
  confidence, and proposal status without a diff or executable patch;
- explicit risks, assumptions, unknowns, affected components, acceptance-criterion mappings,
  evidence/memory references, and future `PlanVerification` records;
- provider, model, prompt-template, policy, source revision, context snapshot, creator, and
  supersession metadata for reproducibility.

## Plan Validation

Provider output uses Pydantic `extra="forbid"` models, bounded strings/lists, strict enums, and
model validators. The application validator checks target resolution against selected source
paths and canonical references, acceptance coverage, step verification, proposed-change status,
evidence, and forbidden execution fragments. Quality issues produce `NEEDS_INPUT`; validation
violations produce `BLOCKED`. The policy asserts that all proposed changes remain proposals.

## Risk

Every deterministic plan carries typed risk category, severity, likelihood, affected reference,
mitigation, verification, reason, and evidence references. Safety, timing, protocol, hardware,
compatibility, and maintainability risks remain visible even when the planner lacks enough
evidence to score them precisely.

## Impact

The impact endpoint reports direct proposed-change targets, dependency edges, transitive nodes,
stale dependency state, and verification impact. It is a review surface only. Impact analysis
does not mutate the dependency graph and does not run a build, test, tool, or hardware action.

## Provenance

Context items identify authority, trust, freshness, canonical reference, source revision, reason,
and evidence references. Plans persist the exact context snapshot and revision maps. Audit rows
record intake, planning, stale propagation, review, comments, and revision operations with the
authenticated actor and project scope.

## Review

The review API supports `APPROVE`, `REJECT`, and `REQUEST_REVISION`. Approval means that a human
accepted the plan for the planning milestone; it sets `execution_authorized=false` and grants no
runtime or mutation capability. A revision request creates a new plan that supersedes the old
one. Comments are project/plan scoped and audited.

## Staleness

On plan reads and review, the backend compares the plan's source revision, claim/evidence
revisions, open claim conflicts, and evidence freshness with current project state. A changed
input propagates `STALE`, increments the plan revision, records reasons, and appends an audit
event. Stale and superseded plans cannot be approved.

## Audit and persistence

Migration `0041_m24a_engineering_planning` adds requirement, context snapshot, plan, structured
child records, review/comment, and audit tables. Writes use project authorization and revision
CAS. Parent rows are flushed before child/audit rows so foreign keys remain valid without relying
on implicit ORM relationships. No historical migration is edited.

## API and desktop flow

The `/api/v1` surface covers requirement intake/update/list, plan creation/read, context,
impact, review, and comments under project/plan scope. The desktop Planning Copilot presents:

`Requirement → Analyze → Structured Plan → Context/Impact → Human Review`

The M24A panel contains only create/analyze and approve/revise/reject review controls. It has no
execute, apply, run, deploy, flash, or mutation control.
