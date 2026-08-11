# M7 Known Issues

No critical local implementation issue is open.

| Severity | Item | Impact / next action |
|---|---|---|
| Low | Pin plans, assignments, and locks are currently returned from the generate vertical slice and are not persisted | Add scoped repositories, migration, and lock/override APIs in the next M7 increment. |
| Low | Device facts are fixture-backed | Add an authorized vendor-data provider and evidence contract before production planning. |
| Info | Remote CI has not run for this change set | Push through the project release workflow when remote publication is authorized. |
| Info | Hardware commissioning is outside M7 | Keep flash, actuator-enable, and commissioning gates separate in later milestones. |
