#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_toolchain -- external-tool presence helpers, DEPENDENCY-FREE.
# ============================================================================
# Deliberately imports nothing heavy (no pcbnew, no cec_score), so it stays
# importable on a host WITHOUT the KiCad python bindings or the kicad-cli
# binary -- the exact "KiCad-less box" case that punchlist R-05
# (docs/agentic-pipeline-review-2026-06-09.md) is about. cec_score itself
# does `import pcbnew` at module top, so it is NOT importable on such a box;
# the R-05 helper therefore cannot live there as the punchlist first suggested.
#
# Two call-site policies (R-05 recommended fix):
#   * require_kicad_cli(action) -- FAIL FAST with the route-prereqs install
#     hint. For stages that cannot mean anything without the tool: DRC, ERC,
#     netlist-for-scoring. A clear one-line error, never a FileNotFoundError
#     traceback.
#   * have_kicad_cli() + warn_once(...) -- DEGRADE to reduced output. For the
#     render helpers and the cascade's netlist export, so the non-routing
#     stages still run on a toolless box (the cec_synth_pipeline header promise).
# ============================================================================
import glob
import os
import shutil
import sys

KICAD_CLI_HINT = (
    "kicad-cli not found on PATH -- install KiCad 10 (it provides kicad-cli) and put it on "
    "PATH; run scripts/route-prereqs.sh for the full prerequisite check"
)

_UNSET = object()
_cli_cache = _UNSET


def kicad_cli():
    """Path to kicad-cli, or None. Resolved once and cached."""
    global _cli_cache
    if _cli_cache is _UNSET:
        override = os.environ.get("CEC_KICAD_CLI")
        if override:
            _cli_cache = override if os.path.isfile(override) else None
        else:
            _cli_cache = shutil.which("kicad-cli")
        if _cli_cache is None and os.name == "nt":
            roots = [os.environ.get("ProgramFiles"),
                     os.environ.get("ProgramFiles(x86)")]
            candidates = []
            for root in (r for r in roots if r):
                candidates.extend(glob.glob(
                    os.path.join(root, "KiCad", "*", "bin", "kicad-cli.exe")))
            if candidates:
                _cli_cache = sorted(candidates, reverse=True)[0]
    return _cli_cache


def have_kicad_cli():
    return kicad_cli() is not None


def require_kicad_cli(action="this operation"):
    """Return the kicad-cli path, or raise RuntimeError with the install hint.

    Use where the tool is mandatory (DRC / ERC / netlist-for-scoring): a clean,
    actionable error instead of a FileNotFoundError deep in a subprocess call.
    """
    p = kicad_cli()
    if p is None:
        raise RuntimeError(f"{action} requires kicad-cli. {KICAD_CLI_HINT}")
    return p


def sha256_file(path, chunk=1 << 20):
    """Content hash of a file (hex). Used for candidate-board dedupe (punchlist R-01:
    Freerouting is deterministic, so identical params yield byte-identical candidates;
    scoring is the expensive step, so dedupe before scoring)."""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


_warned = set()


def warn_once(key, msg=None):
    """Emit a stderr warning at most once per key (per process)."""
    if key in _warned:
        return
    _warned.add(key)
    print(f"[cec] WARNING: {msg or key}", file=sys.stderr)


def find_root_sch(board_dir):
    """The ROOT .kicad_sch of a (possibly HIERARCHICAL) board directory.

    The beta-line boards split into numbered sub-sheets (01-hub-link.kicad_sch, ...), so the
    historical `sorted(glob('*.kicad_sch'))[0]` grabs a LEAF sheet and a netlist export from it
    silently drops most of the board (measured: eps-8pin -> 6 of 63 components). Resolution
    order, all dependency-free:
      1. the .kicad_sch whose stem matches a .kicad_pro stem (KiCad's own root convention);
      2. the .kicad_sch that INSTANTIATES sub-sheets (contains a `(sheet ` block) -- a root
         references children, a leaf does not;
      3. the .kicad_sch whose name contains the directory's name (repo naming convention);
      4. alphabetically first (the historical fallback).
    Returns "" when the directory has no schematic."""
    import glob as _glob
    import os as _os
    cands = sorted(_glob.glob(_os.path.join(board_dir, "*.kicad_sch")))
    if not cands:
        return ""
    if len(cands) == 1:
        return cands[0]
    pro_stems = {_os.path.splitext(_os.path.basename(p))[0]
                 for p in _glob.glob(_os.path.join(board_dir, "*.kicad_pro"))}
    by_pro = [p for p in cands
              if _os.path.splitext(_os.path.basename(p))[0] in pro_stems]
    if by_pro:
        return by_pro[0]
    import re as _re
    roots = []
    for p in cands:
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                if _re.search(r"^\s*\(sheet\b", fh.read(), _re.M):
                    roots.append(p)
        except OSError:
            continue
    if len(roots) == 1:
        return roots[0]
    base = _os.path.basename(_os.path.normpath(board_dir)).replace("-", "")
    by_name = [p for p in (roots or cands)
               if base in _os.path.basename(p).replace("-", "")]
    if by_name:
        return by_name[0]
    return (roots or cands)[0]
