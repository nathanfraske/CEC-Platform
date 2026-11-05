"""Exact ordinary two-terminal RC lead reconstruction and owned return pose.

The legacy additive-pose receiver is intentionally unchanged. This separate
tier owns only an explicitly selected COMPLETE ordinary two-terminal planar
lead and the independently rediscovered RC support/contained ground return.
Power, pairs, sensing, source barrels, pours, package and current changes are
never authorized. Saved receiving grants neither routing nor fab release.
An explicit replacement-only option may use Source-declared signal faces
with an adjacent Ground reference; the original cut remains outer-face only.
"""
import math,time,tempfile
from collections import Counter
from pathlib import Path
import pcbnew
import cec_ordinary_rc_pose as rc
import cec_ordinary_route_receiving as ordinary
import cec_force_current as force
import cec_additive_route_receiving as additive
import cec_copper_echo as sexpr
import cec_field_coupling as field
import cec_board_geometry as geometry
import cec_fab_profile as fab
import cec_fr as fr
import cec_route_quality as quality
import cec_support_field_reflow as reflow
from cec_native_items import discard_items


def _budget(seconds):
    if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<seconds<=10:
        raise ValueError('bounded_ordinary_RC_reconstruction_required')
    return time.monotonic()+seconds


def additional_path_mm(value):
    """Explicit finite search/reconstruction extent, never a width waiver."""
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=32:
        raise ValueError('bounded_explicit_ordinary_RC_additional_path_extent_required')
    return float(value)


def _replacement_faces(board,source,net,floor,allow_signal_inner):
    """Source-only layer/floor policy, never a candidate's asserted stack."""
    result={int(pcbnew.F_Cu):floor,int(pcbnew.B_Cu):floor}
    if not allow_signal_inner:return result
    profile=fab.board_profile_name(board)
    if not profile or not fab.get_profile(profile):
        raise ValueError('explicit_source_stack_required_for_RC_signal_inner_faces')
    legal=set(fab.routing_layers(board,include_power=False)) & set(fab.referenced_signal_layers(board))
    spec=fr._project_netclass_resolver(str(source),board=board)(net) or {}
    widths=spec.get('track_width_by_layer_mm')
    if widths is None:widths={}
    if type(widths) is not dict:raise ValueError('source_RC_per_face_width_map_required')
    result={}
    for name in sorted(legal):
        lid=int(board.GetLayerID(name))
        if lid not in board.GetEnabledLayers().CuStack():continue
        values=[widths[key] for key in {name,board.GetLayerName(lid)} if key in widths]
        if any(type(value) not in (int,float) or not math.isfinite(value) or value<=0 for value in values):
            raise ValueError('positive_source_RC_per_face_width_required')
        result[lid]=max([floor]+[math.ceil(value*1e6) for value in values])
    if not result:raise ValueError('source_ground_referenced_RC_signal_faces_required')
    return result


