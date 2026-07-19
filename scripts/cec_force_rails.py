#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_force_rails -- SHARED-BUS per-rail force-copper synthesis (the 24-pin
#                     zone creator; owner: "the 24 pin is pretty much fully
#                     gated on that working", GO 2026-07-19).
# ============================================================================
# The shared-bus sibling of cec_force_lanes: where the 12VHPWR carries six
# IDENTICAL per-pin lanes (fixed v7 geometry), the 24-pin carries FOUR
# heterogeneous RAILS (12V / 5V / 3V3 / 5VSB), each J3 pin-group -> straddle
# shunt -> TB blade tab(s), with per-rail currents (the owner connector bars:
# 5V 25A / 3V3 20A / 12V 12A / 5VSB 5A) and per-rail FACE (the placer's
# alternating-F/B rail chains). GND is NOT a rail here: the plane + stitching
# own it.
#
# Discovery is NET-NAME-INDEPENDENT (the straddle rule): a 2-pad RS* shunt's
# two nets are the rail; the side carrying J3 pads is the SOURCE, the side
# carrying TB* pads the SINK (RS2's +5V_MAIN and RS4's +5VSB break every
# name pattern -- measured 2026-07-19).
#
# Geometry v1 (bands, the lane fan generalized):
#   SOURCE: per-J3-pin vertical drops onto a per-rail BAND row below the J3
#   field (rank-staggered), the band runs to the shunt column, a spine drops
#   to the shunt HI pad. A pin drop that would cross a foreign barrel (the
#   ATX column pairing puts e.g. -12V under a 3V3 pin) is REFUSED per-pin
#   (left to FR -- same-net short hop to the trunk); the band/spine refusing
#   is rail-fatal (refuse-loud, placer teaches).
#   SINK: shunt LO pad -> a lower band -> per-TB drops onto the blade tabs.
#
# Widths: w = clamp(amps * 0.25, 1.5, 6.0) [wb -- the electrothermal gate is
# the validator of record; F/B mirroring + the inner power-routing layer are
# the v2 levers if the gate asks]. All copper LOCKED (exports as fix -> FR
# protect, same contract as lanes/cells).
import math

MM = 1e6

RAIL_AMPS = (("5VSB", 5.0), ("3V3", 20.0), ("12V", 12.0), ("5V", 25.0))


def _amps_for(nets):
    s = " ".join(n.upper() for n in nets)
    for key, a in RAIL_AMPS:
        if key in s:
            return a
    return 10.0


def _seg_pt_d2(x, y, sx, sy, ex, ey):
    dx, dy = ex - sx, ey - sy
    L2 = dx * dx + dy * dy
    if L2 <= 1e-12:
        return (x - sx) ** 2 + (y - sy) ** 2
    t = max(0.0, min(1.0, ((x - sx) * dx + (y - sy) * dy) / L2))
    px, py = sx + t * dx, sy + t * dy
    return (x - px) ** 2 + (y - py) ** 2


def discover_rails(board):
    """[{rs, src_net, snk_net, amps, face, hi(x,y), lo(x,y), j3:[(pad,x,y,half)],
    tb:[(ref,pad,x,y,half)]}] -- name-independent straddle discovery."""
    import pcbnew
    pads_by_net = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            nn = p.GetNetname()
            if nn:
                pads_by_net.setdefault(nn, []).append((fp.GetReference(), p))
    rails = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if not ref.startswith("RS") or fp.GetPadCount() != 2:
            continue
        p1, p2 = list(fp.Pads())
        nets = (p1.GetNetname(), p2.GetNetname())
        if not all(nets) or nets[0] == nets[1]:
            continue

        def _has(net, pref):
            return any(r.startswith(pref) for r, _ in pads_by_net.get(net, ()))
        src = next((n for n in nets if _has(n, "J3")), None)
        snk = next((n for n in nets if n != src and _has(n, "TB")), None)
        if not (src and snk):
            continue
        hi_p = p1 if p1.GetNetname() == src else p2
        lo_p = p2 if hi_p is p1 else p1
        face = "B.Cu" if fp.IsFlipped() else "F.Cu"
        j3 = [(p.GetPadName(), p.GetPosition().x / MM, p.GetPosition().y / MM,
               max(p.GetSize().x, p.GetSize().y) / (2 * MM))
              for r, p in pads_by_net[src] if r.startswith("J3")]
        tb = [(r, p.GetPadName(), p.GetPosition().x / MM, p.GetPosition().y / MM,
               max(p.GetSize().x, p.GetSize().y) / (2 * MM))
              for r, p in pads_by_net[snk] if r.startswith("TB")]
        rails.append({
            "rs": ref, "src_net": src, "snk_net": snk,
            "amps": _amps_for(nets), "face": face,
            "hi": (hi_p.GetPosition().x / MM, hi_p.GetPosition().y / MM),
            "lo": (lo_p.GetPosition().x / MM, lo_p.GetPosition().y / MM),
            "j3": sorted(j3, key=lambda q: q[1]), "tb": sorted(tb, key=lambda q: q[2]),
        })
    rails.sort(key=lambda rl: rl["hi"][0])                     # rank by shunt column
    return rails


