# Agentic integration — forensics + design (2026-06-14)

_Branch `claude/placement-corridor`. Self-forensic + integration design for why the placer/Hub
`place→route→check` pipeline ran a **bare deterministic route** with the agentic model stack and
corpus gating un-wired, despite CLAUDE.md mandating the opposite — and how to fix it properly._

Provenance: forensics + design panel workflows `wf_27c511ed-113` (forensics, phase-1) and
`wf_cf91431f-a2a` (seam inventory + forensics synthesis + 4-lens design panel + design synthesis).
Every claim below was cross-checked against source at HEAD `c75baad`.

---

## 1. Synopsis (the honest root cause)

The Hub `place→route→check` pipeline (`scripts/hub_pipeline_run.py`, driven by `scripts/hub_run.sh`)
runs a **purely deterministic compute plane with ZERO control-plane wiring**, despite CLAUDE.md
explicitly mandating the tiered/corpus-gated pipeline. The honest root cause is a **smoke-first
bring-up that has started to ossify into the de-facto Hub runner** before its documented agentic
integration was written.

Verified against the code:
- `hub_pipeline_run.py:163` is `cec_router.route(mat, spec, verbose=True)` with **no
  planner/manager/worker/escalator** kwargs, so all four tier slots fall to the deterministic
  `default_*` policies (`cec_router.py:782-785`).
- It ranks candidates by a hardcoded tuple key `(not gates_pass, drc, unconnected, length)`
  (`hub_pipeline_run.py:185`) — i.e. it **judges board quality on the bare deterministic verdict**,
  the exact use CLAUDE.md:1850 / 1938 reserve for "a quick smoke."
- It sets `CEC_SKIP_INTAKE=1` (`:97`), never sets `CEC_CORPUS_REVIEW=1`, and calls `route()`
  directly (not `cec_router.main()`), so even the `--judge/--swarm` CLI wiring is bypassed.
- `grep` confirms the file has **zero** references to `cec_judge_local`, `cec_dispatch`,
  `cec_cascade`, `agent_route`, `make_subagent_policy`, `make_manager*/make_worker*`,
  `CEC_CORPUS_REVIEW`, broker, swarm, or `available()`.

The seams are complete, proven, and trivially adoptable — they were just not plumbed in.
`cec_router.route()` already exposes the four pluggable tiers + `make_subagent_policy`
(`cec_router.py:614,771-785`), an intake gate (`:794-814`), and a `CEC_CORPUS_REVIEW` corpus-fit
hook (`:1432-1442`). `cec_judge_local` supplies route()-shaped, fail-safe makers
(`make_manager_swarm`/`make_worker_swarm`/`make_dispatch_swarm_tier`/`corpus_fit_review`). The
**working reference is `cec_cascade.route_tier` (`cec_cascade.py:103-111`)**:
`manager = worker = None; if cec_judge_local.available(): manager=make_manager_swarm(...);
worker=make_worker_swarm(...)` then `cec_router.route(placement, spec, manager=manager,
worker=worker, ...)` — plus a verify-the-shipped-artifact re-score (`:132-151`). The Hub driver
imports none of them.

## 2. Contributing factors

- **Smoke-first bring-up.** `hub_pipeline_run.py` is the newest code (commits `ec67572`, `b807a28`)
  and existed to prove `place→materialize→route(FR)→check` works *at all* on a synth Hub board.
- **Real FR-on-Hub blockers consumed the bring-up budget.** Three genuine gaps had to clear first:
  `build_board` output is not DSN-exportable (so it materializes onto the committed reference
  stackup); the 0-origin synth frame had to be offset onto the `(70,90)` outline or FR routes
  nothing; the 2-process `Remove()`-then-fill pcbnew SWIG footgun.
- **The integration is documented-but-unbuilt and explicitly post-MV.**
  `docs/placement-strategy-2026-06-14.md:321` names the `cec_loop` Phase-4 reconciliation MANDATORY
  ("without it the placer is dormant"); `docs/placer-upgrade-2026-06-14/STATUS.md:51-52` lists L1
  (route leg) and L7 (validation/escalation gate) as DEFERRED post-MV. The gap is honestly tracked.
- **Seam wiring lives in sibling drivers the Hub driver never imports** (`cec_cascade.route_tier`,
  `cec_fullstack`).
- **The existing agentic entry points cannot absorb a from-scratch Hub without generalization.**
  `cec_dispatch.request_candidates` routes an already-placed board (`cec_dispatch.py:187-217`, no
  placement leg); `cec_loop._resolve` is hard-globbed to `modules/<board>/*.kicad_pcb`
  (`cec_loop.py:30`) running the nudge-only `cec_place.refine` — both are eps/route-shaped.
