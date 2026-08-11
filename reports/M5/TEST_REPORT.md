# M5 Test Report — Sandbox Foundation

**Assessment date:** 2026-08-11

**Baseline:** EEA V1.3.1 candidate

**Implementation version:** `1.3.1.dev5`

**Result:** PASS — policy-level sandbox foundation

## Delivered scope

- `SafePath` and `SandboxWorkspace` path boundaries with absolute, UNC, drive, traversal, and
  resolved-symlink escape rejection.
- ZIP/TAR materialization that rejects traversal, symlink/hardlink, special-file, duplicate, and
  archive-bomb members before unsafe writes.
- Frozen `SandboxPolicy`, structured `CommandSpec`, and `CommandResult` contracts.
- Shell-free, allowlisted command adapter with sanitized environment, secret-argument rejection,
  default network denial, timeout/output budgets, and structured resource errors.
- Error catalog migration `0006_m5` and synchronized OpenAPI/TypeScript error values.

## Acceptance evidence

| Check | Result |
|---|---|
| Ruff lint and format checks | PASS |
| Mypy | PASS — 46 source files |
| Pytest | PASS — 71 passed, 1 environment skip |
| Branch-aware Python coverage | PASS — 88.87% total |
| SafePath | PASS — traversal, absolute/UNC/drive paths, and resolved symlink escape cases |
| ZIP extraction | PASS — traversal and symlink members rejected; no outside file created |
| TAR extraction | PASS — symlink and special-file members rejected |
| Archive budgets | PASS — member size, total size, member count, and compression ratio guards |
| Structured command boundary | PASS — shell-free argv and executable allowlist |
| Secret protection | PASS — disallowed environment keys and secret-like argv values rejected |
| Runtime/output budgets | PASS — timeout and output overage become `RESOURCE_LIMIT_EXCEEDED` |
| Network policy | PASS — commands declaring network access are denied by default |
| Migration | PASS — fresh upgrade, `alembic check`, error-constraint validation, downgrade to base |
| API contracts | PASS — OpenAPI and generated TypeScript exports are current |
| Desktop validation | PASS — frozen install, lint, typecheck, and production build |

## Environment and intentional limits

- Python 3.12.13, pytest 8.4.2, ruff 0.16.2, mypy 1.20.2.
- Node 24.14.0 and pnpm 11.16.0.
- One SafePath symlink test is skipped because this Windows environment denies symlink creation;
  archive symlink entries are still tested through ZIP/TAR fixtures.
- Native OS job-object/cgroup hardening and firewall-level network isolation are not available in
  this standard-library environment. The default policy has an empty executable allowlist, so raw
  external repository/archive/build commands remain blocked; production hardening is required
  before enabling untrusted command profiles.
- The test suite emits the known Starlette/httpx deprecation warning only.
