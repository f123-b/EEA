# Project Scope Hardening Known Issues

- The project-scoped API is the supported external contract. Global records remain readable
  only through explicit repository/service scope semantics; no unscoped project API was added.
- No unresolved cross-project read or metadata-deduplication defect was found in the focused or
  full local tests.
