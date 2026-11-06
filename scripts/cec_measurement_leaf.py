"""Source-owned thin measurement leaves, not force-net rip-up authority.

Infer a bounded endpoint-linear leaf from a manufacturer-typed measurement
land. Its first native junction is a fixed boundary. A replacement must keep
the land and boundary exact and cannot acquire any other same-net contact.
This proves a local topological scope even when global Kelvin/power release
evidence is incomplete; it does not qualify that incomplete evidence.
"""
import math
import time
import json
from pathlib import Path

import pcbnew
import cec_force_current as force
import cec_fr as fr
import cec_pair_semantics as semantics
import cec_device_power_roles as roles


def _xy(point):
    return tuple(int(v) for v in point)


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise ValueError('measurement_leaf_deadline')


def plan(board, pad_uuid, *, timeout_s=10., max_tracks=16, max_length_mm=24.):
    return _plan(board, pad_uuid, role='measurement', timeout_s=timeout_s,
        max_tracks=max_tracks, max_length_mm=max_length_mm)


def plan_with_auxiliary_strap(board,pad_uuid,*,timeout_s=10.,allow_source_reference_maps=False):
    """Two independently owned demands, not a mixed-width linear leaf."""
    import cec_measurement_auxiliary_cut as auxiliary
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.
            or type(allow_source_reference_maps) is not bool):
        raise ValueError('bounded_auxiliary_measurement_leaf_required')
    deadline=time.monotonic()+timeout_s
    strap=auxiliary.plan(board,pad_uuid,timeout_s=timeout_s,
        allow_source_reference_maps=allow_source_reference_maps)
    departure=_plan(board,pad_uuid,role='measurement',
        timeout_s=max(.001,deadline-time.monotonic()),max_tracks=16,max_length_mm=24.,
        source_auxiliary_strap=strap)
    if time.monotonic()>=deadline:raise ValueError('auxiliary_measurement_leaf_deadline')
    return departure,strap


def plan_ground(board, pad_uuid, *, timeout_s=10., max_tracks=16, max_length_mm=24.):
    """Actual manufacturer ground/reference departure, not whole-net rip-up.

    A moved device can leave several obsolete thin escape segments behind if
    only its first segment is retired. Derive their sole endpoint-linear
    ownership up to the FIRST actual mesh junction using the same strict
    native-contact proof. This grants no ground/current/fabrication waiver;
    every old component and surviving boundary still needs restoration.
    """
    return _plan(board, pad_uuid, role='ground_return', timeout_s=timeout_s,
        max_tracks=max_tracks, max_length_mm=max_length_mm)


def plan_source_class_ground(board,pad_uuid,*,timeout_s=10.,max_tracks=8,max_length_mm=12.):
    """Own a linear functional Ground lead at its EXACT saved class width.

    Separate from the legacy thin-leaf API: no raised thin-width cap, guessed
    load, barrel retirement or aggregate Ground-current credit. The Source
    must be saved/pristine, the actual same-face class must exactly match,
    and the unchanged exhaustive contact walk must end at retained material.
    Replacement, physical return, every old partition and original current
    receiving remain independently mandatory after the device pose.
    """
    from cec_route_dimensions import NetclassTable
    import cec_fab_profile as fab
    if (type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10.
            or type(max_tracks)is not int or not 1<=max_tracks<=8
            or type(max_length_mm)not in(int,float)or not math.isfinite(max_length_mm)
            or not 0<max_length_mm<=12.):
        raise ValueError('bounded_source_class_ground_leaf_required')
    deadline=time.monotonic()+timeout_s
    source=Path(board.GetFileName()).resolve()
    project=source.with_suffix('.kicad_pro')
    if not board.GetFileName() or source.suffix!='.kicad_pcb' or not source.is_file() or not project.is_file():
        raise ValueError('literal_saved_ground_leaf_project_required')
    saved_hash,project_hash=force._hash(source),force._hash(project)
    binding=_binding(board)
    if _binding(pcbnew.LoadBoard(str(source)))!=binding:
        raise ValueError('literal_saved_ground_leaf_native_source_required')
    found=[p for fp in board.GetFootprints()for p in fp.Pads()if force._uid(p)==pad_uuid]
    if len(found)!=1:raise ValueError('unique_native_source_ground_leaf_pad_required')
    pad=found[0]
    from cec_return_escape import smd_surface_layer
    face=smd_surface_layer(pad)
    if face is None:raise ValueError('native_surface_source_ground_leaf_required')
    spec=NetclassTable.from_board_path(source).resolve('GND') or {}
    authored=spec.get('track_width')
    per_face=(spec.get('track_width_by_layer_mm')or{}).get(fab.COPPER_LAYER_IDS[face],0.)
    if (type(authored)not in(int,float)or not math.isfinite(authored)or authored<=0
            or type(per_face)not in(int,float)or not math.isfinite(per_face)or per_face<0):
        raise ValueError('positive_literal_source_ground_leaf_class_required')
    width=max(int(board.GetDesignSettings().m_TrackMinWidth),math.ceil(authored*1e6),math.ceil(per_face*1e6))
    if not 0<width<=20000000:raise ValueError('bounded_literal_source_ground_leaf_class_required')
    authority=dict(source=str(source),source_sha256=saved_hash,project=str(project),
        project_sha256=project_hash,width_nm=width,layer_id=int(face),
        basis='literal_saved_source_ground_class',current_authority=False)
    q=_plan(board,pad_uuid,role='source_class_ground',timeout_s=max(.001,deadline-time.monotonic()),
        max_tracks=max_tracks,max_length_mm=max_length_mm,source_ground_class=authority)
    if (force._hash(source)!=saved_hash or force._hash(project)!=project_hash
            or _binding(board)!=binding or q['source_native_binding']!=binding or time.monotonic()>=deadline):
        raise ValueError('source_class_ground_leaf_identity_or_deadline_changed')
    return q


def plan_rated_supply(board, pad_uuid, *, board_hint, timeout_s=10.):
    """Exclusive tiny supply departure carrying the UNCHANGED full rail load.

    No per-IC guessed current, force-bus, via or group retirement permission.
    All old boundaries still require restoration and independent current
    receiving before an atomic placement transaction can be admitted.
    """
    import cec_decoupler_cell as cell
    q=_plan(board,pad_uuid,role='rated_supply',timeout_s=timeout_s,
        max_tracks=8,max_length_mm=8.)
    return _rated_small_supply(board,q,board_hint)


