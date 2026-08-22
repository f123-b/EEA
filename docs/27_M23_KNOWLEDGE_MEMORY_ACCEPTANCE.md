# M23 Knowledge & Memory Acceptance

M23 adds a structured memory projection over the existing authoritative
`EngineeringClaim`, `Evidence`, and `SourceRevision` records. A memory entry
stores references and context; it does not copy canonical claim values or
create a second fact source.

## Delivered contract

- `KnowledgeScope`: `GLOBAL_PUBLIC`, `USER_PRIVATE`, `PROJECT_PRIVATE`,
  `ORGANIZATION_PRIVATE`, and `TASK_ONLY`.
- `KnowledgeLifecycle`: candidate, active, trusted, stale, conflicted,
  deprecated, archived, and rejected states.
- Explicit authority, verification, trust, freshness, license, and source
  revision fields are persisted with optimistic `revision` control.
- Recall applies scope, lifecycle, project, actor, organization, and task
  filters before deterministic lexical ranking. Every recall writes an audit
  record with the request scope and result IDs.
- Claim-linked memory starts as `CANDIDATE/UNTRUSTED`; an open canonical claim
  conflict projects to `CONFLICTED/UNTRUSTED`. User review can accept, verify,
  resolve after canonical conflict closure, reject, archive, or deprecate it.
- Reviewed M22 import findings can be promoted to project experience with an
  `IMPORTED_PROJECT` Evidence record and `IMPORT_VERIFIED` provenance.

## API surface

- `POST /api/v1/memory/entries`
- `GET /api/v1/memory/entries/{entry_id}`
- `POST /api/v1/memory/recall`
- `POST /api/v1/memory/entries/{entry_id}/review`
- `POST /api/v1/imports/{import_id}/memory-entry`

The desktop M21 context panel exposes the first recall slice for the active
project and renders its lifecycle, type, summary, score, and audit reference.
The first implementation intentionally uses deterministic lexical recall; it
does not introduce a vector database, model fine-tuning, or autonomous memory
promotion.

## Acceptance evidence

- Alembic `0035_m23_knowledge_memory` upgrades and downgrades cleanly.
- `tests/test_m23_knowledge_memory.py` covers project isolation, recall audit,
  optimistic review conflict, and M22 finding promotion.
- Full Python suite: `513 passed, 31 skipped`.
- Python coverage: `82.79%`.
- `ruff check .`, `mypy`, OpenAPI export/check, desktop typecheck, ESLint, and
  desktop production build pass.
