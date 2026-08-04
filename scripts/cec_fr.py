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
from concurrent.futures import ProcessPoolExecutor, as_completed

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
        "jar_sha256": "149cebd88169be77f5ddc7e1d50284451204f10c088e5d7380859ab0395b7ce5",
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
)


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
        pat = re.compile(r"(\(layer\s+" + re.escape(name) + r"\s*\(\s*type\s+)signal(\s*\))")
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
        _pnets = plane_tht_exclusion_nets(board)
        if _pnets:
            _tht = set()
            for fp in board.GetFootprints():
                for p in fp.Pads():
                    if (p.GetNetname() in _pnets
                            and p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD):
                        _tht.add(f"{fp.GetReference()}-{p.GetPadName()}")
            if _tht:
                n = _dsn_exclude_pins(dsn_path, _tht)
                print(f"[cec_fr] plane-THT policy: excluded {len(_tht)} THT pad(s) on "
                      f"plane net(s) {sorted(_pnets)} ({n} DSN token(s) removed) -- "
                      "the plane fill is their connection", file=sys.stderr)
    return dsn_path


# ---------------------------------------------------------------------------
# run_freerouting
# ---------------------------------------------------------------------------
def _plateau_floor_disables(best_togo, floor):
    """Plateau-floor semantics (probe 2026-07-23): a flat streak whose best togo
    sits AT/UNDER the floor is FR's normal terminal grind / rip-up phase, not a
    collapse -- the kill is disabled for the rest of the run so the board
    finishes and grades (the killed togo-34 hub board re-routed to unconn 7 =
    the best hub result ever). floor<=0 = feature off (historical behavior)."""
    return floor > 0 and best_togo <= floor


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
        # togo is <= n DISABLES the kill for the rest of the run (the board is
        # nearly routed -- worth finishing + grading); above the floor the kill
        # fires as before (the 24-pin's true collapses sit flat at 190-230 from
        # early passes). Default 0 = floor off, exactly the historical behavior.
        _pfloor = 0
        _pfe = os.environ.get("CEC_FR_PLATEAU_FLOOR", "")
        if _pfe.isdigit():
            _pfloor = int(_pfe)
        _best, _streak, _killed, _lines = None, 0, False, []
        _pk_disabled = False
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
                        elif _f > 0 and not _pk_disabled:
                            _streak += 1
                            if _streak >= _k:
                                if _plateau_floor_disables(_best[0], _pfloor):
                                    _pk_disabled = True
                                    print(f"[cec_fr] plateau at togo/failed={_best} is "
                                          f"WITHIN the floor ({_pfloor}) -- terminal "
                                          f"grind, kill disabled; running to completion",
                                          flush=True)
                                else:
                                    _killed = True
                                    _kill_fr_tree(proc)
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
            try:
                _out, _err = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                _kill_fr_tree(proc)
                try:
                    proc.communicate(timeout=15)
                except Exception:
                    pass
                raise RuntimeError(
                    f"cec_fr.run_freerouting: timed out after {timeout}s "
                    f"(dsn={dsn_path!r}, jar={jar!r})"
                ) from exc
            result = subprocess.CompletedProcess(cmd, proc.returncode,
                                                 _out or "", _err or "")
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
    for p in pours:
        net = p["net"]
        # v3.1 CONNECTOR MANIFOLDS are the ONE named admit through the
        # shunt-only top rule (owner algorithm 2026-07-25: "combine up all
        # similar pins on one connector with a margin-width pour" -- the
        # manifold is the connector's OWN pin field + margin, pad-anchored
        # by construction, not signal-fabric decoration).
        _is_manifold = str(p.get("name") or "").startswith("manifold:")
        if p.get("layer", "F.Cu") == "F.Cu" and _f_nbs and not _is_manifold:
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
        z.SetAssignedPriority(int(p.get("priority", 2)))
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


