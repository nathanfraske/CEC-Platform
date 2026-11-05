"""Source-current local web on real saved via contacts, not hypothetical faces.

The local web proxy is NOT a plated-barrel ampacity/thermal calculation. A
thin unused inner routing layer cannot impose its horizontal track width on
an outer-to-outer transition. Conversely, any actual inner contact reinstates
that layer's full unchanged current/width obligation. No trace, clearance,
factory, branch-sharing, current-budget or release exemption is granted.
"""
import copy
import math
import time

import pcbnew
import cec_fab_profile as fab
import cec_force_current as force


def receive(board, via_uuid, contract, *, timeout_s=2.):
    if (type(via_uuid) is not str or not via_uuid or not isinstance(contract, dict)
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10.):
        raise ValueError('bounded_source_native_supply_via_context_required')
    deadline = time.monotonic()+timeout_s
    authority = contract.get('current_authority') or {}
    if (any(type(authority.get(k)) not in (int,float) or not math.isfinite(authority[k])
            or authority[k] <= 0 for k in ('amps','geometry_margin'))
            or type(authority.get('margin_included')) is not bool
            or authority['margin_included'] and authority['geometry_margin'] != 1.):
        raise ValueError('unchanged_positive_source_current_contract_required')
    if contract.get('net') not in (None, '') and type(contract['net']) is not str:
        raise ValueError('exact_native_supply_via_net_required')
    native = [*(p for fp in board.GetFootprints() for p in fp.Pads()),*board.GetTracks(),
        *[z for z in board.Zones() if not z.GetIsRuleArea()]]
    if len(native) > 16384:
        raise ValueError('native_supply_via_contact_inventory_bound')
    vias = [t for t in board.GetTracks() if force._uid(t) == via_uuid]
    if (len(vias) != 1 or vias[0].GetClass() != 'PCB_VIA'
            or vias[0].GetViaType() != pcbnew.VIATYPE_THROUGH):
        raise ValueError('exact_saved_native_through_supply_via_required')
    via = vias[0]; net = str(via.GetNetname()); code = via.GetNetCode()
    if code <= 0 or contract.get('net') != net:
        raise ValueError('unchanged_native_supply_via_net_contract_required')
    enabled = tuple(map(int, board.GetEnabledLayers().CuStack()))
    floors = contract.get('required_by_layer_mm') or {}
    names = {fab.COPPER_LAYER_IDS[l] for l in enabled}
    if (set(floors) != names or any(type(w) not in (int,float)
            or not math.isfinite(w) or w <= 0 for w in floors.values())
            or not all(via.IsOnLayer(l) for l in enabled)
            or int(via.TopLayer()) != pcbnew.F_Cu or int(via.BottomLayer()) != pcbnew.B_Cu):
        raise ValueError('complete_source_layer_widths_and_native_span_required')
    own = [i for i in native if i.GetNetCode() == code and force._uid(i) != via_uuid]
    if len(own) > 4096:
        raise ValueError('native_supply_via_same_net_inventory_bound')
    contacts = {}
    for layer in enabled:
        shape = via.GetEffectiveShape(layer); found = []
        for item in own:
            if time.monotonic() >= deadline:
                raise ValueError('native_supply_via_contact_deadline')
            if not item.IsOnLayer(layer): continue
            if item.GetClass() == 'ZONE':
                if not item.IsFilled():
                    raise ValueError('saved_native_supply_zone_fill_required')
                if not item.HasFilledPolysForLayer(layer): continue
                other = item.GetFilledPolysList(layer)
            else:
                other = item.GetEffectiveShape(layer)
            if other.Collide(shape,0):
                found.append(dict(uuid=force._uid(item),kind=item.GetClass()))
        if found: contacts[fab.COPPER_LAYER_IDS[layer]] = found
    if len(contacts) < 2:
        raise ValueError('two_real_native_supply_contact_faces_required')
    if not set(contacts) <= set(contract.get('routing_layers') or ()):
        raise ValueError('native_supply_contact_outside_authorized_routing_layers')
    required = {n:math.ceil(floors[n]*1e6) for n in contacts}
    drill = int(via.GetDrillValue())
    rows = [dict(layer=n,diameter_nm=int(via.GetWidth(board.GetLayerID(n))),
        drill_nm=drill,required_full_local_web_nm=required[n]) for n in contacts]
    ok = all(0 < r['drill_nm'] < r['diameter_nm']
        and r['diameter_nm']-r['drill_nm'] >= r['required_full_local_web_nm'] for r in rows)
    return dict(schema=1,scope='actual_saved_native_supply_contact_local_web_only',
        ok=ok,complete=True,via_uuid=via_uuid,net=net,actual_native_contacts=contacts,
        actual_contact_layers=sorted(contacts),source_width_by_contact_layer_nm=required,
        source_required_local_web_nm=max(required.values()),native_dimensions=rows,
        unchanged_source_current_authority=copy.deepcopy(authority),
        unused_copper_layers_not_assumed_to_carry_current=sorted(names-set(contacts)),
        board_mutated=False,trace_width_obligation_changed=False,
        branch_sharing_assumed=False,plated_barrel_current_qualified=False,
        electrical_or_thermal_qualified=False,release_authority=False)
