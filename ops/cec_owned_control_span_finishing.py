"""Finish a positively owned tied-enable span without power-path authority.

The original manufacturer/control classifier must independently own every cut
and re-own exactly source-minus-cut-plus-new material after saving. The exact
leaf land, original input capture, other leaves, source budget, native widths,
barrels and all other objects are retained. No typical current becomes a
maximum, and a control leaf cannot grant a whole-rail width exemption.
"""
import json,math,tempfile,time,uuid
from pathlib import Path
import pcbnew
import cec_actual_face_supply_kernel as kernel
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_current_debt as debt
import cec_device_power_roles as roles
import cec_field_coupling as field
import cec_force_current as force
import cec_native_current_capture as capture
import cec_native_fill_geometry as fills
import cec_ordinary_route_receiving as ordinary
from cec_native_items import discard_items

POLICY='source-owned-manufacturer-tied-control-span-finishing-v1'
require=kernel.require
plain=kernel.plain


def owned_scope(board,source,hint,cut):
    nets={t.GetNetname() for t in board.GetTracks() if force._uid(t) in cut}
    require(len(nets)==1,'one_actual_control_span_net_required');net=next(iter(nets))
    with force._thermal_hint(hint):guard=capture.Guard(board,source,net=net,board_hint=hint,timeout_s=10.)
    scopes=[s for s in guard.scopes if cut<=set(s['exclusive_material_uuids'])]
    require(guard.complete and len(scopes)==1,'complete_positive_original_manufacturer_control_span_ownership_required')
    scope=scopes[0]
    pad=next((p for fp in board.GetFootprints() for p in fp.Pads() if force._uid(p)==scope['control_pad_uuid']),None)
    require(pad is not None,'actual_owned_control_pad_required')
    model=roles.tied_enable_contract(pad.GetParentFootprint())
    require(model is not None and model['enable_pin']==pad.GetNumber()
        and model['current_max_a'] is None and not model['branch_current_qualified'],
        'unchanged_positive_manufacturer_control_role_not_numeric_load_budget_required')
    return dict(net=net,native_scope=plain(scope),manufacturer_role=plain(model))


