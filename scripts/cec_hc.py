#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_hc -- the DETERMINISTIC HIGH-CURRENT routing pass.
# ============================================================================
# Freerouting doesn't know the high-current intent: it via's the Kelvin sense, taps the
# shunt arbitrarily, and routes foreign signals through the 12V pour (cutting the fill).
# This pass fixes the high-current copper deterministically, run AFTER Freerouting:
#   1. RIP any prior TRACKS/VIAS on the high-current (_HI/_LO) nets -- the pours are ZONES
#      and stay, so the force path is untouched; only FR's via'd/arbitrary sense is removed.
#   2. Route the Kelvin SENSE STUB from the INNER edge of each shunt pad to the INA input
#      pad, on F.Cu, no via (§6.8) -- straight, short, leaving the sense point.
#   3. Re-fill the zones.
# Pair it with pour_region_keepouts() fed to route_once(hints=...) BEFORE FR, so FR keeps
# foreign signals off the pour layers and the fill stays whole. Together this clears
# kelvin-fcu, kelvin-sense-from-inner-pad, and high-current-pour-integrity.
#
#   python3 scripts/cec_hc.py <in.kicad_pcb> <out.kicad_pcb>
# ============================================================================
import os, sys, math, shutil, collections

import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cec_fr       # derive_power_pours

MM = 1e6


def _kelvin_stubs(board, hc_nets):
    """[(net, [inner_edge_pt_mm, ina_input_pad_mm]), ...] -- the short F.Cu sense tap from each shunt
    pad's INNER edge (facing the other terminal) to the INA input pad on that net."""
    pads_by_net = collections.defaultdict(list)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            n = p.GetNetname()
            if n:
                pads_by_net[n].append((fp.GetReference(), fp, p))
    stubs = []
    for fp in board.GetFootprints():
        if not fp.GetReference().upper().startswith("RS"):
            continue
        pads = list(fp.Pads())
        if len(pads) != 2:
            continue
        cen = [p.GetPosition() for p in pads]
        for i, pad in enumerate(pads):
            net = pad.GetNetname()
            if net not in hc_nets:
                continue
            pc, other = pad.GetPosition(), cen[1 - i]
            ix, iy = other.x - pc.x, other.y - pc.y          # inner direction (toward the other terminal)
            inn = math.hypot(ix, iy) or 1.0
            ix, iy = ix / inn, iy / inn
            sz = pad.GetSize()
            reach = (abs(ix) * sz.x + abs(iy) * sz.y) / 2 * 0.8   # ~80% to the inner pad edge (stays on copper)
            inner = ((pc.x + ix * reach) / MM, (pc.y + iy * reach) / MM)
            ina = None
            for ref, ofp, op in pads_by_net.get(net, []):
                if ref.startswith("U") and "INA" in (ofp.GetValue() or "").upper():
                    ina = op.GetPosition()
                    break
            if ina is None:
                for ref, ofp, op in pads_by_net.get(net, []):
                    if ref.startswith("U"):
                        ina = op.GetPosition()
                        break
            if ina is not None:
                stubs.append((net, [inner, (ina.x / MM, ina.y / MM)]))
    return stubs


def keepouts_from_pours(pours, margin=0.2):
    """Convert derive_power_pours() rects into FR keepout dicts (both outer layers), so Freerouting keeps
    FOREIGN signals out of the 12V pour regions -> the pour fills whole. Feed to route_once(hints=...)."""
    kos = []
    for i, p in enumerate(pours):
        (x0, y0), _, (x1, y1), _ = p["polygon"]
        kos.append({"name": "hc_pour_%d" % i, "x0": min(x0, x1) - margin, "y0": min(y0, y1) - margin,
                    "x1": max(x0, x1) + margin, "y1": max(y0, y1) + margin, "layers": ("F.Cu", "B.Cu")})
    return kos


def pour_region_keepouts(board_path, margin=0.2):
    return keepouts_from_pours(cec_fr.derive_power_pours(board_path), margin)


def route_high_current(in_path, out_path):
    """Deterministic high-current pass (see module docstring). Returns a summary dict."""
    # Load ONCE. A second pcbnew.LoadBoard in the same process (e.g. via derive_power_pours) corrupts
    # this build's SWIG footprint wrappers (board.GetFootprints() then yields raw SwigPyObjects), so the
    # high-current nets are computed inline here, not from derive_power_pours.
    board = pcbnew.LoadBoard(in_path)
    names = {n.GetNetname() for n in board.GetNetInfo().NetsByNetcode().values() if n.GetNetname()}
    hc_nets = {n for n in names if n.endswith("_HI") or n.endswith("_LO")}
    if not hc_nets:
        shutil.copyfile(in_path, out_path)
        return {"stubs": 0, "note": "no high-current nets"}
    netcode = {n.GetNetname(): n.GetNetCode() for n in board.GetNetInfo().NetsByNetcode().values()}
    fcu = board.GetLayerID("F.Cu")

    # 1. plan the Kelvin stubs FIRST -- board.Remove() below invalidates the footprint-container view,
    #    so read all footprint/pad geometry before ripping.
    stubs = _kelvin_stubs(board, hc_nets)

    # 2. rip prior TRACKS/VIAS on the high-current nets (the pours are zones -> untouched)
    ripped = 0
    for t in list(board.GetTracks()):
        if t.GetNetname() in hc_nets:
            board.Remove(t)
            ripped += 1

    # 3. lay the Kelvin sense stubs: inner shunt edge -> INA input, F.Cu, no via
    w = int(0.25 * MM)
    for net, pts in stubs:
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            tr = pcbnew.PCB_TRACK(board)
            tr.SetStart(pcbnew.VECTOR2I(int(x0 * MM), int(y0 * MM)))
            tr.SetEnd(pcbnew.VECTOR2I(int(x1 * MM), int(y1 * MM)))
            tr.SetWidth(w)
            tr.SetLayer(fcu)
            tr.SetNetCode(netcode.get(net, 0))
            board.Add(tr)

    # NOTE: no re-fill. The rip removed only TRACKS; the pour ZONES (and their fill) are untouched, so
    # connectivity holds -- and ZONE_FILLER hard-crashes this KiCad-10 build after a track rip. Refill in
    # the GUI ('B') or with kicad-cli if a fresh pour fill is wanted before fab.
    pcbnew.SaveBoard(out_path, board)
    return {"stubs": len(stubs), "ripped_tracks": ripped, "nets": sorted(hc_nets)}


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    out = argv[1] if len(argv) > 1 else argv[0].replace(".kicad_pcb", "-hc.kicad_pcb")
    print(route_high_current(argv[0], out))
    print("->", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
