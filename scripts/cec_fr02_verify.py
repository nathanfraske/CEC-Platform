#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  FR-02 FULL VERIFY (the sheet's clause, committed as a reproducible runner):
#  "A directed net on eps-8pin routes through three compiler-placed waypoints
#   on the planned layers; deleting the intent and re-routing free produces a
#   measurably different path."
#
#  PASSED 2026-06-11 on the pinned FR 1.7.0 (container): 3/3 stubs survived,
#  the net routed THROUGH all three (absorbed, zero orphans), paths_differ.
#  Container-only (pcbnew + java + the FR jar). Exit 0 = VERIFY PASS.
# ============================================================================
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BOARD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "modules", "eps-8pin", "eps8pin-module.kicad_pcb")
NET = "/CAN_H"
# three RELATIONAL waypoints, all placeable on the committed floorplan
INTENTS = [{"net": NET,
            "waypoints": [{"between": ["U2", "U1"]},
                          {"ref": "U2", "offset_mm": [-6, 4]},
                          {"ref": "U2", "offset_mm": [-6, 8]}],
            "layers": ["F.Cu"]}]


def _sig(board_path, net):
    import pcbnew
    b = pcbnew.LoadBoard(board_path)
    return sorted(tuple(sorted([(t.GetStart().x, t.GetStart().y),
                                (t.GetEnd().x, t.GetEnd().y)]))
                  for t in b.GetTracks()
                  if t.GetNetname() == net and t.GetClass() == "PCB_TRACK")


def main(passes=10, opt_time=30):
    try:
        import pcbnew  # noqa: F401
    except ImportError:
        print(json.dumps({"verdict": "PREREQ-MISSING", "why": "no pcbnew"}))
        return 2
    import cec_fr
    import cec_fr02

    work = tempfile.mkdtemp(prefix="fr02verify_")
    directed = os.path.join(work, "directed.kicad_pcb")
    res = cec_fr02.compile_intents(BOARD, INTENTS, directed)
    out = {"board": os.path.relpath(BOARD), "net": NET,
           "n_stubs": len(res["stubs"]), "compile_failures": res["failures"]}

    dsn, ses = os.path.join(work, "d.dsn"), os.path.join(work, "d.ses")
    cec_fr.export_dsn(directed, dsn)
    out["protect_upgraded"] = cec_fr02.force_protect_in_dsn(dsn, [NET])
    cec_fr.run_freerouting(dsn, ses, passes=passes, opt_time=opt_time)
    routed = os.path.join(work, "routed.kicad_pcb")
    cec_fr.import_ses(directed, ses, routed)
    v = cec_fr02.verify_intents(routed, res)
    out["per_stub_survived"] = [s["survived"] for s in v["per_stub"]]
    out["hygiene"] = cec_fr02.clean_orphan_stubs(routed, res)

    # the free arm: same board, no intent
    free = os.path.join(work, "free.kicad_pcb")
    shutil.copy(BOARD, free)
    d2, s2 = os.path.join(work, "f.dsn"), os.path.join(work, "f.ses")
    cec_fr.export_dsn(free, d2)
    cec_fr.run_freerouting(d2, s2, passes=passes, opt_time=opt_time)
    freerouted = os.path.join(work, "freerouted.kicad_pcb")
    cec_fr.import_ses(free, s2, freerouted)

    out["paths_differ"] = _sig(routed, NET) != _sig(freerouted, NET)
    out["verdict"] = ("PASS" if (len(res["stubs"]) == 3 and v["all_survived"]
                                 and out["hygiene"]["absorbed"] == 3
                                 and out["paths_differ"]) else "FAIL")
    out["workdir"] = work
    print(json.dumps(out, indent=1))
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
