#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_fr -- Tier-0 deterministic Freerouting-backed routing generator for the
#            CEC Platform automated PCB routing system.
# ============================================================================
# This module forms the lowest tier of the automated routing pipeline: it takes
# a KiCad .kicad_pcb, round-trips it through the Specctra DSN/SES exchange format
# using the real pcbnew engine (same KiCad 10 engine the GUI uses), runs the
# Freerouting autorouter headlessly via xvfb-run + java, and imports the routed
# .ses back into the board — producing real copper tracks and vias identical in
# format to GUI-routed results.
#
# Key design:
#   export_dsn()       KiCad board -> Specctra .dsn (ExportSpecctraDSN, 2-arg headless form)
#   run_freerouting()  .dsn -> .ses via xvfb-run + Freerouting 1.7.0 jar
#   import_ses()       .ses -> routed .kicad_pcb (ImportSpecctraSES, 2-arg headless form)
#   bake_hints()       add keepout rule-area zones to the board before export so
#                      Freerouting avoids reserved vital areas (12V pours, Kelvin windows)
#   route_once()       single full pipeline: bake_hints -> dsn -> FR -> ses -> board
#   generate_batch()   parallel multi-candidate generation via ProcessPoolExecutor
#
# Parallelism strategy: ProcessPoolExecutor with the "spawn" start method (NOT fork --
# pcbnew/wxWidgets is not fork-safe; a forked worker deadlocks at ExportSpecctraDSN when
# the parent has already used pcbnew). Each spawned worker is a fresh interpreter that
# re-imports pcbnew clean, receives only plain strings/dicts (paths + params), and calls
# LoadBoard itself -- no pcbnew objects ever cross the process boundary.
#
# Freerouting writes a logs/ directory into its CWD. All FR invocations run from a fresh
# workdir in the OS temp dir (tempfile.gettempdir(): /tmp on Linux/mac, %TEMP% on Windows)
# to ensure logs/ never appears in the repo, regardless of CWD. The repo-side backstop is
# the .gitignore `logs/` entry (R-10 correction: no Stop hook exists -- .claude/settings.json
# defines only a SessionStart hook, and the kicad-happy plugin ships none).
#
# Verified round-trip (EPS board, 2026-06-06): ExportSpecctraDSN -> FR exit 0 ->
# ImportSpecctraSES -> 481 tracks / 64 vias on the EPS 8-pin module.
import os
import re
import time
import sys
import math
import shutil
import signal
import tempfile
import subprocess
import urllib.request
import json
import fnmatch
from dataclasses import dataclass, field
from concurrent.futures import ProcessPoolExecutor

# ---------------------------------------------------------------------------
# Suppress the benign pcbnew startup noise (assert "m_choices" / "No enum choices"
# lines) without swallowing real stderr from callers. We redirect pcbnew's own
# import stderr to /dev/null only around the import; the rest of the code keeps
# stderr live so real errors surface.
# ---------------------------------------------------------------------------
import contextlib as _cl

with open(os.devnull, "w") as _pcbnew_stderr:
    with _cl.redirect_stderr(_pcbnew_stderr):
        import pcbnew

# SWIG REGISTRY PIN (2026-07-25): keeps pcbnew's type table from being torn down
# mid-run -- the root cause of the hub's all-9999 wall, where LoadBoard began
# returning bare SwigPyObjects and every variant died in bake_hints. See
# scripts/cec_swig_guard.py for the measurement chain.
import cec_swig_guard as _swig_guard                     # noqa: E402
_swig_guard.pin()
import cec_fab_profile as _fab                           # noqa: E402

MM = 1_000_000               # nm per mm
def _nm(v): return int(round(v * MM))

ENDPOINT_NECKDOWN_GROUP = "CEC_LOCAL_ENDPOINT_NECKDOWN"
ENDPOINT_NECKDOWN_RULE_BEGIN = "# BEGIN CEC LOCAL ENDPOINT NECKDOWN"
ENDPOINT_NECKDOWN_RULE_END = "# END CEC LOCAL ENDPOINT NECKDOWN"


def group_endpoint_neckdowns(board, items, full_width):
    """Own generated sub-class endpoint copper in one portable rule group.

    Fine-pitch pads can be narrower than their netclass trunk.  The router may
    taper only the bounded pad-local prefix; grouping those exact generated
    tracks keeps the project netclass unchanged and makes the exception follow
    the copper through board renames and candidate copies.
    """
    narrow = [
        item for item in items
        if item.GetClass() in ("PCB_TRACK", "PCB_ARC")
        and item.GetWidth() < int(full_width)]
    if not narrow:
        return None
    group = next((candidate for candidate in board.Groups()
                  if candidate.GetName() == ENDPOINT_NECKDOWN_GROUP), None)
    if group is None:
        group = pcbnew.PCB_GROUP(board)
        group.SetName(ENDPOINT_NECKDOWN_GROUP)
        board.Add(group)
    for item in narrow:
        if not group.ContainsItem(item):
            group.AddItem(item)
    return {
        "group": ENDPOINT_NECKDOWN_GROUP,
        "tracks": len(narrow),
        "min_width_mm": round(min(item.GetWidth() for item in narrow) / MM, 3),
        "max_length_mm": round(max(item.GetLength() for item in narrow) / MM, 3),
    }


def _endpoint_neckdown_widths(report):
    """Extract widths from either a stage summary or decoupler-cell report."""
    widths = []
    direct = (report or {}).get("endpoint_neckdown") or {}
    if direct.get("group") == ENDPOINT_NECKDOWN_GROUP:
        widths.append(float(direct["min_width_mm"]))
    for row in (report or {}).get("cells", ()):
        evidence = (row.get("supply") or {}).get("endpoint_neckdown") or {}
        if evidence.get("group") == ENDPOINT_NECKDOWN_GROUP:
            widths.append(float(evidence["min_width_mm"]))
    return widths


def ensure_endpoint_neckdown_rule(board_path, report):
    """Install a width exception scoped to the generated endpoint group only."""
    widths = _endpoint_neckdown_widths(report)
    if not widths:
        return {"applicable": False, "written": False}
    minimum = min(widths)
    stem = (board_path[:-len(".kicad_pcb")]
            if board_path.endswith(".kicad_pcb") else board_path)
    path = stem + ".kicad_dru"
    text = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    if not text.strip():
        text = "(version 1)\n"
    block = (
        "\n%s\n"
        "# Short, guarded neckdowns at fine-pitch endpoints only.\n"
        "(rule \"CEC guarded local endpoint neckdown\"\n"
        "  (condition \"A.Type == 'Track' && "
        "A.memberOfGroup('%s')\")\n"
        "  (constraint track_width (min %.3fmm)))\n"
        "%s\n" % (ENDPOINT_NECKDOWN_RULE_BEGIN,
                    ENDPOINT_NECKDOWN_GROUP, minimum,
                    ENDPOINT_NECKDOWN_RULE_END))
    start = text.find(ENDPOINT_NECKDOWN_RULE_BEGIN)
    end = text.find(ENDPOINT_NECKDOWN_RULE_END)
    if start >= 0 and end >= start:
        end += len(ENDPOINT_NECKDOWN_RULE_END)
        updated = text[:start] + block.strip("\n") + text[end:]
    else:
        updated = text.rstrip() + block
    written = updated != text
    if written:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(updated)
    return {"applicable": True, "written": written, "path": path,
            "group": ENDPOINT_NECKDOWN_GROUP,
            "min_width_mm": round(minimum, 3)}


def reconcile_endpoint_neckdown_groups(board, *, netclass_resolver):
    """Recover bounded endpoint taper fragments lost during route transforms.

    SES import, duplicate-UUID repair, and echo reconciliation can split or
    replace one generated taper segment without carrying PCB_GROUP membership
    to the replacement.  Recover only a short sub-class track that terminates
    on a same-net fine-pitch SMD pad and whose other end joins either the
    already-owned taper group or a full-width trunk.  This is a geometric
    ownership reconstruction, not a net-name or coordinate waiver.
    """
    group = next((candidate for candidate in board.Groups()
                  if candidate.GetName() == ENDPOINT_NECKDOWN_GROUP), None)
    if group is None:
        return {"schema": 1, "applicable": False, "recovered": 0,
                "reason": "no_generated_endpoint_group"}
    tracks = [item for item in board.GetTracks()
              if item.GetClass() in ("PCB_TRACK", "PCB_ARC")]
    endpoint_index = {}
    for item in tracks:
        for point in (item.GetStart(), item.GetEnd()):
            endpoint_index.setdefault((point.x, point.y), []).append(item)
    pads_by_net = {}
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetCode() > 0:
                pads_by_net.setdefault(pad.GetNetCode(), []).append(pad)

    def contract_width(item):
        spec = (netclass_resolver(item.GetNetname() or "") or {})
        value = float(spec.get("track_width") or 0.0)
        by_layer = spec.get("track_width_by_layer_mm") or {}
        value = max(value, float(by_layer.get(
            board.GetLayerName(item.GetLayer())) or 0.0))
        return _nm(value)

    def fine_pad_at(item, point, full_width):
        for pad in pads_by_net.get(item.GetNetCode(), ()):
            try:
                if int(pad.GetAttribute()) != int(pcbnew.PAD_ATTRIB_SMD):
                    continue
            except Exception:                            # noqa: BLE001
                continue
            if min(pad.GetSize().x, pad.GetSize().y) >= full_width:
                continue
            if not pad.IsOnLayer(item.GetLayer()):
                continue
            try:
                if pad.GetEffectiveShape(item.GetLayer()).Contains(point):
                    return True
            except Exception:                            # noqa: BLE001
                if pad.HitTest(point):
                    return True
        return False

    recovered = []
    changed = True
    while changed:
        changed = False
        for item in tracks:
            if group.ContainsItem(item):
                continue
            full_width = contract_width(item)
            if full_width <= 0 or item.GetWidth() >= full_width:
                continue
            class_mm = full_width / MM
            max_length = max(0.6, min(1.5, 1.5 * class_mm))
            if item.GetLength() / MM > max_length + 1e-6:
                continue
            start, end = item.GetStart(), item.GetEnd()
            support_ends = []
            if fine_pad_at(item, start, full_width):
                support_ends.append(end)
            if fine_pad_at(item, end, full_width):
                support_ends.append(start)
            if not support_ends:
                continue
            # A short track can sit entirely inside an elongated pad.  Try
            # both physical directions: choosing the first pad-contained end
            # alone can look toward the pad centre and miss the owned taper
            # that actually continues from the opposite end.
            supported = False
            for support_end in support_ends:
                support = [other for other in endpoint_index.get(
                    (support_end.x, support_end.y), ()) if other is not item
                           and other.GetNetCode() == item.GetNetCode()]
                if any(group.ContainsItem(other)
                       or other.GetWidth() >= full_width for other in support):
                    supported = True
                    break
            if not supported:
                continue
            group.AddItem(item)
            recovered.append({
                "uuid": item.m_Uuid.AsString(),
                "net": item.GetNetname() or "",
                "width_mm": round(item.GetWidth() / MM, 3),
                "length_mm": round(item.GetLength() / MM, 3),
            })
            changed = True
    widths = [item.GetWidth() / MM for item in tracks
              if group.ContainsItem(item)]
    return {"schema": 1, "applicable": True,
            "group": ENDPOINT_NECKDOWN_GROUP,
            "recovered": len(recovered), "items": recovered,
            "tracks": len(widths),
            "min_width_mm": round(min(widths), 3) if widths else None}

# Per-process import diagnostics. route_once consumes and removes the entry
# immediately after import_ses returns, so parallel spawn workers never share
# mutable state and repeated routes cannot inherit a stale completion verdict.
_IMPORT_REPORTS = {}

# ---------------------------------------------------------------------------
# SHUNT-GAP notch (owner-ratified 2026-06-28) -- the un-poured channel the high-current pours leave
# AT the Kelvin shunt for the sense cluster (INA238 + §6.13 INA181 + TLV7011) and a B.Cu overflow-
# routing lane. A 2-pad R_2512 shunt's pads are only ~5.9mm apart, so hugging each pad with the 1.0mm
# pour margin left a ~3.9mm notch -- TOO NARROW (the 4.19mm SOT-23-6 INA181 body overshot it, and the
# B.Cu route-under had no lane to dive the overflow nets under the pour edge). SHUNT_GAP_MM opens that
# notch to ~6.5mm by pulling each pour's shunt-side edge back to shunt_centre +/- SHUNT_GAP_MM/2 (the
# pour still overlaps the shunt pad's outer half -> high-current continuity, completed by the B.Cu
# mirror + via field). The placer grows the board ~3mm taller (J_IN<->J_OUT) so the pours stay long.
# General to the per-cable EPS/PCIe interposer family (any 2-pad straddle shunt).
def _shunt_gap_mm():
    """Notch height (mm) between HI/LO pours at the shunt. Env-tunable per board
    (CEC_SHUNT_GAP_MM; the 24-pin sets 16.0 -- the sense cell lives in the band).
    Read per-call, never at import."""
    return float(os.environ.get("CEC_SHUNT_GAP_MM", "6.5"))


SHUNT_GAP_MM = 6.5   # legacy alias; live sites call _shunt_gap_mm()


def _pourfirst_state():
    """FROZEN POUR-FIRST STATE (v3 pour-first placement rung, docs/slab-pour-
    design-2026-07-24.md v3: pours solved on the anchor-only board right after
    connectors + blueprint stamps + MCU seating, then SET IN STONE). The
    pipeline's pour_first_stage writes a JSON sidecar and exports its path as
    CEC_POURFIRST_STATE; route_once consumes its corridors/exclude_pins (the
    pre-FR reservation -- one solve, three consumers) and import_ses passes
    its pour dicts through UNCONVERTED. Returns {} when unset; an unreadable
    state is LOUD, never silently ignored-as-empty-and-forgotten."""
    p = os.environ.get("CEC_POURFIRST_STATE", "").strip()
    if not p:
        return {}
    try:
        import json as _json
        with open(p) as f:
            return _json.load(f) or {}
    except Exception as e:                             # noqa: BLE001
        print(f"[cec_fr] pour-first state UNREADABLE ({e}) -- {p!r} ignored, "
              "falling back to the live pour machinery", file=sys.stderr)
        return {}


def _frozen_power_state_parts(state):
    """Return ``(pours_to_lay, vias_to_lay, owned_nets)`` for a freeze.

    Schema 2 carries an explicit physical ownership list.  An explicit empty
    list is meaningful (the anchor planner deferred every rail), while legacy
    states retain their historical report-key inference.  A pre-laid state
    owns its nets and reservation but has no import-time geometry to add.
    """
    state = state or {}
    stored_pours = list(state.get("pours") or ())
    stored_vias = list(state.get("vias") or ())
    if "frozen_nets" in state:
        nets = set(state.get("frozen_nets") or ())
    else:
        nets = ({d.get("net") for d in stored_pours if d.get("net")}
                | set((state.get("report") or {}).keys()))
    if state.get("prelaid"):
        return [], [], nets
    return ([d for d in stored_pours if d.get("net") in nets],
            [d for d in stored_vias if d.get("net") in nets], nets)


def _shunt_gap_on():
    """The SHUNT_GAP_MM widen is OPT-IN (CEC_SHUNT_GAP=1), DEFAULT OFF. It is a board-specific
    re-place change (owner ratification boundary: a ratified change is board-specific by default,
    not platform-wide) -- the board must be PLACED with the matching wide notch + grown outline for
    the pulled-back pour to stay on the shunt pad. Applying it to a legacy board placed for the
    ~3.9mm notch (e.g. the frozen SB-08 golden eps-8pin) pulls the pour off the shunt and breaks the
    route, so existing committed boards stay on the historical hug-the-shunt pour unless they opt in."""
    return os.environ.get("CEC_SHUNT_GAP", "0") == "1"


def _open_shunt_notch(box, shunt_xy, gap, *, vertical=True):
    """Pull a high-current pour box's SHUNT-SIDE edge back so the un-poured notch centred on the shunt
    is at least *gap* mm (the sense-cluster + B.Cu-overflow channel). *box*=(x0,x1,y0,y1) is one net's
    pour (cable-in->shunt OR shunt->cable-out); *shunt_xy* is the shunt centre. The shunt-side edge is
    the box edge nearest the shunt centre along the corridor axis (vertical for the EPS/PCIe top->bottom
    cables). Only ever PULLS the edge toward the connector (clamped, never extends), so it can only OPEN
    the notch -- the connector-side extent is untouched."""
    x0, x1, y0, y1 = box
    if vertical:
        if (y0 + y1) / 2.0 < shunt_xy[1]:               # box ABOVE the shunt (cable-in/HI) -> clamp bottom up
            y1 = min(y1, shunt_xy[1] - gap / 2.0)
        else:                                           # box BELOW the shunt (cable-out/LO) -> clamp top down
            y0 = max(y0, shunt_xy[1] + gap / 2.0)
    else:
        if (x0 + x1) / 2.0 < shunt_xy[0]:
            x1 = min(x1, shunt_xy[0] - gap / 2.0)
        else:
            x0 = max(x0, shunt_xy[0] + gap / 2.0)
    return (x0, x1, y0, y1)

# Cross-platform scratch dir: the OS temp dir (/tmp on Linux/mac, %TEMP% on Windows).
# Never hardcode /tmp -- it doesn't exist on Windows.
_TMP = tempfile.gettempdir()


def _fr_engine(jar, version=None):
    """The argv prefix that launches Freerouting *version*.

    1.7.0 (and any release whose minimum Java is satisfied) runs `java -jar`.
    2.2.4 is compiled for Java 25 (class-file 69); when the PATH java is older, fall back
    to the hash-pinned official jpackage APP-IMAGE launcher (bundled JRE 25, Linux only).
    """
    v = version or FR_VERSION
    rel = FR_RELEASES.get(v) or {}
    need = int(rel.get("min_java", 17))
    java = _java_executable()
    have = _java_major(java)
    if have >= need:
        return [java, "-jar", jar]
    if rel.get("appimage_launcher") and sys.platform.startswith("linux"):
        return [ensure_appimage(v)]
    raise RuntimeError(
        f"cec_fr: Freerouting {v} needs Java >= {need} (found {have or 'none'}) and no "
        f"bundled-runtime app-image is pinned for this platform. Install a JRE {need}+ "
        f"or set CEC_FR_VERSION/CEC_FREEROUTING_JAR appropriately."
    )


def _fr_command(jar, dsn_path, ses_path, passes, opt_time, threads,
                version=None, workdir=None):
    """Build the Freerouting invocation for THIS platform.

    Freerouting 1.7.0 is a Java/Swing app that touches AWT at startup, so it needs a display.
      * Linux: wrap in an isolated `xvfb-run` (a virtual X server) -- if xvfb-run is
        missing on headless Linux, FR will throw HeadlessException (route-prereqs flags it).
      * Linux WITH $DISPLAY, macOS, Windows: run `java` directly -- the native windowing
        system (X / Quartz / Win32) provides the display. There is NO xvfb on Windows and
        none is needed; a Windows runner must just be in an interactive desktop session.

    2.x runs TRUE headless (`--gui.enabled=false`, no display at all) and additionally gets:
      -da                      analytics/telemetry OFF (no phone-home in a determinism epoch)
      --user_data_path=<wd>    settings (freerouting.json) + logs corralled in the per-run
                               workdir, so no persisted global settings can leak between
                               runs and perturb determinism

    NOTE -oit semantics: 2.x documents -oit as the optimizer improvement threshold in
    PERCENT per pass (default 0.1), not a time. The R-01 spread still varies it as its
    diversity axis; the FR-01 gate measures whether that still yields distinct candidates.
    """
    v = version or FR_VERSION
    base = _fr_engine(jar, v) + [
            "-de", os.path.abspath(dsn_path),
            "-do", os.path.abspath(ses_path),
            "-mp", str(int(passes)),
            "-oit", str(int(opt_time)),
            "-mt", str(int(threads))]
    if not v.startswith("1."):
        base += ["-da", "--gui.enabled=false"]
        if workdir:
            base += [f"--user_data_path={os.path.abspath(workdir)}"]
        return base                                   # true headless: no xvfb needed
    # Linux: ALWAYS prefer xvfb-run when available, even if $DISPLAY is set. The routing container
    # leaks a forwarded display (WSLg sets DISPLAY=:99 with a mounted X11 socket), and the old
    # `not $DISPLAY` guard then took the native-window path -> Freerouting popped a real Swing window
    # on the host desktop. Headless is the correct default for the compute plane. Each concurrent
    # route also needs its OWN auth file: Debian's xvfb-run otherwise defaults to ./.Xauthority,
    # so sixteen workers overwrite one another's cookies and sporadically fail with "Authorization
    # required". A PID-derived starting display avoids the companion auto-server-number race; -a
    # still advances safely if a stale socket exists. Both artifacts live in the disposable route
    # workdir. CEC_FR_USE_DISPLAY=1 opts a Linux desktop dev back into the visible window.
    if sys.platform.startswith("linux") and shutil.which("xvfb-run") and os.environ.get("CEC_FR_USE_DISPLAY") != "1":
        pid = os.getpid()
        server_num = 1000 + (pid % 50000)
        auth_path = os.path.join(os.path.abspath(workdir or _TMP),
                                 ".cec-fr-xauth-%d" % pid)
        return ["xvfb-run", "-a", "-n", str(server_num),
                "-f", auth_path] + base
    return base

# ---------------------------------------------------------------------------
# Freerouting release metadata (FR-01: version-parametric, hash-pinned)
# ---------------------------------------------------------------------------
# The active version resolves from $CEC_FR_VERSION at import (the ledger manifest reads
# cec_fr.FR_VERSION, so an env override is automatically an AM-03 epoch boundary in every
# decision log). The DEFAULT stays the banked-baseline pin until the FR-01 migration gate
# passes on the successor.
# DEFAULT FLIPPED to the CEC seed fork (owner directive 2026-07-14: "apply it so we
# stop using stock now"). Unflagged behavior is byte-identical to stock 1.7.0
# (ops/README-fr-fork.md leg 0b) and the seed axis is additionally OPT-IN via
# CEC_FR_SEED_AXIS=1 (see run_freerouting), so this flip changes NO route anywhere
# until a consumer opts in (the wave does). Version change = an AM-03 epoch (the
# ledger manifest carries fr_version). SB-08 golden state at the flip, measured
# 2026-07-14: RED-PENDING for PRE-EXISTING owner-gated reasons (item-3a
# CEC_GOLDEN_SYNTH re-freeze) -- stock 1.7.0 and this fork produce IDENTICAL
# golden metrics to the decimal (kelvin/unconn/drc/thermal; only elapsed_s
# differs), logs build/golden-{stock-control,cec1-flip2}.log.
FR_VERSION = os.environ.get("CEC_FR_VERSION", "1.7.0-cec3")  # cec3 = cec2 + DSN reader refill (2026-08-04)

# Hash pins (sha256). The 2.2.4 jar digest matches the official GitHub release-asset
# digest (verified 2026-06-10); 1.7.0 is the hash of the jar the banked baseline ran on.
# 2.2.4 is compiled for Java 25 (class-file 69) -- Debian trixie (the routing container)
# tops out at openjdk-21, so on a <25 JVM the linux-x64 jpackage APP-IMAGE (bundled JRE,
# also hash-pinned) is used instead of `java -jar`.
FR_RELEASES = {
    "1.7.0": {
        "jar_sha256": "e6c5db33792a00f99799b1113bb9f5e1576731f885b069da8850520528f7ef8f",
        "min_java": 17,
    },
    # the CEC seed-patched fork (A5, 2026-07-08): v1.7.0 + scripts/patches/
    # freerouting-1.7.0-cec-seed.patch -- adds -seed <long> (per-pass net-order
    # shuffle: same seed = byte-identical, different seeds = distinct routes,
    # no-seed = byte-identical to stock). LOCAL-ONLY (no download URL): resolved
    # from CEC_FREEROUTING_JAR or the durable copies (/mnt/e/toolchain/fr-fork/,
    # build/fr-fork/); rebuildable from the committed patch (ops/README-fr-fork.md).
    "1.7.0-cec1": {
        "jar_sha256": "375e36b8ee347c57127670c06aeaa650d562a0365b0a4ed6dd3634d215f103b1",
        "min_java": 17,
        "local_paths": ("/mnt/e/toolchain/fr-fork/freerouting-1.7.0-cec1.jar",
                        "build/fr-fork/freerouting-1.7.0-cec1.jar"),
        "supports_seed": True,
    },
    # cec2 (2026-07-14, owner "do the surgery"): cec1 + three OPT-IN flags (unflagged
    # still byte-identical to stock, the fork's standing guarantee): -noecho (no
    # protect-wire SES echo -- retires reconcile's ~130 echo strips/route), -maxstall
    # <k> (abort after k no-improvement passes; stock's own detector needs 200+ passes
    # of bookkeeping), -progress (one CEC_PASS line/pass on stdout = the stage-0
    # pre-kill contract). Patch: scripts/patches/freerouting-1.7.0-cec2.patch
    # (cumulative over v1.7.0); rebuild per ops/README-fr-fork.md.
    "1.7.0-cec2": {
        "jar_sha256": "149cebd88169be77f5ddc7e1d50284451204f10c088e5d7380859ab0395b7ce5",
        "min_java": 17,
        "local_paths": ("/mnt/e/toolchain/fr-fork/freerouting-1.7.0-cec2.jar",
                        "build/fr-fork/freerouting-1.7.0-cec2.jar"),
        "supports_seed": True,
        "supports_noecho": True,
        "supports_maxstall": True,
        "supports_progress": True,
    },
    # cec3 (2026-08-04): cec2 plus a position-safe refill for the hand-written
    # Specctra string reader. Upstream's generated DFA can grow its buffer, but
    # next_string() bypassed that path and crashed at exactly 512 KiB on the
    # fully guarded six-layer Hub DSN. The incremental patch is applied after
    # cec2 by scripts/build-freerouting-cec3.sh. The hash below is reproduced
    # with Ubuntu's OpenJDK 17.0.19 toolchain.
    "1.7.0-cec3": {
        "jar_sha256": "202136e7e73d5aa3e2a852bab186f71b67289a4068dee0804cb9c7b2efd8c7f7",
        "min_java": 17,
        "local_paths": ("/mnt/e/toolchain/fr-fork/freerouting-1.7.0-cec3.jar",
                        "build/fr-fork/freerouting-1.7.0-cec3.jar"),
        "supports_seed": True,
        "supports_noecho": True,
        "supports_maxstall": True,
        "supports_progress": True,
    },
    "2.2.4": {
        "jar_sha256": "f5ed374182900ccc78e473518bbb9f6b869f4a07159495f663a76f52bb10523b",
        "min_java": 25,
        "appimage_zip": "freerouting-2.2.4-linux-x64.zip",
        "appimage_zip_sha256": "d712dd0dc1f51c8bab4868d8435d90e8cbba00e0c4bab45837334b17b382578f",
        "appimage_launcher": "freerouting-2.2.4-linux-x64/bin/freerouting",
    },
}

_FR_RELEASE_BASE = "https://github.com/freerouting/freerouting/releases/download"


def _jar_url(version=None):
    v = version or FR_VERSION
    return f"{_FR_RELEASE_BASE}/v{v}/freerouting-{v}.jar"


def _jar_cache(version=None):
    v = version or FR_VERSION
    return os.path.expanduser(f"~/.cache/cec/freerouting-{v}.jar")


def _jar_tmp_candidates(version=None):
    """Extra known-location candidates (checked, never required): the Linux convention
    path and a jar dropped in the OS temp dir. isfile()-probed, harmless when absent."""
    v = version or FR_VERSION
    return [f"/tmp/fr_{v}.jar", os.path.join(_TMP, f"fr_{v}.jar")]


# Back-compat module constants (consumers may read these; derived from the active pin).
FR_JAR_URL = _jar_url()
_FR_JAR_CACHE = _jar_cache()
_FR_JAR_TMP, _FR_JAR_TMP2 = _jar_tmp_candidates()


def _sha256(path, chunk=1 << 20):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _verify_pin(path, expected, what):
    """Hard-fail on a hash-pin mismatch for a CONVENTIONAL location (cache/tmp/download).
    Explicit user overrides (path arg / $CEC_FREEROUTING_JAR) are trusted instead."""
    got = _sha256(path)
    if got != expected:
        raise RuntimeError(
            f"cec_fr: sha256 mismatch for {what} at {path!r}\n"
            f"  expected {expected}\n  got      {got}\n"
            f"  Delete the file and re-run (it will be re-downloaded and re-verified)."
        )


def _java_executable():
    """Resolve the Java runtime used by both wrappers and direct API calls."""
    override = os.environ.get("CEC_JAVA")
    if override:
        return override
    on_path = shutil.which("java")
    if on_path:
        return on_path
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidate = os.path.join(
            java_home, "bin", "java.exe" if os.name == "nt" else "java")
        if os.path.isfile(candidate):
            return candidate

    import glob as _glob
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    exe = "java.exe" if os.name == "nt" else "java"
    patterns = [
        os.path.join(repo, "build", "fr-fork", "jdk-dist", "**", "bin", exe),
    ]
    if os.name == "nt":
        for root in filter(None, (os.environ.get("ProgramFiles"),
                                  os.environ.get("ProgramFiles(x86)"))):
            patterns.extend((
                os.path.join(root, "Eclipse Adoptium", "**", "bin", exe),
                os.path.join(root, "Java", "**", "bin", exe),
                os.path.join(root, "Microsoft", "jdk*", "bin", exe),
                os.path.join(root, "Zulu", "**", "bin", exe),
            ))
    candidates = sorted({path for pattern in patterns
                         for path in _glob.glob(pattern, recursive=True)
                         if os.path.isfile(path)}, reverse=True)
    return candidates[0] if candidates else "java"


def _java_major(executable=None):
    """Major version of the selected Java executable, or 0 if unusable."""
    java = executable or _java_executable()
    try:
        r = subprocess.run([java, "-version"], capture_output=True, text=True,
                           timeout=30)
        out = r.stderr + r.stdout
        import re as _re
        m = _re.search(r'version "(\d+)', out)
        return int(m.group(1)) if m else 0
    except Exception:
        return 0


def ensure_appimage(version=None):
    """Return the launcher path of the hash-pinned jpackage app-image (bundled JRE) for
    *version*, downloading + extracting the official linux-x64 zip into ~/.cache/cec on
    first use. Linux-only (the jpackage runtime ships no standalone bin/java; the native
    launcher is the entry point and passes CLI args straight through to the app)."""
    v = version or FR_VERSION
    rel = FR_RELEASES.get(v) or {}
    zip_name = rel.get("appimage_zip")
    if not zip_name:
        raise RuntimeError(f"cec_fr.ensure_appimage: no app-image pinned for FR {v}")
    cache_dir = os.path.expanduser("~/.cache/cec")
    launcher = os.path.join(cache_dir, rel["appimage_launcher"])
    if os.path.isfile(launcher) and os.access(launcher, os.X_OK):
        return launcher
    os.makedirs(cache_dir, exist_ok=True)
    zip_path = os.path.join(cache_dir, zip_name)
    if not os.path.isfile(zip_path):
        url = f"{_FR_RELEASE_BASE}/v{v}/{zip_name}"
        print(f"[cec_fr] Downloading Freerouting {v} app-image from {url} ...", file=sys.stderr)
        urllib.request.urlretrieve(url, zip_path)
    _verify_pin(zip_path, rel["appimage_zip_sha256"], f"FR {v} app-image zip")
    import zipfile
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(cache_dir)
        for info in z.infolist():                       # restore exec bits (zipfile drops them)
            mode = (info.external_attr >> 16) & 0o7777
            if mode:
                try:
                    os.chmod(os.path.join(cache_dir, info.filename), mode)
                except OSError:
                    pass
    if not (os.path.isfile(launcher) and os.access(launcher, os.X_OK)):
        raise RuntimeError(f"cec_fr.ensure_appimage: launcher missing after extract: {launcher!r}")
    return launcher


# ---------------------------------------------------------------------------
# ensure_jar
# ---------------------------------------------------------------------------
def ensure_jar(path: str | None = None, version: str | None = None) -> str:
    """Return a path to the Freerouting jar for *version* (default: FR_VERSION).

    Resolution order:
      1) ``path`` arg if given and exists                    (explicit -> trusted, hash logged)
      2) $CEC_FREEROUTING_JAR env var if set and exists      (explicit -> trusted, hash logged)
      3) /tmp/fr_<v>.jar / <tempdir>/fr_<v>.jar if present   (conventional -> pin-verified)
      4) ~/.cache/cec/freerouting-<v>.jar if present         (conventional -> pin-verified)
      5) download to ~/.cache/cec and pin-verify

    A hash-pin mismatch on a conventional location or fresh download is a hard error
    (FR-01: the jar is vendored BY HASH; a silent swap would corrupt the epoch).
    Raises RuntimeError if all options fail.
    """
    v = version or FR_VERSION
    pin = (FR_RELEASES.get(v) or {}).get("jar_sha256")
    explicit = []
    if path:
        explicit.append(path)
    env_jar = os.environ.get("CEC_FREEROUTING_JAR")
    if env_jar:
        explicit.append(env_jar)
    for c in explicit:
        if c and os.path.isfile(c):
            if pin:
                print(f"[cec_fr] explicit jar override {c!r} sha256={_sha256(c)[:16]}... "
                      f"(pin for {v}: {pin[:16]}...)", file=sys.stderr)
            return c

    # LOCAL-ONLY releases (the CEC fork): known durable paths, relative ones resolved
    # against the repo root; always pin-verified (never trusted like an explicit arg).
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for c in (FR_RELEASES.get(v) or {}).get("local_paths", ()):
        cc = c if os.path.isabs(c) else os.path.join(_root, c)
        if os.path.isfile(cc):
            if pin:
                _verify_pin(cc, pin, f"FR {v} jar (local)")
            return cc

    jar_cache = _jar_cache(v)
    for c in _jar_tmp_candidates(v) + [jar_cache]:
        if c and os.path.isfile(c):
            if pin:
                _verify_pin(c, pin, f"FR {v} jar")
            return c

    # Download to the cache location
    url = _jar_url(v)
    os.makedirs(os.path.dirname(jar_cache), exist_ok=True)
    print(f"[cec_fr] Downloading Freerouting {v} jar from {url} ...", file=sys.stderr)
    try:
        urllib.request.urlretrieve(url, jar_cache)
    except Exception as exc:
        raise RuntimeError(
            f"cec_fr: Could not download Freerouting jar from {url}: {exc}\n"
            f"  Place the jar manually at one of: {_jar_tmp_candidates(v)[0]}, {jar_cache}"
        ) from exc
    if not os.path.isfile(jar_cache):
        raise RuntimeError(
            f"cec_fr: Download appeared to succeed but {jar_cache} is missing"
        )
    if pin:
        _verify_pin(jar_cache, pin, f"FR {v} jar (fresh download)")
    return jar_cache


# ---------------------------------------------------------------------------
# export_dsn
# ---------------------------------------------------------------------------
def plane_layers(board) -> list:
    """Copper layers that carry a PLANE: any zone whose outline bbox covers more than
    half the board outline bbox. Board-derived, no per-board config -- the EPS/PCIe
    In1 'GND' plane is detected; the Hub's In2 (a deliberate slow-signal ROUTING layer)
    is not, because no board-sized zone lives on it."""
    bb = board.GetBoardEdgesBoundingBox()
    barea = max(1, bb.GetWidth()) * max(1, bb.GetHeight())
    out = []
    for z in board.Zones():
        if z.GetIsRuleArea():
            continue
        zb = z.GetBoundingBox()
        if (zb.GetWidth() * zb.GetHeight()) / barea < 0.5:
            continue
        for lid in z.GetLayerSet().CuStack():
            name = board.GetLayerName(lid)
            if name not in out:
                out.append(name)
    return out


PIPELINE_POUR_PREFIXES = (
    "slab:", "overunder:", "pourfirst:", "pourplan:", "patch:", "manifold:",
    "orthofill:",
)


def _pipeline_power_pickup_nets(board, power_pours=()):
    """Explicit rail-net scope for post-cleanup generated-pickup repair.

    Dedicated routes can receive their pipeline pours in either of two ways:
    as ``power_pours`` passed to :func:`import_ses`, or already materialized on
    the source board.  The latter is the Hub flow.  Looking only at the import
    argument silently reduced its cleanup scope to GND, leaving a POFV dangling
    whenever the nowhere reaper removed that rail's last supporting island.

    Pipeline zone names are the ownership marker already used by router
    reservation and nowhere-zone cleanup.  Reuse that marker here; arbitrary
    hand-authored signal zones and vias never enter the discovery scope.
    """
    nets = {str(p.get("net")) for p in (power_pours or ())
            if p.get("net")}
    for zone in board.Zones():
        try:
            if zone.GetIsRuleArea():
                continue
            name = str(zone.GetZoneName() or "")
            net = str(zone.GetNetname() or "")
        except (AttributeError, TypeError, ValueError):
            continue
        if net and name.startswith(PIPELINE_POUR_PREFIXES):
            nets.add(net)
    nets.add("GND")
    return nets


def laid_pipeline_pour_keepouts(board_path):
    """Return router hints for actual pipeline-owned pours on signal layers.

    These zones are already materialized before a dedicated route, so an
    import-time pour list cannot reserve them.  Convert their saved outlines to
    layer-scoped rule-area hints before DSN export.  Dedicated plane/power
    layers are excluded by the fabrication profile's routing-layer policy.
    """
    board = pcbnew.LoadBoard(board_path)
    allowed = set(_fab.routing_layers(
        board, hint=os.environ.get("CEC_THERMAL_BOARD_HINT", board_path)))
    hints = []
    for index, zone in enumerate(board.Zones()):
        if zone.GetIsRuleArea():
            continue
        name = zone.GetZoneName() or ""
        if not name.startswith(PIPELINE_POUR_PREFIXES):
            continue
        for layer_id in zone.GetLayerSet().CuStack():
            layer = board.GetLayerName(layer_id)
            if layer not in allowed:
                continue
            outline = zone.Outline()
            for contour_index in range(outline.OutlineCount()):
                contour = outline.Outline(contour_index)
                polygon = [(contour.CPoint(k).x / MM,
                            contour.CPoint(k).y / MM)
                           for k in range(contour.PointCount())]
                if len(polygon) < 3:
                    continue
                holes = []
                for hole_index in range(outline.HoleCount(contour_index)):
                    contour_hole = outline.Hole(contour_index, hole_index)
                    hole = [(contour_hole.CPoint(k).x / MM,
                             contour_hole.CPoint(k).y / MM)
                            for k in range(contour_hole.PointCount())]
                    if len(hole) >= 3:
                        holes.append(hole)
                hints.append({
                    "name": "laid-pour:%d:%d:%s:%s"
                            % (index, contour_index, layer, name),
                    "polygon": polygon,
                    "holes": holes,
                    "layers": (layer,),
                })
    return hints


def _dsn_force_power_layers(dsn_path: str, layer_names) -> list:
    """LAYER POLICY (owner-ratified 2026-06-11, the FR-04 plane-carving finding): mark the
    named layers ``(type power)`` in the exported DSN so Freerouting EXCLUDES them from
    signal routing. pcbnew exports plane layers as ``(type signal)`` whenever the layer is
    a plain copper layer, and FR then happily routes signals THROUGH the ground plane
    (measured: 61.7mm of /I2C_SDA on the EPS GND plane), carving return-path slots the
    corpus rule ``gnd-plane-continuity`` forbids. Returns the list actually rewritten."""
    import re
    if not layer_names:
        return []
    with open(dsn_path, "r", encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    done = []
    for name in layer_names:
        # Specctra tokens may be bare or quoted.  More importantly, callers
        # must pass the board-visible layer alias (for example ``PWR``), not
        # KiCad's canonical ``In3.Cu`` name.  Matching both token forms keeps
        # this primitive useful for aliases containing spaces as well.
        token = r'(?:"' + re.escape(name) + r'"|' + re.escape(name) + r')'
        pat = re.compile(r"(\(layer\s+" + token
                         + r"\s*\(\s*type\s+)signal(\s*\))")
        text, n = pat.subn(r"\1power\2", text)
        if n:
            done.append(name)
    if done:
        with open(dsn_path, "w", encoding="utf-8") as handle:
            handle.write(text)
    return done


def kelvin_sense_pins(board, *, kelvin_pairs=None, max_ic_mm=None) -> set:
    """The DSN pin tokens (``"<ref>-<pad>"``) of the current-sense IC INPUT pads (IN+/IN-) that the
    GENERATIVE four-wire tap (:func:`synthesize_kelvin_taps`) owns -- i.e. the pads whose ONLY copper
    connection must be the inner-edge shunt tap, never an FR-routed wire to the cable connector.

    For each Kelvin pair (``*_HI``/``*_LO``) the 2-pad straddle shunt is found, and on each net the
    IN+/IN- pad (by PIN FUNCTION, _SENSE_INPAD: INA238/228 pad 10/9, INA181 pad 3/4) of every seated
    current-sense IC (``INA`` in value, not the shunt) within *max_ic_mm* of the shunt is collected.
    This is the EXACT same selection synthesize_kelvin_taps uses, so the FR exclusion and the post-route
    tap agree by construction: every pad removed here is re-connected by the tap (or, if the tap is
    foreign-guard-REFUSED, the pad stays honestly UNCONNECTED -> the gate fails -> re-place; it is NEVER
    papered over by an FR connector wire, which is the kelvin-from-connector bug this exclusion fixes).

    NOTE: the INA238/228 Vbus pad (8, on the _LO net) is a high-impedance VOLTAGE tap, NOT a Kelvin
    current-sense input, so it is deliberately left in the net for FR to route normally. Returns the set
    of pin tokens; empty (no-op) on a board with no 2-pad straddle shunt / no seated INA (Hub, filtered
    12VHPWR lanes)."""
    from collections import defaultdict
    names = {n.GetNetname() for n in board.GetNetInfo().NetsByNetcode().values() if n.GetNetname()}
    if kelvin_pairs is None:
        kelvin_pairs = _board_kelvin_pairs(board)
    force_nets = {n for pr in kelvin_pairs for n in pr}
    pads_by_net = defaultdict(list)
    padcount = {}
    for fp in board.GetFootprints():
        padcount[fp.GetReference()] = fp.GetPadCount()
        for p in fp.Pads():
            nn = p.GetNetname()
            if nn in force_nets:
                pads_by_net[nn].append((fp.GetReference(), p, fp))
    out = set()
    for hi, lo in kelvin_pairs:
        refs_hi = {r for r, _, _ in pads_by_net.get(hi, [])}
        refs_lo = {r for r, _, _ in pads_by_net.get(lo, [])}
        shunt_refs = {r for r in (refs_hi & refs_lo) if padcount.get(r, 0) == 2}
        if not shunt_refs:
            continue
        sh = sorted(shunt_refs)[0]
        sh_pos = None
        for r, p, _fp in pads_by_net.get(hi, []) + pads_by_net.get(lo, []):
            if r == sh:
                sh_pos = p.GetPosition()
                break
        for net, role in ((hi, "HI"), (lo, "LO")):
            for r, p, fp in pads_by_net.get(net, []):
                if r == sh or "INA" not in (fp.GetValue() or "").upper():
                    continue
                want = _sense_in_pad(fp, role)
                if want is not None and p.GetPadName() != want:
                    continue                                  # not the IN+/IN- pad of a known part
                if sh_pos is not None:
                    d = math.hypot((p.GetPosition().x - sh_pos.x) / MM,
                                   (p.GetPosition().y - sh_pos.y) / MM)
                    # UNCONDITIONAL by default (escalated review round 4, 2026-07-08): the
                    # contract is 'sense inputs are tap-owned, NEVER FR-routed' -- a slid
                    # seat at 8mm escaped the old 6mm radius and FR wired it to the force
                    # net CROSS-FACE (caught by the sense-side gate). Distance is the TAP
                    # synthesizer's quality concern (it refuses far ICs honestly), not the
                    # exclusion's. A radius applies only when explicitly passed.
                    if max_ic_mm is not None and d > max_ic_mm:
                        continue                              # too far to tap -> leave to FR (don't strand)
                out.add(f"{r}-{p.GetPadName()}")
    return out


def sensec_force_connector_pins(board, *, kelvin_pairs=None) -> set:
    """The DSN pin tokens (``"<ref>-<pad>"``) of the CABLE-CONNECTOR force pins (J_IN / J_OUT THT pads)
    on each high-current SENSEC net that ALSO gets a post-route FORCE POUR -- i.e. the pads whose
    connector<->shunt connection is the job of :func:`add_power_pours`, NOT of an FR-routed wire.

    THE INEFFICIENCY THIS FIXES (owner-caught 2026-06-30): the connector force pins sit on the same
    ``*_HI``/``*_LO`` net as the shunt, so Freerouting must satisfy their connectivity -- and with the
    NOTCHED corridor keepout active (:func:`corridor_keepouts`, ``DoNotAllowTracks`` over the pour box)
    FR cannot route connector->shunt THROUGH the reserved corridor, so it DETOURS the force wire AROUND
    it through the cramped sense row. On the congested 3-port that detour exploded to ~80 redundant force
    tracks (~253mm) -- copper the F.Cu pour was going to lay anyway -- clogging the channel and pushing
    foreign signals across the pours. Removing the connector force pins from the DSN makes FR LEAVE the
    connector->shunt force path entirely to the pour (which fills the reserved corridor solid: the keepout
    is ``block_fills=False``), freeing the channel. The exact analog of the kelvin exclusion
    (:func:`kelvin_sense_pins`), but for the FORCE half of the shared shunt pad.

    SURGICAL by design: ONLY the cable-connector THT pads are dropped. The shunt's OWN pads, the §6.13
    INA181 detection-tap pads, and the §6.8 INA238 Kelvin/Vbus pads all stay on the net, so FR still
    routes detection (shunt->INA181) and the post-route Kelvin tap is untouched -- the detection and
    Kelvin paths are NOT broken, only the redundant connector->shunt force copper is.

    SELF-GATING (matches :func:`derive_power_pours` exactly, so a pin is dropped iff a pour will reconnect
    it): a net qualifies only when its pair has a 2-pad straddle shunt AND the net carries at least one THT
    pad (the cable connector). A board with no straddle shunt / no THT cable connector (Hub, filtered
    12VHPWR lanes) yields the empty set -> no-op. Returns the set of pin tokens."""
    from collections import defaultdict
    names = {n.GetNetname() for n in board.GetNetInfo().NetsByNetcode().values() if n.GetNetname()}
    if kelvin_pairs is None:
        kelvin_pairs = _board_kelvin_pairs(board)
    force_nets = {n for pr in kelvin_pairs for n in pr}
    pads_by_net = defaultdict(list)
    padcount = {}
    for fp in board.GetFootprints():
        padcount[fp.GetReference()] = fp.GetPadCount()
        for p in fp.Pads():
            nn = p.GetNetname()
            if nn in force_nets:
                pads_by_net[nn].append((fp.GetReference(), p))
    out = set()
    for hi, lo in kelvin_pairs:
        refs_hi = {r for r, _ in pads_by_net.get(hi, [])}
        refs_lo = {r for r, _ in pads_by_net.get(lo, [])}
        # the 2-pad straddle shunt -> a real Kelvin force corridor (same rule derive_power_pours uses)
        if not {r for r in (refs_hi & refs_lo) if padcount.get(r, 0) == 2}:
            continue
        for net in (hi, lo):
            entries = pads_by_net.get(net, [])
            # only nets with a THT cable connector get a force pour (derive_power_pours' has_tht gate)
            tht = [(r, p) for r, p in entries if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]
            if not tht:
                continue
            for r, p in tht:
                out.add(f"{r}-{p.GetPadName()}")
    # SINGLE-PIN TAP EXEMPTION (2026-07-19, the /FAN_12V root-close): the drop
    # contract is "a pin is dropped iff a pour/lay will reconnect it" -- true for
    # CABLE connectors (J_IN/J_OUT/J3/J4 carry >=2 force-net THT pads per ref and
    # sit inside the pour/lane geometry), FALSE for a single-pin tap header (the
    # 12vhpwr J2 fan feed: ONE force pad, outside every pour region -- excluding
    # it made the net uncompletable by FR on every wave, measured). A ref with
    # exactly one force-net THT pad keeps that pin routable.
    ref_force_tht = defaultdict(int)
    for tok in out:
        ref_force_tht[tok.rsplit("-", 1)[0]] += 1
    out = {tok for tok in out if ref_force_tht[tok.rsplit("-", 1)[0]] >= 2}
    return out


def _dsn_exclude_pins(dsn_path: str, pins) -> int:
    """Remove the given ``"<ref>-<pad>"`` pin tokens from EVERY ``(net ... (pins ...))`` list in the
    exported DSN so Freerouting does NOT route those pads. A pad belongs to exactly one net, so a token
    is globally unique -- a global whole-token removal is safe and net-agnostic. The de-netted pad keeps
    its real net in the .kicad_pcb (only the DSN is edited); FR treats it as a no-net obstacle and leaves
    it for the post-route generative tap. Returns the number of token occurrences removed."""
    import re
    if not pins:
        return 0
    with open(dsn_path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    removed = 0
    for tok in pins:
        # whole-token match: not preceded/followed by a word char or '-' (so 'U10-10' != inside 'U10-100')
        pat = re.compile(r"(?<![\w-])" + re.escape(tok) + r"(?![\w-])")
        text, n = pat.subn("", text)
        removed += n
    if removed:
        # tidy the gaps the removals leave inside (pins ... ) so the file stays clean s-expr
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"\(pins +", "(pins ", text)
        text = re.sub(r" +\)", ")", text)
        with open(dsn_path, "w", encoding="utf-8") as f:
            f.write(text)
    return removed


def plane_tht_exclusion_nets(board, min_fill_ratio=0.5):
    """Nets with a genuinely plane-sized filled zone.

    A routed-object corridor can span most of a board while occupying only a
    few percent of its copper area. Classifying by zone bounding box made such
    rails look like planes and removed every THT pin from the router even when
    the sparse fill did not connect them. Judge actual saved fill area instead.
    """
    bb = board.GetBoardEdgesBoundingBox()
    board_area = max(1, bb.GetWidth()) * max(1, bb.GetHeight())
    nets = set()
    for zone in board.Zones():
        if zone.GetIsRuleArea() or not zone.GetNetname():
            continue
        try:
            filled_area = int(zone.GetFilledArea())
        except Exception:                               # noqa: BLE001
            filled_area = 0
        if filled_area / board_area >= float(min_fill_ratio):
            nets.add(zone.GetNetname())
    return nets


def filled_tht_exclusion_pins(board):
    """THT pins already connected by real filled inner-layer copper.

    Plane-sized-net classification is useful for reporting, but is the wrong
    granularity for routing policy. A sparse routed-object rail may legitimately
    cover three connector pins while leaving a fourth pin on the same net
    outside its copper. Exclude only the individual pins whose centres are in
    saved same-net fill on an inner copper layer. This preserves routability for
    every uncovered THT pin while avoiding redundant surface routes to barrels
    that already pierce their rail or ground plane.

    Returns ``{dsn_pin_token: net_name}`` so callers can audit both the exact
    excluded pins and the affected nets.
    """
    inner_layers = set(board.GetEnabledLayers().CuStack())
    inner_layers.discard(pcbnew.F_Cu)
    inner_layers.discard(pcbnew.B_Cu)
    filled = {}
    for zone in board.Zones():
        if zone.GetIsRuleArea() or not zone.GetNetname():
            continue
        for layer in zone.GetLayerSet().CuStack():
            if layer not in inner_layers:
                continue
            try:
                poly = zone.GetFilledPolysList(layer)
            except Exception:                           # noqa: BLE001
                continue
            if poly and poly.OutlineCount() > 0:
                filled.setdefault(zone.GetNetname(), []).append(poly)

    pins = {}
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            net = pad.GetNetname()
            pad_reach = min(pad.GetSize().x, pad.GetSize().y) // 2
            if (not net or pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD
                    or not any(poly.Collide(pad.GetPosition(), pad_reach)
                               for poly in filled.get(net, ()))):
                continue
            pins[f"{footprint.GetReference()}-{pad.GetPadName()}"] = net
    return pins


def export_dsn(board_path: str, dsn_path: str, *, plane_to_power: bool | None = None) -> str:
    """Load *board_path* with pcbnew and call ExportSpecctraDSN(board, dsn_path).

    plane_to_power (default ON; env CEC_FR_PLANE_POLICY=0 disables): after export,
    detected plane layers are rewritten ``(type power)`` so FR cannot route signals
    through them (see _dsn_force_power_layers).

    Returns *dsn_path*.  Raises RuntimeError if the export returns False or the
    output file is missing/empty.
    """
    if plane_to_power is None:
        plane_to_power = os.environ.get("CEC_FR_PLANE_POLICY", "1") != "0"
    # PROJECT BIND (owner width defect 2026-07-15, measured): pcbnew's settings
    # manager binds the FIRST project loaded in a process; a later LoadBoard of a
    # different board (route_once's hinted copy) silently loses ITS sidecar's
    # netclasses, so the DSN exports class-less and FR routes everything at the
    # 0.2 default. Explicitly activating the board's own .kicad_pro before load
    # restores the class rules (verified: DSN carries (class Power (rule (width
    # 1000))) same-process only with this call). Fail-safe: no sidecar = no-op.
    _pro = board_path[:-len(".kicad_pcb")] + ".kicad_pro"
    if os.path.isfile(_pro):
        try:
            pcbnew.GetSettingsManager().LoadProject(_pro)
        except Exception as _e:                                # noqa: BLE001
            print(f"[cec_fr] project bind failed ({_e}) -- DSN may lose netclasses",
                  flush=True)
    board = pcbnew.LoadBoard(board_path)
    ok = pcbnew.ExportSpecctraDSN(board, dsn_path)
    if not ok:
        raise RuntimeError(
            f"cec_fr.export_dsn: ExportSpecctraDSN returned False for {board_path!r}"
        )
    if not os.path.isfile(dsn_path) or os.path.getsize(dsn_path) == 0:
        raise RuntimeError(
            f"cec_fr.export_dsn: DSN file missing or empty after export: {dsn_path!r}"
        )
    if plane_to_power:
        rewritten = _dsn_force_power_layers(dsn_path, plane_layers(board))
        if rewritten:
            print(f"[cec_fr] layer policy: plane layer(s) {rewritten} -> (type power) "
                  f"(FR signal routing excluded)", file=sys.stderr)
    # KELVIN POLICY (owner directive 2026-06-28, the kelvin-from-connector fix): the current-sense IC
    # IN+/IN- pads sit on the high-current SENSEC net (same net as the cable connector + shunt). If FR
    # is allowed to route them it satisfies their connectivity by wiring them to the NEAREST net point
    # -- the connector -- so the sense taps the connector->shunt copper (+ its IR drop / contact R) and
    # the sense wire carries current: NOT a four-wire Kelvin. Remove those pads from the DSN net so FR
    # leaves them alone; the post-route synthesize_kelvin_taps is then their ONLY connection (the §6.8
    # inner-edge tap). Env kill-switch CEC_KELVIN_FR_EXCLUDE=0 reverts (A/B). Self-gating no-op on a
    # board with no straddle shunt / seated INA.
    if os.environ.get("CEC_KELVIN_FR_EXCLUDE", "1") != "0":
        sense_pins = kelvin_sense_pins(board)
        if sense_pins:
            n = _dsn_exclude_pins(dsn_path, sense_pins)
            print(f"[cec_fr] kelvin policy: excluded {len(sense_pins)} current-sense input pad(s) "
                  f"{sorted(sense_pins)} from FR routing ({n} DSN token(s) removed) -- the inner-edge "
                  f"tap is their only connection", file=sys.stderr)
    # FORCE-POUR-ONLY POLICY (owner directive 2026-06-30, the redundant-force-trace fix): leave the
    # cable connector<->shunt FORCE path entirely to the post-route pour. Without this, FR detours the
    # connector force connectivity AROUND the corridor keepout (it cannot route through the reserved
    # box), laying redundant connector->shunt copper the pour would carry anyway -- ~80 tracks on the
    # congested 3-port, clogging the sense row and pushing foreign onto the pours. Drop ONLY the
    # connector THT force pins (detection + Kelvin pads stay -> those taps still route); the post-route
    # add_power_pours then makes the connector->shunt connection. OPT-IN (default OFF), self-gating to
    # nets that have a force pour, so it is a safe no-op on a board without SENSEC pours. A/B kill-switch.
    if os.environ.get("CEC_SENSEC_FORCE_POUR_ONLY", "0") == "1":
        force_pins = sensec_force_connector_pins(board)
        if force_pins:
            n = _dsn_exclude_pins(dsn_path, force_pins)
            print(f"[cec_fr] force-pour-only policy: excluded {len(force_pins)} cable-connector force "
                  f"pin(s) {sorted(force_pins)} from FR routing ({n} DSN token(s) removed) -- the "
                  f"post-route power pour is their only connection to the shunt", file=sys.stderr)
    # PLANE-THT POLICY (owner catch 2026-07-24: FR routed a GND surface trace to
    # the M2 mezz mount -- a plated THT that pierces to the In1 plane natively;
    # the trace is useless copper crossing the fabric, and the class covers ANY
    # THT pad on a plane-carrying net. The plane fill is their connection at
    # import; SMD pads STAY routable (they need stitching/pickups). OPT-IN per
    # board (params plane_tht_exclude -> _oracle_env): default-off keeps the
    # frozen golden's DSN byte-identical.
    if os.environ.get("CEC_PLANE_THT_EXCLUDE", "0") == "1":
        _tht_by_pin = filled_tht_exclusion_pins(board)
        if _tht_by_pin:
            _tht = set(_tht_by_pin)
            _pnets = sorted(set(_tht_by_pin.values()))
            n = _dsn_exclude_pins(dsn_path, _tht)
            print(f"[cec_fr] plane-THT policy: excluded {len(_tht)} THT pad(s) on "
                  f"filled net(s) {_pnets} ({n} DSN token(s) removed) -- "
                  "saved inner-layer fill is their connection", file=sys.stderr)
    return dsn_path


# ---------------------------------------------------------------------------
# run_freerouting
# ---------------------------------------------------------------------------
def _plateau_floor_disables(best_togo, floor):
    """Plateau-floor semantics (probe 2026-07-23): a flat streak whose best togo
    sits AT/UNDER the floor is FR's normal terminal grind / rip-up phase, not a
    collapse.  This predicate identifies the recovery band; the caller grants a
    bounded number of streak windows before re-arming the kill. floor<=0 =
    feature off (historical behavior)."""
    return floor > 0 and best_togo <= floor


def _plateau_floor_grants_grace(best_togo, floor, used, limit):
    """Whether a low-togo plateau earns one more bounded streak window."""
    return (_plateau_floor_disables(best_togo, floor)
            and int(used) < max(0, int(limit)))


def _plateau_at_terminal_pass(pass_no, requested_passes, streak_window=1):
    """Return true only once the requested terminal pass is actually reached.

    Older logic treated the final *streak window* as terminal.  Combined with a
    low-togo recovery grace, that re-armed another flat window near the end and
    let a proven plateau consume almost the complete pass budget.  The SES needs
    protection only when Freerouting has reached the literal requested pass;
    before then a bounded plateau kill still saves real work. ``streak_window``
    remains accepted for API compatibility but no longer broadens the terminal
    range.
    """
    del streak_window
    return (pass_no is not None and
            int(pass_no) >= int(requested_passes))


def _kill_fr_tree(proc):
    """Kill the FR child AND its whole process group. On headless Linux the child
    is the `xvfb-run -a` WRAPPER, so a bare proc.kill() (or subprocess.run's own
    timeout kill) reaps only the wrapper and ORPHANS the java JVM underneath --
    measured 2026-07-19: 85 leaked JVMs (load avg ~90 on 18 cores) after a night
    of parallel-chain timeouts, each one churning CPU against a dead pipe.
    Requires the child to have been started with start_new_session=True (POSIX),
    which makes its pgid == its pid; falls back to plain kill otherwise/Windows."""
    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        proc.kill()
    except Exception:
        pass


def _xvfb_display_authority(cmd):
    """Return the isolated X display/auth pair carried by an xvfb-run command."""
    args = list(cmd or ())
    if not args or os.path.basename(str(args[0])) != "xvfb-run":
        return None
    try:
        display = ":%d" % int(args[args.index("-n") + 1])
        authority = str(args[args.index("-f") + 1])
    except (ValueError, IndexError, TypeError):
        return None
    return display, authority


def _fr_headless_exception_dialog(cmd):
    """Detect FreeRouting's otherwise invisible fatal Swing exception dialog.

    The legacy GUI exception handler can catch a worker exception, show a modal
    ``Exception Occurred`` JOptionPane under Xvfb, and leave the JVM alive
    forever.  From the caller that looks like a silent route until the full
    timeout.  Query only the private X server named in this invocation; failure
    to inspect it is non-fatal and falls back to the ordinary deadline.
    """
    display_auth = _xvfb_display_authority(cmd)
    if display_auth is None or not shutil.which("xwininfo"):
        return False
    display, authority = display_auth
    env = os.environ.copy()
    env.update({"DISPLAY": display, "XAUTHORITY": authority})
    try:
        probe = subprocess.run(
            ["xwininfo", "-root", "-tree"], env=env,
            capture_output=True, text=True, timeout=2, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return '"Exception Occurred"' in (probe.stdout or "")


def _raise_on_fr_headless_exception(proc, cmd, *, dsn_path, jar):
    """Fail a candidate immediately when its hidden GUI reports a fatal error."""
    if not _fr_headless_exception_dialog(cmd):
        return
    _kill_fr_tree(proc)
    raise RuntimeError(
        "cec_fr.run_freerouting: hidden Freerouting exception dialog "
        "detected under Xvfb; candidate rejected immediately "
        f"(dsn={dsn_path!r}, jar={jar!r})")


class _RestUnavailable(Exception):
    """REST service infra failure -> the caller falls back to the local jar, loudly.
    NEVER raised for a route VERDICT (timeout/plateau/FR-exit/SES-missing): those
    re-raise RuntimeError so wave/oracle semantics are identical REST or local."""


def _rest_base():
    """The CEC fork REST service base URL, or None for the local-jar path.
    CEC_FREEROUTING_URL points at scripts/cec_fr_server.py (the compose
    `freerouting` service since 2026-07-22 -- OUR fork jar behind a thin job
    API, NOT the official freerouting 2.x API image, which is a different
    router with measured blockers and a freerouting.app auth wall).
    CEC_FR_REST=0 force-disables REST even when the URL is set."""
    u = (os.environ.get("CEC_FREEROUTING_URL") or "").strip().rstrip("/")
    if not u or os.environ.get("CEC_FR_REST", "1") == "0":
        return None
    return u


def _run_freerouting_rest(base, dsn_path, ses_path, *, passes, opt_time, threads,
                          seed, timeout, version):
    """Route via the cec_fr_server job API. The server executes run_freerouting
    itself (same pinned fork jar, same env knobs -- forwarded allow-listed below),
    so with equal params the SES is byte-identical to a local run. Streams the
    job log through (CEC_PASS progress lines stay visible in pipeline logs).
    Raises _RestUnavailable on infra failure, RuntimeError on route verdicts."""
    import json as _json
    import base64 as _b64
    import urllib.error                                        # noqa: F401  (explicit)

    def _call(method, path, body=None, ctimeout=30):
        req = urllib.request.Request(base + path, method=method)
        data = None
        if body is not None:
            data = _json.dumps(body).encode()
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, data=data, timeout=ctimeout) as r:
                raw = r.read()
                if (r.headers.get("Content-Type") or "").startswith("text/plain"):
                    return raw.decode(errors="replace")
                return _json.loads(raw.decode() or "{}")
        except urllib.error.HTTPError as e:
            try:
                detail = _json.loads(e.read().decode() or "{}").get("error", "")
            except Exception:                                  # noqa: BLE001
                detail = ""
            raise _RestUnavailable(f"HTTP {e.code} {path}: {detail}") from e
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise _RestUnavailable(f"{type(e).__name__}: {e}") from e

    status = _call("GET", "/v1/system/status", ctimeout=10)
    srv_v = status.get("fr_version")
    if srv_v and srv_v != version:
        raise _RestUnavailable(f"server fr_version={srv_v} != requested {version} "
                               f"(epoch integrity: versions must match)")
    with open(dsn_path, "rb") as fh:
        dsn_b64 = _b64.b64encode(fh.read()).decode()
    env = {k: os.environ[k] for k in ("CEC_FR_SEED_AXIS", "CEC_FR_NOECHO",
                                      "CEC_FR_MAXSTALL", "CEC_FR_PLATEAU_KILL",
                                      "CEC_FR_PLATEAU_FLOOR")
           if k in os.environ}
    job = _call("POST", "/v1/jobs", body={
        "dsn_b64": dsn_b64, "name": os.path.basename(dsn_path),
        # FR names the SES session after the -do basename; sending ours lets the
        # server route under the SAME name -> REST and local SES are byte-identical
        "ses_name": os.path.basename(ses_path),
        "passes": int(passes), "opt_time": int(opt_time), "threads": int(threads),
        "seed": seed, "version": version, "timeout": int(timeout), "env": env})
    jid = job.get("id")
    if not jid:
        raise _RestUnavailable(f"job create returned {job!r}")

    queue_cap = float(os.environ.get("CEC_FR_REST_QUEUE_CAP") or 3600)
    t_post = time.monotonic()
    t_running = None
    log_off = 0
    try:
        while True:
            st = _call("GET", f"/v1/jobs/{jid}", ctimeout=15)
            # stream new log lines through (progress visibility == local path)
            if st.get("log_size", 0) > log_off:
                chunk = _call("GET", f"/v1/jobs/{jid}/log?offset={log_off}",
                              ctimeout=15)
                if isinstance(chunk, str) and chunk:
                    log_off += len(chunk.encode())
                    for ln in chunk.splitlines():
                        if ln.strip():
                            print(f"[fr-rest {jid[-8:]}] {ln}", flush=True)
            state = st.get("state")
            if state == "COMPLETED":
                pin = (FR_RELEASES.get(version) or {}).get("jar_sha256")
                got = st.get("jar_sha256")
                if pin and got and got != pin:
                    raise _RestUnavailable(
                        f"server routed with jar sha {got[:16]}... != pin "
                        f"{pin[:16]}... for {version} (epoch integrity)")
                out = _call("GET", f"/v1/jobs/{jid}/output", ctimeout=60)
                ses = _b64.b64decode(out.get("ses_b64") or "")
                if not ses:
                    raise _RestUnavailable("empty SES from COMPLETED job")
                with open(ses_path, "wb") as fh:
                    fh.write(ses)
                return ses_path
            if state == "FAILED":
                msg = st.get("error") or "job FAILED with no error message"
                if st.get("error_kind") == "route":
                    raise RuntimeError(msg)        # verdict: propagate, never fall back
                raise _RestUnavailable(msg)
            if state == "CANCELLED":
                raise _RestUnavailable("job cancelled server-side")
            now = time.monotonic()
            if state == "RUNNING" and t_running is None:
                t_running = now
            if t_running is not None and now - t_running > timeout + 60:
                _call("DELETE", f"/v1/jobs/{jid}", ctimeout=15)
                raise _RestUnavailable(
                    f"server blew the route deadline ({timeout}s + 60s grace) "
                    f"without its own timeout verdict -- unresponsive")
            if t_running is None and now - t_post > queue_cap:
                _call("DELETE", f"/v1/jobs/{jid}", ctimeout=15)
                raise _RestUnavailable(f"queued longer than {queue_cap:.0f}s "
                                       f"(CEC_FR_REST_QUEUE_CAP)")
            time.sleep(2.0)
    except (KeyboardInterrupt, SystemExit):
        try:
            _call("DELETE", f"/v1/jobs/{jid}", ctimeout=10)
        except _RestUnavailable:
            pass
        raise


def run_freerouting(
    dsn_path: str,
    ses_path: str,
    *,
    passes: int = 10,
    opt_time: int = 30,
    threads: int = 1,
    seed=None,          # accepted for forward-compat/logging; not a real FR 1.7.0 flag
    jar: str | None = None,
    workdir: str | None = None,
    timeout: int = 600,
    version: str | None = None,   # FR release to run (default: the FR_VERSION pin)
) -> str:
    """Run Freerouting (FR_VERSION pin, or *version*) and produce a .ses file.

    Invocation (see _fr_command for the per-platform form)::

        java -jar <jar> -de <dsn> -do <ses> -mp <passes> -oit <opt_time> -mt <threads>
        # on headless Linux this is wrapped in `xvfb-run -a`; on Windows/macOS java runs direct

    Run from *workdir* (a fresh mkdtemp in the OS temp dir if not given) so Freerouting's
    ``logs/`` directory never lands in the repo.

    Note: ``seed`` is accepted for API forward-compatibility and logged, but
    Freerouting 1.7.0 has no ``-seed`` flag.  Vary candidates via passes/opt_time/
    threads instead.

    Returns *ses_path*.  Raises RuntimeError (with captured stdout/stderr tail) if
    FR exits non-zero or the SES is missing/empty.
    """
    v = version or FR_VERSION

    # REST path (2026-07-22, owner-directed): when CEC_FREEROUTING_URL points at the
    # CEC fork job service (scripts/cec_fr_server.py), route THERE -- the server runs
    # this very function with the same pinned fork jar and forwarded env knobs, so
    # the SES is byte-identical for equal params. Infra failure falls back to the
    # local jar LOUDLY; a route VERDICT (timeout/plateau/FR-exit) re-raises
    # unchanged -- never double-routed.
    _base = _rest_base()
    if _base:
        try:
            return _run_freerouting_rest(_base, dsn_path, ses_path, passes=passes,
                                         opt_time=opt_time, threads=threads,
                                         seed=seed, timeout=timeout, version=v)
        except _RestUnavailable as e:
            print(f"[cec_fr] REST service unavailable ({e}) -- "
                  f"falling back to the LOCAL jar", file=sys.stderr, flush=True)

    jar = ensure_jar(jar, version=v)

    # Always route under /tmp to keep logs/ away from the repo.
    _own_workdir = workdir is None
    if _own_workdir:
        workdir = tempfile.mkdtemp(prefix="cec_fr_run_", dir=_TMP)

    _seed_ok = bool((FR_RELEASES.get(v) or {}).get("supports_seed"))
    if seed is not None and not _seed_ok:
        print(f"[cec_fr] note: seed={seed!r} logged (no -seed flag in FR {v})",
              file=sys.stderr)

    cmd = _fr_command(jar, dsn_path, ses_path, passes, opt_time, threads,
                      version=v, workdir=workdir)
    # SEED AXIS IS OPT-IN (CEC_FR_SEED_AXIS=1; 2026-07-14, the -cec1 default flip):
    # every historical caller passes seed=N habitually because it was INERT on stock
    # 1.7.0 -- activating it silently on the flip changed routes under them (measured:
    # the SB-08 golden regressed kelvin/unconn/thermal on its frozen bands the moment
    # the fork became default). Unflagged fork behavior is byte-identical to stock
    # (leg 0b), so with the axis off the flip is bit-safe everywhere; consumers that
    # WANT diversity (the wave) set the env explicitly.
    if (seed is not None and _seed_ok
            and os.environ.get("CEC_FR_SEED_AXIS", "0") == "1"):
        cmd += ["-seed", str(int(seed))]   # the A5 fork's real diversity axis
    _rel = FR_RELEASES.get(v) or {}
    # cec2 flags (2026-07-14). -noecho defaults ON where supported: the echoes it
    # suppresses are exactly the duplicates reconcile_locked_nets strips today, so
    # behavior is net-identical with less work (CEC_FR_NOECHO=0 restores the echo
    # for an A/B). -progress likewise ON (stdout-only; the runner captures it).
    # -maxstall is a route-BEHAVIOR knob (aborts stalled candidates early), so it
    # stays opt-in via CEC_FR_MAXSTALL=<k>; the wave sets it.
    if _rel.get("supports_noecho") and os.environ.get("CEC_FR_NOECHO", "1") == "1":
        cmd += ["-noecho"]
    if _rel.get("supports_progress"):
        cmd += ["-progress"]
    _stall = os.environ.get("CEC_FR_MAXSTALL", "")
    if _stall.isdigit() and int(_stall) > 0 and _rel.get("supports_maxstall"):
        cmd += ["-maxstall", _stall]

    run_kw = dict(cwd=workdir, capture_output=True, text=True, timeout=timeout)
    # cec2: FR's stdout is captured; re-emit the machine-readable CEC_ lines
    # (CEC_PASS / CEC_STALL_ABORT) so pipeline logs + the stage-0 pre-kill see them.
    if sys.platform == "win32":
        # Freerouting is a Java/Swing GUI app; on Windows (real desktop, no xvfb) its window
        # would pop to the foreground and steal focus from whatever you're doing. Ask Windows
        # to start it MINIMIZED and WITHOUT activation (SW_SHOWMINNOACTIVE) and with no console
        # window, so a batch route stays out of the way. (Belt-and-suspenders: set the user's
        # ForegroundLockTimeout so Windows refuses focus-steals outright -- see docs.)
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 7  # SW_SHOWMINNOACTIVE
        run_kw["startupinfo"] = si
        run_kw["creationflags"] = subprocess.CREATE_NO_WINDOW

    # EXTERNAL PLATEAU-KILL (2026-07-14, replaces the in-FR -maxstall experiment: the
    # in-jar abort left FR's improvement-bounded optimizer thrashing an incomplete
    # board to timeout, 900s vs 194s). CEC_FR_PLATEAU_KILL=<k> + a -progress-capable
    # jar: stream FR stdout, watch the CEC_PASS failed= counts, and KILL the JVM after
    # k consecutive passes with no improvement while failures remain. The kill is
    # CANDIDATE REJECTION (raises; route_once returns Candidate(ok=False)) -- a
    # plateaued candidate is a loser whose board we do not want; the win is the
    # wall-clock not spent finishing + optimizing garbage. Unset env = exactly the
    # blocking subprocess.run path below.
    _pk = os.environ.get("CEC_FR_PLATEAU_KILL", "")
    if (_pk.isdigit() and int(_pk) > 0
            and (FR_RELEASES.get(v) or {}).get("supports_progress")):
        _k = int(_pk)
        _pop_kw = {kk: vv for kk, vv in run_kw.items()
                   if kk not in ("capture_output", "text", "timeout")}
        # stderr MERGED into stdout (wave-13 stall forensic, 2026-07-15: a separate
        # stderr PIPE that nobody drains deadlocks the JVM once it fills 64KB; and a
        # timeout checked only when a line ARRIVES never fires on a silent child --
        # select() below enforces the deadline for real).
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True, bufsize=1,
                                start_new_session=(os.name == "posix"), **_pop_kw)
        # PLATEAU FLOOR (probe 2026-07-23): a togo-34 "plateau" on the hub,
        # killed by the streak rule, re-routed with the kill off to unconn 7 /
        # kelvin TRUE in 145s -- the best hub board ever; FR's rip-up phases go
        # flat-then-recover, so a flat streak at LOW togo is the normal terminal
        # grind, not a collapse. With CEC_FR_PLATEAU_FLOOR=<n>, a plateau whose
        # togo <= n earns a bounded number of extra streak windows (the board is
        # nearly routed -- worth a limited recovery attempt); after those windows
        # the kill is armed again. Above the floor it fires as before (the 24-pin's
        # true collapses sit flat at 190-230 from early passes). Default 0 = floor
        # off, exactly the historical behavior.
        _pfloor = 0
        _pfe = os.environ.get("CEC_FR_PLATEAU_FLOOR", "")
        if _pfe.isdigit():
            _pfloor = int(_pfe)
        _best, _streak, _killed, _lines = None, 0, False, []
        _graces_used = 0
        try:
            _grace_limit = max(0, int(os.environ.get(
                "CEC_FR_PLATEAU_GRACES", "1")))
        except ValueError:
            _grace_limit = 1
        _t0 = time.monotonic()
        import select as _select
        def _next_line():
            while True:
                if time.monotonic() - _t0 > timeout:
                    _kill_fr_tree(proc)
                    raise RuntimeError(
                        f"cec_fr.run_freerouting: timed out after {timeout}s "
                        f"(dsn={dsn_path!r}, jar={jar!r})")
                r, _w, _x = _select.select([proc.stdout], [], [], 10.0)
                if r:
                    return proc.stdout.readline()
                if proc.poll() is not None:
                    return ""
                _raise_on_fr_headless_exception(
                    proc, cmd, dsn_path=dsn_path, jar=jar)
        try:
            while True:
                _ln = _next_line()
                if _ln == "":
                    break
                _lines.append(_ln)
                if _ln.startswith("CEC_PASS "):
                    print("[fr] " + _ln.strip(), flush=True)
                    m_f = re.search(r"failed=(\d+)", _ln)
                    m_g = re.search(r"togo=(\d+)", _ln)
                    m_p = re.search(r"pass=(\d+)", _ln)
                    if m_f and m_g:
                        # IMPROVEMENT = either counter dropping (wave-11 calibration,
                        # 2026-07-15: failed= is the stable hard-core retry set and
                        # sits flat from pass 2 while togo= is still falling 116->
                        # 77->68->60 -- keying on failed alone culled ALL 16 live
                        # candidates mid-progress. True plateau = BOTH flat.)
                        _f, _g = int(m_f.group(1)), int(m_g.group(1))
                        _cur = (_g, _f)
                        if _best is None or _cur[0] < _best[0] or _cur[1] < _best[1]:
                            _best = (_cur[0] if _best is None else min(_best[0], _cur[0]),
                                     _cur[1] if _best is None else min(_best[1], _cur[1]))
                            _streak = 0
                        elif _f > 0:
                            _streak += 1
                            if _streak >= _k:
                                if _plateau_at_terminal_pass(
                                        int(m_p.group(1)) if m_p else None,
                                        passes, _k):
                                    _streak = 0
                                    print("[cec_fr] plateau reached the requested "
                                          "terminal pass -- allowing SES "
                                          "finalization (no route time remains to "
                                          "save)", flush=True)
                                elif _plateau_floor_grants_grace(
                                        _best[0], _pfloor,
                                        _graces_used, _grace_limit):
                                    _graces_used += 1
                                    _streak = 0
                                    print(f"[cec_fr] plateau at togo/failed={_best} is "
                                          f"WITHIN the floor ({_pfloor}) -- bounded "
                                          f"recovery grace {_graces_used}/{_grace_limit}; "
                                          f"kill remains armed",
                                          flush=True)
                                else:
                                    _killed = True
                                    _kill_fr_tree(proc)
                                    break
            proc.wait(timeout=30)
        except BaseException:
            # KeyboardInterrupt/SystemExit must obey the same process-tree
            # contract as a timeout.  Without this, stopping a coordinator
            # reparented the xvfb wrapper and a CPU-hot Java router to PID 1.
            if proc.poll() is None:
                _kill_fr_tree(proc)
                try:
                    proc.wait(timeout=15)
                except Exception:
                    pass
            raise
        finally:
            if _own_workdir:
                shutil.rmtree(workdir, ignore_errors=True)
        if _killed:
            print(f"[cec_fr] PLATEAU_KILL: togo/failed={_best} flat for {_streak} pass(es) "
                  f"-- candidate rejected at {round(time.monotonic() - _t0, 1)}s",
                  flush=True)
            raise RuntimeError(
                f"CEC_PLATEAU_KILL: unrouted plateau at togo/failed={_best} "
                f"({_streak} flat passes)")
        result = subprocess.CompletedProcess(
            cmd, proc.returncode, "".join(_lines), proc.stderr.read() if proc.stderr else "")
    else:
        # Popen + communicate instead of subprocess.run: run's own timeout kill
        # reaps only the DIRECT child (the xvfb-run wrapper on headless Linux),
        # orphaning the JVM -- the measured 85-zombie leak. _kill_fr_tree takes
        # the whole group. Windows keeps identical semantics (no session group).
        _blk_kw = {kk: vv for kk, vv in run_kw.items()
                   if kk not in ("capture_output", "text", "timeout")}
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True,
                                    start_new_session=(os.name == "posix"), **_blk_kw)
            _deadline = time.monotonic() + timeout
            while True:
                _remaining = _deadline - time.monotonic()
                if _remaining <= 0:
                    _kill_fr_tree(proc)
                    try:
                        proc.communicate(timeout=15)
                    except Exception:
                        pass
                    raise RuntimeError(
                        f"cec_fr.run_freerouting: timed out after {timeout}s "
                        f"(dsn={dsn_path!r}, jar={jar!r})")
                try:
                    _out, _err = proc.communicate(
                        timeout=min(10.0, _remaining))
                    break
                except subprocess.TimeoutExpired:
                    _raise_on_fr_headless_exception(
                        proc, cmd, dsn_path=dsn_path, jar=jar)
            result = subprocess.CompletedProcess(cmd, proc.returncode,
                                                 _out or "", _err or "")
        except BaseException:
            if "proc" in locals() and proc.poll() is None:
                _kill_fr_tree(proc)
                try:
                    proc.communicate(timeout=15)
                except Exception:
                    pass
            raise
        finally:
            if _own_workdir:
                try:
                    shutil.rmtree(workdir, ignore_errors=True)
                except Exception:
                    pass
        for _ln in (result.stdout or "").splitlines():
            if _ln.startswith(("CEC_PASS ", "CEC_STALL_ABORT ")):
                print("[fr] " + _ln, flush=True)

    if result.returncode != 0:
        tail = (result.stdout + result.stderr)[-2000:]
        raise RuntimeError(
            f"cec_fr.run_freerouting: Freerouting exited {result.returncode}\n"
            f"  dsn={dsn_path!r}\n  ses={ses_path!r}\n"
            f"  tail of output:\n{tail}"
        )

    if not os.path.isfile(ses_path) or os.path.getsize(ses_path) == 0:
        tail = (result.stdout + result.stderr)[-2000:]
        raise RuntimeError(
            f"cec_fr.run_freerouting: SES file missing or empty after FR exit 0\n"
            f"  expected: {ses_path!r}\n  tail:\n{tail}"
        )

    return ses_path


# ---------------------------------------------------------------------------
# add_power_pours -- additive same-net pours, laid AFTER routing
# ---------------------------------------------------------------------------
def add_inner_gnd_fill(board, layer_name, *, gnd_net="GND", inset_mm=0.5):
    """Pour GND into the leftover space of a SIGNAL inner layer, stitched.

    The other half of the 2026-07-25 power-layer ruling. Once rails move to the
    outers, the hub's In2 is signal tracks and empty space -- and empty space on
    the layer directly under the components is worth more as reference copper
    than as nothing: it gives the B.Cu signals below a continuous return path
    instead of the rail-to-rail plane splits they used to cross.

    Three properties make this safe rather than decorative:

      * LOWEST PRIORITY (0) -- any real pour on the same layer, including a
        policy-exception rail region, fills first and this flows around it;
      * ISLAND REMOVAL ALWAYS -- a fill fragment with no connection to the net is
        deleted by the filler itself, so this cannot manufacture the exact defect
        the reapers exist to remove (floating copper doing nothing);
      * it runs POST-ROUTE, so it never competes with Freerouting for the layer
        (a pre-route plane would have been detected as a plane and excluded the
        layer from routing entirely -- the measured gotcha behind In2's freeing).

    Stitching needs no new machinery on the hub: 66 GND vias + 48 GND through-hole
    pads already pierce In2 across 47% of its 10mm cells, and island removal drops
    whatever they do not reach.
    """
    lid = board.GetLayerID(layer_name)
    if lid < 0:
        return None
    net = board.FindNet(gnd_net)
    if net is None:
        return None
    # IDEMPOTENT (measured 2026-07-25: import_ses runs twice in one grade -- the
    # staged-FR tier route and the main route -- which added a SECOND gndfill
    # zone, the 0.0mm2 phantom in the census). One fill per layer, ever.
    _tag = f"gndfill:{layer_name}"
    for _z in board.Zones():
        if _z.GetZoneName() == _tag:
            return _z
    bb = board.GetBoardEdgesBoundingBox()
    if bb.GetWidth() <= 0 or bb.GetHeight() <= 0:
        return None
    ins = int(inset_mm * MM)
    x0, y0 = bb.GetLeft() + ins, bb.GetTop() + ins
    x1, y1 = bb.GetRight() - ins, bb.GetBottom() - ins
    if x1 <= x0 or y1 <= y0:
        return None
    z = pcbnew.ZONE(board)
    z.SetLayer(lid)
    z.SetNet(net)
    z.SetZoneName(f"gndfill:{layer_name}")
    z.SetAssignedPriority(0)
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    o = z.Outline()                      # in-place append (never SetOutline)
    o.NewOutline()
    for (px, py) in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        o.Append(int(px), int(py))
    if z.Outline().FullPointCount() < 3:
        return None
    board.Add(z)
    try:
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    except Exception as e:                                 # noqa: BLE001
        print(f"[cec_fr] inner GND fill: filler failed ({e})", file=sys.stderr)
        return None
    area = z.GetFilledArea() / 1e12
    print(f"[cec_fr] inner GND fill: {layer_name} poured {area:.0f}mm2 "
          f"(priority 0, islands removed)", file=sys.stderr, flush=True)
    return z


def shunt_tap_gaps(board, *, prefix="RS"):
    """The inter-pad gap of every 2-terminal shunt, on the shunt pads' OWN layers.

    This region belongs exclusively to the Kelvin tap stubs (owner pour-termination
    ruling 2026-07-24: "force copper stops at the shunt pad, the gap belongs to the
    taps"). Layer-scoped on purpose: an inner GND plane passing UNDER an SMD shunt
    is correct and must not be clipped -- only copper sharing a layer with the pads
    can steal the tap window.

    Returns [(layer_names:set, (x0, y0, x1, y1), ref), ...] in mm.
    """
    gaps = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if not ref.startswith(prefix):
            continue
        pads = list(fp.Pads())
        if len(pads) != 2:
            continue
        boxes = []
        for pd in pads:
            bb = pd.GetBoundingBox()
            boxes.append((bb.GetLeft() / MM, bb.GetTop() / MM,
                          bb.GetRight() / MM, bb.GetBottom() / MM,
                          {pcbnew.LayerName(l) for l in pd.GetLayerSet().CuStack()}))
        (ax0, ay0, ax1, ay1, al), (bx0, by0, bx1, by1, bl) = boxes
        lays = al & bl
        if not lays:
            continue
        if min(ax1, bx1) < max(ax0, bx0):                  # separated in x
            gx0, gx1 = min(ax1, bx1), max(ax0, bx0)
            gy0, gy1 = max(ay0, by0), min(ay1, by1)
        elif min(ay1, by1) < max(ay0, by0):                # separated in y
            gy0, gy1 = min(ay1, by1), max(ay0, by0)
            gx0, gx1 = max(ax0, bx0), min(ax1, bx1)
        else:
            continue                                        # overlapping pads: no gap
        if gx1 <= gx0 or gy1 <= gy0:
            continue
        gaps.append((lays, (gx0, gy0, gx1, gy1), ref))
    return gaps


def shunt_pour_forbidden(board, *, prefix="RS", margin_mm=0.0):
    """Every region a pour must NOT occupy around a shunt, as clip rects.

    Two rules, both from the 2026-07-24 pour-termination ruling:

      * THE TAP GAP is off limits to everybody (net=None) -- it belongs to the
        Kelvin stubs;
      * A FORCE POUR TERMINATES AT ITS OWN PAD (net=<terminal net>): everything
        beyond that pad's INNER edge, along the shunt axis, is forbidden to that
        net. Without this the gap clip alone just hollows a doughnut -- measured
        on eps, /SENSEC1_HI stopped at nothing: its pad ends at y 17.95 and the
        pour ran to y 28.38, straight past the gap AND past the LO pad, wrapping
        the shunt it is supposed to terminate at. Clipping at the inner edge is
        what "stops at the shunt pad" actually means.

    Returns [(layers:set, (x0, y0, x1, y1), ref, net_or_None), ...] in mm.
    """
    out = [(lays, rect, ref, None) for lays, rect, ref in shunt_tap_gaps(board, prefix=prefix)]
    bb = board.GetBoardEdgesBoundingBox()
    BX0, BY0 = bb.GetLeft() / MM - 10.0, bb.GetTop() / MM - 10.0
    BX1, BY1 = bb.GetRight() / MM + 10.0, bb.GetBottom() / MM + 10.0
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if not ref.startswith(prefix):
            continue
        pads = list(fp.Pads())
        if len(pads) != 2:
            continue
        info = []
        for pd in pads:
            bx = pd.GetBoundingBox()
            info.append((pd.GetNetname(),
                         bx.GetLeft() / MM, bx.GetTop() / MM,
                         bx.GetRight() / MM, bx.GetBottom() / MM,
                         {pcbnew.LayerName(l) for l in pd.GetLayerSet().CuStack()}))
        (n1, ax0, ay0, ax1, ay1, al), (n2, bx0, by0, bx1, by1, bl) = info
        lays = al & bl
        if not lays or not n1 or not n2 or n1 == n2:
            continue
        if min(ax1, bx1) < max(ax0, bx0):                  # x-separated
            if ax1 <= bx0:                                  # pad A is the left one
                out.append((lays, (ax1 + margin_mm, BY0, BX1, BY1), ref, n1))
                out.append((lays, (BX0, BY0, bx0 - margin_mm, BY1), ref, n2))
            else:
                out.append((lays, (BX0, BY0, ax0 - margin_mm, BY1), ref, n1))
                out.append((lays, (bx1 + margin_mm, BY0, BX1, BY1), ref, n2))
        elif min(ay1, by1) < max(ay0, by0):                # y-separated
            if ay1 <= by0:                                  # pad A is the upper one
                out.append((lays, (BX0, ay1 + margin_mm, BX1, BY1), ref, n1))
                out.append((lays, (BX0, BY0, BX1, by0 - margin_mm), ref, n2))
            else:
                out.append((lays, (BX0, BY0, BX1, ay0 - margin_mm), ref, n1))
                out.append((lays, (BX0, by1 + margin_mm, BX1, BY1), ref, n2))
    return out


def _subtract_rect(poly, rect, holes=()):
    """polygon (exterior + holes) minus an axis-aligned rect -> [(ext, holes), ...].

    HOLE-AWARE BY CONSTRUCTION (bug fixed 2026-07-25). Chaining two clips while
    subtracting only the EXTERIOR and carrying the previous holes across produced
    a zone whose hole lay OUTSIDE its own outline -- malformed geometry that
    KiCad's filler turns into a scrap: /SENSEC1_HI came out with a correct
    (29.84,6.30)-(44.44,17.95) outline and 16.6mm2 of fill inside ~170mm2 of it.
    The subtraction now runs on the whole polygon, interiors included.

    Uses shapely when present; falls back to an exact rectangle split when the
    polygon is itself axis-aligned rectangular (which every stamped force pour
    is). Returns [poly] unchanged when the two do not overlap.
    """
    x0, y0, x1, y1 = rect
    xs = [q[0] for q in poly]
    ys = [q[1] for q in poly]
    if not xs or max(xs) <= x0 or min(xs) >= x1 or max(ys) <= y0 or min(ys) >= y1:
        return [(poly, list(holes or []))]                  # no overlap: untouched
    try:
        from shapely.geometry import Polygon, box as _box
        g = Polygon(poly, holes or ()).buffer(0).difference(_box(x0, y0, x1, y1))
        if g.is_empty:
            return []
        parts = list(getattr(g, "geoms", [g]))
        out = []
        for part in parts:
            if part.area <= 1e-9:
                continue
            # HOLES ARE THE POINT (bug caught 2026-07-25): a shunt tap gap sits
            # INSIDE the pour, so the difference is a polygon with an interior
            # ring. Keeping only `exterior` silently restored the original shape
            # -- the clip reported success on every zone and changed nothing.
            ext = [(round(px, 4), round(py, 4))
                   for px, py in list(part.exterior.coords)[:-1]]
            holes = [[(round(px, 4), round(py, 4))
                      for px, py in list(r.coords)[:-1]] for r in part.interiors]
            out.append((ext, holes))
        return out
    except ImportError:
        pass
    # rect-minus-rect (host fallback): up to four surviving slabs
    px0, px1, py0, py1 = min(xs), max(xs), min(ys), max(ys)
    if holes or len({(round(q[0], 6), round(q[1], 6)) for q in poly}) != 4:
        return [(poly, list(holes or []))]                  # holes/non-rect: leave it
    out = []
    for r in ((px0, py0, px1, min(py1, y0)),                # above the gap
              (px0, max(py0, y1), px1, py1),                # below
              (px0, max(py0, y0), min(px1, x0), min(py1, y1)),   # left
              (max(px0, x1), max(py0, y0), px1, min(py1, y1))):  # right
        a0, b0, a1, b1 = r
        if a1 - a0 > 1e-6 and b1 - b0 > 1e-6:
            out.append(([(a0, b0), (a1, b0), (a1, b1), (a0, b1)], []))
    return out


def refill_zones(board_path):
    """Re-fill every zone on a saved board. Returns True if it ran.

    Needed wherever copper is added AFTER import_ses filled the pours. Measured
    2026-07-25 on eps: cec_gnd_fanout drops impedance vias into the routed board
    post-fill, so the pours still carry the fill they had BEFORE those vias
    existed -- the filler had no chance to void around them. DRC then reports a
    clearance violation the board does not really have ("zone clearance 0.5mm;
    actual 0.4542mm"), and because that DRC is what the grade scores, every
    candidate was being penalised for phantom copper. A refill takes the same
    board from 2 violations to 0.
    """
    try:
        board = pcbnew.LoadBoard(board_path)
        for z in board.Zones():
            z.UnFill()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        pcbnew.SaveBoard(board_path, board)
        return True
    except Exception as e:                                 # noqa: BLE001 -- fail-safe
        print(f"[cec_fr] refill_zones failed on {board_path}: {e}", file=sys.stderr)
        return False


def enforce_pour_termination(board, *, refill=True):
    """Clip EXISTING zones out of every same-layer shunt tap gap. Returns the count.

    The input-list clip in add_power_pours is not enough, measured: the eps force
    pours are laid at MATERIALIZE, long before the import-time pour list exists, so
    they reach the routed board as zones and no filter that reads pour DICTS can
    ever see them (their outlines still intruded 15.75mm2 each into RS1/RS2 with
    the dict clip live and reporting "4 clipped"). Enforcing on the ARTIFACT is the
    same lesson the shunt-only rule learned when it was bypassed three ways: the
    board is the only thing every path has in common.

    Layer-scoped via shunt_tap_gaps, so inner GND planes under an SMD shunt are
    untouched. Zones reduced to nothing are removed.
    """
    try:
        gaps = shunt_pour_forbidden(board)
    except Exception:                                      # noqa: BLE001
        return 0
    if not gaps:
        return 0
    changed, doomed = 0, []
    for z in board.Zones():
        if z.GetIsRuleArea():
            continue
        for lid in board.GetEnabledLayers().CuStack():
            if not z.IsOnLayer(lid):
                continue
            lname = pcbnew.LayerName(lid)
            _zn = z.GetNetname() or ""
            # a rect with net=None binds every net (the tap gap); a rect with a
            # net binds only that net (its own terminate-at-the-pad half-plane)
            mine = [g for g in gaps
                    if lname in g[0] and (g[3] is None or g[3] == _zn)]
            if not mine:
                continue
            outline = z.Outline()
            kept = []
            for i in range(outline.OutlineCount()):
                o = outline.Outline(i)
                kept.append(([(o.CPoint(k).x / MM, o.CPoint(k).y / MM)
                              for k in range(o.PointCount())], []))
            touched = False
            for _lays, rect, _ref, _rnet in mine:
                nxt = []
                for ext, holes in kept:
                    res = _subtract_rect(ext, rect, holes)
                    if len(res) != 1 or res[0][0] is not ext:
                        touched = True
                    nxt.extend(res)
                kept = nxt
            if not touched:
                continue
            if not kept:
                doomed.append(z)
                break
            outline.RemoveAllContours()
            for ext, holes in kept:
                oi = outline.NewOutline()
                for (x, y) in ext:
                    outline.Append(_nm(x), _nm(y))
                for hole in holes:
                    hi = outline.NewHole(oi)
                    for (x, y) in hole:
                        outline.Append(_nm(x), _nm(y), oi, hi)
            changed += 1
            break
    for z in doomed:
        board.Remove(z)
    if (changed or doomed) and refill:
        try:
            for z in board.Zones():
                z.UnFill()
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        except Exception as e:                             # noqa: BLE001
            print(f"[cec_fr] pour termination: refill failed ({e})", file=sys.stderr)
    if changed or doomed:
        print(f"[cec_fr] pour termination: {changed} zone outline(s) clipped, "
              f"{len(doomed)} dropped -- the shunt tap gap belongs to the taps",
              file=sys.stderr, flush=True)
    return changed + len(doomed)


def _non_manhattan_ring_edges(points, tol_mm=1e-6):
    """Return diagonal boundary edges from a generated pour ring."""
    pts = list(points or ())
    if len(pts) < 2:
        return []
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    return [(a, b) for a, b in zip(pts, pts[1:])
            if abs(float(b[0]) - float(a[0])) > tol_mm
            and abs(float(b[1]) - float(a[1])) > tol_mm]


def _assert_manhattan_power_pours(pours):
    """Sink-side invariant: additive power-zone outlines are rectilinear.

    Enforcing this where every generated pour becomes KiCad copper prevents a
    new producer from reintroducing a diagonal centerline and relying on a
    later raster approximation. Such an approximation is not cosmetic: it can
    change width, clearance, or via coverage.
    """
    bad = []
    for pour in pours:
        rings = [("outline", pour.get("polygon") or ())]
        rings.extend(("hole", ring) for ring in (pour.get("holes") or ()))
        for kind, ring in rings:
            edges = _non_manhattan_ring_edges(ring)
            if edges:
                bad.append((pour.get("name") or pour.get("net") or "unnamed",
                            pour.get("layer", "F.Cu"), kind, len(edges)))
    if bad:
        sample = ", ".join("%s@%s/%s:%d" % item for item in bad[:6])
        raise ValueError("add_power_pours refused non-Manhattan geometry: %s"
                         % sample)


def _zone_outline_geometry(zone):
    """Return a zone's authored outline as Shapely geometry.

    Filled copper is deliberately not used here: the fill contains local pad
    antipads and thermal details, while this cleanup is concerned with the
    authored slab boundary that the router and dashboard reserve.
    """
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    outline = zone.Outline()
    parts = []
    for oi in range(outline.OutlineCount()):
        contour = outline.Outline(oi)
        ext = [(contour.CPoint(k).x / MM, contour.CPoint(k).y / MM)
               for k in range(contour.PointCount())]
        holes = []
        for hi in range(outline.HoleCount(oi)):
            ring = outline.Hole(oi, hi)
            holes.append([(ring.CPoint(k).x / MM, ring.CPoint(k).y / MM)
                          for k in range(ring.PointCount())])
        if len(ext) >= 3:
            geom = Polygon(ext, holes).buffer(0)
            if not geom.is_empty:
                parts.append(geom)
    return unary_union(parts) if parts else Polygon()


def _orthogonal_fill_additions(geometry, *, forbidden=None, region=None,
                               micro_step_mm=0.25,
                               allow_corner_fills=False,
                               max_corner_fraction=0.35,
                               max_passes=24):
    """Return safe additive rectangles that regularize an orthogonal union.

    A routed corridor and its landing/manifold zones often meet as an L. The
    path search must conservatively avoid a whole THT pad field, but a finished
    zone does not: KiCad can make the exact local antipads around those pads.
    Carrying the path-search envelope into the final outline therefore leaves
    large, artificial rectangular bites, plus sub-grid edge steps where clipped
    pieces almost align.

    By default this helper fixes only sub-grid edge mismatches. Large reflex
    corners are valuable placement/routing pockets in a pour-first flow and
    are preserved even when they are electrically floodable. A caller may
    explicitly opt into corner flooding; those proposals still have to stay
    inside the board, miss hard reservations, remain connected, and stay below
    the bounded area fraction. The helper never subtracts copper.
    """
    from shapely.geometry import box as _box

    stats = {"micro_fills": 0, "corner_fills": 0, "added_mm2": 0.0}
    if geometry is None or geometry.is_empty:
        return [], stats
    union = geometry.buffer(0)
    forbidden = forbidden.buffer(0) if forbidden is not None else None
    additions = []

    def _parts(g):
        return [p for p in getattr(g, "geoms", [g])
                if p.geom_type == "Polygon" and not p.is_empty]

    def _clean_ring(coords):
        pts = [(float(x), float(y)) for x, y in list(coords)[:-1]]
        changed = True
        while changed and len(pts) >= 4:
            changed = False
            out = []
            for i, cur in enumerate(pts):
                prv = pts[i - 1]
                nxt = pts[(i + 1) % len(pts)]
                if ((abs(prv[0] - cur[0]) <= 1e-6 and
                     abs(cur[0] - nxt[0]) <= 1e-6) or
                    (abs(prv[1] - cur[1]) <= 1e-6 and
                     abs(cur[1] - nxt[1]) <= 1e-6)):
                    changed = True
                    continue
                out.append(cur)
            pts = out
        return pts

    for _pass in range(max_passes):
        candidates = []
        for component in _parts(union):
            pts = _clean_ring(component.exterior.coords)
            for i, vertex in enumerate(pts):
                prv = pts[i - 1]
                nxt = pts[(i + 1) % len(pts)]
                leg1_h = abs(prv[1] - vertex[1]) <= 1e-6
                leg1_v = abs(prv[0] - vertex[0]) <= 1e-6
                leg2_h = abs(nxt[1] - vertex[1]) <= 1e-6
                leg2_v = abs(nxt[0] - vertex[0]) <= 1e-6
                if not ((leg1_h and leg2_v) or (leg1_v and leg2_h)):
                    continue
                dx = abs(prv[0] - nxt[0])
                dy = abs(prv[1] - nxt[1])
                if dx <= 1e-6 or dy <= 1e-6:
                    continue
                proposal = _box(min(prv[0], vertex[0], nxt[0]),
                                min(prv[1], vertex[1], nxt[1]),
                                max(prv[0], vertex[0], nxt[0]),
                                max(prv[1], vertex[1], nxt[1]))
                addition = proposal.difference(union)
                if addition.is_empty or addition.area <= 1e-6:
                    continue                         # convex corner
                # A local fill may be large (the three-pad connector corner
                # measured 21% of its corridor), but it may not silently turn
                # a U-shaped territory into a board-sized rectangle.
                if addition.area > max_corner_fraction * component.area:
                    continue
                if region is not None and not region.buffer(1e-6).covers(addition):
                    continue
                if (forbidden is not None and not forbidden.is_empty and
                        forbidden.intersection(addition).area > 1e-6):
                    continue
                merged = union.union(addition).buffer(0)
                if len(_parts(merged)) != len(_parts(union)):
                    continue
                kind = ("micro_fills" if min(dx, dy) <= micro_step_mm + 1e-6
                        else "corner_fills")
                if kind == "corner_fills" and not allow_corner_fills:
                    continue
                # Resolve tiny edge mismatches first, then larger clear elbows.
                candidates.append((0 if kind == "micro_fills" else 1,
                                   addition.area, kind, addition, merged))
        if not candidates:
            break
        _rank, area, kind, addition, union = min(
            candidates, key=lambda item: (item[0], item[1]))
        additions.extend(_parts(addition))
        stats[kind] += 1
        stats["added_mm2"] += area
    stats["added_mm2"] = round(stats["added_mm2"], 3)
    return additions, stats


def _reconcile_patch_corridor_exterior(corridor, patch, *, protected=None,
                                       contact_pads=(), forbidden=None,
                                       region=None,
                                       max_trim_mm=0.5,
                                       max_add_fraction=0.35,
                                       min_pad_contact_fraction=0.5,
                                       min_pad_contact_mm=0.5):
    """Align a rectangular terminal patch with the corridor run it extends.

    A terminal landing commonly overlaps the end of an already verified wide
    corridor.  If the landing extends past the corridor on one axis while its
    *margin* ends a few tenths of a millimetre past the corridor on the other,
    the authored union acquires the two-axis exterior staircase highlighted in
    review.  This is not a routing bend and it is not the intentional inside
    placement pocket: it is disagreement between two same-net producers.

    For each exterior side, this helper projects the corridor's existing
    boundary run through the landing and evaluates both compactly shaving the
    landing back to that run and projecting the run through the landing. The
    smallest safe simplification wins, so placement area is not consumed just
    to make copper look regular. It fails closed if removed copper contains a protected
    via/track, reduces a pad's solid corridor overlap below a bounded contact
    throat, crosses a hard reservation or the board edge, or changes
    component/hole topology. The pad itself remains copper; the pad guard is
    about its zone-to-pad interface, not requiring the zone to duplicate the
    entire land. The returned additions can be emitted as ordinary
    ``orthofill:`` zones; the returned patch geometry replaces only the
    rectangular ``patch:`` outline.
    """
    from shapely.geometry import LineString, box as _box

    stats = {"reconciled": 0, "added_mm2": 0.0, "trimmed_mm2": 0.0}
    if (corridor is None or corridor.is_empty or patch is None or
            patch.is_empty or getattr(patch, "geom_type", "") != "Polygon" or
            patch.interiors):
        return patch, [], stats
    pbox = _box(*patch.bounds)
    if patch.symmetric_difference(pbox).area > 1e-6:
        return patch, [], stats

    protected = protected.buffer(0) if protected is not None else None
    forbidden = forbidden.buffer(0) if forbidden is not None else None
    original = corridor.union(patch).buffer(0)

    def _parts(g):
        return [p for p in getattr(g, "geoms", [g])
                if p.geom_type == "Polygon" and not p.is_empty]

    def _vertices(g):
        total = 0
        for part in _parts(g):
            pts = list(part.exterior.coords)[:-1]
            changed = True
            while changed and len(pts) >= 4:
                changed = False
                clean = []
                for i, cur in enumerate(pts):
                    prv, nxt = pts[i - 1], pts[(i + 1) % len(pts)]
                    if ((abs(prv[0] - cur[0]) <= 1e-6 and
                         abs(cur[0] - nxt[0]) <= 1e-6) or
                        (abs(prv[1] - cur[1]) <= 1e-6 and
                         abs(cur[1] - nxt[1]) <= 1e-6)):
                        changed = True
                        continue
                    clean.append(cur)
                pts = clean
            total += len(pts)
        return total

    def _intervals(cut, vertical):
        out = []
        for seg in getattr(cut, "geoms", [cut]):
            if seg.is_empty or seg.geom_type not in ("LineString", "LinearRing"):
                continue
            b = seg.bounds
            lo, hi = ((b[1], b[3]) if vertical else (b[0], b[2]))
            if hi - lo > 1e-6:
                out.append((lo, hi))
        return out

    px0, py0, px1, py1 = patch.bounds
    span = max(corridor.bounds[2] - corridor.bounds[0],
               corridor.bounds[3] - corridor.bounds[1],
               px1 - px0, py1 - py0, 1.0)
    limit = max(abs(v) for v in corridor.bounds + patch.bounds) + span + 10.0
    proposals = []

    def _consider(component, side):
        cx0, cy0, cx1, cy1 = component.bounds
        probe = max(1e-5, min(1e-3, span * 1e-5))
        if side in ("right", "left"):
            edge = cx1 if side == "right" else cx0
            protrusion = (px1 - edge if side == "right" else edge - px0)
            overlap_primary = (px0 < edge - 1e-6 if side == "right"
                               else px1 > edge + 1e-6)
            if protrusion <= 1e-6 or not overlap_primary:
                return
            xprobe = edge - probe if side == "right" else edge + probe
            cut = component.intersection(
                LineString([(xprobe, -limit), (xprobe, limit)]))
            runs = _intervals(cut, True)
            for run0, run1 in runs:
                if min(run1, py1) - max(run0, py0) <= 1e-6:
                    continue
                low_excess = max(0.0, run0 - py0)
                high_excess = max(0.0, py1 - run1)
                if max(low_excess, high_excess) > max_trim_mm + 1e-6:
                    continue
                clipped = patch.intersection(_box(-limit, run0, limit, run1))
                xlo, xhi = ((edge, px1) if side == "right" else (px0, edge))
                extension = _box(xlo, run0, xhi, run1).difference(corridor)
                _score_candidate(clipped, extension)
                compact_x0, compact_x1 = ((-limit, edge)
                                          if side == "right"
                                          else (edge, limit))
                compact = patch.intersection(
                    _box(compact_x0, run0, compact_x1, run1))
                _score_candidate(compact, patch.difference(patch))
        else:
            edge = cy1 if side == "bottom" else cy0
            protrusion = (py1 - edge if side == "bottom" else edge - py0)
            overlap_primary = (py0 < edge - 1e-6 if side == "bottom"
                               else py1 > edge + 1e-6)
            if protrusion <= 1e-6 or not overlap_primary:
                return
            yprobe = edge - probe if side == "bottom" else edge + probe
            cut = component.intersection(
                LineString([(-limit, yprobe), (limit, yprobe)]))
            runs = _intervals(cut, False)
            for run0, run1 in runs:
                if min(run1, px1) - max(run0, px0) <= 1e-6:
                    continue
                low_excess = max(0.0, run0 - px0)
                high_excess = max(0.0, px1 - run1)
                if max(low_excess, high_excess) > max_trim_mm + 1e-6:
                    continue
                clipped = patch.intersection(_box(run0, -limit, run1, limit))
                ylo, yhi = ((edge, py1) if side == "bottom" else (py0, edge))
                extension = _box(run0, ylo, run1, yhi).difference(corridor)
                _score_candidate(clipped, extension)
                compact_y0, compact_y1 = ((-limit, edge)
                                          if side == "bottom"
                                          else (edge, limit))
                compact = patch.intersection(
                    _box(run0, compact_y0, run1, compact_y1))
                _score_candidate(compact, patch.difference(patch))

    def _score_candidate(clipped, extension):
        if (clipped.is_empty or
                getattr(clipped, "geom_type", "") != "Polygon"):
            return
        extension_area = 0.0 if extension.is_empty else extension.area
        if extension_area > max_add_fraction * max(corridor.area, 1e-6):
            return
        if (extension_area > 1e-6 and region is not None and
                not region.buffer(1e-6).covers(extension)):
            return
        if (extension_area > 1e-6 and forbidden is not None and
                not forbidden.is_empty and
                forbidden.intersection(extension).area > 1e-6):
            return
        candidate = corridor.union(clipped).union(extension).buffer(0)
        removed = original.difference(candidate)
        if (protected is not None and not protected.is_empty and
                protected.intersection(removed).area > 1e-6):
            return
        for pad in contact_pads:
            old_contact = original.intersection(pad)
            if (old_contact.is_empty or old_contact.area <= 1e-6 or
                    removed.intersection(pad).area <= 1e-6):
                continue
            new_contact = candidate.intersection(pad)
            if (new_contact.is_empty or
                    new_contact.area <
                    min_pad_contact_fraction * old_contact.area - 1e-6):
                return
            contact_parts = _parts(new_contact)
            if len(contact_parts) != 1:
                return
            bx0, by0, bx1, by1 = contact_parts[0].bounds
            if min(bx1 - bx0, by1 - by0) < min_pad_contact_mm - 1e-6:
                return
        if (len(_parts(candidate)) != len(_parts(original)) or
                sum(len(p.interiors) for p in _parts(candidate)) !=
                sum(len(p.interiors) for p in _parts(original))):
            return
        improvement = _vertices(original) - _vertices(candidate)
        if improvement < 2:
            return
        proposals.append((-improvement,
                          extension_area + removed.area,
                          clipped, extension, removed, candidate))

    # The helper is deliberately local: every corridor component is examined,
    # but only the single best simplification of this one patch is returned.
    for component in _parts(corridor):
        for side in ("right", "left", "bottom", "top"):
            _consider(component, side)
    if not proposals:
        return patch, [], stats
    _rank, _changed, clipped, extension, removed, _candidate = min(proposals)
    additions = _parts(extension)
    stats.update({"reconciled": 1,
                  "added_mm2": round(sum(g.area for g in additions), 3),
                  "trimmed_mm2": round(removed.area, 3)})
    return clipped, additions, stats


def _replace_zone_outline(zone, geometry):
    """Replace one KiCad zone outline in-place with verified Shapely geometry."""
    parts = [p for p in getattr(geometry, "geoms", [geometry])
             if p.geom_type == "Polygon" and not p.is_empty]
    if len(parts) != 1:
        return False
    outline = zone.Outline()
    outline.RemoveAllContours()
    part = parts[0]
    oi = outline.NewOutline()
    for x, y in list(part.exterior.coords)[:-1]:
        outline.Append(_nm(x), _nm(y))
    for ring in part.interiors:
        hi = outline.NewHole(oi)
        for x, y in list(ring.coords)[:-1]:
            outline.Append(_nm(x), _nm(y), oi, hi)
    zone.UnFill()
    return True


def regularize_power_pour_boundaries(board, zones=None, *, fill=False):
    """Add bounded ``orthofill:`` zones to clean final pipeline-pour unions.

    This is intentionally an artifact/sink check, after shunt clipping. It can
    therefore repairs neither a proxy centerline nor a pre-clip polygon: it
    sees the exact zone outlines consumed by KiCad and the dashboard. The
    default policy is placement-preserving: flatten shallow edge mismatches,
    but retain every larger hook/pocket. Foreign routed copper, foreign non-GND
    pours, rule areas, and shunt gaps are hard blockers in either mode.
    """
    try:
        from shapely.geometry import LineString, Point, box as _box
        from shapely.ops import unary_union
    except ImportError:
        return {"groups": 0, "zones_added": 0, "micro_fills": 0,
                "corner_fills": 0, "exterior_reconciliations": 0,
                "added_mm2": 0.0, "trimmed_mm2": 0.0}

    selected = [z for z in (list(zones) if zones is not None else list(board.Zones()))
                if not z.GetIsRuleArea() and z.GetNetname() != "GND" and
                (zones is not None or
                 (z.GetZoneName() or "").startswith(PIPELINE_POUR_PREFIXES))]
    groups = {}
    for zone in selected:
        for lid in zone.GetLayerSet().CuStack():
            groups.setdefault((zone.GetNetname(), int(lid)), []).append(zone)
    if not groups:
        return {"groups": 0, "zones_added": 0, "micro_fills": 0,
                "corner_fills": 0, "exterior_reconciliations": 0,
                "added_mm2": 0.0, "trimmed_mm2": 0.0}

    bb = board.GetBoardEdgesBoundingBox()
    region = _box(bb.GetLeft() / MM, bb.GetTop() / MM,
                  bb.GetRight() / MM, bb.GetBottom() / MM)
    gaps = shunt_pour_forbidden(board)
    made = []
    edited = 0
    total = {"groups": 0, "zones_added": 0, "micro_fills": 0,
             "corner_fills": 0, "exterior_reconciliations": 0,
             "added_mm2": 0.0, "trimmed_mm2": 0.0}

    for (net, lid), seed_zones in sorted(groups.items()):
        layer = pcbnew.LayerName(lid)
        # ``zones`` scopes the nets/layers to regularize, not the geometry.
        # Same-net copper already on the board participates in the physical
        # union and must therefore participate in the boundary decision too.
        own_zones = [z for z in board.Zones()
                     if not z.GetIsRuleArea() and z.GetNetname() == net and
                     z.IsOnLayer(lid)]
        if not own_zones:
            own_zones = seed_zones
        blockers = []
        protected_parts = []
        contact_pads = []
        for glayers, rect, _ref, gap_net in gaps:
            if layer in glayers and (gap_net is None or gap_net == net):
                blockers.append(_box(*rect))
        # A pad may project past the zone boundary because the pad itself is
        # copper. Its bounding box supplies a conservative contact-throat
        # proof; vias and tracks below remain strict no-trim geometry.
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetname() != net or not pad.IsOnLayer(lid):
                    continue
                bbp = pad.GetBoundingBox()
                contact_pads.append(_box(
                    bbp.GetLeft() / MM, bbp.GetTop() / MM,
                    bbp.GetRight() / MM, bbp.GetBottom() / MM))
        # Non-GND foreign zones are authored power/reservation territories.
        # The GND plane is excluded: it is expected to yield locally to every
        # higher-priority power pour.
        for other in board.Zones():
            if other in own_zones or other.GetNetname() in ("", "GND", net):
                continue
            if other.IsOnLayer(lid):
                blockers.append(_zone_outline_geometry(other))
        # Existing foreign routes are hard reservations. Unlike pads, KiCad
        # cannot turn a route-long crossing into a harmless local antipad.
        for track in board.GetTracks():
            if track.GetNetname() == "" or not track.IsOnLayer(lid):
                continue
            # PCB_VIA::GetWidth() without a layer is an asserted API misuse in
            # KiCad 10; its per-layer diameter is the relevant reservation.
            width = (track.GetWidth(lid) if track.Type() == pcbnew.PCB_VIA_T
                     else track.GetWidth())
            own_track = track.GetNetname() == net
            radius = max(0.01, width / MM / 2.0 +
                         (0.0 if own_track else 0.3))
            try:
                start, end = track.GetStart(), track.GetEnd()
                geom = LineString([(start.x / MM, start.y / MM),
                                   (end.x / MM, end.y / MM)]).buffer(
                                       radius, cap_style=1, join_style=1)
            except Exception:                            # noqa: BLE001
                pos = track.GetPosition()
                geom = Point(pos.x / MM, pos.y / MM).buffer(radius)
            (protected_parts if own_track else blockers).append(geom)
        for area in board.Zones():
            if area.GetIsRuleArea() and area.IsOnLayer(lid):
                blockers.append(_zone_outline_geometry(area))
        forbidden = unary_union([g for g in blockers if not g.is_empty]) \
            if blockers else None
        protected = unary_union(
            [g for g in protected_parts if not g.is_empty]) \
            if protected_parts else None

        # Reconcile producer boundaries before the generic micro-band pass.
        # ``orthofill:`` belongs to the corridor on repeat calls, making this
        # transformation idempotent. Manifolds remain independent because
        # their envelope may intentionally reserve a connector insertion area.
        corridor_zones = [z for z in own_zones
                          if (z.GetZoneName() or "").startswith(
                              ("pourplan:", "orthofill:"))]
        patch_zones = [z for z in own_zones
                       if (z.GetZoneName() or "").startswith("patch:")]
        corridor = unary_union(
            [_zone_outline_geometry(z) for z in corridor_zones]).buffer(0) \
            if corridor_zones else None
        reconcile_additions = []
        reconciled_here = 0
        if corridor is not None and not corridor.is_empty:
            for patch_zone in patch_zones:
                patch_geom = _zone_outline_geometry(patch_zone)
                new_patch, new_additions, rstats = \
                    _reconcile_patch_corridor_exterior(
                        corridor, patch_geom, protected=protected,
                        contact_pads=contact_pads,
                        forbidden=forbidden, region=region)
                if not rstats["reconciled"]:
                    continue
                if not _replace_zone_outline(patch_zone, new_patch):
                    continue
                edited += 1
                reconciled_here += rstats["reconciled"]
                total["exterior_reconciliations"] += rstats["reconciled"]
                total["trimmed_mm2"] += rstats["trimmed_mm2"]
                total["added_mm2"] += rstats["added_mm2"]
                reconcile_additions.extend(new_additions)
                corridor = corridor.union(unary_union(new_additions)).buffer(0)

        own = unary_union(
            [_zone_outline_geometry(z) for z in own_zones] +
            reconcile_additions).buffer(0)
        micro_additions, stats = _orthogonal_fill_additions(
            own, forbidden=forbidden, region=region)
        additions = reconcile_additions + micro_additions
        if not additions and not reconciled_here:
            continue
        total["groups"] += 1
        total["micro_fills"] += stats["micro_fills"]
        total["corner_fills"] += stats["corner_fills"]
        total["added_mm2"] += stats["added_mm2"]
        priority = max(int(z.GetAssignedPriority()) for z in own_zones) + 1
        existing_indices = sum(
            (z.GetZoneName() or "").startswith("orthofill:")
            for z in own_zones)
        for index, geom in enumerate(additions, existing_indices + 1):
            z = pcbnew.ZONE(board)
            ls = pcbnew.LSET()
            ls.AddLayer(lid)
            z.SetLayerSet(ls)
            z.SetNetCode(board.GetNetcodeFromNetname(net))
            z.SetAssignedPriority(priority + index - 1)
            z.SetMinThickness(_nm(0.25))
            z.SetIslandRemovalMode(0)
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
            z.SetZoneName("orthofill:%s:%s:%d" % (net, layer, index))
            outline = z.Outline()
            oi = outline.NewOutline()
            for x, y in list(geom.exterior.coords)[:-1]:
                outline.Append(_nm(x), _nm(y))
            for ring in geom.interiors:
                hi = outline.NewHole(oi)
                for x, y in list(ring.coords)[:-1]:
                    outline.Append(_nm(x), _nm(y), oi, hi)
            board.Add(z)
            made.append(z)
            total["zones_added"] += 1
    total["added_mm2"] = round(total["added_mm2"], 3)
    total["trimmed_mm2"] = round(total["trimmed_mm2"], 3)
    if fill and (made or edited):
        for zone in board.Zones():
            zone.UnFill()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    if made or edited:
        print("[cec_fr] orthogonal pour cleanup: %d zone(s), "
              "%d micro + %d corner + %d exterior reconcile(s), "
              "%.3f mm2 added / %.3f mm2 empty margin trimmed" %
              (total["zones_added"], total["micro_fills"],
               total["corner_fills"], total["exterior_reconciliations"],
               total["added_mm2"], total["trimmed_mm2"]),
              file=sys.stderr, flush=True)
    return total


def add_power_pours(board, pours, *, fill: bool = False):
    """Lay additive same-net copper pours on an ALREADY-ROUTED board.

    Each entry in *pours* is a dict::

        {"net": "/SENSEC1_HI",                 # net to pour (must exist on the board)
         "polygon": [(x, y), ...],             # outline vertices in mm
         "holes": [[(x, y), ...], ...],        # optional interior rings
         "layer": "F.Cu",                      # default "F.Cu"
         "priority": 2,                        # above the GND plane (0); default 2
         "min_thickness": 0.25,                # mm; default 0.25
         "island_removal": 0}                  # 0=remove true islands (keep the body
                                               #   that holds the pads); default 0

    ORDERING IS THE WHOLE POINT. These pours are laid AFTER Freerouting has already
    connected every net, so they are purely ADDITIVE same-net copper: a pour on a net
    that is already routed can only ADD copper to it -- it cannot strand the Kelvin
    sense tap that shares that net node at the shunt. The earlier "pour-THEN-route"
    ordering DID strand the sense, because the pour reshaped Freerouting's GLOBAL
    solution and FR then failed to connect the sense out of the poured region; two
    pipeline-grade attempts both regressed the kelvin_ok gate that way. Pouring
    AFTER the route sidesteps that entirely -- the FR-drawn sense track is already
    there and the pour merges with it (same net, no DRC short). Verified on EPS:
    gates stay kelvin_ok=True / diffpair_ok=True, the four 12V pours fill ~120-150
    mm^2 each (~1 island), and structural DRC does not regress.

    Pads connect solid (ZONE_CONNECTION_FULL) for the high-current path. Returns the
    list of added ZONE objects. If *fill* is True, all zones are re-filled here
    (UnFill first -- re-filling in one process can segfault this KiCad-10 SWIG build).
    """
    pours = list(pours)
    _assert_manhattan_power_pours(pours)

    # SHUNT-ONLY TOP -- ENFORCED AT THE CHOKE POINT (owner rule 2026-07-24;
    # third traced bypass: materialize landing patches, the import list, AND
    # the router's pass-2 re-derivation each lay pours independently, so a
    # per-caller filter can always be bypassed by the next caller. Every pour
    # passes through THIS function: an F.Cu pour on a board with shunts is
    # refused here unless it intersects a shunt neighborhood. No exemptions.)
    _f_nbs = None
    try:
        import cec_slab_pour as _cslb3
        _f_nbs = _cslb3.shunt_neighborhoods(board)
    except Exception:                                  # noqa: BLE001
        _f_nbs = []
    try:
        _f_power_transit = _fab.copper_layer_allows_power(
            board, "F.Cu")
    except Exception:                                  # noqa: BLE001
        _f_power_transit = False
    # POUR TERMINATION AT THE SHUNT PAD (owner ruling 2026-07-24, implemented
    # 2026-07-25). The ruling was recorded in docs/slab-pour-design-2026-07-24.md
    # and never written: commit 1f803c0f added nine lines of prose and no code, so
    # every force pour kept running straight through the shunt's inter-pad gap --
    # measured on the eps winner as 8.16mm2 of /SENSEC1_HI, 6.82mm2 of /SENSEC2_LO
    # and so on sitting exactly where the Kelvin taps must live. Enforced HERE for
    # the same reason the shunt-only rule is: every laying path (materialize
    # patches, the import list, the router's pass-2 re-derivation) funnels through
    # this function, so a per-caller clip can always be bypassed by the next caller.
    try:
        _gaps = shunt_pour_forbidden(board)
    except Exception:                                  # noqa: BLE001
        _gaps = []
    _clipped = 0
    added = []
    # KiCad reports equal-priority intersecting zone outlines even when both
    # zones are on the same net. Preserve every named/provenance zone, but give
    # successive pieces of one net/layer deterministic priorities. Electrical
    # behavior is unchanged (same-net copper unions); names remain available
    # to the reapers and audit views.
    _same_net_layer_priorities = {}
    for p in pours:
        net = p["net"]
        # v3.1 CONNECTOR MANIFOLDS are the ONE named admit through the
        # shunt-only top rule (owner algorithm 2026-07-25: "combine up all
        # similar pins on one connector with a margin-width pour" -- the
        # manifold is the connector's OWN pin field + margin, pad-anchored
        # by construction, not signal-fabric decoration).
        _is_manifold = str(p.get("name") or "").startswith("manifold:")
        if (p.get("layer", "F.Cu") == "F.Cu" and _f_nbs
                and not _is_manifold and not _f_power_transit):
            _xs = [q[0] for q in p.get("polygon") or ()]
            _ys = [q[1] for q in p.get("polygon") or ()]
            if _xs and not any(
                    not (max(_xs) < n[0] or n[2] < min(_xs)
                         or max(_ys) < n[1] or n[3] < min(_ys))
                    for n in _f_nbs):
                print(f"[cec_fr] add_power_pours: REFUSED top pour {net} "
                      "(shunt-only rule, choke-point enforcement)",
                      file=sys.stderr)
                continue
        nc = board.GetNetcodeFromNetname(net)
        if nc <= 0:
            raise KeyError(f"cec_fr.add_power_pours: net {net!r} not found on board")
        z = pcbnew.ZONE(board)
        ls = pcbnew.LSET()
        lid = board.GetLayerID(p.get("layer", "F.Cu"))
        if lid < 0:
            raise KeyError(f"cec_fr.add_power_pours: layer {p.get('layer','F.Cu')!r} not found")
        ls.AddLayer(lid)
        z.SetLayerSet(ls)
        z.SetNetCode(nc)
        _priority_key = (net, p.get("layer", "F.Cu"))
        _used = _same_net_layer_priorities.setdefault(_priority_key, set())
        _assigned_priority = int(p.get("priority", 2))
        while _assigned_priority in _used:
            _assigned_priority += 1
        _used.add(_assigned_priority)
        z.SetAssignedPriority(_assigned_priority)
        z.SetMinThickness(_nm(p.get("min_thickness", 0.25)))
        z.SetIslandRemovalMode(int(p.get("island_removal", 0)))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        # zone-name identity from the dict (v3 deliverable D: the nowhere-
        # reaper + choke exemptions key on it; provenance-derived default)
        try:
            z.SetZoneName(str(p.get("name")
                              or "%s:%s" % (p.get("provenance") or "pour",
                                            net)))
        except Exception:                              # noqa: BLE001
            pass
        # Clip the outline out of every same-layer shunt tap gap before it becomes
        # copper. A pour reduced to nothing is dropped (it was ALL gap).
        _lay_name = p.get("layer", "F.Cu")
        _polys = [(list(p["polygon"]),
                   [list(ring) for ring in (p.get("holes") or ())])]
        for _glays, _grect, _gref, _gnet in _gaps:
            if _lay_name not in _glays or (_gnet is not None and _gnet != net):
                continue
            _next = []
            for _ext, _holes in _polys:
                _res = _subtract_rect(_ext, _grect, _holes)
                if len(_res) != 1 or _res[0][0] is not _ext:
                    _clipped += 1
                _next.extend(_res)
            _polys = _next
        if not _polys:
            print(f"[cec_fr] add_power_pours: pour {net} dropped -- it was entirely "
                  "inside a shunt tap gap", file=sys.stderr)
            continue
        # In-place outline append (never SetOutline -- SWIG alias bug, see cec_route.py)
        o = z.Outline()
        for _ext, _holes in _polys:
            _oi = o.NewOutline()
            for (x, y) in _ext:
                o.Append(_nm(x), _nm(y))
            for _hole in _holes:
                _hi = o.NewHole(_oi)
                for (x, y) in _hole:
                    o.Append(_nm(x), _nm(y), _oi, _hi)
        if z.Outline().FullPointCount() < 3:
            raise RuntimeError(f"cec_fr.add_power_pours: pour on {net!r} has < 3 points")
        board.Add(z)
        added.append(z)
    if _clipped:
        print(f"[cec_fr] pour termination: {_clipped} pour outline(s) clipped out of "
              f"{len(_gaps)} shunt tap gap(s) -- the gap belongs to the taps",
              file=sys.stderr)
    # Final-boundary authority: clipping and same-net zone union can create
    # shallow steps or retain the path search's board-sized THT avoidance
    # envelope. Regularize the exact emitted union, not its centerline proxy.
    if added:
        regularize_power_pour_boundaries(board, added, fill=False)
    if fill and added:
        for z in board.Zones():
            z.UnFill()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    return added


def replace_generated_power_pours(board, pours, *, managed_nets=None,
                                  fill=False):
    """Replace the complete generated pour set for selected force nets.

    ``add_power_pours`` intentionally remains additive for landing patches and
    authored supplemental copper.  A final cable-corridor lay is different: it
    is the authority for the whole ``*_HI``/``*_LO`` zone set, so retaining an
    older placement's zones creates doubled or displaced slabs.  This bounded
    helper removes zones only on the explicitly managed nets and then routes
    every replacement through :func:`add_power_pours`, preserving its solid-pad
    and shunt-gap choke-point rules.
    """
    pours = [dict(pour) for pour in (pours or ())]
    targets = ({str(net) for net in managed_nets if str(net)}
               if managed_nets is not None else
               {str(pour.get("net")) for pour in pours
                if str(pour.get("net") or "").endswith(("_HI", "_LO"))})
    doomed = [zone for zone in list(board.Zones())
              if zone.GetNetname() in targets]
    for zone in doomed:
        board.Remove(zone)
    # Replacement is deliberately closed over ``targets``.  Route import can
    # carry supplemental GND/logic-rail zones in the same list; re-adding those
    # here on every force-pour refresh would merely move the duplication bug to
    # a different net family.  Callers add non-managed supplemental pours once
    # through the ordinary additive path.
    replacements = [pour for pour in pours if pour.get("net") in targets]
    added = add_power_pours(board, replacements, fill=False)
    if fill and (doomed or added):
        for zone in board.Zones():
            zone.UnFill()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    return {
        "managed_nets": sorted(targets),
        "removed": len(doomed),
        "added": len(added),
    }


# ---------------------------------------------------------------------------
# derive_power_pours -- auto-find the high-current pour rectangles from geometry
# ---------------------------------------------------------------------------
def _board_kelvin_pairs(board):
    """Kelvin pairs from a LOADED board: name pairs (_HI/_LO) UNIONED with shunt-straddle
    pairs (any 2-pad RS* footprint's two nets -- the 24-pin's 5V/5VSB rails carry a POWER
    net on one shunt side and are invisible to the name rule; same derivation as
    cec_score.Rules.from_board, 2026-07-08). Orientation: name hint, else the side a known
    sense IC's IN+ pad taps, else lexical."""
    names = {n.GetNetname() for n in board.GetNetInfo().NetsByNetcode().values() if n.GetNetname()}
    pairs = {}
    for h in sorted(names):
        if h.endswith("_HI") and (h[:-3] + "_LO") in names:
            pairs[frozenset((h, h[:-3] + "_LO"))] = (h, h[:-3] + "_LO")
    inp_pin = {"INA238": "10", "INA228": "10", "INA226": "10", "INA181": "3"}
    ina_inp = set()
    shunts = []
    for fp in board.GetFootprints():
        ref = fp.GetReference() or ""
        val = (fp.GetValue() or "").upper()
        want = next((v for k, v in inp_pin.items() if k in val), None)
        for p in fp.Pads():
            if want is not None and p.GetPadName() == want and p.GetNetname():
                ina_inp.add(p.GetNetname())
        if ref.startswith("RS") and fp.GetPadCount() == 2:
            nets = sorted({p.GetNetname() for p in fp.Pads() if p.GetNetname()})
            if len(nets) == 2:
                shunts.append(tuple(nets))
    for na, nb in shunts:
        key = frozenset((na, nb))
        if key in pairs:
            continue
        if na.endswith("_HI") or nb.endswith("_LO"):
            hi, lo = na, nb
        elif nb.endswith("_HI") or na.endswith("_LO"):
            hi, lo = nb, na
        elif na in ina_inp:
            hi, lo = na, nb
        elif nb in ina_inp:
            hi, lo = nb, na
        else:
            hi, lo = na, nb
        pairs[key] = (hi, lo)
    return sorted(pairs.values())


def _lane_width_mm(net):
    """Lane width for a rail net under CEC_POUR_LANES. Default 6.0mm (2oz exterior,
    ~10A at 30C rise first-order); per-net overrides via CEC_LANE_W_JSON. The FEM thermal
    gate VERIFIES whatever is chosen -- widths here are provisional inputs, never trusted
    conclusions."""
    try:
        import json as _json
        return float(_json.loads(os.environ.get("CEC_LANE_W_JSON", "{}")).get(net,
                     os.environ.get("CEC_LANE_W_MM", "6.0")))
    except Exception:                                    # noqa: BLE001
        return 6.0


def _cluster_lanes(cluster, shunt_pts, net, bbox, margin, *, gap_mm=None):
    """L-LANE rectangles for one pin cluster (strict no-parts-in-pours architecture).
    Geometry (2026-07-08 v2): pad cover -> vertical lane at the CLUSTER x down to just
    OUTSIDE the notch band -> horizontal jog AT the band edge (never along the shunt row:
    a row-level jog crossed neighbor shunts) -> a narrow FINGER (pad-width, NOTCH-EXEMPT)
    descending to the shunt pad. The band keeps PARTS out; copper enters only as fingers
    -- without them a wide band would sever the force path from every pour."""
    bx0, by0, bx1, by1 = bbox
    w = _lane_width_mm(net)
    g = (gap_mm if gap_mm is not None else _shunt_gap_mm()) / 2.0
    xs = [p[0] for p in cluster]
    ys = [p[1] for p in cluster]
    ccx = sum(xs) / len(xs)
    rects = [(max(bx0, min(xs) - margin), max(by0, min(ys) - margin),
              min(bx1, max(xs) + margin), min(by1, max(ys) + margin))]
    if shunt_pts:
        sx = sum(p[0] for p in shunt_pts) / len(shunt_pts)
        sy = sum(p[1] for p in shunt_pts) / len(shunt_pts)
        cy = sum(ys) / len(ys)
        from_above = cy <= sy
        band_edge = (sy - g) if from_above else (sy + g)
        # vertical lane: cluster -> band edge
        vy0, vy1 = (min(ys), band_edge) if from_above else (band_edge, max(ys))
        if vy1 - vy0 >= 0.8:
            rects.append((max(bx0, ccx - w / 2), max(by0, vy0),
                          min(bx1, ccx + w / 2), min(by1, vy1)))
        # horizontal jog AT the band edge (outside the band)
        if abs(ccx - sx) > w / 2:
            jy0 = band_edge - w if from_above else band_edge
            rects.append((max(bx0, min(ccx, sx) - w / 2), max(by0, jy0),
                          min(bx1, max(ccx, sx) + w / 2), min(by1, jy0 + w)))
        # FINGER: notch-exempt descent from the band edge to the shunt pad (pad-width-ish)
        fw = 3.2
        p_near = min(shunt_pts, key=lambda q: abs(q[1] - band_edge))
        fy0, fy1 = (band_edge, p_near[1] + 1.0) if from_above else (p_near[1] - 1.0, band_edge)
        rects.append((max(bx0, sx - fw / 2), max(by0, min(fy0, fy1)),
                      min(bx1, sx + fw / 2), min(by1, max(fy0, fy1))))
    return [r for r in rects if r[2] - r[0] >= 0.8 and r[3] - r[1] >= 0.6]

def _pour_boxes_core(names, kelvin_pairs, pads_by_net, padcount, flipped, bbox,
                     inner_layer, *, margin=1.0, layer="F.Cu"):
    """PURE-GEOMETRY pour-box core (box-model unification, 2026-07-08): both the pcbnew
    extraction (derive_power_pours) and the PLACEMENT-side extractor feed this, so the
    settle avoids EXACTLY the boxes the gate checks -- the two-model drift was the
    cross-board craft blocker (re-stamped caps kept landing in gate boxes the settle
    never saw). Inputs: pads_by_net = {net: [(ref, x_mm, y_mm, is_tht)]}; padcount =
    {ref: n}; flipped = {ref: bool}; bbox = (bx0, by0, bx1, by1) already edge-cleared.
    Returns the pour dict list."""
    bx0, by0, bx1, by1 = bbox
    pours = []
    for hi, lo in kelvin_pairs:
        refs_hi = {it[0] for it in pads_by_net.get(hi, [])}
        refs_lo = {it[0] for it in pads_by_net.get(lo, [])}
        # The shunt is the footprint straddling the pair with EXACTLY 2 pads (a Kelvin
        # shunt). A differential INA also has a pad on each of HI/LO but is multi-pad, so
        # the 2-pad test excludes it -- otherwise its small sense pads would inflate the
        # bbox and make the HI box (cable->shunt) overlap the LO box (shunt->cable).
        shunt_refs = {ref for ref in (refs_hi & refs_lo) if padcount.get(ref, 0) == 2}
        # PER-SIDE (dual-sided, 2026-07-08): a back-side rail's pours go on B.Cu, keyed off
        # the shunt's face (THT connector/blade barrels reach both faces, so a B pour
        # connects them identically).
        pair_layer = layer
        if shunt_refs and flipped.get(sorted(shunt_refs)[0]):
            pair_layer = "B.Cu"
        if inner_layer is not None:
            pair_layer = inner_layer
        # shunt centre + corridor axis (for the SHUNT_GAP_MM notch): the two pads of the 2-pad shunt
        # on this pair's HI/LO nets. Vertical corridor (EPS/PCIe top->bottom) if the pads differ more
        # in y than x. None when there is no qualifying 2-pad shunt -> the notch is a no-op (the box
        # keeps hugging the shunt pad, the historical behaviour).
        sh_pads = [(px, py) for ref, px, py, _t in (pads_by_net.get(hi, []) + pads_by_net.get(lo, []))
                   if ref in shunt_refs]
        shunt_xy = vertical = None
        if _shunt_gap_on() and len(sh_pads) >= 2:
            scx = sum(q[0] for q in sh_pads) / len(sh_pads)
            scy = sum(q[1] for q in sh_pads) / len(sh_pads)
            shunt_xy = (scx, scy)
            vertical = (max(q[1] for q in sh_pads) - min(q[1] for q in sh_pads)) >= \
                       (max(q[0] for q in sh_pads) - min(q[0] for q in sh_pads))
        for net in (hi, lo):
            entries = pads_by_net.get(net, [])
            has_tht = any(it[3] for it in entries)
            if not has_tht:
                continue                          # not a cable high-current net -> skip
            tht_entries, shunt_pts = [], []
            for ref, px, py, is_tht in entries:
                if ref in shunt_refs:
                    shunt_pts.append((px, py))
                elif is_tht:
                    tht_entries.append((ref, px, py))
            if not (tht_entries or shunt_pts):
                continue
            # PER-CLUSTER FAN-IN (escalated review 2026-07-08): the ATX-24's interleaved
            # pinout puts one rail's pins in 2-3 groups across the header; one bbox over all
            # of them spanned the board and overlapped the neighbor rails' pours on the same
            # layer (mass unconnected + foreign-on-pour). One sub-pour per pin x-cluster,
            # each converging on the shunt, keeps the copper a fan instead of a blanket.
            clusters = _terminal_aware_x_clusters(
                tht_entries, padcount) or [[]]
            _lanes_on = os.environ.get("CEC_POUR_LANES", "0") == "1"
            for cluster in clusters:
                if _lanes_on and cluster:
                    for (lx0, ly0, lx1, ly1) in _cluster_lanes(cluster, shunt_pts, net,
                                                               (bx0, by0, bx1, by1), margin):
                        # lanes carry their own band/finger geometry -- no notch re-clip
                        pours.append({"net": net, "layer": pair_layer,
                                      "polygon": [(lx0, ly0), (lx1, ly0),
                                                  (lx1, ly1), (lx0, ly1)]})
                    continue
                heavy = list(cluster) + shunt_pts
                if not heavy:
                    continue
                xs = [x for x, _ in heavy]
                ys = [y for _, y in heavy]
                x0 = max(bx0, min(xs) - margin); x1 = min(bx1, max(xs) + margin)
                y0 = max(by0, min(ys) - margin); y1 = min(by1, max(ys) + margin)
                if shunt_xy is not None:          # open the un-poured notch at the shunt to SHUNT_GAP_MM
                    x0, x1, y0, y1 = _open_shunt_notch((x0, x1, y0, y1), shunt_xy, _shunt_gap_mm(),
                                                       vertical=vertical)
                pours.append({"net": net, "layer": pair_layer,
                              "polygon": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]})
    # SAME-LAYER OVERLAP CLIP (escalated review round 2, 2026-07-08): fan sub-boxes can
    # overlap on one layer -- CROSS-NET (broken fills) and SAME-NET too: KiCad flags
    # equal-priority overlapping zones as zones_intersect even on one net (measured: the
    # 3V3/5V fans converging at their shunt). Deterministic priority = list order (earlier
    # box wins); the later box is clipped on the axis that loses less area, dropped if it
    # degenerates (< 1mm). Same-net clipped boxes ABUT exactly, so their fills stay
    # electrically continuous at the shared edge.
    def _rect(p):
        xs = [q[0] for q in p["polygon"]]; ys = [q[1] for q in p["polygon"]]
        return min(xs), max(xs), min(ys), max(ys)
    kept = []
    for p in pours:
        x0, x1, y0, y1 = _rect(p)
        dead = False
        for q in kept:
            if q["layer"] != p["layer"]:
                continue
            qx0, qx1, qy0, qy1 = _rect(q)
            if x1 <= qx0 or x0 >= qx1 or y1 <= qy0 or y0 >= qy1:
                continue
            # clip p on the cheaper axis
            cands = []
            if qx0 > x0:
                cands.append(("x1", qx0, (x1 - qx0) * (y1 - y0)))
            if qx1 < x1:
                cands.append(("x0", qx1, (qx1 - x0) * (y1 - y0)))
            if qy0 > y0:
                cands.append(("y1", qy0, (x1 - x0) * (y1 - qy0)))
            if qy1 < y1:
                cands.append(("y0", qy1, (x1 - x0) * (qy1 - y0)))
            if not cands:
                dead = True                              # fully contained
                break
            edge, val, _loss = min(cands, key=lambda c: c[2])
            if edge == "x0":
                x0 = val
            elif edge == "x1":
                x1 = val
            elif edge == "y0":
                y0 = val
            else:
                y1 = val
            if x1 - x0 < 1.0 or y1 - y0 < 1.0:
                dead = True
                break
        if not dead:
            p["polygon"] = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            kept.append(p)
    return kept



def derive_power_pours(board_path: str, *, margin: float = 1.0, edge_clear: float = 0.4,
                       layer: str = "F.Cu", kelvin_pairs=None, board=None) -> list:
    """Auto-derive additive high-current pour rectangles for an interposer board.

    For each Kelvin pair (``*_HI`` / ``*_LO``) the pour is the bounding box of that net's
    HEAVY pads -- the THT connector pads (the cable in/out) PLUS the shunt's own pad on
    that net -- inflated by *margin* mm and clamped *edge_clear* mm inside the board edge.
    The shunt is identified geometrically as the footprint that has a pad on BOTH members
    of the pair (only a Kelvin shunt straddles HI and LO). The small SMD sense pads of the
    INA / INA181 are deliberately EXCLUDED, so the HI box (cable-in -> shunt) and the LO box
    (shunt -> cable-out) stay on their own sides of the shunt and never overlap -- they meet
    only through the shunt element, exactly as a four-wire Kelvin shunt requires.

    SELF-GATING: a net with no THT pad is not a cable high-current net and is skipped, so on
    a board with no qualifying nets this returns ``[]`` and is a no-op. Verified on EPS: yields
    the four 12V pours (/SENSEC1_HI,_LO,/SENSEC2_HI,_LO) matching the hand-tuned regions.

    Returns a list of pour dicts ready for :func:`add_power_pours` / ``Spec.power_pours``.
    Pass an already-loaded *board* to reuse it (pcbnew shares the cached BOARD per path, so callers
    that also mutate the board must load it ONCE and pass it here rather than re-load board_path).

    POUR LEVER (stage 1, docs/pour-lever-scoping-2026-07-08.md): this is now a thin POST-ROUTE
    VIEW of a ``cec_pourplan.PourPlan`` -- ``PourPlan.from_board`` runs the SAME board-read +
    ``_pour_boxes_core`` geometry kernel this body used to, and ``pour_polygons()`` returns the
    identical ``{net, layer, polygon}`` dict list. Kept byte-for-byte (build/pourwt teeth).
    """
    import cec_pourplan
    return cec_pourplan.PourPlan.from_board(
        board_path, board=board, kelvin_pairs=kelvin_pairs,
        margin=margin, edge_clear=edge_clear, layer=layer).pour_polygons()


def _x_clusters(pts, gap_mm=8.0):
    """Split (x,y) points into x-clusters (single-linkage, split at > gap_mm). The ATX-24's
    interleaved pinout puts one rail's pins in 2-3 groups across the header; one bbox over
    all of them spans the board (escalated review 2026-07-08) -- fan-in per cluster instead."""
    if not pts:
        return []
    pts = sorted(pts)
    out = [[pts[0]]]
    for p in pts[1:]:
        if p[0] - out[-1][-1][0] > gap_mm:
            out.append([p])
        else:
            out[-1].append(p)
    return out


def _terminal_aware_x_clusters(entries, padcount, gap_mm=8.0):
    """Cluster PTH points without splitting one monolithic power terminal.

    ``entries`` are ``(ref, x, y)``.  When every physical pad of a footprint
    belongs to this one net, the footprint is one metal conductor and its pads
    form an indivisible seed even when their pitch exceeds the ordinary
    connector-pin gap.  Mixed-net headers retain the historical pointwise
    clustering, so an interleaved ATX rail cannot become a board-wide blanket.
    """
    by_ref = {}
    for ref, x, y in entries:
        by_ref.setdefault(ref, []).append((x, y))
    seeds = []
    for ref, points in by_ref.items():
        if int(padcount.get(ref, 0)) == len(points):
            seeds.append(list(points))
        else:
            seeds.extend([[point] for point in points])
    seeds.sort(key=lambda group: (min(point[0] for point in group),
                                  max(point[0] for point in group)))
    clusters = []
    for group in seeds:
        if (not clusters or
                min(point[0] for point in group) -
                max(point[0] for point in clusters[-1]) > gap_mm):
            clusters.append(list(group))
        else:
            clusters[-1].extend(group)
    return [sorted(cluster) for cluster in clusters]


def corridor_keepouts(board_path, *, kelvin_pairs=None, nets_12v=None, board=None,
                      layers=("F.Cu", "B.Cu")):
    """Route-time NOTCHED corridor keepout (the ENFORCE leg of the high-current-corridor-keepout /
    high-current-pour-integrity / kelvin-tap-inner-shunt-edge corpus rules).

    *layers* selects which copper layers the keepout reserves. The default reserves BOTH outer pour
    layers (F.Cu + B.Cu) so a foreign trace cannot cut either mirror. Passing ``("F.Cu",)`` reserves
    ONLY F.Cu -- the "layer-tier lever": foreign then routes on B.Cu UNDER the F.Cu pour (which the
    no-foreign-on-high-current-pour gate, F.Cu-scoped, treats as clear), so pass-1 itself lands
    foreign-on-pour=0 with the F.Cu pour solid, WITHOUT a TPC re-route (whose track-based LO re-route
    trips the cut-vertex kelvin check). Pair with tap_channel_keepouts so the notch tap channels stay
    clear too.

    Reserve each high-current FORCE corridor -- the cable connector THT pads' span extended to the 2-pad
    Kelvin shunt -- as a Freerouting keepout, CLIPPED on the shunt's inner side so the tap window
    (shunt-inner-edge -> INA, which the pour deliberately excludes) stays open. That clip IS the "notch":
    FR routes foreign +3V3/GND/signal AROUND the corridor, so the post-route additive power pour fills it
    SOLID instead of being cut into islands by a foreign trace (which would otherwise leave the thin
    0.2mm FR trace carrying the 40A). allow_vias=True so a boxed-in sensor pad can still escape DOWN.

    This is the piece cec_router.route() has (so it converges) and route_directed lacked (so the agentic
    loop stalled on pour-clip). Force nets = the Kelvin _HI/_LO pairs + the 12V nets (derived from the
    board via cec_score.Rules when not given). SELF-GATING: a net with no THT cable pad or no 2-pad shunt
    is skipped, so a shared-bus board (Hub: no cables) returns []. Returns bake_hints-ready dicts.

    POUR LEVER (stage 1, docs/pour-lever-scoping-2026-07-08.md): this is now a thin PRE-ROUTE VIEW
    of a ``cec_pourplan.PourPlan`` -- ``PourPlan.keepout_hints`` reboxes the plan's own pours in
    LANE mode (the keepouts ARE the lane pour shapes) and delegates to ``_force_corridor_hints``
    (the non-lane force-corridor loop below, extracted verbatim) otherwise. Byte-identical (teeth)."""
    import cec_pourplan
    return cec_pourplan.PourPlan.from_board(
        board_path, board=board, kelvin_pairs=kelvin_pairs,
        nets_12v=nets_12v).keepout_hints(layers=layers)


def _force_corridor_hints(board, board_path, *, kelvin_pairs=None, nets_12v=None,
                          layers=("F.Cu", "B.Cu")):
    """NON-LANE force-corridor keepout body (pour lever stage 1, extracted VERBATIM from the old
    corridor_keepouts): reserve each cable connector->shunt FORCE corridor as a Freerouting keepout,
    CLIPPED at the shunt notch so the Kelvin tap window stays open. ``PourPlan.keepout_hints``
    delegates here for the non-lane path (the lane path reboxes the plan's own ``pour_polygons()``).
    *board* is already loaded; *kelvin_pairs* resolved by the plan (else board-derived here)."""
    _inner_mode = False
    if os.environ.get("CEC_INNER_POURS", "0") == "1":        # see derive_power_pours: experimental
        for _lid in range(pcbnew.PCB_LAYER_ID_COUNT):
            try:
                if board.GetLayerName(_lid) == "PWR_RT" and board.GetLayerType(_lid) == pcbnew.LT_SIGNAL:
                    _inner_mode = True
                    break
            except Exception:                                # noqa: BLE001
                pass
    if kelvin_pairs is None:
        kelvin_pairs = _board_kelvin_pairs(board)
    if nets_12v is None:
        try:
            import cec_score
            nets_12v = cec_score.Rules.from_board(board_path).nets_12v
        except Exception:                                    # noqa: BLE001 -- 12V nets are optional
            nets_12v = []
    force_nets = set(nets_12v)
    for hi, lo in kelvin_pairs:
        force_nets.add(hi)
        force_nets.add(lo)

    pads_by_net = {}
    npads = {}
    for fp in board.GetFootprints():
        npads[fp.GetReference()] = fp.GetPadCount()
        for p in fp.Pads():
            nn = p.GetNetname()
            if nn:
                pads_by_net.setdefault(nn, []).append(p)

    hints = []
    for net in sorted(force_nets):
        entries = pads_by_net.get(net, [])
        tht_entries = []
        for fp in board.GetFootprints():
            ref = fp.GetReference()
            for pad in fp.Pads():
                if (pad.GetNetname() == net and
                        pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH):
                    pos = pad.GetPosition()
                    tht_entries.append((ref, pos.x / MM, pos.y / MM))
        # the 2-pad shunt footprint straddling this net. STRADDLE-FIRST (escalated review
        # 2026-07-08): the shunt is the 2-pad footprint whose pads sit on BOTH members of
        # the net's kelvin pair (prefer RS*) -- the old any-2-pad-on-the-net rule grabbed a
        # DECOUPLING CAP on rail-sided nets (+5V_MAIN), collapsing the corridor to a sliver.
        pair_other = None
        for hi, lo in kelvin_pairs:
            if net == hi:
                pair_other = lo
            elif net == lo:
                pair_other = hi
        cands = []
        for fp in board.GetFootprints():
            if npads.get(fp.GetReference(), 0) != 2:
                continue
            fp_nets = {p.GetNetname() for p in fp.Pads()}
            if net not in fp_nets:
                continue
            if pair_other is not None and pair_other not in fp_nets:
                continue                                     # not the straddle part (a cap)
            if pair_other is None and not fp.GetReference().startswith("RS"):
                continue                                     # non-pair net (name-matched "12V"
                                                             # like /ATX_NEG12V): only a REAL
                                                             # shunt makes it a force corridor
            cands.append(fp)
        cands.sort(key=lambda f: (not f.GetReference().startswith("RS"), f.GetReference()))
        shunt = []
        shunt_centre_y = None
        shunt_flipped = False
        if cands:
            fp = cands[0]
            shunt = [(p.GetPosition().x / MM, p.GetPosition().y / MM)
                     for p in fp.Pads() if p.GetNetname() == net]
            shunt_centre_y = fp.GetPosition().y / MM
            shunt_flipped = fp.IsFlipped()
        if not tht_entries or not shunt:
            continue                                         # not a cable-connector high-current net
        # PER-PAIR LAYER (dual-sided): a flipped chain's pour lives on B.Cu -- reserve THAT,
        # never F.Cu-only (the oracle's F-only lever was inverted for back chains). INNER-POUR
        # boards (PWR_RT layer) reserve In2 instead -- the rail copper lives there and both
        # faces stay free for signals.
        net_layers = ("B.Cu",) if (shunt_flipped and tuple(layers) == ("F.Cu",)) else tuple(layers)
        if _inner_mode:
            net_layers = ("In2.Cu",)
        sx, sy = shunt[0]
        # notch edge = shunt centre +/- SHUNT_GAP_MM/2 when the widen is on (matching derive_power_pours
        # so the keepout never blocks the B.Cu overflow lane), else the historical clip AT the shunt pad.
        clip_hi = (shunt_centre_y - _shunt_gap_mm() / 2.0) if (_shunt_gap_on() and shunt_centre_y is not None) else sy
        clip_lo = (shunt_centre_y + _shunt_gap_mm() / 2.0) if (_shunt_gap_on() and shunt_centre_y is not None) else sy
        # PER-CLUSTER FAN-IN (escalated review 2026-07-08): one box per connector pin
        # x-cluster, each converging on the shunt column -- never one bbox over an
        # interleaved rail's whole pin spread (the 5V box spanned the board).
        for ci, cluster in enumerate(_terminal_aware_x_clusters(
                tht_entries, npads)):
            txs = [x for x, _ in cluster]
            tys = [y for _, y in cluster]
            tcy = sum(tys) / len(tys)
            x0 = min(txs + [sx]) - 1.0
            x1 = max(txs + [sx]) + 1.0
            if sy >= tcy:                                    # shunt BELOW the connector (cable-in): clip bottom at the notch top
                y0, y1 = min(tys) - 1.0, clip_hi
            else:                                            # shunt ABOVE the connector (cable-out): clip top at the notch bottom
                y0, y1 = clip_lo, max(tys) + 1.0
            hints.append({"name": f"corr_{net.strip('/')}_{ci}" if ci else f"corr_{net.strip('/')}",
                          "x0": round(x0, 2), "y0": round(y0, 2),
                          "x1": round(x1, 2), "y1": round(y1, 2),
                          "layers": net_layers, "allow_vias": True,
                          # block FOREIGN tracks (FR routes around) but let the SAME-NET power pour fill the
                          # reserved corridor SOLID -- the keepout protects the pour, it must not block it.
                          "block_fills": False})
    return hints


def _fp_bbox_no_text(fp):
    """A footprint's bounding box EXCLUDING its silk/fab reference + value TEXT. pcbnew's bare
    FOOTPRINT.GetBoundingBox() folds in the F.Fab Value string, so a tiny part with a long value
    reads enormous -- the M3 mounting hole (true courtyard 6.95mm) reports a 25.54mm-wide bbox
    because its Value is the 28-char 'MountingHole_3.2mm_M3_Pad_Via'. Used by edge_keepout so an
    edge-resident part's keepout EXCLUSION is its real copper/courtyard extent, not its text (an
    inflated mount bbox otherwise punched a ~25mm hole in the board-edge keepout strip)."""
    try:
        return fp.GetBoundingBox(False, False)              # (aIncludeText=False, aIncludeInvisibleText=False)
    except TypeError:
        try:
            return fp.GetBoundingBox(False)
        except TypeError:
            return fp.GetBoundingBox()


def fiducial_keepouts(board_path, *, board=None, margin=0.0):
    """Return route/fill keepouts for global assembly fiducials.

    Freerouting imports an unconnected fiducial pad as ordinary no-net copper,
    but it does not preserve the pad's larger local-clearance override.  It can
    therefore leave a route that is legal to its global class rules yet fails
    KiCad DRC against the fiducial (the Hub FID1/EN 0.5023 mm vs 0.6000 mm
    failure).  Use the footprint's real no-text bounding box, which includes
    its courtyard/optical working field, as a rule area on the fiducial's own
    outer layer.  Inner and opposite-side routing remains available.

    These are assembly constraints, so vias and zone fills are blocked along
    with tracks.  The helper is self-gating and works for both ``FID*`` refs and
    library footprints whose name contains ``Fiducial``.
    """
    own = board if board is not None else pcbnew.LoadBoard(board_path)
    hints = []
    for fp in own.GetFootprints():
        ref = str(fp.GetReference() or "")
        try:
            lib_name = str(fp.GetFPID().GetLibItemName() or "")
        except Exception:                              # noqa: BLE001
            lib_name = ""
        if not (ref.upper().startswith("FID")
                or "FIDUCIAL" in lib_name.upper()):
            continue
        layer = own.GetLayerName(fp.GetLayer())
        if layer not in ("F.Cu", "B.Cu"):
            layer = "B.Cu" if fp.IsFlipped() else "F.Cu"
        bbox = _fp_bbox_no_text(fp)
        pad = max(0.0, float(margin))
        hints.append({
            "name": "assembly_fiducial_%s" % (ref or len(hints) + 1),
            "x0": round(bbox.GetLeft() / MM - pad, 3),
            "y0": round(bbox.GetTop() / MM - pad, 3),
            "x1": round(bbox.GetRight() / MM + pad, 3),
            "y1": round(bbox.GetBottom() / MM + pad, 3),
            "layers": (layer,),
            "allow_vias": False,
            "block_fills": True,
        })
    return hints


def edge_keepout(board_path, *, margin=1.25, clearance=0.8, board=None,
                 edge_refs=("J", "H"), layers=None,
                 access_windows=False):
    """Route-time board-EDGE keepout (lever B, 2026-06-17). Freerouting has NO board-edge-clearance
    awareness -- the standard ExportSpecctraDSN gives it only the outline, so it routes signal tracks hard
    against Edge.Cuts (measured: ~100% of a routed CEC board's DRC is copper_edge_clearance, incl. a 67mm
    track run along the perimeter). Reserve a *margin*-wide strip just inside each board edge so FR keeps
    tracks off it. By default the strip is continuous: a body overhang is not
    permission for unrelated copper to use a footprint-wide edge channel, and
    normal edge connectors launch from pad centres already seated inward of the
    strip. ``access_windows=True`` restores the legacy footprint-bounding-box
    openings for an explicitly audited board whose conductive lands truly lie
    inside the strip. allow_vias=False (no copper of any kind in the strip);
    block_fills=False so the high-current pours still fill to their own edge clamp. Returns bake_hints-ready
    rects; SELF-GATING (a board with no outline / all-edge parts yields fewer/no strips). Stack with
    corridor_keepouts in the same hints list.

    MARGIN IS WIDTH-AWARE (2026-07-23 forensic): the keepout constrains a track's
    CENTER, but the DRC edge rule (min_copper_edge_clearance 0.5) measures the
    track EDGE -- the hub best's 19 edge hits were 1.0mm Power tracks whose
    centers sat legally at 0.845 (old 0.6 strip + FR clearance) with edges at
    0.345. margin = rule 0.5 + half the widest carried class width (1.5mm Power
    -> 0.75) = 1.25, so even the fattest class keeps its edge >= the rule."""
    own = board if board is not None else pcbnew.LoadBoard(board_path)
    if layers is None:
        # ROUTABLE-LAYER DERIVATION (2026-07-23, hub In2-signal conformance): F/B always
        # (historical behavior -- outer pours keep their own edge clamp, block_fills
        # False) plus any enabled inner copper FR can ACTUALLY route: signal-KIND in
        # the layer table AND not a detected plane. plane_layers is the SAME detector
        # the DSN export policy uses to exclude planes from FR, so the strips exactly
        # cover FR's real solution space -- a stale signal-typed In1 "GND" plane (the
        # frozen golden EPS, the alpha hub) stays OUT and those routes are untouched,
        # while a freed In2 (inner_power_routing; empty pre-route, floods land after)
        # comes IN. Canonical names: GetLayerID resolves user names too, but
        # 'PWR_RT'/'GND' aliases would confuse the hint sidecars.
        _plane = set()
        for _pn in plane_layers(own):
            _pl = own.GetLayerID(_pn)
            if _pl >= 0:
                _plane.add(_pl)
        layers = tuple(pcbnew.LayerName(lid) for lid in own.GetEnabledLayers().CuStack()
                       if lid in (pcbnew.F_Cu, pcbnew.B_Cu)
                       or (own.GetLayerType(lid) == pcbnew.LT_SIGNAL
                           and lid not in _plane))
    bb = own.GetBoardEdgesBoundingBox()
    if bb.GetWidth() <= 0 or bb.GetHeight() <= 0:
        return []
    L, T = bb.GetLeft() / MM, bb.GetTop() / MM
    R, Bn = bb.GetRight() / MM, bb.GetBottom() / MM        # T<Bn (KiCad: top=min y, bottom=max y)

    def _edge_resident(fp):
        ref = fp.GetReference()
        if ref[:1] in edge_refs:
            return True
        name = str(fp.GetFPID().GetLibItemName()).upper()
        return any(k in name for k in ("MOUNTING", "CONN", "RJ45", "USB", "JST", "MOLEX"))

    allow = []                                              # audited legacy access openings
    if access_windows:
        for fp in own.GetFootprints():
            if _edge_resident(fp):
                fb = _fp_bbox_no_text(fp)
                allow.append((fb.GetLeft() / MM - clearance,
                              fb.GetTop() / MM - clearance,
                              fb.GetRight() / MM + clearance,
                              fb.GetBottom() / MM + clearance))

    def _subtract(a0, a1, spans):                          # 1-D: [a0,a1] minus the exclude spans
        cuts = sorted(s for s in spans if s[1] > a0 and s[0] < a1)
        segs, cur = [], a0
        for s0, s1 in cuts:
            if s0 > cur:
                segs.append((cur, min(s0, a1)))
            cur = max(cur, s1)
        if cur < a1:
            segs.append((cur, a1))
        return [(x, y) for x, y in segs if y - x > 0.5]    # drop slivers FR can't use anyway

    hints = []
    for nm, y0, y1 in (("top", T, T + margin), ("bottom", Bn - margin, Bn)):   # split by X
        ex = [(a[0], a[2]) for a in allow if a[1] < y1 and a[3] > y0]
        for i, (x0, x1) in enumerate(_subtract(L, R, ex)):
            hints.append({"name": f"edge_{nm}_{i}", "x0": round(x0, 2), "y0": round(y0, 2),
                          "x1": round(x1, 2), "y1": round(y1, 2), "layers": layers,
                          "allow_vias": False, "block_fills": False})
    for nm, x0, x1 in (("left", L, L + margin), ("right", R - margin, R)):      # split by Y
        ex = [(a[1], a[3]) for a in allow if a[0] < x1 and a[2] > x0]
        for i, (y0, y1) in enumerate(_subtract(T, Bn, ex)):
            hints.append({"name": f"edge_{nm}_{i}", "x0": round(x0, 2), "y0": round(y0, 2),
                          "x1": round(x1, 2), "y1": round(y1, 2), "layers": layers,
                          "allow_vias": False, "block_fills": False})
    # CURVED-EDGE COVER (2026-07-23 forensic): the strips derive from the AABB,
    # but a ROUNDED CORNER (hub corner_radius 2.5) curves the real outline
    # INSIDE the AABB -- copper in the corner notch is legal-by-strip yet
    # violates against the arc (all 20 residual edge hits on the rung probe sat
    # at the two arc corners). Cover every Edge.Cuts ARC's bbox + margin.
    ai = 0
    for d in own.GetDrawings():
        try:
            if own.GetLayerName(d.GetLayer()) != "Edge.Cuts":
                continue
            if d.GetShape() != pcbnew.SHAPE_T_ARC:
                continue
        except Exception:                                   # noqa: BLE001
            continue
        ab = d.GetBoundingBox()
        hints.append({"name": f"edge_arc_{ai}",
                      "x0": round(ab.GetLeft() / MM - margin, 2),
                      "y0": round(ab.GetTop() / MM - margin, 2),
                      "x1": round(ab.GetRight() / MM + margin, 2),
                      "y1": round(ab.GetBottom() / MM + margin, 2),
                      "layers": layers,
                      "allow_vias": False, "block_fills": False})
        ai += 1
    # INTERNAL APERTURES (reverse-mount LEDs, optical windows, slots) are
    # Edge.Cuts too. The perimeter-strip logic cannot see footprint-local
    # graphics, so FR previously routed tracks straight across those holes.
    # Reserve the cut itself plus a small machining guard. Copper pads that
    # intentionally flank a vendor aperture remain outside this box and route
    # away from it; their explicit local edge-clearance rule owns pad-to-hole.
    ci = 0
    # This is copper-to-machined-edge clearance, not merely a plotting guard.
    # The Hub's board rule is 0.50 mm; 0.20 let post-route SIG2 tracks pass
    # 0.473 mm from a reverse-LED aperture and let vias get closer still.
    # Vendor-authored LED pads are handled by their narrowly scoped DRC rule,
    # while routed copper must meet the ordinary board-edge rule.
    cut_guard = 0.50
    for fp in own.GetFootprints():
        for drawing in fp.GraphicalItems():
            try:
                if own.GetLayerName(drawing.GetLayer()) != "Edge.Cuts":
                    continue
            except Exception:                              # noqa: BLE001
                continue
            cb = drawing.GetBoundingBox()
            hints.append({
                "name": "edge_cutout_%s_%d" % (fp.GetReference(), ci),
                "x0": round(cb.GetLeft() / MM - cut_guard, 2),
                "y0": round(cb.GetTop() / MM - cut_guard, 2),
                "x1": round(cb.GetRight() / MM + cut_guard, 2),
                "y1": round(cb.GetBottom() / MM + cut_guard, 2),
                "layers": layers,
                "allow_vias": False,
                "block_fills": False,
            })
            ci += 1
    return hints


# ---------------------------------------------------------------------------
# derive_via_field / add_via_field -- the OQ-10 "more parallel vias" fix
# ---------------------------------------------------------------------------
def _pt_seg_dist(px, py, ax, ay, bx, by):
    """Distance (mm) from point (px,py) to segment (ax,ay)-(bx,by)."""
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def synthesize_force_vias(board, *, kelvin_pairs=None, n_per_pad=3, drill=0.5, dia=0.9,
                          stub_w=1.0, clear=0.25, pours=None):
    """INNER-POUR companion (2026-07-08): each 2-pad SMD shunt pad gets *n_per_pad* through-vias
    just OUTBOARD of the pad (away from the shunt body, so the kelvin inner-edge tap window
    stays untouched) plus a same-net face STUB from the pad to each via -- the force path
    pad -> stub -> via -> In2 rail pour. Guarded: a via/stub that would collide with foreign
    copper (track/pad/via) within *clear* is skipped (fewer parallel barrels, honest). Lays
    copper only for pairs whose straddle shunt exists; returns {pads, vias, stubs}."""
    if kelvin_pairs is None:
        kelvin_pairs = _board_kelvin_pairs(board)
    nets = {n.GetNetname(): c for c, n in board.GetNetInfo().NetsByNetcode().items()}
    from collections import defaultdict
    pads_by_net = defaultdict(list)
    padcount = {}
    for fp in board.GetFootprints():
        padcount[fp.GetReference()] = fp.GetPadCount()
        for p in fp.Pads():
            if p.GetNetname():
                pads_by_net[p.GetNetname()].append((fp.GetReference(), p, fp))
    # VIA-SPACING LEDGER (2026-07-23, owner catch "vias clipping into each
    # other" on s218: the locked rail arrays already sit at these outboard
    # spots, and the per-layer pour emission made this stage fire on top of
    # them -- 9 same-net stacks at 0.1-0.4mm). Existing barrels of ANY net +
    # own placements; hole spacing is net-agnostic.
    ex_vias = [(t.GetPosition().x, t.GetPosition().y)
               for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    # COVERAGE REQUIREMENT (owner catch 2026-07-24: 6 vias dangled at RS1 --
    # seated where NO kept pour on another layer would receive them). When the
    # caller passes the FILTERED pour dicts, a via spot must sit inside a
    # same-net dict's rect or it is skipped (a barrel into nothing helps nothing).
    _cover = defaultdict(list)
    for p in (pours or ()):
        poly = p.get("polygon") or ()
        if p.get("net") and poly:
            xs = [q[0] for q in poly]
            ys = [q[1] for q in poly]
            _cover[p["net"]].append((min(xs), min(ys), max(xs), max(ys)))
    n_v = n_s = n_p = 0
    for hi, lo in kelvin_pairs:
        refs_hi = {r for r, _, _ in pads_by_net.get(hi, [])}
        refs_lo = {r for r, _, _ in pads_by_net.get(lo, [])}
        sh = next((r for r in sorted(refs_hi & refs_lo)
                   if r.startswith("RS") and padcount.get(r) == 2), None)
        if sh is None:
            continue
        sh_pads = [(net, p) for net in (hi, lo) for r, p, _f in pads_by_net.get(net, []) if r == sh]
        if len(sh_pads) != 2:
            continue
        (net_a, pa), (net_b, pb) = sh_pads
        for net, p, other in ((net_a, pa, pb), (net_b, pb, pa)):
            nc = nets.get(net)
            if nc is None:
                continue
            pos, opos = p.GetPosition(), other.GetPosition()
            # outboard direction: away from the other terminal
            dx, dy = pos.x - opos.x, pos.y - opos.y
            L = max((dx * dx + dy * dy) ** 0.5, 1)
            ux, uy = dx / L, dy / L
            step = _nm(dia + 0.35)
            # base clears the pad's own extent along the outboard axis
            # (assembly-class via-in-pad ruling 2026-07-25: a fixed 1.6mm
            # from the CENTER of a long shunt pad lands INSIDE it)
            try:
                _sz = p.GetSize()
                _half_along = (abs(ux) * _sz.x + abs(uy) * _sz.y) / 2.0
            except Exception:                          # noqa: BLE001
                _half_along = 0
            _bd = max(_nm(1.6), int(_half_along + _nm(dia) / 2.0 + _nm(0.1)))
            base = pcbnew.VECTOR2I(int(pos.x + ux * _bd), int(pos.y + uy * _bd))
            perp = (-uy, ux)
            placed = 0
            for k in range(n_per_pad):
                off = (k - (n_per_pad - 1) / 2.0)
                at = pcbnew.VECTOR2I(int(base.x + perp[0] * off * step),
                                     int(base.y + perp[1] * off * step))
                if any((at.x - qx) ** 2 + (at.y - qy) ** 2 < _nm(0.85) ** 2
                       for qx, qy in ex_vias):
                    continue          # a barrel already serves this spot -- never stack
                if pours is not None:
                    _ax, _ay = at.x / 1e6, at.y / 1e6
                    if not any(b0 <= _ax <= b2 and b1 <= _ay <= b3
                               for (b0, b1, b2, b3) in _cover.get(net, ())):
                        continue      # no kept pour will receive this barrel
                if not _tap_pair_overlap_clear(board, pos, at, _nm(stub_w),
                                               board.GetLayerID(p.GetLayerName()), nc, set()):
                    continue
                # assembly-class via-in-pad exclusion (owner ruling
                # 2026-07-25): any pad, own net included
                if _via_pad_excluded(board, at, _nm(dia), _nm(drill), nc) is not None:
                    continue
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(at)
                v.SetDrill(_nm(drill))
                v.SetWidth(_nm(dia))
                v.SetNetCode(nc)
                board.Add(v)
                ex_vias.append((at.x, at.y))
                tr = pcbnew.PCB_TRACK(board)
                tr.SetStart(pos)
                tr.SetEnd(at)
                tr.SetWidth(_nm(stub_w))
                tr.SetLayer(board.GetLayerID(p.GetLayerName()))
                tr.SetNetCode(nc)
                board.Add(tr)
                n_v += 1
                n_s += 1
                placed += 1
            if placed:
                n_p += 1
    return {"pads": n_p, "vias": n_v, "stubs": n_s}


def partition_prebond_pours(pours, *, overunder=False):
    """Return ``(bond_now, deferred)`` for the import pre-bond stage.

    A placer-owned over-under ask is an instruction to synthesize a connected
    lane, not copper that can already prove a bond. Keeping this decision pure
    makes the stage-ordering contract independently testable.
    """
    pours = list(pours or ())
    if not overunder:
        return pours, []
    deferred = [p for p in pours if p.get("provenance") == "placer_ask"]
    bond_now = [p for p in pours if p.get("provenance") != "placer_ask"]
    return bond_now, deferred


def synthesize_pour_bonds(board, pours, *, drill=0.5, dia=0.9, max_per=3,
                          clearance=0.25):
    """POUR-BOND GUARANTEE (2026-07-23, owner catch on s218: 23 mirror-layer
    pours carried no same-net barrel inside their region -- dead or only
    incidentally-connected copper. The mirror doctrine was always 'bonded by
    the through arrays/barrels', but the layers[0] truncation had hidden the
    mirror dicts; un-truncating them exposed the missing bond half). Per net,
    the LARGEST pour's layer is its PRIMARY -- legitimate distribution copper,
    never barrel-required. Every NON-primary (mirror) dict must contain a
    same-net via/THT pad, or this pass plants up to *max_per* bond vias inside
    its overlap with a same-net pour on another layer (all-layer foreign-clear
    + 0.85mm barrel spacing + copper-edge margin). A mirror with no barrel and
    no plantable bond is DROPPED loudly -- no dead copper on the board.
    Returns (kept_pours, {bonded, planned, dropped})."""
    from collections import defaultdict
    nets_nc = {n.GetNetname(): c for c, n in board.GetNetInfo().NetsByNetcode().items()}
    all_vias = [(t.GetPosition().x, t.GetPosition().y, t.GetNetCode())
                for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    tht = defaultdict(list)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() > 0 and p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                pos = p.GetPosition()
                tht[p.GetNetCode()].append((pos.x, pos.y))
    bb = board.GetBoardEdgesBoundingBox()

    def _rect(d):
        xs = [q[0] for q in d["polygon"]]
        ys = [q[1] for q in d["polygon"]]
        return (min(xs), min(ys), max(xs), max(ys))

    def _area(r):
        return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])

    by_net = defaultdict(list)
    for d in pours:
        by_net[d["net"]].append(d)

    def _contact_on_layer(nc_, lay_id, r):
        """Same-net copper ON the pour's own layer inside the rect -- the honest
        keep criterion (2026-07-24, owner catch #2: the old primary-layer
        exemption kept auto-derived floods with no on-layer presence at all)."""
        m = _nm(0.05)
        for fp in board.GetFootprints():
            for p in fp.Pads():
                if p.GetNetCode() != nc_ or lay_id not in p.GetLayerSet().CuStack():
                    continue
                q = p.GetPosition()
                if r[0] * 1e6 - m <= q.x <= r[2] * 1e6 + m \
                        and r[1] * 1e6 - m <= q.y <= r[3] * 1e6 + m:
                    return True
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA" or t.GetNetCode() != nc_ \
                    or t.GetLayer() != lay_id:
                continue
            for q in (t.GetStart(), t.GetEnd()):
                if r[0] * 1e6 - m <= q.x <= r[2] * 1e6 + m \
                        and r[1] * 1e6 - m <= q.y <= r[3] * 1e6 + m:
                    return True
        return False

    def _fill_viable(nc_, lay_id, r):
        """Predicted-fill probe (owner catch #1 on s246: a 514mm2 F.Cu ask
        filled 8% as lace through the dense top fabric -- connected, but visual
        garbage; zones must never be REMOVED post-fill [the 2026-06-09 pcbnew
        corruption footgun], so lace-bound floods are refused BEFORE laying).
        Sample a grid over the rect; a point is open if a 0.5mm spot there
        clears foreign copper on the layer. <30% open = lace -> not viable.
        Small rects always pass (a tap-sized flood fills what it fills)."""
        if _area(r) < 30.0:
            return True
        nx = ny = 6
        open_ = 0
        for i in range(nx):
            for j in range(ny):
                ax = r[0] + (i + 0.5) * (r[2] - r[0]) / nx
                ay = r[1] + (j + 0.5) * (r[3] - r[1]) / ny
                at = pcbnew.VECTOR2I(int(ax * 1e6), int(ay * 1e6))
                probe = pcbnew.VECTOR2I(at.x + 10000, at.y)
                if _tap_foreign_clear(board, at, probe, _nm(0.5), lay_id,
                                      _nm(0.25), {nc_}):
                    open_ += 1
        # 0.45, not 0.30 (owner catch 2026-07-24 on s275: floods the probe
        # predicted >=30% open actually filled 11-20% -- the 0.5mm disc probe
        # over-estimates openness ~2x vs the real filler's carving)
        return open_ / (nx * ny) >= 0.45

    def _barrel_in(nc_, r):
        m = _nm(0.05)
        for (vx, vy, vn) in all_vias:
            if vn == nc_ and r[0] * 1e6 - m <= vx <= r[2] * 1e6 + m \
                    and r[1] * 1e6 - m <= vy <= r[3] * 1e6 + m:
                return True
        for (px, py) in tht.get(nc_, ()):
            if r[0] * 1e6 <= px <= r[2] * 1e6 and r[1] * 1e6 <= py <= r[3] * 1e6:
                return True
        return False

    # primary layer per net = the largest ask's layer: the ONE member allowed
    # to keep by mere track/pad contact. MIRROR members (any other layer) need
    # a BARREL in-region or planted bonds -- a track grazing a mirror does not
    # bond it, and a barrel-less mirror is exactly the owner's "mirrored on top
    # connected to nothing" class (2026-07-24).
    # INNER-FIRST PRIMARY (owner 2026-07-24, "the top mirror pours are
    # definitely causing issues"): power distribution belongs on the inner
    # power layer per the stackup doctrine -- F.Cu is the SIGNAL fabric, so it
    # is primary only when it is the net's ONLY layer. Preference beats area.
    _LAYPREF = {"In3.Cu": 4, "In2.Cu": 3, "B.Cu": 1}
    _primary = {}
    for net, ds in by_net.items():
        _primary[net] = max(
            ds, key=lambda d: (_LAYPREF.get(d.get("layer", "F.Cu"), 0),
                               _area(_rect(d)))).get("layer", "F.Cu")

    # MIRROR NEED TEST (owner refinement 2026-07-24: "just because the mirror
    # has barrels does not make it effective -- if a pour does not need a
    # mirror thermally for its ampacity, remove the mirror"). IPC-2221 inverse:
    # required width for 1.25x the net's current at a 30C rise on the PRIMARY
    # layer alone; if the primary's practical capacity (rect narrow dimension x
    # 0.6 fill derate) covers it, every mirror of the net drops. Conservative
    # direction: unknown current => 0 (logic nets need no mirrors); when in
    # doubt on a real current, the mirror STAYS (thermal safety wins).
    _amps = {}
    _hint = os.environ.get("CEC_THERMAL_BOARD_HINT", "")
    try:
        import cec_thermal_overlay as _ov
        _cfg4 = _ov.board_thermal_config(_hint)        # -> (net_currents, ...) tuple
        _amps = dict((_cfg4[0] if _cfg4 else None) or {})
    except Exception:                                  # noqa: BLE001
        _amps = {}

    _profile_name = (_fab.board_profile_name(board) or
                     os.environ.get("CEC_FAB_PROFILE") or
                     _fab.profile_for_board_hint(_hint))

    def _req_width_mm(amps, lay):
        if _profile_name:
            return _fab.ipc2221_required_width_mm(
                amps, lay, profile_name=_profile_name)
        copper_mm = _fab.OZ_COPPER_MM * (
            2.0 if lay in ("F.Cu", "B.Cu") else 1.0)
        return _fab.ipc2221_required_width_mm(
            amps, lay, copper_mm=copper_mm)

    def _mirror_needed(net, r):
        pr = next((_rect(x) for x in by_net[net]
                   if x.get("layer") == _primary.get(net)), None)
        if pr is None:
            return True
        cap = min(pr[2] - pr[0], pr[3] - pr[1]) * 0.6
        return _req_width_mm(_amps.get(net, 0.0), _primary[net]) > cap

    kept, n_bond = [], 0
    n_plant = n_drop = n_scrap = 0
    for d in pours:
        net, lay = d["net"], d.get("layer", "F.Cu")
        nc_ = nets_nc.get(net)
        if nc_ is None:
            kept.append(d)
            continue
        lay_id = board.GetLayerID(lay)
        r = _rect(d)
        if not _fill_viable(nc_, lay_id, r):
            n_scrap += 1
            print(f"[cec_fr] pour bonds: DROPPED lace-bound pour {net} on {lay} "
                  f"({r[0]:.1f},{r[1]:.1f})-({r[2]:.1f},{r[3]:.1f}) "
                  "(<45% predicted fill)", file=sys.stderr)
            continue
        if lay != _primary.get(net) and not _mirror_needed(net, r):
            n_drop += 1
            print(f"[cec_fr] pour bonds: DROPPED unneeded mirror {net} on {lay} "
                  "(primary carries the current at margin)", file=sys.stderr)
            continue
        # TOP = SHUNT-ONLY (owner categorical rule 2026-07-24: "remove top
        # pours unless they are around the shunts"). An F.Cu dict survives
        # only if its rect intersects a shunt neighborhood, and the kept rect
        # EXPANDS to the neighborhood so the force-via arrays sit INSIDE the
        # pour (the owner's outside-the-pour barrels catch).
        try:
            _f_power_transit = _fab.copper_layer_allows_power(
                board, "F.Cu")
        except Exception:                              # noqa: BLE001
            _f_power_transit = False
        if (lay == "F.Cu" and d.get("provenance") != "slab"
                and not _f_power_transit):
            # slab dicts are exempt: already shunt-restricted AND shaved --
            # the rect expand below would REPLACE the shaved polygon with the
            # neighborhood rectangle (traced 2026-07-24, the owner's
            # "shunt mirror did nothing" bug)
            try:
                import cec_slab_pour as _csp2
                _nbs = _csp2.shunt_neighborhoods(board)
            except Exception:                          # noqa: BLE001
                _nbs = []
            _hit = next((nb for nb in _nbs
                         if not (r[2] < nb[0] or nb[2] < r[0]
                                 or r[3] < nb[1] or nb[3] < r[1])), None)
            if _hit is None:
                n_drop += 1
                print(f"[cec_fr] pour bonds: DROPPED top pour {net} "
                      "(shunt-only rule: F.Cu pours exist only around shunts)",
                      file=sys.stderr)
                continue
            r = (min(r[0], _hit[0]), min(r[1], _hit[1]),
                 max(r[2], _hit[2]), max(r[3], _hit[3]))
            d = dict(d)
            d["polygon"] = [(r[0], r[1]), (r[2], r[1]), (r[2], r[3]),
                            (r[0], r[3])]
        # F.CU DELIVERY PROOF (owner 2026-07-24, render verdicts: a NEEDED
        # mirror on the signal fabric that fills as lace with a couple of vias
        # "isn't doing anything of value" -- justification without delivery is
        # decoration. A kept F mirror must PROVE delivery: >=60% predicted
        # fill AND >=3 barrels in-region; else it drops and the AMPACITY
        # DEFICIT prints loudly -- the honest escalation is widening the
        # primary (the slab core), never decorating the top.)
        if lay == "F.Cu" and lay != _primary.get(net):
            _nbar = 0
            for (vx, vy, vn) in all_vias:
                if vn == nc_ and r[0] * 1e6 <= vx <= r[2] * 1e6 \
                        and r[1] * 1e6 <= vy <= r[3] * 1e6:
                    _nbar += 1
            # re-probe at the strict threshold (the 45% gate above is the
            # generic scrap floor; delivery demands more)
            nx = ny = 6
            open_ = 0
            for i in range(nx):
                for j in range(ny):
                    ax = r[0] + (i + 0.5) * (r[2] - r[0]) / nx
                    ay = r[1] + (j + 0.5) * (r[3] - r[1]) / ny
                    at = pcbnew.VECTOR2I(int(ax * 1e6), int(ay * 1e6))
                    probe = pcbnew.VECTOR2I(at.x + 10000, at.y)
                    if _tap_foreign_clear(board, at, probe, _nm(0.5), lay_id,
                                          _nm(0.25), {nc_}):
                        open_ += 1
            if open_ / (nx * ny) < 0.60 or _nbar < 3:
                n_drop += 1
                print(f"[cec_fr] pour bonds: DROPPED undeliverable F mirror "
                      f"{net} ({open_}/{nx*ny} open, {_nbar} barrel(s)) -- "
                      "AMPACITY DEFICIT on the primary stands; widen the "
                      "primary (slab core), do not decorate the top",
                      file=sys.stderr)
                continue
        if _barrel_in(nc_, r) or (lay == _primary.get(net)
                                  and _contact_on_layer(nc_, lay_id, r)):
            n_bond += 1
            kept.append(d)
            continue
        # plant a bond array in the overlap with a same-net pour on another layer
        planted = 0
        for pd in sorted((x for x in by_net[net] if x.get("layer") != lay),
                         key=lambda x: -_area(_rect(x))):
            pr = _rect(pd)
            ox0, oy0 = max(r[0], pr[0]), max(r[1], pr[1])
            ox1, oy1 = min(r[2], pr[2]), min(r[3], pr[3])
            if ox1 - ox0 < dia or oy1 - oy0 < dia:
                continue
            horiz = (ox1 - ox0) >= (oy1 - oy0)
            for k in range(max_per):
                f = (k + 1) / (max_per + 1)
                ax = ox0 + f * (ox1 - ox0) if horiz else (ox0 + ox1) / 2
                ay = (oy0 + oy1) / 2 if horiz else oy0 + f * (oy1 - oy0)
                at = pcbnew.VECTOR2I(int(ax * 1e6), int(ay * 1e6))
                m = _nm(0.5) + _nm(dia) // 2
                if not (bb.GetLeft() + m <= at.x <= bb.GetRight() - m
                        and bb.GetTop() + m <= at.y <= bb.GetBottom() - m):
                    continue
                if any((at.x - vx) ** 2 + (at.y - vy) ** 2 < _nm(0.85) ** 2
                       for vx, vy, _vn in all_vias):
                    continue
                if not _via_spot_clear(board, at, _nm(dia), _nm(clearance),
                                       {nc_}, drill_nm=_nm(drill),
                                       net_code=nc_):
                    continue
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(at)
                v.SetDrill(_nm(drill))
                v.SetWidth(_nm(dia))
                v.SetNetCode(nc_)
                board.Add(v)
                all_vias.append((at.x, at.y, nc_))
                planted += 1
            if planted:
                break
        if planted:
            n_plant += planted
            kept.append(d)
        else:
            n_drop += 1
            print(f"[cec_fr] pour bonds: DROPPED unbondable pour "
                  f"{net} on {lay} ({r[0]:.1f},{r[1]:.1f})-({r[2]:.1f},{r[3]:.1f})",
                  file=sys.stderr)
    return kept, {"bonded": n_bond, "planned": n_plant, "dropped": n_drop,
                  "scrap": n_scrap}


def _segment_hits_expanded_box(start, end, box, margin_nm):
    """Whether a segment intersects an axis-aligned box expanded by margin."""
    x0, y0, x1, y1 = box
    x0, y0, x1, y1 = (x0 - margin_nm, y0 - margin_nm,
                      x1 + margin_nm, y1 + margin_nm)
    if (max(start.x, end.x) < x0 or min(start.x, end.x) > x1
            or max(start.y, end.y) < y0 or min(start.y, end.y) > y1):
        return False
    dx, dy = end.x - start.x, end.y - start.y
    if dx == 0 and dy == 0:
        return True
    corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    sides = [dy * (cx - start.x) - dx * (cy - start.y)
             for cx, cy in corners]
    return not (all(side > 0 for side in sides)
                or all(side < 0 for side in sides))


def _edge_leg_clear(board, start, end, half_width_nm, *, edge_mm=0.5):
    """Shared copper-to-Edge.Cuts guard for post-route synthesized features.

    Temporary DSN rule areas protect Freerouting, but pickups and last-mile
    copper are created after those areas are discarded.  Enforce the board-edge
    inset, rounded-corner boxes, and footprint-local apertures for both helpers.
    A zero-length leg is the corresponding via-centre check when half_width is
    the via radius.
    """
    cache = getattr(board, "_cec_edge_leg_cache", None)
    if cache is None:
        bb = board.GetBoardEdgesBoundingBox()
        outline = (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom(),
                   bb.GetWidth(), bb.GetHeight())
        arcs = []
        for drawing in board.GetDrawings():
            try:
                if (board.GetLayerName(drawing.GetLayer()) == "Edge.Cuts"
                        and drawing.GetShape() == pcbnew.SHAPE_T_ARC):
                    box = drawing.GetBoundingBox()
                    arcs.append((box.GetLeft(), box.GetTop(),
                                 box.GetRight(), box.GetBottom()))
            except Exception:                           # noqa: BLE001
                continue
        cutouts = []
        for footprint in board.GetFootprints():
            for drawing in footprint.GraphicalItems():
                try:
                    if board.GetLayerName(drawing.GetLayer()) == "Edge.Cuts":
                        box = drawing.GetBoundingBox()
                        cutouts.append((box.GetLeft(), box.GetTop(),
                                        box.GetRight(), box.GetBottom()))
                except Exception:                       # noqa: BLE001
                    continue
        cache = (outline, tuple(arcs), tuple(cutouts))
        # pcbnew BOARD proxies accept Python-side attributes.  The edge model
        # is immutable throughout route/import helpers, so one snapshot avoids
        # re-walking every footprint graphic for every maze lattice hop.
        try:
            setattr(board, "_cec_edge_leg_cache", cache)
        except Exception:                               # noqa: BLE001
            pass
    outline, arcs, cutouts = cache
    left, top, right, bottom, width, height = outline
    if width <= 0 or height <= 0:
        return True
    margin = _nm(edge_mm) + int(half_width_nm)
    for point in (start, end):
        if not (left + margin <= point.x <= right - margin
                and top + margin <= point.y <= bottom - margin):
            return False
    for box in arcs:
        if _segment_hits_expanded_box(start, end, box, margin):
            return False
    for box in cutouts:
        if _segment_hits_expanded_box(start, end, box, margin):
            return False
    return True


def synthesize_power_pickups(board, power_pours, *, plane_nets=("GND",),
                             filled_zone_nets=(), stub_w=0.3, offset=0.8,
                             drill=0.3, dia=0.6, lock=False,
                             max_offset=3.0,
                             cluster_link_max=2.0,
                             terminal_refs_by_net=None):
    """POWER-PICKUP STITCH (2026-07-23, the hub power rung's missing piece --
    measured on the rung probe: additive floods laid but the hub's power pads
    are SMD, and a pour on another layer cannot reach an F.Cu pad without a
    via; the eps precedent worked because THT pads pierce natively). For every
    SMD pad on a poured net (or a *plane_nets* net with an inner plane zone)
    that NO track/via currently touches, lay a short stub + a through-via just
    off the pad, placed INSIDE the covering pour/plane polygon, so the later
    ZONE_FILLER connects it. Foreign-collision-guarded per candidate direction
    (the synthesize_force_vias discipline); a pad with no clear direction is
    skipped loudly-by-count, never forced. On a board with an explicit POFV
    profile, a fully-contained same-net via at the pad centre is preferred; the
    guarded offset stub remains the fallback. With ``lock=True`` only the
    synthesized pickup items are fixed in the DSN; the rest of each power net
    remains routable.

    A compact same-footprint same-net pad bank may legitimately share one
    qualified POFV.  After the ordinary per-pad search, a pad that cannot fit a
    barrel may be joined to a nearby sibling pad only when that sibling already
    contains a fabrication-qualified same-net through via.  The local neck is
    still edge-, foreign-copper-, and pair-overlap-guarded.  This is deliberately
    not a generic "skip the pickup" escape: without a proven POFV anchor, the
    original fail-closed refusal remains.

    Returns {pads, vias, stubs, pofv, skipped, cluster_recovered,
    cluster_links}.

    ``filled_zone_nets`` is the post-fill form of the contract. Those nets
    are eligible only where their *actual filled polygon* contains the future
    via centre; a zone bounding box is used only as a cheap prefilter. This
    lets a second pass connect surface rail pads after shaped pours exist
    without treating the empty space between over-under lanes as copper."""
    import math as _math
    terminal_refs_by_net = {
        str(net): {str(ref) for ref in refs}
        for net, refs in dict(terminal_refs_by_net or {}).items()
        if refs is not None
    }
    nets_nc = {n.GetNetname(): c for c, n in board.GetNetInfo().NetsByNetcode().items()}
    # target polygons per net: the ask/derived pour rects + any same-net ZONE
    # outline (the GND inner plane) -- coverage is tested on the OUTLINE bbox
    # (rect pours today; plane zones are near-board-sized).
    polys = {}
    requested = set()
    for p in (power_pours or ()):
        net = p.get("net")
        if net:
            requested.add(net)
            polys.setdefault(net, [])
        poly = p.get("polygon") or ()
        if net and poly:
            xs = [q[0] for q in poly]; ys = [q[1] for q in poly]
            polys.setdefault(net, []).append((min(xs), min(ys), max(xs), max(ys)))
    exact_nets = set(filled_zone_nets or ())
    filled_polys = {}
    for z in board.Zones():
        if z.GetIsRuleArea():
            continue
        nn = z.GetNetname()
        if nn in plane_nets or nn in exact_nets:
            bb = z.GetBoundingBox()
            polys.setdefault(nn, []).append(
                (bb.GetX() / 1e6, bb.GetY() / 1e6,
                 (bb.GetX() + bb.GetWidth()) / 1e6,
                 (bb.GetY() + bb.GetHeight()) / 1e6))
        if nn in exact_nets:
            for lid in z.GetLayerSet().CuStack():
                try:
                    poly = z.GetFilledPolysList(lid)
                    if poly.OutlineCount():
                        filled_polys.setdefault(nn, []).append(poly)
                except Exception:                         # noqa: BLE001
                    continue
    if not polys:
        return {"pads": 0, "vias": 0, "stubs": 0, "pofv": 0,
                "skipped": 0, "cluster_recovered": 0,
                "cluster_links": []}
    def _filled_at(net, at):
        """Whether *at* is in real, already-filled same-net copper."""
        if net not in exact_nets:
            return True
        return any(poly.Contains(at) for poly in filled_polys.get(net, ()))

    # Use KiCad's real connectivity graph instead of an endpoint-near-bbox
    # proxy, which is ambiguous at rotated and oval lands.
    board.BuildConnectivity()
    connectivity = board.GetConnectivity()
    # A surface trace touching a pad is not, by itself, a pickup.  Treat the
    # complete same-net copper component as already promoted only when that
    # component contains a stack-spanning portal (a via or a through-hole
    # pad).  This distinction matters for complete local bypass cells: their
    # short locked rail link is intentional, but it must not suppress the one
    # via that promotes the whole cell to an inner power trunk.
    def _pickup_component(pad):
        try:
            connected = list(connectivity.GetConnectedItems(pad))
        except Exception:                              # noqa: BLE001
            connected = []
        items = [pad] + [item for item in connected
                         if item.GetNetCode() == pad.GetNetCode()]
        identities = []
        portal = False
        for item in items:
            try:
                identities.append(item.m_Uuid.AsString())
            except Exception:                          # noqa: BLE001
                identities.append("proxy:%d" % id(item))
            kind = item.GetClass()
            if kind == "PCB_VIA":
                portal = True
            elif kind == "PAD":
                try:
                    portal = portal or (
                        item.GetAttribute() != pcbnew.PAD_ATTRIB_SMD)
                except Exception:                      # noqa: BLE001
                    pass
        return tuple(sorted(set(identities))), portal

    promoted_components = set()
    tracks = [t for t in board.GetTracks()]
    # Via-spacing ledger. Ordinary pickup barrels retain the calibrated 0.85mm
    # exclusion. A declared POFV process uses its actual land/drill dimensions:
    # adjacent fine-pitch pins may legitimately be closer than 0.85mm, but
    # their copper lands and finished holes must still retain explicit gaps.
    _pk_vias = [(t.GetPosition().x, t.GetPosition().y,
                 t.GetWidth(t.TopLayer()) / MM,
                 t.GetDrillValue() / MM)
                for t in tracks if t.GetClass() == "PCB_VIA"]
    profile_name = _fab.board_profile_name(board)
    profile = _fab.get_profile(profile_name) if profile_name else None
    pofv_geometry = _fab.preferred_pofv_geometry(profile)

    def _pofv_crowded(at, candidate_dia, candidate_drill):
        for qx, qy, existing_dia, existing_drill in _pk_vias:
            # 0.15mm copper-to-copper and 0.25mm finished-hole edge gaps.
            # The latter is the limiting 0.50mm pitch case for two 0.25mm
            # drills; unlike the old centre-only 0.85mm rule, the calculation
            # remains conservative as either barrel grows.
            centre_floor = max(
                (candidate_dia + existing_dia) / 2.0 + 0.15,
                (candidate_drill + existing_drill) / 2.0 + 0.25)
            if ((at.x - qx) ** 2 + (at.y - qy) ** 2
                    < _nm(centre_floor) ** 2):
                return True
        return False
    n_p = n_v = n_s = n_pofv = n_skip = 0
    skipped_detail = []
    skipped_candidates = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            net = pad.GetNetname()
            if net not in polys:
                continue
            if (net in terminal_refs_by_net
                    and str(fp.GetReference() or "")
                    not in terminal_refs_by_net[net]):
                continue
            if pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue                       # THT pierces the stack natively
            pos = pad.GetPosition()
            px, py = pos.x / 1e6, pos.y / 1e6
            boxes = [b for b in polys[net]
                      if b[0] <= px <= b[2] and b[1] <= py <= b[3]]
            if not boxes and net not in requested:
                continue                       # no covering pour -> not ours
            component_key, has_portal = _pickup_component(pad)
            if has_portal or component_key in promoted_components:
                continue               # this entire local component pierces
            nc = nets_nc.get(net)
            if nc is None:
                continue
            lay_id = board.GetLayerID(pad.GetLayerName())
            # Use the pad net's real class geometry at synthesis time.  A
            # later final-artifact normalizer must never enlarge a pickup via
            # or stub into a pad/neighbor that was only clear at the defaults.
            try:
                netclass = board.GetNetInfo().GetNetItem(net).GetNetClassSlow()
                local_dia = max(float(dia), netclass.GetViaDiameter() / MM)
                local_drill = max(float(drill), netclass.GetViaDrill() / MM)
                class_stub_w = max(float(stub_w), netclass.GetTrackWidth() / MM)
                local_clearance = max(
                    0.25, netclass.GetClearance() / MM)
                # The pickup starts at an SMD pin.  Preserve the full class
                # width whenever the land can physically accept it.  Only a
                # genuinely narrower land receives the same bounded pin
                # neck-down enforced later by normalize_netclass_geometry.
                # The former unconditional ``minor / 2`` rule needlessly
                # narrowed even large fuse and connector lands, then locked
                # the resulting under-class launch into the priority contract.
                try:
                    board_min_w = board.GetDesignSettings().m_TrackMinWidth / MM
                except Exception:                       # noqa: BLE001
                    board_min_w = 0.2
                pad_minor = min(pad.GetSize().x, pad.GetSize().y) / MM
                local_stub_w = (
                    class_stub_w if pad_minor >= class_stub_w - 0.001 else
                    min(class_stub_w, max(
                        float(board_min_w or 0.2), pad_minor / 2.0)))
            except Exception:                            # noqa: BLE001
                local_dia, local_drill = float(dia), float(drill)
                class_stub_w = local_stub_w = float(stub_w)
                local_clearance = 0.25
            # Generation is intentionally stricter than the 1.5 mm legacy
            # normalization ceiling: an injected rail must flare promptly and
            # present a real class-width throat before its plane-entry via.
            neck_budget_mm = 0.6
            via_spacing = max(0.85, local_dia + 0.25)

            # VIA-IN-PAD FIRST. The centralized fabrication check proves the
            # declared profile, same-net identity, SMD attribute, dimensions,
            # and full-land containment. The all-layer collision probe then
            # applies the ordinary through-via clearance contract. Refusal at
            # either gate preserves the established adjacent-via fallback.
            if pofv_geometry:
                pofv_dia, pofv_drill = pofv_geometry
            else:
                pofv_dia = pofv_drill = 0.0
            if (pofv_geometry
                    and _filled_at(net, pos)
                    and not _pofv_crowded(pos, pofv_dia, pofv_drill)
                    and _edge_leg_clear(board, pos, pos,
                                       _nm(pofv_dia) // 2)
                    and _via_spot_clear(board, pos, _nm(pofv_dia), _nm(0.25),
                                        {nc}, drill_nm=_nm(pofv_drill),
                                        net_code=nc,
                                        contained_layers={lay_id})):
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pos)
                v.SetDrill(_nm(pofv_drill))
                v.SetWidth(_nm(pofv_dia))
                v.SetNetCode(nc)
                v.SetLocked(bool(lock))
                board.Add(v)
                _pk_vias.append((pos.x, pos.y, pofv_dia, pofv_drill))
                tracks.append(v)
                n_v += 1; n_p += 1; n_pofv += 1
                promoted_components.add(component_key)
                continue

            if not boxes:
                # A raw ask without established geometry may bootstrap only
                # through a fabrication-qualified via in pad. An adjacent via
                # has no proven future-pour coverage yet, so do not guess one.
                n_skip += 1
                detail = {"ref": fp.GetReference(),
                          "pad": pad.GetPadName(), "net": net,
                          "reason": "no proven covering copper"}
                skipped_detail.append(detail)
                skipped_candidates.append((detail, fp, pad, component_key))
                continue

            placed = False
            guard_summary = {
                "probes": 0,
                "outside_pour": 0,
                "outside_filled_copper": 0,
                "barrel_spacing": 0,
                "no_guarded_path": 0,
                "edge_clearance": 0,
                "via_spot_clearance": 0,
                "placed": 0,
            }
            # Preserve the historical three probes first so already-working
            # boards are bit-for-bit stable. Dense Hub layouts can leave the
            # only legal through-barrel slot between those eight radial rays,
            # or just beyond 1.2 mm. Continue with a bounded inter-cardinal
            # search rather than reporting a false no-slot result. Every new
            # candidate still passes filled-copper, all-layer via, edge,
            # foreign-copper, and pair-overlap guards below.
            _radii = [offset, offset + 0.4, offset - 0.25]
            _radii.extend((1.6, 2.0, 2.5, 3.0))
            _radii = [r for i, r in enumerate(_radii)
                      if r > 0 and r <= float(max_offset)
                      and all(abs(r - q) > 1e-6 for q in _radii[:i])]
            _angles = (0, 90, 180, 270, 45, 135, 225, 315,
                       22.5, 67.5, 112.5, 157.5,
                       202.5, 247.5, 292.5, 337.5)
            for off_mm in _radii:
                if placed:
                    break
                for ang in _angles:
                    guard_summary["probes"] += 1
                    a = _math.radians(ang)
                    at = pcbnew.VECTOR2I(int(pos.x + _math.cos(a) * _nm(off_mm)),
                                         int(pos.y + _math.sin(a) * _nm(off_mm)))
                    ax, ay = at.x / 1e6, at.y / 1e6
                    if not any(b[0] + local_dia / 2 <= ax <= b[2] - local_dia / 2
                               and b[1] + local_dia / 2 <= ay <= b[3] - local_dia / 2
                               for b in boxes):
                        guard_summary["outside_pour"] += 1
                        continue               # via must sit inside the pour
                    if not _filled_at(net, at):
                        guard_summary["outside_filled_copper"] += 1
                        continue               # bbox hit but no real filled copper
                    if any((at.x - qx) ** 2 + (at.y - qy) ** 2 < _nm(via_spacing) ** 2
                           for qx, qy, _vdia, _vdrill in _pk_vias):
                        guard_summary["barrel_spacing"] += 1
                        continue               # barrel spacing (never stack)
                    # CALIBRATED GUARDS (rung probes v2/v3: pair-overlap alone
                    # laid 9 shorts; whole-stub-at-via-diameter placed 0 of 5 --
                    # the honest middle is stub at STUB width plus the via spot
                    # checked point-locally at its own diameter).
                    # EXEMPT SET = {nc} (2026-07-23 false-refusal root cause:
                    # _tap_foreign_clear's FOREIGN = "not in the exempt set",
                    # and set() made the stub's OWN pad foreign -- the stub
                    # starts at the pad center, so every candidate collided
                    # with itself and the stitch fired 0x across ~40 boards.
                    # Same-net copper cannot short itself; {nc} restores the
                    # guard's actual purpose: foreign-NET copper only.)
                    # VIA PROBE SPANS ALL COPPER LAYERS (B2 probe 2026-07-23:
                    # a through-via cleared only on the pad's F.Cu shorted a
                    # foreign In2 track AND a B.Cu track at the same spot --
                    # the freed inner carries FR tracks now. Plane zones are
                    # ignored by design: the filler's antipads handle them.)
                    # Route the pickup with the same two-width state machine as
                    # every other power last-mile.  Only the pad-local prefix
                    # may neck down; the path must flare to class width before
                    # it reaches the plane-entry via.  The previous single
                    # narrow segment was a generic source of locked current
                    # bottlenecks on fine-pitch switches and regulators.
                    legs_nm = _guarded_profiled_lastmile_legs(
                        board, pos, at, _nm(class_stub_w), lay_id,
                        _nm(local_clearance), nc,
                        lambda leg_start, leg_end, half: (
                            _edge_leg_clear(
                                board, leg_start, leg_end, half)
                            and _tap_pair_overlap_clear(
                                board, leg_start, leg_end, half * 2,
                                lay_id, nc, set())),
                        start_escape=(
                            (_nm(local_stub_w), _nm(neck_budget_mm))
                            if local_stub_w < class_stub_w - 0.001 else None),
                        allow_maze=True, maze_margin_mm=2.0)
                    if not legs_nm:
                        guard_summary["no_guarded_path"] += 1
                        continue
                    if not _edge_leg_clear(board, at, at,
                                           _nm(local_dia) // 2):
                        guard_summary["edge_clearance"] += 1
                        continue
                    if not _via_spot_clear(
                            board, at, _nm(local_dia), _nm(0.25), {nc},
                            drill_nm=_nm(local_drill), net_code=nc):
                        guard_summary["via_spot_clearance"] += 1
                        continue
                    v = pcbnew.PCB_VIA(board)
                    v.SetPosition(at)
                    v.SetDrill(_nm(local_drill))
                    v.SetWidth(_nm(local_dia))
                    v.SetNetCode(nc)
                    v.SetLocked(bool(lock))
                    board.Add(v)
                    _pk_vias.append((at.x, at.y, local_dia, local_drill))
                    for leg_start, leg_end, leg_width in legs_nm:
                        tr = pcbnew.PCB_TRACK(board)
                        tr.SetStart(leg_start)
                        tr.SetEnd(leg_end)
                        tr.SetWidth(int(leg_width))
                        tr.SetLayer(lay_id)
                        tr.SetNetCode(nc)
                        tr.SetLocked(bool(lock))
                        board.Add(tr)
                        tracks.append(tr)
                        n_s += 1
                    n_v += 1; n_p += 1
                    promoted_components.add(component_key)
                    placed = True
                    guard_summary["placed"] += 1
                    break
            if not placed:
                n_skip += 1
                detail = {"ref": fp.GetReference(),
                          "pad": pad.GetPadName(), "net": net,
                          "reason": "no guarded via slot in filled copper",
                          "guard_summary": guard_summary}
                skipped_detail.append(detail)
                skipped_candidates.append((detail, fp, pad, component_key))

    # COMPACT PAD-BANK RECOVERY.  Fine-pitch regulators and load switches often
    # expose one electrical node on a tiny control/current-limit land beside a
    # larger power land. Requiring a separate through barrel in every land is
    # both unnecessary and, for sub-0.35 mm lands, physically impossible. Share
    # an already-proven stack portal through a short surface neck, but only
    # within one net. Same-footprint duplicate pins remain preferred, but a
    # nearby bypass/bulk pad may also host a newly qualified POFV. This is the
    # ordinary regulator/load-switch input cell: pin -> decoupler -> one stack
    # portal. Every cross-footprint candidate remains distance bounded and the
    # link plus prospective barrel must both pass the exact guards before
    # either is committed. Requiring a dedicated via beside every 0.4 mm power
    # land makes already-routed inner signal copper permanently enclose an
    # otherwise valid cell.
    cluster_links = []
    unresolved = []
    # Pickups added above change the graph. Rebuild once before asking whether
    # a sibling's complete local component owns a stack portal; otherwise
    # recovery depends on footprint/pad iteration order.
    board.BuildConnectivity()
    connectivity = board.GetConnectivity()
    for detail, fp, pad, component_key in skipped_candidates:
        # A later member of the same pre-existing local copper component may
        # have found the guarded portal.  Do not report the earlier member as
        # refused: connectivity, not pad iteration order, owns this result.
        if component_key in promoted_components:
            n_skip -= 1
            continue
        net = pad.GetNetname()
        nc = pad.GetNetCode()
        start = pad.GetPosition()
        pad_layers = {int(layer) for layer in pad.GetLayerSet().CuStack()}
        anchors = []
        for mate_fp in board.GetFootprints():
          for mate in mate_fp.Pads():  # noqa: E111 - aligned below by patch context
            try:
                same_pad = mate.m_Uuid.AsString() == pad.m_Uuid.AsString()
            except Exception:                           # noqa: BLE001
                same_pad = mate is pad
            if (same_pad or mate.GetNetCode() != nc
                    or mate.GetAttribute() != pcbnew.PAD_ATTRIB_SMD):
                continue
            common_layers = sorted(
                pad_layers.intersection(
                    int(layer) for layer in mate.GetLayerSet().CuStack()))
            if not common_layers:
                continue
            end = mate.GetPosition()
            distance_mm = _math.hypot(end.x - start.x,
                                      end.y - start.y) / MM
            if distance_mm <= 1e-6 or distance_mm > float(cluster_link_max):
                continue
            try:
                connected = list(connectivity.GetConnectedItems(mate))
            except Exception:                           # noqa: BLE001
                connected = []
            portals = []
            for portal in [mate] + connected:
                if portal.GetNetCode() != nc:
                    continue
                kind = portal.GetClass()
                stack_spanning = kind == "PCB_VIA"
                if kind == "PAD":
                    try:
                        stack_spanning = (
                            portal.GetAttribute() != pcbnew.PAD_ATTRIB_SMD)
                    except Exception:                   # noqa: BLE001
                        stack_spanning = False
                if not stack_spanning:
                    continue
                # For an exact post-fill rail, prove that the portal actually
                # lands in filled copper. For a pre-fill requested pour,
                # _filled_at intentionally represents the established future
                # pour contract used by the ordinary pickup path above.
                if not _filled_at(net, portal.GetPosition()):
                    continue
                try:
                    portal_id = portal.m_Uuid.AsString()
                except Exception:                       # noqa: BLE001
                    portal_id = "proxy:%d" % id(portal)
                portals.append((kind, portal_id, portal))
            planned_pofv = None
            if (not portals and pofv_geometry
                    and _filled_at(net, end)):
                pofv_dia, pofv_drill = pofv_geometry
                mate_layer = int(mate.GetLayer())
                blocking, allowed = _fab.via_at_pad_conflicts(
                    board, end, _nm(pofv_dia), _nm(pofv_drill), nc)
                if (blocking is None and allowed
                        and not _pofv_crowded(
                            end, pofv_dia, pofv_drill)
                        and _edge_leg_clear(
                            board, end, end, _nm(pofv_dia) // 2)
                        and _via_spot_clear(
                            board, end, _nm(pofv_dia), _nm(0.25), {nc},
                            drill_nm=_nm(pofv_drill), net_code=nc,
                            contained_layers={mate_layer})):
                    planned_pofv = (pofv_dia, pofv_drill)
                    portals.append((
                        "PLANNED_POFV",
                        "planned:%s-%s" % (
                            mate_fp.GetReference(), mate.GetPadName()),
                        mate))
            for portal_kind, portal_id, portal in sorted(
                    portals, key=lambda row: (row[0], row[1])):
                anchors.append((
                                0 if mate_fp.GetReference() == fp.GetReference()
                                else 1,
                                distance_mm, mate_fp.GetReference(),
                                mate.GetPadName(), mate,
                                portal_kind, portal_id, portal,
                                common_layers,
                                (planned_pofv if portal_kind == "PLANNED_POFV"
                                 else None)))
                break
        recovered = False
        for (_same_fp_rank, distance_mm, mate_ref, _mate_name, mate,
             portal_kind, portal_id, portal, common_layers,
             planned_pofv) in sorted(
                anchors, key=lambda candidate: candidate[:4]):
            end = mate.GetPosition()
            try:
                board_min_w = board.GetDesignSettings().m_TrackMinWidth / MM
            except Exception:                           # noqa: BLE001
                board_min_w = 0.2
            pad_minor = min(pad.GetSize().x, pad.GetSize().y) / MM
            mate_minor = min(mate.GetSize().x, mate.GetSize().y) / MM
            try:
                klass = board.GetNetInfo().GetNetItem(net).GetNetClassSlow()
                clearance = max(0.25, klass.GetClearance() / MM)
                class_width = max(float(board_min_w or 0.2),
                                  klass.GetTrackWidth() / MM)
            except Exception:                           # noqa: BLE001
                clearance = 0.25
                class_width = 0.3
            preferred = int(pad.GetLayer())
            layer_id = (preferred if preferred in common_layers
                        else common_layers[0])
            # Prefer the full land-limited width; step down only when the
            # wider local neck is physically blocked. This is a bounded
            # pin-escape exception, not permission to carry the whole rail at
            # the board minimum.
            max_link_w = max(float(board_min_w or 0.2),
                             min(class_width, pad_minor, mate_minor))
            width_candidates = []
            for width in (max_link_w, min(max_link_w, 0.3),
                          float(board_min_w or 0.2)):
                if width > 0 and not any(
                        abs(width - prior) <= 1e-6
                        for prior in width_candidates):
                    width_candidates.append(width)
            link_w = next((width for width in width_candidates
                           if (_tap_foreign_clear(
                                   board, start, end, _nm(width), layer_id,
                                   _nm(clearance), {nc})
                               and _edge_leg_clear(
                                   board, start, end, _nm(width) // 2)
                               and _tap_pair_overlap_clear(
                                   board, start, end, _nm(width), layer_id,
                                   nc, set()))), None)
            if link_w is None:
                continue
            if planned_pofv is not None:
                pofv_dia, pofv_drill = planned_pofv
                via = pcbnew.PCB_VIA(board)
                via.SetPosition(end)
                via.SetDrill(_nm(pofv_drill))
                via.SetWidth(_nm(pofv_dia))
                via.SetNetCode(nc)
                via.SetLocked(bool(lock))
                board.Add(via)
                portal_id = via.m_Uuid.AsString()
                portal_kind = "PCB_VIA"
                _pk_vias.append((end.x, end.y, pofv_dia, pofv_drill))
                n_v += 1
                n_pofv += 1
            link = pcbnew.PCB_TRACK(board)
            link.SetStart(start)
            link.SetEnd(end)
            link.SetWidth(_nm(link_w))
            link.SetLayer(layer_id)
            link.SetNetCode(nc)
            link.SetLocked(bool(lock))
            board.Add(link)
            tracks.append(link)
            n_s += 1
            n_p += 1
            n_skip -= 1
            cluster_links.append({
                "ref": fp.GetReference(),
                "from_pad": pad.GetPadName(),
                "to_ref": mate_ref,
                "to_pad": mate.GetPadName(),
                "net": net,
                "layer": board.GetLayerName(layer_id),
                "width_mm": round(link_w, 6),
                "length_mm": round(distance_mm, 6),
                "anchor_portal": portal_id,
                "anchor_type": portal_kind,
                # Compatibility for existing dashboard/report consumers.
                "anchor_via": (portal_id if portal_kind == "PCB_VIA"
                               else None),
                "uuid": link.m_Uuid.AsString(),
            })
            promoted_components.add(component_key)
            recovered = True
            break
        if not recovered:
            unresolved.append(detail)
    skipped_detail = unresolved
    return {"pads": n_p, "vias": n_v, "stubs": n_s,
            "pofv": n_pofv, "skipped": n_skip,
            "cluster_recovered": len(cluster_links),
            "cluster_links": cluster_links[:32],
            "skipped_detail": skipped_detail[:32]}


def synthesize_power_escape_fanouts(
        board, power_pours, terminals, *, stub_w=0.3, drill=0.3, dia=0.6,
        lock=False, max_offset=3.5):
    """Escape an enclosed, POFV-anchored rail terminal to open stack space.

    A via can be fabrication-legal inside a fine-pitch power pad yet remain
    topologically trapped on every inner layer by the package's surrounding
    pins and barrels.  The routed-power solver reports the stranded terminal;
    this bounded repair lays one narrow surface neck to a guarded through-via
    farther from the package, then lets the ordinary width-aware lane spread
    from that new anchor.

    Only explicitly named ``terminals`` are considered, and each must already
    contain a fabrication-qualified same-net POFV.  Candidate barrels must be
    inside the declared rail territory and pass the ordinary all-layer via,
    foreign-copper, edge, pair-overlap, and barrel-spacing guards.  Therefore
    this cannot turn an arbitrary unconnected pad into an optimistic route.
    """
    import math as _math

    wanted = {(str(row.get("ref") or ""), str(row.get("pad") or ""),
               str(row.get("net") or ""))
              for row in (terminals or ()) if row.get("ref") is not None}
    if not wanted:
        return {"placed": 0, "refused": 0, "detail": []}

    territories = {}
    for row in power_pours or ():
        net = row.get("net")
        polygon = row.get("polygon") or ()
        if not net or not polygon:
            continue
        xs = [point[0] for point in polygon]
        ys = [point[1] for point in polygon]
        territories.setdefault(net, []).append(
            (min(xs), min(ys), max(xs), max(ys)))

    vias = [item for item in board.GetTracks()
            if item.GetClass() == "PCB_VIA"]
    via_ledger = [
        (item.GetPosition().x, item.GetPosition().y,
         item.GetWidth(item.TopLayer()) / MM,
         item.GetDrillValue() / MM)
        for item in vias
    ]
    placed = []
    refused = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            key = (fp.GetReference(), pad.GetPadName(), pad.GetNetname())
            if key not in wanted:
                continue
            net = pad.GetNetname()
            nc = pad.GetNetCode()
            if (pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                    or nc <= 0 or not territories.get(net)):
                refused.append({"ref": key[0], "pad": key[1], "net": net,
                                "reason": "terminal or rail territory unavailable"})
                continue

            # Prove that the reported land really owns a qualified POFV.  A
            # remote via connected only by unknown copper is not enough.
            anchor_via = None
            for item in vias:
                if item.GetNetCode() != nc:
                    continue
                blocking, allowed = _fab.via_at_pad_conflicts(
                    board, item.GetPosition(), item.GetWidth(item.TopLayer()),
                    item.GetDrillValue(), nc)
                if blocking is None and any(
                        record.get("ref") == fp.GetReference()
                        and record.get("pad") == pad.GetPadName()
                        for record in allowed):
                    anchor_via = item
                    break
            if anchor_via is None:
                refused.append({"ref": key[0], "pad": key[1], "net": net,
                                "reason": "no qualified POFV anchor"})
                continue

            try:
                klass = board.GetNetInfo().GetNetItem(net).GetNetClassSlow()
                local_dia = max(float(dia), klass.GetViaDiameter() / MM)
                local_drill = max(float(drill), klass.GetViaDrill() / MM)
                class_stub_w = max(float(stub_w),
                                   klass.GetTrackWidth() / MM)
                clearance = max(0.25, klass.GetClearance() / MM)
            except Exception:                           # noqa: BLE001
                local_dia, local_drill = float(dia), float(drill)
                class_stub_w, clearance = float(stub_w), 0.25
            try:
                board_min_w = board.GetDesignSettings().m_TrackMinWidth / MM
            except Exception:                           # noqa: BLE001
                board_min_w = 0.2
            pad_minor = min(pad.GetSize().x, pad.GetSize().y) / MM
            local_stub_w = (
                class_stub_w if pad_minor >= class_stub_w - 0.001 else
                min(class_stub_w, max(
                    float(board_min_w or 0.2), pad_minor / 2.0)))
            # Use a prompt 0.6 mm flare for newly generated power injection.
            # The final normalizer's 1.5 mm limit is a compatibility ceiling
            # for imported copper, not a target for fresh synthesis.
            neck_budget_mm = 0.6
            via_spacing = max(0.85, local_dia + 0.25)

            start = pad.GetPosition()
            layer_id = int(pad.GetLayer())
            centre = fp.GetPosition()
            away = _math.degrees(_math.atan2(
                start.y - centre.y, start.x - centre.x)) % 360.0
            # Barrel seats are a two-dimensional resource.  The old 15-degree
            # / sparse-radius star could report no slot even though a legal
            # grid seat existed between two rays.  Use a bounded deterministic
            # polar lattice fine enough to cover the 0.5 mm routing grid.
            angles = list(range(0, 360, 5))
            angles.sort(key=lambda angle: (
                min((angle - away) % 360.0, (away - angle) % 360.0), angle))
            radii = tuple(round(value / 10.0, 3) for value in range(
                8, int(round(float(max_offset) * 10.0)) + 1, 2))
            made = False
            for off_mm in radii:
                if off_mm > float(max_offset):
                    continue
                for angle in angles:
                    rad = _math.radians(angle)
                    at = pcbnew.VECTOR2I(
                        int(start.x + _math.cos(rad) * _nm(off_mm)),
                        int(start.y + _math.sin(rad) * _nm(off_mm)))
                    ax, ay = at.x / MM, at.y / MM
                    if not any(
                            x0 + local_dia / 2.0 <= ax <= x1 - local_dia / 2.0
                            and y0 + local_dia / 2.0 <= ay <= y1 - local_dia / 2.0
                            for x0, y0, x1, y1 in territories[net]):
                        continue
                    if any((at.x - qx) ** 2 + (at.y - qy) ** 2
                           < _nm(max(
                               via_spacing,
                               (local_dia + qdia) / 2.0 + 0.15,
                               (local_drill + qdrill) / 2.0 + 0.25)) ** 2
                           for qx, qy, qdia, qdrill in via_ledger):
                        continue
                    # Search the same width-state path used by guarded
                    # last-mile synthesis.  A straight radial candidate can
                    # have a legal narrow launch but an illegal full-width
                    # flare; a short dogleg may still reach the exact same
                    # qualified barrel without extending the neck-down.
                    legs_nm = _guarded_profiled_lastmile_legs(
                        board, start, at, _nm(class_stub_w), layer_id,
                        _nm(clearance), nc,
                        lambda a, b, half: (
                            _edge_leg_clear(board, a, b, half)
                            and _tap_pair_overlap_clear(
                                board, a, b, half * 2, layer_id, nc, set())),
                        start_escape=(_nm(local_stub_w),
                                      _nm(neck_budget_mm)),
                        allow_maze=True, maze_margin_mm=2.0)
                    if not (legs_nm
                            and _edge_leg_clear(
                                board, at, at, _nm(local_dia) // 2)
                            and _via_spot_clear(
                                board, at, _nm(local_dia), _nm(clearance),
                                {nc}, drill_nm=_nm(local_drill), net_code=nc)):
                        continue
                    via = pcbnew.PCB_VIA(board)
                    via.SetPosition(at)
                    via.SetDrill(_nm(local_drill))
                    via.SetWidth(_nm(local_dia))
                    via.SetNetCode(nc)
                    via.SetLocked(bool(lock))
                    board.Add(via)
                    tracks = []
                    for leg_start, leg_end, leg_width_nm in legs_nm:
                        track = pcbnew.PCB_TRACK(board)
                        track.SetStart(leg_start)
                        track.SetEnd(leg_end)
                        track.SetWidth(int(leg_width_nm))
                        track.SetLayer(layer_id)
                        track.SetNetCode(nc)
                        track.SetLocked(bool(lock))
                        board.Add(track)
                        tracks.append(track)
                    vias.append(via)
                    via_ledger.append((at.x, at.y, local_dia, local_drill))
                    placed.append({
                        "ref": key[0], "pad": key[1], "net": net,
                        "at_mm": [round(ax, 6), round(ay, 6)],
                        "offset_mm": round(off_mm, 6), "angle_deg": angle,
                        "stub_width_mm": round(local_stub_w, 6),
                        "trunk_width_mm": round(class_stub_w, 6),
                        "neck_budget_mm": round(neck_budget_mm, 6),
                        "escape_legs": len(legs_nm),
                        "via_diameter_mm": round(local_dia, 6),
                        "via_drill_mm": round(local_drill, 6),
                        "anchor_via": anchor_via.m_Uuid.AsString(),
                        "via_uuid": via.m_Uuid.AsString(),
                        "track_uuid": tracks[0].m_Uuid.AsString(),
                        "track_uuids": [track.m_Uuid.AsString()
                                        for track in tracks],
                    })
                    made = True
                    break
                if made:
                    break
            if not made:
                refused.append({"ref": key[0], "pad": key[1], "net": net,
                                "reason": "no guarded escape via slot"})
    return {"placed": len(placed), "refused": len(refused),
            "detail": placed, "refused_detail": refused}


def prune_redundant_dangling_pickups(
        board, pickup_item_ids, *, discover_nets=(), discover_pofv_nets=(),
        tol_mm=0.02, max_stub_mm=1.5):
    """Remove a generated pickup only when later local copper supersedes it.

    Pickup synthesis intentionally precedes the local bypass/link passes: doing
    the reverse can make a whole surface cluster look "already connected" even
    though it still has no path to its inner-layer rail.  A later local link can,
    however, join two independently synthesized pickups.  If one barrel did not
    survive the final shaped fill, KiCad then reports a dangling via even though
    the cluster has another valid stack transition.

    Limit pruning to exact items created by the final pickup pass plus the
    short SMD-pad-to-barrel topology on explicitly named discovery nets. The
    latter recovers bootstrap pickups created in the earlier repour process,
    whose UUIDs cannot cross the process boundary. A just-generated POFV whose
    full land survives only on its containing surface pad is removed outright:
    it never reached the intended plane and otherwise becomes a pre-route
    dangling barrel. An adjacent pickup is
    removable only when (1) its barrel contacts copper on at most one layer
    after the final fill, (2) it owns exactly one short surface-pad stub, and
    (3) KiCad's real connected component contains another proven multilayer
    anchor (a non-dangling via or a plated through pad). Via-in-pad pickups,
    router vias, bridge fields, hand-authored copper, and the cluster's only
    transition therefore fail closed and remain untouched.
    """
    import math as _math

    wanted = {str(value) for value in (pickup_item_ids or ())}
    discover = {str(net) for net in (discover_nets or ())}
    discover_pofv = {str(net) for net in (discover_pofv_nets or ())}
    if not wanted and not discover and not discover_pofv:
        return {"vias": 0, "stubs": 0, "unlanded_pofv": 0,
                "detail": []}

    tracks = list(board.GetTracks())
    tracks_by_id = {item.m_Uuid.AsString(): item for item in tracks}
    pads = [pad for fp in board.GetFootprints() for pad in fp.Pads()]

    tol = int(float(tol_mm) * MM)
    max_stub = int(float(max_stub_mm) * MM)
    zones = []
    for zone in board.Zones():
        if zone.GetIsRuleArea() or not zone.IsOnCopperLayer():
            continue
        for layer in zone.GetLayerSet().CuStack():
            try:
                poly = zone.GetFilledPolysList(layer)
            except Exception:                           # noqa: BLE001
                continue
            if poly and poly.OutlineCount() > 0:
                zones.append((zone.GetNetname(), layer, poly))

    def _point_on_track(point, track, extra=0):
        start, end = track.GetStart(), track.GetEnd()
        dx, dy = end.x - start.x, end.y - start.y
        length_sq = dx * dx + dy * dy
        if length_sq:
            along = max(0.0, min(
                1.0, ((point.x - start.x) * dx
                      + (point.y - start.y) * dy) / length_sq))
            near_x, near_y = start.x + along * dx, start.y + along * dy
        else:
            near_x, near_y = start.x, start.y
        return _math.hypot(point.x - near_x, point.y - near_y) <= (
            track.GetWidth() // 2 + int(extra) + tol)

    def _pickup_stubs(via):
        """Short surface pad-to-barrel legs with pickup topology."""
        point = via.GetPosition()
        out = []
        for track in tracks:
            if (track.GetClass() == "PCB_VIA"
                    or track.GetNetCode() != via.GetNetCode()
                    or track.GetLength() > max_stub
                    or not via.IsOnLayer(track.GetLayer())):
                continue
            start, end = track.GetStart(), track.GetEnd()
            start_hit = _math.hypot(start.x - point.x,
                                    start.y - point.y) <= tol
            end_hit = _math.hypot(end.x - point.x,
                                  end.y - point.y) <= tol
            if start_hit == end_hit:
                continue
            source = end if start_hit else start
            if any(pad.GetNetCode() == via.GetNetCode()
                   and pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD
                   and pad.IsOnLayer(track.GetLayer())
                   and pad.HitTest(source, track.GetWidth() // 2 + tol)
                   for pad in pads):
                out.append(track)
        return out

    pickup_vias = []
    stub_cache = {}
    for item in tracks:
        if item.GetClass() != "PCB_VIA":
            continue
        item_id = item.m_Uuid.AsString()
        stubs = _pickup_stubs(item)
        discovered_pofv = False
        if item.GetNetname() in discover_pofv:
            blocking, allowed = _fab.via_at_pad_conflicts(
                board, item.GetPosition(), item.GetWidth(item.TopLayer()),
                item.GetDrillValue(), item.GetNetCode())
            discovered_pofv = blocking is None and bool(allowed)
        if (item_id in wanted
                or (item.GetNetname() in discover and len(stubs) == 1)
                or discovered_pofv):
            pickup_vias.append(item)
            stub_cache[item_id] = stubs
    if not pickup_vias:
        return {"vias": 0, "stubs": 0, "unlanded_pofv": 0,
                "detail": []}

    def _contact_layers(via, *, ignored_ids=()):
        ignored = set(ignored_ids)
        point = via.GetPosition()
        net = via.GetNetname()
        radius = via.GetWidth(via.TopLayer()) // 2
        found = set()
        for other in tracks:
            other_id = other.m_Uuid.AsString()
            if (other is via or other_id in ignored
                    or other.GetNetname() != net):
                continue
            if (other.GetClass() != "PCB_VIA"
                    and via.IsOnLayer(other.GetLayer())
                    and _point_on_track(point, other, radius)):
                found.add(other.GetLayer())
        for pad in pads:
            if pad.GetNetname() != net:
                continue
            try:
                hit = pad.HitTest(point, radius + tol)
            except TypeError:
                hit = pad.HitTest(point)
            if hit:
                found.update(layer for layer in pad.GetLayerSet().CuStack()
                             if via.IsOnLayer(layer))
        for zone_net, layer, poly in zones:
            if (zone_net == net and via.IsOnLayer(layer)
                    and poly.Collide(point, radius + tol)):
                found.add(layer)
        return found

    board.BuildConnectivity()
    connectivity = board.GetConnectivity()
    doomed = []
    detail = []
    unlanded_pofv = 0
    for via in pickup_vias:
        via_id = via.m_Uuid.AsString()
        stubs = stub_cache.get(via_id, ())
        contact_layers = _contact_layers(via)
        if via_id in wanted or via.GetNetname() in discover_pofv:
            blocking, allowed = _fab.via_at_pad_conflicts(
                board, via.GetPosition(), via.GetWidth(via.TopLayer()),
                via.GetDrillValue(), via.GetNetCode())
            if blocking is None and allowed and len(contact_layers) <= 1:
                # Remove only the unlanded barrel. A later surface link may
                # terminate at the same pad centre and resemble a pickup stub;
                # that copper remains useful and is not owned by this POFV.
                doomed.append((via, None))
                pos = via.GetPosition()
                detail.append({
                    "net": via.GetNetname(),
                    "at_mm": [round(pos.x / MM, 6),
                              round(pos.y / MM, 6)],
                    "replacement": "none-unlanded-pofv",
                })
                unlanded_pofv += 1
                continue
        # Multiple stubs are no longer a simple removable leaf, so they remain
        # for explicit diagnosis.
        if len(stubs) != 1:
            continue
        stub_ids = {stub.m_Uuid.AsString() for stub in stubs}
        if len(contact_layers) > 1:
            continue
        try:
            component = list(connectivity.GetConnectedItems(via))
        except Exception:                               # noqa: BLE001
            component = []
        replacement = None
        for item in component:
            if item is via or item.GetNetCode() != via.GetNetCode():
                continue
            if item.GetClass() == "PCB_VIA":
                item_id = item.m_Uuid.AsString()
                original = tracks_by_id.get(item_id)
                if (item_id != via_id and original is not None
                        and len(_contact_layers(
                            original,
                            ignored_ids=stub_ids | {via_id})) > 1):
                    replacement = "via"
                    break
            if item.GetClass() == "PAD":
                layers = tuple(item.GetLayerSet().CuStack())
                if (item.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                        and len(layers) > 1):
                    replacement = "through-pad"
                    break
        if replacement is None:
            continue
        doomed.append((via, stubs[0]))
        pos = via.GetPosition()
        detail.append({"net": via.GetNetname(),
                       "at_mm": [round(pos.x / MM, 6), round(pos.y / MM, 6)],
                       "replacement": replacement})

    removed_stubs = 0
    for via, stub in doomed:
        if stub is not None:
            board.Remove(stub)
            removed_stubs += 1
        board.Remove(via)
    return {"vias": len(doomed), "stubs": removed_stubs,
            "unlanded_pofv": unlanded_pofv, "detail": detail}


def prune_post_cleanup_power_pickups(board_path, power_nets):
    """Reconcile generated rail pickups after file-based zone reaping.

    ``cleanup_floating_zones`` and ``reap_nowhere_zones`` intentionally run in
    a fresh pcbnew process after the routed board has been saved.  A qualified
    POFV can therefore be valid when the import-side fill runs, then become a
    one-layer dangling barrel when the reaper removes the only rail island
    beneath it.  The in-memory pickup pruner cannot predict that later state.

    Reload the actual post-cleanup artifact and discover pickups only on the
    explicitly synthesized power/ground nets.  The underlying pruner remains
    fail-closed: a POFV is removed only when its full land is contained by a
    same-net SMD pad and it contacts copper on no more than one layer; an
    offset pickup additionally requires another proven multilayer anchor in
    the same connected component.  Refill after removal so zone clearances and
    connectivity describe the board that is subsequently scored and shipped.
    """
    nets = tuple(sorted({str(net) for net in (power_nets or ()) if net}))
    if not nets:
        return {"vias": 0, "stubs": 0, "unlanded_pofv": 0,
                "detail": []}
    board = pcbnew.LoadBoard(board_path)
    report = prune_redundant_dangling_pickups(
        board, (), discover_nets=nets, discover_pofv_nets=nets)
    if report["vias"] or report["stubs"]:
        for zone in board.Zones():
            zone.UnFill()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        pcbnew.SaveBoard(board_path, board)
    return report


def prune_dead_zone_via_pairs(board_path, power_nets, *, tol_mm=0.02):
    """Remove generated rail barrels sustained only by one copper-zone layer.

    A locked bridge via and an isolated generated zone can falsely keep one
    another alive: zone cleanup treats the via as a terminal, while the via
    sweep treats the zone as a connection.  Neither object actually reaches a
    pad, a track, or a second copper layer, so KiCad reports both
    ``via_dangling`` and ``isolated_copper``.  Break that cycle using physical
    liveness, scoped to explicitly synthesized rail nets.  Lock state is not a
    liveness proof here because bridge-field vias are intentionally locked.

    A via survives when it contacts any same-net pad/track or filled same-net
    zone copper on two or more layers.  Hand-authored signal nets and valid
    two-layer bridge barrels are therefore outside the removal class.
    """
    nets = {str(net) for net in (power_nets or ()) if str(net)}
    if not nets:
        return {"vias": 0, "detail": []}
    board = pcbnew.LoadBoard(board_path)
    try:
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    except Exception:                                  # noqa: BLE001
        return {"vias": 0, "detail": [],
                "error": "zone fill unavailable; liveness not measured"}
    tracks = list(board.GetTracks())
    pads = [pad for fp in board.GetFootprints() for pad in fp.Pads()]
    tol = int(float(tol_mm) * MM)

    def _point_on_track(point, track, extra=0):
        dx = track.GetEnd().x - track.GetStart().x
        dy = track.GetEnd().y - track.GetStart().y
        length_sq = dx * dx + dy * dy
        if length_sq:
            along = max(0.0, min(
                1.0, ((point.x - track.GetStart().x) * dx
                      + (point.y - track.GetStart().y) * dy) / length_sq))
            nx = track.GetStart().x + along * dx
            ny = track.GetStart().y + along * dy
        else:
            nx, ny = track.GetStart().x, track.GetStart().y
        return math.hypot(point.x - nx, point.y - ny) <= (
            track.GetWidth() // 2 + int(extra) + tol)

    doomed = []
    detail = []
    for via in tracks:
        if via.GetClass() != "PCB_VIA" or via.GetNetname() not in nets:
            continue
        point = via.GetPosition()
        radius = via.GetWidth(via.TopLayer()) // 2
        pad_or_track = any(
            pad.GetNetCode() == via.GetNetCode()
            and pad.HitTest(point, radius + tol)
            for pad in pads)
        if not pad_or_track:
            pad_or_track = any(
                other.GetClass() != "PCB_VIA"
                and other.GetNetCode() == via.GetNetCode()
                and via.IsOnLayer(other.GetLayer())
                and _point_on_track(point, other, radius)
                for other in tracks if other is not via)
        if pad_or_track:
            continue
        zone_layers = set()
        for zone in board.Zones():
            if (zone.GetIsRuleArea() or not zone.IsOnCopperLayer()
                    or zone.GetNetCode() != via.GetNetCode()):
                continue
            for layer in zone.GetLayerSet().CuStack():
                if not via.IsOnLayer(layer):
                    continue
                try:
                    poly = zone.GetFilledPolysList(layer)
                    if poly and poly.Collide(point, radius + tol):
                        zone_layers.add(layer)
                except Exception:                       # noqa: BLE001
                    continue
        if len(zone_layers) > 1:
            continue
        doomed.append(via)
        detail.append({
            "uuid": via.m_Uuid.AsString(),
            "net": via.GetNetname(),
            "at_mm": [round(point.x / MM, 6), round(point.y / MM, 6)],
            "zone_layers": [board.GetLayerName(layer)
                            for layer in sorted(zone_layers)],
        })
    for via in doomed:
        board.Remove(via)
    if doomed:
        pcbnew.SaveBoard(board_path, board)
    return {"vias": len(doomed), "detail": detail}


def settle_generated_power_artifact(board_path, power_nets, *, max_rounds=4):
    """Alternate via and zone liveness cleanup to a bounded fixed point."""
    import cec_power_artifact_worker

    nets = sorted({str(net) for net in (power_nets or ()) if str(net)})

    def _phase(name):
        command = [sys.executable, cec_power_artifact_worker.__file__,
                   name, board_path, "--nets-json", json.dumps(nets)]
        process = subprocess.run(
            command, capture_output=True, text=True, timeout=120)
        if process.stderr:
            print(process.stderr.rstrip(), file=sys.stderr)
        if process.returncode:
            raise RuntimeError(
                "power artifact %s phase failed (%d): %s" % (
                    name, process.returncode,
                    (process.stderr or process.stdout or "no diagnostic")[-2000:]))
        lines = [line for line in process.stdout.splitlines() if line.strip()]
        if not lines:
            raise RuntimeError("power artifact %s phase returned no report" % name)
        return json.loads(lines[-1])

    rounds = []
    for index in range(max(1, int(max_rounds))):
        vias = _phase("via")
        floating = int(_phase("floating").get("removed", 0))
        nowhere = int(_phase("nowhere").get("removed", 0))
        row = {"round": index + 1, "dead_zone_vias": vias,
               "floating_zones": int(floating or 0),
               "nowhere_items": int(nowhere or 0)}
        rounds.append(row)
        if not (vias.get("vias") or floating or nowhere):
            break
    return {"schema": 1, "rounds": rounds,
            "converged": not bool(
                rounds[-1]["dead_zone_vias"].get("vias")
                or rounds[-1]["floating_zones"]
                or rounds[-1]["nowhere_items"])}


def _canonical_45_xy_paths(start, end):
    """Return deterministic shortest paths whose legs are only 0/45/90 degrees.

    The first two alternatives use one diagonal plus one orthogonal leg and
    therefore have the same minimum octilinear length.  Manhattan L paths are
    retained as congestion fallbacks.  Keeping this helper geometry-only makes
    the last-mile and bridge paths share one policy and gives it direct tests.
    """
    sx, sy = (int(start[0]), int(start[1]))
    tx, ty = (int(end[0]), int(end[1]))
    dx, dy = tx - sx, ty - sy
    if dx == 0 and dy == 0:
        return []

    paths = []

    def _add(points):
        clean = []
        for point in points:
            point = (int(point[0]), int(point[1]))
            if not clean or point != clean[-1]:
                clean.append(point)
        candidate = tuple(clean)
        if len(candidate) >= 2 and candidate not in paths:
            paths.append(candidate)

    adx, ady = abs(dx), abs(dy)
    if dx == 0 or dy == 0 or adx == ady:
        _add(((sx, sy), (tx, ty)))
    else:
        sign_x = 1 if dx > 0 else -1
        sign_y = 1 if dy > 0 else -1
        if adx > ady:
            # horizontal then diagonal; diagonal then horizontal
            _add(((sx, sy), (tx - sign_x * ady, sy), (tx, ty)))
            _add(((sx, sy), (sx + sign_x * ady, ty), (tx, ty)))
        else:
            # vertical then diagonal; diagonal then vertical
            _add(((sx, sy), (sx, ty - sign_y * adx), (tx, ty)))
            _add(((sx, sy), (tx, sy + sign_y * adx), (tx, ty)))

    _add(((sx, sy), (tx, sy), (tx, ty)))
    _add(((sx, sy), (sx, ty), (tx, ty)))
    return paths


def _offset_manhattan_xy_paths(start, end, offsets_mm=(0.5, 0.8, 1.2, 1.8)):
    """Deterministic same-layer doglegs around a blocked endpoint rectangle.

    Freerouting residuals often sit on opposite sides of a package body, LED
    shine-through cutout, or dense pin row.  The shortest canonical paths all
    cross that obstacle.  These candidates walk just outside the endpoint
    bounding rectangle, retain only 0/90-degree legs, and remain subject to the
    ordinary foreign-copper and board-edge guards.  They are attempted only
    after every shortest path refuses, so they do not add unnecessary jogs.
    """
    sx, sy = start
    tx, ty = end
    paths = []

    def _add(points):
        cleaned = []
        for point in points:
            if not cleaned or cleaned[-1] != point:
                cleaned.append(point)
        candidate = tuple(cleaned)
        if len(candidate) >= 2 and candidate not in paths:
            paths.append(candidate)

    for offset_mm in offsets_mm:
        delta = _nm(offset_mm)
        for y in (min(sy, ty) - delta, max(sy, ty) + delta):
            _add(((sx, sy), (sx, y), (tx, y), (tx, ty)))
        for x in (min(sx, tx) - delta, max(sx, tx) + delta):
            _add(((sx, sy), (x, sy), (x, ty), (tx, ty)))
    return paths


def _guarded_lastmile_legs(board, S, T, w, lay, clearance_nm, nc, leg_ok,
                           *, allow_maze=True, maze_margin_mm=2.0,
                           foreign_cache=None):
    """Choose the first collision- and edge-safe canonical path S -> T."""
    profiled = _guarded_profiled_lastmile_legs(
        board, S, T, w, lay, clearance_nm, nc, leg_ok,
        allow_maze=allow_maze, maze_margin_mm=maze_margin_mm,
        foreign_cache=foreign_cache)
    if profiled is not None:
        return [(a, b) for a, b, _width in profiled]
    return None


def _profiled_lastmile_path(points, w, start_escape=None, end_escape=None):
    """Split a canonical path at bounded endpoint neck-down transitions.

    ``start_escape`` and ``end_escape`` are ``(width_nm, budget_nm)`` pairs.
    Width changes occur at deterministic graph-distance boundaries, never in
    the middle of an unsplit track.  When two fine-pitch escapes face each
    other on a >=0.5 mm class, their budgets are reduced proportionally to
    reserve a full-width throat.  This prevents overlapping pad allowances
    from silently consuming an entire high-current local link.
    """
    import math as _math

    lengths = [_math.hypot(b.x - a.x, b.y - a.y)
               for a, b in zip(points, points[1:])]
    total = sum(lengths)
    if total <= 0:
        return []
    start_escape, end_escape = _reserve_power_throat(
        total, w, start_escape, end_escape)
    start_cut = (min(total, float(start_escape[1]))
                 if start_escape else 0.0)
    end_cut = (max(0.0, total - float(end_escape[1]))
               if end_escape else total)
    out = []
    walked = 0.0
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        if length <= 0:
            continue
        cuts = [0.0, length]
        for boundary in (start_cut, end_cut):
            local = boundary - walked
            if 1e-6 < local < length - 1e-6:
                cuts.append(local)
        cuts = sorted(set(cuts))

        def _at(offset):
            fraction = max(0.0, min(1.0, offset / length))
            return pcbnew.VECTOR2I(
                int(round(a.x + (b.x - a.x) * fraction)),
                int(round(a.y + (b.y - a.y) * fraction)))

        for lo, hi in zip(cuts, cuts[1:]):
            midpoint = walked + (lo + hi) / 2.0
            width = int(w)
            if start_escape and midpoint <= start_cut + 1e-6:
                width = min(width, int(start_escape[0]))
            if end_escape and midpoint >= end_cut - 1e-6:
                width = min(width, int(end_escape[0]))
            pa, pb = _at(lo), _at(hi)
            if pa != pb:
                out.append((pa, pb, width))
        walked += length
    return out


def _reserve_power_throat(total_nm, class_width_nm,
                          start_escape=None, end_escape=None):
    """Bound opposing power escapes so some class-width copper remains.

    A single pad escape may legitimately run farther along a lightly loaded
    branch (for example a supervisor-divider feed).  The hazardous case is a
    short link with fine-pitch lands at *both* ends: overlapping allowances can
    make the complete current path narrow.  Reserve 25% of short links, capped
    at 0.25 mm, as a class-width throat.  Guarded synthesis then either proves
    that flare against real neighboring copper or refuses closed.
    """
    if (float(class_width_nm) < _nm(0.5)
            or start_escape is None or end_escape is None):
        return start_escape, end_escape
    start_budget = max(0.0, float(start_escape[1]))
    end_budget = max(0.0, float(end_escape[1]))
    combined = start_budget + end_budget
    if combined <= 0:
        return start_escape, end_escape
    throat = min(float(_nm(0.25)), max(0.0, float(total_nm) * 0.25))
    available = max(0.0, float(total_nm) - throat)
    if combined <= available + 1e-6:
        return start_escape, end_escape
    scale = available / combined
    return ((int(start_escape[0]), int(round(start_budget * scale))),
            (int(end_escape[0]), int(round(end_budget * scale))))


def _maze_lastmile_legs(board, S, T, w, lay, clearance_nm, nc, leg_ok,
                         *, start_escape=None, end_escape=None,
                         grid_mm=0.5, margin_mm=2.0, foreign_cache=None):
    """Bounded deterministic Manhattan maze for a stubborn local gap.

    The lattice includes both exact endpoint axes and the escape-budget axes,
    so the result never needs an arbitrary-angle first/last segment.  A start
    neck-down is allowed only while accumulated path length remains inside its
    budget.  Once an end neck-down begins, every subsequent hop must reduce
    Manhattan distance to the endpoint; its remaining graph length is therefore
    proven inside that budget.  Every hop is checked against real board edges
    and foreign copper before it enters the queue.
    """
    import heapq as _heapq
    import itertools as _itertools

    direct_distance = ((T.x - S.x) ** 2 + (T.y - S.y) ** 2) ** 0.5
    # Do not scale escape budgets against straight-line distance here.  A maze
    # exists specifically because the straight path is obstructed; legal
    # fine-pitch fanouts may need to run away from both pads before a wide
    # trunk can cross the open channel.  The former pre-scaling discarded that
    # fanout before search and made a finer grid useless.  Instead retain the
    # physical endpoint budgets and carry proof of an explicit full-width
    # throat in the search state.
    required_throat = 0
    if (float(w) >= _nm(0.5)
            and start_escape is not None and end_escape is not None):
        required_throat = int(min(
            float(_nm(0.25)), max(0.0, direct_distance * 0.25)))
    step = max(1, _nm(grid_mm))
    margin = _nm(margin_mm)
    x_lo = (min(S.x, T.x) - margin) // step * step
    x_hi = ((max(S.x, T.x) + margin + step - 1) // step) * step
    y_lo = (min(S.y, T.y) - margin) // step * step
    y_hi = ((max(S.y, T.y) + margin + step - 1) // step) * step
    xs = set(range(int(x_lo), int(x_hi + step), int(step)))
    ys = set(range(int(y_lo), int(y_hi + step), int(step)))
    xs.update((S.x, T.x)); ys.update((S.y, T.y))
    for point, escape in ((S, start_escape), (T, end_escape)):
        if escape:
            budget = int(escape[1])
            xs.update((point.x - budget, point.x + budget))
            ys.update((point.y - budget, point.y + budget))
    xs, ys = sorted(xs), sorted(ys)
    xi = {x: i for i, x in enumerate(xs)}
    yi = {y: i for i, y in enumerate(ys)}
    start_node = (xi[S.x], yi[S.y])
    target_node = (xi[T.x], yi[T.y])
    direct_manhattan = abs(T.x - S.x) + abs(T.y - S.y)
    path_limit = direct_manhattan + 2 * margin

    def _point(node):
        return pcbnew.VECTOR2I(xs[node[0]], ys[node[1]])

    def _to_target(node):
        p = _point(node)
        return abs(T.x - p.x) + abs(T.y - p.y)

    # state = (x-index, y-index, previous direction, start-narrow,
    #          end-narrow, proven-consecutive-wide-run-nm)
    start_state = (start_node[0], start_node[1], -1,
                   bool(start_escape), False, 0)
    best = {start_state: 0.0}
    travelled = {start_state: 0.0}
    previous = {}
    serial = _itertools.count()
    heap = [(_to_target(start_node), 0.0, 0.0, next(serial), start_state)]
    final_state = None
    directions = ((1, 0), (-1, 0), (0, 1), (0, -1))
    clear_cache = {}
    foreign_zones, foreign_copper = _foreign_shape_indexes(
        board, lay, {nc}, cache=foreign_cache)

    def _hop_clear(A, B, width):
        ends = sorted(((A.x, A.y), (B.x, B.y)))
        key = (ends[0], ends[1], int(width))
        if key not in clear_cache:
            clear_cache[key] = bool(
                leg_ok(A, B, width // 2)
                and _snapshot_foreign_clear(
                    A, B, width, clearance_nm,
                    foreign_zones, foreign_copper))
        return clear_cache[key]

    while heap:
        _priority, cost, distance, _serial, state = _heapq.heappop(heap)
        if cost != best.get(state) or distance != travelled.get(state):
            continue
        ix_, iy_, old_dir, start_narrow, end_narrow, wide_run = state
        node = (ix_, iy_)
        if node == target_node and wide_run >= required_throat:
            final_state = state
            break
        if node == target_node:
            # Reaching the endpoint through overlapping narrow allowances is
            # not a partial success.  Expanding back out from the target can
            # manufacture a full-width dead-end spur and then return, falsely
            # claiming that the throat lies in series with the connection.
            continue
        current_to_target = _to_target(node)
        for direction, (dx, dy) in enumerate(directions):
            nx, ny = ix_ + dx, iy_ + dy
            if not (0 <= nx < len(xs) and 0 <= ny < len(ys)):
                continue
            next_node = (nx, ny)
            next_to_target = _to_target(next_node)
            if end_narrow and next_to_target >= current_to_target:
                continue
            A, B = _point(node), _point(next_node)
            length = abs(B.x - A.x) + abs(B.y - A.y)
            new_distance = distance + length
            if length <= 0 or new_distance > path_limit:
                continue

            next_start = False
            next_end = end_narrow
            width = int(w)
            if (start_narrow and start_escape
                    and new_distance <= float(start_escape[1]) + 1e-6):
                next_start = True
                width = min(width, int(start_escape[0]))
            if (end_escape and not next_start
                    and wide_run >= required_throat
                    and current_to_target <= float(end_escape[1]) + 1e-6
                    and next_to_target < current_to_target):
                next_end = True
                width = min(width, int(end_escape[0]))

            next_wide_run = wide_run
            if not next_start and not next_end:
                next_wide_run = min(required_throat, wide_run + length)

            if not _hop_clear(A, B, width):
                continue
            turn = 0 if old_dir in (-1, direction) else _nm(0.2)
            new_cost = cost + length + turn
            new_state = (nx, ny, direction, next_start, next_end,
                         int(next_wide_run))
            if new_cost >= best.get(new_state, float("inf")):
                continue
            best[new_state] = new_cost
            travelled[new_state] = new_distance
            previous[new_state] = (state, width)
            heuristic = next_to_target
            _heapq.heappush(heap, (new_cost + heuristic, new_cost,
                                   new_distance, next(serial), new_state))

    if final_state is None:
        return None
    rev = []
    state = final_state
    while state != start_state:
        prior, width = previous[state]
        rev.append((_point((prior[0], prior[1])),
                    _point((state[0], state[1])), width))
        state = prior
    rev.reverse()

    # Collapse raster runs only when both direction and qualified width match.
    out = []
    for A, B, width in rev:
        if out:
            P, Q, old_width = out[-1]
            same_axis = ((P.x == Q.x == A.x == B.x)
                         or (P.y == Q.y == A.y == B.y))
            if same_axis and Q == A and old_width == width:
                out[-1] = (P, B, width)
                continue
        out.append((A, B, width))
    return out


def _guarded_profiled_lastmile_legs(board, S, T, w, lay, clearance_nm, nc,
                                     leg_ok, *, start_escape=None,
                                     end_escape=None, allow_maze=True,
                                     maze_margin_mm=2.0,
                                     foreign_cache=None):
    """Choose a guarded canonical path with optional bounded pin neck-downs."""
    foreign_zones, foreign_copper = _foreign_shape_indexes(
        board, lay, {nc}, cache=foreign_cache)
    xy_paths = _canonical_45_xy_paths((S.x, S.y), (T.x, T.y))
    xy_paths += _offset_manhattan_xy_paths((S.x, S.y), (T.x, T.y))
    for xy_path in xy_paths:
        points = [pcbnew.VECTOR2I(x, y) for x, y in xy_path]
        legs = _profiled_lastmile_path(
            points, w, start_escape=start_escape, end_escape=end_escape)
        if all(leg_ok(a, b, width // 2)
               and _snapshot_foreign_clear(
                   a, b, width, clearance_nm,
                   foreign_zones, foreign_copper)
               for a, b, width in legs):
            return legs
    if allow_maze:
        return _maze_lastmile_legs(
            board, S, T, w, lay, clearance_nm, nc, leg_ok,
            start_escape=start_escape, end_escape=end_escape,
            margin_mm=maze_margin_mm,
            foreign_cache=foreign_cache)
    return None


def synthesize_local_power_bypass_links(
        board, *, max_mm=5.0, min_class_width=0.5, min_w=0.2,
        clearance=0.25, lock=True, netclass_resolver=None):
    """Pre-route short local supply links that the global router must preserve.

    A two-terminal fitted ``C*`` footprint with exactly one GND pad is a local
    bypass/bulk capacitor only when its other rail belongs to a power-width
    netclass.  Pair that rail pad with the nearest same-net SMD pad on an IC or
    reverse-mount LED (``U*``/``DL*``) within *max_mm*, then lay a guarded
    same-layer 0/45/90 path, or a guarded two-via bridge on a non-plane signal
    layer when the package pin row blocks the face route.  The class-width
    trunk and bounded fine-pad neck-downs use the same geometry contract as
    :func:`synthesize_lastmile` and :func:`normalize_netclass_geometry`.

    This deliberately ignores Default-class RC/filter capacitors and every
    connector/passive destination.  It is therefore a local power-integrity
    primitive, not a generic pre-router that could freeze arbitrary signal
    topology.  Collision, board-edge, and internal-cutout refusal is fail
    closed.  Returns ``{pairs, linked, legs, refused, ignored, detail}``.
    """
    import math as _math

    all_cu = set(board.GetEnabledLayers().CuStack())
    plane_ids = {board.GetLayerID(name) for name in plane_layers(board)}
    plane_ids.discard(-1)
    bridge_lays = [
        layer for layer in all_cu
        if layer != pcbnew.F_Cu and layer not in plane_ids
        and not any(role in board.GetLayerName(layer).upper()
                    for role in ("GND", "PWR"))]
    bridge_lays.sort(key=lambda layer: (
        0 if "SIG" in board.GetLayerName(layer).upper() else
        1 if board.GetLayerName(layer).upper().startswith("IN") else
        2 if layer == pcbnew.B_Cu else 3,
        layer))

    def _layers(pad):
        return frozenset(layer for layer in pad.GetLayerSet().CuStack()
                         if layer in all_cu)

    def _spec(net):
        if netclass_resolver is not None:
            return dict(netclass_resolver(net) or {})
        try:
            item = board.GetNetInfo().GetNetItem(net)
            klass = item.GetNetClassSlow()
            return {
                "name": klass.GetName(),
                "track_width": klass.GetTrackWidth() / MM,
                "clearance": klass.GetClearance() / MM,
            }
        except Exception:                                # noqa: BLE001
            return {}

    def _escape(pad, class_width):
        try:
            if int(pad.GetAttribute()) != int(pcbnew.PAD_ATTRIB_SMD):
                return None
        except Exception:                                # noqa: BLE001
            return None
        minor = min(pad.GetSize().x, pad.GetSize().y)
        if minor >= class_width:
            return None
        local_width = min(class_width, max(_nm(min_w), minor // 2))
        class_mm = class_width / MM
        budget = _nm(max(0.6, min(1.5, 1.5 * class_mm)))
        return local_width, budget

    def _pad_key(pad):
        pos = pad.GetPosition()
        try:
            ref = pad.GetParentFootprint().GetReference()
        except Exception:                                # noqa: BLE001
            ref = ""
        return ref, str(pad.GetNumber()), pos.x, pos.y

    def _already_connected(source, target):
        target_key = _pad_key(target)
        try:
            return any(item.GetClass() == "PAD"
                       and _pad_key(item) == target_key
                       for item in board.GetConnectivity().GetConnectedItems(source))
        except Exception:                                # noqa: BLE001
            return False

    loads_by_net = {}
    capacitors = []
    ignored = 0
    for fp in board.GetFootprints():
        ref = str(fp.GetReference() or "")
        try:
            if fp.IsDNP():
                continue
        except Exception:                                # noqa: BLE001
            pass
        pads = list(fp.Pads())
        if ref.startswith(("U", "DL")):
            for pad in pads:
                if (pad.GetNetCode() > 0
                        and pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD):
                    loads_by_net.setdefault(pad.GetNetname(), []).append(
                        (ref, pad))
        if not ref.startswith("C") or len(pads) != 2:
            continue
        ground = [pad for pad in pads if pad.GetNetname() == "GND"]
        rail = [pad for pad in pads
                if pad.GetNetCode() > 0 and pad.GetNetname() != "GND"]
        if len(ground) != 1 or len(rail) != 1:
            ignored += 1
            continue
        spec = _spec(rail[0].GetNetname())
        class_mm = float(spec.get("track_width") or 0.0)
        if class_mm < float(min_class_width):
            ignored += 1
            continue
        capacitors.append((ref, rail[0], spec, _nm(class_mm)))

    pairs = linked = legs_added = vias_added = refused = 0
    detail = []
    for cap_ref, cap_pad, spec, class_width in sorted(capacitors):
        cap_pos = cap_pad.GetPosition()
        cap_layers = _layers(cap_pad)
        candidates = []
        for load_ref, load_pad in loads_by_net.get(cap_pad.GetNetname(), ()):
            common = cap_layers & _layers(load_pad)
            if not common:
                continue
            load_pos = load_pad.GetPosition()
            distance = _math.hypot(load_pos.x - cap_pos.x,
                                   load_pos.y - cap_pos.y) / MM
            if 1e-9 < distance <= float(max_mm):
                candidates.append((distance, load_ref,
                                   str(load_pad.GetNumber()), load_pad,
                                   sorted(common)))
        candidates.sort(key=lambda row: (row[0], row[1], row[2]))
        if not candidates:
            refused += 1
            detail.append({"cap": cap_ref, "net": cap_pad.GetNetname(),
                           "status": "refused", "reason": "no local IC/LED pad"})
            continue
        pairs += 1
        board.BuildConnectivity()
        if any(_already_connected(cap_pad, row[3]) for row in candidates):
            detail.append({"cap": cap_ref, "net": cap_pad.GetNetname(),
                           "status": "already-connected"})
            continue

        net_code = cap_pad.GetNetCode()
        local_clearance = _nm(max(float(clearance),
                                  float(spec.get("clearance") or 0.0)))
        selected = None
        for distance, load_ref, load_number, load_pad, common in candidates[:4]:
            target = load_pad.GetPosition()
            for layer in common:
                path = _guarded_profiled_lastmile_legs(
                    board, cap_pos, target, class_width, layer,
                    local_clearance, net_code,
                    lambda start, end, half: _edge_leg_clear(
                        board, start, end, half),
                    start_escape=_escape(cap_pad, class_width),
                    end_escape=_escape(load_pad, class_width))
                if path:
                    selected = (distance, load_ref, load_number,
                                [("trk", start, end, width, layer)
                                 for start, end, width in path])
                    break
            if selected is None and bridge_lays:
                ops = _lastmile_bridge(
                    board, (cap_pos.x, cap_pos.y), cap_layers,
                    (target.x, target.y), _layers(load_pad),
                    class_width, net_code, bridge_lays, local_clearance,
                    drill=float(spec.get("via_drill") or 0.3),
                    dia=float(spec.get("via_diameter") or 0.6),
                    seat_limit=48,
                    leg_ok=lambda start, end, half: _edge_leg_clear(
                        board, start, end, half),
                    start_escape=_escape(cap_pad, class_width),
                    end_escape=_escape(load_pad, class_width))
                if ops:
                    selected = (distance, load_ref, load_number, ops)
            if selected:
                break
        if selected is None:
            refused += 1
            detail.append({"cap": cap_ref, "net": cap_pad.GetNetname(),
                           "status": "refused", "reason": "no guarded path"})
            continue

        distance, load_ref, load_number, ops = selected
        used_layers = set()
        link_vias = 0
        for op in ops:
            if op[0] == "via":
                _, at, drill, diameter = op
                via = pcbnew.PCB_VIA(board)
                via.SetPosition(at)
                via.SetDrill(_nm(drill))
                via.SetWidth(_nm(diameter))
                via.SetNetCode(net_code)
                via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                via.SetLocked(bool(lock))
                board.Add(via)
                vias_added += 1
                link_vias += 1
            else:
                _, start, end, width, layer = op
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(start)
                track.SetEnd(end)
                track.SetWidth(width)
                track.SetLayer(layer)
                track.SetNetCode(net_code)
                track.SetLocked(bool(lock))
                board.Add(track)
                used_layers.add(layer)
                legs_added += 1
        linked += 1
        detail.append({"cap": cap_ref, "load": load_ref,
                       "pad": load_number, "net": cap_pad.GetNetname(),
                       "distance_mm": round(distance, 3),
                       "layers": [board.GetLayerName(layer)
                                  for layer in sorted(used_layers)],
                       "legs": sum(op[0] == "trk" for op in ops),
                       "vias": link_vias, "status": "linked"})

    return {"pairs": pairs, "linked": linked, "legs": legs_added,
            "vias": vias_added, "refused": refused, "ignored": ignored,
            "detail": detail}


def synthesize_same_footprint_links(
        board, *, max_mm=3.0, min_w=0.2, clearance=0.20, lock=True,
        connector_power_max_mm=6.0, netclass_resolver=None,
        include_nets=None, include_refs=None):
    """Close duplicated same-net SMD pins locally before global routing.

    Multi-pin power switches, regulators, and buffers commonly expose two or
    more physical lands for one electrical node. Those lands should form a
    compact local copper cluster; leaving each as an independent global-router
    terminal wastes scarce escape channels and can strand a pad at a
    fine-pitch package corner.

    For every footprint-local same-net SMD group, use KiCad connectivity to
    find distinct components and join the nearest pair with the normal guarded
    0/45/90 last-mile geometry. Width, clearance, and bounded pad neck-downs
    come from the project's real netclass. THT pins remain plane/pour policy's
    responsibility. Kelvin nets remain excluded; duplicated differential-pair
    lands are synthesized only as an atomic two-leg breakout. A connector's
    repeated power lands may span farther than a compact IC package, so
    power-class groups on connector footprints receive the bounded
    ``connector_power_max_mm`` limit; signals and non-connectors retain
    ``max_mm``. Every collision or missing common layer refuses closed.
    ``include_nets`` optionally limits
    synthesis to an explicit net-name allowlist, allowing a pre-pour caller to
    establish only topology that must precede shaped copper. ``include_refs``
    applies the same explicit allowlist to footprint references. Returns
    ``{groups, linked, legs, vias, refused, ignored, detail}``.
    """
    import math as _math
    from collections import defaultdict

    all_cu = set(board.GetEnabledLayers().CuStack())
    kelvin = {net for pair in _board_kelvin_pairs(board) for net in pair}
    wanted = (None if include_nets is None
              else {str(net) for net in include_nets})
    wanted_refs = (None if include_refs is None
                   else {str(ref) for ref in include_refs})

    def _pad_key(pad):
        pos = pad.GetPosition()
        try:
            reference = pad.GetParentFootprint().GetReference()
        except Exception:                               # noqa: BLE001
            reference = ""
        return (reference, str(pad.GetNumber()), pos.x, pos.y)

    def _layers(pad):
        return frozenset(layer for layer in pad.GetLayerSet().CuStack()
                         if layer in all_cu)

    def _spec(net):
        if netclass_resolver is not None:
            return dict(netclass_resolver(net) or {})
        try:
            klass = board.GetNetInfo().GetNetItem(net).GetNetClassSlow()
            return {"track_width": klass.GetTrackWidth() / MM,
                    "clearance": klass.GetClearance() / MM}
        except Exception:                               # noqa: BLE001
            return {}

    def _pairish(net):
        upper = net.upper()
        return (bool(re.search(r"_(?:P|N)$", upper))
                or "USB_D" in upper
                or upper.endswith(("CAN_H", "CAN_L", "CAN_H_BUS",
                                   "CAN_L_BUS")))

    def _pair_mate(net):
        upper = net.upper()
        for left, right in (("CAN_H_BUS", "CAN_L_BUS"),
                            ("CAN_H", "CAN_L"), ("_P", "_N")):
            if upper.endswith(left):
                return net[:-len(left)] + right
            if upper.endswith(right):
                return net[:-len(right)] + left
        return None

    def _escape(pad, class_width):
        minor = min(pad.GetSize().x, pad.GetSize().y)
        if minor >= class_width:
            return None
        local_width = min(class_width, max(_nm(min_w), minor // 2))
        # _reserve_power_throat() reduces opposing budgets just enough to keep
        # a thermally meaningful class-width middle section; guarded geometry
        # refuses the link if that flare cannot fit beside the package pins.
        budget = _nm(max(0.6, min(1.5, 1.5 * class_width / MM)))
        return local_width, budget

    def _is_connector(reference, pads):
        if str(reference).upper().startswith("J"):
            return True
        try:
            name = str(pads[0].GetParentFootprint().GetFPID()
                       .GetLibItemName()).upper()
        except Exception:                               # noqa: BLE001
            name = ""
        return any(token in name for token in (
            "CONN", "USB", "RJ45", "MOLEX", "JST", "HEADER"))

    groups = []
    pair_groups = []
    ignored = 0
    for footprint in board.GetFootprints():
        try:
            if footprint.IsDNP():
                continue
        except Exception:                               # noqa: BLE001
            pass
        if (wanted_refs is not None
                and str(footprint.GetReference()) not in wanted_refs):
            continue
        by_net = defaultdict(list)
        for pad in footprint.Pads():
            if (pad.GetNetCode() > 0 and pad.GetNetname()
                    and pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD):
                by_net[pad.GetNetname()].append(pad)
        paired_names = set()
        for net in sorted(by_net):
            if wanted is not None and net not in wanted:
                continue
            mate = _pair_mate(net)
            if (not mate or mate not in by_net or net >= mate
                    or len(by_net[net]) != 2 or len(by_net[mate]) != 2):
                continue
            pair_groups.append((footprint.GetReference(), net, by_net[net],
                                mate, by_net[mate]))
            paired_names.update((net, mate))
        for net, pads in by_net.items():
            if wanted is not None and net not in wanted:
                ignored += 1
            elif len(pads) >= 2 and net not in kelvin and not _pairish(net):
                groups.append((footprint.GetReference(), net, pads))
            elif net not in paired_names:
                ignored += 1

    plane_ids = {board.GetLayerID(name) for name in plane_layers(board)}
    plane_ids.discard(-1)
    bridge_lays = [
        layer for layer in all_cu
        if layer != pcbnew.F_Cu and layer not in plane_ids
        and not any(role in board.GetLayerName(layer).upper()
                    for role in ("GND", "PWR"))]
    bridge_lays.sort(key=lambda layer: (
        0 if "SIG" in board.GetLayerName(layer).upper() else
        1 if board.GetLayerName(layer).upper().startswith("IN") else
        2 if layer == pcbnew.B_Cu else 3,
        layer))

    linked = legs_added = vias_added = refused = 0
    detail = []
    for reference, net, pads in sorted(groups, key=lambda row: (row[0], row[1])):
        spec = _spec(net)
        width_mm = float(spec.get("track_width") or min_w)
        class_width = _nm(max(float(min_w), width_mm))

        def _group_width(layer):
            by_layer = spec.get("track_width_by_layer_mm") or {}
            layer_name = _fab.COPPER_LAYER_IDS.get(
                int(layer), board.GetLayerName(int(layer)))
            return _nm(max(
                float(min_w), width_mm,
                float(by_layer.get(layer_name) or 0.0)))

        connector_power = _is_connector(reference, pads) and width_mm >= 0.5
        group_max_mm = float(max_mm)
        if connector_power:
            group_max_mm = max(group_max_mm,
                               float(connector_power_max_mm))
        local_clearance = _nm(max(float(clearance),
                                  float(spec.get("clearance") or 0.0)))
        blocked = set()
        group_links = 0
        while True:
            if group_links >= len(pads) - 1:
                # Every selected edge joins two distinct connectivity roots,
                # so n-1 emitted links are a complete spanning tree even when
                # pcbnew has not refreshed its connectivity cache yet.  The
                # former branch mislabeled every successful ordinary group as
                # a refusal on the following pass.
                break
            board.BuildConnectivity()
            connectivity = board.GetConnectivity()
            parent = list(range(len(pads)))

            def _find(index):
                while parent[index] != index:
                    parent[index] = parent[parent[index]]
                    index = parent[index]
                return index

            def _union(left, right):
                left, right = _find(left), _find(right)
                if left != right:
                    parent[right] = left

            key_to_index = {_pad_key(pad): index
                            for index, pad in enumerate(pads)}
            for index, pad in enumerate(pads):
                try:
                    connected = connectivity.GetConnectedItems(pad)
                except Exception:                       # noqa: BLE001
                    connected = ()
                for item in connected:
                    if item.GetClass() != "PAD":
                        continue
                    other = key_to_index.get(_pad_key(item))
                    if other is not None:
                        _union(index, other)
            roots = {_find(index) for index in range(len(pads))}
            if len(roots) <= 1:
                break

            candidates = []
            for left in range(len(pads)):
                for right in range(left + 1, len(pads)):
                    if _find(left) == _find(right):
                        continue
                    pair_key = (_pad_key(pads[left]), _pad_key(pads[right]))
                    if pair_key in blocked:
                        continue
                    common = _layers(pads[left]) & _layers(pads[right])
                    if not common:
                        blocked.add(pair_key)
                        continue
                    a, b = pads[left].GetPosition(), pads[right].GetPosition()
                    distance = _math.hypot(b.x - a.x, b.y - a.y) / MM
                    if distance <= group_max_mm:
                        candidates.append((distance, left, right, pair_key,
                                           sorted(common)))
            candidates.sort(key=lambda row: (row[0], row[1], row[2]))
            selected = None
            for distance, left, right, pair_key, common in candidates:
                start, end = pads[left].GetPosition(), pads[right].GetPosition()
                # A repeated power bank on a high-pin-count connector usually
                # has signal pins between its two lands. Prefer perpendicular
                # dogbones plus an inner-signal-layer bridge so the surface
                # pin-breakout corridor stays available to coupled/high-speed
                # routing. Ordinary IC-local groups still prefer the shorter
                # same-layer connection and use a bridge only as fallback.
                if connector_power and bridge_lays:
                    ops = _lastmile_bridge(
                        board, (start.x, start.y), _layers(pads[left]),
                        (end.x, end.y), _layers(pads[right]),
                        class_width, pads[left].GetNetCode(), bridge_lays,
                        local_clearance,
                        drill=float(spec.get("via_drill") or 0.3),
                        dia=float(spec.get("via_diameter") or 0.6),
                        seat_limit=48,
                        leg_ok=lambda a, b, half: _edge_leg_clear(
                            board, a, b, half),
                        start_escape=_escape(
                            pads[left], _group_width(min(_layers(pads[left])))),
                        end_escape=_escape(
                            pads[right], _group_width(min(_layers(pads[right])))),
                        width_for_layer=_group_width)
                    if ops:
                        selected = (distance, left, right, None, None, ops)
                        break
                for layer in common:
                    layer_width = _group_width(layer)
                    path = _guarded_profiled_lastmile_legs(
                        board, start, end, layer_width, layer,
                        local_clearance, pads[left].GetNetCode(),
                        lambda a, b, half: _edge_leg_clear(board, a, b, half),
                        start_escape=_escape(pads[left], layer_width),
                        end_escape=_escape(pads[right], layer_width))
                    if path:
                        selected = (distance, left, right, layer, path, None)
                        break
                if selected:
                    break
                if bridge_lays and not connector_power:
                    ops = _lastmile_bridge(
                        board, (start.x, start.y), _layers(pads[left]),
                        (end.x, end.y), _layers(pads[right]),
                        class_width, pads[left].GetNetCode(), bridge_lays,
                        local_clearance,
                        drill=float(spec.get("via_drill") or 0.3),
                        dia=float(spec.get("via_diameter") or 0.6),
                        seat_limit=48,
                        leg_ok=lambda a, b, half: _edge_leg_clear(
                            board, a, b, half),
                        start_escape=_escape(
                            pads[left], _group_width(min(_layers(pads[left])))),
                        end_escape=_escape(
                            pads[right], _group_width(min(_layers(pads[right])))),
                        width_for_layer=_group_width)
                    if ops:
                        selected = (distance, left, right, None, None, ops)
                        break
                blocked.add(pair_key)
            if selected is None:
                missing = len(roots) - 1
                refused += missing
                detail.append({"ref": reference, "net": net,
                               "status": "refused",
                               "remaining_components": len(roots)})
                break

            distance, left, right, layer, path, bridge_ops = selected
            if bridge_ops:
                used_layers = set()
                for op in bridge_ops:
                    if op[0] == "via":
                        _, at, drill, diameter = op
                        via = pcbnew.PCB_VIA(board)
                        via.SetPosition(at)
                        via.SetDrill(_nm(drill))
                        via.SetWidth(_nm(diameter))
                        via.SetNetCode(pads[left].GetNetCode())
                        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                        via.SetLocked(bool(lock))
                        board.Add(via)
                        vias_added += 1
                    else:
                        _, start, end, width, op_layer = op
                        track = pcbnew.PCB_TRACK(board)
                        track.SetStart(start); track.SetEnd(end)
                        track.SetWidth(width); track.SetLayer(op_layer)
                        track.SetNetCode(pads[left].GetNetCode())
                        track.SetLocked(bool(lock)); board.Add(track)
                        used_layers.add(op_layer)
                        legs_added += 1
                layer_names = [board.GetLayerName(value)
                               for value in sorted(used_layers)]
                path_legs = sum(op[0] == "trk" for op in bridge_ops)
            else:
                for start, end, width in path:
                    track = pcbnew.PCB_TRACK(board)
                    track.SetStart(start); track.SetEnd(end); track.SetWidth(width)
                    track.SetLayer(layer); track.SetNetCode(pads[left].GetNetCode())
                    track.SetLocked(bool(lock)); board.Add(track)
                    legs_added += 1
                layer_names = [board.GetLayerName(layer)]
                path_legs = len(path)
            linked += 1
            group_links += 1
            detail.append({"ref": reference, "net": net,
                           "from": str(pads[left].GetNumber()),
                           "to": str(pads[right].GetNumber()),
                           "distance_mm": round(distance, 3),
                           "layers": layer_names,
                           "legs": path_legs,
                           "vias": (sum(op[0] == "via" for op in bridge_ops)
                                    if bridge_ops else 0),
                           "status": "linked"})

    # USB-C and similar reversible connectors interleave the duplicate lands
    # of the two pair legs along one pad row.  Joining either net alone can
    # strand its mate or make the global router cross the completed leg.  Tie
    # the two duplicate groups atomically as opposed-side U fanouts on the same
    # signal layer: one pair leg leaves each side of the row, exactly the
    # standard reversible-connector breakout topology.  Both guarded plans
    # must succeed before either is emitted.
    pair_linked = pair_legs = pair_refused = 0
    for reference, net_a, pads_a, net_b, pads_b in pair_groups:
        board.BuildConnectivity()
        connectivity = board.GetConnectivity()

        def _group_connected(pads):
            target = _pad_key(pads[1])
            try:
                return any(item.GetClass() == "PAD"
                           and _pad_key(item) == target
                           for item in connectivity.GetConnectedItems(pads[0]))
            except Exception:                           # noqa: BLE001
                return False

        connected_a = _group_connected(pads_a)
        connected_b = _group_connected(pads_b)
        if connected_a and connected_b:
            continue
        if connected_a != connected_b:
            refused += 1
            pair_refused += 1
            detail.append({"ref": reference, "nets": [net_a, net_b],
                           "status": "refused",
                           "reason": "one pair leg was already connected"})
            continue
        pads_all = pads_a + pads_b
        xs = [pad.GetPosition().x for pad in pads_all]
        ys = [pad.GetPosition().y for pad in pads_all]
        axis_x = max(xs) - min(xs) >= max(ys) - min(ys)
        normal = ys if axis_x else xs
        single_row = max(normal) - min(normal) <= _nm(0.20)
        common = set(all_cu) - plane_ids
        for pad in pads_all:
            common &= set(_layers(pad))
        if not common:
            refused += 2
            pair_refused += 2
            detail.append({"ref": reference, "nets": [net_a, net_b],
                           "status": "refused",
                           "reason": "no common non-plane copper layer"})
            continue

        pair_specs = {net: _spec(net) for net in (net_a, net_b)}
        pair_widths = {
            net: _nm(max(float(min_w), float(
                pair_specs[net].get("diff_pair_width")
                or pair_specs[net].get("track_width") or min_w)))
            for net in (net_a, net_b)}
        pair_clearances = {
            net: _nm(max(float(clearance), float(
                pair_specs[net].get("clearance") or 0.0)))
            for net in (net_a, net_b)}
        normal_halves = [
            (pad.GetSize().y if axis_x else pad.GetSize().x) // 2
            for pad in pads_all]
        base_offset = int(max(
            _nm(0.75), max(normal_halves)
            + max(pair_widths.values()) // 2
            + max(pair_clearances.values()) + _nm(0.05)))
        offset_choices = [base_offset + _nm(step)
                          for step in (0.0, 0.25, 0.50, 0.75)]

        def _u_plan(net, pads, sign, offset, layer):
            pads = sorted(pads, key=lambda pad: (
                pad.GetPosition().x if axis_x else pad.GetPosition().y,
                str(pad.GetNumber())))
            start, end = pads[0].GetPosition(), pads[1].GetPosition()
            if axis_x:
                first = pcbnew.VECTOR2I(start.x, start.y + sign * offset)
                second = pcbnew.VECTOR2I(end.x, end.y + sign * offset)
            else:
                first = pcbnew.VECTOR2I(start.x + sign * offset, start.y)
                second = pcbnew.VECTOR2I(end.x + sign * offset, end.y)
            width = pair_widths[net]
            local_clearance = pair_clearances[net]
            legs = []
            for source, target, start_escape, end_escape in (
                    (start, first, _escape(pads[0], width), None),
                    (first, second, None, None),
                    (second, end, None, _escape(pads[1], width))):
                section = _guarded_profiled_lastmile_legs(
                    board, source, target, width, layer, local_clearance,
                    pads[0].GetNetCode(),
                    lambda a, b, half: _edge_leg_clear(board, a, b, half),
                    start_escape=start_escape, end_escape=end_escape,
                    allow_maze=False)
                if not section:
                    if os.environ.get("CEC_PAIR_DEBUG") == "1":
                        print("[fr] pair fanout leg refused", net,
                              board.GetLayerName(layer), "sign", sign,
                              "offset_mm", round(offset / MM, 3),
                              [round(source.x / MM, 6),
                               round(source.y / MM, 6)], "->",
                              [round(target.x / MM, 6),
                               round(target.y / MM, 6)],
                              file=sys.stderr)
                    return None
                legs.extend(section)
            return legs

        def _direct_plan(net, pads, layer):
            pads = sorted(pads, key=lambda pad: (
                pad.GetPosition().x, pad.GetPosition().y,
                str(pad.GetNumber())))
            start, end = pads[0].GetPosition(), pads[1].GetPosition()
            width = pair_widths[net]
            local_clearance = pair_clearances[net]
            legs = _profiled_lastmile_path(
                [start, end], width,
                start_escape=_escape(pads[0], width),
                end_escape=_escape(pads[1], width))
            checks = []
            for source, target, leg_width in legs:
                edge_clear = _edge_leg_clear(
                    board, source, target, leg_width // 2)
                foreign_clear = _tap_foreign_clear(
                    board, source, target, leg_width, layer,
                    local_clearance, {pads[0].GetNetCode()})
                check = {
                    "from_mm": [round(source.x / MM, 6),
                                round(source.y / MM, 6)],
                    "to_mm": [round(target.x / MM, 6),
                              round(target.y / MM, 6)],
                    "width_mm": round(leg_width / MM, 6),
                    "edge_clear": bool(edge_clear),
                    "foreign_clear": bool(foreign_clear),
                }
                if not foreign_clear:
                    zones, copper = _identified_foreign_shape_indexes(
                        board, layer, {pads[0].GetNetCode()})
                    check["foreign_blockers"] = _snapshot_foreign_blockers(
                        source, target, leg_width, local_clearance,
                        zones, copper)
                checks.append(check)
            return ((legs if all(row["edge_clear"]
                                 and row["foreign_clear"]
                                 for row in checks) else None), {
                "net": net,
                "pads": [str(pad.GetNumber()) for pad in pads],
                "layer": board.GetLayerName(layer),
                "checks": checks,
            })

        def _plans_mutually_clear(plan_a, plan_b):
            """True when two not-yet-emitted pair fanouts do not overlap.

            Each candidate is independently guarded against copper already on
            the board.  That proof cannot see its sibling candidate because
            both plans are intentionally selected before either is committed.
            Check their actual swept copper shapes together here; the
            high-speed pair gate separately enforces the requested electrical
            gap after the complete route is assembled.
            """
            for a0, a1, aw in plan_a:
                a_shape = pcbnew.SHAPE_SEGMENT(a0, a1, int(aw))
                for b0, b1, bw in plan_b:
                    b_shape = pcbnew.SHAPE_SEGMENT(b0, b1, int(bw))
                    if a_shape.Collide(b_shape, 0):
                        return False
            return True

        def _plan_topology_clear(net, plan, layer):
            """Reject a local fanout that doubles back over owned copper.

            Foreign-clearance admission deliberately ignores the candidate's
            own net.  That is electrically correct, but it allowed a new
            duplicate-pad leg to leave a land in the same direction as the
            already-owned long route, overlap it briefly, and then peel away.
            Treat all existing and proposed same-net incident rays as one
            graph and require an opening of at least 89 degrees whenever a
            proposed ray participates.  A straight continuation is 180
            degrees and a right-angle package escape is legal; a covered
            pseudo-stub is 0 degrees and is refused before copper is emitted.
            """
            proposed = []
            vertices = set()
            for start, end, _width in plan:
                if start == end:
                    continue
                a = (int(start.x), int(start.y))
                b = (int(end.x), int(end.y))
                proposed.append((a, b))
                vertices.update((a, b))

            existing = []
            for item in board.GetTracks():
                if (item.GetClass() != "PCB_TRACK"
                        or int(item.GetLayer()) != int(layer)
                        or item.GetNetname() != net
                        or item.GetStart() == item.GetEnd()):
                    continue
                existing.append(((int(item.GetStart().x),
                                  int(item.GetStart().y)),
                                 (int(item.GetEnd().x),
                                  int(item.GetEnd().y))))

            def on_segment(point, a, b):
                cross = ((b[0] - a[0]) * (point[1] - a[1])
                         - (b[1] - a[1]) * (point[0] - a[0]))
                if cross:
                    return False
                return (min(a[0], b[0]) <= point[0] <= max(a[0], b[0])
                        and min(a[1], b[1]) <= point[1] <= max(a[1], b[1]))

            for at in vertices:
                rays = []
                for a, b in proposed:
                    if at == a:
                        rays.append((b[0] - a[0], b[1] - a[1], True))
                    elif at == b:
                        rays.append((a[0] - b[0], a[1] - b[1], True))
                for a, b in existing:
                    if not on_segment(at, a, b):
                        continue
                    if at != a:
                        rays.append((a[0] - at[0], a[1] - at[1], False))
                    if at != b:
                        rays.append((b[0] - at[0], b[1] - at[1], False))
                for index, first in enumerate(rays):
                    for second in rays[index + 1:]:
                        if not (first[2] or second[2]):
                            continue
                        n1 = math.hypot(first[0], first[1])
                        n2 = math.hypot(second[0], second[1])
                        if not n1 or not n2:
                            continue
                        cosine = ((first[0] * second[0]
                                   + first[1] * second[1]) / (n1 * n2))
                        if cosine > math.cos(math.radians(89.0)) + 1e-12:
                            if os.environ.get("CEC_PAIR_DEBUG") == "1":
                                print("[fr] pair fanout topology reject",
                                      net, board.GetLayerName(layer),
                                      [round(at[0] / 1e6, 6),
                                       round(at[1] / 1e6, 6)],
                                      "cos=%.6f" % cosine,
                                      "rays", first, second,
                                      file=sys.stderr)
                            return False
            return True

        selected = None
        layer_order = sorted(common,
                             key=lambda layer: (layer != pcbnew.F_Cu, layer))
        # Parallel package rows (for example a flow-through USB protector)
        # need only two short, parallel ties.  Try that lower-discontinuity
        # topology before the reversible-connector U breakout.
        direct_attempts = []
        for layer in layer_order:
            plan_a, evidence_a = _direct_plan(net_a, pads_a, layer)
            plan_b, evidence_b = _direct_plan(net_b, pads_b, layer)
            mutually_clear = bool(
                plan_a and plan_b and _plans_mutually_clear(plan_a, plan_b))
            topology_a = bool(
                plan_a and _plan_topology_clear(net_a, plan_a, layer))
            topology_b = bool(
                plan_b and _plan_topology_clear(net_b, plan_b, layer))
            direct_attempts.append({
                "layer": board.GetLayerName(layer),
                "members": [evidence_a, evidence_b],
                "mutually_clear": mutually_clear,
                "topology_clear": {net_a: topology_a, net_b: topology_b},
            })
            if (plan_a and plan_b and mutually_clear
                    and topology_a and topology_b):
                selected = [
                    (net_a, pads_a,
                     [("trk", a, b, width, layer)
                      for a, b, width in plan_a]),
                    (net_b, pads_b,
                     [("trk", a, b, width, layer)
                      for a, b, width in plan_b]),
                ]
                break
        if selected is None and single_row:
            for layer in layer_order:
                # Opposite sides are the compact default, but both selected
                # lands may already launch in the same direction.  In that
                # case forcing one duplicate closure onto the opposite side
                # creates a covered backtrack.  Search nested same-side lanes
                # as well; exact mutual-shape and topology admission below
                # decides whether their differing offsets are genuinely safe.
                for sign_a, sign_b in ((-1, 1), (1, -1),
                                       (-1, -1), (1, 1)):
                    for offset_a in offset_choices:
                        plan_a = _u_plan(net_a, pads_a, sign_a, offset_a, layer)
                        if not plan_a:
                            continue
                        for offset_b in offset_choices:
                            plan_b = _u_plan(net_b, pads_b, sign_b, offset_b, layer)
                            if (plan_b
                                    and _plans_mutually_clear(plan_a, plan_b)
                                    and _plan_topology_clear(
                                        net_a, plan_a, layer)
                                    and _plan_topology_clear(
                                        net_b, plan_b, layer)):
                                selected = [
                                    (net_a, pads_a,
                                     [("trk", a, b, width, layer)
                                      for a, b, width in plan_a]),
                                    (net_b, pads_b,
                                     [("trk", a, b, width, layer)
                                      for a, b, width in plan_b]),
                                ]
                                break
                        if selected:
                            break
                    if selected:
                        break
                if selected:
                    break
        if selected is None and single_row and bridge_lays:
            # Four interleaved pair lands can be topologically impossible to
            # close on one surface.  Under an explicitly declared POFV
            # process, transition all four lands symmetrically in pad and join
            # the two members as opposite-side U paths on one signal layer.
            # This keeps layer sets, via counts, delay and return paths matched;
            # without POFV authority this fallback simply does not exist.
            profile_name = _fab.board_profile_name(board)
            profile = _fab.PROFILES.get(profile_name)
            # This is the rare fine-pitch escape where the profile's preferred
            # drill may not fit the land.  Use the profile's explicit minimum
            # drill plus its annular-ring floor; dimensions are still checked
            # by the central POFV authority for every actual pad.
            pofv = ((float(profile["pofv_drill_min_mm"])
                     + 2.0 * float(profile["pofv_annular_min_mm"]),
                     float(profile["pofv_drill_min_mm"]))
                    if profile and profile.get("pofv") else None)
            gnd = board.FindNet("GND")
            if os.environ.get("CEC_PAIR_DEBUG") == "1":
                print("[fr] paired POFV fallback", reference,
                      profile_name, pofv,
                      [board.GetLayerName(value) for value in bridge_lays],
                      bool(gnd), file=sys.stderr)
            if pofv and gnd is not None:
                via_dia, via_drill = pofv
                pair_clearance = max(pair_clearances.values())
                exact_clearance = max(0, pair_clearance - 1)

                def _probe(net, pads, plan, layer, probes):
                    nc = pads[0].GetNetCode()
                    # KiCad SHAPE::Collide treats exact tangency as a hit;
                    # clearance DRC treats the published minimum as legal.
                    # Remove one database unit (1 nm) so an exact 0.200 mm
                    # fine-pitch field is admitted while anything physically
                    # below the rule remains rejected by a huge margin.
                    for pad in pads:
                        at = pad.GetPosition()
                        if not _via_spot_clear(
                                board, at, _nm(via_dia), exact_clearance,
                                {nc}, drill_nm=_nm(via_drill), net_code=nc,
                                contained_layers=(pcbnew.F_Cu,)):
                            if os.environ.get("CEC_PAIR_DEBUG") == "1":
                                blocking, allowed = _fab.via_at_pad_conflicts(
                                    board, at, _nm(via_dia),
                                    _nm(via_drill), nc)
                                # Match the point-like 1 nm probe used by the
                                # actual via admission test.  A 10 um debug
                                # segment could report a blocker that the real
                                # geometry check correctly admits at the fab
                                # minimum, sending investigations down the
                                # wrong path.
                                probe = pcbnew.VECTOR2I(at.x + 1, at.y)
                                layer_clear = {
                                    board.GetLayerName(lid):
                                    _tap_foreign_clear(
                                        board, at, probe, _nm(via_dia), lid,
                                        exact_clearance, {nc})
                                    for lid in board.GetEnabledLayers().CuStack()
                                    if lid != pcbnew.F_Cu}
                                blockers = {}
                                for lid in board.GetEnabledLayers().CuStack():
                                    if lid == pcbnew.F_Cu:
                                        continue
                                    zones, copper = _identified_foreign_shape_indexes(
                                        board, lid, {nc})
                                    blockers[board.GetLayerName(lid)] = (
                                        _snapshot_foreign_blockers(
                                            at, probe, _nm(via_dia),
                                            exact_clearance, zones, copper))
                                print("[fr] paired POFV via refused", net,
                                      pad.GetNumber(),
                                      (blocking.GetNetname()
                                       if blocking is not None else None),
                                      allowed, layer_clear, blockers,
                                      file=sys.stderr)
                            return False
                        via = pcbnew.PCB_VIA(board)
                        via.SetPosition(at); via.SetWidth(_nm(via_dia))
                        via.SetDrill(_nm(via_drill)); via.SetNetCode(nc)
                        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                        board.Add(via); probes.append(via)
                    for a, b, width in plan:
                        if (not _edge_leg_clear(board, a, b, width // 2)
                                or not _tap_foreign_clear(
                                    board, a, b, width, layer,
                                    exact_clearance, {nc})):
                            if os.environ.get("CEC_PAIR_DEBUG") == "1":
                                print("[fr] paired POFV track refused", net,
                                      board.GetLayerName(layer), file=sys.stderr)
                            return False
                        track = pcbnew.PCB_TRACK(board)
                        track.SetStart(a); track.SetEnd(b)
                        track.SetWidth(width); track.SetLayer(layer)
                        track.SetNetCode(nc); board.Add(track)
                        probes.append(track)
                    return True

                def _return_ops(probes):
                    """Prove one nearby GND barrel at each pad-bank end."""
                    gnd_code = gnd.GetNetCode()
                    ordered = sorted(
                        (pad.GetPosition() for pad in pads_all),
                        key=lambda point: point.x if axis_x else point.y)
                    out = []
                    for center in (ordered[0], ordered[-1]):
                        nearest = min((math.hypot(
                            item.GetPosition().x - center.x,
                            item.GetPosition().y - center.y)
                            for item in board.GetTracks()
                            if item.GetClass() == "PCB_VIA"
                            and item.GetNetname() == "GND"),
                            default=float("inf"))
                        if nearest <= _nm(1.50):
                            continue
                        accepted = None
                        base = math.pi / 2 if axis_x else 0.0
                        for radius in (0.80, 1.00, 1.20, 1.40):
                            for step in range(8):
                                angle = base + step * math.pi / 4
                                at = pcbnew.VECTOR2I(
                                    center.x + int(round(
                                        _nm(radius) * math.cos(angle))),
                                    center.y + int(round(
                                        _nm(radius) * math.sin(angle))))
                                if (not _edge_leg_clear(
                                        board, at, at, _nm(0.30))
                                        or not _via_spot_clear(
                                            board, at, _nm(0.60),
                                            exact_clearance, {gnd_code},
                                            drill_nm=_nm(0.30),
                                            net_code=gnd_code)):
                                    continue
                                via = pcbnew.PCB_VIA(board)
                                via.SetPosition(at); via.SetWidth(_nm(0.60))
                                via.SetDrill(_nm(0.30))
                                via.SetNetCode(gnd_code)
                                via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                                board.Add(via); probes.append(via)
                                accepted = ("gnd_via", at, 0.30, 0.60)
                                break
                            if accepted:
                                break
                        if accepted is None:
                            return None
                        out.append(accepted)
                    return out

                for layer in bridge_lays:
                    for sign_a, sign_b in ((-1, 1), (1, -1)):
                        for offset_a in offset_choices:
                            plan_a = _u_plan(
                                net_a, pads_a, sign_a, offset_a, layer)
                            if not plan_a:
                                continue
                            for offset_b in offset_choices:
                                plan_b = _u_plan(
                                    net_b, pads_b, sign_b, offset_b, layer)
                                if (not plan_b
                                        or not _plans_mutually_clear(
                                            plan_a, plan_b)):
                                    continue
                                if os.environ.get("CEC_PAIR_DEBUG") == "1":
                                    print("[fr] paired POFV candidate", reference,
                                          board.GetLayerName(layer), sign_a,
                                          round(offset_a / MM, 3),
                                          round(offset_b / MM, 3),
                                          file=sys.stderr)
                                probes = []
                                ok = (_probe(net_a, pads_a, plan_a,
                                             layer, probes)
                                      and _probe(net_b, pads_b, plan_b,
                                                 layer, probes))
                                return_ops = (_return_ops(probes) if ok
                                              else None)
                                ok = ok and return_ops is not None
                                for item in reversed(probes):
                                    board.Remove(item)
                                if not ok:
                                    continue
                                via_ops_a = [("via", pad.GetPosition(),
                                              via_drill, via_dia)
                                             for pad in pads_a]
                                via_ops_b = [("via", pad.GetPosition(),
                                              via_drill, via_dia)
                                             for pad in pads_b]
                                selected = [
                                    (net_a, pads_a, via_ops_a + return_ops + [
                                        ("trk", a, b, width, layer)
                                        for a, b, width in plan_a]),
                                    (net_b, pads_b, via_ops_b + [
                                        ("trk", a, b, width, layer)
                                        for a, b, width in plan_b]),
                                ]
                                break
                            if selected:
                                break
                        if selected:
                            break
                    if selected:
                        break
        if selected is None:
            refused += 2
            pair_refused += 2
            detail.append({"ref": reference, "nets": [net_a, net_b],
                           "status": "refused",
                           "reason": "no atomic guarded pair fanout",
                           "direct_attempts": direct_attempts})
            continue
        for net, pads, ops in selected:
            used_layers = set()
            pair_vias = return_vias = 0
            for op in ops:
                if op[0] in ("via", "gnd_via"):
                    _, at, drill, diameter = op
                    via = pcbnew.PCB_VIA(board)
                    via.SetPosition(at); via.SetDrill(_nm(drill))
                    via.SetWidth(_nm(diameter))
                    if op[0] == "gnd_via":
                        via.SetNetCode(board.FindNet("GND").GetNetCode())
                        return_vias += 1
                    else:
                        via.SetNetCode(pads[0].GetNetCode())
                        pair_vias += 1
                    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                    via.SetLocked(bool(lock)); board.Add(via)
                    vias_added += 1
                    continue
                _, start, end, width, op_layer = op
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(start); track.SetEnd(end); track.SetWidth(width)
                track.SetLayer(op_layer)
                track.SetNetCode(pads[0].GetNetCode())
                track.SetLocked(bool(lock)); board.Add(track)
                used_layers.add(op_layer)
                legs_added += 1; pair_legs += 1
            linked += 1
            pair_linked += 1
            detail.append({"ref": reference, "net": net,
                           "from": str(pads[0].GetNumber()),
                           "to": str(pads[1].GetNumber()),
                           "layers": [board.GetLayerName(value)
                                      for value in sorted(used_layers)],
                           "legs": sum(op[0] == "trk" for op in ops),
                           "vias": pair_vias,
                           "return_vias": return_vias,
                           "atomic_pair": True,
                           "status": "linked"})

    return {"groups": len(groups) + 2 * len(pair_groups),
            "linked": linked, "legs": legs_added, "vias": vias_added,
            "refused": refused, "ignored": ignored,
            "pair_groups": len(pair_groups), "pair_linked": pair_linked,
            "pair_legs": pair_legs, "pair_refused": pair_refused,
            "detail": detail}


def synthesize_local_signal_links(
        board, *, max_mm=5.0, max_refs=3, min_power_width=0.5,
        min_w=0.2, clearance=0.20, lock=True,
        netclass_resolver=None, include_nets=None):
    """Pre-route topology-proven private IC programming networks.

    A local threshold divider, soft-start capacitor, or current-limit resistor
    should be complete before the global router spends congestion budget on
    it.  Select only nets with one ``U*`` owner and one or two fitted ``R*``/
    ``C*`` followers, no connector or other active member, a non-power
    netclass width, and no Kelvin/differential-pair role.  Connect the nearest
    remaining follower to the already-connected local cluster with guarded
    same-layer 0/45/90 copper.  This is the routing counterpart of the placer's
    low-fanout functional ownership rule and contains no board/refdes list.

    ``include_nets`` optionally restricts the topology-derived candidates to
    an exact set.  This supports a fail-driven second materialization pass:
    only private networks that the finished pour actually refused are allowed
    to reserve pre-pour copper, so unrelated control cells cannot partition a
    wide-rail solve.

    Distributed rails, buses, connector nets, high-speed pairs, and every
    cross-layer-only case remain the global router's responsibility.  All
    collision and edge checks fail closed and emitted tracks are locked so the
    router cannot scatter the local cell again.
    """
    import math as _math
    from collections import defaultdict

    all_cu = set(board.GetEnabledLayers().CuStack())
    pads_by_net = defaultdict(list)
    pad_count_by_ref = {}
    for fp in board.GetFootprints():
        ref = str(fp.GetReference() or "")
        try:
            if fp.IsDNP():
                continue
        except Exception:                                # noqa: BLE001
            pass
        fitted_pads = list(fp.Pads())
        pad_count_by_ref[ref] = len(fitted_pads)
        for pad in fitted_pads:
            if pad.GetNetCode() > 0 and pad.GetNetname():
                pads_by_net[pad.GetNetname()].append((ref, pad))

    kelvin = {net for pair in _board_kelvin_pairs(board) for net in pair}

    def _spec(net):
        if netclass_resolver is not None:
            return dict(netclass_resolver(net) or {})
        try:
            klass = board.GetNetInfo().GetNetItem(net).GetNetClassSlow()
            return {"name": klass.GetName(),
                    "track_width": klass.GetTrackWidth() / MM,
                    "clearance": klass.GetClearance() / MM}
        except Exception:                                # noqa: BLE001
            return {}

    def _pairish(net):
        upper = net.upper()
        return (net in kelvin or "USB_D" in upper
                or upper.endswith(("_P", "_N", "CAN_H", "CAN_L",
                                   "CAN_H_BUS", "CAN_L_BUS")))

    def _layers(pad):
        return frozenset(layer for layer in pad.GetLayerSet().CuStack()
                         if layer in all_cu)

    def _escape(pad, class_width):
        try:
            if int(pad.GetAttribute()) != int(pcbnew.PAD_ATTRIB_SMD):
                return None
        except Exception:                                # noqa: BLE001
            return None
        minor = min(pad.GetSize().x, pad.GetSize().y)
        if minor >= class_width:
            return None
        local_width = min(class_width, max(_nm(min_w), minor // 2))
        budget = _nm(max(0.6, min(1.5, 1.5 * class_width / MM)))
        return local_width, budget

    def _pad_key(pad):
        pos = pad.GetPosition()
        try:
            ref = pad.GetParentFootprint().GetReference()
        except Exception:                                # noqa: BLE001
            ref = ""
        return ref, str(pad.GetNumber()), pos.x, pos.y

    def _connected(source, target):
        target_key = _pad_key(target)
        try:
            return any(item.GetClass() == "PAD"
                       and _pad_key(item) == target_key
                       for item in board.GetConnectivity().GetConnectedItems(source))
        except Exception:                                # noqa: BLE001
            return False

    plane_ids = {board.GetLayerID(name) for name in plane_layers(board)}
    bridge_lays = [
        layer for layer in all_cu
        if layer != pcbnew.F_Cu and layer not in plane_ids
        and not any(role in board.GetLayerName(layer).upper()
                    for role in ("GND", "PWR"))]
    bridge_lays.sort(key=lambda layer: (
        0 if "SIG" in board.GetLayerName(layer).upper() else
        1 if board.GetLayerName(layer).upper().startswith("IN") else
        2 if layer == pcbnew.B_Cu else 3,
        layer))

    selected_nets = (None if include_nets is None
                     else {str(net) for net in include_nets})
    networks = linked = legs_added = vias_added = refused = ignored = 0
    detail = []
    for net, rows in sorted(pads_by_net.items()):
        if selected_nets is not None and net not in selected_nets:
            ignored += 1
            continue
        refs = sorted({ref for ref, _pad in rows})
        owners = [ref for ref in refs if ref.startswith("U")]
        followers = [ref for ref in refs if ref.startswith(("R", "C"))]
        spec = _spec(net)
        width_mm = float(spec.get("track_width") or min_w)
        if (_pairish(net) or len(refs) < 2 or len(refs) > int(max_refs)
                or len(owners) != 1 or len(followers) != len(refs) - 1
                or any(pad_count_by_ref.get(ref) != 2 for ref in followers)
                or width_mm >= float(min_power_width)):
            ignored += 1
            continue
        owner = owners[0]
        owner_pads = [pad for ref, pad in rows if ref == owner]
        follower_pads = {ref: [pad for row_ref, pad in rows if row_ref == ref]
                         for ref in followers}
        if not owner_pads or any(not pads for pads in follower_pads.values()):
            ignored += 1
            continue
        networks += 1
        board.BuildConnectivity()
        root_pad = owner_pads[0]
        connected_refs = {owner}
        remaining = set(followers)
        # Followers already electrically in the owner's cluster need no new
        # copper, but still become valid launch points for the MST growth.
        for ref in list(remaining):
            if any(_connected(root_pad, pad) for pad in follower_pads[ref]):
                connected_refs.add(ref)
                remaining.remove(ref)
        blocked_edges = set()
        while remaining:
            launches = [(ref, pad) for ref, pad in rows
                        if ref in connected_refs]
            candidates = []
            for target_ref in sorted(remaining):
                for target_pad in follower_pads[target_ref]:
                    target_pos = target_pad.GetPosition()
                    for source_ref, source_pad in launches:
                        edge = (_pad_key(source_pad), _pad_key(target_pad))
                        if edge in blocked_edges:
                            continue
                        common = _layers(source_pad) & _layers(target_pad)
                        if not common:
                            continue
                        source_pos = source_pad.GetPosition()
                        distance = _math.hypot(
                            target_pos.x - source_pos.x,
                            target_pos.y - source_pos.y) / MM
                        if 1e-9 < distance <= float(max_mm):
                            candidates.append((distance, target_ref,
                                               source_ref, source_pad,
                                               target_pad, sorted(common), edge))
            candidates.sort(key=lambda row: (
                row[0], row[1], row[2], _pad_key(row[3]), _pad_key(row[4])))
            selected = None
            class_width = _nm(width_mm)
            local_clearance = _nm(max(float(clearance),
                                      float(spec.get("clearance") or 0.0)))
            for (distance, target_ref, source_ref, source_pad, target_pad,
                 common, edge) in candidates:
                source_pos = source_pad.GetPosition()
                target_pos = target_pad.GetPosition()
                for layer in common:
                    path = _guarded_profiled_lastmile_legs(
                        board, source_pos, target_pos, class_width, layer,
                        local_clearance, target_pad.GetNetCode(),
                        lambda start, end, half: _edge_leg_clear(
                            board, start, end, half),
                        start_escape=_escape(source_pad, class_width),
                        end_escape=_escape(target_pad, class_width))
                    if path:
                        ops = [("trk", start, end, width, layer)
                               for start, end, width in path]
                        selected = (distance, target_ref, source_ref,
                                    target_pad.GetNetCode(), ops)
                        break
                if selected is None and bridge_lays:
                    ops = _lastmile_bridge(
                        board, (source_pos.x, source_pos.y),
                        _layers(source_pad),
                        (target_pos.x, target_pos.y), _layers(target_pad),
                        class_width, target_pad.GetNetCode(), bridge_lays,
                        local_clearance,
                        drill=float(spec.get("via_drill") or 0.3),
                        dia=float(spec.get("via_diameter") or 0.6),
                        seat_limit=48,
                        leg_ok=lambda start, end, half: _edge_leg_clear(
                            board, start, end, half),
                        start_escape=_escape(source_pad, class_width),
                        end_escape=_escape(target_pad, class_width))
                    if ops:
                        selected = (distance, target_ref, source_ref,
                                    target_pad.GetNetCode(), ops)
                if selected:
                    break
                blocked_edges.add(edge)
            if selected is None:
                refused += len(remaining)
                detail.append({"net": net, "owner": owner,
                               "followers": sorted(remaining),
                               "status": "refused", "reason": "no guarded MST edge"})
                break
            distance, target_ref, source_ref, net_code, ops = selected
            used_layers = set()
            for op in ops:
                if op[0] == "via":
                    _, at, drill, diameter = op
                    via = pcbnew.PCB_VIA(board)
                    via.SetPosition(at)
                    via.SetDrill(_nm(drill))
                    via.SetWidth(_nm(diameter))
                    via.SetNetCode(net_code)
                    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                    via.SetLocked(bool(lock))
                    board.Add(via)
                    vias_added += 1
                else:
                    _, start, end, width, layer = op
                    track = pcbnew.PCB_TRACK(board)
                    track.SetStart(start)
                    track.SetEnd(end)
                    track.SetWidth(width)
                    track.SetLayer(layer)
                    track.SetNetCode(net_code)
                    track.SetLocked(bool(lock))
                    board.Add(track)
                    used_layers.add(layer)
                    legs_added += 1
            linked += 1
            connected_refs.add(target_ref)
            remaining.remove(target_ref)
            board.BuildConnectivity()
            detail.append({"net": net, "owner": owner, "from": source_ref,
                           "to": target_ref, "distance_mm": round(distance, 3),
                           "layers": [board.GetLayerName(layer)
                                      for layer in sorted(used_layers)],
                           "legs": sum(op[0] == "trk" for op in ops),
                           "vias": sum(op[0] == "via" for op in ops),
                           "status": "linked"})

    return {"networks": networks, "linked": linked, "legs": legs_added,
            "vias": vias_added, "refused": refused, "ignored": ignored,
            "detail": detail}


def _ranked_bridge_seat_pairs(seats_a, seats_b, minimum_separation_nm):
    """Return deterministic qualified seat pairs, not just the first pair.

    Each seat is ``((x, y), ops)``. ``ops`` is empty when the endpoint is
    already present on the bridge layer; two non-empty rows each introduce a
    new barrel and therefore must satisfy the drill-to-drill separation.

    Rank the *complete* escape, not only the distance between its two vias.
    The old via-to-via-only ranking pulled both seats inward across connector
    pin fields because that made the inner-layer bridge artificially short,
    even when the two face-layer stubs became longer and crossed the breakout
    corridor.  Full copper length naturally prefers perpendicular dogbones at
    the two power banks and removes the same inward/diagonal bias on every
    footprint.
    """
    import math as _math

    def _stub_length(ops):
        total = 0.0
        for op in ops:
            if not op or op[0] != "trk" or len(op) < 3:
                continue
            start, end = op[1], op[2]
            try:
                total += _math.hypot(end.x - start.x, end.y - start.y)
            except AttributeError:
                # Synthetic unit-test rows may use opaque placeholders. They
                # carry no geometry and therefore contribute no route length.
                continue
        return total

    rows = []
    minimum2 = int(minimum_separation_nm) ** 2
    for ia, (pa, ops_a) in enumerate(seats_a):
        for ib, (pb, ops_b) in enumerate(seats_b):
            distance2 = ((int(pa[0]) - int(pb[0])) ** 2
                         + (int(pa[1]) - int(pb[1])) ** 2)
            if ops_a and ops_b and distance2 < minimum2:
                continue
            total_length = (_stub_length(ops_a) + _stub_length(ops_b)
                            + _math.sqrt(distance2))
            rows.append((total_length, distance2,
                         len(ops_a) + len(ops_b), ia, ib,
                         (pa, ops_a), (pb, ops_b)))
    rows.sort(key=lambda row: row[:5])
    return [(row[5], row[6]) for row in rows]


def _multilayer_maze_lastmile_ops(
        board, S, T, nc, layers, clearance_nm, leg_ok, *,
        width_for_layer, drill=0.3, dia=0.6,
        start_layers=None, end_layers=None, grid_mm=0.5,
        margin_mm=4.0, max_vias=2, foreign_cache=None):
    """Bounded deterministic via-enabled Manhattan maze.

    The ordinary last-mile maze is intentionally single-layer and the
    historical bridge chooses one bridge layer end to end.  Dense fixed pin
    fields can make every individual layer discontinuous while a legal route
    exists by changing layers inside the corridor.  Search that state space
    directly, but keep the operation tightly bounded:

    * non-plane signal layers are supplied explicitly by the caller;
    * every planar hop uses the existing exact edge/foreign-copper guards;
    * every transition is a through via checked on all enabled copper layers;
    * at most ``max_vias`` intermediate barrels are permitted; and
    * the raster window and path length are both finite.

    Returns ordinary last-mile operations or ``None``.  It never mutates the
    board; the caller retains transactional full-board admission authority.
    """

    import heapq as _heapq
    import itertools as _itertools

    layers = tuple(sorted(set(int(layer) for layer in layers)))
    if len(layers) < 2:
        return None
    start_layers = tuple(sorted(set(int(layer) for layer in
                                    (start_layers or layers)) & set(layers)))
    end_layers = set(int(layer) for layer in (end_layers or layers)) & \
        set(layers)
    if not start_layers or not end_layers:
        return None

    step = max(1, _nm(grid_mm))
    margin = max(step, _nm(margin_mm))
    x_lo = (min(S.x, T.x) - margin) // step * step
    x_hi = ((max(S.x, T.x) + margin + step - 1) // step) * step
    y_lo = (min(S.y, T.y) - margin) // step * step
    y_hi = ((max(S.y, T.y) + margin + step - 1) // step) * step
    xs = set(range(int(x_lo), int(x_hi + step), int(step)))
    ys = set(range(int(y_lo), int(y_hi + step), int(step)))
    xs.update((S.x, T.x)); ys.update((S.y, T.y))
    xs, ys = sorted(xs), sorted(ys)
    xi = {x: index for index, x in enumerate(xs)}
    yi = {y: index for index, y in enumerate(ys)}
    start_xy = (xi[S.x], yi[S.y])
    target_xy = (xi[T.x], yi[T.y])
    direct = abs(T.x - S.x) + abs(T.y - S.y)
    path_limit = direct + 4 * margin
    via_penalty = _nm(3.0)
    serial = _itertools.count()
    directions = ((1, 0), (-1, 0), (0, 1), (0, -1))
    layer_shapes = {
        layer: _foreign_shape_indexes(
            board, layer, {nc}, cache=foreign_cache)
        for layer in layers
    }
    hop_cache = {}
    via_cache = {}

    def _point(ix_, iy_):
        return pcbnew.VECTOR2I(xs[ix_], ys[iy_])

    def _heuristic(ix_, iy_):
        point = _point(ix_, iy_)
        return abs(T.x - point.x) + abs(T.y - point.y)

    def _hop_clear(layer, A, B):
        ends = sorted(((A.x, A.y), (B.x, B.y)))
        width = int(width_for_layer(layer))
        key = (layer, ends[0], ends[1], width)
        if key not in hop_cache:
            zones, copper = layer_shapes[layer]
            hop_cache[key] = bool(
                leg_ok(A, B, width // 2)
                and _snapshot_foreign_clear(
                    A, B, width, clearance_nm, zones, copper))
        return hop_cache[key]

    def _via_clear(point):
        key = (point.x, point.y)
        if key not in via_cache:
            via_cache[key] = bool(
                leg_ok(point, point, _nm(dia) // 2)
                and _via_spot_clear(
                    board, point, _nm(dia), clearance_nm, {nc},
                    drill_nm=_nm(drill), net_code=nc))
        return via_cache[key]

    # state = (x index, y index, layer, previous planar direction,
    #          intermediate via count).  Direction -1 is the launch state;
    # -2 follows a via and prevents zero-length via ping-pong.
    best = {}
    travelled = {}
    previous = {}
    heap = []
    for layer in start_layers:
        state = (start_xy[0], start_xy[1], layer, -1, 0)
        best[state] = 0.0
        travelled[state] = 0.0
        _heapq.heappush(
            heap, (_heuristic(*start_xy), 0.0, 0.0,
                   next(serial), state))

    final_state = None
    while heap:
        _rank, cost, distance, _serial, state = _heapq.heappop(heap)
        if cost != best.get(state) or distance != travelled.get(state):
            continue
        ix_, iy_, layer, old_direction, via_count = state
        if (ix_, iy_) == target_xy and layer in end_layers:
            final_state = state
            break
        point = _point(ix_, iy_)
        for direction, (dx, dy) in enumerate(directions):
            nx, ny = ix_ + dx, iy_ + dy
            if not (0 <= nx < len(xs) and 0 <= ny < len(ys)):
                continue
            target = _point(nx, ny)
            length = abs(target.x - point.x) + abs(target.y - point.y)
            new_distance = distance + length
            if length <= 0 or new_distance > path_limit:
                continue
            if not _hop_clear(layer, point, target):
                continue
            turn = 0 if old_direction in (-2, -1, direction) else _nm(0.2)
            new_cost = cost + length + turn
            new_state = (nx, ny, layer, direction, via_count)
            if new_cost >= best.get(new_state, float("inf")):
                continue
            best[new_state] = new_cost
            travelled[new_state] = new_distance
            previous[new_state] = (state, ("trk", point, target,
                                           int(width_for_layer(layer)),
                                           layer))
            _heapq.heappush(
                heap, (new_cost + _heuristic(nx, ny), new_cost,
                       new_distance, next(serial), new_state))

        if via_count >= max(0, int(max_vias)) or old_direction == -2:
            continue
        if not _via_clear(point):
            continue
        for target_layer in layers:
            if target_layer == layer:
                continue
            new_cost = cost + via_penalty
            new_state = (ix_, iy_, target_layer, -2, via_count + 1)
            if new_cost >= best.get(new_state, float("inf")):
                continue
            best[new_state] = new_cost
            travelled[new_state] = distance
            previous[new_state] = (
                state, ("via", point, drill, dia))
            _heapq.heappush(
                heap, (new_cost + _heuristic(ix_, iy_), new_cost,
                       distance, next(serial), new_state))

    if final_state is None:
        return None
    reversed_ops = []
    state = final_state
    while state not in {
            (start_xy[0], start_xy[1], layer, -1, 0)
            for layer in start_layers}:
        prior, operation = previous[state]
        reversed_ops.append(operation)
        state = prior
    reversed_ops.reverse()

    # Collapse collinear raster runs only when layer and qualified width match.
    operations = []
    for operation in reversed_ops:
        if operation[0] == "trk" and operations and \
                operations[-1][0] == "trk":
            _kind, A, B, width, layer = operations[-1]
            _, C, D, new_width, new_layer = operation
            same_axis = ((A.x == B.x == C.x == D.x)
                         or (A.y == B.y == C.y == D.y))
            if (B == C and same_axis and width == new_width
                    and layer == new_layer):
                operations[-1] = ("trk", A, D, width, layer)
                continue
        operations.append(operation)
    return operations


def _lastmile_bridge(board, A, al, B, bl, w, nc, bridge_lays, clearance_nm,
                     *, drill=0.3, dia=0.6, leg_ok=None,
                     start_escape=None, end_escape=None, seat_limit=1,
                     allow_maze=True, maze_margin_mm=2.0,
                     foreign_cache=None, width_for_layer=None):
    """Over-the-top closure for a dense-field gap: seat a through-via just off
    each end (skipped when the end already spans layers -- a via/THT anchor),
    run the bridge leg on an EMPTY non-plane layer (In2/B.Cu -- the F escape
    fabric is exactly what refused the face-layer route), using a canonical
    diagonal-plus-orthogonal path or Manhattan L. Every
    stub is foreign-guarded on its end's layer, every via spot all-layer
    guarded, every bridge leg guarded on the bridge layer, and every piece
    uses canonical 0/45/90-degree geometry and passes the caller's leg_ok
    bounds check (edge awareness). Returns the op
    list [("trk", S, T, w, lay) | ("via", at, drill, dia)] or None."""
    import math as _math
    if leg_ok is None:
        def leg_ok(_S, _T, _half):
            return True

    def _layer_width(layer):
        if width_for_layer is None:
            return int(w)
        return int(width_for_layer(layer))

    # existing via positions (ANY net): the foreign guard exempts same-net
    # vias, but a seat drilled hole-to-hole against one is a hole_clearance
    # hit regardless of net -- keep every synthesized seat 0.85mm off any barrel
    ex_vias = [(t.GetPosition().x, t.GetPosition().y)
               for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]

    def _seats(end, lays, lay_b, escape):
        ex, ey = end
        if lay_b in lays:
            return [(end, [])]                    # via/THT/track-on-bridge: direct
        lay_e = min(lays)
        stub_width = _layer_width(lay_e)
        seats = []
        # Prefer a zero-length escape when the selected fabrication contract
        # explicitly qualifies a same-net via-in-pad (POFV) or an ordinary
        # track-end barrel.  The centralized guard proves drill, annular ring,
        # complete SMD-land containment, assembly exclusions, and foreign
        # copper on every enabled layer.  If any part fails, this candidate is
        # absent and the historical offset dogbone sweep remains authoritative.
        origin = pcbnew.VECTOR2I(int(ex), int(ey))
        if (not any((origin.x - qx) ** 2 + (origin.y - qy) ** 2
                    < _nm(0.05) ** 2 for qx, qy in ex_vias)
                and leg_ok(origin, origin, _nm(dia) // 2)
                and _via_spot_clear(
                    board, origin, _nm(dia), clearance_nm, {nc},
                    drill_nm=_nm(drill), net_code=nc)):
            seats.append((end, [("via", origin)]))
            if len(seats) >= max(1, int(seat_limit)):
                return seats
        # Fine-pitch controllers often need to clear the full package body or
        # its first passive ring before a legal through-via can land.  Keep the
        # sweep bounded, but do not assume every viable seat is within 1.2 mm
        # of the pad centre.
        for off in (0.55, 0.8, 1.2, 1.6, 2.0, 2.5):
            for ang in (0, 90, 180, 270, 45, 135, 225, 315):
                a = _math.radians(ang)
                vx = int(ex + _math.cos(a) * _nm(off))
                vy = int(ey + _math.sin(a) * _nm(off))
                if any((vx - qx) ** 2 + (vy - qy) ** 2 < _nm(0.85) ** 2
                       for qx, qy in ex_vias):
                    continue
                S = pcbnew.VECTOR2I(int(ex), int(ey))
                V = pcbnew.VECTOR2I(vx, vy)
                if not leg_ok(V, V, _nm(dia) // 2):
                    continue
                stub_legs = _guarded_profiled_lastmile_legs(
                    board, S, V, stub_width, lay_e, clearance_nm, nc, leg_ok,
                    start_escape=escape, allow_maze=False,
                    foreign_cache=foreign_cache)
                if not stub_legs:
                    continue
                if not _via_spot_clear(board, V, _nm(dia), clearance_nm,
                                       {nc}, drill_nm=_nm(drill),
                                       net_code=nc):
                    continue
                stub_ops = [("trk", a, b, width, lay_e)
                            for a, b, width in stub_legs]
                seats.append(((vx, vy), stub_ops + [("via", V)]))
                if len(seats) >= max(1, int(seat_limit)):
                    return seats
        return seats

    for lay_b in bridge_lays:
        bridge_width = _layer_width(lay_b)
        seats_a = _seats(A, al, lay_b, start_escape)
        seats_b = _seats(B, bl, lay_b, end_escape)
        if not seats_a or not seats_b:
            continue
        for (pa, ops_a), (pb, ops_b) in _ranked_bridge_seat_pairs(
                seats_a, seats_b, _nm(0.85)):
            S = pcbnew.VECTOR2I(int(pa[0]), int(pa[1]))
            T = pcbnew.VECTOR2I(int(pb[0]), int(pb[1]))
            legs = _guarded_lastmile_legs(
                board, S, T, bridge_width, lay_b, clearance_nm, nc, leg_ok,
                allow_maze=allow_maze, maze_margin_mm=maze_margin_mm,
                foreign_cache=foreign_cache)
            if legs is None:
                continue
            ops = list(ops_a) + list(ops_b)
            for (ls_, le_) in legs:
                ops.append(("trk", ls_, le_, bridge_width, lay_b))
            # normalize the stub ops' width/layer tuple shape
            out = []
            for op in ops:
                if op[0] == "via":
                    out.append(("via", op[1], drill, dia))
                else:
                    out.append(op)
            return out

    # A fixed pin field may disconnect every individual bridge layer even
    # though a legal path exists by changing layers *inside* the corridor.
    # Reuse the proven endpoint dogbones, then run a bounded 3D maze over the
    # non-plane signal layers.  Through-via seats make all bridge layers
    # reachable at an endpoint; an endpoint already present on bridge copper
    # exposes only its actual layer set.
    if allow_maze and len(bridge_lays) >= 2:
        seat_layer = bridge_lays[0]
        seats_a = _seats(A, al, seat_layer, start_escape)
        seats_b = _seats(B, bl, seat_layer, end_escape)
        for (pa, ops_a), (pb, ops_b) in _ranked_bridge_seat_pairs(
                seats_a, seats_b, _nm(0.85)):
            start_has_via = any(op[0] == "via" for op in ops_a)
            end_has_via = any(op[0] == "via" for op in ops_b)
            start_access = (bridge_lays if start_has_via else
                            [layer for layer in bridge_lays if layer in al])
            end_access = (bridge_lays if end_has_via else
                          [layer for layer in bridge_lays if layer in bl])
            route_ops = _multilayer_maze_lastmile_ops(
                board,
                pcbnew.VECTOR2I(int(pa[0]), int(pa[1])),
                pcbnew.VECTOR2I(int(pb[0]), int(pb[1])),
                nc, bridge_lays, clearance_nm, leg_ok,
                width_for_layer=_layer_width,
                drill=drill, dia=dia,
                start_layers=start_access, end_layers=end_access,
                margin_mm=maze_margin_mm, max_vias=2,
                foreign_cache=foreign_cache)
            if route_ops is None:
                continue
            out = []
            for op in list(ops_a) + route_ops + list(ops_b):
                if op[0] == "via":
                    out.append(("via", op[1], drill, dia))
                else:
                    out.append(op)
            return out
    return None


def synthesize_lastmile(board, *, max_mm=5.0, min_w=0.25, clearance=0.25, cap=40,
                        netclass_resolver=None, include_nets=None,
                        exclude_nets=(), lock=False,
                        attempts_per_pair=4, maze_max_mm=5.0,
                        maze_margin_mm=2.0, terminal_refs_by_net=None):
    """LAST-MILE COMPLETER (2026-07-23, from the s120 residual measurement: 13 of
    30 unconnected gaps were <=5mm same-net pad/via/track gaps FR left unclosed in
    dense clusters -- including BOTH GND criticals, each a stranded pad sitting
    1-2mm from a plane-connected via). Post-route ADDITIVE closure, the pour/
    pickup doctrine: per net, cluster the copper through the REAL connectivity
    engine (GetConnectedItems -- transitive and zone-aware, so run this only on a
    FILLED board); for the closest anchor pair between two clusters that shares a
    copper layer and sits <= max_mm apart, lay ONE guarded canonical 0/45/90
    path (short diagonal+orthogonal first, Manhattan L as fallback) at the net's own
    established width (mode of its existing segments; a fat-class net gets its
    fat width, so the track_width DRC posture matches FR's own copper). Every leg
    is foreign-collision-guarded (_tap_foreign_clear, own-net exempt); refuses
    loudly, never forces. Cross-layer-only gaps are counted, not attempted.
    ``attempts_per_pair`` bounds how many nearest anchor combinations are
    collision-qualified for one component pair; increasing it changes only
    the refusal search budget, never the geometry guards. ``netclass_resolver``
    supplies the final project via dimensions.  Bridge
    seats MUST be collision-checked at those dimensions: validating the
    router-default 0.6/0.3 mm land and enlarging it later can turn a legal seat
    beside a fine-pitch pad into an unqualified via-in-pad.  Returns
    {closed, legs, refused, far, cross_layer}. ``maze_max_mm`` bounds the
    expensive 0.5 mm-grid detour search independently from ``max_mm``. Long
    eligible gaps still receive every canonical and via-bridge attempt, but
    cannot accidentally turn a last-mile pass into a whole-board maze search.
    ``include_nets`` limits work to an explicit net-name allowlist.
    ``exclude_nets`` is the stage-ownership boundary: a net already completed
    by a higher-priority topology compiler is never extended by this finishing
    pass, even if stale connectivity metadata still exposes more than one
    cluster after SES import or zone refill.
    ``terminal_refs_by_net`` optionally scopes a net's component graph to the
    named source/sink footprints and copper already connected to those pads;
    local-load leaves are not promoted into priority-route terminals.
    ``lock`` preserves pre-route closures in the global router. Both default
    to historical post-route behaviour."""
    from collections import Counter, defaultdict
    conn = board.GetConnectivity()
    all_cu = list(board.GetEnabledLayers().CuStack())
    # per-net item sweep -----------------------------------------------------
    def _item_key(kind, obj):
        """Proxy-stable identity that stays unique with cloned child UUIDs."""
        if kind == "pad":
            p = obj.GetPosition()
            try:
                ref = obj.GetParentFootprint().GetReference()
            except Exception:                           # noqa: BLE001
                ref = ""
            return (kind, ref, obj.GetNumber(), p.x, p.y)
        if kind == "via":
            p = obj.GetPosition()
            return (kind, obj.m_Uuid.AsString(), p.x, p.y)
        s, e = obj.GetStart(), obj.GetEnd()
        return (kind, obj.m_Uuid.AsString(), obj.GetLayer(),
                s.x, s.y, e.x, e.y, obj.GetWidth())

    def _connected_kind(obj):
        klass = obj.GetClass()
        if klass == "PAD":
            return "pad"
        if klass == "PCB_VIA":
            return "via"
        if klass in ("PCB_TRACK", "PCB_ARC"):
            return "trk"
        return None

    terminal_refs_by_net = {
        str(net): {str(ref) for ref in refs}
        for net, refs in (terminal_refs_by_net or {}).items()}
    authority_connected = defaultdict(set)
    if terminal_refs_by_net:
        for fp in board.GetFootprints():
            ref = str(fp.GetReference() or "")
            for pad in fp.Pads():
                net_name = str(pad.GetNetname() or "")
                if ref not in terminal_refs_by_net.get(net_name, set()):
                    continue
                authority_connected[net_name].add(_item_key("pad", pad))
                try:
                    for item in conn.GetConnectedItems(pad):
                        kind = _connected_kind(item)
                        if (kind is not None
                                and item.GetNetCode() == pad.GetNetCode()):
                            authority_connected[net_name].add(
                                _item_key(kind, item))
                except Exception:                       # noqa: BLE001
                    pass

    by_net = defaultdict(list)                    # nc -> [(identity, kind, obj)]
    for fp in board.GetFootprints():
        ref = str(fp.GetReference() or "")
        for p in fp.Pads():
            if p.GetNetCode() > 0:
                selected = terminal_refs_by_net.get(str(p.GetNetname() or ""))
                if selected is not None and ref not in selected:
                    continue
                by_net[p.GetNetCode()].append((_item_key("pad", p), "pad", p))
    for t in board.GetTracks():
        if t.GetNetCode() > 0:
            k = "via" if t.GetClass() == "PCB_VIA" else "trk"
            key = _item_key(k, t)
            selected = terminal_refs_by_net.get(str(t.GetNetname() or ""))
            if (selected is not None
                    and key not in authority_connected.get(
                        str(t.GetNetname() or ""), set())):
                continue
            by_net[t.GetNetCode()].append((key, k, t))
    width_mode = {}
    try:
        import cec_current_topology
        current_domains = cec_current_topology.board_current_domains(board)
    except Exception:                                  # noqa: BLE001
        current_domains = {}
    for nc_, items in by_net.items():
        ws = Counter(o.GetWidth() for u, k, o in items if k == "trk")
        width_mode[nc_] = ws.most_common(1)[0][0] if ws else _nm(min_w)
    net_names = {code: info.GetNetname()
                 for code, info in board.GetNetInfo().NetsByNetcode().items()}
    include = None if include_nets is None else {
        str(net) for net in include_nets}
    exclude = {str(net) for net in (exclude_nets or ())}

    def _contract_width(nc_, layer=None):
        spec = (netclass_resolver(net_names.get(nc_, ""))
                if netclass_resolver is not None else {}) or {}
        name = (net_names.get(nc_, "") or "").upper()
        pairish = (bool(re.search(r"_(?:P|N)$", name))
                   or name.endswith(("CAN_H", "CAN_L", "CAN_H_BUS",
                                      "CAN_L_BUS"))
                   or "USB_D" in name)
        width = float((spec.get("diff_pair_width") if pairish else None)
                      or spec.get("track_width") or 0)
        if layer is not None:
            by_layer = spec.get("track_width_by_layer_mm") or {}
            layer_name = _fab.COPPER_LAYER_IDS.get(
                int(layer), board.GetLayerName(int(layer)))
            width = max(width, float(by_layer.get(layer_name) or 0.0))
        # Aggregate source-to-sink ampacity is owned by the priority power
        # compiler and its independent rated-subgraph signoff. Last-mile is a
        # terminal completion pass: applying the complete net current to every
        # capacitor/LED/logic spur makes a 4.4 mm "leaf" on a 0.56 mm land and
        # recreates board-spanning slabs. Netclass remains the local branch
        # contract; an undersized aggregate path still fails signoff.
        return spec, max(width_mode.get(nc_, _nm(min_w)), _nm(width))

    # Existing local pickup stubs can outnumber class-width trunks.  The width
    # used for collision qualification must still be the final project contract;
    # only the bounded endpoint portions below may use a pin escape width.
    for _nc in by_net:
        _spec, width_mode[_nc] = _contract_width(_nc)

    def _pin_escape(kind, obj, class_width):
        """Return the same bounded fine-pitch escape used by normalization."""
        if kind != "pad":
            return None
        try:
            if int(obj.GetAttribute()) != int(pcbnew.PAD_ATTRIB_SMD):
                return None
        except Exception:                                  # noqa: BLE001
            return None
        minor = min(obj.GetSize().x, obj.GetSize().y)
        if minor >= class_width:
            return None
        local_width = min(class_width, max(_nm(min_w), minor // 2))
        class_mm = class_width / MM
        budget = _nm(max(0.6, min(1.5, 1.5 * class_mm)))
        return (local_width, budget)

    def _anchor_owner(kind, obj):
        owner = {"kind": kind, "net": obj.GetNetname() or ""}
        if kind == "pad":
            try:
                owner.update({
                    "ref": obj.GetParentFootprint().GetReference(),
                    "pad": str(obj.GetNumber()),
                })
            except Exception:                           # noqa: BLE001
                pass
        else:
            try:
                owner["uuid"] = obj.m_Uuid.AsString()
            except Exception:                           # noqa: BLE001
                pass
        return owner

    def _anchors(kind, obj, class_width):
        """[(x, y, layers, escape, owner)] -- connectable item points."""
        owner = _anchor_owner(kind, obj)
        if kind == "pad":
            ls = frozenset(l for l in obj.GetLayerSet().CuStack() if l in all_cu)
            p = obj.GetPosition()
            return [(p.x, p.y, ls, _pin_escape(kind, obj, class_width), owner)]
        if kind == "via":
            p = obj.GetPosition()
            return [(p.x, p.y, frozenset(all_cu), None, owner)]
        s, e = obj.GetStart(), obj.GetEnd()
        ls = frozenset((obj.GetLayer(),))
        return [(s.x, s.y, ls, None, owner),
                (e.x, e.y, ls, None, owner)]

    # plane layers carry the solid fills -- a foreign lastmile track there would
    # slot the plane (gnd-plane-continuity); exclude them from candidate layers
    plane_ids = set()
    for _pn in plane_layers(board):
        _pl = board.GetLayerID(_pn)
        if _pl >= 0:
            plane_ids.add(_pl)

    def _lm_leg_ok(S, T, half_nm):
        return _edge_leg_clear(board, S, T, half_nm)

    # KELVIN EXCLUSION: sense nets connect ONLY through their authored taps at
    # the shunt inner edge -- an arbitrary lastmile closure on a shared
    # force+sense net could fake a tap through trunk copper (the exact class
    # the kelvin gate exists to kill). Skip every kelvin-pair net.
    kelvin_nc = set()
    for _hi, _lo in _board_kelvin_pairs(board):
        for _kn in (_hi, _lo):
            _kc = board.GetNetcodeFromNetname(_kn)
            if _kc > 0:
                kelvin_nc.add(_kc)

    n_closed = n_legs = n_ref = n_far = n_cross = 0
    closed_details, refused_details, far_details = [], [], []
    endpoint_neckdowns = []
    refused_seen = set()
    for nc_, items in by_net.items():
        if (len(items) < 2 or nc_ in kelvin_nc
                or net_names.get(nc_, "") in exclude
                or (include is not None
                    and net_names.get(nc_, "") not in include)):
            continue
        # Transitive clusters via the engine. SWIG re-proxies connected items,
        # so Python object identity is unstable; raw child UUID is also unsafe
        # because generated footprint clones can share it. Use the composite
        # physical identity above, which remains stable across proxies.
        uu = {u: (k, o) for u, k, o in items}
        seen, clusters = set(), []
        for u, k, o in items:
            if u in seen:
                continue
            members = [(u, k, o)]
            seen.add(u)
            try:
                for ci in conn.GetConnectedItems(o):
                    if ci.GetNetCode() != nc_:
                        continue
                    ck = _connected_kind(ci)
                    if ck is None:
                        continue
                    cu = _item_key(ck, ci)
                    if cu in uu and cu not in seen:
                        seen.add(cu)
                        members.append((cu, uu[cu][0], uu[cu][1]))
            except Exception:                       # noqa: BLE001 -- engine quirk: solo cluster
                pass
            anc = []
            for mu, mk, mo in members:
                anc.extend(_anchors(mk, mo, width_mode[nc_]))
            clusters.append(anc)
        if len(clusters) < 2:
            continue
        # union-find over cluster indices; ALL eligible pairs ascending by
        # distance, bounded retries per cluster pair so a refused closest
        # anchor pair still gets its 2nd/3rd-nearest chance (v1 merged on
        # refusal and measurably under-closed: 4 of ~13 on s120)
        root = list(range(len(clusters)))

        def _find(i):
            while root[i] != i:
                root[i] = root[root[i]]
                i = root[i]
            return i

        pairs = []
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                for (ax, ay, al, ae, ao) in clusters[i]:
                    for (bx, by_, bl, be, bo) in clusters[j]:
                        d = ((ax - bx) ** 2 + (ay - by_) ** 2) ** 0.5 / 1e6
                        if d <= max_mm:
                            com = (al & bl) - plane_ids
                            pairs.append((d, i, j, (ax, ay), (bx, by_),
                                          com, al, bl, ae, be, ao, bo))
        if not pairs:
            n_far += len(clusters) - 1
            nearest = None
            for i in range(len(clusters)):
                for j in range(i + 1, len(clusters)):
                    for ax, ay, _al, _ae, _ao in clusters[i]:
                        for bx, by_, _bl, _be, _bo in clusters[j]:
                            distance = math.hypot(ax - bx, ay - by_) / MM
                            nearest = distance if nearest is None else min(
                                nearest, distance)
            far_details.append({
                "net": net_names.get(nc_, ""),
                "clusters": len(clusters),
                "nearest_gap_mm": (round(nearest, 4)
                                   if nearest is not None else None),
                "search_limit_mm": float(max_mm),
                "reason": "outside_completion_distance_budget",
            })
            continue
        pairs.sort(key=lambda p: p[0])
        bridge_lays = sorted((l for l in all_cu
                              if l not in plane_ids and l != pcbnew.F_Cu),
                             reverse=True)
        # The board does not mutate until a closure for this net is accepted.
        # Reuse exact per-layer foreign-copper snapshots across its canonical,
        # seat, and maze attempts.  A successful closure adds only own-net
        # copper, which is exempt for the remainder of this net.  The cache is
        # deliberately per-net so copper added for one net is visible when the
        # next net begins.
        foreign_cache = {}
        tries = {}
        for d, i, j, A, B, com, al, bl, ae, be, ao, bo in pairs:
            if n_closed >= cap:
                break
            ri, rj = _find(i), _find(j)
            if ri == rj:
                continue
            key = (min(ri, rj), max(ri, rj))
            if tries.get(key, 0) >= max(1, int(attempts_per_pair)):
                continue
            tries[key] = tries.get(key, 0) + 1
            spec, w = _contract_width(nc_)
            S = pcbnew.VECTOR2I(int(A[0]), int(A[1]))
            T = pcbnew.VECTOR2I(int(B[0]), int(B[1]))
            ops = None
            allow_maze = d <= max(0.0, float(maze_max_mm))
            # Same-layer canonical 0/45/90 path first, emptier layers before
            # congested F. Never introduce arbitrary-angle copper here: raw FR
            # already emits octilinear routes, and a free-angle shortcut creates
            # hard-to-read diagonal stubs and acute copper joins.
            for lay in sorted(com, reverse=True):
                spec, w = _contract_width(nc_, lay)
                legs = _guarded_profiled_lastmile_legs(
                    board, S, T, w, lay, _nm(clearance), nc_, _lm_leg_ok,
                    start_escape=ae, end_escape=be,
                    allow_maze=allow_maze,
                    maze_margin_mm=maze_margin_mm,
                    foreign_cache=foreign_cache)
                if legs:
                    ops = [("trk", a, b, width, lay)
                           for a, b, width in legs]
                    break
            if ops is None:
                # over-the-top: stub+via each end, bridge on an empty layer
                bridge_dia = float(spec.get("via_diameter") or 0.6)
                bridge_drill = float(spec.get("via_drill") or 0.3)
                ops = _lastmile_bridge(board, A, al, B, bl, w, nc_,
                                       bridge_lays, _nm(clearance),
                                       drill=bridge_drill, dia=bridge_dia,
                                       leg_ok=_lm_leg_ok,
                                       start_escape=ae, end_escape=be,
                                       seat_limit=max(
                                           1, int(attempts_per_pair)),
                                       allow_maze=allow_maze,
                                       maze_margin_mm=maze_margin_mm,
                                       foreign_cache=foreign_cache,
                                       width_for_layer=lambda layer: (
                                           _contract_width(nc_, layer)[1]))
            if ops is None:
                n_ref += 1
                refusal_key = (net_names.get(nc_, ""), min(ri, rj),
                               max(ri, rj))
                if refusal_key not in refused_seen:
                    refused_seen.add(refusal_key)
                    certificate = _lastmile_refusal_certificate(
                        board, S, T, w, _nm(clearance), nc_,
                        sorted(set(com) | set(bridge_lays)),
                        endpoint_a=ao, endpoint_b=bo,
                        maze_searched=allow_maze,
                        maze_margin_mm=maze_margin_mm,
                        attempts_per_pair=attempts_per_pair)
                    refused_details.append({
                        "net": net_names.get(nc_, ""),
                        "distance_mm": round(float(d), 4),
                        "same_layer_candidates": len(com),
                        "maze_searched": bool(allow_maze),
                        "reason": "no_exact_clear_canonical_via_or_maze_path",
                        "certificate": certificate,
                    })
                continue
            added_tracks = []
            for op in ops:
                if op[0] == "via":
                    _, at, dr_, di_ = op
                    v = pcbnew.PCB_VIA(board)
                    v.SetPosition(at)
                    v.SetDrill(_nm(dr_))
                    v.SetWidth(_nm(di_))
                    v.SetNetCode(nc_)
                    v.SetLocked(bool(lock))
                    board.Add(v)
                else:
                    _, ls_, le_, w_, lay_ = op
                    tr = pcbnew.PCB_TRACK(board)
                    tr.SetStart(ls_)
                    tr.SetEnd(le_)
                    tr.SetWidth(w_)
                    tr.SetLayer(lay_)
                    tr.SetNetCode(nc_)
                    tr.SetLocked(bool(lock))
                    board.Add(tr)
                    added_tracks.append(tr)
                    n_legs += 1
            # Compare every generated leg with the final contract on its own
            # layer.  Only the pad-local tapered prefix is grouped; the full-
            # width throat and ordinary class-width route remain unqualified.
            per_width = {}
            for track in added_tracks:
                full_width = _contract_width(nc_, track.GetLayer())[1]
                if track.GetWidth() < full_width:
                    per_width.setdefault(full_width, []).append(track)
            closure_neckdowns = []
            for full_width, tracks in per_width.items():
                evidence = group_endpoint_neckdowns(
                    board, tracks, full_width)
                if evidence:
                    closure_neckdowns.append(evidence)
                    endpoint_neckdowns.extend(tracks)
            n_closed += 1
            detail = {
                "net": net_names.get(nc_, ""),
                "distance_mm": round(float(d), 4),
                "legs": sum(1 for op in ops if op[0] != "via"),
                "vias": sum(1 for op in ops if op[0] == "via"),
                "maze_eligible": bool(allow_maze),
            }
            if closure_neckdowns:
                detail["endpoint_neckdown"] = {
                    "group": ENDPOINT_NECKDOWN_GROUP,
                    "tracks": sum(row["tracks"] for row in closure_neckdowns),
                    "min_width_mm": min(
                        row["min_width_mm"] for row in closure_neckdowns),
                    "max_length_mm": max(
                        row["max_length_mm"] for row in closure_neckdowns),
                }
            closed_details.append(detail)
            root[_find(j)] = _find(i)
    endpoint_summary = None
    if endpoint_neckdowns:
        endpoint_summary = {
            "group": ENDPOINT_NECKDOWN_GROUP,
            "tracks": len(endpoint_neckdowns),
            "min_width_mm": round(
                min(item.GetWidth() for item in endpoint_neckdowns) / MM, 3),
            "max_length_mm": round(
                max(item.GetLength() for item in endpoint_neckdowns) / MM, 3),
        }
    return {"closed": n_closed, "legs": n_legs, "refused": n_ref,
            "far": n_far, "cross_layer": n_cross,
            "endpoint_neckdown": endpoint_summary,
            "aggregate_current_domains": {
                net: {
                    "amps": domain.get("amps"),
                    "authority_refs": list(domain.get("authority_refs") or ()),
                }
                for net, domain in sorted(current_domains.items())
                if domain.get("complete")},
            "closed_details": closed_details[:64],
            "refused_details": refused_details[:64],
            "far_details": far_details[:64]}


def _ordinary_final_completion_nets(board, netclass_resolver):
    """Low-risk nets eligible for exhaustive post-router completion.

    Differential/high-speed, Kelvin/sense, clock, ground, and power-width nets
    remain owned by their specialized topology and geometry gates. Ordinary
    GPIO/status/soft-start/LED/control nets may use the deterministic exact
    maze because leaving one as a ratline is never an acceptable final board.
    """
    kelvin = {net for pair in _board_kelvin_pairs(board) for net in pair}
    out = []
    for _code, info in board.GetNetInfo().NetsByNetcode().items():
        name = info.GetNetname() or ""
        if not name or name in kelvin:
            continue
        upper = name.upper()
        if upper.startswith("UNCONNECTED-"):
            continue
        spec = (netclass_resolver(name) or {})
        width = float(spec.get("track_width") or 0.0)
        # KiCad stores non-zero *default values* for the differential-pair
        # width/gap fields on every netclass, including the ordinary Default
        # class.  Their presence therefore does not mean this particular net
        # is a member of a pair.  Classify from the net identity here (the
        # design-principle grader independently verifies declared pairs).
        pairish = (bool(re.search(r"_(?:P|N)$", upper))
                   or upper.endswith(("CAN_H", "CAN_L", "CAN_H_BUS",
                                      "CAN_L_BUS"))
                   or "USB_D" in upper or "PCIE" in upper
                   or "SGMII" in upper)
        ground = (upper == "GND" or upper.endswith("/GND")
                  or upper.startswith("GND_"))
        power = (ground or upper.startswith("+")
                 or width >= 0.5
                 or any(token in upper for token in (
                     "VBUS", "VCC", "VDD", "_5V", "_3V3", "_12V")))
        sensitive = ("SENSE" in upper or "KELVIN" in upper
                     or "CAN_MID" in upper
                     or "XTAL" in upper or "CLOCK" in upper
                     or upper.endswith(("_CLK", "_MCLK")))
        if not pairish and not power and not sensitive:
            out.append(name)
    return tuple(sorted(set(out)))


def synthesize_pipeline_zone_island_bridges(
        board, *, netclass_resolver=None, max_gap_mm=5.0,
        sample_radius_mm=1.0, sample_step_mm=0.2, attempt_cap=32,
        min_power_width=0.5, lock=False):
    """Join split filled islands of one pipeline-owned power zone.

    A shaped over-under zone can fill as two legitimate copper islands when a
    foreign obstacle clips its narrow elbow.  The pre-fill pour-bond planner
    sees one zone dictionary and can bond each island to a *different* layer
    segment, while KiCad still has two disconnected electrical components.
    Object-level connectivity masks this because both islands share one ZONE
    object.  Inspect the filled polygon outlines directly and add a guarded
    same-layer class-width bridge only when:

    * the zone is pipeline-owned and its net is power-width;
    * two filled outlines are at most ``max_gap_mm`` apart; and
    * an exact foreign-copper/edge-qualified 0/45/90 route exists.

    The bounded samples stay within one millimetre of the two nearest outline
    boundaries.  This is an island repair, not a general zone router; ordinary
    user zones, planes, signals, and distant islands are untouched.
    """
    import math as _math

    def _spec(net):
        if netclass_resolver is not None:
            return dict(netclass_resolver(net) or {})
        try:
            klass = board.GetNetInfo().GetNetItem(net).GetNetClassSlow()
            return {"track_width": klass.GetTrackWidth() / MM,
                    "clearance": klass.GetClearance() / MM}
        except Exception:                              # noqa: BLE001
            return {}

    added = legs_added = refused = ignored = 0
    detail = []
    for zone in board.Zones():
        name = str(zone.GetZoneName() or "")
        if (zone.GetIsRuleArea()
                or not name.startswith(PIPELINE_POUR_PREFIXES)):
            continue
        layers = list(zone.GetLayerSet().CuStack())
        if len(layers) != 1 or not zone.IsFilled():
            ignored += 1
            continue
        layer = layers[0]
        polys = zone.GetFilledPolysList(layer)
        count = int(polys.OutlineCount())
        if count < 2:
            continue
        spec = _spec(zone.GetNetname())
        width_mm = float(spec.get("track_width") or 0.0)
        if width_mm < float(min_power_width):
            ignored += count - 1
            continue
        clearance_nm = _nm(max(0.20, float(spec.get("clearance") or 0.0)))
        width_nm = _nm(width_mm)
        outlines = [polys.COutline(index) for index in range(count)]
        root = list(range(count))

        def _find(index):
            while root[index] != index:
                root[index] = root[root[index]]
                index = root[index]
            return index

        edge_rows = []
        for i in range(count):
            for j in range(i + 1, count):
                a = pcbnew.VECTOR2I()
                b = pcbnew.VECTOR2I()
                try:
                    if not outlines[i].NearestPoints(outlines[j], a, b):
                        continue
                except Exception:                       # noqa: BLE001
                    continue
                gap = _math.hypot(a.x - b.x, a.y - b.y) / MM
                if gap <= float(max_gap_mm):
                    edge_rows.append((gap, i, j, a, b))
        edge_rows.sort(key=lambda row: (row[0], row[1], row[2]))

        for gap, i, j, nearest_a, nearest_b in edge_rows:
            ri, rj = _find(i), _find(j)
            if ri == rj:
                continue

            def _samples(outline, near):
                radius = float(sample_radius_mm)
                step = max(0.05, float(sample_step_mm))
                n = int(_math.ceil(radius / step))
                rows = []
                for ix in range(-n, n + 1):
                    for iy in range(-n, n + 1):
                        if _math.hypot(ix * step, iy * step) > radius + 1e-9:
                            continue
                        point = pcbnew.VECTOR2I(
                            int(round(near.x + _nm(ix * step))),
                            int(round(near.y + _nm(iy * step))))
                        try:
                            inside = outline.PointInside(point)
                        except Exception:                # noqa: BLE001
                            inside = False
                        if inside:
                            rows.append(point)
                return rows

            samples_a = _samples(outlines[i], nearest_a)
            samples_b = _samples(outlines[j], nearest_b)
            pairs = sorted(
                ((_math.hypot(a.x - b.x, a.y - b.y), a, b)
                 for a in samples_a for b in samples_b
                 if _math.hypot(a.x - b.x, a.y - b.y)
                 <= _nm(float(max_gap_mm))),
                key=lambda row: (row[0], row[1].x, row[1].y,
                                 row[2].x, row[2].y))
            chosen = None
            for _distance, start, end in pairs[:max(1, int(attempt_cap))]:
                legs = _guarded_profiled_lastmile_legs(
                    board, start, end, width_nm, layer, clearance_nm,
                    zone.GetNetCode(),
                    lambda a, b, half: _edge_leg_clear(board, a, b, half))
                if legs:
                    chosen = legs
                    break
            if chosen is None:
                refused += 1
                detail.append({"net": zone.GetNetname(), "layer":
                               board.GetLayerName(layer),
                               "islands": [i, j], "gap_mm": round(gap, 3),
                               "status": "refused"})
                continue
            for start, end, width in chosen:
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(start)
                track.SetEnd(end)
                track.SetWidth(width)
                track.SetLayer(layer)
                track.SetNetCode(zone.GetNetCode())
                track.SetLocked(bool(lock))
                board.Add(track)
                legs_added += 1
            root[_find(j)] = _find(i)
            added += 1
            detail.append({"net": zone.GetNetname(), "layer":
                           board.GetLayerName(layer), "islands": [i, j],
                           "gap_mm": round(gap, 3), "legs": len(chosen),
                           "status": "linked"})
    return {"added": added, "legs": legs_added, "refused": refused,
            "ignored": ignored, "detail": detail}


def repair_post_cleanup_zone_islands(board_path, *, netclass_resolver=None):
    """Repair split pipeline pours on the actual post-cleanup artifact.

    The first island pass in :func:`import_ses` necessarily runs before pour
    termination and the fresh-load cleanup/reaper.  Those stages refill or
    remove copper and can therefore split a previously single-outline shaped
    rail.  Re-open the deliverable after every zone-mutating stage has
    finished, apply the same guarded island rule to those final filled
    polygons, then refill and save only when a bridge was added.

    This deliberately remains a narrow power-zone repair: the underlying
    helper ignores hand-authored zones, signal-width nets, and gaps without an
    edge- and foreign-copper-qualified octilinear path.
    """
    board = pcbnew.LoadBoard(board_path)
    resolver = (netclass_resolver
                if netclass_resolver is not None
                else _project_netclass_resolver(board_path))
    report = synthesize_pipeline_zone_island_bridges(
        board, netclass_resolver=resolver)
    if report["added"]:
        for zone in board.Zones():
            zone.UnFill()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        pcbnew.SaveBoard(board_path, board)
    return report


def derive_via_field(board_path, *, per_net=10, drill=0.3, dia=0.6, pitch=1.2, keepout=0.5,
                     clearance=0.2, kelvin_pairs=None, board=None):
    """Auto-derive a PARALLEL VIA FIELD for each high-current cable net at its vertical-transition
    region (the §6.7/OQ-10 'more parallel vias' fix: more barrels in parallel -> less current per via).
    A grid of up to `per_net` same-net through-vias in the net's heavy-pad bbox, skipping any grid point
    that is: within keepout of ANY pad; within (clearance + via radius) of a FOREIGN-net track; within
    (clearance + radii) of an EXISTING via (no stacked/coincident drills); or over a decorative LOGO.
    So the field lands in the OPEN same-net pour channel and shorts nothing. To CONNECT (not dangle) the
    through-vias need same-net copper on BOTH spanned layers -- pair this with a B.Cu mirror pour (the
    caller lays one). Returns [{net, positions:[(x,y)...], drill, dia}]; self-gating -> [] if no cable net."""
    from collections import defaultdict
    board = board if board is not None else pcbnew.LoadBoard(board_path)
    names = {n.GetNetname() for n in board.GetNetInfo().NetsByNetcode().values() if n.GetNetname()}
    if kelvin_pairs is None:
        kelvin_pairs = _board_kelvin_pairs(board)
    pads_by_net = defaultdict(list)
    padcount = defaultdict(int)
    all_pads = []                          # (net, x, y, half_extent_mm)
    segs = []                              # (net, ax, ay, bx, by, halfwidth) -- every track
    ex_vias = []                           # (x, y, radius) -- existing vias
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            # KiCad-10: PCB_VIA.GetWidth() with NO layer arg asserts (modal
            # Debug Alert on Windows debug builds) -- the normalize_via_annular
            # fix, applied here too (codex stack-audit 2026-07-19 #12)
            p = t.GetPosition(); ex_vias.append((p.x / MM, p.y / MM,
                                                 t.GetWidth(t.TopLayer()) / MM / 2.0))
        elif t.Type() == pcbnew.PCB_TRACE_T:
            s, e = t.GetStart(), t.GetEnd()
            segs.append((t.GetNetname(), s.x / MM, s.y / MM, e.x / MM, e.y / MM, t.GetWidth() / MM / 2.0))
    logo_rects = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref.upper().startswith("LOGO"):
            bb = fp.GetBoundingBox()
            logo_rects.append((bb.GetLeft() / MM, bb.GetTop() / MM, bb.GetRight() / MM, bb.GetBottom() / MM))
        for p in fp.Pads():
            padcount[ref] += 1
            pos = p.GetPosition(); sz = p.GetSize()
            all_pads.append((p.GetNetname(), pos.x / MM, pos.y / MM,
                             max(sz.x, sz.y) / MM / 2.0))
            if p.GetNetname():
                pads_by_net[p.GetNetname()].append((ref, p))

    vr = dia / 2.0
    fields = []
    for hi, lo in kelvin_pairs:
        refs_hi = {ref for ref, _ in pads_by_net.get(hi, [])}
        refs_lo = {ref for ref, _ in pads_by_net.get(lo, [])}
        shunt_refs = {ref for ref in (refs_hi & refs_lo) if padcount.get(ref, 0) == 2}
        for net in (hi, lo):
            entries = pads_by_net.get(net, [])
            if not any(p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH for _, p in entries):
                continue                   # not a cable high-current net
            heavy = [(p.GetPosition().x / MM, p.GetPosition().y / MM) for ref, p in entries
                     if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH or ref in shunt_refs]
            if not heavy:
                continue
            xs = [x for x, _ in heavy]; ys = [y for _, y in heavy]
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            nx = max(1, int((x1 - x0) / pitch)); ny = max(1, int((y1 - y0) / pitch))
            pos = []
            for ix in range(nx + 1):
                for iy in range(ny + 1):
                    if len(pos) >= per_net:
                        break
                    x, y = x0 + ix * pitch, y0 + iy * pitch
                    at = pcbnew.VECTOR2I(_nm(x), _nm(y))
                    nc = board.GetNetcodeFromNetname(net)
                    blocking, _allowed = _fab.via_at_pad_conflicts(
                        board, at, _nm(dia), _nm(drill), nc)
                    if blocking is not None:
                        continue           # short, THT overlap, or unqualified via-in-pad
                    if any(pnet != net and
                           math.hypot(x - px, y - py) < pr + keepout + vr
                           for (pnet, px, py, pr) in all_pads):
                        continue           # foreign pad clearance, beyond collision
                    if any(snet != net and _pt_seg_dist(x, y, ax, ay, bx, by) < hw + clearance + vr
                           for (snet, ax, ay, bx, by, hw) in segs):
                        continue           # too close to a FOREIGN-net track
                    if any(math.hypot(x - vx, y - vy) < r + vr + clearance for (vx, vy, r) in ex_vias):
                        continue           # would stack on / crowd an existing via
                    if any(lx - keepout <= x <= rx + keepout and ty - keepout <= y <= by_ + keepout
                           for (lx, ty, rx, by_) in logo_rects):
                        continue           # over the decorative LOGO
                    pos.append((round(x, 3), round(y, 3)))
                if len(pos) >= per_net:
                    break
            if pos:
                fields.append({"net": net, "positions": pos, "drill": drill, "dia": dia})
    return fields


def add_via_field(board, fields):
    """Place the parallel via field from derive_via_field as REAL same-net F.Cu<->B.Cu through-vias
    (additive, like add_power_pours). The GND inner plane antipads around each foreign-net via, so no
    short. Returns the added PCB_VIA objects. Re-fill zones after calling if you poured."""
    added = []
    skipped_pad = 0
    f_cu, b_cu = board.GetLayerID("F.Cu"), board.GetLayerID("B.Cu")
    for f in fields:
        nc = board.GetNetcodeFromNetname(f["net"])
        if nc <= 0:
            raise KeyError(f"cec_fr.add_via_field: net {f['net']!r} not found on board")
        for (x, y) in f["positions"]:
            at = pcbnew.VECTOR2I(_nm(x), _nm(y))
            # assembly-class via-in-pad exclusion (owner ruling 2026-07-25)
            if _via_pad_excluded(board, at, _nm(f.get("dia", 0.6)),
                                 _nm(f.get("drill", 0.3)), nc):
                skipped_pad += 1
                continue
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(at)
            v.SetDrill(_nm(f.get("drill", 0.3)))
            v.SetWidth(_nm(f.get("dia", 0.6)))
            v.SetNetCode(nc)
            v.SetLayerPair(f_cu, b_cu)
            board.Add(v)
            added.append(v)
    if skipped_pad:
        print(f"[cec_fr] add_via_field: {skipped_pad} via(s) REFUSED "
              "in-pad (assembly-class exclusion, owner ruling 2026-07-25)",
              file=sys.stderr)
    return added


def add_overunder_vias(board, via_list, *, drill=0.5, dia=0.9):
    """Lay the v2 over-under pour bridge vias (cec_slab_pour.
    synthesize_overunder_pours' via_list) as real same-net through vias --
    additive, same pattern as add_power_pours/add_via_field. Always a
    through via (F.Cu<->B.Cu): on this platform's 4-layer stackup that
    barrel makes electrical contact with same-net copper on In1/In2 too
    wherever it passes through it, matching add_via_field's own convention
    (no blind/buried vias are used anywhere on this platform).

    Unfills every zone before adding a barrel.  This is not cosmetic: a stale
    filled GND plane has copper at a newly planned through-via position because
    its antipad did not exist at the last fill.  KiCad's save-time connectivity
    rebuild then reassigns that explicit rail via to GND.  All over-under
    callers already refill after laying their final zones; clearing the stale
    geometry here preserves the declared via net across save/reload and lets
    that later fill cut the correct antipad.

    Re-checks a diameter-aware any-net barrel ledger against the board's
    CURRENT via set: the two copper radii plus 0.20mm clearance (defense in
    depth -- synthesize_overunder_pours already
    ledger-filters at generation time against this same board object, so
    this is a second, cheap pass, not the first one). Each *via_list* entry
    is {"net", "x_mm", "y_mm"}. Returns the added PCB_VIA objects."""
    for zone in board.Zones():
        zone.UnFill()

    f_cu, b_cu = board.GetLayerID("F.Cu"), board.GetLayerID("B.Cu")
    existing = []
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            existing.append((p.x / MM, p.y / MM,
                             t.GetWidth(f_cu) / MM))
    added = []
    skipped_pad = 0
    skipped_track = 0
    import cec_slab_pour
    for v in via_list:
        x, y = v["x_mm"], v["y_mm"]
        if any((x - qx) ** 2 + (y - qy) ** 2
               < ((dia + qdia) / 2.0 + 0.20) ** 2
               for (qx, qy, qdia) in existing):
            continue
        nc = board.GetNetcodeFromNetname(v["net"])
        if nc <= 0:
            continue
        at = pcbnew.VECTOR2I(_nm(x), _nm(y))
        # Defense in depth at the materialization boundary.  Frozen
        # pour-first state can outlive later critical-pair routing, and old
        # state files predate the exact field-via gate in the planner.  A
        # routed-power via may be omitted (and the candidate rejected for an
        # honest open) but may never be drilled through foreign signal copper.
        if not cec_slab_pour.via_clear_of_foreign_tracks(
                board, nc, x, y, diameter_mm=dia,
                clearance_mm=cec_slab_pour.PAD_MARGIN):
            skipped_track += 1
            continue
        # assembly-class via-in-pad exclusion (owner ruling 2026-07-25) --
        # defense in depth: the v4 planner reseats field vias beside pads
        # upstream, so a refusal here marks an upstream miss, loudly.
        if _via_pad_excluded(board, at, _nm(dia), _nm(drill), nc):
            skipped_pad += 1
            continue
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(at)
        via.SetDrill(_nm(drill))
        via.SetWidth(_nm(dia))
        via.SetNetCode(nc)
        via.SetLayerPair(f_cu, b_cu)
        # These barrels are part of the synthesized rail topology, not router
        # suggestions.  Freerouting preserves the locked pickup tracks but is
        # otherwise free to delete an unlocked bridge via during SES import,
        # which leaves a deterministic dangling rail stub on every seed.
        via.SetLocked(True)
        board.Add(via)
        added.append(via)
        existing.append((x, y, dia))
    if skipped_pad:
        print(f"[cec_fr] add_overunder_vias: {skipped_pad} via(s) REFUSED "
              "in-pad (assembly-class exclusion, owner ruling 2026-07-25 -- "
              "upstream should have reseated)", file=sys.stderr)
    if skipped_track:
        print(f"[cec_fr] add_overunder_vias: {skipped_track} via(s) REFUSED "
              "through foreign routed copper (critical-route ownership "
              "boundary)", file=sys.stderr)
    return added


# ---------------------------------------------------------------------------
# synthesize_kelvin_taps -- the GENERATIVE four-wire Kelvin inner-leg tap (§6.8)
# ---------------------------------------------------------------------------
def _inner_edge_pt(this_pad, other_pos, inset_mm=0.0):
    """The §6.8 inner-edge sense point of a shunt pad: the centre of the pad EDGE that faces the
    other terminal. inner_dir = unit(other_terminal - this_pad); the point is pad_centre advanced
    by the pad half-extent ALONG inner_dir. This is byte-for-byte the inner-ness math the checker
    uses (cec_constraints._chk_kelvin_inner: tap_pt = centre + inner_dir*(|ix|*sx/2 + |iy|*sy/2)),
    so a tap STARTED here passes the inner-edge assertion by construction. Returns (x_mm, y_mm,
    inner_dx, inner_dy).

    *inset_mm* pulls the point that far BACK from the exact boundary toward the pad centre. The
    builder lays the tap start with a small inset so the endpoint sits unambiguously INSIDE the pad
    copper -- a point exactly on the boundary reads as a track_dangling end in KiCad connectivity
    once it is a lone arm (when the sibling INA tap on the same pad is guard-refused, it no longer
    shares the junction). The inset stays a small fraction of the pad reach, so inner-ness remains
    far above the checker's inner_min."""
    pc = this_pad.GetPosition()
    dx, dy = (other_pos.x - pc.x) / MM, (other_pos.y - pc.y) / MM
    dn = math.hypot(dx, dy) or 1.0
    ux, uy = dx / dn, dy / dn                                   # inner direction (board frame, toward other terminal)
    sz = this_pad.GetSize()
    # PROJECT inner_dir onto the pad's LOCAL axes so reach is the TRUE edge distance even when the
    # footprint (hence pad) is rotated: GetSize() is the UNROTATED size, so on a rot +-90 shunt the
    # board-x/board-y extents are swapped and a naive |ux|*sx/2+|uy|*sy/2 lands the start OFF the pad
    # (~1mm into the gap on the EPS R_2512 shunt -- it never tapped the shunt edge; the sibling INA tap
    # meeting at that off-pad junction merely hid it). Support function of the local-axis rectangle:
    # reach = |d.xhat|*hx + |d.yhat|*hy with d projected into the pad frame.
    try:
        ang = math.radians(this_pad.GetOrientationDegrees())
    except Exception:                                          # older binding: EDA_ANGLE
        ang = this_pad.GetOrientation().AsRadians()
    ca, sa = math.cos(ang), math.sin(ang)
    lux = ux * ca + uy * sa                                    # inner_dir in the pad-local frame
    luy = -ux * sa + uy * ca
    reach = abs(lux) * (sz.x / MM) / 2.0 + abs(luy) * (sz.y / MM) / 2.0
    reach = max(0.0, reach - max(0.0, inset_mm))
    return pc.x / MM + ux * reach, pc.y / MM + uy * reach, ux, uy


# Current-sense IC input-pad map, keyed by part-value substring. The footprint pads carry
# no GetPinFunction() (measured empty on the EPS INA238/INA181 lands), so the IN+ / IN- pin is
# resolved by part value + pad NUMBER. IN+ takes the _HI tap, IN- takes the _LO tap. CRITICAL:
# on the INA238/228 the _LO net carries BOTH IN-(pad 9) AND Vbus(pad 8) -- the old nearest-by-
# distance picker grabbed Vbus (the GND-adjacent pad), so the straight stub shorted to GND. Pin
# function is the correct selector.
_SENSE_INPAD = {
    "INA238": {"HI": "10", "LO": "9"},   # VSSOP-10: 10=IN+, 9=IN-, 8=Vbus
    "INA228": {"HI": "10", "LO": "9"},
    "INA181": {"HI": "3",  "LO": "4"},   # 3=IN+, 4=IN-
}


def _sense_in_pad(fp, role):
    """The IN+/IN- input pad NAME of a current-sense IC for the given role ('HI'->IN+, 'LO'->IN-).
    Maps by part value (footprint pads carry no pin function). Returns the pad name, or None when
    the part is unrecognised (caller falls back to nearest-pad)."""
    val = (fp.GetValue() or "").upper()
    for key, m in _SENSE_INPAD.items():
        if key in val:
            return m.get(role)
    return None


def _via_pad_excluded(board, at, dia_nm, drill_nm=None, net_code=None):
    """Return the pad blocking an intended through via, or None when clear.

    Legacy boards retain the blanket no-via-on-pad rule. A board whose own
    properties declare an approved POFV profile may use a same-net via inside
    an SMD land only when the centralized fabrication check verifies drill,
    annular ring, and full-land containment. Different-net and THT overlaps
    always remain blocked. Omitting drill/net intentionally preserves the old
    fail-closed behavior for callers that cannot prove the intended via.
    """
    if drill_nm is not None and net_code is not None:
        blocking, _allowed = _fab.via_at_pad_conflicts(
            board, at, dia_nm, drill_nm, net_code)
        return blocking
    circ = pcbnew.SHAPE_CIRCLE(at, dia_nm // 2)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            stack = p.GetLayerSet().CuStack()
            if not stack:
                continue
            try:
                if p.GetEffectiveShape(stack[0]).Collide(circ, 0):
                    return p
            except Exception:                          # noqa: BLE001
                continue
    return None


def _via_spot_clear(board, at, dia_nm, clearance_nm, exempt_codes, *,
                    drill_nm=None, net_code=None, contained_layers=()):
    """True iff a THROUGH-via of diameter dia_nm at *at* has no foreign-net
    pad/track/via within clearance_nm on ANY enabled copper layer. A through
    barrel exists on every layer of the stack, so a single-layer probe is a
    hole: the B2 rung probe (2026-07-23) measured one pickup via -- cleared on
    its pad's F.Cu only -- shorting a foreign In2 track and a B.Cu track at
    the same spot. Plane ZONES are deliberately not tested (the guard family
    checks pads/tracks/vias): the zone filler's antipads give a via its plane
    clearance at fill time.

    ALSO enforces the net-independent assembly-class pad exclusion
    (_via_pad_excluded, owner via-in-pad ruling 2026-07-25) so every caller
    -- pickups, force vias, lastmile, tap doglegs -- inherits it."""
    if _via_pad_excluded(board, at, dia_nm, drill_nm, net_code) is not None:
        return False
    contained_layers = {int(layer) for layer in (contained_layers or ())}
    # Copper graphics have no net code, so the ordinary foreign-net scan below
    # cannot see them.  A through via piercing exposed logo/artwork copper is
    # nevertheless a real short/clearance fault.  Probe exact graphical shapes
    # on every copper layer before allowing any synthesized barrel.
    circ = pcbnew.SHAPE_CIRCLE(at, dia_nm // 2)
    for fp in board.GetFootprints():
        for item in fp.GraphicalItems():
            try:
                if item.GetLayer() not in board.GetEnabledLayers().CuStack():
                    continue
                if int(item.GetLayer()) in contained_layers:
                    continue
                if item.GetEffectiveShape().Collide(circ, clearance_nm):
                    return False
            except Exception:                           # noqa: BLE001
                continue
    # SHAPE_SEGMENT has no point-only overload.  Use a one-database-unit
    # centreline rather than the historical 10 um ray: that ray made a legal
    # via exactly at minimum clearance appear 10 um closer to whichever
    # foreign object happened to lie in +X.  One nanometre is below every fab
    # resolution while retaining a valid non-zero shape for KiCad.
    probe = pcbnew.VECTOR2I(at.x + 1, at.y)
    for lid in board.GetEnabledLayers().CuStack():
        if int(lid) in contained_layers:
            # The fabrication gate above proved that this via land is wholly
            # contained by an existing same-net surface pad. It cannot worsen
            # that layer's already-established copper clearance. Other layers
            # still receive the full through-via collision probe.
            continue
        if not _tap_foreign_clear(board, at, probe, dia_nm, lid,
                                  clearance_nm, exempt_codes):
            return False
    return True


def _tap_foreign_clear(board, S, T, width_nm, layer_id, clearance_nm, sense_codes):
    """True iff a single straight F.Cu segment S->T (width width_nm) has NO FOREIGN-net copper
    within clearance_nm on layer_id. FOREIGN = any pad/track/via whose net code is NOT in
    sense_codes (the set of all _HI/_LO Kelvin-pair codes -- so the partner sense leg and the
    tap's own net never count, only GND/+3V3/signal/power foreign copper does). Uses the SAME
    GetEffectiveShape().Collide() geometry KiCad DRC uses, so a PASS here is DRC-clean for copper
    clearance on this segment -- the guard that lets the tap REFUSE rather than lay a shorting stub."""
    seg = pcbnew.SHAPE_SEGMENT(S, T, width_nm)
    # Pipeline-owned laid pours are reserved copper, not ordinary zones whose
    # filler may be casually antipadded. Freerouting sees their outlines as
    # keepouts, but additive post-route helpers bypass the DSN. Apply the same
    # no-incursion contract here so all guarded helpers refuse foreign copper.
    for zone in board.Zones():
        if zone.GetIsRuleArea() or zone.GetNetCode() in sense_codes:
            continue
        if not (zone.GetZoneName() or "").startswith(PIPELINE_POUR_PREFIXES):
            continue
        if layer_id not in zone.GetLayerSet().CuStack():
            continue
        try:
            if zone.Outline().Collide(seg, 0):
                return False
        except Exception:                              # noqa: BLE001
            continue
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() in sense_codes:
                continue
            if layer_id not in p.GetLayerSet().CuStack():
                continue
            try:
                if p.GetEffectiveShape(layer_id).Collide(seg, clearance_nm):
                    return False
            except Exception:                       # noqa: BLE001 -- a weird shape never breaks the guard
                continue
        # Copper artwork has no net code, but it is still physical copper.
        # Direct post-route helpers bypass the decorative DSN keepout, so they
        # must treat footprint graphics (logos, shields, custom copper) as
        # foreign obstacles just as the via guard does.
        for item in fp.GraphicalItems():
            try:
                if item.GetLayer() != layer_id:
                    continue
                if item.GetEffectiveShape().Collide(seg, clearance_nm):
                    return False
            except Exception:                       # noqa: BLE001
                continue
    for t in board.GetTracks():
        if t.GetNetCode() in sense_codes:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            if layer_id not in t.GetLayerSet().CuStack():
                continue
        elif t.GetLayer() != layer_id:
            continue
        try:
            if t.GetEffectiveShape(layer_id).Collide(seg, clearance_nm):
                return False
        except Exception:                           # noqa: BLE001
            continue
    return True


def _layer_foreign_shapes(board, layer_id, sense_codes, *, identified=False):
    """Snapshot exact foreign-copper shapes for one guarded path search.

    ``_tap_foreign_clear`` is the authoritative one-shot guard, but a bounded
    maze can qualify thousands of lattice hops without mutating the board.
    Re-walking every footprint and rebuilding every effective pad/track shape
    for every hop made the Hub's post-router take roughly eleven CPU-minutes
    per seed.  Snapshot the same KiCad shapes once per maze and retain their
    bounding boxes only as a conservative rejection accelerator; every nearby
    object still receives the identical ``Collide`` test before a hop passes.

    Pipeline pour outlines use zero extra clearance, matching
    ``_tap_foreign_clear``.  Pads/tracks/vias use the caller's copper
    clearance.  A shape whose bounding box cannot be obtained remains in the
    snapshot with ``None`` and is therefore always tested fail-closed.
    """
    zones = []
    copper = []

    def _net_name(obj):
        try:
            return obj.GetNetname() or ""
        except Exception:                              # noqa: BLE001
            return ""

    layer_name = board.GetLayerName(layer_id)

    def _append(rows, shape, identity=None):
        try:
            box = shape.BBox()
        except Exception:                              # noqa: BLE001
            box = None
        rows.append((shape, box, identity) if identified else (shape, box))

    for zone in board.Zones():
        if zone.GetIsRuleArea() or zone.GetNetCode() in sense_codes:
            continue
        if not (zone.GetZoneName() or "").startswith(PIPELINE_POUR_PREFIXES):
            continue
        if layer_id not in zone.GetLayerSet().CuStack():
            continue
        try:
            _append(zones, zone.Outline(), {
                "kind": "zone", "net": _net_name(zone),
                "name": zone.GetZoneName() or "", "layer": layer_name})
        except Exception:                              # noqa: BLE001
            # Preserve the historical guard's behavior for malformed/engine
            # specific outlines: it also skips only the outline that cannot be
            # inspected, rather than weakening checks on other copper.
            continue
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if (pad.GetNetCode() in sense_codes
                    or layer_id not in pad.GetLayerSet().CuStack()):
                continue
            try:
                _append(copper, pad.GetEffectiveShape(layer_id), {
                    "kind": "pad", "ref": fp.GetReference(),
                    "pad": str(pad.GetNumber()), "net": _net_name(pad),
                    "layer": layer_name})
            except Exception:                          # noqa: BLE001
                continue
        for item in fp.GraphicalItems():
            try:
                if item.GetLayer() == layer_id:
                    _append(copper, item.GetEffectiveShape(), {
                        "kind": "footprint_graphic", "ref": fp.GetReference(),
                        "layer": layer_name})
            except Exception:                          # noqa: BLE001
                continue
    for track in board.GetTracks():
        if track.GetNetCode() in sense_codes:
            continue
        if track.Type() == pcbnew.PCB_VIA_T:
            if layer_id not in track.GetLayerSet().CuStack():
                continue
        elif track.GetLayer() != layer_id:
            continue
        try:
            is_via = track.GetClass() == "PCB_VIA"
            identity = {
                "kind": ("via" if is_via else "track"),
                "net": _net_name(track), "layer": layer_name,
                # Placement materialization deliberately locks synthesized
                # local-cell copper.  Retaining that bit lets a later refusal
                # certificate distinguish a movable generated cell tail from
                # unrelated board routing without relying on UUIDs or refs.
                "locked": bool(track.IsLocked())}
            if not is_via:
                identity["from_mm"] = [
                    round(track.GetStart().x / MM, 6),
                    round(track.GetStart().y / MM, 6)]
                identity["to_mm"] = [
                    round(track.GetEnd().x / MM, 6),
                    round(track.GetEnd().y / MM, 6)]
                identity["width_mm"] = round(track.GetWidth() / MM, 6)
            else:
                identity["at_mm"] = [
                    round(track.GetPosition().x / MM, 6),
                    round(track.GetPosition().y / MM, 6)]
                identity["diameter_mm"] = round(
                    track.GetWidth(layer_id) / MM, 6)
            try:
                identity["uuid"] = track.m_Uuid.AsString()
            except Exception:                          # noqa: BLE001
                pass
            _append(copper, track.GetEffectiveShape(layer_id), identity)
        except Exception:                              # noqa: BLE001
            continue
    return zones, copper


def _foreign_shape_indexes(board, layer_id, sense_codes, *, cache=None):
    """Return exact, bucket-indexed foreign shapes for a layer/net context.

    ``cache`` is intentionally supplied by the caller instead of being global:
    a board is mutable and a module-level cache would become stale after any
    synthesized copper.  The key includes the exempt net set so a snapshot can
    never be reused under a broader clearance exemption.  Bounding boxes only
    select possible collisions; :func:`_snapshot_foreign_clear` still performs
    KiCad's exact ``Collide`` test on every selected shape.
    """
    key = (int(layer_id), tuple(sorted(int(code) for code in sense_codes)))
    if cache is not None and key in cache:
        return cache[key]
    zones, copper = _layer_foreign_shapes(board, layer_id, set(sense_codes))
    indexed = (_bucket_foreign_shapes(zones),
               _bucket_foreign_shapes(copper))
    if cache is not None:
        cache[key] = indexed
    return indexed


def _bucket_foreign_shapes(rows, *, cell_nm=None, max_cells=4096):
    """Build a conservative uniform-grid index over cached KiCad shapes."""
    from collections import defaultdict

    cell = int(cell_nm or _nm(2.0))
    buckets = defaultdict(list)
    global_rows = []
    for index, row in enumerate(rows):
        box = row[1]
        if box is None:
            global_rows.append(index)
            continue
        try:
            x0, y0 = box.GetX() // cell, box.GetY() // cell
            x1 = (box.GetX() + box.GetWidth()) // cell
            y1 = (box.GetY() + box.GetHeight()) // cell
            count = (x1 - x0 + 1) * (y1 - y0 + 1)
            if count > int(max_cells):
                global_rows.append(index)
                continue
            for bx in range(int(x0), int(x1) + 1):
                for by in range(int(y0), int(y1) + 1):
                    buckets[(bx, by)].append(index)
        except Exception:                              # noqa: BLE001
            global_rows.append(index)
    return {"rows": rows, "cell": cell, "buckets": dict(buckets),
            "global": tuple(global_rows)}


def _indexed_shape_rows(index, query_box):
    """Yield the unique cached rows whose grid cells touch *query_box*."""
    if not isinstance(index, dict):
        return index
    rows = index["rows"]
    selected = set(index.get("global", ()))
    if query_box is None:
        selected.update(range(len(rows)))
    else:
        cell = index["cell"]
        try:
            x0, y0 = query_box.GetX() // cell, query_box.GetY() // cell
            x1 = (query_box.GetX() + query_box.GetWidth()) // cell
            y1 = (query_box.GetY() + query_box.GetHeight()) // cell
            buckets = index["buckets"]
            for bx in range(int(x0), int(x1) + 1):
                for by in range(int(y0), int(y1) + 1):
                    selected.update(buckets.get((bx, by), ()))
        except Exception:                              # noqa: BLE001
            selected.update(range(len(rows)))
    return [rows[i] for i in sorted(selected)]


def _snapshot_foreign_clear(S, T, width_nm, clearance_nm, zones, copper):
    """Exact foreign-copper qualification against a shape snapshot."""
    segment = pcbnew.SHAPE_SEGMENT(S, T, width_nm)
    try:
        segment_box = segment.BBox()
        clearance_box = segment_box.GetInflated(clearance_nm)
    except Exception:                                  # noqa: BLE001
        segment_box = clearance_box = None
    for shape, box in _indexed_shape_rows(zones, segment_box):
        try:
            if (box is None or segment_box is None or box.Intersects(segment_box)) \
                    and shape.Collide(segment, 0):
                return False
        except Exception:                              # noqa: BLE001
            continue
    for shape, box in _indexed_shape_rows(copper, clearance_box):
        try:
            if (box is None or clearance_box is None
                    or box.Intersects(clearance_box)) \
                    and shape.Collide(segment, clearance_nm):
                return False
        except Exception:                              # noqa: BLE001
            continue
    return True


def _identified_foreign_shape_indexes(board, layer_id, sense_codes):
    """Exact foreign-shape indexes retaining JSON-safe obstruction identity."""
    zones, copper = _layer_foreign_shapes(
        board, layer_id, set(sense_codes), identified=True)
    return _bucket_foreign_shapes(zones), _bucket_foreign_shapes(copper)


def _snapshot_foreign_blockers(S, T, width_nm, clearance_nm, zones, copper,
                               *, limit=16):
    """Return the exact foreign objects colliding with a candidate segment."""
    segment = pcbnew.SHAPE_SEGMENT(S, T, width_nm)
    try:
        segment_box = segment.BBox()
        clearance_box = segment_box.GetInflated(clearance_nm)
    except Exception:                                  # noqa: BLE001
        segment_box = clearance_box = None
    hits = []
    for rows, query_box, extra, contact in (
            (zones, segment_box, 0, "copper_overlap"),
            (copper, clearance_box, clearance_nm, "clearance")):
        for row in _indexed_shape_rows(rows, query_box):
            shape, box = row[0], row[1]
            identity = row[2] if len(row) > 2 else None
            try:
                if ((box is None or query_box is None
                     or box.Intersects(query_box))
                        and shape.Collide(segment, extra)):
                    hit = dict(identity or {"kind": "unidentified_copper"})
                    hit["contact"] = contact
                    if hit not in hits:
                        hits.append(hit)
            except Exception:                          # noqa: BLE001
                continue
    return hits[:max(0, int(limit))]


def _lastmile_refusal_certificate(
        board, S, T, width_nm, clearance_nm, net_code, layer_ids, *,
        endpoint_a=None, endpoint_b=None, maze_searched=False,
        maze_margin_mm=2.0, attempts_per_pair=4, ray_mm=1.25,
        start_escape=None, end_escape=None):
    """Explain a bounded last-mile refusal using exact geometry identities.

    This certificate intentionally does *not* claim that a net is impossible.
    It records what the bounded canonical/maze/via search tried, plus exact
    objects that block the direct segment and octilinear endpoint escape rays.
    That is sufficient for deterministic placement repair without pretending
    the sampled rays form a mathematical min-cut.
    """
    from collections import Counter

    def _identity_key(row):
        return json.dumps(row, sort_keys=True, separators=(",", ":"))

    endpoints = []
    escape_by_label = {"a": start_escape, "b": end_escape}
    for label, point, owner in (("a", S, endpoint_a or {}),
                                ("b", T, endpoint_b or {})):
        row = dict(owner)
        row.update({"endpoint": label,
                    "x_mm": round(point.x / MM, 6),
                    "y_mm": round(point.y / MM, 6)})
        escape = escape_by_label[label]
        if escape is not None:
            row["neckdown_width_mm"] = round(float(escape[0]) / MM, 6)
            row["neckdown_budget_mm"] = round(float(escape[1]) / MM, 6)
        endpoints.append(row)

    directions = (("E", 1, 0), ("NE", 1, -1), ("N", 0, -1),
                  ("NW", -1, -1), ("W", -1, 0), ("SW", -1, 1),
                  ("S", 0, 1), ("SE", 1, 1))
    ray_nm = _nm(ray_mm)
    layer_rows = []
    all_hits = Counter()
    identities = {}
    for layer_id in sorted(set(int(layer) for layer in layer_ids)):
        zones, copper = _identified_foreign_shape_indexes(
            board, layer_id, {net_code})
        direct_hits = _snapshot_foreign_blockers(
            S, T, width_nm, clearance_nm, zones, copper)
        for hit in direct_hits:
            key = _identity_key(hit)
            identities[key] = hit
            all_hits[key] += 1
        escape_rows = []
        for label, start in (("a", S), ("b", T)):
            endpoint_escape = escape_by_label[label]
            probe_width = (int(endpoint_escape[0])
                           if endpoint_escape is not None else width_nm)
            clear_rays = []
            edge_blocked = []
            ray_details = []
            blockers = Counter()
            local_identities = {}
            for name, dx, dy in directions:
                norm = math.sqrt(float(dx * dx + dy * dy))
                finish = pcbnew.VECTOR2I(
                    int(start.x + ray_nm * dx / norm),
                    int(start.y + ray_nm * dy / norm))
                if not _edge_leg_clear(
                        board, start, finish, probe_width // 2):
                    edge_blocked.append(name)
                    ray_details.append({
                        "direction": name,
                        "status": "board_edge_blocked",
                        "length_mm": round(ray_nm / MM, 6),
                        "blockers": [],
                    })
                    continue
                hits = _snapshot_foreign_blockers(
                    start, finish, probe_width, clearance_nm, zones, copper)
                if not hits:
                    clear_rays.append(name)
                    ray_details.append({
                        "direction": name,
                        "status": "clear",
                        "length_mm": round(ray_nm / MM, 6),
                        "blockers": [],
                    })
                    continue
                ray_details.append({
                    "direction": name,
                    "status": "foreign_copper_blocked",
                    "length_mm": round(ray_nm / MM, 6),
                    "blockers": hits,
                })
                for hit in hits:
                    key = _identity_key(hit)
                    identities[key] = hit
                    local_identities[key] = hit
                    blockers[key] += 1
                    all_hits[key] += 1
            escape_rows.append({
                "endpoint": label,
                "probe_width_mm": round(probe_width / MM, 6),
                "clear_rays": clear_rays,
                "edge_blocked_rays": edge_blocked,
                "ray_details": ray_details,
                "foreign_blocked_ray_count": int(sum(blockers.values())),
                "blockers": [
                    {**local_identities[key], "hit_count": int(count)}
                    for key, count in blockers.most_common(12)],
            })
        layer_rows.append({
            "layer": board.GetLayerName(layer_id),
            "direct_edge_clear": bool(_edge_leg_clear(
                board, S, T, width_nm // 2)),
            "direct_blockers": direct_hits,
            "endpoint_escape": escape_rows,
        })
    return {
        "schema": 1,
        "conclusion": "bounded_search_exhausted_not_global_impossibility",
        "net": board.GetNetInfo().GetNetItem(net_code).GetNetname(),
        "width_mm": round(width_nm / MM, 6),
        "clearance_mm": round(clearance_nm / MM, 6),
        "endpoints": endpoints,
        "search": {
            "canonical_octilinear": True,
            "same_layer_maze": bool(maze_searched),
            "maze_margin_mm": float(maze_margin_mm),
            "via_bridge": True,
            "multilayer_via_maze": bool(
                maze_searched
                and len(set(int(layer) for layer in layer_ids)) >= 2),
            "attempts_per_cluster_pair": int(attempts_per_pair),
            "escape_probe_mm": float(ray_mm),
            "endpoint_neckdowns": bool(
                start_escape is not None or end_escape is not None),
        },
        "layers": layer_rows,
        "dominant_blockers": [
            {**identities[key], "hit_count": int(count)}
            for key, count in all_hits.most_common(16)],
    }


def _tap_pair_overlap_clear(board, S, T, width_nm, layer_id, own_code, sense_codes):
    """True iff the segment S->T does not PLOW THROUGH a sense pad of a DIFFERENT sense net.
    The foreign guard (_tap_foreign_clear) deliberately ignores ALL sense-net copper (the partner
    leg is legitimately ADJACENT at sub-clearance in the seated notch), which is safe for the
    short straight taps but NOT for a multi-leg dogleg that could route a LO leg straight across
    the shunt's HI pad -- a real short DRC would catch only after the copper is laid. This guard
    closes that: different-sense-net pads are tested at a merely-touching clearance (0.02mm), so
    adjacency stays allowed and overlap is refused."""
    seg = pcbnew.SHAPE_SEGMENT(S, T, width_nm)
    near_nm = _nm(0.02)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            nc = p.GetNetCode()
            if nc == own_code or nc not in sense_codes:
                continue
            if layer_id not in p.GetLayerSet().CuStack():
                continue
            try:
                if p.GetEffectiveShape(layer_id).Collide(seg, near_nm):
                    return False
            except Exception:                       # noqa: BLE001
                continue
    return True


def _tap_pending_collider(path, own_code, layer_id, pending, width_nm,
                          clearance_nm):
    """Name an already-planned foreign Kelvin leg that *path* would hit.

    Kelvin candidates are deliberately decided before any are materialized so
    duplicate same-net launches can be coalesced.  The old implementation also
    made every different-net in-call candidate invisible, allowing two valid
    individual tap paths to cross and leaving DRC to discover the short later.
    Same-net overlap remains legal and is pruned by the existing coalescer;
    different-net copper must satisfy the ordinary board clearance now, while
    the fallback ladder can still try another guarded shape.
    """
    for other_path, other_code, other_net, _label, other_layer in pending:
        if other_code == own_code or other_layer != layer_id:
            continue
        for start, end in zip(path, path[1:]):
            if start == end:
                continue
            candidate = pcbnew.SHAPE_SEGMENT(start, end, width_nm)
            for other_start, other_end in zip(other_path, other_path[1:]):
                if other_start == other_end:
                    continue
                other = pcbnew.SHAPE_SEGMENT(
                    other_start, other_end, width_nm)
                try:
                    if candidate.Collide(other, clearance_nm):
                        return "pending Kelvin leg [%s]" % other_net
                except Exception:                       # noqa: BLE001
                    # SWIG shape overloads differ across KiCad releases. The
                    # downstream exact DRC remains fail closed if an older
                    # binding cannot perform this pre-materialization probe.
                    continue
    return None


def _canonical_tap_path(S, T, ux, uy, *, run_pref_mm=0.9, run_min_mm=0.3, gap_mm=None):
    """The TEXTBOOK datasheet Kelvin tap shape (owner directive 2026-07-08): exit the
    shunt pad's INNER edge PERPENDICULAR to it (= along the inner direction u), run
    straight inward "a ways", then ONE 90-degree turn toward the sense IC, final
    approach parallel to the axis. Decompose T-S onto (u, perp): axial a, lateral b.
    Path = S -> P1 (u * run) -> P2 (perp * b) -> T (u * (a - run)). Canonical only
    when the IC sits INWARD (a > run_min); the turn happens at or before the IC's
    axial coordinate and inside the inter-pad gap. Returns the polyline or None."""
    ax = (T.x - S.x) / MM
    ay = (T.y - S.y) / MM
    a = ax * ux + ay * uy                                # axial component (inward)
    px, py = -uy, ux                                     # perpendicular unit
    b = ax * px + ay * py                                # lateral component
    if a <= run_min_mm:
        return None                                      # IC not inward -- not canonical
    run = min(run_pref_mm, a)
    if gap_mm is not None:
        run = min(run, max(run_min_mm, gap_mm * 0.45))   # stay inside the inter-pad gap
    if run < run_min_mm:
        return None
    P1 = pcbnew.VECTOR2I(S.x + _nm(ux * run), S.y + _nm(uy * run))
    P2 = pcbnew.VECTOR2I(P1.x + _nm(px * b), P1.y + _nm(py * b))
    path = [S, P1]
    if (P2.x, P2.y) != (P1.x, P1.y):
        path.append(P2)
    if (T.x, T.y) != (path[-1].x, path[-1].y):
        path.append(T)
    return path if len(path) >= 3 else None


def _dogleg_candidates(S, T):
    """Candidate 2-3 leg orthogonal paths S->..->T for a REFUSED straight tap, nearest-to-straight
    first: the two L-bends, then channel doglegs that run the long axis at a fraction of the
    offset (the '1-bend LO tap down the open notch'). Pure geometry -- every leg is still guarded
    before anything is laid."""
    out = [[S, pcbnew.VECTOR2I(S.x, T.y), T],
           [S, pcbnew.VECTOR2I(T.x, S.y), T]]
    for f in (0.5, 0.3, 0.7):
        xf = int(S.x + f * (T.x - S.x))
        yf = int(S.y + f * (T.y - S.y))
        out.append([S, pcbnew.VECTOR2I(xf, S.y), pcbnew.VECTOR2I(xf, T.y), T])
        out.append([S, pcbnew.VECTOR2I(S.x, yf), pcbnew.VECTOR2I(T.x, yf), T])
    return out


def _locked_pad_contact(board, pad, *, tracks=None):
    """True iff a LOCKED same-net track ENDS on *pad* -- endpoint HitTest at the track's
    HALF-WIDTH tolerance (an endpoint within half a track width of the pad boundary lays
    copper overlapping the pad = electrically connected; closes the pad-edge/centerline
    mismatch class without touching the authored geometry). This is the ONE detection the
    blueprint-tap coverage handshake uses (owner ruling 2026-07-25, blueprint Kelvin tap
    discipline): a stamped cell's authored tap copper is laid LOCKED at materialize, so
    locked pad contact == "this sense input already carries its authored tap".

    *tracks* optionally narrows the scan to a prefiltered track list (per-pair loops)."""
    nn = pad.GetNetname()
    src = tracks if tracks is not None else board.GetTracks()
    for t in src:
        if t.GetClass() != "PCB_TRACK" or not t.IsLocked() or t.GetNetname() != nn:
            continue
        tol = max(0, t.GetWidth() // 2)
        for end in (t.GetStart(), t.GetEnd()):
            try:
                hit = pad.HitTest(end, tol)
            except Exception:                       # noqa: BLE001 -- older binding: no accuracy arg
                hit = pad.HitTest(end)
            if hit:
                return True
    return False


def _tap_shape_bbox_mm(shape):
    """Return a small JSON-safe bounding box for an exact KiCad shape."""
    try:
        box = shape.BBox()
        return [round(box.GetX() / MM, 6), round(box.GetY() / MM, 6),
                round((box.GetX() + box.GetWidth()) / MM, 6),
                round((box.GetY() + box.GetHeight()) / MM, 6)]
    except Exception:                                  # noqa: BLE001
        return None


def _tap_leg_collider_detail(board, S, T, width_nm, layer_id, clr_nm,
                             sense_codes, own_code, *, include_sense=True):
    """Describe the first exact-copper obstruction on one Kelvin tap leg.

    This is the certificate-producing twin of :func:`_tap_foreign_clear`.
    Keep its obstacle classes and clearances in lock-step with that guard so a
    refused route never loses the physical reason that made it fail.  The
    returned coordinates are intentionally generic: downstream placement can
    move a named foreign footprint away from the blocked leg, or move an
    endpoint normal to immutable zone/track copper, without knowing a board or
    reference designator in advance.
    """
    seg = pcbnew.SHAPE_SEGMENT(S, T, width_nm)
    near_nm = _nm(0.02)
    layer_name = board.GetLayerName(layer_id)

    def detail(kind, label, *, ref=None, pad=None, net=None, shape=None,
               position=None):
        row = {
            "kind": kind, "label": label, "layer": layer_name,
            "net": str(net or ""),
        }
        if ref:
            row["ref"] = str(ref)
        if pad is not None:
            row["pad"] = str(pad)
        if position is not None:
            row["position_mm"] = [round(position.x / MM, 6),
                                  round(position.y / MM, 6)]
        if shape is not None:
            bounds = _tap_shape_bbox_mm(shape)
            if bounds is not None:
                row["bbox_mm"] = bounds
        return row

    # Pipeline-owned poured copper is an immutable route authority at this
    # stage.  It is checked before ordinary items, matching
    # _tap_foreign_clear's no-incursion contract.
    for zone in board.Zones():
        if zone.GetIsRuleArea() or zone.GetNetCode() in sense_codes:
            continue
        if not (zone.GetZoneName() or "").startswith(PIPELINE_POUR_PREFIXES):
            continue
        if layer_id not in zone.GetLayerSet().CuStack():
            continue
        try:
            outline = zone.Outline()
            if outline.Collide(seg, 0):
                name = zone.GetZoneName() or "pipeline pour"
                return detail(
                    "zone", "zone %s [%s]" % (name, zone.GetNetname()),
                    net=zone.GetNetname(), shape=outline)
        except Exception:                              # noqa: BLE001
            continue
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for p in fp.Pads():
            nc = p.GetNetCode()
            if layer_id not in p.GetLayerSet().CuStack():
                continue
            try:
                if nc in sense_codes:
                    if (include_sense and nc != own_code
                            and p.GetEffectiveShape(layer_id).Collide(
                                seg, near_nm)):
                        shape = p.GetEffectiveShape(layer_id)
                        label = "sense pad %s.%s [%s]" % (
                            ref, p.GetPadName(), p.GetNetname())
                        return detail(
                            "sense_pad", label, ref=ref, pad=p.GetPadName(),
                            net=p.GetNetname(), shape=shape,
                            position=p.GetPosition())
                elif p.GetEffectiveShape(layer_id).Collide(seg, clr_nm):
                    shape = p.GetEffectiveShape(layer_id)
                    label = "pad %s.%s [%s]" % (
                        ref, p.GetPadName(), p.GetNetname())
                    return detail(
                        "pad", label, ref=ref, pad=p.GetPadName(),
                        net=p.GetNetname(), shape=shape,
                        position=p.GetPosition())
            except Exception:                       # noqa: BLE001 -- a weird shape never breaks the guard
                continue
        for item in fp.GraphicalItems():
            try:
                if item.GetLayer() != layer_id:
                    continue
                shape = item.GetEffectiveShape()
                if shape.Collide(seg, clr_nm):
                    return detail(
                        "footprint_copper", "footprint copper %s" % ref,
                        ref=ref, shape=shape)
            except Exception:                       # noqa: BLE001
                continue
    for t in board.GetTracks():
        if t.GetNetCode() in sense_codes:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            if layer_id not in t.GetLayerSet().CuStack():
                continue
        elif t.GetLayer() != layer_id:
            continue
        try:
            shape = t.GetEffectiveShape(layer_id)
            if shape.Collide(seg, clr_nm):
                kind = "via" if t.Type() == pcbnew.PCB_VIA_T else "track"
                if kind == "via":
                    position = t.GetPosition()
                else:
                    start, end = t.GetStart(), t.GetEnd()
                    position = pcbnew.VECTOR2I(
                        (start.x + end.x) // 2, (start.y + end.y) // 2)
                return detail(
                    kind, "%s [%s]" % (kind, t.GetNetname()),
                    net=t.GetNetname(), shape=shape, position=position)
        except Exception:                           # noqa: BLE001
            continue
    return None


def _tap_leg_collider(board, S, T, width_nm, layer_id, clr_nm, sense_codes, own_code):
    """NAME the first item that blocks leg S->T (legacy string API)."""
    row = _tap_leg_collider_detail(
        board, S, T, width_nm, layer_id, clr_nm, sense_codes, own_code)
    return row.get("label") if row else None


def _tap_reservation_hits(path, reservations, *, net, layer,
                          width_nm, clearance_nm, limit=24):
    """Return exact future-copper intersections for one Kelvin polyline.

    Pour-first reservations are still abstract while the precision ladder is
    running, so the ordinary board-copper collider cannot see them.  Inflate
    each foreign-net rectangle by the proposed tap half-width plus clearance
    and use exact segment/AABB clipping.  Same-net territory is intentionally
    exempt: the Kelvin trace is meant to merge into its own current copper.
    """
    if path is None or len(path) < 2 or not reservations:
        return []

    def segment_hits_rect(px, py, qx, qy, rectangle):
        x0, y0, x1, y1 = rectangle
        dx, dy = qx - px, qy - py
        lo, hi = 0.0, 1.0
        for p, q in ((-dx, px - x0), (dx, x1 - px),
                     (-dy, py - y0), (dy, y1 - py)):
            if abs(p) <= 1e-15:
                if q < 0.0:
                    return False
                continue
            ratio = q / p
            if p < 0.0:
                lo = max(lo, ratio)
            else:
                hi = min(hi, ratio)
            if lo > hi:
                return False
        return True

    inflation = (float(width_nm) / 2.0 + float(clearance_nm)) / MM
    points = [(point.x / MM, point.y / MM) for point in path]
    hits = []
    seen = set()
    for row in reservations or ():
        if not isinstance(row, dict):
            continue
        owner_net = str(row.get("net") or "")
        owner_layer = str(row.get("layer") or "F.Cu")
        if owner_net == str(net) or owner_layer != str(layer):
            continue
        if not all(row.get(key) is not None
                   for key in ("x0", "y0", "x1", "y1")):
            continue
        x0, x1 = sorted((float(row["x0"]), float(row["x1"])))
        y0, y1 = sorted((float(row["y0"]), float(row["y1"])))
        rectangle = (x0 - inflation, y0 - inflation,
                     x1 + inflation, y1 + inflation)
        for index, ((px, py), (qx, qy)) in enumerate(
                zip(points, points[1:])):
            if (max(px, qx) < rectangle[0]
                    or min(px, qx) > rectangle[2]
                    or max(py, qy) < rectangle[1]
                    or min(py, qy) > rectangle[3]):
                continue
            if not segment_hits_rect(px, py, qx, qy, rectangle):
                continue
            signature = (
                owner_net, owner_layer, index,
                round(x0, 6), round(y0, 6),
                round(x1, 6), round(y1, 6))
            if signature in seen:
                continue
            seen.add(signature)
            hits.append({
                "kind": "future_power_reservation",
                "owner": str(row.get("name") or row.get("kind")
                             or owner_net),
                "net": owner_net,
                "layer": owner_layer,
                "leg_index": int(index),
                "leg_start_mm": [round(px, 6), round(py, 6)],
                "leg_end_mm": [round(qx, 6), round(qy, 6)],
                "reservation_bounds_mm": [
                    round(x0, 6), round(y0, 6),
                    round(x1, 6), round(y1, 6)],
                "required_clearance_mm": round(inflation, 6),
            })
            if len(hits) >= int(limit):
                return hits
    return hits


def _tap_path_refusal_certificate(board, path, width_nm, layer_id, clr_nm,
                                  sense_codes, own_code, *, path_kind,
                                  pending=None, include_sense=True,
                                  reservations=(), own_net=None):
    """Capture every blocked leg of one rejected Kelvin path candidate."""
    if path is None:
        return {
            "path_kind": str(path_kind),
            "reason": "no canonical geometry",
            "points_mm": [], "blocked_legs": [],
        }
    points = [[round(point.x / MM, 6), round(point.y / MM, 6)]
              for point in path]
    blocked = []
    for index, (start, end) in enumerate(zip(path, path[1:])):
        if start == end:
            continue
        collider = _tap_leg_collider_detail(
            board, start, end, width_nm, layer_id, clr_nm,
            sense_codes, own_code, include_sense=include_sense)
        if collider:
            blocked.append({
                **collider,
                "leg_index": int(index),
                "leg_start_mm": points[index],
                "leg_end_mm": points[index + 1],
            })
    pending_label = _tap_pending_collider(
        path, own_code, layer_id, pending or (), width_nm, clr_nm)
    if pending_label:
        blocked.append({
            "kind": "pending_kelvin", "label": pending_label,
            "layer": board.GetLayerName(layer_id), "net": "",
        })
    blocked.extend(_tap_reservation_hits(
        path, reservations, net=own_net,
        layer=board.GetLayerName(layer_id),
        width_nm=width_nm, clearance_nm=clr_nm))
    return {
        "path_kind": str(path_kind), "points_mm": points,
        "blocked_legs": blocked,
        "reason": (blocked[0].get("label") if blocked
                   else "collider unresolved"),
    }


def synthesize_kelvin_taps(board, *, kelvin_pairs=None, width=0.25,
                           layer="F.Cu", max_ic_mm=9.0,
                           clearance=0.2, avoid=()):
    """SYNTHESIZE the four-wire Kelvin sense TAP as real copper: a short thin F.Cu stub from each
    2-pad shunt's INNER edge (the sense point facing the other terminal) to each seated current-sense
    IC's matching input pad on that net -- HI-inner -> IN+ (the *_HI pad), LO-inner -> IN- (the *_LO
    pad). The kelvin half cec_fr never had: derive_power_pours deliberately EXCLUDES the INA SMD sense
    pads, so the HI box (cable-in -> shunt) and the LO box (shunt -> cable-out) stop ~3.9mm short of
    each other at the shunt -- an open tap window. This lays the §6.8 inner-edge sense connection INTO
    that window.

    ADDITIVE same-net copper, run AFTER the route (like add_power_pours / add_via_field), so it can
    only ADD a clean direct sense connection -- it never reshapes Freerouting's global solution and so
    never strands the sense (the kelvin_ok gate holds). The stub starts on the shunt-pad copper at the
    inner edge and merges with the same-net pour (ZONE_CONNECTION_FULL). NO VIA: each tap is a single
    F.Cu segment (inner edge -> IN pad), so the sense never folds via inductance into the loop (§6.8).
    The inner-edge geometry MATCHES cec_constraints._chk_kelvin_inner, so the build and the constraint
    check agree by construction.

    TWO defences against the stub shorting to foreign copper in the seated channel:
      (1) PIN-FUNCTION termination -- the tap lands on the IN+/IN- pad by FUNCTION (HI->IN+, LO->IN-),
          NOT the nearest pad by distance. The INA238/228 carries BOTH IN-(pad 9) and Vbus(pad 8) on
          the _LO net; the old nearest-pick grabbed Vbus, which sits 0.5mm from the GND pad, so the
          straight stub clipped GND. IN- is the §6.8 termination and sits clear of the GND cluster.
      (2) CLEARANCE GUARD -- before laying, the straight stub is tested against all FOREIGN-net copper
          (GND/+3V3/signal/power; the partner sense leg is never foreign) at the board *clearance*
          using the same Collide() geometry DRC uses. If it is NOT clear the tap is REFUSED (laid
          nowhere) and recorded in report['refused'] -- a shorting stub is NEVER laid (owner directive:
          the tap yields to foreign copper, it never plows through it; a refused tap re-surfaces the
          inner_tap placement directive so the seat can re-open the channel).

    SELF-GATING: a board with no 2-pad straddle shunt or no recognised INA input
    pad on a sense net lays nothing and is a no-op (shared-bus 24-pin / filtered
    12VHPWR lanes). A recognised INA input beyond ``max_ic_mm`` is different:
    Freerouting deliberately excludes that pad, so silently ignoring it would
    guarantee an open circuit. Such a pad is a named placement refusal. Pass an
    already-loaded *board* (additive, in place). Returns a report dict
    {taps, by_net: {net: ["RSn->Uk.pad", ...]}, refused: {net: [...]}, covered: {net: [...]}}.

    BLUEPRINT KELVIN TAP DISCIPLINE (owner ruling 2026-07-25, recorded at the end of
    docs/slab-pour-design-2026-07-24.md; measured on wave s464 -- precision_route ran this
    synthesizer on materialized boards whose stamped cells already carried their AUTHORED
    orthogonal taps, laying+locking a straight-DIAGONAL fallback to the INA181 on top of
    every cell):
      * COVERED-LEG SKIP (every caller inherits -- precision, import_ses, direct): an IC
        input pad already contacted by LOCKED same-net copper (endpoint HitTest at track
        half-width, _locked_pad_contact) is the stamped cell's authored tap -- the leg is
        SKIPPED and reported under 'covered', never double-laid.
      * CANONICAL-OR-REFUSE on locked-copper pairs: a pair whose _HI/_LO nets carry ANY
        locked track (a stamped blueprint cell, force rails, or precision-locked copper)
        gets ONLY the textbook shape (_canonical_tap_path: perpendicular off the inner
        edge, one 90, land on the IN pad) -- the straight-diagonal / dogleg / vbus-bridge
        fallbacks are REMOVED for that pair; a blocked canonical REFUSES LOUDLY with the
        blocking item NAMED (_tap_leg_collider) so the pour/placement rung fixes the real
        conflict. No 45-degree segments, no side exits on a stamped cell.
      * LEGACY LADDER PRESERVED where the pair's nets carry NO locked copper (the eps
        golden path: floorplan has 0 tracks, FR output is unlocked) -- canonical ->
        straight -> bent -> vbus bridge, byte-identical behavior."""
    from collections import defaultdict
    names = {n.GetNetname() for n in board.GetNetInfo().NetsByNetcode().values() if n.GetNetname()}
    if kelvin_pairs is None:
        kelvin_pairs = _board_kelvin_pairs(board)
    force_nets = {n for pr in kelvin_pairs for n in pr}
    # all _HI/_LO Kelvin codes -- foreign-copper guard treats none of these as foreign (the partner
    # sense leg is legitimately adjacent; a real HI<->LO short is caught by DRC + the hardened gate).
    sense_codes = {board.GetNetcodeFromNetname(n) for n in force_nets}

    pads_by_net = defaultdict(list)                            # net -> [(ref, pad, fp)]
    padcount = {}
    for fp in board.GetFootprints():
        padcount[fp.GetReference()] = fp.GetPadCount()
        for p in fp.Pads():
            nn = p.GetNetname()
            if nn in force_nets:
                pads_by_net[nn].append((fp.GetReference(), p, fp))

    f_cu = board.GetLayerID(layer)
    if f_cu < 0:
        raise KeyError(f"cec_fr.synthesize_kelvin_taps: layer {layer!r} not found")
    clr_nm = _nm(clearance)
    laid, report, refused, refused_details, covered = [], {}, {}, [], {}
    pending = []                                              # decide-then-lay: guard sees no in-call taps

    def future_power_clear(path, net, layer_id):
        return not _tap_reservation_hits(
            path, avoid, net=net, layer=board.GetLayerName(layer_id),
            width_nm=_nm(width), clearance_nm=clr_nm, limit=1)

    def record_path_refusal(*, net, reason, source_ref, target_ref,
                            target_pad, source_position, tap_start,
                            target_position, mode, attempts,
                            inward_vector=None):
        blockers = []
        for attempt in attempts:
            for blocker in attempt.get("blocked_legs") or ():
                blockers.append({
                    **blocker,
                    "path_kind": str(attempt.get("path_kind") or ""),
                })
        row = {
            "net": str(net), "reason": str(reason),
            "reason_kind": "kelvin_path_blocked",
            "mode": str(mode),
            "source_ref": str(source_ref),
            "target_ref": str(target_ref),
            "target_pad": str(target_pad),
            "source_position_mm": [
                round(source_position.x / MM, 6),
                round(source_position.y / MM, 6)],
            "tap_start_position_mm": [
                round(tap_start.x / MM, 6),
                round(tap_start.y / MM, 6)],
            "target_position_mm": [
                round(target_position.x / MM, 6),
                round(target_position.y / MM, 6)],
            "current_distance_mm": round(math.hypot(
                (target_position.x - source_position.x) / MM,
                (target_position.y - source_position.y) / MM), 6),
            "max_distance_mm": round(float(max_ic_mm), 6),
            "width_mm": round(float(width), 6),
            "clearance_mm": round(float(clearance), 6),
            "path_attempts": list(attempts),
            "blocker_refs": sorted({
                str(row.get("ref")) for row in blockers
                if row.get("ref")}),
            "blocker_details": blockers,
        }
        if (isinstance(inward_vector, (list, tuple))
                and len(inward_vector) >= 2):
            ux, uy = float(inward_vector[0]), float(inward_vector[1])
            row["inward_vector"] = [round(ux, 9), round(uy, 9)]
            row["target_inward_mm"] = round(
                ((target_position.x - tap_start.x) / MM) * ux
                + ((target_position.y - tap_start.y) / MM) * uy, 6)
            row["canonical_min_inward_mm"] = 0.3
        refused_details.append(row)

    for hi, lo in kelvin_pairs:
        # the shunt is the footprint straddling BOTH halves with EXACTLY 2 pads (same test as
        # derive_power_pours -- a differential INA is multi-pad and so excluded).
        refs_hi = {r for r, _, _ in pads_by_net.get(hi, [])}
        refs_lo = {r for r, _, _ in pads_by_net.get(lo, [])}
        shunt_refs = {r for r in (refs_hi & refs_lo) if padcount.get(r, 0) == 2}
        if not shunt_refs:
            continue
        sh = sorted(shunt_refs)[0]
        # PER-SIDE (dual-sided boards, 2026-07-08): a back-side rail chain's taps lay on
        # B.Cu -- keyed off the SHUNT footprint's face (the chain shares it by invariant).
        sh_fp = next((f for r, _p, f in pads_by_net.get(hi, []) if r == sh), None)
        lay_id = board.GetLayerID("B.Cu") if (sh_fp is not None and sh_fp.IsFlipped()) else f_cu
        # LOCKED-COPPER MODE (the 2026-07-25 discipline): any locked track on this pair's
        # nets marks stamped-cell / rails / precision territory -- covered legs are
        # skipped, uncovered legs go canonical-or-refuse. Empty on the golden/legacy path.
        locked_pair_tracks = [t for t in board.GetTracks()
                              if t.GetClass() == "PCB_TRACK" and t.IsLocked()
                              and t.GetNetname() in (hi, lo)]
        locked_mode = bool(locked_pair_tracks)
        sh_pad = {}
        for net in (hi, lo):
            for r, p, _fp in pads_by_net.get(net, []):
                if r == sh:
                    sh_pad[net] = p
        if hi not in sh_pad or lo not in sh_pad:
            continue
        hi_pos = sh_pad[hi].GetPosition()
        lo_pos = sh_pad[lo].GetPosition()
        for net, this_pad, other_pos, role in ((hi, sh_pad[hi], lo_pos, "HI"),
                                               (lo, sh_pad[lo], hi_pos, "LO")):
            pc = this_pad.GetPosition()
            # inset the start a hair inside the pad so the endpoint connects to the pad copper
            # even as a lone arm (the sibling INA tap may be guard-refused -> no shared junction).
            psz = this_pad.GetSize()
            reach = math.hypot(psz.x / MM, psz.y / MM) / 2.0
            tx, ty, _ux, _uy = _inner_edge_pt(this_pad, other_pos, inset_mm=min(0.12, reach * 0.25))
            S = pcbnew.VECTOR2I(_nm(tx), _nm(ty))
            nc = board.GetNetcodeFromNetname(net)
            # each seated current-sense IC's input pad on THIS net, chosen by PIN FUNCTION
            # (HI->IN+, LO->IN-) -- not nearest-by-distance (defence 1). INA238/228 + the §6.13
            # INA181 detection amp both tap the shunt. A recognised input
            # beyond max_ic_mm is a placement refusal: broad routing excludes
            # the pad, so silently skipping it would guarantee an open circuit.
            ic_pad = {}                                       # ref -> pad (the IN+/IN- pad)
            ic_fp = {}                                        # ref -> footprint
            for r, p, fp in pads_by_net.get(net, []):
                if r == sh or "INA" not in (fp.GetValue() or "").upper():
                    continue
                want = _sense_in_pad(fp, role)
                if want is not None and p.GetPadName() != want:
                    continue                                  # not the IN+/IN- pad of a known part
                d = math.hypot((p.GetPosition().x - pc.x) / MM, (p.GetPosition().y - pc.y) / MM)
                if d > max_ic_mm:
                    if want is not None and p.GetPadName() == want:
                        reason = (
                            "%s->%s.%s OUT-OF-RANGE: %.3fmm > %.3fmm"
                            % (sh, r, p.GetPadName(), d,
                               float(max_ic_mm)))
                        refused.setdefault(net, []).append(reason)
                        refused_details.append({
                            "net": net, "reason": reason,
                            "source_ref": sh, "target_ref": r,
                            "target_pad": p.GetPadName(),
                            "source_position_mm": [
                                round(pc.x / MM, 6),
                                round(pc.y / MM, 6)],
                            "target_position_mm": [
                                round(p.GetPosition().x / MM, 6),
                                round(p.GetPosition().y / MM, 6)],
                            "current_distance_mm": round(d, 6),
                            "max_distance_mm": round(
                                float(max_ic_mm), 6),
                            "required_closer_mm": round(
                                d - float(max_ic_mm), 6),
                        })
                    continue
                ic_fp[r] = fp
                if r not in ic_pad:
                    ic_pad[r] = p
                else:                                         # unknown part: keep the nearest sense pad
                    d0 = math.hypot((ic_pad[r].GetPosition().x - pc.x) / MM,
                                    (ic_pad[r].GetPosition().y - pc.y) / MM)
                    if d < d0:
                        ic_pad[r] = p
            for r, p in sorted(ic_pad.items()):
                T = p.GetPosition()
                lbl = "%s->%s.%s" % (sh, r, p.GetPadName())
                # COVERED-LEG SKIP (2026-07-25 discipline): this input pad already
                # carries LOCKED same-net tap copper (the stamped cell's authored tap
                # or a precision pre-FR tap) -- never lay a second tap on it. The
                # per-LEG grain (not per-pair) means a partially-covered pair still
                # gets its missing legs handled without doubling the present ones.
                if _locked_pad_contact(board, p, tracks=locked_pair_tracks):
                    covered.setdefault(net, []).append(lbl + " (locked tap present)")
                    continue
                # CANONICAL FIRST (owner 2026-07-08): the textbook datasheet tap --
                # perpendicular off the inner edge, straight run inward, ONE 90 toward
                # the sense IC. Preferred over the direct diagonal whenever it guards
                # clean; falls through to straight, then doglegs, then refusal.
                _gap = math.hypot((other_pos.x - pc.x) / MM, (other_pos.y - pc.y) / MM)
                canon = _canonical_tap_path(S, T, _ux, _uy, gap_mm=_gap)
                canon_pending = (
                    _tap_pending_collider(
                        canon, nc, lay_id, pending, _nm(width), clr_nm)
                    if canon is not None else None)
                if canon is not None:
                    legs = list(zip(canon, canon[1:]))
                    if all(a != b for a, b in legs) and \
                       all(_tap_foreign_clear(board, a, b, _nm(width), lay_id, clr_nm,
                                              sense_codes) and
                           _tap_pair_overlap_clear(board, a, b, _nm(width), lay_id, nc,
                                                   sense_codes)
                           for a, b in legs) and not canon_pending \
                            and future_power_clear(canon, net, lay_id):
                        pending.append((canon, nc, net, lbl + " (canonical)", lay_id))
                        continue
                if locked_mode:
                    # CANONICAL-OR-REFUSE (owner ruling 2026-07-25): on a pair with
                    # locked copper (stamped cell / rails / precision) the diagonal
                    # and dogleg fallbacks are REMOVED -- refuse LOUDLY, naming the
                    # blocking item so the pour/placement rung fixes the real
                    # conflict instead of this pass papering over it with bent
                    # copper on the owner's shunt-zoom renders.
                    attempt = _tap_path_refusal_certificate(
                        board, canon, _nm(width), lay_id, clr_nm,
                        sense_codes, nc, path_kind="canonical",
                        pending=pending, reservations=avoid,
                        own_net=net)
                    if canon is None:
                        why = ("no canonical geometry (IC not inward of the shunt "
                               "pad's inner edge)")
                    else:
                        why = (attempt.get("reason") or canon_pending or
                               "canonical leg blocked (collider unresolved)")
                    reason = lbl + " CANONICAL-REFUSED: " + why
                    refused.setdefault(net, []).append(reason)
                    record_path_refusal(
                        net=net, reason=reason, source_ref=sh,
                        target_ref=r, target_pad=p.GetPadName(),
                        source_position=pc, tap_start=S,
                        target_position=T, mode="canonical_locked",
                        attempts=[attempt], inward_vector=(_ux, _uy))
                    continue
                # GUARD (defence 2): refuse rather than lay a stub that clips foreign copper.
                if (_tap_foreign_clear(
                        board, S, T, _nm(width), lay_id, clr_nm, sense_codes)
                        and not _tap_pending_collider(
                            [S, T], nc, lay_id, pending,
                            _nm(width), clr_nm)
                        and future_power_clear([S, T], net, lay_id)):
                    pending.append(([S, T], nc, net, lbl, lay_id))
                    continue
                # BENT-TAP FALLBACK (the ina238-lo-tap-refusal fix, 2026-07-07): the INA238's
                # IN-(pad 9) sits mid-column with GND(7)/SDA(6) below it, so the straight stub
                # from the LO inner edge clips the IC's OWN foreign pads. Try orthogonal
                # doglegs down the open notch; EVERY leg must pass BOTH the foreign-clearance
                # guard AND the different-sense-net overlap guard (a bent LO leg must never
                # cross the shunt's HI pad, which the foreign guard deliberately ignores).
                # Still via-free single-layer F.Cu (§6.8) -- only the shape bends.
                bent = None
                dogleg_paths = _dogleg_candidates(S, T)
                for path in dogleg_paths:
                    legs = list(zip(path, path[1:]))
                    if all(a != b for a, b in legs) and \
                       all(_tap_foreign_clear(board, a, b, _nm(width), lay_id, clr_nm,
                                              sense_codes) and
                           _tap_pair_overlap_clear(board, a, b, _nm(width), lay_id, nc,
                                                   sense_codes)
                           for a, b in legs) and not _tap_pending_collider(
                               path, nc, lay_id, pending,
                               _nm(width), clr_nm) \
                            and future_power_clear(path, net, lay_id):
                        bent = path
                        break
                if bent is not None:
                    pending.append((bent, nc, net, lbl + " (bent)", lay_id))
                else:
                    refused.setdefault(net, []).append(lbl)
                    attempts = [_tap_path_refusal_certificate(
                        board, canon, _nm(width), lay_id, clr_nm,
                        sense_codes, nc, path_kind="canonical",
                        pending=pending, reservations=avoid,
                        own_net=net)]
                    attempts.append(_tap_path_refusal_certificate(
                        board, [S, T], _nm(width), lay_id, clr_nm,
                        sense_codes, nc, path_kind="straight",
                        pending=pending, include_sense=False,
                        reservations=avoid, own_net=net))
                    attempts.extend(_tap_path_refusal_certificate(
                        board, path, _nm(width), lay_id, clr_nm,
                        sense_codes, nc, path_kind="dogleg-%02d" % index,
                        pending=pending, reservations=avoid,
                        own_net=net)
                        for index, path in enumerate(dogleg_paths))
                    record_path_refusal(
                        net=net, reason=lbl, source_ref=sh,
                        target_ref=r, target_pad=p.GetPadName(),
                        source_position=pc, tap_start=S,
                        target_position=T, mode="legacy_ladder",
                        attempts=attempts, inward_vector=(_ux, _uy))
            # VBUS BRIDGE: the INA238/228 ties Vbus (pad 8) to the SAME LO net as IN- (pad 9),
            # 0.5mm below it INSIDE the reserved tap channel -- FR is kept out of the channel,
            # so bridge the two same-net pads with a stub here (what a hand layout does). Only
            # for the LO role of a recognised part, only when both pads are on this net.
            # LOCKED-COPPER pairs get NO bridge (2026-07-25 discipline: no vbus-bridge shapes
            # on a stamped cell -- pad 8 is a high-Z tap FR routes normally, it was never
            # excluded from the DSN, see kelvin_sense_pins).
            if role == "LO" and not locked_mode:
                for r, p in sorted(ic_pad.items()):
                    fp9 = ic_fp.get(r)
                    if fp9 is None or _sense_in_pad(fp9, "LO") != p.GetPadName():
                        continue                       # unknown part -- no pin-function map
                    vb = next((q for q in fp9.Pads()
                               if q.GetPadName() == "8" and q.GetNetname() == net), None)
                    if vb is None:
                        continue
                    A, B = p.GetPosition(), vb.GetPosition()
                    if (_tap_pair_overlap_clear(
                            board, A, B, _nm(width), lay_id, nc,
                            sense_codes)
                            and future_power_clear([A, B], net, lay_id)):
                        pending.append(([A, B], nc, net,
                                        "%s.9->%s.8 (vbus bridge)" % (r, r), lay_id))
    # Coalesce covered in-call legs before they become locked copper.  A shunt
    # may feed two monitor ICs on the same terminal; decide-then-lay correctly
    # keeps one candidate from blocking another, but historically emitted their
    # identical/collinear launch legs twice.  Connectivity and DRC both passed,
    # leaving a connected pseudo-stub/backtrack at the shared launch.  Keep the
    # longest collinear segment and drop only segments whose complete copper is
    # already covered on the same net/layer.  Endpoint-on-interior remains a
    # valid physical connection and is independently checked by the Kelvin gate.
    planned = []
    for path, nc, net, lbl, p_lay in pending:
        report.setdefault(net, []).append(lbl)
        for A, B in zip(path, path[1:]):
            if A != B:
                planned.append((A, B, nc, net, p_lay, lbl))

    def _covered_by(candidate, survivor):
        A, B, nc, _net, layer_id, _lbl = candidate
        C, D, snc, _snet, slayer, _slbl = survivor
        if nc != snc or layer_id != slayer:
            return False
        vx, vy = D.x - C.x, D.y - C.y
        if vx == 0 and vy == 0:
            return False
        for P in (A, B):
            if vx * (P.y - C.y) - vy * (P.x - C.x) != 0:
                return False
            dot = (P.x - C.x) * vx + (P.y - C.y) * vy
            if dot < 0 or dot > vx * vx + vy * vy:
                return False
        return True

    planned.sort(key=lambda row: (
        -((row[1].x - row[0].x) ** 2 + (row[1].y - row[0].y) ** 2),
        row[3], row[4], row[0].x, row[0].y, row[1].x, row[1].y, row[5]))
    survivors = []
    for segment in planned:
        if any(_covered_by(segment, present) for present in survivors):
            continue
        survivors.append(segment)

    # lay the guarded taps (after all decisions, so the guard never saw an in-call tap)
    for A, B, nc, _net, p_lay, _lbl in survivors:
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(A)
            t.SetEnd(B)
            t.SetWidth(_nm(width))
            t.SetLayer(p_lay)
            t.SetNetCode(nc)
            board.Add(t)
            laid.append(t)
    return {"taps": sum(len(v) for v in report.values()),
            "by_net": report, "refused": refused,
            "refused_details": refused_details, "covered": covered,
            "segments": len(laid),
            "segments_pruned": len(planned) - len(survivors),
            "future_power_reservation_count": len(avoid or ())}


def tap_channel_keepouts(board_path, *, kelvin_pairs=None, board=None, margin=0.25,
                         pad_clear=0.35, max_ic_mm=9.0):
    """Route-time F.Cu TAP-CHANNEL keepout -- the ENFORCE leg of "the inner-tap channel is CLEAR".

    The §6.8 four-wire Kelvin tap (:func:`synthesize_kelvin_taps`) is a straight F.Cu stub from each
    2-pad shunt's INNER edge to each seated current-sense IC input pad. It is laid AFTER the route and
    REFUSES itself rather than plough through foreign copper -- so when pass-1 Freerouting routes a
    TRANSITING foreign signal (a comparator output /DETC*, +3V3, I2C ...) across the notch at the tap
    height, the tap is correctly left UNCONNECTED and kelvin_ok=False (the placement looks congested even
    when it is geometrically clean). This reserves each tap's own channel as a Freerouting keepout on F.Cu
    ONLY, so FR routes that transiting foreign AROUND the channel (or vias it DOWN to B.Cu, which does not
    clip the F.Cu tap) -- pass-1 then lays the taps -> kelvin_ok -> the two-pass corridor / route-under can
    clean the remaining foreign-on-pour. Distinct from :func:`corridor_keepouts`, which reserves the HI/LO
    POUR boxes but deliberately leaves the notch (where the taps live) OPEN.

    ONE box PER TAP (shunt inner-edge -> IN pad), the segment bounding box inflated by *margin*, then
    each box edge is CLIPPED inward to stay *pad_clear* mm clear of any FOREIGN-net pad it would otherwise
    cover (the INA's own +3V3/GND/I2C pads, ~0.5mm pitch in the column): the smaller inward clip per
    offending pad. The shunt pad and the IN pad are same-net (never clipped), so the box reaches the IN
    pad and reserves the full channel a transiting foreign would clip, while the IC's foreign pads stay
    routable. F.Cu only (a B.Cu crossing does not clip the F.Cu tap and is the desired escape), allow_vias
    True, block_fills False (the same-net SENSEC pour is not in the notch). SELF-GATING: no 2-pad straddle
    shunt / no INA input pad within max_ic_mm -> []. Returns bake_hints dicts."""
    board = board if board is not None else pcbnew.LoadBoard(board_path)
    names = {n.GetNetname() for n in board.GetNetInfo().NetsByNetcode().values() if n.GetNetname()}
    if kelvin_pairs is None:
        kelvin_pairs = _board_kelvin_pairs(board)
    force_nets = {n for pr in kelvin_pairs for n in pr}
    from collections import defaultdict
    pads_by_net = defaultdict(list)
    padcount = {}
    foreign_pads = []                                          # (x, y, halfx, halfy) of every non-sense pad
    for fp in board.GetFootprints():
        padcount[fp.GetReference()] = fp.GetPadCount()
        for p in fp.Pads():
            nn = p.GetNetname()
            if nn in force_nets:
                pads_by_net[nn].append((fp.GetReference(), p, fp))
            else:
                pp = p.GetPosition(); sz = p.GetSize()
                foreign_pads.append((pp.x / MM, pp.y / MM, sz.x / MM / 2.0, sz.y / MM / 2.0))

    def _clip_foreign(x0, y0, x1, y1):
        """Shrink the box edges inward so no foreign pad sits within pad_clear of the box interior."""
        for px, py, hx, hy in foreign_pads:
            pax0, pax1 = px - hx - pad_clear, px + hx + pad_clear
            pay0, pay1 = py - hy - pad_clear, py + hy + pad_clear
            if pax1 <= x0 or pax0 >= x1 or pay1 <= y0 or pay0 >= y1:
                continue                                        # pad (inflated) doesn't intrude the box
            # minimal inward clip among the 4 edges that removes the overlap
            cands = []
            if pax1 < x1:
                cands.append(("x0", pax1, pax1 - x0))
            if pax0 > x0:
                cands.append(("x1", pax0, x1 - pax0))
            if pay1 < y1:
                cands.append(("y0", pay1, pay1 - y0))
            if pay0 > y0:
                cands.append(("y1", pay0, y1 - pay0))
            if not cands:
                return None                                     # pad spans the whole box -> degenerate
            edge, val, _cost = min(cands, key=lambda c: c[2])
            if edge == "x0":
                x0 = val
            elif edge == "x1":
                x1 = val
            elif edge == "y0":
                y0 = val
            else:
                y1 = val
            if x1 - x0 < 0.3 or y1 - y0 < 0.3:
                return None
        return (x0, y0, x1, y1)

    hints = []
    for hi, lo in kelvin_pairs:
        refs_hi = {r for r, _, _ in pads_by_net.get(hi, [])}
        refs_lo = {r for r, _, _ in pads_by_net.get(lo, [])}
        shunt_refs = {r for r in (refs_hi & refs_lo) if padcount.get(r, 0) == 2}
        if not shunt_refs:
            continue
        sh = sorted(shunt_refs)[0]
        # PER-SIDE (dual-sided): a back-side chain's tap channel reserves B.Cu, not F.Cu
        sh_fp2 = next((f for r, _p, f in pads_by_net.get(hi, []) if r == sh), None)
        sh_pad = {}
        for net in (hi, lo):
            for r, p, _fp in pads_by_net.get(net, []):
                if r == sh:
                    sh_pad[net] = p
        if hi not in sh_pad or lo not in sh_pad:
            continue
        hi_pos, lo_pos = sh_pad[hi].GetPosition(), sh_pad[lo].GetPosition()
        for net, this_pad, other_pos, role in ((hi, sh_pad[hi], lo_pos, "HI"),
                                               (lo, sh_pad[lo], hi_pos, "LO")):
            pc = this_pad.GetPosition()
            tx, ty, _ux, _uy = _inner_edge_pt(this_pad, other_pos, inset_mm=0.0)
            for r, p, fp in pads_by_net.get(net, []):
                if r == sh or "INA" not in (fp.GetValue() or "").upper():
                    continue
                want = _sense_in_pad(fp, role)
                if want is not None and p.GetPadName() != want:
                    continue
                pp = p.GetPosition()
                if math.hypot((pp.x - pc.x) / MM, (pp.y - pc.y) / MM) > max_ic_mm:
                    continue
                ix, iy = pp.x / MM, pp.y / MM
                box = (min(tx, ix) - margin, min(ty, iy) - margin,
                       max(tx, ix) + margin, max(ty, iy) + margin)
                clipped = _clip_foreign(*box)
                if clipped is None:
                    continue
                x0, y0, x1, y1 = clipped
                hints.append({"name": f"tap_{sh}_{r}", "x0": round(x0, 2), "y0": round(y0, 2),
                              "x1": round(x1, 2), "y1": round(y1, 2),
                              # Ownership is deliberately carried with the
                              # geometry.  Route keepout consumers ignore
                              # these extra fields, while the exact power
                              # planner uses them to block only FOREIGN rails:
                              # the matching sense pour may legally merge into
                              # its own Kelvin channel.
                              "net": net, "purpose": "future_kelvin_tap",
                              "source_ref": sh, "target_ref": r,
                              "layers": (("B.Cu",) if (sh_fp2 is not None and sh_fp2.IsFlipped())
                                          else ("F.Cu",)),
                              "allow_vias": False, "block_fills": False})
    return hints


# ---------------------------------------------------------------------------
# stagger_corridor_crossings -- the LAYER-TIER lever (route-time corridor fix)
# ---------------------------------------------------------------------------
# The cc=6 floor (placement-strategy CORE-PREMISE FINDING): on a cable board some foreign signals MUST
# cross the J_IN->shunt->J_OUT high-current corridor to reach the central ESP -- placement can't avoid
# it. Each crossing on an outer layer cuts that layer's 12V pour. The cable boards carry 12V on BOTH
# outers (GND on both inners), so the fix is to STAGGER the crossings across F.Cu vs B.Cu: no two cross
# at the same x on the same layer, so the un-cut outer pour mirror always carries the current past each
# single-layer cut (the additive F+B pours + via stitching from derive_power_pours/synthesize_power_
# copper then carry it). The placement-side corridor-evict lever clears a body-IN-band; THIS lever
# handles the unavoidable trace crossings -- the actual route-time fix.
def _corridor_foreign_net(net, corridor_nets, sense_nets):
    """A foreign net that, crossing a band, cuts the pour: not a corridor force net, not an INA sense
    net, not GND/a power rail (those legitimately pour/stitch). Mirrors cec_constraints._is_corridor_signal."""
    if not net or net in corridor_nets or net in sense_nets:
        return False
    base = net.rsplit("/", 1)[-1].upper()
    if base in ("GND",) or re.search(r"(^|/)\+?(3V3|5VSB|5V|12V|VBUS|VCC)$", net, re.I):
        return False
    if net.endswith(("_HI", "_LO")) or base.startswith(("SENSEC", "ISENSE")) or "unconnected-" in net.lower():
        return False
    return True


def _seg_band_clip(t, band):
    """Clip PCB_TRACE_T *t* against the band RECTANGLE [x0,x1]x[y0,y1] (Liang-Barsky). Returns
    (p_in_nm, p_out_nm, edge_in, edge_out) for the in-band portion, or None if the segment does not
    intersect the band. ``edge_in``/``edge_out`` are True when that clip endpoint is a real band-boundary
    crossing (the segment continues OUTSIDE the band there, so a layer transition + via is needed) and
    False when it is the segment's own endpoint sitting INSIDE the band (no transition).

    Unlike the old _seg_crosses_band (which required ONE segment to span the whole band x-width), this
    flags ANY segment with copper inside the band -- so an L-bend / 45-degree route whose crossing is
    realised by several short segments is detected, not silently missed (the audit's "83% of real
    crossings missed -> flipped=0 live")."""
    x0, x1, y0, y1 = band
    s, e = t.GetStart(), t.GetEnd()
    sx, sy = s.x / MM, s.y / MM
    dx, dy = e.x / MM - sx, e.y / MM - sy
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, sx - x0), (dx, x1 - sx), (-dy, sy - y0), (dy, y1 - sy)):
        if abs(p) < 1e-12:                                  # segment parallel to this edge
            if q < 0:
                return None                                 # wholly outside this edge
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return None
            if r > t0:
                t0 = r
        else:
            if r < t0:
                return None
            if r < t1:
                t1 = r
    if t1 - t0 < 1e-9:                                       # only grazes a corner -> not a crossing
        return None
    p_in = (int(round((sx + dx * t0) * MM)), int(round((sy + dy * t0) * MM)))
    p_out = (int(round((sx + dx * t1) * MM)), int(round((sy + dy * t1) * MM)))
    return (p_in, p_out, t0 > 1e-9, t1 < 1.0 - 1e-9)


def _relayer_segment_inband(board, t, clip, target_layer, *, drill=0.3, dia=0.6):
    """Move the IN-BAND portion of track *t* (clip = the _seg_band_clip tuple) onto *target_layer*,
    leaving any out-of-band portion on the original layer and adding a transition via at each real
    band-boundary crossing so the net stays connected. *t* itself becomes the in-band (target-layer)
    piece. Returns the list of added objects (0..4: up to a before-seg+via and an after-seg+via).

    Generalises the old _flip_crossing (which handled only the both-ends-outside full-span case) to
    every case: fully-inside (just re-layer, no via -- its neighbours carry the transition), straddling
    one edge (one via), and spanning the band (two vias)."""
    p_in_xy, p_out_xy, edge_in, edge_out = clip
    nc, w, orig = t.GetNetCode(), t.GetWidth(), t.GetLayer()
    start = pcbnew.VECTOR2I(t.GetStart().x, t.GetStart().y)
    end = pcbnew.VECTOR2I(t.GetEnd().x, t.GetEnd().y)
    p_in, p_out = pcbnew.VECTOR2I(*p_in_xy), pcbnew.VECTOR2I(*p_out_xy)
    t.SetStart(p_in); t.SetEnd(p_out); t.SetLayer(target_layer)   # reuse t as the in-band middle piece
    added = []
    for (boundary, far, present) in ((p_in, start, edge_in), (p_out, end, edge_out)):
        if not present:
            continue                                        # the segment's own endpoint sits in-band
        seg = pcbnew.PCB_TRACK(board)
        seg.SetStart(boundary); seg.SetEnd(far); seg.SetWidth(w); seg.SetLayer(orig); seg.SetNetCode(nc)
        board.Add(seg); added.append(seg)
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(boundary); v.SetDrill(_nm(drill)); v.SetWidth(_nm(dia))
        v.SetLayerPair(orig, target_layer); v.SetNetCode(nc); board.Add(v); added.append(v)
    return added


def _rm_tmp_board(path):
    """Remove a temp board and every project sidecar created beside it."""
    base = path[:-len(".kicad_pcb")] if path.endswith(".kicad_pcb") else path
    for p in (path, base + ".kicad_pro", base + ".kicad_dru", base + ".kicad_prl",
              base + ".pourplan.json", base + ".railreport.json",
              base + ".pourfirst-state.json"):
        try:
            os.remove(p)
        except OSError:
            pass


def rebind_project_metadata(board_path):
    """Make a renamed board's project JSON identify its actual sibling path.

    KiCad project files preserve ``meta.filename`` across an ordinary file
    copy.  Route candidates are intentionally renamed many times, so leaving
    the old value binds later headless DRC/render steps to a stale project name
    and can silently orphan the matching custom-rule sidecar.
    """
    base = board_path[:-len(".kicad_pcb")] if board_path.endswith(".kicad_pcb") else board_path
    pro_path = base + ".kicad_pro"
    if not os.path.isfile(pro_path):
        return None
    with open(pro_path, encoding="utf-8") as fh:
        pro = json.load(fh)
    expected = os.path.basename(pro_path)
    if pro.setdefault("meta", {}).get("filename") != expected:
        pro["meta"]["filename"] = expected
        with open(pro_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(pro, fh, indent=2)
            fh.write("\n")
    return pro_path


def copy_project_sidecars(src_board, dst_board):
    """Copy all board-owned route sidecars with a renamed board.

    ``.pourplan.json`` is executable placement/routing ownership data, not a
    disposable report.  Dropping it while cec_router made a named candidate
    caused import to re-derive an empty plan and stranded the Hub power tree.
    Keep it beside every board copy just like the KiCad project/rule files.
    ``.railreport.json`` is retained as provenance/ranking evidence as well.
    ``.pourfirst-state.json`` is executable full-board current ownership: it
    must follow a renamed placement so resumed and independently derived route
    artifacts retain the same exact reservations instead of silently falling
    back to corridor guesses or refusing for missing authority.
    """
    src_base = src_board[:-len(".kicad_pcb")] if src_board.endswith(".kicad_pcb") else src_board
    dst_base = dst_board[:-len(".kicad_pcb")] if dst_board.endswith(".kicad_pcb") else dst_board
    copied = []
    for ext in (".kicad_pro", ".kicad_dru",
                ".pourplan.json", ".railreport.json",
                ".pourfirst-state.json"):
        src, dst = src_base + ext, dst_base + ext
        if os.path.isfile(src):
            if os.path.abspath(src) != os.path.abspath(dst):
                shutil.copy2(src, dst)
            copied.append(dst)
    rebind_project_metadata(dst_board)
    return copied


def stagger_corridor_crossings(board_path, out_path=None, *, verify=True, log=print):
    """LAYER-TIER lever (route-time): stagger the foreign signals that cross each formed high-current
    corridor band across F.Cu/B.Cu so the un-cut outer pour mirror always carries. Per band: collect the
    foreign crossing tracks, order by crossing-x, assign ALTERNATING target layers, and flip those not
    already on their target (split + transition vias). SAFE: if *verify*, the route QUALITY
    (_route_quality = structural DRC + unrouted ratlines + a hard-gate penalty) must not regress --
    otherwise the whole transform is REVERTED, staged via a temp board so an in-place call can never
    overwrite-then-fail-to-restore the original (panel G2/G5). This is safe to run in an overnight loop.
    Returns a report dict. Cable-board / formed-corridor only (shared-bus + degenerate bands yield an
    empty no-op)."""
    import cec_synth_pipeline as sp
    out_path = out_path or board_path
    # SAFE (panel G2): NEVER mutate the original board_path. Stagger a loaded copy, write it to a TEMP,
    # and only copy the temp onto out_path if it passes verify -- so an in-place call (out_path ==
    # board_path) can't overwrite-then-fail-to-restore (the old copy2(path,path) SameFileError crash).
    board = pcbnew.LoadBoard(board_path)
    model, _P = sp._board_corridor_model(board)
    bands = {c.base: c.band for c in model.cables if c.formed}
    sense = _sense_input_nets(board)
    report = {"bands": {}, "flipped": 0, "vias_added": 0, "reverted": False}
    if not bands:
        if out_path != board_path:
            shutil.copy2(board_path, out_path)
        return {**report, "note": "no formed cable corridor (shared-bus/degenerate) -- no-op"}
    for base, band in bands.items():
        x0, x1 = band[0], band[1]
        # Collect, per foreign net: its in-band clipped segments AND the x-extent of ALL its F/B copper.
        # NOTE: collection is read-only and FULLY completes before any board mutation below -- we hold the
        # track refs and never re-call GetTracks() mid-mutation (the re-proxied-ids SWIG footgun).
        by_net = {}                                          # net -> [(track, clip), ...]
        spans = {}                                           # net -> (min endpoint x, max endpoint x) mm
        inband_pts = {}                                      # net -> set of in-band clip endpoints (nm)
        outband_pts = {}                                     # net -> {endpoint (nm): layer} of out-of-band segs
        for t in board.GetTracks():
            if t.Type() != pcbnew.PCB_TRACE_T or t.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu):
                continue
            n = t.GetNetname()
            if not _corridor_foreign_net(n, model.corridor_nets, sense):
                continue
            sx, ex = t.GetStart().x / MM, t.GetEnd().x / MM
            lo, hi = spans.get(n, (1e18, -1e18))
            spans[n] = (min(lo, sx, ex), max(hi, sx, ex))
            clip = _seg_band_clip(t, band)
            if clip:
                by_net.setdefault(n, []).append((t, clip))
                inband_pts.setdefault(n, set()).update((clip[0], clip[1]))  # post-relayer target endpoints
            else:
                d = outband_pts.setdefault(n, {})
                d[(t.GetStart().x, t.GetStart().y)] = t.GetLayer()
                d[(t.GetEnd().x, t.GetEnd().y)] = t.GetLayer()
        # A net CROSSES the band only if it has in-band copper AND its routed copper reaches BOTH x-sides
        # of the band (so it severs the pour across the corridor, rather than merely dipping in). L-bend
        # routes qualify now because the test is on the net's whole x-extent, not one spanning segment.
        crossers = {n: segs for n, segs in by_net.items()
                    if spans[n][0] < x0 and spans[n][1] > x1}
        # Order by leftmost in-band entry x and ALTERNATE target layer so no two cross at the same x on
        # the same layer -> the un-cut outer pour mirror always carries past each single-layer cut.
        for i, n in enumerate(sorted(crossers, key=lambda nn: min(c[1][0][0] for c in crossers[nn]))):
            target = pcbnew.F_Cu if i % 2 == 0 else pcbnew.B_Cu
            flipped_any = False
            via_pts = set()                                  # nm points where _relayer already placed a via
            for t, clip in crossers[n]:
                if t.GetLayer() != target:
                    added = _relayer_segment_inband(board, t, clip, target)
                    for o in added:
                        if o.Type() == pcbnew.PCB_VIA_T:
                            report["vias_added"] += 1
                            via_pts.add((o.GetPosition().x, o.GetPosition().y))
                    flipped_any = True
            if flipped_any:
                report["flipped"] += 1
                # CONNECTIVITY REPAIR (re-audit finding 1): the per-segment edge-via rule misses a via where
                # a relayered (now target-layer) segment's endpoint coincides with an out-of-band segment's
                # endpoint on the OTHER layer (e.g. a fully-in-band segment ending exactly on the band edge,
                # meeting an unclipped out-of-band neighbour) -> the net would be severed. Add the missing
                # target<->other transition via at every such point not already vianed.
                nc = board.FindNet(n).GetNetCode()
                for pt, oly in outband_pts.get(n, {}).items():
                    if oly != target and pt in inband_pts.get(n, set()) and pt not in via_pts:
                        v = pcbnew.PCB_VIA(board)
                        v.SetPosition(pcbnew.VECTOR2I(*pt)); v.SetDrill(_nm(0.3)); v.SetWidth(_nm(0.6))
                        v.SetLayerPair(target, oly); v.SetNetCode(nc); board.Add(v)
                        via_pts.add(pt); report["vias_added"] += 1
        report["bands"][base] = len(crossers)
    # RE-FILL after moving crossings (UnFill-first, like add_power_pours -- a double-fill in one process
    # can segfault this SWIG build). Re-fills ALL zones (the real "Fill All Zones"); for the unchanged
    # GND/12V planes this is idempotent (they were already filled by import_ses / synthesize_power_copper),
    # but it HEALS the force pours around the new geometry: the F.Cu pour reclaims the clearance hole the
    # now-departed foreign track left, and the B.Cu mirror re-carves clearance around the track moved onto
    # it (otherwise the moved track would short the stale B.Cu fill). Without this the stagger moves copper
    # but never updates the pours, so it is inert (the audit's "useless"). Only when something flipped.
    if not report["flipped"]:
        # Nothing changed -> ship the EXACT original bytes (no pcbnew re-serialize churn / version-stamp).
        del board
        if out_path != board_path:
            shutil.copy2(board_path, out_path)
        return report
    for z in board.Zones():
        z.UnFill()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    _fd, tmp = tempfile.mkstemp(suffix=".kicad_pcb", prefix="cec_stagger_", dir=_TMP)
    os.close(_fd)                                          # don't leak the mkstemp fd (cec_score does this too)
    pcbnew.SaveBoard(tmp, board)
    del board
    if verify:
        pre, pre_u, _ = _route_quality_detail(board_path)        # original vs staggered
        post, post_u, _ = _route_quality_detail(tmp)
        # Revert if the staggered board is worse on the aggregate, OR opens ANY new ratline (post_u > pre_u
        # -- a net disconnect, which a drc/heal improvement must never be allowed to mask, re-audit finding
        # 2), OR cannot be scored at all (+inf). An unverifiable or connectivity-regressing transform must
        # never ship over the original.
        if post > pre or post_u > pre_u or not math.isfinite(post):
            if out_path != board_path:
                shutil.copy2(board_path, out_path)
            _rm_tmp_board(tmp)
            report.update(reverted=True, q_pre=pre, q_post=post, unconn_pre=pre_u, unconn_post=post_u,
                          flipped=0, vias_added=0)
            log(f"[cec_fr] stagger reverted: quality {pre}->{post} unconnected {pre_u}->{post_u} "
                f"(kept the un-staggered route)")
            return report
    shutil.copy2(tmp, out_path)                            # accept the staggered board
    _rm_tmp_board(tmp)
    return report


def _sense_input_nets(board):
    """Nets at an INA current-sense input pin (the Kelvin/post-filter sense) -- exempt from staggering."""
    out = set()
    for fp in board.GetFootprints():
        if "INA2" not in (fp.GetValue() or "").upper():
            continue
        for pad in fp.Pads():
            nu = (pad.GetNetname() or "")
            if nu and nu.upper().endswith(("_HI", "_LO", "_P", "_N")):
                out.add(nu)
    return out


def _route_quality_detail(board_path):
    """(scalar, unconnected, gates_ok) for the stagger safe-revert. The scalar combines structural DRC +
    unrouted ratlines + a hard-gate (Kelvin/diff-pair) penalty (LOWER is better). The ``unconnected``
    count is returned SEPARATELY because the scalar alone is not safe: the post-flip re-fill can LOWER drc
    while a flip RAISES unconnected (a net disconnect), and the two would net out -- so the caller must
    veto on any unconnected increase independently of the scalar (re-audit 2026-06-14, finding 2). A
    measurement FAILURE returns (+inf, +inf, False) -- the worst on every axis, so an unscoreable result
    is never accepted over the original board (the old `except: return 0` masked errors as a perfect
    score)."""
    try:
        import cec_score
        m = cec_score.score(board_path)
        gates_ok = bool(m.kelvin_ok and m.diffpair_ok)
        return float(m.drc + m.unconnected + (0 if gates_ok else 10_000)), int(m.unconnected), gates_ok
    except Exception:
        return float("inf"), float("inf"), False


def _route_quality(board_path):
    """Scalar form of :func:`_route_quality_detail` (see there). LOWER is better; +inf on a measurement
    failure. Used where only the aggregate matters (e.g. the purely-additive mirror-pour adoption guard,
    where unconnected can only fall)."""
    return _route_quality_detail(board_path)[0]


# ---------------------------------------------------------------------------
# synthesize_power_copper -- the high-current copper SYNTHESIZER (not a router)
# ---------------------------------------------------------------------------
def synthesize_power_copper(board_path, out_path, *, pour_layers=("F.Cu", "B.Cu"),
                            via_per_net=16, via_drill=0.5, via_dia=0.9, via_pitch=1.0,
                            strip_redundant=True, kelvin_pairs=None):
    """SYNTHESIZE fab-grade high-current copper for the cable force path -- construct it to spec, don't
    autoroute-then-patch it. Freerouting models a 40A net as a 0.2mm wire; the right object is a copper
    POUR + via field. For each cable FORCE net (J_IN->shunt = *_HI, shunt->J_OUT = *_LO) this lays a
    SOLID F.Cu+B.Cu MIRROR pour over the connector->shunt corridor (doubling the cross-section), stitched
    by a same-net VIA FIELD that carries the current between the two outer layers and through the shunt-
    terminal neck (the §6.7/OQ-10 via array); the four-wire Kelvin tap window (shunt inner edge -> INA,
    which derive_power_pours deliberately excludes) is left open.

    Runs AFTER Freerouting (purely ADDITIVE same-net copper, like add_power_pours -> never strands the
    sense tap). Then, BECAUSE the pour is now the solid conductor, it STRIPS the redundant thin force
    traces FR laid inside the pour (keeping the sense taps that exit it) -- so the zone carries the
    current, not the trace. Realises corpus rules high-current-copper-area-not-traces /
    -pour-on-outer-layers / high-current-via-stitch-spacing. Verify with cec_constraints
    (min-pour-cross-section) and cec_synth_pipeline.physics (electrothermal FEM). Returns a report dict.

    Pre-req: route the board WITH the force-corridor keepouts active (cec_router _vital_keepouts_from_
    rules) so both the F.Cu AND B.Cu corridors are clear -> both mirror layers fill solid."""
    from collections import defaultdict
    import shutil
    board = pcbnew.LoadBoard(board_path)
    # carry DRC context (.kicad_pro/.kicad_dru) next to the output board
    for ext in (".kicad_pro", ".kicad_dru"):
        s = board_path[:-len(".kicad_pcb")] + ext
        if os.path.isfile(s):
            shutil.copy2(s, out_path[:-len(".kicad_pcb")] + ext)
    names = {n.GetNetname() for n in board.GetNetInfo().NetsByNetcode().values() if n.GetNetname()}
    if kelvin_pairs is None:
        kelvin_pairs = _board_kelvin_pairs(board)
    force_nets = {n for pr in kelvin_pairs for n in pr}

    # Which pour layers each force net ALREADY carries (the router's pour-after-route lays a single F.Cu
    # pour). We ADD ONLY THE MISSING layer -- never REMOVE a zone (zone removal corrupts pcbnew's net info
    # -> SwigPyObject on the next GetNetInfo) and never double a layer (-> zones_intersect/isolated_copper).
    existing = defaultdict(set)
    for z in board.Zones():
        nn = z.GetNetname()
        if nn in force_nets:
            for L in pour_layers:
                if z.IsOnLayer(board.GetLayerID(L)):
                    existing[nn].add(L)

    base = derive_power_pours(board_path, kelvin_pairs=kelvin_pairs)
    fields = derive_via_field(board_path, per_net=via_per_net, drill=via_drill, dia=via_dia,
                              pitch=via_pitch, kelvin_pairs=kelvin_pairs)
    pours = [{**p, "layer": L, "priority": 2, "min_thickness": 0.25}
             for p in base for L in pour_layers if L not in existing[p["net"]]]
    added_zones = add_power_pours(board, pours, fill=False)
    added_vias = add_via_field(board, fields)
    # NOTE: the GENERATIVE four-wire Kelvin inner-edge tap (synthesize_kelvin_taps) is laid in the
    # ROUTE path (import_ses) on the SEATED board, NOT here. This force-copper synth runs on arbitrary
    # boards (incl. non-seated ones, e.g. cec_synth_pipeline.physics / the additive-mirror adoption
    # guard) where a direct inner-edge->IN+ stub would cross foreign copper -- the tap is only clean
    # when the IC is seated adjacent, which is exactly the route()/import_ses board. A physics-stage
    # board that came through route() already carries the tap.

    # 3. fill the mirror pours with the real engine (UnFill first -- re-fill segfault guard)
    for z in board.Zones():
        z.UnFill()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())

    # SAVE the solid-pour baseline (un-stripped) first -- if the strip below disconnects anything it
    # is REVERTED to exactly this.
    pcbnew.SaveBoard(out_path, board)

    # 4. strip the redundant FORCE traces the solid pour now carries (keep taps that exit the pour),
    # but ONLY if it does not disconnect the net. The pour can still have a fill-neck where a foreign
    # trace crosses it (-> two same-net islands the in-pour trace bridges); removing that bridge would
    # strand the net, so the strip is CONDITIONAL: revert the whole batch if unconnected count rises.
    stripped = 0
    strip_reverted = False
    if strip_redundant:
        board.BuildConnectivity()
        unc0 = board.GetConnectivity().GetUnconnectedCount(False)
        pour_polys = defaultdict(list)
        for z in board.Zones():
            if z.GetNetname() in force_nets:
                pour_polys[z.GetNetname()].append(z.Outline())
        remove = []
        for t in board.GetTracks():
            if t.Type() != pcbnew.PCB_TRACE_T:
                continue
            nm = t.GetNetname()
            if nm not in pour_polys:
                continue
            s, e = t.GetStart(), t.GetEnd()
            if all(any(poly.Contains(pt) for poly in pour_polys[nm]) for pt in (s, e)):
                remove.append(t)                       # both ends inside the same-net pour -> candidate
        if remove:
            for t in remove:
                board.Remove(t)
            for z in board.Zones():
                z.UnFill()
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
            board.BuildConnectivity()
            unc1 = board.GetConnectivity().GetUnconnectedCount(False)
            if unc1 <= unc0:                           # pour genuinely holds -> commit the strip
                stripped = len(remove)
                pcbnew.SaveBoard(out_path, board)
            else:                                       # a bridge -> keep the traces (out_path stays baseline)
                strip_reverted = True

    return {"out": out_path, "force_nets": sorted(force_nets), "mirror_pours": len(added_zones),
            "via_field": len(added_vias), "stripped_force_traces": stripped,
            "strip_reverted": strip_reverted}


# ---------------------------------------------------------------------------
# normalize_via_annular -- fix Freerouting's thin-annular vias
# ---------------------------------------------------------------------------
def normalize_track_width(board, *, tol_mm: float = 0.005) -> int:
    """Snap tracks that land a hair UNDER the board minimum width back onto it.

    Freerouting works on its own grid and the DSN/SES round-trip can return a
    track a fraction of a micron short: measured on the hub candidate, 5 of
    ~1900 tracks came back at 0.1998mm against a 0.2000mm minimum -- stubs as
    short as 12um, on /MAIN_5V_RAW and /USB_VBUS. Every one is a `track_width`
    DRC ERROR, so a 0.2um rounding artifact is a hard fab-gate blocker that no
    amount of reseeding clears.

    Only tracks already within *tol_mm* of the minimum are touched, and only
    upward to exactly the minimum: at 0.2um the change cannot create a
    clearance violation, while a blanket widen would (the same trap
    normalize_via_annular documents for via enlargement). A track genuinely
    thinner than the tolerance is left alone -- that is a real design fault and
    must stay visible. Returns the number of tracks repaired.
    """
    import pcbnew
    try:
        min_w = board.GetDesignSettings().m_TrackMinWidth / MM
    except Exception:                                      # noqa: BLE001
        return 0
    if min_w <= 0:
        return 0
    fixed = 0
    for t in board.GetTracks():
        if t.GetClass() != "PCB_TRACK":
            continue
        try:
            w = t.GetWidth() / MM
        except Exception:                                  # noqa: BLE001
            continue
        if w < min_w and (min_w - w) <= tol_mm:
            t.SetWidth(int(round(min_w * MM)))
            fixed += 1
    return fixed


def prune_degenerate_tracks(board, *, max_length_mm: float = 0.001) -> int:
    """Remove straight copper segments too short to carry geometry.

    DSN/SES coordinate quantization can emit a nominal ``PCB_TRACK`` whose
    endpoints differ by only a few nanometres.  Such an item cannot bridge two
    distinct connectivity clusters, but KiCad still expands its width for DRC
    and can report a real foreign-net clearance error at that point.  Limit the
    sanitizer to at most one micrometre by default; ordinary necks and stubs
    remain untouched and visible to the normal design gates.
    """
    limit = max(0.0, float(max_length_mm)) * MM
    removed = 0
    for item in list(board.GetTracks()):
        if item.GetClass() != "PCB_TRACK":
            continue
        try:
            start, end = item.GetStart(), item.GetEnd()
            length = math.hypot(end.x - start.x, end.y - start.y)
        except Exception:                                  # noqa: BLE001
            continue
        if length <= limit:
            board.Remove(item)
            removed += 1
    return removed


_BOARD_UUID_RE = re.compile(
    r'(\(uuid\s+)("?)([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-'
    r'[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})("?)(\))')


def ensure_unique_board_file_uuids(board_path):
    """Atomically repair duplicate persistent UUID declarations in a PCB file.

    Some generated reference boards contain footprint copies made with a raw
    copy constructor.  The footprint instances differ, but their pads, fields,
    and graphics retain the template UUIDs.  KiCad routes the geometry, while
    JSON DRC identifies child items by that ambiguous UUID and can consequently
    attribute a ratsnest endpoint to the wrong reference or even the wrong net.

    KiCad PCB files declare each persistent item as ``(uuid <value>)``; external
    references (for example group membership) use a different key.  Preserve
    the first declaration and deterministically replace every later occurrence
    with UUIDv5 derived from the original value and occurrence index.  This is
    text-level by design: replacing several live pcbnew footprint objects in one
    process invalidates SWIG iterators.  The rewrite is atomic, idempotent, and
    changes no electrical, physical, library, or schematic-link field.  Returns
    a compact audit report and fails closed if uniqueness is not achieved.
    """
    import uuid as _uuid
    from collections import Counter

    with open(board_path, "r", encoding="utf-8") as source:
        original = source.read()
    matches = list(_BOARD_UUID_RE.finditer(original))
    declared = [match.group(3).lower() for match in matches]
    counts = Counter(declared)
    duplicate_ids = {value for value, count in counts.items() if count > 1}
    if not duplicate_ids:
        return {"duplicate_ids_before": 0, "rewritten": 0,
                "duplicate_ids_after": 0, "status": "ok"}

    used = set(declared)
    seen = Counter()

    def replacement(match):
        value = match.group(3).lower()
        seen[value] += 1
        if seen[value] == 1:
            return match.group(0)
        salt = seen[value]
        while True:
            fresh = str(_uuid.uuid5(
                _uuid.NAMESPACE_OID,
                "cec-board-item:%s:%d" % (value, salt)))
            salt += 1
            if fresh not in used:
                used.add(fresh)
                break
        return "%s%s%s%s%s" % (
            match.group(1), match.group(2), fresh,
            match.group(4), match.group(5))

    rewritten = _BOARD_UUID_RE.sub(replacement, original)
    final_ids = [match.group(3).lower()
                 for match in _BOARD_UUID_RE.finditer(rewritten)]
    remaining = sorted(value for value, count in Counter(final_ids).items()
                       if count > 1)
    if remaining:
        raise RuntimeError(
            "persistent board-item UUID collision remains after rewrite: %s"
            % remaining[:8])

    directory = os.path.dirname(os.path.abspath(board_path)) or "."
    fd, temporary = tempfile.mkstemp(
        prefix=".%s.uuid-" % os.path.basename(board_path), dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as target:
            target.write(rewritten)
            target.flush()
            os.fsync(target.fileno())
        os.chmod(temporary, os.stat(board_path).st_mode)
        os.replace(temporary, board_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"duplicate_ids_before": len(duplicate_ids),
            "rewritten": len(declared) - len(set(declared)),
            "duplicate_ids_after": 0, "status": "repaired"}


def normalize_netclass_geometry(board, board_path, *, tol_mm=0.001,
                                preserve_nets=()):
    """Raise imported tracks/vias to their assigned netclass geometry.

    Freerouting's SES may ignore or round class-specific widths and via sizes.
    Every undersized ordinary feature is raised to the contract; oversized
    copper is retained.  Pre-existing locked items are immutable stage
    contracts and are never resized here: they were admitted before the SES
    round trip, and widening a locked local branch can create a short while
    making its UUID/provenance impossible to reconcile.  Any undersized locked
    current path remains visible to the independent current-path gate instead
    of being silently edited after detailed routing.  The one physical
    exception for ordinary imported copper is a bounded pin neck-down
    at an SMD pad whose minor dimension is narrower than the class track width.
    A 1.0 mm power class cannot physically enter a 0.4 mm fine-pitch pad at full
    width.  Imported narrow copper is therefore preserved for at most 1.5 mm of
    graph distance from that pad, and a longer segment is split at the boundary
    before its remainder is widened.  The same exception is available for at
    most 2.5 mm from a plated through-hole pad, but only when widening the actual
    imported escape would collide with a nearby foreign-net pad.  This covers
    staggered connector pin fields without weakening ordinary THT power routes.
    These are local escapes, never permission for a long skinny power route.
    Direct INA2xx Kelvin nets are excluded because those names can share a force
    rail while their sense stub is intentionally thin; the dedicated Kelvin and
    high-current-pour gates own that topology.  ``preserve_nets`` extends that
    ownership contract to nets whose exact copper geometry was already proved
    by an earlier precision stage.  Neither their tracks nor vias are resized;
    widening one member of a routed differential pair after corridor proof
    would invalidate the proof even if the nominal netclass had drifted.
    """
    preserve_nets = {str(net) for net in (preserve_nets or ()) if str(net)}
    pro_path = (board_path[:-len(".kicad_pcb")] + ".kicad_pro"
                if board_path.endswith(".kicad_pcb") else "")
    if not pro_path or not os.path.isfile(pro_path):
        return {"tracks": 0, "vias": 0, "status": "no-project"}
    try:
        with open(pro_path, encoding="utf-8") as source:
            ns = (json.load(source).get("net_settings") or {})
    except Exception as exc:                              # noqa: BLE001
        return {"tracks": 0, "vias": 0,
                "status": "project-error:%s" % type(exc).__name__}
    classes = {c.get("name"): c for c in (ns.get("classes") or [])
               if c.get("name")}
    if not classes:
        return {"tracks": 0, "vias": 0, "status": "no-classes"}
    assignments = ns.get("netclass_assignments") or {}
    patterns = [(row.get("netclass"), row.get("pattern"))
                for row in (ns.get("netclass_patterns") or [])
                if row.get("netclass") in classes and row.get("pattern")]

    def resolve(net):
        chosen = assignments.get(net)
        if isinstance(chosen, list):
            chosen = chosen[0] if chosen else None
        if chosen in classes:
            return classes[chosen]
        for name, pattern in patterns:
            if fnmatch.fnmatchcase(net, pattern):
                return classes[name]
        return classes.get("Default", {})

    def is_pair_net(net):
        upper = net.upper()
        return (bool(re.search(r"_(?:P|N)$", upper))
                or upper.endswith(("CAN_H", "CAN_L", "CAN_H_BUS", "CAN_L_BUS"))
                or "USB_D" in upper)

    direct_sense = set()
    for fp in board.GetFootprints():
        try:
            value = fp.GetValue().upper()
        except Exception:                                # noqa: BLE001
            value = ""
        if "INA2" not in value:
            continue
        for pad in fp.Pads():
            net = pad.GetNetname() or ""
            if net.endswith(("_HI", "_LO", "_P", "_N")):
                direct_sense.add(net)

    # Fine-pitch SMD escape neck-downs --------------------------------------
    # Freerouting can emit a legal narrow pin escape even when its SES ignores
    # the assigned class width.  Blanket widening those short segments produced
    # the Hub's U7 and USB-C pad-field shorts.  Work on the imported graph before
    # the ordinary normalization pass so only the small, pad-connected prefix is
    # retained and any long first segment is split at a deterministic boundary.
    from collections import defaultdict
    import heapq

    original_items = list(board.GetTracks())
    track_rows = []
    by_net = defaultdict(list)
    preserved_locked_tracks = 0
    preserved_locked_vias = 0
    for item in original_items:
        if item.GetClass() != "PCB_TRACK":
            continue
        net = item.GetNetname() or ""
        if net in preserve_nets:
            continue
        spec = resolve(net)
        target = float((spec.get("diff_pair_width") if is_pair_net(net) else None)
                       or spec.get("track_width") or 0)
        current = item.GetWidth() / MM
        if net in direct_sense or target <= 0:
            continue
        if item.IsLocked() and current < target - tol_mm:
            preserved_locked_tracks += 1
        s, e = item.GetStart(), item.GetEnd()
        length = item.GetLength() / MM
        if length <= 1e-9:
            continue
        row = {
            "item": item, "uuid": item.m_Uuid.AsString(), "net": net,
            "layer": item.GetLayer(), "start": (s.x, s.y), "end": (e.x, e.y),
            "length": length, "current": current, "target": target,
            "undersized": current < target - tol_mm,
            "locked": bool(item.IsLocked()),
        }
        track_rows.append(row)
        by_net[net].append(row)

    def pad_layers(pad):
        return frozenset(pad.GetLayerSet().CuStack())

    # Return whether the centreline segment intersects an axis-aligned pad
    # copper box expanded by the prospective track radius and clearance.  Pad
    # bounding boxes are conservative for round/custom pads, which is desirable
    # here: this function only preserves copper that Freerouting already made
    # narrow, and the subsequent DRC remains authoritative.
    def segment_hits_expanded_box(start, end, box, expansion):
        x0, y0 = start[0] / MM, start[1] / MM
        x1, y1 = end[0] / MM, end[1] / MM
        xmin = box.GetX() / MM - expansion
        ymin = box.GetY() / MM - expansion
        xmax = xmin + box.GetWidth() / MM + 2.0 * expansion
        ymax = ymin + box.GetHeight() / MM + 2.0 * expansion
        dx, dy = x1 - x0, y1 - y0
        lo, hi = 0.0, 1.0
        for origin, delta, low, high in ((x0, dx, xmin, xmax),
                                         (y0, dy, ymin, ymax)):
            if abs(delta) <= 1e-12:
                if origin < low or origin > high:
                    return False
                continue
            enter = (low - origin) / delta
            leave = (high - origin) / delta
            if enter > leave:
                enter, leave = leave, enter
            lo, hi = max(lo, enter), min(hi, leave)
            if lo > hi:
                return False
        return True

    try:
        board_min_width = max(0.0, board.GetDesignSettings().m_TrackMinWidth / MM)
    except Exception:                                  # noqa: BLE001
        board_min_width = 0.20
    all_pads = []
    fine_pads = defaultdict(list)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            net = pad.GetNetname() or ""
            layers = pad_layers(pad)
            if net:
                clearance = float(resolve(net).get("clearance") or 0)
                all_pads.append(
                    (pad, net, layers, pad.GetBoundingBox(), clearance))
            try:
                if int(pad.GetAttribute()) != int(pcbnew.PAD_ATTRIB_SMD):
                    continue
            except Exception:                              # noqa: BLE001
                continue
            if not net or net in direct_sense:
                continue
            spec = resolve(net)
            target = float((spec.get("diff_pair_width") if is_pair_net(net) else None)
                           or spec.get("track_width") or 0)
            size = pad.GetSize()
            minor = min(size.x, size.y) / MM
            if target > 0 and minor < target - tol_mm:
                limit = max(0.6, min(1.5, 1.5 * target))
                local_width = min(target, max(board_min_width, minor / 2.0))
                fine_pads[net].append((pad, layers, limit, local_width))

    # A THT pad need not itself be narrower than a power netclass, yet a
    # staggered adjacent pin can still make a full-width escape impossible.
    # Detect that condition from the imported route geometry.  Only inspect the
    # first 2.5 mm from an endpoint that actually lands on the same-net PTH pad;
    # a collision farther along a route is not a pin-escape entitlement.
    pth_limit = 2.5
    for net, rows in by_net.items():
        if net in direct_sense:
            continue
        seen_pads = {pad.m_Uuid.AsString() for pad, _layers, _limit, _width
                     in fine_pads.get(net, ())}
        for pad, pad_net, layers, _box, _clearance in all_pads:
            if pad_net != net or pad.m_Uuid.AsString() in seen_pads:
                continue
            try:
                if int(pad.GetAttribute()) != int(pcbnew.PAD_ATTRIB_PTH):
                    continue
            except Exception:                              # noqa: BLE001
                continue
            constrained = False
            for row in rows:
                if row["layer"] not in layers:
                    continue
                for endpoint, other in ((row["start"], row["end"]),
                                        (row["end"], row["start"])):
                    point = pcbnew.VECTOR2I(endpoint[0], endpoint[1])
                    if not pad.HitTest(point):
                        continue
                    frac = min(1.0, pth_limit / row["length"])
                    prefix_end = (
                        int(round(endpoint[0] + (other[0] - endpoint[0]) * frac)),
                        int(round(endpoint[1] + (other[1] - endpoint[1]) * frac)))
                    own_clear = float(resolve(net).get("clearance") or 0)
                    for (_foreign, foreign_net, foreign_layers, foreign_box,
                         foreign_clear) in all_pads:
                        if foreign_net == net or row["layer"] not in foreign_layers:
                            continue
                        expansion = row["target"] / 2.0 + max(own_clear, foreign_clear)
                        if segment_hits_expanded_box(endpoint, prefix_end,
                                                     foreign_box, expansion):
                            constrained = True
                            break
                    if constrained:
                        break
                if constrained:
                    break
            if constrained:
                # PTH entitlement preserves an imported narrow escape but does
                # not proactively shrink a class-width route: unlike a
                # fine-pitch SMD land, the pad itself can accept the class
                # width and only the observed foreign-pin collision justifies
                # retaining narrower imported copper.
                fine_pads[net].append((pad, layers, pth_limit, None))
                seen_pads.add(pad.m_Uuid.AsString())

    handled = set()
    neckdown_sections = split_tracks = widened_sections = narrowed_sections = 0
    for net, rows in by_net.items():
        pads = fine_pads.get(net, ())
        if not pads:
            continue
        adjacency = defaultdict(list)
        node_points = {}
        for row in rows:
            a = (row["start"][0], row["start"][1], row["layer"])
            b = (row["end"][0], row["end"][1], row["layer"])
            node_points[a] = pcbnew.VECTOR2I(a[0], a[1])
            node_points[b] = pcbnew.VECTOR2I(b[0], b[1])
            adjacency[a].append((b, row["length"]))
            adjacency[b].append((a, row["length"]))

        # Track the greatest remaining neck-down budget at each graph node.
        # This keeps a 1.5 mm SMD escape and a 2.5 mm constrained-THT escape on
        # the same net independent without globally relaxing either bound.
        budget = {}
        queue = []
        for node, point in node_points.items():
            seeds = [(limit, local_width)
                     for pad, layers, limit, local_width in pads
                     if node[2] in layers and pad.HitTest(point)]
            if seeds:
                remaining = max(row[0] for row in seeds)
                local_width = min(
                    (row[1] for row in seeds
                     if row[0] == remaining and row[1] is not None),
                    default=None)
                budget[node] = (remaining, local_width)
                width_rank = float("inf") if local_width is None else local_width
                heapq.heappush(queue, (-remaining, width_rank, node))
        while queue:
            neg_remaining, width_rank, node = heapq.heappop(queue)
            remaining = -neg_remaining
            local_width = None if width_rank == float("inf") else width_rank
            if (remaining, local_width) != budget.get(node):
                continue
            for other, edge_len in adjacency[node]:
                new_remaining = remaining - edge_len
                if new_remaining <= 1e-9:
                    continue
                old_remaining, old_width = budget.get(other, (0.0, None))
                old_rank = float("inf") if old_width is None else old_width
                new_rank = float("inf") if local_width is None else local_width
                if (new_remaining > old_remaining + 1e-12
                        or (abs(new_remaining - old_remaining) <= 1e-12
                            and new_rank < old_rank)):
                    budget[other] = (new_remaining, local_width)
                    heapq.heappush(queue, (-new_remaining, new_rank, other))

        for row in rows:
            a = (row["start"][0], row["start"][1], row["layer"])
            b = (row["end"][0], row["end"][1], row["layer"])
            length = row["length"]
            budget_a = budget.get(a, (0.0, None))
            budget_b = budget.get(b, (0.0, None))
            keep_a = max(0.0, min(length, budget_a[0]))
            keep_b = max(0.0, min(length, budget_b[0]))
            if keep_a <= 1e-6 and keep_b <= 1e-6:
                continue
            # Classification and mutation are separate authorities.  A locked
            # item is immutable, but a UUID is also the checker exemption unit.
            # Exempting a whole 3 mm segment because its first 1.5 mm touched a
            # fine pad silently waived the unbounded remainder.  Therefore a
            # locked item is legal only when its entire length lies inside the
            # union of its endpoint neck-down budgets.
            if row["locked"]:
                if keep_a + keep_b + 1e-6 >= length:
                    handled.add(row["uuid"])
                    neckdown_sections += 1
                continue
            handled.add(row["uuid"])

            # Replace one long segment with [narrow prefix] [class-width body]
            # [narrow suffix] as applicable.  Track endpoints stay coincident,
            # so electrical connectivity is unchanged and the operation is
            # idempotent on the next normalization pass.
            cuts = [0.0]
            if keep_a > 1e-6:
                cuts.append(keep_a)
            if length - keep_b > cuts[-1] + 1e-6:
                cuts.append(length - keep_b)
            if length > cuts[-1] + 1e-6:
                cuts.append(length)
            elif cuts[-1] != length:
                cuts[-1] = length
            if cuts[-1] < length:
                cuts.append(length)

            sx, sy = row["start"]
            ex, ey = row["end"]

            def point_at(offset):
                frac = max(0.0, min(1.0, offset / length))
                return pcbnew.VECTOR2I(
                    int(round(sx + (ex - sx) * frac)),
                    int(round(sy + (ey - sy) * frac)))

            pieces = []
            for lo, hi in zip(cuts, cuts[1:]):
                mid = (lo + hi) / 2.0
                at_a = mid <= keep_a + 1e-6
                at_b = mid >= length - keep_b - 1e-6
                narrow = at_a or at_b
                if narrow:
                    # Normalization may preserve an already narrow imported
                    # escape, but it must never *create* one by shrinking valid
                    # class-width copper synthesized earlier in the pipeline.
                    width = row["current"]
                else:
                    width = max(row["current"], row["target"])
                pieces.append((point_at(lo), point_at(hi), width, narrow))
            item = row["item"]
            for index, (start, end, width, narrow) in enumerate(pieces):
                piece = item if index == 0 else item.Duplicate()
                piece.SetStart(start)
                piece.SetEnd(end)
                piece.SetWidth(_nm(width))
                if index:
                    board.Add(piece)
                if narrow:
                    neckdown_sections += 1
                if width > row["current"] + tol_mm:
                    widened_sections += 1
                elif width < row["current"] - tol_mm:
                    narrowed_sections += 1
            if len(pieces) > 1:
                split_tracks += 1

    track_fixed = widened_sections + narrowed_sections
    via_fixed = 0
    qualified_pofv = 0
    for item in original_items:
        net = item.GetNetname() or ""
        if net in preserve_nets:
            continue
        spec = resolve(net)
        if item.GetClass() == "PCB_TRACK":
            if item.IsLocked():
                continue
            if item.m_Uuid.AsString() in handled:
                continue
            target = float((spec.get("diff_pair_width") if is_pair_net(net) else None)
                           or spec.get("track_width") or 0)
            current = item.GetWidth() / MM
            if (net not in direct_sense and target > 0
                    and current < target - tol_mm):
                item.SetWidth(_nm(target))
                track_fixed += 1
        elif item.GetClass() == "PCB_VIA":
            target_dia = float(spec.get("via_diameter") or 0)
            target_drill = float(spec.get("via_drill") or 0)
            dia = item.GetWidth(item.TopLayer()) / MM
            drill = item.GetDrillValue() / MM
            if item.IsLocked():
                if (dia < target_dia - tol_mm
                        or drill < target_drill - tol_mm):
                    preserved_locked_vias += 1
                continue
            blocking, allowed = _fab.via_at_pad_conflicts(
                board, item.GetPosition(), item.GetWidth(item.TopLayer()),
                item.GetDrillValue(), item.GetNetCode())
            if blocking is None and allowed:
                # A filled/capped via whose full land is contained by a
                # same-net SMD pad follows the declared fabrication profile,
                # not the ordinary routed-via size in its electrical class.
                qualified_pofv += 1
                continue
            new_dia = max(dia, target_dia)
            new_drill = max(drill, target_drill)
            if new_dia > dia + tol_mm or new_drill > drill + tol_mm:
                item.SetWidth(_nm(new_dia))
                item.SetDrill(_nm(new_drill))
                via_fixed += 1
    return {"tracks": track_fixed, "vias": via_fixed, "status": "ok",
            "neckdown_sections": neckdown_sections,
            "neckdown_split_tracks": split_tracks,
            "neckdown_narrowed_sections": narrowed_sections,
            "qualified_pofv_vias": qualified_pofv,
            "preserved_locked_tracks": preserved_locked_tracks,
            "preserved_locked_vias": preserved_locked_vias,
            "legal_neckdown_uuids": sorted(handled),
            "sense_exempt_nets": sorted(direct_sense),
            "preserved_nets": sorted(preserve_nets)}


def normalize_via_annular(board, *, min_annular: float = 0.10,
                          target_annular: float = 0.12, min_drill: float = 0.30) -> int:
    """Repair vias whose annular ring is below *min_annular* (mm).

    Freerouting IGNORES the netclass via sizes from the DSN and emits every via at its
    own small default, so the SES round-trip produces vias whose annular ring (pad
    radius minus drill radius) is below the board's minimum -- on the EPS module that
    was 49 annular_width DRC hits. The fix SHRINKS THE DRILL rather than growing the
    copper: a smaller drill restores the annular ring while leaving the copper footprint
    IDENTICAL, so it introduces NO new clearance violations (blanket via-ENLARGE does --
    it turned 53 DRC into 82, +77 clearance, in testing). The drill is floored at
    *min_drill* mm; only if drill-shrink alone can't reach the target is the copper grown
    minimally. Touches only violating vias. Re-fill zones after calling this. Returns the
    number of vias adjusted.

    Verified on EPS: 49 thin-annular vias fixed, structural DRC 53 -> 4 (the 4 residual
    being an unrelated decorative-logo placement issue), both hard gates still pass.
    """
    lo = _nm(min_annular)
    want_gap = _nm(2 * target_annular)      # total dia-drill gap for target annular/side
    floor = _nm(min_drill)
    fixed = 0
    for t in board.GetTracks():
        if t.Type() != pcbnew.PCB_VIA_T:
            continue
        # PCB_VIA.GetWidth() WITHOUT a layer asserts in KiCad 10 (via width is per-layer now).
        # On Linux that just prints to stderr, but on a Windows debug build it pops a MODAL
        # "Debug Alert" dialog that BLOCKS a self-hosted runner. Pass the via's top copper layer.
        dia = t.GetWidth(t.TopLayer())
        drill = t.GetDrillValue()
        if (dia - drill) // 2 >= lo:
            continue
        # A fabrication-profile-qualified POFV intentionally follows the
        # process-specific 0.35/0.25 geometry rather than the ordinary board
        # via minima.  Growing it here would undo the locked-via SES restore
        # below and can push the land outside a narrow SMD pad.  Use the same
        # exact dimension/net/full-containment proof as conformance and score;
        # an uncontained or undeclared small via still receives the historical
        # annular repair.
        blocking, allowed = _fab.via_at_pad_conflicts(
            board, t.GetPosition(), dia, drill, t.GetNetCode())
        if blocking is None and allowed:
            continue
        new_drill = dia - want_gap
        if new_drill >= floor:
            t.SetDrill(new_drill)
        else:                                # drill-shrink alone insufficient -> grow copper
            t.SetWidth(floor + want_gap)
            t.SetDrill(floor)
        fixed += 1
    return fixed


# ---------------------------------------------------------------------------
# import_ses
# ---------------------------------------------------------------------------
def owned_locked_nets_board(board) -> set:
    """Return nets fully terminated by locked copper on an in-memory board.

    Keeping this predicate available before a board is saved lets the precision
    router refuse a nominally successful pair when a reversible connector's
    duplicate A/B lands, or an inline flow-through package, still has a loose
    physical pad.  That is the same ownership condition used at the later DSN
    boundary; important-route admission must not use a weaker definition.
    """
    locked_items = {}
    for t in board.GetTracks():
        if not t.IsLocked():
            continue
        n = t.GetNetname() or ""
        if n:
            locked_items.setdefault(n, []).append(t)
    pads_by_net = {}
    for fp in board.GetFootprints():
        for pd in fp.Pads():
            n = pd.GetNetname() or ""
            if n in locked_items:
                pads_by_net.setdefault(n, []).append(pd)

    def touches(pad, item):
        """Exact same-net copper contact, not an endpoint approximation.

        A routed segment may legitimately pass through a duplicate SMD land,
        and a THT barrel reaches every copper layer without a surface-track
        endpoint at its centre.  Endpoint-only ownership mislabeled both as
        ratlines and was the root of the protected USB duplicate-pad refusal.
        Use KiCad's effective pad shape against the actual track/via land on
        every common layer, which is the electrical geometry the connectivity
        engine and DRC see.
        """
        pad_layers = {int(layer) for layer in pad.GetLayerSet().CuStack()}
        if item.Type() == pcbnew.PCB_VIA_T:
            at = item.GetPosition()
            common = pad_layers & {
                int(layer) for layer in board.GetEnabledLayers().CuStack()}
            for layer in common:
                try:
                    circle = pcbnew.SHAPE_CIRCLE(
                        at, int(item.GetWidth(layer)) // 2)
                    if pad.GetEffectiveShape(layer).Collide(circle, 0):
                        return True
                except Exception:                       # noqa: BLE001
                    continue
            return False
        layer = int(item.GetLayer())
        if layer not in pad_layers:
            return False
        try:
            segment = pcbnew.SHAPE_SEGMENT(
                item.GetStart(), item.GetEnd(), int(item.GetWidth()))
            return bool(pad.GetEffectiveShape(layer).Collide(segment, 0))
        except Exception:                               # noqa: BLE001
            return False

    owned = set()
    for n, pads in pads_by_net.items():
        items = locked_items.get(n, ())
        if items and all(any(touches(pad, item) for item in items)
                         for pad in pads):
            owned.add(n)
    return owned


def owned_locked_nets(board_path: str) -> set:
    """Read-only: nets FULLY OWNED by locked copper (every pad on the net touched by
    a locked track endpoint, pad half-extent + 0.15mm) -- the ownership test
    reconcile_locked_nets enforces after the route, exposed pre-route so the DSN can
    EXCLUDE those nets from Freerouting entirely (owner 2026-07-12: "the router is
    still touching the force copper")."""
    return owned_locked_nets_board(pcbnew.LoadBoard(board_path))


def locked_pour_authority_nets_board(board, *, min_width_mm=0.75,
                                     min_trunk_length_mm=3.0,
                                     min_total_length_mm=5.0) -> set:
    """Return locked nets that legitimately suppress broad pour synthesis.

    A single locked item is not whole-net ownership.  Local bypass links and
    pin fanouts are deliberately locked before global routing, yet their
    shared rail still needs a trunk/pour.  Treat a net as pour-authoritative
    only when every pad is covered, or when it carries substantial wide locked
    track geometry characteristic of an authored/compiled current trunk.
    Vias do not contribute length.
    """
    authority = set(owned_locked_nets_board(board))
    minimum_width = pcbnew.FromMM(float(min_width_mm))
    minimum_trunk = float(min_trunk_length_mm)
    minimum_total = float(min_total_length_mm)
    wide_lengths = {}
    widest_segment = {}
    for item in board.GetTracks():
        if (not item.IsLocked()
                or item.Type() == pcbnew.PCB_VIA_T
                or item.GetWidth() < minimum_width):
            continue
        net = item.GetNetname() or ""
        if not net:
            continue
        try:
            length = item.GetLength() / 1e6
        except Exception:                                # noqa: BLE001
            start, end = item.GetStart(), item.GetEnd()
            length = math.hypot(
                end.x - start.x, end.y - start.y) / 1e6
        wide_lengths[net] = wide_lengths.get(net, 0.0) + length
        widest_segment[net] = max(widest_segment.get(net, 0.0), length)
    authority.update(
        net for net, total in wide_lengths.items()
        if total >= minimum_total
        or widest_segment.get(net, 0.0) >= minimum_trunk)
    return authority


def locked_pour_authority_nets(board_path: str, **kwargs) -> set:
    """Path wrapper for :func:`locked_pour_authority_nets_board`."""
    return locked_pour_authority_nets_board(
        pcbnew.LoadBoard(board_path), **kwargs)


def _copper_geometry_rows(board_path: str, nets, *, locked_only=False):
    """Return normalized copper rows used by exact and prefix contracts."""
    selected = {str(net) for net in (nets or ()) if net}
    board = pcbnew.LoadBoard(board_path)
    rows = []
    for item in board.GetTracks():
        net = item.GetNetname() or ""
        if net not in selected or (locked_only and not item.IsLocked()):
            continue
        if item.Type() == pcbnew.PCB_VIA_T:
            pos = item.GetPosition()
            row = (
                "via", net, int(pos.x), int(pos.y),
                board.GetLayerName(item.TopLayer()),
                board.GetLayerName(item.BottomLayer()),
                int(item.GetWidth(item.TopLayer())),
                int(item.GetDrillValue()),
            )
        else:
            start, end = item.GetStart(), item.GetEnd()
            a = (int(start.x), int(start.y))
            b = (int(end.x), int(end.y))
            if b < a:
                a, b = b, a
            row = (
                "track", net, board.GetLayerName(item.GetLayer()),
                a[0], a[1], b[0], b[1], int(item.GetWidth()),
                int(item.Type()),
            )
        rows.append(row)
    rows.sort()
    return selected, rows


def copper_geometry_signature(board_path: str, nets) -> dict:
    """Return a stable geometry fingerprint for the selected copper nets.

    UUIDs and file ordering are deliberately excluded: DSN/SES round-trips may
    rewrite either without changing the route.  Coordinates, layer, width,
    drill, and normalized segment direction are the ownership contract.  The
    caller uses this to prove that broad routing and later finishing stages did
    not silently replace already-authoritative critical/local copper.
    """
    import hashlib

    selected, rows = _copper_geometry_rows(board_path, nets)
    by_net = {}
    for row in rows:
        net = row[1]
        by_net[net] = by_net.get(net, 0) + 1
    payload = json.dumps(rows, separators=(",", ":"), ensure_ascii=True)
    return {
        "schema": 1,
        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "nets": sorted(selected),
        "items": len(rows),
        "items_by_net": {net: by_net.get(net, 0) for net in sorted(selected)},
    }


def copper_geometry_prefix_contract(board_path: str, nets) -> dict:
    """Capture immutable locked copper while allowing same-net extensions.

    Fully-owned routes use :func:`copper_geometry_signature`: no later stage
    may add or remove anything on those nets.  A Kelvin/current prefix can be
    intentionally partial, so the residual router may add copper but must not
    delete or reshape any locked primitive already admitted by the precision
    tier.  Individual row digests make that subset relationship stable across
    UUID and file-order rewrites.
    """
    import collections
    import hashlib

    selected, rows = _copper_geometry_rows(
        board_path, nets, locked_only=True)
    members = collections.Counter()
    by_net = collections.Counter()
    digest_net = {}
    for row in rows:
        payload = json.dumps(row, separators=(",", ":"), ensure_ascii=True)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        members[digest] += 1
        by_net[row[1]] += 1
        digest_net[digest] = row[1]
    return {
        "schema": 1,
        "mode": "locked_geometry_subset",
        "nets": sorted(selected),
        "items": len(rows),
        "items_by_net": {net: by_net.get(net, 0)
                         for net in sorted(selected)},
        "members": dict(sorted(members.items())),
        "member_nets": {digest: digest_net[digest]
                        for digest in sorted(digest_net)},
    }


def check_copper_geometry_prefix(board_path: str, contract) -> dict:
    """Prove every primitive in a locked-prefix contract still exists."""
    import collections
    import hashlib

    expected = dict(contract or {})
    selected, rows = _copper_geometry_rows(
        board_path, expected.get("nets") or ())
    actual = collections.Counter()
    actual_by_net = collections.Counter()
    for row in rows:
        payload = json.dumps(row, separators=(",", ":"), ensure_ascii=True)
        actual[hashlib.sha256(payload.encode("utf-8")).hexdigest()] += 1
        actual_by_net[row[1]] += 1
    missing = {}
    missing_by_net = collections.Counter()
    member_nets = expected.get("member_nets") or {}
    for digest, count in (expected.get("members") or {}).items():
        deficit = int(count) - int(actual.get(digest, 0))
        if deficit > 0:
            missing[digest] = deficit
            missing_by_net[member_nets.get(digest, "")] += deficit
    return {
        "schema": 1,
        "mode": "locked_geometry_subset",
        "applicable": bool(expected.get("items")),
        "ok": not missing,
        "expected_items": int(expected.get("items") or 0),
        "actual_items_on_nets": len(rows),
        "actual_items_by_net": {net: actual_by_net.get(net, 0)
                                for net in sorted(selected)},
        "missing_items": sum(missing.values()),
        "missing_by_net": {net: count for net, count in
                           sorted(missing_by_net.items()) if net},
        "missing_members": dict(sorted(missing.items())),
    }


def locked_copper_keepouts(board_path: str, *, only_nets=None, clearance: float = 0.2):
    """Rule-area keepout rects over owned copper, per layer (owner defect report
    2026-07-14: FR "is routing through the locked routes, and not layer changing
    around it" -- MEASURED on the wave-9 winner: 154/157 shorting, 91/94 clearance,
    75/75 tracks_crossing violations touch locked-copper space). Mechanism: the
    owned-net exclusion truncates those nets to ONE DSN pin, and FR 1.7.0 treats
    their '(type protect)' wires as dangling -- the fr02 bench proved protect stops
    RIP-UP of a routable net's stubs, but an EXCLUDED net's copper drops out of the
    obstacle model entirely. Rule-area keepouts are net-blind and proven respected
    (the corridor lever), so FR must layer-change/route around the cells.

    Scope: *only_nets* (pass the fully-owned set) -- a PARTIALLY-locked net (e.g.
    /FAN_12V) must NOT contribute: FR still legitimately routes its remainder and
    needs access to its pads.  When a fully-owned set is supplied, every physical
    track/via on those nets is guarded, not only items carrying KiCad's LOCKED
    flag, plus every physical pad on those nets.  Plane-access and via-in-pad
    stages deliberately leave some generated vias unlocked, and DSN pin
    exclusion removes the owned pads from Freerouting's obstacle model too;
    omitting either made the residual router collide with invisible copper.
    Without *only_nets*, the historical locked-only behavior is retained.
    Same-layer rects merge only when the union stays TIGHT (union area <= 1.15x
    the sum) so a dense cell collapses to a few zones but a diagonal pair can
    never over-cover a foreign channel/pad."""
    board = pcbnew.LoadBoard(board_path)
    cl = int(clearance * 1e6)
    per_layer = {}
    for t in board.GetTracks():
        net = t.GetNetname() or ""
        if only_nets is None:
            if not t.IsLocked():
                continue
        elif net not in only_nets:
            continue
        bb = t.GetBoundingBox()
        box = [bb.GetLeft() - cl, bb.GetTop() - cl, bb.GetRight() + cl, bb.GetBottom() + cl]
        if t.Type() == pcbnew.PCB_VIA_T:
            lays = tuple(board.GetLayerName(lid)
                         for lid in t.GetLayerSet().CuStack())
        else:
            lays = (board.GetLayerName(t.GetLayer()),)
        for ly in lays:
            per_layer.setdefault(ly, []).append(list(box))
    if only_nets is not None:
        selected = set(only_nets)
        for footprint in board.GetFootprints():
            for pad in footprint.Pads():
                net = pad.GetNetname() or ""
                if not net or net not in selected:
                    continue
                bb = pad.GetBoundingBox()
                box = [bb.GetLeft() - cl, bb.GetTop() - cl,
                       bb.GetRight() + cl, bb.GetBottom() + cl]
                for layer_id in pad.GetLayerSet().CuStack():
                    layer = board.GetLayerName(layer_id)
                    per_layer.setdefault(layer, []).append(list(box))

    out = []
    for ly, boxes in sorted(per_layer.items()):
        for k, (x0, y0, x1, y1) in enumerate(_merge_tight_boxes(boxes)):
            out.append({"name": "lockedcu-%s-%d" % (ly.replace(".", ""), k),
                        "x0": x0 / 1e6, "y0": y0 / 1e6,
                        "x1": x1 / 1e6, "y1": y1 / 1e6, "layers": (ly,)})
    return out


def _box_area(b):
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def _merge_tight_boxes(boxes):
    """Union-merge overlapping boxes only when the union stays TIGHT (union area
    <= 1.15x the sum) so a dense cell collapses to a few zones but a diagonal
    pair can never over-cover a foreign channel/pad (locked_copper_keepouts'
    rule, factored for the partial-net variant)."""
    boxes = [list(b) for b in boxes]
    merged = True
    while merged:
        merged = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                if not (a[0] <= b[2] and b[0] <= a[2]
                        and a[1] <= b[3] and b[1] <= a[3]):
                    continue
                u = [min(a[0], b[0]), min(a[1], b[1]),
                     max(a[2], b[2]), max(a[3], b[3])]
                if _box_area(u) <= 1.15 * (_box_area(a) + _box_area(b)):
                    boxes[i] = u
                    del boxes[j]
                    merged = True
                    break
            if merged:
                break
    return boxes


def _box_minus_window(box, win):
    """Axis-aligned rect subtraction: *box* minus *win* -> up to 4 remainder rects
    (left/right slabs at full height, top/bottom bands inside the x-overlap)."""
    bx0, by0, bx1, by1 = box
    wx0, wy0, wx1, wy1 = win
    if wx1 <= bx0 or bx1 <= wx0 or wy1 <= by0 or by1 <= wy0:
        return [list(box)]
    out = []
    if wx0 > bx0:
        out.append([bx0, by0, wx0, by1])
    if wx1 < bx1:
        out.append([wx1, by0, bx1, by1])
    mx0, mx1 = max(bx0, wx0), min(bx1, wx1)
    if wy0 > by0:
        out.append([mx0, by0, mx1, wy0])
    if wy1 < by1:
        out.append([mx0, wy1, mx1, by1])
    return [b for b in out if _box_area(b) > 0]


def partial_locked_keepouts(board_path: str, *, exclude_nets=(), clearance: float = 0.2,
                            window_mm: float = 1.0):
    """Keepouts over PARTIALLY-owned locked nets' copper, with ACCESS WINDOWS
    subtracted around each net's UNCOVERED pads (the 2026-07-14 bulldozing round's
    residue item (b): /SENSEP6_HI and /FAN_12V carry locked lane copper but are NOT
    fully owned -- a divider tap / fan-gate spur shares the net -- so the owned-set
    keepouts skipped them entirely and FR still crossed their fat copper).

    Semantics: FR must still ROUTE the net's remainder, so it needs to REACH the
    pads the locked lay does not cover -- each uncovered pad (the owned_locked_nets
    coverage rule: locked track endpoint within pad half-extent + 0.15mm) opens a
    window (pad half-extent + *window_mm*) subtracted from the keepout rects; the
    rest of the locked lane stays obstacle-modelled. Fully-owned nets (pass them
    as *exclude_nets*) are locked_copper_keepouts' business, not this function's."""
    board = pcbnew.LoadBoard(board_path)
    cl = int(clearance * 1e6)
    ex = set(exclude_nets or ())
    locked_pts, locked_boxes, locked_via_boxes = {}, {}, {}
    for t in board.GetTracks():
        if not t.IsLocked():
            continue
        n = t.GetNetname() or ""
        if not n or n in ex:
            continue
        bb = t.GetBoundingBox()
        box = [bb.GetLeft() - cl, bb.GetTop() - cl, bb.GetRight() + cl, bb.GetBottom() + cl]
        lays = (tuple(board.GetLayerName(lid)
                      for lid in t.GetLayerSet().CuStack())
                if t.Type() == pcbnew.PCB_VIA_T
                else (board.GetLayerName(t.GetLayer()),))
        if t.Type() == pcbnew.PCB_VIA_T:
            # A pad-access window exists to let the residual route attach to a
            # partially-owned net.  It must never erase the obstacle occupied
            # by an immutable through barrel.  A via is physical copper on
            # every layer it spans, even when it sits inside (or immediately
            # beside) one of those access windows.  Keep its land in a
            # separate, non-windowed ledger; otherwise a foreign inner-layer
            # trace can be routed through the apparently empty window and the
            # SES import reintroduces a hard short at the locked via.
            for ly in lays:
                locked_via_boxes.setdefault(n, {}).setdefault(
                    ly, []).append(box)
            p_ = t.GetPosition()
            locked_pts.setdefault(n, []).append((p_.x, p_.y))
        else:
            for ly in lays:
                locked_boxes.setdefault(n, {}).setdefault(
                    ly, []).append(box)
            s_, e_ = t.GetStart(), t.GetEnd()
            locked_pts.setdefault(n, []).extend([(s_.x, s_.y), (e_.x, e_.y)])
    if not locked_boxes and not locked_via_boxes:
        return []
    win = int(window_mm * 1e6)
    windows = {}                                 # net -> [window rects around uncovered pads]
    for fp in board.GetFootprints():
        for pd in fp.Pads():
            n = pd.GetNetname() or ""
            if n not in locked_boxes and n not in locked_via_boxes:
                continue
            pos = pd.GetPosition()
            sz = pd.GetSize()
            r = max(sz.x, sz.y) / 2 + int(0.15e6)
            # EVERY pad of a partial net opens a window -- covered pads included
            # (2026-07-19 wave-14b forensic): windows-around-uncovered-only let FR
            # LEAVE R5.1/J2.2 but never LAND anywhere -- the lane body AND its
            # covered pads (RS6.1/J3.6, the natural attach points) were walled off,
            # so /FAN_12V was uncompletable BY CONSTRUCTION (3 standing edges on
            # the 14b best). A covered pad's window exposes only pad+1mm of lane,
            # and connecting AT the pad is the electrically-correct attach.
            w = max(sz.x, sz.y) / 2 + win
            windows.setdefault(n, []).append(
                [pos.x - w, pos.y - w, pos.x + w, pos.y + w])
    out = []
    for n in sorted(set(locked_boxes) | set(locked_via_boxes)):
        for ly, source_boxes in sorted(locked_boxes.get(n, {}).items()):
            boxes = list(source_boxes)
            for wrect in windows.get(n, ()):
                boxes = [rb for b in boxes for rb in _box_minus_window(b, wrect)]
            for k, (x0, y0, x1, y1) in enumerate(_merge_tight_boxes(boxes)):
                out.append({"name": "lockedcu-part-%s-%d" % (ly.replace(".", ""), len(out)),
                            "x0": x0 / 1e6, "y0": y0 / 1e6,
                            "x1": x1 / 1e6, "y1": y1 / 1e6, "layers": (ly,)})
        # Do not merge these boxes into the windowed track pieces: such a
        # merge could span the very access aperture the split representation
        # is preserving.  Via boxes may merge with one another when their
        # physical lands overlap, but they are never window-subtracted.
        for ly, boxes in sorted(locked_via_boxes.get(n, {}).items()):
            for x0, y0, x1, y1 in _merge_tight_boxes(boxes):
                out.append({
                    "name": "lockedvia-part-%s-%d" % (
                        ly.replace(".", ""), len(out)),
                    "x0": x0 / 1e6, "y0": y0 / 1e6,
                    "x1": x1 / 1e6, "y1": y1 / 1e6,
                    "layers": (ly,),
                })
    return out


def _coupled_pair_partners(a: str, b: str) -> bool:
    """True iff nets *a*/*b* are the two members of one coupled pair by the repo's
    naming conventions (_P/_N diff pairs, CAN_H/CAN_L, legacy USB_DP/USB_DM).
    Explicit suffix forms only -- a generic single-letter tail would mis-exempt
    unrelated nets in a report-only audit."""
    for pa, pb in (("_P", "_N"), ("_H", "_L"), ("DP", "DM")):
        for x, y in ((pa, pb), (pb, pa)):
            if a.endswith(x) and b.endswith(y) and a[:-len(x)] == b[:-len(y)]:
                return True
    return False


def coupled_pair_nets(board_or_path) -> set:
    """Return conventional coupled-pair members present on a board.

    This complements project netclass declarations.  CAN_H/CAN_L and legacy
    DP/DM names are frequently electrically paired without being assigned to a
    KiCad differential-pair class, but post-route cosmetic finishing must still
    leave them symmetric.
    """
    board = (pcbnew.LoadBoard(board_or_path)
             if isinstance(board_or_path, str) else board_or_path)
    names = sorted({item.GetNetname() for item in board.GetNetInfo().NetsByNetcode().values()
                    if item.GetNetname()})
    paired = set()
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            if _coupled_pair_partners(left, right):
                paired.update((left, right))
    return paired


def locked_mutual_collisions(board_path: str, *, clearance: float = 0.2):
    """READ-ONLY audit: locked copper of DIFFERENT nets within *clearance* on a
    shared layer -- the 2026-07-14 bulldozing round's residue item (a): lanes and
    blueprint cells never mutual-legality-check (refusals check foreign PADS only),
    measured 43 locked-vs-locked self-collisions on the wave-9 winner.

    REAL SHAPES + PAIR EXEMPTION (2026-07-19 forensic): the original bbox proxy
    over-reported EVERY diagonal segment pair -- measured on a solo-tier-routed Hub:
    16 bbox 'collisions' between /CAN_H and /CAN_L whose real shapes were > 0.2mm
    apart everywhere (GetEffectiveShape probe), and the same class flagged the
    24-pin's coupled USB continuation at its LEGAL design gap. Now: exact
    GetEffectiveShape().Collide at *clearance*; declared coupled-pair partners
    (_P/_N, _H/_L, DP/DM) are held only to TRUE OVERLAP (Collide 0) -- running at
    their pair gap is their job, not a defect. The audit REPORTS, it does not
    refuse. Returns [{a, b, layer, x_mm, y_mm}]."""
    board = pcbnew.LoadBoard(board_path)
    cl = int(clearance * 1e6)
    by_layer = {}
    for t in board.GetTracks():
        if not t.IsLocked():
            continue
        n = t.GetNetname() or ""
        if t.Type() == pcbnew.PCB_VIA_T:
            lids = [pcbnew.F_Cu, pcbnew.B_Cu]
        else:
            lids = [t.GetLayer()]
        for lid in lids:
            by_layer.setdefault(lid, []).append((n, t))
    hits = []
    for lid, items in sorted(by_layer.items()):
        ly = board.GetLayerName(lid)
        for i in range(len(items)):
            na, ta = items[i]
            for j in range(i + 1, len(items)):
                nb, tb = items[j]
                if na == nb:
                    continue
                need = 0 if _coupled_pair_partners(na, nb) else cl
                if ta.GetEffectiveShape(lid).Collide(tb.GetEffectiveShape(lid), need):
                    pa = ta.GetPosition()
                    hits.append({"a": na, "b": nb, "layer": ly,
                                 "x_mm": round(pa.x / 1e6, 2),
                                 "y_mm": round(pa.y / 1e6, 2)})
    return hits


def chamfer_unlocked_right_angles(
        board_or_path, out_path=None, *, max_chamfer_mm=0.60,
        min_chamfer_mm=0.15, max_width_mm=1.0, clearance_mm=0.20,
        exclude_nets=(), junction_tol_mm=0.02):
    """Replace legal generated 90-degree corners with short 45-degree bends.

    Freerouting's Manhattan search is fast and deterministic, but its accepted
    paths can retain visually harsh staircase corners.  This is deliberately a
    *finishing* pass rather than a free-angle router:

    * only two unlocked, same-net/same-layer/same-width axis-aligned tracks may
      meet at the corner;
    * pad launches, vias, T-junctions, locked/authored copper, wide trunks, and
      caller-declared sensitive nets are immutable;
    * the replacement diagonal must pass the same exact foreign-copper,
      pipeline-pour, artwork, and board-edge guards as other post-route copper;
    * endpoints, width, layer, and net identity are preserved.

    The caller may additionally wrap this exact geometry proof in a whole-board
    connectivity/DRC transaction.  Returns a JSON-safe evidence report and
    saves only when a path or ``out_path`` was supplied.
    """
    board = (pcbnew.LoadBoard(board_or_path)
             if isinstance(board_or_path, str) else board_or_path)
    excluded = {str(net) for net in (exclude_nets or ()) if net}
    max_width = _nm(max_width_mm) if max_width_mm is not None else None
    d_max, d_min = _nm(max_chamfer_mm), _nm(min_chamfer_mm)
    clearance = _nm(clearance_mm)
    junction_tol = _nm(junction_tol_mm)
    tracks = [item for item in board.GetTracks()
              if item.GetClass() == "PCB_TRACK"]
    vias = [item for item in board.GetTracks()
            if item.GetClass() == "PCB_VIA"]
    pads = [pad for footprint in board.GetFootprints()
            for pad in footprint.Pads()]

    by_endpoint = {}
    for track in tracks:
        key_tail = (track.GetNetCode(), track.GetLayer())
        for point in (track.GetStart(), track.GetEnd()):
            by_endpoint.setdefault(
                (point.x, point.y, *key_tail), []).append(track)

    def _other_end(track, corner):
        return track.GetEnd() if track.GetStart() == corner else track.GetStart()

    def _axis_kind(track):
        start, end = track.GetStart(), track.GetEnd()
        if start.y == end.y and start.x != end.x:
            return "h"
        if start.x == end.x and start.y != end.y:
            return "v"
        return None

    def _point_on_body(track, point):
        start, end = track.GetStart(), track.GetEnd()
        if ((abs(start.x - point.x) <= junction_tol
             and abs(start.y - point.y) <= junction_tol)
                or (abs(end.x - point.x) <= junction_tol
                    and abs(end.y - point.y) <= junction_tol)):
            return False
        vx, vy = end.x - start.x, end.y - start.y
        length2 = vx * vx + vy * vy
        if not length2:
            return False
        ratio = ((point.x - start.x) * vx + (point.y - start.y) * vy) / length2
        if not 0.0 < ratio < 1.0:
            return False
        px, py = start.x + ratio * vx, start.y + ratio * vy
        return math.hypot(point.x - px, point.y - py) <= junction_tol

    detail = []
    skipped = {"locked": 0, "sensitive": 0, "wide": 0,
               "junction": 0, "launch": 0, "short": 0,
               "clearance": 0}
    right_angles = 0
    # Stable order makes the finishing output independent of pcbnew container
    # iteration order and keeps neighboring-corner shortening reproducible.
    for key in sorted(by_endpoint):
        x, y, net_code, layer = key
        incident = by_endpoint[key]
        if len(incident) != 2:
            if len(incident) > 2:
                skipped["junction"] += 1
            continue
        first, second = incident
        kinds = {_axis_kind(first), _axis_kind(second)}
        if kinds != {"h", "v"}:
            continue
        right_angles += 1
        corner = pcbnew.VECTOR2I(x, y)
        net_name = first.GetNetname() or ""
        if first.IsLocked() or second.IsLocked():
            skipped["locked"] += 1
            continue
        if net_name in excluded:
            skipped["sensitive"] += 1
            continue
        if (first.GetWidth() != second.GetWidth()
                or (max_width is not None and first.GetWidth() > max_width)):
            skipped["wide"] += 1
            continue
        # A centerline crossing is an electrical branch even when it does not
        # contribute an endpoint to the map.  Never cut that junction.
        if any(track.GetNetCode() == net_code and track.GetLayer() == layer
               and track not in (first, second)
               and _point_on_body(track, corner) for track in tracks):
            skipped["junction"] += 1
            continue
        # Pad/via corners are launches or layer transitions, not cosmetic
        # staircase bends.  Leave their topology exact.
        if (any(via.GetNetCode() == net_code
                and math.hypot(via.GetPosition().x - x,
                               via.GetPosition().y - y) <= junction_tol
                for via in vias)
                or any(pad.IsOnLayer(layer) and pad.HitTest(corner)
                       for pad in pads)):
            skipped["launch"] += 1
            continue

        far_a, far_b = _other_end(first, corner), _other_end(second, corner)
        len_a = int(round(math.hypot(far_a.x - x, far_a.y - y)))
        len_b = int(round(math.hypot(far_b.x - x, far_b.y - y)))
        distance = min(d_max, int(0.40 * len_a), int(0.40 * len_b))
        if distance < d_min:
            skipped["short"] += 1
            continue

        def _inset(far):
            return pcbnew.VECTOR2I(
                x + (distance if far.x > x else -distance if far.x < x else 0),
                y + (distance if far.y > y else -distance if far.y < y else 0))

        inset_a, inset_b = _inset(far_a), _inset(far_b)
        width = first.GetWidth()
        if (not _edge_leg_clear(board, inset_a, inset_b, width // 2)
                or not _tap_foreign_clear(
                    board, inset_a, inset_b, width, layer, clearance,
                    {net_code})):
            skipped["clearance"] += 1
            continue

        if first.GetStart() == corner:
            first.SetStart(inset_a)
        else:
            first.SetEnd(inset_a)
        if second.GetStart() == corner:
            second.SetStart(inset_b)
        else:
            second.SetEnd(inset_b)
        diagonal = pcbnew.PCB_TRACK(board)
        diagonal.SetStart(inset_a)
        diagonal.SetEnd(inset_b)
        diagonal.SetWidth(width)
        diagonal.SetLayer(layer)
        diagonal.SetNetCode(net_code)
        board.Add(diagonal)
        detail.append({
            "net": net_name, "layer": board.GetLayerName(layer),
            "corner_mm": [round(x / MM, 4), round(y / MM, 4)],
            "chamfer_mm": round(distance / MM, 4),
            "width_mm": round(width / MM, 4),
        })

    target = out_path or (board_or_path if isinstance(board_or_path, str) else None)
    if target is not None and detail:
        pcbnew.SaveBoard(target, board)
    return {"schema": 1, "right_angles": right_angles,
            "chamfered": len(detail), "detail": detail,
            "skipped": skipped}


def _recommended_teardrop_targets(
        board, *, target_kinds=("pth", "via"), exclude_nets=(),
        max_track_to_target_ratio=0.75, junction_tol_mm=0.02):
    """Return conservative pad/via targets and JSON-safe evidence.

    A teardrop is recommended only where at least one same-net track actually
    terminates on a materially larger target.  SMD pads are opt-in because
    fine-pitch escape fields normally value clearance and impedance continuity
    more than filleting; PTH lands and ordinary through vias are the default
    mechanically useful cases.  Sensitive nets are excluded by the caller.
    """
    kinds = {str(kind).lower() for kind in (target_kinds or ())}
    excluded = {str(net) for net in (exclude_nets or ()) if net}
    tol = _nm(junction_tol_mm)
    tracks = [item for item in board.GetTracks()
              if item.GetClass() == "PCB_TRACK"]
    vias = [item for item in board.GetTracks()
            if item.GetClass() == "PCB_VIA"]

    def _endpoint_near(track, point):
        return any(math.hypot(endpoint.x - point.x,
                              endpoint.y - point.y) <= tol
                   for endpoint in (track.GetStart(), track.GetEnd()))

    targets = []
    if "via" in kinds:
        for via in vias:
            net = via.GetNetname() or ""
            if not net or net in excluded or via.IsLocked():
                continue
            incident = [track for track in tracks
                        if track.GetNetCode() == via.GetNetCode()
                        and via.IsOnLayer(track.GetLayer())
                        and _endpoint_near(track, via.GetPosition())]
            if not incident:
                continue
            diameter = min(via.GetWidth(via.TopLayer()),
                           via.GetWidth(via.BottomLayer()))
            narrow = min(track.GetWidth() for track in incident)
            if diameter <= 0 or narrow >= diameter * max_track_to_target_ratio:
                continue
            pos = via.GetPosition()
            targets.append(("via", via, {
                "kind": "via", "net": net,
                "at_mm": [round(pos.x / MM, 4), round(pos.y / MM, 4)],
                "target_mm": round(diameter / MM, 4),
                "track_mm": round(narrow / MM, 4),
                "already_enabled": bool(via.GetTeardropsEnabled()),
            }))

    pad_kinds = kinds & {"pth", "smd"}
    if pad_kinds:
        for footprint in board.GetFootprints():
            for pad in footprint.Pads():
                is_pth = pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
                kind = "pth" if is_pth else "smd"
                if kind not in pad_kinds:
                    continue
                net = pad.GetNetname() or ""
                if not net or net in excluded:
                    continue
                incident = []
                for track in tracks:
                    if (track.GetNetCode() != pad.GetNetCode()
                            or not pad.IsOnLayer(track.GetLayer())):
                        continue
                    if any(pad.HitTest(endpoint)
                           for endpoint in (track.GetStart(), track.GetEnd())):
                        incident.append(track)
                if not incident:
                    continue
                size = pad.GetSize()
                target = min(size.x, size.y)
                narrow = min(track.GetWidth() for track in incident)
                if target <= 0 or narrow >= target * max_track_to_target_ratio:
                    continue
                pos = pad.GetPosition()
                targets.append((kind, pad, {
                    "kind": kind, "net": net,
                    "ref": footprint.GetReference(),
                    "pad": pad.GetPadName(),
                    "at_mm": [round(pos.x / MM, 4),
                              round(pos.y / MM, 4)],
                    "target_mm": round(target / MM, 4),
                    "track_mm": round(narrow / MM, 4),
                    "already_enabled": bool(pad.GetTeardropsEnabled()),
                }))
    targets.sort(key=lambda row: (
        row[0], row[2].get("net", ""), row[2].get("ref", ""),
        row[2]["at_mm"][0], row[2]["at_mm"][1]))
    return targets


def audit_teardrop_junctions(
        board_or_path, *, target_kinds=("pth", "via"), exclude_nets=(),
        max_track_to_target_ratio=0.75, junction_tol_mm=0.02):
    """Read-only recommendation report for modern KiCad teardrops."""
    board = (pcbnew.LoadBoard(board_or_path)
             if isinstance(board_or_path, str) else board_or_path)
    rows = _recommended_teardrop_targets(
        board, target_kinds=target_kinds, exclude_nets=exclude_nets,
        max_track_to_target_ratio=max_track_to_target_ratio,
        junction_tol_mm=junction_tol_mm)
    detail = [row[2] for row in rows]
    counts = {kind: sum(row[0] == kind for row in rows)
              for kind in ("pth", "via", "smd")}
    enabled = sum(item.GetTeardropsEnabled() for _kind, item, _row in rows)
    return {"schema": 1, "candidate_count": len(rows),
            "already_enabled": int(enabled), "by_kind": counts,
            "detail": detail}


def enable_recommended_teardrops(
        board_or_path, out_path=None, *, target_kinds=("pth", "via"),
        exclude_nets=(), max_track_to_target_ratio=0.75,
        junction_tol_mm=0.02, max_length_mm=1.0, max_width_mm=2.0,
        length_ratio=0.5, width_ratio=1.0):
    """Enable modern KiCad teardrops on conservative recommended targets.

    This sets target metadata; KiCad owns the generated copper geometry and its
    DRC interpretation.  The route oracle wraps the result transactionally and
    only adopts it when ratlines, DRC, Kelvin, and pair quality remain monotonic.
    """
    board = (pcbnew.LoadBoard(board_or_path)
             if isinstance(board_or_path, str) else board_or_path)
    rows = _recommended_teardrop_targets(
        board, target_kinds=target_kinds, exclude_nets=exclude_nets,
        max_track_to_target_ratio=max_track_to_target_ratio,
        junction_tol_mm=junction_tol_mm)
    enabled = []
    for kind, item, row in rows:
        if item.GetTeardropsEnabled():
            continue
        item.SetTeardropsEnabled(True)
        item.SetTeardropBestLengthRatio(float(length_ratio))
        item.SetTeardropBestWidthRatio(float(width_ratio))
        item.SetTeardropMaxLength(_nm(max_length_mm))
        item.SetTeardropMaxWidth(_nm(max_width_mm))
        item.SetTeardropMaxTrackWidth(float(max_track_to_target_ratio))
        item.SetTeardropAllowSpanTwoTracks(True)
        item.SetTeardropPreferZoneConnections(False)
        item.SetTeardropCurved(False)
        enabled.append(dict(row))
    target = out_path or (board_or_path if isinstance(board_or_path, str) else None)
    if target is not None and enabled:
        pcbnew.SaveBoard(target, board)
    return {"schema": 1, "candidates": len(rows),
            "enabled": len(enabled), "detail": enabled,
            "target_kinds": sorted({str(kind) for kind in target_kinds})}


def reconcile_locked_nets(board_path: str, out_path: str = None) -> dict:
    """POST-FR LOCKED-NET RECONCILE (owner catch 2026-07-12: the wave "scrapped the
    nice traces... and redid the shunt 90s"). Measured mechanism, both halves:
    (a) FR echoes protected wires back in the SES and the import re-adds them as
    UNLOCKED duplicates at the same coords; (b) FR fails to credit a protected
    tap/lane as connecting its pin and re-routes the net ITSELF at the DSN class
    width -- 2.5mm F.Cu bulldozers through the Kelvin-tap region on /SENSEP*_LO.

    Rule: a locked net is FULLY OWNED by its lay iff EVERY pad on the net is
    touched by a locked track endpoint (pad half-extent + 0.15mm). Fully-owned ->
    strip ALL unlocked tracks/vias on the net (the lay connects it by
    construction; anything FR added is echo or spurious). Partially-owned (e.g.
    /FAN_12V, whose R5/J2/D5 spurs the lay does not cover) -> strip only EXACT
    geometric echoes of locked copper; FR's legitimate spurs stay. GND/+3V3
    (locked stubs only, pads mostly uncovered) are inherently partial -> safe.

    SWIG discipline: fresh load, collect-then-batch-Remove, save, no board API
    after Remove beyond SaveBoard. Returns {net: removed_count} + "_echoes"."""
    board = pcbnew.LoadBoard(board_path)
    locked_by_net, locked_pts, locked_geo = {}, {}, set()
    for t in board.GetTracks():
        if not t.IsLocked():
            continue
        n = t.GetNetname() or ""
        locked_by_net.setdefault(n, []).append(t)
        if t.Type() == pcbnew.PCB_VIA_T:
            p_ = t.GetPosition()
            locked_pts.setdefault(n, []).append((p_.x, p_.y))
        else:
            s_, e_ = t.GetStart(), t.GetEnd()
            locked_pts.setdefault(n, []).extend([(s_.x, s_.y), (e_.x, e_.y)])
            k = (round(s_.x / 1e4), round(s_.y / 1e4), round(e_.x / 1e4), round(e_.y / 1e4))
            locked_geo.add(k)
            locked_geo.add((k[2], k[3], k[0], k[1]))
    pads_by_net = {}
    for fp in board.GetFootprints():
        for pd in fp.Pads():
            n = pd.GetNetname() or ""
            if n in locked_by_net:
                pos = pd.GetPosition()
                sz = pd.GetSize()
                pads_by_net.setdefault(n, []).append(
                    (pos.x, pos.y, max(sz.x, sz.y) / 2 + int(0.15e6)))
    owned = set()
    for n, pads in pads_by_net.items():
        pts = locked_pts.get(n, [])
        if pts and all(any((px - x) ** 2 + (py - y) ** 2 <= r * r for x, y in pts)
                       for px, py, r in pads):
            owned.add(n)
    doomed, report, echoes = [], {}, 0
    for t in board.GetTracks():
        if t.IsLocked():
            continue
        n = t.GetNetname() or ""
        if n not in locked_by_net:
            continue
        if n in owned:
            doomed.append(t)
            report[n] = report.get(n, 0) + 1
            continue
        if t.Type() != pcbnew.PCB_VIA_T:
            s_, e_ = t.GetStart(), t.GetEnd()
            k = (round(s_.x / 1e4), round(s_.y / 1e4), round(e_.x / 1e4), round(e_.y / 1e4))
            if k in locked_geo:
                doomed.append(t)
                echoes += 1
    for t in doomed:
        # Delete (not Remove): Remove orphans the SWIG proxy -> a 'memory leak of
        # type PCB_TRACK*' warning PER ITEM at GC (measured: 20k-line log flood).
        board.Delete(t)
    doomed.clear()
    pcbnew.SaveBoard(out_path or board_path, board)
    if echoes:
        report["_echoes"] = echoes
    return report


def collapse_redundant_pth_transitions(board, *, clearance_mm=0.20):
    """Remove Freerouting's PTH-pad -> track -> via -> other-layer-track dogbone.

    A plated through-hole pad already spans every enabled copper layer. When a
    through via has exactly two incident same-net tracks and one returns to a
    same-net PTH pad, the via is a redundant layer transition: move that short
    pad-side track onto the continuation layer and remove the via. Geometry is
    unchanged. The repair stays conservative: locked copper, vias touching a
    same-net zone, and a relayered stub that would collide with foreign copper
    are left alone.
    """
    clearance = int(float(clearance_mm) * 1e6)
    tracks = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
    vias = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    pads = [(fp, pad) for fp in board.GetFootprints() for pad in fp.Pads()]

    by_endpoint = {}
    for track in tracks:
        for point in (track.GetStart(), track.GetEnd()):
            by_endpoint.setdefault((point.x, point.y, track.GetNetCode()), []).append(track)

    def _other_end(track, point):
        return track.GetEnd() if track.GetStart() == point else track.GetStart()

    def _pth_at(point, netcode, layer_a, layer_b):
        for footprint, pad in pads:
            if (pad.GetNetCode() == netcode
                    and pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
                    and pad.IsOnLayer(layer_a) and pad.IsOnLayer(layer_b)
                    and pad.HitTest(point)):
                return footprint, pad
        return None

    def _via_has_zone(via):
        pos, netcode = via.GetPosition(), via.GetNetCode()
        for zone in board.Zones():
            if zone.GetNetCode() != netcode or not zone.IsOnCopperLayer():
                continue
            try:
                if zone.Outline().Collide(pos, 0):
                    return True
            except Exception:                              # noqa: BLE001
                return True                                # uncertainty -> keep it
        return False

    def _foreign_collision(stub, target_layer, netcode):
        old_layer = stub.GetLayer()
        stub.SetLayer(target_layer)
        try:
            shape = stub.GetEffectiveShape(target_layer)
            for item in board.GetTracks():
                if item.GetNetCode() == netcode:
                    continue
                if (item.IsOnLayer(target_layer)
                        and shape.Collide(item.GetEffectiveShape(target_layer), clearance)):
                    return True
            for _footprint, pad in pads:
                if (pad.GetNetCode() != netcode and pad.IsOnLayer(target_layer)
                        and shape.Collide(pad.GetEffectiveShape(target_layer), clearance)):
                    return True
            return False
        finally:
            stub.SetLayer(old_layer)

    removed = []
    for via in list(vias):
        if via.IsLocked() or _via_has_zone(via):
            continue
        point = via.GetPosition()
        incident = by_endpoint.get((point.x, point.y, via.GetNetCode()), [])
        if len(incident) != 2 or any(track.IsLocked() for track in incident):
            continue
        a, b = incident
        if a.GetLayer() == b.GetLayer():
            continue
        chosen = None
        for stub, continuation in ((a, b), (b, a)):
            pad_end = _other_end(stub, point)
            owner = _pth_at(pad_end, via.GetNetCode(), stub.GetLayer(),
                            continuation.GetLayer())
            if owner and not _foreign_collision(stub, continuation.GetLayer(),
                                                via.GetNetCode()):
                chosen = (stub, continuation, owner, pad_end)
                break
        if chosen is None:
            continue
        stub, continuation, (footprint, pad), _pad_end = chosen
        old_name = board.GetLayerName(stub.GetLayer())
        new_name = board.GetLayerName(continuation.GetLayer())
        stub.SetLayer(continuation.GetLayer())
        board.Delete(via)
        removed.append({"ref": footprint.GetReference(), "pad": pad.GetPadName(),
                        "net": stub.GetNetname(), "from": old_name, "to": new_name,
                        "stub_mm": round(stub.GetLength() / 1e6, 3)})
    return {"removed": len(removed), "detail": removed}


def synthesize_missing_layer_junction_vias(
        board, *, netclass_resolver=None, lock=False, tol_mm=0.02):
    """Heal exact cross-layer track junctions that have no transition barrel.

    A Specctra import can occasionally return two same-net track endpoints at
    the nominally same coordinate on different copper layers, separated only
    by decimal round-trip noise, without the via that makes that apparent
    junction electrical.  KiCad then reports a dangling track and an extra
    ratsnest even though the router visibly drew a continuous path.  Add a
    project-sized through via only when all of these facts are proven:

    * at least two same-net track layers meet inside a 20 um endpoint cluster;
    * no existing same-net via already spans the point;
    * no same-net plated through-hole pad spans every participating layer (a
      THT land already provides the inter-layer connection); and
    * the centralized all-layer via/pad/copper guard accepts the final
      netclass diameter and drill.

    This is an importer repair, not a router: it never bridges separated
    coordinates and it refuses via-in-SMD-pad or foreign-copper conflicts.
    """
    from collections import defaultdict

    endpoints = defaultdict(list)
    tracks = [track for track in board.GetTracks()
              if track.GetClass() in ("PCB_TRACK", "PCB_ARC")
              and track.GetNetCode() > 0]
    for track in tracks:
        for point in (track.GetStart(), track.GetEnd()):
            endpoints[track.GetNetCode()].append((point.x, point.y, track))

    vias = [track for track in board.GetTracks()
            if track.GetClass() == "PCB_VIA"]
    pads = [pad for fp in board.GetFootprints() for pad in fp.Pads()
            if pad.GetNetCode() > 0]
    candidates = added = refused = 0
    detail = []
    tol = _nm(tol_mm)
    clusters = []
    # SES coordinates can differ by a few tens of nanometres after decimal
    # round-trip.  KiCad still flags those apparent junctions as dangling, so
    # form endpoint clusters inside the same 20 um tolerance used by the
    # dangling-track inspector.  Union only within a net and use an x-sorted
    # sweep so this remains cheap on a dense board.
    for net_code, rows in sorted(endpoints.items()):
        rows = sorted(rows, key=lambda row: (row[0], row[1]))
        parent = list(range(len(rows)))

        def _find(index):
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def _join(a, b):
            ra, rb = _find(a), _find(b)
            if ra != rb:
                parent[rb] = ra

        for i, (x, y, _track) in enumerate(rows):
            for j in range(i + 1, len(rows)):
                x2, y2, _track2 = rows[j]
                if x2 - x > tol:
                    break
                if abs(y2 - y) <= tol and (x2 - x) ** 2 + (y2 - y) ** 2 <= tol ** 2:
                    _join(i, j)
        grouped = defaultdict(list)
        for index, row in enumerate(rows):
            grouped[_find(index)].append(row)
        for members in grouped.values():
            clusters.append((net_code, members))

    for net_code, members in clusters:
        incident = [row[2] for row in members]
        layers = {track.GetLayer() for track in incident}
        if len(layers) < 2:
            continue
        x = int(round(sum(row[0] for row in members) / len(members)))
        y = int(round(sum(row[1] for row in members) / len(members)))
        point = pcbnew.VECTOR2I(x, y)
        if any(via.GetNetCode() == net_code
               and (via.GetPosition().x - x) ** 2
               + (via.GetPosition().y - y) ** 2 <= tol ** 2 for via in vias):
            continue
        # A real THT/multilayer pad is already copper on every participating
        # layer.  Do not repeat the historical false-positive behavior that
        # drew a needless via/ratsnest beside through-hole connectors.
        spans = False
        for pad in pads:
            if pad.GetNetCode() != net_code or not pad.HitTest(point):
                continue
            pad_layers = set(pad.GetLayerSet().CuStack())
            if layers <= pad_layers:
                spans = True
                break
        if spans:
            continue
        candidates += 1
        net_name = incident[0].GetNetname()
        spec = (dict(netclass_resolver(net_name) or {})
                if netclass_resolver is not None else {})
        diameter = float(spec.get("via_diameter") or 0.6)
        drill = float(spec.get("via_drill") or 0.3)
        clearance = float(spec.get("clearance") or 0.2)
        if not _via_spot_clear(
                board, point, _nm(diameter), _nm(clearance), {net_code},
                drill_nm=_nm(drill), net_code=net_code):
            refused += 1
            detail.append({"net": net_name, "x_mm": x / MM,
                           "y_mm": y / MM, "status": "refused"})
            continue
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(point)
        via.SetWidth(_nm(diameter))
        via.SetDrill(_nm(drill))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNetCode(net_code)
        via.SetLocked(bool(lock))
        board.Add(via)
        vias.append(via)
        added += 1
        detail.append({"net": net_name, "x_mm": x / MM, "y_mm": y / MM,
                       "diameter_mm": diameter, "drill_mm": drill,
                       "status": "added"})
    if added:
        board.BuildConnectivity()
    return {"candidates": candidates, "added": added,
            "refused": refused, "detail": detail}


def _snapshot_locked_via_geometry(board):
    """Capture exact geometry for vias the source board declares immutable.

    KiCad's Specctra SES importer rebuilds existing vias from the session's
    global via template.  That silently changed locked, fabrication-qualified
    0.35/0.25 mm POFVs into 0.60/0.30 mm vias on the six-layer Hub.  The larger
    lands then overhung narrow SMD pads even though the pre-route board passed
    the same via-on-pad gate.  A locked item is an input contract, so retain its
    diameter and drill across the lossy DSN/SES interchange.

    Net name plus exact position is stable across the import even when KiCad
    replaces UUIDs.  Multiple locked vias at one net/position would be an
    ambiguous source board and are deliberately left out of the snapshot.
    """
    rows = {}
    ambiguous = set()
    for item in board.GetTracks():
        if item.GetClass() != "PCB_VIA" or not item.IsLocked():
            continue
        pos = item.GetPosition()
        key = (item.GetNetname() or "", int(pos.x), int(pos.y))
        if key in rows:
            ambiguous.add(key)
            continue
        rows[key] = {
            "diameter": int(item.GetWidth(item.TopLayer())),
            "drill": int(item.GetDrillValue()),
            "top_layer": int(item.TopLayer()),
            "bottom_layer": int(item.BottomLayer()),
            "via_type": int(item.GetViaType()),
        }
    for key in ambiguous:
        rows.pop(key, None)
    return rows


def _restore_locked_via_geometry(board, snapshot):
    """Restore a :func:`_snapshot_locked_via_geometry` after SES import."""
    restored = []
    recreated = []
    relocked = []
    missing = set(snapshot)
    by_key = {}
    ambiguous = set()
    for item in board.GetTracks():
        if item.GetClass() != "PCB_VIA":
            continue
        pos = item.GetPosition()
        key = (item.GetNetname() or "", int(pos.x), int(pos.y))
        if key in by_key:
            ambiguous.add(key)
            continue
        by_key[key] = item
    for key in ambiguous:
        by_key.pop(key, None)

    for key, source in snapshot.items():
        item = by_key.get(key)
        if item is None:
            net = board.FindNet(key[0])
            if net is None:
                continue
            item = pcbnew.PCB_VIA(board)
            item.SetPosition(pcbnew.VECTOR2I(key[1], key[2]))
            item.SetViaType(source.get("via_type", pcbnew.VIATYPE_THROUGH))
            item.SetLayerPair(source["top_layer"], source["bottom_layer"])
            item.SetWidth(source["diameter"])
            item.SetDrill(source["drill"])
            item.SetNet(net)
            item.SetLocked(True)
            board.Add(item)
            missing.discard(key)
            recreated.append({
                "net": key[0],
                "at_mm": [round(key[1] / MM, 6),
                          round(key[2] / MM, 6)],
                "diameter_mm": round(source["diameter"] / MM, 6),
                "drill_mm": round(source["drill"] / MM, 6),
            })
            continue
        source = snapshot.get(key)
        missing.discard(key)
        before = (int(item.GetWidth(item.TopLayer())),
                  int(item.GetDrillValue()))
        after = (source["diameter"], source["drill"])
        if before != after:
            item.SetWidth(after[0])
            item.SetDrill(after[1])
            restored.append({
                "net": key[0],
                "at_mm": [round(key[1] / MM, 6), round(key[2] / MM, 6)],
                "from_mm": [round(before[0] / MM, 6),
                            round(before[1] / MM, 6)],
                "to_mm": [round(after[0] / MM, 6),
                          round(after[1] / MM, 6)],
            })
        if not item.IsLocked():
            item.SetLocked(True)
            relocked.append({
                "net": key[0],
                "at_mm": [round(key[1] / MM, 6), round(key[2] / MM, 6)],
            })
    return {
        "restored": len(restored),
        "recreated": len(recreated),
        "relocked": len(relocked),
        "missing": len(missing),
        "detail": restored,
        "recreated_detail": recreated,
        "relocked_detail": relocked,
        "missing_keys": sorted(missing),
    }


def _snapshot_footprint_placement(board):
    """Capture the exact placement authority before a lossy SES round trip.

    Routing backends own copper, not component placement.  Specctra sessions
    nevertheless carry component transforms, and KiCad's SES importer applies
    those transforms while importing routes.  That can silently move a part
    after the placer, courtyard checks, and pour-first solve have all accepted
    it.  Reference designators are the stable interchange identity here; a
    duplicate/empty reference is ambiguous and therefore excluded so the
    restore below can fail closed instead of choosing an arbitrary instance.
    """
    rows = {}
    ambiguous = set()
    for footprint in board.GetFootprints():
        ref = str(footprint.GetReference() or "")
        if not ref or ref in rows:
            ambiguous.add(ref)
            continue
        position = footprint.GetPosition()
        rows[ref] = {
            "x": int(position.x),
            "y": int(position.y),
            "orientation": float(footprint.GetOrientationDegrees()),
            "layer": int(footprint.GetLayer()),
            "locked": bool(footprint.IsLocked()),
        }
    for ref in ambiguous:
        rows.pop(ref, None)
    return rows


def _restore_footprint_placement(board, snapshot):
    """Restore placer-owned footprint transforms after SES import.

    A side change is refused rather than repaired with ``SetLayer`` because a
    footprint flip also transforms pad/graphic layers.  Ordinary position,
    rotation, and lock drift are restored exactly.  Missing references are a
    destructive interchange failure and are reported to the caller.
    """
    by_ref = {}
    duplicates = set()
    for footprint in board.GetFootprints():
        ref = str(footprint.GetReference() or "")
        if not ref or ref in by_ref:
            duplicates.add(ref)
            continue
        by_ref[ref] = footprint
    for ref in duplicates:
        by_ref.pop(ref, None)

    restored = []
    missing = []
    side_changed = []
    for ref, source in sorted((snapshot or {}).items()):
        footprint = by_ref.get(ref)
        if footprint is None:
            missing.append(ref)
            continue
        if int(footprint.GetLayer()) != int(source["layer"]):
            side_changed.append(ref)
            continue
        position = footprint.GetPosition()
        before = {
            "x": int(position.x),
            "y": int(position.y),
            "orientation": float(footprint.GetOrientationDegrees()),
            "locked": bool(footprint.IsLocked()),
        }
        after = {
            "x": int(source["x"]),
            "y": int(source["y"]),
            "orientation": float(source["orientation"]),
            "locked": bool(source["locked"]),
        }
        if before == after:
            continue
        footprint.SetPosition(pcbnew.VECTOR2I(after["x"], after["y"]))
        footprint.SetOrientationDegrees(after["orientation"])
        footprint.SetLocked(after["locked"])
        restored.append({
            "ref": ref,
            "from_mm": [round(before["x"] / MM, 6),
                        round(before["y"] / MM, 6),
                        round(before["orientation"], 6)],
            "to_mm": [round(after["x"] / MM, 6),
                      round(after["y"] / MM, 6),
                      round(after["orientation"], 6)],
        })
    return {
        "restored": len(restored),
        "missing": missing,
        "side_changed": side_changed,
        "detail": restored,
    }


def import_ses(board_path: str, ses_path: str, out_path: str, *,
               fill_zones: bool = True, fix_annular: bool = True, power_pours=(),
               kelvin_taps: bool = True, skip_locked_taps: bool = False,
               completed_nets=()) -> str:
    """Import a Freerouting .ses back into the board and save it.

    Loads *board_path*, calls ImportSpecctraSES(board, ses_path), then in order:
      1. lay any *power_pours* (additive same-net copper -- see add_power_pours)
      2. if *fix_annular*, repair thin-annular vias (see normalize_via_annular)
      3. if *fill_zones*, FILL the copper zones
    then SaveBoard(out_path, board). Returns *out_path*.

    Zone fill is essential: the SES import lays tracks/vias but does NOT fill copper pours
    (neither does kicad-cli -- only the real ZONE_FILLER engine fills). Without it, every
    via Freerouting drops into a GND/power plane reads as DANGLING (copper on one side only)
    and every plane-connected pad reads as UNCONNECTED. On the EPS module this fill alone
    takes structural DRC 99 -> 53 and unconnected 71 -> 2. The board's own zone settings are
    honoured (e.g. island_removal_mode), so isolated islands are dropped per the design.

    *fix_annular* (default on) then clears Freerouting's thin-annular vias, and *power_pours*
    lets the caller fatten the high-current nets with real pours AFTER the route -- together
    these took the EPS candidate from DRC 99 to 4 (4 = an unrelated decorative-logo issue)
    with both hard gates still passing.
    """
    board = pcbnew.LoadBoard(board_path)
    _completed_nets = {str(net) for net in (completed_nets or ()) if net}
    import_report = {"completed_nets": sorted(_completed_nets)}
    # Capture pre-materialized pipeline rail ownership before the nowhere
    # reaper is allowed to remove a now-unreachable zone.  Once that zone is
    # gone, its name/net marker cannot be recovered from the output artifact.
    _cleanup_pickup_nets = _pipeline_power_pickup_nets(board, power_pours)
    _locked_vias = _snapshot_locked_via_geometry(board)
    _footprint_placement = _snapshot_footprint_placement(board)
    ok = pcbnew.ImportSpecctraSES(board, ses_path)
    if not ok:
        raise RuntimeError(
            f"cec_fr.import_ses: ImportSpecctraSES returned False\n"
            f"  board={board_path!r}\n  ses={ses_path!r}"
        )
    _placement_fix = _restore_footprint_placement(
        board, _footprint_placement)
    if (_placement_fix["missing"] or _placement_fix["side_changed"]):
        raise RuntimeError(
            "cec_fr.import_ses: routing backend changed footprint identity "
            "or board side: %s" % json.dumps(_placement_fix,
                                              sort_keys=True))
    if _placement_fix["restored"]:
        print("[cec_fr] restored %d router-mutated footprint placement(s): %s"
              % (_placement_fix["restored"],
                 _placement_fix["detail"][:8]), file=sys.stderr)
    _locked_via_fix = _restore_locked_via_geometry(board, _locked_vias)
    if (sum(_locked_via_fix.get(key, 0) for key in
            ("restored", "recreated", "relocked"))
            or _locked_via_fix["missing"]):
        print("[cec_fr] locked-via contract: %d resized, %d recreated, "
              "%d relocked, %d unresolved; %s"
              % (_locked_via_fix["restored"],
                 _locked_via_fix["recreated"],
                 _locked_via_fix["relocked"],
                 _locked_via_fix["missing"],
                 (_locked_via_fix["detail"]
                  + _locked_via_fix["recreated_detail"]
                  + _locked_via_fix["relocked_detail"])[:8]),
              file=sys.stderr)
    if _locked_via_fix["missing"]:
        raise RuntimeError(
            "cec_fr.import_ses: protected via identity unresolved: %s" %
            _locked_via_fix["missing_keys"][:8])
    # LAYER POLICY, import half (complements the export-side (type power) rewrite):
    # plane layers carry ZONES, never tracks. FR may still drop POWER-classified net
    # segments onto a (type power) layer (Specctra semantics allow it; measured: two
    # 4.2mm /SENSEC*_HI segments on the EPS GND plane) -- strip ALL track segments on
    # detected plane layers before the fill (the pours/zones carry those nets).
    if os.environ.get("CEC_FR_PLANE_POLICY", "1") != "0":
        _plane_names = set(plane_layers(board))
        if _plane_names:
            # never strip LOCKED copper (codex stack-audit 2026-07-19 #4: a
            # locked force trunk on a plane-detected layer would be silently
            # erased -- latent on today's boards, measured: the 24-pin's In2
            # is freed/renamed PWR_RT and not plane-detected, but the hole is
            # real for any future planed-layer locked lay)
            _doomed = [t for t in board.GetTracks()
                       if t.GetClass() == "PCB_TRACK" and not t.IsLocked()
                       and board.GetLayerName(t.GetLayer()) in _plane_names]
            for t in _doomed:
                board.Remove(t)
            if _doomed:
                print(f"[cec_fr] layer policy: stripped {len(_doomed)} track segment(s) "
                      f"from plane layer(s) {sorted(_plane_names)}", file=sys.stderr)
    if os.environ.get("CEC_COLLAPSE_THT_TRANSITIONS", "1") != "0":
        _pth_fix = collapse_redundant_pth_transitions(board)
        if _pth_fix["removed"]:
            print("[cec_fr] collapsed %d redundant PTH layer-transition via(s): %s"
                  % (_pth_fix["removed"], _pth_fix["detail"][:8]), file=sys.stderr)
    if os.environ.get("CEC_HEAL_LAYER_JUNCTIONS", "1") != "0":
        _junction_fix = synthesize_missing_layer_junction_vias(
            board, netclass_resolver=_project_netclass_resolver(board_path))
        if _junction_fix["added"] or _junction_fix["refused"]:
            print("[cec_fr] layer-junction repair: %d/%d via(s) added; "
                  "%d refused"
                  % (_junction_fix["added"], _junction_fix["candidates"],
                     _junction_fix["refused"]), file=sys.stderr)
    # POUR LAY MOVED (2026-07-24 trace #2, the owner's "fixes did not land"
    # class): pours are laid ONCE at the single post-conversion site just
    # before fix_annular below. The lay that used to sit HERE ran before the
    # bond/scrap filter (its "already filtered EARLY" comment was stale -- the
    # only synthesize_pour_bonds call sits AFTER this point) and before the
    # slab/over-under conversion, so raw RECTS landed on the board while the
    # converted slab dicts were reassigned into power_pours and then consumed
    # by NOTHING (measured on the published s416: every non-GND zone verts=4 =
    # rect; zero slabs ever reached copper despite the conversion printing
    # success). Filter -> via stages -> conversion -> lay is the real order.
    if kelvin_taps:
        # GENERATIVE four-wire Kelvin tap: lay the short inner-edge -> IN+/IN- F.Cu stub into the
        # window derive_power_pours leaves open. ADDITIVE same-net (after the route) -> never strands
        # the sense; self-gating no-op on shared-bus / filtered-lane boards. (env kill-switch:
        # CEC_KELVIN_TAPS=0 reverts to the un-tapped behaviour for an A/B.)
        # PRECISION PRE-FR TAPS (cec_precision_route / plan §4 R2): when the board already carries
        # LOCKED _HI/_LO tap copper -- laid + locked on the uncontended board pre-FR and PROTECTed
        # through FR -- re-synthesizing here would DOUBLE-LAY the same stubs (synthesize_kelvin_taps
        # is NOT idempotent). skip_locked_taps=True detects that copper and skips only the tap
        # synthesis (the force-via bridge below still runs). Default False = today's post-route tap.
        # PER-PAIR coverage (codex stack-audit 2026-07-19 #9: the old blanket
        # any-locked-_HI/_LO check let locked TRUNK copper -- the 24-pin force
        # rails share those nets -- suppress ALL tap synthesis while the INA
        # pads sat FR-excluded = open sense inputs). A pair counts covered
        # only when locked copper actually CONTACTS an INA input pad on each
        # of its nets.
        _has_locked_taps = False
        _uncovered = None
        if skip_locked_taps:
            def _net_tap_covered(net):
                # detection via _locked_pad_contact (2026-07-25): endpoint HitTest at
                # the locked track's HALF-WIDTH, so an authored tap terminating on the
                # pad edge (not centerline) still counts as coverage.
                _pads = [p for fp in board.GetFootprints() for p in fp.Pads()
                         if p.GetNetname() == net
                         and "INA" in (fp.GetValue() or "").upper()]
                if not _pads:
                    return True                  # no INA pad -> nothing owed
                return any(_locked_pad_contact(board, p) for p in _pads)
            _prs = _board_kelvin_pairs(board)
            _uncovered = [pr for pr in _prs
                          if not (_net_tap_covered(pr[0]) and _net_tap_covered(pr[1]))]
            _has_locked_taps = bool(_prs) and not _uncovered
            if _uncovered:
                print(f"[cec_fr] kelvin taps: {len(_uncovered)}/{len(_prs)} pair(s) "
                      f"UNCOVERED by locked tap copper: {_uncovered}", file=sys.stderr)
        if os.environ.get("CEC_KELVIN_TAPS", "1") != "0" and not _has_locked_taps:
            kt = synthesize_kelvin_taps(
                board, kelvin_pairs=(_uncovered if skip_locked_taps else None))
            if kt["taps"]:
                print(f"[cec_fr] kelvin taps: laid {kt['taps']} inner-edge stub(s) "
                      f"{kt['by_net']}", file=sys.stderr)
            if kt.get("covered"):
                print(f"[cec_fr] kelvin taps: covered legs skipped (locked tap present) "
                      f"{kt['covered']}", file=sys.stderr)
            if kt.get("refused"):
                print(f"[cec_fr] kelvin taps: REFUSED {kt['refused']}", file=sys.stderr)
        elif _has_locked_taps:
            print("[cec_fr] kelvin taps: every pair carries LOCKED pad-contact tap copper -- "
                  "skipping re-synthesis (precision pre-FR taps already laid + protected)",
                  file=sys.stderr)
        # SLAB POURS (owner-ratified 2026-07-24, docs/slab-pour-design-2026-07-24.md,
        # env-gated for the A/B): replace the asks' RECT geometry with shaved
        # slabs -- maximal coverage minus contested space, fragments touching no
        # own-net anchor (the floating-zone rule, structural), and sub-width
        # slivers; min-width invariant reported per (net, layer). The bond/scrap
        # filter is obsolete for slab dicts (anchoring is by construction).
        # SLAB CONVERSION MOVED AFTER THE VIA STAGES (traced 2026-07-24, the
        # owner's vias-outside-pours bug: slabs generated HERE could not anchor
        # on force-vias/pickups that did not exist yet, so barrels landed
        # outside the shaved polys while the bbox coverage test hid it). See
        # the post-pickup block below; only the rect-dict filter stays early.
        if False and power_pours and os.environ.get("CEC_SLAB_POUR", "0") == "1":
            try:
                import cec_slab_pour
                _sp, _srep = cec_slab_pour.synthesize_slab_pours(board, power_pours)
                if _sp:
                    _bad = [f"{k[0]}|{k[1]}" for k, v in _srep.items()
                            if not v.get("min_width_ok", True)]
                    print(f"[cec_fr] slab pours: {len(_sp)} slab(s) for "
                          f"{len(_srep)} (net,layer) pair(s)"
                          + (f"; min-width invariant OPEN on {_bad}" if _bad else
                             "; min-width invariant holds"),
                          file=sys.stderr)
                    power_pours = _sp
            except Exception as _se:                     # noqa: BLE001 -- fall back to rects
                print(f"[cec_fr] slab pours FAILED ({_se}) -- rect asks kept",
                      file=sys.stderr)
        # v3 POUR-FIRST FREEZE (owner ruling 2026-07-25, docs/slab-pour-
        # design-2026-07-24.md v3): pours solved on the anchor-only board are
        # SET IN STONE. Frozen nets' ask dicts are superseded HERE -- before
        # the bond/scrap filter, which may DROP dicts and must never touch
        # frozen geometry -- and the frozen dicts join AFTER the filter so
        # the via stages (force vias, pickups) still see the frozen lanes as
        # their targets. A frozen net is never re-solved (found or failed).
        _pf = _pourfirst_state()
        _pf_pours, _pf_vias, _pf_nets = [], [], set()
        if _pf and power_pours:
            _pf_pours, _pf_vias, _pf_nets = (
                _frozen_power_state_parts(_pf))
            _n_pre = len(power_pours)
            power_pours = [p for p in power_pours
                           if p.get("net") not in _pf_nets]
            _mode = "pre-laid" if _pf.get("prelaid") else "frozen"
            print(f"[cec_fr] pour-first: {len(_pf_pours)} {_mode} dict(s) for "
                  f"{len(_pf_nets)} net(s) pass through SET IN STONE "
                  f"({_n_pre - len(power_pours)} live ask dict(s) superseded)",
                  file=sys.stderr)
        # POUR FILTER FIRST (owner catch 2026-07-24: force-vias and pickups
        # consumed the UNFILTERED ask list while the bond/scrap filter ran at
        # the lay site AFTER them -- vias seated into floods the filter then
        # dropped = copper-less vias in the open field, measured 6 at RS1).
        # Filter once, early; every consumer below sees only the kept pours.
        # (Slab dicts pass through it harmlessly: anchored by construction.)
        if power_pours:
            # An explicit over-under ask is not a pre-existing rectangle that
            # must already be bonded; it is an instruction to BUILD a bonded
            # routed object.  Filtering that placeholder before the pickup and
            # conversion stages creates a circular refusal: no bond exists
            # because the lane/vias have not been synthesized, so the ask is
            # dropped and can never be synthesized.  This erased the Hub's
            # +5VSB/+5V_HOLD/PSU_5V_KVM plans after their corridors had already
            # been reserved, leaving 486 unusable keepout cells. Defer only
            # explicit placer asks when over-under is active; ordinary derived
            # rectangles still pass through the original scrap/bond filter.
            _bond_now, _deferred_ou = partition_prebond_pours(
                power_pours, overunder=os.environ.get("CEC_OVERUNDER") == "1")
            _pb = {"planned": 0, "dropped": 0, "scrap": 0, "bonded": 0}
            _bond_kept = []
            if _bond_now:
                _bond_kept, _pb = synthesize_pour_bonds(board, _bond_now)
            power_pours = list(_bond_kept) + _deferred_ou
            if _pb["planned"] or _pb["dropped"] or _pb.get("scrap"):
                print(f"[cec_fr] pour bonds: {_pb['planned']} bond via(s) planted, "
                      f"{_pb['dropped']} unbondable + {_pb.get('scrap', 0)} lace-bound "
                      f"pour(s) dropped ({_pb['bonded']} kept by contact/barrel)",
                      file=sys.stderr)
            if _deferred_ou:
                print(f"[cec_fr] pour bonds: deferred {len(_deferred_ou)} explicit "
                      "ask(s) to over-under lane synthesis", file=sys.stderr)
        if _pf_pours:
            # frozen bridge vias precede the lanes (design step 5: the vias
            # are the copper the lanes land on; ledger inside the adder)
            if _pf_vias:
                _n_pfv = len(add_overunder_vias(board, _pf_vias) or ())
                print(f"[cec_fr] pour-first: {_n_pfv}/{len(_pf_vias)} frozen "
                      "bridge via(s) laid (ledger-clear)", file=sys.stderr)
            power_pours = list(power_pours or ()) + _pf_pours
            for _n, _v in sorted((_pf.get("report") or {}).items()):
                if not _v.get("path_found", True):
                    # v3 set-in-stone: NO slab fallback for a frozen-stage
                    # no-path net -- it lays ONLY its manifolds + guaranteed
                    # patches (the frozen dicts), loudly, never board-wide
                    # coverage sprawl.
                    print(f"[cec_fr] pour-first: {_n} could not route on the "
                          "OPEN board -- laying manifolds + guaranteed "
                          f"patches only (bottleneck {_v.get('bottleneck')})",
                          file=sys.stderr)
        # INNER-POUR force bridge: when the rail pours live on In2 (PWR_RT boards), each SMD
        # shunt pad needs vias down to them -- THT pins pierce natively, SMD pads do not.
        if any(str(p.get("layer")) == "In2.Cu" for p in (power_pours or ())):
            fv = synthesize_force_vias(board, pours=power_pours)
            if fv["vias"]:
                print(f"[cec_fr] force vias: {fv['vias']} via(s)/{fv['stubs']} stub(s) at "
                      f"{fv['pads']} shunt pad(s) -> In2 rail pours", file=sys.stderr)
        # POWER-PICKUP STITCH (2026-07-23, recipe-gated -- the hub power rung):
        # SMD pads on poured/plane nets that FR never reached get stub+via into
        # the covering flood before the fill. Off by default (golden safety).
        if os.environ.get("CEC_POWER_PICKUP", "0") == "1":
            pk = synthesize_power_pickups(board, power_pours)
            if pk["vias"] or pk["skipped"]:
                print(f"[cec_fr] power pickups: {pk['vias']} via(s) at {pk['pads']} "
                      f"stranded pad(s), {pk['skipped']} skipped (no clear slot)",
                      file=sys.stderr)
        # SLAB CONVERSION -- AFTER the via stages (2026-07-24 trace): the masks
        # now anchor on every just-laid force-via/pickup barrel, so slabs COVER
        # their barrels by construction and no via sits outside a shaved poly.
        # placer_ask dicts always slab; CEC_SLAB_POUR=1 slabs everything.
        if power_pours:
            try:
                import cec_slab_pour
                _full = os.environ.get("CEC_SLAB_POUR", "0") == "1"
                # v3 pour-first: the split is the PURE, teeth-tested core
                # (cec_slab_pour.pourfirst_conv_split) -- frozen dicts and
                # frozen NETS never enter the conversion; with no frozen
                # state it reduces exactly to the historical filter.
                _conv, _frozen3, _keep_r3 = cec_slab_pour.pourfirst_conv_split(
                    power_pours, _pf_nets, _full)
                if _conv or _frozen3:
                    # OVER-UNDER POURS (v2, owner-ratified 2026-07-24 late;
                    # docs/slab-pour-design-2026-07-24.md "v2" section: "the
                    # pour is a routed object"). A/B'd against the shave-
                    # slab realization above via CEC_OVERUNDER=1 -- never
                    # enabled by default (opt-in only; see cec_fresh_wave /
                    # cec_synth_pipeline._oracle_env's "overunder" param).
                    # (_conv may be EMPTY under a full pour-first freeze --
                    # then nothing converts and the frozen dicts carry.)
                    _sp3, _sr3 = [], {}
                    if _conv and os.environ.get("CEC_OVERUNDER") == "1":
                        _sp3, _ou_vias, _sr3 = cec_slab_pour.synthesize_overunder_pours(
                            board, _conv)
                        if _ou_vias:
                            # via_list laid BEFORE the lane dicts, per the
                            # design's step 5 ordering (the bridges are the
                            # copper the lanes will land on top of).
                            # len(): the adder returns the PCB_VIA objects
                            # (pre-existing print showed the SWIG list).
                            _n_ouv = len(add_overunder_vias(board, _ou_vias)
                                         or ())
                            print(f"[cec_fr] over-under: {_n_ouv}/{len(_ou_vias)} "
                                  "bridge via(s) laid (ledger-clear)",
                                  file=sys.stderr)
                        # lanes flow into power_pours below and are laid at
                        # the SINGLE lay site (through add_power_pours -- the
                        # same choke point every pour goes through; the
                        # shunt-only F.Cu rule applies identically to an
                        # over-under F lane). Bridge vias above stay laid
                        # in-branch so vias precede lanes (design step 5).
                        _nopath = [n for n, v in _sr3.items()
                                  if not v.get("path_found", True)]
                        print(f"[cec_fr] over-under conversion (post-via): "
                              f"{len(_conv)} dict(s) -> {len(_sp3)} lane(s) "
                              f"for {len(_sr3)} net(s)"
                              + (f"; NO PATH for {_nopath}" if _nopath else ""),
                              file=sys.stderr)
                        if _nopath:
                            # PER-NET SLAB FALLBACK: a no-path net (e.g. two
                            # genuinely disconnected clusters, s415's
                            # /SENSE12V_LO) still deserves coverage on what
                            # copper it HAS -- slab-shave just its dicts so
                            # both fragments get anchored pour, and the gap
                            # stays honestly visible to DRC/lastmile.
                            _fb = [p for p in _conv if p.get("net") in set(_nopath)]
                            if _fb:
                                _spf, _srf = cec_slab_pour.synthesize_slab_pours(
                                    board, _fb)
                                _sp3 = list(_sp3) + list(_spf)
                                print(f"[cec_fr] over-under: slab fallback laid "
                                      f"{len(_spf)} slab(s) for {len(_fb)} "
                                      f"no-path dict(s)", file=sys.stderr)
                        # PRE-FR RESERVATION LEDGER (CEC_POUR_RESERVE):
                        # route_once drops the reservation report next to the
                        # DSN/SES it exported; log reserved-vs-realized per
                        # net and persist the merged view next to the routed
                        # board (<out>.pour-reserve.json) for the wave /
                        # postmortem readout. Absent sidecar (gate off, or a
                        # direct import_ses caller) = silent no-op.
                        try:
                            import json as _json
                            _rsc = os.path.join(
                                os.path.dirname(os.path.abspath(ses_path)),
                                "pour_reserve.json")
                            if os.path.isfile(_rsc):
                                with open(_rsc) as _rf:
                                    _rsv = (_json.load(_rf) or {}).get("report", {})
                                for _n in sorted(set(_rsv) | set(_sr3)):
                                    _r0, _r1 = _rsv.get(_n, {}), _sr3.get(_n, {})
                                    print("[cec_fr] pour-reserve: %s reserved=%s"
                                          " (%s rect(s)) -> realized path_found=%s"
                                          % (_n, _r0.get("reserved"),
                                             _r0.get("rects", 0),
                                             _r1.get("path_found")),
                                          file=sys.stderr)
                                _rsj = (out_path[:-len(".kicad_pcb")]
                                        if out_path.endswith(".kicad_pcb")
                                        else out_path) + ".pour-reserve.json"
                                with open(_rsj, "w") as _wf:
                                    _json.dump(
                                        {"schema": 1, "reserved": _rsv,
                                         "realized": {
                                             k: {"path_found": v.get("path_found"),
                                                 "layers_used": v.get("layers_used"),
                                                 "bottleneck": v.get("bottleneck")}
                                             for k, v in _sr3.items()}},
                                        _wf, indent=1, sort_keys=True,
                                        default=str)
                        except Exception as _re:             # noqa: BLE001
                            print(f"[cec_fr] pour-reserve ledger failed ({_re})",
                                  file=sys.stderr)
                    elif _conv:
                        _sp3, _sr3 = cec_slab_pour.synthesize_slab_pours(board, _conv)
                        _bad3 = [f"{k[0]}|{k[1]}" for k, v in _sr3.items()
                                 if not v.get("min_width_ok", True)]
                        print(f"[cec_fr] slab conversion (post-via): {len(_conv)} "
                              f"dict(s) -> {len(_sp3)} slab(s)"
                              + (f"; min-width OPEN on {_bad3[:4]}" if _bad3 else ""),
                              file=sys.stderr)
                    # GUARANTEED SHUNT PATCHES -- CONDITIONAL under a
                    # pour-first freeze (single-owner ruling 2026-07-25:
                    # the unconditional guarantee was the RS1-starvation
                    # over-correction; the freeze's WHITELIST now owns
                    # patch policy, and re-deriving them here would
                    # resurrect exactly the insurance copper the whitelist
                    # dropped). Frozen nets get NO import-side patches;
                    # non-frozen nets keep the historical guarantee.
                    _gsp3 = [d for d in
                             cec_slab_pour.guaranteed_shunt_patches(board)
                             if d.get("net") not in set(_pf_nets or ())]
                    if _frozen3:
                        _fkeys = {(d.get("net"), tuple(map(tuple,
                                                           d.get("polygon") or ())))
                                  for d in _frozen3}
                        _gsp3 = [d for d in _gsp3
                                 if (d.get("net"),
                                     tuple(map(tuple, d.get("polygon") or ())))
                                 not in _fkeys]
                    _sp3 = list(_sp3) + _gsp3
                    power_pours = _keep_r3 + _sp3
            except Exception as _se3:                    # noqa: BLE001
                # A raw-rectangle fallback resurrects overlapping, order-owned
                # copper. Refuse the candidate so the caller can re-place or
                # change reviewed geometry instead of routing an invalid pour.
                raise RuntimeError("slab conversion failed closed: %s" % _se3) from _se3
    # SINGLE LAY SITE (2026-07-24): every pour dict -- filtered rects, slab
    # polys, over-under lanes, or the raw list when kelvin_taps=False skipped
    # the filter/conversion stages -- lands on the board HERE, exactly once,
    # through add_power_pours (the choke point that owns the shunt-only F.Cu
    # rule). Conversion failure keeps rects in power_pours, so the fallback
    # lay is this same line.
    if power_pours:
        _managed_force_nets = {
            str(p.get("net")) for p in power_pours
            if str(p.get("net") or "").endswith(("_HI", "_LO"))
        }
        if _managed_force_nets:
            _managed_pours = [
                p for p in power_pours if p.get("net") in _managed_force_nets
            ]
            _supplemental_pours = [
                p for p in power_pours if p.get("net") not in _managed_force_nets
            ]
            _replacement = replace_generated_power_pours(
                board, _managed_pours, managed_nets=_managed_force_nets,
                fill=False)
            if _supplemental_pours:
                add_power_pours(board, _supplemental_pours, fill=False)
            print("[cec_fr] generated force-pour replacement: "
                  "%d stale zone(s) -> %d current zone(s)"
                  % (_replacement["removed"], _replacement["added"]),
                  file=sys.stderr)
        else:
            add_power_pours(board, power_pours, fill=False)
    if fix_annular:
        normalize_via_annular(board)
        _nw = normalize_track_width(board)
        if _nw:
            print("[fr] normalized %d sub-minimum track width(s)" % _nw,
                  file=sys.stderr)
        # The output sidecar is copied only after this import returns. Resolve
        # netclasses from the staged source project that already exists, or
        # every candidate is scored with skinny SES geometry and widened only
        # at the final release choke point (candidate and shipped DRC diverge).
        _ng = normalize_netclass_geometry(board, board_path)
        if _ng.get("tracks") or _ng.get("vias"):
            print("[fr] normalized netclass geometry: %d track(s), %d via(s)"
                  % (_ng.get("tracks", 0), _ng.get("vias", 0)), file=sys.stderr)
    if fill_zones:
        # UnFill first: re-filling an already-filled multi-layer zone in one process can
        # segfault this KiCad-10 SWIG build (see cec_route.py fill()).
        for z in board.Zones():
            z.UnFill()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    # A shaped rail pour may pass under isolated surface terminals that could
    # not be proven covered before fill. Re-run against the actual filled
    # polygons before last-mile clustering; then refill around new barrels.
    if (os.environ.get("CEC_POWER_PICKUP", "0") == "1" and fill_zones):
        _post_nets = {p.get("net") for p in (power_pours or ()) if p.get("net")}
        _post_nets.add("GND")
        _post_nets -= _completed_nets
        _post_pk = synthesize_power_pickups(
            board, (), plane_nets=(), filled_zone_nets=tuple(_post_nets))
        if _post_pk["vias"] or _post_pk["skipped"]:
            print(f"[cec_fr] post-fill power pickups: {_post_pk['vias']} via(s) "
                  f"at {_post_pk['pads']} stranded pad(s), "
                  f"{_post_pk['skipped']} skipped (no clear filled slot)",
                  file=sys.stderr)
        if _post_pk["vias"]:
            _pk_ng = normalize_netclass_geometry(board, board_path)
            if _pk_ng.get("tracks") or _pk_ng.get("vias"):
                print("[fr] normalized post-fill pickup netclass geometry: "
                      "%d track(s), %d via(s)"
                      % (_pk_ng.get("tracks", 0), _pk_ng.get("vias", 0)),
                      file=sys.stderr)
            for z in board.Zones():
                z.UnFill()
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    # A single shaped power zone may itself fill as multiple islands.  Bond
    # planning happens before fill and cannot see that split; repair it against
    # the real filled polygons before generic last-mile clustering.
    if (os.environ.get("CEC_ZONE_ISLAND_BRIDGE", "1") != "0" and fill_zones):
        _zib = synthesize_pipeline_zone_island_bridges(
            board, netclass_resolver=_project_netclass_resolver(board_path))
        if _zib["added"] or _zib["refused"]:
            print("[cec_fr] zone-island bridge: %d link(s), %d leg(s), "
                  "%d refused" % (_zib["added"], _zib["legs"],
                                   _zib["refused"]), file=sys.stderr)
        if _zib["added"]:
            for z in board.Zones():
                z.UnFill()
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    # LAST-MILE COMPLETER (2026-07-23, recipe-gated): close <=5mm same-net
    # cluster gaps FR left unfinished (measured on the s120 best: 13 of 30
    # residual unconn were such gaps, incl. both GND criticals). MUST run on a
    # FILLED board -- cluster membership is zone-aware -- so it sits after the
    # fill, and refills when it lands copper (the new legs need foreign fills
    # to re-yield clearance around them).
    if os.environ.get("CEC_LASTMILE", "0") == "1" and fill_zones:
        board.BuildConnectivity()
        lm = synthesize_lastmile(
            board, max_mm=float(os.environ.get("CEC_LASTMILE_MAX_MM", "5.0")),
            netclass_resolver=_project_netclass_resolver(board_path),
            exclude_nets=_completed_nets,
            attempts_per_pair=int(os.environ.get("CEC_LASTMILE_ATTEMPTS", "4")),
            maze_max_mm=float(os.environ.get(
                "CEC_LASTMILE_MAZE_MAX_MM", "5.0")),
            maze_margin_mm=float(os.environ.get(
                "CEC_LASTMILE_MAZE_MARGIN_MM", "2.0")))
        import_report["lastmile"] = lm
        print(f"[cec_fr] lastmile: {lm['closed']} gap(s) closed ({lm['legs']} leg(s)), "
              f"{lm['refused']} refused, {lm['far']} far, "
              f"{lm['cross_layer']} cross-layer", file=sys.stderr)
        if lm["closed"]:
            # The completer creates fresh tracks/vias after the SES geometry
            # normalization above. Grade candidates with those additions at
            # their shipped netclass dimensions too; otherwise ranking sees
            # skinny last-mile copper and the release choke widens it only
            # after selection, changing both DRC and connectivity.
            _lm_ng = normalize_netclass_geometry(board, board_path)
            if _lm_ng.get("tracks") or _lm_ng.get("vias"):
                print("[fr] normalized last-mile netclass geometry: "
                      "%d track(s), %d via(s)"
                      % (_lm_ng.get("tracks", 0), _lm_ng.get("vias", 0)),
                      file=sys.stderr)
            for z in board.Zones():
                z.UnFill()
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    # FINAL ORDINARY-NET COMPLETION: the ordinary last-mile pass is deliberately
    # local.  A second opt-in pass is allowed to spend a bounded whole-board
    # maze search only on non-power, non-differential, non-Kelvin control nets.
    # It either lays exact collision/edge-qualified copper or records the
    # searched refusal; it never converts a ratline into an assumed success.
    if os.environ.get("CEC_LASTMILE_FINAL", "0") == "1" and fill_zones:
        board.BuildConnectivity()
        _resolver = _project_netclass_resolver(board_path)
        _eligible = tuple(
            net for net in _ordinary_final_completion_nets(board, _resolver)
            if net not in _completed_nets)
        _final_limit = float(os.environ.get(
            "CEC_LASTMILE_FINAL_MAX_MM", "100.0"))
        _final_lm = synthesize_lastmile(
            board, max_mm=_final_limit,
            netclass_resolver=_resolver,
            include_nets=_eligible,
            attempts_per_pair=int(os.environ.get(
                "CEC_LASTMILE_FINAL_ATTEMPTS", "8")),
            maze_max_mm=float(os.environ.get(
                "CEC_LASTMILE_FINAL_MAZE_MAX_MM", str(_final_limit))),
            maze_margin_mm=float(os.environ.get(
                "CEC_LASTMILE_FINAL_MAZE_MARGIN_MM", "8.0")))
        _final_lm["eligible_nets"] = list(_eligible)
        import_report["final_completion"] = _final_lm
        print("[cec_fr] final ordinary completion: %d gap(s) closed "
              "(%d leg(s)), %d refused, %d beyond budget"
              % (_final_lm["closed"], _final_lm["legs"],
                 _final_lm["refused"], _final_lm["far"]),
              file=sys.stderr)
        for _row in (_final_lm.get("refused_details") or ())[:8]:
            print("[cec_fr] final completion REFUSED: "
                  f"{_row.get('net')} gap={_row.get('distance_mm')}mm "
                  f"reason={_row.get('reason')}", file=sys.stderr)
        if _final_lm["closed"]:
            _final_ng = normalize_netclass_geometry(board, board_path)
            if _final_ng.get("tracks") or _final_ng.get("vias"):
                print("[fr] normalized final-completion geometry: "
                      "%d track(s), %d via(s)"
                      % (_final_ng.get("tracks", 0),
                         _final_ng.get("vias", 0)), file=sys.stderr)
            for z in board.Zones():
                z.UnFill()
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    # The SES importer can quantize two nominally distinct endpoints onto the
    # same coordinate (or leave them a few nanometres apart).  The resulting
    # zero-area copper cannot close connectivity, but its full track width is
    # still considered by KiCad DRC and can create an otherwise inexplicable
    # foreign-net clearance error.  Sanitize only after every route/completion
    # stage has finished so no later producer can reintroduce the artifact.
    _degenerate = prune_degenerate_tracks(board)
    import_report["degenerate_tracks_removed"] = _degenerate
    if _degenerate:
        print("[fr] removed %d degenerate track segment(s)" % _degenerate,
              file=sys.stderr)
    # INNER GND FILL (owner ruling 2026-07-25, the companion to the power-layer
    # policy): on a board whose second inner is the SIGNAL layer, the space left
    # between routes becomes reference copper rather than nothing. Last thing
    # before the save so it flows around every track and pour already placed;
    # env-gated, so boards that did not opt in are byte-identical.
    # POUR TERMINATION ON THE ARTIFACT (owner ruling 2026-07-24): zones laid by any
    # earlier stage -- materialize landing patches above all -- are clipped out of
    # the shunt tap gaps here, where every route path passes regardless of who laid
    # what. See enforce_pour_termination for why the dict-level clip cannot suffice.
    try:
        enforce_pour_termination(board)
    except Exception as _pe:                            # noqa: BLE001 -- fail-safe
        print(f"[cec_fr] pour termination skipped ({_pe})", file=sys.stderr)
    _igf = (os.environ.get("CEC_INNER_GND_FILL") or "").strip()
    if _igf:
        try:
            add_inner_gnd_fill(board, _igf)
        except Exception as _ge:                        # noqa: BLE001 -- fail-safe
            print(f"[cec_fr] inner GND fill skipped ({_ge})", file=sys.stderr)
    pcbnew.SaveBoard(out_path, board)
    _uuid_report = ensure_unique_board_file_uuids(out_path)
    if _uuid_report["rewritten"]:
        print("[cec_fr] repaired %d duplicate board-item UUID occurrence(s) "
              "across %d repeated ID(s)"
              % (_uuid_report["rewritten"],
                 _uuid_report["duplicate_ids_before"]), file=sys.stderr)
    # The routed artifact is a deliverable, not a naked board file. Preserve
    # its netclasses and custom rules under the routed basename before any
    # fresh-load cleanup or independent DRC step sees it.
    copy_project_sidecars(board_path, out_path)
    if not os.path.isfile(out_path):
        raise RuntimeError(
            f"cec_fr.import_ses: SaveBoard appeared to succeed but {out_path!r} is missing"
        )
    # FLOATING-ZONE CLEANUP (owner requirement 2026-07-24): zones connecting to
    # no pad/via/track are pure decoration -- removed in a FRESH load->save
    # cycle (isolating the 2026-06-09 in-process zone-removal footgun).
    if os.environ.get("CEC_ZONE_CLEANUP", "1") == "1":
        try:
            import cec_slab_pour
            cec_slab_pour.cleanup_floating_zones(out_path)
            # NOWHERE-REAPER (v3 deliverable D, defense-in-depth against the
            # leads-nowhere pour class): active only when a pour-synthesis
            # path is live -- frozen pour-first state, slab conversion, or
            # over-under -- so the golden / plain-derived paths stay
            # byte-identical. Named patches/manifolds/frozen dicts exempt.
            if (os.environ.get("CEC_POURFIRST_STATE")
                    or os.environ.get("CEC_SLAB_POUR") == "1"
                    or os.environ.get("CEC_OVERUNDER") == "1"):
                cec_slab_pour.reap_nowhere_zones(out_path)
        except Exception as _ze:                        # noqa: BLE001
            print(f"[cec_fr] zone cleanup skipped ({_ze})", file=sys.stderr)
    # Zone cleanup above operates on the saved board and can legitimately
    # remove the only inner-layer island beneath a previously valid generated
    # pickup.  Reconcile those pickups against the *post-reaper* artifact, not
    # the stale in-memory fill.  Scope discovery to the opted-in power/ground
    # rails so hand-authored signal vias are never candidates.
    if os.environ.get("CEC_POWER_PICKUP", "0") == "1" and fill_zones:
        try:
            _pcp = prune_post_cleanup_power_pickups(
                out_path, _cleanup_pickup_nets)
            if _pcp["vias"] or _pcp["stubs"]:
                print("[cec_fr] post-zone-cleanup pickup prune: "
                      "%d via(s), %d stub(s), %d unlanded POFV(s); %s"
                      % (_pcp["vias"], _pcp["stubs"],
                         _pcp["unlanded_pofv"], _pcp["detail"][:8]),
                      file=sys.stderr)
        except Exception as _pe:                        # noqa: BLE001
            print(f"[cec_fr] post-zone-cleanup pickup prune skipped ({_pe})",
                  file=sys.stderr)
    # FINAL-ARTIFACT ISLAND REPAIR: cleanup_floating_zones refills the saved
    # board, pour termination may reshape a rail at that refill, and pickup
    # pruning can trigger one final refill of its own.  The earlier in-memory
    # bridge pass cannot certify copper outlines that do not exist yet.  Run
    # the identical guarded rule only after every zone-mutating stage, so the
    # artifact handed to DRC/ranking is the artifact that was inspected.
    if (os.environ.get("CEC_ZONE_ISLAND_BRIDGE", "1") != "0" and fill_zones):
        try:
            _final_zib = repair_post_cleanup_zone_islands(out_path)
            if _final_zib["added"] or _final_zib["refused"]:
                print("[cec_fr] final-artifact zone-island bridge: "
                      "%d link(s), %d leg(s), %d refused"
                      % (_final_zib["added"], _final_zib["legs"],
                         _final_zib["refused"]), file=sys.stderr)
        except Exception as _fze:                       # noqa: BLE001
            print("[cec_fr] final-artifact zone-island bridge skipped "
                  f"({_fze})", file=sys.stderr)
    # A bridge attempt may leave a locked via and an isolated zone mutually
    # sustaining one another without reaching any real terminal.  Settle the
    # generated power-object graph after *all* bridge/fill mutations so the
    # deliverable cannot retain that two-item dead cycle.
    if os.environ.get("CEC_POWER_PICKUP", "0") == "1" and fill_zones:
        try:
            _settled = settle_generated_power_artifact(
                out_path, _cleanup_pickup_nets)
            _removed = sum(
                row["dead_zone_vias"].get("vias", 0)
                + row["floating_zones"] + row["nowhere_items"]
                for row in _settled["rounds"])
            if _removed:
                print("[cec_fr] generated power artifact settled: "
                      f"{_removed} dead item(s) removed across "
                      f"{len(_settled['rounds'])} round(s)", file=sys.stderr)
        except Exception as _se:                       # noqa: BLE001
            print("[cec_fr] generated power artifact settling skipped "
                  f"({_se})", file=sys.stderr)
    _IMPORT_REPORTS[os.path.abspath(out_path)] = import_report
    return out_path


# ---------------------------------------------------------------------------
# bake_hints
# ---------------------------------------------------------------------------
def _project_netclass_resolver(board_path):
    """Return a ``net name -> class dict`` resolver for *board_path*.

    KiCad's DSN exporter carries the class table, but Freerouting may choose its
    own via geometry and :func:`normalize_netclass_geometry` subsequently raises
    that geometry to the class contract.  Pre-route via exclusions therefore
    have to use the *eventual* class diameter rather than Freerouting's smaller
    temporary land.  An absent/broken project fails to the ordinary 0.6/0.3 mm
    router geometry instead of silently emitting no protection.
    """
    fallback = {"name": "Default", "via_diameter": 0.6, "via_drill": 0.3}
    pro_path = (board_path[:-len(".kicad_pcb")] + ".kicad_pro"
                if board_path.endswith(".kicad_pcb") else "")
    try:
        with open(pro_path, encoding="utf-8") as source:
            ns = (json.load(source).get("net_settings") or {})
        classes = {c.get("name"): c for c in (ns.get("classes") or ())
                   if c.get("name")}
        assignments = ns.get("netclass_assignments") or {}
        patterns = [(row.get("netclass"), row.get("pattern"))
                    for row in (ns.get("netclass_patterns") or ())
                    if row.get("netclass") in classes and row.get("pattern")]
    except Exception:                                      # noqa: BLE001
        classes, assignments, patterns = {}, {}, []

    default = classes.get("Default") or fallback

    def resolve(net):
        chosen = assignments.get(net)
        if isinstance(chosen, list):
            chosen = chosen[0] if chosen else None
        if chosen in classes:
            return classes[chosen]
        for name, pattern in patterns:
            if fnmatch.fnmatchcase(net, pattern):
                return classes[name]
        return default

    return resolve


def _shapely_pad_polygon(pad):
    """Return a cleaned exact copper polygon for one surface pad, or ``None``.

    ``GetEffectivePolygon`` includes rotation, round-rect radii, and custom pad
    primitives.  Falling back to an oriented size rectangle is conservative:
    it may reserve a little extra via space, but cannot permit a via/pad overlap.
    """
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    polys = []
    try:
        layers = list(pad.GetLayerSet().CuStack())
        shape = pad.GetEffectivePolygon(layers[0])
        for oi in range(shape.OutlineCount()):
            outline = shape.Outline(oi)
            pts = [(outline.CPoint(i).x / MM, outline.CPoint(i).y / MM)
                   for i in range(outline.PointCount())]
            if len(pts) >= 3:
                polys.append(Polygon(pts))
    except Exception:                                      # noqa: BLE001
        polys = []
    if polys:
        geom = unary_union(polys).buffer(0)
        if not geom.is_empty:
            return geom

    try:
        pos, size = pad.GetPosition(), pad.GetSize()
        hx, hy = size.x / (2 * MM), size.y / (2 * MM)
        if hx <= 0 or hy <= 0:
            return None
        geom = Polygon(((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)))
        from shapely import affinity
        geom = affinity.rotate(geom, pad.GetOrientationDegrees(), origin=(0, 0))
        return affinity.translate(geom, pos.x / MM, pos.y / MM)
    except Exception:                                      # noqa: BLE001
        return None


def smd_via_keepouts(board_path, *, edge_margin_mm=0.01, quad_segs=8):
    """Build via-only rule-area hints that prevent illegal SMD via-in-pad.

    For a via land of radius *r*, the forbidden centre region is the pad copper
    dilated by *r*, less any pad core eroded by *r* that can contain an approved
    POFV land in full.  This is the same physical distinction enforced after
    routing by ``via-on-pad``: a qualified, fully-contained same-net POFV may
    remain possible, while edge overlaps and pads too narrow for the via are
    reserved from Freerouting.  All pad regions are unioned before emission so
    a real board gets a handful of rule areas, not hundreds of independent
    zones.  The areas block vias only; traces and zone fills retain pad access.
    """
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    board = pcbnew.LoadBoard(board_path)
    resolve = _project_netclass_resolver(board_path)
    profile_name = _fab.board_profile_name(board)
    profile = _fab.PROFILES.get(profile_name)
    forbidden = []
    pad_count = 0
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            try:
                if int(pad.GetAttribute()) != int(pcbnew.PAD_ATTRIB_SMD):
                    continue
            except Exception:                            # noqa: BLE001
                continue
            geom = _shapely_pad_polygon(pad)
            if geom is None or geom.is_empty:
                continue
            spec = resolve(pad.GetNetname() or "")
            dia = max(0.01, float(spec.get("via_diameter") or 0.6))
            drill = max(0.01, float(spec.get("via_drill") or 0.3))
            radius = dia / 2.0
            # A small positive margin turns boundary/tessellation ambiguity into
            # deterministic avoidance.  It is via-only, so it cannot strand the
            # trace that must terminate on this pad.
            outer = geom.buffer(radius + max(0.0, edge_margin_mm),
                                quad_segs=quad_segs, join_style=1)
            safe = None
            dim_ok, _why = _fab.pofv_dimensions(profile, dia, drill)
            if dim_ok:
                safe = geom.buffer(-radius, quad_segs=quad_segs, join_style=1)
            if safe is not None and not safe.is_empty:
                outer = outer.difference(safe)
            if not outer.is_empty:
                forbidden.append(outer)
                pad_count += 1

    if not forbidden:
        return []
    merged = unary_union(forbidden).buffer(0)
    pieces = ([merged] if merged.geom_type == "Polygon" else
              [g for g in getattr(merged, "geoms", ())
               if g.geom_type == "Polygon"])
    # The pipeline permits through vias only, so every routed via occupies both
    # surfaces.  Emitting the same geometry on all six layers bloats the DSN by
    # 3x without adding protection; one surface hit is sufficient, and both
    # surfaces cover SMD pads on either side.
    enabled = set(_fab.enabled_copper_layers(board))
    layers = tuple(layer for layer in ("F.Cu", "B.Cu") if layer in enabled)
    out = []
    for i, piece in enumerate(pieces):
        if piece.is_empty or piece.area < 1e-6:
            continue
        polygon = list(piece.exterior.coords)[:-1]
        holes = [list(ring.coords)[:-1] for ring in piece.interiors]
        if len(polygon) < 3:
            continue
        out.append({
            "name": "SMD_VIA_GUARD_%03d" % i,
            "polygon": polygon,
            "holes": holes,
            "layers": layers,
            "allow_tracks": True,
            "allow_vias": False,
            "block_fills": False,
            "source_pads": pad_count,
        })
    return out


def decorative_copper_keepouts(board_path, *, clearance_mm=0.30):
    """Reserve copper artwork on only the layers where that artwork exists.

    A logo is legitimate exposed copper, but a routed via through it merges the
    decorative island into an electrical net and creates a real clearance fault.
    The previous reactive repair needed one failed routing iteration before it
    learned this every wave.  Emit a no-track/no-via rule area around each LOGO
    footprint's copper graphics up front.  A B.Cu logo does not block legal F.Cu
    routing over it; a B.Cu rule area is sufficient to reject every through-via.
    """
    board = pcbnew.LoadBoard(board_path)
    enabled = set(_fab.enabled_copper_layers(board))
    out = []
    for fp in board.GetFootprints():
        identity = (fp.GetReference() + " " + fp.GetValue()).upper()
        if "LOGO" not in identity:
            continue
        boxes = {}
        for item in fp.GraphicalItems():
            try:
                layer = board.GetLayerName(item.GetLayer())
                if layer not in enabled:
                    continue
                bb = item.GetBoundingBox()
            except Exception:                            # noqa: BLE001
                continue
            row = (bb.GetLeft() / MM, bb.GetTop() / MM,
                   bb.GetRight() / MM, bb.GetBottom() / MM)
            if layer in boxes:
                old = boxes[layer]
                row = (min(old[0], row[0]), min(old[1], row[1]),
                       max(old[2], row[2]), max(old[3], row[3]))
            boxes[layer] = row
        for layer, (x0, y0, x1, y1) in sorted(boxes.items()):
            out.append({
                "name": "decorative_%s_%s" % (
                    fp.GetReference().lower(), layer.replace(".", "")),
                "x0": round(x0 - clearance_mm, 3),
                "y0": round(y0 - clearance_mm, 3),
                "x1": round(x1 + clearance_mm, 3),
                "y1": round(y1 + clearance_mm, 3),
                "layers": (layer,),
                "allow_tracks": False,
                "allow_vias": False,
                "block_fills": False,
            })
    return out


def bake_hints(
    board_path: str,
    out_path: str,
    *,
    keepouts=(),
    copy_pro: bool = True,
) -> str:
    """Copy *board_path* to *out_path*, optionally add rule-area keepout zones, save.

    Each entry in *keepouts* is a dict::

        {"name": str, "x0": float, "y0": float, "x1": float, "y1": float,
         "layers": tuple[str, ...]}   # rectangular, all in mm

    or ``{"name": str, "polygon": [(x, y), ...], "holes": [[...], ...],
    "layers": (...)}`` for an exact non-rectangular outline.  Exact polygons
    keep a routed pour's access notches open; preserving their interior rings
    is equally important because those rings are often the only route to a
    foreign pad deliberately excluded from the pour.

    The keepout is a rule-area ZONE that Freerouting will see in the exported
    DSN and avoid.  Tracks, vias, and fills are blocked by default; individual
    hints may set ``allow_tracks``, ``allow_vias``, or ``block_fills=False``.
    The outline is appended **in-place** into ``z.Outline()`` to avoid the SWIG
    alias pitfall (see cec_route.py zone() for the full explanation).

    If *copy_pro* is True, the sibling ``.kicad_pro`` and ``.kicad_dru`` (if they
    exist) are copied next to *out_path* so DRC/netclass context travels with it.

    Returns *out_path*.  Works correctly even when *keepouts* is empty (pure copy).
    """
    # Copy the board file itself
    shutil.copy2(board_path, out_path)

    # Sidecars BEFORE the first LoadBoard (owner width defect 2026-07-15, measured):
    # pcbnew's settings manager binds a project to the board path at FIRST load; if
    # the .kicad_pro is not there yet it binds an EMPTY dummy, and a later
    # LoadProject on that path returns the cached dummy (rc True, classes lost) --
    # the DSN then exports class-less and FR routes every net at the 0.2 default.
    if copy_pro:
        copy_project_sidecars(board_path, out_path)

    if keepouts or copy_pro:
        board = pcbnew.LoadBoard(out_path)

        for ko in keepouts:
            polygon = ko.get("polygon")
            if polygon is None:
                x0, y0 = float(ko["x0"]), float(ko["y0"])
                x1, y1 = float(ko["x1"]), float(ko["y1"])
                polygon = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
            polygon = [(float(px), float(py)) for px, py in polygon]
            if len(polygon) < 3:
                raise ValueError("cec_fr.bake_hints: keepout %r polygon has < 3 points"
                                 % ko.get("name", "keepout"))
            holes = []
            for hole in ko.get("holes") or ():
                points = [(float(px), float(py)) for px, py in hole]
                if len(points) < 3:
                    raise ValueError(
                        "cec_fr.bake_hints: keepout %r hole has < 3 points"
                        % ko.get("name", "keepout"))
                holes.append(points)
            layers = ko.get("layers", ("F.Cu", "B.Cu"))
            name = ko.get("name", "keepout")

            z = pcbnew.ZONE(board)
            z.SetIsRuleArea(True)
            z.SetDoNotAllowTracks(not bool(ko.get("allow_tracks", False)))
            # allow_vias=True keeps FOREIGN F.Cu tracks out of the corridor while letting a boxed-in pad
            # (e.g. an INA238's GND/+3V3 pin sitting in the Kelvin corridor) via DOWN to an inner plane --
            # without it, a tracks+vias keepout strands the sensor's own power. A foreign net can't place a
            # useful via here anyway (no F.Cu track may reach it), and cec_hc's gate still treats any via as
            # a tap obstacle, so tap cleanliness is preserved.
            z.SetDoNotAllowVias(not bool(ko.get("allow_vias", False)))
            # block_fills=False (corridor keepouts) keeps FOREIGN tracks out during FR routing but lets
            # the post-route additive SAME-NET power pour FILL the reserved corridor SOLID -- without it
            # the keepout's DoNotAllowZoneFills blocks ~89% of the pour it was meant to protect (measured),
            # leaving the thin 0.2mm trace carrying the 40A. Default True preserves the old behaviour.
            block_fills = bool(ko.get("block_fills", True))
            # KiCad 9/10 renamed SetDoNotAllowCopperPour -> SetDoNotAllowZoneFills
            if hasattr(z, "SetDoNotAllowZoneFills"):
                z.SetDoNotAllowZoneFills(block_fills)
            else:
                z.SetDoNotAllowCopperPour(block_fills)

            ls = pcbnew.LSET()
            for lname in layers:
                lid = board.GetLayerID(lname)
                if lid < 0:
                    raise KeyError(
                        f"cec_fr.bake_hints: layer {lname!r} not found in {board_path!r}"
                    )
                ls.AddLayer(lid)
            z.SetLayerSet(ls)
            z.SetZoneName(name)

            # In-place outline append (never SetOutline — SWIG alias bug, see cec_route.py)
            o = z.Outline()
            oi = o.NewOutline()
            for (px, py) in polygon:
                o.Append(_nm(px), _nm(py))
            for hole in holes:
                hi = o.NewHole(oi)
                for (px, py) in hole:
                    o.Append(_nm(px), _nm(py), oi, hi)
            if z.Outline().FullPointCount() < 3:
                raise RuntimeError(
                    f"cec_fr.bake_hints: keepout {name!r} outline has < 3 points"
                )
            board.Add(z)

        pcbnew.SaveBoard(out_path, board)

    return out_path


# ---------------------------------------------------------------------------
# Candidate dataclass
# ---------------------------------------------------------------------------
@dataclass
class Candidate:
    board: str            # path to the imported routed .kicad_pcb (or "" if failed)
    ses: str              # path to the .ses
    seed: object          # the seed / param-variant id
    params: dict          # the FR params used (passes / opt_time / threads)
    ok: bool              # True if a routed board was produced
    err: str | None = None
    # STAGE ERRORS CARRY TRACEBACKS (2026-07-25, hub blindness): route_once used to
    # report only str(exc), so every hub variant read as the opaque one-liner
    # "route failed: 'SwigPyObject' object has no attribute 'GetLayerID'" with no
    # file:line -- the same class the pour stage fixed in 1d9bd5c3. err now carries
    # the failing frame inline (survives the wave's grep) and trace the full text.
    trace: str | None = None


# ---------------------------------------------------------------------------
# route_once
# ---------------------------------------------------------------------------
def prune_dangling_tracks(board_or_path, out_path=None, *, tol_mm=0.02, max_iters=8):
    """DANGLING-RUN safety net (owner scorecard finding, 2026-07-08 blind review: a
    'weird floating CAN_TX run' -- FR litter that connects to nothing at one or both
    ends). Iteratively removes UNLOCKED track segments with a dangling end. An end is
    CONNECTED if it lands on: same-net pad copper (HitTest), a same-net via barrel, a
    same-net track BODY on the same layer (point-to-segment, not just endpoints), or a
    FILLED same-net zone (a pour entry is not dangling -- zone-aware, else legitimate
    pour taps would be pruned). LOCKED tracks are never removed (deliberate stubs /
    kelvin machinery) -- half-connected locked stubs are REPORTED instead. Iterates
    because removing a segment can expose its neighbor."""
    import math as _m
    import pcbnew
    b = board_or_path if not isinstance(board_or_path, str) else pcbnew.LoadBoard(board_or_path)
    tol = int(tol_mm * 1e6)

    def _on_seg(px, py, t2):
        x0, y0 = t2.GetStart().x, t2.GetStart().y
        x1, y1 = t2.GetEnd().x, t2.GetEnd().y
        vx, vy = x1 - x0, y1 - y0
        L2 = vx * vx + vy * vy
        tt = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - x0) * vx + (py - y0) * vy) / L2))
        return _m.hypot(px - (x0 + tt * vx), py - (y0 + tt * vy)) <= t2.GetWidth() // 2 + tol

    zones = [(z.GetNetname(), lid, z.GetFilledPolysList(lid))
             for z in b.Zones() if z.IsOnCopperLayer()
             for lid in z.GetLayerSet().CuStack()]

    def _connected(pt, net, lyr, me):
        for fp in b.GetFootprints():
            for p in fp.Pads():
                if p.GetNetname() == net and p.IsOnLayer(lyr) and p.HitTest(pt):
                    return True
        for t2 in b.GetTracks():
            if t2 is me or t2.GetNetname() != net:
                continue
            if t2.GetClass() == "PCB_VIA":
                r = t2.GetWidth(t2.TopLayer()) // 2   # KiCad-10: via GetWidth NEEDS a layer
                if _m.hypot(t2.GetPosition().x - pt.x, t2.GetPosition().y - pt.y) <= r + tol:
                    return True
            elif t2.IsOnLayer(lyr) and _on_seg(pt.x, pt.y, t2):
                return True
        for znet, zlid, poly in zones:
            if znet == net and zlid == lyr and poly and poly.OutlineCount() > 0 \
                    and poly.Collide(pt, tol):
                return True
        return False

    removed, kept_locked = [], []
    for _ in range(max_iters):
        doomed = []
        for t in list(b.GetTracks()):
            if t.GetClass() == "PCB_VIA":
                continue
            net, lyr = t.GetNetname(), t.GetLayer()
            dang = [e for e in (t.GetStart(), t.GetEnd())
                    if not _connected(e, net, lyr, t)]
            if not dang:
                continue
            if t.IsLocked():
                key = (net, b.GetLayerName(lyr), len(dang))
                if key not in kept_locked:
                    kept_locked.append(key)
                continue
            doomed.append(t)
        if not doomed:
            break
        for t in doomed:
            removed.append((t.GetNetname(), b.GetLayerName(t.GetLayer()),
                            round(_m.hypot(t.GetEnd().x - t.GetStart().x,
                                           t.GetEnd().y - t.GetStart().y) / 1e6, 2)))
            b.Remove(t)
    if out_path and removed:
        b.Save(out_path)
    elif isinstance(board_or_path, str) and removed and out_path is None:
        b.Save(board_or_path)
    return {"removed": len(removed), "detail": removed[:15],
            "locked_dangling_kept": kept_locked[:10]}


def route_once(
    board_path: str,
    out_path: str,
    *,
    hints=(),
    power_pours=(),
    passes: int = 10,
    opt_time: int = 30,
    threads: int = 1,
    seed=None,
    workdir: str | None = None,
    jar: str | None = None,
    timeout: int = 600,
    version: str | None = None,   # FR release to run (default: the FR_VERSION pin)
    protect_nets=(),              # nets whose LOCKED stubs get fix->protect in the DSN
                                  # (FR 1.7.0 DROPS unprotected fix wires -- measured,
                                  # cec_fr02 bench; the coord-hints A/B rides this)
    skip_locked_taps: bool = False,  # precision pre-FR taps already laid+locked -> import_ses must
                                     # NOT re-synthesize (double-lay). Plumbed to import_ses.
    completed_nets=(),            # nets fully owned by an admitted upstream topology stage;
                                  # remove their pins from residual routing and finishing
) -> Candidate:
    """Full single-candidate pipeline: (bake_hints) -> export_dsn -> run_freerouting -> import_ses.

    Uses a fresh /tmp workdir for DSN/SES intermediates (Freerouting's logs/ stays
    in /tmp).  Owned workdirs are removed by default; set
    ``CEC_FR_KEEP_INTERMEDIATES=1`` for an explicitly debug-retained DSN/SES.
    Never raises for a routing failure — catches and returns
    ``Candidate(ok=False, err=...)``.  Does raise for programmer errors such as a
    missing input board.

    Returns a :class:`Candidate`.
    """
    if not os.path.isfile(board_path):
        raise FileNotFoundError(
            f"cec_fr.route_once: input board not found: {board_path!r}"
        )

    v = version or FR_VERSION
    _completed = {str(net) for net in (completed_nets or ()) if net}
    _protected = set(protect_nets or ()) | _completed
    params = {"passes": passes, "opt_time": opt_time, "threads": threads,
              "fr_version": v, "stage_s": {},
              "completed_nets": sorted(_completed)}
    _route_started = _stage_started = time.monotonic()

    def _stage_done(name):
        """Record and stream one monotonic route stage duration."""
        nonlocal _stage_started
        now = time.monotonic()
        elapsed = round(now - _stage_started, 3)
        params["stage_s"][name] = elapsed
        _stage_started = now
        print("[cec_fr] CEC_STAGE stage=%s seconds=%.3f" % (name, elapsed),
              file=sys.stderr, flush=True)
    _own_wd = workdir is None
    if _own_wd:
        workdir = tempfile.mkdtemp(prefix="cec_fr_once_", dir=_TMP)

    try:
        jar = ensure_jar(jar, version=v)
        _stage_done("ensure_jar")

        # 1. Bake hints (keepouts) into a working copy. When locked-protected nets
        # are in play, the FULLY-OWNED nets' locked copper ALSO bakes as rule-area
        # keepouts (owner defect report 2026-07-14: FR routed straight through the
        # blueprint cells -- an excluded net's protect wires drop out of FR's
        # obstacle model, see locked_copper_keepouts). Computed on board_path
        # (bake only adds zones; ownership reads tracks+pads, identical either way)
        # so the SAME set drives the keepouts and the pin exclusion below.
        _owned = set()
        if _protected:
            try:
                _owned = owned_locked_nets(board_path) | _completed
                if _owned:
                    _lk = locked_copper_keepouts(board_path, only_nets=_owned)
                    hints = list(hints) + _lk
                    print("[cec_fr] locked-copper keepouts: %d zone(s) over %d owned "
                          "net(s)" % (len(_lk), len(_owned)), flush=True)
            except Exception as _e:                            # noqa: BLE001
                print("[cec_fr] locked-copper keepouts failed (%s) -- protect-only"
                      % _e, flush=True)
            # PARTIALLY-owned locked nets (2026-07-14 residue (b)): their lane copper
            # bakes as keepouts too, with pad-access WINDOWS so FR can still finish
            # the net's remainder (/SENSEP6_HI divider tap, /FAN_12V fan-gate spur).
            try:
                _pk = partial_locked_keepouts(board_path, exclude_nets=_owned)
                if _pk:
                    hints = list(hints) + _pk
                    print("[cec_fr] partial-locked keepouts: %d zone(s) (windowed "
                          "pad access)" % len(_pk), flush=True)
            except Exception as _e:                            # noqa: BLE001
                print("[cec_fr] partial-locked keepouts failed (%s) -- owned-only"
                      % _e, flush=True)
            # Residue (a) audit: lanes/cells never mutual-legality-check; report
            # locked-vs-locked collisions LOUD (43 measured on the wave-9 winner)
            # so a jank bake is visible at route time, not at the zoom review.
            try:
                _mc = locked_mutual_collisions(board_path)
                if _mc:
                    print("[cec_fr] WARNING: %d locked-vs-locked collision(s) "
                          "(first: %s x %s on %s at %.1f,%.1f) -- the locked lay "
                          "overlaps ITSELF; fix the lanes/cells, keepouts cannot"
                          % (len(_mc), _mc[0]["a"], _mc[0]["b"], _mc[0]["layer"],
                             _mc[0]["x_mm"], _mc[0]["y_mm"]), flush=True)
            except Exception:                                  # noqa: BLE001
                pass
        # PRE-FR POUR-CORRIDOR RESERVATION (owner priority ruling 2026-07-24,
        # docs/slab-pour-design-2026-07-24.md: "the pour takes priority and
        # gets its route first"; wired 2026-07-25 -- the reachability half of
        # the RS1 starvation cycle). CEC_POUR_RESERVE=1 gates it, DEFAULT OFF
        # (golden safety). Each pour ask's over-under corridor is computed on
        # the PRE-ROUTE board (cec_slab_pour.reserve_pour_corridors -- the
        # SAME machinery as the import-time realization, but foreign = the
        # board's existing copper only: locked rails, pads, pre-laid taps --
        # no FR tracks yet) and baked below as keepout rule areas on its own
        # layers, so FR routes signals AROUND it and the post-route
        # realization finds the corridor still clear by construction. The
        # ask set mirrors import_ses' conversion filter (placer_ask dicts;
        # everything under CEC_SLAB_POUR=1). Pads the reserved pour OWNS are
        # excluded from FR after DSN export below (_dsn_exclude_pins
        # pattern); a no-path net excludes nothing and stays fully
        # FR-routed. The per-net report rides a pour_reserve.json sidecar
        # next to the DSN/SES so import_ses can log reserved-vs-realized.
        _reserve_pins = []
        _pf_route = _pourfirst_state()
        if _pf_route:
            # v3 POUR-FIRST: the reservation is FROZEN state -- corridors +
            # pour-owned pads come from the ONE solve the pipeline ran on the
            # anchor-only board (docs/slab-pour-design-2026-07-24.md v3: one
            # solve, three consumers). Never re-solved here: the live
            # CEC_POUR_RESERVE search below is the un-frozen path's tool.
            try:
                import json as _json
                import cec_slab_pour
                _cors = list(_pf_route.get("corridors") or ())
                if _cors:
                    hints = list(hints) + cec_slab_pour.corridors_to_keepouts(_cors)
                _reserve_pins = sorted(set(_pf_route.get("exclude_pins") or ()))
                _rrep = dict(_pf_route.get("reserve_report") or {})
                print("[cec_fr] pour-first reservation (frozen): %d corridor "
                      "rect(s) for %d net(s); %d pad(s) queued for FR "
                      "exclusion" % (len(_cors),
                                     sum(1 for v in _rrep.values()
                                         if v.get("reserved")),
                                     len(_reserve_pins)), file=sys.stderr)
                with open(os.path.join(workdir, "pour_reserve.json"), "w") as _wf:
                    _json.dump({"schema": 1, "pourfirst": True,
                                "report": _rrep}, _wf, indent=1,
                               sort_keys=True, default=str)
            except Exception as _e:                            # noqa: BLE001
                _reserve_pins = []
                print(f"[cec_fr] pour-first reservation FAILED ({_e}) -- "
                      "routing unreserved", file=sys.stderr)
        elif power_pours and os.environ.get("CEC_POUR_RESERVE", "0") == "1":
            try:
                import json as _json
                import cec_slab_pour
                _full_conv = os.environ.get("CEC_SLAB_POUR", "0") == "1"
                _rasks = [p for p in power_pours
                          if _full_conv or p.get("provenance") == "placer_ask"]
                if _rasks:
                    _res = cec_slab_pour.reserve_pour_corridors(
                        pcbnew.LoadBoard(board_path), _rasks)
                    _cors = _res.get("corridors") or []
                    if _cors:
                        hints = list(hints) + cec_slab_pour.corridors_to_keepouts(_cors)
                    _reserve_pins = sorted({t for v in _res.get("report", {}).values()
                                            for t in v.get("exclude_pins", ())})
                    _nres = sorted(n for n, v in _res.get("report", {}).items()
                                   if v.get("reserved"))
                    print("[cec_fr] pour-corridor reservation: %d corridor rect(s) "
                          "for %d/%d net(s) %s; %d pad(s) queued for FR exclusion"
                          % (len(_cors), len(_nres), len(_res.get("report", {})),
                             _nres, len(_reserve_pins)), file=sys.stderr)
                    with open(os.path.join(workdir, "pour_reserve.json"), "w") as _wf:
                        _json.dump({"schema": 1, "report": _res.get("report", {})},
                                   _wf, indent=1, sort_keys=True, default=str)
            except Exception as _e:                            # noqa: BLE001
                _reserve_pins = []
                print(f"[cec_fr] pour-corridor reservation FAILED ({_e}) -- "
                      "routing unreserved", file=sys.stderr)
        # BOARD EDGE: the Specctra outline bounds the routing domain but does
        # not carry KiCad's copper-to-edge clearance.  Direct route_once()
        # callers previously depended on their wrapper remembering this
        # physical rule, unlike the other manufacturing guards compiled at
        # this boundary.  Add the same width-aware/cutout-aware rule areas
        # here and deduplicate wrapper-provided copies by stable name.
        try:
            _existing_hint_names = {
                str(hint.get("name", "")) for hint in hints
                if isinstance(hint, dict)
            }
            _eg = [hint for hint in edge_keepout(board_path)
                   if str(hint.get("name", "")) not in _existing_hint_names]
            if _eg:
                hints = list(hints) + _eg
                print("[cec_fr] board-edge guards: %d rule area(s)" % len(_eg),
                      file=sys.stderr)
        except Exception as _e:                            # noqa: BLE001
            raise RuntimeError("board-edge guards unavailable: %s" % _e) from _e

        # ASSEMBLY FIDUCIALS: make the Specctra translation preserve KiCad's
        # local no-net-pad clearance even for direct route_once() callers or a
        # future custom planner.  Planner/factory hints are retained because
        # they make the intended constraint visible at the control plane; this
        # boundary de-duplicates them and is the fail-closed backstop.
        try:
            _existing_hint_names = {
                str(hint.get("name", "")) for hint in hints
                if isinstance(hint, dict)
            }
            _fg = [hint for hint in fiducial_keepouts(board_path)
                   if str(hint.get("name", "")) not in _existing_hint_names]
            if _fg:
                hints = list(hints) + _fg
                print("[cec_fr] assembly fiducial guards: %d layer-specific "
                      "rule area(s)" % len(_fg), file=sys.stderr)
        except Exception as _e:                            # noqa: BLE001
            raise RuntimeError("assembly fiducial guards unavailable: %s" % _e) from _e

        # VIA-IN-PAD PREVENTION (2026-08-04): Freerouting treats an SMD pin as a
        # convenient layer-transition site and can put a via land partly inside
        # a narrow pad.  KiCad DRC does not report that manufacturing defect; the
        # post-route via-on-pad gate correctly rejects it, but repeated waves had
        # no way to learn.  Bake exact, netclass-sized VIA-ONLY guards around all
        # SMD lands.  Trace access and fills remain legal, and a fully-contained
        # POFV core stays open on a declared profile.
        try:
            _vg = smd_via_keepouts(board_path)
            if _vg:
                hints = list(hints) + _vg
                print("[cec_fr] SMD via guards: %d merged rule area(s) over %d "
                      "surface pad(s)" % (len(_vg), _vg[0].get("source_pads", 0)),
                      file=sys.stderr)
        except Exception as _e:                            # noqa: BLE001
            # Manufacturing protection is a hard input contract.  The caller's
            # Candidate wrapper records this stage failure, so a missing Shapely
            # dependency or malformed pad can never degrade to an unguarded route.
            raise RuntimeError("SMD via guards unavailable: %s" % _e) from _e
        try:
            _dg = decorative_copper_keepouts(board_path)
            if _dg:
                hints = list(hints) + _dg
                print("[cec_fr] decorative copper guards: %d layer-specific "
                      "rule area(s)" % len(_dg), file=sys.stderr)
        except Exception as _e:                            # noqa: BLE001
            raise RuntimeError("decorative copper guards unavailable: %s" % _e) from _e
        _stage_done("prepare_constraints")
        hinted_board = os.path.join(workdir, "hinted.kicad_pcb")
        bake_hints(board_path, hinted_board, keepouts=hints, copy_pro=True)
        _stage_done("bake_hints")

        # 2. Export DSN
        dsn_path = os.path.join(workdir, "board.dsn")
        export_dsn(hinted_board, dsn_path)
        if _protected:
            import cec_fr02
            cec_fr02.force_protect_in_dsn(dsn_path, sorted(_protected))
            # OWNED-NET EXCLUSION (owner 2026-07-12: FR was re-routing the locked
            # lanes/taps at DSN class width -- 2.5mm B.Cu crossings under the bands;
            # reconcile stripped them AFTER, this stops the work happening at all):
            # a net the locked lay fully owns is removed from FR's routable pin
            # lists; its copper is obstacle-modelled by the keepouts baked above.
            try:
                if _owned:
                    n_x = cec_fr02.exclude_net_pins_in_dsn(dsn_path, sorted(_owned))
                    print("[cec_fr] owned-net exclusion: %d net(s) removed from FR routing"
                          % n_x, flush=True)
            except Exception as _e:                            # noqa: BLE001
                print("[cec_fr] owned-net exclusion failed (%s) -- reconcile backstops"
                      % _e, flush=True)
        # PRE-FR RESERVATION pad exclusion (CEC_POUR_RESERVE, computed above):
        # the reserved pour owns these pads' connectivity -- without this, FR
        # still tries to CONNECT them by some other path AROUND the corridor
        # keepouts (wasteful detours through the signal fabric). The pads
        # keep their real net on the board; only the DSN forgets them.
        if _reserve_pins:
            _nrx = _dsn_exclude_pins(dsn_path, _reserve_pins)
            print("[cec_fr] pour-reserve: excluded %d pour-owned pad(s) from "
                  "FR routing (%d DSN token(s) removed)"
                  % (len(_reserve_pins), _nrx), file=sys.stderr)
        _stage_done("export_dsn")

        # 3. Run Freerouting (from its own sub-workdir inside workdir so logs/ is isolated)
        fr_wd = tempfile.mkdtemp(prefix="cec_fr_fr_", dir=_TMP)
        ses_path = os.path.join(workdir, "board.ses")
        try:
            run_freerouting(
                dsn_path, ses_path,
                passes=passes, opt_time=opt_time, threads=threads,
                seed=seed, jar=jar,
                workdir=fr_wd, timeout=timeout, version=v,
            )
        finally:
            shutil.rmtree(fr_wd, ignore_errors=True)
        _stage_done("freerouting")

        # 4. Import SES into the ORIGINAL board (not the hinted copy, so keepout
        #    zones from bake_hints don't clutter the final result). Pour the high-current
        #    nets AFTER the route (additive same-net copper) + fix FR's thin-annular vias.
        import_ses(board_path, ses_path, out_path, power_pours=power_pours,
                   skip_locked_taps=skip_locked_taps,
                   completed_nets=_completed)
        params["import_report"] = _IMPORT_REPORTS.pop(
            os.path.abspath(out_path), {})
        _stage_done("import_ses")
        params["stage_s"]["total"] = round(
            time.monotonic() - _route_started, 3)

        return Candidate(
            board=out_path,
            ses=ses_path,
            seed=seed,
            params=params,
            ok=True,
        )

    except Exception as exc:
        params["stage_s"]["total"] = round(
            time.monotonic() - _route_started, 3)
        import traceback as _tb
        _trace = _tb.format_exc()
        # Innermost OUR-code frame (skip library frames) -> compact file:line the
        # wave log keeps on the ERR line.
        _where = ""
        try:
            for _fr in reversed(_tb.extract_tb(sys.exc_info()[2])):
                if os.sep + "scripts" + os.sep in _fr.filename or _fr.filename.endswith(".py"):
                    _where = " at %s:%d in %s" % (os.path.basename(_fr.filename),
                                                  _fr.lineno, _fr.name)
                    break
        except Exception:                                   # noqa: BLE001
            pass
        print("[cec_fr] route_once FAILED: %s%s\n%s" % (exc, _where, _trace),
              file=sys.stderr)
        return Candidate(
            board="",
            ses=os.path.join(workdir, "board.ses") if workdir else "",
            seed=seed,
            params=params,
            ok=False,
            err="%s%s" % (exc, _where),
            trace=_trace,
        )
    finally:
        if _own_wd:
            # A wave can launch hundreds of workers.  Retaining every successful
            # DSN/SES in /tmp silently consumes the host disk even though the
            # imported PCB is already durable in out_path.  Debug retention is
            # therefore explicit rather than the production default.
            if os.environ.get("CEC_FR_KEEP_INTERMEDIATES", "0") != "1":
                shutil.rmtree(workdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# _worker: top-level function for ProcessPoolExecutor
# ---------------------------------------------------------------------------
# Parallelism design: workers are plain top-level functions that accept only
# strings + dicts (picklable). Each worker re-imports pcbnew locally (via the
# module-level import already done when the worker process forks) and calls
# LoadBoard fresh.  No pcbnew objects cross the process boundary.
def _worker(args: dict) -> Candidate:
    """Worker for generate_batch — called in a subprocess."""
    # All arguments arrive as plain picklable types.
    return route_once(
        args["board_path"],
        args["out_path"],
        hints=args.get("hints", ()),
        power_pours=args.get("power_pours", ()),
        passes=args["passes"],
        opt_time=args["opt_time"],
        threads=args["threads"],
        seed=args["seed"],
        workdir=None,   # each worker gets its own /tmp workdir
        jar=args.get("jar"),
        timeout=args.get("timeout", 600),
        version=args.get("version"),   # None -> the worker's own FR_VERSION pin (env-aware)
        protect_nets=args.get("protect_nets", ()),
        skip_locked_taps=bool(args.get("skip_locked_taps", False)),
        completed_nets=args.get("completed_nets", ()),
    )


# ---------------------------------------------------------------------------
# generate_batch
# ---------------------------------------------------------------------------
_DEFAULT_SEED_SPREAD = {
    0: {"passes": 6,  "opt_time": 10, "threads": 1},
    1: {"passes": 10, "opt_time": 20, "threads": 1},
    2: {"passes": 16, "opt_time": 40, "threads": 2},
}


def generate_batch(
    board_path: str,
    hints=(),
    seeds=(0,),
    *,
    power_pours=(),
    out_dir: str | None = None,
    params=None,
    max_workers: int | None = None,
    jar: str | None = None,
    protect_nets=(),
    skip_locked_taps: bool = False,
    completed_nets=(),
) -> list[Candidate]:
    """Generate one :class:`Candidate` per seed in *seeds*, in parallel.

    Uses :class:`~concurrent.futures.ProcessPoolExecutor`.  Each worker is the
    top-level ``_worker`` function which accepts only plain strings/dicts — no
    pcbnew objects cross the process boundary; each worker calls LoadBoard itself.

    *params* may be:
      - ``None``: uses a built-in spread (passes in {6, 10, 16}, opt_time in {10, 20, 40})
      - a ``dict``: the same FR params for every seed
      - a ``callable(seed) -> dict``: per-seed params

    Calls :func:`ensure_jar` once up front and passes the resolved path to workers.

    Returns the list of :class:`Candidate` objects (both ok and failed), in seed order.
    """
    if not os.path.isfile(board_path):
        raise FileNotFoundError(
            f"cec_fr.generate_batch: input board not found: {board_path!r}"
        )

    jar = ensure_jar(jar)

    if out_dir is None:
        out_dir = tempfile.mkdtemp(prefix="cec_fr_batch_", dir=_TMP)
    else:
        os.makedirs(out_dir, exist_ok=True)

    def _resolve_params(s):
        if params is None:
            idx = list(seeds).index(s) if s in seeds else 0
            return _DEFAULT_SEED_SPREAD.get(idx, {"passes": 10, "opt_time": 20, "threads": 1})
        if callable(params):
            return params(s)
        return dict(params)

    # Build the argument list for the workers
    work_items = []
    for s in seeds:
        p = _resolve_params(s)
        out_path = os.path.join(out_dir, f"candidate_seed{s}.kicad_pcb")
        work_items.append({
            "board_path": board_path,
            "out_path": out_path,
            "hints": list(hints),   # must be picklable
            "power_pours": list(power_pours),   # must be picklable
            "passes": p.get("passes", 10),
            "opt_time": p.get("opt_time", 20),
            "threads": p.get("threads", 1),
            "seed": s,
            "jar": jar,
            "timeout": p.get("timeout", 600),
            "protect_nets": list(protect_nets),
            "skip_locked_taps": bool(skip_locked_taps),
            "completed_nets": list(completed_nets),
        })

    results_by_seed = {}
    n = max_workers if max_workers is not None else min(len(seeds), os.cpu_count() or 1)

    import time as _time
    print(f"[cec_fr] generate_batch: {len(seeds)} seeds -> {n} parallel workers "
          f"(cpu_count={os.cpu_count()}, max_workers={max_workers})", flush=True)
    if n > (os.cpu_count() or 1):
        print(f"[cec_fr] WARNING: {n} workers > {os.cpu_count()} CPU threads -- OVERSUBSCRIBED. "
              f"Each Freerouting JVM is ~0.5GB; this can exhaust RAM and lock the machine "
              f"(2x oversubscription locked an i7-13700K). Prefer max_workers<=CPU threads (0=auto).",
              flush=True)
    _t0 = _time.monotonic()

    # IMPORTANT: use the "spawn" start method, NOT the default "fork". pcbnew/wxWidgets is
    # NOT fork-safe -- if the parent has already loaded/exercised pcbnew (LoadBoard,
    # ExportSpecctraDSN, etc., as the orchestrator cec_router does before this call), a
    # forked worker inherits wx's locked global state and DEADLOCKS on the first heavy
    # pcbnew call (observed: child hangs in __futex_wait at ExportSpecctraDSN, no java ever
    # launches). "spawn" starts a fresh interpreter that re-imports pcbnew clean, so each
    # worker is fully isolated. Workers take only picklable strings/dicts; _worker is a
    # top-level function -> spawn-picklable.
    import multiprocessing as _mp
    import cec_process_pool as _pool_guard
    _ctx = _mp.get_context("spawn")
    pool = ProcessPoolExecutor(max_workers=n, mp_context=_ctx)
    forced_shutdown = False
    future_to_seed = {}
    try:
        future_to_seed = {pool.submit(_worker, item): item["seed"] for item in work_items}
        # route_once owns the per-JVM timeout.  This outer generation watchdog
        # covers queued waves plus bounded pcbnew import/export and prevents a
        # dead executor coordinator from surviving after its Java child exits.
        max_task_timeout = max(
            (float(item.get("timeout", 600)) for item in work_items),
            default=600.0)
        wall_budget = _pool_guard.pool_wall_budget(
            max_task_timeout, len(work_items), n,
            cleanup_s=300.0, multiplier=1.5, minimum_s=600.0)
        for fut in _pool_guard.watched_as_completed(
                pool, future_to_seed, wall_timeout_s=wall_budget,
                poll_s=5.0):
            s = future_to_seed[fut]
            try:
                cand = fut.result()
            except Exception as exc:
                # Wrap unexpected worker-level exceptions (e.g. pickling errors) into
                # a failed Candidate so the caller always gets a list of the right length.
                p = _resolve_params(s)
                cand = Candidate(
                    board="",
                    ses="",
                    seed=s,
                    params={"passes": p.get("passes", 10), "opt_time": p.get("opt_time", 20),
                            "threads": p.get("threads", 1)},
                    ok=False,
                    err=f"worker raised: {exc}",
                )
            results_by_seed[s] = cand
    except _pool_guard.WorkerPoolStalled as exc:
        forced_shutdown = True
        for fut, s in future_to_seed.items():
            if s in results_by_seed:
                continue
            p = _resolve_params(s)
            results_by_seed[s] = Candidate(
                board="", ses="", seed=s,
                params={"passes": p.get("passes", 10),
                        "opt_time": p.get("opt_time", 20),
                        "threads": p.get("threads", 1),
                        "executor_watchdog": str(exc)},
                ok=False,
                err="worker pool stalled: %s" % exc,
            )
    finally:
        shutdown = _pool_guard.shutdown_process_pool(
            pool, force=forced_shutdown, grace_s=5.0)
        print("[cec_fr] batch executor shutdown: %s" % shutdown, flush=True)

    # Return in original seed order
    out = [results_by_seed[s] for s in seeds]
    print(f"[cec_fr] batch done in {_time.monotonic()-_t0:.1f}s: "
          f"{sum(c.ok for c in out)}/{len(out)} candidates ok", flush=True)
    return out


# ---------------------------------------------------------------------------
# Self-test: run as  python3 scripts/cec_fr.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import time

    EPS_BOARD = os.path.join(ROOT, "beta", "eps-8pin-rev3", "eps-8pin-rev3.kicad_pcb")
    OUT_DIR = os.path.join(_TMP, "cec_fr_selftest")

    print("=" * 70)
    print(f"  cec_fr self-test  (Freerouting {FR_VERSION})")
    print("=" * 70)

    # Verify EPS board exists
    if not os.path.isfile(EPS_BOARD):
        print(f"ERROR: EPS board not found at {EPS_BOARD}", file=sys.stderr)
        sys.exit(1)

    # 1. Resolve jar
    print("\n[1] ensure_jar() ...", end=" ", flush=True)
    try:
        jar = ensure_jar()
        print(f"OK  -> {jar}")
    except RuntimeError as e:
        print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Batch with seeds 0 and 1, SHORT runs (passes=4 / opt_time=5 / threads=1)
    #    so the demo finishes in a couple of minutes.
    print("\n[2] generate_batch(EPS, seeds=(0,1), passes=4, opt_time=5) ...")
    print(f"    outputs -> {OUT_DIR}")
    t0 = time.monotonic()

    candidates = generate_batch(
        EPS_BOARD,
        seeds=(0, 1),
        params=lambda s: {"passes": 4, "opt_time": 5, "threads": 1},
        out_dir=OUT_DIR,
        jar=jar,
    )

    elapsed = time.monotonic() - t0
    print(f"    batch done in {elapsed:.1f}s\n")

    # 3. Report
    all_ok = True
    for cand in candidates:
        print(f"  seed={cand.seed}  ok={cand.ok}  params={cand.params}")
        if cand.ok:
            # Count tracks and vias from the saved board
            b = pcbnew.LoadBoard(cand.board)
            tracks = sum(1 for t in b.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T)
            vias   = sum(1 for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T)
            print(f"    board:  {cand.board}")
            print(f"    ses:    {cand.ses}")
            print(f"    copper: {tracks} tracks, {vias} vias")
            if tracks == 0 and vias == 0:
                print("    WARNING: zero copper — check SES import", file=sys.stderr)
                all_ok = False
        else:
            print(f"    FAILED: {cand.err}", file=sys.stderr)
            all_ok = False
        print()

    # 4. Sanity-check that nothing landed in the repo
    repo = "/home/user/CEC-Platform"
    git_status = subprocess.run(
        ["git", "-C", repo, "status", "--short"],
        capture_output=True, text=True
    ).stdout.strip()
    logs_in_repo = any("logs/" in line for line in git_status.splitlines())
    if logs_in_repo:
        print("FAIL: logs/ directory appeared in repo git status!", file=sys.stderr)
        all_ok = False

    print("=" * 70)
    print(f"  {'PASS' if all_ok else 'FAIL'}  (no repo artifacts: {'ok' if not logs_in_repo else 'FAIL'})")
    print("=" * 70)
    sys.exit(0 if all_ok else 1)
