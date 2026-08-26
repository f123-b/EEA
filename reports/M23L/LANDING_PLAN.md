# M23L Landing Plan

## Sequential landing order

```text
main/M20
  -> PR #16: M21 desktop workbench
  -> PR #17: M22 + M22R existing-project import
  -> PR #18: M23 + M23R trusted engineering memory
```

PR #17 is stacked on PR #16. PR #18 is stacked on PR #17. Each branch is
independently buildable and is validated at its own head before any human
landing action.

## Migration strategy

The integrated branch historically interleaved M23 and M22R migrations:
`0035` (M23), `0036` (M22R), and `0037` (M23R). Those files are not copied into
the landing branches. The sequential landing chain uses additive revisions:

```text
0034_m22_existing_project_import
  -> 0038_m23l_m22r_import_candidates
  -> 0039_m23l_knowledge_memory
  -> 0040_m23l_m23r_memory_trust_closure
```

This avoids editing or renumbering historical migrations while allowing a
clean database upgrade and downgrade path in the landing order.

## Scope rules

- M21 contains only the desktop workbench and its release/runtime gates.
- M22/M22R contains import materialization, parsers, candidate review/apply,
  source revision/rescan, dependency impact, and native picker behavior.
- M23/M23R contains Knowledge & Memory and its complete trust/security closure.
- No vector database, agent planning, autonomous execution, or M24 work is
  included.
- PR #15 is not a landing unit and must remain Draft/Open.
