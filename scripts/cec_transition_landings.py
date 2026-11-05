"""Construct and prove complete power-transition fields on their actual layers.

The caller owns a disposable construction board and saves it only on success.
Native filling and the shared pour policy, not a capsule approximation of a
rectangle, decide which copper survives. This proves landing continuity only;
current capacity, local return access and final DRC remain separate gates.
"""
from __future__ import annotations

import math


class LandingRefused(RuntimeError):
    def __init__(self, report):
        self.evidence = report
        super().__init__('power transition landing refused: %s' % report['reason'])


def patches_for(net, sites, layers, *, diameter_mm, drill_mm, margin_mm):
    sites = tuple(tuple(map(float, site)) for site in sites)
    layers = tuple(dict.fromkeys(layers))
    dimensions = (diameter_mm, drill_mm, margin_mm)
    if (not net or len(layers) < 2 or not all(layers) or not sites
            or any(len(site) != 2 for site in sites)
            or len(set(sites)) != len(sites)
            or not all(math.isfinite(v) for site in sites for v in site)
            or not all(math.isfinite(v) for v in dimensions)
            or not 0 < drill_mm < diameter_mm <= 2 * margin_mm):
        raise ValueError('invalid transition field')
    xs, ys = zip(*sites)
    x0, x1 = min(xs)-margin_mm, max(xs)+margin_mm
    y0, y1 = min(ys)-margin_mm, max(ys)+margin_mm
    field = dict(sites=sites, layers=layers, diameter_mm=diameter_mm,
                 drill_mm=drill_mm)
    return [dict(net=net, layer=layer, priority=3, name='patch:'+net,
                 polygon=[(x0,y0),(x1,y0),(x1,y1),(x0,y1)], transition=field)
            for layer in layers]


def _filled_rows(board, net, layers):
    """Actual native fill only, including cut-outs and drilled holes."""
    rows = []
    for zone in board.Zones():
        if zone.GetIsRuleArea() or zone.GetNetname() != net:
            continue
        for layer in layers:
            lid = board.GetLayerID(layer)
            if not zone.IsOnLayer(lid):
                continue
            poly = zone.GetFilledPolysList(lid)
            def points(contour):
                return [(contour.CPoint(i).x / 1e6, contour.CPoint(i).y / 1e6)
                        for i in range(contour.PointCount())]
            for index in range(poly.OutlineCount()):
                exterior = points(poly.Outline(index))
                if len(exterior) >= 3:
                    rows.append(dict(net=net, layer=layer, polygon=exterior,
                        holes=[points(poly.Hole(index, hole))
                               for hole in range(poly.HoleCount(index))]))
    return rows


def audit(board, patches):
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    import cec_pour_plan
    import cec_slab_pour

    fields = {}
    for patch in patches:
        field = patch['transition']
        key = (patch['net'], tuple(field['layers']),
               tuple(tuple(s) for s in field['sites']),
               field['diameter_mm'], field['drill_mm'])
        fields[key] = field
    reports = []
    for (net, layers, sites, diameter, drill), field in fields.items():
        record = dict(net=net, layers=list(layers), required=len(sites),
                      sites=[list(s) for s in sites], ok=False)
        reports.append(record)
        # A drawn zone cannot stand in for an omitted/changed barrel.
        actual = set()
        for via in board.GetTracks():
            if via.GetClass() != 'PCB_VIA' or via.GetNetname() != net:
                continue
            if (all(via.IsOnLayer(board.GetLayerID(layer)) for layer in layers)
                    and abs(via.GetWidth(via.TopLayer()) / 1e6 - diameter) < 1e-6
                    and abs(via.GetDrillValue() / 1e6 - drill) < 1e-6):
                at = via.GetPosition()
                actual.add((round(at.x / 1e6, 6), round(at.y / 1e6, 6)))
        if any((round(x,6),round(y,6)) not in actual for x,y in sites):
            record['reason'] = 'required_barrel_missing_or_changed'
            continue
        rows = _filled_rows(board, net, layers)
        vias = [dict(field_index=0, x_mm=x, y_mm=y) for x,y in sites]
        try:
            for layer in layers[1:]:
                cec_slab_pour.require_bridge_landings(rows, vias,
                    [(0, 0, layers[0], layer, 1., 0.)], diameter_mm=diameter)
        except cec_slab_pour.BridgeFieldRefused as exc:
            record.update(reason='native_fill_does_not_land_entire_field',
                          coverage=exc.evidence)
            continue
        own = cec_pour_plan._own_track_polys(
            board, board.GetNetcodeFromNetname(net), layers)
        # An isolated filled island around each via is not a current path.
        # Each actual transition layer must join the whole field to a primary
        # same-net conductor, not merely touch a via of the field itself.
        disconnected = []
        for layer in layers:
            copper = unary_union([Polygon(row['polygon'], row['holes'])
                                  for row in rows if row['layer'] == layer])
            parts = list(copper.geoms) if hasattr(copper, 'geoms') else [copper]
            tracks = unary_union(own[layer])
            if not any(all(part.covers(Point(*site)) for site in sites)
                       and part.intersection(tracks).area > 1e-8 for part in parts):
                disconnected.append(layer)
        if disconnected:
            record.update(reason='field_not_joined_to_primary', layers_failed=disconnected)
        else:
            record.update(ok=True, reason='native_two_layer_landing_verified')
    return dict(schema=1, ok=all(row['ok'] for row in reports), fields=reports,
                release_authority=False)


