"""Rebuild one already-proved consumer leaf across obsolete route waypoints.

This narrow transaction joins a partial source-owned feed-group cut to a
bounded retained-island cut. Only explicitly selected, pad-free, exclusive
intermediate barrels may disappear. Parts, the real shared tap, every surviving
native conductor partition, current allocations, settings and power fills
remain authoritative. New tracks retain the actual face's complete existing
load floor; inner replacements require explicit source-authorized scope. A
separate opt-in permits at most two factory-size through barrels with complete
actual contact-web proof on every engaged face. No inner-layer neckdown,
inferred load split, plated-barrel ampacity or release credit is granted.
"""
import math,time,tempfile,traceback
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_consumer_group_reconstruction as group_owner
import cec_supply_consumer_branch as consumer
import cec_rated_branch_repair as rated
import cec_ordinary_route_receiving as ordinary
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_fr as fr
import cec_fab_profile as fab
import cec_route_quality as craft
import cec_native_rule_areas as rule_areas
import cec_native_supply_via_context as supply_web
from cec_native_items import discard_items


def plan(board,source,*,board_hint,grouped_track_uuids,island_track_uuids,via_uuids,timeout_s=10.,max_source_total_mm=80.,retained_waypoint_via_uuids=()):
    if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.:
        raise ValueError('bounded_consumer_leaf_reconstruction_required')
    if (type(max_source_total_mm) not in (int,float) or not math.isfinite(max_source_total_mm)
            or not 0<max_source_total_mm<=160.):
        raise ValueError('finite_explicit_consumer_leaf_source_work_limit_required')
    grouped=ordinary._ids(grouped_track_uuids,'consumer_leaf_grouped_cut',16)
    island=ordinary._ids(island_track_uuids,'consumer_leaf_island_cut',32)
    vias=ordinary._ids(via_uuids,'consumer_leaf_barrel_cut',4)
    retained_vias=ordinary._ids(retained_waypoint_via_uuids,'consumer_leaf_retained_waypoints',2)
    if not grouped or not island or not vias or grouped&island or (grouped|island)&(vias|retained_vias) or vias&retained_vias or len(grouped|island)>32:
        raise ValueError('distinct_nonempty_bounded_consumer_leaf_scopes_required')
    r=rated.plan(board,source,board_hint=board_hint,retired_track_uuids=sorted(island),timeout_s=timeout_s,
        max_source_track_mm=32.,max_retired_tracks=32,max_source_width_mm=1.,
        allow_rated_source_inner_layers=True,use_source_declared_consumer_island=True)
    scope=r['source_declared_consumer_scope']
    if len(scope['root_by_net'])!=1:raise ValueError('one_exact_source_consumer_root_required')
    net,root=next(iter(scope['root_by_net'].items()))
    inventory=consumer.inventory(board,board_hint=board_hint,timeout_s=timeout_s)
    matches=[p for p in inventory['proofs'] if p['root_pad_uuid']==root]
    if not inventory['complete'] or len(matches)!=1:
        raise ValueError('complete_unique_existing_consumer_leaf_required')
    proof=matches[0];live={force._uid(t):t for t in board.GetTracks()}
    groups=[g for g in board.Groups() if g.GetName().startswith(consumer.PREFIX+root+'|')]
    if len(groups)!=1:raise ValueError('one_existing_native_consumer_group_required')
    group=groups[0];members={force._uid(t) for t in group.GetItems()}
    planes={board.GetLayerID(name) for name in fr.plane_layers(board)}
    enabled=set(board.GetEnabledLayers().CuStack())
    if group.GetParentGroup() is not None or not grouped<=members:
        raise ValueError('exact_unnested_source_consumer_group_cut_required')
    for uid in grouped:
        t=live.get(uid)
        if (t is None or t.GetClass()!='PCB_TRACK' or t.GetNetname()!=net
                or t.GetLayer() not in enabled-planes or not group.ContainsItem(t)
                or not 0<t.GetLength()<=32000000 or not 0<t.GetWidth()<=1000000
                or t.GetWidth()<math.ceil(proof['budget']['required_by_layer_mm'][fab.COPPER_LAYER_IDS[t.GetLayer()]]*1e6)):
            raise ValueError('source_group_cut_requires_actual_full_budget_nonplane_tracks')
    if (set(r['contracts'])!={net} or r['contracts'][net]['current_authority']!=proof['budget']['current_authority']
            or scope['aggregate_contracts'][net]['current_authority']!=proof['budget']['aggregate_current_authority']):
        raise ValueError('one_exact_source_consumer_root_and_unchanged_budgets_required')
    _,anchor,via_csv=group.GetName()[len(consumer.PREFIX):].split('|')
    g=dict(source_sha256=force._hash(source),net=net,group_uuid=force._uid(group),source_group_name=group.GetName(),
        source_group_members=sorted(members),root_pad_uuid=root,anchor_uuid=anchor,
        source_via_uuids=sorted(filter(None,via_csv.split(','))),retired_track_uuids=sorted(grouped),source_budget=proof['budget'])
    cut=grouped|island|vias;deadline=time.monotonic()+timeout_s
    source_length_nm=sum(live[u].GetLength() for u in grouped|island)
    if source_length_nm>math.floor(max_source_total_mm*1e6):
        raise ValueError('consumer_leaf_source_length_bound')
    witnesses=[]
    for uid in sorted(vias|retained_vias):
        via=live.get(uid)
        if (via is None or via.GetClass()!='PCB_VIA' or via.GetParentGroup() is not None
                or uid==g['anchor_uuid'] or uid in g['source_via_uuids']
                or uid not in proof['retained_consumer_island_uuids'] or via.GetNetname()!=g['net']
                or via.GetViaType()!=pcbnew.VIATYPE_THROUGH or via.TopLayer()!=pcbnew.F_Cu or via.BottomLayer()!=pcbnew.B_Cu):
            raise ValueError('retired_barrel_must_be_an_ungrouped_exclusive_consumer_waypoint')
        contacts=set()
        for face in board.GetEnabledLayers().CuStack():
            shape=via.GetEffectiveShape(face)
            for fp in board.GetFootprints():
                for pad in fp.Pads():
                    if time.monotonic()>=deadline:raise ValueError('consumer_waypoint_inventory_deadline')
                    if pad.IsOnLayer(face) and shape.Collide(pad.GetEffectiveShape(face),0):
                        raise ValueError('component_contact_barrel_is_not_an_obsolete_waypoint')
            for item in [*board.GetTracks(),*[z for z in board.Zones() if not z.GetIsRuleArea()]]:
                if force._uid(item)==uid or not item.IsOnLayer(face):continue
                other=(item.GetFilledPolysList(face) if item.GetClass()=='ZONE' and item.HasFilledPolysForLayer(face)
                    else item.GetEffectiveShape(face) if item.GetClass()!='ZONE' else None)
                if other is not None and shape.Collide(other,0):
                    key=force._uid(item)
                    if item.GetNetname()!=g['net'] or key not in cut or item.GetClass()!='PCB_TRACK':
                        raise ValueError('waypoint_has_unretired_or_foreign_native_contact')
                    contacts.add(key)
        if len(contacts)<2:raise ValueError('actual_two_sided_route_waypoint_required')
        witnesses.append(dict(via_uuid=uid,track_contact_uuids=sorted(contacts),no_actual_component_contact=True,
            all_native_contacts_inside_exact_source_cut=True,barrel_retired=uid in vias))
    return dict(schema=1,source_sha256=force._hash(source),group_scope=g,island_scope=r,
        net=g['net'],root_pad_uuid=g['root_pad_uuid'],anchor_uuid=g['anchor_uuid'],budget=g['source_budget'],
        grouped_track_uuids=sorted(grouped),island_track_uuids=sorted(island),via_uuids=sorted(vias),
        retained_waypoint_via_uuids=sorted(retained_vias),
        exact_retired_uuids=sorted(cut),waypoint_witnesses=witnesses,
        source_total_length_mm=source_length_nm/1e6,source_total_length_work_ceiling_mm=float(max_source_total_mm),
        full_budget_routing_widths_nm={k:max(math.ceil(v*1e6),board.GetDesignSettings().m_TrackMinWidth)
            for k,v in proof['budget']['required_by_layer_mm'].items()
            if board.GetLayerID(k) in enabled-planes and k in r['contracts'][net]['routing_layers']},
        full_budget_outer_widths_nm={k:max(math.ceil(v*1e6),board.GetDesignSettings().m_TrackMinWidth)
            for k,v in proof['budget']['required_by_layer_mm'].items() if k in ('F.Cu','B.Cu')},
        current_authority_changed=False,release_authority=False)


