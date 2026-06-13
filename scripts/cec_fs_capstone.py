#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# cec_fs_capstone -- END-OF-RUN CAPSTONE audit of a completed cec_fullstack run, performed by the
# T5 deep auditor (DeepSeek-V4-Flash by default), corpus-briefed exactly like the in-loop seat.
#
# The in-loop `audit()` judges ONE round. The capstone judges the WHOLE run: did it converge, why
# not, is the morning bundle's conclusion sound, what is the single highest-leverage change, and is
# there any safety / locked-decision / spec concern in the final board. It assembles a FACTUAL
# dossier from the run's own artifacts (bundle.json + measurement.jsonl trajectory + the auditor's
# per-round findings) -- no interpretation is injected, so V4's verdict is its own.
#
# Usage:
#   python3 scripts/cec_fs_capstone.py --run-dir docs/fullstack-run-2026-06-13 [--board eps-8pin]
#       [--model deepseek-v4-flash] [--ts-before 10:05:00] [--timeout 1800] [--max-tokens 6000]
#
# Output: <run-dir>/CAPSTONE-v4.json (+ .md). Reasoning streamed to <run-dir>/streams/capstone.jsonl
# when CEC_STREAM_DIR is set (this script sets it to <run-dir>/streams).

import argparse
import glob
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_fullstack as fs          # noqa: E402  (promoted_corpus_brief, DEEP_AUDITOR)
import cec_judge_local as jl        # noqa: E402  (_chat_json: broker path + grammar + scribe recovery)


CAPSTONE_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_verdict": {"type": "string",
                            "enum": ["converged", "local_minimum", "no_progress", "regressed"]},
        "bundle_accurate": {"type": "boolean"},
        "bundle_assessment": {"type": "string"},
        "root_cause": {"type": "string"},
        "trajectory_reading": {"type": "string"},
        "highest_leverage_change": {
            "type": "object",
            "properties": {
                "change": {"type": "string"},
                "lever_class": {"type": "string",
                                "enum": ["routing", "placement", "constraint", "scoring",
                                         "design_escalation", "none"]},
                "rationale": {"type": "string"},
                "expected_effect": {"type": "string"},
            },
            "required": ["change", "lever_class", "rationale"],
        },
        "safety_or_spec_concern": {"type": "string"},
        "corpus_citations": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["overall_verdict", "bundle_accurate", "root_cause",
                 "highest_leverage_change", "confidence"],
}


def _load_json(path, default=None):
    try:
        return json.load(open(path))
    except Exception:                                            # noqa: BLE001
        return default


def _first_run_rows(run_dir, ts_before):
    """Per-round measurement rows from the COMPLETED first run only (ts lexicographically < ts_before;
    the watchdog relaunch appended later rows with ts >= ~10:10 to the same file)."""
    rows = []
    mp = os.path.join(run_dir, "measurement.jsonl")
    if not os.path.exists(mp):
        return rows
    for ln in open(mp):
        ln = ln.strip()
        if not ln:
            continue
        try:
            d = json.loads(ln)
        except Exception:                                        # noqa: BLE001
            continue
        if ts_before and str(d.get("ts", "")) >= ts_before:
            continue
        rows.append(d)
    return rows


def _trajectory_table(rows):
    keys = ["round", "ts", "drc", "unconnected", "plane_signal_mm", "max_T",
            "kelvin_ok", "gates_pass", "panel", "pour_clipped", "objective", "v4_risk"]
    lines = ["round | drc | unconn | plane_mm | max_T | kelvin | gates | panel | clipped | obj"]
    for d in rows:
        lines.append(" | ".join(str(d.get(k)) for k in
                     ("round", "drc", "unconnected", "plane_signal_mm", "max_T",
                      "kelvin_ok", "gates_pass", "panel", "pour_clipped", "objective")))
    return "\n".join(lines)


