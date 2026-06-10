#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_bench_manager -- manager-tier VERDICT benchmark (single-call, raw).
# ============================================================================
# Benches a candidate manager/reviewer model on the pipeline's REAL judgment task: the three
# differentiated manager contexts whose correct call differs (accept / repair / escalate), using the
# production SYSTEM prompt + VERDICT_SCHEMA from cec_judge_local. It measures the model's RAW
# single-call behaviour ON PURPOSE -- it posts directly, NOT through cec_judge_local._chat_json --
# so a thinking overrun (empty content, answer stranded in reasoning_content) shows up as the
# diagnostic finding it is, rather than being papered over by the production miner->scribe recovery.
#
#   python3 scripts/cec_bench_manager.py                          # broker, cec-manager-fast
#   BENCH_MODEL=cec-manager python3 scripts/cec_bench_manager.py  # the M2.7 deep tier
#   BENCH_URL=http://localhost:8005/v1 BENCH_MODEL=... ...        # direct to an upstream
#
# Provenance: promoted 2026-06-10 from the ad-hoc build/bench_manager.py used in the 2026-06-09
# model-lineup bench session. The raw /tmp/cec-bench logs of that session were LOST to a WSL
# restart (only build/bench-gptoss.log survived: gpt-oss-120b 3/3 correct, 495 tok in 33.2s,
# ~11.1 s/verdict); results are recorded in docs/llm-manager-bench-2026-06-09.md.
# ============================================================================
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cec_judge_local as J  # reuse SYSTEM + VERDICT_SCHEMA (module top is pcbnew-free)  # noqa: E402

URL = os.environ.get("BENCH_URL", "http://localhost:8080/v1").rstrip("/")   # broker by default
MODEL = os.environ.get("BENCH_MODEL", "cec-manager-fast")
MAX_TOKENS = int(os.environ.get("BENCH_MAX_TOKENS", "4000"))
TIMEOUT = float(os.environ.get("BENCH_TIMEOUT", "900"))

# The 3 differentiated manager contexts (the correct call differs per context).
CTX = {
    "accept": {"region": "all", "iteration": 1,
               "candidates_best_first": [{"drc": 0, "unconnected": 0, "kelvin_ok": True,
                                          "diffpair_ok": True, "gates_pass": True}],
               "best_candidate_gate_failures": []},
    "repair": {"region": "all", "iteration": 2,
               "candidates_best_first": [{"drc": 12, "unconnected": 14, "kelvin_ok": False,
                                          "diffpair_ok": True, "gates_pass": False}],
               "best_candidate_gate_failures": ["sense pair SENSEC1 not routed (14 ratlines)"]},
    "escalate": {"region": "all", "iteration": 4, "prior_iterations": 3,
                 "candidates_best_first": [{"drc": 40, "unconnected": 8, "kelvin_ok": True,
                                            "diffpair_ok": True, "gates_pass": False}],
                 "best_candidate_gate_failures": [
                     "clearance +3V3 track to /USB_DP via <0.1mm (real cross-net short); "
                     "stalled at drc=40 for 3 iters"]},
}
EXPECT = {"accept": "accept", "repair": "repair", "escalate": "escalate"}


def call(user):
    payload = {"model": MODEL,
               "messages": [{"role": "system", "content": J.SYSTEM},
                            {"role": "user", "content": user}],
               "temperature": 0, "max_tokens": MAX_TOKENS,
               "response_format": {"type": "json_schema",
                                   "json_schema": {"name": "verdict", "schema": J.VERDICT_SCHEMA,
                                                   "strict": True}}}
    req = urllib.request.Request(URL + "/chat/completions", json.dumps(payload).encode(),
                                 {"Content-Type": "application/json", "X-CEC-Client": "CEC-Platform"})
    t0 = time.time()
    r = json.load(urllib.request.urlopen(req, timeout=TIMEOUT))
    wall = time.time() - t0
    msg = r["choices"][0]["message"]
    u = r.get("usage", {})
    return wall, u.get("completion_tokens", 0), u.get("prompt_tokens", 0), msg


def main():
    print(f"=== MANAGER BENCHMARK :: {MODEL} @ {URL} ===")
    tot_t = tot_tok = ok = 0
    for name, ctx in CTX.items():
        wall, ct, pt, msg = call(json.dumps(ctx))
        content = (msg.get("content") or "").strip()
        try:
            act = json.loads(content).get("action")
        except Exception:
            # The diagnostic that decided the 2026-06-09 bench: a thinking model burning the whole
            # budget in reasoning_content and returning EMPTY content (the miner->scribe trigger).
            trace = (msg.get("reasoning_content") or "")
            act = (f"(EMPTY content; reasoning_content={len(trace)} chars -- thinking overrun)"
                   if not content and trace else "(parse-fail) " + content[:40])
        good = (act == EXPECT[name])
        ok += good
        tot_t += wall
        tot_tok += ct
        print(f"  {name:9s} expect={EXPECT[name]:9s} got={str(act):10s} {'OK' if good else 'XX'}"
              f" | {ct} tok in {wall:.1f}s = {ct / wall:.1f} tok/s")
    print(f"  -> {ok}/3 correct | aggregate {tot_tok} tok in {tot_t:.1f}s = "
          f"{tot_tok / max(tot_t, 1e-9):.1f} tok/s avg ; {tot_t / 3:.1f}s/verdict")
    return 0 if ok == 3 else 1


if __name__ == "__main__":
    sys.exit(main())
