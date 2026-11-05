"""Clear one source-owned shunt pickup face, without qualifying its force path.

Shorten only the outward collinear endpoint of one native force track and
compile a full SOURCE-width collector inside its unchanged shunt land. The
union may lose only unsupported inward end-cap copper; no current boundary,
width, footprint, barrel, or other conductor is moved. Existing undersized
force geometry remains explicit debt, never new ampacity or release credit.
An independently replayed final Kelvin cohort is still required.
"""
import math
from pathlib import Path
import tempfile
import time
import uuid

import pcbnew
import cec_additive_route_receiving as additive
import cec_current_topology as topology
import cec_field_coupling as field
import cec_force_current as force
import cec_ordinary_route_receiving as ordinary
import cec_rectilinear_copper as contour
import cec_sense_topology as sense


ZONE_NAME = 'CEC_SOURCE_SHUNT_COLLECTOR'


def plan(board, source, *, board_hint, pad_uuid, track_uuid, timeout_s=10.):
    if type(timeout_s) not in (float, int) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 10:
        raise ValueError('bounded_source_endcap_replay_required')
    deadline = time.monotonic() + timeout_s
    pad = next((p for fp in board.GetFootprints() for p in fp.Pads() if force._uid(p)==pad_uuid),None)
    edge = next((t for t in board.GetTracks() if force._uid(t)==track_uuid),None)
    if pad is None or edge is None or edge.GetClass()!='PCB_TRACK':
        raise ValueError('exact_source_shunt_land_and_linear_force_edge_required')
    peer = [p for p in pad.GetParentFootprint().Pads() if force._uid(p)!=pad_uuid]
    layer = int(edge.GetLayer())
    if (pad.GetParentFootprint().IsDNP() or len(peer)!=1 or peer[0].GetNetname()==pad.GetNetname()
            or layer not in (pcbnew.F_Cu,pcbnew.B_Cu) or edge.GetNetname()!=pad.GetNetname()
            or any(p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or p.HasHole() or not p.IsOnLayer(layer)
                   for p in (pad,peer[0])) or contour._track_row(edge)['group_uuid']):
        raise ValueError('two_unmoved_outer_layer_shunt_lands_and_ungrouped_force_required')
    at, other = tuple(pad.GetPosition()),tuple(peer[0].GetPosition())
    ends = (tuple(edge.GetStart()),tuple(edge.GetEnd()))
    if ((at[0]==other[0])==(at[1]==other[1]) or at not in ends):
        raise ValueError('cardinal_shunt_axis_and_exact_terminal_endpoint_required')
    axis = tuple((a>b)-(a<b) for a,b in zip(at,other));perp=(-axis[1],axis[0])
    far = ends[1] if ends[0]==at else ends[0]
    depth = lambda p:sum((p[k]-at[k])*axis[k] for k in (0,1))
    if (sum((far[k]-at[k])*perp[k] for k in (0,1))!=0 or not 0<depth(far)<=16000000):
        raise ValueError('source_force_must_already_be_collinear_outward')
    with force._thermal_hint(board_hint):
        domains=topology.board_current_domains(board,board_hint)
        contracts=topology.route_width_contracts(board,board_hint)
    net=str(pad.GetNetname());domain=domains.get(net);contract=contracts.get(net)
    if not domain or domain.get('complete') is not True or not contract:
        raise ValueError('complete_unchanged_source_force_authority_required')
    lineage=sense.board_evidence(board,anchor_refs=domain['authority_refs'])
    if not any(r.get('ok') is True and q['anchor_ref']==pad.GetParentFootprint().GetReference()
            and q['anchor_pad']==pad.GetNumber() and q['anchor_net']==net
            for r in lineage['details'] if r.get('ok') is True
            for q in (r['selected']['p'],r['selected']['n'])):
        raise ValueError('actual_manufacturer_input_to_source_shunt_required')
    bb=pad.GetBoundingBox();half=(bb.GetHeight() if axis[1] else bb.GetWidth())//2
    cross=bb.GetWidth() if axis[1] else bb.GetHeight();width=int(edge.GetWidth())
    backoff=(width+1)//2-half+3000
    if not 400000<=width<=cross or not 0<backoff<min(4000000,depth(far)):
        raise ValueError('bounded_source_width_inner_cap_overhang_required')
    # Full source width is tested against the ACTUAL pad polygon, not its box.
    actual=pcbnew.SHAPE_POLY_SET();pad.TransformShapeToPolygon(actual,layer,0,1,pcbnew.ERROR_INSIDE,False)
    left=width//2;right=width-left
    rect=lambda lo,hi:[[at[k]+axis[k]*d+perp[k]*s for k in (0,1)]
        for s,d in ((-left,lo),(right,lo),(right,hi),(-left,hi))]
    pickup=min(250000,half//3)
    strip=contour._poly(rect(-pickup,1000));strip.BooleanSubtract(actual)
    if strip.OutlineCount():raise ValueError('actual_shunt_land_lacks_full_source_width_strip')
    terminal=tuple(at[k]+axis[k]*backoff for k in (0,1))
    proto=pcbnew.PCB_TRACK(board);proto.SetLayer(layer);proto.SetNet(pad.GetNet());proto.SetWidth(width)
    proto.SetStart(pcbnew.VECTOR2I(*far));proto.SetEnd(pcbnew.VECTOR2I(*terminal))
    points=rect(-pickup,backoff);collector=contour._poly(points)
    old=contour._native_capsule(edge);new=contour._native_capsule(proto)
    union=old.CloneDropTriangulation();union.BooleanAdd(actual)
    extra=collector.CloneDropTriangulation();extra.BooleanSubtract(union)
    new_extra=new.CloneDropTriangulation();new_extra.BooleanSubtract(union)
    if extra.OutlineCount() or new_extra.OutlineCount():
        raise ValueError('source_endcap_rebuild_adds_copper_outside_existing_land_and_force')
    restored=new.CloneDropTriangulation();restored.BooleanAdd(collector);restored.BooleanAdd(actual)
    removed=old.CloneDropTriangulation();removed.BooleanSubtract(restored)
    if not removed.OutlineCount():raise ValueError('actual_unsupported_endcap_loss_required')
    if any(depth(removed.COutline(i).CPoint(j))>=0 for i in range(removed.OutlineCount())
            for j in range(removed.COutline(i).PointCount())):
        raise ValueError('source_endcap_rebuild_would_lose_outward_trunk_material')
    # No second zone may keep the same bulb alive or be silently trimmed.
    if any(not z.GetIsRuleArea() and z.GetNetname()==net and z.IsOnLayer(layer)
            and (not z.IsFilled() or not z.HasFilledPolysForLayer(layer)
                 or z.GetFilledPolysList(layer).Collide(removed,0)) for z in board.Zones()):
        raise ValueError('source_endcap_has_unowned_same_net_keeper')
    contour._check_deadline(deadline)
    uid=str(uuid.uuid5(uuid.UUID(track_uuid),'CEC_SOURCE_SHUNT_COLLECTOR_V1'))
    if any(force._uid(z)==uid for z in board.Zones()):raise ValueError('source_collector_identity_already_present')
    return dict(schema=1,mode='single_source_endcap',pad_uuid=pad_uuid,track_uuid=track_uuid,zone_uuid=uid,
        net=net,layer_id=layer,source_sha256=force._hash(source),source_track=contour._track_row(edge),
        source_pad=contour._link_pad_row(pad),source_boundary_nm=list(far),terminal_nm=list(terminal),
        outline_nm=points,source_width_nm=width,unchanged_current_width_contract=contract,
        inherited_current_debt_qualified=False,new_capacity_credited=False,release_authority=False)


def materialize(board, proposal):
    track=next(t for t in board.GetTracks() if force._uid(t)==proposal['track_uuid'])
    if contour._track_row(track)!=proposal['source_track']:raise ValueError('source_endcap_force_edge_changed')
    old=proposal['source_track'];at=proposal['source_pad']['position_nm']
    if old['start_nm']==at:track.SetStart(pcbnew.VECTOR2I(*proposal['terminal_nm']))
    else:track.SetEnd(pcbnew.VECTOR2I(*proposal['terminal_nm']))
    z=pcbnew.ZONE(board);z.m_Uuid.Clone(pcbnew.KIID(proposal['zone_uuid']));z.SetNet(track.GetNet())
    z.SetLayer(proposal['layer_id']);z.SetZoneName(ZONE_NAME);z.SetLocked(True)
    z.SetAssignedPriority(0);z.SetLocalClearance(max(200000,board.GetDesignSettings().m_MinClearance))
    z.SetMinThickness(100000);z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL);z.SetCornerSmoothingType(0)
    z.Outline().NewOutline()
    for x,y in proposal['outline_nm']:z.Outline().Append(x,y)
    board.Add(z)


