"""Re-prove class-only supply escapes without lowering sustained current.

This is deliberately separate from an under-current endpoint exception. Each
accepted leg carries the entire source-owned current, on its actual copper
face, with the unchanged fabrication profile and margin. Only a bounded,
unbranched typed supply-terminal escape to a full-width retained throat may
be below the preferred netclass width. No via/barrel rating is assigned.
"""
from __future__ import annotations

import math
import time
import json

import pcbnew

import cec_device_power_roles as roles
import cec_device_bypass as bypass
import cec_fab_profile as fab
import cec_fr as fr
from cec_route_dimensions import current_trace_widths


def _manufacturer_supply_bridge(fp, pads):
    """Recognize only a value-qualified, explicitly modeled two-supply cap.

    NXP AH1014 Rev. 1.5 Fig. 17/sec. 8.9 requires VIO-to-VCC EMC bypass.
    Actual package pin functions and both native nets bind this role. It
    grants no smaller load, preferred-width trunk exception, or placement/HF
    qualification; the bounded prefix still carries the complete source.
    """
    board=fp.GetBoard()
    owners=list(board.GetFootprints()) if board is not None else []
    if len(owners)>4096:return None
    cap_nets={str(p.GetNetname()) for p in pads}
    if len(cap_nets)!=2 or 'GND' in cap_nets:return None
    matches=set()
    for owner in owners:
        if owner.IsDNP():continue
        rules=list(bypass.rail_to_rail_requirements_for_value(owner.GetValue()))
        if not rules:continue
        model=roles.footprint_contract(owner)
        if not model:continue
        for first,second,kind,_distance,_source in rules:
            if (not bypass.kind_compatible(kind,bypass.capacitance_f(fp.GetValue()))
                    or any(model['pins'].get(n) not in ('power_input','power_output')
                           for n in (first,second))):continue
            pin_rows=[[p for p in owner.Pads() if str(p.GetNumber())==n]
                      for n in (first,second)]
            if any(len(row)!=1 for row in pin_rows):continue
            selected=[row[0] for row in pin_rows]
            if (any(p.GetNetCode()<=0 or p.HasHole()
                    or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for p in selected)
                    or {str(p.GetNetname()) for p in selected}!=cap_nets):continue
            matches.add((owner.m_Uuid.AsString(),first,second))
    return 'manufacturer_supply_to_supply_bypass_terminal' if len(matches)==1 else None


def supply_terminal_role(pad):
    """Positive pin/capacitor identity, not a net/ref name or load estimate.

    A grounded value-qualified two-land ceramic is a supply shunt terminal,
    not a consumer current allocation. A manufacturer-modeled two-supply EMC
    cap has its own positive pin/net/value binding; arbitrary rail-to-rail
    passives and control/sensing pins remain outside this class-only scope.
    """
    fp = pad.GetParentFootprint()
    if (fp.IsDNP() or pad.GetNetCode() <= 0 or pad.HasHole()
            or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD):
        return None
    selected = roles.footprint_contract(fp)
    if selected and selected['pins'].get(str(pad.GetNumber())) in ('power_input','power_output'):
        return 'manufacturer_supply_pin'
    pads = list(fp.Pads())
    if (len(pads) != 2 or str(pad.GetNetname()) == 'GND'
            or any(p.GetNetCode() <= 0 or p.HasHole() or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD for p in pads)
            or len(tuple(pad.GetLayerSet().CuStack())) != 1
            or any(tuple(p.GetLayerSet().CuStack()) != tuple(pad.GetLayerSet().CuStack()) for p in pads)
            or not bypass.capacitor_identity(fp.GetReference(),fp.GetFPIDAsString())
            or not bypass.local_bypass_technology(fp.GetValue(),fp.GetFPIDAsString())
            or bypass.capacitance_f(fp.GetValue()) is None):
        return None
    if {str(p.GetNetname()) for p in pads} == {'GND',str(pad.GetNetname())}:
        return 'value_qualified_grounded_ceramic_supply_terminal'
    return _manufacturer_supply_bridge(fp,pads)


