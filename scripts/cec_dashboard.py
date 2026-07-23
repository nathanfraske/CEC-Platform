#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_dashboard -- BOARD BROWSER + high-res ANALYZER.
# ============================================================================
# Owner directive (2026-06-30): the dashboard is ONE thing done well -- a full
# high-res board browser + analyzer. No live-run auto-tracking, no per-layer
# raster fallback, no agentic/seat/convergence panels. Just:
#
#   1. BOARD BROWSER -- every archived board lives in its own TIMESTAMPED dir
#      under build/board-archive/<YYYYmmddTHHMM>-<name>/ holding the snapshotted
#      .kicad_pcb, the two analysis PNGs, and a summary.json (name, ts, gates).
#      The browser is a newest-first timeline; each row shows a CLEAN / FAILED
#      gate-verdict badge. Click one to open it in the analyzer.
#
#   2. HIGH-RES ANALYZER -- the owner-approved two-panel detail render
#      (cec_thermal_overlay blended smooth-field + translucent-stacked copper:
#      the TEMPERATURE panel + the CURRENT cross-check panel), shown in a
#      zoom/pan/fit frame at full resolution (>=1600px). Gate badges:
#      kelvin_ok / foreign_on_pour / drc / unconnected / thermal.
#
# Architecture: a plain stdlib http.server on the HOST. The HOST never imports
# pcbnew -- it shells the heavy work (thermal solve + render + gate eval) into
# the routing container, which has pcbnew + cupy (GPU). This same file runs the
# in-container half too: `cec_dashboard.py --analyze-board ...` (run INSIDE the
# container) does one 2.5D solve, draws both panels, evaluates the gates, and
# prints a JSON summary -- so there is no nested-quoting helper script, one file.
#
# Archiving is non-blocking: a single background worker (GPU is single-flight)
# drains an archive queue. Seeding + ad-hoc --archive enqueue onto it.
#
# Usage (host):
#   python3 scripts/cec_dashboard.py [--port 8090] [--seed]
#   python3 scripts/cec_dashboard.py --archive build/route-clean/build-final.kicad_pcb --name eps
#   then open http://localhost:8090
# Usage (in-container, internal):
#   python3 scripts/cec_dashboard.py --analyze-board --board B --detail D.png --current C.png
# ============================================================================
import argparse
import glob
import json
import os
import queue
import re
import shlex
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPOSE_FILE = os.path.join(ROOT, "docker", "compose.yaml")
ARCHIVE_ROOT = os.path.join(ROOT, "build", "board-archive")

# ---- the owner-validated solve recipe (KEEP/REUSE) --------------------------
SOLVE = {"ambient": 50.0, "grid_mm": 0.2, "h_eff": 15.0}   # board_thermal_config -> _prepare_filled -> solve
PANEL_W = 1400                # final_board_w; total PNG >= ~1772px (board + 372px legend) -> the >=1600px ask
GATE_DT = 30.0               # dT-over-ambient PASS gate
WX_NOISE = re.compile(r"duplicate image handler|Debug:|Xvfb|wxWidgets")

# The 3 key boards the archive is seeded with (newest under a glob is taken).
SEED_BOARDS = [
    ("build/route-clean/build-final.kicad_pcb",                  "eps-build-final"),
    ("build/route-pcie2-inrow/pcie2-inrow-routed.kicad_pcb",     "pcie2-inrow-routed"),
    ("build/route-pcie3-forcepour/*.kicad_pcb",                  "pcie3-rev2-routed"),  # glob: latest pcie3
]

# ---- shared archive state (host server) -------------------------------------
_archive = []                 # list of summary dicts, NEWEST FIRST
_archive_by_id = {}           # id -> summary
_archive_lock = threading.Lock()
_jobs = queue.Queue()         # (source_pcb_path, name) archive jobs
_seed_status = {"active": None, "pending": 0, "done": [], "errors": []}
_page_rev = str(int(time.time()))   # server-start stamp: stale browser tabs self-reload on mismatch

# ---- board LIBRARY (explorer) ------------------------------------------------
# The library is what the agent is WORKING ON: the committed beta line (BETA marker
# dirs per beta/README.md) + the fresh pipeline outputs under build/. The watcher
# auto-archives anything NEW matching WATCH_GLOBS (the fresh-run output convention:
# every accepted candidate of the synthesis wave lands in build/fresh/<board>/), so
# new boards appear in the snapshot timeline as they are made.
# build/fresh = the original fresh-run convention; build/fresh-wave-loop = the wave
# drivers' --out publish root (winners + reports land there at wave end -- the 12vhpwr
# work14 relaunch surfaced the gap: the dash never archived its PCBs). WORK dirs
# (build/fresh-wave-loop-work*, build/fresh-work) stay UNWATCHED on purpose: the
# activity feed + the fresh list already show in-progress variants, and auto-archiving
# every intermediate would churn renders/GPU solves. CEC_DASH_WATCH adds extra
# repo-relative globs (comma-separated) without a code edit.
WATCH_GLOBS = ["build/fresh/**/*.kicad_pcb",
               "build/fresh-wave-loop/**/*.kicad_pcb"] + [
    g.strip() for g in os.environ.get("CEC_DASH_WATCH", "").split(",") if g.strip()]
_watch_seen = {}              # path -> mtime already enqueued
_watch_status = {"globs": list(WATCH_GLOBS), "enqueued": 0, "last_scan": None}


