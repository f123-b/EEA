# Changelog

All notable implementation changes are recorded here. Architecture-document changes remain in
the frozen documentation changelogs under `docs/`.

## [Unreleased]

### Added

- M18ER.1 — Runtime Auth & Atomic Restore Closure completed at implementation HEAD
  `21cde4d6398edc85fcb2ea57a5e1bdc44f989e20` on `codex/m18e-renderer-nfr-hardening`. The closure
  adds a real Tauri child-process RuntimeBoundary with loopback-only random port/token,
  authenticated renderer bootstrap, full streaming object hash validation for validate/restore,
  durable `PREPARED -> FS_ACTIVATED -> ACTIVATED` restore recovery, portable source bytes and
  artifact policy, and migration `0033_m18er1_atomic_restore_runtime`. Focused M18E/M18ER.1 and
  migration/runtime tests report **47 passed**; local full pytest reports **481 passed, 4 skipped**
  with the two pre-existing Windows M5 sandbox environment failures; coverage is **84.00%**.
  Ruff check/format, mypy, clean Alembic upgrade/check, OpenAPI, TypeScript contracts, and
  desktop lint/typecheck/build pass. Push CI run `31951639346` and Draft PR CI run
  `31951640929` both pass `backend`, `desktop-web`, and `desktop-tauri`, including cargo check,
  cargo test, and `tauri build --ci`. M18E/M18ER/M18ER.1 remain implemented and ready for final
  human review; M19 has not started.

- M18E Renderer / NFR Hardening implemented on branch
  `codex/m18e-renderer-nfr-hardening`, based on verified main
  `2fc9c9dbd7cdf9cf344899372f1357dbd6d07940`. Added the renderer security contract and
  plain-text sanitizer, loopback backend bearer-auth boundary, Tauri CSP/capability audit,
  bounded and hash-verified Project Backup/Restore, deterministic failure-injection baseline,
  versioned capacity profiles, performance baseline artifact, observability/redaction helpers,
  LOCAL_SINGLE_USER plus User/Organization/Membership/ProjectRole schema foundation, and the
  canonical-unit cross-conversion gate. Added migration
  `0031_m18e_renderer_nfr_hardening`, M18E API routes, and regression coverage. Focused M18E,
  migration, and architecture tests pass; local full pytest reports **453 passed, 4 skipped**,
  with the two pre-existing Windows M5 sandbox environment failures; coverage is **83.76%**.
  Ruff check/format, mypy, clean Alembic upgrade/check, OpenAPI, TypeScript contracts, desktop
  lint, desktop typecheck, and desktop build pass. Rust `cargo check/test` could not run because
  `cargo` is unavailable in this environment. GitHub push CI run `31941880496` and PR CI run
  `31941895651` both passed backend and desktop. The final acceptance-docs push CI run
  `31942245070` and PR CI run `31942247586` also passed backend and desktop. M18E is implemented
  and ready for final human review; M19 has not started.

- M18D/M18DR Final Acceptance completed at reviewed implementation HEAD
  `7dd86a3080b253010cf18f64accee3e2ca665a28`, with implementation final closure commit
  `6afeec383f767634ea45b8453fb7490d45f66ebe` and acceptance docs commit
  `7dd86a3080b253010cf18f64accee3e2ca665a28`. Focused M18/M18R/M18A/M18AR/M18AR.1/M18B/
  M18BR/M18C/M18CR/M18D verification reported **159 passed, 1 skipped**; local full pytest
  reported **435 passed, 4 skipped**, with the two pre-existing Windows M5 sandbox
  environment failures; coverage was **84.19%**. Ruff check/format, mypy, clean Alembic
  upgrade/check, OpenAPI, TypeScript contracts, desktop lint, desktop typecheck, and desktop
  build passed. Final PR CI run `31925059142` and push CI run `31925057389` both passed for
  backend and desktop. Human acceptance is recorded as `M18D = ACCEPTED`, `M18DR = ACCEPTED`,
  `READY_FOR_M18E = YES`, and `M18E = NOT_STARTED`; M18E implementation has not started.

