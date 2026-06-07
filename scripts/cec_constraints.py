#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_constraints -- the CEC platform DESIGN-CONSTRAINT REGISTRY + checkers
#                     + the directive consumer (violation -> placement directive).
# ============================================================================
# The single source of truth for "project structure" rules a constraint-aware
# placer/router must keep -- what the connectivity placer was blind to.
#
#   * REGISTRY  -- curated, ratifiable canonical constraints (id, severity,
#                  checkability, the placement DIRECTIVE to emit on violation,
#                  source, status[ratified|proposed], params). Curated from the
#                  269-row extraction in scripts/constraints/corpus-extracted.json.
#   * CHECKERS  -- deterministic checks (pcbnew geometry / net topology / DRC),
#                  self-gating (return None = N/A when the relevant parts are
#                  absent). The "discover -> ratify -> enforce" migration:
#                  what an LLM/human spots becomes a deterministic checker here.
#   * directives(rows) -- turns FAILs into TYPED placement directives an
#                  auto-placer consumes (pin/adjacent/region/keepout/separate/align).
#
#   python3 scripts/cec_constraints.py <board.kicad_pcb> [...] [--radio] [--json]
# ============================================================================
import os, re, sys, json, math, collections, subprocess, tempfile
from dataclasses import dataclass, field, asdict

import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cec_dispatch   # noqa: E402  -- _drc_types, _locus_is_finishing, _bracket_nets
import cec_score      # noqa: E402  -- _derive_pairs (Kelvin _HI/_LO, diff _P/_N)


# ===========================================================================
#  Registry
# ===========================================================================
@dataclass
class Constraint:
    id: str
    title: str
    category: str
    severity: str               # hard | strong | soft | advisory
    checkable: str              # yes | partial | no
    directive: str              # pin | adjacent | region | keepout | separate | align | none
    rule: str
    source: str
    status: str = "proposed"    # ratified | proposed
    params: dict = field(default_factory=dict)
    checker: str = ""           # registered checker id (defaults to .id)


def C(**kw):
    return Constraint(**kw)


