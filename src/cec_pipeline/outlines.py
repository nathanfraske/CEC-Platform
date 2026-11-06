"""One inward rectangle edge: exact native scope, not mechanical qualification.

All physical receivers (including fresh native DRC) remain mandatory. Only
existing GND saved fill may lose material, only at the changed board edge.
"""
from pathlib import Path
import time

from .identity import require, digest, inspection, family, code_identity
from . import groundplanes as geom


def _point(p):
    return [int(p.x), int(p.y)]


def _rectangle(board):
    import pcbnew
    edges=[g for g in board.GetDrawings() if g.GetLayer()==pcbnew.Edge_Cuts]
    require(len(edges)==4 and all(isinstance(g,pcbnew.PCB_SHAPE)
            and g.GetShape()==pcbnew.SHAPE_T_SEGMENT for g in edges),
            'exact_four_native_rectangle_segments_required')
    # Footprint-local Edge.Cuts would add an unowned cutout or perimeter.
    require(not any(g.GetLayer()==pcbnew.Edge_Cuts for fp in board.GetFootprints()
                    for g in fp.GraphicalItems()), 'footprint_edge_cuts_not_supported')
    segments=[(_point(e.GetStart()),_point(e.GetEnd())) for e in edges]
    xs=sorted({p[0] for s in segments for p in s}); ys=sorted({p[1] for s in segments for p in s})
    require(len(xs)==len(ys)==2, 'nondegenerate_axis_aligned_rectangle_required')
    corners={(x,y) for x in xs for y in ys}
    expected={frozenset(((xs[0],y),(xs[1],y))) for y in ys}
    expected|={frozenset(((x,ys[0]),(x,ys[1]))) for x in xs}
    require({frozenset(map(tuple,s)) for s in segments}==expected
            and all(tuple(p) in corners for s in segments for p in s),
            'exact_closed_rectangle_without_repeated_edges_required')
    return edges,[xs[0],ys[0],xs[1],ys[1]]


def _margin(box, axis, inward, position):
    low=box.GetLeft() if axis==0 else box.GetTop()
    high=box.GetRight() if axis==0 else box.GetBottom()
    return int(low-position if inward==1 else position-high)


def _physical_frontier(board, axis, inward, position, clearance, deadline):
    """Conservative native envelopes; no inferred washer/body qualification."""
    import pcbnew
    margins=[]; count=0
    def check(item, kind, gap):
        nonlocal count
        count+=1; require(count<=65536, 'bounded_outline_material_inventory_required')
        geom._tick(deadline)
        margin=_margin(item.GetBoundingBox(),axis,inward,position)
        require(margin>0 and margin>=gap, 'trim_crosses_or_approaches_native_'+kind)
        margins.append(margin)
    for t in board.GetTracks(): check(t,'conductor_or_barrel',clearance)
    for g in board.GetDrawings():
        if pcbnew.IsCopperLayer(g.GetLayer()): check(g,'copper_artwork',clearance)
    for zone in board.Zones():
        if zone.GetIsRuleArea() or zone.GetNetname()=='GND':continue
        for face in zone.GetLayerSet().CuStack():
            require(zone.IsFilled() and zone.HasFilledPolysForLayer(face),
                    'actual_saved_non_ground_fill_required_for_trim')
            shape=zone.GetFilledPolysList(face)
            if shape.OutlineCount():
                require(_margin(shape.BBox(),axis,inward,position)>=clearance
                        and _margin(shape.BBox(),axis,inward,position)>0,
                        'trim_crosses_or_approaches_fixed_non_ground_fill')
    for fp in board.GetFootprints():
        pads=list(fp.Pads())
        for pad in pads:
            # Native pad bbox includes the padstack; conservatively reserve the
            # whole copper land even on non-plated holes, without moving it.
            check(pad,'pad_or_hole',clearance)
            drill=pad.GetDrillSize()
            radius=(abs(int(drill.x))+abs(int(drill.y))+1)//2
            pos=pad.GetPosition()
            margin=(int(pos.x if axis==0 else pos.y)-position)*inward-radius
            require(not radius or margin>0, 'trim_crosses_native_drill_envelope')
        graphics=list(fp.GraphicalItems())
        if pads:
            # Through-hole lands do not imply a second body, but an actual
            # opposite-face SMD land does. A graphic on the other courtyard
            # layer must never stand in for the occupied face's envelope.
            occupied={fp.GetLayer()}
            occupied.update(face for pad in pads if pad.GetAttribute()==pcbnew.PAD_ATTRIB_SMD
                            for face in (pcbnew.F_Cu,pcbnew.B_Cu) if pad.IsOnLayer(face))
            require(occupied <= {pcbnew.F_Cu,pcbnew.B_Cu},
                    'native_occupied_copper_face_required_for_outline_trim')
            for face in occupied:
                courtyard=fp.GetCourtyard(face)
                require(courtyard.OutlineCount()>0 and not courtyard.IsSelfIntersecting(),
                        'valid_closed_occupied_face_courtyard_required_for_outline_trim')
                for index in range(courtyard.OutlineCount()):
                    chain=courtyard.COutline(index)
                    area2=sum(int(chain.CPoint(i).x)*int(chain.CPoint((i+1)%chain.PointCount()).y)
                              -int(chain.CPoint(i).y)*int(chain.CPoint((i+1)%chain.PointCount()).x)
                              for i in range(chain.PointCount()))
                    require(chain.IsClosed() and chain.PointCount()>=3 and area2!=0,
                            'valid_closed_occupied_face_courtyard_required_for_outline_trim')
                require(_margin(courtyard.BBox(),axis,inward,position)>0,
                        'trim_crosses_or_approaches_native_courtyard')
        courts=[g for g in graphics if g.GetLayer() in (pcbnew.F_CrtYd,pcbnew.B_CrtYd)]
        for g in courts: check(g,'courtyard',0)
        for g in graphics:
            if pcbnew.IsCopperLayer(g.GetLayer()): check(g,'footprint_copper_artwork',clearance)
    return dict(native_envelopes=count, minimum_changed_edge_margin_nm=min(margins) if margins else None,
                washer_and_mating_envelopes_qualified=False)


