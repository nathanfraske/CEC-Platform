"""Source-derived complete local-cell escape proposals.

This is an atomic construction tier, not route/fabrication admission. Moving
an IC invalidates its placement/power-prefix evidence. Every old surviving
native component must be restored before this tier can produce a candidate;
independent saved-board DRC/current/field/pair/Kelvin receiving is still due.
No board, reference, coordinate, guessed pin role or reduced load is a rule.
"""
import math
import copy
import hashlib
import json
from pathlib import Path
import time

import pcbnew
import cec_cell_row_rebuild as row
import cec_cell_shared_fork as shared_fork
import cec_projected_ground_contact as projected_ground
import cec_constraints as constraints
import cec_current_topology as topology
import cec_decoupler_cell as cell
import cec_device_power_roles as roles
import cec_fab_profile as fab
import cec_force_current as force
import cec_fr as fr
import cec_joint_connection_search as joint
import cec_measurement_leaf as leaf
import cec_pair_semantics as semantics
import cec_control_shunt_placement as control_shunt
import cec_control_pullup_placement as control_pullup
import cec_control_gate_bias_placement as control_gate_bias
from cec_native_items import discard_items


# Explicit portfolio budget, not a placement/contact waiver. A complete IC
# and its selected follower can have different translation distances when
# the cell is rotated. Keep the normal local tier at 6 mm, but allow a caller
# to request a finite larger cohort. Every native pose, owned departure and
# complete saved-board receiving obligation remains unchanged.
MAX_EXPLICIT_CELL_SHIFT_MM = 32.
# Separate, explicitly requested construction reach for an already Source-
# qualified additional capacitor. Other roles retain the original 32 mm
# ceiling, and locality/current/clearance/return limits do not change.
MAX_EXPLICIT_AGGREGATE_CAP_SHIFT_MM = 128.


def aggregate_cap_shift_bound(value):
    if value is not None and (type(value) not in (int,float)
            or not math.isfinite(value) or not 0<value<=MAX_EXPLICIT_AGGREGATE_CAP_SHIFT_MM):
        raise ValueError('bounded_explicit_additional_capacitor_construction_reach_required')
    return value


def complete_transport_shift_bound(proposal):
    """Transport ceiling only; prepare independently checks each role's reach."""
    additional=aggregate_cap_shift_bound(proposal.get('aggregate_capacitor_max_shift_mm'))
    return max(proposal['max_shift_mm'],additional or 0.)


def _stationary_ground_lands(fp, target, model):
    """Exact unchanged native terminal metal within a moving package.

    A half-turn about a symmetric ground land need not cut that land's old
    source lead. Same centre, net name or pin number alone is insufficient.
    This retains source quality; it does not qualify an immediate return.
    """
    import cec_native_placement_context as native
    deadline=time.monotonic()+2.
    projected=pcbnew.FOOTPRINT(fp)
    projected.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in target[:2])))
    projected.SetOrientationDegrees(target[2])
    pads={force._uid(p):p for p in projected.Pads()};result={}
    for pad in fp.Pads():
        if (pad.GetNetname()!='GND' or model['pins'].get(pad.GetNumber())
                not in ('ground','reference','power_return')):continue
        first=native._native_stationary_land(pad,deadline)
        peer=pads.get(force._uid(pad))
        if first is None or peer is None or native._native_stationary_land(peer,deadline)!=first:
            continue
        result[force._uid(pad)]=dict(pad_uuid=force._uid(pad),owner=fp.GetReference(),
            pin=pad.GetNumber(),manufacturer_role=model['pins'][pad.GetNumber()],
            source_land_sha256=hashlib.sha256(repr(first).encode()).hexdigest(),
            source_return_mm=None,source_reference_via_uuid=None,
            inherited_return_not_immediate_access_qualification=True)
    return result


def prepare(board, poses, *, board_hint, max_shift_mm=6.,allow_owned_locked_escapes=False,
            rebuild_projected_ground=False,allow_octilinear_rotations=False,reference_group_uuids=(),
            source_rc_input_prefixes=(),aggregate_capacitor_max_shift_mm=None,
            allow_linear_power_stage_reconstruction=False,shared_supply_root_pad_uuids=()):
    if (type(poses) is not dict or not 1 <= len(poses) <= 8
            or type(max_shift_mm) not in (int,float) or not math.isfinite(max_shift_mm)
            or not 0<max_shift_mm<=MAX_EXPLICIT_CELL_SHIFT_MM
            or type(board_hint)is not str or not board_hint
            or type(allow_owned_locked_escapes)is not bool or type(rebuild_projected_ground)is not bool
            or type(allow_octilinear_rotations)is not bool
            or type(allow_linear_power_stage_reconstruction)is not bool):
        raise ValueError('bounded_complete_cell_poses_required')
    aggregate_cap_shift_bound(aggregate_capacitor_max_shift_mm)
    shared_supply_root_pad_uuids=shared_fork.supply_root_ids(shared_supply_root_pad_uuids)
    import cec_source_device_pinmap as source_pinmap
    with source_pinmap.observation_scope(board,board_hint=board_hint,timeout_s=10.):
        return _prepare_source(board,poses,board_hint=board_hint,max_shift_mm=max_shift_mm,
            allow_owned_locked_escapes=allow_owned_locked_escapes,rebuild_projected_ground=rebuild_projected_ground,
            allow_octilinear_rotations=allow_octilinear_rotations,reference_group_uuids=reference_group_uuids,
            source_rc_input_prefixes=source_rc_input_prefixes,
            aggregate_capacitor_max_shift_mm=aggregate_capacitor_max_shift_mm,
            allow_linear_power_stage_reconstruction=allow_linear_power_stage_reconstruction,
            **(dict(shared_supply_root_pad_uuids=shared_supply_root_pad_uuids)
                if shared_supply_root_pad_uuids else {}))


def _stationary_bypass_owner_context(board, poses, by_cap):
    """Positive selected Source assignment, never a moving-device contract."""
    context = {}
    for cap_ref, requirements in by_cap.items():
        if cap_ref not in poses or len(requirements) != 1:
            continue
        req = requirements[0]
        ref = req.get('ref')
        if ref not in poses or ref == cap_ref:
            continue
        owner = board.FindFootprintByReference(ref)
        target = poses[ref]
        if (owner is None or type(target) not in (list, tuple) or len(target) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in target)):
            raise ValueError('exact_finite_stationary_source_owner_pose_required')
        if (tuple(owner.GetPosition()) != tuple(round(v*1e6) for v in target[:2])
                or abs((owner.GetOrientationDegrees()-target[2]+180)%360-180) >= 1e-9):
            continue
        pin = str(req.get('pin', ''))
        supply = [pad for pad in owner.Pads() if pad.GetNumber() == pin]
        cap = board.FindFootprintByReference(cap_ref)
        rail = req.get('rail')
        if (not pin or len(supply) != 1 or not isinstance(rail, str) or not rail
                or rail == 'GND' or supply[0].GetNetname() != rail
                or supply[0].GetNetCode() <= 0 or cap is None
                or (req.get('return_rail') or 'GND') != 'GND'
                or len(list(cap.Pads())) != 2
                or {str(p.GetNetname()) for p in cap.Pads()} != {rail, 'GND'}):
            raise ValueError('exact_positive_source_bypass_owner_pin_net_required')
        proof = context.setdefault(ref, dict(owner_uuid=force._uid(owner),
            source_pose=[owner.GetPosition().x/1e6, owner.GetPosition().y/1e6, owner.GetOrientationDegrees()],
            source_locked=bool(owner.IsLocked()), source_flipped=bool(owner.IsFlipped()),
            selected_bypasses={}, motion_authority=False, cut_authority=False, unlock_authority=False))
        proof['selected_bypasses'][cap_ref] = dict(pin=pin, rail=rail, pad_uuid=force._uid(supply[0]))
    return context


def _prepare_source(board, poses, *, board_hint, max_shift_mm=6.,allow_owned_locked_escapes=False,
            rebuild_projected_ground=False,allow_octilinear_rotations=False,reference_group_uuids=(),
            source_rc_input_prefixes=(),aggregate_capacitor_max_shift_mm=None,
            allow_linear_power_stage_reconstruction=False,shared_supply_root_pad_uuids=()):
    """Derive ownership and ALL changed source contacts before any mutation."""
    aggregate_cap_shift_bound(aggregate_capacitor_max_shift_mm)
    shared_supply_root_pad_uuids=shared_fork.supply_root_ids(shared_supply_root_pad_uuids)
    if (type(poses) is not dict or not 1 <= len(poses) <= 8
            or type(max_shift_mm) not in (int, float) or not math.isfinite(max_shift_mm)
            or not 0 < max_shift_mm <= MAX_EXPLICIT_CELL_SHIFT_MM
            or type(board_hint) is not str or not board_hint or type(allow_owned_locked_escapes) is not bool
            or type(rebuild_projected_ground) is not bool or type(allow_octilinear_rotations) is not bool
            or type(allow_linear_power_stage_reconstruction) is not bool):
        raise ValueError('bounded_complete_cell_poses_required')
    binding = row._source_binding(board)
    import cec_macro_rc_input_prefix as rc_prefix
    prefix_requests=rc_prefix.requests(source_rc_input_prefixes)
    prefixes={q['pad_uuid']:q for q in prefix_requests};used_prefixes=set()
    control_shunts=control_shunt.plan(board,poses,board_hint=board_hint,
        reference_group_uuids=reference_group_uuids)
    control_pullups=control_pullup.complete_plan(board,poses,board_hint=board_hint,
        reference_group_uuids=reference_group_uuids)
    control_gate_biases=control_gate_bias.plan(board,poses,board_hint=board_hint,
        reference_group_uuids=reference_group_uuids)
    import cec_programming_resistor_placement as programming
    programming_resistors=programming.plan(board,poses,board_hint=board_hint,
        reference_group_uuids=reference_group_uuids)
    import cec_source_signal_bias_placement as signal_bias
    signal_biases=signal_bias.plan(board,poses,board_hint=board_hint,
        reference_group_uuids=reference_group_uuids,
        excluded_refs=set(control_shunts)|set(control_pullups)|set(control_gate_biases)|set(programming_resistors))
    passive_roles=(set(control_shunts),set(control_pullups),set(control_gate_biases),set(signal_biases),set(programming_resistors))
    if sum(map(len,passive_roles))!=len(set().union(*passive_roles)):
        raise ValueError('disjoint_source_control_passive_roles_required')
    with force._thermal_hint(board_hint):
        assigned = constraints._device_bypass_assignment(board, project_max_mm=3.5)
        protected = (set(topology.board_current_domains(board, board_hint)) - {'GND'})
        protected |= set(fr.coupled_pair_nets(board))
    by_cap = {}
    for selected in assigned['assigned'].values():
        by_cap.setdefault(selected['cap_ref'], []).append(selected['requirement'])
    stationary_context = _stationary_bypass_owner_context(board, poses, by_cap)
    import cec_additional_aggregate_macro as aggregate_caps
    additional_caps=aggregate_caps.collect(board,poses,board_hint=board_hint,
        reference_group_uuids=reference_group_uuids,
        excluded_refs=set().union(*passive_roles)|set(by_cap))
    if aggregate_capacitor_max_shift_mm is not None and not additional_caps:
        raise ValueError('explicit_additional_capacitor_reach_requires_positive_Source_role')
    if set(additional_caps)&set().union(*passive_roles):
        raise ValueError('disjoint_source_additional_capacitor_role_required')
    linear_stages={}
    if allow_linear_power_stage_reconstruction:
        import cec_source_linear_power_stage as linear_stage
        # A separate positive Source role, never a low-power-device alias.
        # This replays every existing input AND output current domain; it
        # grants no cuts, barrels, placement, route or current authority.
        linear_stages=linear_stage.collect(board,poses,board_hint=board_hint,
            reference_group_uuids=reference_group_uuids,enabled=True)
    # A wired bypass may slide without cutting any Source metal. This is a
    # separate positive tier, NOT a relaxed unwired/projected-return test:
    # every original surface contact and every independent full-width
    # stroke-component entry must survive. No old Ground return is qualified.
    import cec_retained_bypass_contact_frame as retained_bypass
    try:
        retained_contact_frame = retained_bypass.plan(board, poses, board_hint=board_hint,
            max_shift_mm=max_shift_mm, allow_octilinear_rotations=allow_octilinear_rotations)
    except ValueError:
        retained_contact_frame = None
    models = {}; bypasses = {}; leaves = []; ground_leaves = []; ground_refusals = []
    # An additional ceramic is NOT a selected minimum or a device Ground
    # pin. Its separate Source-canonical full-class leaf was independently
    # derived by collect(); retain that exact distinct proof and all of its
    # first fixed native boundaries in the base retirement/restoration frame.
    ground_leaves.extend(copy.deepcopy(p['source_Ground_leaf']) for p in additional_caps.values()
        if p.get('source_Ground_leaf') is not None)
    nonpair_measurements = []; unrouted_measurements = []; source_graph = None; stationary_owners = []
    explicit_no_connects=[];isolated_source_intent_pad_uuids=[]
    supply_leaves = []; supply_refusals = []; stationary_ground = {}; projected_ground_contacts={}
    def retain_projected_ground(pad,target):
        if rebuild_projected_ground:return False
        try:
            proof=projected_ground.plan(board,force._uid(pad),target,board_hint=board_hint,
                **({'allow_octilinear_rotations':True} if allow_octilinear_rotations else {}))
        except ValueError:return False
        projected_ground_contacts[force._uid(pad)]=proof
        return True
    for ref, target in poses.items():
        fp = board.FindFootprintByReference(ref)
        if ref in stationary_context:
            stationary_owners.append(ref)
            continue
        if (fp is None or fp.IsLocked() or len(target) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in target)
                or math.dist(tuple(fp.GetPosition()), [round(v*1e6) for v in target[:2]]) >
                    (aggregate_capacitor_max_shift_mm if ref in additional_caps and aggregate_capacitor_max_shift_mm is not None else max_shift_mm)*1e6
                or any(p.HasHole() or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD for p in fp.Pads())):
            raise ValueError('unlocked_bounded_native_surface_cell_required')
        reqs = by_cap.get(ref, [])
        if ref in additional_caps:
            if reqs:raise ValueError('additional_aggregate_capacitor_cannot_replace_selected_bypass')
            continue
        if ref in control_shunts:
            if reqs:raise ValueError('control_shunt_cannot_alias_power_bypass')
            continue
        if ref in control_pullups:
            if reqs:raise ValueError('control_pullup_cannot_alias_power_bypass')
            continue
        if ref in control_gate_biases:
            if reqs:raise ValueError('control_gate_bias_cannot_alias_power_bypass')
            continue
        if ref in signal_biases:
            if reqs:raise ValueError('signal_bias_resistor_cannot_alias_power_bypass')
            continue
        if ref in programming_resistors:
            if reqs:raise ValueError('programming_resistor_cannot_alias_power_bypass')
            continue
        if reqs:
            if (len(reqs) != 1 or len(list(fp.Pads())) != 2
                    or reqs[0]['ref'] not in poses
                    or {str(p.GetNetname()) for p in fp.Pads()} != {reqs[0]['rail'], 'GND'}
                    or (reqs[0].get('return_rail') or 'GND') != 'GND'):
                raise ValueError('unique_bypass_and_moving_owner_required')
            bypasses[ref] = dict(owner=reqs[0]['ref'], pin=str(reqs[0]['pin']),
                rail=reqs[0]['rail'])
            cap_supply=next(p for p in fp.Pads() if p.GetNetname()==reqs[0]['rail'])
            cap_moving=(tuple(fp.GetPosition())!=tuple(round(v*1e6) for v in target[:2])
                or abs((fp.GetOrientationDegrees()-target[2]+180)%360-180)>=1e-9)
            if cap_moving:
                cap_ground=next(p for p in fp.Pads() if p.GetNetname()=='GND')
                owner=board.FindFootprintByReference(reqs[0]['ref']);owner_target=poses[reqs[0]['ref']]
                if (len(owner_target)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in owner_target)):
                    raise ValueError('bounded_actual_selected_owner_pose_required')
                owner_moving=(tuple(owner.GetPosition())!=tuple(round(v*1e6) for v in owner_target[:2])
                    or abs((owner.GetOrientationDegrees()-owner_target[2]+180)%360-180)>=1e-9)
                preserve_contacts=(retained_contact_frame is not None
                    and ref in retained_contact_frame['moving_refs'])
                if not preserve_contacts and not retain_projected_ground(cap_ground,target):
                    try:
                        ground_leaves.append(leaf.plan_bypass_ground(board,force._uid(cap_ground),
                            board_hint=board_hint,moving_owner_ref=reqs[0]['ref'] if owner_moving else None))
                    except ValueError as exc:
                        ground_refusals.append(dict(pad_uuid=force._uid(cap_ground),reason=str(exc)))
                if not preserve_contacts:
                    try:
                        supply_leaves.append(leaf.plan_rated_bypass_supply(board,force._uid(cap_supply),
                            board_hint=board_hint,moving_owner_ref=reqs[0]['ref'] if owner_moving else None))
                    except ValueError as exc:
                        supply_refusals.append(dict(pad_uuid=force._uid(cap_supply),reason=str(exc),
                            source_copper_retained=True))
            continue
        model = roles.footprint_contract(fp)
        if (not model
                or set(p.GetNumber() for p in fp.Pads()) != set(model['pins'])):
            raise ValueError('positive_complete_low_power_device_pin_contract_required')
        roles.physical_pinmap(fp,model,board_hint=board_hint)
        models[ref] = model
        stationary = (tuple(fp.GetPosition()) == tuple(round(v*1e6) for v in target[:2])
            and abs((fp.GetOrientationDegrees()-target[2]+180)%360-180) < 1e-9)
        if stationary:
            # The owner is an identity/assignment witness, not a request to
            # rebuild any of its unchanged departures. A moving capacitor
            # separately proves ownership of its own source stub. Retiring
            # the stationary IC's good rail feed just creates extra work and
            # another possible failure without improving that placement.
            stationary_owners.append(ref)
            continue
        # An exactly stationary, completely typed power stage above is an
        # assignment/identity witness ONLY. Its unchanged outputs, switch
        # node and feedback network are not a relocation or cut domain.
        # Only the distinct, freshly rederived linear-stage role may enter
        # a complete full-current reconstruction. Switching/feedback owners
        # stay outside this tier, including when the option is enabled.
        if (any(r in ('switch','feedback') for r in model['pins'].values())
                or 'power_output' in model['pins'].values() and ref not in linear_stages):
            raise ValueError('positive_complete_low_power_device_pin_contract_required')
        for pad in fp.Pads():
            if (model['pins'].get(pad.GetNumber()) in ('power_input','measurement')
                    or pad.GetNetname()=='GND' or pad.GetNetCode()<=0):continue
            if source_graph is None:source_graph=fr._read_only_route_connectivity(board)
            if any(force._uid(item)!=force._uid(pad) for item in source_graph.GetConnectedItems(pad)):continue
            isolated_source_intent_pad_uuids.append(force._uid(pad))
        fixed_lands=_stationary_ground_lands(fp,target,model)
        for uid,proof in fixed_lands.items():
            pad=next(p for p in fp.Pads() if force._uid(p)==uid)
            witness=cell._existing_return(board,pad,16.,allow_native_track_body=True)
            if witness is not None:
                proof.update(source_return_mm=witness[0],source_reference_via_uuid=force._uid(witness[1]))
        stationary_ground.update(fixed_lands)
        for pad in fp.Pads():
            if model['pins'].get(pad.GetNumber()) != 'power_input':continue
            try:
                supply_leaves.append(leaf.plan_rated_supply(board,force._uid(pad),board_hint=board_hint))
            except ValueError as exc:
                supply_refusals.append(dict(pad_uuid=force._uid(pad),reason=str(exc),
                    source_copper_retained=True))
        paired = semantics.footprint_input_contract(fp)
        if any(role == 'measurement' for role in model['pins'].values()) and not paired:
            raise ValueError('positive_measurement_pin_partition_required')
        for pad in fp.Pads():
            if model['pins'][pad.GetNumber()] == 'measurement':
                if pad.GetNumber() not in paired[1]:
                    # VBUS is not a shunt input. Preserve its source copper
                    # through the ordinary row boundary/current contract;
                    # never invent a Kelvin leaf or retire its force domain.
                    nonpair_measurements.append(dict(pad_uuid=force._uid(pad),
                        owner=ref, pin=pad.GetNumber(), net=pad.GetNetname(),
                        manufacturer_source=model['source'], retired_by_this_tier=False))
                    continue
                if source_graph is None:
                    source_graph = fr._read_only_route_connectivity(board)
                if not any(force._uid(item) != force._uid(pad)
                        for item in source_graph.GetConnectedItems(pad)):
                    # An existing open owns no departure to cut. Record that
                    # debt explicitly, not as a completed measurement leaf.
                    # A pose proposal may move it, but cannot route it by a
                    # guessed shunt/whole-net target or claim qualification.
                    unrouted_measurements.append(dict(pad_uuid=force._uid(pad),
                        owner=ref, pin=pad.GetNumber(), net=pad.GetNetname(),
                        source_isolated=True, route_authority=False,
                        new_typed_measurement_routing_still_required=True))
                else:
                    if force._uid(pad) in prefixes:
                        proof=rc_prefix.plan(board,Path(board.GetFileName()),board_hint=board_hint,
                            request=prefixes[force._uid(pad)])
                        for peer in (p for f in board.GetFootprints() for p in f.Pads()
                                if force._uid(p) in proof['retained_native_keys']):
                            fixed=peer.GetParentFootprint();target_fixed=poses.get(fixed.GetReference())
                            if target_fixed is not None and (tuple(fixed.GetPosition())!=
                                    tuple(round(v*1e6) for v in target_fixed[:2]) or
                                    abs((fixed.GetOrientationDegrees()-target_fixed[2]+180)%360-180)>=1e-9):
                                raise ValueError('Source_RC_prefix_filter_terminals_must_remain_fixed')
                        leaves.append(proof);used_prefixes.add(force._uid(pad));continue
                    try:
                        leaves.append(leaf.plan(board, force._uid(pad)))
                    except ValueError as original:
                        try:
                            # A declared closed annotation group is not a
                            # copper owner. Forward only its independently
                            # checked Source-map opt-in; the strap and its
                            # external leaf remain distinct mandatory cuts.
                            mapped=any(force._uid(g) in reference_group_uuids and g.ContainsItem(fp)
                                for g in board.Groups())
                            departure,strap=leaf.plan_with_auxiliary_strap(board,force._uid(pad),
                                allow_source_reference_maps=mapped)
                        except ValueError as auxiliary_refusal:
                            raise original from auxiliary_refusal
                        leaves.extend((departure,strap))
            elif (pad.GetNetname() == 'GND'
                    and model['pins'][pad.GetNumber()] in ('ground', 'reference', 'power_return')):
                if force._uid(pad) in fixed_lands:
                    continue
                if not retain_projected_ground(pad,target):
                    try:
                        ground_leaves.append(leaf.plan_ground(board, force._uid(pad)))
                    except ValueError as exc:
                        # A fork/shared/unknown ground departure stays retained.
                        # Refusal is not permission for a blanket GND deletion.
                        ground_refusals.append(dict(pad_uuid=force._uid(pad), reason=str(exc)))
    if used_prefixes!=set(prefixes):
        raise ValueError('every_explicit_Source_RC_prefix_requires_moving_typed_connected_input')
    if isolated_source_intent_pad_uuids:
        import cec_source_no_connect as no_connect
        # One immutable invocation, every physical land retained. Fresh
        # native/hierarchy inventory and final live bindings are shared;
        # no verdict or Source data survives this complete prepare call.
        intent=no_connect.plan_many(board,isolated_source_intent_pad_uuids,board_hint=board_hint)
        explicit_no_connects.extend(proof for proof in intent.values()if proof is not None)
    # An owner's already-selected bypass is not allowed to stay behind as a
    # stale binding or silently become a different owner's capacitor.
    for ref in models:
        # Exact stationary owners keep every unselected Source capacitor
        # and its original connection. Only an actually moving IC requires
        # its complete selected supply cohort to follow its new pose.
        if ref in stationary_owners:
            continue
        selected = [cap for cap, reqs in by_cap.items()
            if any(req['ref'] == ref for req in reqs)]
        if not selected or any(cap not in poses for cap in selected):
            raise ValueError('complete_selected_supply_followers_required')
    for cap_ref, selected in bypasses.items():
        owner = board.FindFootprintByReference(selected['owner'])
        pad = owner.FindPadByNumber(selected['pin'])
        model = models.get(selected['owner'])
        if selected['owner'] in stationary_context:
            proof = stationary_context[selected['owner']]['selected_bypasses'].get(cap_ref)
            if (proof is None or pad is None or force._uid(pad) != proof['pad_uuid']
                    or pad.GetNetname() != proof['rail']):
                raise ValueError('positive_selected_owner_supply_role_required')
            continue
        if (pad is None or pad.GetNetname() != selected['rail'] or not model
                or not (model['pins'].get(selected['pin']) == 'power_input'
                    or model['pins'].get(selected['pin']) == 'power_output'
                    and (selected['owner'] in stationary_owners or selected['owner'] in linear_stages))):
            raise ValueError('positive_selected_owner_supply_role_required')
        # A stationary identity witness or the distinct positive linear
        # stage may own its Source-selected OUTPUT capacitor. OUT never
        # becomes IN. The input-only leaf/fork tiers still refuse output
        # cuts; complete full-current boundary ownership, every retained
        # contact and original partition remain independently due.
    scalar_links=[]; scalar_refusals=[]
    moving_owners=set(models)-set(stationary_owners)
    if len(moving_owners)>=2:
        for ref in sorted(moving_owners):
            for pad in board.FindFootprintByReference(ref).Pads():
                if models[ref]['pins'].get(pad.GetNumber())!='signal_output':continue
                if pad.GetNetname() in protected or pad.GetNetname()=='GND':continue
                try:
                    scalar_links.append(leaf.plan_scalar_link(board,force._uid(pad),
                        owner_refs=moving_owners,allow_owned_locked=allow_owned_locked_escapes))
                except ValueError as exc:
                    scalar_refusals.append(dict(pad_uuid=force._uid(pad),reason=str(exc),
                        source_copper_retained=True))
    scalar_inputs=[];input_refusals=[]
    paired_input_ids={q['peer_pad_uuid'] for q in scalar_links}
    for ref in sorted(moving_owners):
        for pad in board.FindFootprintByReference(ref).Pads():
            if models[ref]['pins'].get(pad.GetNumber())!='signal_input' or force._uid(pad) in paired_input_ids:
                continue
            try:
                scalar_inputs.append(leaf.plan_scalar_input(board,force._uid(pad),board_hint=board_hint,
                    allow_owned_locked=allow_owned_locked_escapes))
            except ValueError as exc:
                input_refusals.append(dict(pad_uuid=force._uid(pad),reason=str(exc),source_copper_retained=True))
    # Context owners never enter the moving/cut backend. Their complete native
    # geometry and lock state remain bound by source_native_binding and replay.
    row_poses = {ref: target for ref, target in poses.items() if ref not in stationary_context}
    plan = row.plan(board, row_poses, {}, protected_nets=protected,
        allow_owned_locked=allow_owned_locked_escapes, allow_cardinal_rotations=True,
        allow_octilinear_rotations=allow_octilinear_rotations,reference_group_uuids=reference_group_uuids,
        maximum_reference_translation_mm=max(max_shift_mm,aggregate_capacitor_max_shift_mm or 0.),
        **(dict(maximum_translation_mm=aggregate_capacitor_max_shift_mm)
            if aggregate_capacitor_max_shift_mm is not None and aggregate_capacitor_max_shift_mm>64. else {}))
    if plan['transformed_track_uuids']:
        raise ValueError('cell_escape_tier_does_not_carry_internal_copper')
    # Linear leaves cannot own a fork at a moving land. A separate positive
    # multiport tier may own its complete bounded source-local scope. Its
    # fixed contacts remain mandatory; no whole-net cut or guessed load is
    # authorized by the failure of the narrow tier.
    moving_refs=set(moving_owners)|set(additional_caps)|{ref for ref in bypasses if
        tuple(board.FindFootprintByReference(ref).GetPosition())!=tuple(round(v*1e6) for v in poses[ref][:2])
        or abs((board.FindFootprintByReference(ref).GetOrientationDegrees()-poses[ref][2]+180)%360-180)>=1e-9}
    source_pads={force._uid(p):p for fp in board.GetFootprints() for p in fp.Pads()}
    supply_forks=[];input_forks=[];ground_forks=[];fork_refusals=[]
    for kind,failures,destination in (('rated_supply',supply_refusals,supply_forks),
            ('scalar_input',input_refusals,input_forks),('ground_return',ground_refusals,ground_forks)):
        grouped={}
        for failure in failures:
            pad=source_pads[failure['pad_uuid']]
            if pad.GetParentFootprint().GetReference() not in moving_refs:continue
            grouped.setdefault((str(pad.GetNetname()),cell.cec_return_escape.smd_surface_layer(pad)),[]).append(force._uid(pad))
        for (net,face),roots in sorted(grouped.items(),key=lambda item:repr(item[0])):
            try:
                if kind=='ground_return':
                    # An in-pad Ground root can have no Source stroke to
                    # retire. Including it in a same-net fork transaction
                    # wrongly invalidates the OTHER roots' real branched
                    # copper. Keep its separate Ground/routing obligation;
                    # only positively present thin departures seed this cut.
                    groups={force._uid(i) for g in board.Groups() for i in g.GetItems()}
                    # Netclass is invariant within this read-only inventory.
                    # Reading/re-hashing its saved project for every Ground
                    # track is redundant work, not an independent verdict.
                    ground_class_minimum=max(board.GetDesignSettings().m_TrackMinWidth,
                        int(cell._netclass(board,net)['width']))
                    thin=[t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK'
                        and t.GetNetname()==net and t.GetLayer()==face and force._uid(t) not in groups
                        and not t.HasSolderMask() and (not t.IsLocked() or allow_owned_locked_escapes)
                        and ground_class_minimum<=t.GetWidth()<=350000
                        and 0<t.GetLength()<=8000000]
                    roots=[uid for uid in roots if any(t.GetBoundingBox().Intersects(source_pads[uid].GetBoundingBox())
                        and t.GetEffectiveShape(face).Collide(source_pads[uid].GetEffectiveShape(face),0) for t in thin)]
                    if not roots:continue
                retained_ground={}
                if kind=='ground_return':
                    retained_ground=dict(retained_ground_pad_uuids=sorted(stationary_ground),
                        retained_ground_track_uuids=sorted({u for q in projected_ground_contacts.values()
                            for u in q['source_entry_native_uuids']}))
                fork=shared_fork.plan(board,sorted(set(roots)),moving_refs=sorted(moving_refs),kind=kind,
                    board_hint=board_hint,allow_owned_locked=allow_owned_locked_escapes,
                    max_tracks=32,max_length_mm=32.,**retained_ground,
                    **(dict(allow_full_current_supply_width=True)if kind=='rated_supply'else{}))
                owned=set(fork['track_uuids'])
                others=[*leaves,*ground_leaves,*supply_leaves,*scalar_links,*scalar_inputs]
                covered=[q for q in others if set(q['track_uuids'])&owned]
                if any(not set(q['track_uuids'])<=owned or q['pad_uuid'] not in fork['moving_source_pad_uuids'] for q in covered):
                    raise ValueError('shared_fork_partial_overlap_with_other_typed_leaf')
                outside=set(plan['retired_track_uuids'])|{u for q in others for u in q['track_uuids']}
                if any(p['native_uuid'] in outside-owned for p in fork['retained_native_ports']):
                    raise ValueError('shared_fork_fixed_port_is_separately_retired')
                for collection in (supply_leaves,scalar_inputs,ground_leaves):
                    collection[:]=[q for q in collection if q not in covered]
                destination.append(fork)
                for failure in failures:
                    if failure['pad_uuid'] in fork['moving_source_pad_uuids']:
                        failure.update(source_copper_retained=False,linear_scope_not_owner=True,
                            reconstruction_owned_by='source_typed_complete_local_multiport_fork')
            except ValueError as exc:
                fork_refusals.append(dict(kind=kind,net=net,root_pad_uuids=sorted(set(roots)),reason=str(exc),
                    source_copper_retained=True))
    retired = set(plan['retired_track_uuids']) | {u for q in
        [*leaves, *ground_leaves,*supply_leaves,*scalar_links,*scalar_inputs,*supply_forks,*input_forks,*ground_forks] for u in q['track_uuids']}
    if (retained_contact_frame is not None
            and retired & set(retained_contact_frame['retained_track_uuids'])):
        raise ValueError('retained_bypass_stroke_component_cannot_be_independently_retired')
    if any(contact['pad_uuid'] in stationary_ground and contact['track_uuid'] in retired
            for contact in plan['source_incident_boundaries']):
        raise ValueError('stationary_ground_source_contact_cannot_be_retired')
    if len(retired) > 64:
        raise ValueError('bounded_complete_cell_retirement_required')
    if row._source_binding(board) != binding:
        raise ValueError('source_changed_during_complete_cell_inventory')
    result=dict(schema=1, scope='source_typed_complete_cell_escape_proposal',
        row_plan=plan, source_native_binding=binding, poses=poses,
        device_contracts=models, selected_bypasses=bypasses,
        measurement_leaves=leaves, retired_track_uuids=sorted(retired),
        preserved_nonpair_measurement_contacts=nonpair_measurements,
        inherited_unrouted_measurement_lands=unrouted_measurements,
        stationary_device_owners=sorted(stationary_owners),
        rated_supply_leaves=supply_leaves,rated_supply_departures_not_owned=supply_refusals,
        scalar_links=scalar_links,scalar_departures_not_owned=scalar_refusals,
        ground_leaves=ground_leaves, ground_departures_not_owned=ground_refusals,
        board_hint=board_hint, max_shift_mm=max_shift_mm,
        routing_admitted=False, release_authority=False,
        requires_new_placement_power_and_independent_saved_board_receiving=True)
    if stationary_context:
        result['stationary_bypass_owner_context'] = stationary_context
    if control_shunts:result['selected_control_shunts']=control_shunts
    if control_pullups:result['selected_control_pullups']=control_pullups
    if control_gate_biases:result['selected_control_gate_biases']=control_gate_biases
    if signal_biases:result['selected_signal_bias_resistors']=signal_biases
    if programming_resistors:result['selected_programming_resistors']=programming_resistors
    if allow_linear_power_stage_reconstruction:
        result['allow_linear_power_stage_reconstruction']=True
    if linear_stages:result['source_linear_power_stages']=linear_stages
    if additional_caps:
        result['additional_aggregate_capacitors']=additional_caps
        result['additional_aggregate_excluded_refs']=sorted(set().union(*passive_roles))
    if aggregate_capacitor_max_shift_mm is not None:
        result['aggregate_capacitor_max_shift_mm']=aggregate_capacitor_max_shift_mm
    if allow_owned_locked_escapes:
        result.update(allow_owned_locked_escapes=True,
            exact_source_owned_locked_ordinary_escapes_not_global_unlock=True)
    if rebuild_projected_ground:
        result['rebuild_projected_ground']=True
    if allow_octilinear_rotations:result['allow_octilinear_rotations']=True
    if reference_group_uuids:result['reference_group_uuids']=list(reference_group_uuids)
    if prefix_requests:result['source_rc_input_prefixes']=prefix_requests
    if stationary_ground:
        result['native_stationary_ground_lands']=stationary_ground
    if projected_ground_contacts:result['native_projected_ground_contacts']=projected_ground_contacts
    if retained_contact_frame is not None:
        result['native_retained_bypass_contact_frame']=retained_contact_frame
    if scalar_inputs:result['scalar_input_leaves']=scalar_inputs
    if input_refusals:result['scalar_input_departures_not_owned']=input_refusals
    if supply_forks:result['source_owned_shared_supply_forks']=supply_forks
    if shared_supply_root_pad_uuids:
        result['shared_supply_root_pad_uuids']=shared_fork.bind_supply_roots(supply_forks,shared_supply_root_pad_uuids)
    if input_forks:result['source_owned_shared_scalar_input_forks']=input_forks
    if ground_forks:result['source_owned_shared_ground_return_forks']=ground_forks
    if explicit_no_connects:result['source_explicit_schematic_no_connects']=explicit_no_connects
    if fork_refusals:result['source_shared_forks_not_owned']=fork_refusals
    # A worker receives a SAVED proposal. In particular native-layer keys in
    # the unchanged full-current contract become strings in JSON. Bind that
    # canonical representation at the producer boundary, so an exact saved
    # round trip is not mistaken for forged authority. apply_private still
    # independently rederives and compares every field before any mutation.
    return json.loads(json.dumps(result,allow_nan=False))


