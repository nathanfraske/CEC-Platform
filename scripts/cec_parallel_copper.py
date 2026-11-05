"""Admit optional parallel conductors only as paths between real contacts.

This trims uncommitted proposals, never existing copper or required vias.
Widths and primary conductors are immutable; thermal qualification may still
require a larger/full parallel path than this topological screen can supply.
"""
from shapely.geometry import LineString, Point


def normalize_proposals(segments):
    """Split at existing endpoints and deduplicate covered collinear runs.

    Two overlapping proposals must not supply one another's missing endpoint
    contact. Keep the widest proposed copper at every coincident run; this is
    representation normalization, not current-width optimization.
    """
    points = {tuple(row[start:start+2]) for row in segments for start in (0,2)}
    pieces = {}
    for row in segments:
        line = LineString([row[:2],row[2:4]])
        if row[4] <= 0:
            raise ValueError('invalid parallel conductor proposal')
        if line.length <= 1e-9:
            continue  # A collapsed collector endpoint is not a parallel path.
        cuts = sorted({line.project(Point(*point)) for point in points
                       if line.distance(Point(*point)) <= 1e-8})
        for start,end in zip(cuts,cuts[1:]):
            if end-start <= 1e-9:
                continue
            a,b = line.interpolate(start),line.interpolate(end)
            ends = tuple(sorted(((round(a.x,9),round(a.y,9)),
                                 (round(b.x,9),round(b.y,9)))))
            key = (ends,tuple(row[5:]))
            part = (*ends[0],*ends[1],row[4],*row[5:])
            if key not in pieces or pieces[key][4] < part[4]:
                pieces[key] = part
    return [pieces[key] for key in sorted(pieces)]


def connected_proposals(segments, anchored_at):
    """Return original indices; ``anchored_at(point)`` queries native copper.

    The input is a single net on a single actual layer. Iteratively discard
    open-ended leaves, then reject components without two spatially distinct
    contacts to the primary board. Proposal order and endpoint direction do
    not affect the result.
    """
    ends = [(tuple(row[:2]), tuple(row[2:4])) for row in segments]
    lines = [LineString(pair) for pair in ends]
    shapes = [line.buffer(float(row[4])/2, quad_segs=8)
              for line,row in zip(lines,segments)]
    active = set(range(len(segments)))
    contacts = {point for pair in ends for point in pair if anchored_at(point)}
    while True:
        rejected = {i for i in active if any(
            point not in contacts and not any(j != i and lines[j].distance(Point(*point)) <= 1e-6
                                              for j in active)
            for point in ends[i])}
        if not rejected:
            break
        active -= rejected
    remaining = set(active)
    accepted = set()
    while remaining:
        component = {min(remaining)}
        frontier = set(component)
        while frontier:
            neighbors = {j for j in remaining-component if any(
                shapes[j].intersects(shapes[i]) for i in frontier)}
            component |= neighbors
            frontier = neighbors
        points = {p for i in component for p in ends[i] if p in contacts}
        if len(points) >= 2:
            accepted |= component
        remaining -= component
    return sorted(accepted)


def native_anchor_test(board, net, layer):
    """Actual same-layer pad/track/via contact, never outline/bbox proxies."""
    import pcbnew
    lid = board.GetLayerID(layer)
    items = [item for item in board.GetTracks()
             if item.GetNetname() == net and item.IsOnLayer(lid)]
    items.extend(pad for fp in board.GetFootprints() for pad in fp.Pads()
                 if pad.GetNetname() == net and pad.IsOnLayer(lid))
    def anchored(point):
        at = pcbnew.VECTOR2I(int(round(point[0]*1e6)), int(round(point[1]*1e6)))
        return any(item.HitTest(at) for item in items)
    return anchored
