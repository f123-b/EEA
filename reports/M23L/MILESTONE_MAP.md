# M23L Milestone Map

M23L converts the long-lived integrated development branch into three additive,
stacked landing units. No historical commit or migration is rewritten.

| Unit | Boundary | Landing branch | PR | Status |
|---|---|---|---|---|
| M20 | `67c7e3ea42d00f67cc473b2041929555764a3daf` | `main` | merged PR #14 | accepted |
| M21 | `67c7e3ea42d00f67cc473b2041929555764a3daf` -> `d345b833f1d7db9879399724071b601a7a399b0a` | `landing/m21-desktop-workbench` | #16 | final-head CI `32980213780` passed |
| M22/M22R | `d345b833f1d7db9879399724071b601a7a399b0a` -> `a09cd1ab9e4279dfa3c17bb391b643840df214c2` | `landing/m22r-existing-project-import` | #17 | final-head CI `33139849241` passed |
| M23/M23R | `a09cd1ab9e4279dfa3c17bb391b643840df214c2` -> `0766ae14c2f3debc17b4c4d9959eb72a29be9153` | `landing/m23r-knowledge-memory-trust` | #18 | synchronized; final-head CI `33140975697` passed |

The integrated snapshot is `e3b720340e219a52ff1098693591d74da2d1f3ad`,
preserved by `archive/m23r-integrated-e3b7203`.

Landing branches are additive copies of the reviewed logical ranges. The
original PR #18 head was `c91687d593af7bbcad2d78fb8d9751d52c3c777a` with
merge-base `8689cf5744f4b66ad5e262dd340b4e5310efc0ab`. Stack synchronization
used the ordinary no-ff merge commit `81b5c98e5a78ad6f54621900f7c6d8865967737f`;
the only follow-up was landing-only test import repair `0766ae14c2f3debc17b4c4d9959eb72a29be9153`.
The PR #17 final head is an ancestor of the synchronized PR #18 head. Exact
heads and independent CI runs are recorded here and in the PR checks; the
original integration PR #15 remains the historical snapshot.

M24 is not started and no merge is authorized by this phase.