def recompile_source_proposal(board, proposal, *, board_hint=None):
    """One exact replay context for every independently receiving caller.

    This forwards ownership inputs, not ownership authority. ``prepare`` must
    freshly validate their real source geometry and callers still compare the
    entire returned proposal. A new explicit compiler option belongs here so
    nested endpoint/return receiving cannot silently lose its source scope.
    """
    if (type(proposal) is not dict
            or proposal.get('scope')!='source_typed_complete_cell_escape_proposal'
            or board_hint is not None and board_hint!=proposal.get('board_hint')):
        raise ValueError('exact_source_proposal_replay_context_required')
    return prepare(board, proposal['poses'], board_hint=proposal['board_hint'],
        max_shift_mm=proposal['max_shift_mm'],
        allow_owned_locked_escapes=proposal.get('allow_owned_locked_escapes',False),
        rebuild_projected_ground=proposal.get('rebuild_projected_ground',False),
        allow_octilinear_rotations=proposal.get('allow_octilinear_rotations',False),
        reference_group_uuids=proposal.get('reference_group_uuids',()),
        source_rc_input_prefixes=proposal.get('source_rc_input_prefixes',()),
        **(dict(aggregate_capacitor_max_shift_mm=proposal['aggregate_capacitor_max_shift_mm'])
            if 'aggregate_capacitor_max_shift_mm'in proposal else {}),
        **(dict(allow_linear_power_stage_reconstruction=proposal['allow_linear_power_stage_reconstruction'])
            if 'allow_linear_power_stage_reconstruction'in proposal else {}),
        **(dict(shared_supply_root_pad_uuids=proposal['shared_supply_root_pad_uuids'])
            if 'shared_supply_root_pad_uuids'in proposal else {}))


def apply_private(board, proposal):
    """No worker-authored allowlist: rederive the entire source scope."""
    fresh = recompile_source_proposal(board,proposal)
    if fresh != proposal:
        raise ValueError('stale_or_forged_complete_cell_proposal')
    row.apply(board, proposal['row_plan'])
    discard_items(board, [t for t in board.GetTracks()
        if force._uid(t) in set(proposal['retired_track_uuids'])])
    if 'native_retained_bypass_contact_frame' in proposal:
        import cec_retained_bypass_contact_frame as retained_bypass
        retained_bypass.observe(board,proposal['native_retained_bypass_contact_frame'])
    # Match the macro compiler's receiving context. An exact existing local
    # pad rule can apply to an independently rederived whole-package pose;
    # without this binding, early Ground planning silently falls back to
    # larger ordinary setup vias and disagrees with final construction.
    # resolve() still rechecks the original saved rule, complete package,
    # live pad and group; this attribute is not a new floor waiver.
    import cec_existing_local_pofv_pad_rule as saved_pad_rule
    saved_pad_rule.bind_projected_source_poses(board,proposal['poses'],
        allow_octilinear_rotations=proposal.get('allow_octilinear_rotations',False))


def assigned_ground_entries(board, selected_bypasses, *, board_hint):
    """Re-derive typed capacitor portals; a same-net neighbour is not an owner.

    These dependencies are proposals, not proof that a capacitor is grounded.
    Its own immediate return must be constructed in the same transaction and
    independently received. Never apply this low-power policy to switches,
    regulators, untyped packages, remote capacitors or arbitrary GND pads.
    """
    if type(selected_bypasses) is not dict or len(selected_bypasses) > 8:
        raise ValueError('bounded_selected_ground_entries_required')
    import cec_ground_return_policy as return_policy
    source_return_policy=return_policy.owner_policy(board_hint)
    with force._thermal_hint(board_hint):
        assignment = constraints._device_bypass_assignment(board, project_max_mm=3.5)
    actual = {}
    for item in assignment['assigned'].values():
        req = item['requirement']
        actual.setdefault(item['cap_ref'], []).append(dict(owner=req['ref'],
            pin=str(req['pin']), rail=req['rail']))
    result = {}
    for cap_ref, selected in sorted(selected_bypasses.items()):
        if actual.get(cap_ref) != [selected]:
            cap=board.FindFootprintByReference(cap_ref)
            owner=board.FindFootprintByReference(selected['owner'])
            supply=owner.FindPadByNumber(selected['pin']) if owner else None
            cap_supply=next((p for p in cap.Pads() if p.GetNetname()==selected['rail']),None) if cap else None
            distance=(math.dist(tuple(supply.GetPosition()),tuple(cap_supply.GetPosition()))/1e6
                if supply and cap_supply else None)
            raise ValueError('ground_entry_source_assignment_not_unique_or_changed:'+cap_ref+
                ':expected='+repr(selected)+':actual='+repr(actual.get(cap_ref))+
                ':expected_supply_distance_mm='+str(distance))
        cap = board.FindFootprintByReference(cap_ref)
        owner = board.FindFootprintByReference(selected['owner'])
        model = roles.footprint_contract(owner) if owner else None
        if (not cap or not model or model['pins'].get(selected['pin']) != 'power_input'
                or any(role in ('power_output', 'switch', 'feedback') for role in model['pins'].values())
                or len(list(cap.Pads())) != 2 or cap.IsFlipped() != owner.IsFlipped()
                or {p.GetNetname() for p in cap.Pads()} != {'GND', selected['rail']}):
            raise ValueError('typed_local_bypass_ground_entry_required')
        supply = owner.FindPadByNumber(selected['pin'])
        cap_supply = next(p for p in cap.Pads() if p.GetNetname() == selected['rail'])
        portal = next(p for p in cap.Pads() if p.GetNetname() == 'GND')
        if (not supply or supply.GetNetname() != selected['rail']
                or math.dist(tuple(supply.GetPosition()), tuple(cap_supply.GetPosition())) > 3500000
                or any(p.HasHole() or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                    for p in [*cap.Pads(), *owner.Pads()])):
            raise ValueError('source_selected_bypass_is_not_local_surface_cell')
        for pad in owner.Pads():
            if (pad.GetNetname() != 'GND' or model['pins'].get(pad.GetNumber())
                    not in ('ground', 'reference', 'power_return')):
                continue
            distance = math.dist(tuple(pad.GetPosition()), tuple(portal.GetPosition()))/1e6
            if distance <= 4.:
                entry = dict(owner_ground_pad_uuid=force._uid(pad),
                    portal_pad_uuid=force._uid(portal),
                    portal_obligation='ground:'+force._uid(portal),
                    root_portal_pad_uuid=force._uid(portal),
                    root_portal_obligation='ground:'+force._uid(portal),
                    selected_bypass=cap_ref, selected_owner=selected['owner'],
                    selected_supply_pin=selected['pin'], selected_rail=selected['rail'],
                    direct_mm=distance, max_direct_mm=4.,
                    max_link_mm=cell._local_supply_limit_mm(distance,
                        max(200000,int(cell._netclass(board,'GND')['width']))/1e6,
                        max(200000,int(cell._netclass(board,'GND')['clearance']))/1e6),
                    immediate_portal_reach_mm=.8,
                    source_owner_return_policy=source_return_policy)
                prior = result.get(force._uid(pad))
                if prior is None or (distance, cap_ref) < (prior['direct_mm'], prior['selected_bypass']):
                    result[force._uid(pad)] = entry
        # Reference and ground-strapped address inputs are not power-return
        # pins. They may take a short link to this package's positively typed
        # GND pin, whose entry in turn owns a qualified capacitor root. The
        # hierarchy is directed by manufacturer roles, never mutually linked
        # reference pads or arbitrary same-net neighbours.
        grounds = [p for p in owner.Pads() if p.GetNetname() == 'GND'
            and model['pins'].get(p.GetNumber()) in ('ground', 'power_return')
            and force._uid(p) in result]
        for pad in owner.Pads():
            if (pad.GetNetname() != 'GND' or model['pins'].get(pad.GetNumber())
                    not in ('reference', 'address') or force._uid(pad) in result):
                continue
            peers = sorted(grounds, key=lambda p: (math.dist(tuple(p.GetPosition()),
                tuple(pad.GetPosition())), force._uid(p)))
            if not peers:continue
            direct_mm=math.dist(tuple(pad.GetPosition()),tuple(peers[0].GetPosition()))/1e6
            contact_frontier=None
            if direct_mm>4.:
                # A track may attach inside the actual connected land. Keep
                # the 4 mm emitted-wire bound; do not charge a fictitious
                # pad-centre detour or grant a longer return/strap allowance.
                import cec_ground_package_pad_contacts as package_contacts
                contact_frontier=package_contacts.contacts(board,pad,peers[0],maximum_wire_mm=4.)
                if contact_frontier is None:continue
                direct_mm=contact_frontier['minimum_octilinear_wire_mm']
            peer = peers[0]; parent = result[force._uid(peer)]
            result[force._uid(pad)] = dict(parent, owner_ground_pad_uuid=force._uid(pad),
                portal_pad_uuid=force._uid(peer), portal_obligation='ground:'+force._uid(peer),
                direct_mm=direct_mm,
                max_link_mm=4.,
                typed_reference_or_address_to_package_ground=True)
            if contact_frontier is not None:
                result[force._uid(pad)]['native_package_pad_contact_frontier']=contact_frontier
    return result


def ground_link_ops(board, pad, portal, *, deadline, max_link_mm=4.):
    """Full-class local GND bodies with bounded native SMD endpoint escapes.

    An endpoint escape is a geometric proposal, not an aggregate Ground
    current allowance. Materialization and saved receiving must separately
    qualify its complete group and source-selected owner/cap hierarchy.
    Never create a hidden barrel or narrow the middle of the link.
    """
    if (pad.GetNetname() != 'GND' or portal.GetNetname() != 'GND'
            or pad.HasHole() or portal.HasHole()
            or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
            or portal.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
            or not 0 < max_link_mm <= 6.):
        raise ValueError('bounded_surface_ground_dependency_required')
    layers = sorted(set(pad.GetLayerSet().CuStack()) & set(portal.GetLayerSet().CuStack()))
    if len(layers) != 1:
        return []
    a, b = tuple(pad.GetPosition()), tuple(portal.GetPosition())
    direct = math.dist(a, b)/1e6
    width = max(200000, int(board.GetDesignSettings().m_TrackMinWidth),
        int(cell._netclass(board, 'GND')['width']))
    gap = max(200000, int(board.GetDesignSettings().m_MinClearance),
        int(cell._netclass(board, 'GND')['clearance']))
    limit = min(max_link_mm, cell._local_supply_limit_mm(direct, width/1e6, gap/1e6))
    if time.monotonic() >= deadline:return []
    if direct > limit:
        import cec_ground_package_pad_contacts as package_contacts
        return package_contacts.links(board,pad,portal,
            maximum_wire_mm=min(4.,max_link_mm),deadline=deadline)
    cache = {}; layer = int(layers[0]); code = pad.GetNetCode(); choices = []
    minimum=max(200000,int(board.GetDesignSettings().m_TrackMinWidth))
    escapes=tuple(fr._pad_local_escape(p,width,gap,minimum) for p in (pad,portal))
    for path in fr._canonical_45_xy_paths(a, b):
        if time.monotonic() >= deadline:
            break
        length = sum(math.dist(s, t) for s, t in zip(path, path[1:]))/1e6
        if length>limit:continue
        vectors=[pcbnew.VECTOR2I(*p) for p in path]
        menus=[[(s,t,width) for s,t in zip(vectors,vectors[1:]) if s!=t]]
        if any(escapes):menus.append(fr._profiled_lastmile_path(vectors,width,*escapes))
        for legs in menus:
            if legs and all(w>=minimum and fr._edge_leg_clear(board,s,t,w/2+gap)
                    and fr._tap_foreign_clear(board,s,t,w,layer,gap,{code},foreign_cache=cache)
                    for s,t,w in legs):
                ops=[('trk',tuple(s),tuple(t),int(w),layer) for s,t,w in legs]
                if ops not in choices:choices.append(ops)
    if not choices and time.monotonic() < deadline:
        legs = fr._guarded_profiled_lastmile_legs(board, pcbnew.VECTOR2I(*a),
            pcbnew.VECTOR2I(*b), width, layer, gap, code,
            lambda s, t, h: fr._edge_leg_clear(board, s, t, h+gap),
            foreign_cache=cache, allow_maze=True, deadline_monotonic=deadline,
            max_length_nm=limit*1e6,start_escape=escapes[0],end_escape=escapes[1])
        if legs:
            choices.append([('trk', tuple(s), tuple(t), int(w), layer) for s, t, w in legs])
    return choices


def typed_non_return_package_ground_links(board,pad,*,deadline,peer_uuids=None):
    """Finite full-class links, not a new return or same-net authority.

    Manufacturer address/reference inputs tied to Ground are NOT power
    returns. Use the existing bounded package-link producer with its native
    pad-local endpoint profile. Callers must qualify the peer's real root:
    ground preflight requires a completed prefix; construction requires all
    independent Source partitions and physical Ground receiving.
    """
    if time.monotonic()>=deadline:return []
    fp=pad.GetParentFootprint();model=roles.footprint_contract(fp)
    if (not model or fp.IsDNP() or pad.GetNetname()!='GND' or pad.GetNetCode()<=0
            or model['pins'].get(pad.GetNumber())not in('address','reference')
            or any(v in('power_output','switch','feedback')for v in model['pins'].values())):
        return []
    peers=sorted((p for p in fp.Pads()if force._uid(p)!=force._uid(pad)
        and p.GetNetname()=='GND' and p.GetNetCode()==pad.GetNetCode()
        and (peer_uuids is None or force._uid(p)in peer_uuids)
        and model['pins'].get(p.GetNumber())in('ground','power_return','address','reference')),
        key=lambda p:(math.dist(tuple(p.GetPosition()),tuple(pad.GetPosition())),force._uid(p)))
    result=[]
    for peer in peers:
        if time.monotonic()>=deadline:break
        result.extend((peer,ops)for ops in ground_link_ops(board,pad,peer,deadline=deadline,max_link_mm=4.))
    return result