def plan_rated_bypass_supply(board,pad_uuid,*,board_hint,timeout_s=10.,moving_owner_ref=None):
    """The unique source-selected bypass owns its exclusive supply stub.

    This does not reduce the rail load to an assumed capacitor/IC current.
    Preserve every via, shared fork, grouped/wide edge and the real terminal
    boundary; a replacement still carries the unchanged FULL rail contract.
    """
    q=_plan(board,pad_uuid,role='rated_bypass_supply',timeout_s=timeout_s,
        max_tracks=8,max_length_mm=8.,board_hint=board_hint,moving_owner_ref=moving_owner_ref)
    return _rated_small_supply(board,q,board_hint)


def plan_bypass_ground(board,pad_uuid,*,board_hint,timeout_s=10.,moving_owner_ref=None):
    """Exclusive selected-cap ground stub, never its barrel or shared mesh."""
    return _plan(board,pad_uuid,role='bypass_ground',timeout_s=timeout_s,
        max_tracks=8,max_length_mm=8.,board_hint=board_hint,moving_owner_ref=moving_owner_ref)


def plan_missing_bypass_supply(board,pad_uuid,*,board_hint,missing_bypass_intent,timeout_s=10.):
    """Corrective missing-role supply leaf; never a fabricated old assignment."""
    deadline=time.monotonic()+timeout_s if type(timeout_s)in(int,float) else time.monotonic()
    q=_plan(board,pad_uuid,role='missing_bypass_supply',timeout_s=timeout_s,
        max_tracks=8,max_length_mm=8.,board_hint=board_hint,
        missing_bypass_intent=missing_bypass_intent)
    q=_rated_small_supply(board,q,board_hint)
    _tick(deadline)
    return q


def plan_missing_bypass_ground(board,pad_uuid,*,board_hint,missing_bypass_intent,timeout_s=10.):
    """Corrective missing-role exclusive Ground stub; no barrel ownership."""
    return _plan(board,pad_uuid,role='missing_bypass_ground',timeout_s=timeout_s,
        max_tracks=8,max_length_mm=8.,board_hint=board_hint,
        missing_bypass_intent=missing_bypass_intent)


def _missing_bypass_owner(board,pad,board_hint,intent,deadline,*,ground_return):
    import cec_missing_bypass_repair as repair
    source=Path(board.GetFileName()).resolve(strict=True)
    if _binding(board)!=_binding(pcbnew.LoadBoard(str(source))):
        raise ValueError('missing_bypass_leaf_requires_literal_unchanged_source')
    role=repair.plan(source,intent,board_hint=board_hint,
        timeout_s=max(.001,deadline-time.monotonic()))
    _tick(deadline)
    if (role.get('scope')!=repair.SCOPE or role.get('complete')is not True
            or role.get('role_only')is not True or role.get('admitted')is not False
            or role.get('source')!=str(source)or role.get('source_sha256')!=force._hash(source)
            or role.get('intent')!=intent or any(role.get(k)is not False
                for k in ('cut_authority','route_authority','current_authority'))):
        raise ValueError('fresh_exact_missing_bypass_role_required')
    req=role['requirement'];expected='GND'if ground_return else req['rail']
    records=[p for p in role['source_capacitor_ports']if p['uuid']==force._uid(pad)]
    if (len(records)!=1 or force._uid(pad.GetParentFootprint())!=intent['capacitor_uuid']
            or pad.GetNetname()!=expected or records[0]['net']!=expected
            or records[0]['at_nm']!=list(pad.GetPosition())
            or records[0]['pin']!=pad.GetNumber()
            or records[0]['layers']!=list(map(int,pad.GetLayerSet().CuStack()))):
        raise ValueError('exact_missing_bypass_source_capacitor_terminal_required')
    owner=board.FindFootprintByReference(req['ref'])
    owner_pad=owner.FindPadByNumber(str(req['pin']))if owner else None
    if (owner_pad is None or force._uid(owner_pad)!=intent['owner_pad_uuid']
            or owner_pad.GetNetname()!=req['rail']
            or list(owner_pad.GetPosition())!=role['source_owner_port']['at_nm']):
        raise ValueError('stationary_missing_bypass_owner_terminal_required')
    # Full raw export evidence remains available from repair.plan itself.
    # Leaf records are repeatedly recompiled and compared as complete values;
    # use its exact semantic replay policy, not a volatile generated-date hash.
    return repair._replay_identity(role)


def _rated_small_supply(board,q,board_hint):
    import cec_decoupler_cell as cell
    with force._thermal_hint(board_hint):
        rated=cell._supply_current_widths(board,q['net'])
    required=(rated or {}).get('required_by_layer_nm',{}).get(q['layer'])
    if required is None or not 0<required<=q['width_nm']<=350000:
        raise ValueError('positive_full_load_rated_small_supply_departure_required')
    q['unchanged_full_rail_current_contract']=rated
    return q


def plan_scalar_link(board, pad_uuid, *, owner_refs, timeout_s=10.,allow_owned_locked=False):
    """Exclusive output-to-input link wholly inside a moved owner group.

    Shared branches, fixed third-party contacts, pairs, force domains and
    locked copper never become retireable by this local signal policy.
    Both real endpoints must be manufacturer-typed, not just same-net pads.
    """
    if (type(owner_refs) not in (list, tuple, set) or not 2 <= len(set(owner_refs)) <= 8
            or type(allow_owned_locked) is not bool):
        raise ValueError('bounded_scalar_link_owner_group_required')
    q=_plan(board,pad_uuid,role='scalar_link',timeout_s=timeout_s,
        max_tracks=8,max_length_mm=8.)
    pads={force._uid(p):p for fp in board.GetFootprints() for p in fp.Pads()}
    if q['owner'] not in owner_refs or len(q['boundary_uuids'])!=1:
        raise ValueError('exclusive_moved_scalar_link_boundary_required')
    peer=pads.get(q['boundary_uuids'][0])
    model=roles.footprint_contract(peer.GetParentFootprint()) if peer else None
    if (not peer or not model or peer.GetParentFootprint().GetReference() not in owner_refs
            or peer.GetParentFootprint().GetReference()==q['owner']
            or model['pins'].get(peer.GetNumber())!='signal_input'
            or peer.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or peer.HasHole()
            or _xy(peer.GetPosition())!=tuple(q['points_nm'][-1])):
        raise ValueError('exclusive_moved_scalar_link_boundary_required')
    locked=sorted(force._uid(t) for t in board.GetTracks() if force._uid(t) in q['track_uuids'] and t.IsLocked())
    if locked and not allow_owned_locked:
        raise ValueError('locked_scalar_link_copper_retained')
    q['peer_pad_uuid']=force._uid(peer)
    if allow_owned_locked:
        q.update(allow_owned_locked=True,source_owned_locked_track_uuids=locked,
            exact_manufacturer_and_native_exclusive_link_scope_not_global_unlock=True)
    return q