- **Incipient ossification.** The smoke driver accreted its own `cec_dashboard.py` viz (read-only,
  NOT the CL-22 adversarial panel), a `hub_run.sh` launcher, and a candidate timeline — hardening
  into the de-facto Hub runner while the documented integration stays unwritten.

## 3. The fair distinction — three kinds of "not wired"

1. **Legitimate deferral** (the FR-on-Hub route-leg bring-up). A bare route *is* a working pipeline;
   CLAUDE.md permits it for a smoke/baseline.
2. **Justified disable** — `CEC_SKIP_INTAKE=1`, *partially*. The comment's premise ("a SYNTH board
   has no sibling schematic") is wrong-in-spirit: the Hub **materializes onto the committed
   reference** (`hub_pipeline_run.py:69-86` copies `hubs/hub-standard/hub-standard.kicad_pcb`), which
   **does** have a sibling `.kicad_sch`. `intake_gate` runs on the materialized candidate (no sibling
   there), which is why the blanket skip was reached — but skipping wholesale is over-broad.
3. **Genuine oversight** — `CEC_CORPUS_REVIEW` off, when `corpus_fit_review` is pcbnew-free,
   fail-safe, out-of-loop (advisory sidecar), and a one-line env set.

Only (3) is a defect; conflating the three either over-blames the deferral or excuses the omission.

## 4. Lessons

- A "temporary" deterministic smoke driver hardens into the permanent path once it grows a launcher
  and a dashboard. The moment a smoke acquires UX it must adopt the mandated control plane **or carry
  a loud banner that it is smoke-only** — a driver that judges/ranks by `gates_pass` is already out
  of CLAUDE.md policy.
- When a proven seam wiring exists in a sibling driver (`cec_cascade.route_tier`), a new driver
  should **copy it** rather than re-implement a bare path — the `available()`-guarded block degrades
  silently when the broker is down, so there is no cost to adopting it even during bring-up.
- Agentic entry points written for one board family become silent blockers for the next; surface the
  generalization debt explicitly rather than spinning up a parallel flat driver.
- Corpus/anti-overfit gating (CL-25 intake + `corpus_fit_review`) is the product per the closed-loop
  docs, not optional polish; the cheap fail-safe half should be **on by default** for any non-smoke
  run.

---

## 5. Integration design (the fix)

**One recommendation — Path A: wire the control plane into the Hub at the existing
`cec_router.route()` call site** in `hub_pipeline_run.py`, mirroring `cec_cascade.route_tier`. Do
**not** route the Hub through `cec_fullstack` now (Path B) — it is eps-hardwired
(`ovd.BOARD_PCB/INTENTS` are eps-only; its route leg uses `ovd._exec_route_one`, a different path
than `cec_router.route`), so generalizing it is a larger, later lever (checklist step 11).

The two-plane rule is honored cleanly: the deterministic plane (placement + `cec_fr`/`cec_router`
generate + `cec_score` gates) **GENERATES + SCORES**; the seats only **JUDGE + FIX** through the
manager/worker slots (`Verdict` + bounded `fr_params`/nudge edits) — no hand-routing, no cloud seat
may alter a ratified constraint.

### 5.1 Cloud ↔ local toggle (the load-bearing simplification)

`cec_judge_local._chat_json` (`:347`) **already auto-routes cloud-vs-broker purely by model name**
via `_is_cloud` (`:253`) → `_chat_json_cloud` (`:301`, shells `claude -p --model <m> --output-format
json`). So the toggle is just *which model string the swarm makers receive* — no new transport, no
duplicate `_cloud` makers. The only additive change: give `make_manager_swarm`/`make_worker_swarm`
an optional `model=/url=` kwarg. `model='opus'`/`'sonnet'` → cloud via the shim; default `None` →
broker models. Both makers already `try/except → default_manager/default_worker`, so a down broker
(local) or absent CLI (cloud) degrades to deterministic with no extra code.

The toggle lives in one resolver `scripts/cec_seats.py` (`select_seat_backend(hours, judge, now)`),
importable by both the Hub driver and, later, `cec_fullstack`/`cec_cascade` (one codepath, no drift).

### 5.2 Default policy — OWNER RESOLVED (2026-06-15)

> Owner: "Cloud or local depending on what I call for, **defaulting to cloud**." (and earlier:
> "default the overnight long runs to local, and short mid day to cloud.")

Resolved rule (highest wins):
1. **Explicit** `--seats {cloud,local,off}` flag, then `CEC_HUB_SEATS` env. `off` ⇒
   `manager=worker=None` ⇒ the sanctioned deterministic smoke. `cloud`/`local` pin the venue.
2. **Duration default**: `--hours` present AND `>= CEC_OVERNIGHT_HOURS_MIN` (default 2.0h) ⇒
   **LOCAL** (broker; 5090 free off-peak; zero cloud spend).
