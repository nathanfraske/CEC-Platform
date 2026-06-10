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
import hashlib
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
    # CL-01 (2026-06-10): the corpus lives in two zones under corpus/ -- hash the whole
    # tree (staging + promoted + SCHEMA.md) deterministically so the manifest pins the
    # exact corpus state a run saw (AM-03 epoching keys off this). Legacy single-file
    # location still hashed when present (pre-migration checkouts).
    czones = os.path.join(ROOT, "corpus")
    if os.path.isdir(czones):
        h = hashlib.sha256()
        for dirpath, dirnames, filenames in sorted(os.walk(czones)):
            dirnames.sort()
            for fn in sorted(filenames):
                p = os.path.join(dirpath, fn)
                h.update(os.path.relpath(p, czones).encode())
                h.update(open(p, "rb").read())
        out["constraint_corpus_sha256"] = h.hexdigest()
    legacy = os.path.join(ROOT, "scripts", "constraints", "corpus-extracted.json")
    if os.path.isfile(legacy):
        out["legacy_constraint_corpus_sha256"] = sha256_file(legacy)
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

    return _write_line(rec, LEDGER_REL,
                       warn=f"no cec-runs repo found (CEC_RUNS_DIR / ../cec-runs / ~/cec-runs) "
                            f"-- run {rec['run_id']} NOT persisted")


