"""Source-owned outer force landing, leaving the inner shunt face available.

This finite geometry transformation owns exactly two existing planar tracks
and their existing compiled keeper. It preserves full declared width, native
identities, source pad and external boundary. It is not arbitrary force rip-up,
Kelvin admission, barrel ampacity or release authority. The final completed
sense cohort needs independent absolute physical and full-board receiving.
"""
import math
from pathlib import Path
import tempfile
import time

import pcbnew
from shapely.geometry import Polygon
from shapely.ops import unary_union

import cec_additive_route_receiving as additive
import cec_copper_echo as sexpr
import cec_current_topology as topology
import cec_field_coupling as field
import cec_force_current as force
import cec_rectilinear_copper as contour
import cec_sense_topology as sense_topology
from cec_native_items import discard_items


def plan(board, source, *, board_hint, pad_uuid, zone_uuid, track_uuids,
         timeout_s=10., mode='outer_reseat'):
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10):
        raise ValueError('bounded_outer_force_landing_required')
    deadline=time.monotonic()+timeout_s
    if mode not in ('outer_reseat','existing_outer_keeper'):
        raise ValueError('explicit_source_force_landing_mode_required')
    if (type(track_uuids) not in (list,tuple) or len(track_uuids)!=2
            or len(set(track_uuids))!=2
            or any(type(u) is not str or not u for u in (*track_uuids,pad_uuid,zone_uuid))):
        raise ValueError('two_exact_source_force_edges_required')
    pads={force._uid(p):p for fp in board.GetFootprints() for p in fp.Pads()}
    pad=pads.get(pad_uuid)
    if pad is None:raise ValueError('source_shunt_pad_missing')
    peers=[p for p in pad.GetParentFootprint().Pads() if force._uid(p)!=pad_uuid]
    if (len(peers)!=1 or peers[0].GetNetname()==pad.GetNetname()
            or any(p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or p.HasHole()
                   or not p.IsOnLayer(pcbnew.F_Cu) for p in (pad,peers[0]))):
        raise ValueError('two_native_top_shunt_lands_required')
    at,other=tuple(pad.GetPosition()),tuple(peers[0].GetPosition())
    if (at[0]==other[0])==(at[1]==other[1]):
        raise ValueError('cardinal_native_shunt_axis_required')
    with force._thermal_hint(board_hint):
        domains=topology.board_current_domains(board,board_hint)
        contracts=topology.route_width_contracts(board,board_hint)
    net=str(pad.GetNetname());domain=domains.get(net);contract=contracts.get(net)
    if not domain or domain.get('complete') is not True or not contract:
        raise ValueError('complete_existing_force_authority_required')
    lineage=sense_topology.board_evidence(board,anchor_refs=domain['authority_refs'])
    witnesses=[r for r in lineage['details'] if r.get('ok') is True
        for leg in (r['selected']['p'],r['selected']['n']) if leg['anchor_ref']==pad.GetParentFootprint().GetReference()
        and leg['anchor_pad']==str(pad.GetNumber()) and leg['anchor_net']==net]
    if not witnesses:raise ValueError('manufacturer_input_to_typed_source_shunt_required')
    native={force._uid(t):t for t in board.GetTracks()}
    if not set(track_uuids)<=native.keys():raise ValueError('source_force_tracks_missing')
    rows=[contour._track_row(native[u]) for u in sorted(track_uuids)]
    if (any(r['net']!=net or r['layer_id']!=pcbnew.F_Cu or r['group_uuid'] for r in rows)
            or rows[0]['width_nm']!=rows[1]['width_nm']
            or any(not 0<native[r['uuid']].GetLength()<=16000000 for r in rows)):
        raise ValueError('bounded_ungrouped_equal_width_top_force_edges_required')
    shared=set(map(tuple,(rows[0]['start_nm'],rows[0]['end_nm'])))&set(map(tuple,(rows[1]['start_nm'],rows[1]['end_nm'])))
    ends=set(map(tuple,(rows[0]['start_nm'],rows[0]['end_nm'],rows[1]['start_nm'],rows[1]['end_nm'])))-shared
    if len(shared)!=1 or len(ends)!=2 or mode=='outer_reseat' and at not in ends:
        raise ValueError('simple_source_pad_to_external_force_boundary_required')
    terminal_source=min(ends,key=lambda p:math.dist(p,at))
    far=next(p for p in ends if p!=(at if mode=='outer_reseat' else terminal_source))
    width=rows[0]['width_nm'];required=contract.get('required_by_layer_mm',{}).get('F.Cu')
    if required is None or width<math.ceil(required*1e6):
        raise ValueError('unchanged_full_current_force_width_required')
    zone=next((z for z in board.Zones() if force._uid(z)==zone_uuid),None)
    if (zone is None or zone.GetZoneName()!=contour.ZONE_NAME or zone.GetNetname()!=net
            or zone.GetIsRuleArea() or not zone.IsOnLayer(pcbnew.F_Cu)):
        raise ValueError('sole_existing_two_track_compiled_keeper_required')
    enclosed=contour._enclosed_native_track_ids(board,zone.Outline(),net,pcbnew.F_Cu,deadline)
    if (enclosed!=set(track_uuids) if mode=='outer_reseat' else not set(track_uuids)<=enclosed):
        raise ValueError('sole_existing_two_track_compiled_keeper_required')
    axis=tuple((v>q)-(v<q) for v,q in zip(at,other));perp=(-axis[1],axis[0])
    bb=pad.GetBoundingBox();half=(bb.GetHeight() if axis[1] else bb.GetWidth())//2
    cross=bb.GetWidth() if axis[1] else bb.GetHeight()
    if cross<=width+4000:raise ValueError('native_source_land_has_no_full_width_collector')
    backoff=(width+1)//2-half+3000
    if not 0<backoff<min(4000000,math.dist(at,far)):
        raise ValueError('bounded_outward_source_seat_required')
    left=width//2;right=width-left
    # Check the actual pad polygon, not only its bounding box. A rounded or
    # custom pad cannot earn a full-width connection through a clipped corner.
    strip=[[at[k]+axis[k]*depth+perp[k]*side for k in (0,1)]
        for side,depth in ((-left,-1000),(right,-1000),(right,1000),(-left,1000))]
    actual=pcbnew.SHAPE_POLY_SET();pad.TransformShapeToPolygon(actual,pcbnew.F_Cu,0,1,pcbnew.ERROR_INSIDE,False)
    uncovered=contour._poly(strip);uncovered.BooleanSubtract(actual)
    if uncovered.OutlineCount():raise ValueError('native_source_cross_section_not_full_width')
    terminal=tuple(at[k]+axis[k]*backoff for k in (0,1))
    if mode=='existing_outer_keeper':
        # An older outward-grid-rounded keeper may project microscopically
        # beyond the actual inner pad face even though its native source end
        # was already backed off. Trim ONLY that unsupported grid end-cap;
        # never regenerate the other collector/trunk portions of the zone.
        displacement=tuple(p-q for p,q in zip(terminal_source,at))
        outward=sum(v*u for v,u in zip(displacement,axis))
        if (sum(v*u for v,u in zip(displacement,perp))!=0
                or not backoff-2000<=outward<4000000
                or not math.dist(terminal_source,at)<math.dist(far,at)
                or any(not contour._centerline_allowed(r['start_nm'],r['end_nm'],'chamfer45') for r in rows)):
            raise ValueError('source_force_end_not_already_outer_and_flush')
        if zone.Outline().OutlineCount()!=1 or zone.Outline().HoleCount(0):
            raise ValueError('simple_existing_source_force_keeper_required')
        ring=zone.Outline().COutline(0)
        old_points=[(ring.CPoint(i).x,ring.CPoint(i).y) for i in range(ring.PointCount())]
        if (not 4<=len(old_points)<=64 or any(not contour._centerline_allowed(s,t,'chamfer45')
                for s,t in zip(old_points,old_points[1:]+old_points[:1]))):
            raise ValueError('purposeful_existing_force_keeper_required')
        depth=lambda p:sum((p[k]-at[k])*axis[k] for k in (0,1))
        # 1 um inside the actual native pad, not a rounded presentation box.
        limit=-half+1000
        trimmed=limit-min(map(depth,old_points))
        if not 0<trimmed<=3000:
            raise ValueError('only_source_grid_scale_inner_keeper_overhang_is_owned')
        points=[]
        for s,t in zip(old_points,old_points[1:]+old_points[:1]):
            a,b=depth(s),depth(t)
            if a>=limit:points.append(list(s))
            if (a>=limit)!=(b>=limit):
                ratio=(limit-a)/(b-a)
                point=[s[k]+ratio*(t[k]-s[k]) for k in (0,1)]
                if any(abs(p-round(p))>1e-5 for p in point):
                    raise ValueError('native_flush_boundary_not_integer_octilinear')
                points.append([round(p) for p in point])
        old_poly=contour._poly(old_points);new_poly=contour._poly(points)
        missing=contour._poly(strip);missing.BooleanSubtract(new_poly)
        if missing.OutlineCount():raise ValueError('flush_keeper_loses_existing_full_width_collector')
        removed=pcbnew.SHAPE_POLY_SET(old_poly);removed.BooleanSubtract(new_poly)
        if (removed.OutlineCount()!=1 or removed.HoleCount(0)
                or not actual.Collide(native[rows[0]['uuid']].GetEffectiveShape(pcbnew.F_Cu),0)
                    and not actual.Collide(native[rows[1]['uuid']].GetEffectiveShape(pcbnew.F_Cu),0)):
            raise ValueError('unambiguous_original_force_land_contact_required')
        loop=removed.COutline(0)
        if any(abs(sum((loop.CPoint(i)[k]-at[k])*perp[k] for k in (0,1)))>cross//2
                for i in range(loop.PointCount())):
            raise ValueError('keeper_flush_would_trim_other_trunk_material')
        contour._check_deadline(deadline)
        return dict(schema=1,scope='native_outer_shunt_force_landing',source_sha256=force._hash(source),mode=mode,
            pad_uuid=pad_uuid,zone_uuid=zone_uuid,track_uuids=sorted(track_uuids),source_tracks=rows,
            net=net,path_nm=[],outline_nm=points,source_pad=contour._link_pad_row(pad),
            unchanged_current_width_contract=contract,required_width_nm=width,
            source_boundary_nm=list(far),new_capacity_credited=False,release_authority=False,
            native_tracks_and_full_width_collector_unchanged=True,source_inner_overhang_trimmed_nm=trimmed)
    if axis[1]:
        length=abs(terminal[1]-far[1]);mid=(far[0]+((at[0]>far[0])-(at[0]<far[0]))*length,terminal[1])
    else:
        length=abs(terminal[0]-far[0]);mid=(terminal[0],far[1]+((at[1]>far[1])-(at[1]<far[1]))*length)
    if mode=='outer_reseat':path=[far,mid,terminal]
    if (any(s==t or not contour._centerline_allowed(s,t,'chamfer45') for s,t in zip(path,path[1:]))
            or sum(math.dist(s,t) for s,t in zip(path,path[1:]))>
               sum(native[r['uuid']].GetLength() for r in rows)+4000000):
        raise ValueError('bounded_canonical_outward_force_path_required')
    pieces=[]
    for s,t in zip(path,path[1:]):
        track=pcbnew.PCB_TRACK(board);track.SetNet(pad.GetNet());track.SetLayer(pcbnew.F_Cu)
        track.SetStart(pcbnew.VECTOR2I(*s));track.SetEnd(pcbnew.VECTOR2I(*t));track.SetWidth(width)
        pieces.append(Polygon(contour.purposeful_envelope(contour._native_capsule(track),
            style='chamfer45',margin_nm=1000,grid_nm=1000)))
    rect=[[at[k]+axis[k]*depth+perp[k]*side for k in (0,1)]
        for side,depth in ((-left,0),(right,0),(right,backoff),(-left,backoff))]
    pieces.append(Polygon(rect));combined=unary_union(pieces)
    if not isinstance(combined,Polygon) or combined.interiors:
        raise ValueError('single_solid_source_force_collector_required')
    points=[[int(x),int(y)] for x,y in list(combined.exterior.coords)[:-1]]
    if any(not contour._centerline_allowed(s,t,'chamfer45') for s,t in zip(points,points[1:]+points[:1])):
        raise ValueError('purposeful_force_outline_required')
    guard=pcbnew.LoadBoard(str(source))
    discard_items(guard,[z for z in guard.Zones() if not z.GetIsRuleArea() and z.GetNetname()=='GND'])
    contour._require_unoccupied_outline(guard,contour._poly(points),net,pcbnew.F_Cu,deadline,
        clearance_nm=max(200000,board.GetDesignSettings().m_MinClearance))
    contour._check_deadline(deadline)
    return dict(schema=1,scope='native_outer_shunt_force_landing',source_sha256=force._hash(source),mode=mode,
        pad_uuid=pad_uuid,zone_uuid=zone_uuid,track_uuids=sorted(track_uuids),source_tracks=rows,
        net=net,path_nm=[list(p) for p in path],outline_nm=points,source_pad=contour._link_pad_row(pad),
        unchanged_current_width_contract=contract,required_width_nm=width,
        source_boundary_nm=list(far),new_capacity_credited=False,release_authority=False)