REGISTRY = [
    # ---- high-current / shunt / Kelvin -------------------------------------------------
    C(id="kelvin-sense-fcu-no-via", title="Kelvin sense pair stays on F.Cu, no vias",
      category="high-current", severity="hard", checkable="yes", directive="none",
      rule="The Kelvin sense pair (*_HI/*_LO) stays short and local on the TOP layer (F.Cu) with ZERO "
           "vias -- never routed to a signal layer and back (that folds via inductance into the sense).",
      source="spec §6.8 (LOCKED, verbatim)", status="ratified"),
    C(id="kelvin-sense-adjacent-shunt", title="Sense IC within 5mm of its shunt",
      category="high-current", severity="hard", checkable="yes", directive="adjacent",
      rule="The current-sense IC (INA228/238/181) sits within max_mm of its shunt (short Kelvin loop). "
           "Threshold calibrated to the as-built boards (ratified 5mm).",
      source="spec §6.8 + as-built calibration", status="ratified", params={"max_mm": 5.0}),
    C(id="shunt-inline-in-corridor", title="Shunt sits inline in the J_IN->J_OUT current path",
      category="high-current", severity="strong", checkable="partial", directive="region",
      rule="Each cable/pin shunt lies between its input and output connector pads, so current flows "
           "through it with no bypass.", source="spec §6.7; user-named", status="ratified"),
    C(id="high-current-corridor-keepout", title="High-current corridor clear of foreign signals",
      category="high-current", severity="strong", checkable="partial", directive="keepout",
      rule="The J_IN->shunt->J_OUT corridor carries no foreign-net via/track (reserved for the pour).",
      source="CLAUDE.md considerations", status="ratified"),
    C(id="high-current-pour-present", title="High-current nets carried by a filled pour",
      category="high-current", severity="strong", checkable="yes", directive="keepout",
      rule="High-current nets (12V/*_HI) carried by a filled pour of adequate area (route-time step).",
      source="CLAUDE.md route-to-clean; user-named", status="ratified", params={"min_area_mm2": 20.0}),
    C(id="shunt-values-per-table", title="Shunt values per the §6.4 table",
      category="high-current", severity="hard", checkable="partial", directive="none",
      rule="EPS/PCIe per-cable 0.5mOhm; 12VHPWR per-pin 1mOhm; 24-pin 2mOhm rails / 25mOhm 5VSB.",
      source="spec §6.4 (LOCKED)", status="ratified"),
    C(id="high-current-stackup-2oz", title="4-layer, 2oz outer, 12V on outers",
      category="high-current", severity="hard", checkable="no", directive="none",
      rule="High-current modules: 4-layer, 2oz outer copper, 12V on outers, GND on inners.",
      source="spec §6.7", status="ratified"),

    # ---- thermal -----------------------------------------------------------------------
    C(id="hot-sensitive-separation", title="Hot parts separated from temp-sensitive parts",
      category="thermal", severity="strong", checkable="yes", directive="separate",
      rule="Hot parts (shunts, high-current connectors, LDO) kept >= sep_mm from temp-sensitive parts "
           "(ambient NTC, the reference, the ESP).", source="spec §6.6", status="proposed",
      params={"sep_mm": 8.0}),
    C(id="ntc-board-temp-by-shunt", title="Board-temp NTC adjacent to the shunt row",
      category="thermal", severity="strong", checkable="yes", directive="adjacent",
      rule="The board-temp NTC sits within max_mm of a shunt; the ambient NTC sits away from heat.",
      source="spec §6.6; as-built", status="proposed", params={"max_mm": 5.0}),

    # ---- EMC / RF / SI -----------------------------------------------------------------
    C(id="esp-antenna-keepout", title="ESP PCB-antenna keepout clear (if radio populated)",
      category="EMC/RF", severity="hard", checkable="partial", directive="keepout",
      rule="If the on-board radio is used, the ESP antenna keepout carries no copper/vias/parts. "
           "Wired-only board -> keepout DROPPABLE (area win).",
      source="ESP datasheet; CLAUDE.md respect_antenna_keepout; user-named", status="ratified",
      params={"gated_on": "radio"}),
    C(id="usb-diffpair-routed-coupled", title="USB D+/D- routed, 0 unconnected (hard gate)",
      category="EMC/RF", severity="hard", checkable="yes", directive="adjacent",
      rule="USB_D_P/_N both routed with 0 unconnected ratlines.", source="spec §3; cec_score",
      status="ratified", checker="diffpair-gate"),
    C(id="diffpair-pn-naming", title="Diff pairs use the _P/_N suffix convention",
      category="EMC/RF", severity="strong", checkable="yes", directive="none",
      rule="Differential pairs use the _P/_N suffix (e.g. /USB_D_P, /USB_D_N) so KiCad's diff-pair "
           "router auto-recognizes them -- NOT /USB_DP //USB_DM.",
      source="repo convention; CLAUDE.md (EPS renamed, PCIe pending)", status="ratified"),
    C(id="can-coupled-no-module-term", title="CAN coupled; 120R split termination at Hub only",
      category="EMC/RF", severity="hard", checkable="partial", directive="none",
      rule="CAN_H/CAN_L coupled; split 120R termination only at the Hub, never a module.",
      source="spec §3.1 (LOCKED)", status="ratified"),

    # ---- connectors / mechanical -------------------------------------------------------
    C(id="rj45-link-pinmap", title="RJ-45 link; pins per the locked allocation",
      category="connectors", severity="hard", checkable="yes", directive="none",
      rule="Module<->Hub link is RJ-45 (never Mini-Fit Jr); pin1 VCC, pin2 GND, pin3 CAN_H, pin6 "
           "CAN_L, pin7 reserved (NOT AUX_REF), pin8 DETECT.", source="spec §2.1/§2.2 (LOCKED)",
      status="ratified"),
    C(id="connector-mouth-faces-edge", title="Connector mouth faces the nearest board edge",
      category="connectors", severity="hard", checkable="partial", directive="pin",
      rule="Each cable/power connector opens toward (and overhangs) the nearest board edge.",
      source="user-named (rotation); as-built", status="ratified", params={"edge_mm": 6.0}),
    C(id="connector-overhang-bounded", title="Connector overhang bounded (all pads on-board)",
      category="connectors", severity="strong", checkable="yes", directive="region",
      rule="A connector may overhang an edge, but ALL its pads stay on-board AND the body overhang "
           "does not exceed the part's shroud depth.", source="user-named (overhang amount)",
      status="ratified"),
    C(id="mount-holes-present-clear", title="M3 mounts present, GND-tied, clear of connectors",
      category="connectors", severity="hard", checkable="yes", directive="pin",
      rule="The board carries its M3 mounts (chassis-grounded), clear of connector courtyards.",
      source="user-named; as-built", status="ratified", params={"min_count": 3, "clear_mm": 2.0}),
    C(id="detect-esd-diode-pin8", title="DETECT pin-8 ESD diode present (PESD SOD-323)",
      category="connectors", severity="hard", checkable="yes", directive="adjacent",
      rule="A low-cap ESD diode (PESD5V0S1BA, SOD-323) clamps the DETECT line on every Hub/module.",
      source="spec §2.4 (LOCKED v2.0)", status="ratified"),

    # ---- placement / passives ----------------------------------------------------------
    C(id="decoupling-cap-owner", title="Decoupling cap at its owner IC power pad",
      category="placement", severity="strong", checkable="yes", directive="adjacent",
      rule="Each decoupling cap sits within max_mm of an IC pad on the same power net.",
      source="cec_pcb verify_passives", status="ratified", params={"max_mm": 3.5}),
    C(id="trace-width-high-current", title="No too-thin trace on a high-current net",
      category="placement", severity="strong", checkable="yes", directive="none",
      rule="No track on a 12V/*_HI net is thinner than min_mm unless the net is carried by a pour.",
      source="user-named (trace widths); .kicad_dru", status="ratified", params={"min_mm": 1.0}),
    C(id="ina-lane-symmetry-12vhpwr", title="12VHPWR 6 INA lanes equal-pitch",
      category="placement", severity="strong", checkable="partial", directive="align",
      rule="The six INA240 per-pin lanes are equal pitch, each its own column, symmetric.",
      source="CLAUDE.md considerations; as-built", status="ratified", params={"pitch_tol_mm": 0.5}),

    # ---- finishing / decorative --------------------------------------------------------
    C(id="logo-bcu-keepout", title="Decorative LOGO copper must not cross functional nets",
      category="finishing", severity="hard", checkable="yes", directive="keepout",
      rule="The decorative B.Cu LOGO polygon is a routing keepout (or GND-assigned): no functional-net "
           "copper may short to it. (LOGO-vs-GND only is finishing-acceptable.)",
      source="discovered by the route loop 2026-06-07; verified", status="ratified"),
    C(id="footprint-matches-datasheet", title="Footprint land matches the MPN datasheet",
      category="finishing", severity="hard", checkable="partial", directive="none",
      rule="Each footprint's pad pitch/drill/size/row matches the part datasheet land. Unverified MPNs "
           "are flagged, not passed.", source="user-named; CLAUDE.md Molex 45586 fix", status="ratified"),
    C(id="fiducials-present", title="Fiducials present (3x)",
      category="finishing", severity="strong", checkable="yes", directive="none",
      rule="Three fiducials (board-only, excl-BOM).", source="as-built", status="proposed",
      params={"min_count": 3}),

    # ---- schematic / BOM conformance ---------------------------------------------------
    C(id="detect-resistor-code", title="DETECT code resistor per §2.3",
      category="conformance", severity="hard", checkable="yes", directive="none",
      rule="DETECT resistor encodes link capability on the 10k/3.3V divider: CAN-only 2.2k, "
           "CAN+RS-485 4.7k.", source="spec §2.3 (LOCKED, OQ-6)", status="ratified",
      params={"expect_k": 2.2}),
    C(id="can-transceiver-tja1051t3", title="CAN transceiver is TJA1051T/3",
      category="conformance", severity="hard", checkable="yes", directive="none",
      rule="Every board carrying the transceiver uses TJA1051T/3 (classical CAN).",
      source="spec §3.1 (LOCKED v3.5)", status="ratified"),
]


