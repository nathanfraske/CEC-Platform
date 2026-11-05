"""Route a declared interface tail to its ACTUAL pad, using the shared router.

No saved endpoint coordinate is treated as a pin. The caller owns the trunk,
zone-refill policy and final full DRC; failed tail search never emits copper.
"""
import time


def resolve_point(point, anchor, *, poses, outline):
    """Resolve explicit edge/part-local construction datums, never guessed refs.

    Axes not selected by the declaration retain their authored board coordinate.
    Part-local offsets rotate with that part; edge offsets are inward-positive.
    """
    import math
    result = list(map(float, point))
    axes = anchor.get('axes', ('x', 'y'))
    if not axes or set(axes)-{'x','y'} or len(result)!=2:
        raise ValueError('explicit point anchor axes required')
    if 'footprint' in anchor:
        x,y,angle=poses[anchor['footprint']]
        dx,dy=map(float,anchor.get('offset_mm',(0,0)))
        a=math.radians(angle)
        target=(x+dx*math.cos(a)+dy*math.sin(a), y-dx*math.sin(a)+dy*math.cos(a))
    elif 'edge' in anchor:
        x0,y0,x1,y1=map(float,outline)
        offset=float(anchor['offset_mm'])
        edge=anchor['edge']
        if edge not in ('left','right','top','bottom') or offset<0:
            raise ValueError('valid edge and inward offset required')
        target=(x0+offset if edge=='left' else x1-offset,
                y0+offset if edge=='top' else y1-offset)
        if set(axes) != ({'x'} if edge in ('left','right') else {'y'}):
            raise ValueError('edge anchor must select its normal axis')
    else:
        raise ValueError('point anchor requires a declared edge or footprint')
    for i,axis in enumerate(('x','y')):
        if axis in axes: result[i]=target[i]
    if not all(math.isfinite(v) for v in result):
        raise ValueError('finite construction point required')
    return tuple(round(v,6) for v in result)


def resolve_constructor_geometry(plan):
    """Return a detached fully resolved constructor; retain declared intent."""
    import copy
    result=copy.deepcopy(plan)
    for row in result.get('routes_mm', ()):
        points=list(row['points'])
        for index,anchor in row.get('point_anchors', {}).items():
            i=int(index)
            if not 0<=i<len(points): raise ValueError('construction point index outside trunk')
            points[i]=resolve_point(points[i],anchor,poses=result['placements_mm'],outline=result.get('outline_rect_mm'))
        row['points']=points
    for row in result.get('vias_mm', ()):
        if row.get('at_anchor'):
            row['at']=resolve_point(row['at'],row['at_anchor'],poses=result['placements_mm'],outline=result.get('outline_rect_mm'))
    return result


def discard_exact_construction_copper(board, signatures):
    """Remove only caller-owned exact geometric stamps, not nearby net copper.

    Integer native coordinates, widths, drill and layer span are all part of
    identity. Unknown, differently sized or foreign-net objects are retained.
    Caller must have mutable constructor ownership, not routed authority.
    """
    import pcbnew
    from cec_native_items import discard_items
    expected=set(signatures)
    point=lambda p:(p.x,p.y)
    doomed=[]
    for item in board.GetTracks():
        if isinstance(item,pcbnew.PCB_VIA):
            key=('via',item.GetNetname(),point(item.GetPosition()),item.GetWidth(item.TopLayer()),
                 item.GetDrillValue(),int(item.TopLayer()),int(item.BottomLayer()))
        elif item.GetClass()=='PCB_TRACK':
            key=('track',item.GetNetname(),tuple(sorted((point(item.GetStart()),point(item.GetEnd())))),
                 item.GetWidth(),item.GetLayer())
        else: continue
        if key in expected: doomed.append(item)
    return discard_items(board,doomed)


def tail(board, start_mm, target, *, net, layer, width_mm,
         clearance_mm=0.25, wall_seconds=10):
    import pcbnew
    import cec_fr
    footprint = board.FindFootprintByReference(target[0])
    pad = footprint.FindPadByNumber(str(target[1])) if footprint else None
    lid = board.GetLayerID(layer)
    if not pad or pad.GetNetname() != net or not pad.IsOnLayer(lid):
        raise ValueError('interface tail requires a same-net pad on its declared layer')
    start = pcbnew.VECTOR2I_MM(*start_mm)
    legs = cec_fr._guarded_profiled_lastmile_legs(
        board, start, pad.GetPosition(), pcbnew.FromMM(width_mm), lid,
        pcbnew.FromMM(clearance_mm), pad.GetNetCode(),
        lambda a, b, half: cec_fr._edge_leg_clear(board, a, b, half),
        deadline_monotonic=time.monotonic() + wall_seconds)
    if legs is None:
        raise ValueError('no clearance-safe interface tail within search budget')
    return [((a.x/1e6, a.y/1e6), (b.x/1e6, b.y/1e6), w/1e6)
            for a, b, w in legs]


