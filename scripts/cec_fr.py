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
    # Linux: ALWAYS prefer xvfb-run when available, even if $DISPLAY is set. The routing container
    # leaks a forwarded display (WSLg sets DISPLAY=:99 with a mounted X11 socket), and the old
    # `not $DISPLAY` guard then took the native-window path -> Freerouting popped a real Swing window
    # on the host desktop. Headless is the correct default for the compute plane; xvfb-run -a starts
    # its own virtual server and overrides the leaked DISPLAY. CEC_FR_USE_DISPLAY=1 opts a Linux
    # desktop dev back into the visible window. Windows/macOS are unaffected (native path below).
    if sys.platform.startswith("linux") and shutil.which("xvfb-run") and os.environ.get("CEC_FR_USE_DISPLAY") != "1":
        return ["xvfb-run", "-a"] + base
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
FR_VERSION = os.environ.get("CEC_FR_VERSION", "1.7.0-cec2")  # cec2 = cec1 + noecho/maxstall/progress (2026-07-14)

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
        "jar_sha256": "de01c829eab9406a1df6d1ad713a3334f138e77c122a61d2ba5a8364b8f904c2",
        "min_java": 17,
        "local_paths": ("/mnt/e/toolchain/fr-fork/freerouting-1.7.0-cec2.jar",
                        "build/fr-fork/freerouting-1.7.0-cec2.jar"),
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
    text = open(dsn_path, "r", encoding="utf-8", errors="replace").read()
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
        open(dsn_path, "w", encoding="utf-8").write(text)
    return removed


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
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, bufsize=1, **_pop_kw)
        _best, _streak, _killed, _lines = None, 0, False, []
        _t0 = time.monotonic()
        try:
            for _ln in proc.stdout:
                _lines.append(_ln)
                if time.monotonic() - _t0 > timeout:
                    proc.kill()
                    raise RuntimeError(
                        f"cec_fr.run_freerouting: timed out after {timeout}s "
                        f"(dsn={dsn_path!r}, jar={jar!r})")
                if _ln.startswith("CEC_PASS "):
                    print("[fr] " + _ln.strip(), flush=True)
                    m_f = re.search(r"failed=(\d+)", _ln)
                    m_g = re.search(r"togo=(\d+)", _ln)
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
                                _killed = True
                                proc.kill()
                                break
            proc.wait(timeout=30)
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
            tht_pts, shunt_pts = [], []
            for ref, px, py, is_tht in entries:
                if ref in shunt_refs:
                    shunt_pts.append((px, py))
                elif is_tht:
                    tht_pts.append((px, py))
            if not (tht_pts or shunt_pts):
                continue
            # PER-CLUSTER FAN-IN (escalated review 2026-07-08): the ATX-24's interleaved
            # pinout puts one rail's pins in 2-3 groups across the header; one bbox over all
            # of them spanned the board and overlapped the neighbor rails' pours on the same
            # layer (mass unconnected + foreign-on-pour). One sub-pour per pin x-cluster,
            # each converging on the shunt, keeps the copper a fan instead of a blanket.
            clusters = _x_clusters(tht_pts) or [[]]
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
        tht = [(p.GetPosition().x / MM, p.GetPosition().y / MM) for p in entries
               if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]
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
        if not tht or not shunt:
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
        for ci, cluster in enumerate(_x_clusters(tht)):
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