def edge_keepout(board_path, *, margin=1.25, clearance=0.8, board=None, edge_refs=("J", "H"),
                 layers=None):
    """Route-time board-EDGE keepout (lever B, 2026-06-17). Freerouting has NO board-edge-clearance
    awareness -- the standard ExportSpecctraDSN gives it only the outline, so it routes signal tracks hard
    against Edge.Cuts (measured: ~100% of a routed CEC board's DRC is copper_edge_clearance, incl. a 67mm
    track run along the perimeter). Reserve a *margin*-wide strip just inside each board edge so FR keeps
    tracks off it. The strip EXCLUDES the (inflated) bounding boxes of edge-resident footprints -- connectors
    J* + mounts H* (and anything whose footprint name says Mounting/Conn/RJ45/USB) -- whose pads legitimately
    sit at the edge and must stay routable. allow_vias=False (no copper of any kind in the strip);
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
        if lay == "F.Cu" and d.get("provenance") != "slab":
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
                             drill=0.3, dia=0.6, lock=False):
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
    remains routable. Returns
    {pads, vias, stubs, pofv, skipped}.

    ``filled_zone_nets`` is the post-fill form of the contract. Those nets
    are eligible only where their *actual filled polygon* contains the future
    via centre; a zone bounding box is used only as a cheap prefilter. This
    lets a second pass connect surface rail pads after shaped pours exist
    without treating the empty space between over-under lanes as copper."""
    import math as _math
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
                "skipped": 0}
    def _filled_at(net, at):
        """Whether *at* is in real, already-filled same-net copper."""
        if net not in exact_nets:
            return True
        return any(poly.Contains(at) for poly in filled_polys.get(net, ()))

    # Use KiCad's real connectivity graph instead of an endpoint-near-bbox
    # proxy, which is ambiguous at rotated and oval lands.
    board.BuildConnectivity()
    connectivity = board.GetConnectivity()
    touched = set()
    tracks = [t for t in board.GetTracks()]
    # via-spacing ledger (the s218 clipping class): never seat a pickup barrel
    # within 0.85mm of ANY existing or just-placed via
    _pk_vias = [(t.GetPosition().x, t.GetPosition().y)
                for t in tracks if t.GetClass() == "PCB_VIA"]
    n_p = n_v = n_s = n_pofv = n_skip = 0
    skipped_detail = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            net = pad.GetNetname()
            if net not in polys:
                continue
            if pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue                       # THT pierces the stack natively
            pos = pad.GetPosition()
            px, py = pos.x / 1e6, pos.y / 1e6
            boxes = [b for b in polys[net]
                      if b[0] <= px <= b[2] and b[1] <= py <= b[3]]
            if not boxes and net not in requested:
                continue                       # no covering pour -> not ours
            try:
                pad_uuid = pad.m_Uuid.AsString()
                hit = any(item.m_Uuid.AsString() != pad_uuid
                          and item.GetNetCode() == pad.GetNetCode()
                          for item in connectivity.GetConnectedItems(pad))
            except Exception:                            # noqa: BLE001
                hit = False
            if hit:
                continue                       # FR/locked copper reached it
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
                # The pickup starts at an SMD pin.  A class-width 1.0 mm power
                # stub cannot enter a 0.4 mm IC pad without consuming adjacent
                # pins; use the same bounded neck-down doctrine enforced later
                # by normalize_netclass_geometry.  Half the pad minor dimension
                # leaves copper/mask room on both sides, while the board minimum
                # prevents an unfabricably thin escape.
                try:
                    board_min_w = board.GetDesignSettings().m_TrackMinWidth / MM
                except Exception:                       # noqa: BLE001
                    board_min_w = 0.2
                pad_minor = min(pad.GetSize().x, pad.GetSize().y) / MM
                local_stub_w = min(
                    class_stub_w,
                    max(float(board_min_w or 0.2), pad_minor / 2.0))
            except Exception:                            # noqa: BLE001
                local_dia, local_drill, local_stub_w = dia, drill, stub_w
            via_spacing = max(0.85, local_dia + 0.25)

            # VIA-IN-PAD FIRST. The centralized fabrication check proves the
            # declared profile, same-net identity, SMD attribute, dimensions,
            # and full-land containment. The all-layer collision probe then
            # applies the ordinary through-via clearance contract. Refusal at
            # either gate preserves the established adjacent-via fallback.
            if (_filled_at(net, pos)
                    and not any((pos.x - qx) ** 2 + (pos.y - qy) ** 2 < _nm(via_spacing) ** 2
                        for qx, qy in _pk_vias)
                    and _edge_leg_clear(board, pos, pos,
                                       _nm(local_dia) // 2)
                    and _via_spot_clear(board, pos, _nm(local_dia), _nm(0.25),
                                        {nc}, drill_nm=_nm(local_drill),
                                        net_code=nc)):
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pos)
                v.SetDrill(_nm(local_drill))
                v.SetWidth(_nm(local_dia))
                v.SetNetCode(nc)
                v.SetLocked(bool(lock))
                board.Add(v)
                _pk_vias.append((pos.x, pos.y))
                tracks.append(v)
                n_v += 1; n_p += 1; n_pofv += 1
                continue

            if not boxes:
                # A raw ask without established geometry may bootstrap only
                # through a fabrication-qualified via in pad. An adjacent via
                # has no proven future-pour coverage yet, so do not guess one.
                n_skip += 1
                skipped_detail.append({"ref": fp.GetReference(),
                                       "pad": pad.GetPadName(), "net": net,
                                       "reason": "no proven covering copper"})
                continue

            placed = False
            for off_mm in (offset, offset + 0.4, offset - 0.25):
                if placed:
                    break
                for ang in (0, 90, 180, 270, 45, 135, 225, 315):
                    a = _math.radians(ang)
                    at = pcbnew.VECTOR2I(int(pos.x + _math.cos(a) * _nm(off_mm)),
                                         int(pos.y + _math.sin(a) * _nm(off_mm)))
                    ax, ay = at.x / 1e6, at.y / 1e6
                    if not any(b[0] + local_dia / 2 <= ax <= b[2] - local_dia / 2
                               and b[1] + local_dia / 2 <= ay <= b[3] - local_dia / 2
                               for b in boxes):
                        continue               # via must sit inside the pour
                    if not _filled_at(net, at):
                        continue               # bbox hit but no real filled copper
                    if any((at.x - qx) ** 2 + (at.y - qy) ** 2 < _nm(via_spacing) ** 2
                           for qx, qy in _pk_vias):
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
                    if not (_tap_foreign_clear(board, pos, at, _nm(local_stub_w),
                                               lay_id, _nm(0.25), {nc})
                            and _edge_leg_clear(board, pos, at,
                                               _nm(local_stub_w) // 2)
                            and _edge_leg_clear(board, at, at,
                                               _nm(local_dia) // 2)
                            and _via_spot_clear(board, at, _nm(local_dia),
                                                _nm(0.25), {nc},
                                                drill_nm=_nm(local_drill),
                                                net_code=nc)
                            and _tap_pair_overlap_clear(board, pos, at, _nm(local_stub_w),
                                                        lay_id, nc, set())):
                        continue
                    v = pcbnew.PCB_VIA(board)
                    v.SetPosition(at)
                    v.SetDrill(_nm(local_drill))
                    v.SetWidth(_nm(local_dia))
                    v.SetNetCode(nc)
                    v.SetLocked(bool(lock))
                    board.Add(v)
                    _pk_vias.append((at.x, at.y))
                    tr = pcbnew.PCB_TRACK(board)
                    tr.SetStart(pos)
                    tr.SetEnd(at)
                    tr.SetWidth(_nm(local_stub_w))
                    tr.SetLayer(lay_id)
                    tr.SetNetCode(nc)
                    tr.SetLocked(bool(lock))
                    board.Add(tr)
                    tracks.append(tr)
                    n_v += 1; n_s += 1; n_p += 1
                    placed = True
                    break
            if not placed:
                n_skip += 1
                skipped_detail.append({"ref": fp.GetReference(),
                                       "pad": pad.GetPadName(), "net": net,
                                       "reason": "no guarded via slot in filled copper"})
    return {"pads": n_p, "vias": n_v, "stubs": n_s,
            "pofv": n_pofv, "skipped": n_skip,
            "skipped_detail": skipped_detail[:32]}


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


def _guarded_lastmile_legs(board, S, T, w, lay, clearance_nm, nc, leg_ok):
    """Choose the first collision- and edge-safe canonical path S -> T."""
    profiled = _guarded_profiled_lastmile_legs(
        board, S, T, w, lay, clearance_nm, nc, leg_ok)
    if profiled is not None:
        return [(a, b) for a, b, _width in profiled]
    return None


def _profiled_lastmile_path(points, w, start_escape=None, end_escape=None):
    """Split a canonical path at bounded endpoint neck-down transitions.

    ``start_escape`` and ``end_escape`` are ``(width_nm, budget_nm)`` pairs.
    Width changes occur at deterministic graph-distance boundaries, never in
    the middle of an unsplit track.  Overlapping endpoint budgets intentionally
    keep the intervening short gap narrow; normalize_netclass_geometry applies
    the identical bounded escape doctrine after the copper is added.
    """
    import math as _math

    lengths = [_math.hypot(b.x - a.x, b.y - a.y)
               for a, b in zip(points, points[1:])]
    total = sum(lengths)
    if total <= 0:
        return []
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


def _maze_lastmile_legs(board, S, T, w, lay, clearance_nm, nc, leg_ok,
                         *, start_escape=None, end_escape=None,
                         grid_mm=0.5, margin_mm=2.0):
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

    if start_escape is None and end_escape is None:
        return None

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

    # state = (x-index, y-index, previous direction, start-narrow, end-narrow)
    start_state = (start_node[0], start_node[1], -1,
                   bool(start_escape), False)
    best = {start_state: 0.0}
    travelled = {start_state: 0.0}
    previous = {}
    serial = _itertools.count()
    heap = [(_to_target(start_node), 0.0, 0.0, next(serial), start_state)]
    final_state = None
    directions = ((1, 0), (-1, 0), (0, 1), (0, -1))
    clear_cache = {}
    foreign_zones, foreign_copper = _layer_foreign_shapes(
        board, lay, {nc})
    foreign_zones = _bucket_foreign_shapes(foreign_zones)
    foreign_copper = _bucket_foreign_shapes(foreign_copper)

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
        ix_, iy_, old_dir, start_narrow, end_narrow = state
        node = (ix_, iy_)
        if node == target_node:
            final_state = state
            break
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
            if (end_escape and current_to_target <= float(end_escape[1]) + 1e-6
                    and next_to_target < current_to_target):
                next_end = True
                width = min(width, int(end_escape[0]))

            if not _hop_clear(A, B, width):
                continue
            turn = 0 if old_dir in (-1, direction) else _nm(0.2)
            new_cost = cost + length + turn
            new_state = (nx, ny, direction, next_start, next_end)
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
                                     end_escape=None, allow_maze=True):
    """Choose a guarded canonical path with optional bounded pin neck-downs."""
    xy_paths = _canonical_45_xy_paths((S.x, S.y), (T.x, T.y))
    xy_paths += _offset_manhattan_xy_paths((S.x, S.y), (T.x, T.y))
    for xy_path in xy_paths:
        points = [pcbnew.VECTOR2I(x, y) for x, y in xy_path]
        legs = _profiled_lastmile_path(
            points, w, start_escape=start_escape, end_escape=end_escape)
        if all(leg_ok(a, b, width // 2)
               and _tap_foreign_clear(board, a, b, width, lay,
                                       clearance_nm, {nc})
               for a, b, width in legs):
            return legs
    if allow_maze:
        return _maze_lastmile_legs(
            board, S, T, w, lay, clearance_nm, nc, leg_ok,
            start_escape=start_escape, end_escape=end_escape)
    return None


def synthesize_local_power_bypass_links(
        board, *, max_mm=5.0, min_class_width=0.5, min_w=0.2,
        clearance=0.25, lock=True, netclass_resolver=None):
    """Pre-route short local supply links that the global router must preserve.

    A two-terminal fitted ``C*`` footprint with exactly one GND pad is a local
    bypass/bulk capacitor only when its other rail belongs to a power-width
    netclass.  Pair that rail pad with the nearest same-net SMD pad on an IC or
    reverse-mount LED (``U*``/``DL*``) within *max_mm*, then lay a guarded
    same-layer 0/45/90 path.  The class-width trunk and bounded fine-pad
    neck-downs use the same geometry contract as :func:`synthesize_lastmile`
    and :func:`normalize_netclass_geometry`.

    This deliberately ignores Default-class RC/filter capacitors and every
    connector/passive destination.  It is therefore a local power-integrity
    primitive, not a generic pre-router that could freeze arbitrary signal
    topology.  Collision, board-edge, and internal-cutout refusal is fail
    closed.  Returns ``{pairs, linked, legs, refused, ignored, detail}``.
    """
    import math as _math

    all_cu = set(board.GetEnabledLayers().CuStack())

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

    pairs = linked = legs_added = refused = 0
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
                    selected = (distance, load_ref, load_number, layer, path)
                    break
            if selected:
                break
        if selected is None:
            refused += 1
            detail.append({"cap": cap_ref, "net": cap_pad.GetNetname(),
                           "status": "refused", "reason": "no guarded path"})
            continue

        distance, load_ref, load_number, layer, path = selected
        for start, end, width in path:
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(start)
            track.SetEnd(end)
            track.SetWidth(width)
            track.SetLayer(layer)
            track.SetNetCode(net_code)
            track.SetLocked(bool(lock))
            board.Add(track)
            legs_added += 1
        linked += 1
        detail.append({"cap": cap_ref, "load": load_ref,
                       "pad": load_number, "net": cap_pad.GetNetname(),
                       "distance_mm": round(distance, 3),
                       "layer": board.GetLayerName(layer),
                       "legs": len(path), "status": "linked"})

    return {"pairs": pairs, "linked": linked, "legs": legs_added,
            "refused": refused, "ignored": ignored, "detail": detail}


def synthesize_local_signal_links(
        board, *, max_mm=5.0, max_refs=3, min_power_width=0.5,
        min_w=0.2, clearance=0.20, lock=True,
        netclass_resolver=None):
    """Pre-route topology-proven private IC programming networks.

    A local threshold divider, soft-start capacitor, or current-limit resistor
    should be complete before the global router spends congestion budget on
    it.  Select only nets with one ``U*`` owner and one or two fitted ``R*``/
    ``C*`` followers, no connector or other active member, a non-power
    netclass width, and no Kelvin/differential-pair role.  Connect the nearest
    remaining follower to the already-connected local cluster with guarded
    same-layer 0/45/90 copper.  This is the routing counterpart of the placer's
    low-fanout functional ownership rule and contains no board/refdes list.

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

    networks = linked = legs_added = refused = ignored = 0
    detail = []
    for net, rows in sorted(pads_by_net.items()):
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
                        selected = (distance, target_ref, source_ref, layer,
                                    target_pad.GetNetCode(), path)
                        break
                if selected:
                    break
                blocked_edges.add(edge)
            if selected is None:
                refused += len(remaining)
                detail.append({"net": net, "owner": owner,
                               "followers": sorted(remaining),
                               "status": "refused", "reason": "no guarded MST edge"})
                break
            distance, target_ref, source_ref, layer, net_code, path = selected
            for start, end, width in path:
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(start)
                track.SetEnd(end)
                track.SetWidth(width)
                track.SetLayer(layer)
                track.SetNetCode(net_code)
                track.SetLocked(bool(lock))
                board.Add(track)
                legs_added += 1
            linked += 1
            connected_refs.add(target_ref)
            remaining.remove(target_ref)
            board.BuildConnectivity()
            detail.append({"net": net, "owner": owner, "from": source_ref,
                           "to": target_ref, "distance_mm": round(distance, 3),
                           "layer": board.GetLayerName(layer),
                           "legs": len(path), "status": "linked"})

    return {"networks": networks, "linked": linked, "legs": legs_added,
            "refused": refused, "ignored": ignored, "detail": detail}


def _lastmile_bridge(board, A, al, B, bl, w, nc, bridge_lays, clearance_nm,
                     *, drill=0.3, dia=0.6, leg_ok=None,
                     start_escape=None, end_escape=None):
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

    # existing via positions (ANY net): the foreign guard exempts same-net
    # vias, but a seat drilled hole-to-hole against one is a hole_clearance
    # hit regardless of net -- keep every synthesized seat 0.85mm off any barrel
    ex_vias = [(t.GetPosition().x, t.GetPosition().y)
               for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]

    def _seat(end, lays, lay_b, escape):
        ex, ey = end
        if lay_b in lays:
            return (end, [])                      # via/THT/track-on-bridge: direct
        lay_e = min(lays)
        for off in (0.55, 0.8, 1.2):
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
                    board, S, V, w, lay_e, clearance_nm, nc, leg_ok,
                    start_escape=escape, allow_maze=False)
                if not stub_legs:
                    continue
                if not _via_spot_clear(board, V, _nm(dia), clearance_nm,
                                       {nc}, drill_nm=_nm(drill),
                                       net_code=nc):
                    continue
                stub_ops = [("trk", a, b, width, lay_e)
                            for a, b, width in stub_legs]
                return ((vx, vy), stub_ops + [("via", V)])
        return None

    for lay_b in bridge_lays:
        sa = _seat(A, al, lay_b, start_escape)
        sb = _seat(B, bl, lay_b, end_escape)
        if sa is None or sb is None:
            continue
        (pa, ops_a), (pb, ops_b) = sa, sb
        if ops_a and ops_b:                       # both seats synthesized: keep
            if ((pa[0] - pb[0]) ** 2 + (pa[1] - pb[1]) ** 2
                    < _nm(0.85) ** 2):            # their drills apart too
                continue
        S = pcbnew.VECTOR2I(int(pa[0]), int(pa[1]))
        T = pcbnew.VECTOR2I(int(pb[0]), int(pb[1]))
        legs = _guarded_lastmile_legs(
            board, S, T, w, lay_b, clearance_nm, nc, leg_ok)
        if legs is None:
            continue
        ops = list(ops_a) + list(ops_b)
        for (ls_, le_) in legs:
            ops.append(("trk", ls_, le_, w, lay_b))
        # normalize the stub ops' width/layer tuple shape
        out = []
        for op in ops:
            if op[0] == "via":
                out.append(("via", op[1], drill, dia))
            else:
                out.append(op)
        return out
    return None


def synthesize_lastmile(board, *, max_mm=5.0, min_w=0.25, clearance=0.25, cap=40,
                        netclass_resolver=None):
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
    ``netclass_resolver`` supplies the final project via dimensions.  Bridge
    seats MUST be collision-checked at those dimensions: validating the
    router-default 0.6/0.3 mm land and enlarging it later can turn a legal seat
    beside a fine-pitch pad into an unqualified via-in-pad.  Returns
    {closed, legs, refused, far, cross_layer}."""
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

    by_net = defaultdict(list)                    # nc -> [(identity, kind, obj)]
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() > 0:
                by_net[p.GetNetCode()].append((_item_key("pad", p), "pad", p))
    for t in board.GetTracks():
        if t.GetNetCode() > 0:
            k = "via" if t.GetClass() == "PCB_VIA" else "trk"
            by_net[t.GetNetCode()].append((_item_key(k, t), k, t))
    width_mode = {}
    for nc_, items in by_net.items():
        ws = Counter(o.GetWidth() for u, k, o in items if k == "trk")
        width_mode[nc_] = ws.most_common(1)[0][0] if ws else _nm(min_w)
    net_names = {code: info.GetNetname()
                 for code, info in board.GetNetInfo().NetsByNetcode().items()}

    def _contract_width(nc_):
        spec = (netclass_resolver(net_names.get(nc_, ""))
                if netclass_resolver is not None else {}) or {}
        name = (net_names.get(nc_, "") or "").upper()
        pairish = (bool(re.search(r"_(?:P|N)$", name))
                   or name.endswith(("CAN_H", "CAN_L", "CAN_H_BUS",
                                      "CAN_L_BUS"))
                   or "USB_D" in name)
        width = float((spec.get("diff_pair_width") if pairish else None)
                      or spec.get("track_width") or 0)
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

    def _anchors(kind, obj, class_width):
        """[(x, y, layers, escape)] -- connectable points of an item."""
        if kind == "pad":
            ls = frozenset(l for l in obj.GetLayerSet().CuStack() if l in all_cu)
            p = obj.GetPosition()
            return [(p.x, p.y, ls, _pin_escape(kind, obj, class_width))]
        if kind == "via":
            p = obj.GetPosition()
            return [(p.x, p.y, frozenset(all_cu), None)]
        s, e = obj.GetStart(), obj.GetEnd()
        ls = frozenset((obj.GetLayer(),))
        return [(s.x, s.y, ls, None), (e.x, e.y, ls, None)]

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
    for nc_, items in by_net.items():
        if len(items) < 2 or nc_ in kelvin_nc:
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
                for (ax, ay, al, ae) in clusters[i]:
                    for (bx, by_, bl, be) in clusters[j]:
                        d = ((ax - bx) ** 2 + (ay - by_) ** 2) ** 0.5 / 1e6
                        if d <= max_mm:
                            com = (al & bl) - plane_ids
                            pairs.append((d, i, j, (ax, ay), (bx, by_),
                                          com, al, bl, ae, be))
        if not pairs:
            n_far += len(clusters) - 1
            continue
        pairs.sort(key=lambda p: p[0])
        bridge_lays = sorted((l for l in all_cu
                              if l not in plane_ids and l != pcbnew.F_Cu),
                             reverse=True)
        tries = {}
        for d, i, j, A, B, com, al, bl, ae, be in pairs:
            if n_closed >= cap:
                break
            ri, rj = _find(i), _find(j)
            if ri == rj:
                continue
            key = (min(ri, rj), max(ri, rj))
            if tries.get(key, 0) >= 4:
                continue
            tries[key] = tries.get(key, 0) + 1
            spec, w = _contract_width(nc_)
            S = pcbnew.VECTOR2I(int(A[0]), int(A[1]))
            T = pcbnew.VECTOR2I(int(B[0]), int(B[1]))
            ops = None
            # Same-layer canonical 0/45/90 path first, emptier layers before
            # congested F. Never introduce arbitrary-angle copper here: raw FR
            # already emits octilinear routes, and a free-angle shortcut creates
            # hard-to-read diagonal stubs and acute copper joins.
            for lay in sorted(com, reverse=True):
                legs = _guarded_profiled_lastmile_legs(
                    board, S, T, w, lay, _nm(clearance), nc_, _lm_leg_ok,
                    start_escape=ae, end_escape=be)
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
                                       start_escape=ae, end_escape=be)
            if ops is None:
                n_ref += 1
                continue
            for op in ops:
                if op[0] == "via":
                    _, at, dr_, di_ = op
                    v = pcbnew.PCB_VIA(board)
                    v.SetPosition(at)
                    v.SetDrill(_nm(dr_))
                    v.SetWidth(_nm(di_))
                    v.SetNetCode(nc_)
                    board.Add(v)
                else:
                    _, ls_, le_, w_, lay_ = op
                    tr = pcbnew.PCB_TRACK(board)
                    tr.SetStart(ls_)
                    tr.SetEnd(le_)
                    tr.SetWidth(w_)
                    tr.SetLayer(lay_)
                    tr.SetNetCode(nc_)
                    board.Add(tr)
                    n_legs += 1
            n_closed += 1
            root[_find(j)] = _find(i)
    return {"closed": n_closed, "legs": n_legs, "refused": n_ref,
            "far": n_far, "cross_layer": n_cross}


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
        board.Add(via)
        added.append(via)
        existing.append((x, y, dia))
    if skipped_pad:
        print(f"[cec_fr] add_overunder_vias: {skipped_pad} via(s) REFUSED "
              "in-pad (assembly-class exclusion, owner ruling 2026-07-25 -- "
              "upstream should have reseated)", file=sys.stderr)
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
                    drill_nm=None, net_code=None):
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
                if item.GetEffectiveShape().Collide(circ, clearance_nm):
                    return False
            except Exception:                           # noqa: BLE001
                continue
    probe = pcbnew.VECTOR2I(at.x + 10000, at.y)
    for lid in board.GetEnabledLayers().CuStack():
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


