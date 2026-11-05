"""Source-typed same-package address straps; no per-input load guesses.

The complete-cell compiler rederives these exact requests and
retains every original current, native partition and saved-board receiver.
"""
import math
import time
import pcbnew
import cec_force_current as force
import cec_fr as fr
import cec_device_power_roles as roles
import cec_decoupler_cell as cell
import cec_constraints as constraints


def requests(source, board, proposal, *, timeout_s=10.):
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10.):
        raise ValueError('bounded_address_supply_derivation_required')
    deadline=time.monotonic()+timeout_s
    def check():
        if time.monotonic()>=deadline:
            raise ValueError('address_supply_derivation_deadline')
    result = {}
    poses = proposal.get('poses')
    if (type(poses) is not dict or not 1 <= len(poses) <= 8
            or any(type(ref) is not str or not ref for ref in poses)):
        raise ValueError('bounded_address_supply_pose_inventory_required')
    footprints = list(source.GetFootprints())
    if not 1 <= len(footprints) <= 4096 or sum(len(list(fp.Pads())) for fp in footprints) > 65536:
        raise ValueError('bounded_address_supply_source_inventory_required')
    if len(list(source.GetTracks())) > 200000:
        raise ValueError('bounded_address_supply_source_track_inventory_required')
    applicable = {}
    for ref in poses:
        check()
        if ref in proposal['stationary_device_owners']:
            continue
        original = source.FindFootprintByReference(ref)
        if original is None:
            raise ValueError('address_supply_source_owner_missing')
        model = roles.footprint_contract(original)
        if model and 'address' in model.get('pins', {}).values():
            applicable[ref] = model
    if not applicable:
        return result
    selected = proposal.get('selected_bypasses')
    if type(selected) is not dict or len(selected) > 8:
        raise ValueError('bounded_address_supply_selected_bypass_inventory_required')
    # This evidence is rederived from ORIGINAL source, not the proposal's
    # asserted cap name or its possibly changed private geometry.
    with force._thermal_hint(proposal['board_hint']):
        assignment = constraints._device_bypass_assignment(source, project_max_mm=3.5)
    check()
    actual = {}
    for item in assignment['assigned'].values():
        check()
        req = item['requirement']
        actual.setdefault(item['cap_ref'], []).append(dict(owner=req['ref'], pin=str(req['pin']), rail=req['rail']))
    roots = {}
    for cap_ref, claim in selected.items():
        check()
        if claim.get('owner') not in applicable:
            continue
        if actual.get(cap_ref) != [claim]:
            raise ValueError('address_supply_unique_source_bypass_assignment_required')
        cap = source.FindFootprintByReference(cap_ref)
        owner = source.FindFootprintByReference(claim['owner'])
        power = owner.FindPadByNumber(claim['pin']) if owner else None
        cpads = list(cap.Pads()) if cap else []
        if (cap is None or owner is None or power is None or len(cpads) != 2
                or {p.GetNetname() for p in cpads} != {'GND', claim['rail']}
                or power.GetNetname() != claim['rail'] or cap.IsFlipped() != owner.IsFlipped()
                or any(p.HasHole() or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD for p in cpads)
                or math.dist(tuple(power.GetPosition()), tuple(next(p for p in cpads if p.GetNetname() == claim['rail']).GetPosition())) > 3500000):
            raise ValueError('address_supply_real_local_surface_bypass_required')
        key = (claim['owner'], claim['pin'], claim['rail'])
        if key in roots:
            raise ValueError('address_supply_ambiguous_source_bypass_root')
        roots[key] = cap_ref
    graph = fr._read_only_route_connectivity(source)
    check()
    def endpoint(p):
        return dict(pad_uuid=force._uid(p), at_nm=list(p.GetPosition()),
                    layers=list(map(int, p.GetLayerSet().CuStack())))
    for ref, model in applicable.items():
        check()
        original = source.FindFootprintByReference(ref)
        live = board.FindFootprintByReference(ref)
        if original is None or live is None:
            raise ValueError('address_supply_source_owner_missing')
        pads = list(original.Pads()); numbers = [p.GetNumber() for p in pads]
        if len(set(numbers)) != len(numbers) or set(numbers) != set(model['pins']):
            raise ValueError('address_supply_exact_unaliased_manufacturer_pinmap_required')
        livepads = {force._uid(p): p for p in live.Pads()}
        if set(livepads) != {force._uid(p) for p in pads}:
            raise ValueError('address_supply_source_pad_identity_changed')
        if any(list(p.GetLayerSet().CuStack()) != list(livepads[force._uid(p)].GetLayerSet().CuStack()) for p in pads):
            raise ValueError('address_supply_source_pad_copper_stack_changed')
        for pad in pads:
            check()
            if model['pins'][pad.GetNumber()] != 'address' or pad.GetNetname() == 'GND' or pad.GetNetCode() <= 0:
                continue
            # Already routed source terminals retain their ordinary literal
            # cut/boundary obligation; never create a parallel shortcut.
            if any(force._uid(p) != force._uid(pad) for p in graph.GetConnectedItems(pad)):
                continue
            net = str(pad.GetNetname())
            peers = [p for p in pads if model['pins'][p.GetNumber()] == 'power_input'
                     and p.GetNetCode() == pad.GetNetCode() and p.GetNetname() == net]
            peers = [p for p in peers if (ref, p.GetNumber(), net) in roots]
            if not peers:
                continue  # The strict unplanned-terminal inventory refuses.
            peers.sort(key=lambda p: (math.dist(tuple(pad.GetPosition()), tuple(p.GetPosition())), force._uid(p)))
            peer = peers[0]
            a, b = livepads[force._uid(pad)], livepads[force._uid(peer)]
            for old, new in ((pad, a), (peer, b)):
                if (new.GetNumber() != old.GetNumber() or new.GetNetname() != old.GetNetname()
                        or new.GetNetCode() <= 0 or old.HasHole() or new.HasHole()
                        or old.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                        or new.GetAttribute() != pcbnew.PAD_ATTRIB_SMD):
                    raise ValueError('address_supply_exact_surface_source_endpoint_required')
            # Numeric net codes are local to a native BOARD and may be
            # renumbered by a save/reload. Exact source names, pad UUIDs and
            # same-child membership must agree, not unrelated code ordinals.
            if a.GetNetCode()!=b.GetNetCode():
                raise ValueError('address_supply_same_child_net_membership_required')
            common = set(a.GetLayerSet().CuStack()) & set(b.GetLayerSet().CuStack())
            if len(common) != 1 or original.IsFlipped() != live.IsFlipped():
                raise ValueError('address_supply_same_source_surface_required')
            # Both positions are compiler-owned transforms, never caller XY.
            witness = pcbnew.FOOTPRINT(original)
            witness.SetPosition(live.GetPosition())
            witness.SetOrientationDegrees(live.GetOrientationDegrees())
            witnesspads = {force._uid(p): p for p in witness.Pads()}
            for old, new in ((pad, a), (peer, b)):
                if tuple(witnesspads[force._uid(old)].GetPosition()) != tuple(new.GetPosition()):
                    raise ValueError('address_supply_origin_or_relative_geometry_changed')
            with force._thermal_hint(proposal['board_hint']):
                contract = cell._supply_current_widths(source, net)
            check()
            if (not contract or not contract.get('current_authority')
                    or any(face not in contract['required_by_layer_nm']
                        or type(contract['required_by_layer_nm'][face]) is not int
                        or contract['required_by_layer_nm'][face] <= 0 for face in common)):
                raise ValueError('address_supply_positive_source_current_contract_required')
            width = max(int(source.GetDesignSettings().m_TrackMinWidth),
                        int(cell._netclass(source, net)['width']),
                        *(int(contract['required_by_layer_nm'][f]) for f in common))
            if width <= 0:
                raise ValueError('address_supply_positive_full_class_width_required')
            result['address_supply:'+force._uid(pad)] = dict(
                kind='source_boundary', net=net, a=endpoint(a), b=endpoint(b), width_nm=width,
                unchanged_full_rail_current_contract=contract,
                source_address_supply=dict(source_address=endpoint(pad), source_power_input=endpoint(peer),
                    manufacturer_contract=model, exact_same_package_positive_power_input=True,
                    original_current_and_local_bypass_obligations_remain_required=True))
    return result


def discharged(source, board, proposal, supplied, *, timeout_s=10.):
    """Only exact independently rebuilt requests in JSON wire form count.

    The compiler serializes its complete packet, so native integer layer
    keys arrive as JSON strings.  Preserve all source evidence and numeric
    values, rather than mistaking that representation change for a missing
    obligation (or using Python's permissive bool/int equality).
    """
    import cec_request_wire_identity as wire
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10.):
        raise ValueError('bounded_address_supply_derivation_required')
    if type(supplied) is not dict or len(supplied) > 64:
        raise ValueError('bounded_address_supply_request_inventory_required')
    deadline = time.monotonic() + timeout_s
    expected = requests(source, board, proposal, timeout_s=timeout_s)
    result = set()
    for key, request in expected.items():
        if key not in supplied:
            continue
        if (wire.canonical(request, deadline=deadline)
                == wire.canonical(supplied[key], deadline=deadline)):
            result.add(request['a']['pad_uuid'])
    if time.monotonic() >= deadline:
        raise ValueError('address_supply_derivation_deadline')
    return result