def materialize(board, proposal):
    """Apply an independently derived source plan; receiving rederives it."""
    native={force._uid(t):t for t in board.GetTracks()}
    for row,s,t in zip(proposal['source_tracks'],proposal['path_nm'],proposal['path_nm'][1:]):
        item=native[row['uuid']]
        if contour._track_row(item)!=row:raise ValueError('source_force_edge_changed')
        if proposal['mode']=='outer_reseat':
            item.SetStart(pcbnew.VECTOR2I(*s));item.SetEnd(pcbnew.VECTOR2I(*t))
    zone=next(z for z in board.Zones() if force._uid(z)==proposal['zone_uuid'])
    zone.UnFill();zone.Outline().RemoveAllContours();zone.Outline().NewOutline()
    for x,y in proposal['outline_nm']:zone.Outline().Append(x,y)


def compile_saved(path, proposal):
    board=pcbnew.LoadBoard(str(path))
    labels={force._uid(t):t.GetNetCode() for t in board.GetTracks()}
    zone=next(z for z in board.Zones() if force._uid(z)==proposal['zone_uuid'])
    batch=pcbnew.ZONES();batch.append(zone)
    import cec_zone_fill
    try:
        cec_zone_fill.compile_selected(board,batch)
    except cec_zone_fill.NativeFillFailed as exc:
        raise ValueError('native_force_keeper_fill_refused') from exc
    if any(t.GetNetCode()!=labels[force._uid(t)] for t in board.GetTracks()):
        raise ValueError('force_keeper_fill_changed_native_net_identity')
    additive._ground_refill(board);field._save_field_snapshot(board,path)