def plan_scalar_input(board,pad_uuid,*,board_hint,timeout_s=10.,allow_owned_locked=False):
    """Own one manufacturer-defined scalar INPUT to its first real junction.

    Moving a comparator invalidates its threshold escape too, not just the
    output and measurement pair. This is neither an ordinary-net override
    nor a guessed GPIO mode. Power, current-monitor pairs, declared pairs,
    clocks/aggressors, grouped copper, interior taps and barrels stay outside.
    Sensitive field identity and the complete old boundary remain mandatory.
    """
    import cec_current_topology as topology
    import cec_field_coupling as field
    import cec_synth_pipeline as synth
    if (type(board_hint) is not str or not board_hint or type(allow_owned_locked) is not bool
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.):
        raise ValueError('explicit_typed_scalar_input_source_context_required')
    deadline=time.monotonic()+timeout_s
    if not board.GetFileName():raise ValueError('named_source_board_for_scalar_input_required')
    pads=[p for fp in board.GetFootprints() for p in fp.Pads() if force._uid(p)==pad_uuid]
    if len(pads)!=1:raise ValueError('unique_native_scalar_input_land_required')
    pad=pads[0];net=str(pad.GetNetname())
    with force._thermal_hint(board_hint):
        protected=set(topology.board_current_domains(board,board_hint))
        if synth.spec_net_current_contract(board_hint,net) is not None:protected.add(net)
    protected|=set(fr.coupled_pair_nets(board))
    protected|={n for q in semantics.analog_input_pairs(board) for n in (q['p'],q['n'])}
    protected|={str(z.GetNetname()) for z in board.Zones() if not z.GetIsRuleArea()}
    resolver=fr._project_netclass_resolver(str(board.GetFileName()),board=board)
    classification=field.classify_net(net,netclass=resolver(net))
    if (not net or net=='GND' or net in protected or classification['power'] or classification['aggressor']
            or str(pad.GetPinType()) in ('power_in','power_out')):
        raise ValueError('unprotected_source_scalar_input_required')
    remaining=deadline-time.monotonic()
    if remaining<=0:raise ValueError('typed_scalar_input_source_deadline')
    q=_plan(board,pad_uuid,role='scalar_input',timeout_s=remaining,max_tracks=8,max_length_mm=8.)
    live={force._uid(t):t for t in board.GetTracks()}
    if any(live[u].HasSolderMask() for u in q['track_uuids']):
        raise ValueError('scalar_input_native_process_reconstruction_required')
    locked=sorted(force._uid(t) for t in board.GetTracks() if force._uid(t) in q['track_uuids'] and t.IsLocked())
    if locked and not allow_owned_locked:raise ValueError('locked_scalar_input_copper_retained')
    q.update(source_field_classification=classification,source_board_hint=board_hint,
        signal_mode_high_impedance_or_current_assumed=False,sensitive_role_reclassification=False)
    if allow_owned_locked:q.update(allow_owned_locked=True,source_owned_locked_track_uuids=locked)
    if time.monotonic()>=deadline:raise ValueError('typed_scalar_input_source_deadline')
    return q


def _bypass_supply_owner(board,pad,board_hint,*,ground_return=False):
    import cec_constraints as constraints
    if type(board_hint) is not str or not board_hint:
        raise ValueError('source_bypass_board_authority_required')
    with force._thermal_hint(board_hint):
        assigned=constraints._device_bypass_assignment(board,project_max_mm=3.5)
    fp=pad.GetParentFootprint()
    selected=[q['requirement'] for q in assigned['assigned'].values() if q['cap_ref']==fp.GetReference()]
    if len(selected)!=1:raise ValueError('unique_source_selected_bypass_required')
    req=selected[0];owner=board.FindFootprintByReference(req['ref'])
    model=roles.footprint_contract(owner) if owner else None
    supply=owner.FindPadByNumber(str(req['pin'])) if owner else None
    if model and model['device_package']=='TPS2121 RUX'and model['pins'].get(str(req['pin']))=='power_output':
        import cec_source_supply_endpoint_cut as source_supply
        rail_pads=[p for p in fp.Pads()if p.GetNetname()==req['rail']]
        if len(rail_pads)!=1 or pad.GetNetname()!=('GND'if ground_return else req['rail']):
            raise ValueError('exact_source_mux_bypass_terminal_required')
        return source_supply.output_bypass_owner(board,rail_pads[0],board_hint)
    if (not model or not supply or model['pins'].get(str(req['pin']))!='power_input'
            or len(list(fp.Pads()))!=2 or fp.IsFlipped()!=owner.IsFlipped()
            or any(p.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for p in fp.Pads())
            or supply.HasHole() or supply.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
            or pad.GetNetname()!=('GND' if ground_return else req['rail'])
            or supply.GetNetname()!=req['rail']
            or (req.get('return_rail') or 'GND')!='GND'
            or {str(p.GetNetname()) for p in fp.Pads()}!={'GND',req['rail']}
            or math.dist(_xy(next(p for p in fp.Pads() if p.GetNetname()==req['rail']).GetPosition()),
                _xy(supply.GetPosition()))>3500000):
        raise ValueError('positive_local_bypass_supply_ownership_required')
    return dict(cap_ref=fp.GetReference(),owner=req['ref'],supply_pin=str(req['pin']),
        rail=req['rail'],manufacturer_source=model['source'])


