# M23L CI Evidence

Each landing PR has its own final-head CI requirement. The integrated PR #15
run is not used as a substitute.

| Unit | PR | Branch | Final-head CI |
|---|---:|---|---|
| M21 | #16 | `landing/m21-desktop-workbench` | required and passed; run/head recorded in final handoff |
| M22/M22R | #17 | `landing/m22r-existing-project-import` | required; one Ruff-only repair was pushed before final run |
| M23/M23R | #18 | `landing/m23r-knowledge-memory-trust` | required after final landing-doc head |

The CI contract covers backend tests, desktop web, Tauri, UI tests, package
smoke, release artifacts, and milestone release jobs. Final CI evidence must
always satisfy:

```text
CI_HEAD == PR_HEAD
```

The final handoff records the concrete run IDs and SHA values after GitHub has
completed the checks. A failed or stale head is not accepted as a landing
gate.
