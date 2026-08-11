# M2 Test Report

## Milestone

- Milestone: M2 AI Provider Foundation
- Corrected architecture baseline: EEA V1.3.1 candidate
- Implementation version: 1.3.1.dev0
- Date: 2026-08-11
- Result: PASS

## Implemented scope

- framework-independent `AIProvider` and `SecretService` ports
- LiteLLM Adapter with API-key injection only at the SDK call boundary
- OS keyring-backed SecretService with opaque references and redacted values
- versioned Prompt Registry with declared purpose, model policy, schemas, evidence requirements,
  fallback, steps, and budget policy
- `StructuredGenerationService` as the single structured model-call entry point
- exact registered output-schema matching and Pydantic output validation
- timeout, provider-failure, token-budget, and cost-budget fail-closed behavior
- append-only usage accounting without prompt or response content
- fixed-precision `NUMERIC(18,8)` LLM cost persistence
- Alembic `0003_m2` forward/reverse migration
- dependency invariants confining provider SDKs to Adapters and keeping Ports framework-free

## Acceptance results

| Check | Result | Evidence |
|---|---:|---|
| Python lint and format | PASS | Ruff check and format check; 52 files formatted |
| Strict type checking | PASS | mypy; 33 source files |
| Python tests | PASS | 50 passed |
| Overall coverage | PASS | 95.16% branch-aware coverage |
| Core Domain coverage | PASS | Core modules 97–100%, above the 80% gate |
| Structured output | PASS | Registered JSON Schema sent to provider and Pydantic result returned |
| Invalid structured output | PASS | Deterministic `VALIDATION_ERROR`; failed usage recorded |
| Provider failure | PASS | Sanitized `AI_PROVIDER_UNAVAILABLE`; provider exception text discarded |
| Timeout | PASS | Request cancelled at hard deadline and accounted as failure |
| Token/cost budget | PASS | Over-limit provider usage returns `BUDGET_EXCEEDED` and is recorded |
| Secret not in prompt | PASS | Secret-like keys and opaque Secret types rejected before provider call |
| Secret not in errors | PASS | Raw provider exception and key values absent from public error/details |
| LiteLLM adapter contract | PASS | Request/response translation and call-boundary credential injection tested |
| SecretService adapter contract | PASS | Configure/read/mask/delete behavior tested against a keyring backend contract |
| Prompt/usage persistence | PASS | SQL round trip and prompt version uniqueness verified |
| Migration forward/reverse | PASS | Empty SQLite DB M0→M1→M2 and downgrade to base |
| Migration drift | PASS | Alembic `check` reports no pending schema operations on a fresh DB |
| OpenAPI/TypeScript synchronization | PASS | Both committed generated contracts are current |
| Frontend lint/typecheck/build | PASS | ESLint, TypeScript, and Vite production build |
| Live paid provider call | SKIP | No user credential or billable integration target supplied |
| Native OS keyring integration | SKIP | Optional keyring dependency is not installed in the baseline environment |
| Native Tauri build | SKIP | Rust/Cargo unavailable; not an M2 hard gate |
| Hosted GitHub Actions | SKIP | No remote repository or runner was supplied |

Mocks/fakes are used only for deterministic Port and Adapter contract tests. They are not reported
as live provider or operating-system integration.

## Tool versions

- Python 3.12.13
- pytest 8.4.2
- Ruff 0.16.2
- mypy 1.20.2
- Node.js 24.14.0
- pnpm 11.16.0
- Cargo: unavailable

## Benchmark delta

The regression baseline increased from 30 to 50 tests. Overall branch-aware coverage remains above
the required threshold at 95.16%. Engineering-domain benchmarks begin with later domain milestones.

## Budget usage

No live provider request was made: 0 provider tokens and 0 provider cost. Budget acceptance uses
deterministic provider-contract usage values and verifies both token and fixed-precision cost limits.
