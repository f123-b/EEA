# M18E Renderer / NFR Hardening — Test Report

## Implementation identity

- Repository: `f123-b/EEA`
- Branch: `codex/m18e-renderer-nfr-hardening`
- Base main / M18D merge commit: `2fc9c9dbd7cdf9cf344899372f1357dbd6d07940`
- M18D reviewed implementation HEAD: `7dd86a3080b253010cf18f64accee3e2ca665a28`
- M18DR implementation commit: `6afeec383f767634ea45b8453fb7490d45f66ebe`
- M18E migration: `0031_m18e_renderer_nfr_hardening`
- Migration parent: `0030_m18d_hardware_commissioning_safety`

## M18ER.1 Runtime Auth & Atomic Restore Closure

- Previous M18ER implementation HEAD: `fc1ef80998530a8ba3f21ed6e71c171811796eae`
- Implementation HEAD: `21cde4d6398edc85fcb2ea57a5e1bdc44f989e20`
- Implementation commit: `21cde4d` — `fix(m18er1): close runtime auth and atomic project restore`
- New migration: `0033_m18er1_atomic_restore_runtime` (parent `0032_m18er_reliability_closure`)
- PR: `#12`, still `OPEN` and `Draft`, base `main`

### Closure design

1. Tauri creates an ephemeral 32-byte token and free loopback port, starts the configured
   `EEA_BACKEND_EXECUTABLE` child with host/port/token in child-scoped environment variables,
   waits for an authenticated `/api/v1/meta/version` handshake, and stores the session in managed
   state. The renderer obtains it only through `get_runtime_session`, passes it to the closure-based
   `createBackendClient`, and performs a real authenticated version request. Token values are not
   placed in argv, URLs, browser storage, DOM, console/log output, or telemetry.
2. `validate_archive()` now streams every declared object with bounded chunks and compares exact
   size plus incremental SHA-256 before returning `VALIDATED`; staging and activated-tree
   verification reuse the same bounded hash pipeline. Same-size tamper, truncated, and invalid
   archives fail closed as `BACKUP_INVALID`.
3. Restore uses a durable `restore_operations` journal and state machine:
   `STAGED -> PREPARED -> FS_ACTIVATED -> ACTIVATED`, with `ROLLBACK_REQUIRED`/`FAILED` for
   deterministic failure. The journal persists project/manifest identity, staging/destination,
   actor, source revision hash, metadata, error code, timestamps, and revision. Startup
   `RecoveryService` verifies the manifest/tree, completes activation/finalization, and is
   idempotent; project owner creation is inside final SQL finalization.
4. Source export includes real `source/<relative-path>` bytes, bounded by the existing capacity
   and `SafePath` rules. Restore recomputes `file_manifest` and `source_manifest_hash` before
   binding `SourceWorkspace.current_source_revision_id`; credential filenames/private-key files
   are excluded while ordinary source strings such as `token` remain valid. Portable artifacts
   include bytes and verified rewritten URIs; rebuildable artifacts are rewritten to
   `rebuild://...` and cannot remain `CURRENT`.

### M18ER.1 verification

- Focused M18E/M18ER.1/migration/runtime suite: **47 passed**.
- Local full pytest: **481 passed, 4 skipped**; the two existing M5 Windows sandbox failures
  remain environment-specific and non-blocking.
- Coverage: **84.00%** (threshold 80%).
- Ruff check: PASS; Ruff format: PASS; mypy: PASS.
- Clean Alembic upgrade through `0033_m18er1_atomic_restore_runtime`: PASS; `alembic check`: PASS.
- OpenAPI export/check: PASS; TypeScript contract export/check: PASS.
- Desktop lint/typecheck/build: PASS.
- Local Rust commands were unavailable because cargo is not installed on Windows; no local Rust
  PASS is claimed. GitHub executed the authoritative Rust/Tauri gates successfully.
- Push CI `31951639346`: backend PASS, desktop-web PASS, desktop-tauri PASS.
- Draft PR CI `31951640929`: backend PASS, desktop-web PASS, desktop-tauri PASS.

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
.venv/Scripts/python.exe -m pytest -q --no-cov tests/test_m18e_nfr.py tests/test_migrations.py tests/test_m18er1_restore_recovery.py tests/test_m18er1_runtime_auth.py
```

Result: **47 passed** for the M18E/M18ER.1/migration/runtime focused command.

Cross-milestone focused regression command covering M18/M18R/M18A/M18B/M18BR/M18C/M18CR/M18D/
M18E:

```text
.venv/Scripts/python.exe -m pytest --no-cov -q tests/test_m18_api.py tests/test_m18_dependency_graph.py tests/test_m18a_reliability.py tests/test_m18b_domain_composition.py tests/test_m18br_composition_authority.py tests/test_m18c_source_authority.py tests/test_m18cr_source_mutation_cas.py tests/test_m18d_hardware_commissioning.py tests/test_m18e_nfr.py tests/test_m18r_real_benchmarks.py
```

The cross-milestone suites are included in the full run below; no new cross-milestone failures
were observed.

Local full verification:

- `.venv/Scripts/python.exe -m pytest -q`: **481 passed, 4 skipped**; two existing M5 sandbox
  tests fail only in the Windows sandbox environment.
- Coverage: **84.00%** (required threshold: 80%).
- The two M5 failures are classified `PRE-EXISTING / ENVIRONMENT-SPECIFIC / NON-BLOCKING`.

Quality gates:

- Ruff check: PASS
- Ruff format --check: PASS
- mypy: PASS
- Clean Alembic upgrade through `0033_m18er1_atomic_restore_runtime`: PASS
- Alembic check against the clean upgraded database: PASS
- OpenAPI export/check: PASS
- TypeScript contract export/check: PASS
- Desktop lint: PASS
- Desktop typecheck: PASS
- Desktop build: PASS
- Rust `cargo check` / `cargo test`: NOT RUN locally — `cargo` is not installed on Windows;
  GitHub authoritative CI PASS.

GitHub CI:

- Push run `31951639346`: backend PASS, desktop-web PASS, desktop-tauri PASS.
- Draft PR run `31951640929`: backend PASS, desktop-web PASS, desktop-tauri PASS.

## State

```text
M18D = ACCEPTED_AND_MERGED
M18DR = ACCEPTED_AND_MERGED
M18E = IMPLEMENTED
M18ER = IMPLEMENTED
M18ER.1 = IMPLEMENTED
READY_FOR_M18E_FINAL_REVIEW = YES
M19 = NOT_STARTED
```
