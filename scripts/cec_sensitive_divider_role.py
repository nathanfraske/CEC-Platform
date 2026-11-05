"""Closed passive scalar-node evidence, never a rail or load reclassification.

A name such as VDD_ADC remains power-like AND sensitive in the field checker.
Only a closed native node with manufacturer-typed scalar GPIOs, a selected
top resistor to an actual source-owned power net, a selected ground resistor,
and optional selected shunt filters can support scalar geometry ownership.
No current, input mode, transfer accuracy or voltage qualification follows.
"""
import pcbnew
import cec_device_power_roles as roles
import cec_force_current as force
import cec_resistive_monitor_branch as resistive


def witness(board,net,*,power_nets):
    if (type(net) is not str or not net or type(power_nets) not in (set,frozenset)
            or any(type(n) is not str or not n for n in power_nets)):
        raise ValueError('actual_source_sensitive_divider_context_required')
    pads=[p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetCode()>0]
    if len(pads)>16384:raise ValueError('sensitive_divider_native_inventory_bound')
    node=[p for p in pads if p.GetNetname()==net]
    if net in power_nets or not 3<=len(node)<=6:return None
    gpios=[];uppers=[];lowers=[];filters=[];footprints=set()
    for pad in node:
        fp=pad.GetParentFootprint();uid=force._uid(fp)
        if (fp.IsDNP() or pad.HasHole() or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
                or pad.GetPinType() in ('power_in','power_out') or uid in footprints):return None
        footprints.add(uid)
        gpio=roles.scalar_gpio_pin(fp,str(pad.GetNumber()))
        if gpio:
            if sum(p.GetNumber()==pad.GetNumber() for p in fp.Pads())!=1:return None
            gpios.append(dict(pad_uuid=force._uid(pad),manufacturer_pin=gpio));continue
        resistor=resistive.resistor_contract(fp)
        if resistor:
            peers=[p for p in fp.Pads() if force._uid(p)!=force._uid(pad)]
            if len(peers)!=1:return None
            other=peers[0]
            row=dict(pad_uuid=force._uid(pad),opposite_pad_uuid=force._uid(other),
                opposite_net=str(other.GetNetname()),selected_resistor=resistor)
            if other.GetNetname()=='GND':lowers.append(row)
            elif other.GetNetname()!=net and other.GetNetname() in power_nets:uppers.append(row)
            else:return None
            continue
        passive=resistive._shunt_filter_contract(fp,pad)
        if passive:filters.append(dict(pad_uuid=force._uid(pad),selected_filter=passive));continue
        return None
    if not 1<=len(gpios)<=2 or len(uppers)!=1 or len(lowers)!=1 or len(filters)>2:return None
    return dict(net=net,kind='closed_manufacturer_gpio_and_selected_passive_divider',
        gpio_terminals=sorted(gpios,key=lambda q:q['pad_uuid']),top_resistor=uppers[0],
        ground_resistor=lowers[0],shunt_filters=sorted(filters,key=lambda q:q['pad_uuid']),
        every_native_node_terminal_accounted=True,field_power_and_victim_classification_changed=False,
        current_budget_voltage_or_input_mode_inferred=False,ordinary_reclassification=False,
        resistor_transfer_or_operating_qualification=False,release_authority=False)
