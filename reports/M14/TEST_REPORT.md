# M14 / M14R Domain Extension Infrastructure Test Report

Date: 2026-08-11
Repository: `f123-b/EEA`
Exact base SHA: `74671ff94366925851c85f42b04b98b5d20a7d06`
Implementation commit SHA: `ade9da3`
Documentation/report evidence commit: `360f5ec` (local evidence history)
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
- M14R added an independent POSIX process controller using real `RLIMIT_AS` address-space and
  `RLIMIT_NPROC` process-spawn boundaries where the current runtime can enforce them. Unsupported
  or privileged runtimes do not advertise the capability and fail closed.
- M14R made configuration omitted/empty/changed semantics explicit, validates plugin schemas and
  activation configuration fail closed, persists schema version/hash snapshots, and adds
  `DOMAIN_CONFIGURATION_INVALID` to the API and persisted error catalog.
- M14R reconciles every Domain in the resolved activation plan against the current Registry
  descriptor and persisted activation snapshot. Compatible plugin upgrades preserve configuration
  and increment revision; incompatible plugin/schema changes return `DOMAIN_INCOMPATIBLE` without
  writes, including for already-active dependencies.

## Verification

Focused commands:

```text
python -m pytest tests/test_m5_sandbox.py -q --no-cov
python -m pytest tests/test_m14_domain_extensions.py -q --no-cov
python -m pytest tests/test_project_scope_hardening.py -q --no-cov
```

Results: M5 **8 passed, 3 skipped** on Windows (POSIX-only enforcement tests are skipped on this
host); M14 **17 passed**; Project Scope **4 passed**. Ubuntu CI exercised the POSIX boundaries.

Full regression:

```text
python -m pytest
```

Result: **175 passed, 3 skipped**, coverage **84.27%** (80% gate passed).

Contracts and frontend:

- `eea openapi export --check`: **PASS**
- `eea openapi typescript --check`: **PASS**
- `pnpm lint`: **PASS**
- `pnpm typecheck`: **PASS**
- `pnpm build`: **PASS**
- `ruff check .`: **PASS**
- `ruff format --check .`: **PASS**
- `mypy`: **PASS**
- Clean database `python -m eea_cli db upgrade` + `alembic check`: **PASS**
- Current local `.eea/eea.db` retains historical constraint/type drift; it is not the clean CI
  acceptance database and was not rewritten by this scoped correction.

Remote acceptance head SHA: `c707b8d751424daeee2c9d44d5555cfa8892be6c`
Remote CI Run ID: `31490663178`

Remote CI result: **GREEN** — backend `178 passed`, coverage `83.84%`, OpenAPI and TypeScript
contract checks passed; desktop lint, typecheck, and build passed.

Human acceptance state: **NOT FABRICATED; separate manual review may apply**

Final state: **ACCEPTED**

M14R: **ACCEPTED**
READY_FOR_M15: **YES**
