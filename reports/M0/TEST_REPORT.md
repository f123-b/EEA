# M0 Test Report

## Milestone

- Milestone: M0 Repository Skeleton
- Architecture baseline: EEA V1.3 / 1.3.0
- Implementation version: 1.3.0.dev0
- Date: 2026-08-11
- Result: PASS

## Environment

- OS: Windows 11 development workspace
- Python: 3.12.13
- Node.js: 22.12.0 (frontend runtime)
- pnpm: 11.16.0
- Git: 2.46.0.windows.1
- Rust/Cargo: unavailable in the local environment

## Acceptance results

| Check | Result | Evidence |
|---|---:|---|
| Frozen documentation integrity | PASS | Every entry in `SHA256SUMS.txt` matched |
| Backend startup | PASS | Uvicorn started on an ephemeral loopback port |
| Health endpoint | PASS | `/health` returned process, version, and database status |
| Alembic forward migration | PASS | `0001_m0` created and seeded `system_metadata` |
| Alembic reverse migration | PASS | Downgrade to `base` removed the bootstrap table |
| CLI smoke | PASS | Version, health, migration, and OpenAPI commands tested |
| Python lint | PASS | `ruff check .` |
| Python type checking | PASS | Strict mypy; 12 source files |
| Python tests | PASS | 12 passed; 94.05% branch-aware coverage |
| Architecture guardrails | PASS | Repository layout and Domain import boundary tested |
| OpenAPI synchronization | PASS | Deterministic committed schema matched the backend |
| Dependency lock replay | PASS | `pnpm install --frozen-lockfile` |
| Frontend lint | PASS | ESLint with zero warnings |
| Frontend type checking | PASS | TypeScript project build check |
| Frontend production build | PASS | Vite built 29 modules |
| Tauri placeholder | PASS | Minimal Rust entrypoint, CSP, capabilities, and config present |
| Tauri native compilation | SKIP | Rust/Cargo is not installed locally; not an M0 hard gate |
| Hosted GitHub Actions run | SKIP | No remote repository or Actions runner was provided |

Skipped checks are not represented as passing integration results. The local commands executed by
the committed CI workflow all passed.

## Tool versions

- FastAPI 0.141.1
- Uvicorn 0.52.1
- Pydantic 2.13.4
- SQLAlchemy 2.0.51
- Alembic 1.19.1
- pytest 8.4.2
- ruff 0.16.2
- mypy 1.20.2
- TypeScript 5.9.2
- Vite 7.3.6

## Benchmark delta

Not applicable. Engineering benchmarks begin after their corresponding domain capabilities exist;
M0 establishes only the repository and verification foundation.

## Budget usage

Not applicable. M0 contains no AI provider, token accounting, external repository analysis, or
sandbox execution.