def rebuild_declared_tails(board, declarations, *, refill_owned_zones=False):
    """Regenerate only explicitly declared signal nets; preserve other copper.

    Retained trunks come from constructor data; tail endpoints come from
    native pads. This is performed on an unpromoted copy followed by full DRC.
    Never call with a live routed authority or immutable power zones.
    """
    import pcbnew
    from cec_native_items import discard_items
    selected = [r for r in declarations if r.get('target_pad')]
    if not selected:
        return {'removed': 0, 'added': 0, 'nets': []}
    if not refill_owned_zones:
        raise ValueError('signal reconstruction requires explicit mutable-zone ownership')
    nets = {r['net'] for r in selected}
    if len(nets) != len(selected):
        raise ValueError('one complete constructor trunk per rebuilt net required')
    # Validate every endpoint before altering the disposable board. A typo in
    # a later row must not first erase earlier valid constructor copper.
    for row in selected:
        if not board.FindNet(row['net']) or board.GetLayerID(row['layer']) < 0:
            raise ValueError('declared constructor net/layer missing')
        for key in ('source_pad', 'target_pad'):
            if not row.get(key):
                continue
            ref, pin = row[key]
            fp = board.FindFootprintByReference(ref)
            pad = fp.FindPadByNumber(str(pin)) if fp else None
            if not pad or pad.GetNetname() != row['net']:
                raise ValueError('declared constructor endpoint missing or wrong-net')
    replacement_nets = {r['net'] for r in selected if not r.get('additive')}
    doomed = [t for t in board.GetTracks() if t.GetNetname() in replacement_nets]
    removed = discard_items(board, doomed)
    for zone in board.Zones():
        if not zone.GetIsRuleArea():
            zone.UnFill()
    added = 0
    for row in selected:
        net = board.FindNet(row['net'])
        lid = board.GetLayerID(row['layer'])
        if not net or lid < 0:
            raise ValueError('declared constructor net/layer missing')
        group_name = 'interface-tail:' + ':'.join(map(str, row['target_pad']))
        for group in list(board.Groups()):
            if group.GetName() == group_name:
                discard_items(board, list(group.GetItems()))
                board.Delete(group)
        group = pcbnew.PCB_GROUP(board)
        group.SetName(group_name)
        board.Add(group)
        def emit(a, b, width):
            nonlocal added
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I_MM(*a))
            t.SetEnd(pcbnew.VECTOR2I_MM(*b))
            t.SetWidth(pcbnew.FromMM(width))
            t.SetLayer(lid)
            t.SetNetCode(net.GetNetCode())
            board.Add(t)
            group.AddItem(t)
            added += 1
        for a, b in zip(row['points'], row['points'][1:]):
            emit(a, b, row['width'])
        chosen_layer, legs = declared_tail(board, row)
        lid = board.GetLayerID(chosen_layer)
        for a, b, width in legs:
            emit(a, b, width)
    import cec_zone_fill
    cec_zone_fill.fill(board)
    return {'removed': removed, 'added': added, 'nets': sorted(nets),
            'requires_native_drc': True}


def declared_tail(board, row):
    if row.get('source_pad'):
        ref, pin = row['source_pad']
        fp = board.FindFootprintByReference(ref)
        pad = fp.FindPadByNumber(str(pin)) if fp else None
        if not pad or pad.GetNetname() != row['net']:
            raise ValueError('constructor return source pad is missing or wrong-net')
        p = pad.GetPosition()
        start = (p.x/1e6, p.y/1e6)
    else:
        pad = None
        start = row['points'][-1]
    failures = []
    for layer in row.get('layer_candidates', [row['layer']]):
        if pad and not pad.IsOnLayer(board.GetLayerID(layer)):
            continue
        try:
            return layer, tail(board, start, row['target_pad'], net=row['net'],
                               layer=layer, width_mm=row['width'])
        except ValueError as exc:
            failures.append(str(exc))
    raise ValueError('no admissible declared tail: ' + '; '.join(failures))
