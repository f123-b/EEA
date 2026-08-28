# M23L CI Evidence

Each landing PR has its own final-head CI requirement. The integrated PR #15
run is not used as a substitute.

| Unit | PR | Branch | Final-head CI |
|---|---:|---|---|
| M21 | #16 | `landing/m21-desktop-workbench` | run `32980213780`, head `d345b833f1d7db9879399724071b601a7a399b0a`, **PASS** |
| M22/M22R | #17 | `landing/m22r-existing-project-import` | run `33139849241`, head `a09cd1ab9e4279dfa3c17bb391b643840df214c2`, **PASS** |
| M23/M23R | #18 | `landing/m23r-knowledge-memory-trust` | PR run `33140975697` and push run `33140973434`, head `0766ae14c2f3debc17b4c4d9959eb72a29be9153`, **PASS** |

The CI contract covers backend tests, desktop web, Tauri, UI tests, package
smoke, release artifacts, and milestone release jobs. Final CI evidence must
always satisfy:

```text
CI_HEAD == PR_HEAD
```

The final synchronized PR #18 head is `0766ae14c2f3debc17b4c4d9959eb72a29be9153`.
The final handoff records the concrete run IDs and SHA values after GitHub has
completed the checks. A failed or stale head is not accepted as a landing
gate. Node.js 20 deprecation annotations are non-blocking warnings; all jobs
completed successfully.