def _layer_foreign_shapes(board, layer_id, sense_codes):
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

    def _append(rows, shape):
        try:
            box = shape.BBox()
        except Exception:                              # noqa: BLE001
            box = None
        rows.append((shape, box))

    for zone in board.Zones():
        if zone.GetIsRuleArea() or zone.GetNetCode() in sense_codes:
            continue
        if not (zone.GetZoneName() or "").startswith(PIPELINE_POUR_PREFIXES):
            continue
        if layer_id not in zone.GetLayerSet().CuStack():
            continue
        try:
            _append(zones, zone.Outline())
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
                _append(copper, pad.GetEffectiveShape(layer_id))
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
            _append(copper, track.GetEffectiveShape(layer_id))
        except Exception:                              # noqa: BLE001
            continue
    return zones, copper


def _bucket_foreign_shapes(rows, *, cell_nm=None, max_cells=4096):
    """Build a conservative uniform-grid index over cached KiCad shapes."""
    from collections import defaultdict

    cell = int(cell_nm or _nm(2.0))
    buckets = defaultdict(list)
    global_rows = []
    for index, (_shape, box) in enumerate(rows):
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


def _tap_leg_collider(board, S, T, width_nm, layer_id, clr_nm, sense_codes, own_code):
    """NAME the first item that blocks leg S->T (the refuse-loud half of canonical-or-
    refuse): the same Collide() geometry as _tap_foreign_clear/_tap_pair_overlap_clear,
    but returning WHAT collided ("pad U12.7 [GND]" / "track [/THRESH]" / "sense pad
    RS3.1 [/SENSE3V3_HI]") so a refusal reports the blocking item the pour/placement
    rung must fix. Cold path -- runs only when a leg is already known refused."""
    seg = pcbnew.SHAPE_SEGMENT(S, T, width_nm)
    near_nm = _nm(0.02)
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for p in fp.Pads():
            nc = p.GetNetCode()
            if layer_id not in p.GetLayerSet().CuStack():
                continue
            try:
                if nc in sense_codes:
                    if nc != own_code and p.GetEffectiveShape(layer_id).Collide(seg, near_nm):
                        return "sense pad %s.%s [%s]" % (ref, p.GetPadName(), p.GetNetname())
                elif p.GetEffectiveShape(layer_id).Collide(seg, clr_nm):
                    return "pad %s.%s [%s]" % (ref, p.GetPadName(), p.GetNetname())
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
            if t.GetEffectiveShape(layer_id).Collide(seg, clr_nm):
                kind = "via" if t.Type() == pcbnew.PCB_VIA_T else "track"
                return "%s [%s]" % (kind, t.GetNetname())
        except Exception:                           # noqa: BLE001
            continue
    return None


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
    laid, report, refused, covered = [], {}, {}, {}
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
                if locked_mode:
                    # CANONICAL-OR-REFUSE (owner ruling 2026-07-25): on a pair with
                    # locked copper (stamped cell / rails / precision) the diagonal
                    # and dogleg fallbacks are REMOVED -- refuse LOUDLY, naming the
                    # blocking item so the pour/placement rung fixes the real
                    # conflict instead of this pass papering over it with bent
                    # copper on the owner's shunt-zoom renders.
                    if canon is None:
                        why = ("no canonical geometry (IC not inward of the shunt "
                               "pad's inner edge)")
                    else:
                        why = None
                        for a, b in zip(canon, canon[1:]):
                            if a == b:
                                continue
                            why = _tap_leg_collider(board, a, b, _nm(width), lay_id,
                                                    clr_nm, sense_codes, nc)
                            if why:
                                break
                        why = why or "canonical leg blocked (collider unresolved)"
                    refused.setdefault(net, []).append(
                        lbl + " CANONICAL-REFUSED: " + why)
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
            "by_net": report, "refused": refused, "covered": covered,
            "segments": len(laid)}


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
    """Remove a temp board and every project sidecar created beside it."""
    base = path[:-len(".kicad_pcb")] if path.endswith(".kicad_pcb") else path
    for p in (path, base + ".kicad_pro", base + ".kicad_dru", base + ".kicad_prl"):
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
    """Copy ``.kicad_pro``/``.kicad_dru`` with a renamed board and rebind it."""
    src_base = src_board[:-len(".kicad_pcb")] if src_board.endswith(".kicad_pcb") else src_board
    dst_base = dst_board[:-len(".kicad_pcb")] if dst_board.endswith(".kicad_pcb") else dst_board
    copied = []
    for ext in (".kicad_pro", ".kicad_dru"):
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


