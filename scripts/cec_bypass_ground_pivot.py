"""Fixed-supply-land pivot of one positively selected low-power bypass.

Only an exact native 180-degree capacitor transform and new full-class GND
tracks are owned. The complete supply land, owner supply path, original
tracks/barrels/planes, other components and source native partitions survive.
The return uses an unchanged actual grounded barrel; no new hole, source
mesh cut, converter/bulk ownership, current budget or release credit follows.
"""
import json
import math
from pathlib import Path
import tempfile
import time
import pcbnew
import cec_additive_route_receiving as additive
import cec_cell_row_rebuild as binding
import cec_constraints as constraints
import cec_copper_echo as syntax
import cec_copper_reuse as reuse
import cec_decoupler_cell as cells
import cec_device_power_roles as roles
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ground_return_shortcut as reference
import cec_native_ground_span_reflow as ground
import cec_ordinary_route_receiving as ordinary
import cec_pi_cleanup as placement
import cec_route_quality as quality
import cec_sensitive_scalar_path_reflow as geometry
import cec_support_pivot_receiving as support


def _source(board,pad_uuid,target_via_uuid):
    pads=[p for f in board.GetFootprints() for p in f.Pads()]
    if len(pads)+len(list(board.GetTracks()))>16384:raise ValueError('bypass_pivot_native_inventory_bound')
    found=[p for p in pads if force._uid(p)==pad_uuid]
    if len(found)!=1:raise ValueError('one_literal_source_bypass_ground_land_required')
    pad=found[0];cap=pad.GetParentFootprint();lands=list(cap.Pads())
    if (cap.IsDNP() or cap.IsLocked() or cap.GetParentGroup() or len(lands)!=2
            or len({str(p.GetNumber()) for p in lands})!=2 or pad.GetNetname()!='GND'
            or any(p.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
                or len(list(p.GetLayerSet().CuStack()))!=1
                or p.GetShape() not in (pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT)
                or not 0<max(p.GetSize().x,p.GetSize().y)<=2000000 for p in lands)
            or any(pcbnew.IsCopperLayer(i.GetLayer()) for i in [*cap.GetFields(),*cap.GraphicalItems()])
            or any(g.ContainsItem(cap) for g in board.Groups())):
        raise ValueError('unlocked_ungrouped_populated_two_surface_land_bypass_required')
    assigned=constraints._device_bypass_assignment(board,project_max_mm=3.5)
    rows=[r['requirement'] for r in assigned['assigned'].values() if r['cap_ref']==cap.GetReference()]
    if len(rows)!=1 or (rows[0].get('return_rail') or 'GND')!='GND':
        raise ValueError('unique_source_selected_ground_bypass_required')
    req=rows[0];owner=board.FindFootprintByReference(req['ref']);model=roles.footprint_contract(owner) if owner else None
    anchors=[p for p in lands if p.GetNetname()==req['rail']]
    if (not model or owner.IsDNP() or model['pins'].get(str(req['pin']))!='power_input'
            or set(model['pins'].values())&{'power_output','switch','power_return'} or len(anchors)!=1
            or owner.IsFlipped()!=cap.IsFlipped()):
        raise ValueError('positive_manufacturer_low_power_bypass_ownership_required')
    anchor=anchors[0];face=cells._ground_terminal_layer(pad)
    if face not in (pcbnew.F_Cu,pcbnew.B_Cu) or not anchor.IsOnLayer(face) or support._fixed_land(anchor) is None:
        raise ValueError('exact_symmetric_source_supply_land_required')
    targets=[t for t in board.GetTracks() if force._uid(t)==target_via_uuid]
    if (len(targets)!=1 or targets[0].GetClass()!='PCB_VIA' or targets[0].GetNetname()!='GND'
            or targets[0].GetViaType()!=pcbnew.VIATYPE_THROUGH or targets[0].TopLayer()!=pcbnew.F_Cu
            or targets[0].BottomLayer()!=pcbnew.B_Cu):
        raise ValueError('literal_unchanged_ground_through_reference_barrel_required')
    via=targets[0];contacts=reference._reference_contacts(board,via)
    conn=fr._read_only_route_connectivity(board)
    if force._uid(via) not in {force._uid(t) for t in conn.GetConnectedItems(pad)}:
        raise ValueError('source_bypass_and_retained_reference_not_native_connected')
    supply=owner.FindPadByNumber(str(req['pin']))
    length=cells._shortest_track_path_mm(board,supply,anchor)
    if length is None or length>float(req['max_mm'])+1e-9:
        raise ValueError('source_selected_bypass_needs_proved_existing_local_supply_path')
    selected={k:req.get(k) for k in ('id','ref','pin','rail','kind','return_rail','max_mm','source')}
    return cap,pad,anchor,owner,supply,via,face,contacts,length,selected,model