def _beta_boards():
    """The committed beta line: every dir carrying a BETA marker (beta/README.md convention)
    plus the output daughterboards. Newest .kicad_pcb (non-routed) + DRAFT state per board."""
    out = []
    pats = [os.path.join(ROOT, "beta", "*"), os.path.join(ROOT, "modules", "*"),
            os.path.join(ROOT, "hubs", "*"),
            os.path.join(ROOT, "beta", "output-daughterboards", "*"),
            os.path.join(ROOT, "modules", "output-daughterboards", "*")]
    for d in sorted({d for p in pats for d in glob.glob(p) if os.path.isdir(d)}):
        is_beta = os.path.exists(os.path.join(d, "BETA"))
        is_db = os.path.sep + "output-daughterboards" + os.path.sep in d + os.path.sep
        if not (is_beta or is_db):
            continue
        pcbs = [p for p in glob.glob(os.path.join(d, "*.kicad_pcb"))
                if "-routed" not in p and ".merged." not in p]
        pcb = max(pcbs, key=os.path.getmtime) if pcbs else None
        if not pcb and not glob.glob(os.path.join(d, "*.kicad_sch")):
            continue                       # a grouping dir, not a board
        out.append({"name": os.path.basename(d), "dir": os.path.relpath(d, ROOT),
                    "pcb": os.path.relpath(pcb, ROOT) if pcb else None,
                    "mtime": os.path.getmtime(pcb) if pcb else None,
                    "draft": os.path.exists(os.path.join(d, "DRAFT")),
                    "sch": bool(glob.glob(os.path.join(d, "*.kicad_sch")))})
    return out


def _fresh_runs(limit=60):
    """Fresh pipeline outputs: every *.kicad_pcb under build/ (newest first) EXCEPT the
    archive's own snapshots -- the working set the explorer browses."""
    skip = os.path.sep + "board-archive" + os.path.sep
    hits = []
    for p in glob.glob(os.path.join(ROOT, "build", "**", "*.kicad_pcb"), recursive=True):
        if skip in p or not os.path.isfile(p):
            continue
        hits.append({"path": os.path.relpath(p, ROOT), "mtime": os.path.getmtime(p),
                     "name": os.path.splitext(os.path.basename(p))[0],
                     "dir": os.path.relpath(os.path.dirname(p), ROOT)})
    hits.sort(key=lambda h: -h["mtime"])
    return hits[:limit]


def _worklog(limit=48):
    """The agent ACTIVITY FEED: build/worklog.jsonl events (renders/waves/studies logged by
    cec_worklog) MERGED with recent git commits (committed work appears automatically),
    newest first. This is the owner's visual-verification window -- see cec_worklog.py."""
    ev = []
    wl = os.path.join(ROOT, "build", "worklog.jsonl")
    if os.path.exists(wl):
        for ln in open(wl).read().splitlines()[-150:]:
            try:
                e = json.loads(ln)
                if isinstance(e, dict) and e.get("ts"):
                    ev.append(e)
            except Exception:                              # noqa: BLE001
                pass
    try:
        out = subprocess.run(["git", "log", "-30", "--pretty=%ct%x09%h%x09%s"],
                             cwd=ROOT, capture_output=True, text=True, timeout=10).stdout
        for ln in out.splitlines():
            ts, h, s = ln.split("\t", 2)
            ev.append({"ts": float(ts), "tag": "commit", "title": s, "detail": h, "image": None})
    except Exception:                                      # noqa: BLE001
        pass
    ev.sort(key=lambda e: -e.get("ts", 0))
    return ev[:limit]


def _artifact_path(rel):
    """Traversal-safe repo-relative IMAGE path for the activity viewer."""
    if not rel:
        return None
    p = os.path.abspath(os.path.join(ROOT, rel))
    if not p.startswith(ROOT + os.path.sep) or not os.path.isfile(p):
        return None
    if not p.lower().endswith((".png", ".svg", ".jpg", ".jpeg")):
        return None
    return p


def _safe_src(rel):
    """Resolve a library/fresh relpath to an absolute .kicad_pcb inside the repo, or None."""
    if not rel or not rel.endswith(".kicad_pcb"):
        return None
    p = os.path.abspath(os.path.join(ROOT, rel))
    if not p.startswith(ROOT + os.path.sep) or not os.path.isfile(p):
        return None
    return p


def _watcher(poll_s=15):
    """Auto-archive NEW boards matching WATCH_GLOBS as they land (mtime-keyed, settle-guarded:
    a file must be >5s old so a mid-write board is not snapshotted half-saved)."""
    while True:
        now = time.time()
        for pat in WATCH_GLOBS:
            for p in glob.glob(os.path.join(ROOT, pat), recursive=True):
                try:
                    mt = os.path.getmtime(p)
                except OSError:
                    continue
                if now - mt < 5 or _watch_seen.get(p) == mt:
                    continue
                _watch_seen[p] = mt
                name = _slug(os.path.relpath(p, os.path.join(ROOT, "build"))[:-len(".kicad_pcb")])
                _jobs.put((p, name))
                _watch_status["enqueued"] += 1
        _watch_status["last_scan"] = time.strftime("%H:%M:%S")
        _seed_status["pending"] = _jobs.qsize()
        time.sleep(poll_s)


