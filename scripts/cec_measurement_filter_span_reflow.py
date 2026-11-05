"""Exact internal RC measurement-span replacement, not whole-net rip-up.

The independent canonical observer owns the actual three-land post-filter
node. This distinct operator proves a sole internal span between two native
terminal-bearing parts, then receives literal saved reconstruction, identical
native contacts, full Source width/face/process and all old partitions. No
pad, resistor, capacitor, barrel, force copper or filter value may change.
Full original-parent absolute Kelvin/current/field/native gates remain due.
"""
from copy import deepcopy
import math
import json
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_measurement_filter_span as observer
import cec_native_partition_pair as partitions
import cec_route_quality as craft
import cec_source_literal_additions as literal
import cec_source_literal_retirement as retirement
import cec_source_retaining_ses_import as text_io
import cec_sensitive_redundant_span as topology
from cec_native_items import discard_items

SCOPE='Source_canonical_RC_measurement_internal_span_reflow'
MAX_INCOMING=8


def _deadline(seconds):
    if type(seconds)not in(int,float)or not math.isfinite(seconds)or not 0<seconds<=10:
        raise ValueError('bounded_RC_span_native_constituent_required')
    return time.monotonic()+seconds


def _left(deadline):
    left=deadline-time.monotonic()
    if left<=0:raise ValueError('RC_span_native_deadline')
    return min(10.,left)


def plan(source,*,board_hint,pad_uuid,span_uuid,timeout_s=10.):
    deadline=_deadline(timeout_s);source=Path(source).resolve(strict=True)
    family=force._family(source,board_hint);code=force._code_identity();board=pcbnew.LoadBoard(str(source))
    proof=observer.plan(board,source,board_hint=board_hint,pad_uuid=pad_uuid,span_uuid=span_uuid,
        expected_source_sha256=force._hash(source),timeout_s=_left(deadline))
    # The observer alone grants no retirement. Establish this operation's
    # additional native scope: removing exactly this internal edge separates
    # the complete RC node into two actual terminal-bearing components.
    initial=topology._native_net_parts(board,proof['node_net'])
    projected=pcbnew.LoadBoard(str(source));discard_items(projected,[t for t in projected.GetTracks()if force._uid(t)==span_uuid])
    cut=topology._native_net_parts(projected,proof['node_net'])
    lands=set(proof['node_pad_uuids'])
    if len(initial)!=1 or len(cut)!=2 or any(not(set(part)&lands)for part in cut):
        raise ValueError('RC_span_must_be_a_sole_internal_two_terminal_bearing_cut')
    normalized=deepcopy(proof)
    # Runtime telemetry is not Source geometry or semantic authority. Each
    # invocation still spends and checks its own fresh bounded lease.
    normalized.pop('elapsed_s',None)
    normalized['source_context']=observer.semantic.replay_identity(normalized['source_context'])
    if family!=force._family(source,board_hint)or code!=force._code_identity():
        raise ValueError('RC_span_Source_epoch_changed')
    _left(deadline)
    return dict(schema=1,scope=SCOPE,source=str(source),source_sha256=force._hash(source),
        source_family=family,code_identity=code,board_hint=board_hint,pad_uuid=pad_uuid,span_uuid=span_uuid,
        source_observation=normalized,terminal_bearing_cut_parts=[sorted(set(p)&lands)for p in cut],
        exact_source_retirement=[span_uuid],maximum_incoming_tracks=MAX_INCOMING,
        all_original_parent_gates_still_required=True,current_authority=False,
        Kelvin_qualified=False,routing_admitted=False,release_authority=False)


def _process(node):
    return syntax._freeze([node[0],*[p for p in node[1:]if p[0]not in('uuid','start','end')]])