# ===========================================================================
#  Checker framework
# ===========================================================================
CHECKERS = {}


def checker(cid):
    def deco(fn):
        CHECKERS[cid] = fn
        return fn
    return deco


# -- geometry / topology helpers ---------------------------------------------
def _mm(v):
    return v / 1e6


def _pads_by_net(board):
    d = collections.defaultdict(list)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            d[pad.GetNetname()].append((fp.GetReference(), pad, fp))
    return d


def _fps(board):
    return list(board.GetFootprints())


def _min_pad_dist_mm(fpA, fpB):
    best = 1e9
    for pa in fpA.Pads():
        a = pa.GetPosition()
        for pb in fpB.Pads():
            b = pb.GetPosition()
            best = min(best, math.hypot(_mm(a.x - b.x), _mm(a.y - b.y)))
    return best


def _track_count(board):
    return sum(1 for t in board.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T)


def _edge_bbox(board):
    bb = board.GetBoardEdgesBoundingBox()
    return _mm(bb.GetLeft()), _mm(bb.GetTop()), _mm(bb.GetRight()), _mm(bb.GetBottom())


def _val(fp):
    return (fp.GetValue() or "").strip()


def _is(fp, *subs):
    """ref/value/fpid contains any of subs (case-insensitive)."""
    s = (fp.GetReference() + " " + _val(fp) + " " + fp.GetFPIDAsString()).upper()
    return any(x.upper() in s for x in subs)


def _nets(board):
    return [n.GetNetname() for n in board.GetNetInfo().NetsByNetcode().values() if n.GetNetname()]


def _param(cid, key, default):
    return next((c.params.get(key, default) for c in REGISTRY if c.id == cid), default)


def _direct_sense_pairs(board, kelvin):
    """(_HI,_LO,sense_ic) for pairs where a non-resistor IC taps BOTH halves directly
    (INA238/228). On filtered lanes (INA240 behind an RC) the _HI/_LO are FORCE nets and this
    returns [] -> the Kelvin geometry checks N/A out (need a filter-aware scope)."""
    by_net = _pads_by_net(board)
    out = []
    for hi, lo in kelvin:
        hi_refs = {r for r, _, _ in by_net.get(hi, [])}
        lo_refs = {r for r, _, _ in by_net.get(lo, [])}
        ics = [r for r in (hi_refs & lo_refs) if not r.startswith("R")]
        if ics:
            out.append((hi, lo, ics[0]))
    return out


def _sense_nets(board):
    """Nets at the INA current-sense IC INPUT pins -- the real Kelvin sense (direct _HI/_LO on
    INA238/228, or the post-filter IN_P/_N on the filtered INA240 lanes). Power/gnd/ref/output excluded.
    (Calibration from the 12VHPWR swarm review: scope to these, not the force nets. And restrict to the
    analog SENSE-pair suffixes -- an INA238 also has I2C/SCL/SDA/ALERT digital pins that route freely.)"""
    out = set()
    for fp in board.GetFootprints():
        if "INA2" not in _val(fp).upper():
            continue
        for pad in fp.Pads():
            nu = (pad.GetNetname() or "").upper()
            if nu and (nu.endswith("_HI") or nu.endswith("_LO") or nu.endswith("_P") or nu.endswith("_N")):
                out.add(pad.GetNetname())
    return out