def _findings_digest(run_dir, max_n=14):
    """The in-loop auditor's per-round root_cause/verdict/failure_class (what T5 concluded each round)."""
    out = []
    for fp in sorted(glob.glob(os.path.join(run_dir, "findings", "round-*-sonnet.json"))):
        d = _load_json(fp)
        if not isinstance(d, dict):
            continue
        rnd = os.path.basename(fp).split("-")[1]
        out.append({"round": rnd, "verdict": d.get("verdict"),
                    "failure_class": d.get("failure_class"),
                    "root_cause": (d.get("root_cause") or "")[:220],
                    "manager_rule": d.get("manager_rule")})
    # keep the head + tail so the model sees the run's arc without flooding the prompt
    if len(out) > max_n:
        out = out[:max_n // 2] + [{"...": f"{len(out) - max_n} rounds elided"}] + out[-max_n // 2:]
    return out


def build_dossier(run_dir, board, ts_before):
    bundle = _load_json(os.path.join(run_dir, "bundle.json"), {}) or {}
    rows = _first_run_rows(run_dir, ts_before)
    # final-board metrics = the last first-run row
    final = rows[-1] if rows else {}
    drc_series = [r.get("drc") for r in rows if isinstance(r.get("drc"), (int, float))]
    best_drc = min(drc_series) if drc_series else None
    parts = []
    parts.append(f"COMPLETED RUN: board={board}, {bundle.get('rounds')} rounds, "
                 f"{bundle.get('records')} records, gate_passing={bundle.get('gate_passing')}, "
                 f"pareto_finalists={bundle.get('pareto_finalists')}.")
    parts.append("MORNING BUNDLE (the run's own end-of-run summary -- assess whether its conclusion "
                 "is correct):\n" + json.dumps({k: bundle.get(k) for k in
                 ("gate_passing", "pareto_finalists", "pour_clip_summary", "pour_clipped_rounds",
                  "final_penalties", "n_rules", "rules", "rejections", "verifier", "front")},
                 indent=1)[:2600])
    parts.append("RULE/PENALTY INJECTIONS over the run (source=v4 are the deep auditor's accepted "
                 "rules):\n" + json.dumps(bundle.get("injections", []), indent=1)[:1400])
    parts.append(f"PER-ROUND TRAJECTORY (first run, {len(rows)} rounds; best drc seen = {best_drc}):\n"
                 + _trajectory_table(rows))
    parts.append("FINAL-BOARD METRICS (last round of the completed run):\n"
                 + json.dumps({k: final.get(k) for k in
                   ("round", "drc", "unconnected", "plane_signal_mm", "max_T", "kelvin_ok",
                    "gates_pass", "pour_clipped", "pour_clipped_nets", "objective")}, indent=1))
    parts.append("IN-LOOP AUDITOR FINDINGS (per-round root_cause/verdict the T5 seat produced):\n"
                 + json.dumps(_findings_digest(run_dir), indent=1)[:2600])
    return "\n\n".join(parts), bundle, rows


CAPSTONE_TEMPLATE = (
    '{"overall_verdict":"converged|local_minimum|no_progress|regressed",'
    '"bundle_accurate":true,"bundle_assessment":"...",'
    '"root_cause":"<why no gate-passing board, mechanistic>",'
    '"trajectory_reading":"<what the per-round series shows>",'
    '"highest_leverage_change":{"change":"...","lever_class":"routing|placement|constraint|'
    'scoring|design_escalation|none","rationale":"...","expected_effect":"..."},'
    '"safety_or_spec_concern":"<any locked-decision/Kelvin/shunt/DETECT/corpus concern in the '
    'final board, or \'none\'>","corpus_citations":["<id>",...],"confidence":"high|medium|low"}')


def run_capstone(run_dir, board, model, ts_before, timeout, max_tokens):
    os.environ.setdefault("CEC_STREAM_DIR", os.path.join(run_dir, "streams"))
    os.makedirs(os.environ["CEC_STREAM_DIR"], exist_ok=True)
    dossier, bundle, rows = build_dossier(run_dir, board, ts_before)
    brief = fs.promoted_corpus_brief(board)
    system = (
        "You are the T5 DEEP AUDITOR for the CEC routing pipeline, giving the END-OF-RUN CAPSTONE "
        "verdict on a COMPLETED full-stack run (not a single round). You judge the run as a whole. "
        "Be mechanistic and specific; cite ratified corpus entries by id where they bear. The loop's "
        "ALLOWED LEVERS are router passes/opt_time, FR-02 waypoint intents (incl. routing an "
        "offending net out of a corridor), placement candidate regeneration, and scorer penalties "
        "(ranking only). A fix that needs a constraint/stackup/footprint/locked-decision change is a "
        "DESIGN ESCALATION to the human, not a loop lever -- say so if that is the real fix. A scorer "
        "reweight only reorders existing candidates; it cannot create a gate-passing board. Emit ONLY "
        "the JSON object the schema defines.")
    user = (brief + "END-OF-RUN CAPSTONE -- assess this completed run:\n\n" + dossier
            + "\n\nReturn ONLY this JSON:\n" + CAPSTONE_TEMPLATE)
    t0 = time.time()
    print(f"[capstone] model={model} board={board} rounds={len(rows)} "
          f"prompt~{len(user)//4} tok timeout={timeout}s -- calling V4 (slow) ...", flush=True)
    try:
        out = jl._chat_json(system, user, CAPSTONE_SCHEMA, name="capstone", temperature=0.0,
                            max_tokens=max_tokens, timeout=timeout, model=model, seat="capstone")
    except Exception as e:                                        # noqa: BLE001
        out = {"error": f"{type(e).__name__}: {e}"}
    dt = time.time() - t0
    if not isinstance(out, dict) or "overall_verdict" not in out:
        out = out if isinstance(out, dict) else {}
        out.setdefault("error", "no verdict returned (see streams/capstone.jsonl)")
    out["_meta"] = {"model": model, "board": board, "rounds": len(rows),
                    "elapsed_s": round(dt, 1), "bundle_gate_passing": bundle.get("gate_passing"),
                    "generated": time.strftime("%Y-%m-%dT%H:%M:%S")}
    json.dump(out, open(os.path.join(run_dir, "CAPSTONE-v4.json"), "w"), indent=1)
    _render_md(run_dir, out)
    print(f"[capstone] done in {dt:.0f}s -> {run_dir}/CAPSTONE-v4.json", flush=True)
    return out


def _render_md(run_dir, out):
    m = out.get("_meta", {})
    hl = out.get("highest_leverage_change", {}) or {}
    md = [f"# Capstone audit -- {m.get('board')} run ({m.get('rounds')} rounds)",
          f"_DeepSeek-V4-Flash, {m.get('elapsed_s')}s, generated {m.get('generated')}_", ""]
    if out.get("error"):
        md += [f"**ERROR:** {out['error']}", ""]
    md += [f"- **Overall verdict:** `{out.get('overall_verdict')}`  (confidence: {out.get('confidence')})",
           f"- **Morning bundle accurate?** {out.get('bundle_accurate')} -- {out.get('bundle_assessment','')}",
           "",
           "## Root cause", out.get("root_cause", ""), "",
           "## Trajectory reading", out.get("trajectory_reading", ""), "",
           "## Highest-leverage change for the next run",
           f"**{hl.get('change','')}**  _(lever class: {hl.get('lever_class','')})_", "",
           f"- Rationale: {hl.get('rationale','')}",
           f"- Expected effect: {hl.get('expected_effect','')}", "",
           "## Safety / spec concern", out.get("safety_or_spec_concern", "none"), "",
           "## Corpus citations", ", ".join(out.get("corpus_citations", []) or ["(none)"]), ""]
    open(os.path.join(run_dir, "CAPSTONE-v4.md"), "w").write("\n".join(md))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default="docs/fullstack-run-2026-06-13")
    ap.add_argument("--board", default=None)
    ap.add_argument("--model", default=fs.DEEP_AUDITOR)
    ap.add_argument("--ts-before", default="10:05:00",
                    help="exclude measurement rows at/after this HH:MM:SS (the watchdog relaunch)")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--max-tokens", type=int, default=6000)
    a = ap.parse_args(argv)
    run_dir = a.run_dir if os.path.isabs(a.run_dir) else os.path.join(ROOT, a.run_dir)
    board = a.board or (_load_json(os.path.join(run_dir, "bundle.json"), {}) or {}).get("board") \
        or "eps-8pin"
    out = run_capstone(run_dir, board, a.model, a.ts_before, a.timeout, a.max_tokens)
    print(json.dumps({k: out.get(k) for k in ("overall_verdict", "bundle_accurate",
          "confidence", "error")}, indent=1))


if __name__ == "__main__":
    main()
