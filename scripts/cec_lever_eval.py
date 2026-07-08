#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Multi-seed placement-lever eval (ablation harness, 2026-07-08): single-seed metrics are
chaotically sensitive (a one-part seat shifted an unrelated divider 40mm), so a lever's
verdict = MEDIAN adjacency metrics over seeds x strats, placements only (no routing --
seconds per candidate). Usage: python3 scripts/cec_lever_eval.py [label]"""
import json
import math
import statistics
import sys

sys.path.insert(0, "scripts")
import cec_synth_pipeline as csp                     # noqa: E402
from cec_placement_session import PlacementSession   # noqa: E402


def measure(board_path):
    import pcbnew
    b = pcbnew.LoadBoard(board_path)
    pos = {fp.GetReference(): fp.GetPosition() for fp in b.GetFootprints()}
    def d(a, c):
        return math.hypot((pos[a].x - pos[c].x) / 1e6, (pos[a].y - pos[c].y) / 1e6) \
            if a in pos and c in pos else float("nan")
    dq = csp._oracle_decoupler_adjacency(board_path)
    cq = csp._oracle_comparator_adjacency(board_path)
    worst_cap = max((v[2] for v in dq["violations"]), default=0.0)
    worst_cmp = max((v[3] for v in cq["violations"]), default=0.0)
    return {"cap_viol": len(dq["violations"]), "worst_cap": worst_cap,
            "cmp_viol": len(cq["violations"]), "worst_cmp": worst_cmp,
            "can_j1": round(d("U2", "J1"), 1), "div": round(d("R52", "R53"), 1)}


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "eval"
    P = json.load(open("modules/atx-24pin-rev3/board-manifest.json"))["placement_directives"]
    P = {k: v for k, v in P.items()
         if not k.startswith("_") and not k.endswith(("_note", "_rules", "provenance"))}
    rows = []
    for strat in ("dataflow", "compact"):
        for seed in (0, 1, 2, 3):
            s = PlacementSession("atx-24pin-rev3", W=70, H=55, strat=strat, seed=seed, params=P)
            s.half("band", "y", 0.30, 0.72)
            s.half("core", "x", 0.58, 1.00)
            s.assign(s.cable_parts(), "band")
            s.assign([r for r in s.peripheral_ics()
                      if "TJA" not in (s.nl.comps[r].value or "").upper()], "core")
            out = f"build/lever-eval/{label}-{strat}-s{seed}.kicad_pcb"
            import os
            os.makedirs("build/lever-eval", exist_ok=True)
            with csp._oracle_env(P):
                s.materialize(out)
            rows.append(measure(out))
    med = {k: round(statistics.median(r[k] for r in rows), 1) for k in rows[0]}
    print(label, "MEDIANS over", len(rows), "placements:", med)


if __name__ == "__main__":
    main()
