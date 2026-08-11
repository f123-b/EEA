# M6 Test Report — Requirement DSL

**Assessment date:** 2026-08-11

**Baseline:** EEA V1.3.1 candidate

**Implementation version:** `1.3.1.dev6`

**Result:** NOT ACCEPTED — remote GitHub Actions has not run for the review-fix commit.

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
- M6 API, SQL repositories, generated OpenAPI/TypeScript contracts, and explicit startup profile
  and prompt seeding.

## Acceptance evidence

| Check | Result |
|---|---|
| Ruff lint and format checks | PASS |
| Mypy | PASS — 49 source files |
| Pytest | PASS — 99 passed, 1 environment skip |
| Branch-aware Python coverage | PASS — 89.00% total |
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
| Persistence migration | PASS — fresh upgrade, `alembic check`, downgrade to `0007_m6`, and re-upgrade |
| API contracts | PASS — OpenAPI and generated TypeScript exports are current |
| Desktop validation | PASS locally — frozen install, lint, typecheck, and production build |

## Local

- Ruff: PASS — `ruff check .`
- Format: PASS — `ruff format --check .`
- Mypy: PASS — 49 source files
- Pytest: PASS — 99 passed, 1 skipped
- Coverage: 89.00% total
- Migration: PASS — upgrade/check/downgrade/re-upgrade sequence
- OpenAPI: PASS — `eea openapi export --check`
- TypeScript: PASS — `eea openapi typescript --check`
- Desktop: PASS — `pnpm install --frozen-lockfile`, `pnpm lint`, `pnpm typecheck`, `pnpm build`

## Remote GitHub Actions

- run id: not run — GitHub CLI is not authenticated in this workspace
- commit: not applicable — local review-fix commits `2141ed5` plus report update, not pushed
- backend: not run
- desktop: not run
- conclusion: unavailable

Remote main CI is therefore not evidence of acceptance. The result remains `NOT ACCEPTED` until
the review-fix commit is run by GitHub Actions and both backend and desktop jobs are green.

## Intentional limits

- No live billable AI-provider request was made; provider-independent structured-generation
  behavior is covered with a deterministic fake provider.
- The FOC profile validates requirement completeness only. Pin assignment, MCU configuration,
  firmware generation, and hardware commissioning remain later milestones.
- Native Tauri packaging remains a later release check when Rust/Cargo is available.