def _assess(board,proposal,points,deadline):
    q=proposal['source_observation'];uid=proposal['span_uuid']
    if(type(points)not in(list,tuple)or not 2<=len(points)<=MAX_INCOMING+1
            or any(type(p)not in(list,tuple)or len(p)!=2 or any(type(v)is not int or abs(v)>2000000000 for v in p)for p in points)):
        raise ValueError('bounded_integer_RC_span_path_required')
    if {tuple(points[0]),tuple(points[-1])}!={tuple(p)for p in q['source_points_nm']}:
        raise ValueError('RC_span_actual_endpoints_must_remain_fixed')
    if sum(math.dist(a,z)for a,z in zip(points,points[1:]))>sum(math.dist(a,z)for a,z in zip(q['source_points_nm'],q['source_points_nm'][1:]))+4000000:
        raise ValueError('RC_span_local_detour_bound')
    old=next(t for t in board.GetTracks()if force._uid(t)==uid)
    width=q['source_width_nm'];native=[]
    for a,z in zip(points,points[1:]):
        _left(deadline)
        if not craft.is_canonical_stroke(a,z,tolerance_nm=0):raise ValueError('RC_span_new_strokes_must_be_octilinear')
        t=old.Duplicate();t.m_Uuid.Clone(pcbnew.KIID());t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z));native.append(t)
        if(not fr._edge_leg_clear(board,t.GetStart(),t.GetEnd(),width/2+q['clearance_nm'])
                or not fr._tap_foreign_clear(board,t.GetStart(),t.GetEnd(),width,pcbnew.F_Cu,q['clearance_nm'],{old.GetNetCode()})):
            raise ValueError('RC_span_full_Source_clearance_or_edge_refused')
    # All new same-net contact must be the identical actual old endcap
    # contact, not a bbox/point count or an extra pickup inside another land.
    peers=[p for fp in board.GetFootprints()for p in fp.Pads()if p.GetNetname()==q['node_net']]
    peers += [t for t in board.GetTracks()if t.GetNetname()==q['node_net']and force._uid(t)!=uid]
    allowed={r['native_uuid']for r in q['retained_endcaps']}
    for outside in(False,True):
        total=pcbnew.SHAPE_POLY_SET()
        for t in native:total.BooleanAdd(observer._elbow_polygon(t,outside))
        old_shape=observer._elbow_polygon(old,outside)
        for peer in peers:
            _left(deadline);actual=observer._elbow_polygon(peer,outside)
            before=old_shape.CloneDropTriangulation();before.BooleanIntersection(actual)
            after=total.CloneDropTriangulation();after.BooleanIntersection(actual)
            if observer._elbow_contours(before,deadline)!=observer._elbow_contours(after,deadline):
                raise ValueError('RC_span_native_same_net_contact_changed:'+force._uid(peer))
            if after.OutlineCount()and force._uid(peer)not in allowed:
                raise ValueError('RC_span_unowned_same_net_contact')
    projected=pcbnew.LoadBoard(proposal['source']);discard_items(projected,[t for t in projected.GetTracks()if force._uid(t)==uid])
    rows=[dict(net=q['node_net'],layer=0,width_nm=width,start_nm=list(a),end_nm=list(z))for a,z in zip(points,points[1:])]
    quality=craft.assess_proposed_route(projected,rows,deadline=deadline)
    coupling=field.assess_proposed_route(projected,rows,deadline=deadline,
        netclass_resolver=fr._project_netclass_resolver(proposal['source']))
    if any(r.get('ok')is not True or r.get('complete')is not True for r in(quality,coupling)):
        raise ValueError('RC_span_whole_proposed_craft_or_field_refused')
    _left(deadline)
    return native,dict(complete=True,ok=True,native_lower_and_upper_contacts_identical=True,
        no_new_same_net_pickup=True,full_Source_clearance=True,proposed_craft=quality,proposed_field=coupling)


def write_private(proposal,directory,points_nm,*,timeout_s=10.):
    deadline=_deadline(timeout_s)
    fresh=plan(proposal['source'],board_hint=proposal['board_hint'],pad_uuid=proposal['pad_uuid'],
        span_uuid=proposal['span_uuid'],timeout_s=_left(deadline))
    if fresh!=proposal:raise ValueError('fresh_exact_Source_RC_span_plan_required')
    board=pcbnew.LoadBoard(fresh['source']);tracks,proof=_assess(board,fresh,points_nm,deadline)
    discard_items(board,[t for t in board.GetTracks()if force._uid(t)==fresh['span_uuid']])
    for t in tracks:board.Add(t)
    grounds=additive._ground_refill(board)
    target=force._copy_family(Path(fresh['source']),Path(directory))
    with tempfile.TemporaryDirectory(prefix='cec-RC-span-construction-')as work:
        native=Path(work)/'board.kicad_pcb';field._save_field_snapshot(board,native)
        projected=retirement.subtract(text_io.raw_text(Path(fresh['source'])),[fresh['span_uuid']])
        text_io.write_raw(target,literal.assemble(projected,text_io.raw_text(native),ground_ids=grounds))
    if fresh['source_family']!=force._family(Path(fresh['source']),fresh['board_hint'])or fresh['code_identity']!=force._code_identity():
        raise ValueError('RC_span_Source_changed_during_save')
    _left(deadline)
    return dict(complete=True,candidate=str(target),candidate_sha256=force._hash(target),construction=proof,
        independent_saved_receiving_required=True,routing_admitted=False,release_authority=False)