def _force_nets(board):
    """Nets carrying high current (poured, or >=1.5mm copper). A shared force+sense net's force leg
    may legitimately run on B.Cu, so off-F.Cu is only a fault on the low-current sense leg."""
    force = set()
    for z in board.Zones():
        try:
            if z.GetFilledArea() > 0:
                force.add(z.GetNetname())
        except Exception:
            force.add(z.GetNetname())
    widest = collections.defaultdict(float)
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_TRACE_T:
            widest[t.GetNetname()] = max(widest[t.GetNetname()], _mm(t.GetWidth()))
    force |= {n for n, w in widest.items() if w >= 1.5}
    return force


# -- checkers ----------------------------------------------------------------
@checker("kelvin-sense-fcu-no-via")
def _chk_kelvin_fcu(board, path, ctx):
    sense = _sense_nets(board)
    if not sense:
        return None, "no INA sense-input nets resolved"
    if _track_count(board) == 0:
        return None, "unrouted floorplan (route-time check)"
    force = _force_nets(board)
    bad = []
    for t in board.GetTracks():
        n = t.GetNetname()
        if n not in sense:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            bad.append("via on %s" % n)                        # §6.8: never route the sense down-and-back
        elif t.Type() == pcbnew.PCB_TRACE_T and t.GetLayer() != pcbnew.F_Cu and n not in force:
            bad.append("%s off F.Cu" % n)                      # off-F.Cu only faults the low-current sense leg
    if bad:
        return (False, "Kelvin sense not top-layer/no-via: " + "; ".join(sorted(set(bad))[:6]),
                [{"type": "keepout", "reserve": "F.Cu-route", "nets": sorted(sense)}])
    return True, "all %d INA sense-input nets clean (F.Cu / no sense via)" % len(sense)


@checker("kelvin-sense-adjacent-shunt")
def _chk_kelvin_adj(board, path, ctx):
    kelvin, _ = cec_score._derive_pairs(_nets(board))
    by_net = _pads_by_net(board)
    max_mm = _param("kelvin-sense-adjacent-shunt", "max_mm", 5.0)
    direct = _direct_sense_pairs(board, kelvin)
    if direct:
        fails, oks, payload = [], [], []
        for hi, lo, ic_ref in direct:
            hi_fps = {r: fp for r, _, fp in by_net.get(hi, [])}
            sh = [r for r in hi_fps if r.startswith("R")]
            if not sh:
                continue
            d = _min_pad_dist_mm(hi_fps[ic_ref], hi_fps[sh[0]])
            (oks if d <= max_mm else fails).append("%s<->%s %.2f" % (ic_ref, sh[0], d))
            if d > max_mm:
                payload.append({"type": "adjacent", "a": ic_ref, "b": sh[0], "max_mm": max_mm, "got_mm": round(d, 2)})
        if fails:
            return False, "Kelvin loop > %.0fmm: %s" % (max_mm, "; ".join(fails)), payload
        if oks:
            return True, "direct-sense ICs <= %.0fmm from shunt: %s" % (max_mm, "; ".join(oks))
    # filtered lanes (INA240 behind an RC): the sense path is the in-column shunt->filter->INA, so the
    # adjacency that matters is the INA being column-aligned with its shunt (calibration from the swarm review).
    inas = [fp for fp in board.GetFootprints() if "INA2" in _val(fp).upper()]
    shunts = [fp for fp in board.GetFootprints() if fp.GetReference().upper().startswith("RS")]
    if not inas or not shunts:
        return None, "no sense IC / shunt pair to check"
    tol, fails = 1.0, []
    for ina in inas:
        ix = _mm(ina.GetPosition().x)
        s = min(shunts, key=lambda sh: abs(_mm(sh.GetPosition().x) - ix))
        dx = abs(_mm(s.GetPosition().x) - ix)
        if dx > tol:
            fails.append("%s<->%s dX=%.2f" % (ina.GetReference(), s.GetReference(), dx))
    if fails:
        return (False, "filtered lane INA not column-aligned with its shunt: " + "; ".join(fails[:6]),
                [{"type": "align", "a": f.split("<")[0], "axis": "X"} for f in fails[:6]])
    return True, "filtered lanes: all %d INA240 column-aligned with their shunt (<=%.1fmm dX)" % (len(inas), tol)


@checker("logo-bcu-keepout")
def _chk_logo(board, path, ctx):
    if _track_count(board) == 0:
        if any(fp.GetReference().upper().startswith("LOGO") for fp in board.GetFootprints()):
            return None, "unrouted: LOGO needs a routing keepout (can't verify short pre-route)"
        return None, "no LOGO footprint"
    _, loci = cec_dispatch._drc_types(path)
    bad = [lc for lc in loci if "LOGO" in lc["where"].upper() and not cec_dispatch._locus_is_finishing(lc)]
    if bad:
        nets = sorted({n for lc in bad for n in cec_dispatch._bracket_nets(lc["where"])
                       if n not in ("<no net>", "no net", "GND", "")})
        logos = sorted({r for lc in bad for r in cec_dispatch._fp_refs(lc["where"]) if r.upper().startswith("LOGO")})
        return (False, "LOGO shorts functional nets: %s (%d hits)" % (", ".join(nets), len(bad)),
                [{"type": "keepout", "target": logos[0] if logos else "LOGO1", "layer": "B.Cu", "nets": nets}])
    return True, "LOGO touches only GND/no-net (finishing-acceptable)"


