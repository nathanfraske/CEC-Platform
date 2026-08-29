#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_dashboard -- BOARD BROWSER + high-res ANALYZER.
# ============================================================================
# Owner directive (2026-06-30): the dashboard is ONE thing done well -- a full
# high-res board browser + analyzer. No live-run auto-tracking and no
# agentic/seat/convergence panels. Just:
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
# Architecture: a plain stdlib http.server on the HOST. Heavy work normally
# runs in the routing container (pcbnew + cupy/GPU), but a clean WSL install
# with the native KiCad/Python toolchain must not require a second copy of that
# toolchain in Docker merely to view a board.  The analyzer therefore falls
# back to the native host when Docker access is unavailable.  This same file
# runs the analysis half in either backend: `cec_dashboard.py --analyze-board
# ...` does one 2.5D solve, draws both panels, evaluates the gates, and prints a
# JSON summary.
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
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, unquote
from xml.sax.saxutils import escape as _xml_escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPOSE_FILE = os.path.join(ROOT, "docker", "compose.yaml")
ARCHIVE_ROOT = os.path.join(ROOT, "build", "board-archive")
ARCHIVE_BOARD_SIDECARS = (
    ".kicad_pro", ".kicad_dru", ".kicad_prl",
    ".pourplan.json", ".railreport.json", ".pourfirst-state.json",
)

# ---- the owner-validated solve recipe (KEEP/REUSE) --------------------------
SOLVE = {"ambient": 50.0, "grid_mm": 0.2, "h_eff": 15.0}   # board_thermal_config -> _prepare_filled -> solve
PANEL_W = 1400                # final_board_w; total PNG >= ~1772px (board + 372px legend) -> the >=1600px ask
GATE_DT = 30.0               # dT-over-ambient PASS gate
THERMAL_GEOMETRY_SOURCE = "source-declared-copper-only:v1"
WX_NOISE = re.compile(r"duplicate image handler|Debug:|Xvfb|wxWidgets")

# Full six-layer stack, in physical order. The wave renderer and archive analyzer
# must both expose In3/In4 added during the six-layer migration; showing only the
# historical F/B/In1/In2 subset makes projected crossings impossible to audit.
COPPER_PLOTS = (
    ("plotf", "plot-f.svg", "F.Cu,Edge.Cuts,F.Silkscreen"),
    ("plot1", "plot-in1.svg", "In1.Cu,Edge.Cuts"),
    ("plot2", "plot-in2.svg", "In2.Cu,Edge.Cuts"),
    ("plot3", "plot-in3.svg", "In3.Cu,Edge.Cuts"),
    ("plot4", "plot-in4.svg", "In4.Cu,Edge.Cuts"),
    ("plotb", "plot-b.svg", "B.Cu,Edge.Cuts,B.Silkscreen"),
)


def _copper_plot_command(board, svg, layers, panel):
    """Build one layer-plot command in the face orientation a reviewer expects.

    KiCad's unmirrored B.Cu export is expressed in top-side board coordinates.
    That is correct manufacturing geometry, but it makes bottom silkscreen and
    copper lettering look backwards in the dashboard.  Mirror only the back
    panel so it represents looking directly at the physical underside; do not
    mutate board copper or mirror internal engineering layers.
    """
    cmd = ["kicad-cli", "pcb", "export", "svg", "--mode-single", "-o", svg,
           "--layers", layers, "--page-size-mode", "2",
           "--exclude-drawing-sheet"]
    if panel == "plotb":
        cmd.append("--mirror")
    cmd.append(board)
    return cmd


_ISSUE_NET_RE = re.compile(r"\[([^\]]+)\]")
_ISSUE_REF_RE = re.compile(r"\bof\s+([^\s,;]+)")


def _issue_tokens(violations):
    """Extract net names, component references, UUIDs, and loci from DRC rows."""
    nets, refs, uuids, positions = set(), set(), set(), []
    for violation in violations or ():
        for item in violation.get("items") or ():
            description = str(item.get("description") or "")
            nets.update(_ISSUE_NET_RE.findall(description))
            refs.update(_ISSUE_REF_RE.findall(description))
            if item.get("uuid"):
                uuids.add(str(item["uuid"]))
            pos = item.get("pos") or {}
            try:
                positions.append((float(pos["x"]), float(pos["y"]),
                                  description))
            except (KeyError, TypeError, ValueError):
                pass
    return {"nets": nets, "refs": refs, "uuids": uuids,
            "positions": positions}


def _structural_issue_rows(drc_data, board):
    """Return the same qualified structural DRC rows used by ``cec_score``.

    The issue overlay is a view of release evidence, not an independent DRC
    authority.  Keep every profile-qualified geometry exception in lockstep
    with the scorer so the dashboard cannot display a different blocker count
    for the exact same board/report pair.
    """
    import cec_score

    structural = [v for v in (drc_data.get("violations") or ())
                  if v.get("type") not in cec_score.COSMETIC_DRC_TYPES]
    structural = cec_score._drop_impossible_pad_artifacts(structural, board)
    structural = cec_score._drop_profile_qualified_pofv_geometry(
        structural, board)
    return cec_score._drop_qualified_endpoint_neckdown_geometry(
        structural, board)


