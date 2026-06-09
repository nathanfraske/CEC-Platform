#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_ledger -- durable run ledger + determinism manifest (addendum SB-01).
# ============================================================================
# Append-only record of every pipeline run so restarts, best-attempts, and
# cross-session convergence detection have MEMORY, and "board = f(decision log)"
# is actually replayable. One JSON line per run in <runs-repo>/runs/ledger.jsonl.
#
# The ledger lives in the SIBLING cec-runs repo (owner decision, 2026-06-09 --
# run churn stays out of the design repo). Location resolution, first hit wins:
#   1. $CEC_RUNS_DIR
#   2. <design-repo>/../cec-runs        (the sibling clone)
#   3. ~/cec-runs
# Absent everywhere -> append() degrades to a one-line warning and returns the
# record (a missing ledger must never break a route run).
#
# Append-only discipline: corrections are NEW lines carrying `corrects:
# <old run_id>`; nothing is ever edited or deleted. Large artifacts stay
# artifacts -- the ledger stores hashes and pointers.
#
# Dependency-free on purpose (no pcbnew, no cec_score): importable on any host,
# the same posture as cec_toolchain (R-05).
#
# CLI:
#   python3 scripts/cec_ledger.py append --board eps-8pin --mode route \
#       --verdict accept --board-file build/route/eps-8pin/eps8pin-module-routed.kicad_pcb
#   python3 scripts/cec_ledger.py query  [--board B] [--since 2026-06-01] [--mode route]
#   python3 scripts/cec_ledger.py lineage <run_id>
# ============================================================================
import os
import sys
import json
import time
import uuid
import argparse
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from cec_toolchain import sha256_file  # noqa: E402  (dependency-free)

LEDGER_REL = os.path.join("runs", "ledger.jsonl")


# ---------------------------------------------------------------------------
# location
# ---------------------------------------------------------------------------
def runs_dir(create=False):
    """Resolve the cec-runs repo dir (see module header). None if absent and not create."""
    cands = [os.environ.get("CEC_RUNS_DIR"),
             os.path.join(os.path.dirname(ROOT), "cec-runs"),
             os.path.expanduser("~/cec-runs")]
    for c in cands:
        if c and os.path.isdir(c):
            return c
    if create:
        d = cands[1] if cands[0] is None else cands[0]
        os.makedirs(os.path.join(d, "runs"), exist_ok=True)
        return d
    return None


def ledger_path(create=False):
    d = runs_dir(create=create)
    if d is None:
        return None
    p = os.path.join(d, LEDGER_REL)
    if create:
        os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# determinism manifest