def receive(source,candidate,*,board_hint,pad_uuid,span_uuid,timeout_s=10.):
    r=dict(ok=False,complete=False,errors=[],scope=SCOPE,routing_admitted=False,release_authority=False,
        current_authority=False,Kelvin_qualified=False,all_original_parent_gates_still_required=True)
    try:
        deadline=_deadline(timeout_s);source,candidate=[Path(p).resolve(strict=True)for p in(source,candidate)]
        if source==candidate:raise ValueError('distinct_RC_span_saved_boundaries_required')
        code=force._code_identity();families=[force._family(p,board_hint)for p in(source,candidate)]
        q=plan(source,board_hint=board_hint,pad_uuid=pad_uuid,span_uuid=span_uuid,timeout_s=_left(deadline))
        parent,child=[pcbnew.LoadBoard(str(p))for p in(source,candidate)]
        _,old=additive._nodes(source);_,new=additive._nodes(candidate);incoming=set(new)-set(old)
        if set(old)-set(new)!={span_uuid}or not 1<=len(incoming)<=MAX_INCOMING:
            raise ValueError('one_exact_RC_span_cut_and_bounded_additions_required')
        tracks=[t for t in child.GetTracks()if force._uid(t)in incoming]
        if len(tracks)!=len(incoming)or any(t.GetClass()!='PCB_TRACK'or _process(new[force._uid(t)])!=_process(old[span_uuid])for t in tracks):
            raise ValueError('RC_span_new_material_must_retain_literal_Source_process')
        points=topology._chain(tracks);_,geometry=_assess(parent,q,points,deadline)
        paired=partitions.compare(parent,child,retired_uuids=[span_uuid],timeout_s=_left(deadline))
        if paired.get('available')is not True or paired.get('preserved')is not True:
            raise ValueError('RC_span_original_native_partition_lost')
        with tempfile.TemporaryDirectory(prefix='cec-RC-span-independent-')as work:
            projected=force._copy_family(source,Path(work)/'source-minus-one')
            text_io.write_raw(projected,retirement.subtract(text_io.raw_text(source),[span_uuid]))
            replay=additive.receive(projected,candidate,board_hint=board_hint,timeout_s=_left(deadline))
        if replay.get('ok')is not True or replay.get('complete')is not True:
            raise ValueError('RC_span_exact_saved_subtract_add_refill_replay_refused:'+str(replay.get('errors')))
        if code!=force._code_identity()or families!=[force._family(p,board_hint)for p in(source,candidate)]:
            raise ValueError('RC_span_saved_families_or_code_changed')
        r.update(ok=True,complete=True,independent_Source_plan=q,geometry=geometry,
            original_native_partitions=paired,exact_saved_subtract_add_refill=replay,
            added_native_uuids=sorted(incoming),retired_track_uuids=[span_uuid])
        _left(deadline)
    except Exception as exc:
        r.update(ok=False,complete=False);r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


PAIR_SCOPE='Source_canonical_three_land_RC_input_pair_tree_reconstruction'


