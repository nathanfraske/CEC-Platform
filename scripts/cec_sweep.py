#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_sweep -- full-pipeline sweep validation across all boards + a local-judge swarm test.
# ============================================================================
# Three sweeps, one structured report:
#   1. CONSTRAINTS  -- the full cec_constraints registry on EVERY board (status counts; ERROR must
#                      be 0; the new min-pour-cross-section advisory surfaces per board).
#   2. ROUTE+JUDGE  -- routes the interposer modules IN PARALLEL (separate processes), each judged by
#                      cec_router's manager tier. With --judge local the local vLLM judges every
#                      board's candidates -> the concurrent routes drive a CONCURRENT JUDGE SWARM at
#                      the batched server. Reports gates_pass / drc / unconnected / verdict tier.
#   3. SWARM        -- fires N judges CONCURRENTLY at the batched server (wall-clock vs serial) to
#                      exercise the local agent swarm directly (Thrust A throughput).
#
# Run inside the routing container (needs pcbnew + kicad-cli). The local judge is OPTIONAL: with the
# vLLM server down, --judge local falls back to the deterministic manager (and --swarm is skipped).
#   python3 scripts/cec_sweep.py [--route] [--judge {default,local}] [--swarm N]
#                                [--boards a,b,..] [--seeds 0,1] [--passes 8] [--opt-time 10]
# ============================================================================
import os
import sys
import json
import time
import subprocess
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

# every board, for the constraint sweep (path relative to ROOT)
ALL_BOARDS = [
    ("24pin-rev2",      "modules/atx-24pin-rev2/24pin-module.kicad_pcb"),
    ("eps-8pin-rev3",   "beta/eps-8pin-rev3/eps-8pin-rev3.kicad_pcb"),
    ("pcie-2port",      "beta/pcie-8pin-2port/pcie8pin-2port-module.kicad_pcb"),
    ("pcie-3port",      "beta/pcie-8pin-3port/pcie8pin-3port-module.kicad_pcb"),
    ("12vhpwr-std",     "beta/12vhpwr-standard/12vhpwr-standard-module.kicad_pcb"),
    ("12vhpwr-pro",     "modules/12vhpwr-pro/12vhpwr-pro-module.kicad_pcb"),
    ("hub-standard-rev2", "beta/hub-standard-rev2/candidate/hub-standard-rev2-candidate.kicad_pcb"),
]
# the cec_router interposer family (module dir names) -- routable from a committed floorplan
ROUTE_BOARDS = ["eps-8pin-rev3", "pcie-8pin-2port", "pcie-8pin-3port"]


def _py():
    return sys.executable


def sweep_constraints(boards):
    """Run the full cec_constraints registry on each board (subprocess --json). Returns
    {name: {FAIL,PASS,NA,DECLARED,ERROR, fails:[...], error:?}}."""
    out = {}

    def one(item):
        name, rel = item
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            return name, {"error": "missing board"}
        r = subprocess.run([_py(), os.path.join(ROOT, "scripts", "cec_constraints.py"), path, "--json"],
                           capture_output=True, text=True)
        # the JSON is the last [...] blob on stdout
        txt = r.stdout
        try:
            start = txt.index("[")
            blob = json.loads(txt[start:])[0]
        except Exception as e:
            return name, {"error": f"parse: {e}", "stderr": (r.stderr or '')[-200:]}
        from collections import Counter
        c = Counter(v["status"] for v in blob["verdicts"])
        fails = [v["id"] for v in blob["verdicts"] if v["status"] == "FAIL"]
        return name, {"FAIL": c["FAIL"], "PASS": c["PASS"], "N/A": c["N/A"],
                      "DECLARED": c["DECLARED"], "ERROR": c["ERROR"], "fails": fails}

    with ThreadPoolExecutor(max_workers=min(8, len(boards))) as ex:
        for name, res in ex.map(one, boards):
            out[name] = res
    return out


def sweep_routes(boards, *, judge="default", seeds="0,1", passes=8, opt_time=10, max_iters=1,
                 route_workers=1):
    """Route each board and capture its verdict. Boards run with route_workers concurrency. NOTE:
    keep route_workers=1 (SERIAL across boards) -- each cec_router route ALREADY parallelizes its
    seeds via an internal Freerouting JVM pool sharing the one Xvfb :99, so running multiple ROUTE
    PROCESSES at once oversubscribes FR/X and starves some routes to 0 candidates (observed: 3
    parallel routes -> the 2 PCIe boards routed nothing while eps won). The concurrent JUDGE swarm is
    demonstrated by sweep_swarm(), not by parallel routes. Returns
    {board: {gates_pass, drc, unconnected, kelvin_ok, diffpair_ok, tier, secs}}."""
    out = {}

    def one(board):
        outd = os.path.join(ROOT, "build", "sweep", board)
        os.makedirs(outd, exist_ok=True)
        cmd = [_py(), os.path.join(ROOT, "scripts", "cec_router.py"), "--board", board,
               "--seeds", seeds, "--passes", str(passes), "--opt-time", str(opt_time),
               "--max-iters", str(max_iters), "--out", outd, "--judge", judge, "--quiet"]
        t0 = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True)
        secs = round(time.time() - t0, 1)
        verdict, tier = {}, ""
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if line.startswith("verdict:"):
                try:
                    verdict = json.loads(line[len("verdict:"):].strip())
                except Exception:
                    pass
            if line.startswith("[judge:local]") or "tier=" in line:
                tier = "local" if "judge:local" in line else tier
        return board, {"gates_pass": verdict.get("gates_pass"), "drc": verdict.get("drc"),
                       "unconnected": verdict.get("unconnected"), "kelvin_ok": verdict.get("kelvin_ok"),
                       "diffpair_ok": verdict.get("diffpair_ok"), "tier": tier or judge, "secs": secs,
                       "rc": r.returncode}

    with ThreadPoolExecutor(max_workers=max(1, route_workers)) as ex:
        for board, res in ex.map(one, boards):
            out[board] = res
    return out