def _plan(board, pad_uuid, *, role, timeout_s, max_tracks, max_length_mm,board_hint=None,
          moving_owner_ref=None, explicit_shunt_binding=None, source_auxiliary_strap=None,
          source_ground_class=None,missing_bypass_intent=None):
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10 or type(max_tracks) is not int
            or not 1 <= max_tracks <= 16 or not math.isfinite(max_length_mm)
            or not 0 < max_length_mm <= 24):
        raise ValueError('invalid_measurement_leaf_bounds')
    deadline = time.monotonic() + timeout_s
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    selected = [p for p in pads if force._uid(p) == pad_uuid]
    if len(selected) != 1:
        raise ValueError('measurement_land_identity_unknown')
    pad = selected[0]
    from cec_return_escape import smd_surface_layer
    surface=smd_surface_layer(pad)
    contract = semantics.footprint_input_contract(pad.GetParentFootprint())
    manufacturer = roles.footprint_contract(pad.GetParentFootprint())
    if role=='source_class_ground':
        manufacturer=manufacturer or roles.passive_steering_protector_contract(pad.GetParentFootprint())
        if (type(source_ground_class)is not dict or source_ground_class.get('current_authority')is not False
                or source_ground_class.get('basis')!='literal_saved_source_ground_class'):
            raise ValueError('positive_saved_source_ground_leaf_authority_required')
    elif source_ground_class is not None:
        raise ValueError('source_ground_class_cannot_retype_another_leaf')
    bypass=_bypass_supply_owner(board,pad,board_hint,ground_return=role=='bypass_ground') \
        if role in ('rated_bypass_supply','bypass_ground') else None
    missing_bypass=None
    if role in ('missing_bypass_supply','missing_bypass_ground'):
        missing_bypass=_missing_bypass_owner(board,pad,board_hint,missing_bypass_intent,deadline,
            ground_return=role=='missing_bypass_ground')
    elif missing_bypass_intent is not None:
        raise ValueError('missing_bypass_intent_cannot_retype_another_leaf')
    explicit_shunt=None
    if role=='explicit_shunt_supply':
        import cec_explicit_shunt_leaf as shunt
        explicit_shunt=shunt.contract(board,explicit_shunt_binding)
        if explicit_shunt_binding['support_pad_uuid']!=pad_uuid:
            raise ValueError('explicit_shunt_source_land_mismatch')
    elif explicit_shunt_binding is not None:
        raise ValueError('explicit_shunt_binding_cannot_retype_measurement')
    resistive=None
    if role=='resistive_monitor':
        import cec_resistive_monitor_branch as taps
        resistive=taps.source_contract(board,pad_uuid,deadline=deadline)
    typed = bool(explicit_shunt or resistive or bypass or missing_bypass or manufacturer and (
        (role == 'measurement' and contract
            and manufacturer['pins'].get(str(pad.GetNumber())) == 'measurement'
            and str(pad.GetNumber()) in contract[1])
        or (role == 'ground_return' and pad.GetNetname() == 'GND'
            and manufacturer['pins'].get(str(pad.GetNumber())) in ('ground', 'reference', 'power_return'))
        or (role=='source_class_ground' and pad.GetNetname()=='GND'
            and manufacturer['pins'].get(str(pad.GetNumber()))=='ground'
            and not set(manufacturer['pins'].values())&{'power_output','switch','feedback'})
        or (role == 'rated_supply' and pad.GetNetname() != 'GND'
            and manufacturer['pins'].get(str(pad.GetNumber())) == 'power_input')
        or (role == 'scalar_link' and pad.GetNetname() != 'GND'
            and manufacturer['pins'].get(str(pad.GetNumber())) == 'signal_output')
        or (role == 'scalar_input' and pad.GetNetname() != 'GND'
            and manufacturer['pins'].get(str(pad.GetNumber())) == 'signal_input')))
    if (not typed
            or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or pad.HasHole()
            or pad.GetNetCode() <= 0 or surface is None):
        raise ValueError('manufacturer_typed_surface_measurement_land_required')
    resolved_ground=[];cohort_retired=set()
    if source_auxiliary_strap is not None:
        import cec_measurement_auxiliary_cut as auxiliary
        if (role!='measurement' or auxiliary.plan(board,pad_uuid,
                timeout_s=max(.001,deadline-time.monotonic()),
                allow_source_reference_maps='source_reference_map' in source_auxiliary_strap)!=source_auxiliary_strap):
            raise ValueError('exact_source_owned_auxiliary_measurement_strap_required')
        cohort_retired.update(source_auxiliary_strap['track_uuids'])
    if moving_owner_ref is not None:
        if (role not in ('bypass_ground','rated_bypass_supply') or type(moving_owner_ref) is not str
                or not moving_owner_ref or moving_owner_ref!=bypass['owner']):
            raise ValueError('actual_selected_moving_bypass_owner_required')
        owner=board.FindFootprintByReference(moving_owner_ref)
        model=roles.footprint_contract(owner)
        for owner_pad in owner.Pads():
            _tick(deadline)
            if role=='bypass_ground':
                if (owner_pad.GetNetname()!='GND' or model['pins'].get(owner_pad.GetNumber())
                        not in ('ground','reference','power_return')):continue
            elif (owner_pad.GetNetname()!=bypass['rail']
                    or owner_pad.GetNumber()!=bypass['supply_pin']
                    or model['pins'].get(owner_pad.GetNumber())!='power_input'):continue
            try:
                # Retype the actual incoming owner departure independently.
                # A cap's two root contacts are not arbitrary mesh rip-up:
                # only a positively owned moving-device leaf terminating on
                # this EXACT selected capacitor land may leave this view.
                owned=(plan_ground(board,force._uid(owner_pad),
                    timeout_s=max(.001,deadline-time.monotonic())) if role=='bypass_ground' else
                    plan_rated_supply(board,force._uid(owner_pad),board_hint=board_hint,
                        timeout_s=max(.001,deadline-time.monotonic())))
            except ValueError:continue  # Unknown contact remains an obstacle.
            if pad_uuid not in owned['boundary_uuids']:continue
            resolved_ground.append(owned);cohort_retired.update(owned['track_uuids'])
    grouped = {force._uid(i) for g in board.Groups() for i in g.GetItems()}
    material = [t for t in board.GetTracks() if force._uid(t) not in cohort_retired]
    touching = [t for t in material if t.GetNetCode() == pad.GetNetCode()
        and t.IsOnLayer(surface)
        and t.GetEffectiveShape(surface).Collide(pad.GetEffectiveShape(surface), 0)]
    if role in ('ground_return','source_class_ground','rated_supply','rated_bypass_supply','bypass_ground',
            'missing_bypass_supply','missing_bypass_ground','explicit_shunt_supply'):
        # An immediate dogbone barrel may overlap the end of a long land.
        # It is a retained boundary, not a second retireable departure.
        # The exhaustive native-contact walk below still rejects a barrel
        # at the root or an unowned interior tap; no via can enter chosen.
        touching = [t for t in touching if t.GetClass()!='PCB_VIA']
    if not touching or len(touching) > max_tracks or any(t.GetClass() != 'PCB_TRACK' for t in touching):
        raise ValueError('unique_linear_measurement_departure_required')
    # Several centreline segments can occupy ONE elongated land. They are
    # not separate departures when they form a single, exact endpoint chain
    # with one interior root and one exterior exit. Keep all the ordinary
    # native-contact/fork/group/width checks below; no area-based ownership.
    adjacency = {}
    for track in touching:
        if (track.GetLayer() != surface or force._uid(track) in grouped
                or track.GetWidth() != touching[0].GetWidth()):
            raise ValueError('unique_linear_measurement_departure_required')
        for endpoint in (_xy(track.GetStart()), _xy(track.GetEnd())):
            adjacency.setdefault(endpoint, []).append(track)
    terminals = [point for point, tracks in adjacency.items() if len(tracks) == 1]
    roots = [point for point in terminals
        if pad.GetEffectiveShape(surface).Collide(pcbnew.VECTOR2I(*point), 0)]
    if (len(terminals) != 2 or len(roots) != 1 or any(len(tracks) > 2 for tracks in adjacency.values())
            or len(adjacency) != len(touching)+1):
        raise ValueError('unique_linear_measurement_departure_required')
    pending = [roots[0]]; seen_points = set(); seen_tracks = set()
    while pending:
        point = pending.pop()
        if point in seen_points:
            continue
        seen_points.add(point)
        for track in adjacency[point]:
            ends = (_xy(track.GetStart()), _xy(track.GetEnd()))
            if ends[0] == ends[1]:
                raise ValueError('unique_linear_measurement_departure_required')
            seen_tracks.add(force._uid(track)); pending.extend(ends)
    if len(seen_tracks) != len(touching):
        raise ValueError('unique_linear_measurement_departure_required')
    first = adjacency[roots[0]][0]
    layer, width = first.GetLayer(), int(first.GetWidth())
    if role=='source_class_ground':
        if width!=source_ground_class['width_nm'] or int(layer)!=source_ground_class['layer_id']:
            raise ValueError('ground_leaf_width_must_equal_actual_saved_source_class')
    elif not 0 < width <= 350000:
        raise ValueError('thin_measurement_leaf_required')
    endpoints = [_xy(first.GetStart()), _xy(first.GetEnd())]
    starts = [roots[0]]
    if roots[0] not in endpoints:
        raise ValueError('measurement_leaf_needs_one_interior_land_endpoint')
    points, chosen, length = [starts[0]], [], 0.
    current = first
    boundary = []
    while True:
        _tick(deadline)
        if (current.GetClass() != 'PCB_TRACK' or force._uid(current) in grouped
                or current.GetLayer() != layer or current.GetWidth() != width
                or force._uid(current) in chosen):
            raise ValueError('nonuniform_grouped_or_cyclic_measurement_leaf')
        ends = [_xy(current.GetStart()), _xy(current.GetEnd())]
        if points[-1] not in ends or ends[0] == ends[1]:
            raise ValueError('measurement_leaf_not_endpoint_linear')
        far = ends[1] if ends[0] == points[-1] else ends[0]
        chosen.append(force._uid(current))
        points.append(far)
        length += current.GetLength() / 1e6
        if len(chosen) > max_tracks or length > max_length_mm:
            raise ValueError('measurement_leaf_scope_bound')
        # Every same-net native contact must be an endpoint contact. Interior
        # taps and same-net filled zones cannot be reclassified as thin leaves.
        contacts = []
        for other in [*pads, *material, *[z for z in board.Zones() if not z.GetIsRuleArea()]]:
            _tick(deadline)
            uid = force._uid(other)
            if (uid in chosen or uid == pad_uuid or other.GetNetCode() != pad.GetNetCode()
                    or not other.IsOnLayer(layer)):
                continue
            if other.GetClass() == 'ZONE' and not other.IsFilled():
                raise ValueError('same_net_zone_material_unknown')
            shape = (other.GetFilledPolysList(layer) if other.GetClass() == 'ZONE'
                else other.GetEffectiveShape(layer))
            if not shape.Collide(current.GetEffectiveShape(layer), 0):
                continue
            # Authored round track ends can overlap electrically even when
            # their centreline endpoints differ. Retain that actual native
            # boundary; do not invent an airwire or traverse/retire the peer.
            at_far = shape.Collide(pcbnew.SHAPE_SEGMENT(
                pcbnew.VECTOR2I(*far), pcbnew.VECTOR2I(*far), width), 0)
            if not at_far:
                raise ValueError('measurement_leaf_has_unowned_interior_contact:'
                    + force._uid(current) + ':' + uid + ':' + other.GetClass())
            contacts.append(other)
        if (len(contacts) != 1 or contacts[0].GetClass() != 'PCB_TRACK'
                or contacts[0].GetLayer() != layer or contacts[0].GetWidth() != width
                or force._uid(contacts[0]) in grouped or far not in (
                    _xy(contacts[0].GetStart()), _xy(contacts[0].GetEnd()))):
            if not contacts:
                raise ValueError('measurement_leaf_fixed_native_boundary_missing')
            boundary = sorted(force._uid(i) for i in contacts)
            break
        current = contacts[0]
    result=dict(schema=1, scope={'measurement':'source_typed_thin_measurement_leaf',
            'ground_return':'source_typed_thin_device_ground_leaf',
            'source_class_ground':'source_typed_full_saved_class_device_ground_leaf',
            'rated_supply':'source_typed_full_load_rated_supply_leaf',
            'rated_bypass_supply':'source_typed_full_load_rated_bypass_supply_leaf',
            'bypass_ground':'source_typed_thin_bypass_ground_leaf',
            'missing_bypass_supply':'source_corrective_missing_bypass_full_load_supply_leaf',
            'missing_bypass_ground':'source_corrective_missing_bypass_thin_ground_leaf',
            'explicit_shunt_supply':'explicit_shunt_source_leaf_retirement_only',
            'scalar_link':'source_typed_exclusive_moved_scalar_link',
            'scalar_input':'source_typed_thin_scalar_input_leaf',
            'resistive_monitor':'source_typed_bounded_resistive_voltage_monitor'}[role],
        pad_uuid=pad_uuid, device=contract[0] if role == 'measurement' else
            'explicit-native-shunt' if explicit_shunt else
            'source-corrective-missing-bypass' if missing_bypass else
            'source-selected-bypass' if bypass else 'selected-resistive-monitor' if resistive else manufacturer['device_package'],
        owner=pad.GetParentFootprint().GetReference(),
        pin=str(pad.GetNumber()), net=str(pad.GetNetname()), layer=layer, width_nm=width,
        track_uuids=chosen, points_nm=[list(p) for p in points],
        boundary_uuids=boundary, source_length_mm=length,
        source_boundary_entry_nm=[list(p) for p in points[-2:]],
        source_native_binding=_binding(board), release_authority=False,
        current_authority=False, kelvin_qualified=False)
    if source_ground_class is not None:result['source_ground_class_authority']=source_ground_class
    if bypass:result['source_selected_bypass']=bypass
    if missing_bypass:result['source_missing_bypass_repair']=missing_bypass
    if source_auxiliary_strap is not None:
        result['separately_owned_source_auxiliary_strap']=source_auxiliary_strap
    if moving_owner_ref is not None:
        result['source_resolved_moving_owner_ground_leaves' if role=='bypass_ground'
            else 'source_resolved_moving_owner_supply_leaves']=resolved_ground
    if resistive:result['source_resistive_monitor_contract']=resistive
    return result


