# M15 Next Phase: First Built-in Domain Plugin

M14/M14R infrastructure is locally verified. M14R is not remotely or human accepted yet; the next
frozen phase is the first concrete built-in Domain plugin under `plugins/builtin/`, using the M14
descriptor, schema, rule, generator, context, UI metadata, and activation contracts.

M15 may begin only after the M14R acceptance report has an exact final commit SHA, remote CI
evidence, and explicit human acceptance. Until then: `READY_FOR_M15 = NO`.

M15 must preserve the M14 invariants: Core remains domain-neutral, ordinary projects may keep zero
active Domains, plugin-owned IR is referenced through opaque envelopes, and plugin rules may only
add safety constraints. The M15 scope must be separately inspected and planned before code changes.
