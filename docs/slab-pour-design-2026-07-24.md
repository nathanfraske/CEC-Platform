# Slab-pour architecture — subtractive power copper (owner concept, 2026-07-24)

**Status: RATIFIED DIRECTION (owner, 2026-07-24 in-session), implementation queued.**
Owner's concept, verbatim intent: *"make a pour just a giant slab, intentional
overshoot in all directions, and progressively shave off areas of it until it fits
and doesn't take up more space than it needs, and no cross-section on it is less
than the min cross-section allowed for that pour."* Plus the priority ruling:
*"this would be an early rung on the ladder — the pour takes priority and gets its
route first before everyone else gets to encroach."*

## Why (the evidence)

Every pour defect caught on 2026-07-23/24 was an OUTLINE-DERIVATION failure of the
constructive approach (small rects derived from pads/asks): the 0.4mm rect miss at
RS1's via rows (severed In2/B rail legs), dead unbonded mirrors, 8-13% lace fills,
bond-planting refusals. A maximal slab cannot miss anything by construction;
material is then removed only for a MEASURED reason. Coverage becomes structural,
ampacity becomes a closed-loop invariant instead of an aspiration.

## The two-part slab (reconciling priority-first with the no-strand lesson)

The 2026-06-07 measured lesson stands: an immutable pour laid before routing walls
FR off and strands sense taps. The owner's slab is negotiable-but-floored, which
splits cleanly:

1. **GUARANTEED CORE — the early rung (priority ruling).** The pour's min-cut
   corridor (the copper path that must survive at >=125% of worst-case cross
   section, the platform margin policy) is laid FIRST at materialize as LOCKED
   copper + route-time reservation (bake_hints keepout). This generalizes the
   proven cec_force_rails locked-trunk pattern from "a trunk line" to "the
   corridor the shave loop may never cut." Nothing encroaches it. FR plans
   around it from move one. Kelvin windows/cell envelopes are notched OUT of the
   core by construction (sense discipline unchanged).
2. **OVERSHOOT — the shaved remainder.** Everything beyond the core floods AFTER
   signals route (additive doctrine preserved), then the shave loop trims it.

## The shave loop (raster-first; fill speed = architectural non-issue)

- Operate on the thermal solver's raster (0.8mm grid; the same grid cec_thermal2d
  uses). Shaving = grid morphology (erode / subtract), microseconds per round.
- Per round: subtract contested space (foreign signals/pads + clearance), drop
  disconnected fragments, drop sub-width slivers; then CHECK the invariant.
