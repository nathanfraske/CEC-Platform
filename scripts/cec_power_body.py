"""Shared mounting-face body reservations for generated power territory.

This retains the existing endpoint/interface exemptions. Ordinary signal
routing is not governed by these pour-only body rules. Inner-layer copper is
governed by pads, holes and native rule areas, not a projected surface body.
"""


def body_regions(board, *, margin_mm=0.0):
    import math
    import pcbnew
    margin = float(margin_mm)
    if not math.isfinite(margin) or margin < 0:
        raise ValueError('invalid power body clearance')
    rows = []
    for fp in board.GetFootprints():
        ref = str(fp.GetReference() or '')
        # Existing power-territory policy: interface and board-only mechanics
        # are controlled by native pad/hole geometry, not a courtyard block.
        if ref.startswith(('J', 'TB', 'H', 'LOGO', 'FID')) or not hasattr(fp, 'IsFlipped'):
            continue
        flipped = bool(fp.IsFlipped())
        try:
            courtyard = fp.GetCourtyard(pcbnew.B_CrtYd if flipped else pcbnew.F_CrtYd)
            bb = courtyard.BBox() if courtyard.OutlineCount() else fp.GetBoundingBox(False, False)
        except Exception:
            bb = fp.GetBoundingBox(False, False)
        pads = list(fp.Pads())
        rows.append(dict(ref=ref, layer='B.Cu' if flipped else 'F.Cu',
            nets=sorted({str(p.GetNetname()) for p in pads if p.GetNetname()}),
            net_codes=sorted({int(p.GetNetCode()) for p in pads if p.GetNetCode() > 0}),
            box=[bb.GetLeft()/1e6-margin, bb.GetTop()/1e6-margin,
                 bb.GetRight()/1e6+margin, bb.GetBottom()/1e6+margin]))
    return rows


def foreign_regions(board, net_code, *, layer=None, margin_mm=0.0):
    return [row for row in body_regions(board, margin_mm=margin_mm)
            if int(net_code) not in row['net_codes']
            and (layer is None or row['layer'] == layer)]


def landing_clear(regions, x_mm, y_mm, layers, *, radius_mm):
    """Seat the complete landing outside already-clearanced foreign bodies.

    ``regions`` must come from ``foreign_regions`` for the current net. Only
    the actual transition faces constrain its landing copper; a body on the
    opposite face is not an obstacle on every inner layer. The square collar
    matches the conservative Manhattan outline clipping, not just the drill.
    """
    import math
    x, y, radius = float(x_mm), float(y_mm), float(radius_mm)
    if not all(math.isfinite(v) for v in (x, y, radius)) or radius < 0:
        raise ValueError('invalid bridge landing geometry')
    for row in regions:
        if row['layer'] not in layers:
            continue
        x0, y0, x1, y1 = row['box']
        if x + radius >= x0 and x - radius <= x1 and y + radius >= y0 and y - radius <= y1:
            return False
    return True
