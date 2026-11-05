"""Exact reconstruction of a source-proved, grouped consumer route.

An electrical allocation is not immutable placement. It is also not deletion
permission: source and saved-child native proofs must reproduce the same
consumer, aggregate envelope, one real tap and load. Only selected linear
members of that ONE proved group can be replaced. No part, source barrel,
tap, other group, rule, budget or release authority is changed.
"""
import math,time,tempfile
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_supply_consumer_branch as consumer
import cec_ordinary_route_receiving as ordinary
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_fab_profile as fab
import cec_native_supply_via_context as web
import cec_fr as fr
import cec_route_quality as craft
from cec_native_items import discard_items


def plan(board,source,*,board_hint,retired_track_uuids,timeout_s=10.):
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10
            or type(board_hint) is not str or not board_hint):
        raise ValueError('bounded_source_consumer_group_context_required')
    cut=ordinary._ids(retired_track_uuids,'source_consumer_group_track_scope',16)
    if not cut:raise ValueError('nonempty_exact_consumer_group_cut_required')
    inventory=consumer.inventory(board,board_hint=board_hint,timeout_s=timeout_s)
    if not inventory['complete']:raise ValueError('complete_positive_source_consumer_group_required')
    groups=[g for g in board.Groups() if any(force._uid(t) in cut for t in g.GetItems())]
    if len(groups)!=1:raise ValueError('one_source_consumer_group_must_own_every_cut')
    group=groups[0];members={force._uid(t) for t in group.GetItems()}
    if (not group.GetName().startswith(consumer.PREFIX) or group.GetParentGroup() is not None
            or not cut<members or any(g.ContainsItem(group) for g in board.Groups())):
        raise ValueError('partial_member_cut_of_one_unnested_consumer_group_required')
    root,anchor,via_csv=group.GetName()[len(consumer.PREFIX):].split('|')
    proofs=[q for q in inventory['proofs'] if q['root_pad_uuid']==root and q['anchor_uuid']==anchor]
    if len(proofs)!=1:raise ValueError('unique_independent_source_consumer_group_proof_required')
    proof=proofs[0];tracks={force._uid(t):t for t in board.GetTracks()}
    if not cut<=members or any(u not in tracks or tracks[u].GetClass()!='PCB_TRACK'
            or tracks[u].GetNetname()!=proof['net'] or tracks[u].GetLayer() not in (pcbnew.F_Cu,pcbnew.B_Cu)
            or not 0<tracks[u].GetWidth()<=1000000 or not 0<tracks[u].GetLength()<=32000000
            or tracks[u].GetParentGroup() is None
            or not group.ContainsItem(tracks[u]) for u in cut):
        raise ValueError('bounded_same_net_source_consumer_group_tracks_required')
    if any(force._uid(g)!=force._uid(group) and any(force._uid(t) in cut for t in g.GetItems()) for g in board.Groups()):
        raise ValueError('source_consumer_group_cut_has_another_owner')
    if sum(tracks[u].GetLength() for u in cut)>64000000:
        raise ValueError('source_consumer_group_total_span_bound')
    authored=max(tracks[u].GetWidth() for u in cut);budget=proof['budget']
    widths={name:max(authored,math.ceil(value*1e6)) for name,value in budget['required_by_layer_mm'].items()}
    if any(tracks[u].GetWidth()<math.ceil(budget['required_by_layer_mm'][fab.COPPER_LAYER_IDS[tracks[u].GetLayer()]]*1e6)
            for u in cut):raise ValueError('source_consumer_group_cut_must_already_carry_its_full_load')
    boundaries=ordinary._boundaries(board,board,[tracks[u] for u in sorted(cut)],time.monotonic()+timeout_s)
    return dict(schema=1,source_sha256=force._hash(source),net=proof['net'],group_uuid=force._uid(group),
        source_group_name=group.GetName(),source_group_members=sorted(members),root_pad_uuid=root,
        anchor_uuid=anchor,source_via_uuids=sorted(filter(None,via_csv.split(','))),
        retired_track_uuids=sorted(cut),source_budget=budget,required_by_layer_nm=widths,
        source_boundaries=boundaries,source_current_reduced=False,branch_sharing_assumed=False,
        private_intermediate_not_an_admission_baseline=True,release_authority=False)


