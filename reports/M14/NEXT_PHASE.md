# M15 Next Phase: First Built-in Domain Plugin

M14/M14R infrastructure is accepted by the automated repository gate. The next frozen phase is the
first concrete built-in Domain plugin under `plugins/builtin/`, using the M14 descriptor, schema,
rule, generator, context, UI metadata, and activation contracts.

M14R remote evidence: CI Run `31490343829`, backend and desktop GREEN. This report records
`READY_FOR_M15 = YES` but does not begin M15; M15 requires its own inspect-and-plan step.

M15 must preserve the M14 invariants: Core remains domain-neutral, ordinary projects may keep zero
active Domains, plugin-owned IR is referenced through opaque envelopes, and plugin rules may only
add safety constraints. This M15 scope was separately inspected and planned before code changes.

M15 implementation is recorded in `reports/M15/TEST_REPORT.md`; the implementation commit is
`e247a12`. The next frozen milestone after M15 is M16 ProtocolIR.
