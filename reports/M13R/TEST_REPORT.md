# M13R Deterministic Static Analysis Test Report

Date: 2026-08-11
Repository: `f123-b/EEA`
Commit under review: `007637fc4a7d0e398f6622262ab56036e08b4824`

## Root cause

The C/C++ RELEASE_GATE rules used regular expressions and a hand-written brace scanner as the
authoritative source parser. Comments, strings, nested scopes, malformed input, and brace-like
text could therefore produce non-deterministic or incorrect findings. Cppcheck output was also
not validated as a complete XML result before being treated as clean.

## Implementation

- Added the provider-neutral `CppSourceAnalyzer` port and a Tree-sitter C/C++ adapter.
- APP_DIRECT_HAL_CALL and ISR_BLOCKING_API now consume parsed AST calls and function bodies;
  parse errors produce `UNKNOWN`, never `PASS`.
- Cppcheck output now requires a complete version-2 XML result document with an errors container;
  malformed, truncated, schema-incomplete, execution-error, and unavailable results are
  `UNKNOWN`.
- Bumped the analysis ruleset identity to `m13.2` so prior regex-based results are not reused.

## Verification

Command:

```text
python -m pytest tests/test_m13_static_analysis.py -q --no-cov
```

Result: **10 passed**. The suite covers comments/strings, nested braces, driver exclusion,
C++ ISR syntax, malformed source fail-closed behavior, clean Cppcheck XML, diagnostic XML, and
malformed/truncated XML.

Acceptance: **M13R = ACCEPTED** for the implemented local gate.
