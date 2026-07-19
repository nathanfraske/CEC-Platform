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


def plan_bands(items, j3_bot, *, y0_off=2.5):
    """Greedy interval-packed BAND rows (shared by the lay and the placement
    keepouts -- one geometry, two consumers). *items* = [{key, w, x_lo, x_hi}];
    x-spans on a shared row must clear each other by the TRACKS' half-widths +
    1.0mm (the audit's width-blind landmine: a 1mm CENTERLINE gap between two
    multi-mm tracks is copper-on-copper). Returns ({key: band_center_y},
    total_depth).

    Row order: NARROWEST span first => the WIDEST bands land on the LOWEST
    rows (closest to the shunts). Measured consequence (first alt lay,
    2026-07-19): pin drops descend from the J3 field to their own row -- with
    a full-width band (3V3 spans the whole connector) on the TOP row, every
    other rail's drops crossed it on the same alt layer and refused;
    widest-lowest means a rail's drops stop at their row before reaching any
    wider band."""
    ranks, assign = [], {}
    for it in sorted(items, key=lambda q: ((q["x_hi"] - q["x_lo"]), q["key"])):
        hw = it["w"] / 2.0
        for ri, occ in enumerate(ranks):
            if all(it["x_hi"] + hw + w_o / 2.0 + 1.0 <= a
                   or b + hw + w_o / 2.0 + 1.0 <= it["x_lo"]
                   for a, b, w_o in occ):
                occ.append((it["x_lo"], it["x_hi"], it["w"]))
                assign[it["key"]] = ri
                break
        else:
            ranks.append([(it["x_lo"], it["x_hi"], it["w"])])
            assign[it["key"]] = len(ranks) - 1
    ys, y = {}, j3_bot + y0_off
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
    # OUTLIER TRIM (2026-07-19: ATX puts one 3V3 pin 43mm from its cluster --
    # the full-width band it forced always sank to the DEEPEST row, straight
    # into the tucked jack's contact row; trimmed, the cluster band packs into
    # the shallow rows). A pin > 18mm from the shunt column is dropped from
    # the band span AND from the pickups (reported), never below 1 kept pin.
    trimmed = {}
    items = []
    for rl in rails:
        w = max(1.5, min(6.0, rl["amps"] * 0.25))
        hx0 = rl["hi"][0]
        keep = [q for q in rl["j3"] if abs(q[1] - hx0) <= 18.0]
        if keep and len(keep) < len(rl["j3"]):
            trimmed[rl["rs"]] = [q for q in rl["j3"] if q not in keep]
        else:
            keep = rl["j3"]
        xs = [q[1] for q in keep] + [hx0]
        items.append({"key": rl["rs"], "w": w, "x_lo": min(xs), "x_hi": max(xs)})
    band_ys, _depth = plan_bands(items, j3_bot)
    spans = {}
    for rl, it in zip(rails, items):
        spans[rl["rs"]] = (it["x_lo"], it["x_hi"], band_ys[rl["rs"]],
                           max(1.5, min(6.0, rl["amps"] * 0.25)))
    # SINK span packing (width-aware, rows stack UP from the TB field)
    _sink_items = []
    for rl in rails:
        _sw = max(1.5, min(6.0, rl["amps"] * 0.25))
        _sxs = [q[2] for q in rl["tb"]] + [rl["lo"][0]]
        _sink_items.append({"key": rl["rs"], "w": _sw,
                            "x_lo": min(_sxs), "x_hi": max(_sxs)})
    _sink_ys, _ = plan_bands(_sink_items, 0.0, y0_off=0.0)
    out = {}
    for rank, rl in enumerate(rails):
        w = max(1.5, min(6.0, rl["amps"] * 0.25))
        # face-stub width ceiling = the shunt pad's long dim (the pad is the
        # neck; the via array carries the layer transition -- a 3mm stub at pad
        # width is the same current class as the pad itself)
        sw = min(w, rl.get("pad_w") or w)
        band_y = band_ys[rl["rs"]]
        hx, hy = rl["hi"]
        lx, lyy = rl["lo"]
        n_via = max(2, int(math.ceil(rl["amps"] / 2.0)))
        body = "alt" if alt else "face"
        arrays = []
        _trim = trimmed.get(rl["rs"], ())
        j3_kept = [q for q in rl["j3"] if q not in _trim]
        xs = [q[1] for q in j3_kept] + [hx]
        if not alt:
            # the descent's LAST reach onto the HI pad clamps to pad width --
            # same physics as the alt-mode stub (the pad is the neck; a fat
            # tail's radius can reach the LO pad = a shunt bypass, surfaced
            # by the honest collider once the shunt's own pads stopped being
            # ref-skipped)
            src = [(min(xs), band_y, max(xs), band_y, w, "face"),
                   (hx, band_y, hx, hy - 3.0, w, "face"),
                   (hx, hy - 3.0, hx, hy, sw, "face")]
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
                src.append((hx, hy - 3.0, hx, hy, sw, "face"))
                arrays.append((hx, hy - 3.0, n_via, rl["src_net"]))
        pin_drops = [(px, py, px, band_y, min(w, 1.4), pn, body)
                     for pn, px, py, _h, _tht in j3_kept]
        tb_y = min(q[3] for q in rl["tb"]) if rl["tb"] else lyy + 8.0
        # sink rows: the SAME width-aware interval packing as the source bands
        # (audit landmine: the fixed 1.7mm rank stagger let crossing multi-mm
        # sink spans overlap). _sink_ys computed once below the loop entry.
        # TB drops carry PER-JOINT current, not the rail total -- graded down
        # (2026-07-19: the full-width face drop grazed a neighbor cell's cap
        # at 2.8 vs 3.75mm; per-joint share needs ~2mm at the 2oz class).
        band2 = max(lyy + 1.5, tb_y - 2.0 - _sink_ys.get(rl["rs"], 1.0))
        txs = [q[2] for q in rl["tb"]] + [lx]
        dwt = max(2.0, w / max(1, len(rl["tb"])))
        if not alt:
            _mid = min(lyy + 3.0, band2)         # pad-width tail off the LO pad
            snk = [(lx, lyy, lx, _mid, sw, "face"),   # (mirror of the src clamp)
                   (lx, _mid, lx, band2, w, "face"),
                   (min(txs), band2, max(txs), band2, w, "face")]
            snk += [(tx, band2, tx, ty, dwt, "face") for _r, _pn, tx, ty, _h, _t in rl["tb"]]
        else:
            snk = [(lx, lyy, lx, lyy + 2.5, sw, "face"),
                   (lx, lyy + 2.5, lx, band2, w, "alt"),
                   (min(txs), band2, max(txs), band2, w, "alt")]
            snk += [(tx, band2, tx, ty, dwt, "alt") for _r, _pn, tx, ty, _h, _t in rl["tb"]]
            arrays.append((lx, lyy + 2.5, n_via, rl["snk_net"]))
        out[rl["rs"]] = {"w": w, "band_y": band_y, "src": src,
                         "pin_drops": pin_drops, "snk": snk, "arrays": arrays,
                         "trimmed": [q[0] for q in _trim],
                         # the LO descent column + the sink band row (placement
                         # reserves both so the lay's FACE-RETRY escape stays
                         # open -- 2026-07-19: a cluster cap 2.8mm off the
                         # column, then a buffer IC under the band row, killed
                         # the alt sink AND its face retry in turn)
                         "snk_desc": (lx, lyy, band2, w),
                         "snk_band": (min(txs), max(txs), band2, w)}
    return out