def _pivot(cap,anchor):
    before=support._fixed_land(anchor);origin=tuple(cap.GetPosition())
    old_lands={force._uid(p):tuple(p.GetPosition()) for p in cap.Pads()}
    fields={force._uid(f):(tuple(f.GetPosition()),f.GetTextAngle().AsDegrees()) for f in cap.GetFields()}
    cap.Rotate(pcbnew.VECTOR2I(*tuple(anchor.GetPosition())),pcbnew.EDA_ANGLE(180,pcbnew.DEGREES_T))
    # Preserve absolute authored annotation poses, not an assumed readable
    # 180-degree text rotation. No unrelated silk move is in this operation.
    for f in cap.GetFields():
        at,angle=fields[force._uid(f)];f.SetPosition(pcbnew.VECTOR2I(*at));f.SetTextAngle(pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    if before!=support._fixed_land(anchor):raise ValueError('entire_native_supply_land_must_remain_exact')
    land_movement=max(math.dist(old_lands[force._uid(p)],tuple(p.GetPosition())) for p in cap.Pads())
    if math.dist(origin,tuple(cap.GetPosition()))>2000000 or not 0<land_movement<=4000000:
        raise ValueError('bounded_two_mm_source_anchor_pivot_required')


def plan(source,*,board_hint,pad_uuid,target_via_uuid,points_nm,timeout_s=10.):
    deadline=ground._deadline(timeout_s)
    if any(type(v) is not str or not v for v in (board_hint,pad_uuid,target_via_uuid)):
        raise ValueError('explicit_source_bypass_pivot_identity_required')
    points=geometry._points(points_nm);source=Path(source).resolve();b=pcbnew.LoadBoard(str(source))
    with force._thermal_hint(board_hint):context=_source(b,pad_uuid,target_via_uuid)
    cap,pad,anchor,owner,supply,via,face,contacts,supply_length,selected,model=context
    before=cells._existing_return(b,pad,16.,allow_native_track_body=True)
    old_pose=[list(cap.GetPosition()),cap.GetOrientationDegrees()];source_binding=binding._source_binding(b)
    _pivot(cap,anchor);placement._pose_preflight(b,cap)
    if points[0]!=tuple(pad.GetPosition()) or points[-1]!=tuple(via.GetPosition()):
        raise ValueError('literal_pivoted_ground_and_unchanged_reference_ports_required')
    length=sum(math.dist(a,z) for a,z in zip(points,points[1:]))/1e6
    if before is None or not .01<length<=4. or length>=before[0]-.01:
        raise ValueError('strict_proved_bounded_ground_return_gain_required')
    spec=cells._netclass(b,'GND');width=max(200000,b.GetDesignSettings().m_TrackMinWidth,int(spec['width']))
    gap=max(200000,b.GetDesignSettings().m_MinClearance,int(spec['clearance']));cache={}
    for a,z in zip(points,points[1:]):
        if time.monotonic()>=deadline:raise ValueError('bypass_pivot_native_geometry_deadline')
        a,z=pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*z)
        if (not fr._edge_leg_clear(b,a,z,(width+1)//2+gap)
                or not fr._tap_foreign_clear(b,a,z,width,face,gap,{pad.GetNetCode()},foreign_cache=cache)):
            raise ValueError('bypass_pivot_foreign_copper_or_edge_clearance')
    retained=reuse.RetainedCopper(reuse.native_inventory(b))
    emitted,proof=retained.subtract([dict(net='GND',layer=int(face),width_nm=width,start_nm=list(a),end_nm=list(z))
        for a,z in zip(points,points[1:])])
    if not 1<=len(emitted)<=15:raise ValueError('bounded_real_new_ground_connector_required')
    reference._new_surface_material(b,points,face,deadline)
    return dict(schema=1,source_sha256=force._hash(source),source_binding=source_binding,
        pad_uuid=pad_uuid,target_via_uuid=target_via_uuid,footprint_uuid=force._uid(cap),anchor_pad_uuid=force._uid(anchor),
        source_pose=old_pose,pivoted_pose=[list(cap.GetPosition()),cap.GetOrientationDegrees()],rotation_delta_deg=180.,
        selected_requirement=selected,manufacturer_source=model['source'],source_supply_path_mm=supply_length,
        source_return_witness_mm=before[0],new_explicit_return_mm=length,points_nm=[list(p) for p in points],
        source_layer=int(face),width_nm=width,emitted_segments_nm=emitted,retained_copper_reuse=proof,
        actual_saved_reference_contacts=contacts,new_holes=0,current_qualified=False,release_authority=False)


def construct(source,proposal,*,board_hint,incoming_uuids=None):
    fresh=plan(source,board_hint=board_hint,**{k:proposal[k] for k in ('pad_uuid','target_via_uuid','points_nm')})
    if fresh!=proposal:raise ValueError('stale_or_forged_source_bypass_pivot_plan')
    b=pcbnew.LoadBoard(str(source));cap=next(f for f in b.GetFootprints() if force._uid(f)==proposal['footprint_uuid'])
    anchor=next(p for p in cap.Pads() if force._uid(p)==proposal['anchor_pad_uuid']);_pivot(cap,anchor)
    _,old=additive._nodes(Path(source));count=len(proposal['emitted_segments_nm'])
    if incoming_uuids is not None and (type(incoming_uuids) is not list or len(incoming_uuids)!=count
            or len(set(incoming_uuids))!=count or any(type(u) is not str or not u or u in old for u in incoming_uuids)):
        raise ValueError('exact_unique_bypass_pivot_replay_UUIDs_required')
    for i,row in enumerate(proposal['emitted_segments_nm']):
        t=pcbnew.PCB_TRACK(b);t.m_Uuid.Clone(pcbnew.KIID(incoming_uuids[i]) if incoming_uuids else pcbnew.KIID())
        t.SetNetCode(b.GetNetcodeFromNetname('GND'));t.SetLayer(proposal['source_layer']);t.SetWidth(proposal['width_nm'])
        t.SetStart(pcbnew.VECTOR2I(*row['start_nm']));t.SetEnd(pcbnew.VECTOR2I(*row['end_nm']));t.SetLocked(True);b.Add(t)
    return b


def receive(source,candidate,proposal,*,board_hint,timeout_s=10.):
    r=dict(ok=False,complete=False,errors=[],current_qualified=False,release_authority=False,
        whole_current_fields_uncapped_native_DRC_Kelvin_stack_and_release_still_required=True)
    try:
        deadline=ground._deadline(timeout_s);source,candidate=map(Path,(source,candidate));epoch=force._code_identity()
        families=[force._family(p,board_hint) for p in (source,candidate)]
        fresh=plan(source,board_hint=board_hint,**{k:proposal[k] for k in ('pad_uuid','target_via_uuid','points_nm')})
        if fresh!=proposal:raise ValueError('source_bypass_pivot_saved_plan_changed')
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        _,old=additive._nodes(source);_,new=additive._nodes(candidate);incoming=set(new)-set(old)
        live={force._uid(t):t for t in child.GetTracks()};ordered=[]
        if set(old)-set(new) or len(incoming)!=len(proposal['emitted_segments_nm']) or not incoming<=live.keys():
            raise ValueError('source_bypass_pivot_cannot_retire_or_add_other_items')
        for row in proposal['emitted_segments_nm']:
            match=[u for u in incoming if live[u].GetClass()=='PCB_TRACK' and list(live[u].GetStart())==row['start_nm']
                and list(live[u].GetEnd())==row['end_nm']]
            if len(match)!=1:raise ValueError('one_literal_bypass_pivot_emitted_leg_required')
            ordered.append(match[0])
        with tempfile.TemporaryDirectory(prefix='cec-bypass-ground-pivot-') as work:
            replay=force._copy_family(source,Path(work)/'expected');expected=construct(source,proposal,board_hint=board_hint,incoming_uuids=ordered)
            field._save_field_snapshot(expected,replay);root,want=additive._nodes(replay);got_root,_=additive._nodes(candidate)
            if syntax._freeze(root)!=syntax._freeze(got_root) or {u:syntax._freeze(n) for u,n in want.items()}!={u:syntax._freeze(n) for u,n in new.items()}:
                raise ValueError('exact_independent_full_source_bypass_pivot_replay_differs')
            basis=force._copy_family(source,Path(work)/'posed-source');posed=pcbnew.LoadBoard(str(basis))
            cap=next(f for f in posed.GetFootprints() if force._uid(f)==proposal['footprint_uuid'])
            anchor=next(p for p in cap.Pads() if force._uid(p)==proposal['anchor_pad_uuid']);_pivot(cap,anchor)
            field._save_field_snapshot(posed,basis)
            delta=additive.receive(basis,candidate,board_hint=board_hint,timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            r['independent_posed_source_additive_receiving']=delta
            if not delta['ok'] or not delta['complete']:raise ValueError('bypass_pivot_additive_receiving_refused')
        if force._sidecars(source)!=force._sidecars(candidate):raise ValueError('bypass_pivot_source_sidecars_changed')
        with force._thermal_hint(board_hint):old_context=_source(parent,proposal['pad_uuid'],proposal['target_via_uuid'])
        cap,old_pad,anchor,owner,supply,*_=old_context
        target=next(f for f in child.GetFootprints() if force._uid(f)==proposal['footprint_uuid'])
        target_pad=next(p for p in target.Pads() if force._uid(p)==proposal['pad_uuid'])
        target_anchor=next(p for p in target.Pads() if force._uid(p)==proposal['anchor_pad_uuid'])
        placement._pose_preflight(child,target)
        if support._fixed_land(anchor)!=support._fixed_land(target_anchor):raise ValueError('saved_bypass_supply_land_changed')
        source_parts=ordinary._partition(parent,deadline);keys=set().union(*source_parts)
        rebind={force._item_key(target_pad):force._item_key(old_pad)}
        child_parts=ordinary._partition(child,deadline,retained_keys=keys,_identity_rebindings=rebind)
        if {frozenset(p) for p in source_parts}!={frozenset(p) for p in child_parts}:
            raise ValueError('bypass_pivot_source_native_conductor_partition_changed')
        after=cells._existing_return(child,target_pad,16.,allow_native_track_body=True)
        if after is None or after[0]>=proposal['source_return_witness_mm']-.01:
            raise ValueError('saved_bypass_pivot_return_witness_did_not_improve')
        new_owner=child.FindFootprintByReference(owner.GetReference());new_supply=new_owner.FindPadByNumber(supply.GetNumber())
        supply_after=cells._shortest_track_path_mm(child,new_supply,target_anchor)
        if supply_after is None or supply_after>proposal['source_supply_path_mm']+1e-6:
            raise ValueError('bypass_pivot_existing_supply_path_worsened')
        child_pads={force._uid(p):p for f in child.GetFootprints() for p in f.Pads()};checked=0
        for f in parent.GetFootprints():
            for pad in f.Pads():
                if force._uid(pad)==proposal['pad_uuid'] or pad.GetNetname()!='GND' or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD:continue
                if time.monotonic()>=deadline:raise ValueError('bypass_pivot_other_return_comparison_deadline')
                if ground._outside_return_reach(pad,[old_pad,target_pad]):continue
                prior=cells._existing_return(parent,pad,16.,allow_native_track_body=True)
                if prior is None:continue
                last=cells._existing_return(child,child_pads[force._uid(pad)],16.,allow_native_track_body=True)
                if last is None or last[0]>prior[0]+1e-6:raise ValueError('bypass_pivot_another_proved_ground_return_worsened')
                checked+=1
        craft=[quality.analyze_board(b) for b in (parent,child)]
        if any(craft[1][k]>craft[0][k] for k in ('issue_count','non_octilinear_count')):
            raise ValueError('bypass_pivot_whole_trace_craft_worsened')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in (source,candidate)]:
            raise ValueError('bypass_pivot_sources_or_code_changed')
        r.update(ok=True,complete=True,code_identity=epoch,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            source_family_and_code_unchanged=True,modified_footprint_uuids=[proposal['footprint_uuid']],
            retired_track_uuids=[],added_native_uuids=ordered,new_holes=0,
            entire_source_supply_land_and_path_preserved=True,every_original_native_partition_identical_after_exact_ground_pad_rebinding=True,
            other_checked_ground_returns=checked,source_return_witness_mm=proposal['source_return_witness_mm'],saved_return_witness_mm=after[0],
            return_witness_gain_mm=proposal['source_return_witness_mm']-after[0],source_supply_path_mm=proposal['source_supply_path_mm'],
            saved_supply_path_mm=supply_after,witness_not_global_optimum_or_immediate_return_qualification=True,
            all_original_tracks_barrels_planes_rules_interfaces_and_other_components_unchanged=True,
            original_absolute_field_poses_preserved=True,ordinary_reclassification=False,placement_authority_transferred=False)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
