> **Historical strategy note.** This 2026-06-14 four-layer placement analysis
> is retained as measured background. It is not the current layer contract.
> The 2026-08-01 owner record permits routing on F.Cu, In2.Cu, In3.Cu, and
> B.Cu, reserves In1.Cu and In4.Cu as GND planes, and requires exact
> schematic-to-candidate signatures before route-oracle scoring. Any statement
> below that assumes a four-layer board or one inner escape layer is superseded.

HYBRID - A (domain-scored annealing) as the spine + the corridor min-cut term from C + a tightly-budgeted route-oracle confirm from D, all wired into cec_loop's run_candidates lever-1 as a "reseed" candidate. Hereafter "**the corridor-aware reseed placer**".

> **⚠ CORE-PREMISE FINDING (2026-06-14, after Phase 2 + a 24-agent adversarial audit - READ FIRST;
> supersedes the first draft of this box, which an audit corrected).** This strategy's central premise
> - that PLACEMENT can drive `corridor_cross` to ~0 - **does NOT hold for the eps topology**, but the
> honest picture is sharper than the first draft (which was measured on an ILLEGAL placement) said:
>
> - **cc=6 is a real, ANALYTIC floor for the HAND board.** The committed best-hand board scores
>   **cc=6** (15.6mm bands). It is derivable, not just empirical: the shared I²C bus (`/I2C_SCL`,
>   `/I2C_SDA`) connects U10 (the INA on cable 1) ↔ U11 (the INA on cable 2), and each INA is
>   **Kelvin-locked adjacent to its own shunt** (so it sits *inside* its band). Each I²C net therefore
>   spans from inside band-1 to inside band-2 → **4 forced crossings**; `/DETC1` + `/THRESH` add 2 → 6.
>   No placement beats 6 (verified: an automated sweep + hand-built ESP-left / ESP-between variants all
>   gave ≥ 6).
> - **The automated placer is currently WORSE than the hand board, not equal.** The first draft's
>   "identical 15.6mm corridors / cc=6, never lower / hand-quality corridors" was **measured on an
>   ILLEGAL placement** (`connector_overhang` defaulted to "none" → the tall connectors packed
>   mid-board, overlapping → residual=6; the band collapsed to ~6mm, which artificially read cc≈6). On
>   a DRC-LEGAL placement (overhang `power_able`, now the default - commit 192503d) the bands are the
>   full ~22mm and the placer's **best legal cc is 8, typically 14–24** - i.e. **1.3–4× the hand
>   board's 6.** The gap is the PERIPHERAL parts (CAN xcvr, USB, ESP, RJ45): the placer scatters them
>   into corridor-crossing positions where the hand board clusters them on the right. Closing that gap
>   is the open placement lever (the anneal soft terms + peripheral clustering below).
> - **`corridor_cross` is layer-agnostic, so its "topological invariant" framing is too strong.** The 4
>   I²C crossings are genuinely forced *in-plane* (Kelvin-locked INAs), but the metric has **no model of
>   layers or the ~9mm top/bottom channels**, so it OVER-counts what a router must actually cut. It is a
>   sound **pour-integrity / required-x-cross** predictor, NOT a placement objective that reaches 0.
>
> **So the pour-cutting (~300 °C) failure is fundamentally a route-time LAYER-ASSIGNMENT problem** -
> route each net that crosses a formed corridor on a non-pour (inner) layer. (Hypothesis, not yet
> verified on copper: the committed board is a 0-track floorplan.) **Recommended pivot: a
> layer-assignment lever at route time**, which the FR/pour machinery is positioned to do. The
> placement phases below still matter for QUALITY (legal residual, formed corridors, peripheral
> clustering to close the 14→6 gap) but will not by themselves clear the corridor. - owner decision
> point: invest in layer-assignment vs. continue placement tuning.

# Domain-aware placement strategy - eps-8pin corridor ceiling

Author: Lead PCB Architect (synthesis pass, 2026-06-14)
Target: scripts/cec_synth_pipeline.py (constructive placer) + scripts/cec_loop.py (the loop that
actually runs nightly) + scripts/cec_constraints.py (close the discover->ratify->enforce loop).
Hard gate to beat: `kelvin_ok AND diffpair_ok AND drc==0 AND pour_integrity_ok`, with `foreign_cross ~ 0`.

---

