"""Short additive pin connections inside already-empty pour clearance space.

The normal router continues to reserve authored power-pour contours. This
narrow exception never asks the filler to carve a route: the complete trace
and clearance envelope must already miss every frozen filled power polygon.
A post-refill integer-polygon subtraction independently proves zero copper
loss before the candidate may be retained.
"""
import math


def capture(board):
    import pcbnew
    import cec_fr
    rows = {}
    for zone in board.Zones():
        if (zone.GetIsRuleArea()
                or not (zone.GetZoneName() or '').startswith(cec_fr.PIPELINE_POUR_PREFIXES)):
            continue
        for layer in zone.GetLayerSet().CuStack():
            key = (zone.m_Uuid.AsString(), int(layer))
            poly = zone.GetFilledPolysList(layer)
            if not zone.IsFilled() or not poly.OutlineCount():
                raise ValueError('protected pour fill is missing')
            rows[key] = pcbnew.SHAPE_POLY_SET(poly)
    return rows


def preservation(frozen, board):
    import pcbnew
    try:
        current = capture(board)
    except ValueError as exc:
        return dict(ok=False, error=str(exc))
    if current.keys() != frozen.keys():
        return dict(ok=False, error='protected pour identity changed')
    rows = []
    for (uuid, layer), before in sorted(frozen.items()):
        missing = pcbnew.SHAPE_POLY_SET(before)
        missing.BooleanSubtract(current[(uuid, layer)])
        rows.append(dict(uuid=uuid, layer=board.GetLayerName(layer),
            lost_polygons=missing.OutlineCount(), lost_area_nm2=abs(missing.Area())))
    return dict(ok=all(row['lost_polygons'] == 0 for row in rows),
        checked_layers=len(rows), tolerance_nm=0, rows=rows)


def refreshed_control(board):
    """Establish the no-edit native fill before attributing a delta to routing.

    Both transitions remain exact: saved source -> no-edit control and
    control -> routed candidate must each lose zero protected copper. This
    is not a numerical allowance or permission to discard refill drift.
    """
    import pcbnew
    source = capture(board)
    for zone in board.Zones():
        zone.UnFill()
    import cec_zone_fill
    cec_zone_fill.fill(board)
    board.BuildConnectivity()
    proof = preservation(source, board)
    return (capture(board) if proof['ok'] else None), proof


def plan(board, endpoints, *, net_code, width_nm, clearance_nm,
         max_span_mm=2.0):
    """Read-only, two-live-SMD-pad, direct octilinear existing-void plan."""
    import pcbnew
    import cec_fr
    if not math.isfinite(max_span_mm) or max_span_mm <= 0:
        raise ValueError('void connection span must be finite and positive')
    if (len(endpoints) != 2 or net_code <= 0 or width_nm <= 0
            or clearance_nm < 0 or any(ep.get('kind') != 'pad' for ep in endpoints)):
        return None
    pads = []
    for ep in endpoints:
        matches = [pad for fp in board.GetFootprints() if fp.GetReference() == ep.get('ref')
            for pad in fp.Pads() if str(pad.GetNumber()) == str(ep.get('pad'))
            and pad.GetNetCode() == net_code
            and pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD
            and (pad.GetPosition().x, pad.GetPosition().y) ==
                (round(float(ep['x_mm'])*1e6), round(float(ep['y_mm'])*1e6))]
        if len(matches) != 1:
            return None
        pads.append(matches[0])
    a, b = [pad.GetPosition() for pad in pads]
    dx, dy = b.x-a.x, b.y-a.y
    if ((dx == dy == 0) or (dx and dy and abs(dx) != abs(dy))
            or math.hypot(dx, dy) > max_span_mm*1e6
            or any(min(pad.GetSize().x, pad.GetSize().y) < width_nm for pad in pads)):
        return None
    if not cec_fr._edge_leg_clear(board, a, b, width_nm//2):
        return None
    shape = pcbnew.SHAPE_SEGMENT(a, b, width_nm)
    resolver = cec_fr._foreign_clearance_resolver(board)
    for layer in sorted(set(pads[0].GetLayerSet().CuStack()) &
                        set(pads[1].GetLayerSet().CuStack())):
        _zones, copper = cec_fr._foreign_shape_indexes(board, layer, {net_code}, cache={})
        if not cec_fr._snapshot_foreign_clear(a, b, width_nm, clearance_nm, [], copper):
            continue
        evidence, blocked = [], False
        for zone in board.Zones():
            if (zone.GetIsRuleArea() or zone.GetNetCode() == net_code
                    or not zone.IsOnLayer(layer)
                    or not (zone.GetZoneName() or '').startswith(cec_fr.PIPELINE_POUR_PREFIXES)):
                continue
            gap = max(clearance_nm, zone.GetLocalClearance(), resolver(zone, layer))
            if not zone.Outline().Collide(shape, gap):
                continue
            fill = zone.GetFilledPolysList(layer)
            if (not zone.IsFilled() or not fill.OutlineCount() or fill.Collide(shape, gap)):
                blocked = True
                break
            evidence.append(dict(uuid=zone.m_Uuid.AsString(), name=zone.GetZoneName(),
                layer=board.GetLayerName(layer), required_clearance_mm=gap/1e6))
        if evidence and not blocked:
            return dict(operations=[('trk', a, b, width_nm, layer)],
                evidence=dict(mode='short_existing_pour_void', length_mm=math.hypot(dx,dy)/1e6,
                    max_span_mm=max_span_mm, width_mm=width_nm/1e6, zones=evidence,
                    requires_post_refill_zero_copper_loss=True))
    return None
