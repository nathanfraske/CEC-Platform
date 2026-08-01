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
them) + a dedicated p8 final settle for boxed offenders (loud residual print); MEASURED
OPEN TENSION (s470): ~28 jellybeans still end on frozen-F bboxes — the frozen F state
(J3-field manifolds + 4mm margin, the wide +5V_MAIN F pour) covers more area than a
74x59 board can evacuate, so the legalizer least-overlap-parks back in, and p8b/p12 are
not box-aware. Owner call needed: shrink the F manifold class / accept parts-on-bbox
(fill carves true clearances) / make p8b box-aware; (3) the POURFIRST artifact (anchor
board + pours, filled + hex render) into build/wave-snaps/<board>/. Defense-in-depth: `cec_slab_pour.reap_nowhere_zones` (same
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

## v4 — TERRITORY PLANNING (owner GO 2026-07-25; supersedes cell-raster pathfinding as primary)

Owner verdict on the raster over-under output: "a bit of a mess... random vias across the
center in a line... blocky and all over the place... clearly regressing." Diagnosis on the
s464 pour state: the via line = 13 +3V3 vias x=25-57mm, a degenerate layer-weave a sane
cost model would never pick over near-empty B.Cu (B-mask/cost defect, to be root-caused in
the v4 build). Structural root: cell-level pathfinding produces connectivity, never design
intent.

v4 = the designer's method, algorithmic: keep MANIFOLDS (v3.1, proven); connect them with
STRAIGHT GEOMETRIC CORRIDORS — trapezoid/L fat polygons manifold-to-manifold at required
width on the obstacle-corner graph (OARSMT-style sparse geometry, not cells); resolve
overlaps by LAYER ASSIGNMENT as a small discrete problem (N rails x 3 layers, exact at
this scale); a genuine crossing = ONE compact via field at the defined crossing point.
The cell raster is DEMOTED to legality verification (clearance + min-width proof); the
direction-state Dijkstra survives only as fallback for corridors the planner cannot place.
Prior art anchors: PowerSynth (corridor-level power-module synthesis), IC P/G-grid
synthesis (Steiner + current-driven sizing), OARSMT.

**RUNG GATE (owner ruling, 2026-07-25): the pipeline does NOT advance past the pour-first
rung until the critical points are perfect.** The pour state is the active development
front; later-rung graduation waits on owner sign-off of the pour artifacts.

**Via-line ROOT CAUSE (2026-07-25, probed + double-ablated on the s464 skeleton — the
mandatory diagnosis before the v4 build):** the "13 vias in a line across x=25-57" is NOT
a Dijkstra cost-accounting bug and NOT a B-mask defect. +3V3 has 16 terminal clusters on
the skeleton, ALL anchored only on F.Cu (each stamped sense cell contributes FOUR separate
+3V3 SMD islands — INA238/INA181/TLV7011/RC — in a 4x4 lattice at x≈25/35/46/56 ×
y≈22.5/27.3/31.3/40.1, + ESP32). Every F-only island mathematically requires >=1 layer
change to reach the In2 trunk, and inter-island F transit is genuinely impassable on the
eroded masks. The instrumented per-round audit shows the trunk stays DOWN on In2 (14-16
In2 cells vs 1 F cell per Prim round); 17 total bridges ≈ the 16-island theoretical
minimum (+1 for a locked-rail-blocked In2 pocket at cluster 9, mask-forced In2→B→F).
Ablation A (F bias landing-only) = byte-identical result; ablation B (bridge_cost 8→16)
= still 17 bridges — the layer changes are mask-forced, not cost-ratio artifacts. The
MESS is REALIZATION smear: apply_bridge_overlap stamps 3-cell-radius disks on BOTH layers
per bridge (17 F blobs ~5.6mm), mask_to_polys' 2-iteration closing merges them into
blocky tiles, bridges_to_vias lays ~2 scattered vias per bridge (28 vias reading as a
line), and nothing aligns bridge positions between Prim rounds. A latent sibling defect
surfaced by the same probe: the ESP32 terminal's F landing blob is silently REFUSED by
the add_power_pours shunt-only choke (outside the belt), leaving its bridge via with no
F copper. Full probe record: build/pourprobe/ (probe1-8).

**v4 implementation state (2026-07-25, LANDED — `scripts/cec_pour_plan.py`):** the
territory planner is live behind wave param `pour_plan` / env `CEC_POUR_PLAN=1`
(pour_first_stage planner switch; `cec_pourfirst.py --v4` standalone; teeth
tests/test_pour_plan.py, 8). Shape as designed: terminal groups (terminal_clusters +
manifold gang + patch cover), Prim tree, per-layer corridor candidates on the
obstacle-corner graph (direct → one-bend → bounded corner Dijkstra), exact-at-scale
branch-and-bound layer assignment (most-constrained-first, node-capped with loud
bounded-exactness print), crossing SPLIT with one compact field, per-group canonical via
spots (incidence-aware), and per-net fallback to route_overunder (loudly labeled).
Mechanisms the s464 board FORCED into the design (all probe-measured): (a) manifold
attach = manifold ∩ per-layer free space, component alternates (plain eroded-polygon
nearest strands in the connector pin field); (b) manifold-polygon attach only on the
manifold's OWN layers — off-layers attach the pin copper directly (a B corridor
"attached" to an F/In2 manifold floats); (c) the ANCHOR-APPROACH NECK, the geometric
twin of the raster taper: within ~3.2mm of own pads a W_NECK=0.8mm centerline is legal
at true clearance (unguarded) — the ONLY way through the J3 THT barrel belt, whose 4.2mm
pin gaps close completely at trunk width + raster guard; (d) square-cap track obstacles
(rasterize's step boxes overhang a wide rail's endpoint by w/2+clearance — a 6mm locked
rail's phantom reached 4mm past its end and flunked a geometrically-legal corridor);
(e) landing patches + neck spines are terminal-zone copper (guaranteed-patch class:
connectivity-stamped, raster-clearance-exempt, the filler carves truth — the 0.8mm
raster cannot express legal copper between 0.5mm-pitch pads). VERIFICATION deviation
(flagged, measured reason): min-width runs as EXACT shapely erosion per realized piece,
not raster erosion — at cell 0.8 the smallest erosion radius proves 1.6mm, so every
floor-width 1.2mm corridor would fail structurally and diagonal capsules mis-verify at
any near-width cell size; clearance + attach-connectivity stay on the existing raster.
**s464 acceptance: 7/9 planned (baseline 6/9 found), the 2 fails (+5VSB, /SENSE12V_HI)
a strict subset of baseline's 3 (both the J3-belt/locked-copper class, the standing
owner question); ZERO crossing/mid-span via fields board-wide; every via field
terminal-labeled and compact (+3V3: 10 corridors / 2 bends / 11 terminal fields vs the
baseline's 17 smeared bridges).** `pourplan:` joined REAP_EXEMPT_PREFIXES. Artifact:
build/wave-snaps/atx-24pin-rev3/POURFIRST-sense-band-dataflow-s464-v4{-hex.png,.kicad_pcb}.

Blueprint tap discipline (same ruling): the stamped cells' Kelvin taps must be the
authored textbook-orthogonal set ONLY — the route-time synthesizer must recognize
blueprint tap copper as coverage (lock + per-pair contact handshake) and never lay
bent/diagonal fallbacks on a stamped cell.

### Tap-form ruling (owner, 2026-07-25, on the s480 zoneless render)
The authored cell taps are orthogonal but attach at the WRONG edges. Required form (the
"every other board" / §6.8 textbook): each sense tap contacts its shunt pad on the INNER
edge (facing the resistive element), runs PERPENDICULAR from that edge into the inter-pad
gap (toward the shunt middle), then ONE 90° turn OUTWARD to the INA. The route-time
canonical shape already says this; the cell-authored geometry must match it. Rework
author_kelvin_taps' derivation + regenerate the blueprint templates + re-prove clearance.

### Pour-termination ruling (owner, 2026-07-25, on the v4 agent's active artifacts)
"The pours go past the shunt's pads." Force-net pour copper (patches, manifolds, v4
corridors) must TERMINATE AT the shunt pad: clipped at the pad's INNER edge — never
entering the inter-pad gap, which belongs exclusively to the Kelvin tap stubs — and not
overhanging the pad's outer/side extents beyond clearance-necessary margin. Mechanism
today: guaranteed_shunt_patches clips at MID-GAP (pad copper extends past the inner edge
into the gap); fix = clip at the pad inner edge. Corridor landings obey the same rule:
approach from the outer face, stop at the pad.

### Via-in-pad ruling (owner, 2026-07-25, same artifacts)
"A couple vias in pads... odd that they aren't already caught." Root cause of the gap:
every via spot-check (_via_spot_clear, barrel ledger) guards FOREIGN-copper shorts; a via
inside a SAME-NET pad is exempt by construction. Missing rule = the assembly-class
exclusion: NO via center inside (or overlapping) an SMD pad regardless of net (solder
wicking; this platform uses no via-in-pad design). THT pads: no via within the annulus.
Applies to every via-laying path: bridge vias, force vias, pickups, lastmile, v4 crossing
fields. Add to _via_spot_clear (net-independent pad test) + teeth.

**Implementation state for both rulings (2026-07-25, LANDED, s464-re-proven):**
POUR TERMINATION -- `guaranteed_shunt_patches` inner-side clip is now the PAD INNER EDGE
exactly (mid-gap + `gap_mm` retired; outer/side margins keep 4.5mm, the outboard
force-via-row cover the patch exists for -- judgment call, the ruling's named mechanism
was the inner clip); new shared geometry source `cec_slab_pour._shunt_pad_halves`
(per-RS pad halves + the inter-pad GAP strip, the taps' exclusive territory). The v4
planner enforces the gap at three levels: F-allow minus gap strips (corridor + neck
spaces), landing patches clipped `land - gap_geom` + `land ∩ patch` for patch-covered
groups (the clipped patch doubles as the outer-face authority: ring spots must sit
inside it, so corridors arriving gap-side bend around the shunt), and an emit-side
`F.Cu - gaps` difference (trims the <=0.4mm neck-spine edge case). Measured: 2 gap
intrusions -> 0. Width-margin attach re-verified after the clip: 7/9 planned holds
(the locked tap stubs contact the pads, so connectivity through pad anchors stands).
VIA-IN-PAD -- new `cec_fr._via_pad_excluded` (barrel-vs-any-pad effective-shape
collision, net-independent; SMD overlap + THT annulus reduce to one test) wired into
`_via_spot_clear` (pickups / lastmile / tap doglegs inherit), `add_via_field`,
`add_overunder_vias` (loud refusals, defense-in-depth), and `synthesize_force_vias`
(whose fixed 1.6mm-from-center outboard base landed INSIDE a long shunt pad -- base now
clears the pad extent + each spot re-checked). MEASURED ROOT CAUSE of the s464 in-pad
locked vias: `cec_force_rails._array_sites` skipped OWN-NET pads in its site test --
now excludes any-net at no-overlap margin (25-site ring reseats). The v4 planner's
spot selection filters pads (`_spot_ok`) and `_field_vias` slide-reseats blocked slots
along the field line (ledger-stepped, capped at the terminal-zone reach, compact
same-layer cover rect keeps slid barrels embedded; total exhaustion returns [] and the
attach-connectivity verifier fails the net loudly -- never a silent drop, never a via
in a pad). Fresh s464 run: NEW in-pad vias 0/97, gap intrusions 0; the 3 remaining
hits are LEGACY LOCKED array vias baked into the historical skeleton by the pre-fix
code (RS2-1 x2, RS2-2) -- they regenerate clean at the next wave's materialize.
`cec_channel_route.py` also lays vias but has no callers in scripts/tests (dormant
tool; guard omitted, noted). Teeth: tests/test_pour_plan.py (patch inner-edge
coordinates, gap/pad-clear plan run, _field_vias slide + loud-empty, container
_via_pad_excluded/_via_spot_clear/add_overunder_vias/synthesize_force_vias) +
test_force_rails alt-array in-pad assertion. Owner-review artifact:
POURFIRST-sense-band-dataflow-s464-v4-shuntband-fcu.png (FILLED termination view over
ZONELESS pad/tap/via view, worklogged tag pour-first).

### Single-owner ruling (owner, 2026-07-25, on s510-class winners)
"Why did it make that bottom blob when it routed just fine on the bottom layers... why
does the top have a pour that goes nowhere if it already has a pour and route on the
bottom that works just fine?" THE PRINCIPLE: one net, one OWNING layer per segment —
copper is laid only where the winning solution actually runs; no layer gets "just in
case" copper. Mechanisms convicted: (a) ask layers treated as MANDATES (In2 laid even
when the search solved on B) — an ask's layer is a PREFERENCE; the realized solution
owns its layers; (b) guaranteed shunt patches UNCONDITIONAL (starvation over-correction)
— a patch exists only when the net's solution uses F at the shunt or Kelvin/thermal need
demands it; reachability is now the pour-first solve's job, not insurance copper's;
(c) no post-solve redundancy reap: any same-net pour piece that is not load-bearing for
the realized connectivity AND not thermally needed (the need-based mirror test) is
REMOVED. The v4 acceptance inherits this: zero non-load-bearing same-net pour copper on
a live winner.

### Single-owner sharpening (owner, 2026-07-25): DELETE-BY-DEFAULT / WHITELIST
"If it finds a solution, all of the pours that were made in pursuit of that solution get
deleted unless they are specifically REQUIRED BRIDGES or REQUIRED THERMAL SECOND PLANES."
Implementation posture: whitelist enumeration, not blacklist testing — after the solve,
enumerate the winning set (the solution's own copper per owning layer, incl. the terminal
attach pieces the path lands on; the bridges the solution genuinely uses, with their via
fields; thermal mirrors PROVEN required by the need-based test) and DELETE every other
same-net pour piece. Exploration copper, alternate-layer duplicates, insurance patches,
unused manifold pieces: gone by default.

## v4 pass 2 — implementation state (2026-07-25, LANDED; the five-part live-variant pass)

Probe record: build/pourprobe2/ (probe_winner = s510 zone/stub forensics; probe_planner =
live-skeleton endpoint/blocker analysis; probe_rate = planned-vs-fallback measurement).

**Part 1 — live-variant planner rate (root causes, all probe-measured):**
(a) `'In2.Cu': 'no-path'/'pa-blocked'` was WIDTH PHYSICS, not a corner-graph bug: 1oz
internal In2 demands 16–46mm for the heavy rails (IPC inverse at 12–25A) — no 74x59 board
holds that corridor; `_make_candidates` now diags it honestly as `width-infeasible(Nmm)`
(empty free space), and heavy corridors land on 2oz B/F as the only feasible layers.
(b) `'B.Cu': 'no-path'` at the J3/TB belts: the inflated foreign-barrel shadow extends past
the 3.2mm own-PAD approach reach, sealing the neck pocket from eroded free space — the
approach region now includes own MANIFOLD polygons and own TRACK capsules (a manifold/rail
is the "pad" of its super-terminal), so the W_NECK collar crossing is legal wherever own
copper stands. (c) THE BIG ONE — same-net locked copper: materialize's locked force rails
already connect most rail-net terminal groups (+5V_MAIN {1,2,3}; /SENSE3V3_LO ALL FIVE —
the 598mm² s510 amoeba re-solved a finished net). `_preconnect_merge` union-finds groups
over the anchor rasters (own tracks included; layers fused at THT/via cells + through
group membership — the first-cell-root shortcut measurably mis-rooted manifold gangs) and
merges pre-connected groups into super-groups whose per-layer attach (`_Group.lay_attach`)
is the member copper + connecting rail capsules — never the hollow union bbox. Corridors
are planned only for residual components; a fully pre-connected net is TRIVIAL (lays
nothing). **Measured rate on 6 live variants (before → after): planner-owned 2/9 → 5/9
(+3V3 REGION, /SENSE5V_HI newly PLANNED, /SENSE3V3_LO + /SENSE5VSB_LO TRIVIAL), overall
path_found 5/9 → 7/9 (/SENSE3V3_HI's fallback now finds a path — the fallback inherits
stage-0 manifold dicts as attach inputs via `manifold_dicts=`). The 2 residual no-paths
(+5VSB, /SENSE12V_HI) fail identically on both engines — the J3-belt width class, with
the RS1/RS2 force-rail REFUSALS (pre-existing) removing their pre-connect; they lay
manifolds only, loudly (v3 rule).**

**Part 2 — region-class nets:** `_classify_net` (structural, never name-based: >=6 served
groups, >=70% plain F-only SMD islands after gang+pre-connect merge) routes a net to
`_realize_region` — the POWER-PLANE doctrine: ONE deliberate region polygon on In2-else-B
(islands' projection + margin, shaved only by real raster obstacles, mask_to_polys
smoothing, min-width erosion invariant kept) + ONE compact pad-aware terminal via field
per island (shared `field_via_line`) + one landing per island, verified through the same
`_attach_connectivity` union-find as corridors. No tree, no bridges, no snake. +3V3
classifies region on every live variant.

**Part 3 — fallback realization discipline:** `route_overunder(chains_out=)` returns the
ordered walks; `realize_overunder_rects` draws one straight capsule cover per maximal
same-layer run (collinear-simplified centerline at required width) + ONE compact pad-aware
via field per genuine layer change (cover boxes embed the field on both layers; F pieces
clip to the shunt/manifold admit at draw time, loud). DEFAULT realization for
`synthesize_overunder_pours`; the dilated-cell smear (3-cell disks + closing = the
owner's blobs/via-lines) survives only behind `CEC_OU_SMEAR=1`. The in-pad via refusals
at lay time drop to zero by construction (the field placer slides).

**Part 4 — orphan/floating hygiene:** (a) s510 forensics: NO orphan In2 stub epidemic
(1 padless via board-wide); the owner's "stubs" read as fallback smear + FR tracks over
blobs — cured by parts 1–3; a `reap_nowhere_zones` orphan-VIA sweep (unlocked barrels
touching nothing, fresh-cycle, pour-live-gated) catches the residual class. (b) measured
exhibit: `pourplan:` fragments with fill=0.0mm² / clusters=0 survived both reaps by name
— `_nowhere_zone_verdict` now reaps ANY zero-cluster zone regardless of name (exemption
protects the sanctioned single-cluster judgment only), and `cleanup_floating_zones`
removes zero-FILL zones outright.

**Part 5 — single-owner whitelist:** `cec_slab_pour.enumerate_winning` (pure, teeth-
tested) enumerates the keep-set at the FREEZE: solution dicts; manifold pieces the
solution touches on the same layer or that embed a solution via; GANGED manifolds
(bind >=2 terminal clusters — the connectivity proof relies on them; `_build_groups`
records `gang_manifolds`, one preferred layer kept); patches only with real solution-F
use at the shunt or a solution/locked barrel to cover; no-path nets keep manifolds (v3
loud rule). Everything else dies at the freeze with a printed reason
(`report.whitelist_dropped`; measured: 10 insurance dicts dropped per live variant,
frozen state 5 lanes + 11 manifolds + 7 patches vs 12/20/8 before). `import_ses` no
longer re-derives guaranteed patches for frozen nets (the resurrection path), and the
POURFIRST artifact runs the same hygiene chain before render. Ask layers are preferences
throughout: the region layer is the solve's choice (teeth: an In2-blanketed board lands
the In2-named ask on B with zero In2 copper); corridor layer assignment was already
preference-driven. Note: the pour-first planner never CREATES thermal mirrors (each
corridor is sized per-layer by the IPC inverse, sufficient by construction), so the
whitelist's "required thermal second plane" class is exercised by the barrel-cover rule;
the legacy `_mirror_needed` machinery still governs the non-frozen path.

Teeth: tests/test_pour_plan.py (pre-connect trivial + corridor control, region shape +
per-island fields, ask-layer-preference, width-infeasible space), tests/test_overunder.py
(fields at run boundaries only, vacated layer carries nothing, rect leaner than smear,
F-admit clip), tests/test_pour_first.py (enumerate_winning: winning lane + attach
manifold survive, duplicate layer dies, bridge/barrel covers survive, gang keep,
no-path keeps manifolds; zero-cluster verdict override incl. the real-board reaper).
80/80 in-container.

**Pass 2b/2c (same day, live-wave-measured closures):** (a) local-cells F landing (a
mixed-native super-group skipped its landing under the strict native=={F} test; the
union bbox would have been a blob — the landing embeds F-anchored cells near the attach
only); (b) `_lay_attach_geom` — native attach targets the layer's ACTUAL anchored cells
(a cluster's B-nativeness can be three via cells; its bbox edge is not copper — measured
as +5V_MAIN's verify split); (c) neck length discipline — a contiguous sub-width run
beyond 4.8mm is legal only as a MINORITY of its corridor (measured degenerate case: a
9.7mm 0.8mm spine on a 10mm run passing the invariant at 20A; an absolute cap was tried
and measurably demoted /SENSE5V_HI's working plan — the ratio rule keeps it);
(d) 4-connected spine line-stamping into the connectivity verify (cell-center stamping
missed sub-cell spines entirely; naive walks stamp diagonal staircases 4-conn labeling
splits); (e) reap_nowhere_zones' pre-verdict name skip removed (the zero-cluster
override never fired — measured: a sliver-fill `pourplan:` zone survived to the
published winner) + PUBLISH HYGIENE in cec_fresh_wave (the published artifact runs the
cleanup chain itself — whichever stage wrote last is not guaranteed to have).
**Acceptance (wave s530-532, winner plain-compact-s532-polish, render
build/wave-snaps/atx-24pin-rev3/PASS2-winner-plain-compact-s532-hex.png, worklogged):**
planner-owned 6/9 (REGION +3V3 on In2 with 11 terminal fields; PLANNED +5V_MAIN,
/SENSE5V_HI, /SENSE12V_LO; TRIVIAL /SENSE3V3_LO + /SENSE5VSB_LO via pre-connect),
paths 7/9; measured on the published board: 0 zero-cluster zones, 0 zero-fill zones,
0 orphan In2 stubs, 0 padless track clusters; +5V_MAIN (solved on B) carries no In2
copper. Residual honest classes: +5VSB + /SENSE12V_HI no-path (the J3-belt width
physics, both engines agree — the corridor abstraction cannot count PARALLEL gap
cross-sections at a connector belt, the standing owner design question; force-rail
REFUSALS of RS1/RS2 remove their pre-connect); /SENSE3V3_HI neck-rejected to a
rect-realized fallback (large but corridor-width capsule copper, not smear).
