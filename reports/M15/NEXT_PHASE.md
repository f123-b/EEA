# Next Phase: M16 ProtocolIR (Not Started)

M15R is limited to MotorControl Integration & Contract Closure. Its final repository gate is green
and `READY_FOR_M16 = YES` is recorded. M16 ProtocolIR is only the next declared phase; it is not
implemented by this change.

M16 must preserve these invariants:

- Core remains neutral and must not import `plugins.builtin.motor_control`.
- ProtocolIR and transport facts use the existing Core IR and Domain composition contracts.
- MotorControl remains optional; ordinary projects may have zero active Domains.
- M19 FOC E2E, M21 Desktop UI Vertical Slice, hardware commissioning, and production loop enable
  remain future gates and must not be pulled into M16.

Status: `M15R = ACCEPTED`
Next phase: `M16 ProtocolIR — NOT STARTED`
M19 FOC E2E: `NOT_STARTED / RESERVED`
M21 Desktop UI Vertical Slice: `NOT_STARTED / RESERVED`
