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
# 5V 20A / 3V3 20A / 12V 12A / 5VSB 3A) and per-rail FACE (the placer's
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
import cec_fab_profile as cec_fab
import cec_via_field_layout

MM = 1e6

RAIL_AMPS = (("5VSB", 3.0), ("3V3", 20.0), ("12V", 12.0), ("5V", 20.0))


def _amps_for(nets):
    s = " ".join(n.upper() for n in nets)
    for key, a in RAIL_AMPS:
        if key in s:
            return a
    return 10.0


def _sink_priority(rl):
    """Critical-first ordering for terminal-side rail collectors."""
    xs = [q[2] for q in rl.get("tb", ())] + [rl["lo"][0]]
    span = max(xs) - min(xs) if xs else 0.0
    return (-span, -float(rl.get("amps", 0.0)), rl["rs"])


def plan_bands(items, j3_bot, *, y0_off=2.5, widest_first=False):
    """Greedy interval-packed BAND rows (shared by the lay and the placement
    keepouts -- one geometry, two consumers). *items* = [{key, w, x_lo, x_hi}];
    x-spans on a shared row must clear each other by the TRACKS' half-widths +
    1.0mm (the audit's width-blind landmine: a 1mm CENTERLINE gap between two
    multi-mm tracks is copper-on-copper). Returns ({key: band_center_y},
    total_depth).

    Source-row order defaults to NARROWEST span first => the WIDEST bands land
    on the LOWEST rows (closest to the shunts). Measured consequence (first alt lay,
    2026-07-19): pin drops descend from the J3 field to their own row -- with
    a full-width band (3V3 spans the whole connector) on the TOP row, every
    other rail's drops crossed it on the same alt layer and refused;
    widest-lowest means a rail's drops stop at their row before reaching any
    wider band.

    Sink collectors use ``widest_first=True``. Their drops run in the
    opposite direction (shunt toward terminal edge), so the topological rule
    is the conjugate: the widest collector must occupy the edge-most row.
    Narrower descents then terminate before reaching it instead of forcing a
    horizontal crossing on every available trunk layer.
    """
    ranks, assign = [], {}
    def _order(q):
        span = q["x_hi"] - q["x_lo"]
        return ((-span if widest_first else span), q["key"])

    for it in sorted(items, key=_order):
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