def _write_line(rec, rel_path, *, warn):
    """Append one JSON line to <runs-repo>/<rel_path>. Single-writer by append; returns the
    record whether or not the ledger repo is present (a missing ledger never errors)."""
    base = runs_dir(create=True)
    if base is None:
        print(f"[cec_ledger] WARNING: {warn}", file=sys.stderr)
        return rec
    p = os.path.join(base, rel_path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec


# ---------------------------------------------------------------------------
# decision capture (DF-01 / DF-06 / PC-01) -- the forensic record schema.
# ---------------------------------------------------------------------------
# Capture cannot be retroactive (DF-01): the schema lands before the analytics matter.
# Every decision point in the pipeline -- corpus promote/reject/demote, a verdict, a
# preflight disposition, a swarm finding, a triage call, an extractor selection, a
# manager attribution, a judge ranking, a bandit allocation, an orchestrator schedule --
# emits one record. The human is one decider among many, not the only one observed.
#
# DF-06 adds three fields over DF-01: a machine-readable CLAIM (what the decision asserts
# about the world), a VERIFICATION HOOK from a closed vocabulary (which check ID / fixture
# / bench measurement / future event settles it), and a SETTLEMENT state (open ->
# provisional -> settled at a DF-07 grade).
#
# PC-01 capture criterion: a FULL record iff the decision carries a SETTLEABLE claim
# (claim + hook present); a claimless micro-decision takes the counter() path instead.
# A claim WITHOUT a hook is legal and scores zero forever -- vagueness is reward-neutral,
# never reward-positive (DF-06).

DECISION_REL = os.path.join("decisions", "decisions.jsonl")

# DF-01 taxonomy of decision classes (closed vocabulary).
DECISION_CLASSES = {
    "promote", "reject", "demote", "supersede", "scope-correct",   # corpus lifecycle
    "accept", "override-up", "override-down", "escalate",          # verdicts
    "confirmed-fixed", "dismissed-with-reason", "accepted-risk",   # preflight dispositions
    "policy-change", "spec-revision", "attribution-override",      # governance
    "finding", "triage", "extract", "rank", "allocate", "schedule",  # DF-06 generalization
}

# DF-06 verification-hook kinds (the closed vocabulary that settles a claim).
HOOK_KINDS = {"check_id", "fixture", "bench", "span_match", "golden", "future_event"}

# DF-07 settlement grades.
SETTLEMENT_STATES = {"open", "provisional", "settled"}
GRADES = {1, 2, 3, None}


def decision(*, decision_class, artifact, decider, verdict, cited_reasons=None,
             claim=None, hook=None, settlement=None, counterfactual=None,
             evidence_bundle_hash=None, covariates=None, blinded_view=None,
             policy_sha256=None, run_id=None, parent_run_id=None, extra=None):
    """Append one DF-01/DF-06 decision record. PC-01: a settleable claim (claim AND hook)
    yields a FULL record; a claimless decision is still recorded but flagged
    capture='counter-eligible' so the forensic layer can fold it into aggregates.

    decider: dict {kind: human|model, id, manifest?: {model, quant, prompt_hash, sampling}}.
    hook: dict {kind: one of HOOK_KINDS, ref} or None (a claim without a hook scores zero).
    settlement: dict {state, grade} or None (defaults to open / no grade).
    """
    if decision_class not in DECISION_CLASSES:
        raise ValueError(f"decision_class {decision_class!r} not in DF-01 taxonomy {sorted(DECISION_CLASSES)}")
    if hook is not None and hook.get("kind") not in HOOK_KINDS:
        raise ValueError(f"hook kind {hook.get('kind')!r} not in DF-06 vocabulary {sorted(HOOK_KINDS)}")

    settleable = bool(claim) and bool(hook)
    settlement = settlement or {"state": "open", "grade": None}
    if settlement.get("state") not in SETTLEMENT_STATES:
        raise ValueError(f"settlement state {settlement.get('state')!r} not in {sorted(SETTLEMENT_STATES)}")
    if settlement.get("grade") not in GRADES:
        raise ValueError(f"settlement grade {settlement.get('grade')!r} not in {sorted(g for g in GRADES if g)} or null")

    rec = {
        "decision_id": run_id or _new_decision_id(),
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "decision_class": decision_class,
        "artifact": artifact,                       # entry id | candidate hash | run id
        "decider": decider,                         # human or model+manifest
        "verdict": verdict,
        "cited_reasons": cited_reasons or [],       # DF-01: click-to-cite from the bundle, not free text
        "evidence_bundle_hash": evidence_bundle_hash,  # exactly what was in front of the decider
        "claim": claim,                             # DF-06: machine-readable assertion about the world
        "hook": hook,                               # DF-06: closed-vocab verification hook (None => scores zero)
        "settlement": settlement,                   # DF-06/07: open|provisional|settled + grade 1/2/3
        "settleable": settleable,                   # PC-01 capture criterion
        "capture": "full" if settleable else "counter-eligible",
        "counterfactual": counterfactual,           # DF-01 stub: what the entry would have gated / shipped
        "covariates": covariates,                   # DF-01: ambient only (queue depth, session position, elapsed)
        "blinded_view": blinded_view,               # DF-02: which provenance fields were hidden at decision time
        "policy_sha256": policy_sha256,             # the policy this decision ran under
        "manifest": manifest(),
        "parent_run_id": parent_run_id,
    }
    if extra:
        rec["extra"] = extra
    return _write_line(rec, DECISION_REL,
                       warn=f"no cec-runs repo -- decision {rec['decision_id']} NOT persisted")


def settle(decision_id, *, state, grade=None, evidence=None, regrades=None):
    """Append-only SETTLEMENT update for an earlier decision (DF-07: re-graded whenever
    Grade 1/2 evidence arrives). Never edits the original line -- a new line carrying
    `settles: <decision_id>` (the same append-only discipline as `corrects`)."""
    if state not in SETTLEMENT_STATES:
        raise ValueError(f"settlement state {state!r} not in {sorted(SETTLEMENT_STATES)}")
    if grade not in GRADES:
        raise ValueError(f"grade {grade!r} not in {sorted(g for g in GRADES if g)} or null")
    rec = {
        "decision_id": _new_decision_id(),
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "decision_class": "attribution-override",   # a settlement is a governance event
        "settles": decision_id,
        "settlement": {"state": state, "grade": grade},
        "evidence": evidence,
        "regrades": regrades,                       # prior grade history if this is a re-grade
        "manifest": manifest(),
    }
    return _write_line(rec, DECISION_REL,
                       warn=f"no cec-runs repo -- settlement of {decision_id} NOT persisted")


def counter(stream, key, *, n=1, board=None):
    """AM-06: high-volume claimless micro-decisions (per-candidate bandit draws, raw swarm
    findings, render views) stream to a per-stream SIDECAR as aggregate counters, with the
    hashes/pointers (not the bulk) flowing to the main ledger. Single-writer by append."""
    rel = os.path.join("decisions", "counters", f"{stream}.jsonl")
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stream": stream, "key": key, "n": n, "board": board,
    }
    return _write_line(rec, rel, warn=f"no cec-runs repo -- counter {stream}/{key} NOT persisted")


