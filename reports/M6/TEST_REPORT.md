# M6 Test Report — Requirement DSL

**Assessment date:** 2026-08-11

**Baseline:** EEA V1.3.1 candidate

**Implementation version:** `1.3.1.dev6`

**Result:** PASS — M6 policy and deterministic requirement-analysis foundation

## Delivered scope

- Generic, versioned requirement profiles with field contracts and evidence contracts.
- Strict profile-version lookup that rejects unsupported versions.
- Natural-language analysis routed through M2 `StructuredGenerationService` with a versioned,
  shell-free prompt contract; the requirement service has no provider or command execution path.
- Deterministic completeness and ambiguity gate producing canonical claims, issues, and follow-up
  questions; unknown is never promoted to complete.
- Deterministic FOC benchmark profile input support without motor-control types in Core.
- M6 API, SQL repositories, generated OpenAPI/TypeScript contracts, and Alembic `0007_m6` tables.

## Acceptance evidence

| Check | Result |
|---|---|
| Ruff lint and format checks | PASS |
| Mypy | PASS — 49 source files |
| Pytest | PASS — 80 passed, 1 environment skip |
| Branch-aware Python coverage | PASS — 88.83% total |
| Profile versioning | PASS — unsupported versions rejected |
| Completeness gate | PASS — missing required fields and evidence become issues/questions |
| Ambiguity gate | PASS — ambiguous fields remain non-complete |
| Canonical engineering values | PASS — profile dimensions validated through M3 normalization |
| Structured generation boundary | PASS — M2 service is the only natural-language generation entry point |
| Sandbox boundary | PASS — no command, archive, or raw adapter path in requirement analysis |
| Persistence migration | PASS — fresh upgrade, `alembic check`, and downgrade to base |
| API contracts | PASS — OpenAPI and generated TypeScript exports are current |
| Desktop validation | PASS — frozen install, lint, typecheck, and production build |

## Intentional limits

- No live billable AI-provider request was made; provider-independent structured-generation
  behavior is covered with a deterministic fake provider.
- The FOC profile validates requirement completeness only. Pin assignment, MCU configuration,
  firmware generation, and hardware commissioning remain later milestones.
- Native Tauri packaging remains a later release check when Rust/Cargo is available.
