# Next Phase — M6 Requirement DSL

## Objective

Introduce versioned requirement profiles and completeness analysis on top of M2 structured
generation, M3 claims, M4 device facts, and the M5 execution boundary.

## Planned scope

- Requirement profile/schema registry with versioned field and evidence contracts.
- Natural-language requirement analysis through `StructuredGenerationService`; no direct model
  calls from the requirement service.
- Completeness and ambiguity analysis producing claims, issues, and required follow-up questions.
- Deterministic FOC benchmark profile input support without adding motor-only fields to Core.

## M6 acceptance focus

- Missing FOC requirements are identified as explicit incomplete/unknown items rather than guessed.
- Structured generation output is schema-validated, budgeted, timeout-bounded, and evidence-aware.
- Requirement profile versions are reproducible and unsupported schema versions are rejected.
- Requirement analysis cannot execute commands or bypass M5 sandbox policy.

## Constraints and sequencing

- M7 Pin Planner must consume M3 canonical units and M4 device facts; it must not duplicate them.
- M5 remains a hard prerequisite for any future import/build command execution.
- FIX-03 remains due before M12, and FIX-09 remains due before raw hardware adapters.
