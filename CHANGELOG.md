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
- M5 Sandbox Foundation: SafePath/workspace boundaries, ZIP/TAR traversal and symlink guards,
  archive-size limits, shell-free allowlisted command execution, sanitized environments, network
  denial, timeout/output budgets, and structured sandbox errors.
- M12R/M12A FirmwareIR review integration: deterministic BuildRun timestamps and durations,
  HOST_SMOKE/DEVICE build profiles, CMake injection guards, disabled PlatformIO native fallback,
  Core-neutral ESCR component catalog/resolver/lock/materialization, official pinned STM32CubeG4
  provider, dependency-aware firmware snapshots, component APIs and migration `0015_m12a`.
- M13 Firmware static analysis: deterministic FirmwareStaticAnalysis contracts, sandboxed
  Cppcheck provider, four firmware RELEASE_GATE rules, normalized SQL persistence, migration
  `0016_m13_firmware_static_analysis`, and project analysis APIs.
- M5R/M13R/Project Scope Hardening: runtime-enforced sandbox boundaries with fail-closed
  capability checks, Tree-sitter C/C++ analysis with strict Cppcheck XML validation, scoped
  Document/DocumentIR/Evidence reads, per-project document metadata, and migration `0017`.
- Alembic `0006_m5` migration extends the API error catalog for sandbox violations and resource
  limits.
- M6 Requirement DSL: versioned generic requirement profiles, evidence contracts, structured
  generation integration, deterministic completeness/ambiguity findings, claims, issues, and
  follow-up questions.
- Deterministic FOC benchmark profile input support and Alembic `0007_m6` persistence tables.

### Changed

- Applied V1.3.1 FIX-01 to remove concrete MotorControl definitions from the Core boundary.
- Applied the M1 portion of FIX-08 by synchronizing JobStatus, Permission, and engineering error
  codes across Core, database constraints, OpenAPI, TypeScript, and frontend state handling.
- Extended architecture checks so provider SDKs remain confined to Adapters and Ports remain
  independent of Core and frameworks.
- Updated product and desktop version metadata to `1.3.1.dev3` / `1.3.1-dev.3` for M3.
- Updated product and desktop version metadata to `1.3.1.dev4` / `1.3.1-dev.4` for M4.
- Updated product and desktop version metadata to `1.3.1.dev5` / `1.3.1-dev.5` for M5.
- Updated product and desktop version metadata to `1.3.1.dev6` / `1.3.1-dev.6` for M6.