def _plan(board, source, operation, deadline):
    require(type(operation) is dict and set(operation)=={'kind','edge_uuid','position_nm'}
            and operation['kind']=='outline_trim' and type(operation['edge_uuid']) is str
            and operation['edge_uuid'] and type(operation['position_nm']) is int
            and abs(operation['position_nm'])<=2_000_000_000,
            'exact_bounded_outline_trim_operation_required')
    edges,bounds=_rectangle(board)
    selected=[e for e in edges if e.m_Uuid.AsString()==operation['edge_uuid']]
    require(len(selected)==1,'exact_source_rectangle_edge_required')
    a,b=_point(selected[0].GetStart()),_point(selected[0].GetEnd())
    axis=0 if a[0]==b[0] else 1; old=a[axis]
    inward=1 if old==bounds[axis] else -1; opposite=bounds[axis+2] if inward==1 else bounds[axis]
    position=operation['position_nm']
    require(0<(position-old)*inward<(opposite-old)*inward,'strict_inward_edge_trim_required')
    clearance=int(board.GetDesignSettings().m_CopperEdgeClearance)
    require(0<=clearance<=100_000_000,'bounded_source_copper_edge_clearance_required')
    frontier=_physical_frontier(board,axis,inward,position,clearance,deadline)
    updates=[]
    for e in edges:
        start,end=_point(e.GetStart()),_point(e.GetEnd()); newstart=start[:]; newend=end[:]
        if start[axis]==old:newstart[axis]=position
        if end[axis]==old:newend[axis]=position
        if (start,end)!=(newstart,newend):
            updates.append(dict(uuid=e.m_Uuid.AsString(),start_nm=newstart,end_nm=newend))
    require(len(updates)==3,'exact_three_edge_primitive_update_required')
    return dict(kind='outline_trim',source=str(Path(source).resolve()),source_sha256=inspection.sha(source),
                edge_uuid=operation['edge_uuid'],axis=axis,inward=inward,old_position_nm=old,
                position_nm=position,source_bounds_nm=bounds,source_copper_edge_clearance_nm=clearance,
                edge_updates=sorted(updates,key=lambda r:r['uuid']),frontier=frontier,
                assembly_qualified=False,fabrication_qualified=False,release_authority=False)


def construct(board, source, operation, *, board_hint, request):
    import pcbnew
    require(type(request) is dict and request.get('operations')==[operation],
            'one_exact_outline_trim_per_transaction_required')
    record=_plan(board,source,operation,time.monotonic()+8.)
    by_id={e.m_Uuid.AsString():e for e in board.GetDrawings()}
    for row in record['edge_updates']:
        by_id[row['uuid']].SetStart(pcbnew.VECTOR2I(*row['start_nm']))
        by_id[row['uuid']].SetEnd(pcbnew.VECTOR2I(*row['end_nm']))
    clip_ground(board,record)
    return record


def _removed_strip(record):
    axis=record['axis']; inward=record['inward']
    limit=record['position_nm']+inward*record['source_copper_edge_clearance_nm']
    bounds=[-2_000_000_000,-2_000_000_000,2_000_000_000,2_000_000_000]
    bounds[axis+2 if inward==1 else axis]=limit
    x0,y0,x1,y1=bounds
    return geom._poly([[[x0,y0],[x1,y0],[x1,y1],[x0,y1]]])


def _clipped(initial,strip,deadline):
    result=geom._difference(initial,strip,deadline)
    # Native saved filled_polygon records encode holes as zero-width bridges.
    # Fracture changes only representation, never authors additional copper.
    result.Fracture(False)
    geom._tick(deadline)
    return result