def receive(source,candidate,*,board_hint,pad_uuid,zone_uuid,track_uuids,timeout_s=10.,mode='outer_reseat'):
    result=dict(ok=False,complete=False,errors=[],scope='independent_source_outer_force_landing',
        release_authority=False,current_authority=False,full_saved_board_receiving_still_required=True)
    started=time.monotonic()
    try:
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        families=[force._family(p,board_hint) for p in (source,candidate)];epoch=force._code_identity()
        board=pcbnew.LoadBoard(str(source))
        proposal=plan(board,source,board_hint=board_hint,pad_uuid=pad_uuid,zone_uuid=zone_uuid,
            track_uuids=track_uuids,timeout_s=timeout_s,mode=mode)
        with tempfile.TemporaryDirectory(prefix='cec-source-force-seat-') as work:
            expected=force._copy_family(source,Path(work)/'expected')
            materialize(board,proposal);field._save_field_snapshot(board,expected)
            compile_saved(expected,proposal)
            first,old=force._preservation_snapshot(expected);last,new=force._preservation_snapshot(candidate)
            if first!=last or old!=new or force._sidecars(expected)!=force._sidecars(candidate):
                raise ValueError('child_differs_from_exact_native_source_force_seat_replay')
        if (families!=[force._family(p,board_hint) for p in (source,candidate)]
                or epoch!=force._code_identity() or time.monotonic()-started>=timeout_s):
            raise ValueError('source_force_seat_identity_or_deadline_changed')
        result.update(ok=True,complete=True,proposal=proposal,added_native_uuids=[],
            modified_native_uuids=sorted([zone_uuid,*([] if mode=='existing_outer_keeper' else track_uuids)]),
            retired_track_uuids=[],retired_via_uuids=[],
            exact_native_force_landing_replayed=True,new_capacity_credited=False)
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    result['elapsed_s']=round(time.monotonic()-started,6)
    return result