def _source_address_roles(board, contracts, source_board, source_proposal, *, timeout_s,
                          track_uuid_scope=()):
    """Fresh source compilation, not a caller-authored list of allowed pads."""
    if source_board is None and source_proposal is None:
        return {}
    if (not isinstance(source_board, pcbnew.BOARD) or type(source_proposal) is not dict
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 10.
            or source_proposal.get('scope') != 'source_typed_complete_cell_escape_proposal'
            or type(source_proposal.get('poses')) is not dict
            or not 1 <= len(source_proposal['poses']) <= 8):
        raise ValueError('complete_source_address_prefix_context_required')
    import cec_cell_escape_replan as escape
    import cec_address_supply_obligations as address
    import cec_cell_row_rebuild as row
    import cec_decoupler_cell as cells
    import cec_force_current as force
    deadline = time.monotonic() + timeout_s
    def remaining():
        left = deadline - time.monotonic()
        if left <= 0:
            raise ValueError('source_address_prefix_context_deadline')
        return min(10., left)
    before = (row._source_binding(source_board), row._source_binding(board))
    fresh = escape.recompile_source_proposal(source_board,source_proposal)
    remaining()
    if fresh != source_proposal:
        raise ValueError('source_address_prefix_stale_or_forged_source_proposal')
    requests = address.requests(source_board, board, fresh, timeout_s=remaining())
    remaining()
    stable = lambda value: json.dumps(value, sort_keys=True, allow_nan=False)
    result = {}
    for request in requests.values():
        net = request['net']; received = contracts.get(net)
        expected = request['unchanged_full_rail_current_contract']
        with force._thermal_hint(fresh['board_hint']):
            live = cells._supply_current_widths(board, net)
        remaining()
        if (received is None or stable(live) != stable(expected)
                or stable(received.get('current_authority')) != stable(expected['current_authority'])
                or received.get('profile') != expected['profile']):
            raise ValueError('source_address_prefix_unchanged_current_contract_required')
        result[request['a']['pad_uuid']] = 'source_recompiled_same_package_supply_strapped_address'
    if track_uuid_scope:
        # A formerly connected Source address has a different mandatory
        # cut-to-throat restoration. Keep the unwired request API unchanged
        # and independently rederive that connected role from actual Source
        # copper, canonical pin/net identity and the literal retained throat.
        import cec_connected_address_supply_prefix as connected_prefix
        connected=connected_prefix.receiver_roles(source_board,board,fresh,contracts,
            track_uuid_scope=track_uuid_scope,timeout_s=remaining())
        if set(result)&set(connected):
            raise ValueError('connected_and_unwired_source_address_role_overlap')
        result.update(connected)
    if before != (row._source_binding(source_board), row._source_binding(board)):
        raise ValueError('source_address_prefix_context_mutated_native_source')
    remaining()
    return result


