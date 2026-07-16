#!/usr/bin/env python3
"""cec_sch_mcp -- MCP server for the schematic layout-quality toolkit.

Owner-approved 2026-07-04: every verb the readability passes ran through
Bash glue becomes a typed MCP tool, with the safety rail BAKED IN: every
MUTATING tool exports the netlist before and after, compares name-aware
connectivity groups, and on ANY delta restores the original file bytes and
returns the failure -- a caller can never receive a schematic whose
connectivity it silently changed. (The rail earned its place live: two of
the mutators' first implementations broke nets in exactly the ways the
gate catches; see cec_sch_layout's guard comments.)

Run:      python3 scripts/cec_sch_mcp.py          (stdio transport)
Register: .mcp.json  ->  "cec-schematic"
Provision: pip install --ignore-installed PyJWT mcp   (ephemeral envs;
           setup-kicad-cli.sh carries this)
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import cec_sch_layout as L          # noqa: E402
import cec_sch_gates as GATES       # noqa: E402  round-4 checker/mutator toolkit
from mcp.server.fastmcp import FastMCP   # noqa: E402

mcp = FastMCP("cec-schematic")


# ---------------------------------------------------------------------- gate
def _netlist_groups(sch_path):
    """{frozenset((ref,pin),...): net_name} via kicad-cli; None on failure."""
    with tempfile.NamedTemporaryFile(suffix=".net", delete=False) as f:
        out = f.name
    try:
        r = subprocess.run(["kicad-cli", "sch", "export", "netlist",
                            "-o", out, sch_path],
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.getsize(out):
            return None
        txt = open(out).read()
        groups = {}
        for m in re.finditer(r'\(net\s+\(code', txt):
            d, i = 0, m.start()
            while True:
                c = txt[i]
                if c == '(':
                    d += 1
                elif c == ')':
                    d -= 1
                    if d == 0:
                        break
                i += 1
            blk = txt[m.start():i + 1]
            nm = re.search(r'\(name "([^"]*)"\)', blk)
            mem = frozenset(re.findall(
                r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', blk))
            if mem:
                groups[mem] = nm.group(1) if nm else "?"
        return groups
    finally:
        os.unlink(out)


def _gated(sch, fn):
    """Run mutator fn() on sch with the identity gate + byte rollback."""
    before_bytes = open(sch, "rb").read()
    before = _netlist_groups(sch)
    if before is None:
        return {"ok": False, "error": "baseline netlist export failed"}
    result = fn()
    after = _netlist_groups(sch)
    missing = extra = renamed = -1
    if after is not None:
        missing = len(set(before) - set(after))
        extra = len(set(after) - set(before))
        renamed = sum(1 for k in set(before) & set(after)
                      if before[k] != after[k])
    if after is None or missing or extra or renamed:
        open(sch, "wb").write(before_bytes)
        return {"ok": False, "rolled_back": True,
                "error": f"netlist identity broke (missing={missing} "
                         f"extra={extra} renamed={renamed}) -- file restored",
                "op_result": result}
    return {"ok": True, "op_result": result,
            "identity": f"{len(before)} groups, exact"}


# --------------------------------------------------------------------- tools
@mcp.tool()
def check_overlaps(sch_path: str) -> dict:
    """Text-vs-text collisions (fields, labels, free text, pin glyphs).
    The zero-overlap gate of the composition standard."""
    pairs = L.detect_overlaps(sch_path)
    return {"count": len(pairs),
            "pairs": [str(p)[:160] for p in pairs[:40]]}


@mcp.tool()
def check_wires(sch_path: str) -> dict:
    """Text-on-wire, text-on-power-glyph, MISROT and GLYPH-CLIP findings
    (the classes text-vs-text cannot see)."""
    f = L.check_wire_collisions(sch_path) + L.check_power_glyphs(sch_path)
    return {"count": len(f), "findings": f[:40]}


@mcp.tool()
def adjacency_scan(sch_path: str, max_dist: float = 10.0) -> dict:
    """Orphaned Value fields (further than max_dist mm from their part) --
    the value-under-reference convention's metric."""
    text = open(sch_path).read()
    work = L._strip_lib_symbols(text)
    orphans = []
    for s, e, (ox, oy), ref, rot, lib, mir in L._symbol_spans(work):
        if ref.startswith("#"):
            continue
        vm = re.search(r'\(property\s+"Value"\s+"((?:[^"\\]|\\.)*)"\s*\n?\s*'
                       r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)', text[s:e])
        if not vm:
            continue
        import math
        d = math.hypot(float(vm.group(2)) - ox, float(vm.group(3)) - oy)
        if d > max_dist:
            orphans.append({"ref": ref, "value": vm.group(1)[:24],
                            "dist_mm": round(d, 1)})
    return {"count": len(orphans), "orphans": orphans[:40]}


