# M7 Known Issues

No critical local implementation issue is open.

| Severity | Item | Impact / next action |
|---|---|---|
| Low | Device facts are fixture-backed | Add an authorized vendor-data provider and evidence contract before production planning. |
| Info | Remote CI has not run for this change set | Push through the project release workflow when remote publication is authorized. |
| Info | M8 SystemArchitecture/HardwareIR is not implemented yet | Consume persisted M7 plans as the only pin-assignment source of truth. |
| Info | Hardware commissioning is outside M7 | Keep flash, actuator-enable, and commissioning gates separate in later milestones. |
