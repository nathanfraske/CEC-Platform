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

    import cec_hc
    log, routed_path, verdicts, directives = [], None, [], []
    for it in range(iters):
        # 0. KELVIN tighten -- pull+ROTATE each INA238 hard against its shunt (§6.8 short Kelvin loop),
        #    BEFORE the decoupling refine so the caps re-cluster to the INA's tight final position. This
        #    is the placement side of the high-current feedback: it makes the deterministic sense tap a
        #    short, clean segment instead of a long diagonal across foreign copper.
        ktight = os.path.join(out, "ktight_%d.kicad_pcb" % it)
        kmoves = cec_place.tighten_kelvin(place, ktight)
        shutil.copyfile(ktight, place)

        # 1. PLACE -- refine the placement against the movable constraints
        placed = os.path.join(out, "placed_%d.kicad_pcb" % it)
        _, rlog = cec_place.refine(place, placed, ctx)
        moves = [a for h in rlog for a in h.get("applied", [])]
        # relocate the movable decorative LOGO to clear space (placement-side logo fix)
        logo_ko = cec_place.relocate_logo_to_clear(placed)
        shutil.copyfile(placed, place)                      # carry the placement (+ logo move) forward

        # 2. ROUTE -- Freerouting with the high-current corridor reserved: the logo keepout, the
        #    pour-region keepouts (foreign signals kept off the 12V pour layers so the fill stays whole),
        #    the KELVIN keepouts (foreign signals kept out of each shunt<->INA238 gap so the sense tap
        #    lands clean), plus the additive pours.
        routed_path = os.path.join(out, "routed_%d.kicad_pcb" % it)
        try:
            pours = cec_fr.derive_power_pours(placed)
        except Exception:
            pours = ()
        try:
            kelvin_ko = cec_hc.kelvin_keepouts(placed)
        except Exception:
            kelvin_ko = []
        hints = ([logo_ko] if logo_ko else []) + cec_hc.keepouts_from_pours(pours) + kelvin_ko
        cand = cec_fr.route_once(placed, routed_path, passes=passes, opt_time=opt_time,
                                 hints=hints, power_pours=pours)
        ok = bool(getattr(cand, "ok", False))
        # 2b. DETERMINISTIC high-current pass (fresh subprocess; pcbnew multi-load is unsafe in-process):
        #     rip FR's via'd sense, lay the clean Kelvin sense tap (do-no-harm). Parse its report so the
        #     loop knows how many taps landed and which sense nets still need a placement fix.
        hc_info = {}
        import subprocess
        if ok:
            r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "cec_hc.py"),
                                routed_path, routed_path], capture_output=True, text=True)
            for line in (r.stdout or "").splitlines():
                line = line.strip()
                if line.startswith("{"):
                    try:
                        hc_info = json.loads(line)
                    except Exception:
                        pass

        # 2c. POWER-ESCAPE -- the constraint registry's `ic-power-ground-connected` emits a power_escape
        #     directive for every IC whose power/GND pad FR left stranded (a tight Kelvin placement boxes
        #     the sense IC's shunt-facing GND in the keepout). Drop a do-no-harm GND stitch via per flagged
        #     IC -> bonds it to the inner GND plane; a boxed-in pin that can't take a clean via is SKIPPED
        #     and stays flagged. (+3V3 has no plane under the locked GND-inner stackup -> trace/finish.)
        esc_info = {}
        if ok:
            _, pre_dirs = cec_place._check(routed_path, ctx)
            esc_ics = sorted({d.get("ic") for d in pre_dirs
                              if (d.get("directive") == "power_escape" or d.get("type") == "power_escape")
                              and d.get("ic")})
            if esc_ics:
                r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "cec_hc.py"),
                                    "--escape-gnd", routed_path, routed_path, ",".join(esc_ics)],
                                   capture_output=True, text=True)
                for line in (r.stdout or "").splitlines():
                    if line.strip().startswith("{"):
                        try:
                            esc_info = json.loads(line.strip())
                        except Exception:
                            pass

        # 3. CHECK -- full registry on the routed board (fresh subprocess)
        target = routed_path if ok else placed
        verdicts, directives = cec_place._check(target, ctx)
        fails = cec_place._fails(verdicts)
        movable = [d for d in directives if (d.get("type") or d.get("directive")) in cec_place.MOVABLE]

        entry = {"iter": it, "placement_moves": [m.get("op") + ":" + str(m.get("a") or m.get("target")) for m in moves],
                 "kelvin_tightened": len(kmoves), "logo_moved": bool(logo_ko), "pours": len(pours),
                 "routed_ok": ok, "route_err": (str(getattr(cand, "err", ""))[:100] if not ok else None),
                 "kelvin_taps_laid": hc_info.get("stubs"), "kelvin_needs_placement": hc_info.get("needs_placement"),
                 "gnd_escape_vias": esc_info.get("vias"), "gnd_escape_skipped_boxed_in": esc_info.get("skipped_boxed_in"),
                 "checked": os.path.basename(target), "fails": sorted(fails), "movable_left": len(movable)}
        log.append(entry)
        print("[loop iter %d] moves=%d ktight=%d pours=%d routed=%s | kelvin_taps=%s needs_place=%s | gnd_escape=%s(skip %s) | FAILs=%s"
              % (it, len(moves), len(kmoves), len(pours), ok, hc_info.get("stubs"),
                 hc_info.get("needs_placement"), esc_info.get("vias"), esc_info.get("skipped_boxed_in"), sorted(fails)))
        if not movable and not hc_info.get("needs_placement"):
            break                                           # placement + Kelvin converged

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
