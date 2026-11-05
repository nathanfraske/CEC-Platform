"""Native filled-copper and local-clearance obstacles for scoped DSN routing.

KiCad's plane export carries neither the zone's own clearance nor a guarantee
that an excluded net remains an obstacle in every backend. Disposable rule
areas expose the actual foreign filled copper with its required clearance.
No manufactured board is edited. Holes/notches and layer identities remain
explicit; an unknown fill is a refusal, never an empty routing channel.
"""
import math
import time

import pcbnew
import cec_fr as fr
import cec_native_fill_geometry as fill


def compile(board_path, *, routed_nets, refillable_nets=(), only_nets=None,
            timeout_s=3.0, max_vertices=200000):
    if (type(timeout_s) not in (float,int) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10 or type(max_vertices) is not int
            or not 32<=max_vertices<=200000):
        raise ValueError('invalid_native_zone_obstacle_bounds')
    routed=set(routed_nets);refillable=set(refillable_nets)
    if any(type(n) is not str or not n for n in routed|refillable):
        raise ValueError('explicit_native_zone_net_identities_required')
    selected=None if only_nets is None else set(only_nets)
    deadline=time.monotonic()+timeout_s;board=pcbnew.LoadBoard(str(board_path))
    clear=fr._foreign_clearance_resolver(board)
    rows=[];sources=[];vertices=0
    for zone in board.Zones():
        if time.monotonic()>=deadline:raise ValueError('native_zone_obstacle_deadline')
        net=str(zone.GetNetname())
        if (zone.GetIsRuleArea() or net in routed or net in refillable
                or (selected is not None and net not in selected)):continue
        if not zone.IsFilled():raise ValueError('foreign_zone_has_no_native_fill:'+str(zone.m_Uuid.AsString()))
        for layer in zone.GetLayerSet().CuStack():
            if not zone.HasFilledPolysForLayer(layer):
                raise ValueError('foreign_zone_layer_has_no_native_fill')
            native=zone.GetFilledPolysList(layer)
            if native.OutlineCount()==0:continue  # Positively empty saved fill, not a guessed pour.
            identity,count=fill.identity(native,deadline,max_vertices=max_vertices)
            vertices+=count
            if vertices>max_vertices:raise ValueError('native_zone_obstacle_vertex_bound')
            clearance=max(int(zone.GetLocalClearance()),int(clear(zone,layer)))
            if not 0<=clearance<=10000000:raise ValueError('native_zone_clearance_bound')
            # Clone() is exposed as the base SHAPE by KiCad's SWIG binding;
            # the typed copy constructor retains polygon offset operations
            # and leaves the saved zone's own filled geometry untouched.
            guard=pcbnew.SHAPE_POLY_SET(native)
            # Native rounded offsets may use inside chords. Two maximum-error
            # units of outward reserve cover that approximation; no inward
            # simplification or bounding-box merge may eat an access pocket.
            error_nm=1000
            guard.Inflate(clearance+2*error_nm,pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS,error_nm)
            _hash,expanded=fill.identity(guard,deadline,max_vertices=max_vertices)
            vertices+=expanded
            if vertices>max_vertices:raise ValueError('native_zone_obstacle_vertex_bound')
            uid=str(zone.m_Uuid.AsString())
            for index in range(guard.OutlineCount()):
                ring=guard.Outline(index)
                polygon=tuple((ring.CPoint(k).x/1e6,ring.CPoint(k).y/1e6) for k in range(ring.PointCount()))
                holes=tuple(tuple((h.CPoint(k).x/1e6,h.CPoint(k).y/1e6) for k in range(h.PointCount()))
                    for h in [guard.Hole(index,j) for j in range(guard.HoleCount(index))])
                rows.append(dict(name='native-zone-'+uid+'-'+str(int(layer))+'-'+str(index),
                    polygon=polygon,holes=holes,layers=(board.GetLayerName(layer),),
                    allow_tracks=False,allow_vias=False,block_fills=False))
            sources.append(dict(uuid=uid,net=net,layer=board.GetLayerName(layer),
                native_fill_identity=identity,clearance_nm=clearance,
                outward_error_reserve_nm=2*error_nm,polygons=guard.OutlineCount()))
    if time.monotonic()>=deadline:raise ValueError('native_zone_obstacle_deadline')
    return dict(schema=1,scope='native_foreign_filled_zone_obstacles',keepouts=rows,
        sources=sources,board_mutated=False,release_authority=False,
        additional_backend_keepout_clearance_may_be_conservative=True)
