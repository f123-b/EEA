# M0 Known Issues

| Severity | Issue | Impact | Workaround | Planned milestone |
|---|---|---|---|---|
| LOW | Rust/Cargo is absent from the local workstation | The native Tauri shell was not compiled locally | Install Rust stable and use `pnpm --filter @eea/desktop tauri build` | Before M21 Desktop UI Vertical Slice |
| LOW | The current third-party FastAPI test client emits a Starlette deprecation warning about its HTTP transport | Tests pass; production API behavior is unaffected | Track the FastAPI/Starlette-supported test transport and update the test dependency together | M1 dependency refresh |
| INFO | GitHub Actions has not run because no remote repository was supplied | Hosted runner behavior is not yet independently evidenced | Push the existing `main` branch to a remote; the workflow is already committed | First remote integration |

There are no known P0, critical, or high-severity M0 issues.
