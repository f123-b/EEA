# M21 Known Issues

- The local Windows workstation has no `cargo`, so native Tauri compilation was delegated to the
  Linux CI packaging gate. This is an environment limitation; final `desktop-tauri` and
  `desktop-package-smoke` both passed, and release packages have no runtime fallback.
- M21 browser E2E uses an explicitly configured same-origin Vite proxy and test-only session token;
  production desktop sessions still come from the Tauri-managed loopback sidecar and IPC bootstrap.
- Physical hardware commissioning, flashing, and actuator operation remain outside M21. The UI
  exposes deterministic software/release evidence and preserves backend `UNKNOWN`, `STALE`, and
  hardware-blocked states.
- AI remains controlled and backend-authoritative. It cannot mutate compiler, pin, ERC, build, or
  review truth.
- The release size report intentionally has no prior-release baseline in this branch, so it emits
  a manual growth-review warning. This is a release-process follow-up, not a packaging failure;
  the artifact validation and secret scan both pass.
- The uploaded Windows NSIS installer is produced and hash-validated in CI. Runtime launch smoke
  is executed on the Linux AppImage in the available CI environment; Windows runtime smoke remains
  outside this gate.

There are no open P0/P1 issues for the M21 P1-1, P1-2, or P1-3 final gates. The remaining items are
scope boundaries or local-environment limitations and do not block final human review.