def plan(board,source,*,via_uuid,board_hint,retired_track_uuids,timeout_s=10.,max_additional_path_mm=16.,
         allow_locked_track_uuids=()):
    deadline=_budget(timeout_s)
    extension=additional_path_mm(max_additional_path_mm)
    scope=rc.plan(board,source,via_uuid,hint=board_hint)
    selected=ordinary._ids(retired_track_uuids,'complete_ordinary_RC_lead',16)
    unlocked=ordinary._ids(allow_locked_track_uuids,'explicit_locked_complete_ordinary_RC_lead',16)
    if not unlocked<=selected:raise ValueError('locked_RC_scope_must_be_inside_the_exact_complete_ordinary_lead')
    if not selected:raise ValueError('nonempty_exact_complete_RC_lead_required')
    native=[t for t in board.GetTracks() if t.GetNetname()==scope['net']]
    if (selected!={force._uid(t) for t in native}
            or any(t.GetClass()!='PCB_TRACK' or t.GetParentGroup() is not None or t.IsLocked() and force._uid(t) not in unlocked
                or not 0<t.GetLength()<=16000000 for t in native)
            or sum(t.GetLength() for t in native)>32000000
            or len({int(t.GetLayer()) for t in native})!=1):
        raise ValueError('entire_unprotected_two_terminal_planar_RC_lead_required')
    lid=int(native[0].GetLayer())
    if lid not in (pcbnew.F_Cu,pcbnew.B_Cu):
        raise ValueError('source_RC_lead_actual_outer_component_face_required')
    pads={force._uid(p):p for f in board.GetFootprints() for p in f.Pads()}
    endpoints=[pads[u] for u in (scope['owner_pad_uuid'],scope['supply_pad_uuid'])]
    spec=fr._project_netclass_resolver(str(source))(scope['net']) or {}
    floor=max(board.GetDesignSettings().m_TrackMinWidth,math.ceil((spec.get('track_width') or .2)*1e6))
    if any(not floor<=t.GetWidth()<=350000 for t in native):
        raise ValueError('source_class_full_width_ordinary_RC_lead_required')
    degree=Counter(tuple(at) for t in native for at in (t.GetStart(),t.GetEnd()))
    tips=[at for at,n in degree.items() if n==1]
    if len(tips)!=2 or any(n not in (1,2) for n in degree.values()):
        raise ValueError('source_RC_lead_single_unbranched_chain_required')
    # A source pad may capture the end cap rather than the track centre.
    # Both tips must contact distinct actual lands; there is no centre/bbox
    # inference and no source connector or barrel shortcut.
    contacts=[]
    for at in tips:
        marker=pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*at),pcbnew.VECTOR2I(*at),
            max(t.GetWidth() for t in native if at in (tuple(t.GetStart()),tuple(t.GetEnd()))))
        owners=[force._uid(p) for p in endpoints if p.IsOnLayer(lid)
            and p.GetEffectiveShape(lid).Collide(marker,0)]
        if len(owners)!=1:raise ValueError('source_RC_lead_actual_distinct_end_contacts_required')
        contacts.extend(owners)
    if set(contacts)!={force._uid(p) for p in endpoints}:
        raise ValueError('source_RC_lead_actual_distinct_end_contacts_required')
    conn=pcbnew.CONNECTIVITY_DATA()
    for item in [*native,*endpoints]:
        if time.monotonic()>=deadline:raise ValueError('source_RC_lead_inventory_deadline')
        if not conn.Add(item):raise ValueError('source_RC_lead_native_item_refused')
    reachable={force._uid(endpoints[0])}|{force._uid(i) for i in conn.GetConnectedItems(endpoints[0])}
    if not selected|{force._uid(p) for p in endpoints}<=reachable:
        raise ValueError('source_RC_lead_contains_detached_or_cyclic_material')
    return dict(schema=1,scope='exact_complete_ordinary_RC_lead_and_owned_return',
        source_sha256=force._hash(source),RC_scope=scope,retired_track_uuids=sorted(selected),
        allow_locked_track_uuids=sorted(unlocked),
        source_length_nm=sum(t.GetLength() for t in native),class_floor_nm=floor,
        max_additional_path_mm=extension,
        source_component_face=lid,source_current_or_barrel_capacity_credited=False,
        routing_admitted=False,release_authority=False)


