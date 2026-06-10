#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_extractor_eval -- the CL-19 extractor FIDELITY eval (rulings 1,4,5,6).
# ============================================================================
# Labeled (trace, gold) pairs -> the extractor under test -> the shared span
# verifier -> per-register report -> the gate of record.
#
#   * REGISTERS (R1): every case carries register: reconstructed | real.
#     The GATE-OF-RECORD metric computes on the REAL register only --
#     reconstructed cases are structural smoke coverage and dev material
#     (an extractor certified only against clean reconstructions is certified
#     for a world it will never see).
#   * ZERO-TOLERANCE classes (R5), any one fails the gate for that
#     model+prompt MANIFEST (never other manifests, never unrelated work):
#       - hallucinated verdict: any REQUIRED span fails cec_span_verify
#         anywhere in the trace. Correct-but-unsupported COUNTS (fidelity is
#         the property under test; truth settles elsewhere in DF-07 currency).
#       - span-not-found (same mechanism, finding-level)
#       - synthesis on a no-conclusion trace (must return no_conclusion)
#       - ratification distractor selected (RB-03 forced choice)
#   * SCORED class: field accuracy on the real register; starting bar 90%
#     (owner-settable in the gate record).
#   * GATE OF RECORD (R4): the result is RECORDED by the owner into
#     cec-policy.json eval_gates/bindings (CODEOWNERS-gated -- the recorded
#     PASS is itself the consent act). This harness emits the record body +
#     a ledger sidecar so report_hash resolves forever. Per-PR CI runs the
#     STRUCTURAL half only (schema validation, shared-verifier identity,
#     property tests) -- the live eval is the pre-binding ritual.
#   * BURN DISCIPLINE (R6): tests/eval/extractor/ is the tunable set;
#     tests/holdout/extractor/ is never touched by prompt iteration (CI greps
#     for references). grade: smoke until the holdout's adjudication-fed
#     growth earns statistical at an owner-set N.
#
#   python3 scripts/cec_extractor_eval.py structural          # CI half, no model
#   python3 scripts/cec_extractor_eval.py run [--model M]     # live eval (broker)
#   python3 scripts/cec_extractor_eval.py sha                 # current eval_set_sha
#   python3 scripts/cec_extractor_eval.py gate-record <report.json>  # record body
# ============================================================================
import argparse, glob, hashlib, json, os, re, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cec_span_verify                                        # noqa: E402
import cec_verdict_core                                       # noqa: E402

EVAL_DIR = os.path.join(ROOT, "tests", "eval", "extractor")
BROKER = os.environ.get("CEC_VLLM_URL", "http://localhost:8080/v1").rstrip("/")
DEFAULT_MODEL = "cec-worker-quality"          # the CL-15 extractor seat (27B)
FIELD_ACCURACY_BAR = 0.90                     # owner-settable in the gate record

# The production extraction prompt UNDER TEST. prompt_sha pins it: any edit
# changes the manifest, which voids the recorded gate for the old manifest.
EXTRACT_PROMPT = """You are the deterministic EXTRACTOR in a hardware-review pipeline. You are given an
ANALYST TRACE about one PCB candidate. Compile the analyst's conclusions into JSON
(schema cec-verdict-core/1). HARD RULES:
- Source the verdict ONLY from the trace's '## Conclusions' section when one exists
  (quote basis_spans verbatim from it). If there is NO conclusions section and the
  trace reaches no stated conclusion, return verdict value "no_conclusion" with empty
  basis_spans and NO findings -- never synthesize.
- Every finding needs evidence_spans QUOTED VERBATIM from the trace (>=20 chars),
  locus refs/nets exactly as the trace names them, a mechanism in YOUR words, a
  severity (info|warn|block-candidate), and a verification_hook
  (type: check|fixture|bench|datasheet + ref) the trace itself points at.
- Report ONLY what the analyst concluded. Asides the analyst raised and dismissed are
  NOT findings. Never add knowledge of your own.
Return ONLY the JSON object."""

RATIFY_PROMPT = """You are the ANALYST being asked to ratify a compression of your own trace (RB-03
forced choice). Below is YOUR trace and two candidate verdict summaries, A and B, plus
option C ("neither"). Choose the one that faithfully states YOUR conclusion. Answer
with exactly one letter: A, B, or C."""


# ----------------------------------------------------------------- loading --
def load_cases(eval_dir=EVAL_DIR):
    out = []
    for path in sorted(glob.glob(os.path.join(eval_dir, "cases", "*.json"))):
        for c in json.load(open(path, encoding="utf-8")):
            c["_file"] = os.path.basename(path)
            out.append(c)
    return sorted(out, key=lambda c: c["id"])


