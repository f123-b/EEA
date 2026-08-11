# M5R Sandbox Hardening Test Report

Date: 2026-08-11
Repository: `f123-b/EEA`
Commit under review: `007637fc4a7d0e398f6622262ab56036e08b4824`

## Root cause

The previous sandbox implementation expressed several limits as policy fields but did not
prove that the runtime enforced them. In particular, executable allowlisting could be
interpreted as a basename check, Windows process containment was attached after process start,
and output capture could not establish a bounded streaming boundary for both pipes.

## Implementation

- Added explicit runtime capability and execution-trust contracts.
- Canonicalized both requested executables and allowlist entries; non-absolute allowlist entries
  are ignored and basename spoofing is rejected.
- Added Windows Job Object limits for process count, process/job memory, and kill-on-close.
  Windows commands are created suspended, assigned to the Job Object, and resumed only after
  successful assignment.
- Added bounded concurrent stdout/stderr readers that terminate the job on overflow.
- Required every capability needed by a command; unsupported network isolation, filesystem
  isolation, strong isolation, or resource containment fails closed with
  `CAPABILITY_UNAVAILABLE`.
- `UNTRUSTED_CODE` cannot be downgraded to the trusted-tool runtime.

## Verification

Command:

```text
python -m pytest tests/test_m5_sandbox.py -q --no-cov
```

Result: **7 passed, 1 skipped**. The skipped case is the pre-existing symlink test when the
host cannot create symlinks. The timeout/process-tree, output-limit, canonical-path, network
fail-closed, archive traversal, and untrusted-execution cases passed.

Acceptance: **M5R = ACCEPTED** for the implemented local gate.
