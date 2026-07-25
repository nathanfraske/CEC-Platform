#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  gen_24pin_sense_cell -- the 24-pin per-rail SENSE-CELL blueprint (v0)
#  (owner ask 2026-07-19: "it needs to stamp out the INA238 and INA181
#   blueprint -- has it called that rung yet?" -- answer was NEVER; this
#   builds the missing template).
# ============================================================================
# One template, four stamps: RS (2512 straddle shunt) + INA238 (VSSOP-10) +
# INA181A2 (SOT-23-6) + TLV7011 (SOT-23-5), netlist-verified identical across
# the four rails (12V / 5V / 3V3 / 5VSB). The 5V rail is the ROLE rail.
#
# DOCTRINE LAYOUT (the v3-keystone answer baked into the cell): parts pack
# PERPENDICULAR to the shunt's pad axis (all below, local -y), leaving BOTH
# pad-axis approaches free -- that is exactly where the force-rail plan lands
# its face stubs + via arrays (the measured 0/4 refusal cause was cell parts
# seated on those sites). Kelvin copper itself is the precision tap pass's
# job at board time; the ONE internal net (INA181 out -> TLV7011 in, DETAMP)
# gets ideal-synthesized routing at stamp (ideal_internal=True).
#
# v0 scope: the 4 silicon parts only -- bypass/threshold passives keep their
# auto_cluster ownership (they cluster to these ICs' stamped positions).
#
# Run IN the routing container:
#   python3 scripts/gen_24pin_sense_cell.py [--out beta/atx-24pin-rev3/blueprints/sense-rail-v0.json]
# Verifies: nets exist for every rail, footprints resolve, courtyards clear.
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)

# role parts (the 5V rail) -> doctrine offsets in the template local frame
# (shunt horizontal at origin, pads +-x; everything else BELOW).
ROLE_PARTS = {
    "RS2":   {"offset_mm": (0.0, 0.0),   "rot_delta": 0.0},
    "U11":   {"offset_mm": (0.0, -4.6),  "rot_delta": 0.0},    # INA238 hard against the inner edge
    # INA181 ROTATED 180 (tap-ability redesign, 2026-07-19: with the inputs on
    # its shunt-facing row, LO could not reach IN- without crossing HI copper
    # or a rail-stub corridor -- every entry measured walled by the v0..v3
    # generator asserts. Rotated, BOTH inputs face the under-lane and each
    # polarity approaches from its own below-lane.)
    "U65V1": {"offset_mm": (-5.6, -4.4), "rot_delta": 180.0},
    "U75V1": {"offset_mm": (-5.6, -8.2), "rot_delta": 0.0},    # authored-taps variant deepens to -8.5
}
ROLE_RAIL = "5V"

# per-rail literals (verified against the rev3 netlist at generation)
RAILS = {
    "12V":  {"rs": "RS1", "ina238": "U10", "ina181": "U612V1", "tlv": "U712V1",
             "CELL_HI": "/SENSE12V_HI", "CELL_LO": "/SENSE12V_LO",
             "CELL_DET": "/DET12V", "CELL_DETAMP": "/DETAMP12V"},
    "5V":   {"rs": "RS2", "ina238": "U11", "ina181": "U65V1", "tlv": "U75V1",
             "CELL_HI": "/SENSE5V_HI", "CELL_LO": "+5V_MAIN",
             "CELL_DET": "/DET5V", "CELL_DETAMP": "/DETAMP5V"},
    "3V3":  {"rs": "RS3", "ina238": "U12", "ina181": "U63V31", "tlv": "U73V31",
             "CELL_HI": "/SENSE3V3_HI", "CELL_LO": "/SENSE3V3_LO",
             "CELL_DET": "/DET3V3", "CELL_DETAMP": "/DETAMP3V3"},
    "5VSB": {"rs": "RS4", "ina238": "U13", "ina181": "U65VSB1", "tlv": "U75VSB1",
             "CELL_HI": "+5VSB", "CELL_LO": "/SENSE5VSB_LO",
             "CELL_DET": "/DET5VSB", "CELL_DETAMP": "/DETAMP5VSB"},
}
SHARED_NETS = ("GND", "+3V3", "/I2C_SDA", "/I2C_SCL", "/THRESH")
TAP_W = 0.25          # sense-class track width for the authored Kelvin taps
TAP_CLR = 0.2         # min copper clearance every authored leg must prove