@mcp.tool()
def snap_values(sch_path: str) -> dict:
    """MUTATES (identity-gated, auto-rollback): snap orphaned Value fields
    to directly under their Reference."""
    return _gated(sch_path, lambda: L.snap_orphan_values(sch_path))


@mcp.tool()
def spread_flags(sch_path: str, max_steps: int = 4) -> dict:
    """MUTATES (identity-gated, auto-rollback): separate clipping power
    glyphs and flags penetrating label text (connectivity-guarded moves)."""
    return _gated(sch_path,
                  lambda: L.spread_power_flags(sch_path, max_steps=max_steps))


@mcp.tool()
def dedupe_flags(sch_path: str) -> dict:
    """MUTATES (identity-gated, auto-rollback): delete redundant same-value
    power flags WITHIN one wire island (union-find guarded)."""
    return _gated(sch_path, lambda: L.dedupe_power_flags(sch_path))


@mcp.tool()
def rotate_flag(sch_path: str, ref: str) -> dict:
    """MUTATES (identity-gated, auto-rollback): rotate power-flag/global-
    power symbol `ref` 180 degrees in place (rotation only, origin fixed) --
    the MISROT fix paired with the directional finding in check_wires."""
    return _gated(sch_path, lambda: L.rotate_flag_180(sch_path, ref))


@mcp.tool()
def retrofit_decoupler(sch_path: str, ic_ref: str, ic_pin: str,
                       cap_ref: str) -> dict:
    """MUTATES (identity-gated, auto-rollback): relocate an existing
    decoupler `cap_ref` next to owner IC `ic_ref`'s `ic_pin`, keeping its
    private +3V3/GND flags wired (rigid translation), and draw one new real
    wire from the IC pin to the cap -- the wired-adjacency ownership
    convention. Sweeps outward for a collision-free spot using the real
    overlap/wire checkers as ground truth; returns op_result=False (no
    rollback needed -- file untouched) if no safe spot is found within
    range, which the caller should treat as "needs a hand/GUI pass"."""
    return _gated(sch_path, lambda: L.retrofit_decoupler_adjacency(
        sch_path, ic_ref, ic_pin, cap_ref))


@mcp.tool()
def flip_labels(sch_path: str) -> dict:
    """MUTATES (identity-gated, auto-rollback): flip label justify off
    foreign wires (anchors never move)."""
    return _gated(sch_path, lambda: L.flip_label_collisions(sch_path))


@mcp.tool()
def nudge(sch_path: str, max_push: int = 24) -> dict:
    """MUTATES (identity-gated, auto-rollback): resolve field-text
    collisions; wires, glyphs and pin glyphs are obstacles."""
    return _gated(sch_path, lambda: L.nudge_texts(sch_path,
                                                  max_push=max_push))


@mcp.tool()
def readability_pipeline(sch_path: str, iterations: int = 2) -> dict:
    """MUTATES (identity-gated per stage, auto-rollback): the full sweep --
    dedupe -> spread -> snap -> flip -> nudge, iterated; returns per-stage
    counts and the final gate numbers."""
    log = []
    for it in range(iterations):
        for name, fn in (("dedupe", lambda: L.dedupe_power_flags(sch_path)),
                         ("spread", lambda: L.spread_power_flags(
                             sch_path, max_steps=3)),
                         ("snap", lambda: L.snap_orphan_values(sch_path)),
                         ("flip", lambda: L.flip_label_collisions(sch_path)),
                         ("nudge", lambda: L.nudge_texts(sch_path,
                                                         max_push=24))):
            r = _gated(sch_path, fn)
            log.append({"iter": it, "op": name, **r})
            if not r["ok"]:
                return {"ok": False, "log": log}
    return {"ok": True, "log": log,
            "overlaps": len(L.detect_overlaps(sch_path)),
            "wire_findings": len(L.check_wire_collisions(sch_path)
                                 + L.check_power_glyphs(sch_path))}


