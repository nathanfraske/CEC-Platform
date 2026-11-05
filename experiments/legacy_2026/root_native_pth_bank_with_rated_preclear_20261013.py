"""Joint source-bound PTH bank transfer and full-load small-branch preclear.

Private prototype, not selection or capacity authority. The entire old zone
footprint must survive on an equally thick outer face. Every old contact must
be a real plated pin with a target land. The interfering branch keeps its
actual full-load source width; search-only future routes are removed before
saving. No board, refdes or coordinate case is contained in this helper.
"""
import argparse
import json
import math
import time
from pathlib import Path
import cec_swig_guard
cec_swig_guard.pin()
import wx
quiet = wx.LogNull()
import pcbnew
import cec_force_current as force
import cec_fr as fr
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_ordinary_route_receiving as ordinary
import cec_rated_branch_repair as rated
import cec_native_component_ports as ports
import cec_rectilinear_copper as copper
import cec_native_fill_geometry as native_fill
import cec_native_current_capture as capture
import cec_current_debt as current
import cec_current_topology as topology
import cec_force_sense_evidence as sense
import cec_native_drc_runner as native
import cec_stage_admission as stage
import cec_zone_fill as zone_fill
from cec_native_items import discard_items
from root_source_capture_search_policy_20261012 import source_capture_search_predicate


class Refused(ValueError):
    def __init__(self,reason,telemetry):
        super().__init__(reason)
        self.telemetry=telemetry


def future_escape_segments(source_board, reservation, *, source_sha256, hint,
                           blocked_net, layer):
    """Validate an entire proposed escape, including its full-width join.

    Reservations protect geometric opportunities, never authorize divided
    current or add saved copper. A route which respects only the fingers can
    still consume the joining corridor. The caller must remove ALL returned
    native segments before independent saved-source receiving.
    """
    if (reservation.get('source_sha256')!=source_sha256
            or reservation.get('capacity_or_equal_current_division_claimed') is not False
            or reservation.get('net')==blocked_net
            or source_board.GetLayerID(reservation.get('layer',''))!=layer
            or layer not in (pcbnew.F_Cu,pcbnew.B_Cu)):
        raise ValueError('exact_source_future_escape_geometry_scope_required')
    net=reservation['net']
    with force._thermal_hint(hint):
        contract=topology.route_width_contracts(source_board,hint)[net]
        domain=topology.board_current_domains(source_board,hint)[net]
    if not domain['complete'] or domain['missing_refs']:
        raise ValueError('complete_unchanged_future_force_domain_required')
    full=math.ceil(contract['required_by_layer_mm'][fab.COPPER_LAYER_IDS[layer]]*1e6)
    width=reservation['split_width_nm']
    if (type(width) is not int or not 0<width<full<=20000000
            or fab.COPPER_LAYER_IDS[layer] not in contract['routing_layers']):
        raise ValueError('bounded_future_split_geometry_and_actual_full_join_required')
    source=next((q for q in source_board.GetTracks()
        if force._uid(q)==reservation['source_track_uuid']),None)
    if (source is None or source.GetClass()!='PCB_TRACK' or source.GetNetname()!=net
            or source.GetLayer()!=layer or source.GetWidth()<full):
        raise ValueError('actual_full_width_future_source_contact_required')
    def point(row):
        if (type(row) is not list or len(row)!=2
                or any(type(v) is not int or abs(v)>2000000000 for v in row)):
            raise ValueError('bounded_integer_future_native_points_required')
        return pcbnew.VECTOR2I(*row)
    paths=reservation['paths_nm'];collector=reservation['collector_nm']
    if (type(paths) is not list or not 2<=len(paths)<=8
            or any(type(q) is not list or not 2<=len(q)<=16 for q in paths)
            or sum(len(q) for q in paths)>64 or type(collector) is not list or len(collector)!=2):
        raise ValueError('bounded_complete_future_fingers_and_join_required')
    ends=[point(q) for q in collector]
    join=pcbnew.SHAPE_SEGMENT(*ends,full)
    if not join.Collide(point(reservation['body_start_nm']),0):
        raise ValueError('future_body_must_begin_in_actual_join')
    segments=[]
    for path in paths:
        native=[point(q) for q in path]
        if (not source.GetEffectiveShape(layer).Collide(pcbnew.SHAPE_SEGMENT(native[0],native[0],width),0)
                or not join.Collide(pcbnew.SHAPE_SEGMENT(native[-1],native[-1],width),0)):
            raise ValueError('future_finger_requires_real_source_and_join_contact')
        segments.extend((a,z,width) for a,z in zip(native,native[1:]))
    segments.append((*ends,full))
    for a,z,w in segments:
        if (tuple(a)==tuple(z) or not (a.x==z.x or a.y==z.y or abs(a.x-z.x)==abs(a.y-z.y))
                or math.dist(tuple(a),tuple(z))>64000000):
            raise ValueError('bounded_canonical_future_native_segments_required')
    return segments


