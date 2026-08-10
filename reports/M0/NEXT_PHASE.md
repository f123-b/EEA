# M0 Next Phase

## Target

M1 Core Domain, as defined by `docs/11_CODEX_IMPLEMENTATION_AND_ACCEPTANCE.md`.

## Scope

- Project
- Artifact
- Evidence
- Issue
- Engineering Decision
- Job
- Permission
- Traceability
- revision and optimistic locking
- schema registry
- SQLAlchemy models and Alembic migration for every new table
- REST contracts under `/api/v1`
- Core Domain test coverage of at least 80%

## Dependencies

- M0 repository skeleton and quality gates
- Frozen entity definitions in `docs/02_DOMAIN_MODEL_AND_SCHEMA.md`
- Storage rules in `docs/03_DATABASE_AND_STORAGE_DESIGN.md`
- API envelope, revision, ETag, and conflict rules in
  `docs/08_FRONTEND_BACKEND_API_CONTRACT.md`

## Entry criteria

- M0 implementation commit is clean and reproducible
- No M0 hard-gate failure remains
- Any schema addition includes migration, forward test, and changelog entry

## Blockers

None for M1.