3. **Else ⇒ CLOUD** (short `--hours`, `--rounds`-bounded, or fully unbounded — all default cloud, per
   the owner). Cloud models = the seat-bakeoff data-chosen defaults: **generation/worker = `sonnet`,
   reasoning/manager = `opus`**, run at **`--effort max`** on every cloud seat (owner 2026-06-15:
   cloud effort = max in all cases). `effort` is threaded maker → `_panel` → `_chat_json` →
   `_chat_json_cloud` (`--effort max`); env override `CEC_HUB_CLOUD_EFFORT`.

So `hub_run.sh build/hub-full 7` ⇒ LOCAL; `hub_run.sh build/hub-full 1` ⇒ CLOUD;
`CEC_JUDGE=local hub_run.sh …` pins local. Length, not wall-clock, is the signal. The threshold ships
as `CEC_OVERNIGHT_HOURS_MIN` (env/policy-overridable, documented, never hardcoded). **Cloud
cost/egress accepted by the owner** (cloud is the midday default).

Per-tier model overrides (`CEC_HUB_MANAGER_MODEL`/`CEC_HUB_WORKER_MODEL`) apply within the chosen
venue. Everything fail-safe: any cloud/broker/policy failure ⇒ deterministic defaults, and the
resolved backend is **logged prominently** so a degraded (silently-deterministic) overnight run is
visible.

Optional `cec-policy.json` `judge_residency` block (CODEOWNERS-gated, `policy_sha256`-stamped) makes
the threshold + per-tier model maps an owner-approved diff; the resolver reads it if present and
fails safe to the env+hardcoded defaults. This is optional polish, not on the critical path.

### 5.3 Corpus gating (anti-overfit honored: committed Hub = HOLDOUT, validate-never-tune)

1. **CL-25 intake** — keep `CEC_SKIP_INTAKE` from pre-refusing the synth candidate, but add a
   synth-appropriate intake: (a) run the schematic-side `intake_gate` **once against the committed
   REF schematic** at run start (cheap base-stackup insurance; `bom-field-lint`'s OQ-11/consigned-THT
   gaps are NOTED-not-failed per `cec_constraints.py:249-250`); (b) run the **PCB-geometry subset of
   `cec_constraints.run()` post-route** on the synth-relevant checkers:
   `high-current-corridor-keepout` (self-N/As on the cable-less Hub — correct, not a miss),
   `netclass-geometry-conformance` (the only enforcement that FR honored widths), `kelvin-sense-*`,
   `high-current-pour-integrity`/`-present`, `logo-bcu-keepout`, `mount-holes-present-clear`,
   `connector-mouth-faces-edge` (all 10 ids verified present in the checker registry). **As shipped it
   is enforced in candidate SELECTION** — the ranking key is `(not gates_pass, conformance_fail>0,
   conformance_fail, drc, unconnected, length)`, so a conformance-failing candidate can never outrank a
   clean one — and recorded per-candidate in the report. Promoting it to an **abort-level HARD gate** is
   deferred until the committed Hub is confirmed to pass the subset (the holdout must pass the gates
   being added; if it fails, fix the gate, never relax toward it). Cosmetic/silk + documented-open items
   stay NOTED-not-failed.
2. **`corpus_fit_review` ON for the Hub but ADVISORY** (sidecar only, never a rank key, never feeds
   back). It is called `corpus_fit_review(dlog)` **directly from the Hub driver** (not by hoisting the
   `cec_router.main()` block into `route()`, which would change every caller). The family is **stable
   as built**: `board_spec` derives it from the out-dir basename (e.g. `hub-full`), so peers accumulate
   under one family across candidates and runs (naming it `hub-standard` is a forward nicety, not done —
   no functional impact while the corpus is eps-only). Even with zero same-family peers (the corpus is
   100% eps-8pin ⇒ `_cf_insufficient`), the **briefed-rules path** (`cec_facts.corpus_briefing`,
   which encodes the Hub In2 slow-signal exception) gives it teeth from run one. **Do not** seed the
   corpus from the committed Hub — that makes the holdout a tuning target.
3. **Policy guards** — import `cec_policy`, call `assert_loadable()` at run start (DF-05/07
   anti-ratchet + binding usability), and stamp `policy_sha256` into the Hub run's ledger entry.

End-to-end gate order: (0) `cec_policy.assert_loadable` [HARD]; (1) schematic intake on REF [HARD];
(2) route + `cec_score` gates (kelvin/diffpair/drc/unconnected) [HARD, present]; (2b) PCB-geometry
conformance subset post-route [SELECTION gate now — ranking key; abort-level HARD deferred];
(3) `corpus_fit_review` [ADVISORY sidecar, briefed];
(4) electrothermal [advisory, present]; (5) `cec_ledger` every run. Run the same gates on the
committed Hub to confirm calibration — never tune a threshold toward it.

### 5.4 Verify-the-shipped-artifact

