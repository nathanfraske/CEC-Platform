"""Reconstruct a bounded source-owned logical ground strap.

Only positively manufacturer-typed ground-tied address/reference lands are
eligible. This is not power-ground, mesh, main-current, or arbitrary via rip-up
authority. The entire unlocked, ungrouped, endpoint-linear source strap must
end at one otherwise unbranched ground-plane via. Every surviving native
partition and selected-bypass return stays intact. Full saved-board receiving
still decides adoption; no current, Kelvin, thermal, or release credit follows.
An ordinary root can alternatively be reseated within 1 mm, retaining its
exact barrel geometry and a bounded uniform strap. This does not relax local
bypass return lengths: every existing immediate return must remain no longer.
Locked source material requires an explicit exact UUID scope, independently
retyped as this same logical leaf. A lock scope never grants power-ground,
mesh, grouped-material or arbitrary ground-via ownership.

Explicit selected_bypass mode also admits a uniquely assigned, manufacturer-
typed low-power input decoupler's single unbranched plane entry. It must get
strictly shorter. Converter outputs, switching/power returns, bulk capacitors,
shared roots and unselected capacitors remain outside this scope. Logical
address/reference behavior and all saved-source receiving gates are unchanged.
"""
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as sexpr
import cec_decoupler_cell as cells
import cec_device_power_roles as roles
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
from cec_native_items import discard_items


def _land_ownership(board, pad, land_role):
    """Retype the requested leaf; an explicit mode is not an ownership waiver."""
    if land_role == 'logical':
        model = roles.footprint_contract(pad.GetParentFootprint())
        if not model or model['pins'].get(str(pad.GetNumber())) not in ('address', 'reference'):
            raise ValueError('positive_ground_tied_nonpower_strap_land_required')
        return model['source'], model['pins'][str(pad.GetNumber())], None
    if land_role != 'selected_bypass':
        raise ValueError('explicit_ground_leaf_ownership_mode_required')
    import cec_constraints as constraints
    cap = pad.GetParentFootprint(); lands = list(cap.Pads())
    if (cap.IsDNP() or len(lands) != 2 or any(p.HasHole()
            or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
            or len(list(p.GetLayerSet().CuStack())) != 1 for p in lands)):
        raise ValueError('selected_two_surface_land_ground_bypass_required')
    assignments = constraints._device_bypass_assignment(board, project_max_mm=3.5)
    matches = [r['requirement'] for r in assignments['assigned'].values()
               if r['cap_ref'] == cap.GetReference()]
    if len(matches) != 1 or (matches[0].get('return_rail') or 'GND') != 'GND':
        raise ValueError('uniquely_selected_ground_bypass_required')
    req = matches[0]; owner = board.FindFootprintByReference(req['ref'])
    model = roles.footprint_contract(owner) if owner is not None else None
    if (owner is None or owner.IsDNP() or not model
            or model['pins'].get(str(req['pin'])) != 'power_input'
            or set(model['pins'].values()) & {'power_output', 'switch', 'power_return'}
            or owner.IsFlipped() != cap.IsFlipped()
            or len([p for p in lands if str(p.GetNetname()) == req['rail']]) != 1):
        raise ValueError('positive_low_power_device_bypass_topology_required')
    # Assignment rows contain live SWIG pads. Evidence must be independently
    # reproducible and serializable, not hold native pointers across epochs.
    selected = {key: req[key] for key in ('id','ref','pin','rail','kind','source') if key in req}
    selected.update(power_pad_uuid=force._uid(req['pad']), return_rail='GND')
    return model['source'], 'selected_bypass', selected