def _pad_geom(fp_of, pose, ref, cec_pcb):
    """{pad: (x, y, sx, sy)} cell-local pad centres + sizes for *ref*. Centres
    come from cec_pcb.pad_global (the ONE rotation convention -- the stamp and
    the placer use the same call); only the sizes are parsed here, axis-swapped
    for 90/270."""
    import re
    nick, name = fp_of[ref].split(":")
    t = open(cec_pcb.fp_path(nick, name)).read()
    rot = pose[ref][2]
    sizes = {}
    for m in re.finditer(r"\(pad ", t):
        b = cec_pcb.carve(t, m.start())
        num = re.match(r'\(pad "([^"]*)"', b)
        sz = re.search(r"\(size ([\d.]+) ([\d.]+)", b)
        if num and sz and num.group(1) and "np_thru_hole" not in b.split("\n")[0]:
            sx, sy = float(sz.group(1)), float(sz.group(2))
            if rot % 180.0 == 90.0:
                sx, sy = sy, sx
            sizes[num.group(1)] = (sx, sy)
    out = {}
    for p, (sx, sy) in sizes.items():
        gx, gy = cec_pcb.pad_global(ref, p, pose, fp_of)
        out[p] = (gx, gy, sx, sy)
    return out


def _leg_pad_gap(a, b, px, py, hx, hy):
    """Distance from axis-aligned segment a->b (points) to the pad rect centred
    (px,py) half (hx,hy). 0 = touching/inside."""
    x0, x1 = min(a[0], b[0]), max(a[0], b[0])
    y0, y1 = min(a[1], b[1]), max(a[1], b[1])
    dx = max(px - hx - x1, x0 - (px + hx), 0.0)
    dy = max(py - hy - y1, y0 - (py + hy), 0.0)
    return (dx * dx + dy * dy) ** 0.5


