#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# cec_v4_task -- hand a task to the DeepSeek-V4-Flash SEAT (owner 2026-06-13: treat V4 as a tier ABOVE a
# Sonnet sub-agent -- deep local reasoning, slow ~7 tok/s). Synchronous dispatch through the broker (:8080
# -> Windows-native :8007). Use it as a panel seat (deep reviewer / auditor / analyst) or via the idle
# queue (cec_v4_queue). V4's deep-reasoner signature is an EMPTY content with the answer stranded in
# reasoning_content -- recovered here to the reasoning tail.

import argparse
import json
import os
import sys
import time
import urllib.request

BROKER = os.environ.get("CEC_LLM_BROKER_URL", "http://localhost:8080/v1").rstrip("/")
MODEL = os.environ.get("CEC_V4_MODEL", "deepseek-v4-flash")


def v4_up(timeout=6):
    """True iff the broker catalog lists the V4 seat (it is a managed:false external backend)."""
    try:
        d = json.load(urllib.request.urlopen(BROKER + "/models", timeout=timeout))
        return any(m.get("id") == MODEL for m in d.get("data", []))
    except Exception:                                          # noqa: BLE001
        return False


def run_task(prompt, *, system=None, schema=None, max_tokens=6000, timeout=1800, temperature=0.2):
    """Synchronous V4 call. With `schema` (a JSON Schema) the output is grammar-constrained JSON. Returns
    {content, reasoning, usage, elapsed_s} -- content falls back to the reasoning tail if V4 stranded the
    answer in reasoning_content."""
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    body = {"model": MODEL, "messages": msgs, "max_tokens": max_tokens, "temperature": temperature}
    if schema:
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": "out", "schema": schema}}
    req = urllib.request.Request(BROKER + "/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json", "X-CEC-Client": "v4-task"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    msg = (d.get("choices") or [{}])[0].get("message", {}) or {}
    content = (msg.get("content") or "").strip()
    reasoning = (msg.get("reasoning_content") or "").strip()
    if not content and reasoning:                            # deep reasoner stranded the answer -> tail
        content = reasoning[-4000:]
    return {"content": content, "reasoning": reasoning, "usage": d.get("usage"),
            "elapsed_s": round(time.time() - t0, 1)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Hand a task to the DeepSeek-V4-Flash seat (deep local reasoner).")
    ap.add_argument("--prompt")
    ap.add_argument("--prompt-file")
    ap.add_argument("--system", default=None)
    ap.add_argument("--system-file", default=None)
    ap.add_argument("--schema-file", default=None, help="JSON-schema file -> grammar-constrained output")
    ap.add_argument("--out", default=None, help="write the result JSON here (else stdout)")
    ap.add_argument("--max-tokens", type=int, default=6000)
    ap.add_argument("--timeout", type=int, default=1800)
    a = ap.parse_args(argv)
    prompt = a.prompt or (open(a.prompt_file).read() if a.prompt_file else None)
    if not prompt:
        ap.error("need --prompt or --prompt-file")
    system = a.system or (open(a.system_file).read() if a.system_file else None)
    schema = json.load(open(a.schema_file)) if a.schema_file else None
    if not v4_up():
        out = {"error": f"{MODEL} not up in the broker at {BROKER}"}
    else:
        try:
            out = run_task(prompt, system=system, schema=schema, max_tokens=a.max_tokens, timeout=a.timeout)
        except Exception as e:                               # noqa: BLE001
            out = {"error": f"{type(e).__name__}: {e}"}
    s = json.dumps(out, indent=1)
    if a.out:
        open(a.out, "w").write(s)
        print(f"[cec_v4_task] -> {a.out} ({out.get('elapsed_s', out.get('error'))})")
    else:
        print(s)
    return 0 if not out.get("error") else 1


if __name__ == "__main__":
    sys.exit(main())
