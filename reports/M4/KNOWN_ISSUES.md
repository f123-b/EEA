# M4 Known Issues

No critical or high-severity issue is open for M4 acceptance.

| Severity | Item | Impact / next action |
|---|---|---|
| Medium | Live Docling runtime and vendor structured-data feeds are not installed | Run the adapter against approved datasheets/reference manuals and vendor STM32 data before production ingestion. |
| Low | Native OS keyring and real LiteLLM provider remain untested | These are optional M2 integration checks; validate in a connected deployment profile. |
| Low | Native Tauri build is not exercised | Install Rust/Cargo and run desktop-native checks before M21 packaging. |
| Low | Starlette/httpx deprecation warning | Track the upstream dependency migration; it does not affect current assertions. |
| Info | GitHub Actions has not run for the M4 push yet | Confirm remote CI after publication. |