def sweep_swarm(n, *, max_workers=None):
    """Fire N local-judge calls CONCURRENTLY (the swarm) and time it vs a serial baseline call.
    Returns a summary dict, or {'skipped':...} if the server is down."""
    import cec_judge_local as J
    if not J.available(timeout=3):
        return {"skipped": "vLLM server not available"}
    # varied synthetic candidate contexts: half gate-passing finishing-residual, half a hard-gate fail
    ctxs = []
    for i in range(n):
        if i % 2 == 0:
            ctxs.append(json.dumps({"region": "all", "iteration": 1, "candidates_best_first": [
                {"drc": 4, "unconnected": 2, "kelvin_ok": True, "diffpair_ok": True, "gates_pass": True}],
                "best_candidate_gate_failures": []}))
        else:
            ctxs.append(json.dumps({"region": "all", "iteration": 3, "candidates_best_first": [
                {"drc": 40, "unconnected": 18, "kelvin_ok": True, "diffpair_ok": False, "gates_pass": False}],
                "best_candidate_gate_failures": ["diff pair USB_D not routed (18 ratlines)"]}))
    mw = max_workers or min(16, n)
    # serial baseline: one call
    t0 = time.time(); _ = J.swarm_judge(ctxs[:1], max_workers=1); serial1 = time.time() - t0
    # the swarm
    t0 = time.time(); res = J.swarm_judge(ctxs, max_workers=mw); wall = time.time() - t0
    ok = [r for r in res if isinstance(r, dict) and "action" in r]
    from collections import Counter
    actions = Counter(r.get("action") for r in ok)
    errors = [r for r in res if isinstance(r, dict) and "error" in r]
    return {"n": n, "max_workers": mw, "wall_s": round(wall, 2), "serial1_s": round(serial1, 2),
            "valid": len(ok), "errors": len(errors), "actions": dict(actions),
            "throughput_per_s": round(n / wall, 1) if wall else None,
            "speedup_vs_serial": round((serial1 * n) / wall, 1) if wall else None}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="cec_sweep -- full-pipeline sweep validation + swarm test")
    ap.add_argument("--route", action="store_true", help="also run the parallel route+judge sweep")
    ap.add_argument("--judge", choices=("default", "local"), default="default")
    ap.add_argument("--swarm", type=int, default=0, help="fire N concurrent local judges (0 = skip)")
    ap.add_argument("--boards", default="", help="comma list to override the route boards")
    ap.add_argument("--seeds", default="0,1")
    ap.add_argument("--passes", type=int, default=8)
    ap.add_argument("--opt-time", type=int, default=10)
    a = ap.parse_args(argv)

    print("=" * 78)
    print("CEC FULL SWEEP VALIDATION")
    print("=" * 78)

    print("\n[1] CONSTRAINTS sweep (full registry on every board)")
    cons = sweep_constraints(ALL_BOARDS)
    tot_err = 0
    for name, _ in ALL_BOARDS:
        r = cons.get(name, {})
        if "error" in r:
            print(f"  {name:14s} ERROR: {r['error']}")
            continue
        tot_err += r["ERROR"]
        mp = "min-pour-cross-section" in r["fails"]
        print(f"  {name:14s} FAIL={r['FAIL']:2d} PASS={r['PASS']:2d} N/A={r['N/A']:2d} "
              f"ERROR={r['ERROR']}  min-pour-x-sec={'FAIL' if mp else '(n/a or pass)'}")
    print(f"  -> total ERROR across all boards: {tot_err} (must be 0)")

    routes = {}
    if a.route:
        rboards = [b for b in (a.boards.split(",") if a.boards else ROUTE_BOARDS) if b]
        print(f"\n[2] ROUTE+JUDGE sweep (parallel, judge={a.judge}): {', '.join(rboards)}")
        routes = sweep_routes(rboards, judge=a.judge, seeds=a.seeds, passes=a.passes, opt_time=a.opt_time)
        for b in rboards:
            r = routes.get(b, {})
            print(f"  {b:20s} gates_pass={r.get('gates_pass')} drc={r.get('drc')} "
                  f"unconn={r.get('unconnected')} kelvin={r.get('kelvin_ok')} diff={r.get('diffpair_ok')} "
                  f"tier={r.get('tier')} ({r.get('secs')}s)")

    swarm = {}
    if a.swarm:
        print(f"\n[3] SWARM test ({a.swarm} concurrent local judges)")
        swarm = sweep_swarm(a.swarm)
        if swarm.get("skipped"):
            print(f"  skipped: {swarm['skipped']}")
        else:
            print(f"  N={swarm['n']} workers={swarm['max_workers']} wall={swarm['wall_s']}s "
                  f"throughput={swarm['throughput_per_s']}/s speedup~{swarm['speedup_vs_serial']}x "
                  f"vs serial | valid={swarm['valid']} errors={swarm['errors']} actions={swarm['actions']}")

    print("\n" + "=" * 78)
    ok = (tot_err == 0)
    print(f"SWEEP {'PASS' if ok else 'FAIL'}: constraints ERROR={tot_err}"
          + (f"; routed {len(routes)} board(s)" if routes else "")
          + (f"; swarm {swarm.get('valid','-')}/{a.swarm} valid" if swarm and not swarm.get('skipped') else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
