# M20 Known Issues

- The local Windows workstation has no `arm-none-eabi-gcc` or `kicad-cli`; these checks are
  delegated to the dedicated GitHub `m20-release` job. The release job passed the real DEVICE
  build, ELF validation, Cppcheck/Firmware Rules, and executed KiCad ERC.
- No physical STM32G431 board or probe is connected. M20 is software/release verification only;
  hardware commissioning is out of scope and remains blocked.
- No P0/P1 release findings were reported. Any later P2/P3 documentation or fixture cleanup is
  backlog only; UNKNOWN or FAIL in a required release gate is not accepted as a pass.