## 0. The one-paragraph thesis

The eps-8pin failure is a **placement-induced topological invariant**, not a routing inefficiency
(recon + run.log confirm it, and I re-confirmed it against the committed PCB: cable-2's corridor band
is `x[34..46.6] y[9.5..27.5]`; U30 at x~24 and U31 at x~47 **sandwich** that band, so `/DETC1 /DETC2
/THRESH` are forced across `/SENSEC2_LO`). No routing effort can undo a sandwich. The fix is to **move
the parts** - seat each detection IC on its own cable's lane and out of any neighbour's band, reserve
the `J_IN -> shunt -> J_OUT` corridor as a hard keepout, and **rank candidates by the corridor-crossing
count** so a corridor-clean placement wins the sweep. The constructive placer already has every seam
for this; it is just **domain-blind** (overlap + HPWL is its entire objective) and - the load-bearing
catch from recon - **it is not the placer the nightly loop runs**. Both gaps must close together.

---

## 1. The decision - scoring the four candidates

| Criterion | A. Domain-scored anneal | B. Rigid macro template | C. Zone min-cut partition | D. Route-as-oracle |
|---|---|---|---|---|
| **Will it break the ceiling?** | Yes, with weight tuning (soft pulls + hard veto) | Yes, by construction (strongest guarantee) | Yes, explicit min-cut objective | Yes, but only **selects** - needs a winner in the set |
| **Effort** | medium | large | large | large (route-per-candidate) |
| **Risk** | medium (SA stall / weight tuning / myopic on the 2-part sandwich) | medium (rigid; area cost; channel-height coupling) | medium (zones fight compactness; reconciliation debt) | medium-high (30-100x slower placement; oracle noise) |
| **Reuse of existing infra** | highest (≈30 lines in anneal + a model builder + sort key) | high (macro machinery exists) | medium (new partition/zone code) | high (materialize/route/score reused) but expensive |
| **Generality to other boards** | high (derived model: EPS/PCIe 2/3/12VHPWR) | high but rigid (one lane topology) | high (derived corridors) | highest (measures the gate, any failure mode) |

**Why not pure A:** A's deepest doubt (its own skeptic #4) is real - SA is myopic and the sandwich is a
**coordinated two-part move** (U30 left of band-2, U31 right of band-2) that local jitter reaches only
by luck. A soft penalty + hard veto can let the chain freeze at the band edge.

**Why not pure B:** B's structural guarantee is the strongest, but it bakes in one lane topology and
couples placement to a channel-height reservation in the size oracle - a large, rigid build that is hard
to walk back if a board wants a different sense arrangement. Over-investment for the first board.

**Why not pure C:** C's min-cut **objective term** is exactly the right signal (a continuous,
pre-route, pure-geometry predictor of the crossing) - but tiling fixed zone rectangles fights the
gen-eps-condensed 96x37 area bar and adds the most new code.

**Why not pure D:** D optimizes the *true* gate with zero proxy gap - but it is a route per candidate
(30-100x slower) and, critically, it can only **select** a winner the constructive placer must first
**create**. D's own skeptic #4 concedes it is "strongest combined with a light version of A/B."

**The hybrid takes the best load-bearing piece of each and discards the heavy parts:**

1. **A's engine** (the existing `anneal_macros` SA loop, untouched) + **A's hard corridor veto**
   (foreign bodies may never enter a band) + **A's Kelvin/thermal soft terms** - smallest delta, highest
   reuse. This is the spine.
2. **C's `corridor_cross` min-cut term** as the **PRIMARY** ranking key and a proxy-reject - the
   continuous, pre-route gradient that A's local SA needs to escape the sandwich. This is C's single
   best idea (a pure-geometry predictor) lifted **without** C's expensive zone-tiling.
3. **A seed-time corridor nudge** (seat each detection IC on its own lane's inner edge, offset out of
   the band toward its ESP-bound exit) so the candidate **set contains** a corridor-clean basin - this is
   the "light B" that A's skeptic #4 and D's skeptic #4 both say is required. It is one deterministic
   seat in `seed_anchors`, not B's full rigid template.
4. **D's route-oracle as a CONFIRM, not a ranker** - route only the **single** top candidate (after the
   geometric `corridor_cross` sort picks it) to verify `foreign_cross/pour_integrity/kelvin/drc` before
   the loop commits. One route, not N. This buys D's "no proxy-vs-reality gap" guarantee for ~1 route's
   cost, sidestepping D's killer (route-per-candidate).