def plan(source,*,board_hint,retired_track_uuids,start_uuid,end_uuid,layer,points_nm,allow_locked_source=False):
    source=Path(source).resolve();epoch=force._code_identity();authority=force._hash(Path(__file__))
    require(type(board_hint) is str and board_hint and type(layer) is int and type(allow_locked_source) is bool,
        'explicit_owned_control_context_required')
    b=pcbnew.LoadBoard(str(source));live={force._uid(t):t for t in b.GetTracks()}
    cut=ordinary._ids(retired_track_uuids,'owned_control_span_cut',8)
    require(cut and cut<=live.keys(),'actual_bounded_control_span_tracks_required')
    old=[live[u] for u in sorted(cut)]
    require(all(t.GetClass()=='PCB_TRACK' and not t.HasSolderMask() and not t.GetParentGroup()
        and (not t.IsLocked() or allow_locked_source) for t in old)
        and len({(t.GetNetname(),int(t.GetLayer()),t.GetWidth()) for t in old})==1,
        'uniform_plain_owned_control_source_span_required')
    scope=owned_scope(b,source,board_hint,cut);net=scope['net'];width=old[0].GetWidth()
    original=[list(p) for p in kernel.capacity.chains._chain(old)]
    require({start_uuid,end_uuid}<=live.keys() and start_uuid!=end_uuid and not {start_uuid,end_uuid}&cut,
        'two_distinct_retained_control_barrel_ports_required')
    ports=[live[u] for u in (start_uuid,end_uuid)]
    require(layer in (int(pcbnew.F_Cu),int(pcbnew.B_Cu))
        and all(kernel.through_barrel(t) and t.GetNetname()==net and t.GetWidth(layer)>=width for t in ports),
        'same_net_actual_unchanged_control_outer_barrels_required')
    endpoints={tuple(original[0]),tuple(original[-1])}
    require(endpoints=={tuple(t.GetPosition()) for t in ports},'literal_old_control_span_ports_required')
    points=[list(p) for p in kernel.capacity.geometry._points(points_nm)]
    contacts=[]
    for port,at,neighbor in ((ports[0],points[0],points[1]),(ports[1],points[-1],points[-2])):
        require(math.dist(at,port.GetPosition())<=(port.GetWidth(layer)+width)/2,
            'bounded_unchanged_native_control_barrel_landing_required')
        t=old[0].Duplicate();t.SetLayer(layer);t.SetStart(pcbnew.VECTOR2I(*at));t.SetEnd(pcbnew.VECTOR2I(*neighbor))
        cap=pcbnew.SHAPE_POLY_SET();t.TransformShapeToPolygon(cap,layer,0,1,pcbnew.ERROR_INSIDE,False)
        land=pcbnew.SHAPE_POLY_SET();port.TransformShapeToPolygon(land,layer,0,1,pcbnew.ERROR_INSIDE,False)
        cap.BooleanIntersection(land);hole=pcbnew.SHAPE_POLY_SET()
        port.GetEffectiveHoleShape().TransformToPolygon(hole,1,pcbnew.ERROR_OUTSIDE);cap.BooleanSubtract(hole)
        require(cap.OutlineCount()>0,'positive_actual_drilled_annular_control_contact_required')
        digest,vertices=fills.identity(cap,time.monotonic()+2.)
        contacts.append(dict(barrel_uuid=force._uid(port),landing_nm=at,annular_contact_sha256=digest,
            contact_vertices=vertices,integer_native_drill_subtraction=True,barrel_rating_qualified=False))
    prior=sum(t.GetLength() for t in old);length=sum(math.dist(a,z) for a,z in zip(points,points[1:]))
    require(0<width<=350000 and 0<length<prior<=4000000,'strictly_shorter_bounded_unchanged_width_control_span_required')
    spec=kernel.capacity.fr._project_netclass_resolver(str(source),board=b)(net) or {}
    floor=max(b.GetDesignSettings().m_TrackMinWidth,math.ceil(float(spec.get('track_width') or .2)*1e6))
    require(width>=floor,'source_control_width_cannot_bypass_unchanged_project_or_factory_floor')
    gap=max(b.GetDesignSettings().m_MinClearance,math.ceil(float(spec.get('clearance') or .2)*1e6))
    for a,z in zip(points,points[1:]):
        require(kernel.capacity.fr._edge_leg_clear(b,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*z),(width+1)//2+gap)
            and kernel.capacity.fr._tap_foreign_clear(b,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*z),width,layer,gap,{ports[0].GetNetCode()}),
            'owned_control_native_foreign_or_edge_clearance_refused')
    require(epoch==force._code_identity() and authority==force._hash(Path(__file__)),'owned_control_plan_epoch_changed')
    return plain(dict(policy=POLICY,source_sha256=force._hash(source),code_identity=epoch,authority_sha256=authority,
        kernel_dependency_sha256=force._hash(Path(kernel.__file__)),board_hint=board_hint,retired_track_uuids=sorted(cut),
        start_uuid=start_uuid,end_uuid=end_uuid,layer=layer,width_nm=width,points_nm=points,source_points_nm=original,
        source_length_nm=prior,candidate_length_nm=length,allow_locked_source=allow_locked_source,
        actual_unchanged_barrel_port_contacts=contacts,
        owned_manufacturer_control=scope,current_budget_or_width_reduced=False,new_barrels_or_parts_authorized=False,
        manufacturer_maximum_current_unknown=True,release_authority=False))


def construct(source,proposal):
    b=pcbnew.LoadBoard(str(source));live={force._uid(t):t for t in b.GetTracks()}
    discard_items(b,[live[u] for u in proposal['retired_track_uuids']]);code=b.GetNetcodeFromNetname(proposal['owned_manufacturer_control']['net'])
    key=repr((POLICY,proposal['source_sha256'],proposal['retired_track_uuids'],proposal['points_nm']))
    for i,(a,z) in enumerate(zip(proposal['points_nm'],proposal['points_nm'][1:])):
        t=pcbnew.PCB_TRACK(b);t.SetNetCode(code);t.SetLayer(proposal['layer']);t.SetWidth(proposal['width_nm']);t.SetLocked(True)
        t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z))
        t.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,key+str(i)))));b.Add(t)
    additive._ground_refill(b);return b