@checker("high-current-pour-present")
def _chk_pour(board, path, ctx):
    hc = [n for n in _nets(board) if "12V" in n.upper() or n.endswith("_HI")]
    if not hc:
        return None, "no high-current nets"
    if _track_count(board) == 0:
        return None, "floorplan: pours are a route-time step"
    poured = set()
    for z in board.Zones():
        try:
            if z.GetFilledArea() > 0:
                poured.add(z.GetNetname())
        except Exception:
            poured.add(z.GetNetname())
    widest = collections.defaultdict(float)
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_TRACE_T:
            widest[t.GetNetname()] = max(widest[t.GetNetname()], _mm(t.GetWidth()))
    # carried = poured OR routed with adequate-width copper (>=1.5mm wide trace, e.g. 12VHPWR lanes)
    missing = sorted({n for n in hc if n not in poured and widest.get(n, 0.0) < 1.5})
    if missing:
        return (False, "high-current nets not carried by a pour or wide copper: %s" % ", ".join(missing[:6]),
                [{"type": "keepout", "reserve": "pour_or_wide", "nets": missing}])
    return True, "all %d high-current nets carried (pour/wide copper)" % len(set(hc))


@checker("diffpair-gate")
def _chk_diffpair(board, path, ctx):
    m = cec_score.score(path)
    if not m.detail.get("diff_pairs"):
        return None, "no _P/_N diff pairs on this board"
    return m.diffpair_ok, "diffpair_ok=%s" % m.diffpair_ok


@checker("diffpair-pn-naming")
def _chk_pn_naming(board, path, ctx):
    nets = set(_nets(board))
    # USB present? look for any USB data net
    usb = [n for n in nets if "USB_D" in n.upper()]
    if not usb:
        return None, "no USB data nets"
    good = any(n.endswith("_P") or n.endswith("_N") for n in usb)
    bad = [n for n in usb if re.search(r"USB_D[PM]$", n.upper())]
    if bad and not good:
        return (False, "USB diff pair uses DP/DM not _P/_N (router can't auto-recognize): %s" % ", ".join(sorted(bad)),
                [{"type": "rename", "nets": sorted(bad), "to": "_P/_N suffix"}])
    return True, "USB diff pair uses _P/_N convention"


@checker("mount-holes-present-clear")
def _chk_mounts(board, path, ctx):
    want = _param("mount-holes-present-clear", "min_count", 3)
    clear = _param("mount-holes-present-clear", "clear_mm", 2.0)
    mounts = [fp for fp in board.GetFootprints() if _is(fp, "MountingHole", "MOUNT")]
    if len(mounts) < want:
        return (False, "found %d mounts, expect >= %d" % (len(mounts), want),
                [{"type": "add", "what": "mounting_hole", "need": want - len(mounts)}])
    conns = [fp for fp in board.GetFootprints() if fp.GetReference().upper().startswith("J") and list(fp.Pads())]
    near = [(mh.GetReference(), j.GetReference(), _min_pad_dist_mm(mh, j))
            for mh in mounts for j in conns if _min_pad_dist_mm(mh, j) < clear]
    if near:
        return (False, "mount too close to connector: " + "; ".join("%s~%s %.2f" % n for n in near[:4]),
                [{"type": "pin", "target": n[0], "hint": "move clear of %s" % n[1]} for n in near])
    return True, "%d mounts present, clear" % len(mounts)


@checker("fiducials-present")
def _chk_fid(board, path, ctx):
    want = _param("fiducials-present", "min_count", 3)
    fids = [fp for fp in board.GetFootprints() if _is(fp, "Fiducial", "FID")]
    if len(fids) < want:
        return False, "found %d fiducials, expect >= %d" % (len(fids), want)
    return True, "%d fiducials present" % len(fids)


@checker("rj45-link-pinmap")
def _chk_rj45(board, path, ctx):
    rj = [fp for fp in board.GetFootprints() if _is(fp, "RJ45")]
    if not rj:
        return None, "no RJ-45 on this board"
    want = {"1": ("5VSB", "VCC"), "2": ("GND",), "3": ("CAN_H", "CAN1_H"),
            "6": ("CAN_L", "CAN1_L"), "8": ("DETECT",)}
    fp = rj[0]
    padnet = {p.GetPadName(): (p.GetNetname() or "").upper() for p in fp.Pads()}
    wrong = []
    for pin, subs in want.items():
        net = padnet.get(pin, "")
        if net and not any(s in net for s in subs):
            wrong.append("pin%s=%s (want %s)" % (pin, net, "/".join(subs)))
    if wrong:
        return False, "RJ-45 pinmap mismatch: " + "; ".join(wrong)
    return True, "RJ-45 pin map matches the locked allocation"