def retained_ground_barrel_ops(board,pad,*,deadline,reach_mm=.8,owner_return_entry=None):
    """Reuse a real grounded immediate barrel instead of duplicating its hole.

    One or two canonical 45-degree legs must fit the actual path-length
    budget. The unchanged through barrel must contact every declared saved
    ground reference. Ordinary via dimensions are NOT permission for partial
    SMD overlap; live pad/process ownership is independently rechecked with
    all proposed strokes present. No fictitious via, relaxed distance, new
    barrel capacity or inferred multi-leg POFV owner is credited.
    """
    import cec_ground_return_policy as return_policy
    allowed=return_policy.reach(pad,{} if owner_return_entry is None else
        {force._uid(pad):owner_return_entry})
    if (pad.GetNetname()!='GND' or pad.HasHole()
            or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
            or type(reach_mm) not in (int,float) or not math.isfinite(reach_mm)
            or not 0<reach_mm<=allowed or type(deadline) not in (int,float)
            or not math.isfinite(deadline)):
        raise ValueError('bounded_native_immediate_ground_barrel_required')
    import cec_ground_return_shortcut as ground
    surface=cell.cec_return_escape.smd_surface_layer(pad)
    if surface is None or pad.GetNetCode()<=0:
        raise ValueError('unique_native_surface_ground_land_required')
    binding=row._source_binding(board);layer=int(surface);start=tuple(pad.GetPosition())
    width=max(200000,int(board.GetDesignSettings().m_TrackMinWidth),int(cell._netclass(board,'GND')['width']))
    gap=max(200000,int(board.GetDesignSettings().m_MinClearance),int(cell._netclass(board,'GND')['clearance']))
    candidates=sorted((v for v in board.GetTracks() if v.GetClass()=='PCB_VIA'
        and v.GetNetCode()==pad.GetNetCode() and v.GetViaType()==pcbnew.VIATYPE_THROUGH
        and v.TopLayer()==pcbnew.F_Cu and v.BottomLayer()==pcbnew.B_Cu and v.IsOnLayer(layer)
        and 0<math.dist(start,tuple(v.GetPosition()))<=reach_mm*1e6),
        key=lambda v:(math.dist(start,tuple(v.GetPosition())),force._uid(v)))[:16]
    choices=[];cache={}
    for via in candidates:
        if time.monotonic()>=deadline:break
        end=tuple(via.GetPosition())
        try:ground._reference_contacts(board,via)
        except ValueError:continue
        diameter=int(via.GetWidth(via.TopLayer()));drill=int(via.GetDrillValue())
        blocked,_=fab.via_at_pad_conflicts(board,via.GetPosition(),diameter,drill,pad.GetNetCode())
        if blocked is not None:continue
        # Literal source identity and a filled reference contact do not
        # qualify a reused plated axis. Recheck its complete existing
        # padstack against every foreign copper face, hole and edge before
        # offering a new ground connection to it. The surface stroke guard
        # below alone cannot see an inherited inner-face barrel conflict.
        import cec_retained_ground_barrel_clearance as barrel_clearance
        if (not fr._edge_leg_clear(board,via.GetPosition(),via.GetPosition(),diameter/2+gap)
                or not barrel_clearance.clear(board,via,gap,deadline=deadline,foreign_cache=cache)):
            continue
        # A qualified fully contained via is already a zero-length return.
        # Do not generate a decorative spoke inside an existing native land.
        if pad.GetEffectiveShape(layer).Collide(via.GetPosition(),diameter//2):continue
        ordinary=(fab.board_legal_through_via_geometry(board,diameter/1e6,drill/1e6)[:2]
            ==(diameter/1e6,drill/1e6))
        # A posed land can enter the BODY of a retained full-class stroke.
        # Re-drawing that exact subinterval makes a covered backtracking
        # duplicate at the old via. Prove the literal native centreline
        # interval, full pad-entry disk and barrel-axis web instead. This
        # never credits a nearby same-net object or a thin centreline kiss.
        import cec_native_track_prefix as prefix
        land=pcbnew.SHAPE_POLY_SET();pad.TransformShapeToPolygon(land,layer,0,1000,pcbnew.ERROR_INSIDE)
        marker=pcbnew.PCB_TRACK(board);marker.SetLayer(layer);marker.SetStart(pad.GetPosition())
        marker.SetEnd(pad.GetPosition());marker.SetWidth(width+4000)
        disk=pcbnew.SHAPE_POLY_SET();marker.TransformShapeToPolygon(disk,layer,0,1000,pcbnew.ERROR_OUTSIDE)
        disk.BooleanSubtract(land)
        if (not disk.OutlineCount() and width+4000<=diameter
                and (ordinary or fab.local_pofv_via_decision(board,via,allow_source_track_body=True)[0])):
            for retained in board.GetTracks():
                if time.monotonic()>=deadline:break
                if (retained.GetClass()=='PCB_TRACK' and retained.GetNetCode()==pad.GetNetCode()
                        and retained.GetLayer()==layer and retained.GetWidth()>=width
                        and prefix.on_centerline(start,retained) and prefix.on_centerline(end,retained)):
                    if row._source_binding(board)!=binding:
                        raise ValueError('retained_ground_body_observation_mutated_source')
                    return [[]]
        for path in fr._canonical_45_xy_paths(start,end):
            if time.monotonic()>=deadline:break
            if any((b[0]-a[0])*(c[0]-b[0])+(b[1]-a[1])*(c[1]-b[1])==0
                    for a,b,c in zip(path,path[1:],path[2:])):continue
            length=sum(math.dist(a,z) for a,z in zip(path,path[1:]))/1e6
            if length>reach_mm:continue
            if not all(fr._edge_leg_clear(board,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*z),width/2+gap)
                    and fr._tap_foreign_clear(board,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*z),
                        width,layer,gap,{pad.GetNetCode()},foreign_cache=cache)
                    for a,z in zip(path,path[1:])):continue
            strokes=[]
            try:
                for a,z in zip(path,path[1:]):
                    stroke=pcbnew.PCB_TRACK(board);stroke.SetNetCode(pad.GetNetCode());stroke.SetLayer(layer)
                    stroke.SetWidth(width);stroke.SetStart(pcbnew.VECTOR2I(*a));stroke.SetEnd(pcbnew.VECTOR2I(*z))
                    board.Add(stroke);strokes.append(stroke)
                if ordinary or fab.local_pofv_via_decision(board,via)[0]:
                    choices.append([('trk',a,z,width,layer) for a,z in zip(path,path[1:])])
            finally:discard_items(board,strokes)
    if row._source_binding(board)!=binding:raise ValueError('retained_ground_barrel_proposal_mutated_source')
    return choices


def _unchanged_retained_surface_contact(original_pad,target_pad,old_track,new_track,layer):
    """Exact original land/stroke metal; a pad centre is not its contact.

    This proves only that an existing boundary needs no new copper. It is
    not an original-contact, current, process or saved-board admission waiver.
    Unsupported native lands conservatively retain their old obligation.
    """
    import cec_native_placement_context as native
    if (old_track is None or new_track is None
            or old_track.GetClass()!='PCB_TRACK' or new_track.GetClass()!='PCB_TRACK'
            or force._uid(original_pad)!=force._uid(target_pad)
            or force._uid(original_pad.GetParentFootprint())!=force._uid(target_pad.GetParentFootprint())):
        return False
    def stroke(t):
        return (force._uid(t),str(t.GetNetname()),int(t.GetLayer()),
            tuple(t.GetStart()),tuple(t.GetEnd()),int(t.GetWidth()),bool(t.IsLocked()),bool(t.HasSolderMask()),
            projected_ground._group_uuid(t.GetBoard(),t))
    # KiCad 10 returns EDA_GROUP (without m_Uuid) from GetParentGroup.
    # Resolve actual UUID-bearing board containers, including literal group
    # membership. Unknown/ambiguous ownership retains the old obligation.
    try:
        if stroke(old_track)!=stroke(new_track) or int(old_track.GetLayer())!=int(layer):return False
    except (ValueError,AttributeError):
        return False
    deadline=time.monotonic()+2.
    before=native._native_stationary_land(original_pad,deadline)
    after=native._native_stationary_land(target_pad,deadline)
    # Numeric NETINFO codes are per-board allocator state. Literal names and
    # each board's own pad/stroke equality own the cross-board comparison.
    def land(identity):
        return None if identity is None else identity[:3]+identity[4:]
    return (before is not None and land(before)==land(after) and original_pad.IsOnLayer(layer)
        and original_pad.GetNetCode()==old_track.GetNetCode()>0
        and target_pad.GetNetCode()==new_track.GetNetCode()>0
        and original_pad.GetEffectiveShape(layer).Collide(old_track.GetEffectiveShape(layer),0))


def obligations(source, board, proposal):
    return _obligations(source,board,proposal)


def _obligations(source,board,proposal,*,composed_supply_fork_tracks=()):
    """Restore external boundaries, not obsolete bends under moved pads."""
    # Only the complete macro compiler uses this internal composition path.
    # Its fresh same-contract union replaces the fork's whole contact tree,
    # not its pad/leaf inventory or mandatory full-width local supply. Public
    # callers have no skip flag; saved macro receiving re-runs the compiler.
    skip={tuple(q)for q in composed_supply_fork_tracks}
    actual={tuple(q['track_uuids'])for q in proposal.get('source_owned_shared_supply_forks',[])}
    if len(skip)!=len(composed_supply_fork_tracks)or not skip<=actual:
        raise ValueError('exact_compiler_composed_source_supply_forks_required')
    # Selected followers can be identity/assignment witnesses at their
    # unchanged pose. They are fixed terminals, not moving cut boundaries.
    # Treating every selected ref as moving rejected an ordinary retained
    # capacitor fork even when its land and all fork tracks stayed exact.
    moved={ref for ref,target in proposal['poses'].items()
        if (tuple(source.FindFootprintByReference(ref).GetPosition())
            !=tuple(round(v*1e6) for v in target[:2])
            or abs((source.FindFootprintByReference(ref).GetOrientationDegrees()
                -target[2]+180)%360-180)>=1e-9)}
    retired = set(proposal['retired_track_uuids'])
    source_pads = [p for fp in source.GetFootprints() for p in fp.Pads()]
    original_pads={force._uid(p):p for p in source_pads}
    original_tracks={force._uid(t):t for t in source.GetTracks()}
    current_tracks={force._uid(t):t for t in board.GetTracks()}
    target_pads = {force._uid(p): p for fp in board.GetFootprints() for p in fp.Pads()}
    requests = {}; leaf_ids = {u for q in [*proposal['measurement_leaves'],*proposal['rated_supply_leaves'],
        *proposal['scalar_links'],*proposal.get('scalar_input_leaves',[]),
        *proposal.get('source_owned_shared_supply_forks',[]),*proposal.get('source_owned_shared_scalar_input_forks',[])]
        for u in q['track_uuids']}
    shared_pads={u for q in [*proposal.get('source_owned_shared_supply_forks',[]),
        *proposal.get('source_owned_shared_scalar_input_forks',[])] for u in q['moving_source_pad_uuids']}
    def pad_end(p):
        return dict(pad_uuid=force._uid(p), at_nm=list(p.GetPosition()),
            layers=[int(l) for l in p.GetLayerSet().CuStack()
                if board.IsLayerEnabled(l)])
    def fixed_end(point, layer, net=None):
        result=dict(at_nm=list(point), layers=[int(layer)])
        if net is not None:
            # Only actual retained copper touching this exact source point
            # can name the component. Nearby same-net material is not a seed.
            material=[*source_pads,*source.GetTracks()]
            seeds=[force._uid(item) for item in material
                if force._uid(item) not in retired and item.GetNetname()==net
                and item.IsOnLayer(layer)
                and (item.GetClass()!='PAD'
                    or item.GetParentFootprint().GetReference() not in moved)
                and item.GetEffectiveShape(layer).Collide(pcbnew.VECTOR2I(*point),0)]
            if 0<len(seeds)<=16:result['native_uuids']=sorted(seeds)
        return result
    def exact_retained_contacts(required,end,net):
        remaining=set(required)-retired;seeds=set(end.get('native_uuids',[]))
        if remaining<=seeds:return True
        import cec_native_component_ports as ports
        excluded=retired|{force._uid(p) for p in source_pads
            if p.GetParentFootprint().GetReference() in moved}
        return ports.retained_members_connected(source,net,seeds,remaining,excluded_uuids=excluded)
    if proposal['inherited_unrouted_measurement_lands']:
        import cec_measurement_terminal_access as terminal_access
        isolated={r['pad_uuid']:r for r in terminal_access.requests(source,
            board_hint=proposal['board_hint'])['requests']}
        for old in proposal['inherited_unrouted_measurement_lands']:
            demand=isolated.get(old['pad_uuid'])
            if demand is None:continue
            owner=target_pads[demand['pad_uuid']];pickup=target_pads[demand['target_uuid']]
            requests['isolated_measurement:'+demand['pad_uuid']]=dict(kind='isolated_measurement',
                net=demand['net'],a=pad_end(owner),b=pad_end(pickup),width_nm=200000,
                source_measurement_demand=demand)
    for q in proposal['measurement_leaves']:
        p = target_pads[q['pad_uuid']]
        target_leaf = dict(q, points_nm=[list(p.GetPosition()), *q['points_nm'][1:]])
        boundary_pads = [source_pad for source_pad in source_pads
            if force._uid(source_pad) in q['boundary_uuids']
            and source_pad.GetParentFootprint().GetReference() in moved]
        if boundary_pads:
            if (len(boundary_pads) != 1 or q['boundary_uuids'] != [force._uid(boundary_pads[0])]
                    or boundary_pads[0].GetParentFootprint().GetReference() != p.GetParentFootprint().GetReference()
                    or list(boundary_pads[0].GetPosition()) != q['points_nm'][-1]):
                raise ValueError('unique_moving_intrapackage_measurement_boundary_required')
            target_boundary = target_pads[force._uid(boundary_pads[0])]
            target_leaf['points_nm'][-1] = list(target_boundary.GetPosition())
            # Source-derived internal two-land contact, recompiled from the
            # actual final lands rather than an obsolete absolute endpoint.
            if len(q['points_nm']) != 2:
                raise ValueError('bounded_two_land_internal_measurement_contact_required')
            target_leaf['source_boundary_entry_nm'] = [list(p.GetPosition()), list(target_boundary.GetPosition())]
        key='measurement:'+q['pad_uuid']
        if q['scope']=='source_typed_same_net_auxiliary_measurement_strap':
            key+=':auxiliary:'+q['boundary_uuids'][0]
        if key in requests:raise ValueError('unique_complete_measurement_obligation_required')
        requests[key] = dict(kind='measurement', net=q['net'],
            a=pad_end(p), b=fixed_end(target_leaf['points_nm'][-1], q['layer']), width_nm=q['width_nm'],
            source_leaf=target_leaf)
    for q in proposal['scalar_links']:
        requests['scalar_link:'+q['pad_uuid']]=dict(kind='source_boundary',net=q['net'],
            a=pad_end(target_pads[q['pad_uuid']]),b=pad_end(target_pads[q['peer_pad_uuid']]),
            width_nm=q['width_nm'])
    for q in proposal.get('scalar_input_leaves',[]):
        moving=[p for p in source_pads if force._uid(p) in q['boundary_uuids']
            and p.GetParentFootprint().GetReference() in moved]
        if moving:
            if len(moving)!=1 or q['boundary_uuids']!=[force._uid(moving[0])]:
                raise ValueError('unique_moving_scalar_input_boundary_required')
            end=pad_end(target_pads[force._uid(moving[0])])
        else:
            end=fixed_end(q['points_nm'][-1],q['layer'],q['net'])
            if not exact_retained_contacts(q['boundary_uuids'],end,q['net']):
                raise ValueError('exact_retained_scalar_input_contact_required')
        requests['scalar_input:'+q['pad_uuid']]=dict(kind='source_boundary',net=q['net'],
            a=pad_end(target_pads[q['pad_uuid']]),b=end,width_nm=q['width_nm'],
            source_typed_scalar_input=q,sensitive_role_reclassification=False)
    for q in proposal['rated_supply_leaves']:
        pad=target_pads[q['pad_uuid']];point=q['points_nm'][-1]
        peers=[p for p in source_pads if force._uid(p) in q['boundary_uuids']
            and p.GetParentFootprint().GetReference() in moved]
        if peers:
            extra=set(q['boundary_uuids'])-{force._uid(p) for p in peers}
            if len(peers)!=1:
                raise ValueError('unique_rated_supply_moving_boundary_required')
            peer=target_pads[force._uid(peers[0])]
            # The positively source-selected owner/cap pair already has one
            # mandatory local_supply domain; avoid duplicate parallel copper.
            local_pair=any(({force._uid(pad),force._uid(peer)}=={
                    force._uid(board.FindFootprintByReference(selected['owner']).FindPadByNumber(selected['pin'])),
                    force._uid(next(p for p in board.FindFootprintByReference(cap).Pads()
                        if p.GetNetname()==selected['rail']))})
                    for cap,selected in proposal['selected_bypasses'].items())
            retained=extra-retired
            if retained:
                # A leaf's terminal capsule can touch BOTH the selected
                # moving capacitor land and a real stationary feed. Moving
                # the pair must not discard the latter or invent an island
                # attachment. Receive every retained boundary at the exact
                # source endpoint; ambiguous/off-centre-only seeds refuse.
                target=fixed_end(point,q['layer'],q['net'])
                if not retained<=set(target.get('native_uuids',[])):
                    raise ValueError('exact_retained_rated_supply_contact_required')
                if not local_pair:
                    requests['rated_supply_peer:'+q['pad_uuid']]=dict(kind='source_boundary',net=q['net'],
                        a=pad_end(pad),b=pad_end(peer),width_nm=q['width_nm'],
                        unchanged_full_rail_current_contract=q['unchanged_full_rail_current_contract'])
            elif local_pair:continue
            else:target=pad_end(peer)
        else:target=fixed_end(point,q['layer'],q['net'])
        requests['rated_supply:'+q['pad_uuid']]=dict(kind='source_boundary',net=q['net'],
            a=pad_end(pad),b=target,width_nm=q['width_nm'],
            unchanged_full_rail_current_contract=q['unchanged_full_rail_current_contract'])
    rows = proposal['row_plan']['source_incident_boundaries']
    for uid in sorted(retired - leaf_ids):
        track = next(t for t in source.GetTracks() if force._uid(t) == uid)
        if track.GetNetname() == 'GND':
            # Ground gets immediate process-qualified entries; the original
            # source partition receiver still requires EVERY retained mesh
            # branch/barrel to be in the moved pad's final native component.
            continue
        ends = []
        for point in (track.GetStart(), track.GetEnd()):
            touched = [p for p in source_pads if p.GetParentFootprint().GetReference() in moved
                and p.GetNetCode() == track.GetNetCode() and p.IsOnLayer(track.GetLayer())
                and p.GetEffectiveShape(track.GetLayer()).Collide(pcbnew.VECTOR2I(*point), 0)]
            if len(touched) > 1:
                raise ValueError('ambiguous_retired_cell_endpoint_owner')
            ends.append(pad_end(target_pads[force._uid(touched[0])]) if touched
                else fixed_end(point, track.GetLayer(),str(track.GetNetname())))
        if ends[0]['at_nm'] == ends[1]['at_nm']:
            continue
        requests['boundary:'+uid] = dict(kind='source_boundary', net=str(track.GetNetname()),
            a=ends[0], b=ends[1], width_nm=int(track.GetWidth()))
    for contact in rows:
        if contact['track_uuid'] in retired:
            continue
        if contact['pad_uuid'] in shared_pads:continue
        p = target_pads[contact['pad_uuid']]
        if str(p.GetNetname()) == 'GND':
            continue
        if (p.GetParentFootprint().GetReference() not in moved
                and _unchanged_retained_surface_contact(original_pads[contact['pad_uuid']],p,
                    original_tracks.get(contact['track_uuid']),current_tracks.get(contact['track_uuid']),contact['layer'])):
            # Native source contacts are often off-centre, including full
            # rated strokes at a land edge. An identical stationary package
            # and retained stroke do not owe a fictional centre-to-contact
            # route or a new whole-net/current classification.
            continue
        # Even retained/protected source copper has to be reached again.
        if list(p.GetPosition()) == contact['contact_nm']:
            continue
        requests['retained:'+contact['pad_uuid']+':'+contact['track_uuid']] = dict(
            kind='source_boundary', net=str(p.GetNetname()), a=pad_end(p),
            b=dict(at_nm=contact['contact_nm'],layers=[contact['layer']],
                native_uuids=[contact['track_uuid']]), width_nm=contact['width_nm'])
    retained_items={force._uid(t):t for t in source.GetTracks() if force._uid(t) not in retired}
    for contact in proposal['row_plan']['source_native_barrel_boundaries']:
        p=target_pads[contact['pad_uuid']]
        if contact['pad_uuid'] in shared_pads:continue
        if p.GetParentFootprint().GetReference() not in moved or p.GetNetname()=='GND':continue
        model=proposal['device_contracts'].get(p.GetParentFootprint().GetReference())
        if model and model['pins'].get(p.GetNumber())=='measurement':
            # A direct measurement barrel is not an ordinary whole-rail
            # target. Its typed aperture still belongs to specialized leaf
            # restoration and the native partition receiver.
            continue
        via=retained_items.get(contact['via_uuid'])
        if (via is None or via.GetClass()!='PCB_VIA' or via.GetNetname()!=p.GetNetname()
                or list(via.GetPosition())!=contact['contact_nm']):
            raise ValueError('exact_source_direct_barrel_boundary_required')
        if p.IsOnLayer(contact['layer']) and p.GetEffectiveShape(contact['layer']).Collide(
                via.GetEffectiveShape(contact['layer']),0):continue
        requests['retained_barrel:'+contact['pad_uuid']+':'+contact['via_uuid']]=dict(
            kind='source_boundary',net=str(p.GetNetname()),a=pad_end(p),
            b=dict(at_nm=contact['contact_nm'],layers=contact['layers'],native_uuids=[contact['via_uuid']]),
            width_nm=max(200000,int(board.GetDesignSettings().m_TrackMinWidth)))
    for cap, selected in proposal['selected_bypasses'].items():
        owner = board.FindFootprintByReference(selected['owner']).FindPadByNumber(selected['pin'])
        supply = next(p for p in board.FindFootprintByReference(cap).Pads()
            if p.GetNetname() == selected['rail'])
        requests['local_supply:'+force._uid(owner)] = dict(kind='local_supply',
            net=selected['rail'], a=pad_end(owner), b=pad_end(supply), width_nm=200000)
        for fork in proposal.get('source_owned_shared_supply_forks',[]):
            if fork['net']==selected['rail']:
                requests['local_supply:'+force._uid(owner)].update(
                    width_nm=max(200000,fork['width_nm']),
                    unchanged_full_rail_current_contract=fork['unchanged_full_rail_current_contract'])
    mandatory=[(r['a']['pad_uuid'],r['b']['pad_uuid']) for r in requests.values() if r['kind']=='local_supply']
    for kind,key in (('supply','source_owned_shared_supply_forks'),('scalar_input','source_owned_shared_scalar_input_forks')):
        for index,fork in enumerate(proposal.get(key,[])):
            if kind=='supply'and tuple(fork['track_uuids'])in skip:continue
            choice=[u for u in proposal.get('shared_supply_root_pad_uuids',())if u in fork['moving_source_pad_uuids']]
            for ordinal,request in enumerate(shared_fork.connections(board,fork,mandatory_links=mandatory,
                    **(dict(preferred_supply_root_pad_uuids=choice)if choice else {}))):
                requests['shared_'+kind+':'+str(index)+':'+str(ordinal)]=request
    # A fixed owner is an identity witness, not a moving low-power load
    # whose Ground may be newly routed through the cap. The capacitor's OWN
    # immediate Ground request below remains mandatory, including when its
    # stationary owner is a mux/regulator with power-output or switch pins.
    linear_ground={}
    if (proposal.get('allow_linear_power_stage_reconstruction')
            or proposal.get('source_linear_power_stages')):
        import cec_linear_stage_ground_entries as stage_ground
        # Positively rederive the distinct full-current stage. Its roots
        # must not borrow the low-power owner's through-cap/package portal.
        linear_ground=stage_ground.entries(source,board,proposal,
            board_hint=proposal['board_hint'])
    independent_stage_caps=set(linear_ground.get('selected_bypasses',{}))
    moving_owner_bypasses={cap:selected for cap,selected in proposal['selected_bypasses'].items()
        if selected['owner'] not in proposal['stationary_device_owners']and cap not in independent_stage_caps}
    entries = assigned_ground_entries(board, moving_owner_bypasses,
        board_hint=proposal['board_hint'])
    import cec_ground_return_policy as return_policy
    # A stationary selected cap still provides a mandatory native root for
    # its moving owner. Receive its actual ground access, never an assumed
    # capacitor dependency or fictitious new via.
    for ref in moved|set(proposal['selected_bypasses']):
        if ref in proposal['stationary_device_owners']:
            continue
        if ref in proposal.get('additional_aggregate_capacitors',{}):
            # The separate Source role supplies its own stricter immediate
            # return request; never overwrite it with a generic Ground reach.
            continue
        for p in board.FindFootprintByReference(ref).Pads():
            if p.GetNetname() == 'GND':
                requests['ground:'+force._uid(p)] = dict(kind='ground', net='GND',
                    a=pad_end(p), reach_mm=return_policy.reach(p,entries),
                    same_package_ground_link_proposal_allowed=ref in proposal['device_contracts'])
                if force._uid(p) in entries:
                    requests['ground:'+force._uid(p)]['selected_bypass_entry'] = entries[force._uid(p)]
                fixed=proposal.get('native_stationary_ground_lands',{}).get(force._uid(p))
                if fixed is not None and fixed['source_return_mm'] is not None:
                    requests['ground:'+force._uid(p)]['retained_stationary_source_return']=fixed
                projected=proposal.get('native_projected_ground_contacts',{}).get(force._uid(p))
                if projected is not None:
                    requests['ground:'+force._uid(p)]['retained_projected_source_return']=projected
    for key,request in linear_ground.get('independent_ground_requests',{}).items():
        if key not in requests or requests[key]['kind']!='ground':
            raise ValueError('linear_stage_independent_ground_root_obligation_missing')
        # Replace the exact re-proved roots, not an open-ended net scope;
        # no inherited shortcut or unqualified old-return metadata survives.
        requests[key]=request
    # A new return for a moving pad does not reconnect a stationary fork or
    # copper-only branch detached by the same source-owned Ground cut.
    import cec_cell_ground_cut_boundaries as ground_boundaries
    cut_ground=ground_boundaries.requests(source,board,proposal)
    requests.update(cut_ground)
    import cec_stationary_owner_ground_obligations as stationary_ground
    requests=stationary_ground.merge(requests,
        stationary_ground.requests(source,board,proposal,cut_ground))
    import cec_address_supply_obligations as address_supply
    requests.update(address_supply.requests(source,board,proposal))
    requests.update(control_shunt.requests(source,board,proposal))
    requests.update(control_pullup.requests(source,board,proposal))
    requests.update(control_gate_bias.requests(source,board,proposal))
    import cec_programming_resistor_placement as programming
    requests.update(programming.requests(source,board,proposal))
    import cec_source_signal_bias_placement as signal_bias
    requests.update(signal_bias.requests(source,board,proposal))
    if proposal.get('additional_aggregate_capacitors'):
        import cec_additional_aggregate_macro as aggregate_caps
        additional_requests=aggregate_caps.requests(source,board,proposal)
        if requests.keys()&additional_requests.keys():
            raise ValueError('additional_aggregate_obligation_identity_collision')
        requests.update(additional_requests)
    if not requests or len(requests) > 64:
        raise ValueError('bounded_complete_cell_obligation_inventory_required')
    return requests