def receive(source,candidate,proposal,*,board_hint):
    result=dict(ok=False,complete=False,errors=[],current_or_barrel_qualified=False,full_kelvin_qualification=False,
        new_vias=0,pads_moved=0,source_current_reduced=False,routing_admitted=False,fab_ready=False,release_authority=False)
    try:
        source,candidate=[Path(p).resolve() for p in (source,candidate)];epoch=force._code_identity()
        families=[force._family(p,board_hint) for p in (source,candidate)]
        fresh=plan(source,board_hint=board_hint,**{k:proposal[k] for k in
            ('retired_track_uuids','start_uuid','end_uuid','layer','points_nm','allow_locked_source')})
        require(fresh==proposal,'stale_or_forged_owned_control_span_plan')
        require(force._sidecars(source)==force._sidecars(candidate),'owned_control_sidecars_or_rules_changed')
        _,old=additive._nodes(source);_,got=additive._nodes(candidate)
        cut=set(proposal['retired_track_uuids']);added=set(got)-set(old)
        require(set(old)-set(got)==cut and len(added)==len(proposal['points_nm'])-1,'exact_owned_control_span_identity_delta_required')
        with tempfile.TemporaryDirectory(prefix='cec-owned-control-') as work:
            replay=force._copy_family(source,Path(work)/'expected');field._save_field_snapshot(construct(source,proposal),replay)
            _,expected=additive._nodes(replay)
            require(got.keys()==expected.keys() and all(syntax._freeze(n)==syntax._freeze(got[u]) for u,n in expected.items()),
                'unowned_saved_control_copper_geometry_or_object_change')
        boards=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        child_scope=owned_scope(boards[1],candidate,board_hint,added)
        before=proposal['owned_manufacturer_control'];a,z=before['native_scope'],child_scope['native_scope']
        require(before['net']==child_scope['net'] and before['manufacturer_role']==child_scope['manufacturer_role']
            and a['control_pad_uuid']==z['control_pad_uuid'] and a['retained_capture_uuids']==z['retained_capture_uuids']
            and a['manufacturer_sources']==z['manufacturer_sources']
            and (set(a['exclusive_material_uuids'])-cut)|added==set(z['exclusive_material_uuids']),
            'exact_original_control_leaf_capture_and_all_exclusive_material_must_be_reowned')
        parts=ordinary._partition(boards[0],time.monotonic()+10.,retired_uuids=cut)
        after=ordinary._partition(boards[1],time.monotonic()+10.,retained_keys=set().union(*parts))
        require(all(any(p<=q for q in after) for p in parts),'owned_control_span_lost_native_partition')
        current=debt.receive(source,candidate,board_hint=board_hint)
        require(current['ok'] and current['complete'],'owned_control_current_debt_regressed_or_unknown')
        require(epoch==force._code_identity() and families==[force._family(p,board_hint) for p in (source,candidate)]
            and proposal['authority_sha256']==force._hash(Path(__file__))
            and proposal['kernel_dependency_sha256']==force._hash(Path(kernel.__file__)),'owned_control_source_code_or_dependency_changed')
        result.update(ok=True,complete=True,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            retired_track_uuids=sorted(cut),added_native_uuids=sorted(added),exact_native_source_reconstruction=True,
            source_typed_control_and_exact_original_input_capture_reowned=True,all_surviving_native_partitions_preserved=True,
            manufacturer_control_current_unknown_not_invented=True,old_parts_force_planes_barrels_rules_budgets_and_widths_exact=True,
            whole_parent_current_receiving=current,centerline_removed_mm=(proposal['source_length_nm']-proposal['candidate_length_nm'])/1e6,
            native_custom_rules_fields_kelvin_ground_returns_pairs_stack_and_release_receiving_still_required=True)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
