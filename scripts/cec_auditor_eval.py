#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
"""V4-Flash auditor packet-replay eval (owner 2026-06-12).

The DeepSeek-V4-Flash deep auditor is now the DEFAULT T5 chair (cec_fullstack.resolve_auditor). Before it
is trusted, REPLAY a recorded round PACKET from a real run through it and record what it produces vs the
Sonnet baseline that ran that round live -- a held-out, reproducible eval, not a vibe. This is the eval-gate
evidence for the seat (the full per-round ECONOMICS -- tokens/s, wall, vs the ~17-min Sonnet baseline --
land from the first V4-Flash overnight; this harness validates the seat produces a competent finding).

A 'packet' = one round's metric record (from a run's measurement.jsonl) + the pour-clip signal; the auditor
reads those + a minimal loop-state. We replay through cec_fullstack.audit(model) and compare the verdict /
failure_class / root_cause-presence to the round's recorded Sonnet finding.

    docker exec ... python3 scripts/cec_auditor_eval.py \
        --run docs/fullstack-run-2026-06-11-validation --rounds 1,2 --model deepseek-v4-flash
"""
import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def load_packet(run_dir, rnd):
    """Reconstruct (rec, lr, baseline) for round `rnd` from a run's artifacts."""
    rec = None
    mj = os.path.join(run_dir, "measurement.jsonl")
    with open(mj) as fh:
        for ln in fh:
            if ln.strip() and json.loads(ln).get("round") == rnd:
                rec = json.loads(ln)
                break
    if rec is None:
        return None
    # the auditor reads these fields; default the ones not in the measurement row
    rec.setdefault("reasons", [])
    rec.setdefault("fem_flags", [])
    rec.setdefault("stub_summary", {})
    rec.setdefault("diffpair_ok", rec.get("diffpair_ok"))
    pourcheck = ({"det_clipped_nets": rec.get("pour_clipped_nets"), "facts": {}}
                 if rec.get("pour_clipped_nets") else None)
    lr = {"scorer_penalties": {"plane_signal_mm": 50.0, "drc": 50.0, "unconnected": 5.0},
          "manager_rules": [], "injections": [], "rejections": [],
          "diagnoses": [], "refuted_metrics": []}
    baseline = {}
    bf = os.path.join(run_dir, "findings", f"round-{rnd:03d}-sonnet.json")
    if os.path.isfile(bf):
        try:
            baseline = json.load(open(bf))
        except Exception:                                        # noqa: BLE001
            pass
    return rec, lr, pourcheck, baseline


def replay(model, rec, lr, pourcheck, rnd):
    import cec_fullstack as fs
    t0 = time.time()
    out = fs.audit(rec, lr, rnd, model, pourcheck=pourcheck, intents_src=rec.get("intents_src", "model"))
    return out, round(time.time() - t0, 1)


def run(run_dir, rounds, model):
    rows = []
    for rnd in rounds:
        pk = load_packet(run_dir, rnd)
        if pk is None:
            rows.append({"round": rnd, "error": "round not found in run"})
            continue
        rec, lr, pourcheck, baseline = pk
        out, wall = replay(model, rec, lr, pourcheck, rnd)
        rows.append({
            "round": rnd, "model": model, "wall_s": wall,
            "verdict": out.get("verdict"), "failure_class": out.get("failure_class"),
            "root_cause_present": bool((out.get("root_cause") or "").strip()),
            "root_cause": (out.get("root_cause") or "")[:300],
            "error": out.get("error"),
            "baseline_sonnet": {"verdict": baseline.get("verdict"),
                                "failure_class": baseline.get("failure_class")},
            "agrees_with_baseline_class": (out.get("failure_class") == baseline.get("failure_class")
                                           if baseline else None),
        })
    ok = [r for r in rows if not r.get("error")]
    return {
        "eval": "v4-flash auditor packet-replay", "run": os.path.relpath(run_dir, ROOT),
        "model": model, "n_rounds": len(rounds), "n_ok": len(ok),
        "competent_findings": sum(1 for r in ok if r["verdict"] and r["root_cause_present"]),
        "mean_wall_s": round(sum(r["wall_s"] for r in ok) / len(ok), 1) if ok else None,
        "class_agreement_with_sonnet": sum(1 for r in ok if r.get("agrees_with_baseline_class")),
        "rows": rows,
        "note": ("Validates the seat emits a verdict + bankable root_cause on real packets. Per-round "
                 "ECONOMICS (tokens/s, wall vs the ~17-min Sonnet baseline) are recorded from the first "
                 "V4-Flash overnight, appended here. Class-agreement with Sonnet is informational, not a "
                 "target -- the seats decorrelate by design."),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="docs/fullstack-run-2026-06-11-validation")
    ap.add_argument("--rounds", default="1", help="comma list of round numbers to replay")
    ap.add_argument("--model", default=None, help="default = resolve_auditor() (V4-Flash)")
    ap.add_argument("--url", default=None, help="deep-auditor endpoint, e.g. the WINDOWS-hosted V4 "
                    "http://<win-host>:<port>/v1 -- V4-Flash cannot run under the WSL broker (it pages "
                    "at the 125 GB ceiling). Sets CEC_FS_AUDITOR_URL.")
    ap.add_argument("--out", default="docs/det-inspection/auditor-v4flash-replay.json")
    a = ap.parse_args()
    if a.url:                                            # MUST set before importing cec_fullstack
        os.environ["CEC_FS_AUDITOR_URL"] = a.url         # (DEEP_AUDITOR_URL is read at import)
    import cec_fullstack as fs
    model = a.model or fs.resolve_auditor(None)
    rounds = [int(x) for x in a.rounds.split(",") if x.strip()]
    rep = run(os.path.join(ROOT, a.run), rounds, model)
    outp = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    json.dump(rep, open(outp, "w"), indent=1)
    for r in rep["rows"]:
        if r.get("error"):
            print(f"  r{r['round']}: ERROR {r['error']}")
        else:
            print(f"  r{r['round']}: verdict={r['verdict']} class={r['failure_class']} "
                  f"root_cause={'yes' if r['root_cause_present'] else 'NO'} {r['wall_s']}s "
                  f"(sonnet:{r['baseline_sonnet']['verdict']}/{r['baseline_sonnet']['failure_class']})")
    print(f"\n{rep['model']}: {rep['competent_findings']}/{rep['n_ok']} competent findings, "
          f"mean {rep['mean_wall_s']}s/round -> {a.out}")