5. **The cec_loop reconciliation** (the mandatory glue every candidate flags): wire the constructive
   placer into `run_candidates` as a new **"reseed"** config, so the nightly loop actually uses it.

This is decisive: **A is the spine, C's term is the brain, a light-B seat guarantees the basin exists,
D confirms the winner once.** It is the lowest-risk path that provably breaks the ceiling while staying
inside the existing, tested engine.

---

## 2. The constraint model to implement (HARD vs SOFT, made concrete)

Build **one** `CorridorModel` per synth, derived from the netlist (no per-board hardcoding), reusing
the geometry primitives that already exist. Everything below hangs off it.

### 2.1 The model (built once, in `synth_one`, before `anneal_macros`)

```
CorridorModel:
  cables: [Cable_n], one per Kelvin pair, where Cable_n =
    { hi='SENSEC{n}_HI', lo='SENSEC{n}_LO',
      j_in, j_out,                # connectors on hi (force in) / lo (force out), by _role
      shunt=RS{n},                # the 2-pad ref straddling (hi,lo) -- the SAME test as
                                  #   derive_power_pours (padcount==2 on refs_hi & refs_lo)
      sense_ics=[INA on hi/lo, INA181 on hi/lo],
      band_n = swept rect over {J_IN power pads, shunt pads, J_OUT power pads},
               inflated CLR=1.5mm on the X (signal-channel) sides only }   # narrow, not swallowing the INAs
  corridor_nets = {each cable's hi, lo}                # the only nets allowed inside its band
  HOT       = {RS*, J_IN*, J_OUT*, LDO}
  SENSITIVE = {every INA/INA181, REF3030, ESP32 U1}    # the paired INA is EXEMPT from its own band's veto
  net_role(net) in {power_corridor, gnd, sense, signal, decouple}   # from name + corridor membership
```

Derivation reuses: `_kelvin_pairs(nl)` (line 599), the `padcount==2` shunt test from
`derive_power_pours` (cec_fr.py:596-600), `_role` (line 1286), `derive_passive_spec` (line 1853).
**Important consistency property:** `band_n` is computed from the SAME pads `derive_power_pours` uses,
so the placement-time corridor and the route-time pour keepouts (`keepouts_from_pours`) are provably the
same rectangle - no drift between "where the placer thinks the corridor is" and "where FR reserves it."

### 2.2 HARD constraints (a violation REJECTS the placement / move)

| # | Constraint | Source (ratified) | Where enforced |
|---|---|---|---|
| H1 | **Corridor keepout**: no HOT/SENSITIVE **body** courtyard inside a foreign cable's `band_n` (paired-INA exempt for its own band) | `high-current-corridor-keepout` (REGISTRY :81), `high-current-pour-integrity` (hard, :576-602) | anneal accept-test veto + legalize obstacle |
| H2 | **No foreign-net cross**: `corridor_cross == 0` on any HARD pour net (pre-route geometric predictor) | derived from H1 / `_chk_pour_integrity` | proxy_reject (rejected before any route) |
| H3 | **Shunt rot=270** (HI=upper terminal) so Kelvin taps don't cross; verify pad-1 local-y < pad-2 (flip if not) | `shunt-rotation-hi-upper-terminal`, `kelvin-sense-from-inner-pad` | STAMPED at seed (never annealed) |
| H4 | **Connectors mouth-to-edge**, J_IN rot180 top / J_OUT rot0 bottom, pads on-board | `connector-mouth-faces-edge` (:edge_mm=6), `eps-pcie-jin-top-jout-bottom` | seed_anchors (already does edge role) |
| H5 | **Courtyard non-overlap** (residual==0) | existing | legalize_pack (already hard) |

H3/H4 are *frozen* (deterministic stamps, zero search). H1/H2/H5 are the veto/reject layer.

### 2.3 SOFT terms (weighted, anneal trades off; drive ranking)

