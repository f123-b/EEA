# M21 Known Issues

- The local Windows workstation has no `cargo`, so native Tauri compilation was delegated to the
  Linux CI packaging gate. This is an environment limitation, not a runtime fallback in release
  packages.
- M21 browser E2E uses an explicitly configured same-origin Vite proxy and test-only session token;
  production desktop sessions still come from the Tauri-managed loopback sidecar and IPC bootstrap.
- Physical hardware commissioning, flashing, and actuator operation remain outside M21. The UI
  exposes deterministic software/release evidence and preserves backend `UNKNOWN`, `STALE`, and
  hardware-blocked states.
- AI remains controlled and backend-authoritative. It cannot mutate compiler, pin, ERC, build, or
  review truth.
