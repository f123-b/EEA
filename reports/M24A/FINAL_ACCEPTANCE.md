# M24A Final Acceptance

Status: `READY_FOR_HUMAN_REVIEW` pending the matching green remote CI run and human review of the
draft PR.

## Acceptance matrix

| Gate | Evidence | Status |
|---|---|---|
| Requirement intake | Requirement API and strict request tests | PASS locally |
| Context assembly / authority | Bounded snapshot, untrusted source, current trusted memory | PASS locally |
| Structured EngineeringPlan | Plan/step/change/risk/assumption/unknown models | PASS locally |
| Impact / provenance / freshness | Impact endpoint, revision maps, stale propagation | PASS locally |
| CAS / audit / review | Approve, reject, revision request, comments and audit | PASS locally |
| Prompt injection / malformed output | Core/application safety tests | PASS locally |
| Cross-project isolation | Authenticated project-scoped route checks | PASS locally |
| No execution authority | Policy flags and `execution_authorized=false` | PASS locally |
| M22R/M23R regression | Full repository suite: 536 passed, 31 skipped, 82.53% coverage | PASS locally |
| Desktop / Tauri / Playwright | 9 desktop tests, 3 Tauri tests, 4 UI tests | PASS locally |
| Remote CI | Matching final head SHA | PENDING PUSH |

## Local verification commands

```text
pytest -q                         536 passed, 31 skipped, 82.53% coverage
ruff check ...                    PASS
mypy                              PASS (166 files)
eea db upgrade / alembic check    PASS through 0041
eea openapi export --check        PASS
eea openapi typescript --check    PASS
desktop lint/typecheck/test/build PASS (9 unit tests)
cargo check/test                  PASS (3 tests)
playwright @ui                    PASS (4 tests)
```

Remote evidence to be filled after push:

```text
CI_RUN_ID=
CI_HEAD_SHA=
```

## Required final state

```text
M24A=ACCEPTED
M24B=NOT_STARTED
M24C=NOT_STARTED
```

Approval of a plan is a review decision only. It never authorizes a source/configuration change,
build, test run, deployment, flash, or hardware action.
