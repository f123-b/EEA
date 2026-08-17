# M19 Known Issues

## Environment and hardware boundaries

The following are not implementation successes and are intentionally not converted to PASS:

- The local full pytest run retains the two pre-existing M5 Windows sandbox failures
  `test_structured_command_is_allowlisted_and_shell_free` and
  `test_structured_command_enforces_timeout_output_and_secret_boundaries`. They reproduce the
  Windows Job/sandbox capability issue and do not touch M19; the authoritative backend CI is
  green.

- The local workstation does not have `arm-none-eabi-gcc` or `kicad-cli`. Local Build/ERC checks
  therefore remain UNKNOWN when those tools are requested; the dedicated GitHub release job
  supplied the real ARM ELF and KiCad ERC evidence.
- No physical STM32G431/DRV8323/AS5047 fixture or authorized probe is connected. M19B is
  `BLOCKED_HARDWARE`; no flash or actuator-enable action was attempted.
- The ordinary built-in requirement executor remains contract-only. M19 release verification
  uses the explicit controlled server-fact executor and completed PASS; this does not claim a
  physical motor run or actuator behavior.

## Scope boundary

M19A is **ACCEPTED** with P0/P1 both zero and is approved to merge. The final PR head before
the acceptance-docs commit was `f8d3352100ef54a37d771e4625f3a2c30cc9a5cd`; PR CI
`32021782056` and push CI `32021777129` were green for backend, desktop-web, desktop-tauri,
and m19-release. No M19R/M19R.1/M19R.2 work was created. M20 and M21 remain `NOT_STARTED` at
this M19 report checkpoint; only a separately authorized hardware commissioning phase may
address M19B.
