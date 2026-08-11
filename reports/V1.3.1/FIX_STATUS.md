# V1.3.1 Incremental Fix Status

Assessment point: after M2 acceptance.

| Fix | Status | Current evidence / insertion point |
|---|---|---|
| FIX-01 Core / Domain boundary | DONE | Core contains no concrete MotorControl/FOC definition or plugin import; frozen docs and merged documentation now use DomainIRRef/DomainIREnvelope; named architecture invariants added |
| FIX-02 Canonical Unit | NOT_STARTED | Required as part of M3 before M7; no EngineeringValue implementation exists yet |
| FIX-03 SourceRevision / BuildInputSnapshot | NOT_STARTED | Required before M12; no build implementation exists yet |
| FIX-04 Domain Composition | NOT_STARTED | Required in M14 before M15; no plugin implementation exists yet |
| FIX-05 Durable Outbox ACK | NOT_STARTED | Required before the first critical event consumer; M0/M1 do not dispatch business events |
| FIX-06 Hardware three-layer fail-safe | NOT_STARTED | Required before commissioning gates; no hardware execution exists yet |
| FIX-07 FOC gate / adapter order | NOT_STARTED | Required at M19A/M19B; no FOC or hardware adapter exists yet |
| FIX-08 Job / Permission / API Error sync | DONE | Canonical values are synchronized across Core/Pydantic, SQL constraints, OpenAPI, generated TypeScript, and exhaustive frontend JobStatus handling; three named cross-surface invariants pass |
| FIX-09 CapabilityBroker / safe ports | NOT_STARTED | Required before raw hardware adapters; none exist yet |
| FIX-10 Consistency / invariants | PARTIAL | Architecture state is CANDIDATE; FIX-01 plus AI Provider SDK confinement and framework-free Port invariants exist; later invariants remain gated by their implementations |

No later fix is marked passing based on documentation, mocks, placeholders, or skipped integration.