def lay_force_rails(board, *, lock=True, verbose=True):
    """Lay the per-rail force copper LOCKED. Returns {rs: report|'REFUSED: ...'}."""
    import pcbnew
    rails = discover_rails(board)
    if not rails:
        return {}
    layer_id = {"F.Cu": board.GetLayerID("F.Cu"), "B.Cu": board.GetLayerID("B.Cu")}
    netmap = {str(k): v for k, v in board.GetNetInfo().NetsByName().items()}

    pads = []                                                  # foreign-guard universe
    for fp in board.GetFootprints():
        for p in fp.Pads():
            pos = p.GetPosition()
            pads.append((fp.GetReference(), p.GetNetname(), pos.x / MM, pos.y / MM,
                         max(p.GetSize().x, p.GetSize().y) / (2 * MM)))
    laid_segs = []                                             # this-run mutual guard

    def _collide(plan, own_nets, skip_refs=()):
        for (x1, y1, x2, y2, w, _ly) in plan:
            for ref, net, px, py, half in pads:
                if net in own_nets or ref.startswith(tuple(skip_refs) or ("\0",)):
                    continue
                if _seg_pt_d2(px, py, x1, y1, x2, y2) < (w / 2 + half + 0.25) ** 2:
                    return "%s [%s] at (%.1f,%.1f)" % (ref, net, px, py)
            for (net2, a1, b1, a2, b2, w2) in laid_segs:
                if net2 in own_nets:
                    continue
                for t in (0.0, 0.25, 0.5, 0.75, 1.0):
                    qx, qy = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
                    if _seg_pt_d2(qx, qy, a1, b1, a2, b2) < (w / 2 + w2 / 2 + 0.25) ** 2:
                        return "laid rail copper [%s]" % net2
        return None

    def _commit(net, plan):
        for (x1, y1, x2, y2, w, ly) in plan:
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(int(x1 * MM), int(y1 * MM)))
            t.SetEnd(pcbnew.VECTOR2I(int(x2 * MM), int(y2 * MM)))
            t.SetWidth(int(w * MM))
            t.SetLayer(ly)
            ni = netmap.get(net)
            if ni is not None:
                t.SetNet(ni)
            if lock:
                t.SetLocked(True)
            board.Add(t)
            laid_segs.append((net, x1, y1, x2, y2, w))

    j3_ys = [q[2] for rl in rails for q in rl["j3"]]
    j3_bot = max(j3_ys) if j3_ys else 8.0
    report = {}
    for rank, rl in enumerate(rails):
        w = max(1.5, min(6.0, rl["amps"] * 0.25))
        ly = layer_id[rl["face"]]
        own = {rl["src_net"], rl["snk_net"]}
        band_y = j3_bot + 2.5 + rank * (w + 1.2)
        hx, hy = rl["hi"]
        # SOURCE band + spine (rail-fatal on collision)
        xs = [q[1] for q in rl["j3"]] + [hx]
        spine = [(min(xs), band_y, max(xs), band_y, w, ly),
                 (hx, band_y, hx, hy, w, ly)]
        col = _collide(spine, own, skip_refs=("J3", rl["rs"], "TB", "FID"))
        if col:
            report[rl["rs"]] = "REFUSED: src spine vs " + col
            if verbose:
                print("[force-rails] %s (%s) REFUSED: %s"
                      % (rl["rs"], rl["src_net"], col), flush=True)
            continue
        picked, dropped = 0, []
        pin_plans = []
        for pn, px, py, half in rl["j3"]:
            drop = [(px, py, px, band_y, min(w, 1.4), ly)]
            c2 = _collide(drop, own, skip_refs=(rl["rs"], "TB", "FID"))
            if c2 is None:
                pin_plans += drop
                picked += 1
            else:
                dropped.append("J3.%s vs %s" % (pn, c2))
        # SINK: lo -> lower band -> TB drops
        lx, lyy = rl["lo"]
        tb_y = min(q[3] for q in rl["tb"]) if rl["tb"] else lyy + 8.0
        band2 = lyy + 2.0 + rank * 1.2
        band2 = min(band2, tb_y - 2.0)
        txs = [q[2] for q in rl["tb"]] + [lx]
        snk = [(lx, lyy, lx, band2, w, ly),
               (min(txs), band2, max(txs), band2, w, ly)]
        for _r, _pn, tx, ty, _h in rl["tb"]:
            snk.append((tx, band2, tx, ty, w, ly))
        c3 = _collide(snk, own, skip_refs=("J3", rl["rs"], "TB", "FID"))
        if c3:
            report[rl["rs"]] = "REFUSED: snk spine vs " + c3
            if verbose:
                print("[force-rails] %s (%s) REFUSED snk: %s"
                      % (rl["rs"], rl["snk_net"], c3), flush=True)
            continue
        _commit(rl["src_net"], spine + pin_plans)
        _commit(rl["snk_net"], snk)
        report[rl["rs"]] = {"segs": len(spine) + len(pin_plans) + len(snk),
                            "pins": "%d/%d" % (picked, len(rl["j3"])),
                            "w": w, "face": rl["face"],
                            "dropped_pins": dropped}
        if verbose:
            print("[force-rails] %s %s->%s laid: %d segs, pins %d/%d, w=%.1f on %s%s"
                  % (rl["rs"], rl["src_net"], rl["snk_net"],
                     report[rl["rs"]]["segs"], picked, len(rl["j3"]), w, rl["face"],
                     (" (dropped: %s)" % "; ".join(dropped)) if dropped else ""),
                  flush=True)
    return report