def author_kelvin_taps(fp_of, pose, nl, role, cec_pcb, side=-1):
    """The §6.8 Kelvin taps AUTHORED into the cell (owner, wave-15 render: taps
    must be the textbook orthogonal 90s, not the route-time guard-refusal
    fallbacks; v5 TAP-FORM ruling 2026-07-25: each tap must CONTACT its shunt
    pad on the INNER edge, run PERPENDICULAR from that edge into the inter-pad
    gap toward the shunt middle, then ONE 90 turn OUTWARD to the INA -- "like
    on every other board"). All-orthogonal paths in template coordinates,
    derived parametrically from the measured pad geometry; every leg is
    clearance-asserted against every foreign pad and opposite-polarity taps are
    cross-checked -- the generator FAILS LOUD rather than emit a colliding
    template. Returns internal_tracks entries (net_role CELL_HI/CELL_LO).

    *side*: -1 = the bank at template -y (the original derivation frame),
    +1 = the MIRRORED cell (bank at +y). Handled by normalizing the measured
    geometry into the -y frame (y *= -side), deriving with the one set of
    formulas, and denormalizing the emitted points -- the asserts run on the
    normalized geometry, so both handednesses carry the same proofs."""
    geom = {r: _pad_geom(fp_of, pose, r, cec_pcb) for r in pose}
    if side > 0:                                   # normalize: mirror into the -y frame
        geom = {r: {p: (x, -y, sx, sy) for p, (x, y, sx, sy) in g.items()}
                for r, g in geom.items()}
    rs, u238, u181 = role["rs"], role["ina238"], role["ina181"]
    hi_net, lo_net = role["CELL_HI"], role["CELL_LO"]

    def net_pads(net):
        return [(r, p) for r, p in nl.nets[net] if r in pose]

    def one(net, ref):
        ps = [p for r, p in net_pads(net) if r == ref]
        assert len(ps) == 1, "%s on %s: expected 1 pad, got %s" % (net, ref, ps)
        return ps[0]

    hi_rs, lo_rs = one(hi_net, rs), one(lo_net, rs)
    in_p = one(hi_net, u238)                       # INA238 IN+ (the only HI pad)
    lo238 = [p for r, p in net_pads(lo_net) if r == u238]
    # IN- = the LO-net pad ADJACENT to IN+ (defence-1 by geometry: VBUS shares
    # the net but sits one pitch farther)
    in_n = min(lo238, key=lambda p: abs(geom[u238][p][1] - geom[u238][in_p][1]))
    inp181, inn181 = one(hi_net, u181), one(lo_net, u181)

    g = lambda ref, pad: geom[ref][pad]
    hx_rs, hy_rs = g(rs, hi_rs)[:2]
    lx_rs, ly_rs = g(rs, lo_rs)[:2]
    x10, y10 = g(u238, in_p)[:2]
    x9, y9 = g(u238, in_n)[:2]
    xi181p, yi181 = g(u181, inp181)[:2]
    xi181n = g(u181, inn181)[0]

    cols238 = sorted({round(v[0], 3) for v in geom[u238].values()})
    lcol_edge = min(v[0] - v[2] / 2 for v in geom[u238].values())
    rcol_edge = max(v[0] + v[2] / 2 for v in geom[u238].values())
    bot238 = min(v[1] - v[3] / 2 for v in geom[u238].values())   # most-negative edge
    in_top = yi181 + g(u181, inp181)[3] / 2                     # 181 input row top edge

    hw = TAP_W / 2.0
    # channel constants, all derived + then proven by the asserts below.
    # Shapes (v5 -- the TAP-FORM ruling, owner 2026-07-25, recorded in
    # docs/slab-pour-design-2026-07-24.md "Tap-form ruling": each tap CONTACTS
    # its shunt pad on the INNER edge -- the edge facing the resistive element
    # -- runs PERPENDICULAR from that edge into the inter-pad gap toward the
    # shunt middle, then makes ONE 90 turn OUTWARD toward the bank and routes
    # to its INA pads; the v4 pad-bottom / outside-corridor entries are
    # retired. Both stubs enter at their pad's own centre row; they clear each
    # other because the turn columns are UNCROSSED (x_hi < x_lo_gap, asserted
    # at 2*hw+TAP_CLR minimum separation) -- the _check pass then re-proves
    # every pairwise clearance on the real geometry:
    #   HI: inner-edge stub east -> 90 DOWN the 238's between-columns channel
    #       to the under-lane -> west branch up into 181.IN+ from below +
    #       east branch at the under-lane up into 238.IN+ (pad 10) from below.
    #   LO: inner-edge stub west -> 90 DOWN inside the gap to the over-column
    #       line -> east over the 238's column top -> down the OUTER drop
    #       (outside the right column) -> sideways into 238.IN- (pad 9) ->
    #       continue to the LOWER lane, west under everything, up into
    #       181.IN- from below. (The only crossing-free topology: both 181
    #       inputs need below-approaches on the west, so the channel belongs
    #       to HI and LO takes the outer drop its own pad overhangs.)
    b181_bot = min(v[1] - v[3] / 2 for v in geom[u181].values())
    y_bot = min(bot238, b181_bot) - TAP_CLR - hw - 0.15          # HI under-lane
    y_lo2 = y_bot - (2 * hw + TAP_CLR + 0.05)                    # LO lower lane
    # the TLV constrains the LO lane only if it actually sits UNDER it (the
    # TLV-beside layout moves it to x_t ~9.4, out of the lane's x-reach)
    _tlv_under = [v[1] + v[3] / 2 for v in geom[role["tlv"]].values()
                  if v[0] < 4.5]
    if _tlv_under:
        assert y_lo2 - max(_tlv_under) >= TAP_CLR + hw - 1e-6, \
            "no LO lane between the HI under-lane and the TLV top row"
    col_top = max(v[1] + v[3] / 2 for v in geom[u238].values())  # 238 col highest edge
    y_jog = col_top + TAP_CLR + hw                               # over-the-column line
    x_od = rcol_edge + TAP_CLR + hw + 0.075                      # outer drop column
    # v5 inner-edge entries + the 238 between-columns channel (the HI descent)
    hi_in_x = hx_rs + g(rs, hi_rs)[2] / 2.0      # HI pad inner edge (faces the element)
    lo_in_x = lx_rs - g(rs, lo_rs)[2] / 2.0      # LO pad inner edge
    _rs_pads = (g(rs, hi_rs), g(rs, lo_rs))
    rs_bot_edge = min(v[1] - v[3] / 2 for v in _rs_pads)         # shunt pad bottom edge
    lcol_in = max(v[0] + v[2] / 2 for v in geom[u238].values() if v[0] < 0)
    rcol_in = min(v[0] - v[2] / 2 for v in geom[u238].values() if v[0] > 0)
    ch_l = lcol_in + TAP_CLR + hw                # descent-centreline channel walls
    ch_r = rcol_in - TAP_CLR - hw
    assert ch_r - ch_l >= 2 * hw + TAP_CLR - 1e-6, \
        "238 between-columns channel too narrow for the HI descent"
    assert y_jog <= rs_bot_edge - TAP_CLR - hw + 1e-6, \
        "no over-column line between the shunt pads and the 238 column top"

    net_of = {"CELL_HI": hi_net, "CELL_LO": lo_net,
              "CELL_DETAMP": role["CELL_DETAMP"]}
    pad_net = {}
    for net in set(n for n, nodes in nl.nets.items()):
        for r, p in nl.nets[net]:
            if r in pose:
                pad_net[(r, p)] = net

    def _check(taps):
        """None if every leg clears every FOREIGN pad (same-net exempt; the
        opposite sense leg is NOT exempt) and HI/LO taps clear each other;
        else the first violation as a string."""
        for rolek, pts in taps:
            tnet = net_of[rolek]
            for a, b in zip(pts, pts[1:]):
                if a == b:
                    return "degenerate leg in %s tap" % rolek
                for r in pose:
                    for p, (px, py, sx, sy) in geom[r].items():
                        if pad_net.get((r, p)) == tnet:
                            continue
                        gap = _leg_pad_gap(a, b, px, py, sx / 2, sy / 2) - hw
                        if gap < TAP_CLR - 1e-6:
                            return "%s leg %s->%s clips %s.%s [%s] by %.3f" % (
                                rolek, a, b, r, p, pad_net.get((r, p)), TAP_CLR - gap)
        def segs(k):
            return [(a, b) for rk, pts in taps if rk == k
                    for a, b in zip(pts, pts[1:])]
        _roles = sorted({rk for rk, _pts in taps})
        for i, k1 in enumerate(_roles):
            for k2 in _roles[i + 1:]:
                if net_of[k1] == net_of[k2]:
                    continue
                for a1, b1 in segs(k1):
                    for a2, b2 in segs(k2):
                        x0a, x1a = min(a1[0], b1[0]) - hw, max(a1[0], b1[0]) + hw
                        y0a, y1a = min(a1[1], b1[1]) - hw, max(a1[1], b1[1]) + hw
                        x0b, x1b = min(a2[0], b2[0]) - hw, max(a2[0], b2[0]) + hw
                        y0b, y1b = min(a2[1], b2[1]) - hw, max(a2[1], b2[1]) + hw
                        dx = max(x0a - x1b, x0b - x1a, 0.0)
                        dy = max(y0a - y1b, y0b - y1a, 0.0)
                        if (dx * dx + dy * dy) ** 0.5 < TAP_CLR - 1e-6:
                            return "%s/%s taps collide: %s->%s vs %s->%s" % (
                                k1, k2, a1, b1, a2, b2)
        return None

    # candidate shapes: the straight-column 181 approaches first, then
    # offset-column variants (a mirrored cell's non-mirroring part layouts put
    # a foreign pad in the straight column -- measured on the -left variant)
    inn_l = xi181n - g(u181, inn181)[2] / 2 - TAP_CLR - hw - 0.1
    inn_r = xi181n + g(u181, inn181)[2] / 2 + TAP_CLR + hw + 0.1
    inp_l = xi181p - g(u181, inp181)[2] / 2 - TAP_CLR - hw - 0.1
    inp_r = xi181p + g(u181, inp181)[2] / 2 + TAP_CLR + hw + 0.1
    # AUTHORED DETAMP (the 181's OUT -> the TLV's IN): the blind ideal
    # synthesis crossed the authored HI tap and the per-segment intra-cell
    # guard (audit #1) rightly refused the whole cell -- authoring it routes
    # the deepest lane (below the LO lane) east to the beside-TLV. The
    # have-set in synthesize_ideal_internal then skips this role.
    da_net = role["CELL_DETAMP"]
    da_pads = [(r, p) for r, p in nl.nets[da_net] if r in pose]
    xo181 = yo181 = xtin = ytin = None
    for r, p in da_pads:
        gx, gy, _sx, _sy = geom[r][p]
        if r == u181:
            xo181, yo181 = gx, gy
        elif r == role["tlv"]:
            xtin, ytin = gx, gy
    assert None not in (xo181, yo181, xtin, ytin), \
        "DETAMP pads not resolvable (need 181 OUT + TLV IN)"
    y_dt = y_lo2 - (2 * hw + TAP_CLR + 0.05)             # deepest lane
    # around-the-west shape (the straight drop clips the GND pad stacked
    # directly under OUT -- measured): north over the 181's top row, west
    # past its body, down the far side, then the deep lane east to the TLV.
    _t181 = max(v[1] + v[3] / 2 for v in geom[u181].values())   # 181 top edge
    _rs_bot = -(max(v[3] for v in geom[rs].values()) / 2.0)     # shunt pad bottom
    y_up = (_rs_bot - 0.325 + _t181 + 0.325) / 2.0
    x_far2 = min(v[0] - v[2] / 2 for v in geom[u181].values()) - TAP_CLR - hw - 0.1
    # rise mid-channel (between the LO outer drop and the TLV's left column)
    # and enter IN from the side -- the TLV's DET pad stacks directly below
    # IN in the same column (measured), so a bottom-up entry clips it
    x_rise = (x_od + TAP_CLR + hw + 0.2
              + (xtin - g(role["tlv"], [p for r, p in da_pads
                                        if r == role["tlv"]][0])[2] / 2 - 0.325)) / 2.0
    detamp = [("CELL_DETAMP", [(xo181, yo181), (xo181, y_up), (x_far2, y_up),
                               (x_far2, y_dt), (x_rise, y_dt),
                               (x_rise, ytin), (xtin, ytin)])]
    # v5 candidate grid: the two stub TURN COLUMNS (x_hi for the HI channel
    # descent, x_lo_gap for the LO in-gap drop) x the 181 approach-column
    # variants. The stubs both run on the pad-centre row, so their clearance
    # IS the column separation -- enforced here and re-proven by _check.
    ch_mid = (ch_l + ch_r) / 2.0
    _sep_min = 2 * hw + TAP_CLR
    x_hi_cands = []
    for _xh in (-0.6, -0.9, -0.3, ch_mid - 0.6):
        _xh = min(max(_xh, ch_l), ch_r)
        if all(abs(_xh - q) > 1e-6 for q in x_hi_cands):
            x_hi_cands.append(_xh)
    x_lo_cands = []
    for _xl in (lo_in_x - 1.15, lo_in_x - 0.75, ch_r):
        _xl = min(_xl, lo_in_x - 2 * hw)         # the stub must actually enter the gap
        if all(abs(_xl - q) > 1e-6 for q in x_lo_cands):
            x_lo_cands.append(_xl)
    cands = []
    for x_hi in x_hi_cands:
        for x_lo_gap in x_lo_cands:
            if x_lo_gap - x_hi < _sep_min - 1e-6:
                continue                          # stubs share the gap row -- keep clear
            for xn in (xi181n, inn_l, inn_r):
                for xp in (xi181p, inp_l, inp_r):
                    _lo1 = [(lo_in_x, ly_rs), (x_lo_gap, ly_rs), (x_lo_gap, y_jog),
                            (x_od, y_jog), (x_od, y_lo2), (xn, y_lo2), (xn, yi181)]
                    if xn != xi181n:
                        _lo1 = _lo1[:-1] + [(xn, yi181), (xi181n, yi181)]
                    _hi1 = [(hi_in_x, hy_rs), (x_hi, hy_rs), (x_hi, y_bot),
                            (xp, y_bot), (xp, yi181)]
                    if xp != xi181p:
                        _hi1 = _hi1[:-1] + [(xp, yi181), (xi181p, yi181)]
                    cands.append([
                        ("CELL_LO", _lo1),
                        ("CELL_LO", [(x_od, y9), (x9, y9)]),     # 238 IN- branch
                        ("CELL_HI", _hi1),                       # 181 IN+ path
                        ("CELL_HI", [(x_hi, y_bot), (x10, y_bot), (x10, y10)]),
                    ] + detamp)
    assert cands, "no stub-column pair satisfies the shared-gap separation"
    taps, _reasons = None, []
    for _ci, _cand in enumerate(cands):
        _why = _check(_cand)
        if _why is None:
            taps = _cand
            break
        _reasons.append("cand%d: %s" % (_ci, _why))
    assert taps is not None, \
        "no tap shape passes (side=%+d): %s" % (side, "; ".join(_reasons))
    tracks = []
    _ys = -1.0 if side > 0 else 1.0                # denormalize back to the real frame
    for rolek, pts in taps:
        for a, b in zip(pts, pts[1:]):
            tracks.append({"net_role": rolek, "layer": "F.Cu",
                           "start_rel_mm": [round(a[0], 4), round(a[1] * _ys, 4)],
                           "end_rel_mm": [round(b[0], 4), round(b[1] * _ys, 4)],
                           "width_mm": TAP_W})
    # tap-form witness (embedded as meta['tap_form'] by _emit_one; the teeth assert
    # the inner-edge entry against these EXACT derived edge coordinates)
    author_kelvin_taps.form = {
        "hi_inner_edge": [round(hi_in_x, 4), round(hy_rs * _ys, 4)],
        "lo_inner_edge": [round(lo_in_x, 4), round(ly_rs * _ys, 4)],
        "outward_y_sign": -_ys,                    # toward the bank in the emitted frame
    }
    return tracks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(
        ROOT, "modules", "atx-24pin-rev3", "blueprints", "sense-rail-v0.json"))
    args = ap.parse_args()

    import cec_synth_pipeline as csp
    import cec_fresh_wave as W
    import cec_pcb

    s, _p = W._build_session("atx-24pin-rev3", 70.0, 55.0, "plain", "compact", 0, None)
    nl = csp.View(s.cfg).nl
    fp_of = csp._fp_of(nl)

    # ---- verify every rail's refs + nets exist --------------------------------
    for rail, m in RAILS.items():
        for k in ("rs", "ina238", "ina181", "tlv"):
            assert m[k] in fp_of, "%s: ref %s missing" % (rail, m[k])
        for k in ("CELL_HI", "CELL_LO", "CELL_DET", "CELL_DETAMP"):
            assert m[k] in nl.nets, "%s: net %s missing from the netlist" % (rail, m[k])
    for n in SHARED_NETS:
        assert n in nl.nets, "shared net %s missing" % n

    role = RAILS[ROLE_RAIL]
    return _emit_variants(args, nl, fp_of, role, csp, cec_pcb)


