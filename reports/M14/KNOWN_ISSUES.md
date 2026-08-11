# M14 / M14R Known Issues

- No concrete built-in Domain plugin is included. This is intentional: the first concrete plugin
  is the next milestone and must not be implemented as M14 infrastructure.
- Signed-trusted and community-untrusted plugins are not loadable until signature verification,
  policy evaluation, and/or a real out-of-process Sandbox runtime are available. They fail closed
  rather than being treated as trusted by manifest declaration.
- M14 persists project activation metadata and exposes opaque Domain IR envelopes. Plugin-owned
  domain tables, migrations, and concrete artifacts remain future work and must be namespaced.
- The implementation commit is `ade9da3`; the documentation/report commit and remote GitHub
  Actions evidence are still pending. Human acceptance is also pending, so this report does not
  mark M14R as ACCEPTED.
- The repository's persistent default `.eea/eea.db` contains historical Alembic comparison drift
  (`llm_cost` type and legacy CHECK-constraint names). A fresh database created by the acceptance
  sequence upgrades to migration `0021` and passes `alembic check`; the persistent local database
  drift was not rewritten as part of this scoped M14R correction.

