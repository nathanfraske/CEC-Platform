# Why the closed-loop PCB pipeline never closes — and what it would take (2026-06-26)

Research: workflow wf_e7bc946c (5 code-grounded researchers + synthesis). Verifies + SHARPENS the
2026-06-16 convergence-blocker analysis. Bottom line below; full agent findings in the run transcript.

## The real blocker (one sentence)
**Nothing produces a corridor-clean placement (`corridor_cross = 0`) BY CONSTRUCTION** — and without
that, the route-time corridor keepout (the keystone that fills the high-current pours solid) strands
the sense taps, so it ships default-off, the pours fragment, and there is nothing to converge to.

## Why it won't close (refined — the CLAUDE.md "domain-blind placer" story is STALE)
- **Routing is NOT the blocker.** The deterministic route converges the committed (human-placed) board:
  `kelvin_ok=true, diffpair_ok=true, drc=0` in ~18.6s. FR clunk / SWIG footguns / the FR pin are real
  but contained.
- **Two placers DO model the domain** (item -2 is wrong): `cec_synth_pipeline.py` builds a CorridorModel,
  forms corridors as tight columns, hard-vetoes hot bodies from corridors, ranks corridor-clean-first;
  `cec_place_planner.py` has w_kelvin_seat (sense IC against shunt inner edge), w_orient, w_partition,
  a CONVERGED gate + LLM hill-climb. **The actuation exists; it just never reaches cross=0.**
- **The genuine tension:** driving `clips→0` needs foreign signals to not cross the corridor pours, but the
  shared logic (ESP/CAN/LDO/per-cable detection amps) has nets that MUST reach ICs on different cables, so
  some foreign pads straddle a corridor BY TOPOLOGY. Keepout ON → pours solid (clips 4-5) but sense stranded
  (kelvin false, unconn 13-15). Keepout OFF → routable but pours fragmented (clips 17-91, never <6). The loop
  oscillates and converges to neither.
- **It's a GLOBAL min-cut problem attacked with LOCAL body-eviction + an LLM hill-climb.** A human produces
  cross=6 in minutes; machine placers stall at cross 15-24 over 384 rounds with 2 improvements. The agentic
  actuator only evicts bodies from bands (which the human already gets right) — it never PARTITIONS the
  foreign logic off the corridors.
- **Compounding:** fresh routes pile copper edge-clearance DRC (~100% of fresh DRC); `cec_fr.edge_keepout`
  exists but is wired into the placer ONLY, not the two route paths.

## What it would take — ordered path to close
1. **[S, hours]** Wire `cec_fr.edge_keepout` into `cec_router.route` + `route_directed`. Kills the ~100%
   edge-clearance DRC wall. (Function exists; one caller today.)
2. **[S-M]** Deterministic **post-route re-pour + defrag** pass re-filling the SENSEC same-net pours after
   foreign routing. Decouples the keystone from the placer — turns `clips` into deterministic cleanup (how
   the committed board reaches drc=0), and lets the keepout default ON without a perfect placer.
3. **[L, multi-day]** The irreplaceable piece: a **constructive corridor-clean seed** — deterministic netlist
   MIN-CUT partition + rigid sense-IC+shunt on-axis columns, seeding the existing placer → `cross=0` by
   construction. The region/veto/kelvin-seat machinery already exists; the LLM tier becomes a refiner.
4. **[S]** Wire the placer into `run_pipeline`, flip the keepout default-on, validate fresh cross=0 end-to-end,
   freeze a golden.
5. **[S, doc]** Fix CLAUDE.md item -2 — the "domain-blind placer" claim is false and keeps re-deferring this.

## The learning gap (why it never improves run-over-run) — ACTUATION BEFORE LEARNING
- The corpus is **judge-only**: 35 promoted entries scope to the judge (0 place/route, no compile blocks);
  the corridor/kelvin/pour rules sit in STAGING as advisory notes behind an owner re-sign that never happened.
- In-run live rules **reset empty every run**, are never reloaded, and only reweight ranking / inject prompt prose.
- The CL-13 outcome-label chain is **fully coded and NEVER fired**: 160 route runs (112 gate-fail on the exact
  pour-clip) produced 4 decision rows, 0 grade-1 settles, 0 ADV fires, empty shadow. CL-08 (the run-over-run
  engine) doesn't exist.
- **But none of this matters until the loop can ACTUATE a placement change.** Actuation first, then learning.

## Recommendation (blunt)
- **Build steps 1+2 first (days).** They converge a routable, solid-pour board on the COMMITTED placement
  WITHOUT the unbuilt min-cut placer — the cheapest existence proof of a self-closing loop, and it de-risks
  whether the L placer is even worth building.
