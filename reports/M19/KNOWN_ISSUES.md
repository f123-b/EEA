# M19 Known Issues

## Environment-gated, fail-closed items

The following are not implementation successes and are intentionally not converted to PASS:

- The full local pytest run has the two pre-existing M5 Windows sandbox failures
  `test_structured_command_is_allowlisted_and_shell_free` and
  `test_structured_command_enforces_timeout_output_and_secret_boundaries`. They reproduce the
  Windows Job/sandbox capability issue, do not touch M19 code, and leave total coverage at
  84.25%.

- The current Windows runtime cannot prove the required network-isolated command boundary.
  The M12 Build endpoint therefore records `UNKNOWN` rather than accepting a 400 capability
  error or fabricating an artifact.
- `arm-none-eabi-gcc` is not installed locally, so no real STM32G431 ELF was produced in this
  workstation run.
- `kicad-cli` is not installed locally, so schematic/ERC remains tool-dependent UNKNOWN when
  requested without a real KiCad backend.
- No physical STM32G431/DRV8323/AS5047 fixture or authorized probe is connected. M19B is
  `BLOCKED_HARDWARE`; no flash or actuator-enable action was attempted.
- The built-in TestExecutionService is contract-only for this software benchmark. Its case
  shape checks can PASS, but the aggregate TestRun remains BLOCKED without an authorized
  behavioral verification authority.

## Backlog

- Run the same benchmark in the approved CI/build image with the ARM toolchain, KiCad CLI, and
  the required command-isolation capability, then attach the real compiler/toolchain version,
  input hash, SourceRevision, BuildInputSnapshot, ELF hash, duration, Cppcheck output, and ERC
  report.
- Complete M19B only with a commissioned real fixture under the existing M18D PermissionToken,
  ResourceLock, SafetyLimit, SafeState, Emergency Stop, and explicit permission contracts.
- Add an authorized behavioral TestExecution adapter before claiming a non-BLOCKED motor-control
  TestRun. This is a verification-authority extension, not permission to weaken the current
  fail-closed result.

No M19R, M19R.1, or M19R.2 was created.