# ---------------------------------------------------------------------------
def _git(*args):
    try:
        # safe.directory: in the routing container the repo is host-owned while git runs
        # as root, and the dubious-ownership guard would blank the manifest's scripts_sha.
        r = subprocess.run(["git", "-c", f"safe.directory={ROOT}", "-C", ROOT, *args],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def _kicad_pin():
    """The pinned KiCad series from versions.env (the format pin, independent of any
    locally installed kicad-cli)."""
    try:
        for ln in open(os.path.join(ROOT, "versions.env")):
            if "KICAD_SERIES" in ln and ":=" in ln:
                return ln.split(":=")[1].rstrip('}"\n ')
    except OSError:
        pass
    return None


def _kicad_cli_version():
    try:
        import cec_toolchain as tc
        cli = tc.kicad_cli()
        if cli:
            r = subprocess.run([cli, "version"], capture_output=True, text=True, timeout=10)
            return r.stdout.strip().splitlines()[0] if r.returncode == 0 else None
    except Exception:
        pass
    return None


def _fr_version():
    try:
        import cec_fr
        return cec_fr.FR_VERSION
    except Exception:
        return None


def manifest():
    """The determinism manifest: same manifest + same inputs => same board (FR 1.7.0 is
    deterministic). Emitted into every ledger line AND every decision log (SB-01: a log
    is self-describing)."""
    return {
        "kicad_series_pin": _kicad_pin(),          # the format pin (versions.env)
        "kicad_cli": _kicad_cli_version(),         # the actually-resolved tool (None off-runner)
        "freerouting": _fr_version(),
        "scripts_sha": _git("rev-parse", "HEAD"),
        "scripts_dirty": bool(_git("status", "--porcelain")),
        "python": ".".join(str(v) for v in sys.version_info[:3]),
    }


def input_hashes(*, netlist=None, board=None):
    """Hashes of the run's inputs. The constraint corpus is always hashed (the compiler
    reads it); netlist/board hashes when the paths exist."""
    out = {}
    corpus = os.path.join(ROOT, "scripts", "constraints", "corpus-extracted.json")
    if os.path.isfile(corpus):
        out["constraint_corpus_sha256"] = sha256_file(corpus)
    if netlist and os.path.isfile(netlist):
        out["netlist_sha256"] = sha256_file(netlist)
    if board and os.path.isfile(board):
        out["input_board_sha256"] = sha256_file(board)
    return out


# ---------------------------------------------------------------------------
# append / query / lineage
# ---------------------------------------------------------------------------
def new_run_id():
    return f"R-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{uuid.uuid4().hex[:8]}"


def append(*, board, mode, verdict=None, board_file=None, netlist=None, input_board=None,
           artifact=None, elapsed_s=None, parent_run_id=None, corrects=None, extra=None,
           run_id=None):
    """Append one run line. Returns the record dict (with its run_id) whether or not the
    ledger repo is present -- a missing ledger degrades to a warning, never an error."""
    rec = {
        "run_id": run_id or new_run_id(),
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "board": board,
        "mode": mode,                                  # route | synth-run | sweep | candidates | ...
        "inputs": input_hashes(netlist=netlist, board=input_board),
        "manifest": manifest(),
        "outputs": {},
        "verdict": verdict,
        "elapsed_s": elapsed_s,
        "parent_run_id": parent_run_id,                # restart lineage
    }
    if board_file and os.path.isfile(board_file):
        rec["outputs"]["board"] = os.path.basename(board_file)
        rec["outputs"]["board_sha256"] = sha256_file(board_file)
    if artifact:
        rec["outputs"]["artifact"] = artifact
    if corrects:
        rec["corrects"] = corrects                     # append-only corrections
    if extra:
        rec["extra"] = extra

    p = ledger_path(create=True) if runs_dir() else None
    if p is None:
        print(f"[cec_ledger] WARNING: no cec-runs repo found (CEC_RUNS_DIR / ../cec-runs / "
              f"~/cec-runs) -- run {rec['run_id']} NOT persisted", file=sys.stderr)
        return rec
    with open(p, "a") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec


def read_all():
    p = ledger_path()
    if not p or not os.path.isfile(p):
        return []
    out = []
    with open(p) as fh:
        for ln in fh:
            ln = ln.strip()
            if ln:
                try:
                    out.append(json.loads(ln))
                except json.JSONDecodeError:
                    print(f"[cec_ledger] WARNING: skipping malformed line", file=sys.stderr)
    return out


def query(board=None, since=None, mode=None):
    recs = read_all()
    if board:
        recs = [r for r in recs if r.get("board") == board]
    if mode:
        recs = [r for r in recs if r.get("mode") == mode]
    if since:
        recs = [r for r in recs if r.get("ts", "") >= since]
    return recs


def lineage(run_id):
    """Walk parent_run_id back to the root: [oldest, ..., run_id]. Reconstructs a restart
    chain so stage-6 convergence reads improvement across the chain, not one run."""
    by_id = {r["run_id"]: r for r in read_all()}
    chain = []
    cur = by_id.get(run_id)
    seen = set()
    while cur is not None and cur["run_id"] not in seen:
        chain.append(cur)
        seen.add(cur["run_id"])
        cur = by_id.get(cur.get("parent_run_id"))
    return list(reversed(chain))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="CEC run ledger (SB-01): append/query/lineage "
                                 "over the sibling cec-runs repo")
    sub = ap.add_subparsers(dest="cmd", required=True)

    aa = sub.add_parser("append")
    aa.add_argument("--board", required=True)
    aa.add_argument("--mode", required=True)
    aa.add_argument("--verdict", default=None)
    aa.add_argument("--board-file", default=None, help="output board (hashed)")
    aa.add_argument("--netlist", default=None)
    aa.add_argument("--input-board", default=None)
    aa.add_argument("--artifact", default=None)
    aa.add_argument("--elapsed", type=float, default=None)
    aa.add_argument("--parent", default=None, help="parent run_id (restart lineage)")
    aa.add_argument("--corrects", default=None, help="run_id this line corrects (append-only)")

    aq = sub.add_parser("query")
    aq.add_argument("--board", default=None)
    aq.add_argument("--since", default=None, help="ISO date floor, e.g. 2026-06-01")
    aq.add_argument("--mode", default=None)

    al = sub.add_parser("lineage")
    al.add_argument("run_id")

    a = ap.parse_args(argv)
    if a.cmd == "append":
        rec = append(board=a.board, mode=a.mode, verdict=a.verdict, board_file=a.board_file,
                     netlist=a.netlist, input_board=a.input_board, artifact=a.artifact,
                     elapsed_s=a.elapsed, parent_run_id=a.parent, corrects=a.corrects)
        print(json.dumps(rec, indent=2, sort_keys=True))
    elif a.cmd == "query":
        for r in query(board=a.board, since=a.since, mode=a.mode):
            print(json.dumps(r, sort_keys=True))
    elif a.cmd == "lineage":
        chain = lineage(a.run_id)
        if not chain:
            print(f"no run {a.run_id!r} in the ledger", file=sys.stderr)
            return 1
        for r in chain:
            print(f"{r['run_id']}  {r.get('ts')}  {r.get('board')}  {r.get('mode')}  "
                  f"verdict={r.get('verdict')}  parent={r.get('parent_run_id')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
