"""Bounded source-typed supply cuts with explicit cross-layer route hints.

This is PRIVATE construction, never receiving or automatic retirement authority.
Every face retains the original complete load and its own physical width floor.
No aggregate power bus, inferred branch load, plane pickup or I/N split is
authorized. Exact saved-source receiving and all final gates remain mandatory.
"""
import math,time
from pathlib import Path
from contextlib import ExitStack
import pcbnew
import cec_force_current as force
import cec_fr as fr
import cec_fab_profile as fab
import cec_rated_branch_repair as rated
import cec_native_component_ports as ports
import cec_native_route_portal as portal
import cec_native_current_capture as capture
import cec_route_quality as quality
import cec_field_coupling as field
from cec_native_items import discard_items


class Refused(ValueError):
    """A bounded construction refusal with structured, non-authoritative telemetry."""
    def __init__(self,message,diagnostics):
        super().__init__(message);self.diagnostics=diagnostics


def _compact_incoming_seams(board,source,net,incoming,*,board_hint,frozen_source_pours):
    """Geometry-only, new strokes only; never use a Source corner waiver.

    Independently routed waypoint legs can meet with an acute reversal.
    Reuse the existing native contact-preserving shortcut constructor on
    disjoint pairs made by THIS private construction only. The saved rated
    receiver still owns all original cuts, widths and current obligations.
    """
    import cec_scalar_corner_stage as corners
    protected={k:v for k,v in field._field_snapshot_inventory(board).items()
        if k[0]!='track'or k[1]not in incoming}
    owned=set(incoming);records=[];deadline=time.monotonic()+9.5
    with ExitStack()as leases:
        if frozen_source_pours:
            import cec_native_frozen_zone_access as frozen
            leases.enter_context(frozen.frozen(board,source,timeout_s=10.))
        for _ in range(4):
            if time.monotonic()>=deadline:break
            inventory=corners.inventory(board,{net},geometry_policy='acute_shortcut')
            requests=[r for r in inventory['selected']if set(r['source_track_uuids'])<=owned][:16]
            if not requests:break
            result=corners.construct(board,requests,{net},allow_locked_source=True,
                geometry_policy='acute_shortcut',timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            retired=set(result['retired_track_uuids']);added=set(result['incoming_source_owners'])
            if (not retired<=owned or any(not set(v)<=owned for v in result['incoming_source_owners'].values())):
                raise ValueError('chain_seam_compaction_touched_unowned_source')
            owned=(owned-retired)|added;records.append(result)
            if not result['chamfered']:break
        actual=field._field_snapshot_inventory(board)
        if any(actual.get(k)!=v for k,v in protected.items())or {
                k for k in actual if k[0]!='track'or k[1]not in owned}!=set(protected):
            raise ValueError('chain_seam_compaction_changed_retained_native_material')
        with force._thermal_hint(board_hint):
            guard=capture.Guard(pcbnew.LoadBoard(str(source)),source,net=net,
                board_hint=board_hint,timeout_s=10.)
        for track in board.GetTracks():
            if force._uid(track)in owned and not guard(tuple(track.GetStart()),tuple(track.GetEnd()),
                    track.GetWidth(),int(track.GetLayer())):
                raise ValueError('chain_seam_compaction_source_current_guard_refused')
    return sorted(owned),dict(scope='newly_constructed_contact_preserving_waypoint_seams_only',
        records=records,retained_native_material_unchanged=True,source_current_guard_rechecked=True,
        source_track_retirement_authority=False,release_authority=False)


def construct(source, *, board_hint, retired_track_uuids, stages,
              max_source_width_mm=.35,max_source_track_mm=8.,
              max_retired_tracks=8,max_replacement_width_mm=.35,
              frozen_source_pours=False,all_layer_failure_diagnostics=False,
              native_board_envelope=False,future_poses=None,
              use_source_declared_consumer_island=False,
              allow_rated_source_inner_layers=False,repair_undersized_source=False,
              compact_new_waypoint_seams=False):
    """Return a new in-memory board only after every full-width leg is found.

    ``stages`` supplies 1..8 face/waypoint hints, not legal routes. All shared
    coordinates must be exact integers; each search lease is <=10 seconds.
    New source-safe plated barrels are derived from actual face changes only.
    Failures leave the saved source and caller's native board untouched. The
    opt-in native envelope searches the real board extent on each explicitly
    requested face under the SAME lease, not a fixed local window. It permits
    no additional face or barrel and keeps the exact full-source width.
    Explicit undersized-source repair requires the existing complete native
    current-fault proof. It does not grandfather the old width: every new
    face still carries the full unchanged source load.
    """
    if (not isinstance(stages,(list,tuple)) or not 1<=len(stages)<=8
            or type(frozen_source_pours) is not bool
            or type(all_layer_failure_diagnostics) is not bool
            or type(native_board_envelope) is not bool
            or type(use_source_declared_consumer_island) is not bool
            or type(allow_rated_source_inner_layers) is not bool
            or type(repair_undersized_source) is not bool
            or type(compact_new_waypoint_seams) is not bool
            or future_poses is not None and type(future_poses) is not dict):
        raise ValueError('bounded_explicit_rated_layer_chain_required')
    parsed=[];point_count=0
    for row in stages:
        if not isinstance(row,dict) or set(row)!={'layer','points_nm'}:
            raise ValueError('exact_layer_chain_face_and_waypoints_required')
        points=row['points_nm'];name=row['layer']
        if (type(name) is not str or not isinstance(points,(list,tuple))
                or not 2<=len(points)<=8 or any(not isinstance(p,(list,tuple)) or len(p)!=2
                    or any(type(v) is not int or abs(v)>2000000000 for v in p) for p in points)
                or any(tuple(a)==tuple(z) for a,z in zip(points,points[1:]))):
            raise ValueError('bounded_integer_layer_chain_waypoints_required')
        point_count+=len(points)
        if point_count>32:raise ValueError('rated_layer_chain_waypoint_inventory_bound')
        parsed.append((name,[tuple(p) for p in points]))
    if any(a[-1]!=z[0] for (_,a),(_,z) in zip(parsed,parsed[1:])):
        raise ValueError('layer_chain_exact_shared_portal_required')
    rated.replacement_width_mm(max_replacement_width_mm,allow_rated_layer_bridges=True)
    source=Path(source).resolve();epoch=force._code_identity();family=force._family(source,board_hint)
    b=pcbnew.LoadBoard(str(source))
    proposal=rated.plan(b,source,board_hint=board_hint,retired_track_uuids=retired_track_uuids,
        max_source_width_mm=max_source_width_mm,max_source_track_mm=max_source_track_mm,
        max_retired_tracks=max_retired_tracks,timeout_s=10.,
        use_source_declared_consumer_island=use_source_declared_consumer_island,
        allow_rated_source_inner_layers=allow_rated_source_inner_layers,
        repair_undersized_source=repair_undersized_source)
    if len(proposal['contracts'])!=1 or len(proposal['source_boundaries'])!=1:
        raise ValueError('one_explicit_source_supply_cut_required')
    net,contract=next(iter(proposal['contracts'].items()));boundary=proposal['source_boundaries'][0]
    code=b.GetNetcodeFromNetname(net);faces=[];widths={}
    # Source boundary receiving owns the actual retired conductor width,
    # even when it exceeds the physical catalog minimum. Preserve that width
    # throughout the replacement instead of creating a new thin landing.
    cut_ids=set(proposal['retired_track_uuids'])
    retained_source_width=max(t.GetWidth() for t in b.GetTracks() if force._uid(t) in cut_ids)
    spec=fr._project_netclass_resolver(str(source))(net) or {}
    for name,_ in parsed:
        layer=b.GetLayerID(name);canonical=fab.COPPER_LAYER_IDS.get(layer)
        if (layer not in b.GetEnabledLayers().CuStack() or canonical not in contract['routing_layers']
                or layer in {b.GetLayerID(n) for n in fr.plane_layers(b)}):
            raise ValueError('actual_source_authorized_nonplane_chain_face_required')
        width=max(math.ceil(contract['required_by_layer_mm'][canonical]*1e6),
            retained_source_width,
            math.ceil(float(spec.get('track_width') or .2)*1e6),
            math.ceil(float((spec.get('track_width_by_layer_mm') or {}).get(canonical) or 0)*1e6),
            math.ceil(float((spec.get('track_width_by_layer_mm') or {}).get(b.GetLayerName(layer)) or 0)*1e6),
            b.GetDesignSettings().m_TrackMinWidth)
        if width>math.floor(max_replacement_width_mm*1e6):
            raise ValueError('rated_chain_face_width_exceeds_explicit_ceiling')
        widths[layer]=width;faces.append(layer)
    cuts=set(proposal['retired_track_uuids'])
    discard_items(b,[t for t in b.GetTracks() if force._uid(t) in cuts])
    groups=ports.boundary_components(b,net,b.GetLayerID(boundary['layer']),boundary['anchors_nm'],
        deadline=time.monotonic()+10.)
    if (len(groups)!=2 or not any(parsed[0][1][0] in map(tuple,g['source_anchors_nm'])
            and parsed[-1][1][-1] in map(tuple,z['source_anchors_nm'])
            for g in groups for z in groups if g is not z)):
        raise ValueError('chain_must_restore_both_exact_retained_source_components')
    gap=max(math.ceil(contract['clearance_mm']*1e6),b.GetDesignSettings().m_MinClearance)
    diameter,drill,_=fab.board_legal_through_via_geometry(b,
        max(.6,float(spec.get('via_diameter') or .6)),max(.3,float(spec.get('via_drill') or .3)))
    diameter_nm=max(round(diameter*1e6),round(drill*1e6)+max(widths.values()))
    drill_nm=round(drill*1e6);new_vias=[];new_tracks=[];legs_report=[]
    needs=[]
    if faces[0] not in portal.endpoint_layers(b,parsed[0][1][0],code):needs.append(parsed[0][1][0])
    for (old,(_,p)),(new,(_,q)) in zip(zip(faces,parsed),zip(faces[1:],parsed[1:])):
        if old!=new and not {old,new}<=portal.endpoint_layers(b,p[-1],code):needs.append(p[-1])
    if faces[-1] not in portal.endpoint_layers(b,parsed[-1][1][-1],code):needs.append(parsed[-1][1][-1])
    needs=list(dict.fromkeys(needs))
    if len(needs)>4:raise ValueError('rated_chain_derived_barrel_count_bound')
    with ExitStack() as leases:
        future_land_plan=None
        if frozen_source_pours:
            import cec_native_frozen_zone_access as frozen
            leases.enter_context(frozen.frozen(b,source,timeout_s=10.))
        if future_poses is not None:
            import cec_native_pose_reservations as reservation
            future_land_plan=leases.enter_context(reservation.reserve(b,future_poses,net,timeout_s=10.))
        with force._thermal_hint(board_hint):
            guard=capture.Guard(b,source,net=net,board_hint=board_hint,timeout_s=10.)
        for point in needs:
            at=pcbnew.VECTOR2I(*point)
            detail={}
            native_clear=fr._via_spot_clear(b,at,diameter_nm,gap,{code},drill_nm=drill_nm,
                net_code=code,foreign_cache={},report=detail)
            edge_clear=fr._edge_leg_clear(b,at,at,(diameter_nm+1)//2)
            refused_faces=[int(l) for l in b.GetEnabledLayers().CuStack()
                if not guard(point,point,diameter_nm,int(l))]
            if not native_clear or not edge_clear or refused_faces:
                stack_report=None
                if all_layer_failure_diagnostics:
                    import cec_native_barrel_blockers as blockers
                    stack_report=blockers.inventory(b,code,point,
                        diameter_nm=diameter_nm,drill_nm=drill_nm,clearance_nm=gap,
                        deadline=time.monotonic()+9.5)
                raise Refused('rated_chain_source_all_layer_barrel_refused',dict(
                    failed_barrel=dict(at_nm=list(point),diameter_nm=diameter_nm,drill_nm=drill_nm,
                        native_all_layer_clear=bool(native_clear),native_report=detail,
                        guarded_copper_stack=stack_report,
                        board_edge_clear=bool(edge_clear),source_current_refused_faces=refused_faces),
                    source_mutated=False,retirement_authorized=False,release_authority=False))
            v=pcbnew.PCB_VIA(b);v.SetPosition(at);v.SetWidth(diameter_nm);v.SetDrill(drill_nm)
            v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
            v.SetNetCode(code);v.SetLocked(True);b.Add(v);new_vias.append(force._uid(v))
        for layer,(_,points) in zip(faces,parsed):
            for start,end in zip(points,points[1:]):
                with force._thermal_hint(board_hint):
                    guard=capture.Guard(pcbnew.LoadBoard(str(source)),source,net=net,
                        board_hint=board_hint,timeout_s=10.)
                detail={};width=widths[layer]
                if native_board_envelope:
                    # A harmless control line can require a detour beyond a
                    # local box. Do not repeatedly search a clipped component
                    # and mistake its exhausted lattice for board-level
                    # impossibility. Empty *complete* capture inventories need
                    # no accumulated-run history; all other scopes retain the
                    # actual guard. Native clearance/holes/rule areas remain.
                    if (type(guard.active) is not bool or guard.complete is not True
                            or type(guard.unclassified_owners) is not int
                            or not 0<=guard.unclassified_owners<=4096):
                        raise ValueError('complete_native_chain_capture_inventory_required')
                    predicate=(None if not guard.active and guard.unclassified_owners==0 else
                        lambda s,t,w,l:guard(tuple(s),tuple(t),w,l))
                    operations=fr._multilayer_maze_lastmile_ops(b,
                        pcbnew.VECTOR2I(*start),pcbnew.VECTOR2I(*end),code,[layer],gap,
                        lambda s,t,r:fr._edge_leg_clear(b,s,t,r),
                        width_for_layer=lambda l:width if l==layer else None,
                        start_layers=[layer],end_layers=[layer],grid_mm=.2,max_vias=0,
                        foreign_cache={},deadline_monotonic=time.monotonic()+9.5,
                        max_length_nm=64000000,diagnostics=detail,heuristic_weight=3.,
                        canonical_turns_only=True,obstacle_channel_axes=True,
                        native_board_envelope=True,max_expanded_states=200000,
                        allow_single_layer=True,planar_guard=predicate,
                        neutral_state_dominance=True,field_state_dominance=True)
                    if operations and (len(operations)>256 or any(
                            len(op)!=5 or op[0]!='trk' or op[3]!=width or op[4]!=layer
                            for op in operations)):
                        raise ValueError('native_chain_envelope_changed_face_width_or_barrels')
                    legs=[(op[1],op[2],op[3]) for op in operations] if operations else None
                else:
                    legs=fr._guarded_profiled_lastmile_legs(b,pcbnew.VECTOR2I(*start),pcbnew.VECTOR2I(*end),
                        width,layer,gap,code,lambda s,t,r:fr._edge_leg_clear(b,s,t,r),
                        allow_maze=True,foreign_cache={},deadline_monotonic=time.monotonic()+9.5,
                        max_length_nm=64000000,maze_margin_mm=12.,refine_maze=True,
                        endpoint_detail_grid_mm=.1,compact_phase_jogs=True,
                        run_guard=lambda s,t,w:guard(tuple(s),tuple(t),w,layer),search_diagnostics=detail)
                if not legs:
                    raise Refused('bounded_native_rated_chain_leg_not_found',dict(
                        completed_full_width_native_legs=legs_report,
                        failed_stage=dict(layer=fab.COPPER_LAYER_IDS[layer],start_nm=list(start),
                            end_nm=list(end),width_nm=width,search=detail),
                        source_mutated=False,retirement_authorized=False,release_authority=False))
                legs_report.append(dict(layer=fab.COPPER_LAYER_IDS[layer],start_nm=list(start),
                    end_nm=list(end),width_nm=width,search=detail))
                for s,t,w in legs:
                    if w!=width:raise ValueError('whole_source_chain_width_not_preserved')
                    item=pcbnew.PCB_TRACK(b);item.SetStart(s);item.SetEnd(t);item.SetWidth(w)
                    item.SetLayer(layer);item.SetNetCode(code);item.SetLocked(True);b.Add(item)
                    new_tracks.append(force._uid(item))
    seam_compaction=None
    if compact_new_waypoint_seams:
        new_tracks,seam_compaction=_compact_incoming_seams(b,source,net,set(new_tracks),
            board_hint=board_hint,frozen_source_pours=frozen_source_pours)
    craft=quality.analyze_board(b,track_uuid_scope=set(new_tracks))
    if not craft['geometry_ok'] or not craft['craft_ok']:
        raise Refused('rated_chain_canonical_incoming_craft_refused',dict(
            completed_full_width_native_legs=legs_report,incoming_craft=craft,
            source_mutated=False,retirement_authorized=False,release_authority=False))
    if epoch!=force._code_identity() or family!=force._family(source,board_hint):
        raise ValueError('rated_chain_source_or_code_changed')
    return b,dict(schema=1,scope='private_full_load_source_rated_layer_chain',source_plan=proposal,
        exact_retained_boundary_components=groups,full_width_native_legs=legs_report,
        new_track_uuids=new_tracks,new_via_uuids=new_vias,derived_new_barrel_sites_nm=[list(p) for p in needs],
        source_and_code_unchanged=True,craft=craft,source_current_reduced=False,
        native_board_envelope=native_board_envelope,
        source_declared_consumer_island_reproved=use_source_declared_consumer_island,
        rated_inner_source_scope_explicit=allow_rated_source_inner_layers,
        undersized_source_repair_scope_explicit=repair_undersized_source,
        incoming_waypoint_seam_compaction=seam_compaction,
        future_land_planning=future_land_plan,
        branch_sharing_inferred=False,new_barrel_ampacity_credited=False,
        independent_saved_receiving_required=True,routing_admitted=False,release_authority=False)