- **Invariant:** every cut across the net's current path holds >=125% of the
  required cross-section (reuse the electrothermal `_min_cut` + the field
  solver's per-net current map). A shave that would pinch below the floor is
  FORBIDDEN — the conflicting signal is the one that must move (named
  escalation, ratification doctrine).
- **Shave criteria — what "no more space than it needs" means:** does not BLOCK
  anything that needs the space. Shave only (a) space contested by foreign
  copper, (b) disconnected fragments, (c) slivers below the width floor.
  Uncontested copper in empty regions STAYS (free thermal margin; the spec's
  copper-favoring doctrine). Minimal-copper shaving would recreate lace.
- **Current-driven shaving is gated on injection success** (the INJECTION
  INCOMPLETE class): with an open rail circuit the current map is garbage —
  fall back to geometric-only shaving until the circuit closes.
- **Finalization:** convert the converged raster to outline polygons; ONE real
  ZONE_FILLER pass on the slab zones only (the filler accepts a zone subset —
  today's cost mostly comes from refilling every zone incl. the GND plane) as
  the source of truth; verify (DRC + connectivity + re-measured min-cut).

## Priorities and layers

- Contested overlap between two rail slabs on one layer: zone priority by
  current ranking (heavier rail wins contested space); deterministic.
- Multi-layer slabs overlap massively -> via stitching degenerates to
  grid-stitch wherever slabs of the same net overlap (existing derive_via_field
  machinery + the 0.85mm barrel ledger). The whole bond-planting problem class
  (synthesize_pour_bonds) becomes obsolete inside slab nets.
- Kelvin/sense nets NEVER slab. Sense-cell envelopes + tap windows are hard
  slab keepouts (existing envelope boxes).

## Integration map

- Keeps: the ask channel (nets/layers/evac semantics/provenance), post-route
  additive ordering for the overshoot, the locked-copper materialize rung for
  the core, kelvin exclusions, the 0.85 via ledger.
- Replaces: rect derivation in compile_rail_pour_asks regions + derive_power_pours
  geometry for slab nets; most of synthesize_pour_bonds (bonding trivial);
  the scrap-fill predictor (useless copper is shaved by measurement instead).
- New module: scripts/cec_slab_pour.py (slab seed, raster shave loop, min-cut
  invariant, finalize+verify). Wire: materialize lays cores; import_ses lays
  overshoot slabs + runs the shave loop before the final fill.
- A/B plan: prototype on the 24-pin rails (where rect derivation kept failing);
  one wave slab vs one wave current machinery, same seeds; grade + thermal +
  the owner's visual pass decide adoption. Hub logic-rail floods convert second.

## Non-goals

Does not touch FR signal quality, placement, or the R61-in-cell kelvin refusal
(separate threads; kelvin debug remains #1 on the 24-pin ladder).

## Addendum (owner, 2026-07-24, render evidence): dead-end appendage prune

"Auto-shave any parts sticking out from the main pathway or deviating from it
without going anywhere." Formalized as body-vs-appendage decomposition: body =
opening at the body scale (~2.5x the width floor); each appendage component
(mask minus body) is PRUNED iff it contains NO anchor (a finger reaching a
pad/via is a tap -- stays) AND touches at most ONE body region (a corridor
bridging two body lobes is a pathway -- stays, so pruning can never disconnect
anything). A sub-floor corridor legitimately dies at the sliver stage instead,
and the min-width invariant reports the split. Teeth: tests/test_slab_pour.py.
Measured on the s266 board: 12-58 appendages pruned per (net, layer).

## v2 — OVER-UNDER POURS (owner ratification, 2026-07-24 late): the pour is a routed object

The shunt-only top refusal is a BANDAID (owner's word; kept as the choke-point
safety net). The architecture: per rail, ONE continuous wide path from source
terminals to sink terminals, existing on exactly ONE layer per segment --
preferred layer (In2) until contested space blocks it, then a VIA-ARRAY BRIDGE
to another layer, carry on, bridge back. The vacated layer carries NO copper
there (the mirrored part is removed by construction, not by rule).

Consequences that fall out for free: criss-cross dies (paths, not slabs);
F.Cu copper exists only where the path must touch it (terminal fields/shunt
pads -- the shunt neighborhoods EMERGE instead of being decreed); mirrors
exist only as bridge overlaps (need-based by construction); vias always sit
inside copper (they ARE the bridges); the min-width invariant is the SEARCH
CONSTRAINT (pathfind on per-layer masks eroded by half the required width --
every found path is provably wide enough, per layer, oz-aware via the IPC
width per segment).

Implementation mapping (synthesize_overunder_pours in cec_slab_pour):
1. Terminals per rail from the chains (J3 pin group, shunt pads, TB group).
2. Per-layer obstacle rasters (existing rasterize) eroded by half the
   REQUIRED width for that net on that layer (IPC inverse, oz-aware).
3. Multi-layer A* over (cell, layer) nodes: step cost 1, layer-change cost =
   bridge penalty (~8 cells), layer preference bias (In2 cheapest, B mid,
   F expensive except within terminal fields).
4. Realize: each maximal same-layer run -> dilate by half-width -> lane
   polygon; each transition -> via-array bridge (ledger pitch, both-layer
   overlap for the bridge length).
5. Lay through add_power_pours (the choke point; path-derived F segments at
   terminals pass the shunt test naturally). Verify: min-cut re-measure +
   the invariant report.
A/B behind CEC_OVERUNDER=1 against the slab-shave path.

## v3 — POUR-FIRST PLACEMENT (owner ruling 2026-07-25)

"Pours are the first rung after you place the connectors and stamp the blueprints and
the MCU. Literally get rid of all of the rest of the components besides the stamps,
connectors, and MCU, run the pour algorithm and get it to a good state, then re-add
all of the other components. Save the pour state for me to look at."

Implementation state: `scripts/cec_pourfirst.py` = the standalone demonstrator (strip a
variant to its anchor skeleton -> solve pours tight -> save POURFIRST-*.kicad_pcb + hex
render to build/wave-snaps for owner review). First run on s415: 6/9 nets path_found on
the skeleton — including /SENSE12V_LO (TB1<->RS1), provably unreachable post-route —
25 lanes / 8 guaranteed patches / 44 bridge vias. OPEN: (a) 3 skeleton no-paths
(+5VSB, /SENSE12V_HI, /SENSE5V_HI — same bottleneck cells with and without the
anchor-approach taper, so the taper hypothesis is NOT their mechanism; DIAGNOSED
2026-07-25, see the v3.1 state note below);
(b) the pipeline seam — wire this stage between anchor/blueprint/MCU seating and
general placement, freeze pour geometry into placer avoid-boxes + route-time
reservations (the CEC_POUR_RESERVE corridor machinery is the same compute core);
(c) capsule-end/organic-merge aesthetics on bridge overlap disks.

**Implementation state (2026-07-25, pipeline seam LANDED — the rung is live):**
`cec_synth_pipeline.pour_first_stage(session)` runs from `cec_fresh_wave._build_session`
under the new per-board param `pour_first` (24-pin ON; prune and grade phases both, so the
cheap place key ranks the same avoid-box placement the grade routes). The seam: compile →
materialize the ANCHOR-ONLY board from the placer's own seam knowledge
(`Candidate.pourfirst_anchor_refs` = connector-role anchors + mounts/fiducials +
blueprint-cell members + MCU + owner pins; cells/rails/patches laid by materialize as
board truth) → ONE solve (manifolds stage 0 + over-under + guaranteed patches, `collect=`
returning the search internals) → FREEZE, three consumers: (1) a JSON state
(`params['pourfirst_state']` → `CEC_POURFIRST_STATE`) consumed by `cec_fr.route_once`
(frozen corridors + pour-owned pad exclusion — supersedes the live CEC_POUR_RESERVE
re-solve) and `cec_fr.import_ses` (provenance-"pourfirst" dicts pass through SET IN
STONE: excluded from the bond/scrap filter and from every re-conversion —
`cec_slab_pour.pourfirst_conv_split` is the pure core; a frozen no-path net lays ONLY its
manifolds + patches, loudly — the board-wide slab fallback is DELETED for frozen nets);
(2) F.Cu pour polygons → `params['pourfirst_avoid_boxes']` → the p8/p9 evac +
pour-aware-legalize channel ("pourfirst:"-prefixed so own-net exemption can never bypass
them); (3) the POURFIRST artifact (anchor board + pours, filled + hex render) into
build/wave-snaps/<board>/. Defense-in-depth: `cec_slab_pour.reap_nowhere_zones` (same
fresh-load site as cleanup_floating_zones, active only when a pour-synthesis path is
live) removes any filled non-GND zone touching <2 same-net terminal clusters unless
named patch:/manifold:/pourfirst: (zone names now set from dict provenance in
add_power_pours). Teeth: tests/test_pour_first.py (15).

## v3.1 — CONNECTOR MANIFOLDS + WIDTH-MARGIN ATTACH (owner algorithm, 2026-07-25)

Owner: "combine up all similar pins on one connector with a margin-width pour, then run
a trace from the target location to the closest part of the pour that still has the
width margin cross section. Then it draws the pour out from that, crossing layers as
needed with via fields."

Mapping: (1) MANIFOLD stage (new): per (connector, net), gang the pin group into one
margin-width bus-bar pour BEFORE any spine routing -- pad-anchored by construction
(never reaped), turns today's scatter of thin per-pin anchors inside foreign barrel
fields into ONE solid wide attach target. Likely cures the three skeleton no-paths
(+5VSB, /SENSE12V_HI, /SENSE5V_HI): their bottleneck clusters are multi-pin connector
groups unreachable at width as individual pads. (2) WIDTH-MARGIN ATTACH RULE (new):
spine search targets are erode(manifold, req_w/2) cells -- attach only where the
manifold can actually feed the width -- not any bare anchor cell (today's rule).
(3) "draws the pour out from that" = realize_overunder's width dilation along the
spine (exists). (4) via-field layer crossing = the bridge machinery (exists).
Sequencing: manifolds become stage 0 of the pour-first rung, before spine solving;
the pipeline agent spec inherits this.

**Implementation state (2026-07-25):** LANDED — `cec_slab_pour.connector_manifolds`
(one margin-width dict per (connector, net, natural-layer); THT groups F.Cu+In2.Cu, SMD
their own side; name "manifold:<ref>:<net>", provenance "slab") + the width-margin
attach in `_prep_overunder_net` (cluster anchors REPLACED by erode(manifold∪anchors,
req_w/2) per manifold component; clusters ganged by one component MERGE; empty erosion
falls back to raw anchors with a note), wired behind
`synthesize_overunder_pours(manifolds=True)` — ON only for the pour-first path (+ the
demonstrator's `--manifolds`); import-side callers byte-identical. The F choke admits
transit through a laid F manifold's own footprint; `add_power_pours` admits F manifolds
by name. **Thesis verdict (measured on the s415 skeleton, margin 4/6/8mm sweep): the
manifolds do NOT flip the three no-paths — 6/9 unchanged.** Diagnosis (ablated):
+5VSB strands on a locked force-via TRIPLET at (42,23) and /SENSE12V_HI on a stamped-cell
SMD pad (U612V1-3) — neither is a connector group, manifolds definitionally don't apply;
/SENSE5V_HI strands on J3-6 whose manifold pocket IS attached (notes confirm anchor
replacement) but is walled off from the tree by locked trunk copper at width on every
searched layer — a margin the sweep cannot open. The v3.1 mechanism itself is
teeth-proven (tests/test_pour_first.py: a walled pin connects with a manifold, not
without); the s415 failures are a different class (locked-copper congestion at the seam,
open design question for the owner).
