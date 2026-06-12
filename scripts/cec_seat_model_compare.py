"""Regression probe: can the VISION model (cec-vision-judge) also serve the NON-vision text seats
(the CL-24 verifier charters) so the pipeline runs one model for both seats instead of swapping
worker<->vision every round? Runs the 3 charter seats on a real captured finding, on each model,
and reports verdict agreement / output validity / latency.

  python3 scripts/cec_seat_model_compare.py            # round-1 finding, worker vs vision-judge

Baseline = cec-worker (today's text-seat model). Candidate = cec-vision-judge with nothink (the
grammar-safe config). A regression = the candidate returns invalid JSON, disagrees with the
baseline verdict, or is materially slower. Each model is warmed once and its 3 seats run together
(minimize broker swaps). The deep-tier sampling/scribe guards in _chat_json still apply.
"""
import argparse
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cec_judge_local as jl                                     # noqa: E402
import cec_verifier as cv                                       # noqa: E402

BROKER = os.environ.get("CEC_VLLM_URL", "http://localhost:8080/v1")
RUN = os.path.join(ROOT, "docs", "fullstack-run-2026-06-11-validation")
OWNED_LEVERS = ("router passes/opt_time, FR-02 waypoint intents (incl. routing an OFFENDING "
                "foreign signal net AROUND a sense corridor), bake_hints keepouts, GR-02 repair "
                "battery (shift/swap/via), power pours")


def warm(model, timeout=960):
    try:
        reg = json.load(urllib.request.urlopen(BROKER.rstrip("/v1") + "/broker/models", timeout=10))
        if (reg.get("models", {}).get(model) or {}).get("running"):
            return True
    except Exception:                                            # noqa: BLE001
        pass
    body = {"model": model, "messages": [{"role": "user", "content": "ok"}], "max_tokens": 1}
    req = urllib.request.Request(BROKER + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "X-CEC-Client": "seat-compare"})
    try:
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except Exception as e:                                       # noqa: BLE001
        print(f"  warm({model}) failed: {type(e).__name__}: {e}")
        return False


def build_case(rnd):
    sj = json.load(open(os.path.join(RUN, "findings", f"round-{rnd:03d}-sonnet.json")))
    meas = None
    for line in open(os.path.join(RUN, "measurement.jsonl")):
        if line.strip() and json.loads(line)["round"] == rnd:
            meas = json.loads(line)
    facts = json.load(open(os.path.join(RUN, "vision", f"pour-r{rnd:03d}.json"))).get("facts", {})
    finding = {"issue": sj.get("reasoning", "")[:600], "root_cause": sj.get("root_cause"),
               "scorer_penalty": sj.get("scorer_penalty"), "manager_rule": sj.get("manager_rule")}
    # bundle-completeness fix: the evidence carries the SAME pour/FEM facts the auditor cited
    evidence = {k: meas.get(k) for k in ("drc", "kelvin_ok", "plane_signal_mm", "unconnected",
                                         "max_T")}
    evidence["pour_facts"] = facts
    ctx = {"rules_excerpt": "[]", "evidence": json.dumps(evidence), "levers": OWNED_LEVERS,
           "metrics": json.dumps([{"round": rnd, "drc": meas.get("drc"),
                                   "kelvin_ok": meas.get("kelvin_ok")}])}
    return finding, ctx


def run_seats(model, finding, ctx, nothink):
    rows = []
    for charter, spec in cv.CHARTERS.items():
        user = spec["slice"](finding, ctx)
        t0 = time.time()
        try:
            out = jl._chat_json(spec["system"], user, cv.VERDICT_SCHEMA, name="verifier",
                                temperature=spec["temperature"], max_tokens=512, model=model,
                                url=BROKER, timeout=600, nothink=nothink)
            rows.append({"charter": charter, "verdict": out.get("verdict"),
                         "failure_class": out.get("failure_class"),
                         "reason": out.get("reason", ""), "ok": True,
                         "secs": round(time.time() - t0, 1)})
        except Exception as e:                                   # noqa: BLE001
            rows.append({"charter": charter, "verdict": f"ERR:{type(e).__name__}", "ok": False,
                         "secs": round(time.time() - t0, 1), "err": str(e)[:120]})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int, default=1)
    ap.add_argument("--candidate", default="cec-vision-judge",
                    help="the model to test against the cec-worker baseline")
    ap.add_argument("--candidate-nothink", action="store_true",
                    help="run the candidate with enable_thinking=false (needed for Qwen3-VL grammar)")
    ap.add_argument("--out", default=None, help="write the structured result JSON here (eval artifact)")
    a = ap.parse_args()
    finding, ctx = build_case(a.round)
    print(f"finding (round {a.round}): scorer_penalty={json.dumps(finding['scorer_penalty'])[:90]}")
    results = {}
    # candidate first (warm), then the cec-worker baseline (one swap)
    for model, nothink in [(a.candidate, a.candidate_nothink), ("cec-worker", False)]:
        print(f"\n=== {model} (nothink={nothink}) ===")
        if not warm(model):
            print(f"  {model} DOWN"); results[model] = None; continue
        results[model] = run_seats(model, finding, ctx, nothink)
        for r in results[model]:
            print(f"  {r['charter']:<20} verdict={r['verdict']:<10} "
                  f"fc={r.get('failure_class')}  ok={r['ok']}  {r['secs']}s")

    base, cand = results.get("cec-worker"), results.get(a.candidate)
    print(f"\n=== REGRESSION SUMMARY (baseline cec-worker vs candidate {a.candidate}) ===")
    if not base or not cand:
        print("  inconclusive (a model was down)")
        return
    agree = sum(1 for b, c in zip(base, cand) if b["ok"] and c["ok"] and b["verdict"] == c["verdict"])
    cand_valid = sum(1 for c in cand if c["ok"])
    for b, c in zip(base, cand):
        flag = "OK " if (b["ok"] and c["ok"] and b["verdict"] == c["verdict"]) else "DIFF"
        print(f"  [{flag}] {b['charter']:<20} worker={b['verdict']:<10} vision={c['verdict']:<10} "
              f"(Δlatency {c['secs']-b['secs']:+.1f}s)")
    bw = sum(r["secs"] for r in base); vw = sum(r["secs"] for r in cand)
    print(f"\n  verdict agreement: {agree}/3   candidate valid JSON: {cand_valid}/3")
    print(f"  total latency: worker {bw:.1f}s  vision {vw:.1f}s  (vision {vw/bw:.2f}x)")
    print(f"  VERDICT: {'NO REGRESSION (unify viable)' if agree == 3 and cand_valid == 3 else 'REGRESSION — see DIFF/invalid above'}")
    print("\n=== SEAT REASONING (both models) ===")
    for b, c in zip(base, cand):
        print(f"\n[{b['charter']}]")
        print(f"  worker ({b['verdict']}): {str(b.get('reason',''))[:420]}")
        print(f"  vision ({c['verdict']}): {str(c.get('reason',''))[:420]}")
    if a.out:
        report = {"round": a.round, "baseline": "cec-worker", "candidate": a.candidate,
                  "candidate_nothink": a.candidate_nothink, "agreement": f"{agree}/3",
                  "candidate_valid_json": f"{cand_valid}/3",
                  "latency_s": {"worker": round(bw, 1), "candidate": round(vw, 1)},
                  "verdict": "no_regression" if agree == 3 and cand_valid == 3 else "see_diffs",
                  "baseline_rows": base, "candidate_rows": cand}
        json.dump(report, open(a.out, "w"), indent=1)
        print(f"\nartifact -> {a.out}")


if __name__ == "__main__":
    main()