- M18DR Final Closure repair at implementation commit
  `6afeec383f767634ea45b8453fb7490d45f66ebe` (based on the reviewed M18DR docs HEAD
  `2757832435253a0f81b51d0b4902f3e731c35385`). Closed the four residual blockers without adding
  a migration: `PermissionAuthority` is fail-closed with explicit test-only fake authority
  injection; stale `RECONCILE_REQUIRED` hardware actions can be atomically preempted only by
  durable EmergencyStop/SafeState claims; unverified SafeState now forces `ROLLBACK_REQUIRED`
  with `emergency_stop_state = UNKNOWN`; and PWM-enable duration, current-ramp rate, speed-ramp
  rate, watchdog duration, runtime, and existing safety measurements are enforced independently
  with canonical dimensions/units. API payload permissions remain ignored and deprecated.
  Added crash/retry, permission, SafeState, PWM/ramp, normalization, and independent-limit
  regressions. Focused M18/M18R/M18A/M18AR/M18AR.1/M18B/M18BR/M18C/M18CR/M18D: **159 passed,
  1 skipped**; M18D/M18DR module: **57 passed**; local full pytest: **435 passed, 4 skipped**,
  with **2 pre-existing Windows M5 sandbox environment failures**; coverage **84.19%**. Ruff
  check/format, mypy, clean Alembic upgrade/check, OpenAPI, TypeScript contracts, desktop lint,
  desktop typecheck, and desktop build pass. Implementation push CI run `31924719464` and PR
  CI run `31924721927` both have backend PASS and desktop PASS. `M18D = IMPLEMENTED`,
  `M18DR = IMPLEMENTED`, `READY_FOR_M18D_FINAL_REVIEW = YES`, and `M18E = NOT_STARTED`.

- M18DR Hardware Safety Authority & Side-Effect Closure at implementation commit
  `c5308ec95b6e38c9e757b5aa59ef78523a834c67`, repairing reviewed M18D HEAD
  `2fc232825d07294ef474a8d308c004927765c363`. Closed client permission spoofing with
  server-issued, resource-scoped PermissionToken verification; made ResourceLock acquisition
  atomic and owner-bound; added pre-side-effect session CAS claims and M18A SideEffectJournal
  durable hardware intents; added conservative startup reconciliation that never blindly retries
  unknown hardware actions; made E-stop reachable from NORMAL_OPERATION and recoverable unsafe
  states; enforced SafeState on adapter failures/timeouts; consumed Core-neutral MotorControl
  commissioning contributions; and enforced canonical unit/dimension/runtime SafetyLimit gates.
  Added M18DR regression coverage for permission separation/scope, lock exclusivity/ownership,
  concurrent action claims, prepared-action recovery, failure/timeout SafeState, E-stop,
  MotorControl gates, approval binding, and applicable limits. Focused
  M18/M18R/M18A/M18AR/M18AR.1/M18B/M18BR/M18C/M18CR/M18D: **143 passed, 1 skipped**; local
  full pytest **422 passed, 4 skipped**, with **2 pre-existing Windows M5 sandbox environment
  failures**; coverage **84.26%**. Ruff, format, mypy, clean Alembic upgrade/check, OpenAPI,
  TypeScript contracts, desktop lint, desktop typecheck, and desktop build pass. GitHub CI push
  run `31894735902` and pull request run `31894738013` both have backend PASS and desktop PASS.
  `M18C = ACCEPTED_AND_MERGED`, `M18CR = ACCEPTED_AND_MERGED`, `M18D = IMPLEMENTED`,
  `M18DR = IMPLEMENTED`, `READY_FOR_M18D_FINAL_REVIEW = YES`, and `M18E = NOT_STARTED`.

- M18D Hardware Commissioning & Safety at implementation commit
  `fca5962be81309e50290bf1767f03457067fc40a`, built from verified main
  `97d62e47c7bf287627d051197e6ef756abf89523`. Added the fail-closed commissioning state
  machine, structured SafetyLimit/SafeState contracts, deny-by-default permission gates,
  hardware identity and ResourceLock heartbeat/quarantine checks, E-stop/watchdog recovery,
  immutable SourceRevision/BuildInputSnapshot binding, the Fake hardware adapter with fault
  injection, MotorControl commissioning rules, migration `0030_m18d_hardware_commissioning_safety`,
  and M18D regression coverage. Focused M18/M18R/M18A/M18AR/M18AR.1/M18B/M18BR/M18C/M18CR/M18D:
  **179 passed, 1 skipped**; local full pytest **393 passed, 4 skipped**, with the two
  pre-existing Windows M5 sandbox environment failures; coverage **84.11%**. Ruff check,
  Ruff format, mypy, clean Alembic upgrade/check, OpenAPI, TypeScript contracts, desktop lint,
  desktop typecheck, and desktop build pass. `M18C = ACCEPTED_AND_MERGED`,
  `M18CR = ACCEPTED_AND_MERGED`, `M18D = IMPLEMENTED`,
  `READY_FOR_M18D_FINAL_REVIEW = YES`, and `M18E = NOT_STARTED`.

