# M6 Test Report — Requirement DSL

**Assessment date:** 2026-08-11

**Baseline:** EEA V1.3.1 candidate

**Implementation version:** `1.3.1.dev6` — Review-2 implementation commit `7a9f4a4`

**Result:** NOT ACCEPTED — local Review-2 gates pass, but the Review-2 commit has not been
published to the remote CI gate.

## Delivered scope

- Generic, versioned requirement profiles with field contracts and evidence contracts.
- Strict profile-version lookup that rejects unsupported versions.
- Natural-language analysis routed through M2 `StructuredGenerationService` with a durable,
  versioned, shell-free prompt contract; the requirement service has no provider or command
  execution path.
- Deterministic completeness and ambiguity gate producing canonical claims, issues, and follow-up
  questions; unknown is never promoted to complete.
- Deterministic FOC benchmark profile input support without motor-control types in Core.
- Evidence repository validation, server-owned `RequirementDraft`, generic field constraints,
  canonical requirement/claim persistence, and Alembic `0008_m6_review_fixes`.
- M6 API, SQL repositories, generated OpenAPI/TypeScript contracts, and explicit startup profile,
  prompt, and Claim predicate seeding.
- Review-2 canonical Claim normalization/conflict retention, EngineeringValue round-trip,
  Requirement reanalysis reconciliation, model-alias routing, production AI composition, and
  client Evidence registration allowlist.

## Acceptance evidence

| Check | Result |
|---|---|
| Ruff lint and format checks | PASS |
| Mypy | PASS — 49 source files |
| Pytest | PASS — 107 passed, 1 environment skip |
| Branch-aware Python coverage | PASS — 89.18% total |
| Profile versioning | PASS — unsupported versions rejected |
| Evidence validation | PASS — existence, scope, global evidence, and type contracts enforced |
| Completeness gate | PASS — missing required fields and evidence become issues/questions |
| Ambiguity gate | PASS — ambiguous fields remain non-complete |
| Server-owned requirement identity | PASS — provider draft cannot supply entity identity |
| Generic field constraints | PASS — blank text, non-finite/range/fractional values rejected |
| Canonical engineering values | PASS — profile dimensions validated through M3 normalization |
| Structured generation boundary | PASS — M2 service is the only natural-language generation entry point |
| Sandbox boundary | PASS — no command, archive, or raw adapter path in requirement analysis |
| Canonical persistence | PASS — M3 claims and requirements persist atomically with analysis refs |
| Canonical Claim semantics | PASS — registered predicates, normalized EngineeringValue, M3 resolver, and retained conflicts |
| Claim snapshot parity | PASS — analysis snapshots match canonical repository claims by ID and semantic JSON |
| Requirement reanalysis | PASS — stable ID, revision increment, semantic update, and duplicate-code rejection |
| Model alias routing | PASS — logical alias resolves to configured concrete model; unresolved aliases fail closed |
| Evidence registration | PASS — project-scoped DOCUMENT/USER_CONFIRMATION/DEVICE_DB bridge; trusted types rejected |
| Persistence migration | PASS — fresh upgrade, `alembic check`, downgrade to `0007_m6`, and re-upgrade |
| API contracts | PASS — OpenAPI and generated TypeScript exports are current |
| Desktop validation | PASS locally — frozen install, lint, typecheck, and production build |

## Local

- Ruff: PASS — `ruff check .`
- Format: PASS — `ruff format --check .`
- Mypy: PASS — 49 source files
- Pytest: PASS — 107 passed, 1 skipped
- Coverage: 89.18% total
- Migration: PASS — upgrade/check/downgrade/re-upgrade sequence
- OpenAPI: PASS — `eea openapi export --check`
- TypeScript: PASS — `eea openapi typescript --check`
- Desktop: PASS — `pnpm lint`, `pnpm typecheck`, `pnpm build`

The live provider gate remains `NOT_EVIDENCED`: no user-authorized billable credential or target
was supplied. The production composition path is implemented and covered with alias-routing and
provider-boundary tests; FakeProvider is not counted as a real-provider smoke test.

## Remote GitHub Actions

- latest prior run id: `31458628923`
- latest prior remote commit: `7f80e94`
- latest prior backend: PASS
- latest prior desktop: PASS
- Review-2 commit `7a9f4a4`: not pushed; no remote run available in this workspace
- Review-2 backend/desktop conclusion: pending

The prior remote run is evidence for `7f80e94`, not for Review-2 commit `7a9f4a4`. The result
therefore remains `NOT ACCEPTED` until the Review-2 commit is run by GitHub Actions and both
backend and desktop jobs are green.

## Intentional limits

- No live billable AI-provider request was made; the real AI integration gate is explicitly
  `NOT_EVIDENCED`, while provider-independent structured-generation behavior is covered with a
  deterministic fake provider.
- The FOC profile validates requirement completeness only. Pin assignment, MCU configuration,
  firmware generation, and hardware commissioning remain later milestones.
- Native Tauri packaging remains a later release check when Rust/Cargo is available.