def clip_ground(board,record):
    """Clip ORIGINAL native saved GND material; never refill other regions."""
    deadline=time.monotonic()+8.;strip=_removed_strip(record)
    for zone in board.Zones():
        if zone.GetIsRuleArea() or zone.GetNetname()!='GND':continue
        require(zone.IsFilled(),'actual_saved_outline_ground_fill_required')
        for face in zone.GetLayerSet().CuStack():
            require(zone.HasFilledPolysForLayer(face),'actual_saved_outline_ground_fill_required')
            initial=zone.GetFilledPolysList(face).CloneDropTriangulation()
            zone.SetFilledPolysList(face,_clipped(initial,strip,deadline))
        zone.SetIsFilled(True)


def _residue(source,candidate,record,ground_ids):
    import cec_additive_route_receiving as native
    import cec_copper_echo as syntax
    roots,nodes=zip(*(native._nodes(path) for path in (source,candidate)))
    require(nodes[0].keys()==nodes[1].keys(),'outline_trim_native_population_changed')
    changed={r['uuid'] for r in record['edge_updates']}
    for uid in nodes[0]:
        omitted={'start','end'} if uid in changed else {'filled_polygon'} if uid in ground_ids else set()
        def strip(node):
            return syntax._freeze([p for p in node if not(isinstance(p,list) and p and p[0] in omitted)])
        require(strip(nodes[0][uid])==strip(nodes[1][uid]),'outline_trim_changed_unowned_native_material')
    def globals_only(root,objects):
        ids={id(n) for n in objects.values()}
        return syntax._freeze([p for p in root if id(p) not in ids])
    require(globals_only(roots[0],nodes[0])==globals_only(roots[1],nodes[1]),
            'outline_trim_changed_global_context')


def receive(source,candidate,operation,record,*,board_hint):
    import pcbnew
    import cec_force_current as force
    import cec_native_fill_geometry as fill_geometry
    deadline=time.monotonic()+8.
    paths=[Path(p).resolve(strict=True) for p in (source,candidate)]
    require(paths[0]!=paths[1],'distinct_saved_outline_source_candidate_required')
    families=[family(p) for p in paths]; epoch=code_identity()
    require(force._sidecars(paths[0])==force._sidecars(paths[1]),'outline_trim_project_companions_changed')
    before,after=[pcbnew.LoadBoard(str(p)) for p in paths]
    fresh=_plan(before,paths[0],operation,deadline)
    require(digest(fresh)==digest(record),'stale_or_forged_outline_trim_record')
    expected={r['uuid']:r for r in fresh['edge_updates']}
    edges,_=_rectangle(after)
    for e in edges:
        uid=e.m_Uuid.AsString()
        if uid in expected:
            require(_point(e.GetStart())==expected[uid]['start_nm']
                    and _point(e.GetEnd())==expected[uid]['end_nm'],'saved_outline_endpoints_not_expected')
    ground={z.m_Uuid.AsString():z for z in before.Zones() if z.GetNetname()=='GND' and not z.GetIsRuleArea()}
    _residue(*paths,fresh,set(ground))
    axis=fresh['axis']; inward=fresh['inward']; permitted=_removed_strip(fresh)
    zones={z.m_Uuid.AsString():z for z in after.Zones()}; removed_total=0; rows=[]
    for uid,old in ground.items():
        new=zones[uid]
        for face in old.GetLayerSet().CuStack():
            geom._tick(deadline)
            require(old.IsFilled() and new.IsFilled() and old.HasFilledPolysForLayer(face)
                    and new.HasFilledPolysForLayer(face),'actual_saved_outline_ground_fill_required')
            initial,final=[z.GetFilledPolysList(face).CloneDropTriangulation() for z in (old,new)]
            expected_clip=_clipped(initial,permitted,deadline)
            require(fill_geometry.identity(final,deadline)==fill_geometry.identity(expected_clip,deadline),
                    'saved_ground_fill_not_exact_source_edge_clip')
            if final.OutlineCount():
                margin=_margin(final.BBox(),axis,inward,fresh['position_nm'])
                require(margin>0 and margin>=fresh['source_copper_edge_clearance_nm'],
                        'saved_ground_fill_violates_trimmed_edge_setback')
            require(geom._difference(final,initial,deadline).OutlineCount()==0,'outline_trim_added_ground_material')
            removed=geom._difference(initial,final,deadline)
            require(geom._difference(removed,permitted,deadline).OutlineCount()==0,
                    'outline_trim_removed_ground_outside_changed_edge_setback')
            area=geom._area2(removed,deadline); removed_total+=area
            rows.append(dict(zone_uuid=uid,layer_id=int(face),removed_area2_nm2=area))
    geom._tick(deadline)
    require(families==[family(p) for p in paths] and epoch==code_identity(),
            'outline_trim_source_candidate_or_code_changed')
    return dict(ok=True,complete=True,scope='exact_source_rectangle_single_inward_edge',
                edge_updates=fresh['edge_updates'],ground_fill=rows,removed_ground_area2_nm2=removed_total,
                fresh_native_drc_required=True,current_qualified=False,assembly_qualified=False,
                fabrication_qualified=False,release_authority=False)
