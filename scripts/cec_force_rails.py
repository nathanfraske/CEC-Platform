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


def plan_bands(items, j3_bot):
    """Greedy interval-packed BAND rows (shared by the lay and the placement
    keepouts -- one geometry, two consumers). *items* = [{key, w, x_lo, x_hi}];
    bands whose x-spans clear each other by >=1.0mm SHARE a row (the naive
    one-rank-per-rail stack measured ~26mm deep and walled the 24-pin's MCU out
    of its own board). Returns ({key: band_center_y}, total_depth). Rows are
    packed widest-span-first; a row's height is its widest member."""
    ranks, assign = [], {}
    for it in sorted(items, key=lambda q: (-(q["x_hi"] - q["x_lo"]), q["key"])):
        for ri, occ in enumerate(ranks):
            if all(it["x_hi"] + 1.0 < a or b + 1.0 < it["x_lo"] for a, b, _w in occ):
                occ.append((it["x_lo"], it["x_hi"], it["w"]))
                assign[it["key"]] = ri
                break
        else:
            ranks.append([(it["x_lo"], it["x_hi"], it["w"])])
            assign[it["key"]] = len(ranks) - 1
    ys, y = {}, j3_bot + 2.5
    for ri, occ in enumerate(ranks):
        h = max(w for _a, _b, w in occ)
        ys[ri] = y + h / 2.0
        y += h + 1.2
    return {k: ys[ri] for k, ri in assign.items()}, (y - j3_bot)


def plan_rail_chains(rails, j3_bot):
    """The IDEAL per-rail CHAIN segments -- pure data, THE one geometry source
    (pour-strategy refinement §2.1/§2.4, owner GO 2026-07-19): the lay commits
    these (with collider guards + dogleg fallbacks), the placement keepouts
    inflate them, and the future pour compiler widens them. *rails* is the
    discover_rails entry shape (rs/src_net/snk_net/amps/hi/lo/j3/tb; the
    placement side builds the same shape from netlist+anchors). Returns
    {rs: {w, band_y, src: [(x1,y1,x2,y2,w)], pin_drops: [...], snk: [...]}}."""
    items = []
    for rl in rails:
        w = max(1.5, min(6.0, rl["amps"] * 0.25))
        xs = [q[1] for q in rl["j3"]] + [rl["hi"][0]]
        items.append({"key": rl["rs"], "w": w, "x_lo": min(xs), "x_hi": max(xs)})
    band_ys, _depth = plan_bands(items, j3_bot)
    out = {}
    for rl in rails:
        w = max(1.5, min(6.0, rl["amps"] * 0.25))
        band_y = band_ys[rl["rs"]]
        hx, hy = rl["hi"]
        lx, lyy = rl["lo"]
        xs = [q[1] for q in rl["j3"]] + [hx]
        src = [(min(xs), band_y, max(xs), band_y, w),
               (hx, band_y, hx, hy, w)]
        pin_drops = [(px, py, px, band_y, min(w, 1.4), pn)
                     for pn, px, py, _h in rl["j3"]]
        tb_y = min(q[3] for q in rl["tb"]) if rl["tb"] else lyy + 8.0
        band2 = max(lyy + 1.5, tb_y - 3.0)
        txs = [q[2] for q in rl["tb"]] + [lx]
        snk = [(lx, lyy, lx, band2, w),
               (min(txs), band2, max(txs), band2, w)]
        snk += [(tx, band2, tx, ty, w) for _r, _pn, tx, ty, _h in rl["tb"]]
        out[rl["rs"]] = {"w": w, "band_y": band_y, "src": src,
                         "pin_drops": pin_drops, "snk": snk}
    return out


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
    # ONE geometry source (§2.1/§2.4): the ideal chains; guards/doglegs below
    # ADAPT them, the placement keepouts inflate the same plan.
    chains = plan_rail_chains(rails, j3_bot)
    report = {}
    for rank, rl in enumerate(rails):
        _ch = chains[rl["rs"]]
        w = _ch["w"]
        ly = layer_id[rl["face"]]
        own = {rl["src_net"], rl["snk_net"]}
        band_y = _ch["band_y"]
        hx, hy = rl["hi"]
        # SOURCE band + spine from the plan (rail-fatal on collision)
        spine = [(x1, y1, x2, y2, sw, ly) for (x1, y1, x2, y2, sw) in _ch["src"]]
        col = _collide(spine, own, skip_refs=("J3", rl["rs"], "TB", "FID"))
        if col:
            report[rl["rs"]] = "REFUSED: src spine vs " + col
            if verbose:
                print("[force-rails] %s (%s) REFUSED: %s"
                      % (rl["rs"], rl["src_net"], col), flush=True)
            continue
        picked, dropped = 0, []
        pin_plans = []
        for (px, py, x2, y2, dw, pn) in _ch["pin_drops"]:
            drop = [(px, py, x2, y2, dw, ly)]
            c2 = _collide(drop, own, skip_refs=(rl["rs"], "TB", "FID"))
            if c2 is None:
                pin_plans += drop
                picked += 1
            else:
                dropped.append("J3.%s vs %s" % (pn, c2))
        # SINK from the plan: lo -> shared lower band -> TB drops
        snk = [(x1, y1, x2, y2, sw, ly) for (x1, y1, x2, y2, sw) in _ch["snk"]]
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
