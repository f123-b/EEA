# M13R Known Issues

- Cppcheck remains an optional external tool. When it is unavailable, blocked, exits with an
  execution error, or produces incomplete output, the result is intentionally `UNKNOWN` and is
  not release-gate passing.
- No unresolved deterministic-analysis defect was found in the focused or full local tests.
