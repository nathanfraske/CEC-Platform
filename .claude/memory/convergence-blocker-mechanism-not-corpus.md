---
name: convergence-blocker-mechanism-not-corpus
description: "Why runs don't converge a fresh board — it's enforcement/mechanism (pour-clip), not a corpus-knowledge gap; the deterministic route already converges the committed board."
metadata: 
  node_type: memory
  type: project
  originSessionId: f4532aca-d14d-4db6-907e-4f75a063ae3c
---

**Can a run converge (pass the HARD gates kelvin_ok+diffpair_ok, finishing-only DRC) right now, or does the corpus need more first?** Answer (verified 2026-06-16, workflow wf_7b4f6e0a + independent trace): **YES it converges on a hand-finished board via the deterministic route; the blocker for a fresh/agentic run is MECHANISM, not corpus.**

- **Existence proof:** routing the committed `eps-8pin` through the deterministic pipeline → `kelvin_ok=true, diffpair_ok=true, drc=0` (live, 18.2s). SB-08 golden locks this. The golden's only "red" is a THERMAL band (max_T over budget) — the owner-gated AM-04 re-freeze, NOT a hard-gate/DRC blocker.
- **The crux divergence (same board, converges vs stalls):** `cec_router.route()` bakes a route-time vital-corridor keepout (`_vital_keepouts_from_rules`, cec_router.py:631) reserving the connector→shunt high-current corridors, so FR routes foreign signals AROUND the pours → they stay solid → converges. `route_directed` (the full-stack route, cec_overnight_directed.py:188) does NOT — it bakes only REACTIVE avoid intents (one round late, and the finder targets the FENCED sense nets → refused). So foreign signals route THROUGH the corridors → pours fragment (`/SENSEC2_LO` clipped 36–40/46 rounds) → `gates=FAIL`.
- **Corpus is NOT the bottleneck:** the rules are encoded + ratified + checked — `cec_constraints.py:82` high-current-corridor-keepout, `:98` high-current-pour-integrity, `:116` kelvin-sense-from-inner-pad — and the pour-integrity checker correctly DETECTS the clip. The "notched-corridor keepout / re-pour-after-route" fix is only a TODO string (cec_fullstack.py:2786); no notch/defrag function exists; layer-stagger is wired-but-inert (fired 31×, "flipped 0 crossings, reverted" 31/31).
- **To unblock a fresh-board converge (5 CODE, 1 advisory-CORPUS):** (1) notched-corridor keepout at route time [highest value; `bake_hints` only makes solid rects today]; (2) re-pour/defrag-after-route; (3) make layer-stagger actually relocate a crossing to the B.Cu mirror; (4) same-route corridor reservation (avoid is next-round-reactive); (5) domain-aware placer (corridor keepout + sense-adjacent-to-shunt as HARD constraints — CLAUDE.md item -2, the real fresh-board unblock); (6) [CORPUS, advisory] bench-calibrate min-pour-cross-section / FEM-k (OQ-10/12) — gates physics sign-off, not the hard gates.

The placement actuation lever (wired 2026-06-16, see [[current-work-handoff]]) is one enforcement mechanism; the DOMINANT eps blocker is the pour-clip (#1/#2). Build #1 if the goal is a self-converging fresh-board run.