def receive(source,candidate,*,via_uuid,board_hint,retired_track_uuids,timeout_s=10.,max_additional_path_mm=16.,
            reflow_neighbor_fields=False,allow_locked_track_uuids=(),allow_source_signal_inner_layers=False):
    report=dict(schema=1,scope='independent_complete_ordinary_RC_lead_and_return_pose',
        ok=False,complete=False,errors=[],routing_admitted=False,current_qualified=False,
        placement_qualified=False,release_authority=False)
    try:
        deadline=_budget(timeout_s)
        if type(reflow_neighbor_fields) is not bool:
            raise ValueError('explicit_native_RC_neighbor_field_reflow_mode_required')
        if type(allow_source_signal_inner_layers) is not bool:
            raise ValueError('explicit_source_RC_signal_inner_permission_required')
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        if source==candidate:raise ValueError('distinct_saved_ordinary_RC_construction_required')
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,candidate)]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        proposal=plan(parent,source,via_uuid=via_uuid,board_hint=board_hint,
            retired_track_uuids=retired_track_uuids,timeout_s=timeout_s,max_additional_path_mm=max_additional_path_mm,
            allow_locked_track_uuids=allow_locked_track_uuids)
        scope=proposal['RC_scope'];retired=set(proposal['retired_track_uuids'])
        replacement_faces=_replacement_faces(parent,source,scope['net'],
            proposal['class_floor_nm'],allow_source_signal_inner_layers)
        if geometry.outline_bbox_mm(parent)!=geometry.outline_bbox_mm(child):
            raise ValueError('ordinary_RC_reconstruction_outline_changed')
        caps=[f for f in child.GetFootprints() if force._uid(f)==scope['footprint_uuid']]
        if len(caps)!=1:raise ValueError('saved_source_owned_RC_missing')
        cap=caps[0]
        if [*list(cap.GetPosition()),cap.GetOrientationDegrees()]==[*scope['source_pose_nm'],scope['source_orientation']]:
            raise ValueError('nonempty_source_owned_RC_pose_required')
        before=ordinary._partition(parent,deadline,retired_uuids=retired)
        moved=[p for f in parent.GetFootprints() if force._uid(f)==scope['footprint_uuid'] for p in f.Pads()]
        moved.append(next(t for t in parent.GetTracks() if force._uid(t)==via_uuid))
        source_keys={force._uid(i):force._item_key(i) for i in moved}
        discard_items(parent,[t for t in parent.GetTracks() if force._uid(t) in retired])
        cap,via,_,_=rc.pose(parent,scope,list(cap.GetPosition()),cap.GetOrientationDegrees())
        report['source_pose_preflight']=rc.preflight(parent,scope)
        bindings={force._item_key(i):source_keys[force._uid(i)] for i in [*cap.Pads(),via]}
        report['candidate_pose_preflight']=rc.preflight(child,scope)
        _,old=additive._nodes(source);_,new=additive._nodes(candidate)
        if old.keys()-new.keys()!=retired:
            raise ValueError('saved_RC_retirement_differs_from_complete_source_lead')
        incoming=new.keys()-old.keys()
        items=[t for t in child.GetTracks() if force._uid(t) in incoming]
        if not 1<=len(items)<=64 or {force._uid(t) for t in items}!=incoming:
            raise ValueError('bounded_ordinary_RC_tracks_and_standard_vias_only')
        tracks=[t for t in items if t.GetClass()=='PCB_TRACK'];vias=[t for t in items if t.GetClass()=='PCB_VIA']
        if not tracks or len(vias)>2 or len(tracks)+len(vias)!=len(items):
            raise ValueError('bounded_ordinary_RC_two_transition_lead_required')
        if any(t.GetNetname()!=scope['net'] for t in items):
            raise ValueError('only_independently_ordinary_RC_net_may_be_rebuilt')
        if (any(int(t.GetLayer()) not in replacement_faces
                or not replacement_faces.get(int(t.GetLayer()),350001)<=t.GetWidth()<=350000 for t in tracks)
                or sum(t.GetLength() for t in tracks)>min(24000000,
                    proposal['source_length_nm']+proposal['max_additional_path_mm']*1e6)):
            raise ValueError('bounded_full_class_ordinary_RC_replacement_tracks_required')
        required_d,required_h,_=fab.board_legal_through_via_geometry(child,.6,.3)
        settings=child.GetDesignSettings();spec=fr._project_netclass_resolver(str(source))(scope['net']) or {}
        gap=max(200000,settings.m_MinClearance,math.ceil((spec.get('clearance') or .2)*1e6))
        for v in vias:
            d,h=v.GetWidth(v.TopLayer()),v.GetDrillValue()
            if (v.GetViaType()!=pcbnew.VIATYPE_THROUGH or v.TopLayer()!=pcbnew.F_Cu or v.BottomLayer()!=pcbnew.B_Cu
                    or not math.ceil(required_d*1e6)<=d<=1000000
                    or not math.ceil(required_h*1e6)<=h<=500000
                    or d<settings.m_ViasMinSize or h<settings.m_MinThroughDrill
                    or d-h<2*settings.m_ViasMinAnnularWidth):
                raise ValueError('ordinary_RC_new_transition_below_absolute_standard_via_rules')
            detail={}
            if not fr._via_spot_clear(child,v.GetPosition(),d,gap,{v.GetNetCode()},drill_nm=h,
                    net_code=v.GetNetCode(),foreign_cache={},report=detail,existing_via_uuid=force._uid(v)):
                raise ValueError('ordinary_RC_new_transition_native_all_layer_refused:'+str(detail))
        craft=quality.analyze_board(child,track_uuid_scope={force._uid(t) for t in tracks})
        if not craft['geometry_ok'] or not craft['craft_ok']:
            raise ValueError('ordinary_RC_replacement_canonical_craft_refused')
        report['incoming_craft']=craft
        field_owners=set()
        if reflow_neighbor_fields:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise ValueError('ordinary_RC_saved_field_receiving_deadline')
            # Rediscover the collision cohort on SOURCE-reconstructed pads.
            # Never accept caller-selected neighboring owners, hide/resize a
            # label, or copy a candidate footprint's unrelated properties.
            layout=reflow.construct_collision_cohort(parent,[scope['footprint_uuid']],
                timeout_s=min(10.,remaining),include_changed_owners=True)
            report['source_native_field_collision_cohort']=layout
            if layout.get('ok') is not True:
                raise ValueError('ordinary_RC_native_neighbor_field_reflow_refused')
            field_owners=set(layout['reflowed_footprint_uuids'])
        with tempfile.TemporaryDirectory(prefix='cec-exact-ordinary-RC-reconstruction-') as work:
            projected=force._copy_family(source,Path(work)/'projected')
            additive._ground_refill(parent);field._save_field_snapshot(parent,projected)
            _,expected=additive._nodes(projected)
            allowed={scope['footprint_uuid'],via_uuid}|field_owners|{force._uid(z) for z in parent.Zones()
                if not z.GetIsRuleArea() and z.GetNetname()=='GND'}
            if (expected.keys()!=old.keys()-retired or any(sexpr._freeze(expected[u])!=sexpr._freeze(old[u])
                    for u in expected if u not in allowed)):
                raise ValueError('ordinary_RC_projection_changed_unowned_source_material')
            remaining=deadline-time.monotonic()
            if remaining<=0:raise ValueError('ordinary_RC_saved_receiving_deadline')
            replay=additive.receive(projected,candidate,timeout_s=min(10.,remaining),board_hint=board_hint)
            report['exact_native_source_pose_cut_plus_additions']=replay
            if not replay['ok'] or not replay['complete']:
                raise ValueError('saved_ordinary_RC_source_reconstruction_refused:'+str(replay['errors']))
        keys=set().union(*before)
        after=ordinary._partition(child,deadline,retained_keys=keys,_identity_rebindings=bindings)
        if any(not any(p<=q for q in after) for p in before):
            raise ValueError('ordinary_RC_reconstruction_original_partition_lost')
        if (time.monotonic()>=deadline or epoch!=force._code_identity()
                or families!=[force._family(p,board_hint) for p in (source,candidate)]):
            raise ValueError('ordinary_RC_source_candidate_or_epoch_changed')
        report.update(ok=True,complete=True,source_proposal=proposal,
            source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            actual_owned_ground_barrel_geometry_preserved=True,
            all_surviving_source_native_partitions_preserved=True,
            exact_unowned_source_nodes_preserved=True,new_standard_transition_count=len(vias),
            reflowed_native_field_owner_uuids=sorted(field_owners),
            source_derived_replacement_layer_floors_nm={str(k):v for k,v in sorted(replacement_faces.items())},
            source_signal_inner_layers_explicit=allow_source_signal_inner_layers,
            complete_source_ordinary_lead_retired=True,source_candidate_and_code_unchanged=True,
            full_native_DRC_field_current_pair_and_matched_stack_receiving_required=True)
    except Exception as exc:report['errors'].append(type(exc).__name__+':'+str(exc))
    return report