def subtract(board,scope):
    group_owner.subtract(board,scope['group_scope'])
    ids=set(scope['island_track_uuids'])|set(scope['via_uuids'])
    discard_items(board,[t for t in board.GetTracks() if force._uid(t) in ids])


def assign(board,scope,incoming_track_uuids,incoming_via_uuids=()):
    group_owner.assign(board,scope['group_scope'],incoming_track_uuids,
        sorted(set(incoming_via_uuids)|set(scope['retained_waypoint_via_uuids'])))


def receive(source,candidate,*,board_hint,grouped_track_uuids,island_track_uuids,via_uuids,timeout_s=10.,max_source_total_mm=80.,allow_outer_layer_bridges=False,allow_rated_replacement_inner_layers=False,retained_waypoint_via_uuids=(),allow_rated_layer_bridges=False):
    report=dict(ok=False,complete=False,errors=[],current_authority=False,release_authority=False)
    phase='explicit_scope_validation'
    try:
        if type(allow_outer_layer_bridges) is not bool:
            raise ValueError('explicit_outer_consumer_bridge_mode_required')
        if type(allow_rated_replacement_inner_layers) is not bool:
            raise ValueError('explicit_full_budget_consumer_inner_replacement_mode_required')
        if type(allow_rated_layer_bridges) is not bool or allow_rated_layer_bridges and not allow_rated_replacement_inner_layers:
            raise ValueError('rated_consumer_bridges_require_explicit_full_budget_layer_scope')
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,candidate)]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        phase='independent_source_scope_typing'
        scope=plan(parent,source,board_hint=board_hint,grouped_track_uuids=grouped_track_uuids,
            island_track_uuids=island_track_uuids,via_uuids=via_uuids,timeout_s=timeout_s,max_source_total_mm=max_source_total_mm,
            retained_waypoint_via_uuids=retained_waypoint_via_uuids)
        _,old=additive._nodes(source);_,new=additive._nodes(candidate);cut=set(scope['exact_retired_uuids'])
        incoming=new.keys()-old.keys();live={force._uid(t):t for t in child.GetTracks()}
        if old.keys()-new.keys()!=cut or not 1<=len(incoming)<=128 or not incoming<=live.keys():
            raise ValueError('exact_consumer_leaf_source_cut_and_native_track_delta_required')
        resolver=fr._project_netclass_resolver(str(source));spec=resolver(scope['net']) or {}
        incoming_tracks=set();incoming_vias=set()
        phase='incoming_native_inventory_and_full_face_widths'
        for uid in incoming:
            item=live[uid];name=fab.COPPER_LAYER_IDS.get(int(item.GetLayer()))
            if item.GetClass()=='PCB_VIA' and (allow_outer_layer_bridges or allow_rated_layer_bridges):
                diameter,drill,_=fab.board_legal_through_via_geometry(child,.6,.3)
                if (item.GetNetname()!=scope['net'] or item.GetViaType()!=pcbnew.VIATYPE_THROUGH
                        or item.TopLayer()!=pcbnew.F_Cu or item.BottomLayer()!=pcbnew.B_Cu
                        or not round(diameter*1e6)<=item.GetWidth(item.TopLayer())<=1000000
                        or not round(drill*1e6)<=item.GetDrillValue()<item.GetWidth(item.TopLayer())):
                    raise ValueError('consumer_leaf_bridge_requires_unchanged_factory_through_geometry')
                incoming_vias.add(uid);continue
            widths=scope['full_budget_routing_widths_nm'] if allow_rated_replacement_inner_layers else scope['full_budget_outer_widths_nm']
            required=max(widths.get(name,2000000000),
                math.ceil(float(spec.get('track_width') or .2)*1e6),
                math.ceil(float((spec.get('track_width_by_layer_mm') or {}).get(name) or 0)*1e6))
            if (item.GetClass()!='PCB_TRACK' or item.GetNetname()!=scope['net']
                    or name not in widths or not required<=item.GetWidth()<=1000000
                    or not craft.is_canonical_stroke(tuple(item.GetStart()),tuple(item.GetEnd()),tolerance_nm=0)):
                raise ValueError('consumer_leaf_incoming_must_be_full_budget_authorized_nonplane_tracks')
            incoming_tracks.add(uid)
        if not incoming_tracks or len(incoming_vias)>2:
            raise ValueError('bounded_outer_consumer_track_and_bridge_inventory_required')
        if sum(live[u].GetLength() for u in incoming_tracks)>80000000:
            raise ValueError('consumer_leaf_replacement_length_bound')
        phase='saved_single_tap_consumer_and_budget_retyping'
        saved=consumer.inventory(child,board_hint=board_hint,timeout_s=timeout_s)
        matches=[p for p in saved['proofs'] if p['root_pad_uuid']==scope['root_pad_uuid']]
        if (not saved['complete'] or len(matches)!=1 or matches[0]['budget']!=scope['budget']
                or matches[0]['anchor_uuid']!=scope['anchor_uuid']
                or not incoming_tracks<=set(matches[0]['track_requirements'])
                or not incoming_vias<=set(matches[0]['exact_branch_material_uuids'])):
            raise ValueError('same_saved_consumer_budget_actual_terminals_and_single_tap_required')
        if force._preservation_snapshot(source)[1]!=force._preservation_snapshot(candidate)[1] or force._sidecars(source)!=force._sidecars(candidate):
            raise ValueError('consumer_leaf_parts_interfaces_settings_or_sidecars_changed')
        # An unchanged barrel is not permission to engage a new power face.
        # Re-prove its complete actual contact web whenever new tracks use a
        # face which had no saved source contact. Old/remaining faces grant
        # no new thermal or plated-barrel rating by inheritance.
        phase='actual_barrel_contact_webs'
        old_vias={force._uid(t):t for t in parent.GetTracks() if t.GetClass()=='PCB_VIA' and t.GetNetname()==scope['net']}
        old_material=[*(p for fp in parent.GetFootprints() for p in fp.Pads()),*parent.GetTracks()]
        old_material=[i for i in old_material if i.GetNetname()==scope['net']]
        changed_faces=[]
        contract=dict(net=scope['net'],current_authority=scope['budget']['current_authority'],
            required_by_layer_mm=scope['budget']['required_by_layer_mm'],
            routing_layers=list(scope['budget']['required_by_layer_mm']))
        new_web=[]
        for uid in sorted(incoming_vias):
            checked=supply_web.receive(child,uid,contract,timeout_s=2.)
            faces=set(checked['actual_contact_layers'])
            allowed=set(scope['full_budget_routing_widths_nm']) if allow_rated_layer_bridges else {'F.Cu','B.Cu'}
            if not checked['ok'] or not checked['complete'] or not faces<=allowed or len(faces)<2:
                raise ValueError('new_consumer_barrel_requires_full_actual_authorized_contact_web')
            new_web.append(checked)
        for uid,via in old_vias.items():
            if uid in cut:continue
            engaged={int(live[t].GetLayer()) for t in incoming_tracks
                if via.GetEffectiveShape(live[t].GetLayer()).Collide(live[t].GetEffectiveShape(live[t].GetLayer()),0)}
            new_faces=[face for face in engaged if not any(force._uid(i)!=uid and i.IsOnLayer(face)
                and via.GetEffectiveShape(face).Collide(i.GetEffectiveShape(face),0) for i in old_material)]
            if new_faces:
                checked=supply_web.receive(child,uid,contract,timeout_s=2.)
                if not checked['ok'] or not checked['complete']:
                    raise ValueError('existing_barrel_new_power_face_requires_full_actual_contact_web')
                changed_faces.append(dict(via_uuid=uid,new_contact_faces=new_faces,actual_web_receiving=checked))
        phase='all_original_surviving_native_partitions'
        before=ordinary._partition(parent,time.monotonic()+timeout_s,retired_uuids=cut)
        after=ordinary._partition(child,time.monotonic()+timeout_s,retained_keys=set().union(*before))
        if not all(any(p<=q for q in after) for p in before):
            raise ValueError('consumer_leaf_lost_original_surviving_native_partition')
        with tempfile.TemporaryDirectory(prefix='cec-consumer-leaf-replay-') as tmp:
            phase='source_minus_owned_cut_native_clearance_and_rule_guards'
            path=force._copy_family(source,Path(tmp)/'family');basis=pcbnew.LoadBoard(str(path))
            subtract(basis,scope)
            gap=max(basis.GetDesignSettings().m_MinClearance,math.ceil(float(spec.get('clearance',.2))*1e6));indexes={}
            blocked=rule_areas.areas(basis,'tracks')
            for uid in sorted(incoming_vias):
                via=live[uid]
                if (not fr._via_spot_clear(basis,via.GetPosition(),via.GetWidth(via.TopLayer()),gap,{via.GetNetCode()},
                        drill_nm=via.GetDrillValue(),net_code=via.GetNetCode(),foreign_cache={},native_padstack_via=via)
                        or not fr._edge_leg_clear(basis,via.GetPosition(),via.GetPosition(),(via.GetWidth(via.TopLayer())+1)//2)):
                    raise ValueError('consumer_leaf_original_all_layer_bridge_clearance_refused')
                item=via.Duplicate();item.m_Uuid.Clone(pcbnew.KIID(uid));item.SetNetCode(basis.GetNetcodeFromNetname(scope['net']));basis.Add(item)
            for uid in sorted(incoming_tracks):
                t=live[uid];face=int(t.GetLayer())
                if face not in indexes:indexes[face]=fr._foreign_shape_indexes(basis,face,{t.GetNetCode()})
                shape=pcbnew.SHAPE_SEGMENT(t.GetStart(),t.GetEnd(),t.GetWidth())
                if (not fr._snapshot_foreign_clear(t.GetStart(),t.GetEnd(),t.GetWidth(),gap,*indexes[face])
                        or not fr._edge_leg_clear(basis,t.GetStart(),t.GetEnd(),(t.GetWidth()+1)//2)
                        or any(face in row['layers'] and row['shape'].Collide(shape,0) for row in blocked)):
                    raise ValueError('consumer_leaf_source_minus_cut_native_clearance_or_rule_refused')
            # Keep an empty intermediate group in memory. Saving a temporary
            # empty group may discard its native identity. Import only the
            # independently typed incoming tracks, then reconstruct the exact
            # source group before ONE canonical ground/snapshot replay.
            for uid in sorted(incoming_tracks):
                item=live[uid].Duplicate();item.m_Uuid.Clone(pcbnew.KIID(uid))
                item.SetNetCode(basis.GetNetcodeFromNetname(scope['net']));basis.Add(item)
            phase='exact_native_group_barrel_track_and_ground_replay'
            assign(basis,scope,sorted(incoming_tracks),sorted(incoming_vias))
            additive._ground_refill(basis);field._save_field_snapshot(basis,path)
            _,expected=additive._nodes(path)
            if expected.keys()!=new.keys() or any(syntax._freeze(expected[u])!=syntax._freeze(new[u]) for u in new):
                raise ValueError('consumer_leaf_exact_group_cut_track_additions_and_ground_replay_differs')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in (source,candidate)]:
            raise ValueError('consumer_leaf_source_candidate_or_code_changed')
        report.update(ok=True,complete=True,source_scope=scope,incoming_track_uuids=sorted(incoming_tracks),incoming_via_uuids=sorted(incoming_vias),
            all_actual_terminals_and_surviving_native_partitions_preserved=True,
            same_native_single_trunk_tap_and_current_budgets_reproved=True,
            newly_engaged_existing_barrel_faces=changed_faces,
            retained_source_waypoint_barrels_reclassified=scope['retained_waypoint_via_uuids'],
            new_barrels_added=len(incoming_vias),new_actual_supply_contact_webs=new_web,
            new_barrel_ampacity_credited=False,source_candidate_and_code_unchanged=True,
            independent_full_drc_current_kelvin_field_pair_and_stack_receiving_still_required=True)
    except Exception as exc:
        report['errors'].append(type(exc).__name__+':'+str(exc));report['failure_stage']=phase;report['traceback']=traceback.format_exc()
    return report