def plan(board, pad_uuid, *, allow_locked_track_uuids=(), allow_locked_via_uuid=None,
         land_role='logical', timeout_s=10.):
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10):
        raise ValueError('bounded_ground_strap_inventory_required')
    deadline = time.monotonic()+timeout_s
    allowed = ordinary._ids(allow_locked_track_uuids,'logical_ground_locked_tracks',8)
    allowed_vias = ordinary._ids([] if allow_locked_via_uuid is None else [allow_locked_via_uuid],
        'logical_ground_locked_root',1)
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    matching = [p for p in pads if force._uid(p)==pad_uuid]
    if len(matching)!=1:raise ValueError('ground_strap_source_land_unknown')
    pad = matching[0]
    layers = list(pad.GetLayerSet().CuStack())
    if (str(pad.GetNetname())!='GND' or pad.HasHole()
            or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or len(layers)!=1):
        raise ValueError('positive_ground_tied_nonpower_strap_land_required')
    manufacturer_source, role, selected_requirement = _land_ownership(board, pad, land_role)
    layer=layers[0];code=pad.GetNetCode()
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    tracks=list(board.GetTracks())
    zones=[z for z in board.Zones() if not z.GetIsRuleArea()]
    touching=[t for t in tracks if t.GetNetCode()==code and t.IsOnLayer(layer)
        and t.GetEffectiveShape(layer).Collide(pad.GetEffectiveShape(layer),0)]
    if len(touching)!=1 or touching[0].GetClass()!='PCB_TRACK':
        raise ValueError('unique_source_ground_strap_departure_required')
    current=touching[0];ends=[tuple(current.GetStart()),tuple(current.GetEnd())]
    starts=[p for p in ends if pad.HitTest(pcbnew.VECTOR2I(*p))]
    if len(starts)!=1:raise ValueError('ground_strap_interior_endpoint_required')
    point=starts[0];width=current.GetWidth();retired=[];length=0.;points=[list(point)]
    if not 0 < width <= 350000:raise ValueError('small_nonpower_ground_strap_required')
    mesh_root=None;via=None
    while True:
        if time.monotonic()>=deadline:raise ValueError('ground_strap_inventory_deadline')
        uid=force._uid(current)
        if (current.GetClass()!='PCB_TRACK' or current.IsLocked() and uid not in allowed or uid in grouped
                or current.GetLayer()!=layer or current.GetWidth()!=width or uid in retired):
            raise ValueError('ground_strap_not_unlocked_ungrouped_uniform_linear_source')
        ends=[tuple(current.GetStart()),tuple(current.GetEnd())]
        if point not in ends or ends[0]==ends[1]:raise ValueError('source_strap_not_endpoint_linear')
        far=ends[1] if ends[0]==point else ends[0]
        retired.append(uid);length+=current.GetLength()/1e6
        points.append(list(far))
        if len(retired)>8 or length>12.:raise ValueError('ground_strap_scope_bound')
        contacts=[]
        for other in [*pads,*tracks,*zones]:
            if force._uid(other) in retired or force._uid(other)==pad_uuid:
                continue
            if other.GetNetCode()!=code or not other.IsOnLayer(layer):continue
            if other.GetClass()=='ZONE':
                if not other.IsFilled():raise ValueError('ground_strap_zone_material_unknown')
                shape=other.GetFilledPolysList(layer)
            else:shape=other.GetEffectiveShape(layer)
            if not shape.Collide(current.GetEffectiveShape(layer),0):continue
            if not shape.Collide(pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*far),pcbnew.VECTOR2I(*far),width),0):
                raise ValueError('source_ground_strap_has_interior_tee')
            contacts.append(other)
        # A short final bend may contact its ordinary circular via before
        # the traversal reaches that bend's endpoint. This is still the
        # same exact linear endpoint kernel, not a second ground branch.
        # Defer ONLY that one via beside its one uniform endpoint leg; the
        # following iteration must still terminate at the actual native via.
        if len(contacts)==2:
            next_edges=[t for t in contacts if t.GetClass()=='PCB_TRACK']
            next_vias=[v for v in contacts if v.GetClass()=='PCB_VIA']
            if len(next_edges)==len(next_vias)==1:
                edge,entry=next_edges[0],next_vias[0]
                ends={tuple(edge.GetStart()),tuple(edge.GetEnd())}
                if (ends=={far,tuple(entry.GetPosition())} and len(ends)==2
                        and edge.GetLayer()==layer and edge.GetWidth()==width
                        and 0<edge.GetLength()<=1000000
                        and entry.GetEffectiveShape(layer).Collide(edge.GetEffectiveShape(layer),0)):
                    contacts=[edge]
        # Stop at a retained same-net trunk's interior junction. Its geometry
        # and all its other branches remain immutable; only this logical
        # address/reference leaf is eligible for reconstruction.
        if (1<=len(contacts)<=4 and all(t.GetClass()=='PCB_TRACK' for t in contacts)
                and (len(contacts)>1 or far not in (
                    tuple(contacts[0].GetStart()),tuple(contacts[0].GetEnd())))):
            mesh_root=contacts[0];break
        if len(contacts)!=1:raise ValueError('source_strap_branch_or_terminal_ambiguity')
        next_item=contacts[0]
        if next_item.GetClass()=='PCB_VIA':
            via=next_item;break
        if next_item.GetClass()!='PCB_TRACK':raise ValueError('strap_terminates_at_unowned_material')
        current=next_item;point=far
    if mesh_root is not None:
        if land_role == 'selected_bypass':
            raise ValueError('selected_bypass_requires_its_own_unbranched_plane_entry')
        if not allowed <= set(retired) or allowed_vias:
            raise ValueError('logical_ground_lock_scope_contains_unowned_material')
        conn=fr._read_only_route_connectivity(board)
        reached={force._uid(t) for t in conn.GetConnectedItems(mesh_root)}
        contacts=sorted(force._uid(z) for z in zones if z.GetNetname()=='GND'
            and z.IsFilled() and force._uid(z) in reached)
        if not contacts:raise ValueError('source_ground_mesh_root_has_no_saved_plane_contact')
        return dict(schema=1,pad_uuid=pad_uuid,owner=pad.GetParentFootprint().GetReference(),
            pin=str(pad.GetNumber()),manufacturer_source=manufacturer_source,role=role,
            retired_track_uuids=retired,retired_via_uuid=None,source_path_mm=length,
            source_ground_plane_uuids=contacts,source_width_nm=width,source_points_nm=points,
            root_nm=list(far),mesh_root_uuid=force._uid(mesh_root),root_kind='retained_mesh_junction',
            source_binding=field._field_snapshot_inventory(board),release_authority=False,
            allow_locked_track_uuids=sorted(allowed),allow_locked_via_uuid=None)
    if (via.IsLocked() and force._uid(via) not in allowed_vias or force._uid(via) in grouped
            or via.GetViaType()!=pcbnew.VIATYPE_THROUGH):
        raise ValueError('source_ground_strap_root_is_protected_or_non_through')
    neighbours=[t for t in tracks if force._uid(t)!=force._uid(via)
        and t.GetNetCode()==code and any(t.IsOnLayer(l) and t.GetEffectiveShape(l).Collide(
            via.GetEffectiveShape(l),0) for l in board.GetEnabledLayers().CuStack())]
    if (retired[-1] not in {force._uid(t) for t in neighbours}
            or not {force._uid(t) for t in neighbours}<=set(retired)):
        raise ValueError('source_strap_root_has_other_live_branch')
    if any(p.GetNetCode()==code and any(p.IsOnLayer(l) and p.GetEffectiveShape(l).Collide(
            via.GetEffectiveShape(l),0) for l in board.GetEnabledLayers().CuStack()) for p in pads):
        raise ValueError('source_strap_root_contacts_another_terminal')
    contacts=[force._uid(z) for z in zones if z.GetNetname()=='GND' and z.IsFilled()
        and any(z.IsOnLayer(l) and via.IsOnLayer(l) and z.GetFilledPolysList(l).Collide(
            via.GetEffectiveShape(l),0) for l in board.GetEnabledLayers().CuStack())]
    if not contacts:raise ValueError('source_strap_root_has_no_saved_ground_plane')
    if not allowed <= set(retired) or not allowed_vias <= {force._uid(via)}:
        raise ValueError('logical_ground_lock_scope_contains_unowned_material')
    return dict(schema=1,pad_uuid=pad_uuid,owner=pad.GetParentFootprint().GetReference(),
        pin=str(pad.GetNumber()),manufacturer_source=manufacturer_source,role=role,
        retired_track_uuids=retired,retired_via_uuid=force._uid(via),source_path_mm=length,
        source_ground_plane_uuids=sorted(contacts),source_width_nm=width,
        source_points_nm=points,root_nm=list(via.GetPosition()),
        root_diameter_nm=via.GetWidth(via.TopLayer()),root_drill_nm=via.GetDrillValue(),
        root_layers=[via.TopLayer(),via.BottomLayer()],root_kind='unbranched_via',
        source_binding=field._field_snapshot_inventory(board),release_authority=False,
        allow_locked_track_uuids=sorted(allowed),allow_locked_via_uuid=allow_locked_via_uuid,
        **({'selected_requirement': selected_requirement} if land_role == 'selected_bypass' else {}))