def _write_issue_overlay(board_path, svg_path, drc_data, metrics=None):
    """Write an evidence-backed board issue map and return its compact summary.

    The map uses the same cosmetic/parity filtering as :mod:`cec_score`.  Whole
    affected nets are shown faintly for context, while the exact UUID-bearing
    items and reported loci are emphasized.  This prevents a large GND net from
    hiding the actual broken branch yet still lets a reviewer follow ownership.
    """
    import pcbnew

    board = pcbnew.LoadBoard(board_path)
    structural = _structural_issue_rows(drc_data, board)
    unconnected = list(drc_data.get("unconnected_items") or ())
    drc = _issue_tokens(structural)
    unc = _issue_tokens(unconnected)
    topology = ((getattr(metrics, "detail", {}) or {}).get("route_quality")
                if metrics is not None else None)
    if topology is None:
        import cec_route_quality
        topology = cec_route_quality.analyze_board(board)
    topology_issues = list(topology.get("issues") or ())
    topology_nets = {row.get("net") for row in topology_issues if row.get("net")}
    topology_uuids = {uuid for row in topology_issues
                      for uuid in (row.get("track_uuids") or ())}
    topology_positions = [
        (float(row["at_mm"][0]), float(row["at_mm"][1]), row.get("message", ""))
        for row in topology_issues if len(row.get("at_mm") or ()) == 2]
    # One exact DRC authority feeds both the visible overlay and the durable
    # blocker ledger.  The ledger intentionally starts with origin_known=False:
    # a final KiCad error proves the bad geometry, not which earlier pass made
    # it.  Wave stage events can later attribute generated UUIDs or associate
    # upstream net/ref evidence without inventing a causal story.
    import cec_blocker_provenance
    blockers = cec_blocker_provenance.final_blockers(
        {"violations": structural, "unconnected_items": unconnected},
        topology=topology)
    blocker_summary = cec_blocker_provenance.compact_summary(blockers)

    # Resolve implicated references from pad UUIDs as well as descriptions.
    pad_refs = {}
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            pad_refs[pad.m_Uuid.AsString()] = footprint.GetReference()
    drc["refs"].update(pad_refs[u] for u in drc["uuids"] if u in pad_refs)
    unc["refs"].update(pad_refs[u] for u in unc["uuids"] if u in pad_refs)
    problem_refs = drc["refs"] | unc["refs"]

    edges = board.GetBoardEdgesBoundingBox()
    x0, y0 = edges.GetX() / 1e6, edges.GetY() / 1e6
    width, height = edges.GetWidth() / 1e6, edges.GetHeight() / 1e6
    if width <= 0 or height <= 0:
        bbox = board.GetBoundingBox()
        x0, y0 = bbox.GetX() / 1e6, bbox.GetY() / 1e6
        width, height = bbox.GetWidth() / 1e6, bbox.GetHeight() / 1e6
    margin, legend_h = 3.0, 10.0
    vx, vy = x0 - margin, y0 - margin - legend_h
    vw, vh = width + 2 * margin, height + 2 * margin + legend_h

    red, amber, cyan, magenta = "#ff453a", "#ffb020", "#00d4ff", "#d946ef"
    context, board_bg = "#78909c", "#0b1115"
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (f'<svg xmlns="http://www.w3.org/2000/svg" '
         f'viewBox="{vx:.3f} {vy:.3f} {vw:.3f} {vh:.3f}">'),
        f'<rect x="{vx:.3f}" y="{vy:.3f}" width="{vw:.3f}" '
        f'height="{vh:.3f}" fill="{board_bg}"/>',
        f'<rect x="{x0:.3f}" y="{y0:.3f}" width="{width:.3f}" '
        f'height="{height:.3f}" fill="#10251f" stroke="{context}" '
        'stroke-width="0.18"/>',
    ]

    # Quiet component context first; implicated parts are redrawn prominently.
    footprint_by_ref = {}
    for footprint in board.GetFootprints():
        ref = footprint.GetReference()
        footprint_by_ref[ref] = footprint
        box = footprint.GetBoundingBox()
        lines.append(
            f'<rect x="{box.GetX()/1e6:.3f}" y="{box.GetY()/1e6:.3f}" '
            f'width="{box.GetWidth()/1e6:.3f}" height="{box.GetHeight()/1e6:.3f}" '
            f'fill="none" stroke="{context}" stroke-opacity="0.22" '
            'stroke-width="0.10"/>')

    # Faint whole-net context plus strong exact item geometry.
    all_problem_nets = drc["nets"] | unc["nets"] | topology_nets
    for track in board.GetTracks():
        net = track.GetNetname()
        if net not in all_problem_nets:
            continue
        uuid = track.m_Uuid.AsString()
        color = (cyan if uuid in topology_uuids
                 else red if net in drc["nets"] else amber)
        exact = (uuid in drc["uuids"] or uuid in unc["uuids"]
                 or uuid in topology_uuids)
        opacity = 0.96 if exact else 0.22
        if track.GetClass() == "PCB_VIA":
            pos = track.GetPosition()
            radius = max(0.22, track.GetWidth(track.TopLayer()) / 2e6)
            lines.append(
                f'<circle cx="{pos.x/1e6:.3f}" cy="{pos.y/1e6:.3f}" '
                f'r="{radius:.3f}" fill="none" stroke="{color}" '
                f'stroke-opacity="{opacity:.2f}" stroke-width="0.24"><title>'
                f'{_xml_escape(net)}</title></circle>')
        else:
            a, b = track.GetStart(), track.GetEnd()
            stroke = max(0.30, track.GetWidth() / 1e6 + (0.22 if exact else 0.0))
            lines.append(
                f'<line x1="{a.x/1e6:.3f}" y1="{a.y/1e6:.3f}" '
                f'x2="{b.x/1e6:.3f}" y2="{b.y/1e6:.3f}" '
                f'stroke="{color}" stroke-opacity="{opacity:.2f}" '
                f'stroke-width="{stroke:.3f}" stroke-linecap="round"><title>'
                f'{_xml_escape(net)}</title></line>')

    for ref in sorted(problem_refs):
        footprint = footprint_by_ref.get(ref)
        if footprint is None:
            continue
        box = footprint.GetBoundingBox()
        pad = 0.35
        lines.append(
            f'<rect x="{box.GetX()/1e6-pad:.3f}" y="{box.GetY()/1e6-pad:.3f}" '
            f'width="{box.GetWidth()/1e6+2*pad:.3f}" '
            f'height="{box.GetHeight()/1e6+2*pad:.3f}" fill="none" '
            f'stroke="{magenta}" stroke-width="0.32" stroke-dasharray="0.8 0.35">'
            f'<title>{_xml_escape(ref)}</title></rect>')

    def loci(rows, color):
        for x, y, description in rows:
            title = _xml_escape(description)
            lines.append(
                f'<circle cx="{x:.3f}" cy="{y:.3f}" r="0.52" fill="none" '
                f'stroke="{color}" stroke-width="0.24"><title>{title}</title></circle>')
            lines.append(
                f'<path d="M {x-0.36:.3f} {y:.3f} H {x+0.36:.3f} '
                f'M {x:.3f} {y-0.36:.3f} V {y+0.36:.3f}" '
                f'stroke="{color}" stroke-width="0.18"/>')

    loci(drc["positions"], red)
    loci(unc["positions"], amber)
    loci(topology_positions, cyan)

    lx, ly = x0, y0 - margin - legend_h + 2.0
    lines.extend([
        f'<text x="{lx:.3f}" y="{ly:.3f}" fill="#e8f1f5" '
        'font-family="monospace" font-size="1.55" font-weight="bold">ISSUE MAP</text>',
        f'<line x1="{lx:.3f}" y1="{ly+2.2:.3f}" x2="{lx+3.0:.3f}" '
        f'y2="{ly+2.2:.3f}" stroke="{red}" stroke-width="0.65"/>',
        f'<text x="{lx+3.7:.3f}" y="{ly+2.65:.3f}" fill="#e8f1f5" '
        f'font-family="monospace" font-size="1.15">structural DRC ({len(structural)})</text>',
        f'<line x1="{lx+24:.3f}" y1="{ly+2.2:.3f}" x2="{lx+27:.3f}" '
        f'y2="{ly+2.2:.3f}" stroke="{amber}" stroke-width="0.65"/>',
        f'<text x="{lx+27.7:.3f}" y="{ly+2.65:.3f}" fill="#e8f1f5" '
        f'font-family="monospace" font-size="1.15">unconnected ({len(unconnected)})</text>',
        f'<rect x="{lx:.3f}" y="{ly+4.2:.3f}" width="3" height="1.35" '
        f'fill="none" stroke="{magenta}" stroke-width="0.28" stroke-dasharray="0.6 0.3"/>',
        f'<text x="{lx+3.7:.3f}" y="{ly+5.35:.3f}" fill="#e8f1f5" '
        f'font-family="monospace" font-size="1.15">implicated component ({len(problem_refs)})</text>',
        f'<line x1="{lx+24:.3f}" y1="{ly+4.9:.3f}" x2="{lx+27:.3f}" '
        f'y2="{ly+4.9:.3f}" stroke="{cyan}" stroke-width="0.65"/>',
        f'<text x="{lx+27.7:.3f}" y="{ly+5.35:.3f}" fill="#e8f1f5" '
        f'font-family="monospace" font-size="1.15">route topology ({len(topology_issues)})</text>',
    ])
    if not structural and not unconnected and not topology_issues:
        lines.append(
            f'<text x="{lx+24:.3f}" y="{ly+5.35:.3f}" fill="#63d391" '
            'font-family="monospace" font-size="1.15">no accepted issue evidence</text>')
    lines.append('</svg>')
    with open(svg_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    return {
        "ok": True, "structural_drc": len(structural),
        "unconnected": len(unconnected),
        "drc_nets": sorted(drc["nets"]),
        "unconnected_nets": sorted(unc["nets"]),
        "route_topology": len(topology_issues),
        "route_topology_nets": sorted(topology_nets),
        "components": sorted(problem_refs),
        "blockers": blockers,
        "blocker_summary": blocker_summary,
        "legend": {"structural_drc": red, "unconnected": amber,
                   "route_topology": cyan, "component": magenta},
    }

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
_archive_disk_signature = None
_archive_sync_status = {"last_scan": None, "last_change": None, "errors": []}
ARCHIVE_SCAN_SECONDS = 1.0
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
               "build/fresh-wave-loop/**/*.kicad_pcb",
               # The router overwrites exactly one scored progress board per
               # iteration. Unlike worker fanout, this is small and already
               # ranked, so it belongs in the analyzed wave timeline.
               "build/hub-closure-wave*/route-cand*/*-progress.kicad_pcb"] + [
    g.strip() for g in os.environ.get("CEC_DASH_WATCH", "").split(",") if g.strip()]
