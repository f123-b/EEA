# M20 Known Issues

- The local Windows workstation has no `arm-none-eabi-gcc` or `kicad-cli`; real DEVICE build,
  ELF validation, Cppcheck release evidence, and KiCad ERC are intentionally delegated to the
  dedicated GitHub `m20-release` job.
- No physical STM32G431 board or probe is connected. M20 is software/release verification only;
  hardware commissioning is out of scope and remains blocked.
- Any P2/P3 documentation or fixture cleanup discovered by CI is backlog only. UNKNOWN or FAIL
  in a required release gate is not accepted as a pass.
