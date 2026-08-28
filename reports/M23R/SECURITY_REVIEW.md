# M23R Security Review

## Review scope

This review covers the Knowledge/Memory trust boundary: identity binding,
scope authorization, evidence authority, freshness/conflict propagation, audit,
and optimistic concurrency.

| Control | Result | Evidence |
|---|---|---|
| Identity spoofing | PASS locally | client actor/owner/org/trust fields are ignored; server principal is used |
| User/project/org/task scope | PASS locally | `IdentityContext` policy and focused scope tests |
| Fake tool/hardware verification | PASS locally | strict producer/provenance checks and client evidence allowlist |
| Canonical propagation | PASS locally | synchronous reconcile plus exact semantic outbox handlers |
| Conflict resolution | PASS locally | resolved conflicts remain candidates until explicit revalidation |
| Audit | PASS locally | append-only `knowledge_audits` records mutation and derived transitions |
| CAS | PASS locally | memory, evidence, claim-conflict, and review revisions are conditional |

## Residual delivery checks

Remote CI remains the final delivery check for the exact pushed commit. Local
Playwright UI and native Tauri evidence is complete. No merge, force push, or
administrative bypass is authorized by this review.
