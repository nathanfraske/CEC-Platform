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
