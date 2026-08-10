# M1 Known Issues

| Severity | Issue | Impact | Workaround | Planned milestone |
|---|---|---|---|---|
| LOW | Rust/Cargo is absent locally | Native Tauri compilation is not locally evidenced | Install Rust stable before desktop-native implementation | Before M21 |
| LOW | FastAPI's current test-client compatibility layer emits a third-party Starlette transport deprecation warning | Tests and production endpoints pass; no runtime behavior is affected | Upgrade the supported test transport with FastAPI/Starlette as one dependency change | M2 dependency review |
| INFO | Hosted GitHub Actions has not executed | Hosted runner behavior is not independently evidenced | Push `main` to a remote with Actions enabled | First remote integration |

There are no known P0, critical, or high-severity M1 issues.
