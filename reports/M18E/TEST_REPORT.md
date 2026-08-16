# M18E Renderer / NFR Hardening — Test Report

## Implementation identity

- Repository: `f123-b/EEA`
- Branch: `codex/m18e-renderer-nfr-hardening`
- Base main / M18D merge commit: `2fc9c9dbd7cdf9cf344899372f1357dbd6d07940`
- M18D reviewed implementation HEAD: `7dd86a3080b253010cf18f64accee3e2ca665a28`
- M18DR implementation commit: `6afeec383f767634ea45b8453fb7490d45f66ebe`
- M18E migration: `0031_m18e_renderer_nfr_hardening`
- Migration parent: `0030_m18d_hardware_commissioning_safety`

## Implemented contracts

### Renderer and desktop security

`RendererSecurityPolicy` validates loopback-only CSP sources, rejects remote JavaScript and
frames, and converts untrusted Markdown/HTML/SVG-like input into bounded plain text. Script,
event-handler, `javascript:`, `vbscript:`, `data:text/html`, iframe, object, and embed payloads
are not passed to an HTML execution sink. External links require HTTP(S) and an explicit host
allowlist and open in an isolated browser target; the main WebView is never navigated.

The desktop backend client keeps the ephemeral bearer credential in closure state, never in
localStorage, DOM, query strings, or logs. Backend middleware rejects non-loopback Origins;
missing and wrong bearer tokens are rejected, and production mode enables local auth by default.
The Tauri CSP permits only self plus loopback HTTP/WS connections, and the capability file
retains the minimal `core:default` allowlist without filesystem, shell, process, unrestricted
HTTP, environment, clipboard, or arbitrary-window permissions.

### Backup / Restore

`ProjectBackupManifest` records schema versions, project identity, export time, source revision
binding, object references, knowledge snapshot references, per-object SHA-256/size, and a final
manifest hash. Export enumerates authoritative records, excludes secret-shaped content, writes
to a bounded sibling temporary archive, verifies every member, and atomically activates it.

Restore validates actor/project authority, schema compatibility, manifest and object hashes,
archive member paths, required member presence, and optional migration dry-run before writing to
staging. Activation is atomic; collisions, path traversal, corruption, write failure, and
unsupported schema fail closed and clean staging. Existing project/source authority is not
silently overwritten.

### Reliability / NFR

The deterministic failure harness covers SQL commit, Outbox dispatch, Source object write,
Artifact object write, Sandbox execution, Desktop/backend connection, vector query, LLM request,
tool execution, and WebSocket replay. Baseline scenarios include process kill, DB lock, disk
full, object write failure, vector unavailable, LLM timeout/rate limit, missing tool, sandbox
crash, corrupt cache, network unavailable, lock-holder crash, and WebSocket disconnect/replay
failure. Backup disk/object failure leaves no success archive.

Capacity profiles are versioned and deterministic: `minimal`, `foc-dev`, `full`, and `ci`, with
bounded file/repository/document/page/job/vector/log/object/tool-runtime limits and fail-closed
boundary checks. `reports/M18E/PERFORMANCE_BASELINE.json` stores relative-tolerance baselines
for cold start, project open, search, API p50/p95, event propagation, pin validation, build
queue, large repository/document, context retrieval, and UI large-list metrics.

`ObservabilityContext` provides optional request/project/job/agent/tool/import/commissioning/
event/source-revision correlation fields. Recursive redaction removes bearer, authorization,
API-key, secret, password, token, cookie, environment, and private-key shaped values.

### Identity and canonical units

The migration and Core contracts add User, Organization, Membership, and ProjectRole foundation
records with `OWNER`, `MAINTAINER`, `ENGINEER`, and `VIEWER` roles. `LOCAL_SINGLE_USER` remains
stable and auditable as `local:single-user`; it is distinct from action-level PermissionToken
authority. Cross-unit regressions cover mV/V, mA/A, deg/rad, rpm/rad/s, rpm/s/rad/s², A/s/mA/s,
ms/s, C/K, and wrong-dimension rejection.

## Verification

Focused command:

```text
.venv/Scripts/python.exe -m pytest --no-cov -q tests/test_migrations.py tests/test_m18e_nfr.py tests/test_architecture.py
```

Result: **25 passed**.

Cross-milestone focused regression command covering M18/M18R/M18A/M18B/M18BR/M18C/M18CR/M18D/
M18E:

```text
.venv/Scripts/python.exe -m pytest --no-cov -q tests/test_m18_api.py tests/test_m18_dependency_graph.py tests/test_m18a_reliability.py tests/test_m18b_domain_composition.py tests/test_m18br_composition_authority.py tests/test_m18c_source_authority.py tests/test_m18cr_source_mutation_cas.py tests/test_m18d_hardware_commissioning.py tests/test_m18e_nfr.py tests/test_m18r_real_benchmarks.py
```

Result: **177 passed, 1 skipped**.

Local full verification:

- `.venv/Scripts/python.exe -m pytest -q`: **453 passed, 4 skipped**; two existing M5 sandbox
  tests fail only in the Windows sandbox environment.
- Coverage: **83.76%** (required threshold: 80%).
- The two M5 failures are classified `PRE-EXISTING / ENVIRONMENT-SPECIFIC / NON-BLOCKING`.

Quality gates:

- Ruff check: PASS
- Ruff format --check: PASS
- mypy: PASS
- Clean Alembic upgrade through `0031_m18e_renderer_nfr_hardening`: PASS
- Alembic check against the clean upgraded database: PASS
- OpenAPI export/check: PASS
- TypeScript contract export/check: PASS
- Desktop lint: PASS
- Desktop typecheck: PASS
- Desktop build: PASS
- Rust `cargo check` / `cargo test`: NOT RUN — `cargo` is not installed in this local
  environment; no PASS is claimed.

GitHub CI is pending the first M18E Draft PR push.

## State

```text
M18D = ACCEPTED_AND_MERGED
M18DR = ACCEPTED_AND_MERGED
M18E = IMPLEMENTED
READY_FOR_M18E_FINAL_REVIEW = YES
M19 = NOT_STARTED
```
