# Next Phase — M5 Sandbox Foundation

## Objective

Create the safe execution foundation required before any external repository, archive, or build
workflow is enabled.

## Planned scope

- `SafePath` resolution and workspace ownership checks.
- Archive traversal and symlink protection for ZIP/TAR materialization.
- Isolated workspaces with no secrets and network denied by default.
- Structured command execution with process, CPU, RAM, and runtime limits.
- Deterministic command results and failure diagnostics for later import/build stages.

## M5 acceptance focus

- Malicious archives, symlinks, and build scripts cannot read or write outside the isolated
  workspace, host key material, or configured data root.
- A denied network request and a resource-limit violation become structured engineering errors.
- External Git/repository/archive build remains blocked until the sandbox acceptance gate passes.

## Constraints and sequencing

- M4 DocumentIR and Device Provider remain read-only fact sources; M5 must not mutate source
  documents or device facts.
- M6 Requirement DSL consumes M2 structured generation and M3/M4 claims; it must not execute raw
  commands directly.
- FIX-03 remains due before M12, and FIX-09 remains due before raw hardware adapters.
