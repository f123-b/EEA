# M23L Milestone Map

M23L converts the long-lived integrated development branch into three additive,
stacked landing units. No historical commit or migration is rewritten.

| Unit | Boundary | Landing branch | PR | Status |
|---|---|---|---|---|
| M20 | `67c7e3ea42d00f67cc473b2041929555764a3daf` | `main` | merged PR #14 | accepted |
| M21 | `67c7e3e` -> `92758c1` | `landing/m21-desktop-workbench` | #16 | CI passed |
| M22 | `92758c1` -> `fe1254d` | `landing/m22r-existing-project-import` | #17 | stacked |
| M22R | `dfdaf8d` -> `36ae9eb` | `landing/m22r-existing-project-import` | #17 | stacked |
| M23 | `fe1254d` -> `7726a32` | `landing/m23r-knowledge-memory-trust` | #18 | stacked |
| M23R | `36ae9eb` -> `e3b7203` | `landing/m23r-knowledge-memory-trust` | #18 | stacked |

The integrated snapshot is `e3b720340e219a52ff1098693591d74da2d1f3ad`,
preserved by `archive/m23r-integrated-e3b7203`.

Landing branches are additive copies of the reviewed logical ranges. Their
final heads and independent CI runs are recorded in the handoff and the PR
checks; the original integration PR #15 remains the historical snapshot.

M24 is not started and no merge is authorized by this phase.