- M18CR Source Mutation Atomicity & Cross-Session CAS Closure at implementation commit
  `25ba1a23da6a5057fa7722f41be2f40ede90f747`, reviewed against M18C review HEAD
  `6cc9b7057c5c210396ae4b2fcfdf5c5e6cd4baac`. Closed the two M18C P1 blockers: source
  mutation ownership is now a database conditional-update claim/finalize protocol shared by
  PatchProposal apply, generated candidate apply, Git commit, reconcile formalization, and
  recovery; multi-file apply now persists a workspace-local `.eea/source-recovery/<operation>`
  BEFORE/staged bundle plus PREPARED journal and only proves APPLIED after a complete AFTER
  state. Active leases prevent reconcile from authoritatively scanning in-flight partial bytes;
  expired leases use deterministic recovery. Added real two-Session, cross-Service, active
  reconcile, partial hard-crash, and Git concurrency regressions. Focused M12/M17/M18/M18A/
  M18B/M18BR/M18C/M18CR: **139 passed, 1 skipped**; local full pytest **378 passed, 4
  skipped**, with **2 pre-existing Windows M5 sandbox environment failures**; coverage
  **84.07%**. Ruff, format, mypy, clean Alembic upgrade/check, OpenAPI, TypeScript contracts,
  desktop lint, desktop typecheck, and desktop build pass. GitHub CI push run `31879721794`
  has backend PASS and desktop PASS. `M18C = IMPLEMENTED`,
  `M18CR = IMPLEMENTED`, `READY_FOR_M18C_FINAL_REVIEW = YES`, and `M18D = NOT_STARTED`.

- M18C Final Acceptance at reviewed final HEAD
  `6cc9b7057c5c210396ae4b2fcfdf5c5e6cd4baac`: the Source Authority / Workspace / Git
  Contract established by implementation commit `c9f2644` is accepted. It establishes
  `SourceWorkspaceService` as the application boundary for editable
  source bytes, filesystem/Git ports and adapters with SafePath enforcement, deterministic
  `SourceRevision` reconciliation, optimistic `PatchProposal` apply, generated-owned
  divergence blocking, bounded Git commit, durable `source.changed` outbox publication,
  source mutation journal recovery, startup workspace reconciliation, migration
  `0027_m18c_source_authority`, and M18C regression coverage. Focused M12/M17/M18/M18A/
  M18B/M18BR/M18C: **123 passed, 1 skipped**; local full pytest **373 passed, 4 skipped**,
  with **2 pre-existing Windows M5 sandbox environment failures**; coverage **84.42%**.
  Ruff, mypy, clean Alembic upgrade/check, OpenAPI, TypeScript contracts, desktop lint,
  desktop typecheck, and desktop build pass. GitHub CI push run `31871683749` and pull
  request run `31871685995` both have backend and desktop PASS. `M18C = ACCEPTED`,
  `READY_FOR_M18D = YES`, and `M18D = NOT_STARTED`.

- M18B/M18BR Final Acceptance and merge closure: reviewed final HEAD
  `6131b0339fc7a92e9b0c1665a9c0edf18d193ef5`, with M18BR implementation HEAD
  `cc5fd96654d41ee7fcf0b112671d5fa9b5305455`. Final verification records focused
  M18/M18R/M18A/M18AR/M18AR.1/M18B/M18BR **129 passed**, local full pytest
  **364 passed, 3 skipped**, **2 pre-existing Windows M5 sandbox environment failures**,
  coverage **84.61%**, all local quality gates PASS, and GitHub CI runs
  `31868017475`, `31868019387`, `31868263048`, and `31868523802` with backend and
  desktop PASS. `M18B = ACCEPTED`, `M18BR = ACCEPTED`, `READY_FOR_M18C = YES`, and
  `M18C = NOT_STARTED`.

