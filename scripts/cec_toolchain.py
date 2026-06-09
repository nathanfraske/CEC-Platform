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
        _cli_cache = shutil.which("kicad-cli")
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


_warned = set()


def warn_once(key, msg=None):
    """Emit a stderr warning at most once per key (per process)."""
    if key in _warned:
        return
    _warned.add(key)
    print(f"[cec] WARNING: {msg or key}", file=sys.stderr)