def _emit_variants(args, nl, fp_of, role, csp, cec_pcb):
    """Write BOTH handedness variants: the base file (bank at template -y =
    board-RIGHT of the column at the 270 seats) and the *-left sibling (bank
    mirrored to +y = board-LEFT). Per-rail handedness is the wave wiring's
    choice -- the J1/J6 wedge (2026-07-19): the rightmost rail's bank must
    not reach J6, the leftmost's must not reach J1, and one handedness for
    all four cannot satisfy both."""
    rc = 0
    # THREE artifacts (the 2026-07-19 wedge arithmetic: the authored-tap
    # cell's extra ~0.35mm of bank reach re-wedges every four-column
    # handedness assignment at pitch 12 on W=70, so the STAMPED template is
    # parts-only tonight):
    #   v0.json       parts-only, bank right -- what all four stamps use
    #   v0-left.json  parts-only, bank left  -- kept for per-rail handedness
    #   v0-taps.json  the authored Kelvin-90 cell -- next pass's artifact
    #                 (needs the TLV-beside redesign to shave its reach)
    for suffix, side, taps_on in (("", -1, False), ("-left", +1, False),
                                  ("-taps", -1, True)):
        out = args.out if not suffix else args.out[:-len(".json")] + suffix + ".json"
        _emit_one(out, nl, fp_of, role, csp, cec_pcb, side=side, author_taps=taps_on)
    return rc


