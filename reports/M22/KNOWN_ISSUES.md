# M22 Known Issues

- The first M22 slice reports conservative candidates; it does not yet persist normalized Claim, HardwareIR, MCUConfigIR, or ProtocolIR rows. Candidate payloads remain durable in the import session and are intentionally not trusted facts.
- KiCad and protocol analysis is evidence detection with unresolved fields, not a complete schematic/netlist/DBC semantic parser.
- The Desktop wizard accepts a local path string. Native Tauri folder/archive chooser integration and Git credential-provider UX remain follow-up work; credentials embedded in Git URLs are rejected.
- Rescan creates a new SourceRevision but the Desktop surface does not yet render a structured `+ / ~ / -` diff or affected-node impact list.
- Remote CI release acceptance for commit `f7f7d24` passed in run `32548432274`; M21 PR #15 remains Draft/Open and unmerged pending the project landing decision.