def _plan_rail_chains_forward(rails, j3_bot, *, alt=False):
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
    # PER-RAIL PRIMARY LAYER (owner 2026-07-20: "it's still just mirroring
    # In2 and B.Cu" -- the bottom must be a PRIMARY trunk layer, not a copy):
    # 2-color the rails across the alt pair by span-overlap conflict, greedy
    # widest-first. Overlapping rails land on DIFFERENT layers, so their
    # bands share the same shallow row and the interleaved-pin drop
    # contention (rail A's band vs rail B's drops at the same x) vanishes
    # by construction. Face-only mode keeps everything on "alt"=face.
    body_of = {}
    if alt:
        placed_by_layer = {"alt": [], "back": []}
        for it in sorted(items, key=lambda q: -(q["x_hi"] - q["x_lo"])):
            def _conf(tag):
                return sum(1 for (a, b) in placed_by_layer[tag]
                           if it["x_lo"] < b + 2.0 and it["x_hi"] + 2.0 > a)
            tag = "alt" if _conf("alt") <= _conf("back") else "back"
            body_of[it["key"]] = tag
            placed_by_layer[tag].append((it["x_lo"], it["x_hi"]))
    else:
        body_of = {it["key"]: "alt" for it in items}
    # per-LAYER band packing: each layer's rows stack independently
    band_ys = {}
    for tag in ("alt", "back"):
        sub = [it for it in items if body_of.get(it["key"], "alt") == tag]
        if sub:
            ys, _d = plan_bands(sub, j3_bot)
            band_ys.update(ys)
    spans = {}
    for rl, it in zip(rails, items):
        spans[rl["rs"]] = (it["x_lo"], it["x_hi"], band_ys[rl["rs"]],
                           max(1.5, min(6.0, rl["amps"] * 0.25)),
                           body_of.get(rl["rs"], "alt"))
    # SINK span packing (width-aware, rows stack UP from the TB field),
    # ALSO per layer
    _sink_items = []
    for rl in rails:
        _sw = max(1.5, min(6.0, rl["amps"] * 0.25))
        _sxs = [q[2] for q in rl["tb"]] + [rl["lo"][0]]
        _sink_items.append({"key": rl["rs"], "w": _sw,
                            "x_lo": min(_sxs), "x_hi": max(_sxs)})
    _sink_ys = {}
    for tag in ("alt", "back"):
        sub = [it for it in _sink_items if body_of.get(it["key"], "alt") == tag]
        if sub:
            ys, _d = plan_bands(sub, 0.0, y0_off=0.0,
                                widest_first=True)
            _sink_ys.update(ys)
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
        body = body_of.get(rl["rs"], "alt") if alt else "face"
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
            # spine column: the rail's PRIMARY layer unless it crosses a
            # foreign band row ON THE SAME LAYER (different-layer bands never
            # collide -- the whole point of the 2-coloring)
            lo_y, hi_y = min(band_y, hy - 3.0), max(band_y, hy - 3.0)
            crossed = any(lo_y < by < hi_y and (bx0 - bw / 2 - 0.5) <= hx <= (bx1 + bw / 2 + 0.5)
                          for k2, (bx0, bx1, by, bw, btag) in spans.items()
                          if k2 != rl["rs"] and btag == body)
            src = [(min(xs), band_y, max(xs), band_y, w, body)]
            if crossed:
                src.append((hx, band_y, hx, hy, w, "face"))
                arrays.append((hx, band_y, n_via, rl["src_net"]))
            else:
                src.append((hx, band_y, hx, hy - 3.0, w, body))
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
        # A monolithic multi-leg terminal is not a row of independent blade
        # tabs.  Keep the full-rail-width collection band beyond its physical
        # body/courtyard, then use one current-sharing neck per solder leg.
        # This prevents a wide trunk from occupying the narrow foreign-net
        # gaps inside a compact screw-terminal field.
        if rl.get("tb_escape_y") is not None:
            band2 = min(band2, float(rl["tb_escape_y"]))
        txs = [q[2] for q in rl["tb"]] + [lx]
        terminal_refs = {q[0] for q in rl["tb"]}
        if len(terminal_refs) == 1 and len(rl["tb"]) > 1:
            dwt = max(0.8, min(2.0, w / len(rl["tb"])))
        else:
            dwt = max(2.0, w / max(1, len(rl["tb"])))
        if not alt:
            _mid = min(lyy + 3.0, band2)         # pad-width tail off the LO pad
            snk = [(lx, lyy, lx, _mid, sw, "face"),   # (mirror of the src clamp)
                   (lx, _mid, lx, band2, w, "face"),
                   (min(txs), band2, max(txs), band2, w, "face")]
            snk += [(tx, band2, tx, ty, dwt, "face") for _r, _pn, tx, ty, _h, _t in rl["tb"]]
        else:
            snk = [(lx, lyy, lx, lyy + 2.5, sw, "face"),
                   (lx, lyy + 2.5, lx, band2, w, body),
                   (min(txs), band2, max(txs), band2, w, body)]
            snk += [(tx, band2, tx, ty, dwt, body) for _r, _pn, tx, ty, _h, _t in rl["tb"]]
            arrays.append((lx, lyy + 2.5, n_via, rl["snk_net"]))
        out[rl["rs"]] = {"w": w, "band_y": band_y, "src": src, "body": body,
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


def plan_rail_chains(rails, j3_bot, *, alt=False):
    """Plan rail chains for either vertical connector ordering.

    The original compiler is expressed in a source-at-top coordinate frame.
    Rev3's assembly datum puts J3 at the bottom and the TB outputs at the top.
    Reflecting Y before and after the proven compiler preserves every width,
    layer, via-array, and collision invariant without maintaining a second
    geometry implementation.
    """
    j3_ys = [q[2] for rl in rails for q in rl.get("j3", ())]
    tb_ys = [q[3] for rl in rails for q in rl.get("tb", ())]
    reverse = bool(j3_ys and tb_ys
                   and (sum(j3_ys) / len(j3_ys) > sum(tb_ys) / len(tb_ys)))
    if not reverse:
        return _plan_rail_chains_forward(rails, j3_bot, alt=alt)

    def _ry(rl):
        q = dict(rl)
        q["hi"] = (rl["hi"][0], -rl["hi"][1])
        q["lo"] = (rl["lo"][0], -rl["lo"][1])
        q["j3"] = [tuple(list(p[:2]) + [-p[2]] + list(p[3:]))
                   for p in rl.get("j3", ())]
        q["tb"] = [tuple(list(p[:3]) + [-p[3]] + list(p[4:]))
                  for p in rl.get("tb", ())]
        if rl.get("tb_escape_y") is not None:
            q["tb_escape_y"] = -float(rl["tb_escape_y"])
        return q

    rrails = [_ry(rl) for rl in rails]
    rj3_edge = max((q[2] for rl in rrails for q in rl.get("j3", ())),
                   default=-j3_bot)
    raw = _plan_rail_chains_forward(rrails, rj3_edge, alt=alt)

    def _seg(s):
        x1, y1, x2, y2, w, tag = s
        return (x1, -y1, x2, -y2, w, tag)

    out = {}
    for rs, ch in raw.items():
        q = dict(ch)
        q["band_y"] = -ch["band_y"]
        q["src"] = [_seg(s) for s in ch["src"]]
        q["snk"] = [_seg(s) for s in ch["snk"]]
        q["pin_drops"] = [(x1, -y1, x2, -y2, w, net, tag)
                          for x1, y1, x2, y2, w, net, tag
                          in ch["pin_drops"]]
        q["arrays"] = [(x, -y, n, net) for x, y, n, net in ch["arrays"]]
        x, y0, y1, w = ch["snk_desc"]
        q["snk_desc"] = (x, -y0, -y1, w)
        x0, x1, y, w = ch["snk_band"]
        q["snk_band"] = (x0, x1, -y, w)
        out[rs] = q
    return out


def rail_placement_boxes(rails, j3_bot, *, alt=False, include_inner=False):
    """Return the component-free XY envelopes required by the emitted rail plan.

    This is the shared placement/mechanical-probe view of ``plan_rail_chains``.
    By default it reserves only face copper, every through-via array site, and
    the sink retry corridors; inner-layer runs may pass below SMD parts.
    ``include_inner=True`` reserves every copper layer for THT mechanical
    probes because connector barrels pierce the inner power layers.
    Each result is ``(x0, x1, y0, y1)`` in board coordinates.
    """
    boxes = []
    for ch in plan_rail_chains(rails, j3_bot, alt=alt).values():
        half = ch["w"] / 2.0 + 0.75
        for x1, y1, x2, y2, _sw, tag in list(ch["src"]) + list(ch["snk"]):
            if tag != "face" and not include_inner:
                continue
            boxes.append((min(x1, x2) - half, max(x1, x2) + half,
                          min(y1, y2) - half, max(y1, y2) + half))
        for ax, ay, _n_v, _net in ch.get("arrays", ()):
            # The via placer may select sites at +/-2.6 mm; include barrel and
            # clearance so the placement model covers every candidate site.
            ah = 2.6 + 0.45 + 0.45
            boxes.append((ax - ah, ax + ah, ay - ah, ay + ah))
        sd = ch.get("snk_desc")
        if sd:
            x, y0, y1, w = sd
            h = w / 2.0 + 0.75
            boxes.append((x - h, x + h, min(y0, y1), max(y0, y1)))
        sb = ch.get("snk_band")
        if sb:
            x0, x1, y, w = sb
            h = w / 2.0 + 0.75
            boxes.append((x0 - h, x1 + h, y - h, y + h))
    return boxes


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


def rail_current_contract(nets, *, board_hint=None, current_by_net=None):
    """Resolve sustained current once for reservation and copper generation.

    A declared board is required to supply a rating. The historical voltage
    ladder is retained only for anonymous legacy callers and is identified in
    the returned provenance instead of silently overriding current policy.
    """
    explicit = dict(current_by_net or {})
    if board_hint:
        import cec_synth_pipeline
        for net in nets:
            if net not in explicit:
                contract = cec_synth_pipeline.spec_net_current_contract(
                    board_hint, net)
                if contract is not None:
                    explicit[net] = contract["amps"]
    selected = [(net, float(explicit[net])) for net in nets if net in explicit]
    if selected:
        if any(not math.isfinite(amps) or amps <= 0 for _, amps in selected):
            raise ValueError("invalid sustained rail current: %r" % selected)
        return {"amps": max(amps for _, amps in selected),
                "source": "declared_current_contract", "net_ratings": dict(selected)}
    if board_hint or current_by_net is not None:
        raise ValueError("no declared current for rail nets %r" % (tuple(nets),))
    return {"amps": _amps_for(nets), "source": "legacy_voltage_current_ladder"}


def discover_rails(board, *, board_hint=None, current_by_net=None, topology=None):
    """Resolve physical rail terminals and currents using the shared compiler."""
    import cec_rail_geometry as geometry
    pads, courtyards, roles = geometry.board_facts(board)
    if topology is None:
        topology = geometry.discover_topology(pads, roles=roles)
    return geometry.compile_rails(
        topology, pads, courtyards,
        lambda nets: rail_current_contract(
            nets, board_hint=board_hint, current_by_net=current_by_net))


def lay_force_rails(board, *, lock=True, verbose=True, alt_layer=None,
                    mirror_bcu=False, escape_layers=(), board_hint=None,
                    current_by_net=None, topology=None, preserved_nets=(),
                    detour_budget_s=2.0, construction_evidence=None,
                    access_report=None, transition_budget_s=2.0, pickup_budget_s=2.0):
    """Lay the per-rail force copper LOCKED. Returns {rs: report|'REFUSED: ...'}.
    *alt_layer* (e.g. "In2.Cu", the board-class inner POWER-ROUTING layer -- In1
    stays the solid GND plane per the owner's 2026-07-19 ruling): plan in ALT
    mode (bands/sinks on the inner layer, direct into THT barrels, via arrays at
    the SMD shunt stubs). Absent/not-found -> face-only planning (unchanged)."""
    import pcbnew
    if not math.isfinite(float(detour_budget_s)) or float(detour_budget_s)<0:
        raise ValueError('invalid force-rail detour budget')
    if not math.isfinite(float(transition_budget_s)) or float(transition_budget_s)<0:
        raise ValueError('invalid force-rail transition budget')
    if not math.isfinite(float(pickup_budget_s)) or float(pickup_budget_s)<0:
        raise ValueError('invalid force-rail pickup budget')
    rails = discover_rails(board, board_hint=board_hint,
                           current_by_net=current_by_net, topology=topology)
    if preserved_nets:
        import cec_frozen_copper
        cec_frozen_copper.require_present(board, preserved_nets)
    if not rails:
        return {}
    import cec_portal_copper
    _portal_report = cec_portal_copper.required_ground_portals(
        board, board_path=board.GetFileName())
    _portals = _portal_report['portals']
    _portal_clearance = cec_portal_copper.reservation_clearance(board)
    _portal_report['clearance_mm'] = _portal_clearance
    if access_report is not None:
        access_report.update(_portal_report)
    layer_id = {"F.Cu": board.GetLayerID("F.Cu"), "B.Cu": board.GetLayerID("B.Cu")}
    alt_id = board.GetLayerID(alt_layer) if alt_layer else -1
    alt_on = alt_id >= 0
    _escape_layers = tuple(
        ln for ln in dict.fromkeys(escape_layers or ())
        if ln not in {"F.Cu", "B.Cu", alt_layer}
        and board.GetLayerID(ln) >= 0)
    netmap = {str(k): v for k, v in board.GetNetInfo().NetsByName().items()}

    pads = []                                                  # foreign-guard universe
    for fp in board.GetFootprints():
        for p in fp.Pads():
            pos = p.GetPosition()
            pads.append((fp.GetReference(), p.GetNetname(), pos.x / MM, pos.y / MM,
                         max(p.GetSize().x, p.GetSize().y) / (2 * MM),
                         p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH))
    import cec_native_pad_obstacles
    pad_obstacles = cec_native_pad_obstacles.Index(board, clearance_mm=.25)
    laid_segs = []                                             # (net, x1,y1,x2,y2, w, tag)
    laid_vias = []                                             # (x, y)
    # PRE-INDEX existing LOCKED copper (audit landmine: the collider started
    # empty while blueprint-cell copper is laid BEFORE the rails on the same
    # board) -- tagged by layer class so the layer-aware checks apply.
    for _t0 in board.GetTracks():
        if not _t0.IsLocked():
            continue
        if _t0.Type() == pcbnew.PCB_VIA_T:
            _p0 = _t0.GetPosition()
            laid_vias.append((_p0.x / MM, _p0.y / MM))
        else:
            _ln = board.GetLayerName(_t0.GetLayer())
            # Retained boards may rename In*.Cu (for example a power plane).
            # Preserve the real layer identity, not a display-name comparison
            # with the configured canonical alias or this rail's relative face.
            _tag0 = _ln
            _s0, _e0 = _t0.GetStart(), _t0.GetEnd()
            laid_segs.append((_t0.GetNetname() or "", _s0.x / MM, _s0.y / MM,
                              _e0.x / MM, _e0.y / MM, _t0.GetWidth() / MM, _tag0))

    def _collide(plan, own_nets, skip_refs=(), *, pending_segments=(), pending_vias=(),
                 feedback=False):
        """Layer-aware: an ALT segment passes under SMD pads (face-only copper)
        and foreign face segments; it collides with THT barrels (all layers),
        same-tag laid copper, and laid via barrels. FACE segments collide as
        before (all pads + face copper + vias)."""
        if feedback:
            # Placement needs the COMPLETE physical blocker set of this
            # principal conductor, including pads later in the same segment
            # and on later segments. First-hit admission below stays intact.
            attempt = pad_obstacles.conductor_obstructions([
                dict(segment_mm=list(segment[:5]), layer=board.GetLayerName(
                    board.GetLayerID(_tag_layer(segment[5], rl['face']))))
                for segment in plan], own_nets, skip_prefixes=skip_refs)
            if attempt['blocked_segments'] and attempt not in _rail_obstruction_sets:
                _rail_obstruction_sets.append(attempt)
            for witness in attempt['blocked_segments']:
                if witness not in _rail_blocked_segments and len(_rail_blocked_segments) < 64:
                    _rail_blocked_segments.append(witness)
        for (x1, y1, x2, y2, w, tag) in plan:
            layer = board.GetLayerID(_tag_layer(tag, rl['face']))
            conflict = cec_portal_copper.segment_portal_conflict(
                (x1,y1),(x2,y2),w,net=next(iter(own_nets)),layer_id=layer,
                portals=_portals,clearance_mm=_portal_clearance)
            if conflict is not None:
                return 'reserved return portal %s.%s on %s' % (
                    conflict['ref'],conflict['pad'],board.GetLayerName(layer))
            obstruction = pad_obstacles.collision(
                (x1,y1,x2,y2,w), layer, own_nets, skip_prefixes=skip_refs)
            if obstruction is not None:
                ref, net = obstruction['ref'], obstruction['net']
                px, py = obstruction['at_mm']
                return ("%s [%s] at (%.1f,%.1f) vs plan (%.1f,%.1f)-(%.1f,%.1f)"
                        % (ref, net, px, py, x1, y1, x2, y2))
            for (net2, a1, b1, a2, b2, w2, tag2) in [*laid_segs,*pending_segments]:
                if (net2 in own_nets or
                        board.GetLayerID(_tag_layer(tag2,rl['face'])) != layer):
                    continue
                # exact seg-seg distance (audit landmine: 5-point sampling
                # missed thin crossings)
                if _seg_seg_d2(x1, y1, x2, y2, a1, b1, a2, b2) < (w / 2 + w2 / 2 + 0.25) ** 2:
                    return ("laid copper [%s] (%.1f,%.1f)-(%.1f,%.1f) vs plan "
                            "(%.1f,%.1f)-(%.1f,%.1f)"
                            % (net2, a1, b1, a2, b2, x1, y1, x2, y2))
            for (vx, vy) in [*laid_vias,*pending_vias]:
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
    _detour_region = None
    _detour_region_checked = False

    def _detour(plan, own_nets, *, anchors=(), array_anchors=None,
                pending_segments=(), pending_vias=(), deadline=None):
        """Search XY before surrendering a layer; never move graph terminals."""
        nonlocal _detour_region, _detour_region_checked
        import time
        deadline=_rail_detour_deadline if deadline is None else deadline
        if not _bb_ok or time.monotonic() >= deadline:
            _rail_detours.append(dict(schema=1,changed=False,admitted=False,
                reason='missing_native_outline' if not _bb_ok else 'bounded_search_exhausted'))
            return plan
        import cec_rail_detour
        import cec_pour_plan
        import cec_fr
        from shapely.geometry import Point, LineString
        if not _detour_region_checked:
            _detour_region = cec_rail_detour.native_region(
                board, edge_clearance_mm=max(.25,
                    board.GetDesignSettings().m_CopperEdgeClearance / MM))
            _detour_region_checked = True
        if _detour_region is None or _detour_region.is_empty:
            _rail_detours.append(dict(schema=1,changed=False,admitted=False,
                                     reason='missing_native_outline'))
            return plan
        net = next(iter(own_nets))
        def obstacles(tag):
            layer = _tag_layer(tag, rl['face'])
            lid = board.GetLayerID(layer)
            values = cec_pour_plan._geo_obstacles(
                board, board.GetNetcodeFromNetname(net), [layer], .25, 0.)[layer]
            # The shared model already includes conservative pad bounding
            # boxes. A second maximum-dimension circle used to enlarge long
            # rectangular pads sideways and erase otherwise legal channels.
            values.extend(Point(x,y).buffer(.70,quad_segs=8) for x,y in laid_vias)
            values.extend(Point(x,y).buffer(.70,quad_segs=8) for x,y in pending_vias)
            values.extend(LineString(((x1,y1),(x2,y2))).buffer(width/2+.25)
                for other,x1,y1,x2,y2,width,tg in pending_segments
                if other not in own_nets and _tag_layer(tg,rl['face'])==layer)
            values.extend(Point(*p['at_mm']).buffer(
                p['diameter_mm']/2+_portal_clearance,quad_segs=8)
                for p in _portals if p['net'] not in own_nets and lid in p['layer_ids'])
            values.extend(cec_fr._zone_outline_geometry(z).buffer(.25,join_style=2)
                          for z in board.Zones() if z.GetIsRuleArea()
                          and z.IsOnLayer(lid) and z.GetDoNotAllowTracks())
            return values
        fixed_anchors = tuple(anchors) + tuple(
            (x,y) for _ref,net,x,y,_half,_tht in pads if net in own_nets)
        fixed_anchors += (tuple(array_anchors) if array_anchors is not None else
                         tuple((x,y) for x,y,_n,net in _plan_arrays if net in own_nets))
        replacement, evidence = cec_rail_detour.repair_plan(
            plan, region=_detour_region, obstacles_for=obstacles, anchors=fixed_anchors,
            collision=lambda rows:_collide(rows,own_nets,skip_refs=('FID',),
                pending_segments=pending_segments,pending_vias=pending_vias),
            deadline=deadline, relax_unanchored_bends=True, repair_topology=True)
        _rail_detours.append(evidence)
        return replacement if replacement is not None else plan

    def _array_sites(x, y, n, own_nets, pending=(), *, pending_segments=(), landing_plan=None):
        """n clear through-barrel sites clustered at (x,y), or None. Via barrels
        pierce every layer -> clear of ALL pads regardless of tag, ALL laid
        copper on any tag (audit landmine: tracks were unchecked), the board
        edge (>=1.2mm), prior vias, and *pending* same-rail array sites."""
        sites = []
        occupied = list(laid_vias) + [q for arr in pending for q in arr]
        intended_net = sorted(own_nets)[0] if own_nets else ""
        intended_code = board.GetNetcodeFromNetname(intended_net)
        def clear_site(cx, cy, accepted):
            if _bb_ok and not (_bx0 + 1.2 <= cx <= _bx1 - 1.2
                               and _by0 + 1.2 <= cy <= _by1 - 1.2):
                return False
            # Through POFV may land inside a same-net SMD pad only when the
            # board declares the approved profile and the complete 0.9/0.5mm
            # land passes the central fabrication check. Legacy boards, THT
            # pads, and every foreign-net overlap remain excluded. Foreign
            # pads also retain the 0.25mm copper clearance beyond collision.
            at = pcbnew.VECTOR2I(int(cx * MM), int(cy * MM))
            blocking, _allowed = cec_fab.via_at_pad_conflicts(
                board, at, int(0.9 * MM), int(0.5 * MM), intended_code)
            ok = blocking is None
            ok = ok and all(not (net not in own_nets
                                 and (px - cx) ** 2 + (py - cy) ** 2
                                 < (half + 0.45 + 0.25) ** 2)
                            for ref, net, px, py, half, tht in pads)
            ok = ok and all(not (net2 not in own_nets
                                 and _seg_pt_d2(cx, cy, a1, b1, a2, b2)
                                 < (w2 / 2 + 0.45 + 0.25) ** 2)
                            for (net2, a1, b1, a2, b2, w2, _tg) in [*laid_segs,*pending_segments])
            ok = ok and all((vx - cx) ** 2 + (vy - cy) ** 2 >= 1.15 ** 2
                            for vx, vy in (occupied + accepted))
            ok = ok and all(p['net'] in own_nets or math.dist(p['at_mm'],(cx,cy))
                            >= .45+p['diameter_mm']/2+_portal_clearance for p in _portals)
            return ok
        for dx, dy in _ARR_OFF:
            if len(sites) >= n and landing_plan is None:
                break
            cx, cy = x + dx, y + dy
            if clear_site(cx, cy, sites):
                sites.append((cx, cy))
        chosen=sites[:n] if len(sites)>=n else None
        landing_evidence={}
        legal=None
        if landing_plan is not None:
            import cec_transition_landings
            actual=[(*s[:5],_tag_layer(s[5],rl['face'])) for s in landing_plan]
            layers=tuple(dict.fromkeys(s[5] for s in actual))
            actual_pending=[(*s[:6],_tag_layer(s[6],rl['face'])) for s in pending_segments]
            legal=cec_transition_landings.proposal_filter(board,intended_net,layers,actual,
                portals=_portals,pending_segments=actual_pending,
                clearance_mm=_portal_clearance,evidence=landing_evidence)
        # Prefer whole exact-count symmetric proposals rather than a prefix
        # of a ring-ordered grid. Keep existing pitch/reach/count and all
        # all-layer obstacles and full-landing checks. No committed via moves.
        center_nm=(round(x*MM),round(y*MM));symmetric=None
        symmetric_rejections={'site_blocked':0,'full_landing_refused':0}
        for offsets in cec_via_field_layout.centered_offsets(n,pitch_nm=1300000,reach_nm=2600000):
            trial=[((center_nm[0]+dx)/MM,(center_nm[1]+dy)/MM) for dx,dy in offsets]
            accepted=[]
            for point in trial:
                if not clear_site(*point,accepted):
                    symmetric_rejections['site_blocked']+=1
                    break
                accepted.append(point)
            if len(accepted)!=n:
                continue
            if legal is not None and not legal(trial):
                symmetric_rejections['full_landing_refused']+=1
                continue
            symmetric=trial
            break
        if symmetric is not None:
            chosen=symmetric
        elif chosen is not None and legal is not None:
            # Every compact subset used to include a central site whose land
            # would be clipped, while excluding a farther usable site. Remove
            # individually impossible lands before the bounded subset search;
            # never reduce the required field size or omit the joint test.
            viable=legal.viable_sites(sites)
            landing_evidence['site_candidates']=len(sites)
            landing_evidence['viable_sites']=len(viable)
            # At most 26 deterministic compact subsets, never combinatorial
            # enumeration or fewer barrels than the current contract requires.
            options=([viable[:n]]+[sorted(viable,key=lambda p:(math.dist(p,seed),math.dist(p,(x,y)),p))[:n]
                                   for seed in viable]) if len(viable)>=n else []
            chosen=next((q for q in options if legal(q)),None)
        observed=(cec_via_field_layout.shape_evidence(
            [(round(a*MM),round(b*MM)) for a,b in chosen],center_nm) if chosen else None)
        _rail_arrays.append(dict(center=[x,y],required=n,available=max(len(sites),len(chosen or ())),
                                 nets=sorted(own_nets),ok=chosen is not None,
                                 legacy_grid_available=len(sites),
                                 layout_mode=('symmetric_exact_count' if symmetric is not None
                                     else 'obstacle_qualified_fallback' if chosen is not None else 'refused'),
                                 centered_pattern_rejections=symmetric_rejections,
                                 field_shape=observed,
                                 landing_preview_required=landing_plan is not None,
                                 landing_preview=landing_evidence))
        return chosen

    def _transition_repair(plan, array, own_nets, *, anchors=(),
                           pending_arrays=(), pending_segments=(), remaining_variants=1):
        """Move only an uncommitted transition; never its contact or rating."""
        nonlocal _rail_transition_deadline
        import time
        import cec_rail_transition_search
        import cec_rail_detour
        if _rail_transition_deadline is None:
            _rail_transition_deadline=time.monotonic()+float(transition_budget_s)
        # A difficult first layer must not consume the whole portfolio's
        # budget before a different legal layer gets a turn.
        now=time.monotonic()
        call_deadline=now+max(0.,_rail_transition_deadline-now)/max(1,remaining_variants)
        contacts=[(x,y) for _r,n,x,y,_h,_t in pads if n in own_nets]
        pending_vias=[p for sites in pending_arrays for p in sites]
        for trial,center in cec_rail_transition_search.candidates(
                plan,array[:2],fixed_contacts=contacts,
                # Two field-grid pitches of extra reach at full body width.
                # The short pad neck and complete via/current contract stay
                # unchanged; native admission still qualifies the proposal.
                full_width_extensions_mm=(1.3,2.6),limit=48):
            if time.monotonic()>=call_deadline:
                _rail_transitions.append(dict(reason='bounded_search_exhausted',accepted=False))
                break
            row=dict(old_center=list(array[:2]),new_center=list(center),
                     required_vias=array[2],nets=sorted(own_nets),accepted=False)
            _rail_transitions.append(row)
            def collision(parts):
                return _collide(parts,own_nets,skip_refs=('FID',),
                    pending_segments=pending_segments,pending_vias=pending_vias)
            blocked=collision([s for s in trial if s[5]=='face'])
            if blocked:
                row.update(reason='face_neck_blocked',detail=blocked)
                continue
            # Moving the virtual transition can reverse its old body elbow
            # without creating a collision. Rebuild only that unanchored
            # equal-width chain BEFORE qualifying its complete via field.
            # Existing copper, physical contacts and branches stay fixed.
            topology_anchors=tuple(contacts)+tuple(anchors)+(center,)
            if cec_rail_detour.has_virtual_backtrack(trial,anchors=topology_anchors):
                trial=_detour(trial,own_nets,anchors=anchors,array_anchors=(center,),
                    pending_segments=pending_segments,pending_vias=pending_vias,
                    deadline=call_deadline)
                if cec_rail_detour.has_virtual_backtrack(trial,anchors=topology_anchors):
                    row['reason']='virtual_backtrack_unresolved'
                    continue
            sites=_array_sites(*center,array[2],own_nets,pending=pending_arrays,
                               pending_segments=pending_segments,landing_plan=trial)
            if sites is None:
                row['reason']='full_via_field_unavailable'
                continue
            if collision(trial):
                trial=_detour(trial,own_nets,anchors=anchors,array_anchors=(center,),
                    pending_segments=pending_segments,pending_vias=pending_vias,
                    deadline=call_deadline)
            blocked=collision(trial)
            if blocked:
                row.update(reason='body_blocked',detail=blocked)
                continue
            row.update(reason='proposal_requires_native_landing_admission',accepted=True,
                       available_vias=len(sites))
            return trial,(*center,array[2]),sites
        return None

    def _layer_of(tag, face_ly):
        if tag == "back":
            return layer_id["B.Cu"]
        if tag == "alt" and alt_on:
            return alt_id
        if tag not in {"face", "alt"}:
            lid = board.GetLayerID(tag)
            if lid >= 0:
                return lid
        return face_ly

    def _tag_layer(tag, face_name):
        if tag == "alt" and alt_on:
            return alt_layer
        if tag == "back":
            return "B.Cu"
        if tag not in {"face", "alt"}:
            return tag
        return face_name

    def _commit(net, plan, face_ly):
        for (x1, y1, x2, y2, w, tag) in plan:
            if (round(x1*MM),round(y1*MM)) == (round(x2*MM),round(y2*MM)):
                continue  # A collapsed collector is not a native track.
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(round(x1 * MM), round(y1 * MM)))
            t.SetEnd(pcbnew.VECTOR2I(round(x2 * MM), round(y2 * MM)))
            t.SetWidth(round(w * MM))
            t.SetLayer(_layer_of(tag, face_ly))
            ni = netmap.get(net)
            if ni is not None:
                t.SetNet(ni)
            if lock:
                t.SetLocked(True)
            board.Add(t)
            laid_segs.append((net, x1, y1, x2, y2, w,
                              board.GetLayerName(_layer_of(tag,face_ly))))

    def _normalize_primary(net, plan, sites):
        import cec_conductor_proposal
        import cec_parallel_copper
        tags = {s[5] for s in plan}
        tests = {tag: cec_parallel_copper.native_anchor_test(
            board, net, _tag_layer(tag, rl['face'])) for tag in tags}
        fixed = [(x, y, tag) for x, y in sites for tag in tags]
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetname() != net:
                    continue
                point = pad.GetPosition()
                fixed.extend((point.x/MM, point.y/MM, tag) for tag in tags
                    if pad.IsOnLayer(board.GetLayerID(_tag_layer(tag, rl['face']))))
        return cec_conductor_proposal.normalize_terminal_paths(plan,
            anchored_at=lambda point, tag: tests[tag](point), fixed_points=fixed,
            layer_key=lambda tag: _tag_layer(tag, rl['face']))

    def _commit_array(net, sites, face_ly, face_name="F.Cu", alt_name=None):
        # Every declared transition requires both real layer landings. A
        # capsule proxy overhangs a rectangle and used to silently suppress
        # one landing while still emitting every barrel. Native filling and
        # complete-field admission now own this decision in the materializer.
        if sites:
            import cec_transition_landings
            _patch_pours.extend(cec_transition_landings.patches_for(
                net, sites, (face_name, alt_name), diameter_mm=.9,
                drill_mm=.5, margin_mm=.65))
        for (cx, cy) in sites:
            v = pcbnew.PCB_VIA(board)
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetPosition(pcbnew.VECTOR2I(int(round(cx * MM)), int(round(cy * MM))))
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
    frozen = set(preserved_nets or ())
    _twin_cands = []          # (rs, net, seg, face_ly) -- committed pass 2
    _patch_pours = []         # rectangular landing-zone dicts (add_power_pours)
    # Commit dominant collectors first.  The collider is intentionally
    # asymmetric: copper already accepted owns its corridor and later rails
    # adapt.  Therefore lexical/shunt-X order can strand a wide collector
    # behind several narrow descents even when the inverse order is routable.
    # This is the power-copper equivalent of critical-net-first detailed
    # routing: largest terminal interval, then current, then reference for a
    # deterministic tie break.
    for rank, rl in enumerate(sorted(rails, key=_sink_priority)):
        import time
        _rail_detour_deadline = time.monotonic() + float(detour_budget_s)
        _rail_detours = []
        _rail_arrays = []
        _rail_transitions = []
        _rail_blocked_segments = []
        _rail_obstruction_sets = []
        _rail_transition_deadline = None
        if construction_evidence is not None:
            construction_evidence[rl['rs']] = dict(
                schema=1, detours=_rail_detours, arrays=_rail_arrays,
                transition_search=_rail_transitions,
                blocked_segments=_rail_blocked_segments,
                obstruction_sets=_rail_obstruction_sets,
                release_authority=False)
        owned = {rl["src_net"], rl["snk_net"]}
        if owned & frozen:
            report[rl["rs"]] = (
                {"preserved": True, "nets": sorted(owned)} if owned <= frozen
                else "REFUSED: partially frozen rail requires explicit topology replacement")
            continue
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
        # BAND-WIDTH shrink (2026-07-19: a pin can pass the drop-width pre-test
        # while the FULL-width band still dies at its thin extremity -- RS3's
        # w=5 band's 4.35mm radius vs J1's VCC pad; the pin's 6A reach doesn't
        # need rail width): iteratively drop the extreme pin farther from the
        # shunt column until the band itself guards clean.
        def _band_ok(xs, tag):
            if max(xs) - min(xs) < 0.1:
                return True
            # test on the rail's OWN primary layer (hardcoded "alt" shrank a
            # back-bodied rail's band against the wrong layer's copper --
            # measured: RS1 degenerated to a point, 2026-07-20)
            _b = [(min(xs), band_y, max(xs), band_y, w, tag)]
            return _collide(_b, own_src, skip_refs=("FID",)) is None

        _source_spans = {}
        def _live_span(tag):
            # Access on one layer is not evidence about another. Reuse the
            # existing pickup grammar and widths, but evaluate it anew for
            # each permitted layer before shortening that layer's collector.
            if tag in _source_spans:
                return _source_spans[tag]
            xs = [hx]
            through = {p[0]: p[4] for p in rl['j3']}
            for px, py, x2, y2, dw, pn, _old_tag in _ch['pin_drops']:
                if not through.get(pn) and _tag_layer(tag,rl['face']) != rl['face']:
                    continue
                for ddx in (0.0, 2.1, -2.1, 1.8, -1.8):
                    if ddx == 0.0:
                        drop = [(px,py,x2,y2,dw,tag)]
                    else:
                        neck = min(dw,1.0)  # Existing pickup policy, not a new rating.
                        drop = [(px,py,px+ddx,py,neck,tag),
                                (px+ddx,py,px+ddx,y2,neck,tag)]
                    if _collide(drop,own_src,skip_refs=('FID',)) is None:
                        xs.append(px)
                        break
            while len(xs)>1 and not _band_ok(xs,tag):
                lo,hi=min(xs),max(xs)
                cut=lo if abs(lo-hx)>=abs(hi-hx) else hi
                if cut==hx:
                    break
                xs.remove(cut)
            _source_spans[tag]=xs
            return xs

        def _respan(segs, xs):
            """Clamp the (single) band segment of a source shape to the live span;
            a span collapsed to a point drops the band seg entirely (a zero-length
            seg still collides as a point -- measured)."""
            o = []
            for (x1, y1, x2, y2, w2, tg) in segs:
                if y1 == y2 == band_y and abs(x2 - x1) > 0.1:
                    if max(xs) - min(xs) > 0.1:
                        o.append((min(xs), band_y, max(xs), band_y, w2, tg))
                else:
                    o.append((x1, y1, x2, y2, w2, tg))
            return o
        # SOURCE variants: (segs, src_array_pos). A colliding FACE-fallback
        # column retries JOGGED variants around the cell envelope (audit
        # finding 4: the full-width fallback ran straight through the shunt-pad
        # column where the one-sided cell bank sits): the column offsets
        # sideways, the alt band EXTENDS to the jog x, the via array moves to
        # the jog junction, and a short axial elbow re-enters the pad.
        _primary_tag = _ch.get('body','alt') if alt_on else 'face'
        _primary_span = _live_span(_primary_tag)
        _src_variants = [(_respan(list(_ch["src"]),_primary_span),
                          _src_arr, None, _primary_span)]
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
                _src_variants.append((_v, _sa, None, _primary_span))
        if alt_on:
            # LAST-RESORT plain-FACE source (pour doc §2.3 layer stagger; s0d
            # probe: ATX interleaves 5V/12V pins at the SAME x, so an earlier
            # rail's laid In2 pin drops contend the next rail's In2 band --
            # stagger the loser onto the face. THT pickups need no via array;
            # pin drops follow onto the face (tag threaded per-variant).
            _face_span = _live_span('face')
            _face_src = [(min(_face_span), band_y, max(_face_span), band_y, w, "face"),
                         (hx, band_y, hx, hy, w, "face")]
            _src_variants.append((_face_src, None, "face", _face_span))
            # THIRD ESCAPE TIER: the rail's OTHER inner/bottom layer (owner
            # 2026-07-19/20 -- with per-rail primary layers, "other" is B.Cu
            # for an In2-bodied rail and In2 for a B.Cu-bodied one). THT
            # pickups pierce natively, the same via array bonds the stub end.
            _body0 = _ch.get("body", "alt")
            _other0 = "back" if _body0 == "alt" else "alt"
            _other_span = _live_span(_other0)
            _back_src = [(x1, y1, x2, y2, w2, (_other0 if tg == _body0 else tg))
                         for (x1, y1, x2, y2, w2, tg) in _respan(list(_ch["src"]),_other_span)]
            _src_variants.append((_back_src, _src_arr, _other0, _other_span))
            # Remaining profile-declared routing layers are genuine escape
            # resources too.  They are supplied by the central stackup
            # authority, never guessed here; through pickups and through-via
            # arrays make the transition legal without blind/buried vias.
            for _extra0 in _escape_layers:
                _extra_span = _live_span(_extra0)
                _extra_src = [
                    (x1, y1, x2, y2, w2,
                     (_extra0 if tg == _body0 else tg))
                    for (x1, y1, x2, y2, w2, tg)
                    in _respan(list(_ch["src"]),_extra_span)]
                _src_variants.append((_extra_src, _src_arr, _extra0, _extra_span))
        if construction_evidence is not None:
            construction_evidence[rl['rs']]['source_spans'] = {
                _tag_layer(tag,rl['face']): list(xs) for tag,xs in _source_spans.items()}
        col, spine, arr_sites = "no plan", None, []
        _drops_tag = None
        _vreasons = []                       # per-variant refusal trace (audit:
        # Reserve every possible drop endpoint in the existing bounded
        # pickup portfolio for both conductor and via-field repair paths.
        taps=[(x2+dx,y2) for _x,_y,x2,y2,_w,_p,_t in _ch['pin_drops']
              for dx in (0.,2.1,-2.1,1.8,-1.8)]
        for _vi, (_sv, _sa, _dtag_v, _xs_live) in enumerate(_src_variants):  # the message showed only the LAST
            col = _collide(_sv, own_src, skip_refs=("FID",), feedback=True)
            if col is not None:
                _sv = _detour(_sv, own_src, anchors=taps)
                col = _collide(_sv, own_src, skip_refs=("FID",))
            if col is not None:
                if _sa is not None:
                    moved=_transition_repair(_sv,_sa,own_src,anchors=taps,
                        remaining_variants=len(_src_variants)-_vi)
                    if moved is not None:
                        _sv,_sa,_sites=moved
                        col=None
            if col is not None:
                _vreasons.append("v%d %s" % (_vi, col))
                continue
            _trial, _ok = [], True
            if _sa is not None:
                s_ = _array_sites(_sa[0], _sa[1], _sa[2], {rl["src_net"]},landing_plan=_sv)
                if s_ is None:
                    # A clear conductor can still have an impossible via
                    # field. That failure needs the same bounded transition
                    # search, not only a retry after conductor collisions.
                    moved=_transition_repair(_sv,_sa,own_src,anchors=taps,
                        remaining_variants=len(_src_variants)-_vi)
                    if moved is not None:
                        _sv,_sa,s_=moved
                if s_ is None:
                    col = "no clear %d-via src array at (%.1f,%.1f)" % (_sa[2], _sa[0], _sa[1])
                    _ok = False
                else:
                    _trial.append((rl["src_net"], s_))
            # The sink has its own face/layer/transition portfolio below.
            # Refusing its original virtual field here would prevent that
            # portfolio from ever running. Nothing is committed until both
            # sides and their actual required fields have been qualified.
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
        _source_tag = next((s[5] for s in spine if s[5] != "face"), "face")
        _source_layer = _tag_layer(_source_tag, rl["face"])
        picked, dropped = 0, []
        picked_numbers=set()
        pickup_repairs=[]
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
                picked_numbers.add(pn)
            else:
                dropped.append("J3.%s [%s]" % (pn, "; ".join(_dreasons)))
        # A band shrunk on the original layer is not the authority for a
        # source subsequently rerouted on another layer. Reconnect unresolved
        # physical contacts to the ACTUAL admitted trunk, retaining their
        # declared pickup width. Never force an SMD contact onto an inner layer.
        if _bb_ok and picked<len(rl['j3']):
            import cec_rail_detour
            import cec_precision_route
            pickup_deadline=time.monotonic()+float(pickup_budget_s)
            widths={p[5]:p[4] for p in _ch['pin_drops']}
            for pn,px,py,_half,tht in rl['j3']:
                if pn in picked_numbers or (not tht and _source_tag!='face'): continue
                if time.monotonic()>=pickup_deadline: break
                width=widths.get(pn,min(w,1.4))
                for target in cec_rail_detour.contact_targets((px,py),spine,_source_tag):
                    if time.monotonic()>=pickup_deadline: break
                    path=[(px,py),(px,target[1]),target]
                    path=[p for i,p in enumerate(path) if i==0 or p!=path[i-1]]
                    direct=[(*a,*b,width,_source_tag) for a,b in zip(path,path[1:])]
                    if not direct: continue
                    proposal=direct
                    if _collide(proposal,own_src,skip_refs=('FID',)):
                        proposal=_detour(proposal,own_src,anchors=((px,py),target),
                                         array_anchors=(),deadline=pickup_deadline)
                    if _collide(proposal,own_src,skip_refs=('FID',)) is not None: continue
                    # Preserve target and contact while softening the simple
                    # two-leg fallback, only if its full width stays legal.
                    if proposal==direct:
                        smooth=cec_precision_route._chamfer_axis_path(path)
                        polished=[(*a,*b,width,_source_tag) for a,b in zip(smooth,smooth[1:])]
                        if _collide(polished,own_src,skip_refs=('FID',)) is None:
                            proposal=polished
                    pin_plans+=proposal
                    picked+=1; picked_numbers.add(pn)
                    dropped=[reason for reason in dropped if not reason.startswith('J3.%s [' % pn)]
                    pickup_repairs.append(dict(pad=str(pn),contact=[px,py],target=list(target),
                        layer=_source_layer,width_mm=width,segments=len(proposal),
                        reason='reattached_to_actual_trunk'))
                    break
        # SINK from the plan: lo -> lower band -> TB drops. FACE-STAGGER
        # retry (2026-07-19, the source-side medicine applied to the sink:
        # TB fields interleave in x, so one rail's alt sink drop crosses the
        # next rail's alt sink band -- measured at 3.95 vs 4.0mm on W74):
        # the whole sink moves to the face; THT TB barrels need no array.
        pending_arrays=[sites for net,sites in arr_sites if net!=rl['snk_net']]
        pending_segments=[(rl['src_net'],*s) for s in spine+pin_plans]
        pending_vias=[p for sites in pending_arrays for p in sites]
        def sink_collision(plan, *, feedback=False):
            return _collide(plan,own_snk,skip_refs=('FID',),feedback=feedback,
                pending_segments=pending_segments,pending_vias=pending_vias)
        def sink_detour(plan):
            return _detour(plan,own_snk,pending_segments=pending_segments,
                           pending_vias=pending_vias)
        snk = list(_ch["snk"])
        c3 = sink_collision(snk, feedback=True)
        if c3:
            snk = sink_detour(snk)
            c3 = sink_collision(snk)
        _snk_arr_on = True
        _snk_layer = _tag_layer(
            next((s[5] for s in snk if s[5] != "face"), "face"),
            rl["face"])
        if c3 and alt_on:
            _snk_face = [(x1, y1, x2, y2, w2, "face")
                         for (x1, y1, x2, y2, w2, _tg) in _ch["snk"]]
            c3b = sink_collision(_snk_face, feedback=True)
            if c3b:
                _snk_face = sink_detour(_snk_face)
                c3b = sink_collision(_snk_face)
            if c3b is None:
                snk, c3, _snk_arr_on = _snk_face, None, False
                _snk_layer = rl["face"]
            else:
                # THIRD ESCAPE TIER: the rail's OTHER layer (via-around rung;
                # TB barrels pierce, the LO-stub array bonds)
                _bod1 = _ch.get("body", "alt")
                _oth1 = "back" if _bod1 == "alt" else "alt"
                _snk_back = [(x1, y1, x2, y2, w2, (_oth1 if _tg == _bod1 else _tg))
                             for (x1, y1, x2, y2, w2, _tg) in _ch["snk"]]
                c3c = sink_collision(_snk_back, feedback=True)
                if c3c:
                    _snk_back = sink_detour(_snk_back)
                    c3c = sink_collision(_snk_back)
                if c3c is None:
                    snk, c3 = _snk_back, None
                    _snk_layer = _tag_layer(_oth1, rl["face"])
                else:
                    _snk_reasons = [c3, "face retry: " + c3b,
                                    "back retry: " + c3c]
                    for _extra1 in _escape_layers:
                        _snk_extra = [
                            (x1, y1, x2, y2, w2,
                             (_extra1 if _tg == _bod1 else _tg))
                            for (x1, y1, x2, y2, w2, _tg) in _ch["snk"]]
                        _c3x = sink_collision(_snk_extra, feedback=True)
                        if _c3x:
                            _snk_extra = sink_detour(_snk_extra)
                            _c3x = sink_collision(_snk_extra)
                        if _c3x is None:
                            snk, c3 = _snk_extra, None
                            _snk_layer = _extra1
                            break
                        _snk_reasons.append("%s retry: %s" % (_extra1, _c3x))
                    if c3 is not None:
                        c3 = "; ".join(_snk_reasons)
        sink_array=next(((x,y,n) for x,y,n,net in _oth_arrs
                         if net==rl['snk_net']),None)
        if c3 is None and alt_on and _snk_arr_on and sink_array is not None:
            sites=_array_sites(*sink_array,own_snk,pending=pending_arrays,
                pending_segments=pending_segments,landing_plan=snk)
            if sites is None:
                c3='complete sink transition field unavailable'
            else:
                arr_sites.append((rl['snk_net'],sites))
        if c3 and alt_on:
            # The old layer portfolio held the virtual face/array junction
            # fixed even when that location, rather than the rail, was blocked.
            # Retry bounded positions without moving the pad or shrinking the
            # neck/field. Source proposals are foreign pending copper here.
            if sink_array is not None:
                body=_ch.get('body','alt')
                variants=list(dict.fromkeys((body,'back' if body=='alt' else 'alt',
                                             *_escape_layers)))
                for variant,layer_tag in enumerate(variants):
                    candidate=[(*s[:5],layer_tag if s[5]==body else s[5])
                               for s in _ch['snk']]
                    moved=_transition_repair(candidate,sink_array,own_snk,
                        pending_arrays=pending_arrays,pending_segments=pending_segments,
                        remaining_variants=len(variants)-variant)
                    if moved is not None:
                        snk,_position,sites=moved
                        arr_sites=[(net,s) for net,s in arr_sites if net!=rl['snk_net']]
                        arr_sites.append((rl['snk_net'],sites))
                        _snk_arr_on=True
                        _snk_layer=_tag_layer(layer_tag,rl['face'])
                        c3=None
                        break
        if c3:
            report[rl["rs"]] = "REFUSED: snk spine vs " + c3
            if verbose:
                print("[force-rails] %s (%s) REFUSED snk: %s"
                      % (rl["rs"], rl["snk_net"], c3), flush=True)
            continue
        # All real pickups and relocated transitions are known now. Remove
        # uncommitted virtual tails and duplicate backtracking, never an
        # existing protected item or a terminal-to-terminal current path.
        _src_count = len(spine)
        _src_parts, _src_normalization = _normalize_primary(rl['src_net'],
            spine + pin_plans, [p for n, sites in arr_sites if n == rl['src_net'] for p in sites])
        _snk_parts, _snk_normalization = _normalize_primary(rl['snk_net'], snk,
            [p for n, sites in arr_sites if n == rl['snk_net'] for p in sites])
        spine = [s for i, s in _src_parts if i < _src_count]
        pin_plans = [s for i, s in _src_parts if i >= _src_count]
        snk = [s for _, s in _snk_parts]
        _commit(rl["src_net"], spine + pin_plans, face_ly)
        _commit(rl["snk_net"], snk, face_ly)
        _bcu_twins = 0
        if mirror_bcu and alt_on:
            # TWIN CANDIDATES only -- committed in a SECOND PASS after every
            # rail's PRIMARY copper is down (2026-07-20: eager twins consumed
            # the other layer's lane space before later rails claimed their
            # primary there, re-creating the contention the per-rail
            # 2-coloring removed -- measured: RS2's back twin walled RS1's
            # back-primary descent). Primaries always win; twins yield.
            for (_net_m, _segs_m) in ((rl["src_net"], spine + pin_plans),
                                      (rl["snk_net"], snk)):
                for (x1, y1, x2, y2, w2, tg) in _segs_m:
                    if tg == "alt":
                        _mt = "back"
                    elif tg == "back":
                        _mt = "alt"
                    else:
                        continue
                    _twin_cands.append((rl["rs"], _net_m,
                                        (x1, y1, x2, y2, w2, _mt), face_ly))
        if not _snk_arr_on:          # face-staggered sink: no layer transition,
            arr_sites = [(n, s_) for (n, s_) in arr_sites   # its array would dangle
                         if n != rl["snk_net"]]
        for (a_net, s_) in arr_sites:
            _alt_name = (_source_layer if a_net == rl["src_net"]
                         else _snk_layer)
            if _alt_name == rl["face"]:
                _alt_name = None
            _commit_array(a_net, s_, face_ly, face_name=rl["face"],
                          alt_name=_alt_name)
        n_arr = sum(len(s_) for _n2, s_ in arr_sites)
        report[rl["rs"]] = {"segs": len(spine) + len(pin_plans) + len(snk),
                            "pins": "%d/%d" % (picked, len(rl["j3"])),
                            "vias": n_arr, "alt": alt_on,
                            "bcu_twins": _bcu_twins,
                            "w": w, "face": rl["face"],
                            "source_layer": _source_layer,
                            "source_spans": {_tag_layer(tag,rl['face']):list(xs)
                                             for tag,xs in _source_spans.items()},
                            "sink_layer": _snk_layer,
                            "source_segments": spine,
                            "sink_segments": snk,
                            "detours": _rail_detours,
                            "transition_search": _rail_transitions,
                            "pickup_repairs": pickup_repairs,
                            "proposal_normalization": {
                                "source": _src_normalization, "sink": _snk_normalization},
                            "dropped_pins": dropped}
        if verbose:
            print("[force-rails] %s %s->%s laid: %d segs + %d array via(s), "
                  "pins %d/%d, w=%.1f%s%s"
                  % (rl["rs"], rl["src_net"], rl["snk_net"],
                     report[rl["rs"]]["segs"], n_arr, picked, len(rl["j3"]), w,
                     (" [alt=%s]" % alt_layer) if alt_on else "",
                     (" (dropped: %s)" % "; ".join(dropped)) if dropped else ""),
                  flush=True)
    # PASS 2 -- the ampacity twins, AFTER every rail's primary copper (twins
    # yield to primaries by construction; a colliding twin is skipped and the
    # original carries alone).
    _twinned = 0
    _twin_groups = {}
    for (_rs2, _net_m, _seg_m, _fl2) in _twin_cands:
        if not isinstance(report.get(_rs2), dict):
            continue                          # its rail refused -- no primary to twin
        _twin_groups.setdefault((_rs2, _net_m, _seg_m[5], _fl2), []).append(_seg_m)
    for (_rs2, _net_m, _tag_m, _fl2), proposals in _twin_groups.items():
        import cec_parallel_copper
        legal = cec_parallel_copper.normalize_proposals([
            seg for seg in proposals
            if _collide([seg], {_net_m}, skip_refs=("FID",)) is None])
        anchors = cec_parallel_copper.native_anchor_test(
            board, _net_m, _tag_layer(_tag_m, board.GetLayerName(_fl2)))
        admitted = cec_parallel_copper.connected_proposals(legal, anchors)
        for index in admitted:
            _commit(_net_m, [legal[index]], _fl2)
        report[_rs2]["bcu_twins"] += len(admitted)
        report[_rs2]["unlanded_twin_proposals"] = (
            report[_rs2].get("unlanded_twin_proposals", 0) + len(legal)-len(admitted))
        _twinned += len(admitted)
    if verbose and _twin_cands:
        print("[force-rails] ampacity twins: %d/%d laid (pass 2, yield-to-primary)"
              % (_twinned, len(_twin_cands)), flush=True)
    if _patch_pours:
        report["_patches"] = {"pours": _patch_pours}
    if construction_evidence is not None:
        for ref, evidence in construction_evidence.items():
            outcome = report.get(ref)
            evidence['constructed'] = isinstance(outcome, dict)
            if isinstance(outcome, str):
                evidence['refusal'] = outcome
    return report


