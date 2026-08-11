# M8 Known Issues

No critical local implementation issue is open.

| Severity | Item | Impact / next action |
|---|---|---|
| Low | Architecture and Hardware IR use generic JSON attribute bags for extensible fields | Replace only with registered, versioned schemas as later IR milestones define stable contracts. |
| Low | Device facts are fixture-backed | Add an authorized vendor-data provider and evidence contract before production planning. |
| Info | Remote CI has not run for this change set | Publish through the project release workflow when remote execution is authorized. |
| Info | CircuitIR/electrical validation is implemented in M9, while schematic/ERC output remains pending | M10 must consume the persisted CircuitIR and retain the M7/M8 source-of-truth chain. |