# ============================================================================
#  IN-CONTAINER half -- one solve, two panels, gate eval. Imports pcbnew only
#  here (this branch runs inside the routing container).
# ============================================================================
def _analyze_in_container(board, detail_png, current_png, width,
                          render_png=None, plotf_svg=None, plotb_svg=None):
    """Solve the 2.5D field ONCE (board_thermal_config -> _prepare_filled -> solve at the SOLVE recipe),
    draw the TEMPERATURE panel + the CURRENT cross-check panel from that one field, evaluate the
    gates, and (owner ask 2026-07-07) export the raytraced top RENDER + the front/back copper
    PLOTS. Print one JSON line {thermal, gates}; every part is degrade-safe (a failed render
    still yields gates and panels, and vice-versa). Runs in the container only."""
    import sys
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    out = {"ok": True, "thermal": {"ok": False, "error": "not run"},
           "gates": {"ok": False, "error": "not run"}}

    # ---- render + copper plots (kicad-cli; independent of the solve) ----
    if render_png:
        try:
            import cec_render
            cec_render.render(board, render_png, side="top", timeout=300)  # silk stripped
        except Exception:                                           # noqa: BLE001
            pass
    for svg, layers, mirror in ((plotf_svg, "F.Cu,Edge.Cuts,F.Silkscreen", False),
                                (plotb_svg, "B.Cu,Edge.Cuts,B.Silkscreen", False)):
        if not svg:
            continue
        try:
            cmd = ["kicad-cli", "pcb", "export", "svg", "--mode-single", "-o", svg,
                   "--layers", layers, "--page-size-mode", "2",
                   "--exclude-drawing-sheet", board]
            if mirror:
                cmd.insert(-1, "--mirror")
            subprocess.run(cmd, capture_output=True, timeout=300)
        except Exception:                                           # noqa: BLE001
            pass

    # ---- thermal solve + the two blended detail panels (reuse cec_thermal_overlay) ----
    try:
        import cec_thermal_overlay as ov
        res, fpath, cool = ov._solve_thermal(
            board, ambient=SOLVE["ambient"], grid_mm=SOLVE["grid_mm"], h_eff=SOLVE["h_eff"])
        ov._draw_detail_blend(fpath, res, detail_png, mode="thermal", cool_label=cool,
                              gate_dt=GATE_DT, final_board_w=width, title=os.path.basename(board))
        ov._draw_detail_blend(fpath, res, current_png, mode="current", cool_label=cool,
                              gate_dt=GATE_DT, final_board_w=width, title=os.path.basename(board))
        dt = res.max_T - res.ambient
        out["thermal"] = {"ok": True, "max_T": round(res.max_T, 2), "ambient": res.ambient,
                          "dT": round(dt, 2), "verdict": "PASS" if dt <= GATE_DT else "FAIL",
                          "cooling": cool, "grid_mm": res.grid_mm,
                          "detail": os.path.basename(detail_png), "current": os.path.basename(current_png)}
    except Exception as e:                                          # noqa: BLE001
        out["thermal"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    # ---- gates: kelvin / diffpair / drc / unconnected + foreign-on-pour (CEC_SHUNT_GAP set by caller) ----
    try:
        import cec_score
        import cec_constraints
        m = cec_score.score(board)
        fp = cec_constraints.foreign_on_pour_summary(board)
        out["gates"] = {"ok": True, "kelvin_ok": bool(m.kelvin_ok), "diffpair_ok": bool(m.diffpair_ok),
                        "drc": int(m.drc), "unconnected": int(m.unconnected),
                        "gates_pass": bool(m.gates_pass),
                        "foreign": {"status": fp.get("status"), "applicable": fp.get("applicable"),
                                    "n_tracks": int(fp.get("n_tracks") or 0),
                                    "n_vias": int(fp.get("n_vias") or 0)}}
    except Exception as e:                                          # noqa: BLE001
        out["gates"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    print(json.dumps(out))                                         # LAST line = the parseable summary


# ============================================================================
#  HOST half -- container exec, archiving, browser/analyzer server.
# ============================================================================
def _container_run(argv, timeout, env=None):
    """Run `argv` inside the routing container via `sg docker -c "... exec -T routing bash -lc '...'"`.
    `env` is a dict of VAR=val prefixed before the command (NOT shell-quoted as args). Returns the
    CompletedProcess; raises on timeout (caller catches). Plain args -> no nested-quoting helper script."""
    prefix = "".join(f"{k}={shlex.quote(str(v))} " for k, v in (env or {}).items())
    inner = "cd /workspace && " + prefix + " ".join(shlex.quote(a) for a in argv)
    compose = (f"docker compose -f {shlex.quote(COMPOSE_FILE)} exec -T routing "
               f"bash -lc {shlex.quote(inner)}")
    return subprocess.run(["sg", "docker", "-c", compose],
                          capture_output=True, text=True, timeout=timeout)


def _parse_last_json(stdout):
    """Last `{...}` line of a container run's stdout (wx Debug noise interleaves before it)."""
    for ln in reversed((stdout or "").splitlines()):
        ln = ln.strip()
        if ln.startswith("{") and ln.endswith("}"):
            try:
                return json.loads(ln)
            except Exception:                                      # noqa: BLE001
                continue
    return None


def _slug(name):
    return re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-") or "board"


def _verdict(gates, thermal):
    """Roll the per-gate state into CLEAN / FAILED + the ordered list of failing gates. Thermal counts
    only on an actual FAIL (a thermal that did not solve is shown 'n/a', it does not by itself fail the
    board)."""
    failing = []
    if not gates.get("ok"):
        return "FAILED", ["gate-eval"]
    if not gates.get("kelvin_ok"):
        failing.append("kelvin")
    fp = gates.get("foreign") or {}
    if fp.get("status") == "error" or (fp.get("status") == "ok" and (fp.get("n_tracks") or fp.get("n_vias"))):
        failing.append("foreign")
    if gates.get("unconnected"):
        failing.append("unconnected")
    if gates.get("drc"):
        failing.append("drc")
    if thermal.get("ok") and thermal.get("verdict") == "FAIL":
        failing.append("thermal")
    return ("CLEAN" if not failing else "FAILED"), failing


def archive_board(pcb_path, name):
    """Snapshot ONE board into its own timestamped archive dir, render its two analysis panels, evaluate
    its gates, and write summary.json. Returns the summary dict (also appended to the live _archive).

    Layout:  build/board-archive/<YYYYmmddTHHMM>-<name>/
               board.kicad_pcb   (+ .kicad_pro/.kicad_dru/.kicad_prl siblings if present)
               detail.png        TEMPERATURE panel (smooth field + translucent copper)
               current.png       per-net CURRENT cross-check panel
               summary.json      {name, timestamp, gates, thermal, verdict}

    The host snapshots + mkdir's (host-owned); the container writes the PNGs (root, world-readable) into
    the host dir. Degrade-safe: a render/gate failure still produces a summary (verdict reflects it)."""
    pcb_path = os.path.abspath(pcb_path)
    if not os.path.exists(pcb_path):
        raise FileNotFoundError(pcb_path)
    ts = time.strftime("%Y%m%dT%H%M")
    aid = f"{ts}-{_slug(name)}"
    adir = os.path.join(ARCHIVE_ROOT, aid)
    os.makedirs(adir, exist_ok=True)

    # snapshot the board + its project siblings (needed for fill/score/DRC)
    snap = os.path.join(adir, "board.kicad_pcb")
    shutil.copy(pcb_path, snap)
    base = pcb_path[:-len(".kicad_pcb")]
    for ext in (".kicad_pro", ".kicad_dru", ".kicad_prl"):
        sib = base + ext
        if os.path.exists(sib):
            shutil.copy(sib, os.path.join(adir, "board" + ext))

    detail = os.path.join(adir, "detail.png")
    current = os.path.join(adir, "current.png")
    render = os.path.join(adir, "render.png")
    plotf = os.path.join(adir, "plot-f.svg")
    plotb = os.path.join(adir, "plot-b.svg")
    rel = lambda p: "/workspace/" + os.path.relpath(p, ROOT)       # noqa: E731
    summary = {"schema": 1, "id": aid, "name": name, "timestamp": ts,
               "ts_human": time.strftime("%Y-%m-%d %H:%M"), "epoch": time.time(),
               "source": os.path.relpath(pcb_path, ROOT), "board": "board.kicad_pcb",
               "panels": {}, "gates": {"ok": False, "error": "not run"},
               "thermal": {"ok": False, "error": "not run"}, "verdict": "FAILED", "failing": ["pending"]}
    try:
        cp = _container_run(
            ["python3", "scripts/cec_dashboard.py", "--analyze-board",
             "--board", rel(snap), "--detail", rel(detail), "--current", rel(current),
             "--render", rel(render), "--plotf", rel(plotf), "--plotb", rel(plotb),
             "--width", str(PANEL_W)],
            timeout=900, env={"CEC_SHUNT_GAP": "1", "CEC_THERMAL_GPU_AMG": "1"})
        res = _parse_last_json(cp.stdout)
        if res:
            summary["thermal"] = res.get("thermal", summary["thermal"])
            summary["gates"] = res.get("gates", summary["gates"])
        else:
            summary["gates"] = {"ok": False, "error": (cp.stderr or cp.stdout or "no output")[-300:]}
    except subprocess.TimeoutExpired:
        summary["gates"] = {"ok": False, "error": "analyze timed out (>900s)"}
    except Exception as e:                                          # noqa: BLE001
        summary["gates"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    if os.path.exists(detail):
        summary["panels"]["detail"] = "detail.png"
    if os.path.exists(current):
        summary["panels"]["current"] = "current.png"
    if os.path.exists(render):
        summary["panels"]["render"] = "render.png"
    if os.path.exists(plotf):
        summary["panels"]["plotf"] = "plot-f.svg"
    if os.path.exists(plotb):
        summary["panels"]["plotb"] = "plot-b.svg"
    summary["verdict"], summary["failing"] = _verdict(summary["gates"], summary["thermal"])

    with open(os.path.join(adir, "summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2)
    with _archive_lock:
        _archive_by_id[aid] = summary
        _archive[:] = sorted(_archive_by_id.values(), key=lambda s: -s.get("epoch", 0))
    return summary


def _load_archive():
    """Load every build/board-archive/*/summary.json into the live list (newest first)."""
    found = {}
    for sj in glob.glob(os.path.join(ARCHIVE_ROOT, "*", "summary.json")):
        try:
            s = json.load(open(sj))
            s["id"] = s.get("id") or os.path.basename(os.path.dirname(sj))
            found[s["id"]] = s
        except Exception:                                          # noqa: BLE001
            pass
    with _archive_lock:
        _archive_by_id.clear()
        _archive_by_id.update(found)
        _archive[:] = sorted(found.values(), key=lambda s: -s.get("epoch", 0))


def _resolve_seed(pat):
    """Resolve a SEED_BOARDS path/glob to an existing board (newest match for a glob), or None."""
    p = pat if os.path.isabs(pat) else os.path.join(ROOT, pat)
    if "*" in p:
        ms = [m for m in glob.glob(p) if os.path.isfile(m)]
        # newest; tie-break to the shorter basename so the main routed board wins over a "-under" variant
        return max(ms, key=lambda m: (os.path.getmtime(m), -len(os.path.basename(m)))) if ms else None
    return p if os.path.exists(p) else None


def _archive_worker():
    """Single-flight archive worker -- drains the job queue ONE board at a time (the GPU solve is
    single-flight). Never lets one bad board kill the worker."""
    while True:
        pcb, name = _jobs.get()
        _seed_status["active"] = name
        _seed_status["pending"] = _jobs.qsize()
        try:
            archive_board(pcb, name)
            _seed_status["done"].append(name)
        except Exception as e:                                     # noqa: BLE001
            _seed_status["errors"].append(f"{name}: {type(e).__name__}: {e}")
        finally:
            _seed_status["active"] = None
            _seed_status["pending"] = _jobs.qsize()
            _jobs.task_done()


def _enqueue_seed():
    """Enqueue the key boards, de-duped against what is already archived (same name + same source mtime),
    so a re-launch with --seed does not pile up identical entries."""
    seen = set()
    with _archive_lock:
        for s in _archive_by_id.values():
            seen.add((s.get("name"), s.get("source")))
    for pat, name in SEED_BOARDS:
        b = _resolve_seed(pat)
        if not b:
            _seed_status["errors"].append(f"{name}: no board at {pat}")
            continue
        if (name, os.path.relpath(b, ROOT)) in seen:
            continue                                               # already archived this exact source
        seen.add((name, os.path.relpath(b, ROOT)))
        _jobs.put((b, name))
    _seed_status["pending"] = _jobs.qsize()


# ---------------------------------------------------------------- http
def _img_path(aid, panel):
    """Traversal-safe archive image path for (id, panel), or None. Besides the five built-in
    panels, an entry's summary.json may register EXTRA panels (ad-hoc studies, e.g. a
    worst-case-current thermal solve) as {key: filename}; the filename must be a bare
    .png/.svg basename inside that entry's own archive dir."""
    aid = os.path.basename(aid or "")
    if not re.match(r"^[A-Za-z0-9T_-]+$", aid):
        return None
    fn = {"detail": "detail.png", "current": "current.png", "render": "render.png",
          "plotf": "plot-f.svg", "plotb": "plot-b.svg"}.get(panel)
    if not fn:
        with _archive_lock:
            s = _archive_by_id.get(aid) or {}
        fn = (s.get("panels") or {}).get(panel)
        if (not fn or os.path.basename(fn) != fn
                or not fn.endswith((".png", ".svg"))):
            return None
    p = os.path.join(ARCHIVE_ROOT, aid, fn)
    return p if os.path.exists(p) else None


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):                                     # quiet
        pass

    def _send(self, body, ctype, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if "html" in ctype or "json" in ctype:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(json.dumps(obj).encode(), "application/json", code)

    def do_HEAD(self):
        # existence probe for the viewer's 3D-twin toggle (stdlib has no default do_HEAD)
        try:
            from urllib.parse import urlparse, parse_qs
            u = urlparse(self.path)
            if u.path == "/artifact":
                p = (parse_qs(u.query).get("p") or [""])[0]
                full = os.path.realpath(os.path.join(ROOT, p))
                ok = full.startswith(ROOT) and os.path.isfile(full)
                self.send_response(200 if ok else 404)
                self.end_headers()
                return
        except Exception:                                # noqa: BLE001
            pass
        self.send_response(404)
        self.end_headers()

    def do_GET(self):                                              # noqa: N802
        path, _, q = self.path.partition("?")
        params = {k: unquote(v) for k, v in (p.split("=", 1) for p in q.split("&") if "=" in p)}
        if path == "/":
            self._send(PAGE.replace("__REV__", _page_rev).encode(), "text/html; charset=utf-8")
        elif path == "/api/archive":
            with _archive_lock:
                boards = list(_archive)
            self._json({"ts": time.time(), "rev": _page_rev, "boards": boards,
                        "seeding": dict(_seed_status), "archive_root": os.path.relpath(ARCHIVE_ROOT, ROOT)})
        elif path == "/api/worklog":
            self._json({"ts": time.time(), "events": _worklog()})
        elif path == "/artifact":
            p = _artifact_path(params.get("p"))
            if p:
                ctype = "image/svg+xml" if p.endswith(".svg") else "image/png"
                self._send(open(p, "rb").read(), ctype)
            else:
                self._json({"error": "no such artifact"}, 404)
        elif path == "/api/library":
            self._json({"ts": time.time(), "beta": _beta_boards(), "fresh": _fresh_runs(),
                        "watch": dict(_watch_status)})
        elif path == "/api/enqueue":
            src = _safe_src(params.get("src"))
            if not src:
                self._json({"error": "bad src (must be an existing repo-relative .kicad_pcb)"}, 400)
            else:
                name = _slug(params.get("name") or os.path.splitext(os.path.basename(src))[0])
                _jobs.put((src, name))
                _seed_status["pending"] = _jobs.qsize()
                self._json({"ok": True, "queued": name, "pending": _jobs.qsize()})
        elif path == "/img":
            p = _img_path(params.get("id"), params.get("panel", "detail"))
            if p:
                ctype = "image/svg+xml" if p.endswith(".svg") else "image/png"
                self._send(open(p, "rb").read(), ctype)
            else:
                self._json({"error": "no such panel"}, 404)
        else:
            self._json({"error": "not found"}, 404)


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>CEC board browser</title><style>
*{box-sizing:border-box}
body{background:#101418;color:#cfd8dc;font:13px/1.45 ui-monospace,Menlo,monospace;margin:0;height:100vh;overflow:hidden}
#app{display:grid;grid-template-columns:340px minmax(0,1fr);height:100vh}
#side{border-right:1px solid #263238;display:flex;flex-direction:column;min-height:0}
#sidehdr{padding:10px 12px;border-bottom:1px solid #263238;flex:none}
#sidehdr h1{font-size:14px;color:#80cbc4;margin:0;letter-spacing:1px}
#seed{font-size:11px;color:#90a4ae;margin-top:6px;min-height:14px}
#list{overflow:auto;flex:1;min-height:0}
.row{padding:9px 12px;border-bottom:1px solid #1c242b;cursor:pointer}
.row:hover{background:#161c22}
.row.sel{background:#17242b;border-left:3px solid #80cbc4;padding-left:9px}
.row .nm{color:#e0f2f1;font-size:12.5px}
.row .tsx{color:#607d8b;font-size:11px}
.main{display:flex;flex-direction:column;min-height:0;min-width:0}
#bar{padding:8px 12px;border-bottom:1px solid #263238;flex:none;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
#bar .title{color:#e0f2f1;font-size:13px;margin-right:8px}
.pill{background:#263238;border-radius:10px;padding:2px 10px;font-size:11px;white-space:nowrap}
button.pill{cursor:pointer;border:0;color:#cfd8dc}
button.pill.on{background:#33691e;color:#dcedc8}
.ok{background:#1b3a1f;color:#a5d6a7}.bad{background:#4a1f1f;color:#ef9a9a}
.warn{background:#4a3a17;color:#ffcc80}.dim{color:#607d8b}
.sec{padding:7px 12px;background:#0d1418;color:#80cbc4;font-size:11px;letter-spacing:1px;
  cursor:pointer;border-bottom:1px solid #263238;position:sticky;top:0;z-index:1}
button.pill.act{background:#1c313a;color:#80deea;margin-left:6px;float:right}
.pill.act2{background:#2a1c3a;color:#ce93d8}.pill.dim2{background:#1c242b;color:#78909c}
button.pill.act:hover{background:#26424e}
#pwrap{flex:1;overflow:auto;cursor:grab;background:#000;min-height:0}
#pstack{position:relative;width:1100px;background:#000;isolation:isolate}
#pstack .panel{position:relative;width:100%}
#pstack .panel img{width:100%;display:block;pointer-events:none}
#pstack .cap{position:absolute;left:8px;top:6px;z-index:2;background:#0d1117cc;color:#80cbc4;
  font:11px monospace;padding:2px 8px;border-radius:3px;pointer-events:none}
#empty{padding:40px;color:#607d8b;text-align:center}
</style></head><body><div id="app">
<div id="side">
 <div id="sidehdr"><h1>CEC BOARD LIBRARY <span style="color:#607d8b;font-size:10px">ui __REV__</span></h1><div id="seed"></div></div>
 <div id="list"></div>
</div>
<div class="main">
 <div id="bar"><span class="title" id="btitle">select a board</span><span id="badges"></span>
  <span style="flex:1"></span>
  <button class="pill" id="m_all" onclick="setMode('all')">all</button>
  <button class="pill" id="m_detail" onclick="setMode('detail')">temperature</button>
  <button class="pill" id="m_current" onclick="setMode('current')">current</button>
  <button class="pill" id="m_render" onclick="setMode('render')">render</button>
  <button class="pill" id="m_plot" onclick="setMode('plot')">plot</button>
  <button class="pill" onclick="fit()">fit</button>
  <button class="pill" onclick="zoom(1.25)">+</button>
  <button class="pill" onclick="zoom(0.8)">-</button>
 </div>
 <div id="pwrap"><div id="pstack"><div id="empty">no board selected</div></div></div>
</div></div>
<script>
let boards=[], lib={beta:[],fresh:[],watch:{}}, acts=[], cur=null, curAct=null, mode='all', plotW=1100, actBodies=false, actTwin=null, actImg=null;
const PAGE_REV='__REV__';
let secOpen={act:true,beta:true,fresh:true,snaps:true};
function esc(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function vpill(v){const cl=v==='CLEAN'?'ok':'bad';return `<span class="pill ${cl}">${v}</span>`;}
function ago(mt){if(!mt)return'';const s=Date.now()/1000-mt;
 if(s<90)return Math.round(s)+'s ago';if(s<5400)return Math.round(s/60)+'m ago';
 if(s<172800)return Math.round(s/3600)+'h ago';return Math.round(s/86400)+'d ago';}
function toggleSec(k){secOpen[k]=!secOpen[k];renderList();}
async function enqueue(src,name,ev){ev.stopPropagation();
 await fetch(`/api/enqueue?src=${encodeURIComponent(src)}&name=${encodeURIComponent(name)}`);tick();}
// ---- sidebar: LIBRARY explorer (beta line + fresh runs) + snapshot timeline ---
function sec(k,title,count){
 return `<div class="sec" onclick="toggleSec('${k}')">${secOpen[k]?'▾':'▸'} ${title} <span class="dim">${count}</span></div>`;}
function renderList(){
 const el=document.getElementById('list');
 let h='';
 // agent ACTIVITY feed (worklog + commits) -- the owner's visual-verification window
 h+=sec('act','ACTIVITY — live work feed',acts.length);
 if(secOpen.act) h+=acts.map((a,i)=>{
  const tag=`<span class="pill ${a.tag==='commit'?'dim2':'act2'}">${esc(a.tag)}</span>`;
  const cam=a.image?' 📷':'';
  return `<div class="row ${curAct===i?'sel':''}" onclick="pickAct(${i})">
    <div class="nm">${tag} ${esc(a.title)}${cam}</div>
    <div class="tsx">${ago(a.ts)}${a.detail?(' · '+esc(a.detail.slice(0,70))):''}</div></div>`;
 }).join('');
 // beta line (committed boards)
 h+=sec('beta','BETA LINE',lib.beta.length);
 if(secOpen.beta) h+=lib.beta.map(b=>{
  const badges=(b.draft?'<span class="pill warn">DRAFT</span>':'')
   +(b.pcb?'':'<span class="pill bad">no pcb</span>');
  const act=b.pcb?`<button class="pill act" onclick="enqueue('${esc(b.pcb)}','${esc(b.name)}',event)">analyze ▶</button>`:'';
  return `<div class="row"><div class="nm">${esc(b.name)} ${badges}${act}</div>
    <div class="tsx">${esc(b.dir)}${b.mtime?(' · pcb '+ago(b.mtime)):''}</div></div>`;
 }).join('');
 // fresh pipeline outputs under build/
 h+=sec('fresh','FRESH RUNS (build/)',lib.fresh.length);
 if(secOpen.fresh) h+=lib.fresh.map(f=>{
  const act=`<button class="pill act" onclick="enqueue('${esc(f.path)}','${esc(f.dir.replace('build/','')+'-'+f.name)}',event)">analyze ▶</button>`;
  return `<div class="row"><div class="nm">${esc(f.name)} ${act}</div>
    <div class="tsx">${esc(f.dir)} · ${ago(f.mtime)}</div></div>`;
 }).join('');
 // snapshot timeline (analyzed archive)
 h+=sec('snaps','SNAPSHOTS (analyzed)',boards.length);
 if(secOpen.snaps){
  if(!boards.length) h+='<div style="padding:12px;color:#607d8b">none yet — hit analyze ▶ on a board above</div>';
  h+=boards.map(b=>{
   const fg=(b.failing&&b.failing.length)?(' '+b.failing.join(',')):'';
   const badge=`<span class="pill ${b.verdict==='CLEAN'?'ok':'bad'}">${b.verdict}${b.verdict==='CLEAN'?'':esc(fg)}</span>`;
   const np=Object.keys(b.panels||{}).length;
   return `<div class="row ${cur&&cur.id===b.id?'sel':''}" onclick="pick('${b.id}')">
     <div class="nm">${esc(b.name)} ${badge}</div>
     <div class="tsx">${esc(b.ts_human||b.timestamp||'')} · ${np} panel${np===1?'':'s'}</div></div>`;
  }).join('');
 }
 el.innerHTML=h;
}
// ---- analyzer: gate badges + the two high-res panels --------------------------
function gbadge(label,ok,extra){const cl=ok===true?'ok':(ok===false?'bad':'dim');
 return `<span class="pill ${cl}">${label}${extra?(' '+extra):''}</span>`;}
function renderBadges(){
 const el=document.getElementById('badges');
 if(!cur){el.innerHTML='';return;}
 const g=cur.gates||{}, t=cur.thermal||{}, fp=g.foreign||{};
 if(!g.ok){el.innerHTML=`<span class="pill bad" title="${esc(g.error||'')}">gate-eval n/a</span>`+verdictPill();return;}
 const fclean=(fp.status==='na')||(fp.status==='ok'&&!fp.n_tracks&&!fp.n_vias);
 const fok=(fp.status==='na')?null:fclean;
 const fext=fp.status==='ok'?`${fp.n_tracks}T/${fp.n_vias}V`:(fp.status||'');
 let h=gbadge('kelvin',g.kelvin_ok)
  +gbadge('foreign-on-pour',fok,fext)
  +gbadge('drc',g.drc===0,String(g.drc))
  +gbadge('unconnected',g.unconnected===0,String(g.unconnected));
 if(t.ok) h+=`<span class="pill ${t.verdict==='PASS'?'ok':'bad'}" title="2.5D electro-thermal, grid ${t.grid_mm}mm, amb ${t.ambient}C, gate dT<=${30}C. cooling: ${esc(t.cooling||'')}">thermal ${t.verdict} · θmax ${t.max_T}°C dT ${t.dT}°C</span>`;
 else h+=`<span class="pill dim" title="${esc(t.error||'')}">thermal n/a</span>`;
 el.innerHTML=h+verdictPill();
}
function verdictPill(){return cur?(' '+vpill(cur.verdict)):'';}
const PANEL_LABEL={
 detail:'TEMPERATURE (°C) — smooth field + translucent stacked copper',
 current:'CURRENT cross-check (A) — heat should track current',
 render:'RENDER — raytraced top view',
 plotf:'PLOT — front copper (F.Cu + Edge.Cuts + silkscreen)',
 plotb:'PLOT — back copper (B.Cu + Edge.Cuts + silkscreen)'};
function buildPanels(){
 const st=document.getElementById('pstack'); st.style.width=plotW+'px'; st.innerHTML='';
 if(!cur){st.innerHTML='<div id="empty">no board selected</div>';return;}
 const have=cur.panels||{};
 const KNOWN=['detail','current','render','plotf','plotb'];
 const extras=Object.keys(have).filter(k=>!KNOWN.includes(k)).sort();
 // studies (worst-case solves etc.) are thermal panels: show them RIGHT UNDER the
 // temperature panel, not buried after the render/plots at the bottom of the stack
 const want = mode==='all'?['detail',...extras,'current','render','plotf','plotb']
            : mode==='plot'?['plotf','plotb']
            : mode==='detail'?['detail',...extras]
            : [mode];
 let any=false;
 for(const pn of want){
  if(!have[pn]) continue;
  any=true;
  const w=document.createElement('div'); w.className='panel'+(pn==='plotf'||pn==='plotb'?' plot':'');
  const im=document.createElement('img'); im.src=`/img?id=${encodeURIComponent(cur.id)}&panel=${pn}&v=${cur.epoch||0}`;
  const cap=document.createElement('div'); cap.className='cap';
  cap.textContent=PANEL_LABEL[pn]||('STUDY — '+pn.replace(/-/g,' '));
  w.appendChild(im); w.appendChild(cap); st.appendChild(w);
 }
 if(!any) st.innerHTML='<div id="empty">no panels of this kind for this board — older snapshots predate render/plot: hit analyze ▶ again from the library to regenerate</div>';
}
function setMode(m){mode=m;
 for(const x of ['all','detail','current','render','plot']) document.getElementById('m_'+x).classList.toggle('on',x===m);
 buildPanels();}
function pickAct(i){
 curAct=i; cur=null;
 const a=acts[i]||{};
 // state keys to the IMAGE (poll reorders indices); the toggle is a PERMANENT header
 // element -- async-appended buttons were wiped by every re-render/poll ('ephemeral
 // buttons', owner bug report). Probes only flip its visibility.
 if(a.image!==actImg){actBodies=false;actTwin=null;actImg=a.image;}
 document.getElementById('btitle').textContent=`[${a.tag}] ${a.title}`;
 document.getElementById('badges').innerHTML=
  `<span class="pill dim">${ago(a.ts)}</span>`+
  `<button id="tgl3d" class="pill" style="cursor:pointer;margin-left:8px;display:${actTwin?'inline-block':'none'}">${actBodies?'copper view':'3D bodies'}</button>`;
 document.getElementById('tgl3d').onclick=()=>{
  actBodies=!actBodies;
  const el=document.getElementById('actimg');
  if(el&&actTwin) el.src=`/artifact?p=${encodeURIComponent(actBodies?actTwin:actImg)}`;
  document.getElementById('tgl3d').textContent=actBodies?'copper view':'3D bodies';};
 const st=document.getElementById('pstack');
 st.style.width=plotW+'px';
 if(a.image){
  st.innerHTML='';
  const w=document.createElement('div'); w.className='panel';
  const im=document.createElement('img'); im.src=`/artifact?p=${encodeURIComponent(actBodies&&actTwin?actTwin:a.image)}`;
  im.id='actimg';
  const cap=document.createElement('div'); cap.className='cap'; cap.textContent=a.title;
  w.appendChild(im); w.appendChild(cap); st.appendChild(w);
  if(!actTwin&&(a.image.includes('-top.png')||a.image.includes('-bottom.png'))){
   const tw=a.image.replace('-top.png','-top-bodies.png').replace('-bottom.png','-bottom-bodies.png');
   fetch(`/artifact?p=${encodeURIComponent(tw)}`,{method:'HEAD'}).then(r=>{
    if(!r.ok||a.image!==actImg) return;
    actTwin=tw;
    const b3=document.getElementById('tgl3d');
    if(b3) b3.style.display='inline-block';
   }).catch(()=>{});
  }
 }else{
  st.innerHTML=`<div id="empty" style="text-align:left;max-width:900px;white-space:pre-wrap">${esc(a.title)}\n\n${esc(a.detail||'(no artifact attached — this event is a text milestone; commits carry their diff in git)')}</div>`;
 }
 renderList();
}
function pick(id){
 curAct=null;
 cur=boards.find(b=>b.id===id)||null;
 document.getElementById('btitle').textContent=cur?(cur.name+'  ·  '+(cur.source||'')):'select a board';
 renderList(); renderBadges(); fit();
}
function rerender(){ if(cur){buildPanels();} else if(curAct!==null){pickAct(curAct);} }
function fit(){plotW=document.getElementById('pwrap').clientWidth-4; rerender();}
function zoom(f){plotW=Math.min(24000,Math.max(200,plotW*f)); rerender();}
// wheel-zoom anchored at cursor + drag-pan (the reused high-res viewing frame)
window.addEventListener('DOMContentLoaded',()=>{
 const pw=document.getElementById('pwrap');
 pw.addEventListener('wheel',e=>{e.preventDefault();
  const f=e.deltaY<0?1.25:0.8, nw=Math.min(24000,Math.max(200,plotW*f)), r=pw.getBoundingClientRect();
  const fx=(pw.scrollLeft+e.clientX-r.left)/plotW, fy=(pw.scrollTop+e.clientY-r.top)/plotW;
  plotW=nw; rerender();
  pw.scrollLeft=fx*plotW-(e.clientX-r.left); pw.scrollTop=fy*plotW-(e.clientY-r.top);},{passive:false});
 let pan=null;
 pw.addEventListener('mousedown',e=>{pan={x:e.clientX,y:e.clientY,l:pw.scrollLeft,t:pw.scrollTop};pw.style.cursor='grabbing';e.preventDefault();});
 window.addEventListener('mousemove',e=>{if(pan){pw.scrollLeft=pan.l-(e.clientX-pan.x);pw.scrollTop=pan.t-(e.clientY-pan.y);}});
 window.addEventListener('mouseup',()=>{pan=null;pw.style.cursor='grab';});
 setMode('all'); tick(); setInterval(tick,3000);
});
async function tick(){
 try{
  const s=await (await fetch('/api/archive')).json();
  if(s.rev && PAGE_REV!=='__'+'REV__' && s.rev!==PAGE_REV){location.reload();return;}
  boards=s.boards||[];
  try{ lib=await (await fetch('/api/library')).json(); }catch(e){}
  try{ acts=((await (await fetch('/api/worklog')).json()).events)||[]; }catch(e){}
  const sd=s.seeding||{};
  let msg=`${(lib.beta||[]).length} beta · ${(lib.fresh||[]).length} fresh · ${boards.length} analyzed`;
  if(sd.active) msg+=`  ·  <span style="color:#ffcc80">archiving ${esc(sd.active)}…</span>`;
  if(sd.pending) msg+=`  ·  ${sd.pending} queued`;
  if((lib.watch||{}).last_scan) msg+=`  ·  watch ${esc(lib.watch.last_scan)}`;
  if((sd.errors||[]).length) msg+=`  ·  <span style="color:#ef9a9a">${sd.errors.length} err</span>`;
  document.getElementById('seed').innerHTML=msg;
  if(cur){ const u=boards.find(b=>b.id===cur.id); if(u){const e0=cur.epoch; cur=u; if(u.epoch!==e0){renderBadges();buildPanels();}} }
  else renderBadges();
  renderList();
 }catch(e){document.getElementById('seed').textContent='dashboard error: '+e;}
}
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="CEC board browser + high-res analyzer")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--seed", action="store_true", help="archive the key boards (eps + PCIe-2/3) on start")
    ap.add_argument("--no-watch", action="store_true",
                    help="disable the build/fresh/** auto-archive watcher")
    ap.add_argument("--archive", default=None, help="archive ONE board (path) then keep serving")
    ap.add_argument("--name", default=None, help="name for --archive (default: derived from the path)")
    # ---- in-container analysis mode (internal; run INSIDE the routing container) ----
    ap.add_argument("--analyze-board", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--board", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--detail", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--current", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--render", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--plotf", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--plotb", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--width", type=int, default=PANEL_W, help=argparse.SUPPRESS)
    a = ap.parse_args()

    if a.analyze_board:                                            # container half: solve, panels, render, plots, gates
        _analyze_in_container(a.board, a.detail, a.current, a.width,
                              render_png=a.render, plotf_svg=a.plotf, plotb_svg=a.plotb)
        return

    os.makedirs(ARCHIVE_ROOT, exist_ok=True)
    _load_archive()
    threading.Thread(target=_archive_worker, daemon=True).start()
    if not a.no_watch:
        # pre-mark existing watch matches as seen so a restart doesn't re-archive history;
        # only boards that CHANGE (or appear) after launch auto-enqueue.
        for pat in WATCH_GLOBS:
            for p in glob.glob(os.path.join(ROOT, pat), recursive=True):
                try:
                    _watch_seen[p] = os.path.getmtime(p)
                except OSError:
                    pass
        threading.Thread(target=_watcher, daemon=True).start()
    if a.archive:
        _jobs.put((os.path.abspath(a.archive), a.name or _slug(os.path.splitext(os.path.basename(a.archive))[0])))
    if a.seed:
        _enqueue_seed()
    with _archive_lock:
        n = len(_archive)
    print(f"dashboard: http://localhost:{a.port}  (archive={os.path.relpath(ARCHIVE_ROOT, ROOT)}, "
          f"{n} board(s), queued={_jobs.qsize()})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