def _emit_one(out_path, nl, fp_of, role, csp, cec_pcb, *, side=-1, author_taps=True):
    # the mirrored (+y) variant reflects the offsets only; part rotations keep
    # their template values (the shunt anchor's rotation is the board hi/lo
    # polarity contract either way).
    pose = {}
    for r, sp in ROLE_PARTS.items():
        ox, oy, rot = sp["offset_mm"][0], sp["offset_mm"][1], sp["rot_delta"]
        if r == "U75V1" and author_taps and side < 0:
            # TLV BESIDE the sink corridor, not below the 181 (owner render
            # report 2026-07-19 evening: the deep TLV column cost +0.35mm of
            # bank reach, which kept the authored-90 cell un-stampable and
            # left the route-time diagonal/wraparound fallback taps on the
            # boards). At (9.4, -4.4) it sits board-(col-4.4, row+9.4) --
            # measured clear of the sink stub corridor (x_t 3..6.2) and the
            # LO outer drop; the cell's deep reach drops ~9.75 -> ~7.9 and
            # fits the 11.9 pitch with ~1.6mm spare. y -4.4 -> -5.0 (measured
            # s2a: at -4.4 the TLV pads sat 0.3mm inside the rail's own sink
            # descent corridor, board col+3.45 vs the 3.75 radius).
            ox, oy = 9.4, -5.0
        if r == "U65V1" and not author_taps:
            rot = 0.0          # the 181's rot-180 exists FOR the authored taps
        if side > 0:           # (inputs facing the under-lane); parts-only
            oy = -oy           # cells keep the original facing -- rot 180
        pose[r] = (ox, oy, rot)  # moved the ideal-DETAMP path onto +3V3
                                 # (measured whole-cell refusal)

    # ---- courtyard legality of the template itself ----------------------------
    boxes = {}
    for r in ROLE_PARTS:
        x0, x1, y0, y1 = cec_pcb.courtyard_bbox(fp_of[r], *pose[r])
        boxes[r] = (x0, x1, y0, y1)
    refs = list(boxes)
    for i, a in enumerate(refs):
        for b in refs[i + 1:]:
            ax0, ax1, ay0, ay1 = boxes[a]
            bx0, bx1, by0, by1 = boxes[b]
            assert (ax1 + 0.3 <= bx0 or bx1 + 0.3 <= ax0
                    or ay1 + 0.3 <= by0 or by1 + 0.3 <= ay0), \
                "template courtyards collide: %s vs %s" % (a, b)

    # ---- role mapping: net -> role key ---------------------------------------
    lit2role = {role[k]: k for k in ("CELL_HI", "CELL_LO", "CELL_DET", "CELL_DETAMP")}
    for n in SHARED_NETS:
        lit2role[n] = n                                   # shared nets are their own role

    # ---- collect pads per role net -------------------------------------------
    pads_by_role = {}
    for net, nodes in nl.nets.items():
        if net not in lit2role:
            continue
        rolek = lit2role[net]
        for r, p in nodes:
            if r not in ROLE_PARTS:
                continue
            gx, gy = cec_pcb.pad_global(r, p, pose, fp_of)
            pads_by_role.setdefault(rolek, []).append(
                {"ref": r, "pad": p, "rel_mm": [round(gx, 4), round(gy, 4)]})

    internal = {"CELL_DETAMP": {"pads": pads_by_role.pop("CELL_DETAMP", [])}}
    assert len(internal["CELL_DETAMP"]["pads"]) == 2, \
        "DETAMP must be exactly the 181-out -> 7011-in pair"

    parts = {}
    for r in ROLE_PARTS:
        parts[r] = {"offset_mm": [pose[r][0], pose[r][1]],
                    "rot_delta": pose[r][2], "flipped": False,
                    "footprint": fp_of[r],
                    "value": nl.comps[r].value or ""}

    template = {
        "meta": {"board": "atx-24pin-rev3", "generator": "gen_24pin_sense_cell v0",
                 "role_rail": ROLE_RAIL, "bank_side": ("left" if side > 0 else "right"),
                 "doctrine": "parts pack perpendicular to the pad axis; both "
                             "pad-axis approaches stay free for the force-rail "
                             "face stubs + via arrays (the v3-keystone rule)"},
        "anchor": {"ref": role["rs"], "footprint": fp_of[role["rs"]],
                   "value": nl.comps[role["rs"]].value or "", "flipped": False},
        "parts": parts,
        "net_roles": {k: role[k] for k in ("CELL_HI", "CELL_LO", "CELL_DET",
                                           "CELL_DETAMP")} |
                     {n: n for n in SHARED_NETS},
        "ports": {k: {"net": (role[k] if k in role else k), "pads": v}
                  for k, v in pads_by_role.items()},
        "internal_pads": internal,
        # AUTHORED Kelvin taps (owner, wave-15 render: textbook orthogonal 90s,
        # stamped LOCKED with the cell -- the route-time synthesizer's
        # double-lay guard then skips these pairs, ending the guard-refusal
        # diagonal fallbacks). CELL_DETAMP stays ideal-synthesized (the
        # have-set in synthesize_ideal_internal skips authored roles only).
        "internal_tracks": (author_kelvin_taps(fp_of, pose, nl, role, cec_pcb, side=side)
                            if author_taps else []),
        # v5 tap-form witness (owner ruling 2026-07-25): the derived shunt-pad
        # inner-edge coordinates the authored stubs start ON -- the teeth assert
        # inner-edge entry + perpendicular-then-90-outward against these.
        "tap_form": (getattr(author_kelvin_taps, "form", None) if author_taps else None),
        "port_tracks": [],
        "standins": [],
        "vias": [],
        "gnd_vias": [],
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(template, fh, indent=1)
    print("template written:", out_path, "(bank", template["meta"]["bank_side"] + ")")
    print("  parts:", list(parts), "| ports:", list(template["ports"]),
          "| internal:", list(internal),
          "| taps:", len(template["internal_tracks"]))


if __name__ == "__main__":
    sys.exit(main())