class _ProposalFilter:
    """Callable field test plus necessary per-site landing qualification."""
    def __init__(self, field_test, site_test):
        self._field_test = field_test
        self._site_test = site_test

    def __call__(self, sites):
        return self._field_test(sites)

    def viable_sites(self, sites):
        return [site for site in sites if self._site_test(site)]


def proposal_filter(board, net, layers, segments, *, portals=(),
                    pending_segments=(), clearance_mm=.25, margin_mm=.65,
                    diameter_mm=.9, evidence=None):
    """Cheap necessary landing test before choosing an uncommitted via field.

    Segments use real layer names. This mirrors conservative outline clipping
    and rejects a disconnected/scattered field; it does NOT replace native
    filling or the complete landing audit after construction.
    ``viable_sites`` discards individually clipped lands before a caller's
    bounded compact-subset search. It cannot certify a complete field.
    """
    from shapely.geometry import box, Point, LineString
    from shapely.ops import unary_union
    import cec_pour_plan
    from cec_slab_pour import copper_contains_disk
    obstacles=cec_pour_plan._geo_obstacles(
        board,board.GetNetcodeFromNetname(net),layers,clearance_mm,0.)
    forbidden={}; primary={}
    for layer in layers:
        lid=board.GetLayerID(layer)
        values=[box(*g.bounds) for g in obstacles[layer] if not g.is_empty]
        for p in portals:
            if p['net']==net or lid not in p['layer_ids']: continue
            x,y=p['at_mm'];r=p['diameter_mm']/2+clearance_mm
            values.append(box(x-r,y-r,x+r,y+r))
        for other,x1,y1,x2,y2,width,tag in pending_segments:
            if other==net or board.GetLayerID(tag)!=lid: continue
            g=LineString(((x1,y1),(x2,y2))).buffer(width/2+clearance_mm,cap_style=3)
            values.append(box(*g.bounds))
        forbidden[layer]=unary_union(values)
        primary[layer]=unary_union([
            LineString((s[:2],s[2:4])).buffer(s[4]/2)
            for s in segments if board.GetLayerID(s[5])==lid])
    def allowed(sites):
        if not sites: return False
        if evidence is not None:
            evidence['attempted']=evidence.get('attempted',0)+1
        xs,ys=zip(*sites)
        declared=box(min(xs)-margin_mm,min(ys)-margin_mm,
                     max(xs)+margin_mm,max(ys)+margin_mm)
        lands=[Point(*p) for p in sites]
        radius=diameter_mm/2+.05
        for layer in layers:
            remaining=declared.difference(forbidden[layer])
            parts=list(remaining.geoms) if hasattr(remaining,'geoms') else [remaining]
            if not any(all(copper_contains_disk(part,land,radius) for land in lands)
                       and part.intersection(primary[layer]).area>1e-8 for part in parts):
                if evidence is not None:
                    complete=[part for part in parts if all(copper_contains_disk(part,land,radius) for land in lands)]
                    uncovered=[list(site) for site,land in zip(sites,lands)
                               if not any(copper_contains_disk(part,land,radius) for part in parts)]
                    reason=('field_land_clipped' if uncovered else
                            'field_not_joined_to_primary' if complete else 'split_field')
                    counts=evidence.setdefault('rejection_counts',{})
                    counts[reason]=counts.get(reason,0)+1
                    samples=evidence.setdefault('samples',[])
                    sample=dict(reason=reason,layer=layer,required=len(sites),
                                uncovered_sites=uncovered,site_bounds=list(declared.bounds))
                    if len(samples)<4 and sample not in samples:
                        samples.append(sample)
                return False
        if evidence is not None:
            evidence['accepted']=True
        return True
    def site_allowed(site):
        point=Point(*site)
        return all(forbidden[layer].is_valid and (forbidden[layer].is_empty
                   or (not forbidden[layer].covers(point)
                       and forbidden[layer].distance(point)+1e-9>=diameter_mm/2+.05))
                   for layer in layers)
    return _ProposalFilter(allowed,site_allowed)


