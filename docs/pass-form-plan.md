# Pass-form placement & routing — plan of record

_Owner directive (2026-07-08): "What if instead of wiring everything in one go and just
praying, we do placements and routing like a human would... in a pass form?" + "route the
important ones with high precision first alone, and then fill in the gaps cheaply."
Synthesized from two research legs: industry best-practice pass order (TI/ADI/Cadence/
Altium/IPC-class sources, disagreements flagged) and the repo self-mining report (what we
already documented, built, and broke). Companion evidence: the failure-mode ledger in §2._

## 1. Diagnosis — why "one go and pray" is the root cause

- The active pipeline routes EVERYTHING in one Freerouting call (`route_once` inside
  `route_oracle_grade`), with keepout *reservations* but no locked copper. Measured
  consequence: "the recipe KEEPOUTS over-constrain an untuned placement" (~61 unconn vs 5
  plain) — FR must solve routing and corridor-avoidance in one search.
- **TPC (`cec_router.two_pass_corridor`, :852-1097) already implements the owner's ask** —
  lock kelvin/pairs as `protect`, rip foreign, re-route around a notched reservation,
  re-pour — and measured foreign-through-pour 48→0 with kelvin held (2026-06-27). It is
  called ONLY from `cec_router.route()`; the wave pipeline (`route_oracle_grade`) bypasses
  it entirely. The corpus text (`cec_constraints.py:120`) claims TPC is load-bearing —
  currently FALSE against the live pipeline (drift to fix).
- Placement is one monolith (`synth_one`) whose ordering was won by trial: the in-code
  comment "applied LAST so nothing downstream undoes them — the lesson every seat learned"
  is the ad-hoc version of the pass discipline this plan makes structural.
- The blind audit (2026-07-08) showed the same story from the human side: the nets a human
  routes FIRST (kelvin, pairs) are exactly where the all-at-once route embarrassed itself.

## 2. Failure-mode ledger → missing pass boundaries (evidence base)

| Failure (handoff/TODO) | Missing boundary |
|---|---|
| Cluster scatter → rigid re-stamp (G6) | passives stamped before owner position was FINAL (no lock point) |
| Anchor-vs-anchor J1 crash (G4) | no validation gate at end of anchor pass |
| Anneal undoes intents (G4) | search stage not bound by declaration stage (fixed only when partition supplied) |
| 4-lever batch regression (G5) | no declared precedence between eviction and adjacency passes |
| Divider lever inert (TODO) | downstream silently overwrites upstream (no never-undo rule) |
| Box-model duality (fixed by PourPlan) | two passes derived the same geometry independently |
| THT-backside, lane-aware seats | constraints bolted on after seats committed, not honored at seat time |
| TPC bypassed | the routing pass ladder was never wired into the grader |

## 3. Design principles (non-negotiable)

1. **Ordered passes with PROGRESSIVE LOCKING** — each pass ends by LOCKING its output;
   later passes fit within, structurally unable to undo (locked refs excluded from every
   later mover; locked copper `protect`-ed through FR).
2. **Per-pass done-criteria = teeth** — a pass is complete only when its own gate passes
   on the real artifact; the next pass does not start otherwise. No end-of-line prayer.
3. **Escalate upstream, never edit silently** — a pass that cannot meet criteria emits a
   named snag to the pass that owns the fix (the documented 4-stage loop rule,
   README-cec_pcb:155). This is the repair ladder's home.
4. **Precision first, cheap fill after** (owner): critical geometry is laid
   deterministically on an uncontended board; the autorouter gets only the residual, with
   all locked copper protected.
5. **One authoritative geometry object per concern** (the PourPlan lesson): pass outputs
   are objects later passes compile views from, never re-derive.
6. **Blueprint replication is a modifier, not a pass**: place+route ONE channel cell, then
   affine-stamp N (KiCad-9 multichannel precedent keys on hierarchical containment — the
   round-4 beta schematics are already per-cable hierarchical).
7. **Human gates stay**: placement sign-off and final review are human rungs (the
   literature is unanimous; the blind-audit protocol is our instrument).

## 4. The CEC pass ladder

Format: pass — goal → existing machinery → gap → done-criteria (teeth).

### Placement
- **P0 stackup/netclass basis** → stackup() + board-manifest + netclass/.kicad_dru
  authoring → gap: none structural → criteria: every net resolves a class (RT-0 input).
- **P1 outline + mechanical/keep-outs** → build_board edges, corner radius, keepouts →
  criteria: geometry exists before any part.
- **P2 anchors (connectors by role, overhang) + mounts/fiducials** → seed_anchors +
  place_mechanical (+ fiducial emission, landed) → gap: anchor-vs-anchor gate AT THIS
  BOUNDARY (today it fires at the end) → criteria: courtyard-clean among anchors, mouths
  render-verified. LOCK.
- **P3 critical blocks: corridor spine + shunt seats + kelvin/comparator seats + ESP** →
  _seed_corridor_spine, _seat_sense_ics, _seat_antenna_ic, CAN seat → gap: seats must
  honor lane/pour + THT-backside constraints AT SEAT TIME (the bolted-on-later class) →
  criteria: kelvin-reach, comparator-adjacency, THT-backside, bodies-in-pours green on the
  seated set alone. LOCK.
