# M5 Known Issues

No critical issue is open for the policy-level M5 foundation. External untrusted execution remains
blocked until the operating-system hardening items below are closed.

| Severity | Item | Impact / next action |
|---|---|---|
| Medium | Windows job-object, memory/process-count, and firewall-level network isolation are not wired | Add a hardened OS/container runner before enabling external repository, archive, or build profiles. |
| Low | Windows symlink creation is unavailable in this environment | Re-run the SafePath symlink test with developer mode or an elevated CI worker. |
| Low | Native Tauri build is not exercised | Install Rust/Cargo and run desktop-native checks before M21 packaging. |
| Low | Starlette/httpx deprecation warning | Track the upstream dependency migration; it does not affect current assertions. |
| Info | GitHub Actions has not run for the M5 push yet | Confirm remote CI after publication. |
