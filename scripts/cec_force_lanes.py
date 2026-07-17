#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# cec_force_lanes -- the SHARED fat-force-copper lay for the 12VHPWR straight-
# through boards (owner rung 2026-07-11: "the trace routing to and from the
# shunts needs to be SET and not infringed on"). One geometry, two callers:
#
#   * cec_force_thermal_probe.phase_lay  -- the stripped thermal probe
#   * cec_synth_pipeline.materialize     -- the fresh-wave board (LOCKED, so the
#     FR residual protects it via the existing locked->fix->protect machinery,
#     exactly like the blueprint cells' copper)
#
# The geometry is the DRC-proven v7 lay (0 shorts / 0 clearance on the probe,
# battery-solved through the worst-case ladder):
#   HI (F.Cu): 12V pad -> 1.4mm stub -> 1.0mm jog to the lane's OWN barrel gap
#              (left trio pin-1.5 / right trio pin+1.5) -> 0.95mm neck through
#              the 1.48mm GND-barrel gap -> 2.5mm vertical -> nested Manhattan
#              fan band (pitch 2.9, right-trio +1.45 endcap offset) -> RS.1.
#   LO (B.Cu): RS.2 -> 1.0mm F.Cu spokes -> up-to-4-via field (0.9/0.5,
#              clearance-searched vs cell copper) -> 1.2mm B.Cu laterals ->
#              2.0mm collector -> 2.5mm vertical -> mirrored nested band ->
#              0.95mm neck through J4's GND row -> 1.5mm into the J4 pad.
#
# HONESTY: before laying a lane, every planned F.Cu segment is checked against
# FOREIGN pads (anything not J3/J4/that lane's own nets); a collision REFUSES
# the whole lane with the collider named (escalate-never-force -- the cell
# guard's discipline). On the fresh wave the placement corridors should make
# refusals impossible; a refusal there means the corridor reservation failed
# and must be fixed at the placer, never by forcing copper.

MM = 1_000_000


def hi_net(n, netnames):
    """Lane n's pre-shunt net: beta names lane 6 /FAN_12V (J2 fan tap)."""
    if n == 6 and "/FAN_12V" in netnames:
        return "/FAN_12V"
    return f"/SENSEP{n}_HI"


def _seg_pt_d2(x, y, sx, sy, ex, ey):
    dx, dy = ex - sx, ey - sy
    L2 = dx * dx + dy * dy or 1e-9
    t = max(0.0, min(1.0, ((x - sx) * dx + (y - sy) * dy) / L2))
    qx, qy = sx + t * dx, sy + t * dy
    return (qx - x) ** 2 + (qy - y) ** 2


