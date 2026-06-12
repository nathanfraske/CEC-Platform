"""PR #35 review item 2 — REQUIRED RIDER: dry-run the new BLOCKING pour-integrity gate
(cec_score.pour_integrity_ok) over EVERY golden board and report. Run in the routing container
(needs pcbnew). If the run is CLEAN, the gate may merge in #35. If ANY golden TRIPS, the gate
moves to its own PR and the trip is an owner decision -- never a silent merge.

  docker exec docker-routing-1 python3 /workspace/scripts/cec_pour_gate_dryrun.py
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cec_score                                                # noqa: E402
import pcbnew                                                   # noqa: E402

_SENSE = re.compile(r"/?SENSEC\d+_(HI|LO)$", re.I)


def pour_facts(board_path):
    """Islands per /SENSEC* F.Cu zone (same definition as cec_fullstack.pour_facts)."""
    b = pcbnew.LoadBoard(board_path)
    facts = {}
    for z in b.Zones():
        nn = z.GetNetname()
        if not _SENSE.search(nn):
            continue
        try:
            sp = z.GetFilledPolysList(pcbnew.F_Cu)
            isl = sp.OutlineCount()
            ar = sp.Area() / 1e12
        except Exception:                                       # noqa: BLE001
            isl, ar = -1, -1.0
        facts[nn] = {"islands": isl, "area_mm2": round(ar, 2)}
    return facts


def main():
    boards = sorted(glob.glob(os.path.join(ROOT, "tests/golden/**/*.kicad_pcb"), recursive=True))
    rows, tripped = [], []
    for bp in boards:
        rel = os.path.relpath(bp, ROOT)
        facts = pour_facts(bp)
        ok, reasons = cec_score.pour_integrity_ok(facts)
        in_scope = bool(facts)
        rows.append({"board": rel, "in_scope": in_scope, "sense_nets": facts,
                     "gate_ok": ok, "reasons": reasons})
        if not ok:
            tripped.append(rel)
    report = {"gate": "pour_integrity_ok (islands==1 per /SENSEC* net)",
              "boards": rows, "tripped": tripped,
              "verdict": "CLEAN -- gate may merge in PR #35" if not tripped
              else "TRIPPED -- gate moves to its own PR; owner decision required"}
    out = os.path.join(ROOT, "tests/golden/pour-integrity-dryrun.json")
    json.dump(report, open(out, "w"), indent=1)
    for r in rows:
        scope = "in-scope" if r["in_scope"] else "no /SENSEC* (vacuous)"
        print(f"  {'OK ' if r['gate_ok'] else 'TRIP'}  {r['board']}  [{scope}]"
              + (f"  {r['reasons']}" if r["reasons"] else ""))
    print(f"\nVERDICT: {report['verdict']}")
    print(f"report -> {os.path.relpath(out, ROOT)}")
    return 1 if tripped else 0


if __name__ == "__main__":
    sys.exit(main())