def edge_keepout(board_path, *, margin=0.6, clearance=0.8, board=None, edge_refs=("J", "H"),
                 layers=("F.Cu", "B.Cu")):
    """Route-time board-EDGE keepout (lever B, 2026-06-17). Freerouting has NO board-edge-clearance
    awareness -- the standard ExportSpecctraDSN gives it only the outline, so it routes signal tracks hard
    against Edge.Cuts (measured: ~100% of a routed CEC board's DRC is copper_edge_clearance, incl. a 67mm
    track run along the perimeter). Reserve a *margin*-wide strip just inside each board edge so FR keeps
    tracks off it. The strip EXCLUDES the (inflated) bounding boxes of edge-resident footprints -- connectors
    J* + mounts H* (and anything whose footprint name says Mounting/Conn/RJ45/USB) -- whose pads legitimately
    sit at the edge and must stay routable. allow_vias=False (no copper of any kind in the strip);
    block_fills=False so the high-current pours still fill to their own edge clamp. Returns bake_hints-ready
    rects; SELF-GATING (a board with no outline / all-edge parts yields fewer/no strips). Stack with
    corridor_keepouts in the same hints list."""
    own = board if board is not None else pcbnew.LoadBoard(board_path)
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

    allow = []                                              # inflated bboxes that may touch the edge
    for fp in own.GetFootprints():
        if _edge_resident(fp):
            fb = _fp_bbox_no_text(fp)
            allow.append((fb.GetLeft() / MM - clearance, fb.GetTop() / MM - clearance,
                          fb.GetRight() / MM + clearance, fb.GetBottom() / MM + clearance))

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
                          stub_w=1.0, clear=0.25):
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
            base = pcbnew.VECTOR2I(int(pos.x + ux * _nm(1.6)), int(pos.y + uy * _nm(1.6)))
            perp = (-uy, ux)
            placed = 0
            for k in range(n_per_pad):
                off = (k - (n_per_pad - 1) / 2.0)
                at = pcbnew.VECTOR2I(int(base.x + perp[0] * off * step),
                                     int(base.y + perp[1] * off * step))
                if not _tap_pair_overlap_clear(board, pos, at, _nm(stub_w),
                                               board.GetLayerID(p.GetLayerName()), nc, set()):
                    continue
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(at)
                v.SetDrill(_nm(drill))
                v.SetWidth(_nm(dia))
                v.SetNetCode(nc)
                board.Add(v)
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


def _tap_foreign_clear(board, S, T, width_nm, layer_id, clearance_nm, sense_codes):
    """True iff a single straight F.Cu segment S->T (width width_nm) has NO FOREIGN-net copper
    within clearance_nm on layer_id. FOREIGN = any pad/track/via whose net code is NOT in
    sense_codes (the set of all _HI/_LO Kelvin-pair codes -- so the partner sense leg and the
    tap's own net never count, only GND/+3V3/signal/power foreign copper does). Uses the SAME
    GetEffectiveShape().Collide() geometry KiCad DRC uses, so a PASS here is DRC-clean for copper
    clearance on this segment -- the guard that lets the tap REFUSE rather than lay a shorting stub."""
    seg = pcbnew.SHAPE_SEGMENT(S, T, width_nm)
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