def compile_rail_pour_asks(rails, chains, *, alt_layer=None, mirror_bcu=False,
                           laid_report=None):
    """THE POUR COMPILER (§2.1/§2.4 of docs/pour-strategy-refinement-2026-07-19.md,
    owner GO "do the pour compiler... so it's done instead of deferred"): compile
    the rail plan into WIDENED same-net pour ASKS that ride the PourPlan sidecar
    and lay AFTER Freerouting (the add_power_pours doctrine -- additive same-net
    copper can never strand the locked taps). The ZONE_FILLER is DRC-aware by
    construction, so the FLOOD regions connect what the drop grammar could not:
    an unpickable J3 pin (foreign barrel underneath, jack shadow, span outlier)
    is picked up by copper FLOWING AROUND the obstacles with clearance.

    Per rail, three region families:
      1. J3 PICKUP FLOOD -- the rail's own pin-group bbox, extended down INTO
         the band row so the flood merges with the trunk. F.Cu + the alt layer.
      2. SINK FLOOD -- the TB tab field up through the sink band row. F.Cu +
         alt (+ B.Cu when the trunk mirrors there).
      3. TRUNK WIDEN -- the band row itself at ~2x the track width.
    Returns PourPlan ask dicts ({net, region_hint, layers, priority,
    provenance="rail_compiler"}); the _oracle_hints_pours locked-net filter
    exempts this provenance (deliberate plan-derived copper, not the geometric
    deriver's mega-pour class)."""
    asks = []
    laid_report = laid_report or {}

    def _planned_layer(body):
        if body == "alt" and alt_layer:
            return alt_layer
        if body == "back":
            return "B.Cu"
        return "F.Cu"

    def _uniq(*layers):
        return tuple(dict.fromkeys(ln for ln in layers if ln))

    def _mirror(layer):
        return (alt_layer or "B.Cu") if layer == "B.Cu" else "B.Cu"

    for rl in rails:
        ch = chains.get(rl["rs"]) or {}
        w = float(ch.get("w", 1.5))
        band_y = float(ch.get("band_y", 0.0))
        # Regions follow the ACTUALLY LAID source/sink layer.  The guarded lay
        # may move one side to another profile-approved routing layer; pour
        # widening must not silently revert to the ideal-plan layer.
        _body = ch.get("body", "alt")
        _rr = laid_report.get(rl["rs"], {})
        if not isinstance(_rr, dict):
            _rr = {}
        _base_layer = _planned_layer(_body)
        _src_layer = _rr.get("source_layer") or _base_layer
        _snk_layer = _rr.get("sink_layer") or _base_layer
        layers_src = _uniq("F.Cu", _src_layer)
        # 1. J3 pickup flood
        if rl["j3"]:
            xs = [q[1] for q in rl["j3"]]
            ys = [q[2] for q in rl["j3"]]
            # +3.0 beyond the band toward the shunt (owner catch 2026-07-24: the
            # rects stopped 0.4mm short of the shunt force-via rows -- measured
            # 6 dangling vias at RS1, the In2/B legs severed AT the shunt)
            reg = (min(xs) - 2.2, min(ys) - 1.2,
                   max(xs) + 2.2, max(band_y + w / 2.0 + 3.0, max(ys) + 1.2))
            for ln in layers_src:
                asks.append({"net": rl["src_net"], "region_hint": reg,
                             "layers": (ln,), "priority": 3,
                             "provenance": "rail_compiler"})
        # 2. sink flood
        sd = ch.get("snk_desc")
        if rl["tb"] and sd:
            _lx, _lyy, band2, _wd = sd
            txs = [q[2] for q in rl["tb"]]
            tys = [q[3] for q in rl["tb"]]
            # -3.0 above the band toward the shunt (same 2026-07-24 catch: cover
            # the shunt pad + its outboard via row so the sink flood BONDS there)
            reg = (min(txs) - 2.2, min(band2 - w / 2.0 - 3.0, min(tys) - 1.2),
                   max(txs) + 2.2, max(tys) + 1.2)
            lset = _uniq("F.Cu", _snk_layer,
                         _mirror(_snk_layer) if mirror_bcu else None)
            for ln in lset:
                asks.append({"net": rl["snk_net"], "region_hint": reg,
                             "layers": (ln,), "priority": 3,
                             "provenance": "rail_compiler"})
        # 3. trunk widen -- EVERY non-face trunk seg, src AND snk (owner
        # 2026-07-20: rectangular pours over the whole trunk so the spine
        # tracks read as clean rectangles on the final board)
        for _net, _segments, _actual_layer in (
                (rl["src_net"], _rr.get("source_segments",ch.get("src")) or (), _src_layer),
                (rl["snk_net"], _rr.get("sink_segments",ch.get("snk")) or (), _snk_layer)):
            segs = [s for s in _segments
                    if s[5] != "face"
                    and (abs(s[2] - s[0]) > 2.0
                         or abs(s[3] - s[1]) > 2.0)]
            for (x1, y1, x2, y2, w2, _tg) in segs:
                if abs(x2 - x1) >= abs(y2 - y1):  # horizontal run
                    reg = (min(x1, x2) - 0.5, min(y1, y2) - w2,
                           max(x1, x2) + 0.5, max(y1, y2) + w2)
                else:                             # vertical run
                    reg = (min(x1, x2) - w2, min(y1, y2) - 0.5,
                           max(x1, x2) + w2, max(y1, y2) + 0.5)
                lset = _uniq(
                    _actual_layer,
                    _mirror(_actual_layer) if mirror_bcu else None)
                for ln in lset:
                    asks.append({"net": _net, "region_hint": reg,
                                 "layers": (ln,), "priority": 3,
                                 "provenance": "rail_compiler"})
    return asks
