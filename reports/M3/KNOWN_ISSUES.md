# M3 Known Issues

No critical or high-severity issue is open for M3 acceptance.

| Severity | Item | Impact / next action |
|---|---|---|
| Low | Real LiteLLM-provider integration is not exercised | Install `.[ai,dev]` and provide a non-production provider configuration when validating M2 adapters in a connected environment. |
| Low | Native OS keyring integration is not exercised | Validate against the target operating system's keyring before production secret handling. |
| Low | Native Tauri build is not exercised | Install Rust/Cargo and run the desktop-native checks before M21 packaging. |
| Low | Starlette/httpx deprecation warning | Track the upstream dependency migration; it does not affect current assertions. |
| Info | GitHub Actions has not run for this push yet | Confirm remote CI after the branch is published. |