def _seg_pt_d2(x, y, sx, sy, ex, ey):
    dx, dy = ex - sx, ey - sy
    L2 = dx * dx + dy * dy
    if L2 <= 1e-12:
        return (x - sx) ** 2 + (y - sy) ** 2
    t = max(0.0, min(1.0, ((x - sx) * dx + (y - sy) * dy) / L2))
    px, py = sx + t * dx, sy + t * dy
    return (x - px) ** 2 + (y - py) ** 2


def _seg_seg_d2(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2):
    """Exact min distance^2 between two segments (audit landmine: the 5-point
    sampling missed thin crossings). Intersection -> 0; else min of the four
    endpoint-to-segment distances (exact for non-intersecting segments)."""
    d1x, d1y = ax2 - ax1, ay2 - ay1
    d2x, d2y = bx2 - bx1, by2 - by1
    den = d1x * d2y - d1y * d2x
    if abs(den) > 1e-12:
        t = ((bx1 - ax1) * d2y - (by1 - ay1) * d2x) / den
        u = ((bx1 - ax1) * d1y - (by1 - ay1) * d1x) / den
        if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
            return 0.0
    return min(_seg_pt_d2(ax1, ay1, bx1, by1, bx2, by2),
               _seg_pt_d2(ax2, ay2, bx1, by1, bx2, by2),
               _seg_pt_d2(bx1, by1, ax1, ay1, ax2, ay2),
               _seg_pt_d2(bx2, by2, ax1, ay1, ax2, ay2))


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
            # the shunt pad's long dim: the face stub's width ceiling (the pad
            # IS the neck -- a stub wider than its landing pad buys no copper
            # and grazes the sense cell's own parts; probe: U65V1 3.5mm off a
            # 6mm stub)
            "pad_w": max(hi_p.GetSize().x, hi_p.GetSize().y) / MM,
            "j3": sorted(j3, key=lambda q: q[1]), "tb": sorted(tb, key=lambda q: q[2]),
        })
    rails.sort(key=lambda rl: rl["hi"][0])                     # rank by shunt column
    return rails