def force_plan(board, source, hint, ids):
    """Explicit complete force-domain load, NEVER a distributed-load alias."""
    assert 1<=len(ids)<=32 and len(set(ids))==len(ids)
    tracks={force._uid(q):q for q in board.GetTracks()}
    assert set(ids)<=tracks.keys()
    net=str(tracks[ids[0]].GetNetname())
    with force._thermal_hint(hint):
        contract=topology.route_width_contracts(board,hint)[net]
        domain=topology.board_current_domains(board,hint)[net]
    assert domain['complete'] and not domain['missing_refs']
    grouped={force._uid(q) for g in board.Groups() for q in g.GetItems()}
    for uid in ids:
        q=tracks[uid];face=fab.COPPER_LAYER_IDS.get(q.GetLayer())
        floor=contract['required_by_layer_mm'].get(face)
        assert (q.GetClass()=='PCB_TRACK' and uid not in grouped and q.GetNetname()==net
            and q.GetLayer() in (pcbnew.F_Cu,pcbnew.B_Cu) and face in contract['routing_layers']
            and floor is not None and 0<floor<=1.
            and math.ceil(floor*1e6)<=q.GetWidth()<=1000000 and 0<q.GetLength()<=32000000), \
            'source_force_edge_below_full_original_load_or_outside_bound'
    spec=fr._project_netclass_resolver(str(source))(net) or {}
    contract=dict(contract,clearance_mm=max(.2,float(spec.get('clearance') or .2)))
    return dict(retired_track_uuids=sorted(ids),contracts={net:contract},source_domain=domain,
        source_boundaries=ordinary._boundaries(board,board,[tracks[u] for u in sorted(ids)],time.monotonic()+9.5),
        original_full_force_current_and_widths_preserved=True,inferred_branch_load=False)


