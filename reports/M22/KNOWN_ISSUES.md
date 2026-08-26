# M22 Known Issues (historical vertical slice)

- The original M22 slice was intentionally conservative. M22R now adds parser-backed candidate rows, explicit review/apply APIs, and candidate-only canonical metadata; imported values remain unverified until downstream gates run.
- KiCad and DBC analysis remains structural rather than a full electrical/protocol validation tool. Unknown fields are preserved and surfaced for review.
- Git credential-provider UX remains outside this local closeout; credentials embedded in Git URLs continue to be rejected.
- The original Desktop rescan surface was not retrofitted into a full graph editor; the backend returns structured diff and dependency-impact buckets for the next workbench surface.
- Remote CI release acceptance for commit `f7f7d24` passed in run `32548432274`; M21 PR #15 remains Draft/Open and unmerged pending the project landing decision.