def constrain_new_outlines(board, zones, *, portals=(), clearance_mm=.25):
    """Cut owned declarations around foreign copper and reserved barrels.

    Filler antipads alone do not satisfy the no-foreign-in-pour rule. Use
    conservative Manhattan obstacle bounds and apply after boundary cleanup
    so cleanup cannot regrow a removed reservation. Nothing pre-existing is
    passed to this function; every via and primary track stays untouched.
    """
    from shapely.geometry import box
    from shapely.ops import unary_union
    import cec_fr
    import cec_pour_plan
    import cec_native_items
    cache = {}
    changes, empty = [], []
    for zone in zones:
        net, lid = zone.GetNetname(), zone.GetLayer()
        layer = board.GetLayerName(lid)
        key = (net,lid)
        if key not in cache:
            obstacles = cec_pour_plan._geo_obstacles(
                board,zone.GetNetCode(),[layer],clearance_mm,0.)[layer]
            rectangles = [box(*g.bounds) for g in obstacles if not g.is_empty]
            for portal in portals:
                if portal['net'] == net or lid not in portal['layer_ids']:
                    continue
                x,y = portal['at_mm']
                r = portal['diameter_mm']/2+clearance_mm
                rectangles.append(box(x-r,y-r,x+r,y+r))
            cache[key] = unary_union(rectangles)
        before = cec_fr._zone_outline_geometry(zone)
        after = before.difference(cache[key])
        removed = before.area-after.area
        if removed <= 1e-9:
            continue
        changes.append(dict(net=net,layer=layer,removed_mm2=removed))
        if after.is_empty:
            empty.append(zone)
        else:
            cec_fr._replace_zone_outline(zone,after)
    cec_native_items.discard_items(board,empty)
    return dict(schema=1,changes=changes,scope='new_landing_declarations_only',
                clearance_mm=clearance_mm)


def install(board, patches, *, portals=(), clearance_mm=None):
    """Fail closed if choke-point policy, clipping or fill loses any landing."""
    import cec_fr
    patches = list(patches)
    if not patches:
        return dict(schema=1, ok=True, fields=[], release_authority=False)
    import cec_portal_copper
    import cec_zone_fill
    clearance = cec_portal_copper.reservation_clearance(
        board, .25 if clearance_mm is None else clearance_mm)
    original_ids = {z.m_Uuid.AsString() for z in board.Zones()}
    cec_fr.add_power_pours(board, patches, fill=False)
    created = [z for z in board.Zones() if z.m_Uuid.AsString() not in original_ids
               and not z.GetIsRuleArea()]
    outline_evidence = constrain_new_outlines(
        board,created,portals=portals,clearance_mm=clearance)
    for zone in board.Zones():
        zone.UnFill()
    cec_zone_fill.fill(board)
    report = audit(board, patches)
    report['outline_reservations'] = outline_evidence
    if not report['ok']:
        report['reason'] = 'required_native_landing_missing'
        raise LandingRefused(report)
    return report