@mcp.tool()
def render(sch_path: str, out_dir: str, tiles: str = "3x4",
           dsf: float = 3.0) -> dict:
    """Render the schematic to overview + zoomed tile PNGs (the T0
    self-analysis substrate)."""
    r = subprocess.run([sys.executable, os.path.join(HERE,
                        "cec_sch_render.py"), sch_path, "--out", out_dir,
                        "--tiles", tiles, "--dsf", str(dsf)],
                       capture_output=True, text=True)
    files = sorted(os.listdir(out_dir)) if os.path.isdir(out_dir) else []
    return {"ok": r.returncode == 0, "out_dir": out_dir,
            "files": files, "stderr": r.stderr[-400:] if r.returncode else ""}


@mcp.tool()
def verify_identity(sch_path: str, baseline_git_rev: str = "HEAD") -> dict:
    """Compare the working file's netlist connectivity groups against a git
    revision of the same file (name-aware)."""
    rel = os.path.relpath(sch_path)
    r = subprocess.run(["git", "show", f"{baseline_git_rev}:{rel}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return {"ok": False, "error": r.stderr[:200]}
    with tempfile.NamedTemporaryFile("w", suffix=".kicad_sch",
                                     delete=False) as f:
        f.write(r.stdout)
        base = f.name
    try:
        a, b = _netlist_groups(base), _netlist_groups(sch_path)
        if a is None or b is None:
            return {"ok": False, "error": "netlist export failed"}
        renamed = [(a[k], b[k]) for k in set(a) & set(b) if a[k] != b[k]]
        return {"ok": not (set(a) ^ set(b)) and not renamed,
                "groups": f"{len(a)}->{len(b)}",
                "missing": len(set(a) - set(b)),
                "extra": len(set(b) - set(a)),
                "renamed": renamed[:10]}
    finally:
        os.unlink(base)


@mcp.tool()
def check_region_containment(sch_path: str) -> dict:
    """Round-4 G6 checker: dashed 'region' accent frames (round-3 convention)
    vs. every non-power symbol's full extent (body + pin reach). Findings:
    CONTAINMENT (extent not fully inside any region -- sheets with zero
    regions are exempt entirely), STRADDLE (extent crosses a region's own
    boundary), REGION-OVERLAP (two regions overlap each other), REGION-
    OVERRUN (a region extends past the sheet's own paper rectangle)."""
    findings = GATES.check_region_containment(sch_path)
    return {"count": len(findings), "findings": findings[:40]}


@mcp.tool()
def check_sheet_bounds(sch_path: str) -> dict:
    """Round-4 G6 checker: any symbol extent, text/label glyph, or wire
    endpoint that falls outside the sheet's own `(paper ...)` rectangle."""
    findings = GATES.check_sheet_bounds(sch_path)
    return {"count": len(findings), "findings": findings[:40]}


@mcp.tool()
def inventory_diff(baseline_sch: str, new_sch: str) -> dict:
    """Round-4 G2 gate: full symbol-inventory equality (ref -> lib_id/value/
    footprint/dnp/in_bom/on_board/all BOM properties) between two project
    roots, walked recursively through every referenced sheet -- catches a
    dropped DNP part or a silently-changed property that a netlist diff
    alone cannot see (DNP'd parts and non-electrical properties carry no net
    membership)."""
    findings = GATES.check_inventory_equal(baseline_sch, new_sch)
    return {"count": len(findings), "findings": findings[:60]}


@mcp.tool()
def prose_preserved(baseline_sch_paths: list, new_sch_paths: list,
                    waivers: list = None) -> dict:
    """Round-4 G8 gate: every engineering-content free `(text ...)` string
    in `baseline_sch_paths` must survive (whitespace-normalized) into
    `new_sch_paths` or be covered by an explicit `waivers` entry."""
    missing = GATES.check_prose_preserved(baseline_sch_paths, new_sch_paths,
                                         waivers or ())
    return {"count": len(missing), "missing": missing[:60]}


@mcp.tool()
def bus_power_ladder(sch_path: str, ref: str, net: str = "GND") -> dict:
    """MUTATES (identity-gated, auto-rollback): collapse every qualifying
    un-bused GND (or other net) ladder on symbol `ref` -- >=3 collinear
    same-net pins, uniform pitch, each currently terminated by its own
    private #PWR/#FLG stamp (cec_sch_layout.power_ladder_runs) -- down to
    ONE kept stamp + a single real chain wire (cec_sch_layout.wire_chain).
    Refuses (file untouched) if the chain's corridor is blocked by a
    foreign body/pin, or if the post-mutation detect_overlaps/
    check_wire_collisions/check_power_glyphs counts would increase; the
    identity gate below additionally requires exact name-aware netlist
    connectivity before/after."""
    return _gated(sch_path,
                  lambda: GATES.bus_power_ladder(sch_path, ref, net))


if __name__ == "__main__":
    mcp.run()