def eval_set_sha(eval_dir=EVAL_DIR):
    """Stable hash of the eval set (gate-record staleness key). Holdout is
    deliberately EXCLUDED -- the gate cites the eval set it ran on."""
    h = hashlib.sha256()
    for path in sorted(glob.glob(os.path.join(eval_dir, "cases", "*.json"))):
        h.update(os.path.basename(path).encode())
        h.update(open(path, "rb").read())
    return h.hexdigest()


# ------------------------------------------------------------------ scoring --
def _facts_for(board):
    if not board:
        return None
    import cec_facts
    b = cec_facts.find_board(board)
    return cec_facts.board_facts(b) if b else None


def _has_conclusions(trace):
    return bool(re.search(r"^##\s*conclusions\b", trace, re.I | re.M))


def _conclusions_slice(trace):
    """The conclusions section is the LAST line-anchored heading, never the
    first: real analyst traces MENTION the literal heading mid-rumination
    while planning the answer (measured on the first M2.7 real trace,
    2026-06-10), and the section is terminal by construction (CL-15)."""
    ms = list(re.finditer(r"^##\s*conclusions\b.*?$", trace, re.I | re.M))
    return trace[ms[-1].start():] if ms else ""


def score_case(case, core_json):
    """Score one extractor output against one case. -> result dict with
    zero_tolerance failures + field accuracy components."""
    res = {"id": case["id"], "register": case.get("register", "reconstructed"),
           "kind": case.get("kind", "standard"), "zt": [], "fields": {}}
    try:
        core = json.loads(core_json) if isinstance(core_json, str) else core_json
    except Exception as e:                                    # noqa: BLE001
        res["zt"].append({"class": "schema", "reason": "unparseable JSON: %s" % e})
        return res
    schema_errs = cec_verdict_core.validate(core)
    gold = case["gold"]
    trace = case["trace"]

    # synthesis on a no-conclusion trace -- checked FIRST (schema errors on a
    # correct bare no_conclusion shape must not mask the real class)
    if case.get("kind") == "no-conclusion":
        if (core.get("verdict") or {}).get("value") != "no_conclusion" \
                or core.get("findings"):
            res["zt"].append({"class": "synthesis-on-no-conclusion",
                              "reason": "verdict=%r findings=%d"
                              % ((core.get("verdict") or {}).get("value"),
                                 len(core.get("findings") or []))})
        return res

    if schema_errs:
        res["zt"].append({"class": "schema", "reason": "; ".join(schema_errs[:4])})
        return res

    # span fidelity through THE shared verifier (hallucination = unsupported)
    v = cec_span_verify.verify_verdict(core, trace, _facts_for(case.get("board")))
    for f in v["failures"]:
        cls = ("hallucinated-verdict" if f["field"].startswith("verdict")
               else "span-not-found")
        res["zt"].append({"class": cls, **f})

    # conclusions-sourcing rule: basis spans must come from the conclusions
    # section when one exists (outside-sourced -> the RB-03 path, not a pass)
    if _has_conclusions(trace):
        concl = cec_span_verify.normalize(_conclusions_slice(trace))
        for sp in (core.get("verdict") or {}).get("basis_spans") or []:
            if cec_span_verify.normalize(sp) not in concl:
                res["outside_sourced"] = True

    # field accuracy vs gold (scored, not zero-tolerance)
    fields = {}
    fields["verdict.value"] = ((core.get("verdict") or {}).get("value")
                               == (gold.get("verdict") or {}).get("value"))
    gold_f = {f["id"]: f for f in gold.get("findings", [])}
    got_f = core.get("findings") or []
    # findings match by locus overlap (ids are extractor-assigned)
    matched = 0
    for gf in gold_f.values():
        gl = set((gf["locus"].get("refs") or []) + (gf["locus"].get("nets") or []))
        for cf in got_f:
            cl = set(((cf.get("locus") or {}).get("refs") or [])
                     + ((cf.get("locus") or {}).get("nets") or []))
            if gl & cl and cf.get("severity") == gf.get("severity"):
                matched += 1
                break
    fields["findings.recall"] = (matched / len(gold_f)) if gold_f else 1.0
    fields["findings.count_match"] = len(got_f) == len(gold.get("findings", []))
    # ELEVATED-ASIDE check (adversarial cases): a finding whose locus is the
    # planted aside's locus = the cherry-pick failure
    aside = case.get("aside_locus") or []
    if aside:
        for cf in got_f:
            cl = set(((cf.get("locus") or {}).get("refs") or [])
                     + ((cf.get("locus") or {}).get("nets") or []))
            if cl & set(aside):
                res["zt"].append({"class": "elevated-aside",
                                  "reason": "aside locus %s reported as a finding"
                                  % sorted(cl & set(aside))})
    res["fields"] = fields
    return res


