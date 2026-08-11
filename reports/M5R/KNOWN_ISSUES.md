# M5R Known Issues

- This Windows host does not provide network isolation, filesystem isolation, or strong
  isolation through the current adapter. The adapter reports those capabilities as unavailable
  and refuses requests that require them; it does not silently execute with weaker guarantees.
- Consequently, `UNTRUSTED_CODE` is intentionally unavailable on this host. Trusted-tool
  commands with network disabled also fail closed before spawn because network isolation cannot
  be proven.
- Hosted CI evidence was not produced in this local run. The local Windows runtime test and the
  full repository regression are green.