def _binding(board):
    from cec_cell_row_rebuild import _source_binding
    return _source_binding(board)


def _source_boundary_kernel(proposal):
    """Existing source contact aperture, not a whole same-net landing waiver.

    Orthogonal/offset round track ends can overlap outside a circle centred
    on their shared endpoint. A circle-only guard even rejected replaying the
    *original* T junction. Keep the original last retired edge's narrow copper
    envelope at named retained boundaries. A new route may not touch any
    other part of those tracks/zones or acquire any other same-net object.
    Independent receiving derives this entry again from the immutable parent;
    a worker's packet is not authority to enlarge the aperture.
    """
    from shapely.geometry import LineString
    entry = proposal.get('source_boundary_entry_nm')
    if (type(entry) is not list or len(entry) != 2
            or any(type(p) is not list or len(p) != 2
                or any(type(v) is not int or abs(v) > 2_000_000_000 for v in p) for p in entry)
            or entry[0] == entry[1]
            or entry[1] != proposal['points_nm'][-1]
            or type(proposal.get('width_nm')) is not int
            or not 0 < proposal['width_nm'] <= 350000):
        raise ValueError('exact_source_boundary_entry_required')
    return LineString(entry).buffer(proposal['width_nm']/2+1002, quad_segs=64)


def _native_boundary_contact_kernel(proposal, pads, root, work):
    """Keep the exact Source junction, plus its actual fixed land interior.

    A terminal can already contain a retained track and filled force zone.
    Changing the approach angle at the SAME fixed endpoint must not be
    mistaken for acquiring those conductors elsewhere. Only named Source
    boundary objects benefit, and only inside a named same-face/net land
    which conservatively contains the whole endpoint capsule. Unlisted
    contacts, the rest of a zone, and a pad's empty bounding-box corners
    remain forbidden. This grants no retirement, force or Kelvin credit.
    Saved receiving still independently rederives the complete Source leaf.
    """
    from shapely.geometry import Point
    import cec_kelvin_copper_cut as cut
    kernel = _source_boundary_kernel(proposal)
    endpoint = Point(proposal['points_nm'][-1]).buffer(
        proposal['width_nm']/2+1001, quad_segs=64)
    for pad in pads:
        work.tick()
        if (force._uid(pad) not in proposal['boundary_uuids']
                or pad.GetNetCode() != root.GetNetCode()
                or not pad.IsOnLayer(proposal['layer'])):
            continue
        # Use the native ERROR_INSIDE core itself, not a bounding box or an
        # outward tolerance. Eroding a rectangular land by the general
        # boolean guard would incorrectly leave a 1um strip where a named
        # Source zone terminates EXACTLY at the pad's integer edge. Require
        # exact convex half-plane containment of the returned core instead;
        # unsupported/concave pads retain the old narrow junction aperture.
        native = pcbnew.SHAPE_POLY_SET()
        pad.TransformShapeToPolygon(native, proposal['layer'], 0, cut.ERROR_NM,
            pcbnew.ERROR_INSIDE, False)
        interior = cut._poly(native, work)
        if not cut._convex_core_contained(native, [], work, returned_geometry=interior):
            continue
        if interior.covers(endpoint):
            kernel = kernel.union(interior)
    return kernel


