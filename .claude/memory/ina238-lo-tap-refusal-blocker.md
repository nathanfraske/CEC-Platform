---
name: ina238-lo-tap-refusal-blocker
description: "The convergent blocker for the placer-autonomy milestone AND the PCIe-3port grow — the INA238 LO Kelvin tap (pad 9) is refused because it's top-clustered, far from the bottom LO shunt terminal."
metadata: 
  node_type: memory
  type: project
  originSessionId: 6a1b6a2a-dfb9-4421-89b6-0ca014fb9552
---

The single highest-leverage open blocker on the placement-corridor branch (2026-06-30). It
blocks BOTH the placer-autonomy milestone-1 (a fresh synth_one-placed eps routing gate-clean)
AND the owner-ratified PCIe-3port grow (its `SENSEC*_LO` failures). Same root cause.

**Symptom:** `route_oracle_grade` on a synth_one-placed eps (or the grown 3-port) returns
`kelvin_ok=False` with every cable's `/SENSEC*_LO` unconnected, while foreign_ok/thermal/
diffpair pass. `cec_fr.synthesize_kelvin_taps`' `refused` report names it exactly:
`{'/SENSEC1_LO': ['RS1->U10.9'], ...}`.

**Root cause (pcbnew-verified, not theory):** the INA238 LO Kelvin tap (IN-, **pad 9**) is
refused by defence-2 — the clearance guard that refuses any STRAIGHT tap stub crossing
foreign copper. On the VSSOP-10 INA238, IN-(pad 9) sits TOP-clustered next to IN+(pad 10)
(`cec_fr._SENSE_INPAD INA238: HI=10, LO=9`), but the LO shunt terminal (RS.2) is at the
BOTTOM (~6mm away). So the straight LO stub travels up across the shunt/HI band and clips
foreign copper → refused → IN- floats in the pour antipad. The HI tap (pad 10 → top
terminal) is short and clean, so it IS laid. The hand-finalized committed eps (515cae7)
does not hit this (its INA238 seat clears the LO tap); the AUTO-seat `_seat_sense_ics` does.

**Ruled out (don't re-litigate):** not the partition (the cable parts are seated, not
partition-governed), not the 3-port grow (a fresh eps hits it too), not pass budget (24
passes didn't change the net class), not pitch (that's the middle-cable cut-vertex, a
different, horizontal failure).

**Fix candidates (next lever):** re-seat the INA238 so the LO tap channel is clear; OR allow
a 1-bend LO tap down the open notch instead of a straight stub; OR extend
`tap_channel_keepout` to reserve the LO channel so FR routes the foreign away. Placement/
tap-guard work — the [[route-oracle grader]] adjudicates it, and the intent-compiler
(`cec_placement_session.PlacementSession`) is the natural vehicle for a re-seat intent, but
the seat geometry is the substance. Detail in `docs/owner-queue.md` (2026-06-30 entries).
