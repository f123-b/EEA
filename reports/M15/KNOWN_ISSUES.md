# M15 Known Issues

- The plugin currently provides declarative generator/rule contracts and pure MCUConfigIR
  cross-validation. It does not claim to perform real firmware generation, hardware execution, or
  commissioning.
- The complete FOC minimal E2E (real build, static-analysis release gate, protocol/test/review
  chain) remains the separately frozen M19 gate and is not marked PASS here.
- The complete HardwareCommissioningService, SafeState/E-Stop runtime, flash orchestration, and
  actuator-enable permission path remain reserved for the later commissioning milestones.
- Signed-trusted and community-untrusted plugins remain fail-closed under the M14 policy; M15 only
  adds the bundled in-process plugin permitted by the V1.3 SDK.
- The repository's historical local `.eea/eea.db` drift remains documented by M14; M15 adds no
  migration and does not rewrite that database.
