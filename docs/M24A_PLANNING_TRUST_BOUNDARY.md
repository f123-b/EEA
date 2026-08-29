# M24A Planning Trust Boundary

M24A is a proposal boundary. The following statements are normative:

| Surface | Trust meaning | M24A rule |
|---|---|---|
| LLM output | Proposal, not fact | Validate schema, targets, evidence coverage, and policy before persistence. |
| Plan approval | Permission to accept a plan for review | Never execution authority; persisted as `execution_authorized=false`. |
| Memory | Context and recall | Never canonical authority; stale/untrusted entries are filtered. |
| Source content | Untrusted data | Treat paths/content as data, never as instructions or tool commands. |
| Canonical records | Backend-owned facts/evidence | Read with project scope and revision provenance. |
| User identity | Server-authenticated principal | Ignore spoofable actor/owner fields for authorization. |

## Untrusted source and prompt injection

Source manifests and imported project content can contain instruction-shaped text such as
“ignore previous instructions” or shell syntax. The context assembler labels source items
`UNTRUSTED_SOURCE` / `UNTRUSTED` and sets `source_content_is_untrusted=true`. The planner receives
the content as a bounded context value, not as an instruction channel. The deterministic
provider uses only stable metadata and never dispatches a command from source text.

Provider output is separately untrusted. Strict Pydantic models reject unknown fields, invalid
enums, invalid sizes, and malformed nested values. Proposed-change validators and the application
validator reject executable fragments, patch instructions, shell/process hints, and invalid
targets. Invalid output fails closed as a validation error.

## Capability denial

The M24A `PlanningPolicy` sets all of the following to false:

`allow_file_mutation`, `allow_shell`, `allow_build`, `allow_test_execution`,
`allow_hardware_action`, and `allow_canonical_mutation`.

The application package has no M24A path to a subprocess, filesystem mutation, build executor,
test executor, flash/deploy adapter, or canonical write. Verification is described as a future
plan, and `PlanVerification.execution_allowed_in_m24a` is always false. Approval does not change
these flags.

## Scope, freshness, and concurrency

Every route first loads the authenticated identity context and checks project access. Plan and
requirement IDs are resolved inside that project scope. Context captures source/claim/evidence
revisions. Reads and reviews refresh staleness before returning data. Review and revision
operations require `expected_revision`; a mismatch returns a revision conflict and does not apply
the requested action. Stale, superseded, or conflicting inputs cannot silently become approved.

## Human review boundary

M24A can make a structured engineering question and its consequences legible. It cannot decide
that a proposed change is safe to execute, cannot mutate canonical engineering state, and cannot
claim that a future build, test, ERC, simulation, or hardware measurement passed. Those actions
belong to the explicitly separate M24B controlled change execution milestone.
