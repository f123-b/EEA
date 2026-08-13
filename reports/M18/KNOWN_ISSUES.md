# M18R Known Issues

Date: 2026-08-13

## Scope boundaries

- The provider registry is intentionally explicit and fail-closed. A new graph
  node type requires an explicit provider and binding implementation.
- Global Claim records cannot be mutated through a project-scoped lifecycle
  endpoint. An authoritative cross-project mutation path remains a future
  capability.
- Bootstrap records unresolved explicit references as gaps; it does not infer
  relationships from naming, ordering, or foreign tables.

## Environment note

The repository contains pre-existing Windows sandbox subprocess coverage that is
environment-sensitive when launched through the `uv` interpreter redirector.
This is outside the M18 change surface and is retained as an environment note.

No unresolved M18R implementation failure is known after the focused benchmark
suite. The repository-wide Python run still reports two pre-existing Windows
sandbox subprocess failures under the local interpreter redirector; these are
outside the M18 change surface and are retained for the final handoff.

The current working database reports pre-existing Alembic drift in legacy
tables and `ai_usage_records.llm_cost`; a clean temporary database passes
upgrade and `alembic check`. No M18R.1 schema migration was required, and no
`0025` migration was added.
