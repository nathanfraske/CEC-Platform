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
  resolved. **Still open (the enforce-leg):** flow a ratified min-width on the carved high-current
  netclass through `spec_to_dru` into the DRC, once a bench measurement calibrates `dt_ipc` / `shunt_rth`.
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
