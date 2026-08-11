# M8 Known Issues

No critical local implementation issue is open.

| Severity | Item | Impact / next action |
|---|---|---|
| Low | Architecture and Hardware IR use generic JSON attribute bags for extensible fields | Replace only with registered, versioned schemas as later IR milestones define stable contracts. |
| Low | Device facts are fixture-backed | Add an authorized vendor-data provider and evidence contract before production planning. |
| Info | Remote CI has not run for this change set | Publish through the project release workflow when remote execution is authorized. |
| Info | CircuitIR and electrical validation are not implemented | M9 must consume HardwareIR without creating a second device or pin source of truth. |
