# Changelog

All notable implementation changes are recorded here. Architecture-document changes remain in
the frozen documentation changelogs under `docs/`.

## [Unreleased]

### Added

- M17 Test/Traceability/Review: added Core-neutral declarative TestIR and immutable TestRun
  contracts, deterministic requirement-based test generation, project-scoped controlled
  fail-closed executors, revision/source freshness checks, design/verification coverage,
  project-scoped traceability, deterministic ReviewRun findings, stable Issue dedupe with
  atomic/concurrency-controlled lifecycle updates, migration `0023_m17_test_traceability_review`,
  API routes, and synchronized OpenAPI/TypeScript contracts. M17R.1 now separates contract
  checks from authorized verification, adds project-scoped deterministic facts, restores stable
  source identity to issue dedupe, and makes traceability evidence union concurrency-safe.
- M16 ProtocolIR: added the Core-neutral project-scoped CAN Classic/FD protocol
  IR, canonical semantic hashing, deterministic 12-rule validation, reference
  codec, standalone C11/Python/DBC/Markdown generators, revisioned persistence,
  API routes, migration `0022_m16_protocol_ir`, golden-vector tests, and synced
  OpenAPI/TypeScript contracts.
- M15 MotorControl Built-in Domain Plugin: added the bundled `org.eea.motor_control` manifest,
  plugin-owned MotorControlIR requirements/references, deterministic additive rule catalog,
  declarative generator/context/UI contributions, fail-closed MCUConfigIR cross-validation, and
  default Domain Registry integration without adding MotorControl concepts to Core.
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
- M14 Domain Extension Infrastructure: Core-neutral Domain descriptors and opaque IR envelopes,
  deterministic composition/capability/generator routing, project activation APIs and storage,
  metadata-only UI hooks, bundled-only trust enforcement, and migrations `0018`/`0019`.
- M14R Repository Acceptance Hardening: Windows-only Sandbox Job Object isolation, deterministic
  Domain configuration lifecycle and Schema validation, configuration compatibility snapshots,
  synchronized error contracts, migration `0020`/`0021`, and implementation version `1.3.1.dev14`.
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

- M16 ProtocolIR and M16R are accepted at implementation head
  `e75a06d72eec057b230618d6478c98ed734d3b68`, with GitHub Actions Run `31516179752` passing
  for backend and desktop; M17R.1 is implemented and ready for final repository review.
- M17R.1 focused verification records `27 passed`; the full authoritative Python 3.12.13 suite
  records `278 passed, 3 skipped` with `84.99%` coverage. The implementation HEAD CI is green;
  the pull request remains Draft pending repository acceptance.
- M16R closes ProtocolIR determinism and boundary semantics: canonical ordering is shared by
  every generator, CAN arbitration and transport identifiers are fail-closed when ambiguous,
  generated identifiers are C11/DBC safe, full 1..64-bit raw integer codecs are available with
  explicit IEEE-754 physical-value limits, and project-scoped repository writes use atomic
  optimistic-concurrency compare-and-swap semantics.
- M15R.1 closes fail-closed validation semantics: declaration-only startup/calibration `PASS` now
  returns `UNKNOWN` without trusted execution evidence, ADC expected range alone returns `UNKNOWN`
  until current-sense range evidence exists, and composition preview no longer executes Domain
  validators or emits validation diagnostics.
- M15R closes the MotorControl executable validation contract: the Domain Validate action now invokes
  plugin-owned deterministic validation, returns per-rule PASS/FAIL/UNKNOWN/BLOCKED diagnostics,
  synchronizes project-scoped MCUConfigIR inputs, and keeps Core/Application MotorControl-neutral.
- M15R aligns MotorControlIR 1.0.0 with the frozen loop, startup/calibration, and EngineeringValue
  dimension semantics, adds manifest/descriptor/config/UI parity tests, and synchronizes OpenAPI and
  TypeScript contracts without adding a migration.
- Applied V1.3.1 FIX-01 to remove concrete MotorControl definitions from the Core boundary.
- Applied the M1 portion of FIX-08 by synchronizing JobStatus, Permission, and engineering error
  codes across Core, database constraints, OpenAPI, TypeScript, and frontend state handling.
- Extended architecture checks so provider SDKs remain confined to Adapters and Ports remain
  independent of Core and frameworks.
- Updated product and desktop version metadata to `1.3.1.dev3` / `1.3.1-dev.3` for M3.
- Updated product and desktop version metadata to `1.3.1.dev4` / `1.3.1-dev.4` for M4.
- Updated product and desktop version metadata to `1.3.1.dev5` / `1.3.1-dev.5` for M5.
- Updated product and desktop version metadata to `1.3.1.dev6` / `1.3.1-dev.6` for M6.
- Updated product and desktop version metadata to `1.3.1.dev14` / `1.3.1-dev.14` for M14R.
