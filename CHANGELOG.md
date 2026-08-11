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
- M2 provider-neutral AI and Secret ports, LiteLLM/keyring adapters, versioned Prompt Registry,
  structured Pydantic output validation, timeout and budget enforcement, and durable usage
  accounting.
- Alembic `0003_m2` migration for prompt definitions and AI usage records.
- M3 Canonical Unit and Claim Core: normalized `EngineeringValue` values, frozen engineering
  dimensions, claim predicates, applicability-aware conflict detection, and configurable claim
  resolution.
- Evidence-gated `DOCUMENT_VERIFIED` verification and durable SQL repositories for predicate,
  claim, and conflict records.
- Alembic `0004_m3_claim_core` migration and synchronized claim enum metadata in OpenAPI and
  generated TypeScript.
- M4 Document + Device Intelligence: content-addressed document upload, DocumentIR, Docling and
  claim-extraction ports, STM32G431 provider fixture, and auditable multi-source device merge.
- Document/device API routes, M4 enum catalogs, durable `0005_m4` persistence migration, and
  synchronized OpenAPI/TypeScript contracts.

### Changed

- Applied V1.3.1 FIX-01 to remove concrete MotorControl definitions from the Core boundary.
- Applied the M1 portion of FIX-08 by synchronizing JobStatus, Permission, and engineering error
  codes across Core, database constraints, OpenAPI, TypeScript, and frontend state handling.
- Extended architecture checks so provider SDKs remain confined to Adapters and Ports remain
  independent of Core and frameworks.
- Updated product and desktop version metadata to `1.3.1.dev3` / `1.3.1-dev.3` for M3.
- Updated product and desktop version metadata to `1.3.1.dev4` / `1.3.1-dev.4` for M4.
