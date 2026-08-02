# Pour-strategy refinement - the 24-pin stress case + the blade-coupler rung

> **Historical strategy note.** The measured failure analysis remains useful,
> but its four-layer assumption and its statement that inner pours are
> schema-only are superseded. The approved six-layer contract assigns In2.Cu to
> signals and In3.Cu to power routing and pours. The current pipeline must carry
> those roles through DSN export, routing, SES import, pour compilation, and
> post-route verification. A stale schematic-to-PCB candidate is rejected
> before this strategy is evaluated.

_Owner directive (2026-07-19): "I figure it's going to need the blade coupler
replacement rung to make the pours work here. Should be a good stress test of the
pour strategy pipeline and that is the first thing to refine - brainstorm how we
make that one better." This doc is that brainstorm: grounded in the measured
2026-07-19 wave/forensic evidence, the pour-lever architecture of record
(`docs/pour-lever-scoping-2026-07-08.md`, stages 1–4 landed, four owner rulings
ratified 2026-07-09), and the single-sided 24-pin as the forcing function._

## 0. Why the 24-pin single-sided IS the pour stress test

Every simplification the pour machinery has leaned on is absent here, measured:

| Assumption baked into today's pours | 24-pin single-sided reality |
|---|---|
| Per-cable interposer: ONE force net per corridor, J_IN→shunt→J_OUT straight by construction | FOUR heterogeneous rails share one connector; pin groups interleave along J3 (3V3 owns cols 1,2,12,13 - the SPAN of the connector) |
| Mirrored F/B pours carry the current (cable-board doctrine) | ONE assembly face (owner 2026-07-19); B.Cu is not a mirror partner for SMT-adjacent copper |
| Pour rectangles from connector+shunt pad bboxes (`_pour_boxes_core`) | Rail regions are L/Z-shaped chains (group → band → column → TB slots); bboxes tile the board (measured: the 12V_LO box was 17×26mm; the strict gate found "nowhere legal") |
| Pours are POST-ROUTE additive copper on an FR-routed skeleton | FR never routes the fat rails (force-pin exclusion / owned nets); force-rails lays the skeleton - and its first three firings measured 0/4 laid against squatters and crossing spines |
| The TB blade coupling is FIXED (netlist ref-order) | The coupling is a FREE VARIABLE - the daughterboard absorbs net-mapping by §2.8 architecture ("all output pin-mapping inside it"); positions/pitch are the only contract |

