# M18E Renderer / NFR Hardening — Test Report

## Implementation identity

- Repository: `f123-b/EEA`
- Branch: `codex/m18e-renderer-nfr-hardening`
- Base main / M18D merge commit: `2fc9c9dbd7cdf9cf344899372f1357dbd6d07940`
- M18D reviewed implementation HEAD: `7dd86a3080b253010cf18f64accee3e2ca665a28`
- M18DR implementation commit: `6afeec383f767634ea45b8453fb7490d45f66ebe`
- M18E migration: `0031_m18e_renderer_nfr_hardening`
- Migration parent: `0030_m18d_hardware_commissioning_safety`

## M18ER Final Reliability Closure

- Reviewed implementation baseline: `1ccd549aa209af70688ff161af3c8ab8565c8c06`
- Final implementation HEAD: `fc1ef80998530a8ba3f21ed6e71c171811796eae`
- Implementation commits: `78c4b1c3f177d66fd07e145f56c7af2a9dd3bc2b`,
  `3148b7e65560df2d10709055f513cc55ebe51e91`,
  `fc1ef80998530a8ba3f21ed6e71c171811796eae`
- New migration: `0032_m18er_reliability_closure` (parent `0031_m18e_renderer_nfr_hardening`)
- PR: `#12`, still `OPEN` and `Draft`, base `main`

### Closure design

1. Production and default non-dev backend sessions require a random per-app bearer token;
   anonymous access is available only with explicit `insecure_local_dev=true`. The Desktop
   client validates HTTP loopback URLs, keeps the launch token in closure state, rejects token
   query/fragment paths, and never writes the token to browser storage, DOM, logs, or telemetry.
   External links use the official Tauri opener plugin and the WebView remains isolated.
2. Backup preflight bounds archive/member/manifest/total/path/count/compression limits and
   rejects traversal, absolute/drive paths, duplicates, special members, missing/duplicate
   manifests, and undeclared members. Export and restore use bounded chunks, incremental
   SHA-256, staging, fsync, cleanup, and atomic activation; the API selects the configured
   `foc-dev` CapacityProfile instead of using an unbounded default.
3. `BackupSecretPolicy` recursively rejects secret-shaped nested keys and values before
   canonical serialization, with deterministic errors that do not echo secret material.
4. Project backup is explicitly project-authoritative (`ProjectRecord`, source revision/workspace,
   artifacts and references), while runtime/session state and secrets are excluded. API restore
   validates authority/schema/migration compatibility, restores the record set in one SQL
   transaction, rejects collisions/overwrite, reconstructs source workspace binding, and reports
   only after atomic `VALIDATE -> STAGE -> ACTIVATE` completion.
5. CI now has separate `desktop-web` and `desktop-tauri` jobs. The latter installs Linux Tauri
   dependencies, generates the checked-in icon set, runs `cargo check`, `cargo test`, and the
   real `tauri build --ci` command.

### M18ER verification

- Focused M18E/M18ER/migration suite: **35 passed**.
- Cross-milestone M18/M18R/M18A/M18AR/M18AR.1/M18B/M18BR/M18C/M18CR/M18D/M18E suite:
  **193 passed, 1 skipped**.
- Local full pytest: **469 passed, 4 skipped**; the two existing M5 Windows sandbox failures
  remain environment-specific and non-blocking.
- Coverage: **84.28%** (threshold 80%).
- Ruff check: PASS; Ruff format: PASS; mypy: PASS.
- Clean Alembic upgrade through `0032_m18er_reliability_closure`: PASS; `alembic check`: PASS.
- OpenAPI export/check: PASS; TypeScript contract export/check: PASS.
- Desktop lint/typecheck/build: PASS.
- Local Rust commands were unavailable because cargo is not installed on Windows; no local Rust
  PASS is claimed. GitHub executed the authoritative Rust/Tauri gates successfully.
- Push CI `31946613210`: backend PASS, desktop-web PASS, desktop-tauri PASS.
- Draft PR CI `31946616696`: backend PASS, desktop-web PASS, desktop-tauri PASS.

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

GitHub CI:

- Push run `31941880496`: backend PASS, desktop PASS.
- Draft PR run `31941895651`: backend PASS, desktop PASS.
- Final acceptance-docs push run `31942245070`: backend PASS, desktop PASS.
- Final acceptance-docs PR run `31942247586`: backend PASS, desktop PASS.

## State

```text
M18D = ACCEPTED_AND_MERGED
M18DR = ACCEPTED_AND_MERGED
M18E = IMPLEMENTED
READY_FOR_M18E_FINAL_REVIEW = YES
M19 = NOT_STARTED
```
