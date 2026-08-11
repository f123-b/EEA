# M14 Domain Extension Infrastructure Test Report

Date: 2026-08-11  
Repository: `f123-b/EEA`  
HEAD under review: `cccdd74ee4a86818c0c2e948997460fea9ad638c`

## Scope

M14 implements the Core-neutral Domain Extension Infrastructure defined by the Architecture
Freeze. It does not implement a concrete control-domain plugin and does not start M15.

## Implementation

- Added Core contracts for `DomainDescriptor`, `DomainIRRef`, opaque `DomainIREnvelope`, durable
  `DomainActivation`, rule/generator/context/UI contributions, and composition plans.
- Added a framework-neutral Domain plugin port.
- Added deterministic `DomainExtensionRegistry` and project-scoped activation service with:
  dependency closure, declared conflict detection, capability routing by explicit selection then
  priority, domain/generator DAG ordering, rule phase ordering, and additive-only safety rules.
- Added metadata-only UI extensions; remote/javascript routes are rejected.
- Bundled plugins are the only currently loadable trust tier. Signed/community plugins fail closed
  until signature verification or an isolated runtime is available.
- Added project activation API routes, SQL persistence, migration `0018_m14_domain_extensions`,
  error-catalog migration `0019_m14_domain_error_catalog`, OpenAPI/TypeScript synchronization,
  and the reserved `plugins/builtin/` location.

## Verification

Focused command:

```text
python -m pytest tests/test_m14_domain_extensions.py -q --no-cov
```

Result: **8 passed**.

Coverage includes empty Domain project creation, opaque IR registration, dependency resolution,
capability routing, conflict detection, dependency/generator cycles, remote UI rejection,
non-bundled trust fail-closed behavior, activation/deactivation dependency protection, API
routes, and persistence migration.

Acceptance: **M14 = ACCEPTED** for the implemented local gate.