def _native_ops(board, ops, net):
    made = []
    enabled_copper = set(map(int, board.GetEnabledLayers().CuStack()))
    if board.GetNetcodeFromNetname(net) <= 0:
        raise ValueError('native_cell_operation_net_identity_missing')
    # Validate the whole packet before adding its first object.
    for op in ops:
        if (not isinstance(op, (list, tuple)) or not op
                or (op[0] == 'trk' and (len(op) != 5 or op[1] == op[2]
                    or not 0 < op[3] <= 100000000
                    or op[4] not in enabled_copper
                    or (op[1][0] != op[2][0] and op[1][1] != op[2][1]
                        and abs(op[1][0]-op[2][0]) != abs(op[1][1]-op[2][1]))))
                or (op[0] == 'via' and (len(op) != 4 or not 0 < op[2] < op[3] <= 2))
                or op[0] not in ('trk', 'via')):
            raise ValueError('invalid_octilinear_native_cell_operation')
    # Independent obligations may legitimately share an identical supply
    # segment. Reuse that exact native metal instead of constructing a
    # duplicate, which the craft gate correctly reports as a backtrack.
    # This changes no retained conductor, width, rule, group or endpoint.
    # A longer retained stroke or a gap-free collinear UNION may likewise
    # cover a segmented demand. Reuse only exact sufficient-width native
    # capsules, never off-axis overlap or a different face/net. Full current
    # and terminal-path receiving still decides whether that metal suffices.
    def track_key(a,b,width,layer):
        return (net,int(layer),int(width),tuple(sorted((tuple(a),tuple(b)))))
    existing={track_key(t.GetStart(),t.GetEnd(),t.GetWidth(),t.GetLayer())
        for t in board.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetNetname()==net}
    retained=[t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetNetname()==net]
    from cec_additive_portal_compaction import covered_by_collinear_union
    for op in ops:
        if op[0] == 'trk':
            _, a, b, width, layer = op
            key=track_key(a,b,width,layer)
            if key in existing:continue
            item = pcbnew.PCB_TRACK(board); item.SetStart(pcbnew.VECTOR2I(*a))
            item.SetEnd(pcbnew.VECTOR2I(*b)); item.SetWidth(width); item.SetLayer(layer)
            item.SetNetCode(board.GetNetcodeFromNetname(net))
            if covered_by_collinear_union(item,retained):continue
        elif op[0] == 'via':
            _, at, drill, diameter = op
            item = pcbnew.PCB_VIA(board); item.SetPosition(pcbnew.VECTOR2I(*at))
            item.SetWidth(round(diameter*1e6)); item.SetDrill(round(drill*1e6))
            item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); item.SetViaType(pcbnew.VIATYPE_THROUGH)
        else:
            raise ValueError('unknown_cell_escape_native_operation')
        item.SetNetCode(board.GetNetcodeFromNetname(net)); item.SetLocked(True)
        board.Add(item); made.append(item)
        if op[0]=='trk':existing.add(key);retained.append(item)
    return made


def native_barrel_blockers(board, at_nm, net, *, diameter_mm, max_blockers=16):
    """Name actual all-layer copper at a seat; not a via/factory certificate."""
    if (type(diameter_mm) not in (int,float) or not math.isfinite(diameter_mm)
            or not 0 < diameter_mm <= 2 or type(max_blockers) is not int or not 1 <= max_blockers <= 64):
        raise ValueError('bounded_native_barrel_diagnostic_required')
    code = board.GetNetcodeFromNetname(net)
    if code <= 0:
        raise ValueError('native_barrel_net_identity_missing')
    marker = pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*at_nm), pcbnew.VECTOR2I(*at_nm),
        round(diameter_mm*1e6))
    gap = max(200000,int(cell._netclass(board,net)['clearance']))
    blockers = []
    for layer in board.GetEnabledLayers().CuStack():
        zones,copper = fr._layer_foreign_shapes(board,layer,{code},identified=True)
        for shape,_,identity,local_gap in [*zones,*copper]:
            if shape.Collide(marker,max(gap,local_gap)):
                blockers.append(dict(layer=board.GetLayerName(layer),native=identity))
                if len(blockers) >= max_blockers:
                    return blockers
    return blockers


def retained_ground_reference_connection(board,request,*,timeout_s=10.):
    """A typed cut between actual plated reference entries needs no echo.

    This emits no copper or holes and cannot qualify a remote SMD return.
    Same net/zone identifiers or XY proximity are not connectivity evidence:
    both complete real barrels must contact every declared reference face
    and be connected in the native retained-material connectivity graph.
    """
    import cec_ground_return_shortcut as reference
    if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.:
        raise ValueError('bounded_retained_ground_reference_connection_required')
    deadline=time.monotonic()+timeout_s
    authorities=request.get('exact_additional_macro_component_source_ownership')
    if (request.get('kind')!='source_boundary' or request.get('net')!='GND'
            or request.get('every_surviving_source_component_port_mandatory') is not True
            or type(authorities) is not list or not 1<=len(authorities)<=64
            or any(q.get('kind')!='positive_existing_low_power_ground_boundary' for q in authorities)):
        return None
    live={force._uid(t):t for t in board.GetTracks()};entries=[]
    owned_barrels={q.get('via_uuid') for a in authorities for q in a.get('source_owned_barrel_roots',[])}
    enabled=set(map(int,board.GetEnabledLayers().CuStack()))
    for end in ('a','b'):
        port=request.get(end,{})
        ids=port.get('native_uuids')
        if (type(ids) is not list or len(ids)!=1 or ids[0] not in live
                or port.get('pad_uuid') is not None or type(port.get('layers')) is not list
                or not port['layers'] or any(type(face) is not int or face not in enabled for face in port['layers'])):
            return None
        contact=live[ids[0]];via=contact
        if contact.GetClass()=='PCB_TRACK':
            # A literal factory pickup endpoint may be named instead of its
            # coincident barrel. Resolve only the exact axis of a barrel
            # independently owned in this Source boundary proof. Never pick
            # a nearby same-net via or traverse an arbitrary Ground mesh.
            point=port.get('at_nm');faces=port.get('layers')
            if (contact.GetNetname()!='GND' or not faces or type(point) is not list or len(point)!=2
                    or any(not contact.IsOnLayer(face) or not contact.GetEffectiveShape(face).Collide(
                        pcbnew.VECTOR2I(*point),0) for face in faces)):return None
            matches=[live[u] for u in owned_barrels if u in live and live[u].GetClass()=='PCB_VIA'
                and list(live[u].GetPosition())==point and live[u].GetNetname()=='GND'
                and all(live[u].IsOnLayer(face) and contact.GetWidth()<=live[u].GetWidth(face) for face in faces)]
            if len(matches)!=1:return None
            via=matches[0]
        if (via.GetClass()!='PCB_VIA' or via.GetNetname()!='GND'
                or via.GetViaType()!=pcbnew.VIATYPE_THROUGH
                or via.TopLayer()!=pcbnew.F_Cu or via.BottomLayer()!=pcbnew.B_Cu
                or list(via.GetPosition())!=port.get('at_nm') or not port.get('layers')
                or any(not via.IsOnLayer(face) for face in port['layers'])):return None
        d,h=via.GetWidth(via.TopLayer())/1e6,via.GetDrillValue()/1e6
        if (fab.board_legal_through_via_geometry(board,d,h)[:2]!=(d,h)
                and not fab.local_pofv_via_decision(board,via,allow_source_track_body=True)[0]):return None
        try:contacts=reference._reference_contacts(board,via)
        except ValueError:return None
        entries.append(dict(uuid=force._uid(via),native_port_uuid=ids[0],actual_filled_reference_contacts=contacts))
        if time.monotonic()>=deadline:raise ValueError('retained_ground_reference_connection_deadline')
    graph=fr._read_only_route_connectivity(board)
    reached={force._uid(t) for t in graph.GetConnectedItems(live[entries[0]['uuid']])}
    if entries[1]['uuid'] not in reached:return None
    if time.monotonic()>=deadline:raise ValueError('retained_ground_reference_connection_deadline')
    return dict(entries=entries,actual_native_retained_connectivity_proved=True,new_copper=0,new_holes=0,
        remote_smd_return_not_inferred=True,current_qualified=False,routing_admitted=False,release_authority=False)


def local_supply_path_limit(request,direct_mm,width_mm,gap_mm):
    """Retain the existing limit, tightened by explicit Source local intent.

    The complete saved receiver rederives the originating Source role. These
    fields are rejection-only: they cannot broaden a route, face or budget.
    """
    limit=cell._local_supply_limit_mm(direct_mm,width_mm,gap_mm)
    keys={'source_maximum_same_surface_path_mm','source_required_surface_layer'}
    present=keys&request.keys()
    if present:
        bound=request.get('source_maximum_same_surface_path_mm')
        face=request.get('source_required_surface_layer')
        if (present!=keys or request.get('kind')!='local_supply'
                or type(bound)not in(int,float)or not math.isfinite(bound)or not 0<bound<=3.5
                or type(face)is not int or face not in(int(pcbnew.F_Cu),int(pcbnew.B_Cu))
                or any(request.get(end,{}).get('layers')!=[face]for end in('a','b'))):
            raise ValueError('complete_Source_same_surface_local_supply_bound_required')
        limit=min(limit,bound)
    return limit


def retained_local_supply_connection(board,request,*,timeout_s=10.):
    """Observe an EXISTING bounded physical bypass link; add no copper.

    Native reachability and an explicit-copper shortest path are both needed.
    A plane, same-net label, remote detour or output pin cannot substitute.
    This observation grants no current or clearance qualification; original
    Source compilation and independent saved/whole-board receiving remain.
    """
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.):
        raise ValueError('bounded_retained_local_supply_observation_required')
    if type(request) is not dict or request.get('kind')!='local_supply':return None
    started=time.monotonic();pads={force._uid(p):p for fp in board.GetFootprints() for p in fp.Pads()}
    a,b=[pads.get(request.get(end,{}).get('pad_uuid')) for end in ('a','b')]
    if a is None or b is None or force._uid(a)==force._uid(b):return None
    net=request.get('net');owner=a.GetParentFootprint();cap=b.GetParentFootprint()
    model=roles.footprint_contract(owner)
    if (not model or model['pins'].get(a.GetNumber())!='power_input'
            or set(model['pins'])!={p.GetNumber() for p in owner.Pads()}
            or len(list(cap.Pads()))!=2 or {p.GetNetname() for p in cap.Pads()}!={net,'GND'}
            or a.GetNetname()!=net or b.GetNetname()!=net or a.GetNetCode()<=0
            or owner.IsFlipped()!=cap.IsFlipped()):return None
    for key,pad in (('a',a),('b',b)):
        end=request[key]
        if (list(pad.GetPosition())!=end.get('at_nm')
                or list(map(int,pad.GetLayerSet().CuStack()))!=end.get('layers')
                or pad.HasHole() or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD):return None
    direct=math.dist(tuple(a.GetPosition()),tuple(b.GetPosition()))/1e6
    if direct>3.5:return None
    graph=fr._read_only_route_connectivity(board)
    if force._uid(b) not in {force._uid(t) for t in graph.GetConnectedItems(a)}:return None
    length=cell._shortest_track_path_mm(board,a,b,snap_mm=.000001)
    spec=cell._netclass(board,net);gap=max(200000,int(spec['clearance']))
    width=max(int(request.get('width_nm',0)),int(spec['width']))
    limit=local_supply_path_limit(request,direct,width/1e6,gap/1e6)
    if length is None or length>limit or time.monotonic()-started>timeout_s:return None
    return dict(owner_pad_uuid=force._uid(a),capacitor_pad_uuid=force._uid(b),
        explicit_native_path_mm=length,limit_mm=limit,native_reachability_proved=True,
        zone_edges_excluded=True,new_copper=0,new_holes=0,current_qualified=False,release_authority=False)


def retained_native_boundary_connection(board,request,*,timeout_s=10.):
    """Prove literal boundary contacts without adding echo copper.

    Only actual same-net pads/tracks/barrels participate. Zone/plane edges,
    foreign shorts, ambiguous custom-pad islands and guessed nearby ports do
    not form this proof. Every named contact is mandatory. Original current,
    Kelvin, physical-return and saved-partition receivers remain independent.
    """
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.):
        raise ValueError('bounded_retained_native_boundary_observation_required')
    if type(request)is not dict:return None
    proof=request.get('retained_source_ground_fragment')or {}
    typed_ground=(request.get('kind')=='ground_boundary'and request.get('net')=='GND'
        and proof.get('actual_fixed_source_contacts_not_same_net_proximity')is True
        and proof.get('whole_original_current_plane_and_saved_partition_receiving_required')is True)
    if not typed_ground and (request.get('kind')!='source_boundary'or request.get('net')=='GND'):return None
    started=time.monotonic();net=request.get('net')
    items=[p for f in board.GetFootprints() for p in f.Pads() if p.GetNetname()==net]
    items.extend(t for t in board.GetTracks() if t.GetNetname()==net)
    if not 1<=len(items)<=4096:return None
    if any(p.GetClass()=='PAD' and p.GetShape() not in
            (pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT,pcbnew.PAD_SHAPE_CIRCLE,pcbnew.PAD_SHAPE_OVAL)
            for p in items):return None
    live={force._uid(t):t for t in items}
    ends=[]
    for name in ('a','b'):
        end=request.get(name,{})
        ids=[end['pad_uuid']] if end.get('pad_uuid') else end.get('native_uuids')
        point=end.get('at_nm');layers=end.get('layers')
        if (type(ids) is not list or not 1<=len(ids)<=16 or len(set(ids))!=len(ids)
                or not set(ids)<=live.keys() or type(point) is not list or len(point)!=2
                or any(type(x) is not int for x in point) or type(layers) is not list or not layers):return None
        for uid in ids:
            item=live[uid]
            if item.GetNetCode()<=0 or not all(board.IsLayerEnabled(lid) and item.IsOnLayer(lid)
                    and item.GetEffectiveShape(lid).Collide(pcbnew.VECTOR2I(*point),0) for lid in layers):return None
        ends.append(ids)
    graph=pcbnew.CONNECTIVITY_DATA()
    for item in items:
        if time.monotonic()-started>timeout_s:return None
        if not graph.Add(item):return None
    reached={ends[0][0]}|{force._uid(t) for t in graph.GetConnectedItems(live[ends[0][0]])}
    if not set(ends[0]+ends[1])<=reached or time.monotonic()-started>timeout_s:return None
    return dict(source_endpoint_native_uuids=ends,all_named_contacts_connected=True,
        zone_and_foreign_net_edges_excluded=True,new_copper=0,new_holes=0,
        typed_source_ground_fragment=typed_ground,
        physical_return_and_original_current_receiving_still_required=True,
        current_qualified=False,release_authority=False)


def _typed_macro_ground_scope(request):
    """Recognize compiler-owned small return restoration, never a load rating.

    This is a menu policy only. Complete construction and saved receiving
    independently recompile the exact Source proof before using any offer;
    an ordinary request label or same-net Ground contact grants nothing.
    """
    authorities=request.get('exact_additional_macro_component_source_ownership')
    width=request.get('width_nm')
    if (request.get('kind')!='source_boundary' or request.get('net')!='GND'
            or request.get('every_surviving_source_component_port_mandatory') is not True
            or type(width) is not int or not 0<width<=20000000
            or type(authorities) is not list or not 1<=len(authorities)<=64):return None
    ids=[];source_widths=[];source_class_floors=[]
    def owner(root):
        if (type(root) is not dict or any(type(root.get(k)) is not str or not root[k]
                for k in ('pad_uuid','ref','role'))):return False
        if root['role']=='source_selected_bypass_ground':
            selected=root.get('selected_bypass')
            return bool(type(selected) is dict and all(type(selected.get(k)) is str and selected[k]
                for k in ('owner','pin','rail')))
        if root['role']=='source_optional_ground_attachment':
            proof=root.get('source_ground_attachment')
            if type(proof)is not dict:return False
            manufacturer=proof.get('manufacturer')
            return bool(root.get('primary_manufacturer_role')=='no_connect'
                and root.get('functional_ground_return')is False and root.get('current_authority')is False
                and root.get('source_ground_strap_restored_without_role_or_current_reclassification')is True
                and proof.get('kind')=='explicit_manufacturer_optional_ground_metal'
                and proof.get('pad_uuid')==root['pad_uuid'] and proof.get('owner')==root['ref']
                and proof.get('net')=='GND'
                and all(proof.get(k)is False for k in
                    ('functional_ground_return','bypass_owner','current_authority','release_authority'))
                and type(manufacturer)is dict
                and manufacturer.get('scope')=='manufacturer_optional_external_ground_attachment'
                and manufacturer.get('permitted_external_nets')==['GND']
                and all(manufacturer.get(k)is False for k in
                    ('functional_ground_return','current_authority','release_authority')))
        import cec_programming_resistor_placement as programming
        if root['role']==programming.GROUND_ROLE:
            return programming.ground_root_label(root)
        return bool(root['role'] in ('ground','reference','power_return','address')
            and root.get('manufacturer_source')
            and root.get('source_ground_strap_restored_without_role_or_current_reclassification') is True)
    for authority in authorities:
        import cec_source_ground_continuation as continuation
        continued=authority.get('kind')==continuation.KIND if type(authority)is dict else False
        if (type(authority) is not dict
                or authority.get('kind')not in('positive_existing_low_power_ground_boundary',continuation.KIND)
                or type(authority.get('native_source_uuid')) is not str or not authority['native_source_uuid']
                or not continued and authority.get('source_width_preserved_not_aggregate_ground_injection_rating') is not True
                or authority.get('every_source_partition_and_physical_return_still_requires_receiving') is not True
                or authority.get('current_authority') is not False):return None
        if continued:
            original=continuation.ground_root_authorities(authority)
            if original is None:return None
            roots=[q for a in original for q in a['source_pad_roots']]
            barrels=[]
        else:
            roots=authority.get('source_pad_roots');barrels=authority.get('source_owned_barrel_roots')
        if (type(roots) is not list or type(barrels) is not list or len(roots)+len(barrels)>64):return None
        roots=list(roots)
        for barrel in barrels:
            if (type(barrel) is not dict or type(barrel.get('via_uuid')) is not str or not barrel['via_uuid']
                    or type(barrel.get('source_terminal_owners')) is not list
                    or not 1<=len(barrel['source_terminal_owners'])<=64):return None
            roots+=barrel['source_terminal_owners']
        if not roots or any(not owner(root) for root in roots):return None
        dimensions=[authority.get(k)for k in('source_width_nm','source_full_class_width_nm')]
        if any(type(v)is not int or not 0<v<=20000000 for v in dimensions):return None
        source_widths.append(dimensions[0]);source_class_floors.append(dimensions[1])
        ids.append(authority['native_source_uuid'])
    if len(set(ids))!=len(ids):return None
    literal=max(source_widths);full=max(literal,*source_class_floors)
    if width not in(literal,full)or literal>max(350000,*source_class_floors):return None
    return dict(source_track_uuids=sorted(ids),source_width_nm=width,
        source_full_class_width_nm=full,
        original_net_class_minimum_still_required=True,not_aggregate_ground_injection_rating=True,
        whole_original_current_receiving_still_required=True,
        every_original_partition_and_physical_ground_return_still_required=True,
        current_authority=False,release_authority=False)


def _source_current_via_geometry(board, current, contact_layers, *, minimum_width_nm=0):
    """Conservative proposal for the explicitly possible contact faces only.

    This consumes a freshly derived current contract, not caller current or
    barrel ampacity. A multi-face search sizes for every face it may contact;
    final materialized receiving still derives the actual native contacts.
    """
    authority=(current or {}).get('current_authority') or {}
    amps=authority.get('amps')
    if type(amps) not in (int,float) or not math.isfinite(amps) or amps<=0:
        raise ValueError('positive_source_current_contact_authority_required')
    faces=set(contact_layers);raw_floors=(current or {}).get('required_by_layer_nm')
    floors={}
    if isinstance(raw_floors,dict):
        for key,value in raw_floors.items():
            # Saved compiler packets use JSON object keys; accept only the
            # exact integer spelling, never aliases or duplicate identities.
            if type(key) is int:layer=key
            elif type(key) is str and key.isdecimal() and str(int(key))==key:layer=int(key)
            else:raise ValueError('positive_source_current_contact_face_widths_required')
            if layer in floors:raise ValueError('duplicate_source_current_contact_face')
            floors[layer]=value
    enabled=set(map(int,board.GetEnabledLayers().CuStack()))
    if (not isinstance(raw_floors,dict) or not faces or not faces<=enabled
            or type(minimum_width_nm) is not int or minimum_width_nm<0
            or any(type(l) is not int or l not in floors
                or type(floors[l]) is not int or floors[l]<=0 for l in faces)):
        raise ValueError('positive_source_current_contact_face_widths_required')
    web=max(minimum_width_nm,*(floors[l] for l in faces))
    diameter,drill,_=fab.board_legal_through_via_geometry(board,.6,.3)
    # Recompute using the ACTUAL board-clamped drill, never its requested
    # minimum. Re-resolve the enlarged land through the same process gates.
    diameter,drill,_=fab.board_legal_through_via_geometry(board,
        max(diameter,math.ceil(drill*1e6+web)/1e6),drill)
    if (not all(math.isfinite(v) and v>0 for v in (diameter,drill))
            or round(diameter*1e6)-round(drill*1e6)<web):
        raise ValueError('source_current_full_contact_web_geometry_unresolved')
    return dict(dia=diameter,drill=drill,minimum_local_via_web_nm=web)


