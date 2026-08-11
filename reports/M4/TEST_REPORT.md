# M4 Test Report — Document + Device Intelligence

**Assessment date:** 2026-08-11

**Baseline:** EEA V1.3.1 candidate

**Implementation version:** `1.3.1.dev4`

**Result:** PASS

## Delivered scope

- Content-addressed document upload and durable DocumentIR persistence.
- Core DocumentIR page/section/table/figure locations and extracted-claim references.
- Docling parser and claim-extraction adapter ports with deterministic fixture adapters.
- STM32G431 provider facts for package, pin, alternate function, peripheral, ADC/DMA, and
  complementary-PWM queries.
- Applicability-preserving multi-source device merge with retained scalar and pin-function
  conflicts.
- Versioned document/device API routes, OpenAPI/TypeScript synchronization, and migration
  `0005_m4`.

## Acceptance evidence

| Check | Result |
|---|---|
| Ruff lint and format checks | PASS |
| Mypy | PASS — 43 source files |
| Pytest | PASS — 67 passed |
| Branch-aware Python coverage | PASS — 90.96% total |
| Document upload | PASS — base64 upload, SHA-256 content address, duplicate-safe persistence, retrieval |
| DocumentIR | PASS — page/section/table/figure locations survive parser and SQL round-trip |
| Docling boundary | PASS — injected converter contract and optional-runtime error path |
| Claim extraction | PASS — adapter output is validated as EngineeringClaim and retains evidence rules |
| STM32G431 PA8/TIM1_CH1 | PASS — AF6 fixture query |
| Complementary PWM | PASS — PB13/TIM1_CH1N fixture query |
| FDCAN | PASS — PA11 RX and PA12 TX |
| ADC/DMA | PASS — PA0/ADC1_IN1 and DMA1 request facts |
| Package query | PASS — UFQFPN48 package selection |
| Illegal alternate function | PASS — `PIN_FUNCTION_INVALID`, no guessed PASS |
| Multi-source merge | PASS — compatible facts are unioned and conflicts are retained |
| Migration | PASS — fresh upgrade, `alembic check`, and downgrade to base |
| API contracts | PASS — OpenAPI and generated TypeScript exports are current |
| Desktop validation | PASS — frozen install, lint, typecheck, and production build |

## Environment and intentional limits

- Python 3.12.13, pytest 8.4.2, ruff 0.16.2, mypy 1.20.2.
- Node 24.14.0 and pnpm 11.16.0.
- Native Tauri validation remains skipped because Cargo/Rust is unavailable in this environment.
- The Docling SDK and live vendor-data downloads are not installed; deterministic injected/frozen
  fixtures validate the adapter and provider contracts. Live-source integration remains a follow-up
  before production knowledge ingestion.
- The test suite emits the known Starlette/httpx deprecation warning only.

No M4 acceptance condition is satisfied by silently guessing an unsupported pin function.