def compile_saved(path, proposal):
    b=pcbnew.LoadBoard(str(path));z=next(z for z in b.Zones() if force._uid(z)==proposal['zone_uuid'])
    labels={force._uid(t):t.GetNetCode() for t in b.GetTracks()}
    batch=pcbnew.ZONES();batch.append(z)
    import cec_zone_fill
    try:
        cec_zone_fill.compile_selected(b,batch)
    except cec_zone_fill.NativeFillFailed as exc:
        raise ValueError('source_collector_native_fill_refused') from exc
    if any(t.GetNetCode()!=labels[force._uid(t)] for t in b.GetTracks()):raise ValueError('collector_fill_changed_native_net')
    # Actual filled copper, not the outline, must retain a full source-width
    # cross-section through the middle of the untouched shunt land.
    pad=next(p for fp in b.GetFootprints() for p in fp.Pads() if force._uid(p)==proposal['pad_uuid'])
    at=tuple(pad.GetPosition());terminal=proposal['terminal_nm'];axis=tuple((t>a)-(t<a) for t,a in zip(terminal,at))
    perp=(-axis[1],axis[0]);width=proposal['source_width_nm'];left=width//2;right=width-left
    points=[[at[k]+axis[k]*d+perp[k]*s for k in (0,1)]
        for s,d in ((-left,-1000),(right,-1000),(right,1000),(-left,1000))]
    missing=contour._poly(points);missing.BooleanSubtract(z.GetFilledPolysList(proposal['layer_id']))
    if missing.OutlineCount():raise ValueError('native_collector_fill_loses_full_source_width_strip')
    additive._ground_refill(b);field._save_field_snapshot(b,path)