def menus(proposal, *, max_paths=96, offset_mm=4., avoid=None):
    """Finite orthogonal detours in the source-local domain, not no-path proof."""
    if (type(max_paths) is not int or not 1 <= max_paths <= 96
            or not math.isfinite(offset_mm) or not 0 < offset_mm <= 6):
        raise ValueError('invalid_measurement_detour_menu')
    a, b = [tuple(p) for p in (proposal['points_nm'][0], proposal['points_nm'][-1])]
    source = proposal['points_nm']
    bound = round(offset_mm * 1e6)
    xs = {a[0], b[0]}
    ys = {a[1], b[1]}
    for point in source:
        for step in (250000, 500000, 1000000, 1500000, 2000000, bound):
            if step <= bound:
                xs.update((point[0]-step, point[0]+step))
                ys.update((point[1]-step, point[1]+step))
    paths = [[a, (a[0], b[1]), b], [a, (b[0], a[1]), b]]
    paths += [[a, (x, a[1]), (x, b[1]), b] for x in sorted(xs)]
    paths += [[a, (a[0], y), (b[0], y), b] for y in sorted(ys)]
    source_x = sorted({p[0] for p in source})
    source_y = sorted({p[1] for p in source})
    paths += [[a, (x, a[1]), (x, y), (b[0], y), b] for x in source_x for y in sorted(ys)]
    paths += [[a, (a[0], y), (x, y), (x, b[1]), b] for y in source_y for x in sorted(xs)]
    # Two independent obstacle faces can require changing BOTH the cross
    # channel and the final approach. One-axis menus only reproduce a corner
    # that remains blocked, even when a short source-local dogleg exists.
    # The source has at most sixteen edges. This finite Cartesian tier is
    # bounded before the unchanged clearance/owned-contact receiver. Include
    # both departure orientations so rotation cannot remove a legal channel.
    paths += [[a, (a[0], y), (x, y), (x, b[1]), b]
        for y in sorted(ys) for x in sorted(xs)]
    paths += [[a, (x, a[1]), (x, y), (b[0], y), b]
        for x in sorted(xs) for y in sorted(ys)]
    unique = {}
    for path in paths:
        clean = [path[0]]
        backtrack = False
        for point in path[1:]:
            if point != clean[-1]:
                clean.append(point)
            # Different cross-axis samples can describe the same straight
            # route with extra vertices. Fund the physical path once, not
            # many collinear representations of the shortest blocked path.
            while len(clean) >= 3:
                p, q, r = clean[-3:]
                u = (q[0]-p[0], q[1]-p[1]); v = (r[0]-q[0], r[1]-q[1])
                if u[0]*v[1] != u[1]*v[0]:
                    break
                if u[0]*v[0]+u[1]*v[1] < 0:
                    backtrack = True
                    break
                clean.pop(-2)
        if backtrack or len(set(clean)) != len(clean):
            continue
        length = sum(math.dist(p, q) for p, q in zip(clean, clean[1:])) / 1e6
        if length > _replacement_length_basis_mm(proposal) + 2*offset_mm:
            continue
        if avoid is not None:
            from shapely.geometry import LineString
            if LineString(clean).buffer(proposal['width_nm']/2+1000).intersects(avoid):
                continue
        unique[tuple(clean)] = length
    return [list(path) for path in sorted(unique, key=lambda p: (unique[p], p))[:max_paths]]


def _replacement_length_basis_mm(proposal):
    """Finite search allowance for the ACTUAL, possibly moved endpoints.

    The historical source length remains immutable evidence, not a length
    rating rewritten after IC motion. A placement proposal can increase the
    direct distance beyond that length. Its bounded replacement search must
    start at least at that new geometric lower bound, as the multilayer leaf
    producer already does. Final electrical/pose/whole-board gates still decide
    whether the longer route is acceptable; this helper grants no such credit.
    Stationary source leaves retain their old allowance exactly.
    """
    points=proposal['points_nm']
    return max(float(proposal['source_length_mm']),math.dist(points[0],points[-1])/1e6)


