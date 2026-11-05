"""Explicit small foreign-lead reconstruction at a real future native cell.

This grants no generic power/Ground cut. Each bounded ungrouped Source edge
needs an ordinary-net role or unchanged full-current Source contract. Each
same-net native cut component must actually obstruct a moving Source land or
owned barrel. All literal surviving component ports are restored separately
by the macro compiler and independently re-received from the saved board.
"""
import math
import time

import pcbnew
import cec_force_current as force
import cec_fr as fr
import cec_full_current_planar_reflow as full
import cec_ordinary_route_receiving as ordinary


def ownership(parent,private,source,proposal,track_uuids,*,excluded_uuids=(),
              transported_barrel_uuids=(),allow_locked=False,deadline,max_source_track_mm=8.,max_tracks=8,
              required_ground_pad_entries=(),required_supply_departures=(),allow_full_width_supply_obstacles=False,
              required_new_ground_dogbones=(),required_measurement_corridors=(),existing_ground_cut_rows=()):
    # Normal portfolios keep their original 1..16 extent. A caller may
    # explicitly choose one larger 32-edge work tier for a complete cell;
    # individual widths, 96-mm total work, ownership and all receivers stay.
    if type(max_tracks) is not int or not (1<=max_tracks<=16 or max_tracks==32):
        raise ValueError('bounded_explicit_source_obstacle_track_count_required')
    ids=ordinary._ids(track_uuids,'additional_source_native_obstacle_cut',max_tracks)
    if type(allow_locked) is not bool:raise ValueError('explicit_locked_obstacle_scope_required')
    if type(allow_full_width_supply_obstacles) is not bool:
        raise ValueError('explicit_full_width_supply_obstacle_scope_required')
    import cec_macro_measurement_corridor as corridor
    required_measurement_corridors=corridor.requests(required_measurement_corridors)
    if (type(max_source_track_mm) not in (int,float) or not math.isfinite(max_source_track_mm)
            or not 0<max_source_track_mm<=32.):
        raise ValueError('bounded_explicit_source_obstacle_work_extent_required')
    if not ids:return []
    def tick():
        if time.monotonic()>=deadline:raise ValueError('source_native_obstacle_cut_deadline')
    tracks={force._uid(t):t for t in parent.GetTracks()}
    if not ids<=tracks.keys() or ids&set(excluded_uuids):
        raise ValueError('additional_obstacle_cut_stale_or_already_owned')
    originals={fp.GetReference():fp for fp in parent.GetFootprints()}
    posed={fp.GetReference():fp for fp in private.GetFootprints()}
    moving=[]
    for ref in proposal['poses']:
        tick();a,b=originals[ref],posed[ref]
        if (tuple(a.GetPosition())!=tuple(b.GetPosition())
                or abs((a.GetOrientationDegrees()-b.GetOrientationDegrees()+180)%360-180)>1e-9):
            moving.extend(b.Pads())
    carried=set(transported_barrel_uuids)
    moving.extend(t for t in private.GetTracks() if force._uid(t) in carried)
    projected_ground={}
    if required_ground_pad_entries:
        import cec_macro_ground_ingress as ingress
        proofs,columns=ingress.plan(parent,private,proposal,required_ground_pad_entries,
            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        moving.extend(columns)
        projected_ground={q['proposal_column_uuid']:q for q in proofs}
    projected_supply={}
    new_ground={}
    critical={}
    if required_measurement_corridors:
        proofs,strokes=corridor.plan(parent,private,proposal,required_measurement_corridors,
            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        moving.extend(strokes)
        critical={uid:q for q in proofs for uid in q['proposal_track_uuids']}
    if required_new_ground_dogbones:
        import cec_macro_new_ground_dogbone as dogbone
        proofs,columns=dogbone.plan(parent,private,proposal,required_new_ground_dogbones,
            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        moving.extend(columns)
        new_ground={q['proposal_column_uuid']:q for q in proofs}
    if required_supply_departures:
        import cec_macro_supply_departure as departure
        proofs,columns=departure.plan(parent,private,proposal,required_supply_departures,
            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        moving.extend(columns)
        projected_supply={q['proposal_column_uuid']:q for q in proofs}
    if not moving:raise ValueError('actual_moving_native_obstacle_owner_required')
    eligible=ordinary.eligible_nets(parent,source,proposal['board_hint'])
    local=fr._foreign_clearance_resolver(parent)
    minimum=int(parent.GetDesignSettings().m_MinClearance)
    # Ground is NOT an ordinary/full-current obstacle alias. Only the
    # separate Source-selected low-power continuation owner may acquire
    # these explicit short edges; its existing roots stay in the SAME
    # complete native cut component and all surviving ports remain due.
    ground_ids={u for u in ids if tracks[u].GetNetname()=='GND'}
    ground_rows=[]
    if ground_ids:
        import cec_source_ground_continuation as continuation
        ground_rows=continuation.ownership(parent,private,source,proposal,sorted(ground_ids),
            existing_ground_cut_rows=existing_ground_cut_rows,deadline=deadline,
            max_source_track_mm=max_source_track_mm,max_tracks=min(8,max_tracks))
    rows={};graph=pcbnew.CONNECTIVITY_DATA();length=sum(tracks[u].GetLength()for u in ground_ids)
    if length>96000000:raise ValueError('bounded_total_source_obstacle_work_extent_required')
    for uid in sorted(ids-ground_ids):
        tick();edge=tracks[uid]
        if (edge.GetClass()!='PCB_TRACK' or edge.GetParentGroup() is not None or edge.HasSolderMask()
                or edge.GetNetname()=='GND' or edge.IsLocked() and not allow_locked
                or not 0<edge.GetWidth()<=10000000
                or edge.GetWidth()>350000 and not allow_full_width_supply_obstacles
                or not 0<edge.GetLength()<=round(max_source_track_mm*1e6)):
            raise ValueError('bounded_ungrouped_non_ground_source_obstacle_edge_required:'+uid)
        length+=edge.GetLength()
        if length>96000000:raise ValueError('bounded_total_source_obstacle_work_extent_required')
        if edge.GetWidth()<=350000 and edge.GetNetname() in eligible:
            authority=dict(kind='positive_source_ordinary',native_source_uuid=uid)
        else:
            plan=full.plan(parent,source,board_hint=proposal['board_hint'],retired_track_uuids=[uid],
                timeout_s=min(10.,max(.001,deadline-time.monotonic())),
                max_source_track_mm=max_source_track_mm)
            if edge.GetWidth()>350000:
                # This opt-in is only for an already budgeted distributed
                # supply, not aggregate force/collector relocation. Width or
                # ordinary-net eligibility cannot supply current authority.
                if plan['current_domain_kind']!='explicit_all_terminal_distributed_supply':
                    raise ValueError('positive_distributed_supply_only_for_full_width_obstacle:'+uid)
            authority=dict(kind='unchanged_full_current_source_edge',native_source_uuid=uid,source_plan=plan)
            if edge.GetWidth()>350000:
                authority['explicit_full_width_distributed_supply_reconstruction']=True
        rows[uid]=dict(change=dict(uuid=uid,net=str(edge.GetNetname()),
            source_nm=[list(edge.GetStart()),list(edge.GetEnd())],
            explicit_future_native_obstacle_reconstruction=True),authority=authority)
        if not graph.Add(edge):raise ValueError('native_obstacle_cut_graph_member_refused')
    pending=set(ids-ground_ids)
    while pending:
        tick();root=min(pending);edge=tracks[root]
        group=(set(force._uid(t) for t in graph.GetConnectedItems(edge))|{root})&pending
        if not group:raise ValueError('empty_native_obstacle_cut_component')
        if any(tracks[u].GetNetname()!=edge.GetNetname() or tracks[u].GetLayer()!=edge.GetLayer() for u in group):
            raise ValueError('one_source_native_obstacle_net_face_per_component_required')
        pending-=group;contacts=[]
        for uid in sorted(group):
            t=tracks[uid];face=int(t.GetLayer())
            for land in moving:
                tick()
                if (land.GetNetCode()==t.GetNetCode() or not land.IsOnLayer(face)):
                    continue
                gap=max(minimum,int(local(t,face)),int(local(land,face)))
                if t.GetEffectiveShape(face).Collide(land.GetEffectiveShape(face),gap):
                    contacts.append(dict(source_track_uuid=uid,future_native_uuid=force._uid(land),
                        layer_id=face,required_clearance_nm=gap))
                    if force._uid(land) in projected_ground:
                        contacts[-1]['mandatory_projected_ground_entry']=projected_ground[force._uid(land)]
                    if force._uid(land) in projected_supply:
                        contacts[-1]['mandatory_source_supply_departure']=projected_supply[force._uid(land)]
                    if force._uid(land) in new_ground:
                        contacts[-1]['mandatory_new_ground_dogbone']=new_ground[force._uid(land)]
                    if force._uid(land) in critical:
                        contacts[-1]['mandatory_source_measurement_corridor']=critical[force._uid(land)]
        if not contacts:
            raise ValueError('additional_cut_component_does_not_block_actual_future_native_copper:'+','.join(sorted(group)))
        proof=dict(component_source_track_uuids=sorted(group),literal_foreign_native_conflicts=contacts,
            unchanged_native_width_and_complete_source_contract_required=True,
            every_surviving_component_contact_requires_independent_saved_reconstruction=True)
        for uid in group:rows[uid]['source_native_obstacle_ownership']=proof
    tick()
    return sorted([*ground_rows,*rows.values()],key=lambda q:q['change']['uuid'])
