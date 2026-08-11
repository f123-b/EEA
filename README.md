# Embedded Engineering Agent

EEA is an AI-assisted embedded engineering platform built around versioned intermediate
representations, evidence, deterministic rules, tool verification, and domain plugins.

This repository follows the V1.3 architecture-freeze documents in [`docs/`](docs/README.md).
Implementation advances one milestone at a time using the required sequence:
`Implement -> Test -> Review -> Acceptance -> Commit`.

## Current milestone

M3 EngineeringValue + Claim Core is implemented on the accepted M2 AI Provider Foundation
(implementation version `1.3.1.dev3`):

- FastAPI backend with health and version endpoints;
- SQLAlchemy 2.x and Alembic migration foundation;
- `eea` CLI for serving, migrations, health, and OpenAPI export;
- React/TypeScript desktop shell with a Tauri placeholder;
- pytest, ruff, mypy, frontend checks, and CI;
- generated OpenAPI contract at [`schemas/openapi.json`](schemas/openapi.json).
- framework-independent Project, Artifact, Evidence, Issue, Decision, Job, Permission, and
  Traceability entities;
- Project lifecycle API with ETag/If-Match optimistic concurrency and soft deletion;
- schema registry plus synchronized Python/OpenAPI/TypeScript Core enums;
- V1.3.1 corrected JobStatus, Permission, and engineering error catalogs.
- provider-neutral `AIProvider` and `SecretService` ports;
- LiteLLM and OS keyring adapters behind optional `ai` dependencies;
- versioned Prompt Registry and durable usage accounting;
- `StructuredGenerationService` with exact output-schema checks, Pydantic validation, timeout,
  token/cost budget gates, and secret-input rejection;
- Alembic `0003_m2` migration for prompt definitions and AI usage records.
- Canonical-unit EngineeringValue normalization across the frozen engineering-dimension catalog;
- Engineering claims, predicate definitions, applicability-aware resolution, and durable conflict
  records;
- evidence-gated `DOCUMENT_VERIFIED` claims and source-priority / source-version conflict
  resolution;
- Alembic `0004_m3_claim_core` migration plus synchronized Core/OpenAPI/TypeScript claim enums.

## Development

Requirements: Python 3.12+, Node.js LTS, pnpm, Git, and Rust stable when running Tauri.

```bash
python -m venv .venv
.venv/Scripts/activate
python -m pip install -e ".[dev]"
eea db upgrade
eea serve
```

Install real AI/keyring adapters only when required:

```bash
python -m pip install -e ".[ai,dev]"
```

In another terminal:

```bash
pnpm install --frozen-lockfile
pnpm --filter @eea/desktop dev
```

Quality checks:

```bash
ruff check core/src ports/src application/src adapters/src apps/backend/src apps/cli/src migrations tests
mypy
pytest
pnpm lint
pnpm typecheck
pnpm build
eea openapi export --check
eea openapi typescript --check
```

The API listens on loopback by default. Set `EEA_SESSION_TOKEN` to require a bearer token for
versioned API routes. The process-level `/health` endpoint remains available for sidecar liveness.