Plus the standing structural facts: the 24-pin's stackup exception gives it an
**inner POWER-ROUTING layer** (owner stackup ruling 2026-06-14: rails "must route
around each other" - In2 is FOR this), and tonight's third-mover forensic showed
the placement passes themselves still fight over the shunt columns.

**Single-sided ≠ single-layer.** Assembly is one-faced; copper is not. The inner
power layer is the release valve for the 3V3-spans-the-connector problem - and
today NOTHING in the pour pipeline can place copper there (`CEC_INNER_POURS`
parked; PourPlan ruling (3): In2 is schema-only until the FR-binding fix).

## 1. The blade-coupler replacement rung (the owner's named lever)

**What it is:** which TB receptacle couples which rail is a MUTABLE pipeline
decision - order re-assignable, positions/pitch fixed (the daughterboard mating
contract; keying proofs are geometric, not net-keyed). Today the coupling is
chosen ONCE, at placement, by `_perm_cost` (now J3-centroid-weighted). That is
the wrong altitude: the quantity the coupling should optimize is **pour cost**,
and only the pour planner knows it.

**The rung, concretely (PourPlan verb `recouple`):**
1. PourPlan gains the blade field as a first-class object: the fixed slot row
   (positions, pitch, groups) + the current ref→slot assignment.
2. At plan time (pre-route), the planner evaluates coupling permutations against
   the REAL pour cost per rail: corridor length, bend count, crossings-with-
   other-rails (the quantity that forced dual-siding), min-cut width achievable,
   and thermal (the coarse-CPU solve is 3 s - cheap enough to score the top-k
   permutations, not just a geometric proxy).
3. The chosen coupling emits as (a) a TB ref re-stamp within the fixed row
   (same-footprint slots - legal at any pass before lock), (b) a
   `pourplan.json` record with provenance, (c) on ADOPTION, the out-db net-map
   regen + checker-table update (already queued in FOLLOWUPS 2026-07-19).
4. Autonomy line: re-coupling is GEOMETRY-ONLY at the module (no netlist edit -
   refs move, nets ride them), same class as the ratified reshape autonomy;
   the out-db regen at adoption is the owner-visible artifact.

**Why it unlocks pours here:** with coupling chosen by pour cost, each rail's
sink fan (shunt→TBs) becomes short and straight, sink corridors stop crossing,
and the residual crossing burden concentrates in the SOURCE half (J3 pin
interleave) - which is exactly what the inner layer is for (§2.3).

## 2. Ranked refinement brainstorm (the pour strategy itself)

**2.1 Chain-shaped pour regions (kill the bbox).** The parked LANE-BASED POUR
SYNTHESIS (TODO 2026-07-08) is the right shape, generalized: a pour region is a
POLYLINE CHAIN with per-segment width from IPC-2152 at the rail's current -
group-collect stub(s) → band run → column → sink fan. `plan_bands` (landed
tonight) already computes the packed band rows; the chain pours are those bands
made copper. One geometry source: **force-rails trunks and pours UNIFY** - the
trunk IS the chain's spine at minimum width; "pour" = the same chain compiled
wider where space allows. This kills the current trunk-vs-pour split before it
calcifies into a second duality debt.

**2.2 Pour-driven coupling (the §1 rung).** Ranked second only because §2.1 is
its substrate - the permutation cost needs chain geometry to score.

**2.3 In2 as a first-class pour layer on the 24-pin.** The ratified PourPlan
ruling holds In2 at schema-only pending the FR binding fix; the 24-pin makes
that fix worth doing NOW: crossing rails dive to In2 for the crossing segment
with via fields at each end (per-via current split already modeled by the
electrothermal solver). The one measured footgun to honor: a through-via's
anti-pad severs a THIN foreign lane (the atx24-out-db lesson) - so In2 crossing
segments must be WIDE (they are; they're power) and the via fields land inside
own-copper, never on a foreign thin lane. Deliverable: `CEC_INNER_POURS`
unparked for shared-bus boards + the DSN plane/keepout binding for In2.

**2.4 Close the box-model duality NOW (it bit again tonight).** The restamp
settle avoided `_pour_boxes_from_P` while the corridors/gates check other
derivations - tonight's fix bolted corridor boxes into the settle as a third
box source. Under §2.1 all three (pour boxes, corridor keepouts, settle
obstacles) compile from the ONE PourPlan chain set. This is the pour-lever
scoping's own thesis; the 24-pin evidence says finish it before adding more
consumers.

**2.5 Bounded pour↔route↔coupling negotiation.** The rebuild verb exists
(stage 4, rebuilds count against Kmax). Add the coupling swap to the repair
repertoire: when FR feedback shows a rail's residual unroutable through its
corridor, the manager may propose `recouple` (cheap tier: re-stamp TBs +
re-derive chains + refill ≈ 0.1 s) before `pour_reshape` or escalation. Two
rounds max - the ladder discipline, not a solver loop.

**2.6 Thermal-closed-loop widths.** Chain segment widths start at IPC-2152
closed-form and get ONE refinement pass from the coarse-CPU 2.5D solve on the
planned copper (3 s, hint-resolved config - both landed tonight): any segment
whose local dT exceeds budget widens or splits to In2. Provenance-stamped like
the wave thermal.

**2.7 GND is a pour-strategy citizen.** The GND criticals persist on every
24-pin wave: TB6-9 + 8 J3 barrels + the plane. The chain model should emit the
GND SINK chain too (plane reach into the TB field + stitch rows), replacing the
implicit "the plane will cover it" - measured, it doesn't (GND critical on
every best).

**2.8 Pour-plan A/B discipline.** Every plan-level lever above (coupling,
In2 dive, width refinement) lands behind the pinned-seed A/B protocol with the
oracle deltas (foreign-on-pour / unconn / dT / bodies-in-pours) - the
coord-router lesson: a mechanism that loses its A/B gets shelved, not argued.

## 3. Sequencing vs the running work

1. **Now (this wave series):** force-rails refusals keep teaching; the
   corridor-aware settle/sweep landed; the third-mover forensic is the
   placement-side prerequisite for straight columns.
2. **First pour-refinement PR:** §2.1 chain regions + §2.4 unification on the
   24-pin (eps/pcie byte-identical regression per the pour-lever discipline),
   with force-rails compiling FROM the chain plan.
3. **Second:** §1/§2.2 the recouple rung + §2.5 repair-repertoire entry.
4. **Third:** §2.3 In2 unpark (needs the FR In2 binding fix - its own bench).
5. Owner-gated on adoption: out-db net-map regen; ratified-constraint touches
   none (positions/pitch/keying unchanged throughout).