def lay_force_rails(board, *, lock=True, verbose=True, alt_layer=None,
                    mirror_bcu=False):
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
    # PRE-INDEX existing LOCKED copper (audit landmine: the collider started
    # empty while blueprint-cell copper is laid BEFORE the rails on the same
    # board) -- tagged by layer class so the layer-aware checks apply.
    _alt_ln = alt_layer or ""
    for _t0 in board.GetTracks():
        if not _t0.IsLocked():
            continue
        if _t0.Type() == pcbnew.PCB_VIA_T:
            _p0 = _t0.GetPosition()
            laid_vias.append((_p0.x / MM, _p0.y / MM))
        else:
            _ln = board.GetLayerName(_t0.GetLayer())
            _tag0 = "alt" if _ln == _alt_ln else "face"
            _s0, _e0 = _t0.GetStart(), _t0.GetEnd()
            laid_segs.append((_t0.GetNetname() or "", _s0.x / MM, _s0.y / MM,
                              _e0.x / MM, _e0.y / MM, _t0.GetWidth() / MM, _tag0))

    def _collide(plan, own_nets, skip_refs=()):
        """Layer-aware: an ALT segment passes under SMD pads (face-only copper)
        and foreign face segments; it collides with THT barrels (all layers),
        same-tag laid copper, and laid via barrels. FACE segments collide as
        before (all pads + face copper + vias)."""
        for (x1, y1, x2, y2, w, tag) in plan:
            for ref, net, px, py, half, tht in pads:
                if net in own_nets or ref.startswith(tuple(skip_refs) or ("\0",)):
                    continue
                if tag in ("alt", "back") and not tht:
                    continue
                if _seg_pt_d2(px, py, x1, y1, x2, y2) < (w / 2 + half + 0.25) ** 2:
                    return ("%s [%s] at (%.1f,%.1f) vs plan (%.1f,%.1f)-(%.1f,%.1f)"
                            % (ref, net, px, py, x1, y1, x2, y2))
            for (net2, a1, b1, a2, b2, w2, tag2) in laid_segs:
                if net2 in own_nets or tag2 != tag:
                    continue
                # exact seg-seg distance (audit landmine: 5-point sampling
                # missed thin crossings)
                if _seg_seg_d2(x1, y1, x2, y2, a1, b1, a2, b2) < (w / 2 + w2 / 2 + 0.25) ** 2:
                    return ("laid copper [%s] (%.1f,%.1f)-(%.1f,%.1f) vs plan "
                            "(%.1f,%.1f)-(%.1f,%.1f)"
                            % (net2, a1, b1, a2, b2, x1, y1, x2, y2))
            for (vx, vy) in laid_vias:
                if _seg_pt_d2(vx, vy, x1, y1, x2, y2) < (w / 2 + 0.45 + 0.25) ** 2:
                    return "laid via at (%.1f,%.1f)" % (vx, vy)
        return None

    # generated ring-ordered grid (25 sites @1.3mm): the fat rails need real
    # arrays -- 5V@25A -> 13 vias, 3V3@20A -> 10 (2A/via platform class); a
    # 9-site hand list could never seat them (caught by the alt teeth)
    _ARR_OFF = sorted(((dx * 1.3, dy * 1.3) for dx in range(-2, 3)
                       for dy in range(-2, 3)),
                      key=lambda q: (q[0] ** 2 + q[1] ** 2, q))

    _bb = board.GetBoardEdgesBoundingBox()
    _bx0, _by0 = _bb.GetLeft() / MM, _bb.GetTop() / MM
    _bx1, _by1 = _bb.GetRight() / MM, _bb.GetBottom() / MM
    # a board with no Edge.Cuts (synthetic fixtures) yields a degenerate bbox --
    # the edge-margin test must not reject every site then
    _bb_ok = (_bx1 - _bx0) > 2.0 and (_by1 - _by0) > 2.0

    def _array_sites(x, y, n, own_nets, pending=()):
        """n clear through-barrel sites clustered at (x,y), or None. Via barrels
        pierce every layer -> clear of ALL pads regardless of tag, ALL laid
        copper on any tag (audit landmine: tracks were unchecked), the board
        edge (>=1.2mm), prior vias, and *pending* same-rail array sites."""
        sites = []
        occupied = list(laid_vias) + [q for arr in pending for q in arr]
        for dx, dy in _ARR_OFF:
            if len(sites) >= n:
                break
            cx, cy = x + dx, y + dy
            if _bb_ok and not (_bx0 + 1.2 <= cx <= _bx1 - 1.2
                               and _by0 + 1.2 <= cy <= _by1 - 1.2):
                continue
            ok = all(not (net not in own_nets
                          and (px - cx) ** 2 + (py - cy) ** 2 < (half + 0.45 + 0.25) ** 2)
                     for ref, net, px, py, half, tht in pads)
            ok = ok and all(not (net2 not in own_nets
                                 and _seg_pt_d2(cx, cy, a1, b1, a2, b2)
                                 < (w2 / 2 + 0.45 + 0.25) ** 2)
                            for (net2, a1, b1, a2, b2, w2, _tg) in laid_segs)
            ok = ok and all((vx - cx) ** 2 + (vy - cy) ** 2 >= 1.15 ** 2
                            for vx, vy in (occupied + sites))
            if ok:
                sites.append((cx, cy))
        return sites if len(sites) >= n else None

    def _layer_of(tag, face_ly):
        if tag == "back":
            return layer_id["B.Cu"]
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

    def _commit_array(net, sites, face_ly):
        # LANDING PATCHES (owner, wave-15 render: "the via fields are clipped
        # out of the pours"): every via must land on same-net copper on BOTH
        # layers -- the plan's stub/band segs don't cover the full site spread.
        # Try one bbox patch per layer (collide-checked, own-net exempt); fall
        # back to per-site pads where the full patch is contended.
        if sites:
            _pxs = [s[0] for s in sites]
            _pys = [s[1] for s in sites]
            _px0, _px1, _py0, _py1 = min(_pxs), max(_pxs), min(_pys), max(_pys)
            _pm = 0.65
            for _ptag in (("face", "alt") if alt_on else ("face",)):
                if _px1 - _px0 >= _py1 - _py0:
                    _patch = [(_px0 - _pm, (_py0 + _py1) / 2.0,
                               _px1 + _pm, (_py0 + _py1) / 2.0,
                               (_py1 - _py0) + 2 * _pm, _ptag)]
                else:
                    _patch = [((_px0 + _px1) / 2.0, _py0 - _pm,
                               (_px0 + _px1) / 2.0, _py1 + _pm,
                               (_px1 - _px0) + 2 * _pm, _ptag)]
                if _collide(_patch, {net}) is None:
                    _commit(net, _patch, face_ly)
                else:
                    for (cx, cy) in sites:
                        _p1 = [(cx - _pm, cy, cx + _pm, cy, 2 * _pm, _ptag)]
                        if _collide(_p1, {net}) is None:
                            _commit(net, _p1, face_ly)
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
        # PER-SIDE own nets (audit landmine: the two-net own set let source
        # copper ignore sink-net pads and vice versa)
        own_src, own_snk = {rl["src_net"]}, {rl["snk_net"]}
        hx, hy = rl["hi"]
        band_y = _ch["band_y"]
        _plan_arrays = list(_ch.get("arrays", ()))
        _src_arr = next(((ax, ay, nv) for (ax, ay, nv, an) in _plan_arrays
                         if an == rl["src_net"]), None)
        _oth_arrs = [(ax, ay, nv, an) for (ax, ay, nv, an) in _plan_arrays
                     if an != rl["src_net"]]
        # LIVE SPAN (2026-07-19: the tucked jack's contact field shadows the
        # 3V3 cluster pins at every y -- a band stretched to unpickable pins
        # dies on the jack while the rail itself could lay): pre-test each
        # planned pickup with the same drop shapes; a pin with NO viable drop
        # leaves the band span, which shrinks to the pins that can actually
        # join (+ the shunt column).
        _xs_live = [hx]
        for (px, py, x2, y2, dw, pn, dtag) in _ch["pin_drops"]:
            for _ddx in (0.0, 2.1, -2.1, 1.8, -1.8):
                if _ddx == 0.0:
                    _dtry = [(px, py, x2, y2, dw, dtag)]
                else:
                    _dw2 = min(dw, 1.0)
                    _dtry = [(px, py, px + _ddx, py, _dw2, dtag),
                             (px + _ddx, py, px + _ddx, y2, _dw2, dtag)]
                if _collide(_dtry, own_src, skip_refs=("FID",)) is None:
                    _xs_live.append(px)
                    break
        # BAND-WIDTH shrink (2026-07-19: a pin can pass the drop-width pre-test
        # while the FULL-width band still dies at its thin extremity -- RS3's
        # w=5 band's 4.35mm radius vs J1's VCC pad; the pin's 6A reach doesn't
        # need rail width): iteratively drop the extreme pin farther from the
        # shunt column until the band itself guards clean.
        def _band_ok(xs):
            if max(xs) - min(xs) < 0.1:
                return True
            _b = [(min(xs), band_y, max(xs), band_y, w,
                   "alt" if alt_on else "face")]
            return _collide(_b, own_src, skip_refs=("FID",)) is None
        while len(_xs_live) > 1 and not _band_ok(_xs_live):
            _lo_e, _hi_e = min(_xs_live), max(_xs_live)
            _cut = _lo_e if abs(_lo_e - hx) >= abs(_hi_e - hx) else _hi_e
            if _cut == hx:
                break
            _xs_live.remove(_cut)

        def _respan(segs):
            """Clamp the (single) band segment of a source shape to the live span."""
            o = []
            for (x1, y1, x2, y2, w2, tg) in segs:
                if y1 == y2 == band_y and abs(x2 - x1) > 0.1:
                    o.append((min(_xs_live), band_y, max(_xs_live), band_y, w2, tg))
                else:
                    o.append((x1, y1, x2, y2, w2, tg))
            return o
        # SOURCE variants: (segs, src_array_pos). A colliding FACE-fallback
        # column retries JOGGED variants around the cell envelope (audit
        # finding 4: the full-width fallback ran straight through the shunt-pad
        # column where the one-sided cell bank sits): the column offsets
        # sideways, the alt band EXTENDS to the jog x, the via array moves to
        # the jog junction, and a short axial elbow re-enters the pad.
        _src_variants = [(_respan(list(_ch["src"])), _src_arr, None)]
        if alt_on and any(tg == "face" and abs(y2 - y1) > 4.0
                          for (x1, y1, x2, y2, _w2, tg) in _ch["src"]):
            _alt_only = [s for s in _ch["src"] if s[5] != "face"]
            _bxs = [q for s in _alt_only for q in (s[0], s[2])]
            for _dxo in (3.6, -3.6, 5.2, -5.2):
                _jx = hx + _dxo
                _v = list(_alt_only)
                if _bxs and not (min(_bxs) <= _jx <= max(_bxs)):
                    _near = min(_bxs, key=lambda q: abs(q - _jx))
                    _v.append((_near, band_y, _jx, band_y, w, "alt"))
                _v += [(_jx, band_y, _jx, hy - 2.0, w, "face"),
                       (_jx, hy - 2.0, hx, hy - 2.0, w, "face"),
                       (hx, hy - 2.0, hx, hy, w, "face")]
                _sa = (_jx, band_y, _src_arr[2]) if _src_arr else None
                _src_variants.append((_v, _sa, None))
        if alt_on:
            # LAST-RESORT plain-FACE source (pour doc §2.3 layer stagger; s0d
            # probe: ATX interleaves 5V/12V pins at the SAME x, so an earlier
            # rail's laid In2 pin drops contend the next rail's In2 band --
            # stagger the loser onto the face. THT pickups need no via array;
            # pin drops follow onto the face (tag threaded per-variant).
            _face_src = [(min(_xs_live), band_y, max(_xs_live), band_y, w, "face"),
                         (hx, band_y, hx, hy, w, "face")]
            _src_variants.append((_face_src, None, "face"))
            # THIRD ESCAPE TIER: B.Cu (owner observation 2026-07-19: the
            # bottom was only a mirror, "not another via-around layer") --
            # the default alt shape retagged onto the back, THT pickups
            # pierce natively, the same via array bonds the SMD stub end.
            _back_src = [(x1, y1, x2, y2, w2, ("back" if tg == "alt" else tg))
                         for (x1, y1, x2, y2, w2, tg) in _respan(list(_ch["src"]))]
            _src_variants.append((_back_src, _src_arr, "back"))
        col, spine, arr_sites = "no plan", None, []
        _drops_tag = None
        _vreasons = []                       # per-variant refusal trace (audit:
        for _vi, (_sv, _sa, _dtag_v) in enumerate(_src_variants):  # the message showed only the LAST
            col = _collide(_sv, own_src, skip_refs=("FID",))
            if col is not None:
                _vreasons.append("v%d %s" % (_vi, col))
                continue
            _trial, _ok = [], True
            if _sa is not None:
                s_ = _array_sites(_sa[0], _sa[1], _sa[2], {rl["src_net"]})
                if s_ is None:
                    col = "no clear %d-via src array at (%.1f,%.1f)" % (_sa[2], _sa[0], _sa[1])
                    _ok = False
                else:
                    _trial.append((rl["src_net"], s_))
            if _ok:
                for (ax, ay, nv, an) in _oth_arrs:
                    s_ = _array_sites(ax, ay, nv, {an},
                                      pending=[s for _n2, s in _trial])
                    if s_ is None:
                        col = "no clear %d-via array at (%.1f,%.1f)" % (nv, ax, ay)
                        _ok = False
                        break
                    _trial.append((an, s_))
            if _ok:
                spine, arr_sites, _drops_tag = _sv, _trial, _dtag_v
                break
            _vreasons.append("v%d %s" % (_vi, col))
        if spine is None:
            col = "; ".join(_vreasons) if _vreasons else col
            report[rl["rs"]] = "REFUSED: src " + col
            if verbose:
                print("[force-rails] %s (%s) REFUSED: %s"
                      % (rl["rs"], rl["src_net"], col), flush=True)
            continue
        picked, dropped = 0, []
        for _tpn in _ch.get("trimmed", ()):
            dropped.append("J3.%s [trimmed: >18mm span outlier]" % _tpn)
        pin_plans = []
        for (px, py, x2, y2, dw, pn, dtag) in _ch["pin_drops"]:
            if not (min(_xs_live) - 0.1 <= px <= max(_xs_live) + 0.1):
                dropped.append("J3.%s [band shrunk away from x=%.1f]" % (pn, px))
                continue                         # its drop would dangle off-band
            _dt = _drops_tag or dtag
            # straight drop first; else MID-COLUMN DOGLEGS (s0e probe: ATX
            # stacks two rows at the SAME x, so a top-row pin's straight drop
            # dies on the bottom-row barrel 1.8mm beneath -- escape
            # horizontally at pad y between the same-row barrels, descend on
            # the half-pitch column). The collider verifies each candidate.
            c2, _dreasons = None, []
            for _ddx in (0.0, 2.1, -2.1, 1.8, -1.8):
                if _ddx == 0.0:
                    drop = [(px, py, x2, y2, dw, _dt)]
                else:
                    # dogleg width 1.0: the Mini-Fit barrel half (1.18) + 0.25
                    # clearance leaves exactly ~1.93mm to the half-pitch column
                    # -- a 1.4 drop misses it by 0.03mm (measured, s0f). Short
                    # per-pin stub; the thermal gate judges the result.
                    _dw2 = min(dw, 1.0)
                    drop = [(px, py, px + _ddx, py, _dw2, _dt),
                            (px + _ddx, py, px + _ddx, y2, _dw2, _dt)]
                c2 = _collide(drop, own_src, skip_refs=("FID",))
                if c2 is None:
                    break
                _dreasons.append("%+.1f:%s" % (_ddx, c2))
            if c2 is None:
                pin_plans += drop
                picked += 1
            else:
                dropped.append("J3.%s [%s]" % (pn, "; ".join(_dreasons)))
        # SINK from the plan: lo -> lower band -> TB drops. FACE-STAGGER
        # retry (2026-07-19, the source-side medicine applied to the sink:
        # TB fields interleave in x, so one rail's alt sink drop crosses the
        # next rail's alt sink band -- measured at 3.95 vs 4.0mm on W74):
        # the whole sink moves to the face; THT TB barrels need no array.
        snk = list(_ch["snk"])
        c3 = _collide(snk, own_snk, skip_refs=("FID",))
        _snk_arr_on = True
        if c3 and alt_on:
            _snk_face = [(x1, y1, x2, y2, w2, "face")
                         for (x1, y1, x2, y2, w2, _tg) in _ch["snk"]]
            c3b = _collide(_snk_face, own_snk, skip_refs=("FID",))
            if c3b is None:
                snk, c3, _snk_arr_on = _snk_face, None, False
            else:
                # THIRD ESCAPE TIER: B.Cu (the via-around rung -- alt segs
                # retagged back; TB barrels pierce, the LO-stub array bonds)
                _snk_back = [(x1, y1, x2, y2, w2, ("back" if _tg == "alt" else _tg))
                             for (x1, y1, x2, y2, w2, _tg) in _ch["snk"]]
                c3c = _collide(_snk_back, own_snk, skip_refs=("FID",))
                if c3c is None:
                    snk, c3 = _snk_back, None
                else:
                    c3 = c3 + "; face retry: " + c3b + "; back retry: " + c3c
        if c3:
            report[rl["rs"]] = "REFUSED: snk spine vs " + c3
            if verbose:
                print("[force-rails] %s (%s) REFUSED snk: %s"
                      % (rl["rs"], rl["snk_net"], c3), flush=True)
            continue
        _commit(rl["src_net"], spine + pin_plans, face_ly)
        _commit(rl["snk_net"], snk, face_ly)
        _bcu_twins = 0
        if mirror_bcu and alt_on:
            # B.Cu TRUNK MIRROR (owner ask 2026-07-19: "are the large pours/
            # traces able to go to the bottom layer too?"): on a single-sided-
            # assembly board B.Cu is free real estate -- twin every committed
            # ALT (In2) trunk seg onto B.Cu, guarded per-seg (THT barrels +
            # cross-net locked copper; SMD pads are front-only). The through
            # J3/TB barrels and the via arrays bond the layers, doubling the
            # trunk cross-section. Best-effort: a colliding twin is skipped,
            # the In2 original stands.
            for (_net_m, _segs_m) in ((rl["src_net"], spine + pin_plans),
                                      (rl["snk_net"], snk)):
                for (x1, y1, x2, y2, w2, tg) in _segs_m:
                    if tg == "alt":
                        _mt = "back"
                    elif tg == "back":       # a trunk that took the back
                        _mt = "alt"          # escape rung mirrors up to In2
                    else:
                        continue
                    _tw = [(x1, y1, x2, y2, w2, _mt)]
                    if _collide(_tw, {_net_m}, skip_refs=("FID",)) is None:
                        _commit(_net_m, _tw, face_ly)
                        _bcu_twins += 1
        if not _snk_arr_on:          # face-staggered sink: no layer transition,
            arr_sites = [(n, s_) for (n, s_) in arr_sites   # its array would dangle
                         if n != rl["snk_net"]]
        for (a_net, s_) in arr_sites:
            _commit_array(a_net, s_, face_ly)
        n_arr = sum(len(s_) for _n2, s_ in arr_sites)
        report[rl["rs"]] = {"segs": len(spine) + len(pin_plans) + len(snk),
                            "pins": "%d/%d" % (picked, len(rl["j3"])),
                            "vias": n_arr, "alt": alt_on,
                            "bcu_twins": _bcu_twins,
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