def subtract(board,scope):
    """Typed transaction only; the native deletion primitive stays fail-closed."""
    group=next(g for g in board.Groups() if force._uid(g)==scope['group_uuid'])
    if (group.GetName()!=scope['source_group_name']
            or sorted(force._uid(t) for t in group.GetItems())!=scope['source_group_members']):
        raise ValueError('consumer_group_subtraction_source_identity_changed')
    items={force._uid(t):t for t in board.GetTracks()}
    selected=[items[u] for u in scope['retired_track_uuids']]
    for item in selected:group.RemoveItem(item)
    discard_items(board,selected)


def assign(board,scope,track_uuids,via_uuids):
    group=next(g for g in board.Groups() if force._uid(g)==scope['group_uuid'])
    if (group.GetName()!=scope['source_group_name'] or set(force._uid(t) for t in group.GetItems())
            !=set(scope['source_group_members'])-set(scope['retired_track_uuids'])):
        raise ValueError('consumer_group_retained_members_or_tap_changed')
    live={force._uid(t):t for t in board.GetTracks()}
    for uid in track_uuids:group.AddItem(live[uid])
    vias=sorted(set(scope['source_via_uuids'])|set(via_uuids))
    group.SetName(consumer.PREFIX+'|'.join((scope['root_pad_uuid'],scope['anchor_uuid'],','.join(vias))))


