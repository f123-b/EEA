# M16 Next Phase: ProtocolIR

M15 is accepted for its frozen built-in MotorControl Domain Plugin scope. The next milestone is
M16 ProtocolIR under the existing Core/Domain/Plugin architecture.

M16 must continue to preserve these invariants:

- Core remains neutral and must not import `plugins.builtin.motor_control`.
- ProtocolIR and transport facts must use the existing Core IR and Domain composition contracts.
- MotorControl remains optional; ordinary projects may have zero active Domains.
- M19 real FOC E2E, hardware commissioning, and production loop enable remain future gates and
  must not be silently pulled into M16.

Status: `M15 = ACCEPTED`
Next phase: `M16 ProtocolIR`
M19 FOC E2E: `NOT_STARTED / RESERVED`