class _CompiledPathGuard:
    """Ephemeral exact source-minus-leaf snapshot, never worker authority."""
    def __init__(self,board,proposal,avoid,deadline):
        from shapely.ops import unary_union
        from shapely.prepared import prep
        import cec_kelvin_copper_cut as cut
        self.board=board
        self.proposal_identity=json.dumps(proposal,sort_keys=True)
        self.binding=_binding(board)
        self.avoid_identity=None if avoid is None else avoid.wkb
        self.foreign_cache={};self.material=[]
        present={force._uid(t) for t in board.GetTracks()}
        if present & set(proposal['track_uuids']):
            raise ValueError('source_leaf_not_privately_retired')
        pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
        matching=[p for p in pads if force._uid(p)==proposal['pad_uuid']]
        if len(matching)!=1:raise ValueError('exact_measurement_land_missing')
        pad=matching[0];layer=proposal['layer'];width=proposal['width_nm']
        work=cut._Work(deadline)
        land=cut._shape(pad,layer,True,work).buffer(width/2+1002)
        junction=_native_boundary_contact_kernel(proposal,pads,pad,work)
        objects=[*pads,*board.GetTracks(),*[z for z in board.Zones() if not z.GetIsRuleArea()]]
        if len(objects)>8192:raise ValueError('bounded_measurement_contact_inventory_required')
        for other in objects:
            _tick(deadline)
            if other.GetNetCode()!=pad.GetNetCode() or not other.IsOnLayer(layer):continue
            if other.GetClass()=='ZONE' and not other.IsFilled():
                raise ValueError('same_net_zone_material_unknown')
            shape=(cut._poly(other.GetFilledPolysList(layer),work)
                if other.GetClass()=='ZONE' else cut._shape(other,layer,True,work))
            uid=force._uid(other)
            permitted=land if uid==proposal['pad_uuid'] else (
                shape.buffer(width/2+1002) if uid in proposal['boundary_uuids']
                    and other.GetClass()=='PAD' else
                junction if uid in proposal['boundary_uuids'] else None)
            blocked=shape if permitted is None else shape.difference(permitted)
            if not blocked.is_empty:self.material.append((uid,other.GetClass(),blocked))
        self.forbidden_geometry=unary_union([s for _,_,s in self.material])
        self.forbidden=prep(self.forbidden_geometry)
        hints=[]
        for shape in [*[s for _,_,s in self.material],*([avoid] if avoid is not None else [])]:
            for part in cut._parts(shape.buffer(width/2+1000,join_style=2)):
                if not part.is_empty:hints.append(tuple(part.bounds))
        end=proposal['points_nm'][-1]
        self.centerline_boxes=tuple(sorted(set(hints),key=lambda b:(
            ((b[0]+b[2])/2-end[0])**2+((b[1]+b[3])/2-end[1])**2,b))[:64])
        if _binding(board)!=self.binding:raise ValueError('measurement_guard_source_changed_during_compile')
        _tick(deadline)

    def check_binding(self,board,proposal,avoid):
        if (board is not self.board
                or json.dumps(proposal,sort_keys=True)!=self.proposal_identity
                or (None if avoid is None else avoid.wkb)!=self.avoid_identity
                or _binding(board)!=self.binding):
            raise ValueError('compiled_measurement_guard_source_or_policy_changed')


def compile_path_guard(board,proposal,*,avoid=None,timeout_s=10.):
    """Keep exact native contact geometry warm for ONE immutable local trial.

    Failed menu queries need not repeatedly polygonize every same-net pour.
    Source/proposal/avoid identity is rechecked before each use. Construction
    and saved-board receiving still use independent fresh native geometry.
    """
    if proposal.get('scope')=='explicit_shunt_source_leaf_retirement_only':
        raise ValueError('explicit_shunt_requires_separate_full_rated_reconstruction')
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10):raise ValueError('bounded_measurement_guard_compile_required')
    return _CompiledPathGuard(board,proposal,avoid,time.monotonic()+timeout_s)


def path_clear(board, proposal, points, *, avoid=None, timeout_s=10., diagnostics=None,
               _compiled_guard=None):
    """Actual foreign clearance and no acquired same-net material contact.

    Source leaf items must be absent. Only the exact source land and first
    source junction are allowed native contacts, within bounded endpoint
    kernels. A trace passing through the interior of a same-net force bus is
    refused even though ordinary foreign-net clearance would allow it.
    """
    if proposal.get('scope')=='explicit_shunt_source_leaf_retirement_only':
        raise ValueError('explicit_shunt_requires_separate_full_rated_reconstruction')
    from shapely.geometry import LineString
    import cec_kelvin_copper_cut as cut
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10 or not 2 <= len(points) <= 17):
        raise ValueError('invalid_measurement_detour_bounds')
    deadline = time.monotonic()+timeout_s
    if _compiled_guard is not None:
        if type(_compiled_guard) is not _CompiledPathGuard:
            raise ValueError('native_compiled_measurement_guard_required')
        _compiled_guard.check_binding(board,proposal,avoid)
    def refuse(reason, **details):
        if diagnostics is not None:
            diagnostics.update(ok=False, reason=reason, **details)
        return False
    if (list(points[0]) != proposal['points_nm'][0]
            or list(points[-1]) != proposal['points_nm'][-1]):
        return refuse('source_boundary_endpoint_changed')
    if any(a == b or (a[0] != b[0] and a[1] != b[1] and abs(a[0]-b[0]) != abs(a[1]-b[1]))
            for a, b in zip(points, points[1:])):
        return refuse('non_octilinear_or_zero_length_leg')
    present = {force._uid(t) for t in board.GetTracks()}
    if present & set(proposal['track_uuids']):
        raise ValueError('source_leaf_not_privately_retired')
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    pad = next(p for p in pads
        if force._uid(p) == proposal['pad_uuid'])
    layer, width, net = proposal['layer'], proposal['width_nm'], pad.GetNetCode()
    gap = max(int(board.GetDesignSettings().m_MinClearance), 200000)
    cache = {} if _compiled_guard is None else _compiled_guard.foreign_cache
    for index, (a, b) in enumerate(zip(points, points[1:])):
        _tick(deadline)
        a, b = pcbnew.VECTOR2I(*a), pcbnew.VECTOR2I(*b)
        if not fr._edge_leg_clear(board, a, b, width/2+gap):
            return refuse('native_edge_clearance', leg=index)
        if not fr._tap_foreign_clear(board, a, b, width, layer, gap, {net}, foreign_cache=cache):
            blockers = []
            if diagnostics is not None:
                zones, copper = fr._layer_foreign_shapes(board, layer, {net}, identified=True)
                segment = pcbnew.SHAPE_SEGMENT(a, b, width)
                for shape, _, identity, local_gap in [*zones, *copper]:
                    _tick(deadline)
                    if shape.Collide(segment, max(gap, local_gap)):
                        blockers.append(identity)
                        if len(blockers) >= 8:
                            break
            return refuse('native_foreign_copper_or_rule_area', leg=index, blockers=blockers)
    work = cut._Work(deadline)
    # An outward-inflated high-resolution capsule bounds the actual round
    # native track, rather than using an inscribed GEOS buffer as a proof.
    body = LineString(points).buffer(width/2+1000, quad_segs=64)
    if avoid is not None and body.intersects(avoid):
        return refuse('reserved_local_supply_or_reference_path')
    if _compiled_guard is not None:
        if _compiled_guard.forbidden.intersects(body):
            uid,kind,_=next(row for row in _compiled_guard.material if row[2].intersects(body))
            return refuse('unowned_same_net_contact',uuid=uid,kind=kind,
                net=str(pad.GetNetname()),permitted_boundary=uid in proposal['boundary_uuids'])
        _compiled_guard.check_binding(board,proposal,avoid);_tick(deadline)
        if diagnostics is not None:diagnostics.update(ok=True)
        return True
    land_kernel = cut._shape(pad, layer, True, work).buffer(width/2+1002)
    junction_kernel = _native_boundary_contact_kernel(proposal,pads,pad,work)
    for other in [*pads,
                  *board.GetTracks(), *[z for z in board.Zones() if not z.GetIsRuleArea()]]:
        _tick(deadline)
        if other.GetNetCode() != net or not other.IsOnLayer(layer):
            continue
        if other.GetClass() == 'ZONE' and not other.IsFilled():
            raise ValueError('same_net_zone_material_unknown')
        shape = (cut._poly(other.GetFilledPolysList(layer), work)
            if other.GetClass() == 'ZONE' else cut._shape(other, layer, True, work))
        overlap = body.intersection(shape)
        if overlap.is_empty:
            continue
        uid = force._uid(other)
        permitted = land_kernel if uid == proposal['pad_uuid'] else (
            shape.buffer(width/2+1002) if uid in proposal['boundary_uuids']
                and other.GetClass() == 'PAD' else
            junction_kernel if uid in proposal['boundary_uuids'] else None)
        if permitted is None or not overlap.difference(permitted).is_empty:
            return refuse('unowned_same_net_contact', uuid=uid, kind=other.GetClass(),
                          net=str(other.GetNetname()), permitted_boundary=permitted is not None)
    if diagnostics is not None:
        diagnostics.update(ok=True)
    return True


