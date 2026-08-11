# Project Scope Hardening Test Report

Date: 2026-08-11
Repository: `f123-b/EEA`
Commit under review: `007637fc4a7d0e398f6622262ab56036e08b4824`

## Root cause

Document, DocumentIR, and Evidence repository reads were not consistently scoped by project.
Document content-hash uniqueness also caused an upload in one project to reuse the metadata
identity of another project, creating a scope-pollution risk.

## Implementation

- Repository reads now accept an explicit project scope and apply the rule
  `project_id = requested project OR project_id IS NULL`.
- Project APIs use project-path routes for Document and Evidence reads/writes; cross-project
  resources are reported as `KNOWLEDGE_SCOPE_DENIED`, while unknown IDs retain their existing
  not-found behavior.
- DocumentIR reads join through the scoped Document record.
- Removed the global Document content-hash unique constraint. Same-content uploads retain
  deduplicated storage bytes but receive independent project metadata identities.
- Added Alembic migration `0017_project_scope_hardening` and regenerated OpenAPI and TypeScript
  contracts.

## Verification

Command:

```text
python -m pytest tests/test_project_scope_hardening.py tests/test_m4_intelligence.py tests/test_m6_requirements.py tests/test_m6_review2.py tests/test_migrations.py -q --no-cov
```

Result: **48 passed**. Coverage includes cross-project Document/Evidence/DocumentIR denial,
same-project reads, global-resource visibility, same-content upload isolation, API behavior,
and migration verification.

Acceptance: **PROJECT_SCOPE_HARDENING = ACCEPTED** for the implemented local gate.