def receive(board, contracts, *, track_uuid_scope, retained_via_uuids=(),
            timeout_s=10., source_board=None, source_proposal=None):
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10. or not isinstance(contracts, dict)):
        raise ValueError('bounded_full_current_prefix_receiving_required')
    scope = set(track_uuid_scope)
    if not scope or len(scope) > 256:
        raise ValueError('finite_native_prefix_scope_required')
    deadline = time.monotonic() + timeout_s
    address_roles = _source_address_roles(board, contracts, source_board, source_proposal,
        timeout_s=max(.001, deadline-time.monotonic()),track_uuid_scope=scope)
    def terminal_role(pad):
        return supply_terminal_role(pad) or address_roles.get(pad.m_Uuid.AsString())
    group = next((g for g in board.Groups()
        if g.GetName() == fr.ENDPOINT_NECKDOWN_GROUP), None)
    report = dict(complete=True, track_uuids=[], proofs=[], refusals=[],
        scope_basis='exact_requested_native_class_prefix_delta',
        unscoped_grouped_copper_current_credited=False,
        current_budget_lowered=False, barrel_capacity_qualified=False,
        release_authority=False)
    if group is None:
        return report
    tracks = [t for t in board.GetTracks() if t.GetClass() == 'PCB_TRACK']
    grouped = [t for t in tracks if group.ContainsItem(t)]
    if len(grouped) > 4096:
        report.update(complete=False, refusals=['native_prefix_scope_exhausted'])
        return report
    planes = {board.GetLayerID(n) for n in fr.plane_layers(board)}
    enabled = set(board.GetEnabledLayers().CuStack())
    retained_via_uuids = set(retained_via_uuids)
    vias = [v for v in board.GetTracks() if v.GetClass() == 'PCB_VIA'
        and v.m_Uuid.AsString() in retained_via_uuids]
    pads = []
    for fp in board.GetFootprints():
        if fp.IsDNP():
            continue
        pads.extend(p for p in fp.Pads() if terminal_role(p) is not None)
    legal = set()
    for net, contract in sorted(contracts.items()):
        if time.monotonic() >= deadline:
            report.update(complete=False)
            report['refusals'].append('native_prefix_receiving_deadline')
            break
        authority = contract.get('current_authority') or {}
        positive = all(type(authority.get(k)) in (int, float)
            and math.isfinite(authority[k]) and authority[k] > 0
            for k in ('amps', 'geometry_margin'))
        profile = contract.get('profile')
        layers = tuple(contract.get('routing_layers') or ())
        if (not positive or type(authority.get('margin_included')) is not bool
                or not contract.get('authority_refs') or not layers
                or profile != fab.active_profile_name(board)
                or not set(layers) <= set(contract.get('required_by_layer_mm') or {})
                or any(board.GetLayerID(n) not in enabled - planes for n in layers)):
            report['refusals'].append(dict(net=net, reason='complete_source_current_authority_required'))
            continue
        floors = current_trace_widths(authority, layers, profile, rise_c=30.)
        floors = {board.GetLayerID(n): max(int(board.GetDesignSettings().m_TrackMinWidth),
            math.ceil(w * 1e6)) for n, w in floors.items()}
        required = {board.GetLayerID(n): math.ceil(
            contract['required_by_layer_mm'][n] * 1e6) for n in layers}
        if any(required[l] < floors[l] for l in floors):
            report['refusals'].append(dict(net=net, reason='class_contract_below_actual_current'))
            continue
        # The complete Source contract can list a non-plane PWR routing face
        # even when this exact new prefix is entirely on F/B or SIG2. Its
        # presence is not a prefix request on that protected face. Keep every
        # Source current/layer/floor binding above; restrict both actual new
        # prefixes AND their retained throats to the same permitted faces as
        # before. An unused PWR face must not poison an unrelated F prefix,
        # nor may it become a new cross-layer throat permission.
        permitted = {l: w for l, w in required.items()
            if not any(role in board.GetLayerName(l).upper() for role in ('GND', 'PWR'))}
        forbidden_scope = sorted(t.m_Uuid.AsString() for t in grouped
            if t.m_Uuid.AsString() in scope and t.GetNetname() == net
            and t.GetLayer() in required and t.GetLayer() not in permitted)
        if forbidden_scope:
            report['refusals'].append(dict(net=net,
                reason='actual_prefix_on_protected_routing_face_forbidden',
                track_uuids=forbidden_scope))
        for layer in sorted(permitted):
            # Re-prove the exact requested delta, not unrelated inherited
            # prefixes joined through its real supply land. A capacitor may
            # already have a narrower manufacturer-pin lead on the opposite
            # side. That lead is neither deleted nor current-credited here.
            # Qualification still demands the complete requested component,
            # a real typed supply pad, unchanged whole-source physics, the
            # original locality bound, and an actual full-width throat. An
            # omitted thin midspan leg cannot supply that throat. Saved
            # delta receiving independently derives ALL new narrow IDs.
            candidates = [t for t in grouped if t.m_Uuid.AsString() in scope
                and t.GetNetname() == net
                and t.GetLayer() == layer and t.GetWidth() < required[layer]]
            qualified, _ = fr._qualified_endpoint_neckdown_tracks(board,
                candidates, required[layer],
                required_clearance=int(board.GetDesignSettings().m_MinClearance))
            unseen = {t.m_Uuid.AsString(): t for t in qualified}
            while unseen:
                if time.monotonic() >= deadline:
                    report.update(complete=False)
                    report['refusals'].append('native_prefix_receiving_deadline')
                    return report
                first = unseen.pop(min(unseen)); component = [first]
                queue = [first]
                while queue:
                    t = queue.pop(); ends = {tuple(t.GetStart()), tuple(t.GetEnd())}
                    for uid, peer in list(unseen.items()):
                        if ends & {tuple(peer.GetStart()), tuple(peer.GetEnd())}:
                            component.append(peer); queue.append(peer); del unseen[uid]
                ids = {t.m_Uuid.AsString() for t in component}
                if not ids & scope or any(t.GetWidth() < floors[layer] for t in component):
                    continue
                degree = {}; points = {}
                for t in component:
                    for p in (t.GetStart(), t.GetEnd()):
                        key = tuple(p); degree[key] = degree.get(key, 0) + 1; points[key] = p
                boundary = [points[k] for k, d in degree.items() if d == 1]
                launch = [p for p in pads if p.GetNetname() == net and p.IsOnLayer(layer)
                    and min(p.GetSize()) < required[layer]
                    and any(p.GetEffectiveShape(layer).Collide(at, 0) for at in boundary)]
                if len(boundary) != 2 or not launch:
                    continue
                throats = [t for t in tracks if t.m_Uuid.AsString() not in ids
                    and t.GetNetname() == net and t.GetLayer() == layer
                    and t.GetWidth() >= required[layer]
                    and any(at in (t.GetStart(), t.GetEnd()) for at in boundary)]
                retained = []
                for v in vias:
                    if (v.GetNetname() != net or v.GetPosition() not in boundary
                            or not fr._profiled_pofv_full_width_throat(board, v, layer,
                                required[layer], tracks)):
                        continue
                    continuations = [t for t in tracks if t.GetNetname() == net
                        and t.GetLayer() in permitted and t.GetLayer() != layer
                        and t.GetWidth() >= permitted[t.GetLayer()]
                        and v.GetPosition() in (t.GetStart(), t.GetEnd())]
                    if continuations:
                        retained.append(v.m_Uuid.AsString()); throats.extend(continuations)
                if not throats:
                    continue
                legal.update(ids & scope)
                report['proofs'].append(dict(net=net, layer=board.GetLayerName(layer),
                    track_uuids=sorted(ids), actual_whole_current_floor_nm=floors[layer],
                    unchanged_class_width_nm=required[layer], current_authority=authority,
                    launch_pad_uuids=sorted(p.m_Uuid.AsString() for p in launch),
                    launch_terminal_roles={p.m_Uuid.AsString():terminal_role(p) for p in launch},
                    full_width_throat_uuids=sorted(t.m_Uuid.AsString() for t in throats),
                    source_retained_via_uuids=sorted(retained)))
    report['track_uuids'] = sorted(legal)
    return report
