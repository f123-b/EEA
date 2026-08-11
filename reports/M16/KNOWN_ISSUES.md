# M16 Known Issues and Explicit Boundaries

- ProtocolIR currently supports CAN Classic and CAN FD only. UART, SPI, I2C,
  Ethernet, transport sockets, and hardware bus execution are reserved for a
  later milestone.
- M16 fields are fixed-layout scalar fields. Multiplexing, variable-length
  payloads, container messages, floating-point wire formats, and runtime signal
  scheduling are not implemented.
- Generated C uses a standalone C11 codec and compile gate; it does not flash,
  open a socket, or communicate with hardware.
- Protocol validation is deterministic over the persisted ProtocolIR. It does
  not substitute hardware test evidence, commissioning evidence, or runtime
  traceability.
- M17 Test/Traceability/Review and M18 dependency invalidation are not part of
  this change. M19 FOC E2E, M21 Desktop UI, and Agent Runtime remain reserved.
- M16 does not add MotorControl concepts to Core and does not make the
  MotorControl plugin mandatory for ordinary projects.
- On this Windows host, the venv redirector can resolve `sys.executable` to the
  base interpreter when starting a sandbox child; that is an existing M5 test
  environment issue and is not an M16 runtime defect. The CI Linux gate and the
  base-interpreter full regression are the authoritative results.