| Term | Meaning | Target | Source |
|---|---|---|---|
| `corridor_cross` (**PRIMARY rank key**) | foreign-net HPWL-box straddling a non-owned band with pads on both sides | 0 | `high-current-pour-integrity` lifted to a count |
| `kelvin_inner_dist` | paired INA + INA181 sense pads to shunt INNER edge | <=3mm soft / 5mm hard wall | `kelvin-sense-adjacent-shunt` (max_mm=5), §6.8 |
| `hot_sensitive_sep` | every SENSITIVE (except paired INA) to every HOT | >=8mm | `hot-sensitive-separation` (sep_mm=8), §6.6 |
| `current_axis_offset` | shunt x to mean-x of its J_IN/J_OUT power pads | 0 (on-axis) | `high-current-path-inline`, §6.7 |
| `hpwl` (existing tiebreak) | wirelength | - | existing |

**Tension resolution (the corpus exception):** `kelvin_inner_dist` PULLS the paired INA into its band;
`corridor_cross`/`hot_sensitive_sep` PUSH everything else out. Only the paired INA is exempt from its
own band's veto - every other SENSITIVE part is evicted. This is the §6.6/§6.8 reconciliation already
ratified in the corpus; it is not a new policy.

### 2.4 PRESERVED conformance (placer must not violate by substitution)

Shunt values §6.4, RJ-45-not-Mini-Fit, pin allocation (pin7 reserved), DETECT 2.2k, TJA1051T/3, INA240
D-package, **pour-AFTER-route ordering** (the placer never pre-pours). These are gated by `intake_gate`
upstream; the placer stamps rotations/pairings, never swaps parts.

### 2.5 Gate decomposition (how the model maps to the 4-clause gate)

- `pour_integrity_ok` <- **H1 + H2** (no foreign body/net in the band) - *the direct cause of tonight's failure*.
- `drc==0` <- **H1** (no foreign cross) + **H4/H5** (pads on-board, courtyard clean).
- `kelvin_ok` <- **H3** (rot270/inner-edge) + `kelvin_inner_dist` soft term on F.Cu.
- `diffpair_ok` <- USB pair unchanged + power-escape vector reserved beside each adjacent INA (existing).

The single highest-leverage item is **H1/H2 (corridor)** - it cascades to pour islanding, drc, and the
~300C thin-neck max_T. The hybrid attacks it three ways at once (veto + reject + seed nudge).

---

## 3. Phased implementation plan

Each phase is independently testable and validated on eps-8pin. **Success metric** for the milestone
phases: a placement candidate that, when routed, reaches `pour_integrity_ok=True` AND `drc==0` with
`foreign_cross ~ 0`. We start with the **smallest phase that PROVES the thesis** (a measurable drop in
corridor crossings), so a regression or a wrong model is caught in minutes, not after a 30-min route.

All new functions are **top-level and picklable** (spawn-pool requirement, like `synth_one`).

### Phase 0 - Instrument the failure (PROVES the thesis; ~1 hr; no behaviour change)

The cheapest possible first cut: a pure measurement that turns "foreign_cross" into a number the placer
can read, validated on the committed board.

