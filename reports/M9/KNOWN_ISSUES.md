# M9 Known Issues

No critical local implementation issue is open.

| Severity | Item | Impact / next action |
|---|---|---|
| Low | Circuit component ratings and net attributes use extensible JSON bags | Add registered component/electrical fact schemas as selection and schematic milestones stabilize. |
| Low | Electrical rules require canonical `EngineeringValue` inputs | Missing or dimension-mismatched inputs intentionally produce `UNKNOWN`; callers must provide traceable facts. |
| Low | Device and component facts are fixture-backed | Add an authorized vendor-data/component provider and evidence contract before production selection. |
| Info | Schematic/ERC generation is not implemented | M10 should consume only persisted CircuitIR and surface ERC issues without creating another pin map. |
| Info | Remote CI has not run for this change set | Publish through the project release workflow when remote execution is authorized. |
