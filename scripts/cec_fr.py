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
# to ensure logs/ never appears in the repo (a stop-hook checks for that), regardless of CWD.
#
# Verified round-trip (EPS board, 2026-06-06): ExportSpecctraDSN -> FR exit 0 ->
# ImportSpecctraSES -> 481 tracks / 64 vias on the EPS 8-pin module.
import os
import sys
import shutil
import tempfile
import subprocess
import urllib.request
from dataclasses import dataclass, field
from concurrent.futures import ProcessPoolExecutor, as_completed

# ---------------------------------------------------------------------------
# Suppress the benign pcbnew startup noise (assert "m_choices" / "No enum choices"
# lines) without swallowing real stderr from callers. We redirect pcbnew's own
# import stderr to /dev/null only around the import; the rest of the code keeps
# stderr live so real errors surface.
# ---------------------------------------------------------------------------
import contextlib as _cl

with _cl.redirect_stderr(open(os.devnull, "w")):
    import pcbnew

MM = 1_000_000               # nm per mm
def _nm(v): return int(round(v * MM))

# Cross-platform scratch dir: the OS temp dir (/tmp on Linux/mac, %TEMP% on Windows).
# Never hardcode /tmp -- it doesn't exist on Windows.
_TMP = tempfile.gettempdir()


def _fr_command(jar, dsn_path, ses_path, passes, opt_time, threads):
    """Build the Freerouting invocation for THIS platform.

    Freerouting is a Java/Swing app that touches AWT at startup, so it needs a display.
      * Linux, no $DISPLAY: wrap in `xvfb-run -a` (a virtual X server) -- if xvfb-run is
        missing on headless Linux, FR will throw HeadlessException (route-prereqs flags it).
      * Linux WITH $DISPLAY, macOS, Windows: run `java` directly -- the native windowing
        system (X / Quartz / Win32) provides the display. There is NO xvfb on Windows and
        none is needed; a Windows runner must just be in an interactive desktop session.
    """
    base = ["java", "-jar", jar,
            "-de", os.path.abspath(dsn_path),
            "-do", os.path.abspath(ses_path),
            "-mp", str(int(passes)),
            "-oit", str(int(opt_time)),
            "-mt", str(int(threads))]
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and shutil.which("xvfb-run"):
        return ["xvfb-run", "-a"] + base
    return base

# ---------------------------------------------------------------------------
# Freerouting jar metadata
# ---------------------------------------------------------------------------
FR_VERSION = "1.7.0"
FR_JAR_URL = (
    "https://github.com/freerouting/freerouting/releases/download"
    f"/v{FR_VERSION}/freerouting-{FR_VERSION}.jar"
)
_FR_JAR_CACHE = os.path.expanduser(
    f"~/.cache/cec/freerouting-{FR_VERSION}.jar"
)
# extra known-location candidates (checked, never required): the Linux convention path and
# a jar dropped in the OS temp dir. Both are just os.path.isfile()-probed, so harmless when absent.
_FR_JAR_TMP = f"/tmp/fr_{FR_VERSION}.jar"
_FR_JAR_TMP2 = os.path.join(_TMP, f"fr_{FR_VERSION}.jar")


# ---------------------------------------------------------------------------
# ensure_jar
# ---------------------------------------------------------------------------
def ensure_jar(path: str | None = None) -> str:
    """Return a path to the Freerouting jar.

    Resolution order:
      1) ``path`` arg if given and exists
      2) $CEC_FREEROUTING_JAR env var if set and the file exists
      3) /tmp/fr_1.7.0.jar if it exists
      4) ~/.cache/cec/freerouting-1.7.0.jar if it exists
      5) download FR_JAR_URL to ~/.cache/cec/freerouting-1.7.0.jar and return it

    Raises RuntimeError if all options fail.
    """
    candidates = []
    if path:
        candidates.append(path)
    env_jar = os.environ.get("CEC_FREEROUTING_JAR")
    if env_jar:
        candidates.append(env_jar)
    candidates.append(_FR_JAR_TMP)
    candidates.append(_FR_JAR_TMP2)
    candidates.append(_FR_JAR_CACHE)

    for c in candidates:
        if c and os.path.isfile(c):
            return c

    # Download to the cache location
    cache_dir = os.path.dirname(_FR_JAR_CACHE)
    os.makedirs(cache_dir, exist_ok=True)
    print(f"[cec_fr] Downloading Freerouting {FR_VERSION} jar from {FR_JAR_URL} ...",
          file=sys.stderr)
    try:
        urllib.request.urlretrieve(FR_JAR_URL, _FR_JAR_CACHE)
    except Exception as exc:
        raise RuntimeError(
            f"cec_fr: Could not download Freerouting jar from {FR_JAR_URL}: {exc}\n"
            f"  Place the jar manually at one of: {_FR_JAR_TMP}, {_FR_JAR_CACHE}"
        ) from exc
    if not os.path.isfile(_FR_JAR_CACHE):
        raise RuntimeError(
            f"cec_fr: Download appeared to succeed but {_FR_JAR_CACHE} is missing"
        )
    return _FR_JAR_CACHE