_watch_seen = {}              # path -> mtime already enqueued
_watch_status = {"globs": list(WATCH_GLOBS), "enqueued": 0, "last_scan": None}


def _beta_boards():
    """The committed current BETA line, from the authoritative manifest only.

    Marker/glob discovery previously omitted the current EPS and Hub whenever a
    directory lacked a BETA marker, while also making it too easy for archived
    lineages to reappear.  The dashboard must show the same ten products as the
    electrical and routing pipelines.
    """
    import cec_beta_manifest as manifest

    out = []
    for project in manifest.PROJECTS:
        d = os.path.join(ROOT, "beta", project["directory"])
        schematic = os.path.join(d, project["schematic"])
        pcb = os.path.join(d, project["pcb"]) if project.get("pcb") else None
        if pcb and not os.path.isfile(pcb):
            pcb = None
        out.append({"name": project["board"], "dir": os.path.relpath(d, ROOT),
                    "pcb": os.path.relpath(pcb, ROOT) if pcb else None,
                    "mtime": os.path.getmtime(pcb) if pcb else None,
                    "draft": os.path.exists(os.path.join(d, "DRAFT")),
                    "sch": os.path.isfile(schematic),
                    "wave": bool(project.get("wave"))})
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


def _thermal_board_hint(path):
    """Recover the manifest board identity before an archive renames it board.*."""
    normalized = str(path).replace("\\", "/").lower()
    daughterboard_aliases = (
        ("output-daughterboards/atx24-out-db/", "atx24-out-db"),
        ("output-daughterboards/eps-out-db/", "eps-out-db"),
        ("output-daughterboards/pcie-out-db/", "pcie-out-db"),
    )
    for marker, board in daughterboard_aliases:
        if marker in normalized:
            return board
    try:
        import cec_beta_manifest as manifest
        for board in sorted(manifest.CURRENT_BETA_BOARDS, key=len, reverse=True):
            if board.lower() in normalized:
                return board
        # Review exports and compact/wave artifacts often retain only a family
        # prefix, not the full manifest slug. Keep aliases explicit and narrow;
        # the exact manifest match above always wins (including daughterboards).
        filename = os.path.basename(normalized)
        aliases = (
            (("12vhpwr", "12v2x6"), "12vhpwr-standard"),
            (("atx-", "atx24-"), "atx-24pin-rev3"),
            (("hub-",), "hub-standard-rev2"),
            (("eps-",), "eps-8pin-rev3"),
        )
        for prefixes, board in aliases:
            if filename.startswith(prefixes):
                return board
    except Exception:                                      # noqa: BLE001 -- optional hint
        pass
    return None


def _thermal_injection_report(result):
    """Summarize whether every configured current path actually injected."""
    requested = dict(getattr(result, "nets_requested", None) or {})
    dropped = dict(getattr(result, "nets_dropped", None) or {})
    absent = dict(getattr(result, "nets_absent", None) or {})
    omitted = sorted(set(dropped) | set(absent))
    return {"nets_requested": len(requested),
            "nets_injected": len(requested) - len(dropped) - len(absent),
            "nets_dropped": {name: dropped[name] for name in sorted(dropped)},
            "nets_absent": sorted(absent),
            "omitted": omitted}


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
def _gate_issue_analysis(board, issues_svg=None):
    """Score and render issue evidence in a fresh KiCad interpreter.

    KiCad's SWIG registries are process-global.  A long thermal/FEM analysis
    loads and traverses the same board deeply enough that a later DRC/score pass
    can fail nondeterministically (the measured dashboard failure was an ASCII
    decode in a board containing the ohm symbol).  Gate badges and their issue
    map are acceptance evidence, so give them an isolated process and one DRC
    JSON authority rather than letting FEM state contaminate them.
    """
    import sys
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    out = {"gates": {"ok": False, "error": "not run"},
           "issues": {"ok": False, "error": "not requested"}}
    try:
        import cec_score
        import cec_pour_clearance
        import cec_synth_pipeline
        fd, drc_path = tempfile.mkstemp(
            prefix="cec_dash_drc_", suffix=".json")
        os.close(fd)
        try:
            drc_data = cec_score._run_drc(board, drc_path)
            m = cec_score.score(board, drc_json=drc_path)
            if issues_svg:
                try:
                    out["issues"] = _write_issue_overlay(
                        board, issues_svg, drc_data, metrics=m)
                except Exception as issue_error:              # noqa: BLE001
                    out["issues"] = {
                        "ok": False,
                        "error": (f"{type(issue_error).__name__}: "
                                  f"{issue_error}")}
        finally:
            try:
                os.unlink(drc_path)
            except OSError:
                pass
        # Keep the two authorities visibly separate.  The derived corridor is
        # a conservative placement/routing reservation; the laid outline is
        # copper that will actually exist in Gerbers and is the release badge.
        # Combining them recreated the phantom FEM slabs that are not present
        # on the routed board.
        fp = cec_pour_clearance.inspect_file(board)
        laid = dict(fp.get("laid") or {})
        reserved = dict(fp.get("derived") or {})
        try:
            route_sanity = cec_synth_pipeline._oracle_route_sanity(board)
        except Exception as route_error:                       # noqa: BLE001
            route_sanity = {
                "ok": False,
                "error": f"{type(route_error).__name__}: {route_error}"}
        out["gates"] = {
            "ok": True,
            "kelvin_ok": bool(m.kelvin_ok),
            "diffpair_ok": bool(m.diffpair_ok),
            "drc": int(m.drc),
            "unconnected": int(m.unconnected),
            "gates_pass": bool(m.gates_pass),
            "route_sanity": route_sanity,
            "foreign": {
                "authority": "actual_laid_pour",
                "status": laid.get("status"),
                "applicable": laid.get("applicable"),
                "n_parts": int(laid.get("n_parts") or 0),
                "n_tracks": int(laid.get("n_tracks") or 0),
                "n_vias": int(laid.get("n_vias") or 0),
            },
            "reserved_corridor": {
                "authority": "planning_advisory",
                "status": reserved.get("status"),
                "applicable": reserved.get("applicable"),
                "n_tracks": int(reserved.get("n_tracks") or 0),
                "n_vias": int(reserved.get("n_vias") or 0),
            },
        }
    except Exception as error:                                # noqa: BLE001
        out["gates"] = {
            "ok": False, "error": f"{type(error).__name__}: {error}"}
    return out