def _new_decision_id():
    return f"D-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{uuid.uuid4().hex[:8]}"


def read_decisions():
    d = runs_dir()
    if d is None:
        return []
    p = os.path.join(d, DECISION_REL)
    if not os.path.isfile(p):
        return []
    out = []
    for ln in open(p):
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                print("[cec_ledger] WARNING: skipping malformed decision line", file=sys.stderr)
    return out


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

    # DF-01/DF-06 decision capture
    ad = sub.add_parser("decision", help="append a DF-01/DF-06 decision record")
    ad.add_argument("--class", dest="dclass", required=True, help=f"one of {sorted(DECISION_CLASSES)}")
    ad.add_argument("--artifact", required=True, help="entry id | candidate hash | run id")
    ad.add_argument("--decider", required=True, help="decider id (human login or model name)")
    ad.add_argument("--decider-kind", default="human", choices=["human", "model"])
    ad.add_argument("--verdict", required=True)
    ad.add_argument("--reason", action="append", default=[], help="cited reason (repeatable; click-to-cite)")
    ad.add_argument("--claim", default=None, help="machine-readable assertion (DF-06)")
    ad.add_argument("--hook-kind", default=None, choices=sorted(HOOK_KINDS))
    ad.add_argument("--hook-ref", default=None)
    ad.add_argument("--bundle-hash", default=None)

    # DF-07 settlement / CL-13 outcome label
    asl = sub.add_parser("settle", help="append-only settlement of a decision (DF-07)")
    asl.add_argument("decision_id")
    asl.add_argument("--state", required=True, choices=sorted(SETTLEMENT_STATES))
    asl.add_argument("--grade", type=int, default=None, choices=[1, 2, 3])
    asl.add_argument("--evidence", default=None)

    alb = sub.add_parser("label", help="CL-13 reality outcome -> Grade-1 settlement of a decision")
    alb.add_argument("decision_id")
    alb.add_argument("--outcome", required=True, choices=["vindicated", "refuted"])
    alb.add_argument("--evidence", required=True, help="bench/field/fab evidence ref")

    a = ap.parse_args(argv)
    if a.cmd == "decision":
        hook = {"kind": a.hook_kind, "ref": a.hook_ref} if a.hook_kind else None
        rec = decision(decision_class=a.dclass, artifact=a.artifact,
                       decider={"kind": a.decider_kind, "id": a.decider},
                       verdict=a.verdict, cited_reasons=a.reason, claim=a.claim, hook=hook,
                       evidence_bundle_hash=a.bundle_hash)
        print(json.dumps(rec, indent=2, sort_keys=True))
    elif a.cmd == "settle":
        rec = settle(a.decision_id, state=a.state, grade=a.grade, evidence=a.evidence)
        print(json.dumps(rec, indent=2, sort_keys=True))
    elif a.cmd == "label":
        # CL-13: a physical outcome is Grade-1 ground truth; it SETTLES the decision's claim.
        rec = settle(a.decision_id, state="settled", grade=1,
                     evidence=f"{a.outcome}: {a.evidence}")
        print(json.dumps(rec, indent=2, sort_keys=True))
    elif a.cmd == "append":
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
