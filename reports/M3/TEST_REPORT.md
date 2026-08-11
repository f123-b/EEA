# M3 Test Report — Canonical Unit + Claim Core

**Assessment date:** 2026-08-11

**Baseline:** EEA V1.3.1 candidate

**Implementation version:** `1.3.1.dev3`
**Result:** PASS

## Delivered scope

- Core-owned canonical unit normalization for all frozen engineering dimensions.
- `EngineeringValue`, `EngineeringClaim`, claim predicate, and claim conflict models.
- Applicability-aware claim resolution with source-priority, source-version, and manual paths.
- Durable SQL repositories and Alembic migration `0004_m3_claim_core`.
- Synced claim enums across Core, API metadata/OpenAPI, generated TypeScript, and desktop tests.

## Acceptance evidence

| Check | Result |
|---|---|
| Ruff lint and format checks | PASS |
| Mypy | PASS — 37 source files |
| Pytest | PASS — 60 passed |
| Branch-aware Python coverage | PASS — 93.32% total |
| Canonical equivalence | PASS — `24 V == 24000 mV`, `1 kHz == 1000 Hz`, `1000 us == 1 ms` |
| Canonical ordering | PASS — `48 V > 40 V` |
| Dimension protection | PASS — VOLTAGE/CURRENT comparisons raise an explicit normalization error |
| Evidence invariant | PASS — `DOCUMENT_VERIFIED` claims require evidence |
| Claim predicate contract | PASS — built-in references are registered and unsupported references are rejected |
| Conflict handling | PASS — errata source priority resolves; distinct package/revision applicability does not create a false conflict; version/manual paths are covered |
| Persistence and migration | PASS — claim round-trip, conflict retention, fresh upgrade, schema check, and downgrade to base |
| OpenAPI / TypeScript contracts | PASS — deterministic export and generated client checks current |
| Desktop validation | PASS — frozen install, lint, typecheck, and production build |

## Environment and intentional skips

- Python 3.12.13, pytest 8.4.2, ruff 0.16.2, mypy 1.20.2.
- Node 24.14.0 and pnpm 11.16.0.
- Native Tauri validation is skipped because Cargo/Rust is unavailable in this environment.
- Live LiteLLM-provider and OS-keyring checks remain optional M2 integration checks; M3 does not
  require a real provider request or secret-store mutation.
- The test suite emits the known Starlette/httpx deprecation warning only.

No M3 acceptance condition is satisfied through a mock, placeholder, or skipped integration.