def synthesize_kelvin_taps(board, *, kelvin_pairs=None, width=0.25, layer="F.Cu", max_ic_mm=9.0,
                           clearance=0.2):
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

    SELF-GATING: a board with no 2-pad straddle shunt, or no INA input pad on a sense net within
    max_ic_mm of the shunt (shared-bus 24-pin / filtered 12VHPWR lanes), lays nothing and is a no-op.
    Pass an already-loaded *board* (additive, in place). Returns a report dict
    {taps, by_net: {net: ["RSn->Uk.pad", ...]}, refused: {net: [...]}}."""
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
    laid, report, refused = [], {}, {}
    pending = []                                              # decide-then-lay: guard sees no in-call taps
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
            # INA181 detection amp both tap the shunt; skip a stray INA farther than max_ic_mm.
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
                # CANONICAL FIRST (owner 2026-07-08): the textbook datasheet tap --
                # perpendicular off the inner edge, straight run inward, ONE 90 toward
                # the sense IC. Preferred over the direct diagonal whenever it guards
                # clean; falls through to straight, then doglegs, then refusal.
                _gap = math.hypot((other_pos.x - pc.x) / MM, (other_pos.y - pc.y) / MM)
                canon = _canonical_tap_path(S, T, _ux, _uy, gap_mm=_gap)
                if canon is not None:
                    legs = list(zip(canon, canon[1:]))
                    if all(a != b for a, b in legs) and \
                       all(_tap_foreign_clear(board, a, b, _nm(width), lay_id, clr_nm,
                                              sense_codes) and
                           _tap_pair_overlap_clear(board, a, b, _nm(width), lay_id, nc,
                                                   sense_codes)
                           for a, b in legs):
                        pending.append((canon, nc, net, lbl + " (canonical)", lay_id))
                        continue
                # GUARD (defence 2): refuse rather than lay a stub that clips foreign copper.
                if _tap_foreign_clear(board, S, T, _nm(width), lay_id, clr_nm, sense_codes):
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
                for path in _dogleg_candidates(S, T):
                    legs = list(zip(path, path[1:]))
                    if all(a != b for a, b in legs) and \
                       all(_tap_foreign_clear(board, a, b, _nm(width), lay_id, clr_nm,
                                              sense_codes) and
                           _tap_pair_overlap_clear(board, a, b, _nm(width), lay_id, nc,
                                                   sense_codes)
                           for a, b in legs):
                        bent = path
                        break
                if bent is not None:
                    pending.append((bent, nc, net, lbl + " (bent)", lay_id))
                else:
                    refused.setdefault(net, []).append(lbl)
            # VBUS BRIDGE: the INA238/228 ties Vbus (pad 8) to the SAME LO net as IN- (pad 9),
            # 0.5mm below it INSIDE the reserved tap channel -- FR is kept out of the channel,
            # so bridge the two same-net pads with a stub here (what a hand layout does). Only
            # for the LO role of a recognised part, only when both pads are on this net.
            if role == "LO":
                for r, p in sorted(ic_pad.items()):
                    fp9 = ic_fp.get(r)
                    if fp9 is None or _sense_in_pad(fp9, "LO") != p.GetPadName():
                        continue                       # unknown part -- no pin-function map
                    vb = next((q for q in fp9.Pads()
                               if q.GetPadName() == "8" and q.GetNetname() == net), None)
                    if vb is None:
                        continue
                    A, B = p.GetPosition(), vb.GetPosition()
                    if _tap_pair_overlap_clear(board, A, B, _nm(width), lay_id, nc, sense_codes):
                        pending.append(([A, B], nc, net,
                                        "%s.9->%s.8 (vbus bridge)" % (r, r), lay_id))
    # lay the guarded taps (after all decisions, so the guard never saw an in-call tap)
    for path, nc, net, lbl, p_lay in pending:
        for A, B in zip(path, path[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(A)
            t.SetEnd(B)
            t.SetWidth(_nm(width))
            t.SetLayer(p_lay)
            t.SetNetCode(nc)
            board.Add(t)
            laid.append(t)
        report.setdefault(net, []).append(lbl)
    return {"taps": sum(len(v) for v in report.values()),
            "by_net": report, "refused": refused, "segments": len(laid)}


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
    """Remove a temp board AND the .kicad_pro/.kicad_prl sidecars pcbnew.SaveBoard writes next to it
    (os.remove on the .kicad_pcb alone leaks the two sidecars on every staged stagger -- re-audit LOW)."""
    base = path[:-len(".kicad_pcb")] if path.endswith(".kicad_pcb") else path
    for p in (path, base + ".kicad_pro", base + ".kicad_prl"):
        try:
            os.remove(p)
        except OSError:
            pass


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
def owned_locked_nets(board_path: str) -> set:
    """Read-only: nets FULLY OWNED by locked copper (every pad on the net touched by
    a locked track endpoint, pad half-extent + 0.15mm) -- the ownership test
    reconcile_locked_nets enforces after the route, exposed pre-route so the DSN can
    EXCLUDE those nets from Freerouting entirely (owner 2026-07-12: "the router is
    still touching the force copper")."""
    board = pcbnew.LoadBoard(board_path)
    locked_pts = {}
    for t in board.GetTracks():
        if not t.IsLocked():
            continue
        n = t.GetNetname() or ""
        if t.Type() == pcbnew.PCB_VIA_T:
            p_ = t.GetPosition()
            locked_pts.setdefault(n, []).append((p_.x, p_.y))
        else:
            s_, e_ = t.GetStart(), t.GetEnd()
            locked_pts.setdefault(n, []).extend([(s_.x, s_.y), (e_.x, e_.y)])
    pads_by_net = {}
    for fp in board.GetFootprints():
        for pd in fp.Pads():
            n = pd.GetNetname() or ""
            if n in locked_pts:
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
    return owned


def locked_copper_keepouts(board_path: str, *, only_nets=None, clearance: float = 0.2):
    """Rule-area keepout rects over LOCKED copper, per layer (owner defect report
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
    needs access to its pads. Same-layer rects merge only when the union stays
    TIGHT (union area <= 1.15x the sum) so a dense cell collapses to a few zones
    but a diagonal pair can never over-cover a foreign channel/pad."""
    board = pcbnew.LoadBoard(board_path)
    cl = int(clearance * 1e6)
    per_layer = {}
    for t in board.GetTracks():
        if not t.IsLocked():
            continue
        if only_nets is not None and (t.GetNetname() or "") not in only_nets:
            continue
        bb = t.GetBoundingBox()
        box = [bb.GetLeft() - cl, bb.GetTop() - cl, bb.GetRight() + cl, bb.GetBottom() + cl]
        if t.Type() == pcbnew.PCB_VIA_T:
            lays = ("F.Cu", "B.Cu")
        else:
            lays = (board.GetLayerName(t.GetLayer()),)
        for ly in lays:
            per_layer.setdefault(ly, []).append(list(box))

    def _area(b):
        return max(0, b[2] - b[0]) * max(0, b[3] - b[1])

    out = []
    for ly, boxes in sorted(per_layer.items()):
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
                    if _area(u) <= 1.15 * (_area(a) + _area(b)):
                        boxes[i] = u
                        del boxes[j]
                        merged = True
                        break
                if merged:
                    break
        for k, (x0, y0, x1, y1) in enumerate(boxes):
            out.append({"name": "lockedcu-%s-%d" % (ly.replace(".", ""), k),
                        "x0": x0 / 1e6, "y0": y0 / 1e6,
                        "x1": x1 / 1e6, "y1": y1 / 1e6, "layers": (ly,)})
    return out


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


def import_ses(board_path: str, ses_path: str, out_path: str, *,
               fill_zones: bool = True, fix_annular: bool = True, power_pours=(),
               kelvin_taps: bool = True, skip_locked_taps: bool = False) -> str:
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
        _has_locked_taps = False
        if skip_locked_taps:
            _has_locked_taps = any(
                t.GetClass() == "PCB_TRACK" and t.IsLocked()
                and (t.GetNetname().endswith("_HI") or t.GetNetname().endswith("_LO"))
                for t in board.GetTracks())
        if os.environ.get("CEC_KELVIN_TAPS", "1") != "0" and not _has_locked_taps:
            kt = synthesize_kelvin_taps(board)
            if kt["taps"]:
                print(f"[cec_fr] kelvin taps: laid {kt['taps']} inner-edge stub(s) "
                      f"{kt['by_net']}", file=sys.stderr)
        elif _has_locked_taps:
            print("[cec_fr] kelvin taps: board carries LOCKED tap copper -- skipping re-synthesis "
                  "(precision pre-FR taps already laid + protected)", file=sys.stderr)
        # INNER-POUR force bridge: when the rail pours live on In2 (PWR_RT boards), each SMD
        # shunt pad needs vias down to them -- THT pins pierce natively, SMD pads do not.
        if any(str(p.get("layer")) == "In2.Cu" for p in (power_pours or ())):
            fv = synthesize_force_vias(board)
            if fv["vias"]:
                print(f"[cec_fr] force vias: {fv['vias']} via(s)/{fv['stubs']} stub(s) at "
                      f"{fv['pads']} shunt pad(s) -> In2 rail pours", file=sys.stderr)
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

        # 1. Bake hints (keepouts) into a working copy. When locked-protected nets
        # are in play, the FULLY-OWNED nets' locked copper ALSO bakes as rule-area
        # keepouts (owner defect report 2026-07-14: FR routed straight through the
        # blueprint cells -- an excluded net's protect wires drop out of FR's
        # obstacle model, see locked_copper_keepouts). Computed on board_path
        # (bake only adds zones; ownership reads tracks+pads, identical either way)
        # so the SAME set drives the keepouts and the pin exclusion below.
        _owned = set()
        if protect_nets:
            try:
                _owned = owned_locked_nets(board_path)
                if _owned:
                    _lk = locked_copper_keepouts(board_path, only_nets=_owned)
                    hints = list(hints) + _lk
                    print("[cec_fr] locked-copper keepouts: %d zone(s) over %d owned "
                          "net(s)" % (len(_lk), len(_owned)), flush=True)
            except Exception as _e:                            # noqa: BLE001
                print("[cec_fr] locked-copper keepouts failed (%s) -- protect-only"
                      % _e, flush=True)
        hinted_board = os.path.join(workdir, "hinted.kicad_pcb")
        bake_hints(board_path, hinted_board, keepouts=hints, copy_pro=True)

        # 2. Export DSN
        dsn_path = os.path.join(workdir, "board.dsn")
        export_dsn(hinted_board, dsn_path)
        if protect_nets:
            import cec_fr02
            cec_fr02.force_protect_in_dsn(dsn_path, list(protect_nets))
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
        import_ses(board_path, ses_path, out_path, power_pours=power_pours,
                   skip_locked_taps=skip_locked_taps)

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