# ---------------------------------------------------------------------------
# export_dsn
# ---------------------------------------------------------------------------
def export_dsn(board_path: str, dsn_path: str) -> str:
    """Load *board_path* with pcbnew and call ExportSpecctraDSN(board, dsn_path).

    Returns *dsn_path*.  Raises RuntimeError if the export returns False or the
    output file is missing/empty.
    """
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
    return dsn_path


# ---------------------------------------------------------------------------
# run_freerouting
# ---------------------------------------------------------------------------
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
) -> str:
    """Run Freerouting 1.7.0 and produce a .ses file.

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
    jar = ensure_jar(jar)

    # Always route under /tmp to keep logs/ away from the repo.
    _own_workdir = workdir is None
    if _own_workdir:
        workdir = tempfile.mkdtemp(prefix="cec_fr_run_", dir=_TMP)

    if seed is not None:
        print(f"[cec_fr] note: seed={seed!r} logged (no -seed flag in FR {FR_VERSION})",
              file=sys.stderr)

    cmd = _fr_command(jar, dsn_path, ses_path, passes, opt_time, threads)

    run_kw = dict(cwd=workdir, capture_output=True, text=True, timeout=timeout)
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

    try:
        result = subprocess.run(cmd, **run_kw)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"cec_fr.run_freerouting: timed out after {timeout}s "
            f"(dsn={dsn_path!r}, jar={jar!r})"
        ) from exc
    finally:
        if _own_workdir:
            try:
                shutil.rmtree(workdir, ignore_errors=True)
            except Exception:
                pass

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
def add_power_pours(board, pours, *, fill: bool = False):
    """Lay additive same-net copper pours on an ALREADY-ROUTED board.

    Each entry in *pours* is a dict::

        {"net": "/SENSEC1_HI",                 # net to pour (must exist on the board)
         "polygon": [(x, y), ...],             # outline vertices in mm
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
    added = []
    for p in pours:
        net = p["net"]
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
        z.SetAssignedPriority(int(p.get("priority", 2)))
        z.SetMinThickness(_nm(p.get("min_thickness", 0.25)))
        z.SetIslandRemovalMode(int(p.get("island_removal", 0)))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        # In-place outline append (never SetOutline -- SWIG alias bug, see cec_route.py)
        o = z.Outline()
        o.NewOutline()
        for (x, y) in p["polygon"]:
            o.Append(_nm(x), _nm(y))
        if z.Outline().FullPointCount() < 3:
            raise RuntimeError(f"cec_fr.add_power_pours: pour on {net!r} has < 3 points")
        board.Add(z)
        added.append(z)
    if fill and added:
        for z in board.Zones():
            z.UnFill()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    return added


# ---------------------------------------------------------------------------
# derive_power_pours -- auto-find the high-current pour rectangles from geometry
# ---------------------------------------------------------------------------
def derive_power_pours(board_path: str, *, margin: float = 1.0, edge_clear: float = 0.4,
                       layer: str = "F.Cu", kelvin_pairs=None) -> list:
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
    """
    from collections import defaultdict
    board = pcbnew.LoadBoard(board_path)
    names = {n.GetNetname() for n in board.GetNetInfo().NetsByNetcode().values() if n.GetNetname()}
    if kelvin_pairs is None:
        kelvin_pairs = [(h, h[:-3] + "_LO") for h in sorted(names)
                        if h.endswith("_HI") and (h[:-3] + "_LO") in names]

    bb = board.GetBoardEdgesBoundingBox()
    bx0, by0 = bb.GetLeft() / MM + edge_clear, bb.GetTop() / MM + edge_clear
    bx1, by1 = bb.GetRight() / MM - edge_clear, bb.GetBottom() / MM - edge_clear

    pads_by_net = defaultdict(list)
    padcount = defaultdict(int)
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for p in fp.Pads():
            padcount[ref] += 1
            nn = p.GetNetname()
            if nn:
                pads_by_net[nn].append((ref, p))

    pours = []
    for hi, lo in kelvin_pairs:
        refs_hi = {ref for ref, _ in pads_by_net.get(hi, [])}
        refs_lo = {ref for ref, _ in pads_by_net.get(lo, [])}
        # The shunt is the footprint straddling the pair with EXACTLY 2 pads (a Kelvin
        # shunt). A differential INA also has a pad on each of HI/LO but is multi-pad, so
        # the 2-pad test excludes it -- otherwise its small sense pads would inflate the
        # bbox and make the HI box (cable->shunt) overlap the LO box (shunt->cable).
        shunt_refs = {ref for ref in (refs_hi & refs_lo) if padcount.get(ref, 0) == 2}
        for net in (hi, lo):
            entries = pads_by_net.get(net, [])
            has_tht = any(p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH for _, p in entries)
            if not has_tht:
                continue                          # not a cable high-current net -> skip
            heavy = []
            for ref, p in entries:
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH or ref in shunt_refs:
                    pos = p.GetPosition()
                    heavy.append((pos.x / MM, pos.y / MM))
            if not heavy:
                continue
            xs = [x for x, _ in heavy]
            ys = [y for _, y in heavy]
            x0 = max(bx0, min(xs) - margin); x1 = min(bx1, max(xs) + margin)
            y0 = max(by0, min(ys) - margin); y1 = min(by1, max(ys) + margin)
            pours.append({"net": net, "layer": layer,
                          "polygon": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]})
    return pours


# ---------------------------------------------------------------------------
# normalize_via_annular -- fix Freerouting's thin-annular vias
# ---------------------------------------------------------------------------
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
def import_ses(board_path: str, ses_path: str, out_path: str, *,
               fill_zones: bool = True, fix_annular: bool = True, power_pours=()) -> str:
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
    ok = pcbnew.ImportSpecctraSES(board, ses_path)
    if not ok:
        raise RuntimeError(
            f"cec_fr.import_ses: ImportSpecctraSES returned False\n"
            f"  board={board_path!r}\n  ses={ses_path!r}"
        )
    if power_pours:
        add_power_pours(board, power_pours, fill=False)
    if fix_annular:
        normalize_via_annular(board)
    if fill_zones:
        # UnFill first: re-filling an already-filled multi-layer zone in one process can
        # segfault this KiCad-10 SWIG build (see cec_route.py fill()).
        for z in board.Zones():
            z.UnFill()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(out_path, board)
    if not os.path.isfile(out_path):
        raise RuntimeError(
            f"cec_fr.import_ses: SaveBoard appeared to succeed but {out_path!r} is missing"
        )
    return out_path


# ---------------------------------------------------------------------------
# bake_hints
# ---------------------------------------------------------------------------
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
         "layers": tuple[str, ...]}   # all in mm

    The keepout is a rule-area ZONE (DoNotAllowTracks + DoNotAllowVias +
    DoNotAllowCopperPour) that Freerouting will see in the exported DSN and avoid.
    The outline is appended **in-place** into ``z.Outline()`` to avoid the SWIG
    alias pitfall (see cec_route.py zone() for the full explanation).

    If *copy_pro* is True, the sibling ``.kicad_pro`` and ``.kicad_dru`` (if they
    exist) are copied next to *out_path* so DRC/netclass context travels with it.

    Returns *out_path*.  Works correctly even when *keepouts* is empty (pure copy).
    """
    # Copy the board file itself
    shutil.copy2(board_path, out_path)

    if keepouts or copy_pro:
        board = pcbnew.LoadBoard(out_path)

        for ko in keepouts:
            x0, y0 = float(ko["x0"]), float(ko["y0"])
            x1, y1 = float(ko["x1"]), float(ko["y1"])
            layers = ko.get("layers", ("F.Cu", "B.Cu"))
            name = ko.get("name", "keepout")

            z = pcbnew.ZONE(board)
            z.SetIsRuleArea(True)
            z.SetDoNotAllowTracks(True)
            z.SetDoNotAllowVias(True)
            # KiCad 9/10 renamed SetDoNotAllowCopperPour -> SetDoNotAllowZoneFills
            if hasattr(z, "SetDoNotAllowZoneFills"):
                z.SetDoNotAllowZoneFills(True)
            else:
                z.SetDoNotAllowCopperPour(True)

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
            o.NewOutline()
            for (px, py) in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
                o.Append(_nm(px), _nm(py))
            if z.Outline().FullPointCount() < 3:
                raise RuntimeError(
                    f"cec_fr.bake_hints: keepout {name!r} outline has < 3 points"
                )
            board.Add(z)

        pcbnew.SaveBoard(out_path, board)

    if copy_pro:
        base = os.path.splitext(board_path)[0]
        out_base = os.path.splitext(out_path)[0]
        for ext in (".kicad_pro", ".kicad_dru"):
            src = base + ext
            if os.path.isfile(src):
                shutil.copy2(src, out_base + ext)

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


# ---------------------------------------------------------------------------
# route_once
# ---------------------------------------------------------------------------
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
) -> Candidate:
    """Full single-candidate pipeline: (bake_hints) -> export_dsn -> run_freerouting -> import_ses.

    Uses a fresh /tmp workdir for DSN/SES intermediates (Freerouting's logs/ stays
    in /tmp).  Never raises for a routing failure — catches and returns
    ``Candidate(ok=False, err=...)``.  Does raise for programmer errors such as a
    missing input board.

    Returns a :class:`Candidate`.
    """
    if not os.path.isfile(board_path):
        raise FileNotFoundError(
            f"cec_fr.route_once: input board not found: {board_path!r}"
        )

    params = {"passes": passes, "opt_time": opt_time, "threads": threads}
    _own_wd = workdir is None
    if _own_wd:
        workdir = tempfile.mkdtemp(prefix="cec_fr_once_", dir=_TMP)

    try:
        jar = ensure_jar(jar)

        # 1. Bake hints (keepouts) into a working copy
        hinted_board = os.path.join(workdir, "hinted.kicad_pcb")
        bake_hints(board_path, hinted_board, keepouts=hints, copy_pro=True)

        # 2. Export DSN
        dsn_path = os.path.join(workdir, "board.dsn")
        export_dsn(hinted_board, dsn_path)

        # 3. Run Freerouting (from its own sub-workdir inside workdir so logs/ is isolated)
        fr_wd = tempfile.mkdtemp(prefix="cec_fr_fr_", dir=_TMP)
        ses_path = os.path.join(workdir, "board.ses")
        try:
            run_freerouting(
                dsn_path, ses_path,
                passes=passes, opt_time=opt_time, threads=threads,
                seed=seed, jar=jar,
                workdir=fr_wd, timeout=timeout,
            )
        finally:
            shutil.rmtree(fr_wd, ignore_errors=True)

        # 4. Import SES into the ORIGINAL board (not the hinted copy, so keepout
        #    zones from bake_hints don't clutter the final result). Pour the high-current
        #    nets AFTER the route (additive same-net copper) + fix FR's thin-annular vias.
        import_ses(board_path, ses_path, out_path, power_pours=power_pours)

        return Candidate(
            board=out_path,
            ses=ses_path,
            seed=seed,
            params=params,
            ok=True,
        )

    except Exception as exc:
        return Candidate(
            board="",
            ses=os.path.join(workdir, "board.ses") if workdir else "",
            seed=seed,
            params=params,
            ok=False,
            err=str(exc),
        )
    finally:
        if _own_wd:
            # Keep intermediates: the caller may want to inspect dsn/ses.
            # Only clean up if the run succeeded (board is in out_path already).
            # Actually — always leave workdir if it holds a .ses, clean otherwise.
            ses_exists = os.path.isfile(os.path.join(workdir, "board.ses"))
            if not ses_exists:
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
    _ctx = _mp.get_context("spawn")
    with ProcessPoolExecutor(max_workers=n, mp_context=_ctx) as pool:
        future_to_seed = {pool.submit(_worker, item): item["seed"] for item in work_items}
        for fut in as_completed(future_to_seed):
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

    EPS_BOARD = "/home/user/CEC-Platform/modules/eps-8pin/eps8pin-module.kicad_pcb"
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