def extend_cut(board, seeds, contract, *, maximum=32, distance_mm=64.):
    """Bounded centreline chain proposal; whole material receiving is required.

    Overlapping caps of sub-width cleanup jogs are not centreline branches.
    Do not infer preserved connectivity from this proposal. Actual pads,
    barrels, zones and centreline tees stop it; saved partitions, boundaries
    and absolute cuts must independently verify every retained contact.
    """
    if (type(maximum) is not int or not 1<=maximum<=32
            or type(distance_mm) not in (int,float) or not 0<distance_mm<=64):
        raise ValueError('bounded_explicit_chain_construction_scope_required')
    live = list(board.GetTracks())
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    zones = [z for z in board.Zones() if not z.GetIsRuleArea()]
    grouped = {force._uid(q) for g in board.Groups() for q in g.GetItems()}
    seen = set(seeds)
    pending = sorted((t for t in live if force._uid(t) in seen), key=force._uid)
    deadline = time.monotonic()+9.5
    length = 0
    while pending:
        copper._check_deadline(deadline)
        edge = pending.pop(0)
        layer = edge.GetLayer()
        for at in (edge.GetStart(), edge.GetEnd()):
            marker = pcbnew.SHAPE_SEGMENT(at, at, 1)
            def touches(q):
                return (q.GetNetCode()==edge.GetNetCode() and q.IsOnLayer(layer)
                    and q.GetEffectiveShape(layer).Collide(marker, 0))
            if (any(touches(p) for p in pads) or any(z.IsOnLayer(layer)
                    and z.GetNetCode()==edge.GetNetCode() and (not z.IsFilled()
                    or z.GetFilledPolysList(layer).Collide(marker, 0)) for z in zones)):
                continue
            if any(t.GetClass()=='PCB_VIA' and touches(t) for t in live):
                continue
            incident = [t for t in live if t.GetClass()=='PCB_TRACK'
                and t.GetNetCode()==edge.GetNetCode() and t.GetLayer()==layer
                and tuple(at) in (tuple(t.GetStart()),tuple(t.GetEnd()))]
            if len(incident)!=2:
                continue
            other = next(t for t in incident if force._uid(t)!=force._uid(edge))
            uid = force._uid(other)
            floor = math.ceil(contract['required_by_layer_mm'][fab.COPPER_LAYER_IDS[layer]]*1e6)
            if (uid in seen or uid in grouped or other.GetClass()!='PCB_TRACK'
                    or other.GetLayer()!=layer or other.GetWidth()!=edge.GetWidth()
                    or not floor<=other.GetWidth()<=1000000 or other.GetLength()>32000000
                    or tuple(at) not in (tuple(other.GetStart()),tuple(other.GetEnd()))):
                continue
            if len(seen)>=maximum or length+other.GetLength()>distance_mm*1e6:
                raise ValueError('complete_degree_two_source_cut_exceeds_explicit_bound')
            seen.add(uid)
            pending.append(other)
            length += other.GetLength()
    return sorted(seen)


