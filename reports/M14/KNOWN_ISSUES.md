# M14 Known Issues

- No concrete built-in Domain plugin is included. This is intentional: the first concrete plugin
  is the next milestone and must not be implemented as part of M14 infrastructure.
- Signed-trusted and community-untrusted plugins are not loadable until signature verification,
  policy evaluation, and/or a real out-of-process Sandbox runtime are available. They fail closed
  rather than being treated as trusted by manifest declaration.
- M14 persists project activation metadata and exposes opaque Domain IR envelopes. Plugin-owned
  domain tables, migrations, and concrete artifacts remain plugin-specific future work and must
  be namespaced when introduced.
- The existing M12 hosted-CI/human-acceptance blocker remains recorded in the prior reports; this
  local M14 acceptance does not fabricate remote evidence.
