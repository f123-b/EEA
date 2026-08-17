# M19 Next Phase

M19A is **ACCEPTED** at final PR head `f8d3352100ef54a37d771e4625f3a2c30cc9a5cd`.
PR #13 remains OPEN/DRAFT/UNMERGED and approved to merge; its final PR CI is `32021782056`
and push CI is `32021777129`, with backend, desktop-web, desktop-tauri, and m19-release green.
The acceptance-docs commit will produce a new PR head and must be revalidated before merge.

The only remaining M19 scope is hardware commissioning, which is not authorized or available:

```text
M19A = ACCEPTED
M19B = BLOCKED_HARDWARE
M20 = NOT_STARTED
M21 = NOT_STARTED
APPROVED_TO_MERGE = YES
```

If M19B is later authorized, it must use the existing M18D permission, resource-lock, safe-state,
emergency-stop, and explicit commissioning contracts. It must keep `Flash != Actuator Enable`.
