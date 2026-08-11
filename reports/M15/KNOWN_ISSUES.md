# M15R Known Issues and Explicit Boundaries

- `CURRENT_LOOP_TIMING_BUDGET` returns `UNKNOWN` when runtime execution-budget evidence is absent;
  static frequency/period arithmetic still fails closed on invalid values.
- `ELECTRICAL_ANGLE_DIRECTION_CONSISTENT` returns `UNKNOWN` until a canonical phase-map evidence
  contract exists; explicit sign fields are required but do not pretend to prove runtime polarity.
- `STARTUP_ALIGNMENT_REQUIRED` returns `UNKNOWN` when no startup/calibration test result is supplied.
  A declared `PASS` is accepted only as an input result; M15 does not execute hardware calibration.
- A Domain Validate request without `domain_ir` is `BLOCKED`; without a project-scoped current
  `mcu_config_id` the MCUConfig cross-validation remains `UNKNOWN`.
- M19 FOC Minimal E2E, real firmware generation, protocol/test/review chain, and hardware
  commissioning are not implemented and are not accepted by M15R.
- M21 Desktop UI Vertical Slice is not implemented; M15 provides metadata-only dynamic UI
  contributions and an API contract, not a completed desktop screen.
- HardwareCommissioningService, SafeState/E-Stop runtime, flash orchestration, and actuator-enable
  permission paths remain reserved for their later frozen milestones.
- Signed-trusted and community-untrusted plugins remain fail-closed under the M14 policy; M15R only
  executes the bundled in-process plugin.
- No M15R database migration was added. The existing historical `.eea/eea.db` drift remains an M14
  repository issue and is not rewritten by this change.