@checker("detect-resistor-code")
def _chk_detect_r(board, path, ctx):
    by_net = _pads_by_net(board)
    det = [n for n in by_net if "DETECT" in n.upper() and "SENSE" not in n.upper()]
    if not det:
        return None, "no DETECT net"
    expect_k = _param("detect-resistor-code", "expect_k", 2.2)
    rs = {r for n in det for r, _, fp in by_net[n] if r.startswith("R")}
    if not rs:
        return None, "no resistor on DETECT (Hub-side pullup board?)"
    vals = {r: _val(fp) for fp in board.GetFootprints() for r in [fp.GetReference()] if r in rs}
    ok = any(re.search(r"2\.?2\s*k", v, re.I) or "2k2" in v.lower() for v in vals.values())
    if not ok:
        return False, "DETECT resistor not %.1fk (CAN-only): %s" % (expect_k, vals)
    return True, "DETECT code resistor = %.1fk (CAN-only)" % expect_k


@checker("detect-esd-diode-pin8")
def _chk_detect_esd(board, path, ctx):
    by_net = _pads_by_net(board)
    det = [n for n in by_net if "DETECT" in n.upper() and "SENSE" not in n.upper()]
    if not det:
        return None, "no DETECT net"
    ds = [(r, _val(fp)) for n in det for r, _, fp in by_net[n] if r.startswith("D")]
    if not ds:
        return False, "no ESD diode on DETECT pin-8", [{"type": "add", "what": "PESD5V0S1BA", "net": det[0]}]
    pesd = any("PESD" in v.upper() for _, v in ds)
    return (pesd, "DETECT ESD diode: %s%s" % (ds, "" if pesd else " (not a PESD part!)"))


@checker("can-transceiver-tja1051t3")
def _chk_can_xcvr(board, path, ctx):
    xcvr = [fp for fp in board.GetFootprints() if "TJA10" in (_val(fp)).upper()]
    if not xcvr:
        return None, "no CAN transceiver placed on this board"
    bad = [_val(fp) for fp in xcvr if "1051T/3" not in _val(fp) and "1051T3" not in _val(fp).replace("/", "")]
    if bad:
        return False, "transceiver not TJA1051T/3: %s" % bad
    return True, "CAN transceiver = TJA1051T/3"


@checker("shunt-values-per-table")
def _chk_shunt_val(board, path, ctx):
    rs = [(fp.GetReference(), _val(fp)) for fp in board.GetFootprints() if fp.GetReference().upper().startswith("RS")]
    if not rs:
        return None, "no RS* shunts on this board"
    # accept any explicit milliohm-style value; FAIL only obviously-wrong (no mOhm marker)
    bad = [r for r in rs if not re.search(r"(0?\.5|1|2|25)\s*m", r[1], re.I) and "R0" not in r[1].upper()]
    if bad:
        return False, "shunt value not a §6.4 mOhm value: %s" % bad
    return True, "shunt values look like §6.4 mOhm parts: %s" % rs


@checker("decoupling-cap-owner")
def _chk_decap(board, path, ctx):
    max_mm = _param("decoupling-cap-owner", "max_mm", 3.5)
    POWER = ("+3V3", "+5VSB", "VBUS", "VREF", "+3.3", "VDD", "VCC")
    by_net = _pads_by_net(board)
    ic_pad_by_net = collections.defaultdict(list)   # power net -> [(IC pad, IC ref)]  (real bypass loop)
    for n, lst in by_net.items():
        if any(p in n.upper() for p in POWER):
            for r, pad, fp in lst:
                if r.startswith("U"):
                    ic_pad_by_net[n].append((pad, r))
    if not ic_pad_by_net:
        return None, "no IC power pads resolved"
    fails = []
    for fp in board.GetFootprints():
        r = fp.GetReference()
        if not r.startswith("C"):
            continue
        val = _val(fp).lower().replace("µ", "u")
        # only DECOUPLING caps (nF range / 0.1u) own an IC; bulk/hold-up caps (>=1uF) sit off-IC
        if not (("n" in val and "u" not in val) or "0.1u" in val):
            continue
        # measure the actual bypass loop: cap power pad -> the IC power pad on the SAME net (not IC centre)
        best, owner = 1e9, None
        for cpad in fp.Pads():
            cn = cpad.GetNetname()
            for ipad, iref in ic_pad_by_net.get(cn, []):
                a, b = cpad.GetPosition(), ipad.GetPosition()
                dd = math.hypot(_mm(a.x - b.x), _mm(a.y - b.y))
                if dd < best:
                    best, owner = dd, iref
        if best < 1e8 and best > max_mm and owner:
            fails.append((r, best, owner))
    if fails:
        return (False, "decoupling caps far from their IC power pad (>%.1fmm bypass loop): %s"
                % (max_mm, ", ".join("%s %.1fmm" % (f[0], f[1]) for f in fails[:8])),
                [{"type": "adjacent", "a": f[0], "b": f[2], "max_mm": max_mm} for f in fails[:8]])
    return True, "decoupling caps within %.1fmm of their IC power pad" % max_mm