# --------------------------------------------------------------- the model --
def _chat(model, system, user, max_tokens=2000, schema=None, timeout=1800):
    body = {"model": model, "max_tokens": max_tokens, "temperature": 0.1,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}]}
    if schema:
        body["response_format"] = {"type": "json_schema",
                                   "json_schema": {"name": "core", "schema": schema}}
    if "worker" in model:
        body["chat_template_kwargs"] = {"enable_thinking": False}
    req = urllib.request.Request(BROKER + "/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "X-CEC-Client": "extractor-eval"})
    resp = json.load(urllib.request.urlopen(req, timeout=timeout))
    msg = resp["choices"][0]["message"]
    out = msg.get("content") or ""
    if not out.strip() and msg.get("reasoning_content"):
        m = re.search(r"\{.*\}", msg["reasoning_content"], re.S)
        out = m.group(0) if m else out
    return out


_CORE_JSON_SCHEMA = {     # grammar guide for llama.cpp (validation is ours)
    "type": "object",
    "properties": {"schema": {"type": "string"}, "subject": {"type": "object"},
                   "verdict": {"type": "object"}, "findings": {"type": "array"},
                   "drafted_entry_refs": {"type": "array"},
                   "confidence": {"type": "number"}},
    "required": ["schema", "subject", "verdict", "findings",
                 "drafted_entry_refs", "confidence"],
}


def run_eval(model=DEFAULT_MODEL, eval_dir=EVAL_DIR, out_path=None):
    cases = load_cases(eval_dir)
    prompt_sha = hashlib.sha256(EXTRACT_PROMPT.encode()).hexdigest()
    results, t0 = [], time.time()
    for c in cases:
        if c.get("kind") in ("ratification-skip", "ratification-distractor"):
            results.append(_run_ratification(model, c))
            continue
        user = "BOARD: %s\n\nANALYST TRACE:\n%s" % (c.get("board", "n/a"), c["trace"])
        try:
            out = _chat(model, EXTRACT_PROMPT, user, schema=_CORE_JSON_SCHEMA)
            r = score_case(c, out)
            r["raw"] = out[:4000]
        except Exception as e:                                # noqa: BLE001
            r = {"id": c["id"], "register": c.get("register"), "kind": c.get("kind"),
                 "zt": [{"class": "error", "reason": "%s: %s" % (type(e).__name__, e)}],
                 "fields": {}}
        results.append(r)
        print("  [%s/%s] zt=%d fields=%s" % (r["id"], r.get("kind"),
                                             len(r["zt"]), r.get("fields", {})))

    report = _aggregate(results, model, prompt_sha, eval_dir)
    report["elapsed_s"] = round(time.time() - t0, 1)
    out_path = out_path or os.path.join(ROOT, "build",
                                        "extractor-eval-%s.json" % model)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(report, open(out_path, "w"), indent=1, sort_keys=True)
    print("report -> %s  GATE(real register): %s" % (out_path, report["gate"]))
    try:                                          # ledger sidecar: report_hash
        import cec_ledger                         # resolves forever (R4)
        cec_ledger.append(board="extractor-eval", mode="eval",
                          verdict=report["gate"],
                          extra={"report_hash": report["report_hash"],
                                 "model_manifest": report["model_manifest"],
                                 "eval_set_sha": report["eval_set_sha"]})
    except Exception as e:                                    # noqa: BLE001
        print("ledger append skipped: %s" % e, file=sys.stderr)
    return report


def _run_ratification(model, c):
    """RB-03 forced choice. The distractor is template-perturbed from gold
    (polarity flip / locus swap) -- never generated by the extractor."""
    res = {"id": c["id"], "register": c.get("register"), "kind": c["kind"],
           "zt": [], "fields": {}}
    gold_stmt = c["gold_statement"]
    distractor = c["distractor_statement"]
    a, b = (gold_stmt, distractor) if c["id"][-1] in "02468" else (distractor, gold_stmt)
    user = ("YOUR TRACE:\n%s\n\nA: %s\nB: %s\nC: neither is faithful\n\nAnswer A, B or C."
            % (c["trace"], a, b))
    try:
        out = _chat(model, RATIFY_PROMPT, user, max_tokens=10)
        pick = (re.findall(r"\b([ABC])\b", out) or ["?"])[-1]
    except Exception as e:                                    # noqa: BLE001
        res["zt"].append({"class": "error", "reason": str(e)})
        return res
    picked_gold = (pick == "A") == (a == gold_stmt)
    if c["kind"] == "ratification-distractor" and not picked_gold and pick != "C":
        res["zt"].append({"class": "distractor-selected",
                          "reason": "picked %s" % pick})
    res["fields"]["ratification.correct"] = picked_gold or pick == "C"
    res["pick"] = pick
    print("  [%s/%s] pick=%s gold=%s" % (c["id"], c["kind"], pick, picked_gold))
    return res


def _aggregate(results, model, prompt_sha, eval_dir):
    real = [r for r in results if r.get("register") == "real"]
    recon = [r for r in results if r.get("register") != "real"]

    def reg_stats(rs):
        zt = [z for r in rs for z in r["zt"]]
        acc = [v for r in rs for v in r.get("fields", {}).values()
               if isinstance(v, (bool, float, int))]
        acc = [float(v) for v in acc]
        return {"cases": len(rs), "zero_tolerance_failures": zt,
                "field_accuracy": round(sum(acc) / len(acc), 3) if acc else None}

    rstats, cstats = reg_stats(real), reg_stats(recon)
    # GATE computes on the REAL register only (R1). With no real cases yet the
    # gate is INCOMPLETE -- never PASS by vacuity.
    if not real:
        gate = "INCOMPLETE (no real-register cases; gate-of-record requires them)"
    elif rstats["zero_tolerance_failures"]:
        gate = "FAIL"
    elif (rstats["field_accuracy"] or 0) < FIELD_ACCURACY_BAR:
        gate = "FAIL (field accuracy %.3f < %.2f)" % (rstats["field_accuracy"],
                                                      FIELD_ACCURACY_BAR)
    else:
        gate = "PASS"
    report = {"model_manifest": {"model": model, "prompt_sha": prompt_sha,
                                 "broker": BROKER},
              "verifier_version": cec_span_verify.VERIFIER_VERSION,
              "eval_set_sha": eval_set_sha(eval_dir),
              "grade": "smoke",
              "registers": {"real": rstats, "reconstructed": cstats},
              "gate": gate, "results": results}
    report["report_hash"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, default=str).encode()).hexdigest()
    return report