def plan_pair(source,*,board_hint,pad_uuid,span_uuid,timeout_s=10.):
    """Distinct whole POST-filter pair scope, not a wider single-span plan.

    Both nets must be exactly the canonical manufacturer input, differential
    capacitor land and selected series-resistor INPUT land. Raw shunt copper,
    other loads, zones, barrels and arbitrary same-net branches cannot enter.
    """
    deadline=_deadline(timeout_s);source=Path(source).resolve(strict=True)
    family=force._family(source,board_hint);code=force._code_identity();board=pcbnew.LoadBoard(str(source))
    q=observer.plan(board,source,board_hint=board_hint,pad_uuid=pad_uuid,span_uuid=span_uuid,
        expected_source_sha256=force._hash(source),timeout_s=_left(deadline))
    _,nodes=additive._nodes(source);model=q['lineage'];result={};retired=[]
    grouped={force._uid(i)for g in board.Groups()for i in g.GetItems()}
    identities=[]
    for net in model['input_nets']:
        pads=[p for fp in board.GetFootprints()for p in fp.Pads()if p.GetNetname()==net]
        tracks=[t for t in board.GetTracks()if t.GetNetname()==net]
        if len(pads)!=3 or not 1<=len(tracks)<=64 or any(z.GetNetname()==net and not z.GetIsRuleArea()for z in board.Zones()):
            raise ValueError('RC_pair_exact_three_land_front_node_without_zones_required')
        if any(p.HasHole()or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or p.GetParentFootprint().IsDNP()
                or tuple(map(int,p.GetLayerSet().CuStack()))!=(0,)for p in pads):
            raise ValueError('RC_pair_both_nodes_require_populated_front_SMD_lands')
        if any(t.GetClass()!='PCB_TRACK'or int(t.GetLayer())!=0 or t.GetParentGroup()is not None
                or force._uid(t)in grouped or t.HasSolderMask()for t in tracks):
            raise ValueError('RC_pair_only_ungrouped_authored_front_signal_tracks')
        identities.extend(force._uid(i)for i in[*pads,*tracks])
        spec=fr._project_netclass_resolver(str(source),board=board)(net)or{}
        width=max(int(board.GetDesignSettings().m_TrackMinWidth),math.ceil(float(spec.get('track_width')or 0)*1e6))
        gap=max(int(board.GetDesignSettings().m_MinClearance),math.ceil(float(spec.get('clearance')or 0)*1e6))
        if not 0<width<=350000 or gap<=0 or any(t.GetWidth()!=width for t in tracks):
            raise ValueError('RC_pair_exact_complete_Source_signal_dimensions_required')
        signatures=set()
        for t in tracks:
            node=nodes[force._uid(t)]
            if any(type(n)is not list or not n or n[0]not in('start','end','width','layer','net','uuid','locked')for n in node[1:]):
                raise ValueError('RC_pair_unknown_Source_copper_metadata')
            signatures.add(syntax._freeze([node[0],*[n for n in node[1:]if n[0]not in('start','end','uuid','locked')]]))
        if len(signatures)!=1 or len(topology._native_net_parts(board,net))!=1:
            raise ValueError('RC_pair_complete_connected_uniform_Source_node_required')
        ids=sorted(force._uid(t)for t in tracks);retired+=ids
        result[net]=dict(pad_uuids=sorted(force._uid(p)for p in pads),track_uuids=ids,
            width_nm=width,clearance_nm=gap,locked=any(t.IsLocked()for t in tracks),
            Source_process=repr(next(iter(signatures))),Source_spec=spec,
            original_length_nm=sum(t.GetLength()for t in tracks))
    if len(identities)!=len(set(identities)):raise ValueError('RC_pair_unique_physical_material_identities_required')
    normalized=deepcopy(q);normalized.pop('elapsed_s',None)
    normalized['source_context']=observer.semantic.replay_identity(normalized['source_context'])
    if family!=force._family(source,board_hint)or code!=force._code_identity():raise ValueError('RC_pair_Source_epoch_changed')
    _left(deadline)
    return dict(schema=1,scope=PAIR_SCOPE,source=str(source),source_sha256=force._hash(source),
        source_family=family,code_identity=code,board_hint=board_hint,pad_uuid=pad_uuid,span_uuid=span_uuid,
        source_observation=normalized,nodes=result,retired_track_uuids=sorted(retired),
        force_copper_barrels_parts_and_filter_values_immutable=True,
        current_authority=False,Kelvin_qualified=False,routing_admitted=False,release_authority=False)