@checker("trace-width-high-current")
def _chk_tw(board, path, ctx):
    if _track_count(board) == 0:
        return None, "floorplan (no tracks)"
    min_mm = _param("trace-width-high-current", "min_mm", 1.0)
    # exempt nets carried by a pour
    poured = set()
    for z in board.Zones():
        try:
            if z.GetFilledArea() / 1e12 > 5:
                poured.add(z.GetNetname())
        except Exception:
            pass
    thin = collections.defaultdict(float)
    for t in board.GetTracks():
        if t.Type() != pcbnew.PCB_TRACE_T:
            continue
        n = t.GetNetname()
        if not ("12V" in n.upper() or n.endswith("_HI")) or n in poured:
            continue
        thin[n] = max(thin[n], _mm(t.GetWidth()))
    bad = sorted(n for n, w in thin.items() if w < min_mm)
    if bad:
        return (False, "high-current nets routed thinner than %.1fmm (and not poured): %s" % (min_mm, ", ".join(bad[:6])),
                [{"type": "keepout", "reserve": "pour_or_widen", "nets": bad}])
    return True, "no too-thin high-current trace"


@checker("hot-sensitive-separation")
def _chk_hotsep(board, path, ctx):
    sep = _param("hot-sensitive-separation", "sep_mm", 8.0)
    shunts = [fp for fp in board.GetFootprints() if fp.GetReference().upper().startswith("RS")]
    hot = [fp for fp in board.GetFootprints()
           if fp.GetReference().upper().startswith("RS") or _is(fp, "LP5907")
           or (fp.GetReference().upper().startswith("J") and _is(fp, "Mini-Fit", "12V2x6", "12V-2x6", "Molex", "2191", "pigtail"))]

    def _board_temp_ntc(fp):
        # an NTC intentionally AT the shunt row (board-temp, e.g. TH1) is NOT a "sensitive" part
        return bool(shunts) and min(_min_pad_dist_mm(fp, s) for s in shunts) <= 6.0
    sens = [fp for fp in board.GetFootprints()
            if (fp.GetReference().upper().startswith("TH") or _is(fp, "REF3030", "REF3033", "Thermistor"))
            and not _board_temp_ntc(fp)]
    if not hot or not sens:
        return None, "no hot/sensitive pair to separate on this board"
    fails = []
    for h in hot:
        for s in sens:
            d = _min_pad_dist_mm(h, s)
            if d < sep:
                fails.append((s.GetReference(), h.GetReference(), d))
    if fails:
        return (False, "temp-sensitive part too close to a hot part (<%.0fmm): %s" % (sep, "; ".join("%s~%s %.1f" % f for f in fails[:5])),
                [{"type": "separate", "a": f[0], "b": f[1], "min_mm": sep} for f in fails[:5]])
    return True, "temp-sensitive parts >= %.0fmm from hot parts" % sep


@checker("ntc-board-temp-by-shunt")
def _chk_ntc(board, path, ctx):
    max_mm = _param("ntc-board-temp-by-shunt", "max_mm", 5.0)
    ntcs = [fp for fp in board.GetFootprints() if fp.GetReference().upper().startswith("TH") or _is(fp, "Thermistor", "NTC")]
    shunts = [fp for fp in board.GetFootprints() if fp.GetReference().upper().startswith("RS")]
    if not ntcs or not shunts:
        return None, "no NTC + shunt pair on this board"
    near = any(min(_min_pad_dist_mm(t, s) for s in shunts) <= max_mm for t in ntcs)
    if not near:
        d = min(min(_min_pad_dist_mm(t, s) for s in shunts) for t in ntcs)
        return False, "no board-temp NTC within %.0fmm of a shunt (nearest %.1fmm)" % (max_mm, d)
    return True, "a board-temp NTC sits within %.0fmm of a shunt" % max_mm


@checker("connector-overhang-bounded")
def _chk_overhang(board, path, ctx):
    l, t, r, b = _edge_bbox(board)
    off = []
    for fp in board.GetFootprints():
        if not (fp.GetReference().upper().startswith("J") and list(fp.Pads())):
            continue
        for pad in fp.Pads():
            name = (pad.GetPadName() or "").strip()
            # only ELECTRICAL contacts must stay on-board; shield/mounting-peg pads may overhang
            if not name or name.upper().startswith(("SH", "MP", "MH")):
                continue
            p = pad.GetPosition()
            x, y = _mm(p.x), _mm(p.y)
            if x < l - 0.05 or x > r + 0.05 or y < t - 0.05 or y > b + 0.05:
                off.append("%s pad %s" % (fp.GetReference(), name))
                break
    if off:
        return (False, "connector electrical pads off the board edge: " + "; ".join(off[:5]),
                [{"type": "region", "target": o.split()[0], "hint": "pull electrical pads on-board"} for o in off[:5]])
    return True, "all connector electrical pads on-board"


