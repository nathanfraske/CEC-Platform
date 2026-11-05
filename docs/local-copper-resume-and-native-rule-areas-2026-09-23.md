# Local-copper resume and native rule-area admission — 2026-09-23

## Result

This slice fixes reusable ownership and proposal-generation defects. It does
**not** close either board or promote a new fabrication candidate. The verified
Hub checkpoint remains **0 native DRC / 199 unconnected**, with its complete CAN
pair independently passing saved-board physics. USB and residual routing remain
unfinished. ATX still fails complete power admission before signal routing.

Evidence root: `build/local-copper-resume-20260923/`.

## Generic repairs

1. **Exact local-copper placement handoff.** Placement now consumes the admitted
   frozen state's existing local-copper contract, preserving each owned UUID,
   geometry, lock, and fabrication group. It does not grant ownership of an
   entire GND or supply net. Hub retention increased from **208/271 to 271/271
   items**; the 63 previously unrecognized items are no longer a handoff blocker.
   The full local-power contract contains 97 items, 34 of which were already
   covered by the power prefix.
2. **Contact-scoped terminal binding and durable publication.** New schema-2
   local contracts bind all pad geometry of physically attached packages, not
   every unrelated consumer sharing a rail. Legacy contracts can be upgraded
   only after their original broad terminal digest and exact copper are verified.
   Read-only verification never recreates missing copper, substitutes a UUID, or
   repairs a group silently. Item-scoped frozen copper now locks its actual
   attached packages too. Atomic publication rebases the frozen-skeleton pointer
   out of the disposable staging directory. Project rules are not overwritten by
   this state-only handoff after qualification.
3. **Native keepouts in planning and construction.** Board and footprint rule
   areas, their actual polygons/holes, enabled copper layers, and separate no-via
   / no-zone-fill permissions now feed the shared via guards and both exact and
   raster pour planning. Net exemptions cannot bypass these permissions. Final
   native DRC, power/current, connectivity, and pair checks remain mandatory.

These changes contain no board, reference-designator, or coordinate exceptions.
The two new regression files contain **34 synthetic native tests**, including
renamed supply nets, unrelated same-net consumers, moved/changed attached pads,
UUID/group/lock loss, legacy upgrade refusal, staging-path durability, inner-layer
and footprint keepouts, via-land overlap, polygon holes, and distinct permissions.

## Hub execution

`handoff.json` proves that a no-change materialization is byte-identical to the
verified checkpoint. A disposable in-place USB-protector rotation also survives
materialization with all 97 local-power items, all 271 total copper items, and the
qualified CAN pair retained. Its frozen skeleton remains readable after staging
cleanup. This is handoff evidence, **not approval of that placement or USB routing**.

The canonical bounded continuation (`usb-continuation/repair.json`) reused the
sealed baseline and screened 12 placement proposals. Eleven were legal; eight
pair probes ran in parallel. **Five completed without an accepted route, three
exhausted their probe budget, and the remaining three were not probed.** The
round stopped as `critical_probe_budget_inconclusive`, accepted zero candidates,
and preserved the incumbent. A completed negative probe describes its finite
search domain, not a mathematical proof that the board cannot be routed.

The repair round took 122.41 seconds and recorded 588.934 worker CPU-seconds
across eight workers. USB still refuses coupled escape through the inline
protector. No failed rotation, incomplete measurement, or partial USB route was
promoted. Width, gap, clearance, mating geometry, and outlines were not relaxed.

## ATX forensic and bounded replay

The prior rejected exact-power diagnostic has three `/SENSE12V_LO` vias inside
the native capacitor vent keepout. The old power-via constructor returned no
conflict for all three; the repaired constructor returns `native_via_keepout`
for all three. Compare `atx-via-rule-area-forensic.json` and
`atx-via-rule-area-after.json`.

An item-preserving replay of the old 48-via field found one alternative position
but could not seat the remaining conflicts in the existing overlap region. It
returned `replacement_lattice_exhausted`, `ok:false`, and `changed:false`; its
partial proposal was not committed. This requires replanning the landing/current
path, not deleting the vent guard or accepting fewer required vias.

The fresh canonical power-authority attempt (`atx-rule-area-replan/probe.json`)
ran for **87.59 seconds** and failed `exact_filled_power_admission_failed`.
Several power domains had no proposed complete path, and the proposed
`/SENSE5VSB_LO` domain remained open after exact admission. Fewer generated items
or a different diagnostic rendering must not be represented as progress toward
an electrically complete board. The current ATX source was not replaced.

## Regression and source integrity

The combined suite passed **1,017 tests and 18 subtests**, with **one skipped**
test. See `combined-regression.log`. The final native PCIe two-port control
retains **0 DRC / 0 unconnected**, 749 tracks, 197 vias, and 1199.913 mm copper
length. Its two previously documented independent release findings remain:
RS1 pad 2 Kelvin departure direction, and CAN reference-plane coverage of 80%
against the 95% contract. Full release/generic acceptance is therefore still
false; these findings have not been waived.

`controls.json` confirms unchanged hashes for the original Hub and ATX placement
sources, the verified CAN checkpoint, the active Hub/ATX pairing manifest, and
the PCIe control archive. The verified Hub's native counts, exact local copper,
CAN physics, and complete item retention were checked again after these fixes.

No new accepted board was published. The existing models-off, six-layer Hub
review remains the correct unchanged view:
`http://localhost:8090/?id=20260923-hub-can-prefix-verified-965e13b59b`.
Both the dashboard page and its models-off render returned HTTP 200 on a fresh
GET check. All bounded runs have ended; no unattended wave is left running.
This slice's retained diagnostic artifacts occupy approximately 30 MB.

Next work is constructive USB escape through inline devices and complete ATX
current-path/landing replanning with native keepouts present from the start.
Neither needs a board-specific coordinate patch or permission to enlarge the
board, reshape protected copper, reduce current margins, or waive native gates.
