# M10 Known Issues

No critical local implementation issue is open.

| Severity | Item | Impact / next action |
|---|---|---|
| Medium | KiCad CLI is not installed or configured in the local environment | Validate returns `UNKNOWN`; configure a KiCad runner and import its versioned ERC output before claiming tool verification. |
| Low | Netlist text is persisted as the editable intermediate, not a native `.kicad_sch` file | Add SKiDL/KiCad materialization and artifact file storage when the authorized toolchain is available. |
| Low | Schematic component and electrical attributes retain extensible JSON shape | Stabilize component-selection and symbol-library schemas in later milestones. |
| Info | Remote CI has not run for this change set | Publish through the project release workflow when remote execution is authorized. |
