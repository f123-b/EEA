# M14 / M14R Domain Extension Infrastructure Test Report

Date: 2026-08-11
Repository: `f123-b/EEA`
Exact base SHA: `4b5346f695e89db81982def2ba56d1d07515c97b`
Exact final SHA: **NOT AVAILABLE — working tree is intentionally uncommitted**
Python: `3.12.13`
Node: `v24.14.0`
pnpm: `11.16.0`
Migration head: `0021_m14_domain_configuration_error_catalog`

## Scope

M14 implements the Core-neutral Domain Extension Infrastructure defined by the Architecture
Freeze. M14R hardens Repository Acceptance and Domain configuration semantics. No concrete control
domain plugin was implemented and M15 was not started.

## Implementation

- Added Core contracts for `DomainDescriptor`, `DomainIRRef`, opaque `DomainIREnvelope`, durable
  `DomainActivation`, rule/generator/context/UI contributions, and composition plans.
- Added a framework-neutral Domain plugin port and deterministic project-scoped activation service
  with dependency, capability, rule, generator, and additive-safety ordering.
- Added metadata-only UI extensions; remote/javascript routes are rejected.
- Bundled plugins are the only currently loadable trust tier. Signed/community plugins fail closed
  until signature verification or an isolated runtime is available.
- Added project activation API routes, SQL persistence, migrations `0018`/`0019`, OpenAPI/TypeScript
  synchronization, and the reserved `plugins/builtin/` location.
- M14R isolated Windows Job Object ctypes into a Windows-only lazy adapter while preserving
  process-tree/resource enforcement and fail-closed behavior.
- M14R made configuration omitted/empty/changed semantics explicit, validates plugin schemas and
  activation configuration fail closed, persists schema version/hash snapshots, and adds
  `DOMAIN_CONFIGURATION_INVALID` to the API and persisted error catalog.

## Verification

Focused commands:

```text
python -m pytest tests/test_m5_sandbox.py tests/test_m14_domain_extensions.py \
  tests/test_project_scope_hardening.py -q --no-cov
python -m pytest tests/test_m14_domain_extensions.py -q --no-cov
```

Results: **25 passed, 1 skipped** for the combined focused suite; **13 passed** for the M14
configuration-focused suite.

Full regression:

```text
python -m pytest
```

Result: **171 passed, 1 skipped**, coverage **84.92%** (80% gate passed).

Contracts and frontend:

- `eea openapi export --check`: **PASS**
- `eea openapi typescript --check`: **PASS**
- `pnpm lint`: **PASS**
- `pnpm typecheck`: **PASS**
- `pnpm build`: **PASS**
- `ruff check .`: **PASS**
- `ruff format --check .`: **PASS**
- `mypy`: **PASS**
- Clean database `eea db upgrade` + `alembic check`: **PASS**

Remote CI Run ID: **NOT RUN — no final commit was pushed**

Remote CI result: **PENDING**

Human acceptance state: **HUMAN_ACCEPTANCE_PENDING**

Final state: **LOCAL_VERIFIED**

M14R: **LOCAL_VERIFIED, not ACCEPTED**
