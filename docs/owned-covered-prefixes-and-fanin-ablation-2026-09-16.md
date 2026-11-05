# Owned covered-prefix normalization and local fan-in ablation

## Measured improvement: PCIe3 USB diagnostic now qualifies

The selected USB probe on current PCIe3 **400ffdd8635e** previously emitted a
connected pair but failed the final craft gate: a narrow 0.20 mm long segment
overlapped two 0.25 mm package-closure prefixes. The ordinary duplicate remover
correctly could not delete the wider short copper. There was no corresponding
generated-long-leg trim in the precision pair's transaction-end normalization.

`cec_copper_overlap.trim_covered_prefixes` now supplies that missing generic
operation. It requires exact integer collinearity, common net/layer/origin,
strictly different lengths and a covering prefix at least as wide. Only a long
leg whose UUID is explicitly writable can change. It is trimmed to the short
leg's far endpoint; both primitives and the explicit junction remain. UUIDs,
widths, nets, layers, locks, groups and inherited copper are preserved. There is
no board/refdes/coordinate exception, no near-parallel deletion and no new copper.

The precision route transaction invokes it after same-footprint closure and
ordinary covered-track removal, before the existing topology, partner-pad,
coupling, skew and whole-board checks. This is not a gate waiver or a blanket
unlock of earlier priority routes. The helper and failure-replay module are
also registered in the declared generic-core audit.

Current-source old/new replay:
`build/covered-prefix-suite-20260916/report.json`.

- PCIe3 selected USB: **pairs_ok false -> true**, with the same 48 tracks and
  no added vias. Two covered-prefix trims remove 1.25 mm of double-counted
  primitive length, not 1.25 mm of physical copper. Native DRC remains **0**;
  the partially routed diagnostic retains **246 opens** for the other work.
- Hub's selected pair still passes; PCIe2's preexisting pair is retained;
  VHP's USB still refuses. Their native geometry/results are identical.
- EPS and ATX remain held before native replay by their interface-ECO gates.
- All source/hierarchy identities, placements and protected input copper remain
  unchanged. These private probes are not published or retained as canonical.

Independent native evidence:
`build/covered-prefix-suite-20260916/native-comparison.json`.
All four comparisons preserve native DRC/open counts and prior pair/Kelvin
passes. PCIe3's differential-pair score changes false -> true. Per-net/layer
round-buffer copper unions have **zero symmetric-difference area** at the
documented sampling resolution, independently corroborating the helper's exact
integer coverage proof. This is a local routing-quality improvement, not
whole-board closure, fabrication release or thermal qualification.

## Regression coverage

**219 tests and two subtests pass**, 14.08 seconds:
`build/covered-prefix-final-tests-20260916.log`.
Loaded-native regressions cover translated/rotated front/back/internal copper,
equal/wider versus too-narrow covering prefixes, inherited-versus-writable long
legs, explicit branch junctions, retained group/lock identities, multiple-prefix
chains, save/reload and unchanged source bytes. Cross-net/layer, a one-nanometre
noncollinear fork, opposite direction, no shared origin and equal-length cases
remain untouched. Existing flow-through, ribbon, lifetime, failure-replay and
anti-overfit tests pass. Do not sum this count with overlapping earlier suites.

Historical PCIe2 SHA, complete `board_regression` and all `probes` are unchanged:
`build/covered-prefix-control-comparison-20260916.json`. The declared generic core
passes; broader legacy release holds remain.

## Rejected experiment: obstacle-derived fan-in bends

Before finding the PCIe3 normalization gap, a private prototype added local
bend/spine coordinates from inflated native obstacle boxes after the ordinary
joint escape failed. Existing exact guards, skew/coupling policies and deadlines
remained. This differed from the earlier portal-seat-only experiments.

`build/local-fanin-contact-suite-20260916/report.json` records baseline/contact
probes across all six current identities (four native pairs, two ECO refusals).
For VHP, the prototype attempted 278 extra local searches and constructed 80,064
extra bend-path proposals in roughly 5.41 seconds of fallback work. **None yielded
a newly solved local pair.** Hub/PCIe3 also gained no local solution. Constructed
proposals are not all necessarily fully evaluated before deadlines.

Independent old/new native geometry, poses and scores are identical:
`build/local-fanin-contact-suite-20260916/native-comparison.json`.
The prototype is **not integrated** into production. It is neither evidence of
physical unroutability nor justification for another unchanged larger wave.
Some retained local examples have zero legal member paths before joint pairing;
future investigation should isolate exact pad/heading/reservation access rather
than merely multiplying perimeter candidates. The fixed-power/mating constraints
remain unchanged.

## Completed canonical verification

One new full PCIe3 follow-up is justified by the verified USB-gate improvement:
**`build/covered-prefix-followup-suite-20260916/suite.json`**.
It starts from the existing explicit **400ffdd8635e** placement, not a private
probe. Limits: one board job, four placement workers, eight craft trials, four
passes, 480-second priority repair and 900-second total job bound, with the 16 GiB
free-space floor. Runner: `tmp/covered_prefix_followup_20260916.py`.

The follow-up finished blocked after **659.227 seconds**. It confirms critical
route failures **12 -> 11** against the previous rigid-cell full pass: nine
Kelvin reach refusals and two CAN pair refusals remain, while route-quality
refusals fall **1 -> 0**. The local craft gate passes. No placement move is
admitted; the final PCB remains byte-identical **400ffdd8635e**, and detailed
routing does not begin. Do not confuse preflight's repaired USB qualification
with new saved copper, reduced full-board opens or fabrication signoff.

Source, hierarchy and engine remained unchanged during the run. Explicit
`continuation_inputs` revalidation selects the hash-bound placement. All six
canonical board/hierarchy signatures were independently rechecked at completion.
Receipt: **`build/covered-prefix-followup-completion-20260916.json`**.

The dashboard API verifies immutable review
`pass-covered-prefix-followup-suite-20260916-pcie-8pin-3port-effa868feb`, SHA
**400ffdd8635e**, BLOCKED/placement, with no release authority. Both body-free
top/bottom panels were visually inspected in the Windows review mirror under
`CEC-Board-Reviews/covered-prefix-followup-suite-20260916/pcie-8pin-3port/`.

No owned pipeline workers remain. The other five boards keep their separate
holds; the canonical six-input plan remains
**`build/route-finish-next-inputs-20260916.json`** because this output is identical
to its existing PCIe3 source. About 66 GiB remains free, above the 16 GiB floor.
Do not repeat this exhausted full pass. Rotate the next development slice to an
independent physical dependency instead of retrying the unchanged failure set.