@checker("connector-mouth-faces-edge")
def _chk_mouth(board, path, ctx):
    edge_mm = _param("connector-mouth-faces-edge", "edge_mm", 6.0)
    l, t, r, b = _edge_bbox(board)
    interior = []
    cab = [fp for fp in board.GetFootprints()
           if fp.GetReference().upper().startswith("J") and _is(fp, "RJ45", "Mini-Fit", "12V2x6", "USB", "Molex", "JST")]
    if not cab:
        return None, "no edge connectors resolved"
    for fp in cab:
        # the nearest PAD reaching the edge (large connectors have an inboard centre but edge-reaching pads)
        nd = 1e9
        for pad in fp.Pads():
            p = pad.GetPosition()
            x, y = _mm(p.x), _mm(p.y)
            nd = min(nd, x - l, r - x, y - t, b - y)
        if nd > edge_mm:
            interior.append("%s(%.1f)" % (fp.GetReference(), nd))
    if interior:
        return (False, "connector(s) not reaching a board edge (mouth can't seat a cable): %s" % ", ".join(interior),
                [{"type": "pin", "target": ref.split("(")[0], "hint": "move to nearest edge, mouth outward"} for ref in interior])
    return True, "all edge connectors reach a board edge"


@checker("footprint-matches-datasheet")
def _chk_fp_ds(board, path, ctx):
    # reporter: which placed parts carry an MPN but have no datasheet-land verification record yet.
    db = ctx.get("datasheet_db", {})  # mpn -> verified land (future: kicad-happy datasheets skill)
    unverified = []
    for fp in board.GetFootprints():
        mpn = ""
        for k in ("MPN", "Manufacturer_Part_Number", "LCSC"):
            try:
                if fp.HasField(k):
                    mpn = fp.GetFieldText(k)
                    break
            except Exception:
                pass
        if not mpn:
            mpn = _val(fp)
        if mpn and mpn not in db and fp.GetReference()[0] in "UJDQ":
            unverified.append("%s(%s)" % (fp.GetReference(), mpn[:18]))
    if unverified:
        return None, "%d part(s) need datasheet-land verification (no DB record): %s" % (len(unverified), ", ".join(unverified[:8]))
    return True, "all placed MPNs have a datasheet-land record"


# ===========================================================================
#  directive consumer
# ===========================================================================
def directives(rows):
    """Turn FAIL rows into typed placement directives an auto-placer consumes."""
    out = []
    for c, status, detail, payload in rows:
        if status != "FAIL":
            continue
        if payload:
            for p in payload:
                out.append({"constraint": c.id, "severity": c.severity, "directive": p.get("type", c.directive), **p})
        else:
            out.append({"constraint": c.id, "severity": c.severity, "directive": c.directive, "detail": detail[:120]})
    return out


# ===========================================================================
#  run / report
# ===========================================================================
STATUS_ORDER = {"FAIL": 0, "PASS": 1, "DECLARED": 2, "N/A": 3, "ERROR": 4}


def run(board_path, ctx=None):
    ctx = ctx or {}
    board = pcbnew.LoadBoard(board_path)
    out = []
    for c in REGISTRY:
        fn = CHECKERS.get(c.checker or c.id)
        if not fn:
            out.append((c, "DECLARED", "recorded; deterministic checker pending", None))
            continue
        try:
            res = fn(board, board_path, ctx)
            ok, detail = res[0], res[1]
            payload = res[2] if len(res) > 2 else None
            status = "N/A" if ok is None else ("PASS" if ok else "FAIL")
            out.append((c, status, detail, payload))
        except Exception as e:
            out.append((c, "ERROR", "%s: %s" % (type(e).__name__, e), None))
    return out


def report(board_path, ctx, as_json=False):
    rows = run(board_path, ctx)
    if as_json:
        return {"board": os.path.basename(board_path),
                "verdicts": [{"id": c.id, "severity": c.severity, "status": s, "detail": d} for c, s, d, _ in rows],
                "directives": directives(rows)}
    print("=" * 96)
    print("CONSTRAINT REPORT :: %s   (radio=%s)" % (os.path.basename(board_path), ctx.get("radio", False)))
    print("=" * 96)
    rows_s = sorted(rows, key=lambda r: (STATUS_ORDER.get(r[1], 9), r[0].category))
    icon = {"FAIL": "[X]", "PASS": "[v]", "DECLARED": "[.]", "N/A": "[-]", "ERROR": "[!]"}
    for c, status, detail, _ in rows_s:
        print("%s %-9s %-30s %s" % (icon.get(status, "[?]"), status, c.id, str(detail)[:110]))
    n = collections.Counter(r[1] for r in rows)
    print("-" * 96)
    print("  FAIL=%d PASS=%d N/A=%d DECLARED=%d ERROR=%d  (%d canonical; corpus 269)"
          % (n["FAIL"], n["PASS"], n["N/A"], n["DECLARED"], n["ERROR"], len(REGISTRY)))
    ds = directives(rows)
    if ds:
        print("  DIRECTIVES (%d) for the placer:" % len(ds))
        for d in ds[:12]:
            print("    -> %s" % json.dumps(d))
    return rows


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    ctx = {"radio": "--radio" in argv}
    as_json = "--json" in argv
    boards = [a for a in argv if not a.startswith("--")]
    blobs = []
    for b in boards:
        if as_json:
            blobs.append(report(b, ctx, as_json=True))
        else:
            report(b, ctx)
            print()
    if as_json:
        print(json.dumps(blobs, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