def construct(source, *, hint, zone_uuid, target_name, seed_uuids, reservation,
              enclosure_margin_nm=0, body_max_vias=0):
    b = pcbnew.LoadBoard(str(source))
    src = pcbnew.LoadBoard(str(source))
    zone = next(z for z in b.Zones() if force._uid(z)==zone_uuid)
    assert (not zone.GetIsRuleArea() and zone.IsFilled()
        and len(zone.GetLayerSet().CuStack())==1 and zone.GetParentGroup() is None)
    old_layer, target = zone.GetLayer(), b.GetLayerID(target_name)
    assert {old_layer,target}=={pcbnew.F_Cu,pcbnew.B_Cu}
    assert type(enclosure_margin_nm) is int and 0<=enclosure_margin_nm<=100000
    assert type(body_max_vias) is int and 0<=body_max_vias<=2
    shape = zone.GetFilledPolysList(old_layer).CloneDropTriangulation()
    native_fill.identity(shape,time.monotonic()+9.5)
    contacts = [q for q in [*b.GetTracks(),*(p for fp in b.GetFootprints() for p in fp.Pads())]
        if q.GetNetCode()==zone.GetNetCode() and q.IsOnLayer(old_layer)
        and shape.Collide(q.GetEffectiveShape(old_layer),0)]
    assert 2<=len(contacts)<=32 and all(q.GetClass()=='PAD'
        and q.GetAttribute()==pcbnew.PAD_ATTRIB_PTH and q.HasHole()
        and q.IsOnLayer(target) for q in contacts), 'exact_plated_source_bank_contacts_required'
    seed_plan = force_plan(b,source,hint,seed_uuids)
    assert len(seed_plan['contracts'])==1
    net, contract = next(iter(seed_plan['contracts'].items()))
    assert net!=zone.GetNetname()
    retired = extend_cut(b,seed_uuids,contract)
    plan = force_plan(b,source,hint,retired)
    assert len(plan['source_boundaries'])==1, 'one_complete_planar_preclear_branch_required'
    boundary = plan['source_boundaries'][0]
    old = [t for t in b.GetTracks() if force._uid(t) in set(retired)]
    width = max(t.GetWidth() for t in old)
    assert len({t.GetWidth() for t in old})==1
    assert width>=math.ceil(contract['required_by_layer_mm']['B.Cu']*1e6)
    report = dict(source_plan=plan,retired_track_uuids=retired,
        source_plated_contact_uuids=sorted(force._uid(q) for q in contacts),
        reflowed_zone_uuid=zone_uuid,zone_net=zone.GetNetname(),
        original_layer=b.GetLayerName(old_layer),target_layer=target_name,
        source_zone_area_or_current_reduced=False,full_source_branch_width_nm=width,
        source_bank_enclosure_margin_nm=enclosure_margin_nm)
    discard_items(b,old)
    if enclosure_margin_nm:
        outline=zone.Outline()
        assert outline.OutlineCount()==1 and outline.HoleCount(0)==0
        ring=outline.COutline(0)
        points=[[int(ring.CPoint(i).x),int(ring.CPoint(i).y)] for i in range(ring.PointCount())]
        expanded=copper.purposeful_envelope(shape,style='chamfer45',
            margin_nm=enclosure_margin_nm,grid_nm=1000)
        zone.Outline().RemoveAllContours();zone.Outline().NewOutline()
        for x,y in expanded:
            zone.Outline().Append(x,y)
    copper._require_unoccupied_outline(b,zone.Outline(),zone.GetNetname(),target,
        time.monotonic()+9.5,clearance_nm=max(zone.GetLocalClearance(),b.GetDesignSettings().m_MinClearance),
        allow_native_hole_bridges=True)
    zone.UnFill()
    zone.SetLayer(target)
    batch = pcbnew.ZONES();batch.append(zone)
    report['native_reflow_compilation'] = zone_fill.compile_selected(b,batch,initialize_selected=True)
    filled = zone.GetFilledPolysList(target)
    loss = shape.CloneDropTriangulation();loss.BooleanSubtract(filled)
    if loss.OutlineCount():
        box=loss.BBox()
        raise ValueError('actual_source_bank_fill_lost_on_target_face:'+json.dumps(dict(
            original_fill_sha256=native_fill.identity(shape,time.monotonic()+9.5)[0],
            target_fill_sha256=native_fill.identity(filled,time.monotonic()+9.5)[0],
            loss_bounds_nm=[box.GetLeft(),box.GetTop(),box.GetRight(),box.GetBottom()],
            loss_polygons=native_fill.snapshot(loss,time.monotonic()+9.5,max_vertices=4096,max_polygons=32))))
    for q in contacts:
        assert filled.Collide(q.GetEffectiveShape(target),0), 'plated_bank_contact_lost'
    report['whole_original_filled_bank_enclosed_on_equal_outer_face']=True
    parts = ports.boundary_components(b,net,b.GetLayerID(boundary['layer']),
        boundary['anchors_nm'],deadline=time.monotonic()+9.5)
    assert len(parts)==2, 'two_actual_surviving_branch_components_required'
    report['actual_retained_branch_components'] = parts
    layer = old_layer
    code = b.GetNetcodeFromNetname(net)
    gap = max(math.ceil(contract['clearance_mm']*1e6),b.GetDesignSettings().m_MinClearance)
    diameter,drill,_ = fab.board_legal_through_via_geometry(b,.6,.3)
    diameter_nm = max(round(diameter*1e6),width+round(drill*1e6))
    incoming, records = [], []
    temporary=[]
    reserved=future_escape_segments(src,reservation,source_sha256=force._hash(source),
        hint=hint,blocked_net=net,layer=layer)
    for left,right,reserved_width in reserved:
        q=pcbnew.PCB_TRACK(b);q.SetStart(left);q.SetEnd(right)
        q.SetWidth(reserved_width);q.SetLayer(layer)
        q.SetNetCode(b.GetNetcodeFromNetname(reservation['net']));b.Add(q);temporary.append(q)
    report['future_native_reservation']=dict(segments=len(reserved),
        fingers=sum(len(q)-1 for q in reservation['paths_nm']),
        joining_collector_included=True,collector_width_nm=reserved[-1][2],
        source_sha256=reservation['source_sha256'],capacity_assumed=False)
    with force._thermal_hint(hint):
        guard = capture.Guard(src,source,net=net,board_hint=hint,timeout_s=9.5)
    menus=ports.retained_face_ports(b,net,b.GetLayerID(boundary['layer']),boundary['anchors_nm'],
        route_layers=[pcbnew.F_Cu,pcbnew.B_Cu],minimum_width_nm=width,
        deadline=time.monotonic()+9.5,max_ports=16,allow_plated_pad_ports=True)
    assert len(menus)==2
    report['actual_native_component_port_menus']=menus
    filtered=[]
    for menu in menus:
        rows=[]
        for port in menu['ports']:
            if not guard.allows_endpoint(port):
                continue
            at=pcbnew.VECTOR2I(*port['at_nm'])
            need=layer not in port['layers']
            if need and (not fr._via_spot_clear(b,at,diameter_nm,gap,{code},
                    drill_nm=round(drill*1e6),net_code=code,foreign_cache={})
                    or not fr._edge_leg_clear(b,at,at,(diameter_nm+1)//2)):
                continue
            rows.append(dict(port,needs_new_barrel=need))
        assert rows, 'actual_full_web_clear_branch_exit_required'
        filtered.append(rows)
    pairs=sorted([(x,y) for x in filtered[0] for y in filtered[1]],key=lambda pair:(
        sum(q['needs_new_barrel'] for q in pair),math.dist(pair[0]['at_nm'],pair[1]['at_nm']),
        pair[0]['at_nm'],pair[1]['at_nm']))
    pairs=ports.diverse_pairs(pairs,point=lambda q:q['at_nm'],layers=lambda q:q['layers'],limit=4,breadth=4)
    ops=None;attempts=[]
    for pair in pairs:
        added_vias=[]
        for port in pair:
            if not port['needs_new_barrel']:
                continue
            at=pcbnew.VECTOR2I(*port['at_nm'])
            v=pcbnew.PCB_VIA(b);v.SetPosition(at);v.SetWidth(diameter_nm);v.SetDrill(round(drill*1e6))
            v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
            v.SetNetCode(code);v.SetLocked(True);b.Add(v);added_vias.append(v)
        with force._thermal_hint(hint):
            active_guard=capture.Guard(src,source,net=net,board_hint=hint,timeout_s=9.5)
        search={}
        anchors=[pcbnew.VECTOR2I(*q['at_nm']) for q in pair]
        body_layers=[pcbnew.F_Cu,pcbnew.B_Cu] if body_max_vias else [layer]
        ops=fr._multilayer_maze_lastmile_ops(b,*anchors,code,body_layers,gap,
            lambda s,t,r:fr._edge_leg_clear(b,s,t,r),width_for_layer=lambda l:width,
            start_layers=[layer],end_layers=[layer],grid_mm=.2,max_vias=body_max_vias,
            drill=drill,dia=diameter_nm/1e6,
            foreign_cache={},deadline_monotonic=time.monotonic()+9.5,max_length_nm=64000000,
            diagnostics=search,heuristic_weight=3.,canonical_turns_only=True,
            obstacle_channel_axes=True,native_board_envelope=True,max_expanded_states=200000,
            allow_single_layer=len(body_layers)==1,planar_guard=source_capture_search_predicate(active_guard),
            neutral_state_dominance=True,field_state_dominance=True)
        actual_blockers=[]
        zone_index,copper_index=fr._identified_foreign_shape_indexes(b,layer,{code})
        for hop in search.get('blocked_hop_samples',[])[:8]:
            if hop['layer']!=b.GetLayerName(layer):
                continue
            start=pcbnew.VECTOR2I(*(round(v*1e6) for v in hop['start_mm']))
            end=pcbnew.VECTOR2I(*(round(v*1e6) for v in hop['end_mm']))
            hits=fr._snapshot_foreign_blockers(start,end,width,gap,zone_index,copper_index)
            actual_blockers.append(dict(hop=hop,actual_native_blockers=hits))
        search['identified_actual_native_hop_blockers']=actual_blockers
        attempts.append(dict(ports=pair,search=search,found=bool(ops)))
        if ops:
            incoming.extend(added_vias)
            for v in added_vias:
                records.append(dict(kind='via',uuid=force._uid(v),at_nm=list(v.GetPosition()),
                    diameter_nm=diameter_nm,drill_nm=round(drill*1e6),net=net))
            report['selected_actual_retained_ports']=pair
            break
        discard_items(b,added_vias)
    discard_items(b,temporary)
    report['search_attempts'] = attempts
    if not ops or len(ops)>128:
        raise Refused('bounded_future_clear_full_source_branch_not_found',report)
    for op in ops:
        if op[0]=='via':
            _,at,d,land=op
            assert d==drill and round(land*1e6)==diameter_nm
            v=pcbnew.PCB_VIA(b);v.SetPosition(at);v.SetWidth(diameter_nm);v.SetDrill(round(drill*1e6))
            v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
            v.SetNetCode(code);v.SetLocked(True);b.Add(v);incoming.append(v)
            records.append(dict(kind='via',uuid=force._uid(v),at_nm=list(at),
                diameter_nm=diameter_nm,drill_nm=round(drill*1e6),net=net))
            continue
        kind,s,t,w,l=op
        assert kind=='trk' and w==width and l in body_layers
        q=pcbnew.PCB_TRACK(b);q.SetStart(s);q.SetEnd(t);q.SetWidth(w);q.SetLayer(l)
        q.SetNetCode(code);q.SetLocked(True);b.Add(q);incoming.append(q)
        records.append(dict(kind='track',uuid=force._uid(q),start_nm=list(s),end_nm=list(t),
            width_nm=w,layer_id=l,net=net))
    report.update(incoming_records=records,incoming_uuids=[force._uid(q) for q in incoming],
        added_via_uuids=[force._uid(q) for q in incoming if q.GetClass()=='PCB_VIA'],
        future_reservation_saved_as_copper=False)
    return b,report


def main():
    p=argparse.ArgumentParser()
    for name in ('source','source-drc','reservation','reporting-build','out'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--hint',required=True);p.add_argument('--zone',required=True)
    p.add_argument('--target-layer',required=True);p.add_argument('--seed',action='append')
    p.add_argument('--obstruction-probe',type=Path)
    p.add_argument('--bank-enclosure-margin-mm',type=float,default=0.)
    p.add_argument('--body-max-vias',type=int,default=0)
    a=p.parse_args();assert not a.out.exists();a.out.mkdir()
    epoch,family=force._code_identity(),force._family(a.source,a.hint)
    r=dict(schema=1,source=str(a.source),source_sha256=force._hash(a.source),code_identity=epoch,
        candidate=None,errors=[],scope='private_joint_pth_bank_and_full_load_branch_prototype',
        current_qualified=False,coupled_thermal_qualified=False,fab_ready=False,release_authority=False)
    try:
        assert bool(a.seed)!=(a.obstruction_probe is not None), 'one_explicit_native_source_cut_scope_required'
        if a.obstruction_probe:
            probe=json.loads(a.obstruction_probe.read_text())
            assert probe['source_sha256']==force._hash(a.source) and probe['zone_uuid']==a.zone
            hits=probe['faces'][a.target_layer]['blockers']
            assert 1<=len(hits)<=32 and all(q['kind']=='track' for q in hits)
            a.seed=sorted({q['uuid'] for q in hits})
            r['exact_obstruction_probe_sha256']=force._hash(a.obstruction_probe)
        b,constructed=construct(a.source,hint=a.hint,zone_uuid=a.zone,target_name=a.target_layer,
            seed_uuids=a.seed,reservation=json.loads(a.reservation.read_text()),
            enclosure_margin_nm=round(a.bank_enclosure_margin_mm*1e6),body_max_vias=a.body_max_vias)
        r.update(constructed)
        child=force._copy_family(a.source,a.out/'UNADMITTED-joint-native-bank-preclear')
        additive._ground_refill(b);field._save_field_snapshot(b,child)
        r.update(candidate=str(child),candidate_sha256=force._hash(child))
        r['current_debt_receiving']=current.receive(a.source,child,board_hint=a.hint)
        assert r['current_debt_receiving']['ok'] and r['current_debt_receiving']['complete']
        first=sense.replay(a.source,board_hint=a.hint,timeout_s=10.)
        last=sense.replay(child,board_hint=a.hint,timeout_s=10.)
        branch_net=next(iter(r['source_plan']['contracts']))
        transform=dict(net=branch_net,retired_track_uuids=r['retired_track_uuids'],
            added_track_uuids=r['incoming_uuids'],added_via_uuids=r['added_via_uuids'],
            retired_via_uuids=[],added_zone_uuids=[])
        r['physical_kelvin_preservation']=sense.compare_contour_preservation(first,last,
            modified_nets=[branch_net,r['zone_net']],native_copper_transforms=[transform])
        assert r['physical_kelvin_preservation']['comparison_complete'] and r['physical_kelvin_preservation']['same_evidence']
        old=pcbnew.LoadBoard(str(a.source));parts=ordinary._partition(old,time.monotonic()+10.,
            retired_uuids=set(r['retired_track_uuids']))
        updated=ordinary._partition(pcbnew.LoadBoard(str(child)),time.monotonic()+10.,
            retained_keys=set().union(*parts))
        assert all(any(q<=v for v in updated) for q in parts)
        r['native_partitions_preserved']=True
        with force._thermal_hint(a.hint):
            r['new_field_blockers']=sorted(field.blocker_keys(field.field_coupling_summary(str(child)))
                -field.blocker_keys(field.field_coupling_summary(str(a.source))))
        assert not r['new_field_blockers']
        intake=force._copy_family(child,a.out/'native-grade')
        produced=native.run(intake,a.out/'candidate.drc.json',reporting_build=a.reporting_build,timeout_s=10.)
        assert produced['ok'] and produced['complete'] and not produced['native_inventory']['potentially_truncated']
        actual=json.loads((a.out/'candidate.drc.json').read_text())
        prior=json.loads(a.source_drc.read_text());baseline={stage._canonical_identity(q) for q in prior['violations']}
        r['opens']=len(actual['unconnected_items'])
        r['new_native_faults']=[q for q in actual['violations'] if stage._canonical_identity(q) not in baseline]
        assert not r['new_native_faults'], 'new_native_faults_refused'
        r['independent_whole_saved_source_receiving_required']=True
    except Exception as exc:
        if isinstance(exc,Refused):
            r['construction_trial']=exc.telemetry
        r['errors'].append(type(exc).__name__+':'+str(exc))
    assert epoch==force._code_identity() and family==force._family(a.source,a.hint)
    r['source_and_code_unchanged']=True
    force._write(a.out/'construction.json',r)
    print(json.dumps({k:r.get(k) for k in ('candidate','opens','retired_track_uuids','errors')}),flush=True)


if __name__=='__main__':
    main()