def _connection_menu(board, request, *, board_hint, deadline, layers, append, detail,
                     source_board=None, shared_power_pad_uuids=(), full_net_width_nm=0,
                     source_requests=None):
    """Explore contacts without moving/derating the named retained component."""
    import cec_native_component_ports as ports
    net=request['net'];code=board.GetNetcodeFromNetname(net)
    typed_quiet=request.get('kind')=='source_typed_incoming_quiet_output'
    if typed_quiet:
        import cec_macro_quiet_output as quiet_outputs
        if source_board is None:raise ValueError('literal_quiet_Source_context_required')
        policy=quiet_outputs._policy(source_board,source_board.GetFileName(),net)
        if policy!=request.get('source_policy') or policy['allowed_layers']!=request.get('allowed_layers'):
            raise ValueError('exact_quiet_Source_signal_layer_policy_required')
        layers=[face for face in layers if face in policy['allowed_layers']]
    a,b=request['a'],request['b']
    reference=retained_ground_reference_connection(board,request,
        timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    if reference is None:
        import cec_retained_ground_component as retained_ground
        reference=retained_ground.observe(board,request,
            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    if reference is not None:
        append([]);detail['retained_native_ground_reference_connection']=reference
        return
    # Conditional proposal only: staging all mandatory local returns may
    # connect this Source-named SMD boundary without additional copper.
    # The complete-selection observer below independently recompiles Source;
    # this shape test is deliberately NOT connection/return authority.
    if (request.get('kind')=='source_boundary' and net=='GND'
            and request.get('every_surviving_source_component_port_mandatory') is True
            and request.get('exact_additional_macro_component_source_ownership')
            and any(request.get(n,{}).get('pad_uuid') for n in ('a','b'))):
        detail['conditional_source_smd_ground_boundary_requires_staged_receiving']=True
        append([])
    small_ground=_typed_macro_ground_scope(request)
    if request['kind']=='ground_boundary':
        proof=request.get('retained_source_ground_fragment') or {}
        if (net!='GND' or not proof.get('actual_fixed_source_contacts_not_same_net_proximity')
                or not proof.get('whole_original_current_plane_and_saved_partition_receiving_required')):
            raise ValueError('typed_retained_ground_cut_boundary_required')
        # A conditional empty proposal may reuse mandatory local entries and
        # actual reference fill. It is NOT a connection witness: both trial
        # and saved receiving freshly rederive this exact Source cut and
        # require every named a/b contact on the same native fill island.
        detail['conditional_source_ground_cut_requires_staged_receiving']=True
        append([])
        # This is an existing small typed return branch, not the board's
        # aggregate Ground injection trunk. Keep its full class/source width;
        # the ORIGINAL current/plane/partition receivers remain mandatory.
        current=None
    elif small_ground is not None:
        # The exact Source compiler has positively owned this existing
        # bounded branch at a low-power terminal/barrel. Restoring it is
        # not a new aggregate Ground injection. Keep the original maximum
        # Source edge width plus the full class/factory floor below; never
        # substitute a guessed component load or narrow rated supply metal.
        current=None
        detail['source_owned_low_power_ground_component']=small_ground
    else:
        with force._thermal_hint(board_hint):
            current=cell._supply_current_widths(board,net)
    if typed_quiet and current is not None:
        raise ValueError('quiet_output_cannot_inherit_power_current_authority')
    expected=request.get('unchanged_full_rail_current_contract')
    if expected is not None and json.loads(json.dumps(current,allow_nan=False))!=json.loads(json.dumps(expected,allow_nan=False)):
        raise ValueError('complete_cell_source_current_contract_changed_or_unknown')
    width=max(request['width_nm'],full_net_width_nm,int(board.GetDesignSettings().m_TrackMinWidth),
        int(small_ground['source_full_class_width_nm'])if small_ground is not None
        else int(cell._netclass(board,net)['width']))
    face_widths=None
    if current is not None and source_requests is not None:
        import cec_source_face_widths as source_widths
        face_widths=source_widths.envelope(board,source_requests,net,current)
        # Keep THIS obligation's literal width on every proposed leg. Only
        # explained peer-face floors stop contaminating unrelated faces.
        width=max(request['width_nm'],int(board.GetDesignSettings().m_TrackMinWidth),
            int(cell._netclass(board,net)['width']))
    def layer_width(layer):
        if current is None:return width
        if layer not in current['required_by_layer_nm']:
            raise ValueError('complete_cell_current_layer_authority_missing')
        return max(width,current['required_by_layer_nm'][layer],
            face_widths[layer]if face_widths is not None else width)
    if typed_quiet and width!=request['width_nm']:
        raise ValueError('exact_quiet_Source_width_required')
    detail['unchanged_current_contract']=current
    retained=retained_local_supply_connection(board,request,
        timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    if retained is not None:
        append([]);detail['retained_native_local_supply_connection']=retained
        return
    retained=retained_native_boundary_connection(board,request,
        timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    if retained is not None:
        append([]);detail['retained_literal_native_boundary_connection']=retained
        return
    clearance=max(200000,int(cell._netclass(board,net)['clearance']))
    diverse=request['kind'] in ('source_boundary','ground_boundary','source_typed_incoming_quiet_output')
    def component_seed(endpoint):
        if not diverse or endpoint.get('native_uuids') or not endpoint.get('pad_uuid'):
            return endpoint
        # A literal compiler-owned pad is a real native component seed too.
        # Do not mistake its surface-only padstack for the access of an
        # existing barrel on the same connected copper. Pad identity, net,
        # material contact and connectivity are still checked independently;
        # no nearby same-net item or zone outline becomes an attachment point.
        if not any(force._uid(p)==endpoint['pad_uuid'] for fp in board.GetFootprints() for p in fp.Pads()):
            raise ValueError('literal_source_boundary_pad_identity_missing')
        return dict(endpoint,native_uuids=[endpoint['pad_uuid']])
    aa=ports.endpoints(board,net,component_seed(a),toward_nm=b['at_nm'],deadline=deadline,
        diverse_native_sites=diverse)
    bb=ports.endpoints(board,net,component_seed(b),toward_nm=a['at_nm'],deadline=deadline,
        diverse_native_sites=diverse)
    # Several mandatory branches at one narrow power input must not form a
    # branched thin escape star. A different contact on the SAME actual Source
    # pad can sometimes accept the full class width directly. Only native
    # pad/cap metal and unchanged whole-current authority can offer that port.
    body_ports=set();detail['source_current_pad_body_ports']=[]
    if current is not None and source_board is not None:
        import cec_source_current_pad_ports as body
        for endpoint,target,rows in ((a,b,aa),(b,a,bb)):
            uid=endpoint.get('pad_uuid')
            if uid not in shared_power_pad_uuids:continue
            pad=next((p for fp in board.GetFootprints() for p in fp.Pads() if force._uid(p)==uid),None)
            model=roles.footprint_contract(pad.GetParentFootprint()) if pad is not None else None
            if not model or model['pins'].get(pad.GetNumber())!='power_input':continue
            try:
                pad_faces=list(map(int,pad.GetLayerSet().CuStack()))
                if len(pad_faces)!=1:raise ValueError('source_body_actual_surface_required')
                proposed=body.sites(source_board,board,uid,board_hint=board_hint,width_nm=layer_width(pad_faces[0]),
                    toward_nm=target['at_nm'],deadline=deadline)
                for port in proposed:
                    if port not in rows:rows.append(port)
                    body_ports.add((uid,tuple(port['at_nm'])))
                detail['source_current_pad_body_ports'].append(dict(pad_uuid=uid,ports=proposed))
            except ValueError as exc:
                detail['source_current_pad_body_ports'].append(dict(pad_uuid=uid,refused=str(exc)))
    pairs=[(first,last) for first in aa for last in bb]
    pairs.sort(key=lambda q:math.dist(q[0]['at_nm'],q[1]['at_nm']))
    # Original obligation stays in the portfolio and in the source partition
    # receiver. A substitute is on precisely its connected retained copper.
    pairs=[(a,b),*[q for q in pairs if q!=(a,b)]]
    pairs=(ports.diverse_pairs(pairs,point=lambda p:p['at_nm'],layers=lambda p:p['layers'],
        limit=32,breadth=8) if diverse else pairs[:32])
    detail['native_component_ports']=[len(aa),len(bb)]
    detail['diverse_native_component_ports']=diverse
    joined=ports.plain_endpoint_turn_guard(board,net)
    emit=append
    detail['native_plain_endpoint_turn_refusals']=0
    detail['nonproductive_connection_walk_refusals']=0
    def complete_rejection(ops):
        # Search must see the SAME complete-proposal predicates as the
        # receiver-facing menu. Otherwise its first rejected join hides a
        # later legal path/seat. This callback is pure: exploratory trials
        # cannot emit choices or mutate the final-refusal counters.
        if typed_quiet and any(op[0] not in ('trk','via') or op[0]=='trk' and (
                int(op[3])!=request['width_nm'] or int(op[4])not in request['allowed_layers']) for op in ops):
            return 'typed_quiet_restriction'
        if 'source_required_surface_layer'in request:
            face=request['source_required_surface_layer']
            limit=local_supply_path_limit(request,math.dist(a['at_nm'],b['at_nm'])/1e6,
                layer_width(face)/1e6,clearance/1e6)
            if (any(op[0]!='trk'or int(op[4])!=face for op in ops)
                    or sum(math.dist(op[1],op[2])for op in ops)>limit*1e6):
                return 'source_required_surface_restriction'
        import cec_connection_walk as walk
        if not walk.productive(ops):
            return 'nonproductive_connection_walk_refusals'
        if not joined(ops):
            return 'native_plain_endpoint_turn_refusals'
        return None
    def accepts_complete(ops):return complete_rejection(ops) is None
    def append(ops):
        # Never trust a worker to honor its search callback. Retain this
        # independent final recheck, including for composed frontier paths.
        reason=complete_rejection(ops)
        if reason is not None:
            if reason in ('nonproductive_connection_walk_refusals','native_plain_endpoint_turn_refusals'):
                detail[reason]+=1
            return False
        emit(ops)
        return True
    # An existing plated contact exposes actual copper, not permission to
    # run a new signal across every plane it traverses. Keep the caller's
    # permitted routing faces plus the original literal common surface.
    # This does not expand a supply's independently rederived width authority.
    # A PTH's LayerSet legitimately names every *potential* copper layer,
    # including disabled ones. Only the actual native stack exposes copper;
    # otherwise a perfectly clear proposal on a nonexistent face repeatedly
    # loses the Source partition during independent native receiving.
    enabled_copper=set(map(int,board.GetEnabledLayers().CuStack()))
    surface_layers={int(pcbnew.F_Cu),*layers,*set(a['layers']).intersection(b['layers'])}&enabled_copper
    if typed_quiet:surface_layers &= set(request['allowed_layers'])
    foreign={};surface_offered=False
    # Reuse the ordinary supply producer's pad-local class-only escape.
    # The complete source current still applies to every leg; this is not
    # consumer allocation or a thin midspan route. The saved receiver must
    # independently rederive the exact typed terminals and full-width throat.
    detail['whole_current_surface_prefix_trials']=[]
    actual_pads={force._uid(p):p for fp in board.GetFootprints() for p in fp.Pads()}
    connected_address=None
    if source_board is not None and request.get('source_supply_pad_contact_lead_restoration') is not None:
        import cec_connected_address_supply_prefix as connected_prefix
        connected_address=connected_prefix.endpoint_context(source_board,board,request,
            board_hint=board_hint,timeout_s=min(9.1,max(.001,deadline-time.monotonic())))
        if connected_address is not None:
            # This is a freshly rederived connected Source address cut. Its
            # destination stays the exact original full-class native throat,
            # not a fictitious unwired address-to-power-pad shortcut.
            detail['source_connected_address_to_retained_throat']=connected_address
    def body_port(endpoint):return (endpoint.get('pad_uuid'),tuple(endpoint['at_nm'])) in body_ports
    def literal_pad_port(endpoint,original):
        # component_seed adds a native identity tag; that tag does not move
        # or retype the exact compiler-owned address endpoint.
        return (endpoint.get('pad_uuid')==original.get('pad_uuid')
            and endpoint.get('at_nm')==original.get('at_nm')
            and endpoint.get('layers')==original.get('layers'))
    def typed_supply_endpoints(first,last):
        endpoint_pads=[actual_pads.get(e.get('pad_uuid')) for e in (first,last)]
        if not any(p is not None for p in endpoint_pads):return None
        if any(p is None and not e.get('native_uuids') for p,e in zip(endpoint_pads,(first,last))):return None
        address=request.get('source_address_supply')
        import cec_full_current_supply_prefix as prefix
        def typed(p):
            if p is None:return True  # unchanged full-width native port
            if prefix.supply_terminal_role(p) is not None:return True
            model=roles.footprint_contract(p.GetParentFootprint())
            if (connected_address is not None and literal_pad_port(first,a)
                    and literal_pad_port(last,b) and endpoint_pads[1] is None
                    and endpoint_pads[0] is p and force._uid(p)==connected_address['pad_uuid']
                    and model and model['pins'].get(p.GetNumber())=='address'):
                return True
            return bool(address and literal_pad_port(first,a)
                and (literal_pad_port(last,b) or body_port(last))
                and last.get('pad_uuid')==b.get('pad_uuid') and force._uid(p)==a.get('pad_uuid')
                and address.get('exact_same_package_positive_power_input') is True
                and model and model['pins'].get(p.GetNumber())=='address'
                and endpoint_pads[1] is not None
                and force._uid(endpoint_pads[0].GetParentFootprint())==force._uid(endpoint_pads[1].GetParentFootprint())
                and model['pins'].get(endpoint_pads[1].GetNumber())=='power_input')
        # No class-only narrowing at a proved full-class body contact. The
        # other endpoint retains its existing bounded escape if Source-typed.
        return [None if body_port(e) else p for p,e in zip(endpoint_pads,(first,last))] \
            if all(typed(p) for p in endpoint_pads) else None
    def whole_current_escapes(first,last,face):
        endpoints=typed_supply_endpoints(first,last) if current is not None else None
        if endpoints is None:return (None,None)
        return cell._whole_current_endpoint_escapes(board,endpoints,net_code=code,layer=face,
            class_width_nm=layer_width(face),clearance_nm=clearance,current_widths=current)
    def whole_current_bridge_escapes(first,last):
        # A bridge's two physical pad faces need not be the same. Derive
        # each existing typed launch independently on its actual surface;
        # fixed/full-class native ports get no local-width allowance.
        # These are the SAME bounded, whole-current profiles as the surface
        # tier, not permission for a narrow middle or a smaller barrel web.
        endpoints=typed_supply_endpoints(first,last) if current is not None else None
        if endpoints is None:return (None,None)
        result=[]
        for endpoint,pad in zip((first,last),endpoints):
            if pad is None:
                result.append(None);continue
            faces=tuple(map(int,pad.GetLayerSet().CuStack()))
            if len(faces)!=1 or faces[0] not in endpoint['layers']:
                result.append(None);continue
            face=faces[0]
            result.append(cell._whole_current_endpoint_escapes(board,[pad,None],
                net_code=code,layer=face,class_width_nm=layer_width(face),
                clearance_nm=clearance,current_widths=current)[0])
        return tuple(result)
    if current is not None:
        for first,last in pairs:
            if time.monotonic()>=deadline:break
            endpoint_pads=typed_supply_endpoints(first,last)
            if endpoint_pads is None:continue
            address=request.get('source_address_supply')
            # The source compiler (and saved replay) owns this exact address
            # request. It cannot retype another control or measurement pin.
            common=sorted(set(first['layers'])&set(last['layers'])&surface_layers)
            direct=math.dist(a['at_nm'],b['at_nm'])/1e6
            for face in common:
                face_width=layer_width(face)
                limit=(local_supply_path_limit(request,direct,face_width/1e6,clearance/1e6)
                    if request['kind']=='local_supply' or address else min(32.,direct+8.))
                found=cell._canonical_whole_rail_surface(board,pcbnew.VECTOR2I(*first['at_nm']),
                    pcbnew.VECTOR2I(*last['at_nm']),[face],net_code=code,class_width_nm=face_width,
                    clearance_nm=clearance,current_widths=current,deadline_monotonic=deadline,
                    max_length_nm=limit*1e6,foreign_cache=foreign,endpoint_pads=endpoint_pads)
                detail['whole_current_surface_prefix_trials'].append(dict(found=bool(found),layer=face,
                    actual_source_current_unchanged=True,max_length_mm=limit,no_path_proof=False))
                if found:
                    legs,face,full_width=found
                    if append([('trk',tuple(s),tuple(t),int(w),face) for s,t,w in legs]):
                        surface_offered=True
    for first,last in pairs:
        if time.monotonic()>=deadline:break
        for layer in sorted(set(first['layers']) & set(last['layers']) & surface_layers):
            face_width=layer_width(layer)
            paths=list(fr._canonical_45_xy_paths(tuple(first['at_nm']),tuple(last['at_nm'])))
            ax,ay=first['at_nm'];bx,by=last['at_nm']
            for offset in (500000,1000000,2000000,3000000):
                for sign in (-1,1):
                    paths.extend([[(ax,ay),(ax+sign*offset,ay),(ax+sign*offset,by),(bx,by)],
                        [(ax,ay),(ax,ay+sign*offset),(bx,ay+sign*offset),(bx,by)]])
            for path in paths:
                if time.monotonic()>=deadline:break
                pts=[tuple(p) for p in path];pts=[p for i,p in enumerate(pts) if not i or p!=pts[i-1]]
                if len(pts)<2:continue
                if all(fr._edge_leg_clear(board,pcbnew.VECTOR2I(*s),pcbnew.VECTOR2I(*t),face_width/2+clearance)
                        and fr._tap_foreign_clear(board,pcbnew.VECTOR2I(*s),pcbnew.VECTOR2I(*t),
                            face_width,layer,clearance,{code},foreign_cache=foreign)
                        for s,t in zip(pts,pts[1:])):
                    length=sum(math.dist(s,t) for s,t in zip(pts,pts[1:]))/1e6
                    direct=math.dist(a['at_nm'],b['at_nm'])/1e6
                    if (request['kind']=='local_supply' and length>local_supply_path_limit(request,
                            direct,face_width/1e6,clearance/1e6)):continue
                    if append([('trk',s,t,face_width,layer) for s,t in zip(pts,pts[1:])]):
                        surface_offered=True
    if request['kind']=='local_supply':
        # Fixed rectangles can all miss a short legal throat between native
        # lands. Give the ACTUAL owner/cap terminals one bounded same-face
        # obstacle-aware proposal, with the unchanged full-current width and
        # local length limit. This tier cannot introduce a barrel, substitute
        # a distant same-net contact, or borrow a route on another layer.
        detail['local_supply_surface_trials']=[]
        search_pairs=pairs[:8]
        tasks=[(first,last,layer) for first,last in search_pairs
            for layer in sorted(set(first['layers']) & set(last['layers']) & surface_layers)]
        for index,(first,last,layer) in enumerate(tasks):
            now=time.monotonic()
            if now>=deadline:break
            face_width=layer_width(layer)
            direct=math.dist(a['at_nm'],b['at_nm'])/1e6
            limit=local_supply_path_limit(request,direct,face_width/1e6,clearance/1e6)
            trial={}
            start_escape,end_escape=whole_current_escapes(first,last,layer)
            legs=fr._guarded_profiled_lastmile_legs(board,pcbnew.VECTOR2I(*first['at_nm']),
                pcbnew.VECTOR2I(*last['at_nm']),face_width,layer,clearance,code,
                lambda s,t,h:fr._edge_leg_clear(board,s,t,h+clearance),
                foreign_cache=foreign,allow_maze=True,refine_maze=True,
                endpoint_detail_grid_mm=.2,compact_phase_jogs=True,
                start_escape=start_escape,end_escape=end_escape,
                path_validator=lambda legs,face=layer:accepts_complete(
                    [('trk',tuple(s),tuple(t),int(w),face)for s,t,w in legs]),
                deadline_monotonic=now+(deadline-now)/(len(tasks)-index),
                max_length_nm=limit*1e6,search_diagnostics=trial)
            length=sum(math.dist(tuple(s),tuple(t)) for s,t,w in legs)/1e6 if legs else None
            minimum=max(int(board.GetDesignSettings().m_TrackMinWidth),
                current['required_by_layer_nm'][layer]) if current else face_width
            accepted=bool(legs and length<=limit and all(minimum<=int(w)<=face_width for s,t,w in legs)
                and tuple(legs[0][0])==tuple(first['at_nm'])
                and tuple(legs[-1][1])==tuple(last['at_nm'])
                and all(tuple(first[1])==tuple(last[0]) for first,last in zip(legs,legs[1:])))
            detail['local_supply_surface_trials'].append(dict(layer=layer,width_nm=face_width,
                a_nm=first['at_nm'],b_nm=last['at_nm'],
                max_length_mm=limit,length_mm=length,found=accepted,diagnostics=trial,
                no_path_proof=False))
            if accepted:append([('trk',tuple(s),tuple(t),int(w),layer) for s,t,w in legs])
        return
    if ((request.get('source_ordinary_join_scope') is not None
            or request.get('source_ordinary_boundary_scope') is not None) and time.monotonic()<deadline):
        # Local surface/remote-via halos are not a whole-board path proof.
        # Reserve a finite slice for the actual native endpoint graph before
        # the old portfolios can spend the entire obligation lease. This is
        # only separately Source-qualified ordinary joins/cut restoration; no power,
        # Ground, measurement or pair role borrows this scope.
        import cec_macro_ordinary_join_obligations as ordinary_joins
        import cec_connection_walk as walk
        now=time.monotonic();native_deadline=now+(deadline-now)*.45
        proposal=ordinary_joins.native_choices(board,request,pairs,
            route_layers=layers,width_for_layer=layer_width,clearance_nm=clearance,
            foreign_cache=foreign,deadline=native_deadline,
            accept=accepts_complete)
        detail['source_ordinary_native_envelope_search']={k:v for k,v in proposal.items()if k!='choices'}
        for ops in proposal['choices']:
            if append(ops):surface_offered=True
    if request['kind'] in ('source_boundary','ground_boundary','source_typed_incoming_quiet_output') and (not surface_offered or len(pairs)>1):
        import cec_route_quality as quality
        # A scalar/fixed-port or typed low-power Ground-cut connection
        # deserves the same native surface
        # search as a bypass before we demand new holes on all six faces.
        # The ORIGINAL obligation, full current width and every native guard
        # still own it. A real connected contact needs a detailed surface
        # search too: fixed rectangles alone are not an exhaustive detour
        # attempt. Keep the later complete bridge portfolio and all original
        # native partition obligations; this is not routing admission.
        detail['source_boundary_surface_trials']=[]
        surface_deadline=min(deadline,time.monotonic()+max(0.,deadline-time.monotonic())*.3, time.monotonic()+2.)
        searched=ports.surface_maze_pairs(board,pairs,route_layers=sorted(surface_layers))
        detail['source_boundary_surface_portfolio_size']=len(searched)
        detail['original_component_and_bridge_pairs_retained']=True
        for pair_index,(first,last) in enumerate(searched):
            now=time.monotonic()
            if now>=surface_deadline:break
            # Preserve a useful original-pair lease; share the remaining
            # bounded work fairly across actual alternative contacts.
            fraction=.5 if pair_index==0 and len(searched)>1 else 1/(len(searched)-pair_index)
            pair_deadline=now+(surface_deadline-now)*fraction
            common=sorted(set(first['layers'])&set(last['layers'])&surface_layers)
            for index,layer in enumerate(common):
                now=time.monotonic()
                if now>=pair_deadline:break
                face_width=layer_width(layer);direct=math.dist(first['at_nm'],last['at_nm'])/1e6
                limit=min(32.,direct+8.);trial={}
                start_escape,end_escape=whole_current_escapes(first,last,layer)
                legs=fr._guarded_profiled_lastmile_legs(board,pcbnew.VECTOR2I(*first['at_nm']),
                    pcbnew.VECTOR2I(*last['at_nm']),face_width,layer,clearance,code,
                    lambda s,t,h:fr._edge_leg_clear(board,s,t,h+clearance),foreign_cache=foreign,
                    allow_maze=True,refine_maze=True,endpoint_detail_grid_mm=.1,compact_phase_jogs=True,
                    start_escape=start_escape,end_escape=end_escape,
                    path_validator=lambda legs,face=layer:accepts_complete(
                        [('trk',tuple(s),tuple(t),int(w),face)for s,t,w in legs]),
                    deadline_monotonic=now+(pair_deadline-now)/(len(common)-index),
                    max_length_nm=limit*1e6,search_diagnostics=trial)
                length=sum(math.dist(tuple(s),tuple(t)) for s,t,w in legs)/1e6 if legs else None
                minimum=max(int(board.GetDesignSettings().m_TrackMinWidth),
                    current['required_by_layer_nm'][layer]) if current else face_width
                accepted=bool(legs and length<=limit and all(minimum<=int(w)<=face_width and
                    quality.is_canonical_stroke(tuple(s),tuple(t),tolerance_nm=0) for s,t,w in legs)
                    and tuple(legs[0][0])==tuple(first['at_nm']) and tuple(legs[-1][1])==tuple(last['at_nm'])
                    and all(tuple(x[1])==tuple(y[0]) for x,y in zip(legs,legs[1:])))
                detail['source_boundary_surface_trials'].append(dict(layer=layer,width_nm=face_width,
                    a_nm=first['at_nm'],b_nm=last['at_nm'],original_named_pair=pair_index==0,
                    max_length_mm=limit,length_mm=length,found=accepted,diagnostics=trial,no_path_proof=False))
                if accepted:append([('trk',tuple(s),tuple(t),int(w),layer) for s,t,w in legs])
    current_via={}
    if current is not None:
        possible_faces=set(map(int,layers))|set(map(int,a['layers']))|set(map(int,b['layers']))
        try:
            web_width=max(width,*(layer_width(face)for face in possible_faces
                if face in set(map(int,board.GetEnabledLayers().CuStack()))))
            current_via=_source_current_via_geometry(board,current,possible_faces,minimum_width_nm=web_width)
            if current_via['minimum_local_via_web_nm']>2000000:
                raise ValueError('source_current_web_exceeds_bounded_bridge_geometry')
            detail['source_current_barrel_geometry']=dict(current_via,
                possible_contact_layers=sorted(possible_faces),barrel_ampacity_qualified=False)
        except ValueError as exc:
            # A refusal of new barrels cannot erase an already valid full-
            # width surface offer. It cannot fund a smaller barrel either.
            detail['source_current_barrel_refusal']=str(exc)
            return
    # A moved scalar terminal can be shadowed by copper on the other five
    # layers. A short radial ladder then has no legal barrel even when a
    # native free pocket exists just beyond that shadow. Derive the seats
    # from all saved layers, prove BOTH surface departures, and explicitly
    # include each new barrel in the complete proposal. No ghost portals.
    if request['kind'] in ('source_boundary','source_typed_incoming_quiet_output') and time.monotonic()<deadline:
        import cec_native_via_frontier as frontier
        import cec_kelvin_copper_cut as cut
        port_deadline=time.monotonic()+max(0,deadline-time.monotonic())*.55
        portal_sets=[];detail['native_surface_portfolio']=[]
        endpoint_escapes=whole_current_bridge_escapes(a,b)
        for endpoint_index,end in enumerate((a,b)):
            now=time.monotonic();lease=now+max(0,port_deadline-now)*.3
            reachable=[]
            try:
                found=frontier.sites(board,code,tuple(end['at_nm']),clearance_nm=clearance,
                    radius_mm=8.,max_sites=12,deadline=lease,diverse=True,
                    **(dict(diameter_mm=current_via['dia'],drill_mm=current_via['drill'])
                        if current_via else {}))
                for at in found['sites_nm']:
                    if time.monotonic()>=lease:break
                    for face in end['layers']:
                        face_width=layer_width(face)
                        stub=fr._guarded_profiled_lastmile_legs(board,pcbnew.VECTOR2I(*end['at_nm']),
                            pcbnew.VECTOR2I(*at),face_width,face,clearance,code,
                            lambda s,t,h:fr._edge_leg_clear(board,s,t,h+clearance),
                            foreign_cache=foreign,deadline_monotonic=lease,allow_maze=True,
                            refine_maze=True,endpoint_detail_grid_mm=.2,max_length_nm=10000000,
                            start_escape=endpoint_escapes[endpoint_index],end_escape=None)
                        if stub:
                            reachable.append((at,[('trk',tuple(s),tuple(t),int(w),int(face))
                                for s,t,w in stub]+[('via',tuple(at),found['drill_mm'],found['diameter_mm'])]))
                            break
                    if len(reachable)>=4:break
                detail['native_surface_portfolio'].append(dict(native_sites=len(found['sites_nm']),
                    reached_surface_sites=len(reachable),no_path_proof=False))
            except (ValueError,cut.Unknown) as exc:
                detail['native_surface_portfolio'].append(dict(error=str(exc),no_path_proof=False))
            portal_sets.append(reachable)
        trials=sorted(((first,last) for first in portal_sets[0] for last in portal_sets[1]),
            key=lambda q:math.dist(q[0][0],q[1][0]))[:8]
        for index,(first,last) in enumerate(trials):
            now=time.monotonic()
            if now>=port_deadline:break
            middle=fr._lastmile_bridge(board,tuple(first[0]),layers,tuple(last[0]),layers,
                width,code,layers,clearance,seat_limit=2,seat_pair_first=True,
                allow_maze=True,foreign_cache=foreign,
                deadline_monotonic=now+(port_deadline-now)/(len(trials)-index),
                refine_stubs=True,width_for_layer=layer_width,
                # Both endpoint departures belong to the candidate. The
                # middle alone cannot reveal a backward retained join.
                ops_ok=lambda middle,first=first,last=last:accepts_complete(
                    [*first[1],*middle,*last[1]]),
                **current_via,
                multilayer_lays=layers,early_multilayer_pairs=2,
                leg_ok=lambda s,t,h:fr._edge_leg_clear(board,s,t,h+clearance))
            if middle:
                # The target departure was enumerated outward from its real
                # endpoint. Native segments are bidirectional, not implied
                # endpoint layers masquerading as retained copper.
                append([*first[1],*middle,*last[1]])
    detail['bridge_port_trials']=[]
    for index,(first,last) in enumerate(pairs):
        now=time.monotonic()
        if now>=deadline:break
        trial={}
        start_escape,end_escape=whole_current_bridge_escapes(first,last)
        ops=fr._lastmile_bridge(board,tuple(first['at_nm']),tuple(first['layers']),
            tuple(last['at_nm']),tuple(last['layers']),width,code,layers,clearance,
            # A short obligation lease must try a complete guarded pair
            # before collecting every speculative seat. The existing
            # full-domain fallback, guards and parent deadline remain.
            seat_limit=4,seat_pair_first=True,allow_maze=True,foreign_cache=foreign,
            deadline_monotonic=min(deadline,now+max(.03,(deadline-now)/(min(8,len(pairs)-index)))),
            refine_stubs=True,width_for_layer=layer_width,diagnostics=trial,
            start_escape=start_escape,end_escape=end_escape,
            ops_ok=accepts_complete,
            **current_via,
            multilayer_lays=[int(request['a']['layers'][0]),*layers],early_multilayer_pairs=2,
            leg_ok=lambda s,t,h:fr._edge_leg_clear(board,s,t,h+clearance))
        detail['bridge_port_trials'].append(dict(a_nm=first['at_nm'],b_nm=last['at_nm'],
            found=bool(ops),diagnostics=trial,
            actual_whole_current_start_escape=start_escape,actual_whole_current_end_escape=end_escape))
        if ops:append(ops)


def menus(board, requests, *, board_path, board_hint, timeout_s=10., max_choices=48,
          measurement_bridges=False, include_power_layer=False, per_obligation_leases=False,
          source_board=None, whole_requests=None):
    """Derive native-guarded alternative paths without leaving any copper."""
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10 or type(max_choices) is not int or not 1 <= max_choices <= 48
            or type(measurement_bridges) is not bool or type(include_power_layer) is not bool
            or type(per_obligation_leases) is not bool
            or type(requests) is not dict or not 1<=len(requests)<=64):
        raise ValueError('bounded_cell_menu_budget_required')
    binding = row._source_binding(board); started = time.monotonic()
    whole_deadline=started+timeout_s*(len(requests) if per_obligation_leases else 1)
    domains = {}; diagnostics = {}
    import cec_source_current_pad_ports as body_ports
    whole_requests=requests if whole_requests is None else whole_requests
    if (type(whole_requests)is not dict or not 1<=len(whole_requests)<=64
            or any(key not in whole_requests or whole_requests[key]!=request for key,request in requests.items())):
        raise ValueError('exact_complete_source_request_context_required')
    shared_power_pad_uuids=body_ports.shared_terminals(whole_requests)
    # Reuse the already-bound native Source owner. Loading a second project
    # merely to enumerate contacts can change ambient native class objects.
    # Standalone callers without Source context retain the old portfolios.
    if source_board is not None and not isinstance(source_board,pcbnew.BOARD):
        raise ValueError('actual_native_source_board_context_required')
    full_net_widths={}
    for request in whole_requests.values():
        net=request['net'];full_net_widths[net]=max(full_net_widths.get(net,0),request.get('width_nm',0))
    layers = list(fr._lastmile_route_layers(board, exclude_front=True))
    if include_power_layer:
        # Explicit caller policy, never an automatic plane or coupled-pair
        # exception. Native reservations and unchanged current widths still
        # apply to every candidate; saved-board receiving is still required.
        planes = {board.GetLayerID(name) for name in fr.plane_layers(board)}
        layers = [board.GetLayerID(name) for name in fab.routing_layers(board, include_power=True)
            if board.GetLayerID(name) not in planes and board.GetLayerID(name) != pcbnew.F_Cu]
    # Source-role dependency order, not random UUID order: immediate cap
    # root, actual owner GND, then its reference/address inputs. Menus stay
    # separate and jointly mandatory; this does not inject fictitious vias.
    def order(pair):
        key,request=pair
        if request['kind']!='ground':return (1 if request['kind'] in ('measurement','isolated_measurement') else 2,0,key)
        entry=request.get('selected_bypass_entry')
        depth=0 if not entry else (2 if entry.get('typed_reference_or_address_to_package_ground') else 1)
        return (0,depth,key)
    ordered_requests = sorted(requests.items(), key=order)
    root_blocking = None; deferred = []
    for index, (key, request) in enumerate(ordered_requests):
        slot_started = time.monotonic()
        # Reserve a fair portion of the remaining lease for every obligation.
        # A difficult first measurement may not starve power/ground menus.
        deadline = (min(whole_deadline,slot_started+timeout_s) if per_obligation_leases else
            slot_started + max(0., whole_deadline-slot_started)/(len(ordered_requests)-index))
        if slot_started >= whole_deadline:
            diagnostics[key] = dict(error='whole_menu_lease_exhausted'); domains[key] = []; continue
        choices = []; detail = {}; net = request['net']; code = board.GetNetcodeFromNetname(net)
        required_ground=request.get('required_projected_ground_entry')
        required_new_ground=request.get('required_new_ground_dogbone')
        required_supply=request.get('required_supply_departure')
        required_corridor=request.get('required_measurement_corridor')
        if required_corridor is not None:
            import cec_macro_measurement_corridor as corridor
            if (request['kind']!='isolated_measurement'
                    or request['a'].get('pad_uuid')!=required_corridor['pad_uuid']
                    or request['b'].get('pad_uuid')!=required_corridor['target_pad_uuid']
                    or request['net']!=required_corridor['net'] or request['width_nm']!=required_corridor['width_nm']
                    or any(value is not None for value in (required_supply,required_ground,required_new_ground))):
                raise ValueError('required_measurement_corridor_request_identity_mismatch')
        if required_new_ground is not None:
            import cec_macro_new_ground_dogbone as dogbone
            if (required_ground is not None or request['kind']!='ground'
                    or request['a']['pad_uuid']!=required_new_ground['pad_uuid']):
                raise ValueError('required_new_ground_dogbone_request_identity_mismatch')
            dogbone.rederive(board,required_new_ground,timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        if required_supply is not None:
            import cec_macro_supply_departure as departure
            if (request['kind']!='supply_departure' or request['a']['pad_uuid']!=required_supply['pad_uuid']
                    or request['net']!=required_supply['net']):
                raise ValueError('required_supply_departure_request_identity_mismatch')
        if required_ground is not None:
            import cec_macro_ground_ingress as ingress
            if request['kind']!='ground' or request['a']['pad_uuid']!=required_ground['pad_uuid']:
                raise ValueError('required_ground_entry_request_identity_mismatch')
            ingress.rederive(board,required_ground,timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        def append(ops, dependency=None):
            if required_ground is not None and not ingress.required_ops(required_ground,ops):return
            if required_new_ground is not None and not dogbone.required_ops(required_new_ground,ops):return
            if required_supply is not None and not departure.required_ops(required_supply,ops):return
            if required_corridor is None and request['kind'] in ('measurement','isolated_measurement'):
                import cec_measurement_launch_pruning as launch_pruning
                old_count=len(ops)
                ops=launch_pruning.prune(board,request.get('a',{}).get('pad_uuid'),ops,
                    timeout_s=min(1.,max(.001,deadline-time.monotonic())))
                if len(ops)<old_count:
                    detail['generated_land_internal_prefix_tracks_pruned']=detail.get(
                        'generated_land_internal_prefix_tracks_pruned',0)+old_count-len(ops)
            clean = [[op[0], list(op[1]), *([list(op[2]), int(op[3]), int(op[4])]
                if op[0] == 'trk' else [float(op[2]), float(op[3])])] for op in ops]
            if any(q['ops'] == clean and q.get('requires_ground_entry') == dependency for q in choices):
                return
            length = sum(math.dist(op[1], op[2])/1e6 for op in clean if op[0] == 'trk')
            candidate=dict(id=str(len(choices)), cost=length+sum(2 for op in clean if op[0] == 'via'),
                net=net, ops=clean, clearance_nm=max(200000, int(cell._netclass(board, net)['clearance'])))
            if not clean and detail.get('conditional_source_smd_ground_boundary_requires_staged_receiving'):
                candidate['requires_source_smd_ground_boundary_observation']=True
            if dependency is not None:
                candidate['requires_ground_entry'] = dependency
            import cec_route_choice_portfolio as portfolio
            retained=portfolio.retain(choices,candidate,capacity=max_choices)
            counters=detail.setdefault('bounded_topology_retention',dict(guarded_candidates=0,
                retained_arrivals=0,evictions=0,capacity=max_choices,no_geometry_authority=True))
            counters['guarded_candidates']+=1
            counters['retained_arrivals']+=int(retained['retained'])
            counters['evictions']+=int(retained['evicted'])
        def finish_domain():
            # Late alternative retention may replace early entries. References
            # to this domain are created only AFTER its final IDs are assigned.
            for choice_id,choice in enumerate(choices):choice['id']=str(choice_id)
            detail.update(menu_elapsed_s=time.monotonic()-slot_started,
                per_obligation_lease_exhausted=time.monotonic() >= deadline,
                generated_choices=len(choices), no_path_proof=False)
            domains[key]=choices;diagnostics[key]=detail
        if required_corridor is not None:
            ops,evidence=corridor.entry_ops(board,required_corridor,
                timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            detail['required_measurement_corridor_offer']=evidence
            if ops:append(ops)
        elif required_supply is not None:
            ops,evidence=departure.entry_ops(board,required_supply,
                timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            detail['required_supply_departure_offer']=evidence
            if ops:append(ops)
        elif required_new_ground is not None:
            ops,evidence=dogbone.entry_ops(board,required_new_ground,
                timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            detail['required_new_ground_dogbone_offer']=evidence
            if ops:append(ops)
        elif required_ground is not None:
            ops,evidence=ingress.entry_ops(board,required_ground,
                timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            detail['required_ground_entry_offer']=evidence
            if ops:append(ops)
        elif request['kind'] == 'measurement':
            q = request['source_leaf']
            import cec_measurement_route_policy as measurement_policy
            import cec_macro_rc_input_prefix as rc_prefix
            is_fixed_rc_prefix=q.get('scope')==rc_prefix.SCOPE
            layer_policy=measurement_policy.input_contract(board,q['pad_uuid'])
            bridge_allowed=measurement_bridges and layer_policy['allow_layer_bridge'] and not is_fixed_rc_prefix
            for points in leaf.menus(q, max_paths=96, offset_mm=6):
                if time.monotonic() >= deadline or len(choices) >= max_choices:
                    break
                try:
                    if (leaf.path_clear(board, q, points, timeout_s=min(2., max(.001, deadline-time.monotonic())))
                            and (not is_fixed_rc_prefix or rc_prefix.path_clear(board,q,points,
                                timeout_s=min(2.,max(.001,deadline-time.monotonic()))))):
                        append([('trk', a, b, q['width_nm'], q['layer']) for a, b in zip(points, points[1:])])
                except ValueError as exc:
                    detail = dict(error=str(exc)); break
            if not choices and time.monotonic() < deadline:
                try:
                    remaining=max(.001,deadline-time.monotonic())
                    detail = leaf.search(board, q, timeout_s=min(10.,remaining*.45) if
                        per_obligation_leases and bridge_allowed else min(10.,remaining))
                    if detail['points_nm'] and (not is_fixed_rc_prefix or rc_prefix.path_clear(board,q,
                            detail['points_nm'],timeout_s=min(2.,max(.001,deadline-time.monotonic())))):
                        pts = detail['points_nm']
                        append([('trk', a, b, q['width_nm'], q['layer']) for a, b in zip(pts, pts[1:])])
                except ValueError as exc:
                    detail = dict(error=str(exc))
            bridge_deadline=deadline if per_obligation_leases else whole_deadline
            detail['measurement_layer_policy']=layer_policy
            if bridge_allowed and not choices and time.monotonic()<bridge_deadline:
                import cec_measurement_leaf_bridge as bridge
                try:
                    detail['multilayer_measurement']=bridge.search(board,q,
                        timeout_s=min(10. if per_obligation_leases else 2.,
                            max(.001,bridge_deadline-time.monotonic())),
                        include_power_layer=include_power_layer)
                    if detail['multilayer_measurement']['ops']:
                        append(detail['multilayer_measurement']['ops'])
                except ValueError as exc:
                    detail['multilayer_error']=str(exc)
        elif request['kind']=='isolated_measurement':
            import cec_measurement_terminal_route as terminal_route
            import cec_measurement_route_policy as measurement_policy
            layer_policy=measurement_policy.input_contract(board,
                request['source_measurement_demand']['pad_uuid'])
            bridge_allowed=measurement_bridges and layer_policy['allow_layer_bridge']
            try:
                remaining=max(.001,deadline-time.monotonic())
                detail=terminal_route.menus(board,request['source_measurement_demand'],
                    width_nm=request['width_nm'],timeout_s=min(1.,remaining*.45) if
                        bridge_allowed else min(10.,remaining),
                    max_choices=max_choices)
                for ops in detail['ops']:append(ops)
            except ValueError as exc:detail=dict(error=str(exc))
            bridge_deadline=deadline if per_obligation_leases else whole_deadline
            detail['measurement_layer_policy']=layer_policy
            if bridge_allowed and not choices and time.monotonic()<bridge_deadline:
                import cec_measurement_leaf_bridge as bridge
                try:
                    detail['multilayer_measurement']=bridge.search_isolated(board,
                        request['source_measurement_demand'],width_nm=request['width_nm'],
                        timeout_s=min(10. if per_obligation_leases else 2.,
                            max(.001,bridge_deadline-time.monotonic())),
                        include_power_layer=include_power_layer)
                    if detail['multilayer_measurement']['ops']:
                        append(detail['multilayer_measurement']['ops'])
                except ValueError as exc:detail['multilayer_error']=str(exc)
        elif request['kind'] == 'source_retained_address_ground_connection':
            import cec_retained_address_ground as address_ground
            detail['retained_logical_address_connection']=address_ground.observe(board,request,requests,
                timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            append([])
        elif request['kind'] == 'ground':
            p = next(p for fp in board.GetFootprints() for p in fp.Pads()
                if force._uid(p) == request['a']['pad_uuid'])
            fixed=request.get('retained_stationary_source_return')
            if fixed is not None:
                import cec_native_placement_context as native
                actual=native._native_stationary_land(p,deadline)
                model=roles.footprint_contract(p.GetParentFootprint())
                if (actual is None or not model or fixed['pad_uuid']!=force._uid(p)
                        or model['pins'].get(p.GetNumber())!=fixed['manufacturer_role']
                        or fixed['manufacturer_role'] not in ('ground','reference','power_return')
                        or hashlib.sha256(repr(actual).encode()).hexdigest()!=fixed['source_land_sha256']):
                    raise ValueError('exact_stationary_source_ground_land_required')
                witness=cell._existing_return(board,p,16.,allow_native_track_body=True)
                graph=fr._read_only_route_connectivity(board)
                reached={force._uid(item) for item in graph.GetConnectedItems(p)}
                planes={force._uid(z) for z in board.Zones()
                    if not z.GetIsRuleArea() and z.GetNetname()=='GND' and z.IsFilled()}
                if (witness is not None and witness[0]<=fixed['source_return_mm']+.000001
                        and fixed['source_reference_via_uuid'] in reached and reached & planes):
                    append([])
                    detail['inherited_exact_stationary_source_return_preserved']=fixed
                    detail['new_immediate_return_or_process_qualified']=False
                    finish_domain();continue
            projected=request.get('retained_projected_source_return')
            if projected is not None and time.monotonic()<deadline:
                try:
                    observed=projected_ground.observe(board,p,projected,
                        timeout_s=min(10.,max(.001,deadline-time.monotonic())))
                except ValueError as exc:
                    observed=None;detail['projected_source_return_refused']=str(exc)
                # Retention is not an immediate-return waiver. A long old
                # path remains copper, but this moving cell must still find
                # a process-qualified entry within its normal design bound.
                if (observed is not None and observed['full_class_direct_reference_reach_proved']
                        and observed['saved_return_mm']<=request['reach_mm']):
                    append([]);detail['inherited_projected_source_return']=observed
                    finish_domain();continue
            for ops in retained_ground_barrel_ops(board,p,deadline=deadline,reach_mm=request['reach_mm'],
                    owner_return_entry=request.get('selected_bypass_entry')):
                append(ops)
            # Existing native return producer already checks actual copper,
            # immediate distance and the declared filled/capped-via process.
            result, error = cell._add_ground_return(board, p, board_path=board_path,
                reach_mm=request['reach_mm'], lock=True, diagnostics=detail)
            if result is not None:
                added = result['items']; ops = []
                for item in added:
                    if item.GetClass() == 'PCB_TRACK':
                        ops.append(('trk', tuple(item.GetStart()), tuple(item.GetEnd()),
                            item.GetWidth(), item.GetLayer()))
                    else:
                        ops.append(('via', tuple(item.GetPosition()), item.GetDrillValue()/1e6,
                            item.GetWidth(item.TopLayer())/1e6))
                append(ops); discard_items(board, added)
            else:
                detail['error'] = error
                profile_name = fab.active_profile_name(board,hint=board_path)
                profile = fab.get_profile(profile_name) if profile_name else None
                pofv = fab.preferred_pofv_geometry(profile) if profile else None
                if pofv:
                    detail['native_pad_center_barrel_blockers'] = native_barrel_blockers(
                        board,tuple(p.GetPosition()),net,diameter_mm=pofv[0])
                    detail['diagnostic_diameter_mm'] = pofv[0]
            if request.get('same_package_ground_link_proposal_allowed'):
                # Use the SAME guarded endpoint-profiled producer as the
                # positive Ground preflight. A bare full-width segment at a
                # fine-pitch grounded address input can be impossible even
                # when its legitimate short pad-local escape is clear.
                for peer,ops in typed_non_return_package_ground_links(board,p,deadline=deadline):
                    append(ops)
                # The manufacturer's ground/reference lands may share a
                # local entry. This is a bounded routing proposal, not an
                # immediate-return qualification or a cap-return exception.
                # Complete native receiving must prove the peer actually
                # reaches the original retained ground network, preventing
                # an isolated cycle of mutually "grounded" pads.
                width = max(200000, int(cell._netclass(board, net)['width']))
                gap = max(200000, int(cell._netclass(board, net)['clearance']))
                for peer in p.GetParentFootprint().Pads():
                    if force._uid(peer) == force._uid(p) or peer.GetNetname() != 'GND':
                        continue
                    for path in fr._canonical_45_xy_paths(tuple(p.GetPosition()), tuple(peer.GetPosition())):
                        length = sum(math.dist(s, t) for s, t in zip(path, path[1:]))/1e6
                        if length > 4 or time.monotonic() >= deadline:
                            continue
                        layer = int(p.GetLayerSet().CuStack()[0])
                        if all(fr._edge_leg_clear(board, pcbnew.VECTOR2I(*s), pcbnew.VECTOR2I(*t), width/2+gap)
                            and fr._tap_foreign_clear(board, pcbnew.VECTOR2I(*s), pcbnew.VECTOR2I(*t),
                                width, layer, gap, {code}, foreign_cache={}) for s, t in zip(path, path[1:])):
                            append([('trk', s, t, width, layer) for s, t in zip(path, path[1:])])
            entry = request.get('selected_bypass_entry')
            if entry:
                # Keep cap return and IC link as separate, jointly mandatory
                # domains. Do not inject a temporary via and then mistake it
                # for retained source copper in the next obligation's menu.
                cap_key = entry['portal_obligation']
                cap_request = requests.get(cap_key)
                if (not cap_request or cap_request['kind'] != 'ground'
                        or cap_request['a']['pad_uuid'] != entry['portal_pad_uuid']
                        or (cap_request.get('selected_bypass_entry')
                            and not entry.get('typed_reference_or_address_to_package_ground'))):
                    raise ValueError('mandatory_immediate_cap_entry_obligation_missing')
                portal = next(pad for fp in board.GetFootprints() for pad in fp.Pads()
                    if force._uid(pad) == entry['portal_pad_uuid'])
                for ops in ground_link_ops(board, p, portal, deadline=deadline,
                        max_link_mm=entry['max_link_mm']):
                    append(ops, dependency=entry)
                detail['selected_bypass_entry'] = entry
        else:
            try:
                if net in fr.coupled_pair_nets(board):
                    raise ValueError('complete_cell_coupled_route_authority_missing')
                _connection_menu(board,request,board_hint=board_hint,deadline=deadline,
                    layers=layers,append=append,detail=detail,source_board=source_board,
                    shared_power_pad_uuids=shared_power_pad_uuids,
                    full_net_width_nm=full_net_widths[net],source_requests=whole_requests)
            except ValueError as exc:
                detail['error']=str(exc)
        finish_domain()
        if request['kind'] == 'ground' and not choices:
            # Source-derived local-access failure belongs upstream of route
            # search. Do not spend the rest of a wave rerouting unrelated
            # leaves for a pose that cannot complete its mandatory return.
            # This finite return menu is NOT physical impossibility proof.
            root_blocking = key
            for other_key,_ in ordered_requests[index+1:]:
                domains[other_key] = []
                diagnostics[other_key] = dict(deferred_not_attempted=True,
                    reason='upstream_local_ground_access_refused',root_obligation=key,
                    no_path_proof=False)
                deferred.append(other_key)
            break
    if row._source_binding(board) != binding:
        raise ValueError('cell_menu_producer_changed_native_material')
    return dict(domains=domains, diagnostics=diagnostics, source_native_binding=binding,
        ground_dependency_board_hint=board_hint,
        nonload_branch_source_path=str(Path(board_path).resolve()),
        elapsed_s=time.monotonic()-started, source_unchanged=True,
        explicit_nonplane_power_role_policy=include_power_layer,
        per_obligation_leases=per_obligation_leases,independent_stage_max_seconds=timeout_s,
        total_menu_work_bound_seconds=timeout_s*(len(requests) if per_obligation_leases else 1),
        upstream_access_refused=root_blocking is not None,
        root_blocking_obligation=root_blocking, deferred_not_attempted=deferred,
        obligation_count=len(requests), all_obligations_present=set(domains) == set(requests),
        empty_obligations=[k for k, values in domains.items() if not values])


def _clean_source_craft_rejection(source_quality,quality,selected,constructed_by,*,domain_binding):
    """Reject a proved bad same-net context, not unrelated Ground variants.

    Native craft is not generally monotone: another same-net branch can
    change a junction's degree or cover a stroke. Therefore retain EVERY
    selected choice on the offending net in this run-local clause, not only
    the two named segments. Only an actually clean Source craft inventory
    funds this optimization, so improvement on another net cannot pay for
    the persistent issue. Unknown provenance falls back to ordinary False.
    This is rejecting-only search feedback; all whole-selection and saved
    native receivers still run for a different, potentially valid context.
    """
    if (source_quality.get('issue_count')!=0 or source_quality.get('non_octilinear_count')!=0
            or type(quality.get('issues'))is not list):return False
    import cec_joint_connection_search as joint
    for issue in quality['issues']:
        net=issue.get('net');ids=issue.get('track_uuids')
        if (type(net)is not str or not net or type(ids)is not list or not ids
                or any(type(uid)is not str or not uid for uid in ids)):continue
        owners=[constructed_by[uid] for uid in ids if uid in constructed_by]
        if not owners:continue
        if any(type(owner)is not dict or owner.get('obligation')not in selected
                or owner.get('choice_id')!=selected[owner['obligation']].get('id')
                or selected[owner['obligation']].get('net')!=net for owner in owners):continue
        context=tuple(sorted((key,choice['id'])for key,choice in selected.items()
            if choice.get('net')==net))
        if not context:continue
        return joint.RejectedSelection(domain_binding,context,
            'native_clean_Source_craft_same_net_context')
    return False


def conflict_oracle(board):
    """Future-path conflict map over real layers, widths and drill spacing."""
    shapes = {}; layers = tuple(map(int, board.GetEnabledLayers().CuStack()))
    def geometry(choice):
        key = repr(choice)
        if key not in shapes:
            copper = []; holes = []
            for op in choice['ops']:
                if op[0] == 'trk':
                    copper.append((op[4], pcbnew.SHAPE_SEGMENT(
                        pcbnew.VECTOR2I(*op[1]),pcbnew.VECTOR2I(*op[2]),op[3])))
                else:
                    via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I(*op[1]))
                    via.SetWidth(round(op[3]*1e6));via.SetDrill(round(op[2]*1e6))
                    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
                    shape=via.GetEffectiveShape(pcbnew.F_Cu)
                    copper.extend((layer, shape) for layer in layers)
                    holes.append((op[1],round(op[2]*1e6)))
            shapes[key] = copper, holes
        return shapes[key]
    def conflicts(a, b):
        first, left_holes = geometry(a); last, right_holes = geometry(b)
        hole_min = int(board.GetDesignSettings().m_HoleToHoleMin)
        if any(math.dist(p, q) < (d+e)/2+hole_min for p, d in left_holes for q, e in right_holes):
            return True
        if a['net'] == b['net']:
            return False
        gap = max(a['clearance_nm'], b['clearance_nm'])
        # The producer and selector must qualify the SAME manufactured
        # capsules/circles at the SAME clearance. Buffered polygon samples
        # plus an extra epsilon rejected native-clear narrow throats (and
        # were not exact bounds for large caps). Native shape collision is
        # also the final copper guard; no process floor is reduced here.
        return bool(any(layer == other and shape.Collide(peer,gap)
            for layer, shape in first for other, peer in last))
    return conflicts


def choose(board, packet, *, validate_selection=None, timeout_s=10.):
    if row._source_binding(board) != packet['source_native_binding']:
        raise ValueError('stale_cell_connection_menus')
    import cec_exact_connection_aliases as aliases
    coverage=aliases.packet_coverage(packet)
    def receive(selected):
        if not _ground_dependencies_received(board, selected,
                board_hint=packet.get('ground_dependency_board_hint')):
            return False
        return True if validate_selection is None else validate_selection(selected)
    result=joint.solve(packet['domains'], conflicts=conflict_oracle(board),
        validate_selection=receive, timeout_s=timeout_s)
    if coverage is not None:
        if aliases.packet_coverage(packet)!=coverage:
            raise ValueError('source_alias_coverage_changed_during_selection')
        result['original_obligation_coverage']=coverage
    return result


def _with_staged_ground_failure_frontier(packet,requests,selection,trials):
    """Spend existing retry slots on an actual failed native Ground join.

    An empty conditional offer is not a proved connection or an immutable
    Source obstacle. Replan it with the selector's exact OTHER future copper
    present. This changes effort order only; every original domain, typed
    producer, work bound and independent physical receiver stays mandatory.
    """
    if (selection.get('complete')is not False or selection.get('input_unchanged')is not True
            or selection.get('domain_binding')!=joint._binding(packet['domains'])):
        return selection
    result=[];seen=set();domains=packet['domains'];binding=selection['domain_binding']
    for trial in reversed(trials[:8]):
        if (trial.get('reason')!='source_smd_ground_boundary_or_local_return_unreceived'
                or trial.get('source_domain_binding')!=binding):continue
        ids=trial.get('selected_choice_ids')
        if type(ids)is not dict or set(ids)!=set(domains):continue
        choices={}
        for key,uid in ids.items():
            matches=[q for q in domains[key]if q.get('id')==uid]
            if len(matches)!=1:break
            choices[key]=matches[0]
        if set(choices)!=set(domains):continue
        for key in trial.get('unreceived_native_terminal_obligations',[]):
            if key not in requests or key in seen:continue
            request=requests[key];choice=choices[key]
            if request.get('net')!='GND':continue
            fragment=request.get('retained_source_ground_fragment')or {}
            typed_cut=(request.get('kind')=='ground_boundary'
                and fragment.get('actual_fixed_source_contacts_not_same_net_proximity')is True
                and fragment.get('whole_original_current_plane_and_saved_partition_receiving_required')is True)
            typed_smd=(request.get('kind')=='source_boundary'
                and choice.get('requires_source_smd_ground_boundary_observation')is True
                and _typed_macro_ground_scope(request)is not None)
            if not (typed_cut or typed_smd):continue
            result.append(dict(obligation=key,assigned={k:v for k,v in ids.items()if k!=key},
                reason='staged_source_ground_native_connection_unreceived',
                effort_order_only_no_connectivity_or_cut_authority=True))
            seen.add(key)
            if len(result)>=4:break
        if len(result)>=4:break
    if not result:return selection
    return dict(selection,failure_frontier=[*result,*selection.get('failure_frontier',[])][:8])


def _conflict_context_key(packet,key,assigned):
    """Deduplicate effort only for the same target and exact future copper.

    Opaque choice IDs alone are insufficient: a changed route may reuse an
    ID, and a previously tried terminal can face a newly selected prefix.
    Singleton obstacles are implicit in refinement, so include them too.
    Unassigned multi-choice menus and costs do not change held copper.
    """
    held={peer:values[0] for peer,values in packet['domains'].items()
        if peer!=key and len(values)==1}
    for peer,uid in assigned.items():
        if peer==key:continue
        choices=[q for q in packet['domains'].get(peer,[]) if q['id']==uid]
        if len(choices)!=1:raise ValueError('exact_conflict_context_choice_required')
        held[peer]=choices[0]
    return _held_conflict_context_key(packet['source_native_binding'],key,held)


def _held_conflict_context_key(source_binding,key,held):
    """Internal fingerprint of actual proposed held copper, not authority."""
    material={peer:{field:value for field,value in choice.items() if field not in ('cost','id')}
        for peer,choice in sorted(held.items())}
    return hashlib.sha256(json.dumps(dict(source=source_binding,
        obligation=key,held=material),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _menu_copper_binding(packet):
    """Physical menu progress, ignoring renamed/duplicate/cost-only offers."""
    material={key:sorted({json.dumps({field:value for field,value in choice.items()
        if field not in ('id','cost')},sort_keys=True,separators=(',',':'),allow_nan=False)
        for choice in choices}) for key,choices in sorted(packet['domains'].items())}
    return hashlib.sha256(json.dumps(material,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _followup_producer_slots(initial_menu_binding,packet,actions):
    """Only unused original slots; genuine initial OR cooperative progress."""
    if type(actions)is not list or len(actions)>4:
        raise ValueError('bounded_cooperative_action_accounting_required')
    return 4-len(actions) if _menu_copper_binding(packet)!=initial_menu_binding else 0


def refine_conflict_frontier(board,packet,requests,selection,*,board_path,board_hint,
                             timeout_s=10.,include_power_layer=False,max_obligations=4,
                             measurement_bridges=False,source_board=None):
    """One finite typed-menu retry against mandatory future copper.

    Independent endpoint menus can all prefer the same channel. The joint
    solver's actual failure frontier identifies which menu needs more effort.
    A one-choice generated route is negotiable, not immutable Source metal.
    Stage only compatible peer proposals, retain all original choices,
    and propose alternative boundaries/measurement leaves with those real
    obstacles present. Measurement contact, width and layer policy remain
    unchanged, including a no-via Kelvin input. All temporary material is
    removed; final joint/native receiving still decides whether ANY complete
    selection is acceptable.
    """
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10
            or type(include_power_layer) is not bool or type(measurement_bridges) is not bool
            or type(max_obligations) is not int
            or not 1<=max_obligations<=4 or row._source_binding(board)!=packet['source_native_binding']
            or set(packet['domains'])!=set(requests) or selection.get('complete') is not False
            or selection.get('input_unchanged') is not True
            or selection.get('domain_binding')!=joint._binding(packet['domains'])):
        raise ValueError('exact_failed_joint_frontier_and_bounded_refinement_required')
    binding=row._source_binding(board);material,groups=cell._cell_trial_snapshot(board)
    # Diagnostic current contracts may contain immutable native pad handles.
    # Only the JSON operation domains need a private copy; do not pickle a
    # SWIG object or mutate the original diagnostic/source binding.
    result=dict(packet,domains=copy.deepcopy(packet['domains']));deadline=time.monotonic()+timeout_s
    single={key:values[0] for key,values in packet['domains'].items() if len(values)==1}
    eligible={'source_boundary','ground_boundary','local_supply','measurement','isolated_measurement'}
    hard={key:choice for key,choice in single.items() if
        requests[key].get('required_projected_ground_entry') is not None
        or requests[key].get('required_new_ground_dogbone') is not None
        or requests[key]['kind'] not in eligible or not choice['ops']}
    oracle=conflict_oracle(board);values=list(hard.values())
    if any(oracle(a,b) for i,a in enumerate(values) for b in values[i+1:]):
        raise ValueError('mandatory_singleton_proposals_are_not_compatible')
    keys=[];contexts={}
    def add_key(key,failed):
        if key in requests and key not in hard and requests[key]['kind'] in eligible and key not in keys:
            keys.append(key);contexts[key]=failed.get('assigned',{})
    for failed in selection.get('failure_frontier',[]):
        key=failed.get('obligation')
        add_key(key,failed)
        # MRV/opaque-ID ordering may assign the generated singleton first,
        # then report a REQUIRED column as the failed domain. That column is
        # not movable: regenerate the conflicting assigned route instead.
        if key in hard:
            for peer,choice_id in sorted(failed.get('assigned',{}).items()):
                choices=[q for q in packet['domains'].get(peer,[]) if q['id']==choice_id]
                if len(choices)!=1:raise ValueError('failed_frontier_assigned_choice_missing')
                if peer not in hard and oracle(choices[0],hard[key]):add_key(peer,failed)
    keys=keys[:max_obligations];trials=[]
    for index,key in enumerate(keys):
        now=time.monotonic()
        if now>=deadline:break
        # Required copper is fixed; an unrelated GENERATED singleton is
        # merely one proposal. Two incompatible generated choices must not
        # prevent this failed domain from obtaining an alternative. Stage a
        # compatible subset around every required obstacle, but retain ALL
        # original domains for the final all-obligation native selection.
        # This is not partial routing credit or permission to remove Source
        # metal. The target's obsolete choice never obstructs its retry.
        fixed={peer:choice for peer,choice in hard.items() if peer!=key}
        unstaged=[];unstaged_assigned=[];staged_assigned={}
        # The failed selector's actual prefix includes useful multi-choice
        # routes too. Ignoring those routes regenerates alternatives through
        # exactly the corridor that just failed. Hold their concrete native
        # choices where compatible with required copper; all domains remain
        # negotiable in the final solver, and no prefix is routing admission.
        for peer,choice_id in sorted(contexts[key].items()):
            choices=[q for q in packet['domains'].get(peer,[]) if q['id']==choice_id]
            if len(choices)!=1:raise ValueError('failed_frontier_assigned_choice_missing')
            if peer==key or peer in hard:continue
            choice=choices[0]
            if any(oracle(choice,other) for other in fixed.values()):
                unstaged_assigned.append(peer)
            else:fixed[peer]=choice;staged_assigned[peer]=choice_id
        for peer,choice in sorted(single.items()):
            if peer==key or peer in hard or peer in fixed or peer in unstaged_assigned:continue
            if any(oracle(choice,other) for other in fixed.values()):
                unstaged.append(peer)
            else:fixed[peer]=choice
        try:
            for choice in fixed.values():_native_ops(board,choice['ops'],choice['net'])
            left=deadline-time.monotonic()
            if left<=0:
                trials.append(dict(obligation=key,before_choices=len(result['domains'][key]),added_choices=0,
                    deferred_reason='refinement_lease_exhausted_after_obstacle_staging',mandatory_obstacles=sorted(hard),
                    staged_obligations=sorted(fixed),unstaged_conflicting_generated_singletons=unstaged,
                    staged_assignment_choices=staged_assigned,unstaged_conflicting_assignment_choices=unstaged_assigned))
                break
            fresh=menus(board,{key:requests[key]},board_path=board_path,board_hint=board_hint,
                timeout_s=left/(len(keys)-index),max_choices=48,
                include_power_layer=include_power_layer,measurement_bridges=measurement_bridges,
                source_board=source_board,whole_requests=requests)
            before=len(result['domains'][key]);added=0
            used_ids={choice['id'] for choice in result['domains'][key]};ordinal=0
            for candidate in fresh['domains'][key]:
                if len(result['domains'][key])>=96:break
                if any(candidate['ops']==old['ops'] and candidate.get('requires_ground_entry')==
                        old.get('requires_ground_entry') for old in result['domains'][key]):continue
                while 'future_copper_'+str(ordinal) in used_ids:ordinal+=1
                candidate=dict(candidate,id='future_copper_'+str(ordinal));used_ids.add(candidate['id'])
                result['domains'][key].append(candidate);added+=1
            trials.append(dict(obligation=key,before_choices=before,added_choices=added,
                conflict_context_key=_conflict_context_key(packet,key,contexts[key]),
                mandatory_obstacles=sorted(hard),staged_obligations=sorted(fixed),
                unstaged_conflicting_generated_singletons=unstaged,staged_assignment_choices=staged_assigned,
                unstaged_conflicting_assignment_choices=unstaged_assigned,diagnostics=fresh['diagnostics'][key]))
        finally:
            discard_items(board,[t for t in board.GetTracks() if force._uid(t) not in material])
            if cell._cell_trial_snapshot(board)!=(material,groups) or row._source_binding(board)!=binding:
                raise ValueError('joint_frontier_refinement_changed_private_source')
    result['conflict_aware_refinement']=dict(trials=trials,source_unchanged=True,
        hard_singleton_obligations=sorted(hard),generated_singleton_routes_are_negotiable=True,
        one_bounded_pass_only=True,no_path_proof=False,release_authority=False)
    return result


def unplanned_source_terminals(parent,proposal,requests,*,timeout_s=10.,board=None,
        required_quiet_output_pad_uuids=()):
    """Isolated terminals need routing or literal source no-connect intent."""
    if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.:
        raise ValueError('bounded_source_terminal_obligation_inventory_required')
    deadline=time.monotonic()+timeout_s
    missing=[r for r in proposal['inherited_unrouted_measurement_lands']
        if 'isolated_measurement:'+r['pad_uuid'] not in requests]
    graph=fr._read_only_route_connectivity(parent)
    explicit={q['pad_uuid'] for q in proposal.get('source_explicit_schematic_no_connects',[])}
    import cec_address_supply_obligations as address_supply
    address_discharged=(address_supply.discharged(parent,board,proposal,requests,
        timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        if board is not None else set())
    quiet_discharged=set()
    if required_quiet_output_pad_uuids or any(r.get('kind')=='source_typed_incoming_quiet_output'
            or k.startswith('quiet_output:') for k,r in requests.items()):
        if board is None:raise ValueError('actual_projected_quiet_frame_required')
        import cec_macro_quiet_output as quiet_outputs
        quiet_discharged=quiet_outputs.discharged(parent,board,proposal,requests,
            required_quiet_output_pad_uuids,timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    for ref,model in proposal['device_contracts'].items():
        if ref in proposal['stationary_device_owners']:continue
        for pad in parent.FindFootprintByReference(ref).Pads():
            if time.monotonic()>=deadline:raise ValueError('source_terminal_obligation_inventory_deadline')
            if (pad.GetNetCode()<=0 or pad.GetNetname()=='GND' or force._uid(pad) in explicit
                    or force._uid(pad) in address_discharged or force._uid(pad) in quiet_discharged
                    or model['pins'][pad.GetNumber()] in ('power_input','measurement')):continue
            if not any(force._uid(peer)!=force._uid(pad) for peer in graph.GetConnectedItems(pad)):
                missing.append(dict(pad_uuid=force._uid(pad),owner=ref,pin=pad.GetNumber(),
                    net=pad.GetNetname(),new_typed_terminal_routing_still_required=True))
    import cec_source_no_connect as no_connect
    if not no_connect.bindings_current(proposal.get('source_explicit_schematic_no_connects',[])):
        raise ValueError('explicit_source_noconn_schematic_epoch_changed')
    return missing


def _source_ground_preparation_lease(deadline,now,timeout_s,per_obligation_leases):
    """Accounting only: one finite Source stage, never route authority."""
    if now>=deadline:raise ValueError('complete_connection_source_ground_preparation_lease_exhausted')
    return ((timeout_s,timeout_s) if per_obligation_leases else
        (min(timeout_s,deadline-now),0.))


def complete_connection_screen(source, board, proposal, *, board_hint, timeout_s=10.,
                               measurement_bridges=False, include_power_layer=False,
                               per_obligation_leases=False, allow_native_ground_refill=False,
                               require_trace_craft_nonregression=False,source_macro_packet=None,
                               cooperative_conflict_negotiation=False):
    """Prove one complete private connection proposal, not ground-only fit.

    Rederive the source-owned cuts and exact draft from the saved parent.
    Every affected obligation needs a compatible native-guarded choice and
    the joint copper must restore every surviving source partition, including
    moved pad identities. All temporary additions are removed on every exit.
    An empty finite menu or exhausted lease is UNKNOWN, never no-path proof.
    Saved-board DRC/current/field/pair/Kelvin and IC-motion receiving remain
    mandatory; this does not grant placement, routing or release authority.
    """
    import cec_ordinary_route_receiving as ordinary
    import cec_ground_return_preservation as ground_preservation
    import cec_route_quality as route_quality
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10 or type(measurement_bridges) is not bool
            or type(include_power_layer) is not bool or type(per_obligation_leases) is not bool
            or type(allow_native_ground_refill) is not bool or type(require_trace_craft_nonregression) is not bool
            or type(cooperative_conflict_negotiation) is not bool
            or source_macro_packet is not None and type(source_macro_packet) is not dict):
        raise ValueError('bounded_complete_connection_screen_required')
    initial_stages=3 if source_macro_packet is not None else 1
    compilation_error=None
    if source_macro_packet is not None:
        import cec_cell_macro_requests as macro
        try:
            compilation_budgets=macro.packet_options(source_macro_packet).get('compilation_phase_timeouts_s')
            if compilation_budgets is not None:
                if any(v>timeout_s for v in compilation_budgets):
                    raise ValueError('connection_screen_compilation_constituents_exceed_limit')
                initial_stages+=len(compilation_budgets)-1
        except ValueError as exc:
            # Malformed worker packets are a normal refused screen, not an
            # exception escaping before the public negative report exists.
            compilation_error=exc
    started=time.monotonic();deadline=started+timeout_s*initial_stages
    source=Path(source).resolve();family=force._family(source,board_hint)
    epoch=force._code_identity();parent=pcbnew.LoadBoard(str(source))
    parent_binding=row._source_binding(parent);binding=row._source_binding(board)
    material,groups=cell._cell_trial_snapshot(board)
    result=dict(schema=1,scope='complete_private_cell_connection_screen',complete=False,
        errors=[],no_path_proof=False,routing_admitted=False,release_authority=False,
        kelvin_qualified=False,current_authority=False,placement_authority=False,
        independent_saved_board_and_ic_motion_receiving_still_required=True)
    result['upstream_trace_craft_nonregression_requested']=require_trace_craft_nonregression
    result['explicit_initial_frame_stages']=initial_stages
    try:
        if compilation_error is not None:raise compilation_error
        if source_macro_packet is None:
            fresh=recompile_source_proposal(parent,proposal,board_hint=board_hint)
            expected=pcbnew.LoadBoard(str(source));apply_private(expected,fresh)
            retired=set(fresh['retired_track_uuids'])
        else:
            import cec_cell_macro_requests as macro
            expected,compiled=macro.compile(source,proposal['poses'],board_hint=board_hint,
                max_shift_mm=proposal['max_shift_mm'],timeout_s=timeout_s,
                allow_owned_locked_escapes=proposal.get('allow_owned_locked_escapes',False),
                rebuild_projected_ground=proposal.get('rebuild_projected_ground',False),
                additional_obstacle_track_uuids=source_macro_packet.get('explicit_additional_obstacle_track_uuids',[]),
                **macro.packet_options(source_macro_packet))
            if compiled!=source_macro_packet:
                raise ValueError('stale_or_forged_complete_macro_source_packet')
            fresh=compiled['source_plan'];retired=set(compiled['retired_track_uuids'])
            result['source_macro_transport']=compiled['transport']
            before_fill=macro.pre_refill_barrel_screen(expected,compiled,timeout_s=timeout_s)
            result['pre_refill_native_macro_barrels']=before_fill
            if not before_fill['ok']:raise ValueError('complete_macro_pre_refill_native_barrel_collision')
        if fresh!=proposal:
            raise ValueError('stale_or_forged_complete_connection_source_plan')
        # Ground boundary identities belong to the exact Source-minus-cut
        # frame, before independent refill changes its native zone islands.
        # Do not derive authority from a caller-supplied/refilled frame.
        if source_macro_packet is None:
            requests=obligations(parent,expected,fresh)
        refill_started=time.monotonic()
        if allow_native_ground_refill:
            # Reconstruct the ACTUAL compiler result, not a wildcard zone
            # exception. The normal selective compiler proves every
            # non-Ground native item exact; caller and expected fills must
            # still match before any temporary route is attempted.
            import cec_additive_route_receiving as additive
            result['independently_rebuilt_ground_zone_uuids']=additive._ground_refill(expected)
        if source_macro_packet is not None and time.monotonic()-refill_started>timeout_s:
            raise ValueError('complete_macro_native_refill_stage_deadline')
        result['native_ground_refill_requested']=allow_native_ground_refill
        if row._source_binding(expected)!=binding:
            raise ValueError('complete_connection_draft_differs_from_exact_source_cut_and_pose')
        if source_macro_packet is not None:
            checked=macro.native_pose_screen(parent,expected,compiled,timeout_s=timeout_s)
            result['independent_macro_native_frame']=checked
            if not checked['ok']:raise ValueError('complete_macro_native_frame_refused')
            requests=compiled['requests']
        result['requests']=requests
        # The complete Source inventory remains mandatory in every saved
        # receiver. Only an exact ordinary duplicate gets one routing domain;
        # otherwise two copies of its proposed barrel collide with themselves.
        import cec_exact_connection_aliases as aliases
        routing_requests,alias_coverage=aliases.routing_view(requests)
        result['exact_source_request_aliases']=alias_coverage
        quiet_ids=(macro.packet_options(compiled).get('required_quiet_output_pad_uuids',())
            if source_macro_packet is not None else ())
        missing=unplanned_source_terminals(parent,fresh,requests,board=board,
            **(dict(required_quiet_output_pad_uuids=quiet_ids)if quiet_ids else {}))
        result['inherited_unplanned_terminals']=missing
        if missing:
            raise ValueError('isolated_source_terminals_have_no_complete_routing_obligation')
        # Explicitly compose finite <=10-s connection stages, like the typed
        # cut-chain receiver. A complete eight-terminal cell need not squeeze
        # all routing strategies AND native receiving into one ten-second
        # aggregate lease. No retries, skipped obligation, or waived predicate.
        if per_obligation_leases:
            deadline=started+timeout_s*(len(requests)+initial_stages+1)
        result.update(per_obligation_leases=per_obligation_leases,
            independent_stage_max_seconds=timeout_s,total_work_bound_seconds=deadline-started)
        ground_planes={force._uid(zone) for zone in parent.Zones()
            if not zone.GetIsRuleArea() and zone.GetNetname()=='GND' and zone.IsFilled()}
        now=time.monotonic()
        if now>=deadline:raise ValueError('complete_connection_inventory_lease_exhausted')
        # Reserve joint receiving time. A first difficult leaf cannot spend
        # the complete lease and then be mistaken for a accepted cell pose.
        packet=menus(board,routing_requests,board_path=source,board_hint=board_hint,
            timeout_s=timeout_s if per_obligation_leases else min(10.,(deadline-now)*.7),max_choices=48,
            measurement_bridges=measurement_bridges,include_power_layer=include_power_layer,
            per_obligation_leases=per_obligation_leases,source_board=parent)
        packet.update(original_source_requests=copy.deepcopy(requests),
            exact_source_request_aliases=alias_coverage)
        result['packet']=packet
        result['obligation_count']=len(requests)
        result['routing_obligation_count']=len(routing_requests)
        aliases.packet_coverage(packet)
        if set(packet['domains'])!=set(routing_requests) or packet['all_obligations_present'] is not True:
            raise ValueError('complete_connection_obligation_inventory_missing')
        result['empty_obligations']=list(packet['empty_obligations'])
        if packet['empty_obligations']:
            result['errors'].append('finite_connection_menu_empty_not_no_path_proof')
        else:
            import cec_complete_cell_receiving as saved_cell
            import cec_native_partition_pair as partition_pair
            rebindings=saved_cell._pad_rebindings(parent,board,fresh['poses'])
            if source_macro_packet is not None:
                macro_mapping=macro.identity_rebindings(parent,board,compiled,
                    timeout_s=min(10.,max(.001,deadline-time.monotonic())))
                # Track/barrel UUID keys do not encode position. Their exact
                # Source-owned transform is independently checked by the
                # compiler; they never need a fake PAD rebinding here.
                if any(k[0]!='pad' and k!=v for k,v in macro_mapping.items()):
                    raise ValueError('complete_connection_changed_copper_identity_key')
                if any(rebindings.get(k)!=v for k,v in macro_mapping.items()if k[0]=='pad'):
                    raise ValueError('complete_connection_macro_pad_identity_mismatch')
            trials=[]; ground_trials=[];craft_trials=[];alias_trials=[];terminal_ground_trials=[]
            source_craft=route_quality.analyze_board(parent) if require_trace_craft_nonregression else None
            source_ground_observer=None
            if (any(request.get('kind')=='ground_boundary'for request in requests.values())
                    or any(choice.get('requires_source_smd_ground_boundary_observation') is True
                        for choices in packet['domains'].values() for choice in choices)):
                import cec_source_ground_boundary_connection as source_ground
                prepared_started=time.monotonic()
                prep_lease,prep_extra=_source_ground_preparation_lease(
                    deadline,prepared_started,timeout_s,per_obligation_leases)
                source_ground_observer=source_ground._prepare_observer(parent,requests,
                    board_hint=board_hint,source_proposal=fresh,timeout_s=prep_lease,
                    source_macro_packet=source_macro_packet)
                deadline+=prep_extra
                result['total_work_bound_seconds']+=prep_extra
                result['source_ground_expectation_preparation']=dict(
                    elapsed_s=time.monotonic()-prepared_started,stage_max_seconds=prep_lease,
                    additional_bounded_stages=int(per_obligation_leases),
                    aggregate_deadline_extension_seconds=prep_extra,
                    aggregate_deadline_from_start_seconds=deadline-started,
                    post_preparation_remaining_seconds=max(0.,deadline-time.monotonic()),
                    joint_callback_inclusive_max_seconds=timeout_s,
                    private_source_expectation_not_live_return_or_connectivity=True)
                # Exactly one extra bounded stage only for the explicitly
                # composed mode; legacy single-lease callers gain no time.
            def validate(selected):
                constructed_by={}
                try:
                    try:
                        _,constructed_by=_stage_selected_connections(board,selected,
                            board_hint=packet.get('ground_dependency_board_hint'),
                            source_path=packet.get('nonload_branch_source_path'),
                            requests=packet.get('original_source_requests',requests))
                    except ValueError as exc:
                        if 'deadline' in str(exc):raise
                        trials.append(dict(lost_source_partitions=None,
                            unreceived_native_terminal_obligations=[],
                            reason='selected_endpoint_materialization_refused',error=str(exc),
                            **_bounded_selected_choice_ids(selected,len(trials))))
                        import cec_cell_endpoint_groups as endpoint_groups
                        # Include wider covering strokes/barrels too. A
                        # partial thin-UUID clause could wrongly prune a
                        # different same-net full-width choice that fixes it.
                        return endpoint_groups.rejection_clause(exc,selected,
                            domain_binding=joint._binding(packet['domains']),domains=packet['domains'])
                    conditional=[key for key,choice in selected.items()
                        if requests[key].get('kind')=='ground_boundary'
                        or choice.get('requires_source_smd_ground_boundary_observation') is True]
                    if conditional:
                        if source_ground_observer is None:raise ValueError('source_ground_expectation_missing')
                        observed=source_ground_observer(board,
                            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
                        missing=[key for key in conditional if observed.get(key)is None]
                        if missing:
                            trials.append(dict(lost_source_partitions=None,
                                unreceived_native_terminal_obligations=missing,
                                source_domain_binding=joint._binding(packet['domains']),
                                reason='source_smd_ground_boundary_or_local_return_unreceived',
                                **_bounded_selected_choice_ids(selected,len(trials))))
                            return False
                    if source_macro_packet is not None and compiled.get('required_supply_departure_columns'):
                        import cec_macro_supply_departure as departure
                        try:
                            departure.receive(board,compiled['required_supply_departure_columns'],
                                {force._uid(t) for t in board.GetTracks() if force._uid(t) not in material},
                                timeout_s=min(10.,max(.001,deadline-time.monotonic())))
                        except ValueError as exc:
                            trials.append(dict(lost_source_partitions=None,
                                unreceived_native_terminal_obligations=['required_supply_departure:'+str(exc)]))
                            return False
                    if source_macro_packet is not None and compiled.get('required_measurement_corridors'):
                        import cec_macro_measurement_corridor as corridor
                        try:
                            corridor.receive(board,compiled['required_measurement_corridors'],
                                {force._uid(t) for t in board.GetTracks() if force._uid(t) not in material},
                                timeout_s=min(10.,max(.001,deadline-time.monotonic())))
                        except ValueError as exc:
                            trials.append(dict(lost_source_partitions=None,
                                unreceived_native_terminal_obligations=['required_measurement_corridor:'+str(exc)]))
                            return False
                    paired=partition_pair.compare(parent,board,
                        timeout_s=min(10.,max(.001,deadline-time.monotonic())),
                        retired_uuids=retired,identity_rebindings=rebindings)
                    lost=len(paired['demoted_parts'])
                    graph=fr._read_only_route_connectivity(board);terminal_failures=[]
                    for key,request in requests.items():
                        if time.monotonic()>=deadline:
                            raise ValueError('complete_connection_terminal_receiving_lease_exhausted')
                        if request['kind'] not in ('ground','source_retained_address_ground_connection','local_supply','isolated_measurement','source_typed_incoming_quiet_output'):continue
                        pad=next(p for fp in board.GetFootprints() for p in fp.Pads()
                            if force._uid(p)==request['a']['pad_uuid'])
                        reached={force._uid(item) for item in graph.GetConnectedItems(pad)}
                        required=(ground_planes if request['kind']in('ground','source_retained_address_ground_connection')
                            else {request['b']['pad_uuid']})
                        if not (reached & required):terminal_failures.append(key)
                    trials.append(dict(lost_source_partitions=lost,
                        unreceived_native_terminal_obligations=terminal_failures))
                    if lost or terminal_failures:
                        return False
                    # Electrical plane reachability is NOT a bounded local
                    # return. Match the saved cell receiver before accepting
                    # a complete choice: an address/reference strap cannot
                    # make a mutually grounded pair into a real nearby entry.
                    local_ground=dict(ok=True,proofs=[],failed_request=None)
                    terminal_ground_trials.append(local_ground)
                    for key,request in requests.items():
                        if request['kind']=='source_retained_address_ground_connection':
                            import cec_retained_address_ground as address_ground
                            try:
                                proof=address_ground.observe(board,request,requests,
                                    timeout_s=min(10.,max(.001,deadline-time.monotonic())))
                                local_ground['proofs'].append(dict(request=key,logical_connection=proof))
                            except ValueError as exc:
                                local_ground.update(ok=False,failed_request=key,error=str(exc))
                                return False
                            continue
                        if request['kind']!='ground':continue
                        pad=next(p for fp in board.GetFootprints()for p in fp.Pads()
                            if force._uid(p)==request['a']['pad_uuid'])
                        immediate=cell._existing_return(board,pad,request['reach_mm'],
                            allow_native_track_body=True)
                        if immediate is not None:
                            local_ground['proofs'].append(dict(request=key,return_mm=immediate[0],
                                via_uuid=force._uid(immediate[1])))
                        else:
                            import cec_saved_ground_hierarchy as hierarchy
                            try:
                                proof=hierarchy.receive(parent,board,request,requests,
                                    board_hint=board_hint,deadline=min(deadline,time.monotonic()+10.),
                                    source_proposal=fresh)
                                local_ground['proofs'].append(dict(request=key,hierarchy=proof))
                            except ValueError as exc:
                                local_ground.update(ok=False,failed_request=key,
                                    source_max_return_mm=request['reach_mm'],error=str(exc))
                                return False
                    try:
                        alias_paths=aliases.receive_paths(board,requests,
                            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
                        alias_trials.append(alias_paths)
                    except ValueError as exc:
                        alias_trials.append(dict(ok=False,complete=False,error=str(exc)))
                        return False
                    if require_trace_craft_nonregression:
                        quality=route_quality.analyze_board(board)
                        craft_trials.append(dict(source_issues=source_craft['issue_count'],
                            candidate_issues=quality['issue_count'],
                            source_non_octilinear=source_craft['non_octilinear_count'],
                            candidate_non_octilinear=quality['non_octilinear_count']))
                        # Preserve a bounded exact fail stack instead of
                        # retrying anonymous "two issue" counts. Provenance
                        # is diagnostic only, never a routing exception.
                        if len(craft_trials)<=8:
                            craft_trials[-1].update(
                                selected_choice_ids={k:q['id'] for k,q in selected.items()},
                                issues=[dict(issue,construction_ownership={u:constructed_by.get(u,
                                    {'retained_source':True}) for u in issue['track_uuids']})
                                    for issue in quality.get('issues',[])[:8]],
                                non_octilinear=quality.get('non_octilinear',[])[:8],
                                issue_detail_truncated=len(quality.get('issues',[]))>8
                                    or len(quality.get('non_octilinear',[]))>8,
                                issue_detail_unavailable='issues' not in quality
                                    or 'non_octilinear' not in quality)
                        if (quality['issue_count']>source_craft['issue_count']
                                or quality['non_octilinear_count']>source_craft['non_octilinear_count']):
                            return _clean_source_craft_rejection(source_craft,quality,selected,
                                constructed_by,domain_binding=joint._binding(packet['domains']))
                    remaining=deadline-time.monotonic()
                    if remaining<=0:
                        raise ValueError('complete_connection_ground_receiving_lease_exhausted')
                    ground=ground_preservation.receive(parent,board,
                        timeout_s=min(10.,remaining))
                    ground_trials.append(ground)
                    return ground['complete'] is True and ground['ok'] is True
                finally:
                    cell._rollback_cell_trial(board,(material,groups))
                    if row._source_binding(board)!=binding:
                        raise ValueError('complete_connection_trial_changed_private_source')
            remaining=deadline-time.monotonic()
            if remaining<=0:raise ValueError('complete_connection_partition_lease_exhausted')
            attempted_frontiers=set()
            initial_menu_binding=_menu_copper_binding(packet)
            selection=choose(board,packet,validate_selection=validate,
                timeout_s=min(10.,remaining))
            selection=_with_staged_ground_failure_frontier(packet,routing_requests,selection,trials)
            if (not selection.get('complete') and selection.get('failure_frontier')
                    and time.monotonic()<deadline):
                packet=refine_conflict_frontier(board,packet,routing_requests,selection,
                    board_path=source,board_hint=board_hint,source_board=parent,
                    timeout_s=min(10.,max(.001,deadline-time.monotonic())),
                    include_power_layer=include_power_layer,measurement_bridges=measurement_bridges)
                result['packet']=packet
                result['first_joint_selection']=selection
                attempted_frontiers.update(trial['conflict_context_key']for trial in
                    packet.get('conflict_aware_refinement',{}).get('trials',[])
                    if trial.get('obligation')in routing_requests and 'diagnostics'in trial)
                remaining=deadline-time.monotonic()
                if remaining>0:
                    selection=choose(board,packet,validate_selection=validate,
                        timeout_s=min(10.,remaining))
                    selection=_with_staged_ground_failure_frontier(packet,routing_requests,selection,trials)
            if (cooperative_conflict_negotiation and not selection.get('complete')
                    and selection.get('failure_frontier')):
                import cec_joint_route_negotiation as negotiation
                # Explicit independent stages, not an unbounded lease
                # extension: at most four <=10-s producer actions followed
                # by one <=10-s joint/native selection. Source scopes and
                # the full physical receiving callback remain unchanged.
                result['explicit_cooperative_negotiation_stages']=5
                deadline=time.monotonic()+5*timeout_s
                packet=negotiation.propose(board,packet,routing_requests,selection,
                    board_path=source,board_hint=board_hint,timeout_s=timeout_s,max_actions=4,source_board=parent,
                    include_power_layer=include_power_layer,measurement_bridges=measurement_bridges)
                result['packet']=packet
                selection=choose(board,packet,validate_selection=validate,timeout_s=timeout_s)
                selection=_with_staged_ground_failure_frontier(packet,routing_requests,selection,trials)
                actions=packet.get('cooperative_conflict_cluster',{}).get('actions',[])
                if type(actions) is not list or len(actions)>4:
                    raise ValueError('bounded_cooperative_action_accounting_required')
                attempted_frontiers.update(action['conflict_context_key']for action in actions
                    if action.get('obligation')in routing_requests and 'diagnostics'in action)
                unused=_followup_producer_slots(initial_menu_binding,packet,actions)
                # A repaired prefix can expose the NEXT real conflict. Do
                # not discard useful choices and restart the whole board,
                # nor keep retrying the old frontier. Spend only UNUSED
                # producer slots, one typed target at a time, and stop at
                # once when the menu binding does not change. Every retry
                # has its own <=10 s producer and <=10 s selection stage;
                # the unchanged physical receiving callback still decides.
                if (unused and not selection.get('complete') and selection.get('failure_frontier')):
                    result['explicit_followup_negotiation_stages']=2*unused
                    result['maximum_total_cooperative_producer_actions']=4
                    deadline=time.monotonic()+2*unused*timeout_s
                    following=[]
                    result['bounded_followup_frontiers']=following
                    for index in range(unused):
                        if selection.get('complete') or not selection.get('failure_frontier'):break
                        before=joint._binding(packet['domains'])
                        current_failure=copy.deepcopy(selection['failure_frontier'])
                        remaining_failures=[failure for failure in current_failure
                            if _conflict_context_key(packet,failure['obligation'],failure.get('assigned',{}))
                                not in attempted_frontiers]
                        if not remaining_failures:
                            result['followup_frontier_stop']='no_unattempted_failure_target_not_no_path'
                            break
                        # Preserve the full reported failure for provenance.
                        # Only effort order changes: an old first failure may
                        # not starve a different, newly exposed typed target.
                        next_target=dict(selection,failure_frontier=remaining_failures)
                        attempted_before=sorted(attempted_frontiers)
                        packet=refine_conflict_frontier(board,packet,routing_requests,next_target,
                            board_path=source,board_hint=board_hint,timeout_s=timeout_s,source_board=parent,
                            max_obligations=1,include_power_layer=include_power_layer,
                            measurement_bridges=measurement_bridges)
                        result['packet']=packet
                        after=joint._binding(packet['domains'])
                        attempted_frontiers.update(row['conflict_context_key']for row in
                            packet['conflict_aware_refinement'].get('trials',[])
                            if row.get('obligation')in routing_requests and 'diagnostics'in row)
                        trial=dict(ordinal=index,failure_frontier=current_failure,
                            scheduled_failure_frontier=remaining_failures,
                            previously_attempted_targets=attempted_before,
                            before_domain_binding=before,after_domain_binding=after,
                            refinement=packet['conflict_aware_refinement'],
                            source_unchanged=True,new_choices=before!=after,
                            producer_slot=len(actions)+index+1,
                            routing_admitted=False,release_authority=False)
                        following.append(trial)
                        if before==after:
                            trial['stop']='no_new_menu_choices_not_global_no_path'
                            if any(_conflict_context_key(packet,f['obligation'],f.get('assigned',{}))
                                    not in attempted_frontiers for f in current_failure):
                                continue
                            break
                        selection=choose(board,packet,validate_selection=validate,timeout_s=timeout_s)
                        selection=_with_staged_ground_failure_frontier(packet,routing_requests,selection,trials)
                        trial['complete_selection_found']=selection.get('complete') is True
                        if time.monotonic()>=deadline:
                            raise ValueError('bounded_followup_frontier_stages_exhausted')
            result['selection']=selection
            result['complete_selection_partition_trials']=trials
            result['complete_selection_ground_return_trials']=ground_trials
            result['complete_selection_terminal_ground_return_trials']=terminal_ground_trials
            result['complete_selection_trace_craft_trials']=craft_trials
            result['complete_selection_original_alias_path_trials']=alias_trials
            result['complete']=(selection.get('complete') is True
                and selection.get('all_obligations_present') is True
                and bool(trials) and trials[-1]['lost_source_partitions']==0
                and bool(ground_trials) and ground_trials[-1]['complete'] is True
                and ground_trials[-1]['ok'] is True
                and bool(alias_trials) and alias_trials[-1]['complete'] is True
                and alias_trials[-1]['ok'] is True
                and time.monotonic()<deadline)
            if not result['complete']:
                result['errors'].append('finite_joint_connection_proposal_not_completed')
    except ValueError as exc:
        result['errors'].append(str(exc))
    finally:
        discard_items(board,[t for t in board.GetTracks() if force._uid(t) not in material])
        new_groups=[g for g in board.Groups() if force._uid(g) not in groups]
        for group in new_groups:
            for item in list(group.GetItems()):group.RemoveItem(item)
        discard_items(board,new_groups)
        import cec_source_no_connect as no_connect
        if (row._source_binding(board)!=binding or row._source_binding(parent)!=parent_binding
                or cell._cell_trial_snapshot(board)!=(material,groups)
                or family!=force._family(source,board_hint) or epoch!=force._code_identity()
                or not no_connect.bindings_current(proposal.get('source_explicit_schematic_no_connects',[]))):
            raise ValueError('complete_connection_screen_changed_source_draft_or_code')
    result.update(elapsed_s=time.monotonic()-started,lease_exhausted=time.monotonic()>=deadline,
        source_and_private_draft_unchanged=True)
    return result


def _ground_dependencies_received(board, selected, *, board_hint):
    """Receive actual joint copper; reject circular or missing portal promises."""
    dependent = [(choice, choice['requires_ground_entry']) for choice in selected.values()
        if choice.get('requires_ground_entry')]
    if not dependent:
        return True
    if not board_hint:
        return False
    bypasses = {entry['selected_bypass']: dict(owner=entry['selected_owner'],
        pin=entry['selected_supply_pin'], rail=entry['selected_rail']) for _, entry in dependent}
    fresh = assigned_ground_entries(board, bypasses, board_hint=board_hint)
    pads = {force._uid(p): p for fp in board.GetFootprints() for p in fp.Pads()}
    made = []; binding = row._source_binding(board)
    original_items = {force._uid(t) for t in board.GetTracks()}
    try:
        for choice in selected.values():
            made.extend(_native_ops(board, choice['ops'], choice['net']))
        for choice, entry in dependent:
            portal = pads.get(entry['portal_pad_uuid'])
            root = pads.get(entry['root_portal_pad_uuid'])
            cap_choice = selected.get(entry['root_portal_obligation'])
            if (portal is None or root is None or entry['portal_obligation'] not in selected
                    or cap_choice is None or cap_choice['net'] != 'GND'
                    or cap_choice.get('requires_ground_entry')
                    or cell._existing_return(board, root, .8) is None):
                return False
            # The producer's metadata cannot invent a different owner, a
            # looser length limit, or a peer with a merely similar net name.
            owners = [pads[uid] for uid, value in fresh.items() if value == entry
                and uid == entry['owner_ground_pad_uuid']]
            if not owners:
                return False
            linked = False
            for pad in owners:
                path = cell._shortest_track_path_mm(board, pad, portal, snap_mm=.000001)
                spec = cell._netclass(board, 'GND')
                limit = min(entry['max_link_mm'], cell._local_supply_limit_mm(entry['direct_mm'],
                    spec['width']/1e6, max(200000, int(spec['clearance']))/1e6))
                if path is not None and path <= limit+1e-9:
                    linked = True
            if not linked:
                return False
        return True
    finally:
        discard_items(board, [t for t in board.GetTracks() if force._uid(t) not in original_items])
        if row._source_binding(board) != binding:
            raise ValueError('ground_dependency_receiving_changed_source')


def _bounded_selected_choice_ids(selected,trial_index):
    """Bounded diagnostics only, never a saved routing/return witness."""
    return ({'selected_choice_ids':{key:choice['id']for key,choice in selected.items()}}
        if trial_index<8 else {})


def _stage_selected_connections(board,selected,*,board_hint,source_path,requests=None):
    """The SAME native copper and endpoint ownership for trial and save.

    Group labels alone confer no current or local-return authority. Both
    staged and saved receivers still rederive actual Source/current/geometry.
    The caller owns rollback, including any partially created endpoint group.
    """
    # Materialize sufficient-width proposals before narrower demands.  The
    # exact collinear reuse in _native_ops is deliberately one-way: it cannot
    # replace, widen or remove retained metal.  If a narrow local endpoint
    # demand happens to precede a wider Source-boundary replacement, adding
    # them in dictionary order otherwise manufactures a covered backtrack.
    # This order changes no selected path or width and never clips partial
    # overlap; the full saved current/partition/craft receivers still apply.
    operations=[]
    for obligation,choice in selected.items():
        for index,op in enumerate(choice['ops']):
            if op[0]=='trk':
                a,b=op[1:3]
                priority=(0,-int(op[3]),-sum((a[i]-b[i])**2 for i in (0,1)),
                    str(choice['net']),int(op[4]),tuple(sorted((tuple(a),tuple(b)))))
            else:
                priority=(1,0,0,str(choice['net']),0,())
            operations.append((priority,str(obligation),index,obligation,choice,op))
    made=[];constructed_by={}
    for _,_,_,obligation,choice,op in sorted(operations,key=lambda entry:entry[:3]):
        for item in _native_ops(board,[op],choice['net']):
            made.append(item)
            constructed_by[force._uid(item)]=dict(obligation=obligation,choice_id=choice['id'])
    import cec_cell_endpoint_groups as endpoint_groups
    try:
        endpoint_groups.group(board,made,board_hint=board_hint,source_path=source_path,requests=requests)
    except endpoint_groups.EndpointMaterializationRefused as exc:
        exc.constructed_by={uid:dict(owner)for uid,owner in constructed_by.items()}
        raise
    return made,constructed_by


def construct_private(board, packet, selection):
    import cec_exact_connection_aliases as aliases
    coverage=aliases.packet_coverage(packet)
    if coverage is not None and selection.get('original_obligation_coverage')!=coverage:
        raise ValueError('complete_original_source_alias_selection_coverage_required')
    if (selection.get('complete') is not True or selection.get('all_obligations_present') is not True
            or selection.get('routing_admitted') is not False
            or selection.get('domain_binding') != joint._binding(packet['domains'])
            or row._source_binding(board) != packet['source_native_binding']
            or set(selection.get('selected', {})) != set(packet['domains'])
            or any(choice not in packet['domains'][key] for key, choice in selection['selected'].items())):
        raise ValueError('complete_unadmitted_joint_selection_required')
    if not _ground_dependencies_received(board, selection['selected'],
            board_hint=packet.get('ground_dependency_board_hint')):
        raise ValueError('joint_selected_ground_entry_not_received')
    made = []; original_items = {force._uid(t) for t in board.GetTracks()}
    original_groups={force._uid(g):{force._uid(i) for i in g.GetItems()} for g in board.Groups()}
    try:
        made,_=_stage_selected_connections(board,selection['selected'],
            board_hint=packet.get('ground_dependency_board_hint'),
            source_path=packet.get('nonload_branch_source_path'),
            requests=packet.get('original_source_requests'))
    except Exception:
        for group in list(board.Groups()):
            keep=original_groups.get(force._uid(group),set())
            for item in list(group.GetItems()):
                if force._uid(item) not in keep:group.RemoveItem(item)
            if force._uid(group) not in original_groups:discard_items(board,[group])
        discard_items(board, [t for t in board.GetTracks() if force._uid(t) not in original_items])
        raise
    return made
