# Milestone Boundaries

This file is the repository-local boundary record for the M23L landing closeout. It is
intentionally additive: it does not rewrite history, move tags, or alter historical migrations.

## Baseline

- `main`: `67c7e3ea42d00f67cc473b2041929555764a3daf` (`Merge M20 Core Neutrality Smoke Gate`)
- Integrated development branch: `codex/m21-desktop-ui-vertical-slice`
- Landing branch: `landing/m23r-knowledge-memory-trust`
- Working branch HEAD before M23R changes: `7726a328c8a991840bff00a337c97e8f28da4e9c`
- Integrated snapshot: `e3b720340e219a52ff1098693591d74da2d1f3ad`
- M23R current milestone SSOT: `apps/backend/src/eea_backend/version.py`
- Landing Alembic chain ends at: `0040_m23l_m23r_memory_trust_closure`
- M24 status: not started

## Logical implementation and acceptance boundaries

| Milestone | Base | Implementation boundary | Acceptance boundary | Status |
|---|---|---|---|---|
| M21 | M20 `67c7e3e` | `a47d2d3` | `92758c1` | Accepted on the development branch |
| M22 | `92758c1` | `f7f7d24` | `fe1254d` | Implemented vertical slice; hardening retained in M23R |
| M23 | `fe1254d` | `7726a32` | M23R gate | Core implemented; M23R closes hardening |
| M23R | `7726a32` | `42bc9e4` | final M23R acceptance commit | This closeout |

The M21 implementation boundary names the last M21 code fix before the acceptance evidence
sequence. The M22 implementation boundary includes the repository-formatting commit after the
feature commit and before its acceptance record.

## PR presentation boundary

The existing branch name and its ancestry span M21 through M23. Rewriting that history would make
the release evidence and dependency chain less reliable, so M23L records a safe additive split:

1. M21: `67c7e3e` → `92758c1`
2. M22: `92758c1` → `fe1254d`
3. M23 Core: `fe1254d` → `7726a32`
4. M23R Hardening: `7726a32` → final M23R commit

The landing PRs are #16 (M21), #17 (M22/M22R), and #18 (M23/M23R). PR #15 remains the preserved
integrated development history and is not a direct landing unit.

The remote PR title/description should use these boundaries when the PR is manually retitled or
split. No remote PR mutation was performed by this local closeout.

## Boundary rules

- Verification authority is backend-derived from loaded evidence; request fields are compatibility
  inputs only and are not authorization.
- User identity and organization scope come from the authenticated principal.
- Source revision, claim conflict, evidence freshness, and UI load state are explicit.
- Reviewed M22 findings promote to canonical claim/evidence records with provenance.
- No historical migration was edited. M23L uses additive revisions `0038`, `0039`, and `0040` to
  linearize the landing chain after M22.
- M24 work must not be mixed into the M23R acceptance commit.