- M18BR Composition Authority & Apply Closure at implementation HEAD
  `cc5fd96654d41ee7fcf0b112671d5fa9b5305455`: made public `apply-composition` require
  a valid preview revision and lowercase SHA-256 plan hash, made persisted
  `DomainCompositionState` the runtime/restart SSOT with fail-closed drift detection,
  replaced migration-provider string optimism with executable dry-run validation,
  added explicit `None` versus `{}` capability selection semantics, and added real SQL
  rollback/CAS regressions. Focused M14/M15/M18/M18R/M18A/M18AR/M18B/M18BR: **129 passed**;
  local full pytest: **364 passed, 3 skipped**, with **2 pre-existing,
  environment-specific Windows M5 sandbox failures**; coverage **84.61%**. Ruff,
  mypy, clean Alembic upgrade/check, OpenAPI, TypeScript contracts, desktop lint,
  desktop typecheck, and desktop build pass. GitHub CI push run `31868017475` and
  pull request run `31868019387` both have backend PASS and desktop PASS.
  `M18B = IMPLEMENTED`, `M18BR = IMPLEMENTED`, `READY_FOR_M18B_FINAL_REVIEW = YES`,
  with M18B acceptance pending human review; M18C remains not started.

- M18B Domain Composition Contract at implementation commit
  `fa2c22ee20b9f6ebbf1b78df7124987c6d4e8391`: added the project-scoped
  `DomainCompositionState` SSOT, deterministic canonical plan hashes and capability
  selection persistence, preview/apply TOCTOU protection, atomic multi-Domain
  activation/deactivation with CAS, migration compatibility dry-run reporting, the
  composition API endpoints, migration `0026_m18b_domain_composition_contract`, and
  M18B regression coverage. Focused M14/M15/M18/M18R/M18A/M18AR/M18B: **122 passed**;
  local full pytest: **354 passed, 3 skipped**, with **2 pre-existing,
  environment-specific Windows M5 sandbox failures**; coverage **84.40%**. Ruff,
  mypy, clean Alembic upgrade/check, OpenAPI, TypeScript contracts, desktop lint,
  desktop typecheck, and desktop build pass. `M18B = IMPLEMENTED` and
  `READY_FOR_M18B_FINAL_REVIEW = YES`; GitHub CI runs `31866031198` (push) and
  `31866046633` (pull request) both have backend PASS and desktop PASS. M18B acceptance
  remained pending human review and M18C remained not started.

- M18A Final Acceptance: reviewed implementation HEAD
  `68401b60b88935e7c19bc0309c1845eab3328555`; implementation commit
  `fix(m18a): close dispatcher shutdown lifecycle`. Final verification:
  focused M18/M18R/M18A/M18AR/M18AR.1 **69 passed**; local full pytest
  **345 passed, 3 skipped**, with **2 existing Windows M5 sandbox environment
  failures**; coverage **84.37%**; Ruff check/format, mypy, clean Alembic
  upgrade, `alembic check`, OpenAPI, TypeScript contracts, desktop lint,
  desktop typecheck, and desktop build all pass. GitHub CI run `31859806569`
  has backend PASS and desktop PASS. `M18A = ACCEPTED`, `M18AR = ACCEPTED`,
  `M18AR.1 = ACCEPTED`, `READY_FOR_M18B = YES`, and `M18B = NOT_STARTED`.
- M18R Semantic Freshness, Runtime Binding & Recovery Closure: added canonical
  semantic freshness rules, explicit provider-backed dependency binding,
  historical artifact hash revalidation, CAS merge/recovery semantics, complete
  bootstrap reconciliation, persisted generated protocol output nodes, runtime
  impact propagation for requirement/claim and engineering IR mutations,
  fail-closed dependency APIs, migration `0024_m18_engineering_dependency_graph`,
  and real DB/API acceptance benchmarks. M18R.1 closes mutation snapshot ordering,
  invalid-source recovery, protocol output rebind/regeneration, historical
  protocol bootstrap hashes, FirmwareIR runtime/bootstrap bindings to BuildRun
  and StaticAnalysis, vertical Build/Static/Review freshness, requirement
  analysis reconciliation, and terminal artifact projections. `M18R.1 = IMPLEMENTED`;
  `READY_FOR_M18_FINAL_REVIEW = YES`; `M18A = NOT_STARTED`.