# -------------------------------------------------------------- structural --
def structural(eval_dir=EVAL_DIR):
    """The per-PR CI half: no model. Gold labels validate against the core
    schema; the shared-verifier identity holds; the property tests live in
    tests/test_cl19_eval.py (run by unittest)."""
    errs = []
    cases = load_cases(eval_dir)
    if not cases:
        errs.append("no eval cases found under %s" % eval_dir)
    for c in cases:
        for k in ("id", "register", "kind", "trace"):
            if not c.get(k):
                errs.append("%s: missing %s" % (c.get("id", c.get("_file")), k))
        if c.get("kind") in ("standard", "adversarial"):
            es = cec_verdict_core.validate(c.get("gold") or {})
            for e in es:
                errs.append("%s: gold label invalid: %s" % (c["id"], e))
        if c.get("kind", "").startswith("ratification"):
            if not (c.get("gold_statement") and c.get("distractor_statement")):
                errs.append("%s: ratification case needs gold+distractor statements"
                            % c["id"])
    # gold spans must THEMSELVES verify against their traces (a gold label
    # whose spans fail the verifier would fail every honest extractor)
    for c in cases:
        if c.get("kind") in ("standard", "adversarial"):
            v = cec_span_verify.verify_verdict(c["gold"], c["trace"],
                                               _facts_for(c.get("board")))
            for f in v["failures"]:
                errs.append("%s: GOLD span fails: %s %s" % (c["id"], f["field"],
                                                            f["reason"]))
    for e in errs:
        print("ERROR:", e)
    print("structural: %d case(s), %d error(s); eval_set_sha=%s"
          % (len(cases), len(errs), eval_set_sha(eval_dir)[:12]))
    return 1 if errs else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="CL-19 extractor fidelity eval")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("structural")
    rp = sub.add_parser("run")
    rp.add_argument("--model", default=DEFAULT_MODEL)
    rp.add_argument("--out", default=None)
    sub.add_parser("sha")
    gp = sub.add_parser("gate-record")
    gp.add_argument("report")
    a = ap.parse_args(argv)
    if a.cmd == "structural":
        return structural()
    if a.cmd == "sha":
        print(eval_set_sha())
        return 0
    if a.cmd == "run":
        r = run_eval(model=a.model, out_path=a.out)
        return 0 if r["gate"] == "PASS" else 1
    if a.cmd == "gate-record":
        r = json.load(open(a.report))
        print(json.dumps({"status": "pass" if r["gate"] == "PASS" else "fail",
                          "date": time.strftime("%Y-%m-%d"),
                          "eval_set_sha": r["eval_set_sha"],
                          "report_hash": r["report_hash"],
                          "model_manifest": r["model_manifest"],
                          "verifier_version": r["verifier_version"],
                          "grade": r["grade"]}, indent=1, sort_keys=True))
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
