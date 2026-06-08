# Local compute exploration — putting the workstation to work on CEC

Status: **plan / capability build-out** (chosen scope, 2026-06-07). Sequenced Phase 0 → 3.
This is a planning/reference doc, not a locked decision. It does not resolve any open
question (OQ-*); where physics informs an OQ it is surfaced as OQ input, per CLAUDE.md.

## Why this doc exists

The goal: use the local workstation (RTX 5090 32 GB, 192 GB RAM, Core Ultra 7 265K
20 cores, Windows 11) effectively for the CEC pipeline — local agent swarms, higher-
resolution physics, and a learned policy off the Freerouting candidate corpus. An
adversarially-verified research pass (11-agent workflow + an OrthoRoute/Docker agent)
produced the calibration below. The headline correction:

> **The binding resource is cores + RAM, not the GPU.** The compute plane is CPU/RAM-bound
> (one ~0.5 GB Freerouting JVM per core); the 5090 is idle in the current pipeline. Its real
> jobs are (1) local LLM inference for the control-plane judge tiers and (2) ML on the
> DecisionLog corpus — **not** classical FEM (CPU/FP64) and **not** a from-scratch RL router.

## Corrected resource map

| Hardware | Real job here | Not its job |
|---|---|---|
| 20 cores + 192 GB | Freerouting JVM swarm (throughput engine, ~1 JVM/core) + all FEM (Elmer/scipy electrothermal is CPU, FP64) | — |
| RTX 5090 (32 GB) | (1) local LLM inference for judge tiers; (2) ML for a candidate surrogate; (3) *maybe* an OrthoRoute experiment | Classical FEM (FP64-bound, overhead-dominated at this board size); speeding up Freerouting/DRC |

## Adversarial verdicts (the calibration)

- **GPU-FEM gives higher-res analysis than CPU — REFUTED.** DC IR-drop / current-density /
  steady electrothermal on a 4-layer board is small-DOF, overhead-dominated on GPU, FP64-bound
  (5090 ≈ 1.6 TFLOPS FP64 vs ≈105 FP32). The realistic OSS path (Elmer) is CPU-only. RAM + cores
  are the higher-resolution lever.
- **Local LLMs replace the control tiers without worse boards — PARTIALLY HOLDS.** True for the
  *gated* manager/worker slots (hard gates + independent DRC own outcome quality). Keep cloud
  Opus/human for ungated structural re-plan. Do not fine-tune on 9 boards.
- **A learned policy off the DecisionLog beats Freerouting+gates as a quick win — REFUTED.** 9
  correlated boards + zero committed logs is far too little; the only published winner
  (DreamerV3+FR, ESA 2026) is online world-model RL = GPU-weeks. The defensible learned win is a
  *supervised surrogate ranker*.
- **The whole investment pays off for ~9 boards — REFUTED on pure ROI**, which is why the chosen
  framing is **capability build-out**: the tooling + corpus compound across future boards.

## The substrate — a Linux container home for the compute plane (Phase 0)

Confirmed working on this box; improves the *current* loop and is the prerequisite for
vLLM/PyTorch/openEMS.

- WSL2 ≥ 2.7.0 + Docker + NVIDIA Container Toolkit; driver ≥ 576. `.wslconfig`: `memory=128GB`,
  `processors=18`. Clone the repo on the **ext4 WSL home, not `/mnt/c`** (DSN/SES is many-small-
  file churn).
- **Headless Freerouting**: official image `ghcr.io/freerouting/freerouting` runs fully headless
  as a REST server (:37864, JRE 25) — **deletes the Windows interactive-desktop hack** in
  `docs/self-hosted-router.md` (no Xvfb, no Session-0 problem).
- **~3 containers sharing `--gpus all`** (5090 is not MIG-capable → MPS or time-slice): *routing/
  KiCad* · *FEM* · *inference (on-demand)*. Don't colocate a VRAM-hogging vLLM server with a CUDA
  FEM/router job. Judges default to deterministic, so the inference container is off most of the
  time and FEM/router can take the whole GPU.
