# Joint terminal reach and obstacle-aware placement

## Cause and generic repair

The PCIe3 incumbent's earlier move3 reduced critical refusals from ten to nine,
but rotated the sense amplifier into a crossed terminal order. Its existing
single-terminal range proposal ranked rotations by distance to one terminal.
The other sense terminal was left to the final checker. That checker correctly
rejected the move; the proposal was incomplete, not an acceptance bypass.

`cec_terminal_range` proposes the complete owner/bypass group using the existing
explicit terminal/pin contract and exact loaded native pad positions. It
intersects the two reach discs in translation space for each quarter-turn,
rejects crossed demands, and preserves the rigid follower geometry. There are
no board, reference, pin-number or destination-coordinate selectors. Native
pose, side, net and unique-pad identity must agree. Fixed group members remain
fixed. The strictest existing reported reach bounds the proposals; neither the
approved electrical limits nor power/assembly constraints change.

The shared `contact_translation_sites` packing primitive now optionally
intersects its translation domain with supplied reach discs. Conservative
native courtyard/pad envelopes and same-face power reservations provide free
space witnesses. The inscribed circle approximation can omit valid space; it
does not enlarge reach. All returned witnesses are rechecked analytically.
This finite proposal menu is not a completeness or no-path proof. Native
frozen-copper, complete craft, physical and exact routing gates still own
adoption. Existing total repair budgets are unchanged.

## Validation and negative evidence

- `build/terminal-range-final-tests-20260916.log`: **381 passed, 13 skipped**,
  118.95 s. Includes renamed/translated/rotated geometry, native front/back
  footprints, fixed and stale identities, rigid follower transforms, malformed
  domains, obstacle/reach intersections and existing full-pipeline regressions.
- First concurrent native cohort:
  `build/terminal-range-replay-20260916/report.json`. Of 48 PCIe3 analytical
  proposals, 44 hit courtyards and four hit protected power. None was adopted.
- Updated concurrent native cohort:
  `build/terminal-range-replay-v2-20260916/report.json`. Of 48 bounded PCIe3
  proposals, 31 hit courtyards, 16 failed exact frozen-power independence, and
  one reached full physical measurement. That one is still craft-blocked by
  the detector-to-driver locality requirement (14.9 mm); it is not a candidate
  admitted for routing or release. One private test board was written, not 48
  full boards or full routing runs.
- PCIe2, Hub and 12VHPWR have no applicable reported range obligation for this
  proposal family. Their independently remeasured physical statuses are
  unchanged. EPS and ATX retain their explicit unadmitted interface-ECO holds.
- Every current source PCB and hierarchy signature is unchanged. Historical
  PCIe2 board hash, complete regression and all four probes match exactly.
  The new module passes the static generalization gate. Existing legacy audit
  findings are not cleared by this slice.

## Canonical follow-up

At 20:08Z the bounded canonical pass was launched in
`build/terminal-range-joint-pass-20260916/suite.json`, using
`tmp/terminal_range_full_pass_20260916.py`. It selects only applicable families
from the six-board replay receipt, not hard-coded product selection. PCIe3 is
the sole applicable family this time. It starts from the canonical source,
not from a manually edited diagnostic board. All shared engine files remain
fixed while it runs. This is not yet evidence of an adopted placement or route.

Canonical cohort remains `build/priority-coopt-next-inputs-20260916.json` until
a journal-verified completion and independent qualification justify updating
it. Do not rerun unchanged exhausted failures on the other families.

## Live follow-up caveat (20:22Z)

The first canonical cooptimization round reduced priority refusals **10 -> 8**
and repaired detector locality using the existing generic craft solver. That
is a measured intermediate improvement, not routing or retained-bus signoff.
The second bounded round is still running. **Do not advance the input plan yet.**

Independent investigation found that the authority rebuild regenerated planned
power pours even though saved PCB copper was preserved. Comparing the first
checkpoint with the original frozen plan shows changes on SENSEC2_HI and
SENSEC3_HI, both outer layers. The original-plan dry-run rejects the new U21
pose for foreign pad contacts. Therefore the 10 -> 8 result is conditional on
power replanning and cannot be described as an unchanged-bus improvement.
`tmp/terminal_range_power_delta_20260916.py` distinguishes polygon geometry
from changed metadata. Original canonical sources remain untouched.

There is also a separate reproducible proposal bug: detector clearance-grid
rotations rotate the comparator but only translate its assigned bypass. The
new `tests/test_detection_cell_rotation.py` initially had four red cases;
`build/detection-cell-rotation-before-20260916.log` records the pre-fix failure.
They were reproduced before changing the running engine. This fix is not
counted among the earlier 381 passing tests above.

## Final outcome and next boundary (20:32Z)

The full attempt exited after **1165.897 s**. Placement did not complete:
power reconstruction in the second outer round consumed the remaining campaign
budget, and the following physical measurement was correctly refused with
`campaign_budget_exhausted`. The durable first-round checkpoint survived with
**eight priority refusals**. A later seven-refusal trial is not fully validated
and is not the published board. No further wave or native solver remains active.

After every campaign worker exited, the detector grid was changed to use
`rigid_cell_transform` for the owner and all assigned bypasses; a fixed bypass
now excludes the whole compound move. All four previously failing orientations
pass, with an additional fixed-follower negative case. The current focused
suite passes **315 tests** in 44.10 s:
`build/terminal-range-rotation-final-tests-20260916.log`. This overlaps the
earlier suite and is not 315 additional independent tests.

Final four-family native replay, two interface holds and historical-control
parity pass in `build/terminal-range-replay-v3-20260916/report.json`. Engine,
all six canonical PCBs and their hierarchy signatures remain unchanged during
the replay. Generic-core audit passes; legacy debt remains 23 physical and
380 runtime findings. No new PCB is promoted.

`build/terminal-range-checkpoint-reviewed-20260916.json` independently validates
the saved checkpoint identity, physical placement and its rebuilt exact power
authority. Saved PCB copper and qualified pairs are preserved. The original
frozen-power independence check **fails**, with the specific foreign-pad
contacts recorded, and four net/layer pour geometry differences are measured.
Priority routing is not independently rerun in this inspection; eight is the
checkpoint's recorded, completed priority result. Canonical continuation and
fabrication acceptance both remain false.

The body-free top/bottom views were inspected and published as **BLOCKED /
placement-checkpoint:priority / NOT FAB SIGNOFF**:
[dashboard review](http://localhost:8090/?id=pass-terminal-range-joint-pass-20260916-pcie-8pin-3port-055ab0188b).
Windows files are in
`C:/Users/Admin/Documents/CEC-Board-Reviews/terminal-range-joint-pass-20260916/pcie-8pin-3port/`.
SHA256 `21c18489b07cd944d6c9d108a083f86ae68b377701d829e0cf1c1891056b7fbb`;
83 footprints, zero tracks/vias. It is not a routed board.

**Next generic work:** consume the exact frozen-plan independence proof before
placement candidates spend the finite route-probe budget, and carry that proof
through compound craft repair. The saved-PCB prefix alone cannot protect power
that exists only in the committed pour-plan sidecar. A move needing changed
bus geometry must be an explicit rejected/dependency handoff, not silently
counted as an unchanged-bus win. Also bound power reconstruction together with
the post-authority physical/finalization reserve; this run shows that the
earlier round-cost estimate is not a worst-case bound for nested power repair.
These two remaining issues are diagnosed, **not yet repaired**. Keep the
existing canonical plan and do not repeat this unchanged failed full wave.