def receive(source,candidate,*,board_hint,pad_uuid,track_uuid,timeout_s=10.):
    result=dict(ok=False,complete=False,errors=[],current_authority=False,release_authority=False,
        inherited_debt_qualified=False,full_saved_board_receiving_still_required=True)
    started=time.monotonic()
    try:
        source,candidate=map(lambda p:Path(p).resolve(),(source,candidate));families=[force._family(p,board_hint) for p in (source,candidate)]
        epoch=force._code_identity();b=pcbnew.LoadBoard(str(source))
        proposal=plan(b,source,board_hint=board_hint,pad_uuid=pad_uuid,track_uuid=track_uuid,timeout_s=timeout_s)
        with tempfile.TemporaryDirectory(prefix='cec-source-endcap-') as work:
            expected=force._copy_family(source,Path(work)/'expected');materialize(b,proposal)
            field._save_field_snapshot(b,expected);compile_saved(expected,proposal)
            first,old=force._preservation_snapshot(expected);last,new=force._preservation_snapshot(candidate)
            if first!=last or old!=new or force._sidecars(expected)!=force._sidecars(candidate):
                raise ValueError('child_differs_from_exact_source_endcap_replay')
        parent,child=map(lambda p:pcbnew.LoadBoard(str(p)),(source,candidate));deadline=started+timeout_s
        prior=ordinary._partition(parent,deadline);keys=set().union(*prior)
        after=ordinary._partition(child,deadline,retained_keys=keys)
        if any(not any(p<=q for q in after) for p in prior):raise ValueError('source_endcap_lost_native_conductor_partition')
        if families!=[force._family(p,board_hint) for p in (source,candidate)] or epoch!=force._code_identity() or time.monotonic()>=deadline:
            raise ValueError('source_endcap_identity_or_deadline_changed')
        result.update(ok=True,complete=True,proposal=proposal,modified_native_uuids=[track_uuid],
            added_native_uuids=[proposal['zone_uuid']],retired_track_uuids=[],retired_via_uuids=[],
            exact_native_force_landing_replayed=True,new_capacity_credited=False)
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    result['elapsed_s']=round(time.monotonic()-started,6)
    return result
