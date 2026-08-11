# M6 Known Issues

No critical issue is open for the policy-level M6 foundation.

| Severity | Item | Impact / next action |
|---|---|---|
| Low | Live LiteLLM/provider execution was not run | Run an explicitly authorized provider smoke test before relying on external model behavior. |
| Low | Requirement profile registration is currently application/API seeded for the built-in benchmark | Add admin-managed profile lifecycle and approval audit in a later profile-management milestone. |
| Low | Native Tauri build is not exercised | Install Rust/Cargo and run desktop-native checks before M21 packaging. |
| Info | Hardware commissioning is not part of M6 | Keep Flash and actuator-enable gates separate in later commissioning milestones. |
