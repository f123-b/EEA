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

M19A is **ACCEPTED_AND_MERGED** with P0/P1 both zero. The final PR head was
`e9b947e1d21202ea568c65af49a866f4961c6cc1`; merge commit/main HEAD is
`7573e1f3525c54cd5fb1155f634b77034d74b255`; acceptance CI was `32038057014` and post-merge
main CI was `32038973317`, green for backend, desktop-web, desktop-tauri, and m19-release.
No M19R/M19R.1/M19R.2 work was created. M20 proceeds on its separate branch; only a separately
authorized hardware commissioning phase may address M19B.
