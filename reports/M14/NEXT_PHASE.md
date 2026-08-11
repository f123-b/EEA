# M15 Next Phase: First Built-in Domain Plugin

M14/M14R infrastructure is accepted by the automated repository gate. The next frozen phase is the
first concrete built-in Domain plugin under `plugins/builtin/`, using the M14 descriptor, schema,
rule, generator, context, UI metadata, and activation contracts.

M14R remote evidence: CI Run `31490343829`, backend and desktop GREEN. This report records
`READY_FOR_M15 = YES` but does not begin M15; M15 requires its own inspect-and-plan step.

M15 must preserve the M14 invariants: Core remains domain-neutral, ordinary projects may keep zero
active Domains, plugin-owned IR is referenced through opaque envelopes, and plugin rules may only
add safety constraints. The M15 scope must be separately inspected and planned before code changes.
