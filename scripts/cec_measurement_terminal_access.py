"""Source-native route demands for isolated manufacturer measurement inputs.

A force-net name must not suppress its nonload sense-terminal routing demand.
Targets come from the unique schematic input/series/shunt topology, never the
DRC zone origin, nearest whole-net island, or a guessed Kelvin pickup. This
module discovers proposals only; native contact, branch-current, field, pair,
Kelvin and saved-board receiving remain mandatory.
"""
import math
import time
import pcbnew
import cec_device_power_roles as roles
import cec_force_current as force
import cec_fr as fr
import cec_current_topology as current
import cec_sense_topology as sense
import cec_cell_row_rebuild as row


def _input_island(root, connected, model, *, deadline):
    """Positively typed stranded package copper, never a whole-net retarget.

    This only inventories an additive demand. Source branches are retained;
    the saved receiver still has to prove their complete native partitions.
    A rail pin, external land, barrel, zone or untyped contact refuses it.
    """
    if not 1<=len(connected)<=24:return None
    owner=force._uid(root.GetParentFootprint());layer=next(iter(root.GetLayerSet().CuStack()))
    ids=[]
    for item in connected:
        if time.monotonic()>=deadline:raise ValueError('measurement_terminal_inventory_deadline')
        if item.GetNetCode()!=root.GetNetCode():return None
        if item.GetClass()=='PAD':
            if (force._uid(item.GetParentFootprint())!=owner or item.HasHole()
                    or item.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
                    or list(item.GetLayerSet().CuStack())!=[layer]
                    or model['pins'].get(item.GetNumber())!='measurement'):return None
        elif item.GetClass()=='PCB_TRACK':
            a,b=tuple(item.GetStart()),tuple(item.GetEnd())
            if (item.GetLayer()!=layer or not 0<item.GetWidth()<=350000 or a==b
                    or a[0]!=b[0] and a[1]!=b[1] and abs(a[0]-b[0])!=abs(a[1]-b[1])):return None
        else:return None
        ids.append(force._uid(item))
    if len(set(ids))!=len(ids):return None
    # GetConnectedItems' track/pad graph does not expose every native zone
    # contact. Receive the actual saved filled copper separately; otherwise
    # a stranded-looking stub could already be a force/pour pickup.
    zones=[z for z in root.GetBoard().Zones() if not z.GetIsRuleArea()
        and z.GetNetCode()==root.GetNetCode() and z.IsOnLayer(layer)]
    if len(zones)>4096:return None
    for z in zones:
        for item in connected:
            if time.monotonic()>=deadline:raise ValueError('measurement_terminal_inventory_deadline')
            shape=item.GetEffectiveShape(layer)
            native=z.GetFilledPolysList(layer) if z.IsFilled() else z.Outline()
            if native.Collide(shape,0):return None
    return sorted(ids)


def requests(board, *, board_hint, timeout_s=3., max_requests=64, allow_partial_inputs=False):
    if (type(board_hint) is not str or not board_hint
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10 or type(max_requests) is not int
            or not 1<=max_requests<=64 or type(allow_partial_inputs) is not bool):
        raise ValueError('bounded_source_measurement_terminal_inventory_required')
    deadline=time.monotonic()+timeout_s;binding=row._source_binding(board)
    with force._thermal_hint(board_hint):
        domains=current.board_current_domains(board,board_hint)
    anchors={ref for d in domains.values() if d.get('complete') is True
        for ref in d.get('authority_refs',())}
    lineage=sense.board_evidence(board,anchor_pairs=(),anchor_refs=anchors)
    graph=fr._read_only_route_connectivity(board);rows=[];refusals=[]
    def terminal(endpoint,net):
        fp=board.FindFootprintByReference(endpoint['ref'])
        pads=[] if fp is None else [p for p in fp.Pads() if p.GetNumber()==endpoint['pad']]
        if fp is None or fp.IsDNP() or len(pads)!=1 or pads[0].GetNetname()!=net:
            raise ValueError('unique_live_schematic_measurement_terminal_required')
        return pads[0]
    for proof in lineage['details']:
        if time.monotonic()>=deadline:raise ValueError('measurement_terminal_inventory_deadline')
        if proof.get('ok') is not True:
            refusals.append(dict(owner=proof['ref'],reason='source_input_topology_not_unique'));continue
        owner=board.FindFootprintByReference(proof['ref']);model=roles.footprint_contract(owner)
        if owner.IsDNP() or not model:
            refusals.append(dict(owner=proof['ref'],reason='manufacturer_input_role_unknown'));continue
        for segment in sense.placement_segments(proof):
            if segment['start']['ref']!=proof['ref']:continue
            net=segment['net'];root=terminal(segment['start'],net);target=terminal(segment['end'],net)
            if (model['pins'].get(root.GetNumber())!='measurement' or root.HasHole()
                    or root.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
                    or len(list(root.GetLayerSet().CuStack()))!=1):
                refusals.append(dict(pad_uuid=force._uid(root),reason='typed_single_surface_measurement_land_required'));continue
            connected={force._uid(i):i for i in [root,*graph.GetConnectedItems(root)]}
            island=None
            if set(connected)!={force._uid(root)}:
                if not allow_partial_inputs:continue
                island=_input_island(root,list(connected.values()),model,deadline=deadline)
                if island is None:
                    refusals.append(dict(pad_uuid=force._uid(root),reason='source_contact_not_stranded_typed_package_input'));continue
            if domains.get(net,{}).get('complete') is not True:
                refusals.append(dict(pad_uuid=force._uid(root),reason='complete_current_domain_missing'));continue
            if len(rows)>=max_requests:raise ValueError('measurement_terminal_request_bound')
            rows.append(dict(pad_uuid=force._uid(root),target_uuid=force._uid(target),net=net,
                a_nm=list(root.GetPosition()),b_nm=list(target.GetPosition()),
                source_layer_ids=list(map(int,root.GetLayerSet().CuStack())),
                target_layer_ids=[int(l) for l in board.GetEnabledLayers().CuStack() if target.IsOnLayer(l)],
                owner_uuid=force._uid(owner),input_pin=root.GetNumber(),manufacturer_source=model['source'],
                source_topology=proof['selected'],source_segment=segment,
                source_input_island_uuids=island or [force._uid(root)],
                preserved_source_prefix=bool(island),
                current_capacity_qualified=False,kelvin_qualified=False,release_authority=False))
    if row._source_binding(board)!=binding:
        raise ValueError('measurement_terminal_inventory_mutated_native_source')
    if time.monotonic()>=deadline:raise ValueError('measurement_terminal_inventory_deadline')
    return dict(schema=1,requests=rows,refusals=refusals,source_binding=binding,
        no_path_proof=False,retirement_authority=False,current_authority=False,
        release_authority=False,independent_saved_current_field_and_kelvin_receiving_required=True)
