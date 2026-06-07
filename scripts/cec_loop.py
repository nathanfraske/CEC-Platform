#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_loop -- the OUTER constraint-aware design loop: PLACE -> ROUTE -> CHECK.
# ============================================================================
# Composes the three planes around the shared constraint registry:
#   1. PLACE  -- cec_place.refine: cec_constraints directives -> placement moves
#                (+ owned-cluster cascade, overlap guard, rip moved nets for re-route).
#   2. ROUTE  -- cec_fr.route_once: Freerouting the refined placement, then lay the
#                high-current pours additively (derive_power_pours).
#   3. CHECK  -- cec_constraints (fresh subprocess) on the routed board: the full
#                verdict, including the routing-dependent constraints (logo short,
#                Kelvin-on-F.Cu, pour-present, trace-width).
# A residual MOVABLE directive after routing feeds the next placement pass; routing /
# finishing FAILs are the router's / finishing pass's job. Everything on a COPY.
#
#   python3 scripts/cec_loop.py --board eps-8pin [--iters 2] [--passes 12] [--opt-time 30]
# ============================================================================
import os, sys, glob, json, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cec_place    # refine / _check / _fails / MOVABLE
import cec_fr       # route_once / derive_power_pours


def _resolve(board):
    cands = [p for p in glob.glob(os.path.join(ROOT, "modules", board, "*.kicad_pcb"))
             if "-routed" not in p and ".merged." not in p]
    if not cands:
        raise FileNotFoundError("no .kicad_pcb under modules/%s" % board)
    return sorted(cands)[0]


def run_loop(board, ctx=None, iters=2, passes=12, opt_time=30, out=None):
    ctx = ctx or {}
    src = _resolve(board)
    out = out or os.path.join(ROOT, "build", "loop", board)
    os.makedirs(out, exist_ok=True)
    place = os.path.join(out, "placement.kicad_pcb")
    shutil.copyfile(src, place)

    log, routed_path, verdicts, directives = [], None, [], []
    for it in range(iters):
        # 1. PLACE -- refine the placement against the movable constraints
        placed = os.path.join(out, "placed_%d.kicad_pcb" % it)
        _, rlog = cec_place.refine(place, placed, ctx)
        moves = [a for h in rlog for a in h.get("applied", [])]
        # relocate the movable decorative LOGO to clear space (placement-side logo fix)
        logo_ko = cec_place.relocate_logo_to_clear(placed)
        shutil.copyfile(placed, place)                      # carry the placement (+ logo move) forward

        # 2. ROUTE -- Freerouting (logo keepout hint + additive high-current pours)
        routed_path = os.path.join(out, "routed_%d.kicad_pcb" % it)
        try:
            pours = cec_fr.derive_power_pours(placed)
        except Exception:
            pours = ()
        hints = [logo_ko] if logo_ko else []
        cand = cec_fr.route_once(placed, routed_path, passes=passes, opt_time=opt_time,
                                 hints=hints, power_pours=pours)
        ok = bool(getattr(cand, "ok", False))

        # 3. CHECK -- full registry on the routed board (fresh subprocess)
        target = routed_path if ok else placed
        verdicts, directives = cec_place._check(target, ctx)
        fails = cec_place._fails(verdicts)
        movable = [d for d in directives if (d.get("type") or d.get("directive")) in cec_place.MOVABLE]

        entry = {"iter": it, "placement_moves": [m.get("op") + ":" + str(m.get("a") or m.get("target")) for m in moves],
                 "logo_moved": bool(logo_ko), "pours": len(pours), "routed_ok": ok,
                 "route_err": (str(getattr(cand, "err", ""))[:100] if not ok else None),
                 "checked": os.path.basename(target), "fails": sorted(fails),
                 "movable_left": len(movable)}
        log.append(entry)
        print("[loop iter %d] moves=%d pours=%d routed=%s | FAILs=%s | movable_left=%d"
              % (it, len(moves), len(pours), ok, sorted(fails), len(movable)))
        if not movable:
            break                                           # placement converged

    # HUMAN-REVIEW HANDOFF: a copper plot + a 3D render of the final routed board for the human to review
    review = {}
    if routed_path and os.path.isfile(routed_path):
        try:
            import cec_plot
            plot_png = os.path.join(out, "review-copper.png")
            top_png = os.path.join(out, "review-top.png")
            cec_plot.copper_plot(routed_path, plot_png, title="%s -- loop result (place->route->check)" % board)
            cec_plot.render_3d(routed_path, top_png, side="top")
            review = {"copper_plot": plot_png, "render_top": top_png}
        except Exception as e:
            review = {"error": repr(e)}
    return {"board": board, "routed": routed_path, "final_fails": sorted(cec_place._fails(verdicts)),
            "log": log, "review": review}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="cec_loop -- outer PLACE->ROUTE->CHECK design loop")
    ap.add_argument("--board", default="eps-8pin")
    ap.add_argument("--iters", type=int, default=2)
    ap.add_argument("--passes", type=int, default=12)
    ap.add_argument("--opt-time", type=int, default=30)
    ap.add_argument("--radio", action="store_true")
    a = ap.parse_args(argv)
    res = run_loop(a.board, ctx={"radio": a.radio}, iters=a.iters, passes=a.passes, opt_time=a.opt_time)
    print("\n=== LOOP RESULT ===")
    print(json.dumps(res["log"], indent=1))
    print("final FAILs:", res["final_fails"])
    print("routed board ->", res["routed"])
    rv = res.get("review") or {}
    if rv.get("copper_plot"):
        print("REVIEW copper plot ->", rv["copper_plot"])
        print("REVIEW 3D render   ->", rv.get("render_top"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