- **Full FRESH-board closure is NOT worth chasing now.** It needs the L-effort min-cut placer whose sufficiency
  was never demonstrated (the clips<6 AND unconn<2 experiment was never run). The human-PCB split WORKS — a
  person produces cross=6 in minutes that 384 machine rounds can't beat, because corridor partitioning is
  spatial reasoning humans are cheap at and these generators are bad at. **The owner was right to revert.**
- **Make the learning chain fire AT ALL** — one CL-13 label per run costs almost nothing; the loop currently
  emits zero feedback over 160 runs. Defer the min-cut placer + CL-08 until there's a real reason to want
  hands-off fresh-board synthesis. Don't rewrite the placer; fix the doc.

## Build log — step 1 done + a SHARPER finding (2026-06-26, same day)
Built step 1 (edge_keepout) + an A/B on the committed eps EXPOSED a more precise blocker than the research framed:

- **Step 1 (edge_keepout) is wired** into `cec_router.route()` (default_planner) + `route_directed` (kos),
  SAFE/always-on, `CEC_NO_EDGE_KEEPOUT=1` off. Also gated route()'s CORRIDOR keepout default-OFF (was
  unconditional; it strands sense) — matching route_directed. **But on the COMMITTED eps it self-gates to []**
  (the connectors fill the edges → no clear strip; eps's drc=5 is LOGO/shield, NOT edge-clearance). The edge
  wall is a FRESH-placement problem, so step 1's value is on `route_directed` fresh runs, not the committed board.
- **THE REAL SNAG (empirical):** the same committed eps board converges via **cec_golden** (`kelvin_ok=true,
  diffpair_ok=true, drc=0`) but NOT via **cec_router.route()** (`kelvin_ok=false, drc=5, unconn=16`). route()'s
  route is **byte-identical (803.57mm/462 tracks) regardless of passes/opt_time/seeds/edge-keepout** → it is NOT
  an FR-effort issue.
- **Root cause located:** cec_golden runs `cec_fr.synthesize_power_copper` (F.Cu+B.Cu MIRROR pour + via field)
  after the route, which connects the SENSEC kelvin nets; `route_directed` also lays the mirror; **`route()` lays
  only the plain F.Cu `add_power_pours` and NEVER mirrors → the SENSEC_HI kelvin taps stay unconnected ("0 routed
  track segments")**. So the orchestrator strands exactly what the golden routes clean.
- **PRECISE step-2 fix (sharper than "post-route re-pour/defrag"):** give `cec_router.route()` the SAME B.Cu
  mirror (`synthesize_power_copper`) that cec_golden + route_directed already use — apply it per-candidate before
  scoring so the kelvin gate sees the connected net. That reconciles route() ↔ cec_golden and should converge the
  committed board through the orchestrator. This is a contained route()-pipeline change, NOT the L-effort placer.
- NET: the "cheap existence proof" is real but lives in cec_golden today; closing it through the ORCHESTRATOR is
  one precise change (the missing mirror), now located. Step 1 (edge) helps fresh routes; step 2 (mirror in route())
  is the committed-board unblock.

### CORRECTION (same session) — two hypotheses tested and DISPROVEN
Tested the step-2 diagnosis directly instead of shipping it; both failed:
- **The placements are IDENTICAL.** tests/golden/eps-8pin and modules/eps-8pin have the same 46 parts at the
  same positions (0 differing). So the route()-vs-golden gap is NOT a placement difference.
- **The mirror does NOT bridge it.** Applying `cec_fr.synthesize_power_copper` to route()'s stranded output left
  kelvin_ok=False / drc=5 / unconn=16 unchanged. So the "route() lacks the mirror" diagnosis (committed cccb2a2)
  is WRONG — the mirror is additive same-net copper and can't connect a kelvin tap FR never routed.
- **What's actually true:** on the SAME board+placement, cec_golden's clean harness (generate_batch single-seed
  passes10/opt20 + power_pours, NO planner/scoring/repair) routes the SENSEC kelvin; cec_router.route()'s harness
  (planner hints + _candidate_pool scoring + manager/repair loop) produces a route where SENSEC*_HI has 0 segments,
  byte-identical regardless of params. So the gap is in the ORCHESTRATOR HARNESS, not placement/mirror — narrower
  than the research framed but NOT yet pinned. Prime suspects (next diagnostic): the .kicad_dru/.kicad_pro netclass
  files differ between the two board copies (FR routing rules), or route()'s candidate scoring/repair selects a
  kelvin-stranding candidate cec_golden's single clean route avoids. Step 1 (edge_keepout) stands; the committed-
  board-via-orchestrator proof needs that one harness diff pinned first.

### RESOLVED — the audit found a dead-code bug; fixing it CLOSED the loop on the committed eps
The step-1 audit (wf_c8c9b807) caught that my route() edits landed in `default_planner`, which is DEAD CODE:
every route() caller goes through `board_spec()` (cec_router.py:957-958), which builds the region hints —
unconditionally baking the CORRIDOR keepout — BEFORE route() runs, so default_planner short-circuits. So my
edge_keepout + corridor-off never ran via route(); the "byte-identical regardless of params" was the dead code
not executing, and my "edge_keepout self-gates to []" claim was wrong (it returns 6 strips). The corridor
keepout was STILL ON for route() (via board_spec) — i.e. route()'s kelvin-stranding WAS the corridor keepout,
exactly the research's original diagnosis.

**FIX (board_spec, the live hints path):** corridor keepout DEFAULT-OFF (CEC_OVD_CORRIDOR_KEEPOUT=1 to enable),
edge_keepout always-on (CEC_NO_EDGE_KEEPOUT=1 off). **RESULT on the committed eps via cec_router.route():**

| | before (corridor on, dead-code fix) | after (corridor off + edge_keepout, live) |
|---|---|---|
| kelvin_ok | **false** | **true** ✅ |
| diffpair_ok | true | **true** ✅ |
| unconnected | 16 | 3 |
| drc | 5 | 9 — **ALL 9 are LOGO1 B.Cu** (shorting/clearance/mask-bridge vs the decorative copper logo) |
| route | byte-identical 803mm/462trk (inert) | 1049mm/546trk (genuinely re-routed) |

The 9 DRC are 100% the LOGO1 no-via-keepout/GND-assign finishing item (documented, GUI/placement-level, same
class cec_golden's golden board has pre-handled) — NOT routing. So **the ORCHESTRATOR now CONVERGES the committed
eps at the hard-gate + finishing-only bar** (kelvin+diffpair pass, DRC finishing-only) — the self-closing-loop
existence proof, via cec_router.route(), achieved by step-1's edge_keepout + turning the corridor keepout off by
default. The earlier "missing mirror" + "self-gates to []" hypotheses were wrong and are retracted; the real
unblock was the corridor keepout being on in the wrong (live) place. NEXT for full drc=0: the LOGO1 B.Cu no-via
keepout / GND-assign (a finishing pass, not the loop).

## BREAKTHROUGH (2026-06-27) — the loop was chasing an UNREACHABLE metric
Design panel wf_d53e2eab + verification. The min-cut placer turned out NOT to be a multi-day solver — it
was a wrong metric. Built + verified the fix:

- **The old corridor_cross_count is UNREACHABLE to 0.** The hub(ESP)->per-cable fan-out (DETC1 on cable1 vs
  DETC2 on cable2) is a topological x-straddle invariant: for K>=2 cables with the hub on one side, at least
  one fan-out branch MUST straddle a corridor on a single copper layer. So the 384-round hill-climb chased an
  impossible target and stalled at 15-24; the HUMAN scores 6 and can't reach 0 either.
- **The honest metric reaches 0.** The corridor keepout clips each pour to the connector-pad ROWS, not the
  full board height, so the top/bottom channels are physically clear -> a straddling net routed along a clear
  channel cuts NO pour. `corridor_cross_channel_aware` counts a straddle only when it can't escape via a
  body-clear channel. Built: `channels_of`, `_body_clear`, `channels_feasible` (bounded H-grow trigger, NOT a
  search), `corridor_cross_channel_aware` (== predicted post-route F.Cu clips).
- **VERIFIED on the REAL committed eps: OLD corridor_cross=6, CHANNEL-AWARE=0.** The human's corridor-clean
  placement IS cross=0 in the honest metric (the 6 are all channel-escapable). Plus a host unit test
  (tests/test_channel_aware_cross.py): channel-aware reaches 0 where old=1, has teeth when channels blocked.
- **So fresh-board cross=0 is achievable by construction** = reserve the channels (keep foreign bodies out) +
  a bounded H-grow when too short. NOT the multi-day solver the research feared; the residual unavoidable
  straddles route UNDER on B.Cu (CEC_ROUTE_UNDER, already built).
- **REMAINING (the actuation, well-scoped now):** wire `corridor_cross_channel_aware` as the placer's
  rank/gate (replacing the unreachable old metric) + `_channel_veto` into the anneal + the H-grow re-seed in
  synth_one; then validate a FRESH eps routes to finishing-only DRC end-to-end (route() + route-under). The
  hard insight is done + proven; this is mechanical wiring + a route-validation pass.