- M18 Final Acceptance: reviewed implementation HEAD
  `2cce5b7ac9facf12ff2ef8f7c743446ec8cb368e`; `M18 = ACCEPTED`,
  `M18R = ACCEPTED`, and `M18R.1 = ACCEPTED`. Acceptance gates are green,
  `READY_FOR_M18_FINAL_REVIEW = YES`, `READY_FOR_M18A = YES`, and
  `M18A = NOT_STARTED`. M18A scope is documented for the next milestone only;
  no M18A implementation was started.
- M18A Transactional Outbox & Recovery: added migration `0025_m18a_transactional_outbox_recovery`,
  durable OutboxEvent/ProcessedEvent/SideEffectJournal records, producer idempotency,
  atomic ProjectCreated/ArtifactCreated/BuildCompleted publication, bounded leasing and
  retry/dead-letter recovery, deterministic handler allowlisting, crash-injection replay
  boundaries, interrupted-job reconciliation, reliability status/reconcile APIs, and
  synchronized OpenAPI/TypeScript contracts. `M18A = IMPLEMENTED` and
  `READY_FOR_M18A_REVIEW = YES`; M18B remains `NOT_STARTED`.
- M18AR Dispatcher, Lease Identity & Transactional Race Closure: connected the durable
  dispatcher to the application lifecycle with unique app-scoped worker identity, startup
  recovery, wake/poll dispatch, savepoint-preserving idempotent race handling, authoritative
  Artifact projection, derived-artifact replay closure, project-scoped reconciliation,
  bounded SQLite busy retry, lease renewal/takeover protection, safe side-effect
  reconciliation, recovery diagnostics, and ProjectConsistencyData. `M18AR = IMPLEMENTED`;
  its implementation state was pending final acceptance at that point;
  `M18B = NOT_STARTED`.
- M18AR.1 Transaction Replay & Recovery CAS Closure: replaced unsafe
  rollback-then-commit retry with complete unit-of-work replay, closed claim/
  renew/finalize/reclaim and interrupted-job recovery CAS conditions, moved
  synchronous dispatcher work off the asyncio loop, made recovery diagnostics
  mutually exclusive, and excluded lost-lease finalize conflicts from retry/
  dead-letter summaries. Added fault-injected write/commit busy regressions,
  CAS race protection, exact diagnostics, lease-loss accounting, and
  non-blocking dispatcher coverage. Focused M18/M18R/M18A/M18AR/M18AR.1:
  **63 passed** at the implementation stage; the final acceptance verification
  and status are recorded in the M18A Final Acceptance entry above.
- M17 Test/Traceability/Review: added Core-neutral declarative TestIR and immutable TestRun
  contracts, deterministic requirement-based test generation, project-scoped controlled
  fail-closed executors, revision/source freshness checks, design/verification coverage,
  project-scoped traceability, deterministic ReviewRun findings, stable Issue dedupe with
  atomic/concurrency-controlled lifecycle updates, migration `0023_m17_test_traceability_review`,
  API routes, and synchronized OpenAPI/TypeScript contracts. M17R.1 now separates contract
  checks from authorized verification, adds project-scoped deterministic facts, restores stable
  source identity to issue dedupe, and makes traceability evidence union concurrency-safe.
- M17 Acceptance: `M17 = ACCEPTED`, `M17R = ACCEPTED`, and `M17R.1 = ACCEPTED` at
  implementation head `a806b805784599500f54dc7923768becc73bf4f7`; PR CI `31601493785`
  and push CI `31601489575` pass for backend and desktop. `READY_FOR_M18 = YES` while
  `M18 = NOT_STARTED`.
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
  for backend and desktop; M17 and its review closures are accepted at the reviewed
  implementation head.
- M17R.1 focused verification records `27 passed`; the full authoritative Python 3.12.13 suite
  records `278 passed, 3 skipped` with `84.99%` coverage. The implementation HEAD CI is green;
  M17 acceptance is complete and M18 remains not started.
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