def lay_force_lanes(board, *, lock=True, verbose=True):
    """Lay the six force lanes onto *board* (open pcbnew BOARD). Returns
    {lane: {"vias": k} | "MISSING PADS" | "REFUSED: <collider>"}. Caller saves."""
    import pcbnew
    fcu, bcu = board.GetLayerID("F.Cu"), board.GetLayerID("B.Cu")
    nets = {str(k): v for k, v in board.GetNetInfo().NetsByName().items()}

    pads = []                                     # (ref, num, net, x, y, half)
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for p_ in fp.Pads():
            pos = p_.GetPosition()
            sz = p_.GetSize()
            half = max(sz.x, sz.y) / (2.0 * MM)   # true half-extent (guard = DRC, not 2mm-pad guess)
            pads.append((ref, p_.GetNumber(), p_.GetNetname(), pos.x / MM, pos.y / MM, half))

    lock_vias, lock_segs = [], []
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T and t.IsLocked():
            pos = t.GetPosition()
            lock_vias.append((pos.x / MM, pos.y / MM))
        elif t.IsLocked():
            s_, e_ = t.GetStart(), t.GetEnd()
            lock_segs.append((t.GetNetname(), s_.x / MM, s_.y / MM, e_.x / MM, e_.y / MM))

    added = []

    def track(net, x1, y1, x2, y2, w, layer):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(int(x1 * MM), int(y1 * MM)))
        t.SetEnd(pcbnew.VECTOR2I(int(x2 * MM), int(y2 * MM)))
        t.SetWidth(int(w * MM))
        t.SetLayer(layer)
        ni = nets.get(net)
        if ni is not None:
            t.SetNet(ni)
        if lock:
            t.SetLocked(True)
        board.Add(t)
        added.append(t)

    def via(net, x, y):
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(int(x * MM), int(y * MM)))
        v.SetDrill(int(0.5 * MM))
        v.SetWidth(int(0.9 * MM))
        ni = nets.get(net)
        if ni is not None:
            v.SetNet(ni)
        if lock:
            v.SetLocked(True)
        board.Add(v)
        added.append(v)

    def clear_spot(x, y):
        """Via site must clear foreign pads + locked cell copper."""
        for ref, num, net, px, py, half in pads:
            if ref.startswith(("J3", "J4")):
                continue
            if abs(px - x) < 1.35 and abs(py - y) < 1.35 \
                    and not net.startswith("/SENSEP") and net != "/FAN_12V":
                return False
        for vx, vy in lock_vias:
            if (vx - x) ** 2 + (vy - y) ** 2 < 1.45 ** 2:
                return False
        for net, sx, sy, ex, ey in lock_segs:
            if _seg_pt_d2(x, y, sx, sy, ex, ey) < 0.85 ** 2:
                return False
        return True

    def lane_collider(plan, own_nets):
        """First foreign pad within reach of a planned segment (w/2 + pad-half
        1.0 + clearance 0.25), or None. Foreign = not J3/J4/own-lane/GND-via-
        exempt; GND THT barrels are part of the DESIGN (the necks thread their
        gaps) so J3/J4 are skipped -- the geometry owns that clearance."""
        for (x1, y1, x2, y2, w, _ly) in plan:
            for ref, num, net, px, py, half in pads:
                if ref.startswith(("J3", "J4", "FID")) or net in own_nets:
                    continue
                reach = (w / 2.0 + half + 0.25) ** 2
                if _seg_pt_d2(px, py, x1, y1, x2, y2) < reach:
                    return "%s.%s [%s] at (%.1f,%.1f)" % (ref, num, net, px, py)
        return None

    j3_gnd = sorted(y for r, n, net, x, y, h_ in pads if r == "J3" and net == "GND")
    j4_gnd = sorted(y for r, n, net, x, y, h_ in pads if r == "J4" and net == "GND")
    j3_gnd_y = j3_gnd[0] if j3_gnd else None
    j4_gnd_y = j4_gnd[0] if j4_gnd else None

    report = {}
    for n in range(1, 7):
        hi, lo = hi_net(n, nets), f"/SENSEP{n}_LO"
        rs1 = next(((x, y) for r, pn, net, x, y, h_ in pads if r == f"RS{n}" and net == hi), None)
        rs2 = next(((x, y) for r, pn, net, x, y, h_ in pads if r == f"RS{n}" and net == lo), None)
        j3p = [(x, y) for r, pn, net, x, y, h_ in pads if r == "J3" and net == hi]
        j4p = [(x, y) for r, pn, net, x, y, h_ in pads if r == "J4" and net == lo]
        if not (rs1 and rs2 and j3p and j4p and j3_gnd_y and j4_gnd_y):
            report[n] = "MISSING PADS"
            continue
        p12 = min(j3p, key=lambda q: abs(q[0] - rs1[0]))
        p4 = min(j4p, key=lambda q: abs(q[0] - rs2[0]))
        gap_dir = -1.5 if n <= 3 else 1.5
        rank = (n - 1) if n <= 3 else (6 - n)
        off = 1.45 if n > 3 else 0.0
        xn = p12[0] + gap_dir
        fan_y = j3_gnd_y + 3.2 + 2.9 * rank + off

        # ---- plan the HI path (F.Cu), then guard, then commit
        fx, fy = p12
        hi_plan = [
            (fx, fy, fx, fy + 0.8, 1.4, fcu),
            (fx, fy + 0.8, xn, j3_gnd_y - 1.9, 1.0, fcu),
            (xn, j3_gnd_y - 1.9, xn, j3_gnd_y + 1.9, 0.95, fcu),
            (xn, j3_gnd_y + 1.9, xn, fan_y, 2.5, fcu),
            (xn, fan_y, rs1[0], fan_y, 2.5, fcu),
            (rs1[0], fan_y, rs1[0], rs1[1], 2.5, fcu),
        ]
        own = {hi, lo}
        col = lane_collider(hi_plan, own)
        if col:
            # HOOK-DESCENT fallback (lane 6 vs the right-edge RJ-45): drop on an
            # offset column clear of the obstacle, approach the shunt from ABOVE
            # (the cell's validated top-entry window), same 2.5mm cross-section.
            for hx in (rs1[0] - 3.5, rs1[0] + 3.5, rs1[0] - 4.5):
                hook = hi_plan[:3] + [
                    (xn, j3_gnd_y + 1.9, xn, fan_y, 2.5, fcu),
                    (xn, fan_y, hx, fan_y, 2.5, fcu),
                    (hx, fan_y, hx, rs1[1] - 1.2, 2.5, fcu),
                    (hx, rs1[1] - 1.2, rs1[0], rs1[1] - 1.2, 2.5, fcu),
                    (rs1[0], rs1[1] - 1.2, rs1[0], rs1[1], 2.5, fcu),
                ]
                if lane_collider(hook, own) is None:
                    hi_plan, col = hook, None
                    break
        if col:
            report[n] = "REFUSED: HI vs " + col
            continue

        # ---- LO via field beside RS.2 (F.Cu spokes -> B.Cu)
        lane_x = rs2[0]
        sites = []
        for dy in (1.3, 2.0, 2.7, 3.4, 4.1):
            for dx in (-1.7, 1.7, -1.0, 1.0, 0.0):
                if len(sites) >= 4:
                    break
                cx, cy = lane_x + dx, rs2[1] + dy
                if clear_spot(cx, cy) and all(
                        (cx - a) ** 2 + (cy - b) ** 2 >= 1.15 ** 2 for a, b in sites):
                    sites.append((cx, cy))
        if not sites:
            report[n] = "REFUSED: no clear LO via site"
            continue
        sy_max, sy_min = max(b for a, b in sites), min(b for a, b in sites)
        y_h = j4_gnd_y - 3.2 - 2.9 * rank - off
        xn4 = p4[0] + gap_dir
        lo_spokes = [(rs2[0], rs2[1], cx, cy, 1.0, fcu) for cx, cy in sites]
        col = lane_collider(lo_spokes, own)
        if col:
            report[n] = "REFUSED: LO spoke vs " + col
            continue

        # ---- commit
        for seg in hi_plan:
            track(hi, *seg[:4], seg[4], seg[5])
        for cx, cy in sites:
            via(lo, cx, cy)
            track(lo, rs2[0], rs2[1], cx, cy, 1.0, fcu)
            track(lo, cx, cy, lane_x, cy, 1.2, bcu)
        track(lo, lane_x, sy_min, lane_x, sy_max, 2.0, bcu)
        track(lo, lane_x, sy_max, lane_x, y_h, 2.5, bcu)
        track(lo, lane_x, y_h, xn4, y_h, 2.5, bcu)
        track(lo, xn4, y_h, xn4, j4_gnd_y - 1.9, 2.5, bcu)
        track(lo, xn4, j4_gnd_y - 1.9, xn4, j4_gnd_y + 1.9, 0.95, bcu)
        track(lo, xn4, j4_gnd_y + 1.9, p4[0], p4[1], 1.5, bcu)
        report[n] = {"vias": len(sites)}
    return report
