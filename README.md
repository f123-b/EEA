# Embedded Engineering Agent

EEA is an AI-assisted embedded engineering platform built around versioned intermediate
representations, evidence, deterministic rules, tool verification, and domain plugins.

This repository follows the V1.3 architecture-freeze documents in [`docs/`](docs/README.md).
Implementation advances one milestone at a time using the required sequence:
`Implement -> Test -> Review -> Acceptance -> Commit`.

## Current milestone

M0 Repository Skeleton is implemented:

- FastAPI backend with health and version endpoints;
- SQLAlchemy 2.x and Alembic migration foundation;
- `eea` CLI for serving, migrations, health, and OpenAPI export;
- React/TypeScript desktop shell with a Tauri placeholder;
- pytest, ruff, mypy, frontend checks, and CI;
- generated OpenAPI contract at [`schemas/openapi.json`](schemas/openapi.json).

No M1 domain behavior is included yet.

## Development

Requirements: Python 3.12+, Node.js LTS, pnpm, Git, and Rust stable when running Tauri.

```bash
python -m venv .venv
.venv/Scripts/activate
python -m pip install -e ".[dev]"
eea db upgrade
eea serve
```

In another terminal:

```bash
pnpm install --frozen-lockfile
pnpm --filter @eea/desktop dev
```

Quality checks:

```bash
ruff check .
mypy apps/backend/src apps/cli/src
pytest
pnpm lint
pnpm typecheck
pnpm build
eea openapi export --check
```

The API listens on loopback by default. Set `EEA_SESSION_TOKEN` to require a bearer token for
versioned API routes. The process-level `/health` endpoint remains available for sidecar liveness.