Adopt `cec_cascade.py:132-151`: re-score the **saved** board with `cec_score` after `route()` (and
any pour/via mutation) before trusting the verdict — the cascade caught a stale pre-mutation verdict
this exact way. The Hub already scores `final` post-route; this makes the dependency explicit and
guards any future post-route mutation.

### 5.5 Feedback loop + dashboard (later / lighter)

- **Dashboard** (this PR, anti-ossification): a read-only "agentic decisions" card surfacing the
  resolved backend + per-tier model + per-candidate manager/worker verdicts + corpus-fit
  classification + gate-pass, so a degraded overnight run is visible.
- **Placer↔router feedback** (deferred to step 11 / a later PR): a `request_placements` leg +
  `place_then_route` (route-confirm top-K → model selects best → reseed on placement-caused stall →
  escalate), gated `lane==augmented` for A/B integrity. Requires the Path-B generalization
  (`find_board` hubs/ fallback, register Hub in `BOARD_PCB`).

---

## 6. Implementation checklist (ordered)

| # | Effort | File | What |
|---|--------|------|------|
| 1 | S | `scripts/cec_seats.py` (NEW) | `select_seat_backend(hours, judge, now)` resolver: explicit flag/env > duration default (`--hours>=CEC_OVERNIGHT_HOURS_MIN[2.0]→local`) > else cloud. Cloud=opus/sonnet, local=cec-manager-fast/cec-worker. Optional `cec-policy.json judge_residency` read, fail-safe. Pure/host-testable. |
| 2 | S | `scripts/cec_judge_local.py` | Add `model=/url=` to `make_manager_swarm`/`make_worker_swarm`; thread into `_panel`/`_chat_json` (cloud auto-routes by model name). Keep the existing deterministic fallback. |
| 3 | M | `scripts/hub_pipeline_run.py` | `--seats {auto,cloud,local,off}`; before the route call build manager/worker per the resolver (cloud panel=1: `claude -p` has no sampling temp; local panel=3); pass them into `cec_router.route(...)`. Log the resolved backend. |
| 4 | S | `scripts/hub_pipeline_run.py` | Make verify-the-shipped-artifact explicit (re-score the saved board; guard any future post-route mutation). |
| 5 | M | `scripts/hub_pipeline_run.py` | Call `corpus_fit_review(dlog)` directly → advisory sidecar (family is stable as built — out-dir basename). No corpus seeding from the holdout. |
| 6 | M | `scripts/hub_pipeline_run.py` | Post-route PCB-geometry conformance gate folded into candidate SELECTION (ranking key; abort-level HARD deferred); REF-schematic intake at start instead of blanket skip. |
| 7 | S | `scripts/hub_pipeline_run.py` | `cec_policy.assert_loadable()` at start; ledger the run with `policy_sha256`. |
| 8 | S | `scripts/hub_run.sh` | Forward `CEC_JUDGE`/positional `--seats` to the container invocation. |
| 9 | M | `scripts/cec_dashboard.py` | Read-only "agentic decisions" card (resolved backend + per-tier model + verdicts + corpus-fit + gate-pass). |
| 10 | S | `tests/test_cec_seats.py` (NEW) | Table-test the resolver + precedence + fail-safe. |
| 11 | L | `cec_router.find_board` / `cec_loop` / `cec_place` / `cec_overnight_directed` | **(LATER PR)** Path-B generalization: `hubs/` fallback in `find_board` (modules/ first), register Hub in `BOARD_PCB`, the placer↔router feedback loop. |

---

## 7. Open questions / owner decisions

- **[RESOLVED]** Default residency: cloud or local on demand, **defaulting to cloud**; overnight-long
  (`--hours>=2`) ⇒ local. Cloud cost/egress accepted.
- Cloud manager is **single-judge** (`panel=1`): `claude -p` exposes no sampling temperature, so the
  3-lens voted swarm collapses to one judge in cloud mode (fine for short midday runs; cloud
  diversity would need prompt variation — a separate, holdout-validated PR).
- `CEC_OVERNIGHT_HOURS_MIN=2.0` is a heuristic; ships env/policy-overridable.
- Deep auditor (`deepseek-v4-flash`, ~160GB) cannot run under the WSL broker — but the Hub route leg
  uses the manager/worker swarm (`cec-manager-fast`/`cec-worker`, which fit), not the deep auditor,
  so this is only a concern if the deep tier is later added to the Hub.
- The post-route PCB-geometry HARD gate may surface real failures the place-only run hid (STATUS.md:
  ~211 unconnected + ~64 real-structural DRC at low effort) — gate only the synth-relevant subset;
  the committed Hub must PASS the gates being added (if not, fix the gate, never relax toward the
  holdout).
- Corpus-fit insufficiency: rely on the briefed-rules path until Hub peers accumulate under the
  stable family; do NOT seed peers from the committed Hub holdout.