def _pair_geometry(parent,proposal,rows,deadline):
    if type(rows)not in(list,tuple)or not 2<=len(rows)<=64:
        raise ValueError('bounded_RC_pair_route_rows_required')
    board=pcbnew.LoadBoard(proposal['source']);cuts=set(proposal['retired_track_uuids'])
    prototypes={n:next(t for t in parent.GetTracks()if force._uid(t)in q['track_uuids'])for n,q in proposal['nodes'].items()}
    discard_items(board,[t for t in board.GetTracks()if force._uid(t)in cuts])
    made=[];lengths={n:0. for n in proposal['nodes']}
    for row in rows:
        _left(deadline)
        if type(row)is not dict or set(row)!={'net','start_nm','end_nm'}or row['net']not in proposal['nodes']:
            raise ValueError('RC_pair_geometry_cannot_supply_width_face_role_or_process')
        a,z=row['start_nm'],row['end_nm'];q=proposal['nodes'][row['net']]
        if any(type(p)not in(list,tuple)or len(p)!=2 or any(type(v)is not int or abs(v)>2000000000 for v in p)for p in(a,z)):
            raise ValueError('RC_pair_integer_native_coordinates_required')
        if not craft.is_canonical_stroke(a,z,tolerance_nm=0):raise ValueError('RC_pair_only_new_octilinear_strokes')
        t=prototypes[row['net']].Duplicate();t.m_Uuid.Clone(pcbnew.KIID());t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z))
        t.SetLocked(q['locked'])
        if(not fr._edge_leg_clear(board,t.GetStart(),t.GetEnd(),q['width_nm']/2+q['clearance_nm'])
                or not fr._tap_foreign_clear(board,t.GetStart(),t.GetEnd(),q['width_nm'],0,q['clearance_nm'],{t.GetNetCode()})):
            raise ValueError('RC_pair_new_full_Source_clearance_refused:'+row['net'])
        board.Add(t);made.append(t);lengths[row['net']]+=t.GetLength()
    for net,q in proposal['nodes'].items():
        if lengths[net]<=0 or lengths[net]>q['original_length_nm']+4000000:
            raise ValueError('RC_pair_local_path_length_bound')
        parts=topology._native_net_parts(board,net)
        expected=set(q['pad_uuids'])|{force._uid(t)for t in made if t.GetNetname()==net}
        if len(parts)!=1 or parts[0]!=expected:
            raise ValueError('RC_pair_all_actual_lands_and_every_new_edge_must_be_one_node')
    proposed=[dict(net=t.GetNetname(),layer=0,width_nm=t.GetWidth(),start_nm=list(t.GetStart()),end_nm=list(t.GetEnd()))for t in made]
    pristine=pcbnew.LoadBoard(proposal['source']);discard_items(pristine,[t for t in pristine.GetTracks()if force._uid(t)in cuts])
    quality=craft.assess_proposed_route(pristine,proposed,deadline=deadline)
    coupling=field.assess_proposed_route(pristine,proposed,deadline=deadline,netclass_resolver=fr._project_netclass_resolver(proposal['source']))
    if any(q.get('ok')is not True or q.get('complete')is not True for q in(quality,coupling)):
        raise ValueError('RC_pair_complete_incoming_craft_or_field_refused')
    return board,dict(ok=True,complete=True,geometry_only=False,each_post_filter_node_whole_native_connected=True,
        all_new_copper_F_only_full_Source_width=True,proposed_craft=quality,proposed_field=coupling,
        candidate_lengths_nm=lengths)


def write_pair_private(proposal,directory,rows,*,timeout_s=10.):
    deadline=_deadline(timeout_s)
    fresh=plan_pair(proposal['source'],board_hint=proposal['board_hint'],pad_uuid=proposal['pad_uuid'],
        span_uuid=proposal['span_uuid'],timeout_s=_left(deadline))
    if fresh!=proposal:raise ValueError('fresh_exact_Source_RC_pair_plan_required')
    parent=pcbnew.LoadBoard(fresh['source']);board,proof=_pair_geometry(parent,fresh,rows,deadline)
    grounds=additive._ground_refill(board);target=force._copy_family(Path(fresh['source']),Path(directory))
    with tempfile.TemporaryDirectory(prefix='cec-RC-pair-construction-')as work:
        native=Path(work)/'board.kicad_pcb';field._save_field_snapshot(board,native)
        projected=retirement.subtract(text_io.raw_text(Path(fresh['source'])),fresh['retired_track_uuids'])
        text_io.write_raw(target,literal.assemble(projected,text_io.raw_text(native),ground_ids=grounds))
    if fresh['source_family']!=force._family(Path(fresh['source']),fresh['board_hint'])or fresh['code_identity']!=force._code_identity():
        raise ValueError('RC_pair_Source_changed_during_save')
    _left(deadline)
    return dict(complete=True,candidate=str(target),candidate_sha256=force._hash(target),construction=proof,
        independent_saved_receiving_required=True,routing_admitted=False,release_authority=False)