def normalize_netclass_geometry(board, board_path, *, tol_mm=0.001):
    """Raise imported tracks/vias to their assigned netclass geometry.

    Freerouting's SES may ignore or round class-specific widths and via sizes.
    Every undersized ordinary feature is raised to the contract; oversized
    copper is retained.  The one physical exception is a bounded pin neck-down
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
    high-current-pour gates own that topology.
    """
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
    for item in original_items:
        if item.GetClass() != "PCB_TRACK":
            continue
        net = item.GetNetname() or ""
        spec = resolve(net)
        target = float((spec.get("diff_pair_width") if is_pair_net(net) else None)
                       or spec.get("track_width") or 0)
        current = item.GetWidth() / MM
        if net in direct_sense or target <= 0:
            continue
        s, e = item.GetStart(), item.GetEnd()
        length = item.GetLength() / MM
        if length <= 1e-9:
            continue
        row = {
            "item": item, "uuid": item.m_Uuid.AsString(), "net": net,
            "layer": item.GetLayer(), "start": (s.x, s.y), "end": (e.x, e.y),
            "length": length, "current": current, "target": target,
            "undersized": current < target - tol_mm,
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
                    allowed = [row["current"]]
                    if at_a and budget_a[1] is not None:
                        allowed.append(budget_a[1])
                    if at_b and budget_b[1] is not None:
                        allowed.append(budget_b[1])
                    width = min(allowed)
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
    for item in original_items:
        net = item.GetNetname() or ""
        spec = resolve(net)
        if item.GetClass() == "PCB_TRACK":
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
            "legal_neckdown_uuids": sorted(handled),
            "sense_exempt_nets": sorted(direct_sense)}


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
            lays = tuple(board.GetLayerName(lid)
                         for lid in t.GetLayerSet().CuStack())
        else:
            lays = (board.GetLayerName(t.GetLayer()),)
        for ly in lays:
            per_layer.setdefault(ly, []).append(list(box))

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
    locked_pts, locked_boxes = {}, {}
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
        for ly in lays:
            locked_boxes.setdefault(n, {}).setdefault(ly, []).append(box)
        if t.Type() == pcbnew.PCB_VIA_T:
            p_ = t.GetPosition()
            locked_pts.setdefault(n, []).append((p_.x, p_.y))
        else:
            s_, e_ = t.GetStart(), t.GetEnd()
            locked_pts.setdefault(n, []).extend([(s_.x, s_.y), (e_.x, e_.y)])
    if not locked_boxes:
        return []
    win = int(window_mm * 1e6)
    windows = {}                                 # net -> [window rects around uncovered pads]
    for fp in board.GetFootprints():
        for pd in fp.Pads():
            n = pd.GetNetname() or ""
            if n not in locked_boxes:
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
    for n in sorted(locked_boxes):
        for ly, boxes in sorted(locked_boxes[n].items()):
            for wrect in windows.get(n, ()):
                boxes = [rb for b in boxes for rb in _box_minus_window(b, wrect)]
            for k, (x0, y0, x1, y1) in enumerate(_merge_tight_boxes(boxes)):
                out.append({"name": "lockedcu-part-%s-%d" % (ly.replace(".", ""), len(out)),
                            "x0": x0 / 1e6, "y0": y0 / 1e6,
                            "x1": x1 / 1e6, "y1": y1 / 1e6, "layers": (ly,)})
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
            _pf_pours = list(_pf.get("pours") or ())
            _pf_vias = list(_pf.get("vias") or ())
            _pf_nets = ({d.get("net") for d in _pf_pours}
                        | set((_pf.get("report") or {}).keys()))
            _n_pre = len(power_pours)
            power_pours = [p for p in power_pours
                           if p.get("net") not in _pf_nets]
            print(f"[cec_fr] pour-first: {len(_pf_pours)} frozen dict(s) for "
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
            power_pours, _pb = synthesize_pour_bonds(board, power_pours)
            if _pb["planned"] or _pb["dropped"] or _pb.get("scrap"):
                print(f"[cec_fr] pour bonds: {_pb['planned']} bond via(s) planted, "
                      f"{_pb['dropped']} unbondable + {_pb.get('scrap', 0)} lace-bound "
                      f"pour(s) dropped ({_pb['bonded']} kept by contact/barrel)",
                      file=sys.stderr)
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
            netclass_resolver=_project_netclass_resolver(board_path))
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
