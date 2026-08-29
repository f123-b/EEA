# M24A Known Issues

- M24A intentionally does not execute proposed changes, builds, tests, hardware actions, or
  deployment. Controlled execution is deferred to M24B.
- The reference provider is deterministic and offline. Hosted LLM adapters are not part of this
  milestone; the protocol is provider-neutral for a later adapter.
- Context selection is bounded and relevance-based. A reviewer must resolve unknowns when the
  source revision, hardware evidence, acceptance criterion, or dependency state is insufficient.
- The desktop acceptance evidence is limited to the planning panel and focused UI safety checks;
  release packaging remains covered by the existing repository gates.
- No P0/P1 issue is known. Any CI infrastructure failure is recorded under `INFRA` in the final
  acceptance report rather than hidden as a product pass.