def receive_pair(source,candidate,*,board_hint,pad_uuid,span_uuid,timeout_s=10.):
    r=dict(ok=False,complete=False,errors=[],scope=PAIR_SCOPE,current_authority=False,Kelvin_qualified=False,
        routing_admitted=False,release_authority=False,all_original_parent_gates_still_required=True)
    try:
        deadline=_deadline(timeout_s);source,candidate=[Path(p).resolve(strict=True)for p in(source,candidate)]
        if source==candidate:raise ValueError('distinct_RC_pair_saved_boundaries_required')
        code=force._code_identity();families=[force._family(p,board_hint)for p in(source,candidate)]
        q=plan_pair(source,board_hint=board_hint,pad_uuid=pad_uuid,span_uuid=span_uuid,timeout_s=_left(deadline))
        parent,child=[pcbnew.LoadBoard(str(p))for p in(source,candidate)]
        _,old=additive._nodes(source);_,new=additive._nodes(candidate);incoming=set(new)-set(old)
        if set(old)-set(new)!=set(q['retired_track_uuids'])or not 2<=len(incoming)<=64:
            raise ValueError('RC_pair_exact_complete_post_filter_retirement_required')
        tracks=[t for t in child.GetTracks()if force._uid(t)in incoming];rows=[]
        if len(tracks)!=len(incoming):raise ValueError('RC_pair_only_native_track_additions')
        for t in tracks:
            net=str(t.GetNetname());node=new[force._uid(t)]
            process=syntax._freeze([node[0],*[n for n in node[1:]if n[0]not in('start','end','uuid','locked')]])
            if(t.GetClass()!='PCB_TRACK'or net not in q['nodes']or int(t.GetLayer())!=0
                    or repr(process)!=q['nodes'][net]['Source_process']or t.IsLocked()!=q['nodes'][net]['locked']):
                raise ValueError('RC_pair_literal_Source_process_width_face_and_locks_required')
            rows.append(dict(net=net,start_nm=list(t.GetStart()),end_nm=list(t.GetEnd())))
        _,geometry=_pair_geometry(parent,q,rows,deadline)
        paired=partitions.compare(parent,child,retired_uuids=q['retired_track_uuids'],timeout_s=_left(deadline))
        if paired.get('available')is not True or paired.get('preserved')is not True:raise ValueError('RC_pair_retained_native_partition_lost')
        with tempfile.TemporaryDirectory(prefix='cec-RC-pair-independent-')as work:
            projected=force._copy_family(source,Path(work)/'source-minus-post-filter-trees')
            text_io.write_raw(projected,retirement.subtract(text_io.raw_text(source),q['retired_track_uuids']))
            replay=additive.receive(projected,candidate,board_hint=board_hint,timeout_s=_left(deadline))
        if replay.get('ok')is not True or replay.get('complete')is not True:
            raise ValueError('RC_pair_exact_saved_subtract_add_refill_replay_refused:'+str(replay.get('errors')))
        if code!=force._code_identity()or families!=[force._family(p,board_hint)for p in(source,candidate)]:raise ValueError('RC_pair_saved_epoch_changed')
        r.update(ok=True,complete=True,independent_Source_plan=q,geometry=geometry,
            original_native_partitions=paired,exact_saved_subtract_add_refill=replay,
            added_native_uuids=sorted(incoming),retired_track_uuids=q['retired_track_uuids'])
        _left(deadline)
    except Exception as exc:r.update(ok=False,complete=False);r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
