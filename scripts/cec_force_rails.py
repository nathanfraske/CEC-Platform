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


def plan_rail_chains(rails, j3_bot, *, alt=False):
    """The IDEAL per-rail CHAIN segments -- pure data, THE one geometry source
    (pour-strategy refinement §2.1/§2.4 + §2.3 layer crossing, owner GO
    2026-07-19): the lay commits these (guards adapt), the placement keepouts
    inflate the FACE segments + array sites, the future pour compiler widens
    them. *rails* = the discover_rails entry shape (j3/tb tuples carry a
    trailing THT flag). Segments are 6-tuples (x1,y1,x2,y2,w,tag) with tag
    "face"|"alt".

    alt=True (the 24-pin In2 mode -- single-sided ASSEMBLY, not single-layer
    copper: the board-class inner POWER-ROUTING layer): collection bands, pin
    drops and sink runs live on the ALT layer, connecting J3/TB THT barrels
    DIRECTLY (no via needed at a through pad) and passing legally under SMD
    parts and foreign face copper; only the SMD shunt needs the face -- one
    short face stub per side with a VIA ARRAY (n = max(2, ceil(amps/2)) at the
    2A/via platform class) at the transition. A spine column that would cross
    a FOREIGN alt band row falls back to a face column with its array moved up
    to the band junction. Sink rows rank-stagger (shared-y alt rows of
    different nets would mutually collide). Returns
    {rs: {w, band_y, src, pin_drops, snk, arrays: [(x,y,n,net)]}}."""
    items = []
    for rl in rails:
        w = max(1.5, min(6.0, rl["amps"] * 0.25))
        xs = [q[1] for q in rl["j3"]] + [rl["hi"][0]]
        items.append({"key": rl["rs"], "w": w, "x_lo": min(xs), "x_hi": max(xs)})
    band_ys, _depth = plan_bands(items, j3_bot)
    spans = {}
    for rl, it in zip(rails, items):
        spans[rl["rs"]] = (it["x_lo"], it["x_hi"], band_ys[rl["rs"]],
                           max(1.5, min(6.0, rl["amps"] * 0.25)))
    out = {}
    for rank, rl in enumerate(rails):
        w = max(1.5, min(6.0, rl["amps"] * 0.25))
        band_y = band_ys[rl["rs"]]
        hx, hy = rl["hi"]
        lx, lyy = rl["lo"]
        n_via = max(2, int(math.ceil(rl["amps"] / 2.0)))
        body = "alt" if alt else "face"
        arrays = []
        xs = [q[1] for q in rl["j3"]] + [hx]
        if not alt:
            src = [(min(xs), band_y, max(xs), band_y, w, "face"),
                   (hx, band_y, hx, hy, w, "face")]
        else:
            # spine column: alt unless it crosses a FOREIGN alt band row
            lo_y, hi_y = min(band_y, hy - 3.0), max(band_y, hy - 3.0)
            crossed = any(lo_y < by < hi_y and (bx0 - bw / 2 - 0.5) <= hx <= (bx1 + bw / 2 + 0.5)
                          for k2, (bx0, bx1, by, bw) in spans.items() if k2 != rl["rs"])
            src = [(min(xs), band_y, max(xs), band_y, w, "alt")]
            if crossed:
                src.append((hx, band_y, hx, hy, w, "face"))
                arrays.append((hx, band_y, n_via, rl["src_net"]))
            else:
                src.append((hx, band_y, hx, hy - 3.0, w, "alt"))
                src.append((hx, hy - 3.0, hx, hy, w, "face"))
                arrays.append((hx, hy - 3.0, n_via, rl["src_net"]))
        pin_drops = [(px, py, px, band_y, min(w, 1.4), pn, body)
                     for pn, px, py, _h, _tht in rl["j3"]]
        tb_y = min(q[3] for q in rl["tb"]) if rl["tb"] else lyy + 8.0
        band2 = max(lyy + 1.5, tb_y - 3.0 - (rank * 1.7 if alt else 0.0))
        txs = [q[2] for q in rl["tb"]] + [lx]
        if not alt:
            snk = [(lx, lyy, lx, band2, w, "face"),
                   (min(txs), band2, max(txs), band2, w, "face")]
            snk += [(tx, band2, tx, ty, w, "face") for _r, _pn, tx, ty, _h, _t in rl["tb"]]
        else:
            snk = [(lx, lyy, lx, lyy + 2.5, w, "face"),
                   (lx, lyy + 2.5, lx, band2, w, "alt"),
                   (min(txs), band2, max(txs), band2, w, "alt")]
            snk += [(tx, band2, tx, ty, w, "alt") for _r, _pn, tx, ty, _h, _t in rl["tb"]]
            arrays.append((lx, lyy + 2.5, n_via, rl["snk_net"]))
        out[rl["rs"]] = {"w": w, "band_y": band_y, "src": src,
                         "pin_drops": pin_drops, "snk": snk, "arrays": arrays}
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
               max(p.GetSize().x, p.GetSize().y) / (2 * MM),
               p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH)
              for r, p in pads_by_net[src] if r.startswith("J3")]
        tb = [(r, p.GetPadName(), p.GetPosition().x / MM, p.GetPosition().y / MM,
               max(p.GetSize().x, p.GetSize().y) / (2 * MM),
               p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH)
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


def lay_force_rails(board, *, lock=True, verbose=True, alt_layer=None):
    """Lay the per-rail force copper LOCKED. Returns {rs: report|'REFUSED: ...'}.
    *alt_layer* (e.g. "In2.Cu", the board-class inner POWER-ROUTING layer -- In1
    stays the solid GND plane per the owner's 2026-07-19 ruling): plan in ALT
    mode (bands/sinks on the inner layer, direct into THT barrels, via arrays at
    the SMD shunt stubs). Absent/not-found -> face-only planning (unchanged)."""
    import pcbnew
    rails = discover_rails(board)
    if not rails:
        return {}
    layer_id = {"F.Cu": board.GetLayerID("F.Cu"), "B.Cu": board.GetLayerID("B.Cu")}
    alt_id = board.GetLayerID(alt_layer) if alt_layer else -1
    alt_on = alt_id >= 0
    netmap = {str(k): v for k, v in board.GetNetInfo().NetsByName().items()}

    pads = []                                                  # foreign-guard universe
    for fp in board.GetFootprints():
        for p in fp.Pads():
            pos = p.GetPosition()
            pads.append((fp.GetReference(), p.GetNetname(), pos.x / MM, pos.y / MM,
                         max(p.GetSize().x, p.GetSize().y) / (2 * MM),
                         p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH))
    laid_segs = []                                             # (net, x1,y1,x2,y2, w, tag)
    laid_vias = []                                             # (x, y)

    def _collide(plan, own_nets, skip_refs=()):
        """Layer-aware: an ALT segment passes under SMD pads (face-only copper)
        and foreign face segments; it collides with THT barrels (all layers),
        same-tag laid copper, and laid via barrels. FACE segments collide as
        before (all pads + face copper + vias)."""
        for (x1, y1, x2, y2, w, tag) in plan:
            for ref, net, px, py, half, tht in pads:
                if net in own_nets or ref.startswith(tuple(skip_refs) or ("\0",)):
                    continue
                if tag == "alt" and not tht:
                    continue
                if _seg_pt_d2(px, py, x1, y1, x2, y2) < (w / 2 + half + 0.25) ** 2:
                    return "%s [%s] at (%.1f,%.1f)" % (ref, net, px, py)
            for (net2, a1, b1, a2, b2, w2, tag2) in laid_segs:
                if net2 in own_nets or tag2 != tag:
                    continue
                for t in (0.0, 0.25, 0.5, 0.75, 1.0):
                    qx, qy = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
                    if _seg_pt_d2(qx, qy, a1, b1, a2, b2) < (w / 2 + w2 / 2 + 0.25) ** 2:
                        return "laid rail copper [%s]" % net2
            for (vx, vy) in laid_vias:
                if _seg_pt_d2(vx, vy, x1, y1, x2, y2) < (w / 2 + 0.45 + 0.25) ** 2:
                    return "laid rail via at (%.1f,%.1f)" % (vx, vy)
        return None

    # generated ring-ordered grid (25 sites @1.3mm): the fat rails need real
    # arrays -- 5V@25A -> 13 vias, 3V3@20A -> 10 (2A/via platform class); a
    # 9-site hand list could never seat them (caught by the alt teeth)
    _ARR_OFF = sorted(((dx * 1.3, dy * 1.3) for dx in range(-2, 3)
                       for dy in range(-2, 3)),
                      key=lambda q: (q[0] ** 2 + q[1] ** 2, q))

    def _array_sites(x, y, n, own_nets):
        """n clear through-barrel sites clustered at (x,y), or None (via barrels
        pierce every layer -> clear of ALL pads regardless of tag)."""
        sites = []
        for dx, dy in _ARR_OFF:
            if len(sites) >= n:
                break
            cx, cy = x + dx, y + dy
            ok = all(not (net not in own_nets
                          and (px - cx) ** 2 + (py - cy) ** 2 < (half + 0.45 + 0.25) ** 2)
                     for ref, net, px, py, half, tht in pads)
            ok = ok and all((vx - cx) ** 2 + (vy - cy) ** 2 >= 1.15 ** 2
                            for vx, vy in (laid_vias + sites))
            if ok:
                sites.append((cx, cy))
        return sites if len(sites) >= n else None

    def _layer_of(tag, face_ly):
        return alt_id if (tag == "alt" and alt_on) else face_ly

    def _commit(net, plan, face_ly):
        for (x1, y1, x2, y2, w, tag) in plan:
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(int(x1 * MM), int(y1 * MM)))
            t.SetEnd(pcbnew.VECTOR2I(int(x2 * MM), int(y2 * MM)))
            t.SetWidth(int(w * MM))
            t.SetLayer(_layer_of(tag, face_ly))
            ni = netmap.get(net)
            if ni is not None:
                t.SetNet(ni)
            if lock:
                t.SetLocked(True)
            board.Add(t)
            laid_segs.append((net, x1, y1, x2, y2, w, tag))

    def _commit_array(net, sites):
        for (cx, cy) in sites:
            v = pcbnew.PCB_VIA(board)
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetPosition(pcbnew.VECTOR2I(int(cx * MM), int(cy * MM)))
            v.SetDrill(int(0.5 * MM))
            v.SetWidth(int(0.9 * MM))
            ni = netmap.get(net)
            if ni is not None:
                v.SetNet(ni)
            if lock:
                v.SetLocked(True)
            board.Add(v)
            laid_vias.append((cx, cy))

    j3_ys = [q[2] for rl in rails for q in rl["j3"]]
    j3_bot = max(j3_ys) if j3_ys else 8.0
    # ONE geometry source (§2.1/§2.4/§2.3): the ideal chains (alt mode when the
    # inner power-routing layer exists); guards below ADAPT them, the placement
    # keepouts inflate the same plan's FACE segs + array sites.
    chains = plan_rail_chains(rails, j3_bot, alt=alt_on)
    report = {}
    for rank, rl in enumerate(rails):
        _ch = chains[rl["rs"]]
        w = _ch["w"]
        face_ly = layer_id[rl["face"]]
        own = {rl["src_net"], rl["snk_net"]}
        # VIA ARRAYS first (alt mode; the transitions are essential -- a rail
        # whose array cannot seat refuses loud)
        arr_sites = []
        _arr_fail = None
        for (ax, ay, n_v, a_net) in _ch.get("arrays", ()):
            s_ = _array_sites(ax, ay, n_v, own)
            if s_ is None:
                _arr_fail = "no clear %d-via array at (%.1f,%.1f)" % (n_v, ax, ay)
                break
            arr_sites.append((a_net, s_))
        if _arr_fail:
            report[rl["rs"]] = "REFUSED: " + _arr_fail
            if verbose:
                print("[force-rails] %s REFUSED: %s" % (rl["rs"], _arr_fail), flush=True)
            continue
        # SOURCE band + spine from the plan (rail-fatal on collision)
        spine = list(_ch["src"])
        col = _collide(spine, own, skip_refs=("J3", rl["rs"], "TB", "FID"))
        if col:
            report[rl["rs"]] = "REFUSED: src spine vs " + col
            if verbose:
                print("[force-rails] %s (%s) REFUSED: %s"
                      % (rl["rs"], rl["src_net"], col), flush=True)
            continue
        picked, dropped = 0, []
        pin_plans = []
        for (px, py, x2, y2, dw, pn, dtag) in _ch["pin_drops"]:
            drop = [(px, py, x2, y2, dw, dtag)]
            c2 = _collide(drop, own, skip_refs=(rl["rs"], "TB", "FID"))
            if c2 is None:
                pin_plans += drop
                picked += 1
            else:
                dropped.append("J3.%s vs %s" % (pn, c2))
        # SINK from the plan: lo -> lower band -> TB drops
        snk = list(_ch["snk"])
        c3 = _collide(snk, own, skip_refs=("J3", rl["rs"], "TB", "FID"))
        if c3:
            report[rl["rs"]] = "REFUSED: snk spine vs " + c3
            if verbose:
                print("[force-rails] %s (%s) REFUSED snk: %s"
                      % (rl["rs"], rl["snk_net"], c3), flush=True)
            continue
        _commit(rl["src_net"], spine + pin_plans, face_ly)
        _commit(rl["snk_net"], snk, face_ly)
        for (a_net, s_) in arr_sites:
            _commit_array(a_net, s_)
        n_arr = sum(len(s_) for _n2, s_ in arr_sites)
        report[rl["rs"]] = {"segs": len(spine) + len(pin_plans) + len(snk),
                            "pins": "%d/%d" % (picked, len(rl["j3"])),
                            "vias": n_arr, "alt": alt_on,
                            "w": w, "face": rl["face"],
                            "dropped_pins": dropped}
        if verbose:
            print("[force-rails] %s %s->%s laid: %d segs + %d array via(s), "
                  "pins %d/%d, w=%.1f%s%s"
                  % (rl["rs"], rl["src_net"], rl["snk_net"],
                     report[rl["rs"]]["segs"], n_arr, picked, len(rl["j3"]), w,
                     (" [alt=%s]" % alt_layer) if alt_on else "",
                     (" (dropped: %s)" % "; ".join(dropped)) if dropped else ""),
                  flush=True)
    return report