def _analyze_in_container(board, detail_png, current_png, width,
                          bottlenecks_png=None,
                          render_png=None, plotf_svg=None, plot1_svg=None,
                          plot2_svg=None, plot3_svg=None, plot4_svg=None,
                          plotb_svg=None, issues_svg=None):
    """Solve the 2.5D field ONCE (board_thermal_config -> _prepare_filled -> solve at the SOLVE recipe),
    draw the TEMPERATURE panel + the CURRENT cross-check panel from that one field, evaluate the
    gates, and (owner ask 2026-07-07) export the raytraced top RENDER + the front/back copper
    PLOTS. Print one JSON line {thermal, gates}; every part is degrade-safe (a failed render
    still yields gates and panels, and vice-versa). Runs in the container only."""
    import sys
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    out = {"ok": True, "thermal": {"ok": False, "error": "not run"},
           "gates": {"ok": False, "error": "not run"},
           "issues": {"ok": False, "error": "not run"}}

    # ---- render + copper plots (kicad-cli; independent of the solve) ----
    if render_png:
        try:
            import cec_render
            cec_render.render(board, render_png, side="top", timeout=300)  # silk stripped
        except Exception:                                           # noqa: BLE001
            pass
    plot_paths = {"plotf": plotf_svg, "plot1": plot1_svg, "plot2": plot2_svg,
                  "plot3": plot3_svg, "plot4": plot4_svg, "plotb": plotb_svg}
    for panel, _filename, layers in COPPER_PLOTS:
        svg = plot_paths[panel]
        if not svg:
            continue
        try:
            cmd = _copper_plot_command(board, svg, layers, panel)
            subprocess.run(cmd, capture_output=True, timeout=300)
        except Exception:                                           # noqa: BLE001
            pass

    # ---- thermal solve + the two blended detail panels (reuse cec_thermal_overlay) ----
    try:
        import cec_thermal_overlay as ov
        # BUDGETED + COARSEN-RETRY (2026-07-23, the archive-analyzer pathology:
        # fine-grid per-net CG spun 2.5 cores for 2-4.5h on fat-copper boards
        # -- faulthandler-traced). Fine grid gets a hard wall-clock budget; a
        # PARTIAL result (budget-skipped nets) retries once at the waves'
        # proven 0.8mm grid with its own budget. Never camp a core for hours.
        res, fpath, cool = ov._solve_thermal(
            board, ambient=SOLVE["ambient"], grid_mm=SOLVE["grid_mm"],
            h_eff=SOLVE["h_eff"], time_budget_s=180.0)
        if any("time budget" in str(v)
               for v in (getattr(res, "nets_dropped", None) or {}).values()):
            print("[dash] fine-grid thermal hit its budget -- retrying at 0.8mm",
                  file=sys.stderr)
            res, fpath, cool = ov._solve_thermal(
                board, ambient=SOLVE["ambient"], grid_mm=0.8,
                h_eff=SOLVE["h_eff"], time_budget_s=300.0)
        ov._draw_detail_blend(fpath, res, detail_png, mode="thermal", cool_label=cool,
                              gate_dt=GATE_DT, final_board_w=width, title=os.path.basename(board))
        ov._draw_detail_blend(fpath, res, current_png, mode="current", cool_label=cool,
                              gate_dt=GATE_DT, final_board_w=width, title=os.path.basename(board))
        bottleneck_error = None
        if bottlenecks_png:
            try:
                ov.draw_current_density_diagnostic(
                    res, bottlenecks_png, title=os.path.basename(board))
            except Exception as error:                         # noqa: BLE001
                bottleneck_error = f"{type(error).__name__}: {error}"
        dt = res.max_T - res.ambient
        injection = _thermal_injection_report(res)
        thermal = {"ok": True, "max_T": round(res.max_T, 2), "ambient": res.ambient,
                   "dT": round(dt, 2), "verdict": "PASS" if dt <= GATE_DT else "FAIL",
                   "cooling": cool, "grid_mm": res.grid_mm,
                   "geometry_source": res.meta.get("geometry_source"),
                   "source_geometry_sha256": res.meta.get("source_geometry_sha256"),
                   "analysis_geometry_sha256": res.meta.get("analysis_geometry_sha256"),
                   "geometry_counts": res.meta.get("geometry_counts"),
                   "nets_requested": injection["nets_requested"],
                   "nets_injected": injection["nets_injected"],
                   "max_current_density_A_per_mm2": {
                       net: round(value, 3)
                       for net, value in res.per_net_maxJ.items()},
                   "top_current_bottlenecks": res.current_bottlenecks[:24],
                   "current_density_error": bottleneck_error,
                   "detail": os.path.basename(detail_png),
                   "current": os.path.basename(current_png),
                   "current_density": (
                       os.path.basename(bottlenecks_png)
                       if bottlenecks_png else None)}
        if not injection["nets_requested"]:
            thermal.update({"ok": False, "verdict": "N/A",
                            "error": "no configured current-injection scenario for this board"})
        elif injection["omitted"]:
            thermal.update({"verdict": "FAIL",
                            "nets_dropped": injection["nets_dropped"],
                            "nets_absent": injection["nets_absent"],
                            "error": "INJECTION INCOMPLETE: configured net(s) injected no current: "
                                     + ", ".join(injection["omitted"])})
        elif dt <= 0.05:
            thermal.update({"verdict": "FAIL",
                            "error": "solver returned dT~0 for a powered board"})
        out["thermal"] = thermal
    except Exception as e:                                          # noqa: BLE001
        out["thermal"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        if type(e).__name__ == "ThermalGeometryError":
            out["thermal"].update({"verdict": "FAIL", "geometry_source": "INVALID"})

    # ---- gates + issue map in a clean process ----------------------------
    # Thermal/FEM and pcbnew scoring cannot safely share one long-lived SWIG
    # registry.  The child also pins UTF-8 for stdout so a valid non-ASCII net,
    # value, or reference can never erase the dashboard evidence in transit.
    try:
        cmd = [sys.executable, os.path.abspath(__file__),
               "--analyze-gates", "--board", board]
        if issues_svg:
            cmd.extend(["--issues", issues_svg])
        gate_cp = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=300)
        gate_result = _parse_last_json(gate_cp.stdout)
        if not gate_result:
            raise RuntimeError((gate_cp.stderr or gate_cp.stdout or
                                "gate worker produced no JSON")[-500:])
        out["gates"] = gate_result.get("gates", out["gates"])
        out["issues"] = gate_result.get("issues", out["issues"])
    except Exception as error:                                    # noqa: BLE001
        out["gates"] = {
            "ok": False, "error": f"{type(error).__name__}: {error}"}

    print(json.dumps(out))                                         # LAST line = the parseable summary


# ============================================================================
#  HOST half -- container exec, archiving, browser/analyzer server.
# ============================================================================
def _native_analysis_argv(argv):
    """Translate container `/workspace/...` arguments to this checkout."""
    prefix = "/workspace/"
    return [os.path.join(ROOT, arg[len(prefix):]) if arg.startswith(prefix) else arg
            for arg in argv]