def receive(source,candidate,*,board_hint,retired_track_uuids,timeout_s=10.):
    report=dict(schema=1,scope='exact_source_consumer_group_reconstruction',ok=False,complete=False,
        errors=[],source_current_reduced=False,branch_sharing_assumed=False,
        terminal_or_barrel_ampacity_qualified=False,release_authority=False)
    try:
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,candidate)]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        scope=plan(parent,source,board_hint=board_hint,retired_track_uuids=retired_track_uuids,timeout_s=timeout_s)
        _,old=additive._nodes(source);_,new=additive._nodes(candidate)
        retired=set(scope['retired_track_uuids']);incoming=new.keys()-old.keys()
        if old.keys()-new.keys()!=retired or not 1<=len(incoming)<=128:
            raise ValueError('exact_saved_consumer_group_cut_and_incoming_inventory_required')
        live={force._uid(t):t for t in child.GetTracks()};tracks=[];vias=[]
        if not incoming<=live.keys():raise ValueError('consumer_group_incoming_must_be_native_conductors')
        for uid in sorted(incoming):
            item=live[uid]
            if item.GetNetname()!=scope['net']:raise ValueError('consumer_group_incoming_net_changed')
            if item.GetClass()=='PCB_TRACK':
                if (item.GetLayer() not in (pcbnew.F_Cu,pcbnew.B_Cu)
                        or item.GetWidth()<scope['required_by_layer_nm'][fab.COPPER_LAYER_IDS[item.GetLayer()]]
                        or not craft.is_canonical_stroke(tuple(item.GetStart()),tuple(item.GetEnd()))):
                    raise ValueError('consumer_group_complete_actual_face_load_width_required')
                tracks.append(uid)
            elif item.GetClass()=='PCB_VIA':vias.append(uid)
            else:raise ValueError('consumer_group_unsupported_incoming_conductor')
        if not tracks or len(vias)>4 or sum(live[u].GetLength() for u in tracks)>80000000:
            raise ValueError('consumer_group_incoming_geometry_bound')
        proof=consumer.inventory(child,board_hint=board_hint,timeout_s=timeout_s)
        rows=[r for r in proof['proofs'] if r['root_pad_uuid']==scope['root_pad_uuid']]
        if (not proof['complete'] or len(rows)!=1 or rows[0]['budget']!=scope['source_budget']
                or rows[0]['anchor_uuid']!=scope['anchor_uuid']):
            raise ValueError('same_exact_saved_consumer_load_and_single_tap_required')
        report['saved_source_consumer_proof']=rows[0]
        contract=dict(net=scope['net'],current_authority=scope['source_budget']['current_authority'],
            required_by_layer_mm=scope['source_budget']['required_by_layer_mm'],routing_layers=['F.Cu','B.Cu'])
        report['actual_new_barrel_contact_web']=[web.receive(child,u,contract,timeout_s=2.) for u in vias]
        if not all(r['ok'] and r['complete'] for r in report['actual_new_barrel_contact_web']):
            raise ValueError('consumer_group_actual_new_full_load_barrel_web_required')
        if (force._preservation_snapshot(source)[1]!=force._preservation_snapshot(candidate)[1]
                or force._sidecars(source)!=force._sidecars(candidate)):
            raise ValueError('consumer_group_settings_parts_or_sidecars_changed')
        # Replay the source-owned group transformation and actual fresh native
        # conductors. Never copy a proposed group name/membership into authority.
        with tempfile.TemporaryDirectory(prefix='cec-consumer-group-replay-') as tmp:
            path=force._copy_family(source,Path(tmp)/'family')
            subtract(parent,scope)
            field._save_field_snapshot(parent,path)
            root,nodes=additive._nodes(path)
            basis=pcbnew.LoadBoard(str(path))
            spec=fr._project_netclass_resolver(str(source))(scope['net']) or {}
            clearance=max(basis.GetDesignSettings().m_MinClearance,
                math.ceil(float(spec.get('clearance') or .2)*1e6))
            for uid in vias:
                via=live[uid]
                if not fr._via_spot_clear(basis,via.GetPosition(),via.GetWidth(via.TopLayer()),
                        clearance,{via.GetNetCode()},drill_nm=via.GetDrillValue(),
                        net_code=via.GetNetCode(),foreign_cache={},native_padstack_via=via):
                    raise ValueError('consumer_group_source_minus_cut_native_barrel_guard_refused')
            path.write_text(additive._render([root[0],*root[1:],*[new[u] for u in sorted(incoming)]])+'\n')
            rebuilt=pcbnew.LoadBoard(str(path));assign(rebuilt,scope,tracks,vias)
            additive._ground_refill(rebuilt);field._save_field_snapshot(rebuilt,path)
            _,expected=additive._nodes(path)
            if expected.keys()!=new.keys() or any(syntax._freeze(expected[u])!=syntax._freeze(new[u]) for u in new):
                raise ValueError('consumer_group_exact_source_minus_cut_plus_saved_delta_differs')
        boundary_parent=pcbnew.LoadBoard(str(source))
        report['restored_full_width_source_boundaries']=ordinary._boundaries(
            boundary_parent,child,[t for t in boundary_parent.GetTracks()
                if force._uid(t) in retired],time.monotonic()+timeout_s)
        first=ordinary._partition(pcbnew.LoadBoard(str(source)),time.monotonic()+timeout_s,retired_uuids=retired)
        last=ordinary._partition(child,time.monotonic()+timeout_s,retained_keys=set().union(*first))
        if not all(any(p<=q for q in last) for p in first):
            raise ValueError('consumer_group_lost_original_surviving_native_partition')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in (source,candidate)]:
            raise ValueError('consumer_group_source_candidate_or_code_changed')
        report.update(ok=True,complete=True,source_scope=scope,incoming_track_uuids=tracks,
            incoming_via_uuids=vias,all_original_surviving_partitions_preserved=True,
            exact_native_ground_refill_replayed=True,source_candidate_and_code_unchanged=True)
    except Exception as exc:report['errors'].append(type(exc).__name__+':'+str(exc))
    return report