- **`cec_synth_pipeline.py` NEW** `corridor_cross_count(pads_by_net, bands, corridor_nets) -> int`:
  for each foreign net (role==signal), `box = bbox(pads)`; for each `band_n` the net does NOT own, add
  1 per band the net's pad-box straddles **with pads on both x-sides** of the band. Pure geometry on the
  `pads_by_net` the proxy already builds. (Mirror of `_chk_pour_integrity`'s cut, lifted to placement.)
- **`cec_synth_pipeline.py` NEW** `build_corridor_model(nl, P) -> CorridorModel` (§2.1). Reuses
  `_kelvin_pairs`, the `padcount==2` straddle, `_role`.
- **`cec_constraints.py` NEW** `@checker("high-current-corridor-keepout")` and
  `@checker("shunt-inline-in-corridor")` - the two registry entries (:77-84) that **declare a directive
  but have no checker function today** (recon root-6). Reuse `_chk_pour_integrity`'s geometry to detect
  a foreign track/via inside the `J_IN->shunt->J_OUT` swept rect on the ROUTED board. This closes the
  discover->ratify->enforce loop and gives the loop a real post-route corridor score.

**Validation (Phase 0):** run `build_corridor_model` + `corridor_cross_count` on the committed
`eps8pin-module.kicad_pcb`'s netlist+placement -> assert it returns `>= 3` (the known `/DETC1 /DETC2
/THRESH` crossings) and that `/CAN_L` (x>62) contributes **0** (it must not be a false offender - recon
confirmed CAN does not structurally cross). This is the falsifiable proof the model sees the real
problem before we change any placement. New `tests/test_corridor_model.py`.

### Phase 1 - Corridor-aware ranking + seed nudge (BREAKS THE CEILING; ~1 day)

The minimal set that produces a corridor-clean candidate and selects it.

- **`cec_synth_pipeline.py` CHANGE** `synth_one` (line 1817): after `_classify`, **stamp shunt rot=270**
  (H3, with the pad-1-local-y verify/flip); build the `CorridorModel` after the macro step (~line 1880);
  compute `corridor_cross = corridor_cross_count(...)` on the final `P` and attach it to the returned
  `Candidate` (add a `corridor_cross: int = 0` field to the `Candidate` dataclass, line 1804).
- **`cec_synth_pipeline.py` CHANGE** `seed_anchors` (line 1481): after connector edge-seating, **seat
  each detection/sense IC on its OWN cable's inner edge with a y-offset OUT of the band** toward the
  free top/bottom channel (the light-B nudge - guarantees the basin exists). One deterministic seat per
  sense IC keyed off `CorridorModel` (pass the cable->IC map in). The paired INA stays adjacent (inner
  edge); the §6.13 comparator (U30/U31) is offset to the channel.
- **`cec_synth_pipeline.py` CHANGE** `place_candidates` sort key (line 1927):
  `(c.residual, c.proxy["hpwl"])` -> `(c.residual, c.corridor_cross, c.proxy["hpwl"])`. A corridor-clean
  candidate now ALWAYS beats a sandwich, regardless of HPWL (today they tie at residual=0).
- **`cec_synth_pipeline.py` CHANGE** `proxy_reject` (line 1258) / `placement_proxy` (line 1243): surface
  `corridor_cross` into the proxy dict and **hard-reject** any candidate with `corridor_cross>0` on a
  HARD pour net **before** routing (never waste a route on a known-bad placement - H2).

**Validation (Phase 1):** `place_candidates(cfg, 96, 37, seeds=(0..7))` on eps-8pin -> assert the
**winning** candidate has `corridor_cross == 0` and the detection ICs sit outside `y[9.5..27.5]`.
Materialize the winner and run ONE `route_once` + the new corridor checker -> assert `foreign_cross`
dropped from ~11 to ~0 and the `/SENSEC2_LO` pour fills as ONE island. **This is the milestone that
proves the ceiling is broken.** If the winner still crosses, the seed nudge needs more channel offset
(tunable, board-specific) - caught here, cheaply.

> **IMPLEMENTATION NOTE (2026-06-14, "Phase 1a" + its audit remediation, claude/placement-corridor / PR #60).**
>
> _First cut (RETRACTED):_ with the rank key wired, `place_candidates(cfg, 96, 37, seeds=0..7)` showed the
> new `(residual, corridor_cross, hpwl)` sort picking a `cc=0` winner where the old `(residual, hpwl)` sort
> picked `cc=4` - and I claimed "the ranking alone breaks the ceiling." **A 4-skeptic adversarial audit
> proved that claim is a MEASUREMENT ARTIFACT and it is withdrawn.** The constructive placer does NOT form
> corridors: it leaves the shunts ~24 mm off their connectors (RS1 at x≈7.5, J_IN1 at x≈30.8) and does not
> column-align J_IN/J_OUT per cable, so the band (computed over the cable's pads) inflates to **~73 mm on a
> 96 mm board**. A near-board-wide band cannot be straddled, so `cc=0` is trivially true - it does NOT mean
> the placement is corridor-clean. The ranking does not yet break the ceiling.
>
> _What Phase 1a actually is, after remediation:_ the corridor rank-key **plumbing**, made HONEST.
> - **Band corrected** to the J_IN→shunt→J_OUT **connector + 2-pad-shunt pads only** (the INA SMD sense pads
>   are excluded) - this matches `cec_fr.derive_power_pours`, the earlier "same rectangle as the pour" claim
>   having been false (it included the INA taps). On the committed (well-formed) board this still gives the
>   real ≥5 crossings / `/CAN_L`=0; on raw synth output the band is degenerate.
> - **Degeneracy guard** (`build_corridor_model(board_w=)` / `corridor_cross_count(board_w=)`): a band wider
>   than ~½ the board is marked `formed=False` and SKIPPED, so an unformed corridor scores 0 **inertly**, not
>   as a false clean. The rank key therefore does nothing on raw synth output (all `cc=0` → falls back to
>   HPWL) and only discriminates once corridors are **formed** (Phase 2) or on a well-formed board.
> - **Determinism fixed**: `relative_place`/`anneal_macros` iterated hash-randomized sets (`nbrs`, `hot`), so
>   `corridor_cross` varied across processes (`compact s6` ∈ {0,1,2}); the iterations are now `sorted()`.
> - **Checkers scoped**: `shunt-inline-in-corridor` / `high-current-corridor-keepout` now **N/A on shared-bus
>   boards** (24-pin / 12VHPWR J3/J4 serve every pair → the per-cable model doesn't apply, a Phase-5 per-pin
>   variant) and exclude the INA sense nets (`_sense_nets`, incl. 12VHPWR `/IN_P/_N`) - they were false-FAILing
>   on every routed 12VHPWR/24-pin/EPS board. Plus an opt-in `proxy_reject(corridor_max=)`, default OFF.
>
> **So the real ceiling-break is NOT done; it needs Phase 2 to FORM the corridor** (the `current_axis_offset`
> term pulls the shunt onto the J_IN→J_OUT line; the connector-alignment seat aligns J_IN/J_OUT; then the
> band is tight and `corridor_cross` discriminates) - and Phase 3 to route-confirm. Phase 1a's standing value
> is the honest measurement tooling + the bug fixes, proven on the committed board, not a ranking win on synth
> output. The deferred `seed_anchors` channel nudge and **H3 shunt-rot270 stamp** fold into that Phase-2 work.

### Phase 2 - Domain cost in the anneal + hard veto (HARDENS it; ~1 day)

Phase 1 ranks; Phase 2 makes the SA itself avoid the corridor and keep Kelvin/thermal so the win is
robust across seeds (not just luck).

- **`cec_synth_pipeline.py` CHANGE** `anneal_macros` (line 1686): add `model=None, weights=None` params.
  Inside `cost(r)`, after the existing `_ov_area + alpha*HPWL`, add (each term reads ONLY the moved
  macro + its fixed partners, preserving O(1)/step):
  - `w_corr  * corridor_penetration(r, model, P)`  (segment-to-ESP inside a foreign band - A's term 1)
  - `w_kelv  * kelvin_inner_dist(r, model, P)`     (soft barrier, paired INA only)
  - `w_therm * hot_sensitive_overlap(r, model, P)` (8mm, replaces the crude 4mm hot-from-hot nudge)
  - `w_axis  * current_axis_offset(r, model, P)`   (shunt on the J_IN->J_OUT line)
  Then, in the accept test, BEFORE the Metropolis line (1730), add the **hard veto**:
  `if hard_corridor_violation(r, model, P): P[r]=(ox,oy,orot); T*=cool; continue` - a HOT/SENSITIVE body
  entering a foreign band is rejected unconditionally (H1), independent of temperature.
- **`cec_synth_pipeline.py` CHANGE** `synth_one`: pass `model` + `cfg.params.get("domain_weights",
  DEFAULTS)` into `anneal_macros`. Weights live in `cfg.params` (board-specific, tunable, logged - NOT a
  platform default; mirrors `BOARD_PARAMS` and the human-ratification boundary).
- **`cec_synth_pipeline.py` CHANGE** `legalize_pack` (line 1601): accept an optional `forbidden=[rect]`
  appended to `placed` so movable control parts are pushed out of corridor bands during legalization
  (belt-and-braces with the anneal veto).

**Validation (Phase 2):** sweep all 3 strategies x 8 seeds on eps-8pin -> assert ALL winning candidates
across seeds reach `corridor_cross==0` (robustness, not luck), `kelvin_inner_dist<=5mm` (kelvin_ok wall
held), and no SENSITIVE part within 8mm of a shunt. Confirm SA did not stall (residual==0). If the SA
oscillates at the band edge, the weights need calibration - a `domain_weights` bump is board-specific
and logged (lever-2 territory only if it must change a ratified *threshold*, which it does not here).

### Phase 3 - Route-oracle CONFIRM on the winner (PROVES the gate; ~0.5 day)

One route, not N - D's guarantee for D's cost avoided.

- **`cec_synth_pipeline.py` NEW** `confirm_winner(cand, cfg, tmp) -> dict`: materialize the **single**
  top-ranked candidate, `derive_power_pours`, `keepouts_from_pours + kelvin_keepouts`, ONE
  `route_once(passes=8, opt_time=12)`, then `cec_score.score` + `corridor_cross_count` on the routed
  board. Returns `{gate_pass, foreign_cross, kelvin_ok, diffpair_ok, drc, unconnected}`. Lexicographic:
  if the winner fails, fall to the 2nd candidate (cap at top-3 to bound cost).
- **`cec_synth_pipeline.py` CHANGE** `place_with_consent` / `run_sweep`: behind
  `cfg.params.get("route_confirm", True)`, return the route-confirmed winner.

**Validation (Phase 3):** end-to-end on eps-8pin -> the returned board passes `kelvin_ok AND
diffpair_ok AND drc==0 AND pour_integrity_ok` with `foreign_cross~0` and `max_T` back at the wide-pour
baseline (not the ~300C thin-neck). This is the full gate beaten on a real route.

### Phase 4 - The cec_loop reconciliation (MAKES IT RUN NIGHTLY; ~0.5 day; MANDATORY)

The recon's #1 finding: the nightly loop runs `cec_place.refine` (nudge-only), not this placer. Without
this phase the work is correct but **dormant**.

- **`cec_loop.py` CHANGE** `run_candidates` (line 213): add a third config `{"_tag": "reseed",
  "reseed_corridor": True}` to the default sweep (alongside `tight`/`loose`). It competes on the same
  `_score` key `(#hard_fails, #total_fails)`.
- **`cec_loop.py` CHANGE** `run_loop` (line 48): when `params.get("reseed_corridor")`, BEFORE the iter
  loop, replace the `shutil.copyfile(src, place)` (line 56) seed with a from-scratch corridor-aware
  placement: call `cec_synth_pipeline.place_with_consent(cfg, W, H, route_confirm=True)` ->
  `materialize(winner, cfg, place)`. The board size W/H comes from the committed board's edge bbox (or
  the size oracle). Then the existing place->route->check loop runs UNCHANGED on the re-seeded board -
  its route-time keepouts (`keepouts_from_pours`, `kelvin_keepouts`) now have legal around-paths because
  the placement opened the channel.
- Gate it: `reseed_corridor` defaults **off** platform-wide; eps-8pin opts in via
  `BOARD_PARAMS["eps-8pin"]["reseed_corridor"]=True` (board-specific, ratified choice - §5).

**Validation (Phase 4):** `python3 scripts/cec_loop.py --board eps-8pin --candidates` -> the `reseed`
candidate wins on `_score` (0 hard_fails), and `run_candidates` reports `cleared_wall=True`,
`escalate_to_human=False`. Compare the `tight`/`loose` (nudge-only, committed floorplan) candidates,
which still FAIL on pour_integrity - demonstrating the reseed is the lever that cleared the wall.

### Phase 5 - Generalize + freeze (after eps-8pin passes)

- Run the same path on **PCIe-2port / PCIe-3port** (identical HI/LO corridor structure, same
  `derive_power_pours`) -> confirm `corridor_cross==0` selection generalizes with no per-board code.
- **12VHPWR** caveat: its 6 lanes share one J3/J4 (not per-cable connectors), so the
  `J_IN{n}/J_OUT{n}` pairing breaks - needs a per-pin corridor variant. Flag as a follow-up, do NOT
  block eps/PCIe on it.
- Add the eps-8pin route-confirmed board as an `SB-08`-style golden so a future placer change that
  re-breaks the corridor fails CI (the new `high-current-corridor-keepout` checker is the teeth).

---

## 4. Files & functions touched (summary)

| File | Add | Change |
|---|---|---|
| `cec_synth_pipeline.py` | `corridor_cross_count`, `build_corridor_model`, `corridor_penetration`, `kelvin_inner_dist`, `hot_sensitive_overlap`, `current_axis_offset`, `hard_corridor_violation`, `confirm_winner` | `Candidate` (+corridor_cross field), `synth_one` (stamp rot270, build model, score), `seed_anchors` (channel seat), `anneal_macros` (domain cost + veto), `legalize_pack` (forbidden rects), `placement_proxy`/`proxy_reject` (corridor_cross), `place_candidates` (sort key), `place_with_consent`/`run_sweep` (route_confirm) |
| `cec_loop.py` | - | `run_candidates` (+reseed config), `run_loop` (reseed seed path), `BOARD_PARAMS["eps-8pin"]` (reseed_corridor) |
| `cec_constraints.py` | `@checker("high-current-corridor-keepout")`, `@checker("shunt-inline-in-corridor")` | - |
| `cec_pcb.py` | - | none required (geometry primitives reused via `courtyard_bbox`/`pad_global`) |
| `tests/` | `test_corridor_model.py`, corridor checker fixtures | - |

No new files in `scripts/`. The anneal engine, legalizer, spawn-pool sweep, materialize, score, and
route are all reused. `oracle/route_confirm` default keeps every existing caller byte-identical when off.

---

## 5. Risks + the human-ratification boundary

**Top risks (and the mitigation already in the plan):**

1. **SA weight tuning (A's skeptic #1).** `kelvin` pulls the paired INA in while `corridor`/`thermal`
   push everything out; mistuned weights stall the chain. *Mitigation:* the corridor is a HARD veto +
   pre-route reject (not a soft tug), the paired INA is veto-exempt, and Phase 1's seed nudge means the
   SA starts in a corridor-clean basin - it only has to *hold* it, not *discover* it. Weights are
   board-specific in `cfg.params`, calibrated in Phase 2's seed sweep.
2. **Geometric `corridor_cross` is a proxy for a real route (C's skeptic #4 / D's honesty).** A net whose
   pads are both outside a band could still detour through it. *Mitigation:* Phase 3's route-confirm
   verifies the WINNER on a real route before the loop commits - the geometric term ranks, the route
   adjudicates. The route is the final arbiter, exactly as CLAUDE.md's sub-agent-routing rule demands.
3. **Reconciliation is load-bearing (recon #1).** Phase 4 is mandatory; without it the placer is dormant.
   It changes which placer the nightly loop trusts, but only behind the per-board `reseed_corridor` flag.
4. **INA181 own-Kelvin regression (A's skeptic #3).** Moving U30/U31 to the channel must not strand the
   INA181's short Kelvin. *Mitigation:* `kelvin_inner_dist` covers the INA181 pair independently in the
   model; Phase 2 validation asserts both pairs' inner-dist <= 5mm.
5. **Area cost.** Channel-seating the detection ICs + 8mm separation may push the board past the
   gen-eps-condensed 96x37 bar. *Mitigation:* the size oracle can grow H if the channel is too thin;
   accept a modest area increase - a routable board beats a smaller unroutable one.

**The human-ratification boundary (CLAUDE.md "SET IN STONE 2026-06-07).** This whole strategy IS
**lever 1** - "go back to the top and regenerate a PLACEMENT CANDIDATE" to clear the wall WITHOUT a
design change. The corridor-aware reseed is automatic lever-1 candidate regeneration; it changes no
ratified *threshold*, no stackup, no footprint, no locked decision. The new constraints
(`high-current-corridor-keepout`, etc.) are **already ratified** in `cec_constraints.REGISTRY` and the
corpus - this plan *compiles them earlier* (seed-time), it does not author new policy.

The placement result is **BOARD-SPECIFIC by default**: `reseed_corridor=True` and any `domain_weights`
live in `BOARD_PARAMS["eps-8pin"]`, NOT as a platform default. **Lever 2 (owner escalation) fires only
if** the route-confirm still fails after candidate regeneration AND the only remaining fix is a ratified
change - e.g. the channel cannot be opened without **loosening the §6.8 Kelvin target** (the registry
`max_mm` / `kelvin_tighten_mm`) or **growing the board past a ratified size target**. In that case
`run_candidates` already returns `escalate_to_human=True`; the owner ratifies the board-specific
loosening, logged with its board scope, and we do NOT silently relax the threshold to "get it to pass."

---

## 6. The smallest next action

Implement **Phase 0** first (the `corridor_cross_count` + `build_corridor_model` + the two missing
checkers + `tests/test_corridor_model.py`). It is ~1 hour, changes no placement behaviour, and its pass
criterion - "the model reports >=3 crossings on the committed board and 0 for /CAN_L" - is the
falsifiable proof that the domain model sees the real ceiling before we spend a day moving parts. If
Phase 0's number is wrong, every later phase is built on sand; if it's right, the path to the gate is
mechanical.