def _docker_analysis_available():
    """True only when this user can actually invoke the routing container."""
    if not shutil.which("docker") or not os.path.isfile(COMPOSE_FILE):
        return False
    try:
        groups = subprocess.run(["id", "-nG"], capture_output=True, text=True,
                                timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return groups.returncode == 0 and "docker" in groups.stdout.split()


def _container_run(argv, timeout, env=None):
    """Run the analyzer in Docker when available, otherwise in native WSL.

    The native path is deliberate clean-machine support: it avoids a large,
    duplicate Docker image when KiCad, pcbnew, and the compute dependencies are
    already installed in WSL.  `env` has identical semantics in both backends.
    """
    if not _docker_analysis_available():
        host_env = os.environ.copy()
        host_env.update({str(k): str(v) for k, v in (env or {}).items()})
        return subprocess.run(_native_analysis_argv(argv), cwd=ROOT, env=host_env,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=timeout)

    prefix = "".join(f"{k}={shlex.quote(str(v))} " for k, v in (env or {}).items())
    inner = "cd /workspace && " + prefix + " ".join(shlex.quote(a) for a in argv)
    compose = (f"docker compose -f {shlex.quote(COMPOSE_FILE)} exec -T routing "
               f"bash -lc {shlex.quote(inner)}")
    return subprocess.run(["sg", "docker", "-c", compose],
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          timeout=timeout)


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
    geometry_source = thermal.get("geometry_source")
    if geometry_source == "INVALID" or (
            thermal.get("ok") and geometry_source != THERMAL_GEOMETRY_SOURCE):
        failing.append("thermal-geometry")
    elif thermal.get("ok") and thermal.get("verdict") == "FAIL":
        failing.append("thermal")
    return ("CLEAN" if not failing else "FAILED"), failing


def archive_board(pcb_path, name, provenance_path=None):
    """Snapshot ONE board into its own timestamped archive dir, render its two analysis panels, evaluate
    its gates, and write summary.json. Returns the summary dict (also appended to the live _archive).

    Layout:  build/board-archive/<YYYYmmddTHHMM>-<name>/
               board.kicad_pcb   (+ .kicad_pro/.kicad_dru/.kicad_prl siblings if present)
               detail.png        TEMPERATURE panel (smooth field + translucent copper)
               current.png       per-net CURRENT cross-check panel
               plot-*.svg        all six copper layers in stack order
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

    # Snapshot the complete executable board family.  The pour plan and frozen
    # ownership state are as important to independent analysis as the KiCad
    # project rules: without them the dashboard reconstructs a different
    # corridor contract and can falsely label an admitted route as foreign.
    snap = os.path.join(adir, "board.kicad_pcb")
    shutil.copy(pcb_path, snap)
    base = pcb_path[:-len(".kicad_pcb")]
    for ext in ARCHIVE_BOARD_SIDECARS:
        sib = base + ext
        if os.path.exists(sib):
            shutil.copy(sib, os.path.join(adir, "board" + ext))

    detail = os.path.join(adir, "detail.png")
    current = os.path.join(adir, "current.png")
    current_density = os.path.join(adir, "current-density.png")
    render = os.path.join(adir, "render.png")
    issues = os.path.join(adir, "issues.svg")
    blockers_report = os.path.join(adir, "blockers.json")
    routing_report = os.path.join(adir, "routing-preflight.json")
    routing_heatmap = os.path.join(adir, "routing-congestion.png")
    plots = {panel: os.path.join(adir, filename)
             for panel, filename, _layers in COPPER_PLOTS}
    rel = lambda p: "/workspace/" + os.path.relpath(p, ROOT)       # noqa: E731
    summary = {"schema": 1, "id": aid, "name": name, "timestamp": ts,
               "ts_human": time.strftime("%Y-%m-%d %H:%M"), "epoch": time.time(),
               "source": os.path.relpath(pcb_path, ROOT), "board": "board.kicad_pcb",
               "panels": {}, "gates": {"ok": False, "error": "not run"},
               "thermal": {"ok": False, "error": "not run"},
               "issues": {"ok": False, "error": "not run"},
               "routing": {"ok": False, "error": "not run"},
               "verdict": "FAILED", "failing": ["pending"]}
    try:
        analysis_env = {"CEC_SHUNT_GAP": "1", "CEC_THERMAL_GPU_AMG": "1"}
        # A generated artifact may be named merely ``improved.kicad_pcb`` even
        # though its archive label retains the product family.  Resolve both
        # before snapshotting renames it to board.kicad_pcb; otherwise the
        # dashboard silently drops declarative critical-net and thermal policy.
        board_hint = (_thermal_board_hint(pcb_path)
                      or _thermal_board_hint(name))
        if board_hint:
            analysis_env["CEC_THERMAL_BOARD_HINT"] = board_hint
        frozen_state = os.path.splitext(snap)[0] + ".pourfirst-state.json"
        if os.path.isfile(frozen_state):
            # Relative to the common repository working directory so the
            # exact same value resolves in native WSL and /workspace Docker.
            analysis_env["CEC_POURFIRST_STATE"] = os.path.relpath(
                frozen_state, ROOT)
            # ``CEC_POURFIRST_STATE`` names the authority; reservation
            # compilation is intentionally gated separately.  Omitting the
            # enable flag made archived placement heatmaps analyze a rail-free
            # board and report zero reserved cells even though the exact state
            # had been copied beside the snapshot.
            analysis_env["CEC_POUR_RESERVE"] = "1"
        cp = _container_run(
            ["python3", "scripts/cec_dashboard.py", "--analyze-board",
             "--board", rel(snap), "--detail", rel(detail), "--current", rel(current),
             "--bottlenecks", rel(current_density),
             "--render", rel(render), "--issues", rel(issues),
             *[arg for panel, _filename, _layers in COPPER_PLOTS
               for arg in (f"--{panel}", rel(plots[panel]))],
             "--width", str(PANEL_W)],
            timeout=900, env=analysis_env)
        res = _parse_last_json(cp.stdout)
        if res:
            summary["thermal"] = res.get("thermal", summary["thermal"])
            summary["gates"] = res.get("gates", summary["gates"])
            summary["issues"] = res.get("issues", summary["issues"])
            issue_blockers = list(
                (summary.get("issues") or {}).pop("blockers", ()) or ())
            # A board-only archive can prove the final defect but not its
            # upstream owner.  When the wave/oracle verdict is supplied, retain
            # its UUID-joined causal chains and non-DRC gate blockers instead
            # of regenerating a final-only ledger.  Auto-discovery keeps this
            # working for copied artifacts named BOARD.oracle.json.
            provenance_candidates = [provenance_path]
            provenance_candidates += [
                pcb_path + ".oracle.json",
                pcb_path[:-len(".kicad_pcb")] + ".oracle.json",
            ]
            provenance = None
            for candidate in provenance_candidates:
                if not candidate or not os.path.isfile(candidate):
                    continue
                try:
                    with open(candidate, encoding="utf-8") as handle:
                        provenance = json.load(handle)
                    break
                except (OSError, ValueError):
                    continue
            if provenance:
                oracle_blockers = list(provenance.get("blockers") or ())
                if oracle_blockers:
                    issue_blockers = oracle_blockers
                elif provenance.get("stage_trace"):
                    import cec_blocker_provenance
                    issue_blockers = cec_blocker_provenance.join_events(
                        issue_blockers, provenance["stage_trace"])
                if issue_blockers:
                    import cec_blocker_provenance
                    summary["issues"]["blocker_summary"] = (
                        cec_blocker_provenance.compact_summary(
                            issue_blockers))
                summary["issues"]["provenance_source"] = os.path.basename(
                    candidate)
            if issue_blockers:
                with open(blockers_report, "w", encoding="utf-8") as handle:
                    json.dump({
                        "schema": 1, "board": "board.kicad_pcb",
                        "summary": (summary.get("issues") or {}).get(
                            "blocker_summary"),
                        "blockers": issue_blockers,
                    }, handle, indent=2, sort_keys=True)
                summary["issues"]["blockers_report"] = "blockers.json"
                summary["issues"]["blocker_preview"] = [
                    {key: row.get(key) for key in
                     ("id", "kind", "rule", "message", "nets", "refs",
                      "origin_known", "next_action")}
                    for row in issue_blockers[:12]]
        else:
            summary["gates"] = {"ok": False, "error": (cp.stderr or cp.stdout or "no output")[-300:]}
    except subprocess.TimeoutExpired:
        summary["gates"] = {"ok": False, "error": "analyze timed out (>900s)"}
    except Exception as e:                                          # noqa: BLE001
        summary["gates"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    # Routing intelligence is independent of the thermal/electrical analyzer:
    # preserve its report and four-layer congestion map even when another panel
    # fails. Eight negotiation iterations are enough for a review heatmap while
    # keeping archive latency bounded; full route waves may request more.
    try:
        cp = _container_run(
            ["python3", "scripts/cec_route_preflight.py", rel(snap),
             "--iters", "8", "--grid-mm", "0.75", "--backend", "auto",
             "--multiresolution", "--future-congestion",
             *(["--board-hint", board_hint] if board_hint else []),
             "--heatmap", rel(routing_heatmap),
             "--output", rel(routing_report)], timeout=300,
            env=analysis_env)
        if cp.returncode != 0 or not os.path.exists(routing_report):
            raise RuntimeError((cp.stderr or cp.stdout or
                                "routing preflight produced no report")[-300:])
        preflight = json.load(open(routing_report))
        congestion = preflight.get("congestion") or {}
        pin_access = preflight.get("pin_access") or {}
        fanout = preflight.get("fanout") or {}
        future = preflight.get("future_congestion") or {}
        summary["routing"] = {
            "ok": True, "gate": bool(preflight.get("gate")),
            "backend": congestion.get("backend"),
            "cost_mode": congestion.get("cost_mode"),
            "wall_s": congestion.get("wall_s"),
            "residual_overuse": congestion.get("residual_overuse"),
            "residual_overuse_escaped": congestion.get("residual_overuse_escaped"),
            "pin_blocked": pin_access.get("blocked_count"),
            "pin_constrained": pin_access.get("constrained_count"),
            "array_count": fanout.get("array_count"),
            "fanout_blocked": fanout.get("blocked"),
            "layers": congestion.get("layers"),
            "hotspots": congestion.get("hotspots"),
            "blockage_witnesses": congestion.get("blockage_witnesses"),
            "blockage_witness_count": len(
                congestion.get("blockage_witnesses") or ()),
            "negotiation": congestion.get("negotiation"),
            "multiresolution": preflight.get("multiresolution"),
            "future_congestion": future,
            "future_critical_conflicts": future.get(
                "critical_corridor_conflicts"),
            "future_overflow_units": future.get("overflow_units"),
            "future_via_count": future.get("expected_via_count"),
            "report": "routing-preflight.json",
        }
    except subprocess.TimeoutExpired:
        summary["routing"] = {"ok": False, "error": "preflight timed out (>300s)"}
    except Exception as e:                                          # noqa: BLE001
        summary["routing"] = {"ok": False,
                              "error": f"{type(e).__name__}: {e}"}

    if os.path.exists(detail):
        summary["panels"]["detail"] = "detail.png"
    if os.path.exists(current):
        summary["panels"]["current"] = "current.png"
    if os.path.exists(current_density):
        summary["panels"]["current-density"] = "current-density.png"
    if os.path.exists(render):
        summary["panels"]["render"] = "render.png"
    if os.path.exists(issues):
        summary["panels"]["issues"] = "issues.svg"
    if os.path.exists(routing_heatmap):
        summary["panels"]["routing"] = "routing-congestion.png"
    for panel, filename, _layers in COPPER_PLOTS:
        if os.path.exists(plots[panel]):
            summary["panels"][panel] = filename
    summary["verdict"], summary["failing"] = _verdict(summary["gates"], summary["thermal"])

    _decorate_archive_summary(summary)
    _write_json_atomic(os.path.join(adir, "summary.json"), summary)
    with _archive_lock:
        _archive_by_id[aid] = summary
        _archive[:] = sorted(_archive_by_id.values(), key=lambda s: -s.get("epoch", 0))
    return summary


def _decorate_archive_summary(summary):
    """Attach stable browser URLs to one self-contained archive summary.

    Codex runs the PCB toolchain in WSL, but the desktop renderer cannot
    reliably dereference raw ``/home/...`` paths.  Every published image must
    therefore have a localhost URL owned by the dashboard.  Keeping the URLs
    in the archive contract also makes CLI-created archives immediately
    shareable without copying images into a second tree.
    """
    aid = str(summary.get("id") or "")
    if not aid:
        return summary
    summary["viewer_url"] = "/?id=" + quote(aid, safe="")
    summary["panel_urls"] = {
        panel: ("/img?id=" + quote(aid, safe="") + "&panel="
                + quote(str(panel), safe=""))
        for panel in (summary.get("panels") or {})
    }
    return summary


def _write_json_atomic(path, payload):
    """Publish JSON without exposing a half-written catalog entry."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=".summary-", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _archive_signature():
    """Cheap change token for summaries written by this or another process."""
    rows = []
    for path in glob.glob(os.path.join(ARCHIVE_ROOT, "*", "summary.json")):
        try:
            stat = os.stat(path)
            rows.append((os.path.basename(os.path.dirname(path)),
                         stat.st_mtime_ns, stat.st_size))
        except OSError:
            continue
    return tuple(sorted(rows))


def _load_archive(force=True):
    """Synchronize the live catalog with self-contained archives on disk.

    A second ``--archive`` process used to write a perfectly valid snapshot
    which the already-running dashboard never learned about.  The API and a
    lightweight watcher now share this mtime/size-indexed synchronizer, so an
    externally generated archive becomes visible without restarting either
    process or re-running the expensive analysis.
    """
    global _archive_disk_signature
    signature = _archive_signature()
    if not force and signature == _archive_disk_signature:
        _archive_sync_status["last_scan"] = time.time()
        return False
    found = {}
    errors = []
    for sj in glob.glob(os.path.join(ARCHIVE_ROOT, "*", "summary.json")):
        try:
            with open(sj, encoding="utf-8") as handle:
                s = json.load(handle)
            s["id"] = s.get("id") or os.path.basename(os.path.dirname(sj))
            # Verdict policy evolves. In particular, pre-v1 thermal summaries
            # may have been solved on verifier-synthesized copper; never retain
            # a historical CLEAN badge when current policy can prove the FEM
            # geometry provenance is missing.
            s["verdict"], s["failing"] = _verdict(
                s.get("gates") or {}, s.get("thermal") or {})
            _decorate_archive_summary(s)
            found[s["id"]] = s
        except Exception as exc:                                   # noqa: BLE001
            errors.append(f"{os.path.relpath(sj, ROOT)}: "
                          f"{type(exc).__name__}: {exc}")
    with _archive_lock:
        _archive_by_id.clear()
        _archive_by_id.update(found)
        _archive[:] = sorted(found.values(), key=lambda s: -s.get("epoch", 0))
    changed = signature != _archive_disk_signature
    _archive_disk_signature = signature
    _archive_sync_status["last_scan"] = time.time()
    if changed:
        _archive_sync_status["last_change"] = time.time()
    _archive_sync_status["errors"] = errors[-12:]
    return changed


def _archive_catalog_watcher():
    """Hot-load archives created by independent pipeline/CLI processes."""
    while True:
        try:
            _load_archive(force=False)
        except Exception as exc:                                   # noqa: BLE001
            _archive_sync_status["errors"] = [
                f"catalog watcher: {type(exc).__name__}: {exc}"]
        time.sleep(ARCHIVE_SCAN_SECONDS)


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
        job = _jobs.get()
        pcb, name = job[:2]
        provenance = job[2] if len(job) > 2 else None
        _seed_status["active"] = name
        _seed_status["pending"] = _jobs.qsize()
        try:
            archive_board(pcb, name, provenance_path=provenance)
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
    """Traversal-safe archive image path for (id, panel), or None. Besides the built-in
    panels, an entry's summary.json may register EXTRA panels (ad-hoc studies, e.g. a
    worst-case-current thermal solve) as {key: filename}; the filename must be a bare
    .png/.svg basename inside that entry's own archive dir."""
    aid = os.path.basename(aid or "")
    if not re.match(r"^[A-Za-z0-9T_-]+$", aid):
        return None
    fn = {"detail": "detail.png", "current": "current.png", "render": "render.png",
          **{key: filename for key, filename, _layers in COPPER_PLOTS}}.get(panel)
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
            # Pipelines and one-shot ``--archive`` publishers are allowed to
            # run independently of this long-lived HTTP process.  Sync at the
            # read boundary as well as in the background so the very next UI
            # poll observes a newly completed atomic summary.
            _load_archive(force=False)
            with _archive_lock:
                boards = list(_archive)
            self._json({"ts": time.time(), "rev": _page_rev, "boards": boards,
                        "seeding": dict(_seed_status),
                        "catalog_sync": dict(_archive_sync_status),
                        "archive_root": os.path.relpath(ARCHIVE_ROOT, ROOT)})
        elif path == "/healthz":
            _load_archive(force=False)
            with _archive_lock:
                latest = _archive[0].get("id") if _archive else None
                count = len(_archive)
            self._json({"ok": True, "archive_count": count,
                        "latest_archive": latest,
                        "catalog_sync": dict(_archive_sync_status)})
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
a.pill{color:#cfd8dc;text-decoration:none}
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
  <button class="pill" id="m_issues" onclick="setMode('issues')">issues</button>
  <button class="pill" id="m_plot" onclick="setMode('plot')">plot</button>
  <a class="pill" id="share" href="/" style="display:none">share view</a>
  <a class="pill" id="openpanel" href="/" target="_blank" style="display:none">open image</a>
  <button class="pill" onclick="fit()">fit</button>
  <button class="pill" onclick="zoom(1.25)">+</button>
  <button class="pill" onclick="zoom(0.8)">-</button>
 </div>
 <div id="pwrap"><div id="pstack"><div id="empty">no board selected</div></div></div>
</div></div>
<script>
let boards=[], lib={beta:[],fresh:[],watch:{}}, acts=[], cur=null, curAct=null, mode='all', plotW=1100, actBodies=false, actTwin=null, actImg=null;
const PAGE_REV='__REV__';
const INITIAL_QUERY=new URLSearchParams(location.search);
const INITIAL_ID=INITIAL_QUERY.get('id');
const INITIAL_PANEL=INITIAL_QUERY.get('panel');
let initialSelectionApplied=false;
let secOpen={act:true,beta:true,fresh:true,snaps:true};
// API summaries deliberately gain richer structured evidence over time.  The
// view boundary must therefore accept every JSON value, not assume that every
// badge field is already a string.  Object values are kept useful in tooltips
// instead of degrading to "[object Object]"; HTML quotes are escaped as well
// because most callers place the result in a title attribute.
function displayText(v){if(v===null||v===undefined)return'';if(typeof v==='string')return v;if(typeof v==='object'){try{return JSON.stringify(v);}catch(_){}}return String(v);}
function esc(s){return displayText(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}
function vpill(v){const cl=v==='CLEAN'?'ok':'bad';return `<span class="pill ${cl}">${esc(v)}</span>`;}
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
 const g=cur.gates||{}, t=cur.thermal||{}, rt=cur.routing||{}, fp=g.foreign||{}, rv=g.reserved_corridor||{}, rq=g.route_sanity||{};
 if(!g.ok){el.innerHTML=`<span class="pill bad" title="${esc(g.error||'')}">gate-eval n/a</span>`+verdictPill();return;}
 const fclean=(fp.status==='na')||(fp.status==='ok'&&!fp.n_parts&&!fp.n_tracks&&!fp.n_vias);
 const fok=(fp.status==='na')?null:fclean;
 const fext=fp.status==='ok'?`${fp.n_parts||0}P/${fp.n_tracks}T/${fp.n_vias}V`:(fp.status||'');
 const rvext=rv.status==='ok'?`${rv.n_tracks||0}T/${rv.n_vias||0}V`:(rv.status||'');
 let h=gbadge('kelvin',g.kelvin_ok)
  +gbadge('actual-pour',fok,fext)
  +gbadge('route-reserve',null,rvext)
 +gbadge('drc',g.drc===0,String(g.drc))
  +gbadge('unconnected',g.unconnected===0,String(g.unconnected));
 if(rt.ok){
  const rr=Number.isFinite(rt.residual_overuse_escaped)?rt.residual_overuse_escaped:'?';
  const ng=rt.negotiation||{}, mr=rt.multiresolution||{};
  const plateau=ng.plateau?' · plateau':'';
  const levels=(mr.levels||[]).map(x=>`${x.grid_mm}mm:${x.backend||'?'}:${x.residual_overuse_escaped}`).join(' → ');
  h+=`<span class="pill ${rt.gate?'ok':'bad'}" title="Negotiated congestion (${esc(rt.cost_mode||'')} on ${esc(rt.backend||'')}), raw ${esc(rt.residual_overuse)}, outside pin escapes ${esc(rr)}; constrained pads ${esc(rt.pin_constrained)}; blockage witnesses ${esc(rt.blockage_witness_count)}; best iteration ${esc(ng.best_iteration)} stall ${esc(ng.stall_age)}${esc(plateau)}; coarse-to-fine ${esc(levels)}">congestion ${esc(rr)}${esc(plateau)}</span>`;
  const fc=rt.future_congestion||{};
  if(Number.isFinite(fc.overflow_units)){
   const clean=fc.critical_corridor_conflicts===0&&fc.overflow_units===0;
   h+=`<span class="pill ${clean?'ok':'warn'}" title="Incremental future-route forecast: protected-corridor conflicts ${esc(fc.critical_corridor_conflicts)}, fixed-point overflow ${esc(fc.overflow_units)}, expected vias ${esc(fc.expected_via_count)}, obstacle crossings ${esc(fc.corridor_obstacle_crossings)} across ${(fc.layers||[]).length} route layers">forecast ${esc(fc.critical_corridor_conflicts)}/${esc(fc.overflow_units)}</span>`;
  }
 }else h+=`<span class="pill dim" title="${esc(rt.error||'')}">congestion n/a</span>`;
 const off45=Number.isInteger(rq.unlocked_off45_tracks)?rq.unlocked_off45_tracks:null;
 if(off45!==null) h+=`<span class="pill ${off45===0?'ok':'warn'}" title="Unlocked generated trace segments outside 0/45/90 degrees; locked authored launches excluded">off-45 ${off45}</span>`;
 const geomOk=t.geometry_source==='source-declared-copper-only:v1';
 if(t.ok&&!geomOk) h+=`<span class="pill bad" title="Legacy or unproven FEM geometry; re-run this board with source-only copper verification">thermal INVALID · geometry unproven</span>`;
 else if(t.ok) h+=`<span class="pill ${t.verdict==='PASS'?'ok':'bad'}" title="2.5D electro-thermal on source-declared copper only, grid ${t.grid_mm}mm, amb ${t.ambient}C, gate dT<=${30}C. cooling: ${esc(t.cooling||'')}">thermal ${t.verdict} · θmax ${t.max_T}°C dT ${t.dT}°C</span>`;
 else if(t.geometry_source==='INVALID') h+=`<span class="pill bad" title="${esc(t.error||'FEM geometry parity failed')}">thermal INVALID · geometry parity</span>`;
 else h+=`<span class="pill dim" title="${esc(t.error||'')}">thermal n/a</span>`;
 el.innerHTML=h+verdictPill();
}
function verdictPill(){return cur?(' '+vpill(cur.verdict)):'';}
const PANEL_LABEL={
 detail:'TEMPERATURE (°C) — smooth field + translucent stacked copper',
 current:'CURRENT cross-check (A) — heat should track current',
 'current-density':'CURRENT DENSITY / COPPER NECKS — solved per-layer flow and ranked pinch coordinates',
 render:'RENDER — raytraced top view',
 issues:'ISSUES — structural DRC, unconnected copper, and implicated components',
 plotf:'PLOT — front copper (F.Cu + Edge.Cuts + silkscreen)',
 plot1:'PLOT — L2 internal copper (In1.Cu)',
 plot2:'PLOT — L3 internal copper (In2.Cu)',
 plot3:'PLOT — L4 internal copper (In3.Cu)',
 plot4:'PLOT — L5 internal copper (In4.Cu)',
 plotb:'PLOT — physical bottom view, mirrored (B.Cu + Edge.Cuts + silkscreen)',
 routing:'ROUTING CONGESTION — legal usage cyan, over-capacity cells red'};
function buildPanels(){
 const st=document.getElementById('pstack'); st.style.width=plotW+'px'; st.innerHTML='';
 if(!cur){st.innerHTML='<div id="empty">no board selected</div>';return;}
 const have=cur.panels||{};
 const PLOTS=['plotf','plot1','plot2','plot3','plot4','plotb'];
 const KNOWN=['issues','detail','current','render',...PLOTS];
 const extras=Object.keys(have).filter(k=>!KNOWN.includes(k)).sort();
 // studies (worst-case solves etc.) are thermal panels: show them RIGHT UNDER the
 // temperature panel, not buried after the render/plots at the bottom of the stack
 const want = mode==='all'?['issues','detail',...extras,'current','render',...PLOTS]
            : mode==='plot'?PLOTS
            : mode==='detail'?['detail',...extras]
            : [mode];
 let any=false;
 for(const pn of want){
  if(!have[pn]) continue;
  any=true;
  const w=document.createElement('div'); w.className='panel'+(PLOTS.includes(pn)?' plot':'');
  const im=document.createElement('img'); im.src=`/img?id=${encodeURIComponent(cur.id)}&panel=${pn}&v=${cur.epoch||0}`;
  const cap=document.createElement('div'); cap.className='cap';
  cap.textContent=PANEL_LABEL[pn]||('STUDY — '+pn.replace(/-/g,' '));
  w.appendChild(im); w.appendChild(cap); st.appendChild(w);
 }
 if(!any) st.innerHTML='<div id="empty">no panels of this kind for this board — older snapshots predate render/plot: hit analyze ▶ again from the library to regenerate</div>';
}
function setMode(m){mode=m;
 for(const x of ['all','issues','detail','current','render','plot']) document.getElementById('m_'+x).classList.toggle('on',x===m);
 buildPanels(); updateShareLinks();}
function preferredPanel(){
 if(!cur)return null;
 const have=cur.panels||{};
 if(mode!=='all'&&mode!=='plot'&&have[mode])return mode;
 if(mode==='plot')return ['plotf','plot1','plot2','plot3','plot4','plotb'].find(p=>have[p])||null;
 return ['render','issues','plotf','routing','detail','current'].find(p=>have[p])||Object.keys(have)[0]||null;
}
function updateShareLinks(){
 const share=document.getElementById('share'), image=document.getElementById('openpanel');
 if(!cur){share.style.display='none';image.style.display='none';return;}
 const panel=preferredPanel();
 const view=`/?id=${encodeURIComponent(cur.id)}${mode!=='all'?('&panel='+encodeURIComponent(mode)):''}`;
 share.href=view;share.style.display='inline-block';
 if(panel){image.href=`/img?id=${encodeURIComponent(cur.id)}&panel=${encodeURIComponent(panel)}`;image.style.display='inline-block';}
 else image.style.display='none';
}
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
function pick(id,updateLocation=true){
 curAct=null;
 cur=boards.find(b=>b.id===id)||null;
 document.getElementById('btitle').textContent=cur?(cur.name+'  ·  '+(cur.source||'')):'select a board';
 // Panels are the primary payload.  Mount them before optional badge metadata
 // so a future badge-schema regression can never blank an otherwise valid
 // archived board again.
 renderList(); fit(); renderBadges(); updateShareLinks();
 if(cur&&updateLocation){
  const suffix=mode!=='all'?('&panel='+encodeURIComponent(mode)):'';
  history.replaceState(null,'',`/?id=${encodeURIComponent(cur.id)}${suffix}`);
 }
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
  if(!initialSelectionApplied&&INITIAL_ID&&boards.some(b=>b.id===INITIAL_ID)){
   if(['all','issues','detail','current','render','plot'].includes(INITIAL_PANEL))mode=INITIAL_PANEL;
   initialSelectionApplied=true;
   pick(INITIAL_ID,false);
  }
  try{ lib=await (await fetch('/api/library')).json(); }catch(e){}
  try{ acts=((await (await fetch('/api/worklog')).json()).events)||[]; }catch(e){}
  const sd=s.seeding||{};
  let msg=`${(lib.beta||[]).length} beta · ${(lib.fresh||[]).length} fresh · ${boards.length} analyzed`;
  if(sd.active) msg+=`  ·  <span style="color:#ffcc80">archiving ${esc(sd.active)}…</span>`;
  if(sd.pending) msg+=`  ·  ${sd.pending} queued`;
  if((lib.watch||{}).last_scan) msg+=`  ·  watch ${esc(lib.watch.last_scan)}`;
  if((sd.errors||[]).length) msg+=`  ·  <span style="color:#ef9a9a">${sd.errors.length} err</span>`;
  document.getElementById('seed').innerHTML=msg;
  if(cur){ const u=boards.find(b=>b.id===cur.id); if(u){const e0=cur.epoch; cur=u; if(u.epoch!==e0){buildPanels();renderBadges();}} }
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
    ap.add_argument("--provenance", default=None,
                    help="oracle/wave JSON whose blocker stage trace belongs to --archive")
    # ---- in-container analysis mode (internal; run INSIDE the routing container) ----
    ap.add_argument("--analyze-board", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--analyze-gates", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--board", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--detail", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--current", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--bottlenecks", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--render", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--issues", default=None, help=argparse.SUPPRESS)
    for panel, _filename, _layers in COPPER_PLOTS:
        ap.add_argument(f"--{panel}", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--width", type=int, default=PANEL_W, help=argparse.SUPPRESS)
    a = ap.parse_args()

    if a.analyze_gates:
        print(json.dumps(_gate_issue_analysis(a.board, a.issues)))
        return

    if a.analyze_board:                                            # container half: solve, panels, render, plots, gates
        _analyze_in_container(a.board, a.detail, a.current, a.width,
                              bottlenecks_png=a.bottlenecks,
                              render_png=a.render,
                              issues_svg=a.issues,
                              **{f"{panel}_svg": getattr(a, panel)
                                 for panel, _filename, _layers in COPPER_PLOTS})
        return

    os.makedirs(ARCHIVE_ROOT, exist_ok=True)
    _load_archive()
    threading.Thread(target=_archive_worker, daemon=True).start()
    # Archive analysis is often launched by a separate CLI/pipeline process.
    # Keep the long-lived dashboard catalog synchronized with those atomic
    # publications so reviewers never have to restart the server to see them.
    threading.Thread(target=_archive_catalog_watcher, daemon=True).start()
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
        _jobs.put((os.path.abspath(a.archive),
                   a.name or _slug(os.path.splitext(
                       os.path.basename(a.archive))[0]),
                   os.path.abspath(a.provenance) if a.provenance else None))
    if a.seed:
        _enqueue_seed()
    with _archive_lock:
        n = len(_archive)
    print(f"dashboard: http://localhost:{a.port}  (archive={os.path.relpath(ARCHIVE_ROOT, ROOT)}, "
          f"{n} board(s), queued={_jobs.qsize()})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