- **Validate:** `kicad-cli` has no Specctra export; the DSN/SES round-trip rides the deprecated
  SWIG `pcbnew` bindings (`cec_fr.ExportSpecctraDSN`/`ImportSpecctraSES`). Works in a Linux KiCad
  10 install; note an eventual migration to the KiCad **IPC API server**.
- **Start persisting** `DecisionLog` JSON to a `build/route/*-decision-log.json` corpus (today
  emitted and discarded) — prerequisite for Thrust C.

> **VALIDATED in-container (2026-06-07, WSL2 on the workstation).** The substrate is up and proven
> end-to-end. The one real blocker found + fixed: Freerouting 1.7.0 needs the **FULL** `openjdk-21-jre`
> (the `-headless` JRE omits `libawt_xawt.so` and forces `java.awt.headless=true` → `HeadlessException`
> on every route, even with a live Xvfb — it's a Swing app). `docker/Dockerfile.routing` now installs
> the full JRE + `docker/xvfb-entrypoint.sh` runs a persistent Xvfb (`DISPLAY=:99`, so `cec_fr` skips
> `xvfb-run`); `compose.yaml` sets `init: true`. Confirmed from a clean rebuilt image: `eps-8pin`
> routes 2 seeds in parallel (~14 s), **`kelvin_ok` + `diffpair_ok` pass**, `drc=4` (the documented
> LOGO1 + shield-tab floor); DecisionLogs persist + accumulate under `build/route/corpus/`; GPU
> passthrough works (`nvidia-smi` sees the RTX 5090, 32 GB, driver 595.97). The Phase-1 `cec_dcir.py`
> DC IR-drop solver also runs in-container (6/6 nets on the 24-pin board; 4/4 on the routed EPS, where
> it flags a real `SENSEC2_LO` pour neck — 337 mV / ~2870 A/mm²). **Still open:** the headless
> Freerouting REST service binds `127.0.0.1` only (Task #2 host-bind, see `docker/README.md`).

## Thrust A — Local agent swarm (hybrid control plane)

> **MANAGER TIER WIRED + VALIDATED in-container (2026-06-07).** The local vLLM judge is live on the
> 5090. vLLM **0.22.1** (torch 2.11/cu13) runs on Blackwell **sm_120** (cap 12.0) in WSL2 — verified
> bf16 compute + serving. Model: **`cpatonn/Qwen3-Coder-30B-A3B-Instruct-AWQ`** (16.85 GiB AWQ, MoE
> 3B-active; the *official* `Qwen/...-AWQ` repo is gated → 401, so the public community AWQ is the
> pick), served as `cec-judge` (`docker/compose.yaml` `inference` profile, `--enforce-eager`,
> `--gpu-memory-utilization 0.85`, ipc=host). `scripts/cec_judge_local.py` adapts it into
> `cec_router`'s `manager=` slot via vLLM **guided JSON** constrained to the `Verdict` schema, FAIL-SAFE
> (any error/timeout → `default_manager`) and unable to widen the safety envelope (`route()` only
> accepts a `gates_pass` candidate; an LLM `accept` on a non-passing board is downgraded to `repair`).
> Wired through `cec_router.py --judge local` (+ `CEC_VLLM_URL` on the routing container). Validated:
> `/v1/models` serves `cec-judge`; a gate-passing finishing-residual candidate → the judge returns
> `accept` with a correct rationale; a full `eps-8pin` route ran with the local judge in the loop
> (`[judge:local] all -> repair: DRC count is 4 but require_drc_zero=True` — a correct verdict, tier
> `local:qwen3-coder-30b-awq`).
> **ON-DEMAND GATE (the server is profile-gated, never auto-started — it holds ~0.85× VRAM while up):**
> `cec_judge_local.ensure_up()` lazily starts the service + polls ready + warms the grammar;
> `shutdown()` frees the VRAM. `scripts/route-local.sh <board> [args]` is the one-command gated path
> (spin up → warm → route → stop), `python3 scripts/cec_judge_local.py up|down|warm|status` the manual
> control. Verified: a gated route spun vLLM up on demand (ready 43 s from cache, grammar warm 1 s),
> judged in-loop, then stopped → VRAM back to 2.5 GB. The cold first-compile is absorbed by the
> warm-up (then ~2 s/call); the manager is fail-safe (any error → `default_manager`). **Still hybrid:**
> only the manager tier is local; planner/escalator structural re-plans stay cloud-Opus (below).
>
> **SWARM + full-sweep validation (`scripts/cec_sweep.py`, 2026-06-07).** The batched server serves a
> concurrent judge SWARM: **16 judges in 1.75 s — 9.5× over serial, 16/16 valid**, correctly split
> 8 `accept` (gate-passing contexts) / 8 `repair` (diff-pair-fail contexts) — confirming the Thrust-A
> "one batched server, not many" throughput claim. Full sweep: the constraint registry runs clean
> (`ERROR=0`) on all 9 boards; the 3 interposers route (eps → drc=4 floor, kelvin+diff pass; PCIe route
> but their Kelvin needs the `cec_hc` pass via `cec_loop`). LESSON baked into `cec_sweep`: route the
> boards SERIALLY — running multiple `cec_router` processes at once oversubscribes the shared Xvfb /
> FR JVMs and starves some routes to 0 candidates (the concurrent *judge* swarm is the `swarm_judge`
> path, not parallel routes).
>
> **TRUE AGENT SWARM -- manager + worker + dispatch tiers as concurrent voted panels (2026-06-07).**
> The control plane is now a swarm of local agents, not a single judge: `make_manager_swarm` (the
> `cec_router` manager slot) fires N concurrent agents each with a DISTINCT LENS (safety / finishing /
> progress) and VOTES conservatively (accept needs a true majority AND a gate-passing candidate);
> `make_worker_swarm` (the worker slot) fires N concurrent agents that propose repair effort,
> aggregated to a bounded consensus; `make_dispatch_swarm_tier` is the parallel "Haiku swarm" rung for
> `cec_dispatch.agent_route`. All fail-safe (-> the deterministic policy). Wired via
> `cec_router.py --judge local --swarm N` and `cec_dispatch.py agent-route --swarm`. Full-gamut run on
> eps (panel 3): the manager panel voted `{repair:3}` while the worker swarm escalated effort
> (`passes 8->15->25`), and at it3 the **progress lens diverged to `escalate`** (`{repair:2,escalate:1}`)
> -- catching the stall a single judge would miss, before Kmax did; the dispatch ladder ran the same
> way (`request_more` x2 then a budget-lens `escalate` divergence). `cec_synth_pipeline.route_swarm`
> passes `manager=`/`worker=` straight through, so the same swarm drops into the synthesis pipeline.
>
> **OPUS-TEAM x LOCAL-SWARM stress test + bounded runner (2026-06-07).** A team of cloud-Opus agents,
> each driving a local swarm on the box, was stress-tested. Enablers: `cec_dispatch.request_candidates
> (where='runner')` is now real -- THIS system's compute plane (not GitHub Actions), gated by
> `runner_slot()`, a cross-process flock semaphore (`CEC_RUNNER_SLOTS`, default ~cores/4) that bounds
> total concurrent Freerouting jobs so a team can't lock the box. Capacity ramp: the single batched
> vLLM serves **~48 concurrent judge calls @ ~36/s, 0 errors, 23% GPU util** (~40x over serial) -> the
> GPU has ~4x headroom and is NOT the team bottleneck. A 3-Opus-agent team (one per interposer board,
> via a Workflow) routed all three concurrently through the local swarm + bounded runner in 88/121/133 s,
> **zero errors**, with the box healthy throughout (3 runner slots held, 6 FR JVMs, load ~5.5/18 cores).
> **HONEST value verdict:** the architecture WORKS and is SAFE (the swarm cannot widen the safety
> envelope by construction; the bounded runner contains the CPU), and the *parallelism* is a real
> latency win. BUT this run did NOT prove the swarm adds DECISION value: all three boards took the
> IDENTICAL ladder (`request_more` x3 -> budget-forced escalate -> the cloud Sonnet tier made every
> `accept`); the local Qwen lenses never independently converged on accept or differentiated the boards,
> and the round-3 "divergence" was the BUDGET counter, not semantic reasoning. **Binding bottleneck =
> CPU-FR slots** (~4 concurrent routes on ~18 cores), not the GPU and not cloud-agent count. **Where it
> pays:** a cheap local-swarm TRIAGE filter that handles the easy "keep routing" cycles for ~free and
> reserves the paid cloud tier for gate-relevant/structural cases. **To actually prove the swarm's
> judgment** (the open follow-up): re-run on a scenario where the correct calls DIFFER per board
> (one accept-now, one real-repair, one structural-escalate) -- identical-outcome boards can't show it.
>
> **DECISION VALUE PROVEN + the CASCADING SWARM (2026-06-07).** The follow-up is done:
> `cec_judge_local.differentiated_test` feeds the swarm three contexts whose correct call DIFFERS and
> it returns **accept / request_more / escalate -- 3/3** (`cec_judge_local.py diff-test`). Two fixes
> made it sound: (1) DIMENSION-AWARE voting -- each lens judges a different dimension, so the
> escalate-authority lens (structural/progress) owns escalate as the safety lens owns accept (a naive
> majority can never escalate on a lone qualified vote); (2) a VERIFY guard (`_escalate_corroborated`)
> -- a structural escalate is honored only when the METRICS corroborate (DRC stalled = >=3 identical
> recent values, or a locus shorting two DIFFERENT functional nets), which stopped the lens
> over-escalating a still-improving board (the 2/3 failure before the guard). So the swarm is NOT just
> a "route-N-then-escalate" policy -- it makes distinct, correct calls. The **full cascade** is then
> wired (`cec_cascade.py`): PLACE-swarm (`make_placement_swarm` -- the same panel on a placement's
> constraint metrics) -> ROUTE-swarm (manager panel + worker swarm) -> FEM (`physics_gates`: J/dT/T/
> via/shunt) -> APEX, which classifies the escalation that comes back UP: release-ready (sign) |
> design-change lever-2 (a FEM over-temp re-route can't fix -> a human stackup/copper decision) |
> cascade-down. Verified end-to-end on eps (deterministic + swarm): PLACE accept -> ROUTE drc=4 floor
> -> FEM 5 over-temp flags -> APEX correctly escalates the 40 A thermal as a **lever-2 human design
> decision** (the §6.7 / OQ-10 boundary), not a re-route. This is the discover->ratify->enforce ladder
> with a local swarm at every tier and the human/Opus at the apex.

Best GPU use; unlocks routing depth. The deterministic `default_manager` never accepts
non-perfect DRC, which is why `route_swarm` is pinned to `max_iters=1`.

- One batched **vLLM** server, one model: Qwen3-Coder-30B (AWQ-4bit, ~16–20 GB, ~1,150 tok/s
  aggregate @16 concurrent). Not many small servers; not a 70B (won't fit usably). Run **AWQ/BF16,
  not FP8/FP4** — Blackwell FP8 tensor cores aren't exposed through WSL2 dxgkrnl yet (FP8 ~3×
  slower emulated).
- Wire via existing seams: `cec_router.make_subagent_policy(decide_local)` → `route()`'s
  `manager=`/`worker=`; `cec_synth_pipeline.resolve(tiers={'manager': local, 'frontier':
  cloud_opus})`; the `cec_dispatch.agent_route` budgeted ladder. Use vLLM **guided JSON**
  constrained to the `Verdict`/`Action` dataclasses.
- **Hybrid, not all-local**: local 30B handles the ~90% mechanical volume; **cloud Opus** stays
  for planner/escalator structural re-plans and anything closing a `CONFORM`/`SCOPE`/`CROSS` flag
  (local tool-calls ~95%/call → ~66% over 8 steps). Safe because gates + independent DRC own
  outcome quality.
- **Pin cores**: E-cores for the Freerouting JVMs, 2–4 P-cores for the inference host; cap
  `max_workers`. Without this, contention can cut inference ~3.8×.
- **Make `cec_dispatch.request_candidates(where='runner')` real** (currently `NotImplementedError`)
  — the documented seam to keep the swarm local while dispatching Freerouting compute to the runner.

Effort: low–moderate. Payoff: high (≈$0 cheap-tier tokens, offline, unlocks multi-iter routing).

## Thrust B — Higher-resolution physics (electrothermal upgrade, CPU)

Upgrade the **already-implemented** analytic stage; don't build GPU-FEM. `electrothermal_solve`
→ `physics_gates` already reads copper from `pcbnew`, pulls currents from `_net_currents`, and
gates on `dT_max=30 / T_max=105 / J_max=100`.

- **First slice — DONE (2026-06-07), `scripts/cec_dcir.py`:** a 2.5D **DC IR-drop + current-density**
  field solve on the routed copper — rasterizes each poured net to a copper-square resistor mesh
  (numpy-only Jacobi-CG, not scipy, so it runs in KiCad's bundled python too; sub-second/net),
  injects the design current between the connector ↔ shunt pads, returns IR drop / peak J / bottleneck
  cross-section per net. Fallback-safe (None per unresolvable net). Validated in-container: 6/6 nets
  on the 24-pin, 4/4 on the routed EPS.
- **Close the loop — DONE (2026-06-07):** `C(id='min-pour-cross-section', directive='keepout', …)` is
  in `cec_constraints.REGISTRY` + a `@checker` (`_chk_min_cross`) that runs the `cec_dcir` solve and
  flags any poured high-current net whose bottleneck density exceeds `j_max` (= `physics_gates`'
  100 A/mm²), emitting a `reserve: pour-cross-section` placer directive with the numbers. It is
  **advisory / proposed** by design — the solver is not yet bench-validated, so it SURFACES
  **OQ-10 (copper coin) / OQ-12 (stackup)** real numbers (it lands in `final_fails`, never `hard_fails`,
  so it neither hard-gates a release nor triggers the loop's human-escalation) — OQ input, not
  resolved.
- **Enforce-leg — DONE (2026-06-07):** `cec_constraints.derive_cross_section_dru` /
  `ratify_cross_section` turn the field solve into the deterministic enforcement, split by net
  topology (an empirically-verified platform fact). A geometric DRC width rule (`track_width` OR
  KiCad's `connection_width`) FALSE-FLAGS the thin ~0.25 mm Kelvin sense tap (verified:
  `connection_width min 2.86 mm` fired on the 0.2–0.3 mm taps), so a **shared force+sense** net is
  **checker-enforced** (the field solve injects current only connector↔shunt, so the zero-current
  sense branch is never a "neck"). EVERY current CEC high-current net is shared (the INA senses
  *across* the shunt), so today enforcement = the `min-pour-cross-section` checker, ratified per
  board. A **force-only** net (future plane tapped by a Hall sensor) gets a `connection_width` DRU
  rule (min = physics-required width) that flows through `spec_to_dru` / `.kicad_dru` into the DRC —
  validated end-to-end (force-only sim: derive → ratify-write → **DRC enforces, 76 hits**, hand rules
  preserved). RATIFY is the human's board-specific act (`--enforce-cross-section --write`); promoting
  the checker itself from advisory→gating still wants the bench calibration of `dt_ipc` / `shunt_rth`.
- **Sign-off tier (later):** Elmer coupled steady+transient electrothermal to calibrate the
  hardcoded `dt_ipc` k-constant and `shunt_rth_CW=25 C/W` placeholder; validate against one bench
  measurement before a FEM flag blocks a release.
- **Phase-2 SI:** `gerber2ems` → openEMS (in container) for USB 90 Ω / RS-485 / CAN diff-pair
  impedance (answers the "recompute for the 1 oz JLC04161H-7628 stack" TODO). openEMS has no CUDA
  → also a CPU job, but the only realistic OSS SI path.

Effort: medium. Payoff: high (closes two open layout questions). The GPU is not involved.

## Thrust C — Learned policy (surrogate ranker, not RL)

- **Build (after logs accumulate):** a supervised surrogate scorer — gradient-boosted trees
  (later a small GNN on the 5090) on the `DecisionLog` candidate-metrics vectors → predict
  gate-pass / final-DRC, to **prune candidates to top-k before the expensive DRC** in
  `cec_router._candidate_pool` / `cec_dispatch.request_candidates`. Fails safe (gates adjudicate
  survivors). Keep a full-DRC-top-k + random-audit net.
- **Parallel track:** the corpus→checker migration — 164 of 269 `corpus-extracted.json` rows have
  no checker yet; converting the deterministically-checkable ones is compounding `cec_constraints`
  work.
- **Defer:** a learned router/placement policy. The only published winner is online world-model RL
  = GPU-weeks; 9 correlated boards is too little to imitate. A quarters-long research bet, only if
  the platform grows to dozens of similar boards.

Effort: surrogate = moderate (data plumbing first); RL = research-grade.

## Thrust D — OrthoRoute (fenced experiment only)

Keep Freerouting as production. OrthoRoute (GPU autorouter, MIT, alpha, single-author) is built
for 32-layer 8000-net backplanes, outputs dirty (non-DRC-clean) copper, integrates via the KiCad
IPC API (not DSN/SES), and — the blocker — has **no documented way to route a net-subset or treat
locked pours / Kelvin / diff pairs as immovable**. Attempt only as an experiment (like Quilter):
hand it a board with vital nets pre-routed-and-locked, route only the digital spine, feed
candidates into the **same `cec_score` gates** — and only after confirming in its source that it
respects locked tracks + keepout zones. If that check fails, it cannot touch these boards.

## Roadmap

- **Phase 0 (substrate):** containerize; headless Freerouting REST; validate in-container DSN/SES;
  persist DecisionLogs. *Improves today's loop immediately.*
- **Phase 1 (cheap, high-payoff):** local 30B hybrid judge tiers (A) + scipy DC IR-drop slice →
  `min-pour-cross-section` constraint (B). *Unlocks multi-iter routing + closes OQ-10/12 input.*
- **Phase 2 (compounding):** surrogate ranker on accumulated logs (C) + Elmer sign-off FEM +
  corpus→checker migration.
- **Phase 3 (optional/research):** openEMS SI in-container (B); OrthoRoute fenced experiment (D);
  world-model RL only if the corpus grows (C).

## Do / Defer / Don't

- **Do now:** the container + headless Freerouting; persist logs; local hybrid judge tiers; the
  scipy DC IR-drop slice.
- **Defer:** Elmer sign-off; surrogate ranker (needs logs first); openEMS SI; the checker-migration
  grind.
- **Don't (or don't expect):** GPU-accelerated classical FEM; fine-tuning a router on 9 boards;
  OrthoRoute in production; the 5090 speeding up Freerouting/DRC.

## Pointers

- Existing architecture: `scripts/README-cec_pcb.md`, `docs/self-hosted-router.md`,
  `scripts/cec_router.py`, `cec_fr.py`, `cec_score.py`, `cec_synth_pipeline.py`,
  `cec_constraints.py`, `cec_dispatch.py`.
- OrthoRoute: https://github.com/bbenchoff/OrthoRoute (MIT, alpha).
- Freerouting headless image: `ghcr.io/freerouting/freerouting` (REST :37864).
- CUDA-on-WSL: https://docs.nvidia.com/cuda/wsl-user-guide/ ; Blackwell-in-WSL fix:
  microsoft/WSL#14452.
- gerber2ems (KiCad→openEMS SI): https://github.com/antmicro/gerber2ems.
