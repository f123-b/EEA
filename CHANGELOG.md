# Changelog

All notable implementation changes are recorded here. Architecture-document changes remain in
the frozen documentation changelogs under `docs/`.

## [Unreleased]

### Added

- M0 repository skeleton with FastAPI, SQLAlchemy/Alembic, CLI, React/Tauri placeholder, CI,
  health checks, and deterministic OpenAPI export.
- M1 Core Domain entities, schema registry, SQL migration, Project application service, REST API,
  optimistic concurrency, soft deletion, and architecture tests.
- Generated TypeScript contract and exhaustive frontend JobStatus handling.

### Changed

- Applied V1.3.1 FIX-01 to remove concrete MotorControl definitions from the Core boundary.
- Applied the M1 portion of FIX-08 by synchronizing JobStatus, Permission, and engineering error
  codes across Core, database constraints, OpenAPI, TypeScript, and frontend state handling.