- **P4 blueprint cells** (NEW primitive): compile ONE sense-cell template (shunt + INA +
  comparator + RC + decouplers as learned offsets — auto_cluster already computes
  relocatable offsets; mirror cec_sch_archetypes' shape) → stamp per rail/cable on the
  spine pitch → criteria: per-cell local DRC + adjacency gates; cells RIGID from here. LOCK.
- **P5 owned passives around remaining ICs** → derive_passive_spec + auto_cluster +
  (single, final) stamp — the re-stamp hack dissolves because owners are already locked →
  criteria: decoupler-adjacency ≤7mm functional gate.
- **P6 thermal spread review** → thermal proxy + electrothermal on placement → advisory
  now, criteria TBD by calibration.
- **P7 glue/general parts** → relative_place + anneal + legalize, movers = ONLY unlocked
  refs, bounds = intents → criteria: zero courtyard overlaps, pin-escape, courtyard-edge,
  stranded, gap-profile advisories.
- **P8 placement sign-off gate** → the full placement conjunction + render + (fresh line)
  owner eyes via the dashboard → LOCK ALL.

### Routing (mirrors it: "high precision first alone, then fill cheaply")
- **R0 rules** → netclasses/DRU from P0 (exists).
- **R1 escapes** → fine-pitch fanout (VSSOP/QFN) — partially implicit today; make explicit
  where pin-escape gate flags → criteria: every fine-pitch pin has a legal stub.
- **R2 KELVIN precision pass** → synthesize_kelvin_taps with CANONICAL datasheet geometry
  (landed 798526e: perpendicular inner-edge exit → run → one 90°) laid on the UNCONTENDED
  board, PRE-FR (today it runs post-route; moving it pre-FR + protect is the change) →
  criteria: inner-edge checker + all taps laid or named snags. LOCK (protect).
- **R3 coupled pairs** → cec_route deterministic diff-pair routing (proven June: USB pair
  0-structural headlessly) at impedance geometry from cec_impedance (fix the CAN 120Ω gap
  by construction) → criteria: pairs routed coupled, Zdiff within band, skew ≤ gate. LOCK.
- **R4 power copper** → PourPlan reservations pre-route + additive copper post-fill (our
  MEASURED pour-after-route invariant reconciles the literature's power-order disagreement
  for autorouted flows; corpus rule high-current-pour-after-route-ordering) → criteria:
  circuit-completeness (pour reaches shunt/blades), min-cross-section. LOCK.
- **R5 GND return/stitching** → cec_gnd_fanout (impedance-reducing only) + via fields +
  stitch rules → criteria: fanout audit + (future) PDN solve. LOCK.
- **R6 general fill (CHEAP)** → Freerouting on the residual ONLY, `protect_nets` = every
  locked net (the T3 plumbing; TPC generalized from corridor-scope to ladder-scope) →
  criteria: routing_complete tolerances.
- **R7 skew/length tune** → owner scorecard metrics (layers-per-route landed; skew gate
  exists) → criteria: matched groups within tolerance.
- **R8 zone fill** → ZONE_FILLER + island rules (exists).
- **R9 finishing** → prune_dangling_tracks (landed) + redundant-branch reduction (queued) +
  normalize_via_annular + silk score → criteria: silk/fp ≤1.0, no dangling.
- **R10 verification** → the oracle conjunction + thermal (mirage-guarded) + BLIND-AUDIT
  protocol for mechanism-level judgments → human sign-off.

## 5. Implementation staging

- **S1 — pass-runner skeleton** (framework): declare the ladder; each pass = (fn, locks,
  gate); progressive lock sets threaded through movers + FR protect. Mostly re-orders
  EXISTING calls under enforcement. Teeth: byte-identity when every pass mirrors today's
  order; then the boundary gates turn on one at a time (ablation discipline).
- **S2 — precision-first routing** (the big quality lever): R2/R3/R4-reservation laid
  pre-FR + protect; FR residual-only. This is TPC generalized and wired into the ACTIVE
  pipeline. A/B by blind-audit protocol.
- **S3 — blueprint primitive** (P4): template compile + affine stamp; absorbs the
  repeated-cell backlog item; KiCad multichannel as the GUI-parity reference.
- **S4 — boundary gates for P2/P3 at their boundaries** (move existing gates earlier) +
  seat-time constraint honoring (lane/THT-aware seats).
- **S5 — finishing passes + the redundant-branch pass.**
- Fix the corpus/`cec_constraints.py:120` TPC drift in whichever direction S2 lands.

## 6. Open ends
- Power-vs-critical ordering is a genuine literature disagreement; our measured
  pour-after-route rule decides it for THIS toolchain (R4 copper additive after R6? No:
  R4 lays reservations pre-FR and copper post-FR — both halves stated in R4).
- The 12vhpwr "6 cells @ exact 17.00mm" figure is a probe measurement, not committed —
  re-measure before using as the blueprint pitch target.
- TI SDAA115 (canonical tap app note) resisted text extraction — fetch raw + PDF-extract
  if verbatim numeric tap specs are wanted (the landed canonical geometry matches its
  indexed summary + the ADI Analog Dialogue rules).
