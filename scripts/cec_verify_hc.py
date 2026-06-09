#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_verify_hc -- RAW facts for adversarial verification of the high-current pass.
# ============================================================================
# Emits raw, minimally-interpreted observations about a routed board so an independent
# reviewer can REFUTE "the Kelvin is clean + real" from the data, not from a self-report:
#   * structural DRC (shorts/crossings/clearance, with positions)
#   * unconnected ratlines (which nets, which pads)
#   * every track on a *_HI/_LO sense net: layer, endpoints, width, and whether each
#     endpoint lands on a shunt (RS*) pad or an INA238 input pad   (fake/floating taps show here)
#   * any VIA on a sense net (a Kelvin tap must be via-less, §6.8)
#   * each shunt<->INA238 pair + the min pad gap (did the INA actually seat tight?)
#   * zones: net, layer, filled-area, island count (pour integrity)
#
#   python3 scripts/cec_verify_hc.py <board.kicad_pcb>   -> JSON on stdout
# ============================================================================
import os, sys, json, math, subprocess, tempfile

import pcbnew

MM = 1e6
_COSMETIC = ("silk_overlap", "silk_over_copper", "silk_edge_clearance",
             "lib_footprint_mismatch", "lib_footprint_issues")
_STRUCT = ("shorting_items", "tracks_crossing", "clearance", "courtyards_overlap",
           "solder_mask_bridge", "track_dangling", "via_dangling", "hole_clearance")


def _mm(v):
    return v / MM


def _pad_rects(board):
    """[(ref, padname, net, value, l, t, r, b, is_fcu)] for every pad (mm AABB)."""
    out = []
    for fp in board.GetFootprints():
        ref, val = fp.GetReference(), (fp.GetValue() or "")
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            out.append((ref, p.GetPadName(), p.GetNetname() or "", val,
                        _mm(bb.GetLeft()), _mm(bb.GetTop()), _mm(bb.GetRight()), _mm(bb.GetBottom()),
                        p.GetLayerSet().Contains(pcbnew.F_Cu)))
    return out


def _hits(x, y, rects, want_ref_prefix=None, want_ina=False):
    """Which pad (ref.pad on its net) a point lands in -- filtered to RS* (shunt) or INA238 if asked."""
    for ref, pad, net, val, l, t, r, b, fcu in rects:
        if want_ref_prefix and not ref.upper().startswith(want_ref_prefix):
            continue
        if want_ina and "INA238" not in val.upper() and "INA228" not in val.upper():
            continue
        if l - 0.05 <= x <= r + 0.05 and t - 0.05 <= y <= b + 0.05:
            return "%s.%s[%s]" % (ref, pad, net)
    return None


def verify(board_path):
    board = pcbnew.LoadBoard(board_path)
    rects = _pad_rects(board)

    # --- sense-net tracks + vias ---
    sense_tracks, sense_vias = [], []
    for t in board.GetTracks():
        net = t.GetNetname() or ""
        if not (net.endswith("_HI") or net.endswith("_LO")):
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            c = t.GetPosition()
            sense_vias.append({"net": net, "at": [round(_mm(c.x), 3), round(_mm(c.y), 3)]})
        elif t.Type() == pcbnew.PCB_TRACE_T:
            s, e = t.GetStart(), t.GetEnd()
            sx, sy, ex, ey = _mm(s.x), _mm(s.y), _mm(e.x), _mm(e.y)
            layer = board.GetLayerName(t.GetLayer())
            sense_tracks.append({
                "net": net, "layer": layer, "width_mm": round(_mm(t.GetWidth()), 3),
                "start": [round(sx, 3), round(sy, 3)], "end": [round(ex, 3), round(ey, 3)],
                "len_mm": round(math.hypot(ex - sx, ey - sy), 3),
                "start_on_shunt": _hits(sx, sy, rects, "RS"), "end_on_shunt": _hits(ex, ey, rects, "RS"),
                "start_on_ina": _hits(sx, sy, rects, None, True), "end_on_ina": _hits(ex, ey, rects, None, True)})

    # --- shunt <-> INA238 pairs + min pad gap ---
    pairs = []
    shunts = [fp for fp in board.GetFootprints() if fp.GetReference().upper().startswith("RS")]
    inas = [fp for fp in board.GetFootprints()
            if fp.GetReference().startswith("U") and ("INA238" in (fp.GetValue() or "").upper()
                                                      or "INA228" in (fp.GetValue() or "").upper())]
    for sh in shunts:
        snets = {p.GetNetname() for p in sh.Pads() if (p.GetNetname() or "").endswith(("_HI", "_LO"))}
        for ina in inas:
            inets = {p.GetNetname() for p in ina.Pads()}
            if snets & inets:
                best = 1e9
                for ps in sh.Pads():
                    for pi in ina.Pads():
                        best = min(best, math.hypot(_mm(ps.GetPosition().x - pi.GetPosition().x),
                                                    _mm(ps.GetPosition().y - pi.GetPosition().y)))
                pairs.append({"shunt": sh.GetReference(), "ina": ina.GetReference(),
                              "min_pad_gap_mm": round(best, 3),
                              "ina_rot": ina.GetOrientationDegrees()})
                break

    # --- zones (pour integrity) ---
    zones = []
    for z in board.Zones():
        try:
            area = round(z.GetFilledArea() / MM / MM, 2)
        except Exception:
            area = None
        try:
            islands = z.GetFilledPolysList(z.GetLayer()).OutlineCount() if z.IsFilled() else 0
        except Exception:
            islands = None
        zones.append({"net": z.GetNetname(), "layer": board.GetLayerName(z.GetLayer()),
                      "area_mm2": area, "islands": islands})

    # --- DRC (structural + unconnected) via kicad-cli ---
    drcf = os.path.join(tempfile.gettempdir(), "cec_verify_drc_%d.json" % os.getpid())
    subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "-o", drcf, board_path], capture_output=True)
    drc = {}
    try:
        drc = json.load(open(drcf))
    except Exception:
        pass
    struct = []
    for v in drc.get("violations", []):
        if v["type"] in _STRUCT:
            struct.append({"type": v["type"],
                           "items": [it.get("description", "") for it in v.get("items", [])]})
    unconn = []
    for v in drc.get("unconnected_items", []):
        unconn.append({"items": [it.get("description", "") for it in v.get("items", [])]})

    return {
        "board": board_path,
        "sense_tracks": sense_tracks, "n_sense_tracks": len(sense_tracks),
        "sense_vias": sense_vias, "n_sense_vias": len(sense_vias),
        "kelvin_pairs": pairs,
        "zones": zones,
        "drc_structural": struct, "n_drc_structural": len(struct),
        "unconnected": unconn, "n_unconnected": len(unconn),
    }


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    print(json.dumps(verify(argv[0]), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