def add_path(board, proposal, points):
    if proposal.get('scope')=='explicit_shunt_source_leaf_retirement_only':
        raise ValueError('explicit_shunt_requires_separate_full_rated_reconstruction')
    pad = next(p for fp in board.GetFootprints() for p in fp.Pads()
        if force._uid(p) == proposal['pad_uuid'])
    result = []
    for a, b in zip(points, points[1:]):
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I(*a)); track.SetEnd(pcbnew.VECTOR2I(*b))
        track.SetWidth(proposal['width_nm']); track.SetLayer(proposal['layer'])
        track.SetNetCode(pad.GetNetCode()); track.SetLocked(True)
        board.Add(track); result.append(track)
    return result


def search(board, proposal, *, avoid=None, timeout_s=2.):
    """Use the existing native maze without relaxing owned-contact guards.

    The source leaf is privately absent. Snapshot forbidden same-net material
    once for this immutable trial; preserve the native foreign/edge/rule-area
    guards for every hop. A finite failure is not a no-path proof.
    """
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    from shapely.prepared import prep
    import cec_kelvin_copper_cut as cut
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10):
        raise ValueError('invalid_measurement_maze_budget')
    started = time.monotonic(); deadline = started+timeout_s
    if set(proposal['track_uuids']) & {force._uid(t) for t in board.GetTracks()}:
        raise ValueError('source_leaf_not_privately_retired')
    pad = next(p for fp in board.GetFootprints() for p in fp.Pads()
        if force._uid(p) == proposal['pad_uuid'])
    layer, width, net = proposal['layer'], proposal['width_nm'], pad.GetNetCode()
    compiled=compile_path_guard(board,proposal,avoid=avoid,
        timeout_s=max(.001,deadline-time.monotonic()))
    blocked=[compiled.forbidden_geometry]
    if avoid is not None:
        blocked.append(avoid)
    forbidden = prep(unary_union(blocked))
    counters = dict(guarded_hops=0, refused_owned_or_reserved_hops=0)
    def guard(a, b, half_width):
        _tick(deadline)
        counters['guarded_hops'] += 1
        if forbidden.intersects(LineString([tuple(a), tuple(b)]).buffer(
                half_width+1000, quad_segs=64)):
            counters['refused_owned_or_reserved_hops'] += 1
            return False
        return fr._edge_leg_clear(board, a, b, half_width+200000)
    search_diagnostics={}
    def validate(rows):
        points=[_xy(rows[0][0]),*[_xy(row[1]) for row in rows]]
        if len(points)>8:return False
        return path_clear(board,proposal,points,avoid=avoid,
            timeout_s=max(.001,min(10.,deadline-time.monotonic())),_compiled_guard=compiled)
    legs = fr._guarded_profiled_lastmile_legs(board,
        pcbnew.VECTOR2I(*proposal['points_nm'][0]), pcbnew.VECTOR2I(*proposal['points_nm'][-1]),
        width, layer, max(int(board.GetDesignSettings().m_MinClearance), 200000), net, guard,
        allow_maze=True,maze_margin_mm=4.,foreign_cache={},deadline_monotonic=deadline,
        max_length_nm=round((_replacement_length_basis_mm(proposal)+8)*1e6),refine_maze=True,
        endpoint_detail_grid_mm=.2,
        refinement_grids_mm=(.25,.125),
        centerline_obstacle_boxes=compiled.centerline_boxes,
        path_validator=validate,search_diagnostics=search_diagnostics)
    points = None
    validation = {}
    if legs:
        points = [_xy(legs[0][0]), *[_xy(row[1]) for row in legs]]
        if len(points) > 8:
            validation = dict(ok=False, reason='bounded_corner_count_exceeded', corners=len(points))
            points = None
        elif not path_clear(board, proposal, points, avoid=avoid,
                timeout_s=max(.001, min(10., deadline-time.monotonic())), diagnostics=validation,
                _compiled_guard=compiled):
            points = None
    return dict(points_nm=points, native_maze_found_path=bool(legs), validation=validation,
        **counters, bounded_search_diagnostics=search_diagnostics,elapsed_s=time.monotonic()-started,
        lease_exhausted=time.monotonic() >= deadline, no_path_proof=False)
