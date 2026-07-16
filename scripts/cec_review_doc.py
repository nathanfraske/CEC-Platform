#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_review_doc -- assemble a clean, readable REVIEW.md of EVERY model seat's
#  FULL reasoning from a fullstack/in-loop run's captured per-seat streams.
# ============================================================================
# The run records each seat's complete chain-of-thought + answer as delta events
# in <run-dir>/streams/<seat>.jsonl (cec_seat_stream). That is the lossless
# capture, but it is machine-format. This tool reconstructs each seat call into a
# human-readable transcript -- per seat, every call in chronological order, the
# full reasoning then the answer -- so the owner can READ what each model thought
# (the value of the overnight run) without parsing JSONL.
#
# RUN-INDEPENDENT: it only reads captured files, so it is safe to run WHILE the
# run is live (a partial doc) or after it finishes (the complete doc). Re-run any
# time to regenerate from the latest captured data.
#
# Usage:
#   python3 scripts/cec_review_doc.py --run-dir docs/fullstack-run-2026-06-13
#   python3 scripts/cec_review_doc.py --run-dir <dir> --out REVIEW.md [--chronological]
# ============================================================================
import argparse
import glob
import json
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_calls(stream_path):
    """Parse one <seat>.jsonl into a list of calls: {seat, model, role, call, t0, t1,
    reasoning, content}. A call is start -> (reasoning|content deltas) -> end."""
    calls = {}
    order = []
    try:
        with open(stream_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:                                   # noqa: BLE001
                    continue
                cid = e.get("call")
                key = (e.get("seat"), cid)
                if key not in calls:
                    calls[key] = {"seat": e.get("seat"), "model": e.get("model"),
                                  "role": e.get("role"), "call": cid, "t0": e.get("ts"),
                                  "t1": e.get("ts"), "reasoning": [], "content": [],
                                  "ok": None, "error": None}
                    order.append(key)
                c = calls[key]
                k = e.get("kind")
                if k == "start":
                    c["model"] = e.get("model") or c["model"]
                    c["role"] = e.get("role") or c["role"]
                    c["t0"] = e.get("ts") or c["t0"]
                elif k == "delta":
                    (c["reasoning"] if e.get("ch") == "reasoning" else c["content"]).append(e.get("d") or "")
                    c["t1"] = e.get("ts") or c["t1"]
                elif k == "end":
                    c["ok"] = e.get("ok")
                    c["error"] = e.get("error")
                    c["t1"] = e.get("ts") or c["t1"]
    except OSError:
        return []
    out = []
    for key in order:
        c = calls[key]
        c["reasoning"] = "".join(c["reasoning"])
        c["content"] = "".join(c["content"])
        out.append(c)
    return out


def _fmt_ts(ts):
    try:
        return time.strftime("%H:%M:%S", time.localtime(float(ts)))
    except Exception:                                               # noqa: BLE001
        return "?"


def _call_md(c):
    dur = ""
    try:
        dur = f" ({float(c['t1']) - float(c['t0']):.0f}s)"
    except Exception:                                               # noqa: BLE001
        pass
    head = (f"### {_fmt_ts(c['t0'])}{dur} — call {c['call']} — role `{c.get('role') or '?'}`"
            + (f" — model `{c.get('model')}`" if c.get('model') else "")
            + ("" if c.get("ok") in (None, True) else f" — **ERROR: {c.get('error')}**"))
    parts = [head, ""]
    rea, con = c.get("reasoning", ""), c.get("content", "")
    if rea:
        parts += ["<details><summary>reasoning (" + str(len(rea)) + " chars)</summary>", "",
                  "```", rea.strip(), "```", "", "</details>", ""]
    if con:
        parts += ["**answer:**", "", "```", con.strip(), "```", ""]
    if not rea and not con:
        parts += ["_(no captured text)_", ""]
    return "\n".join(parts)


def build(run_dir, out_name="REVIEW.md", chronological=False):
    run_dir = os.path.abspath(run_dir)
    sdir = os.path.join(run_dir, "streams")
    streams = sorted(glob.glob(os.path.join(sdir, "*.jsonl")))
    all_calls = []
    per_seat = {}
    for sp in streams:
        seat = os.path.basename(sp)[:-6]
        calls = _load_calls(sp)
        per_seat[seat] = calls
        all_calls.extend(calls)
    n_calls = sum(len(v) for v in per_seat.values())

    lines = [f"# Run review — {os.path.basename(run_dir)}",
             "",
             f"_Assembled by scripts/cec_review_doc.py from the per-seat reasoning streams. "
             f"{len(per_seat)} seat(s), {n_calls} model call(s). Re-run to refresh; safe while the run is live._",
             ""]
    # quick metric series if present
    mpath = os.path.join(run_dir, "measurement.jsonl")
    if os.path.exists(mpath):
        try:
            rows = [json.loads(l) for l in open(mpath) if l.strip()]
            lines += [f"_measurement.jsonl: {len(rows)} round row(s) recorded._", ""]
        except Exception:                                           # noqa: BLE001
            pass
    lines += ["## Seats", "", "| seat | calls | reasoning chars | content chars |",
              "|---|---|---|---|"]
    for seat, calls in sorted(per_seat.items()):
        rc = sum(len(c["reasoning"]) for c in calls)
        cc = sum(len(c["content"]) for c in calls)
        lines.append(f"| `{seat}` | {len(calls)} | {rc:,} | {cc:,} |")
    lines.append("")

    if chronological:
        lines += ["## Transcript (chronological, all seats)", ""]
        for c in sorted(all_calls, key=lambda c: (c.get("t0") or 0)):
            lines.append(f"#### seat `{c.get('seat')}`")
            lines.append(_call_md(c))
    else:
        for seat, calls in sorted(per_seat.items()):
            lines += [f"## Seat: `{seat}`  ({len(calls)} call(s))", ""]
            for c in calls:
                lines.append(_call_md(c))

    out_path = os.path.join(run_dir, out_name)
    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return out_path, len(per_seat), n_calls


def main():
    ap = argparse.ArgumentParser(description="assemble a readable REVIEW.md from a run's per-seat reasoning streams")
    ap.add_argument("--run-dir", default=os.path.join(ROOT, "docs", "fullstack-run-2026-06-13"))
    ap.add_argument("--out", default="REVIEW.md")
    ap.add_argument("--chronological", action="store_true",
                    help="interleave all seats in time order instead of grouping per seat")
    a = ap.parse_args()
    out_path, nseats, ncalls = build(a.run_dir, a.out, a.chronological)
    print(f"wrote {out_path}: {nseats} seat(s), {ncalls} call(s)")


if __name__ == "__main__":
    main()
