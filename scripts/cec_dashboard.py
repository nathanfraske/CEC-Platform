#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_dashboard -- live run dashboard for the in-loop audit / overnight runs.
# ============================================================================
# Owner ask (2026-06-11): "a live metrics dashboard that shows the latest board,
# streaming thoughts from the entire pass, each step happening realtime."
# Realizes the standing live-viewer TODO in cec_reasoning_bakeoff.py: plain
# stdlib http.server + client polling, strictly READ-ONLY (plus one sanctioned
# side effect: rendering the newest candidate board to PNG, in-container).
#
# Panels:
#   * status header   -- run alive/PID/elapsed, round count, deadline
#   * step feed       -- run.log tail (route/audit/inject lines), realtime
#   * latest board    -- newest *.kicad_pcb in the run output, auto-rendered
#                        via the routing container's kicad-cli (bg thread)
#   * thoughts stream -- the newest auditor stream-json (claude -p
#                        --output-format=stream-json tee; text deltas parsed
#                        server-side) with fallback to the newest finding's
#                        full `reasoning` field; V4 checkpoint reasoning too
#   * convergence     -- measurement.jsonl series (pen_total vs physical
#                        metrics sparkline + last rows)
#   * injected rules  -- live-rules.json penalties + newest manager rules
#
# Usage:
#   python3 scripts/cec_dashboard.py [--port 8090] [--run-dir docs/inloop-audit-2026-06-11]
#   then open http://localhost:8090
# ============================================================================
import argparse
import glob
import json
import os
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPOSE = ["docker", "compose", "-f", os.path.join(ROOT, "docker", "compose.yaml")]

CFG = {
    "run_dir": os.path.join(ROOT, "docs", "inloop-audit-2026-06-11"),
    "board_glob": os.path.join(ROOT, "build", "overnight-directed", "*.kicad_pcb"),
    "proc_pattern": "cec_inloop_audit.py|cec_overnight_directed.py|cec_place_planner.py",
    "plot_layers": "F.Cu,B.Cu,In1.Cu,In2.Cu,Edge.Cuts",
    "auto": True,           # auto-discover the live run (off when --run-dir is given explicitly)
    "kind": None,           # which run kind is being tracked (set by discovery)
    "max_boards": 8,        # cap rendered candidates (a long run has 100s) -> newest N; small so the
                            # per-board electro-thermal solve (now full max-realism physics) stays snappy
}

# Known CEC run kinds, newest-PID-first preference. Each: (kind, process regex, --flag whose value is the
# run/out dir [None -> a fixed dir]). The dashboard auto-points run_dir + board_glob at whichever is live,
# so it tracks the place-planner / overnight / audit run with no manual --run-dir.
RUN_KINDS = [
    # (kind, re.search pattern [discovery], pgrep pattern [_proc_info, no \b], --dir flag, default dir)
    ("place-planner",      r"cec_place_planner\.py .*--run", "cec_place_planner.py.*--run", "--out-dir",
     os.path.join(ROOT, "build", "place-planner")),
    ("overnight-directed", r"cec_overnight_directed\.py",   "cec_overnight_directed.py",   "--out-dir",
     os.path.join(ROOT, "build", "overnight-directed")),
    ("inloop-audit",       r"cec_inloop_audit\.py",         "cec_inloop_audit.py",         None,
     os.path.join(ROOT, "docs", "inloop-audit-2026-06-11")),
]


def _flag_val(cmd, flag):
    """Value of `flag` in a command line (supports '--flag v' and '--flag=v')."""
    toks = cmd.split()
    for i, t in enumerate(toks):
        if t == flag and i + 1 < len(toks):
            return toks[i + 1]
        if t.startswith(flag + "="):
            return t.split("=", 1)[1]
    return None


def _discover_run():
    """Find a LIVE CEC run and derive its run_dir + board_glob so the dashboard auto-tracks it. The run's
    boards land in its --out-dir; cec_place_planner also writes run.log + measurement.jsonl there. Returns
    a dict to merge into CFG, or None when nothing is running (keep the last config so the final board stays
    visible after a run ends)."""
    try:
        out = subprocess.run(["pgrep", "-af", "cec_place_planner.py|cec_overnight_directed.py|cec_inloop_audit.py"],
                             capture_output=True, text=True, timeout=5).stdout
    except Exception:                                            # noqa: BLE001
        return None
    for ln in out.splitlines():
        if "cec_dashboard" in ln or "pgrep" in ln:
            continue
        _pid, _, cmd = ln.partition(" ")
        for kind, rx, pgrep_pat, dirflag, default_dir in RUN_KINDS:
            if re.search(rx, cmd):
                d = _flag_val(cmd, dirflag) if dirflag else None
                run_dir = (d if (d and os.path.isabs(d)) else os.path.join(ROOT, d)) if d else default_dir
                return {"kind": kind, "run_dir": os.path.abspath(run_dir),
                        "board_glob": os.path.join(os.path.abspath(run_dir), "*.kicad_pcb"),
                        "proc_pattern": pgrep_pat}
    # FALLBACK (auto-point at the LATEST, 2026-06-27): no live tracked script -> follow the MOST ACTIVE
    # build/ run-dir, so the dash auto-tracks ANY run (cec_router routes / agent / workflow runs the
    # RUN_KINDS pgrep misses). Follow the dir with the MOST boards touched in the last 90s -- NOT raw
    # newest-mtime: under heavy multi-agent work a single verify agent re-routing a canonical board would
    # otherwise hijack the view from the busy run. Tie-break + idle-fallback by newest board. Race-safe
    # (scratch boards vanish mid-scan). Excludes the dashboard's own render copies.
    def _mt(p):
        try:
            return os.path.getmtime(p)
        except OSError:
            return 0.0
    boards = [p for p in glob.glob(os.path.join(ROOT, "build", "*", "*.kicad_pcb"))
              if "renders" not in p and "-filled" not in p and ".dash-renders" not in p]
    if boards:
        now = time.time()
        recent, newest = {}, {}                              # per-dir: boards touched in last 90s + newest mtime
        for p in boards:
            d, m = os.path.dirname(p), _mt(p)
            if m >= now - 90:
                recent[d] = recent.get(d, 0) + 1
            if m > newest.get(d, 0.0):
                newest[d] = m
        pool = recent or newest
        rd = os.path.abspath(max(pool, key=lambda d: (recent.get(d, 0), newest.get(d, 0.0))))
        return {"kind": "latest", "run_dir": rd, "board_glob": os.path.join(rd, "*.kicad_pcb"),
                "proc_pattern": None}
    return None


def _discover_loop():
    """Re-discover the live run every few seconds so the dashboard FOLLOWS runs: it re-points at a newly
    started run, and when one ends it keeps the last run's dir (so the result stays on screen)."""
    while True:
        try:
            if CFG.get("auto"):
                disc = _discover_run()
                if disc and disc["run_dir"] != CFG.get("run_dir"):
                    CFG.update(disc)
                    with _cands_lock:
                        _cands.clear()                          # drop the old run's renders
                elif disc:
                    CFG["kind"] = disc["kind"]; CFG["proc_pattern"] = disc["proc_pattern"]
        except Exception:                                       # noqa: BLE001
            pass
        time.sleep(5)
NOISE = re.compile(r"duplicate image handler|Debug:|Xvfb|_XSERV|xvfb-entry|wxWidgets")

_render = {"status": "idle", "board": None, "ts": 0}     # newest-render status (header)
_cands = []                                             # ordered candidate renders (the timeline)
_cands_lock = threading.Lock()

# Which candidate the dashboard is DISPLAYING -- the frontend reports its focused stem on every /api/state
# poll (?focus=<stem>); the async fine-thermal worker solves THAT board at fine grid. Stale/absent -> the
# worker falls back to the newest candidate (the view the dashboard follows by default).
_focus = {"stem": None, "ts": 0.0}
_fine = {"status": "idle", "stem": None, "grid": None}  # async fine-thermal worker status (header/debug)


# ---------------------------------------------------------------- helpers
def _runfile(name):
    return os.path.join(CFG["run_dir"], name)


