---
name: thermal-gate-required
description: "A routed board is NOT \"clean\" until electrothermal_solve passes — kelvin/diffpair/DRC gates say nothing about current density."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6a1b6a2a-dfb9-4421-89b6-0ca014fb9552
---

The owner caught me calling an eps-rev3 board "clean" (kelvin+diffpair+DRC pass, unconn=0) when it actually hit **max_T=181.6 C** — fusing 0.36mm SENSEC vias at 1049 C and +5VSB left as a 0.2mm trace at 120 C. `cec_router.route` reports `gates_pass` on kelvin/diffpair/DRC but NEVER runs the thermal solver, so a passing route says nothing thermally.

**Why:** high-current pours can be thin / F.Cu-only / via-unstitched and still pass DRC; only `sp.electrothermal_solve(board, cfg)` (per-net cross_mm2, J, dT, via temps) reveals it. The owner's tell was "lines straight across" = power rails left as 0.2mm traces (`poured:False`).

**How to apply:** for ANY board I claim routed / clean / fab-ready, RUN `sp.electrothermal_solve` and check max_T/max_dT + the via temps BEFORE reporting. Run `cec_fr.synthesize_power_copper` FIRST (B.Cu mirror + via field) — the plain route skips it (it drops the eps board 181.6→120.5 C, vias 1049→65). Even then `+5VSB`/`+3V3` stay traces and SENSEC1_HI can miss the mirror — so thermal still fails until those are poured. See FOLLOWUPS 2026-06-27 (thermal gate missing from route). Relates to [[convergence-blocker-mechanism-not-corpus]].