def subtract(board, proposal):
    if field._field_snapshot_inventory(board)!=proposal['source_binding']:
        raise ValueError('ground_strap_source_binding_changed')
    if plan(board,proposal['pad_uuid'],
            allow_locked_track_uuids=proposal.get('allow_locked_track_uuids',()),
            allow_locked_via_uuid=proposal.get('allow_locked_via_uuid'),
            land_role='selected_bypass' if proposal.get('role') == 'selected_bypass' else 'logical') != proposal:
        raise ValueError('ground_strap_exact_source_scope_changed')
    ids=set(proposal['retired_track_uuids'])
    if proposal['retired_via_uuid']:ids.add(proposal['retired_via_uuid'])
    discard_items(board,[t for t in board.GetTracks() if force._uid(t) in ids])


def receive(source,candidate,*,pad_uuid,board_hint,allow_locked_track_uuids=(),
            allow_locked_via_uuid=None,land_role='logical',timeout_s=10.):
    result=dict(schema=1,ok=False,complete=False,errors=[],release_authority=False,
        current_authority=False,full_saved_board_receiving_still_required=True)
    try:
        source,candidate=map(lambda p:Path(p).resolve(),(source,candidate))
        families=[force._family(p,board_hint) for p in (source,candidate)];epoch=force._code_identity()
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        proposal=plan(parent,pad_uuid,allow_locked_track_uuids=allow_locked_track_uuids,
            allow_locked_via_uuid=allow_locked_via_uuid,land_role=land_role,timeout_s=timeout_s)
        retired=set(proposal['retired_track_uuids'])
        if proposal['retired_via_uuid']:retired.add(proposal['retired_via_uuid'])
        _,old=additive._nodes(source);_,new=additive._nodes(candidate)
        if old.keys()-new.keys()!=retired:raise ValueError('saved_ground_strap_retirement_differs_from_typed_scope')
        incoming=new.keys()-old.keys()
        additions=[v for v in child.GetTracks() if force._uid(v) in incoming]
        vias=[v for v in additions if v.GetClass()=='PCB_VIA']
        tracks=[v for v in additions if v.GetClass()=='PCB_TRACK']
        mesh=proposal['root_kind']=='retained_mesh_junction'
        if len(vias)!=(0 if mesh else 1) or len(vias)+len(tracks)!=len(additions) or any(v.GetNetname()!='GND' for v in additions):
            raise ValueError('one_ground_entry_and_its_bounded_strap_required')
        via=vias[0] if vias else None;pad=child.FindFootprintByReference(proposal['owner']).FindPadByNumber(proposal['pin'])
        spec=fr._project_netclass_resolver(str(source))('GND') or {}
        minimum_width=max(child.GetDesignSettings().m_TrackMinWidth,
            round(float(spec.get('track_width') or .2)*1e6))
        if any(t.GetWidth()<minimum_width for t in tracks):
            raise ValueError('new_ground_strap_below_unchanged_class_minimum')
        valid=False if mesh else fab.via_pad_decision(child,pad,via.GetPosition(),via.GetWidth(via.TopLayer()),
            via.GetDrillValue(),via.GetNetCode())[0]
        path_length=0.
        if valid:
            if tracks or not fab.local_pofv_via_decision(child,via)[0]:
                raise ValueError('contained_entry_needs_no_extra_ground_tracks')
            mode='contained_local_entry'
        else:
            if not mesh:
                ordinary_dia,ordinary_drill,_=fab.board_legal_through_via_geometry(child,
                    max(proposal['root_diameter_nm']/1e6,float(spec.get('via_diameter') or .6)),
                    max(proposal['root_drill_nm']/1e6,float(spec.get('via_drill') or .3)))
            if (not 1<=len(tracks)<=8 or (not mesh and (via.GetViaType()!=pcbnew.VIATYPE_THROUGH
                    or via.GetWidth(via.TopLayer())!=proposal['root_diameter_nm']
                    or via.GetDrillValue()!=proposal['root_drill_nm']
                    or [via.TopLayer(),via.BottomLayer()]!=proposal['root_layers']
                    or round(ordinary_dia*1e6)!=proposal['root_diameter_nm']
                    or round(ordinary_drill*1e6)!=proposal['root_drill_nm']
                    or not 0 < math.dist(list(via.GetPosition()),proposal['root_nm']) <= 1e6))):
                raise ValueError('root_reseat_must_retain_ordinary_geometry_and_local_scope')
            cursor=tuple(proposal['source_points_nm'][0]);target=tuple(proposal['root_nm'] if mesh else via.GetPosition());used=set()
            while cursor!=target:
                choices=[t for t in tracks if force._uid(t) not in used and cursor in (
                    tuple(t.GetStart()),tuple(t.GetEnd()))]
                if len(choices)!=1:raise ValueError('new_ground_strap_not_endpoint_linear')
                t=choices[0];used.add(force._uid(t));path_length+=t.GetLength()/1e6
                if (t.GetWidth()!=proposal['source_width_nm']
                        or t.GetLayer()!=next(iter(pad.GetLayerSet().CuStack()))):
                    raise ValueError('new_ground_strap_width_or_surface_changed')
                cursor=tuple(t.GetEnd()) if cursor==tuple(t.GetStart()) else tuple(t.GetStart())
            if len(used)!=len(tracks) or path_length>proposal['source_path_mm']+(4. if mesh else 2.):
                raise ValueError('root_reseat_extra_material_or_length_bound')
            if proposal['role']=='reference' and path_length>proposal['source_path_mm']+1e-6:
                raise ValueError('manufacturer_reference_ground_return_length_worsened')
            if proposal['role']=='selected_bypass' and path_length >= proposal['source_path_mm']-1e-6:
                raise ValueError('selected_bypass_ground_return_not_strictly_shortened')
            mode='retained_mesh_logical_leaf' if mesh else 'bounded_ordinary_root_reseat'
        if mesh:
            live={force._uid(t):t for t in child.GetTracks()}
            root=live.get(proposal['mesh_root_uuid'])
            if root is None:raise ValueError('source_ground_mesh_root_missing')
            reached={force._uid(t) for t in fr._read_only_route_connectivity(child).GetConnectedItems(root)}
            if not set(proposal['source_ground_plane_uuids'])<=reached:
                raise ValueError('retained_ground_mesh_lost_saved_plane_contact')
        elif not all(any(z.GetNetname()=='GND' and z.IsFilled() and force._uid(z)==uid
                and any(z.IsOnLayer(l) and via.IsOnLayer(l) and z.GetFilledPolysList(l).Collide(
                    via.GetEffectiveShape(l),0) for l in child.GetEnabledLayers().CuStack())
            for z in child.Zones()) for uid in proposal['source_ground_plane_uuids']):
            raise ValueError('replacement_entry_lost_existing_ground_plane')
        first=ordinary._partition(parent,time.monotonic()+timeout_s,retired_uuids=retired)
        keys=set().union(*first);last=ordinary._partition(child,time.monotonic()+timeout_s,retained_keys=keys)
        if any(not any(p<=q for q in last) for p in first):
            raise ValueError('ground_strap_replacement_lost_surviving_native_partition')
        # A source-selected immediate return on any existing capacitor/ground
        # land must not become longer or disappear through the reconstruction.
        oldpads={force._uid(p):p for fp in parent.GetFootprints() for p in fp.Pads() if p.GetNetname()=='GND'}
        newpads={force._uid(p):p for fp in child.GetFootprints() for p in fp.Pads() if p.GetNetname()=='GND'}
        for uid,p in oldpads.items():
            before=cells._existing_return(parent,p,1.5)
            if before is None:continue
            after=cells._existing_return(child,newpads[uid],1.5)
            if after is None or after[0]>before[0]+1e-6:
                raise ValueError('existing_immediate_ground_return_worsened:'+uid)
        with tempfile.TemporaryDirectory(prefix='cec-ground-strap-replay-') as work:
            projected=force._copy_family(source,Path(work)/'projected');basis=pcbnew.LoadBoard(str(projected))
            subtract(basis,proposal);field._save_field_snapshot(basis,projected)
            _,nodes=additive._nodes(projected)
            if nodes.keys()!=old.keys()-retired or any(sexpr._freeze(nodes[u])!=sexpr._freeze(old[u]) for u in nodes):
                raise ValueError('ground_strap_subtraction_changed_unowned_material')
            # Check proposed copper against the immutable source-minus-exact-
            # strap, not a child in which a foreign contact could be relabelled.
            gap=max(basis.GetDesignSettings().m_MinClearance,round(float((
                fr._project_netclass_resolver(str(source))('GND') or {}).get('clearance') or .2)*1e6))
            if via is not None and not fr._via_spot_clear(basis,via.GetPosition(),via.GetWidth(via.TopLayer()),gap,
                    {via.GetNetCode()},drill_nm=via.GetDrillValue(),net_code=via.GetNetCode(),foreign_cache={}):
                raise ValueError('new_ground_entry_native_all_layer_guard_refused')
            for t in tracks:
                if (not fr._edge_leg_clear(basis,t.GetStart(),t.GetEnd(),math.ceil(t.GetWidth()/2+gap))
                        or not fr._tap_foreign_clear(basis,t.GetStart(),t.GetEnd(),t.GetWidth(),
                            t.GetLayer(),gap,{t.GetNetCode()},foreign_cache={})):
                    raise ValueError('new_ground_strap_native_guard_refused')
            proof=additive.receive(projected,candidate,timeout_s=timeout_s)
            result['independent_source_cut_ground_refill_and_rule_replay']=proof
            if not proof['ok'] or not proof['complete']:raise ValueError('ground_strap_exact_replay_refused')
        if families!=[force._family(p,board_hint) for p in (source,candidate)] or epoch!=force._code_identity():
            raise ValueError('ground_strap_source_candidate_or_code_changed')
        result.update(ok=True,complete=True,source_candidate_and_code_unchanged=True,
            retired_track_uuids=proposal['retired_track_uuids'],retired_via_uuids=[proposal['retired_via_uuid']] if proposal['retired_via_uuid'] else [],
            added_native_uuids=sorted(incoming),contained_return_via_uuid=force._uid(via) if via else None,
            source_path_mm=proposal['source_path_mm'],source_proposal={k:v for k,v in proposal.items() if k!='source_binding'},
            entry_mode=mode,new_path_mm=path_length,
            ground_return_shortening_mm=proposal['source_path_mm']-path_length,
            all_surviving_partitions_and_immediate_returns_preserved=True,
            independently_measured_local_PI_progress=mode=='contained_local_entry',
            main_force_copper_poses_and_power_fills_exact=True)
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