def _proc_info():
    try:
        out = subprocess.run(["pgrep", "-af", CFG["proc_pattern"]],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        for ln in out.splitlines():
            pid, _, cmd = ln.partition(" ")
            if "cec_dashboard" in cmd:
                continue
            et = subprocess.run(["ps", "-p", pid, "-o", "etime="],
                                capture_output=True, text=True, timeout=5).stdout.strip()
            return {"alive": True, "pid": int(pid), "elapsed": et, "cmd": cmd[:120]}
    except Exception:                                              # noqa: BLE001
        pass
    return {"alive": False}


def _log_tail(n=80):
    p = _runfile("run.log")
    if not os.path.exists(p):
        return []
    try:
        with open(p, "rb") as fh:                                 # cheap tail: last ~64KB
            fh.seek(max(0, os.path.getsize(p) - 65536))
            txt = fh.read().decode("utf-8", "replace")
        lines = [L for L in txt.splitlines() if L.strip() and not NOISE.search(L)]
        return lines[-n:]
    except Exception:                                             # noqa: BLE001
        return []


def _measurement(n=400):
    p = _runfile("measurement.jsonl")
    rows = []
    if os.path.exists(p):
        for L in open(p):
            try:
                rows.append(json.loads(L))
            except Exception:                                     # noqa: BLE001
                pass
    return rows[-n:]


def _live_rules():
    p = _runfile("live-rules.json")
    if not os.path.exists(p):
        return {}
    try:
        d = json.load(open(p))
        return {"penalties": d.get("scorer_penalties", {}),
                "n_rules": len(d.get("manager_rules", [])),
                "n_accepted": len(d.get("injections", [])),
                "n_rejected": len(d.get("rejections", [])),
                "last_rules": d.get("manager_rules", [])[-3:]}
    except Exception:                                             # noqa: BLE001
        return {}


def _latest(globpat):
    files = glob.glob(globpat)
    return max(files, key=os.path.getmtime) if files else None


def _latest_finding():
    """Newest auditor finding (sonnet or v4) with its full reasoning."""
    out = {}
    for kind, pat in (("sonnet", "round-*-sonnet.json"), ("v4", "round-*-v4.json")):
        f = _latest(os.path.join(CFG["run_dir"], "findings", pat))
        if not f:
            continue
        try:
            d = json.load(open(f))
        except Exception:                                         # noqa: BLE001
            continue
        out[kind] = {"file": os.path.basename(f),
                     "verdict": d.get("verdict"), "is_new": d.get("is_new_finding"),
                     "reasoning": (d.get("reasoning") or d.get("reasoning_content")
                                   or d.get("content") or "")[:6000],
                     "scorer_penalty": d.get("scorer_penalty") or
                                       (d.get("parsed_findings") or {}).get("scorer_penalty"),
                     "manager_rule": (d.get("manager_rule") or
                                      (d.get("parsed_findings") or {}).get("manager_rule") or "")[:400],
                     "local_minimum_risk": (d.get("parsed_findings") or {}).get("local_minimum_risk"),
                     "mtime": os.path.getmtime(f)}
    return out


def _stream_text(off):
    """Incremental text from the NEWEST auditor stream-json file (claude -p
    --output-format=stream-json tee). Extracts assistant text + tool intents."""
    f = _latest(os.path.join(CFG["run_dir"], "findings", "*.stream.jsonl"))
    if not f:
        return {"file": None, "off": 0, "text": ""}
    size = os.path.getsize(f)
    if off > size:                                                 # new file rotated in
        off = 0
    chunks = []
    with open(f, "rb") as fh:
        fh.seek(off)
        raw = fh.read(262144)
    for line in raw.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:                                         # noqa: BLE001
            continue
        # partial text deltas (stream_event) and complete assistant messages
        e = ev.get("event") or {}
        delta = (e.get("delta") or {})
        if delta.get("type") in ("text_delta", "thinking_delta"):
            chunks.append(delta.get("text") or delta.get("thinking") or "")
        elif ev.get("type") == "assistant":
            for blk in ((ev.get("message") or {}).get("content") or []):
                if blk.get("type") == "text":
                    chunks.append("\n" + blk.get("text", "") + "\n")
                elif blk.get("type") == "tool_use":
                    chunks.append(f"\n[tool: {blk.get('name')}]\n")
    return {"file": os.path.basename(f), "off": off + len(raw), "text": "".join(chunks)}


# ---------------------------------------------------------------- per-seat streams
def _seats():
    """Every seat with recorded thoughts: the local NDJSON streams (cec_seat_stream wrote
    <run-dir>/streams/<seat>.jsonl for each manager / panel-lens / worker / reviewer call) PLUS the
    host-side auditor (the claude -p stream-json). Newest-active first -> the live seat is on top."""
    out = []
    sd = os.path.join(CFG["run_dir"], "streams")
    if os.path.isdir(sd):
        for fn in os.listdir(sd):
            if fn.endswith(".jsonl"):
                key = fn[:-6]
                if not re.match(r"^[A-Za-z0-9_.-]+$", key):  # only recorder-written keys (safe in HTML/URL)
                    continue
                out.append({"key": key, "name": key.replace("__", ":"),
                            "mtime": os.path.getmtime(os.path.join(sd, fn))})
    af = _latest(os.path.join(CFG["run_dir"], "findings", "*.stream.jsonl"))
    if af:
        out.append({"key": "auditor", "name": "auditor (claude -p)", "mtime": os.path.getmtime(af)})
    out.sort(key=lambda s: -s["mtime"])
    return out


def _agentic_from_decision_log():
    """The agent panel for a plain / two-pass cec_router route: read the run's *-decision-log.json (the
    DecisionLog -- per-iteration repair/escalate verdicts + the chosen candidate's drc/unconnected) and
    map it to the agentic-panel shape, so the panel PULLS for routes too, not just Hub agentic runs
    (2026-06-27). The DecisionLog stores candidates/verdict as repr-strings, so literal_eval them."""
    import ast
    dl = _latest(os.path.join(CFG["run_dir"], "*-decision-log.json"))
    if not dl:
        return {}
    try:
        d = json.load(open(dl))
    except Exception:                                             # noqa: BLE001
        return {}

    def _p(s):
        if isinstance(s, dict):
            return s
        try:
            v = ast.literal_eval(s)
            return v if isinstance(v, dict) else {}
        except Exception:                                         # noqa: BLE001
            return {}
    routes = []
    for e in (d.get("entries") or []):
        ch, v = _p(e.get("chosen")), _p(e.get("verdict"))
        routes.append({"rank": e.get("iteration"), "strat": str(v.get("action", "")) or e.get("region", ""),
                       "gates_pass": (v.get("action") == "accept") if v else None,
                       "kelvin_ok": ch.get("kelvin_ok"), "diffpair_ok": ch.get("diffpair_ok"),
                       "conformance_fail": None, "drc": ch.get("drc"), "unconnected": ch.get("unconnected")})
    fin = d.get("final") or {}
    fv = _p(fin.get("verdict"))
    cf = ("gates_pass=%s  %s" % (fv.get("gates_pass"), (fv.get("reasons") or [""])[0]))[:140] if fv else None
    return {"seats": "cec_router DecisionLog (deterministic route)", "policy_ok": None, "ref_intake": None,
            "routes": routes, "corpus_fit": cf, "best_rank": None}


def _agentic():
    """The Hub run's agentic-decisions summary from report.json: the resolved seat backend +
    per-tier model (so a silently-deterministic / degraded run is VISIBLE -- the anti-ossification
    countermeasure), per-candidate gate + conformance verdicts, the advisory corpus-fit, and the
    policy/intake-gate state. Read-only; empty {} when no report yet."""
    rf = _runfile("report.json")
    if not os.path.exists(rf):
        return _agentic_from_decision_log()       # a cec_router route writes a DecisionLog, not report.json
    try:
        r = json.load(open(rf))
    except Exception:                                             # noqa: BLE001
        return {}
    routes = [{"rank": x.get("rank"), "strat": x.get("strat"), "gates_pass": x.get("gates_pass"),
               "kelvin_ok": x.get("kelvin_ok"), "diffpair_ok": x.get("diffpair_ok"),
               "conformance_fail": x.get("conformance_fail"), "drc": x.get("drc"),
               "unconnected": x.get("unconnected")} for x in (r.get("routes") or [])]
    cf = r.get("corpus_fit") or {}
    cf_s = (cf.get("verdict") or cf.get("status") or cf.get("fit")
            or ("error: " + str(cf.get("error"))[:80] if cf.get("error") else None)) if isinstance(cf, dict) else cf
    return {"seats": r.get("seats"), "policy_ok": r.get("policy_ok"),
            "ref_intake": r.get("ref_intake"), "routes": routes, "corpus_fit": cf_s,
            "best_rank": (r.get("best_route") or {}).get("rank")}


def _seat_events(key, off):
    """Incremental events for one seat since byte-offset `off`. The auditor seat reuses the claude -p
    stream parser (returned as one content delta); a local seat returns its NDJSON events (start /
    delta{ch:content|reasoning} / end). Only COMPLETE lines are consumed, so a half-written final line
    is re-read next poll. `key` is filename-safe (no URL-encoding needed)."""
    if key == "auditor":
        st = _stream_text(off)
        evs = [{"kind": "delta", "ch": "content", "call": 0, "d": st["text"]}] if st["text"] else []
        return {"key": "auditor", "off": st["off"], "file": st["file"], "events": evs}
    safe = os.path.basename(key)                                  # traversal-safe
    f = os.path.join(CFG["run_dir"], "streams", safe + ".jsonl")
    if not os.path.exists(f):
        return {"key": key, "off": 0, "file": None, "events": []}
    if off > os.path.getsize(f):                                  # rotated / truncated
        off = 0
    with open(f, "rb") as fh:
        fh.seek(off)
        raw = fh.read(1 << 20)
    parts = raw.split(b"\n")
    consumed = len(raw) - len(parts[-1])                          # bytes of complete lines only
    evs = []
    for b in parts[:-1]:
        b = b.strip()
        if b:
            try:
                evs.append(json.loads(b.decode("utf-8", "replace")))
            except Exception:                                     # noqa: BLE001
                pass
    return {"key": key, "off": off + consumed, "file": safe + ".jsonl", "events": evs}


# ---------------------------------------------------------------- board render thread
def _board_files():
    """Every board matching the (comma-separated) board_glob, de-duped + ordered by mtime -- the
    candidate TIMELINE the scroller steps through. Each glob may use ** (recursive)."""
    out = {}
    for g in CFG["board_glob"].split(","):
        g = g.strip()
        if not g:
            continue
        for b in glob.glob(g, recursive=True):
            try:
                out[os.path.abspath(b)] = os.path.getmtime(b)
            except OSError:
                pass
    ordered = [b for b, _ in sorted(out.items(), key=lambda kv: kv[1])]
    cap = CFG.get("max_boards") or 0
    return ordered[-cap:] if cap and len(ordered) > cap else ordered   # newest N (a long run has 100s)


def _reap_overlay(rel_out, proc=None):
    """Stop a thermal overlay run: kill the host `docker compose exec` (so we stop waiting) AND the CONTAINER
    python, which otherwise ORPHANS and keeps thrashing the CPU/GPU after the host side goes away. Matched by
    the unique per-board out-dir so we never reap a different board's solve."""
    if proc is not None:
        for fn in (proc.kill, lambda: proc.wait(timeout=5)):
            try:
                fn()
            except Exception:                                     # noqa: BLE001
                pass
    try:
        subprocess.run(COMPOSE + ["exec", "-T", "routing", "pkill", "-9", "-f", rel_out],
                       capture_output=True, timeout=20)
    except Exception:                                             # noqa: BLE001
        pass


def _parse_overlay(stdout, tdir):
    """Map cec_thermal_overlay.py's LAST-line JSON summary -> (layers, cbar, summary)."""
    summary = {}
    for ln in reversed((stdout or "").splitlines()):
        ln = ln.strip()
        if ln.startswith("{") and ln.endswith("}"):
            try:
                summary = json.loads(ln)
            except Exception:                                     # noqa: BLE001
                summary = {}
            break
    if summary.get("ok"):
        layers = {name: os.path.join(tdir, fn)
                  for name, fn in (summary.get("layers") or {}).items()
                  if os.path.exists(os.path.join(tdir, fn))}
        cbar = os.path.join(tdir, summary.get("cbar", "")) if summary.get("cbar") else None
        if cbar and not os.path.exists(cbar):
            cbar = None
        # full-detail copper map (the primary thermal view); stash its absolute path in the summary so
        # the candidate dict can serve it. Absent/failed -> just no detail (per-layer raster still shows).
        dfn = summary.get("detail")
        dpath = os.path.join(tdir, dfn) if dfn else None
        summary["detail_path"] = dpath if (dpath and os.path.exists(dpath)) else None
        # current-twin map (the per-net current cross-check); same degrade-safe handling as the detail map.
        cfn = summary.get("current")
        cpath = os.path.join(tdir, cfn) if cfn else None
        summary["current_path"] = cpath if (cpath and os.path.exists(cpath)) else None
        return layers, cbar, summary
    return {}, None, (summary or {"ok": False, "error": "no overlay produced"})


def _run_overlay(board, tdir, grid, timeout, extra_env=None, should_cancel=None, timeout_msg=None):
    """Run cec_thermal_overlay.py (PER-LAYER mode) in the routing container and return (layers, cbar,
    summary). Non-blocking-safe: a Popen + poll loop so the caller can CANCEL mid-solve (via should_cancel)
    and so a stuck solve is bounded by `timeout`. Any failure degrades to ({}, None, {error}) -- the thermal
    overlay must NEVER break the dashboard; the plain render still shows.

    extra_env  -- {k:v} passed as `docker compose exec -e k=v` (the fine pass sets CEC_THERMAL_GPU_AMG=1).
    should_cancel -- a 0-arg predicate polled ~every 2s; True -> reap the container solve + return cancelled.
    """
    rel_out = os.path.relpath(tdir, ROOT)
    cmd = COMPOSE + ["exec", "-T"]
    for k, v in (extra_env or {}).items():
        cmd += ["-e", f"{k}={v}"]
    cmd += ["routing", "python3", "/workspace/scripts/cec_thermal_overlay.py",
            "--board", f"/workspace/{os.path.relpath(board, ROOT)}",
            "--out-dir", f"/workspace/{rel_out}", "--grid-mm", str(grid)]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except Exception as e:                                        # noqa: BLE001
        return {}, None, {"ok": False, "error": f"{type(e).__name__}: {e}"}
    deadline = time.time() + timeout
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            _reap_overlay(rel_out, proc)
            return {}, None, {"ok": False,
                              "error": timeout_msg or f"thermal solve >{timeout:.0f}s -- layout shown, no heatmap"}
        try:
            out, _err = proc.communicate(timeout=min(2.0, remaining))   # retrying communicate keeps all output
            return _parse_overlay(out, tdir)
        except subprocess.TimeoutExpired:
            if should_cancel and should_cancel():
                _reap_overlay(rel_out, proc)
                return {}, None, {"ok": False, "error": "fine thermal cancelled (focus moved)"}
        except Exception as e:                                    # noqa: BLE001
            _reap_overlay(rel_out, proc)
            return {}, None, {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _render_thermal(board, rdir, stem):
    """OPTIONAL, NON-BLOCKING COARSE electro-thermal heatmap overlay for ONE board, run SYNCHRONOUSLY in the
    per-board render so every candidate gets a heatmap fast. CEC_DASH_THERMAL_GRID (default 0.8mm) = ~2s/board
    so the live multi-board render loop stays snappy. The FOCUSED board is additionally upgraded to a FINE
    grid asynchronously (see _fine_thermal_loop). Returns (layers, cbar, summary)."""
    grid = os.environ.get("CEC_DASH_THERMAL_GRID", "0.8")   # 0.8 = ~2s/board for the live loop. For a small
    #   curated showcase, set CEC_DASH_THERMAL_GRID=0.4 so a 0.6mm GND berth (the void around the 12V pins)
    #   is resolved -- at 0.8mm a sub-grid void averages away and reads as "no hole" (the owner-caught issue).
    tmo = 45 if grid == "0.8" else 420                      # finer grid is slower (AMG 0.15mm ~3min) -> longer window
    tdir = os.path.join(rdir, stem + "-thermal")            # PER-LAYER mode: a dir of <layer>.png + _cbar.png
    return _run_overlay(board, tdir, grid, tmo,
                        timeout_msg=f"thermal solve >{tmo}s (routed board) -- layout shown, no heatmap")


def _render_board(board):
    """Render ONE board to per-candidate artifacts under run_dir/renders/<stem>.{png,svg} +
    <stem>-layers/ (the raytraced top render + the per-layer plot SVGs). Returns a candidate dict or
    None. Paths are passed to the routing container as /workspace/<repo-relative> (the repo is mounted
    there); the build/hub-LIVE symlink is relative so it resolves identically in-container."""
    rel = os.path.relpath(board, ROOT)
    # render artifacts go to a HOST-OWNED base, NOT <run-dir>/renders: an agent/container run-dir is
    # root-owned, so the host-run dashboard can't mkdir renders/ there -> PermissionError -> BLANK panel
    # (2026-06-27). This base is under the repo (mounted /workspace) so the container can write the fill +
    # render into it too; the host only mkdir's + reads.
    rdir = os.path.join(ROOT, "build", ".dash-renders", os.path.basename(CFG["run_dir"].rstrip("/")) or "run")
    os.makedirs(rdir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(board))[0]
    png, svg = os.path.join(rdir, stem + ".png"), os.path.join(rdir, stem + ".svg")
    ldir = os.path.join(rdir, stem + "-layers")
    os.makedirs(ldir, exist_ok=True)
    # FILL ZONES first (2026-06-26): kicad-cli CANNOT refill zones, so a routed board's copper POURS
    # (the GND/12V planes) plot EMPTY -- the recurring "dashboard shows no planes/traces" bug. pcbnew's
    # ZONE_FILLER can, so fill a COPY in-container (UnFill->Fill, the cec_route.py-proven order) and
    # render/plot THAT. Degrades to the unfilled board if the fill fails -- never blocks a render.
    filled = os.path.join(rdir, stem + "-filled.kicad_pcb")
    _fill = ("import pcbnew,sys,os,shutil\n"
             "s,d=sys.argv[1],sys.argv[2]\n"
             "for e in ('.kicad_pro','.kicad_dru','.kicad_prl'):\n"
             "    p=s[:-10]+e\n"
             "    if os.path.exists(p): shutil.copy(p,d[:-10]+e)\n"
             "b=pcbnew.LoadBoard(s)\n"
             "f=pcbnew.ZONE_FILLER(b)\n"
             "[z.UnFill() for z in b.Zones()]\n"
             "f.Fill(b.Zones())\n"
             "b.Save(d)\n")
    fr = subprocess.run(COMPOSE + ["exec", "-T", "routing", "python3", "-c", _fill,
                                   f"/workspace/{rel}", f"/workspace/{os.path.relpath(filled, ROOT)}"],
                        capture_output=True, timeout=150)
    src_rel = os.path.relpath(filled, ROOT) if (fr.returncode == 0 and os.path.exists(filled)) else rel
    r = subprocess.run(COMPOSE + ["exec", "-T", "routing", "kicad-cli", "pcb", "render", "--side",
                                  "top", "-o", f"/workspace/{os.path.relpath(png, ROOT)}",
                                  f"/workspace/{src_rel}"], capture_output=True, timeout=180)
    p = subprocess.run(COMPOSE + ["exec", "-T", "routing", "kicad-cli", "pcb", "export", "svg",
                                  "--layers", CFG["plot_layers"], "--page-size-mode", "2",
                                  "--exclude-drawing-sheet",
                                  "-o", f"/workspace/{os.path.relpath(svg, ROOT)}",
                                  f"/workspace/{src_rel}"], capture_output=True, timeout=120)
    subprocess.run(COMPOSE + ["exec", "-T", "routing", "kicad-cli", "pcb", "export", "svg",
                              "--mode-multi", "--layers", CFG["plot_layers"], "--page-size-mode", "2",
                              "--exclude-drawing-sheet",
                              "-o", f"/workspace/{os.path.relpath(ldir, ROOT)}",
                              f"/workspace/{src_rel}"], capture_output=True, timeout=120)
    layers = {}
    for lf in glob.glob(os.path.join(ldir, f"{stem}-*.svg")):
        layers[os.path.basename(lf)[len(stem) + 1:-4]] = lf       # e.g. "F_Cu"
    ok_png = r.returncode == 0 and os.path.exists(png)
    ok_svg = p.returncode == 0 and os.path.exists(svg)
    if not (ok_png or ok_svg):
        return None
    # OPTIONAL per-layer COARSE electro-thermal overlay (never blocks; degrades to {} on error). The focused
    # board is then upgraded to a FINE grid asynchronously by _fine_thermal_loop, which swaps thermal_* +
    # flips thermal_tier coarse->fine in place on this candidate dict.
    thermal_layers, thermal_cbar, thermal_sum = _render_thermal(board, rdir, stem)
    return {"stem": stem, "board": board, "png": png if ok_png else None,
            "svg": svg if ok_svg else None, "layers": layers, "rdir": rdir,
            "thermal_layers": thermal_layers, "thermal_cbar": thermal_cbar, "thermal_sum": thermal_sum,
            "thermal_detail": (thermal_sum or {}).get("detail_path"),   # full-detail copper map (primary thermal view)
            "thermal_current": (thermal_sum or {}).get("current_path"),  # per-net current cross-check (twin panel)
            "thermal_tier": ("coarse" if thermal_layers else None),
            "thermal_status": ("coarse" if thermal_layers else None),
            "mtime": os.path.getmtime(board), "ts": time.time()}


def _render_loop():
    """Render every candidate board (timeline scroller) -- but render NEWEST-FIRST and publish _cands
    INCREMENTALLY after each one, so the live board shows within seconds instead of after a whole pass
    (a long run has dozens of boards). Cache by mtime -- a board is re-rendered only when it changes."""
    while True:
        try:
            with _cands_lock:
                have = {c["stem"]: c for c in _cands}
            boards = _board_files()                              # oldest -> newest
            stems = [os.path.splitext(os.path.basename(b))[0] for b in boards]
            live = set(stems)
            have = {s: c for s, c in have.items() if s in live}  # drop boards no longer present
            for b in reversed(boards):                           # newest first -> live board appears fast
                stem = os.path.splitext(os.path.basename(b))[0]
                ex = have.get(stem)
                if ex and ex.get("mtime", -1) >= os.path.getmtime(b) and (ex["png"] or ex["svg"]):
                    continue                                     # cached + current
                _render.update(status="rendering", board=stem)
                c = _render_board(b) or ex or {"stem": stem, "board": b, "png": None, "svg": None,
                                               "layers": {}, "mtime": os.path.getmtime(b), "ts": time.time()}
                have[stem] = c
                with _cands_lock:                                # publish after EACH render (board order)
                    _cands[:] = [have[s] for s in stems if s in have]
                _render.update(status="ok", board=stem, ts=c.get("ts", 0))
            if not boards:
                _render.update(status="idle", board=None)
        except Exception as e:                                    # noqa: BLE001
            _render.update(status=f"err:{type(e).__name__}")
        time.sleep(8)


def _cand_at(idx):
    """The candidate dict at scroller index *idx* (default = newest), or None."""
    with _cands_lock:
        if not _cands:
            return None
        if idx is None or idx < 0 or idx >= len(_cands):
            return _cands[-1]
        return _cands[idx]


def _focused_cand():
    """The candidate the dashboard is DISPLAYING: the frontend-reported focused stem if fresh (the viewer
    can scroll the timeline), else the newest candidate (the default the dashboard follows). This is the
    board the async fine-thermal worker upgrades to a fine grid."""
    with _cands_lock:
        cands = list(_cands)
    if not cands:
        return None
    fs, fts = _focus.get("stem"), _focus.get("ts", 0.0)
    if fs and (time.time() - fts) < 30:
        for c in cands:
            if c["stem"] == fs:
                return c
    return cands[-1]


# ---------------------------------------------------------------- async fine-thermal worker
def _fine_thermal_loop():
    """SECOND thermal tier: while the live render loop gives every board a FAST COARSE heatmap, this daemon
    upgrades the ONE focused (displayed/newest) board to a FINE grid (CEC_DASH_THERMAL_FINE_GRID, default
    0.1mm) using the GPU AMG solver in the routing container, then SWAPS the fine heatmap onto that candidate
    in place (thermal_layers/cbar/sum + thermal_tier coarse->fine). Single-flight by design (one blocking
    solve at a time -> at most one GPU job, the card is not MIG-capable). De-duped by board mtime so an
    unchanged board is never re-solved; CANCELLED (container reaped) if the focus moves on mid-solve. A fine
    error degrades silently -> the coarse heatmap stays. The fine PNGs land in a SEPARATE <stem>-thermal-fine
    dir so the coarse set survives as the fallback."""
    grid = os.environ.get("CEC_DASH_THERMAL_FINE_GRID", "0.1")
    timeout = int(os.environ.get("CEC_DASH_THERMAL_FINE_TIMEOUT", "900"))   # GPU 0.1mm ~3min -> generous margin
    solved = {}                                                  # stem -> board mtime already upgraded to fine
    while True:
        try:
            cand = _focused_cand()
            if not cand or not (cand.get("png") or cand.get("svg")):
                _fine.update(status="idle", stem=None, grid=None)
                time.sleep(3)
                continue
            stem, bmtime = cand["stem"], cand.get("mtime", 0)
            already = cand.get("thermal_tier") == "fine" and cand.get("_fine_mtime") == bmtime
            if already or solved.get(stem) == bmtime:
                # prune the de-dupe set of boards that are gone, then idle
                with _cands_lock:
                    live = {c["stem"] for c in _cands}
                for s in [s for s in solved if s not in live]:
                    solved.pop(s, None)
                _fine.update(status="idle", stem=stem, grid=None)
                time.sleep(3)
                continue
            # mark the board "fine solving" so the frontend shows the badge immediately
            with _cands_lock:
                cand["thermal_status"] = "solving"
                if cand.get("thermal_tier") is None and cand.get("thermal_layers"):
                    cand["thermal_tier"] = "coarse"
            _fine.update(status="solving", stem=stem, grid=grid)

            def _cancel(_stem=stem, _bm=bmtime):                 # cancel if the focus moves OR the board changes
                cur = _focused_cand()
                return cur is None or cur["stem"] != _stem or cur.get("mtime", 0) != _bm

            rdir = cand.get("rdir") or os.path.join(
                ROOT, "build", ".dash-renders", os.path.basename(CFG["run_dir"].rstrip("/")) or "run")
            tdir = os.path.join(rdir, stem + "-thermal-fine")
            layers, cbar, summary = _run_overlay(
                cand["board"], tdir, grid, timeout,
                extra_env={"CEC_THERMAL_GPU_AMG": "1"}, should_cancel=_cancel,
                timeout_msg=f"fine thermal >{timeout}s -- coarse heatmap shown")

            # re-resolve focus: only publish if the SAME board is still focused + unchanged (race-safe)
            cur = _focused_cand()
            same = cur is not None and cur["stem"] == stem and cur.get("mtime", 0) == bmtime
            if summary.get("ok") and layers and same:
                with _cands_lock:
                    cur["thermal_layers"] = layers
                    cur["thermal_cbar"] = cbar
                    cur["thermal_sum"] = summary
                    cur["thermal_detail"] = summary.get("detail_path")   # upgrade the detail map to the fine field
                    cur["thermal_current"] = summary.get("current_path")  # upgrade the current twin too
                    cur["thermal_tier"] = "fine"
                    cur["thermal_status"] = "fine"
                    cur["_fine_mtime"] = bmtime
                    cur["ts"] = time.time()                      # cache-bust -> the frontend re-fetches + swaps
                solved[stem] = bmtime
            else:
                if summary.get("ok"):
                    solved[stem] = bmtime                        # solved, but focus moved -> don't redo
                with _cands_lock:                                # clear the badge; keep coarse as fallback
                    if cur is not None and cur["stem"] == stem and cur.get("thermal_tier") != "fine":
                        cur["thermal_status"] = "coarse" if cur.get("thermal_layers") else None
                        if not summary.get("ok"):
                            cur["thermal_fine_error"] = summary.get("error")
            _fine.update(status="idle")
        except Exception as e:                                    # noqa: BLE001
            _fine.update(status=f"err:{type(e).__name__}")
        time.sleep(2)


# ---------------------------------------------------------------- http
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):                                    # quiet
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):                                             # noqa: N802
        path, _, q = self.path.partition("?")
        params = dict(p.split("=", 1) for p in q.split("&") if "=" in p)
        if path == "/":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/state":
            foc = params.get("focus")                            # the frontend reports the DISPLAYED stem ->
            if foc:                                              # the async fine-thermal worker upgrades it
                _focus["stem"] = unquote(foc)
                _focus["ts"] = time.time()
            bundle = None
            if os.path.exists(_runfile("morning-bundle.json")):
                try:
                    b = json.load(open(_runfile("morning-bundle.json")))
                    bundle = {k: b.get(k) for k in ("rounds", "convergence_verdict",
                              "n_usable_ratification_candidates", "n_manager_rules", "pareto_finalists")}
                except Exception:                                 # noqa: BLE001
                    pass
            with _cands_lock:
                cands = [{"stem": c["stem"], "ts": c["ts"], "has_png": bool(c["png"]),
                          "has_svg": bool(c["svg"]), "layers": sorted(c["layers"]),
                          "has_thermal": bool(c.get("thermal_layers")),
                          "thermal_layers": sorted((c.get("thermal_layers") or {}).keys()),
                          "has_thermal_cbar": bool(c.get("thermal_cbar")),
                          "has_thermal_detail": bool(c.get("thermal_detail")),  # full-detail copper map available
                          "has_thermal_current": bool(c.get("thermal_current")),  # per-net current cross-check available
                          "thermal_tier": c.get("thermal_tier"),     # coarse | fine
                          "thermal_status": c.get("thermal_status"),  # coarse | solving | fine (the badge state)
                          "thermal": (c.get("thermal_sum") or {})} for c in _cands]
            self._json({"ts": time.time(), "run": _proc_info(),
                        "measurement": _measurement(), "rules": _live_rules(),
                        "log": _log_tail(), "finding": _latest_finding(),
                        "board": {"name": _render["board"], "status": _render["status"],
                                  "rendered_ts": _render["ts"]},
                        "candidates": cands,                      # the timeline scroller's data
                        "bundle": bundle, "run_dir": CFG["run_dir"],
                        "kind": CFG.get("kind"), "auto": CFG.get("auto")})
        elif path == "/api/stream":
            self._json(_stream_text(int(params.get("off", 0))))
        elif path == "/api/seats":
            self._json({"seats": _seats()})
        elif path == "/api/agentic":
            self._json(_agentic())
        elif path == "/api/seat":
            self._json(_seat_events(os.path.basename(params.get("key", "auditor")),
                                    int(params.get("off", 0))))
        elif (path in ("/board.png", "/board.svg", "/thermal-cbar.png", "/thermal-detail.png",
                       "/thermal-current.png")
              or path.startswith("/layer/") or path.startswith("/thermal-layer/")):
            try:
                idx = int(params["cand"]) if "cand" in params else None
            except ValueError:
                idx = None
            cand = _cand_at(idx)                                   # the scroller-selected candidate
            if path == "/thermal-detail.png":
                p, ctype = (cand or {}).get("thermal_detail"), "image/png"
            elif path == "/thermal-current.png":
                p, ctype = (cand or {}).get("thermal_current"), "image/png"
            elif path == "/thermal-cbar.png":
                p, ctype = (cand or {}).get("thermal_cbar"), "image/png"
            elif path.startswith("/thermal-layer/"):
                name = os.path.basename(path[len("/thermal-layer/"):])   # traversal-safe
                p, ctype = ((cand or {}).get("thermal_layers", {}).get(name)), "image/png"
            elif path.startswith("/layer/"):
                name = os.path.basename(path[len("/layer/"):])      # traversal-safe
                p, ctype = ((cand or {}).get("layers", {}).get(name)), "image/svg+xml"
            else:
                key, ctype = (("png", "image/png") if path.endswith("png")
                              else ("svg", "image/svg+xml"))
                p = (cand or {}).get(key)
            if p and os.path.exists(p):
                body = open(p, "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self._json({"error": "not available yet"}, 404)
        elif path == "/thermal-grid":                              # the T(x,y) field for the hover-readout
            try:
                idx = int(params["cand"]) if "cand" in params else None
            except ValueError:
                idx = None
            cand = _cand_at(idx)
            tl = (cand or {}).get("thermal_layers") or {}
            gp = os.path.join(os.path.dirname(next(iter(tl.values()))), "thermal-grid.json") if tl else None
            if gp and os.path.exists(gp):
                body = open(gp, "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self._json({"error": "no grid"}, 404)
        else:
            self._json({"error": "not found"}, 404)


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>CEC live run</title><style>
body{background:#101418;color:#cfd8dc;font:13px/1.45 ui-monospace,Menlo,monospace;margin:0}
.grid{display:grid;grid-template-columns:1.1fr 1fr 1fr;grid-template-rows:auto 1fr 1fr auto;gap:8px;padding:8px;min-height:97vh;box-sizing:border-box}
.card{background:#161c22;border:1px solid #263238;border-radius:8px;padding:8px;overflow:auto;min-height:0}
h2{font-size:12px;color:#80cbc4;margin:0 0 6px;text-transform:uppercase;letter-spacing:1px}
#hdr{grid-column:1/4;display:flex;gap:24px;align-items:center}
.ok{color:#a5d6a7}.bad{color:#ef9a9a}.warn{color:#ffcc80}.dim{color:#607d8b}
#log,#thoughts{white-space:pre-wrap;word-break:break-word;font-size:12px}
#board img{max-width:100%;border-radius:4px}
table{border-collapse:collapse;width:100%}td,th{padding:1px 6px;text-align:right;font-size:11px}
th{color:#80cbc4;position:sticky;top:0;background:#161c22}
canvas{width:100%;height:90px;background:#0d1117;border-radius:4px}
.pill{background:#263238;border-radius:10px;padding:2px 10px;margin-right:6px}
.seat{border:1px solid #2e3c44;border-radius:6px;margin-bottom:8px;background:#0e1419}
.seathdr{font-size:11px;color:#80cbc4;padding:4px 8px;border-bottom:1px solid #2e3c44;position:sticky;top:0;background:#11181e;text-transform:uppercase;letter-spacing:.5px}
.seatbody{white-space:pre-wrap;word-break:break-word;font-size:11.5px;padding:6px 8px;max-height:280px;overflow:auto}
.callhdr{color:#546e7a;margin:6px 0 2px}
.reason{color:#7e8ea0;font-style:italic}
.answer{color:#c5e1a5}
</style></head><body><div class="grid">
<div class="card" id="hdr"><h2 style="margin:0">CEC live run</h2><span id="status"></span><span id="bundle"></span></div>
<div class="card"><h2>step feed (realtime)</h2><div id="log"></div></div>
<div class="card" id="board" style="display:flex;flex-direction:column"><h2 style="flex:none">latest board <span id="bstat" class="dim"></span>
<button class="pill" style="cursor:pointer;border:0;color:#cfd8dc" onclick="bmode='png';bswap()">render</button>
<button class="pill" style="cursor:pointer;border:0;color:#cfd8dc" onclick="bmode='svg';bswap()">plot</button>
<button class="pill" style="cursor:pointer;border:0;color:#cfd8dc" onclick="bmode='thermal';bswap()" title="2D electro-thermal heatmap over the layout">thermal</button>
<button class="pill" style="cursor:pointer;border:0;color:#cfd8dc" onclick="pfit()">fit</button>
<span id="thermhdr"></span>
<span id="lyrboxes"></span></h2>
<div id="cscrub" style="flex:none;display:flex;align-items:center;gap:6px;margin-bottom:5px;font-size:11px">
 <button class="pill" style="cursor:pointer;border:0;color:#cfd8dc" onclick="cstep(-1)" title="previous candidate">◀</button>
 <input type="range" id="crange" min="0" max="0" value="0" step="1" style="flex:1;accent-color:#80cbc4" oninput="cpick(+this.value)">
 <button class="pill" style="cursor:pointer;border:0;color:#cfd8dc" onclick="cstep(1)" title="next candidate">▶</button>
 <button class="pill" id="cfollow" style="cursor:pointer;border:0" onclick="followNewest=true;cpick(cands.length-1)" title="jump to newest + auto-follow">live</button>
 <span id="clabel" class="dim">no candidates yet</span></div>
<img id="bimg" src="/board.png" style="display:none;max-width:100%;border-radius:4px">
<div id="pwrap" style="flex:1;overflow:auto;cursor:grab;border-radius:4px;background:#000;min-height:0">
<div id="pstack" style="position:relative;width:860px;background:#000;isolation:isolate"></div></div>
<img id="cbar" src="/thermal-cbar.png" style="display:none;width:100%;margin-top:5px;border-radius:3px">
<div id="thtip" style="position:fixed;display:none;z-index:60;pointer-events:none;background:#101418ee;color:#e0f2f1;border:1px solid #37474f;border-radius:3px;padding:3px 7px;font:12px/1.3 monospace;white-space:nowrap"></div></div>
<div class="card" id="seatcard" style="display:flex;flex-direction:column"><h2 style="flex:none">seat streams (live) — per manager · panel lens · worker · reviewer · auditor</h2><div id="seats" style="flex:1;overflow:auto;min-height:0"><span class="dim">waiting for seats…</span></div></div>
<div class="card" style="grid-column:1/3"><h2>convergence — pen_total (orange) vs drc (blue), kelvin band (red=fail)</h2>
<canvas id="spark" width="900" height="90"></canvas><div style="max-height:230px;overflow:auto"><table id="mt"></table></div></div>
<div class="card"><h2>injected ruleset</h2><div id="rules"></div></div>
<div class="card" id="agentic" style="grid-column:1/4"><h2>agentic decisions — active tier · per-candidate verdicts · corpus-gate</h2><div id="agbody"><span class="dim">no agentic (Hub) run yet…</span></div></div>
</div><script>
let soff=0, thoughtsBuf="", bmode='svg', plotW=860, knownLayers=[], lyrOn={};
let thermGrid=null;                                           // T(x,y) field for the hover readout
let cands=[], selCand=-1, followNewest=true;                  // candidate timeline scroller state
const DEFAULT_ON={F_Cu:1,B_Cu:1,Edge_Cuts:1};                 // inner planes OFF by default
function cq(){ // image query: scope to the selected candidate + cache-bust on its render ts
 const c=cands[selCand]; return '?cand='+(selCand<0?0:selCand)+'&v='+((c&&c.ts)||0);}
function cstep(d){ if(!cands.length)return; cpick(Math.max(0,Math.min(cands.length-1,(selCand<0?cands.length-1:selCand)+d))); }
function cpick(i){ if(!cands.length)return; selCand=Math.max(0,Math.min(cands.length-1,i));
 followNewest=(selCand===cands.length-1);
 const c=cands[selCand], nl=(c&&c.layers)||[];               // adopt THIS candidate's layer set
 if(nl.join()!==knownLayers.join()){knownLayers=nl; for(const L of nl) if(!(L in lyrOn)) lyrOn[L]=!!DEFAULT_ON[L]; lyrBoxes();}
 clabel(); thermLabel(); bswap(); }
function clabel(){
 const r=document.getElementById('crange'), lab=document.getElementById('clabel'), fb=document.getElementById('cfollow');
 r.max=Math.max(0,cands.length-1); r.value=Math.max(0,selCand);
 const c=cands[selCand];
 lab.textContent = cands.length? ((selCand+1)+'/'+cands.length+'  '+(c?c.stem:'')) : 'no candidates yet';
 fb.style.background=followNewest?'#33691e':'#263238'; fb.style.color=followNewest?'#dcedc8':'#90a4ae';}
function bswap(){
 const im=document.getElementById('bimg'), pw=document.getElementById('pwrap'), cb=document.getElementById('cbar');
 im.style.display='none'; pw.style.display='block'; if(cb)cb.style.display='none';   // ALL modes use the zoom/pan frame
 lyrBoxes();                                                  // checkboxes reflect the current mode
 buildStack();                                                // png/svg/thermal all render into the zoomable pstack now
 if(bmode==='thermal'){ const c=cands[selCand];
  if(c&&c.has_thermal_detail){                                // the detail map carries its OWN colorbar+legend -> no strip, no hover
   thermGrid=null; document.getElementById('thtip').style.display='none'; }
  else { fetchThermGrid();                                    // per-layer raster fallback: load the T field for the hover readout
   if(cb){ if(c&&c.has_thermal_cbar){cb.style.display='block';cb.src='/thermal-cbar.png'+cq();} } } }
 else { thermGrid=null; document.getElementById('thtip').style.display='none'; } }
function fetchThermGrid(){
 thermGrid=null; const c=cands[selCand]; if(!c||!c.has_thermal) return;
 fetch('/thermal-grid'+cq()).then(r=>r.ok?r.json():null).then(g=>{thermGrid=g;}).catch(()=>{thermGrid=null;}); }
function thermHover(e){
 const tip=document.getElementById('thtip');
 if(bmode!=='thermal'||!thermGrid){ tip.style.display='none'; return; }
 const r=document.getElementById('pstack').getBoundingClientRect();
 const fx=(e.clientX-r.left)/r.width, fy=(e.clientY-r.top)/r.height;
 if(fx<0||fx>1||fy<0||fy>1){ tip.style.display='none'; return; }
 const rows=thermGrid.shape[0], cols=thermGrid.shape[1];
 const col=Math.max(0,Math.min(cols-1,Math.floor(fx*cols))), row=Math.max(0,Math.min(rows-1,Math.floor(fy*rows)));
 const T=thermGrid.T[row*cols+col], ex=thermGrid.extent;      // [xmin,ymin,xmax,ymax]
 const mx=(ex[0]+fx*(ex[2]-ex[0])).toFixed(1), my=(ex[1]+fy*(ex[3]-ex[1])).toFixed(1);
 tip.innerHTML=`<b style="color:#ffcc80">${T.toFixed(1)}°C</b> <span style="opacity:.55">@ ${mx},${my}mm</span>`;
 tip.style.display='block'; tip.style.left=(e.clientX+14)+'px'; tip.style.top=(e.clientY+12)+'px'; }
function tierBadge(c,t){
 // two-tier thermal indicator: coarse (fast live solve) -> "solving…" -> fine (GPU 0.1mm) for the focused board
 const g=(t&&t.grid_mm!=null)?(t.grid_mm+'mm'):'';
 if(c&&c.thermal_status==='solving')
  return `<span class="pill warn" title="upgrading the displayed board to a fine GPU (0.1mm) electro-thermal solve in the background">⟳ fine thermal: solving…</span>`;
 if(c&&c.thermal_tier==='fine')
  return `<span class="pill ok" title="fine-grid GPU AMG electro-thermal solve (resolves local hot necks the coarse grid averages away)">fine ${g}</span>`;
 if(c&&c.has_thermal)
  return `<span class="pill dim" title="fast coarse solve for the live loop; the displayed board upgrades to fine in the background">coarse ${g}</span>`;
 return '';
}
function thermLabel(){
 // show max_T / dT / verdict for the selected candidate's thermal solve in the board header
 const el=document.getElementById('thermhdr'); const c=cands[selCand];
 const t=(c&&c.thermal)||{};
 let h='';
 if(c&&c.has_thermal&&t.ok){
  const cl=t.verdict==='PASS'?'ok':'bad';
  const cool=t.cooling?`  ·  ${esc(t.cooling)}`:'';
  h=`<span class="pill ${cl}" title="2D electro-thermal: max copper temperature; gate dT<=30C over ambient ${t.ambient}C (balanced 350W; solid pins). Cooling model: ${esc(t.cooling||'still-air')}">`+
    `θ max ${t.max_T}°C  dT ${t.dT}°C  ${t.verdict}${cool}</span>`;
 } else if(c&&t&&t.error){
  h=`<span class="pill dim" title="${esc(t.error)}">θ n/a</span>`;
 }
 h+=tierBadge(c,t);                                            // coarse / solving… / fine badge
 el.innerHTML=h;}
function modeLayers(){ // the layer set + image source for the current board mode
 const c=cands[selCand], therm=(bmode==='thermal');
 if(bmode==='png') return {ls:[], base:'', therm:false};      // 3D raytrace render: one image, no per-layer toggles
 return {ls: therm?((c&&c.thermal_layers)||[]):knownLayers, base: therm?'/thermal-layer/':'/layer/', therm};}
function buildStack(){
 const st=document.getElementById('pstack'); st.style.width=plotW+'px'; st.innerHTML='';
 if(bmode==='png'){                                           // 3D raytrace render -> a single image in the zoom/pan frame
  const im=document.createElement('img'); im.src='/board.png'+cq();
  im.style.cssText='width:100%;display:block;pointer-events:none'; st.appendChild(im); return; }
 if(bmode==='thermal'){ const c=cands[selCand];               // blended detail map + its per-net CURRENT twin, shown together
  if(c&&c.has_thermal_detail){                                // (board-accurate pours/traces/pads/vias coloured by T / A)
   const mk=(src,lab)=>{ const w=document.createElement('div'); w.style.cssText='position:relative;width:100%';
    const cap=document.createElement('div'); cap.textContent=lab;
    cap.style.cssText='position:absolute;left:6px;top:4px;z-index:2;background:#0d1117cc;color:#80cbc4;font:11px monospace;padding:1px 7px;border-radius:3px;pointer-events:none';
    const im=document.createElement('img'); im.src=src+cq(); im.style.cssText='width:100%;display:block;pointer-events:none';
    w.appendChild(im); w.appendChild(cap); return w; };
   st.appendChild(mk('/thermal-detail.png','TEMPERATURE (°C) — smooth field + detailed copper'));
   if(c.has_thermal_current) st.appendChild(mk('/thermal-current.png','CURRENT cross-check (A) — heat should track current'));
   return; } }
 const {ls,base,therm}=modeLayers();
 // draw order: bottom copper first, F.Cu then Edge on top
 const order=[...ls].sort((a,b)=>(a==='Edge_Cuts')-(b==='Edge_Cuts')||(a==='F_Cu')-(b==='F_Cu'));
 const ons=order.filter(L=>lyrOn[L]);                        // show ONLY the selected layer(s); none -> blank
 let first=true;
 for(const L of ons){
  const im=document.createElement('img'); im.src=base+L+cq();
  // mix-blend-mode:lighten lets the layers STACK -- each SVG's black background (and the thermal PNGs'
  // cool/transparent areas) contributes nothing, so toggling a layer on no longer hides the others.
  im.style.cssText='width:100%;display:block;pointer-events:none;mix-blend-mode:lighten;'+(first?'position:relative':'position:absolute;left:0;top:0');
  first=false; st.appendChild(im);}}
 // NO never-blank fallback in either mode: nothing selected -> blank (the owner-caught bug was svg mode
 // falling back to the combined /board.svg, which read as "something is still selected").
function lyrBoxes(){
 const c=cands[selCand];
 if(bmode==='thermal'&&c&&c.has_thermal_detail){              // detail map shows all layers at once -> no per-layer toggles
  document.getElementById('lyrboxes').innerHTML=''; return; }
 const {ls}=modeLayers();
 document.getElementById('lyrboxes').innerHTML=ls.map(L=>
  `<label class="pill" style="cursor:pointer"><input type="checkbox" ${lyrOn[L]?'checked':''} onchange="lyrOn['${L}']=this.checked;buildStack()"> ${L.replace('_','.')}</label>`).join('');}
function pfit(){plotW=document.getElementById('pwrap').clientWidth-4;buildStack();}
// wheel-zoom anchored at the cursor + drag-pan
window.addEventListener('DOMContentLoaded',()=>{
 const pw=document.getElementById('pwrap');
 pw.addEventListener('wheel',e=>{e.preventDefault();
  const f=e.deltaY<0?1.25:0.8, nw=Math.min(24000,Math.max(200,plotW*f)), r=pw.getBoundingClientRect();
  const fx=(pw.scrollLeft+e.clientX-r.left)/plotW, fy=(pw.scrollTop+e.clientY-r.top)/plotW;
  plotW=nw; buildStack();
  pw.scrollLeft=fx*plotW-(e.clientX-r.left); pw.scrollTop=fy*plotW-(e.clientY-r.top);},{passive:false});
 let pan=null;
 pw.addEventListener('mousedown',e=>{pan={x:e.clientX,y:e.clientY,l:pw.scrollLeft,t:pw.scrollTop};pw.style.cursor='grabbing';e.preventDefault();});
 window.addEventListener('mousemove',e=>{if(pan){pw.scrollLeft=pan.l-(e.clientX-pan.x);pw.scrollTop=pan.t-(e.clientY-pan.y);}});
 window.addEventListener('mouseup',()=>{pan=null;pw.style.cursor='grab';});
 const st=document.getElementById('pstack');                  // hover readout: T(x,y) in thermal mode
 st.addEventListener('mousemove',thermHover);
 st.addEventListener('mouseleave',()=>{document.getElementById('thtip').style.display='none';});
});
async function tick(){
 try{
  // report the DISPLAYED candidate so the server upgrades THAT board's thermal to a fine grid async
  const fstem=(cands[selCand]&&cands[selCand].stem)||'';
  const s=await (await fetch('/api/state'+(fstem?('?focus='+encodeURIComponent(fstem)):''))).json();
  const r=s.run||{};
  document.getElementById('status').innerHTML=
   `<span class="pill ${r.alive?'ok':'bad'}">${r.alive?'RUNNING pid '+r.pid+' ('+(r.elapsed||'')+')':'NOT RUNNING'}</span>`+
   (s.kind?`<span class="pill ${s.auto?'ok':'dim'}">${s.auto?'AUTO ':''}${s.kind}</span>`:'')+
   `<span class="pill">rounds: ${s.measurement.length}</span>`+
   `<span class="pill">boards: ${(s.candidates||[]).length}</span>`+
   `<span class="pill dim">${(s.run_dir||'').split('/').pop()}</span>`;
  document.getElementById('bundle').innerHTML = s.bundle?
   `<span class="pill warn">FINAL: ${s.bundle.convergence_verdict} | usable ${s.bundle.n_usable_ratification_candidates} | rules ${s.bundle.n_manager_rules} | finalists ${s.bundle.pareto_finalists}</span>`:'';
  document.getElementById('log').textContent=(s.log||[]).slice(-40).join('\n');
  const el=document.getElementById('log'); el.scrollTop=el.scrollHeight;
  // board + candidate timeline scroller
  document.getElementById('bstat').textContent=`${s.board.name||''} ${s.board.status||''}`;
  const oldKey = (selCand>=0 && cands[selCand]) ? (selCand+'@'+cands[selCand].ts) : '';
  cands = s.candidates||[];
  if(followNewest || selCand<0 || selCand>=cands.length) selCand = cands.length-1;
  const c = cands[selCand];
  const nl = (c&&c.layers)||[];
  if(nl.join()!==knownLayers.join()){knownLayers=nl;
   for(const L of nl) if(!(L in lyrOn)) lyrOn[L]=!!DEFAULT_ON[L];
   lyrBoxes();}
  clabel(); thermLabel();
  const newKey = c ? (selCand+'@'+c.ts) : '';   // re-fetch the image when the selected cand/render changes
  if(newKey && newKey!==oldKey) bswap();
  // (per-seat thoughts are handled by seatTick below — one live section per seat)
  // rules
  const ru=s.rules||{};
  document.getElementById('rules').innerHTML=
   `<b>penalties</b>: ${JSON.stringify(ru.penalties||{})}<br><b>rules</b>: ${ru.n_rules||0} | accepted ${ru.n_accepted||0} | rejected/noop ${ru.n_rejected||0}<br><br>`+
   ((ru.last_rules||[]).map(x=>'• '+x.slice(0,180)).join('<br><br>'));
  // measurement table + sparkline
  const m=s.measurement||[];
  const cols=['round','verdict','kelvin_ok','plane_signal_mm','drc','unconnected','penalty_total','live_objective','n_rules','sonnet_is_new'];
  document.getElementById('mt').innerHTML='<tr>'+cols.map(c=>'<th>'+c.replace(/_/g,' ')+'</th>').join('')+'</tr>'+
   m.slice(-14).reverse().map(r=>'<tr>'+cols.map(c=>{let v=r[c];let cl='';
     if(c==='kelvin_ok')cl=v?'ok':'bad'; if(c==='verdict')cl=v==='accept'?'ok':(v==='escalate'?'warn':'');
     return `<td class="${cl}">${v}</td>`}).join('')+'</tr>').join('');
  const cv=document.getElementById('spark').getContext('2d'); cv.clearRect(0,0,900,90);
  if(m.length>1){const W=900,H=90,n=m.length;
   const mx=Math.max(...m.map(r=>r.penalty_total)),md=Math.max(...m.map(r=>r.drc));
   m.forEach((r,i)=>{const x=i*W/(n-1);
     if(!r.kelvin_ok){cv.fillStyle='rgba(239,83,80,.12)';cv.fillRect(x-W/(n-1)/2,0,W/(n-1)+1,H);}});
   cv.strokeStyle='#ffb74d';cv.beginPath();m.forEach((r,i)=>{const x=i*W/(n-1),y=H-4-(r.penalty_total/mx)*(H-10);i?cv.lineTo(x,y):cv.moveTo(x,y)});cv.stroke();
   cv.strokeStyle='#64b5f6';cv.beginPath();m.forEach((r,i)=>{const x=i*W/(n-1),y=H-4-(r.drc/md)*(H-10);i?cv.lineTo(x,y):cv.moveTo(x,y)});cv.stroke();}
 }catch(e){document.getElementById('status').innerHTML='<span class="pill bad">dashboard error: '+e+'</span>';}
}
// ---- per-seat live streams: one section per manager / panel lens / worker / reviewer / auditor ----
let seatState={};
function esc(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
async function seatTick(){
 try{
  const sl=await (await fetch('/api/seats')).json();
  const cont=document.getElementById('seats');
  const seats=sl.seats||[];
  if(seats.length && cont.firstChild && cont.firstChild.nodeType===3) cont.innerHTML='';  // clear placeholder
  for(const s of seats){
   let st=seatState[s.key];
   if(!st){
    const d=document.createElement('div'); d.className='seat';
    d.innerHTML=`<div class="seathdr">▸ ${esc(s.name)} <span class="dim" id="sm_${s.key}"></span></div>`+
                `<div class="seatbody" id="sb_${s.key}"></div>`;
    cont.appendChild(d);
    st={off:0,frags:[]}; seatState[s.key]=st;
    st.body=document.getElementById('sb_'+s.key); st.meta=document.getElementById('sm_'+s.key);
   }
   const r=await (await fetch('/api/seat?key='+encodeURIComponent(s.key)+'&off='+st.off)).json();
   if(r.off<st.off) st.frags=[];                 // rotated -> restart
   st.off=r.off;
   for(const ev of (r.events||[])){
    if(ev.kind==='start'){ st.frags.push(`<div class="callhdr">── call ${ev.call} · ${esc(ev.model||'')} ${esc(ev.role||'')} ──</div>`); if(st.meta)st.meta.textContent='call '+ev.call; }
    else if(ev.kind==='delta'){ st.frags.push(`<span class="${ev.ch==='reasoning'?'reason':'answer'}">${esc(ev.d)}</span>`); }
    else if(ev.kind==='end'){ st.frags.push(`<span class="dim"> [${ev.ok?'done':'FAIL'} ${ev.ms||0}ms]</span>\n`); }
   }
   if((r.events||[]).length){
    if(st.frags.length>500) st.frags=st.frags.slice(-500);
    const near=st.body.scrollTop+st.body.clientHeight>=st.body.scrollHeight-40;
    st.body.innerHTML=st.frags.join('');
    if(near) st.body.scrollTop=st.body.scrollHeight;   // follow the live tail, but don't yank a scrolled-up reader
   }
  }
 }catch(e){}
}
// ---- agentic decisions: resolved seat backend + per-candidate verdicts + corpus-gate (Hub report.json) ----
function vpill(v){const ok=v===true,bad=v===false;return `<span class="pill ${ok?'ok':bad?'bad':'dim'}">${v}</span>`;}
async function agenticTick(){
 try{
  const a=await (await fetch('/api/agentic')).json();
  const el=document.getElementById('agbody');
  if(!a||!a.seats){return;}                                   // leave the placeholder until a Hub run exists
  const s=a.seats||{}, be=s.backend||'?';
  const becl=be==='cloud'?'warn':(be==='local'?'ok':'dim');   // cloud=amber, local=green, off=dim
  let h=`<div style="margin-bottom:6px"><span class="pill ${becl}">TIER: ${be.toUpperCase()}</span>`+
        `<span class="pill">manager: ${esc(s.manager_model||'—')}</span>`+
        `<span class="pill">worker: ${esc(s.worker_model||'—')}</span>`+
        (s.effort?`<span class="pill">effort: ${esc(s.effort)}</span>`:'')+
        `<span class="pill dim">${esc(s.reason||'')}</span></div>`;
  h+=`<div style="margin-bottom:6px">`+
     `<span class="pill ${a.policy_ok===true?'ok':'bad'}">policy ${a.policy_ok===true?'ok':'FAIL'}</span>`+
     (a.ref_intake?`<span class="pill ${a.ref_intake.ok?'ok':'warn'}">ref intake ${a.ref_intake.ok?'ok':a.ref_intake.error?'n/a':'fail'}</span>`:'')+
     (a.corpus_fit?`<span class="pill dim">corpus-fit: ${esc(String(a.corpus_fit))}</span>`:'')+`</div>`;
  const rt=a.routes||[];
  if(rt.length){
   const cols=['rank','strat','gates_pass','kelvin_ok','diffpair_ok','conformance_fail','drc','unconnected'];
   h+='<table><tr>'+cols.map(c=>'<th>'+c.replace(/_/g,' ')+'</th>').join('')+'</tr>'+
     rt.map(r=>'<tr>'+cols.map(c=>{let v=r[c];let cl='';
       if(c==='gates_pass'||c==='kelvin_ok'||c==='diffpair_ok')cl=v===true?'ok':(v===false?'bad':'');
       if(c==='conformance_fail')cl=(v>0)?'bad':(v===0?'ok':'');
       if(c==='rank'&&v===a.best_rank)cl='ok';
       return `<td class="${cl}">${v}</td>`}).join('')+'</tr>').join('')+'</table>';
  }
  el.innerHTML=h;
 }catch(e){}
}
tick(); setInterval(tick,2000);
seatTick(); setInterval(seatTick,1500);
agenticTick(); setInterval(agenticTick,3000);
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="CEC live run dashboard (read-only; auto-tracks the live run)")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--run-dir", default=None, help="pin a run dir (default: AUTO-discover the live run)")
    ap.add_argument("--board-glob", default=None, help="pin the board glob (default: auto from the run dir)")
    ap.add_argument("--no-auto", action="store_true", help="disable auto-discovery even with no --run-dir")
    a = ap.parse_args()
    if a.run_dir or a.board_glob or a.no_auto:
        CFG["auto"] = False                                     # explicit config -> don't auto-follow
        if a.run_dir:
            CFG["run_dir"] = os.path.abspath(a.run_dir)
            CFG["board_glob"] = a.board_glob or os.path.join(CFG["run_dir"], "*.kicad_pcb")
        elif a.board_glob:
            CFG["board_glob"] = a.board_glob
    else:
        disc = _discover_run()                                  # seed from whatever is live right now
        if disc:
            CFG.update(disc)
            print(f"dashboard: auto-tracking {disc['kind']} -> {disc['run_dir']}", flush=True)
        else:
            print("dashboard: no live run found yet -- will auto-attach when one starts", flush=True)
    threading.Thread(target=_render_loop, daemon=True).start()
    threading.Thread(target=_discover_loop, daemon=True).start()
    threading.Thread(target=_fine_thermal_loop, daemon=True).start()   # async fine-grid upgrade of the focused board
    print(f"dashboard: http://localhost:{a.port}  (auto={CFG['auto']}, run_dir={CFG['run_dir']})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
