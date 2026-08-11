# M2 Known Issues

| Severity | Issue | Impact | Workaround | Planned milestone |
|---|---|---|---|---|
| LOW | Live LiteLLM/provider execution was not run because no user credential or billable target was supplied | Provider-independent behavior and Adapter translation pass, but a real network/provider response is not evidenced | Install `.[ai]`, configure a keyring reference, and run an explicitly authorized provider smoke test | M6 real-provider gate remains NOT_EVIDENCED |
| LOW | Native OS keyring integration was not run in the baseline environment | The keyring Adapter contract passes against a backend implementation, but Windows Credential Manager behavior is not locally evidenced | Install `.[ai]` and run a non-production credential set/get/delete smoke test | Before first local secret configuration UI |
| LOW | FastAPI's test-client compatibility layer emits a third-party Starlette transport deprecation warning | Tests and production endpoints pass; no runtime behavior is affected | Upgrade the supported test transport with FastAPI/Starlette as one dependency change | Dependency maintenance |
| LOW | Rust/Cargo is absent locally | Native Tauri compilation is not locally evidenced | Install Rust stable before desktop-native implementation | Before M21 |
| INFO | The original M2 stage report lacked hosted CI evidence | Hosted CI subsequently passed on current main; the original stage assessment remains historical | Keep the remote CI record aligned with the reviewed commit | Ongoing |

There are no known P0, critical, or high-severity M2 issues.
