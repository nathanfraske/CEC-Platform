#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Escalator measurement probe (owner ask 2026-07-08: "show the fixes on the dash like the
wave ones"). Grades ONE placement variant under the oracle recipe, renders the routed
candidate (both faces on dual-sided boards, back face banner-stamped), and logs the round
to the dashboard ACTIVITY feed with the verdict line -- so every fix-measure round of the
escalation loop is visually reviewable exactly like a wave variant.

Usage (in the routing container):
    python3 scripts/cec_escalator_probe.py --board atx-24pin-rev3 --round "round 5: inner pours" \
        [--strat dataflow --seed 1 --fr-seed 11 --passes 8 --opt 10 --w 70 --h 55]
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True)
    ap.add_argument("--round", required=True, help="short label for the feed, e.g. 'round 5: inner pours'")
    ap.add_argument("--strat", default="dataflow")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--fr-seed", type=int, default=11)
    ap.add_argument("--passes", type=int, default=8)
    ap.add_argument("--opt", type=int, default=10)
    ap.add_argument("--fr-timeout", type=int, default=1200)
    ap.add_argument("--w", type=float, default=70.0)
    ap.add_argument("--h", type=float, default=55.0)
    args = ap.parse_args()

    import cec_synth_pipeline as csp
    import cec_worklog
    from cec_placement_session import PlacementSession
    from cec_fresh_wave import _stamp_back_face

    mf = next((c for c in (os.path.join(ROOT, "beta", args.board, "board-manifest.json"),
                           os.path.join(ROOT, "modules", args.board, "board-manifest.json"))
               if os.path.isfile(c)),
              os.path.join(ROOT, "beta", args.board, "board-manifest.json"))
    P = {}
    if os.path.isfile(mf):
        with open(mf, encoding="utf-8") as f:
            pd = (json.load(f) or {}).get("placement_directives") or {}
        P = {k: v for k, v in pd.items()
             if not k.startswith("_") and not k.endswith(("_note", "_rules", "provenance"))}

    s = PlacementSession(args.board, W=args.w, H=args.h, strat=args.strat, seed=args.seed, params=P)
    out_dir = os.path.join(ROOT, "build", "escalator", args.board)
    os.makedirs(out_dir, exist_ok=True)
    slug = args.round.lower().replace(" ", "-").replace(":", "")
    placed = os.path.join(out_dir, f"{slug}.kicad_pcb")
    v = s.grade(out=placed, keep=True, passes=args.passes, opt=args.opt,
                fr_timeout=args.fr_timeout, seed=args.fr_seed, unconn_finish_tol=0)

    th = v.get("thermal") or {}
    detail = (f"gate={v.get('gate')} kelvin={v.get('kelvin_ok')} drc={v.get('drc')} "
              f"unconn={v.get('unconnected')} foreign={(v.get('foreign') or {}).get('tracks')}t "
              f"dT={th.get('dT')} sense_side={v.get('sense_side_ok')} "
              f"[{args.strat}-s{args.seed} fr{args.fr_seed} p{args.passes}]")
    print(detail)
    for r in (v.get("reasons") or [])[:6]:
        print(" -", r[:160])

    routed = v.get("routed")
    img = None
    if routed and os.path.isfile(str(routed)):
        import cec_render
        img = cec_render.render(routed, os.path.join(out_dir, f"{slug}-top.png"), side="top")
        if P.get("dual_sided"):
            imgb = cec_render.render(routed, os.path.join(out_dir, f"{slug}-bottom.png"),
                                     side="bottom")
            if imgb:
                _stamp_back_face(imgb)
                cec_worklog.log(f"escalator {args.board} {args.round} — BACK FACE (mirrored view)",
                                tag="fix", detail=detail, image=imgb)
    
    cec_worklog.log(f"escalator {args.board} {args.round}", tag="fix", detail=detail, image=img)
    return 0


if __name__ == "__main__":
    sys.exit(main())
