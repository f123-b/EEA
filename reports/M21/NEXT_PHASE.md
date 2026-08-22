# M21 Next Phase

M21 final gates are closed on `codex/m21-desktop-ui-vertical-slice` at
`ea0a0a8d0d33581ea30f01e83739ec3857c8443a`.

- `M21=IMPLEMENTED_AND_FINAL_GATE_CLOSED`
- `P0=0`
- `P1=0`
- `READY_FOR_M21_FINAL_REVIEW=YES`
- `APPROVED_TO_MERGE=NO`
- `M22=NOT_STARTED`

The validated Desktop release download is the `desktop-release-artifact` Actions artifact from
push CI rerun [`32496409227`](https://github.com/f123-b/EEA/actions/runs/32496409227), with the
matching Draft PR verification in [`32496414796`](https://github.com/f123-b/EEA/actions/runs/32496414796).
It contains the normalized Windows NSIS installer, Linux AppImage, `SHA256SUMS.txt`,
`release-manifest.json`, and `release-size-report.json`. Desktop defaults to Chinese (`zh-CN`)
and Settings persists the Chinese/English choice.

The branch must remain a **Draft PR** until human review is complete; PR #15 is Open and not
merged. Recommended review focus: launch the final AppImage, walk the M20 benchmark in the
renderer, activate/deactivate a domain from backend metadata, and inspect the
Build/Static/ERC/TestRun/traceability/Review evidence surfaces.
