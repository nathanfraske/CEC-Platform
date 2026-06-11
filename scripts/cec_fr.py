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
import sys
import math
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


def _fr_engine(jar, version=None):
    """The argv prefix that launches Freerouting *version*.

    1.7.0 (and any release whose min_java the PATH `java` satisfies) runs `java -jar`.
    2.2.4 is compiled for Java 25 (class-file 69); when the PATH java is older, fall back
    to the hash-pinned official jpackage APP-IMAGE launcher (bundled JRE 25, Linux only).
    """
    v = version or FR_VERSION
    rel = FR_RELEASES.get(v) or {}
    need = int(rel.get("min_java", 17))
    have = _java_major()
    if have >= need:
        return ["java", "-jar", jar]
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
      * Linux, no $DISPLAY: wrap in `xvfb-run -a` (a virtual X server) -- if xvfb-run is
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
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and shutil.which("xvfb-run"):
        return ["xvfb-run", "-a"] + base
    return base

# ---------------------------------------------------------------------------
# Freerouting release metadata (FR-01: version-parametric, hash-pinned)
# ---------------------------------------------------------------------------
# The active version resolves from $CEC_FR_VERSION at import (the ledger manifest reads
# cec_fr.FR_VERSION, so an env override is automatically an AM-03 epoch boundary in every
# decision log). The DEFAULT stays the banked-baseline pin until the FR-01 migration gate
# passes on the successor.
FR_VERSION = os.environ.get("CEC_FR_VERSION", "1.7.0")

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


def _java_major():
    """Major version of the `java` on PATH, or 0 when absent/unparsable."""
    try:
        r = subprocess.run(["java", "-version"], capture_output=True, text=True, timeout=30)
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
    text = open(dsn_path, "r", encoding="utf-8", errors="replace").read()
    done = []
    for name in layer_names:
        pat = re.compile(r"(\(layer\s+" + re.escape(name) + r"\s*\(\s*type\s+)signal(\s*\))")
        text, n = pat.subn(r"\1power\2", text)
        if n:
            done.append(name)
    if done:
        open(dsn_path, "w", encoding="utf-8").write(text)
    return done


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
    jar = ensure_jar(jar, version=v)

    # Always route under /tmp to keep logs/ away from the repo.
    _own_workdir = workdir is None
    if _own_workdir:
        workdir = tempfile.mkdtemp(prefix="cec_fr_run_", dir=_TMP)

    if seed is not None:
        print(f"[cec_fr] note: seed={seed!r} logged (no -seed flag in FR {v})",
              file=sys.stderr)

    cmd = _fr_command(jar, dsn_path, ses_path, passes, opt_time, threads,
                      version=v, workdir=workdir)

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
    """
    from collections import defaultdict
    board = board if board is not None else pcbnew.LoadBoard(board_path)
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
        kelvin_pairs = [(h, h[:-3] + "_LO") for h in sorted(names)
                        if h.endswith("_HI") and (h[:-3] + "_LO") in names]
    pads_by_net = defaultdict(list)
    padcount = defaultdict(int)
    all_pads = []                          # (x, y, half_extent_mm) -- every pad, for the keepout
    segs = []                              # (net, ax, ay, bx, by, halfwidth) -- every track
    ex_vias = []                           # (x, y, radius) -- existing vias
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition(); ex_vias.append((p.x / MM, p.y / MM, t.GetWidth() / MM / 2.0))
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
            all_pads.append((pos.x / MM, pos.y / MM, max(sz.x, sz.y) / MM / 2.0))
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
                    if any(math.hypot(x - px, y - py) < pr + keepout + vr for (px, py, pr) in all_pads):
                        continue           # too close to a pad
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
    f_cu, b_cu = board.GetLayerID("F.Cu"), board.GetLayerID("B.Cu")
    for f in fields:
        nc = board.GetNetcodeFromNetname(f["net"])
        if nc <= 0:
            raise KeyError(f"cec_fr.add_via_field: net {f['net']!r} not found on board")
        for (x, y) in f["positions"]:
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(_nm(x), _nm(y)))
            v.SetDrill(_nm(f.get("drill", 0.3)))
            v.SetWidth(_nm(f.get("dia", 0.6)))
            v.SetNetCode(nc)
            v.SetLayerPair(f_cu, b_cu)
            board.Add(v)
            added.append(v)
    return added


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
        kelvin_pairs = [(h, h[:-3] + "_LO") for h in sorted(names)
                        if h.endswith("_HI") and (h[:-3] + "_LO") in names]
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
    # LAYER POLICY, import half (complements the export-side (type power) rewrite):
    # plane layers carry ZONES, never tracks. FR may still drop POWER-classified net
    # segments onto a (type power) layer (Specctra semantics allow it; measured: two
    # 4.2mm /SENSEC*_HI segments on the EPS GND plane) -- strip ALL track segments on
    # detected plane layers before the fill (the pours/zones carry those nets).
    if os.environ.get("CEC_FR_PLANE_POLICY", "1") != "0":
        _plane_names = set(plane_layers(board))
        if _plane_names:
            _doomed = [t for t in board.GetTracks()
                       if t.GetClass() == "PCB_TRACK"
                       and board.GetLayerName(t.GetLayer()) in _plane_names]
            for t in _doomed:
                board.Remove(t)
            if _doomed:
                print(f"[cec_fr] layer policy: stripped {len(_doomed)} track segment(s) "
                      f"from plane layer(s) {sorted(_plane_names)}", file=sys.stderr)
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
            # allow_vias=True keeps FOREIGN F.Cu tracks out of the corridor while letting a boxed-in pad
            # (e.g. an INA238's GND/+3V3 pin sitting in the Kelvin corridor) via DOWN to an inner plane --
            # without it, a tracks+vias keepout strands the sensor's own power. A foreign net can't place a
            # useful via here anyway (no F.Cu track may reach it), and cec_hc's gate still treats any via as
            # a tap obstacle, so tap cleanliness is preserved.
            z.SetDoNotAllowVias(not bool(ko.get("allow_vias", False)))
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
    version: str | None = None,   # FR release to run (default: the FR_VERSION pin)
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

    v = version or FR_VERSION
    params = {"passes": passes, "opt_time": opt_time, "threads": threads,
              "fr_version": v}
    _own_wd = workdir is None
    if _own_wd:
        workdir = tempfile.mkdtemp(prefix="cec_fr_once_", dir=_TMP)

    try:
        jar = ensure_jar(jar, version=v)

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
                workdir=fr_wd, timeout=timeout, version=v,
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
        version=args.get("version"),   # None -> the worker's own FR_VERSION pin (env-aware)
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
