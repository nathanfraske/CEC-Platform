"""Read-only, stable native power-terminal components, not airwire witnesses.

KiCad's ratsnest is a spanning tree. Its representative endpoint can change
when unrelated routing is added; it is not an inventory of stranded ICs.
This inventory reports actual supply/ground roles on fragmented power nets and
keeps isolated terminals distinct from multi-terminal islands. Measurement
inputs on a power-named net are not device supply pins. It does not infer
which island is energized, or grant current, Kelvin or release qualification.
"""
from collections import defaultdict
import math
import time

import pcbnew
import cec_device_bypass as bypass
import cec_device_power_roles as device_roles
import cec_pair_semantics as semantics


def _uid(item):
    return str(item.m_Uuid.AsString())


def power_name(net):
    name = net.upper()
    return name == 'GND' or any(p in name for p in
        ('+3V3', '+5VSB', '+5V', 'VBUS', 'VCC', 'VDD', '+3.3'))


def _ground_name(net):
    return net == 'GND' or net.endswith('/GND')


def _device_supply_pins(value, *, mpn=None, footprint=None):
    # Reuse the device contracts, not capacitor proximity or a board/refdes
    # exception. Both ends of a rail-to-rail bypass are actual supply pins.
    pins = {str(pin) for pin, *_ in bypass.requirements_for_value(
        value, mpn=mpn, footprint=footprint)}
    for supply, return_pin, *_ in bypass.rail_to_rail_requirements_for_value(value):
        pins.update((str(supply), str(return_pin)))
    return pins


def _device_measurement_pins(value, *, mpn=None, footprint=None):
    contract = semantics.current_input_contract(value, mpn=mpn, footprint=footprint)
    pins = set(contract[1]) if contract else set()
    auxiliary = semantics.current_auxiliary_input_contract(value)
    if auxiliary:
        for first, second, *_ in auxiliary[1]:
            pins.update((first, second))
    return pins


def terminal_role(net, pin, pin_type, supply_pins, measurement_pins=(), manufacturer=None):
    native_type = pin_type.strip().lower()
    if manufacturer and pin in manufacturer['pins']:
        role = manufacturer['pins'][pin]
        if role in ('power_input', 'power_output'):
            return 'supply', 'manufacturer_pin_function_table'
        if role == 'ground':
            return 'ground', 'manufacturer_pin_function_table'
        if role == 'reference' and _ground_name(net):
            return 'ground_reference', 'manufacturer_pin_function_table_and_declared_ground_net'
        return 'not_power', 'manufacturer_pin_function_table'
    if pin in measurement_pins:
        return 'not_power', 'selected_device_measurement_pin_contract'
    if native_type in ('input', 'output', 'bidirectional', 'tri_state',
                       'open_collector', 'open_emitter', 'no_connect'):
        return 'not_power', 'native_symbol_signal_pin_type'
    if _ground_name(net):
        return 'ground', 'native_ground_net'
    if pin in supply_pins:
        return 'supply', 'selected_device_supply_contract'
    if native_type in ('power_in', 'power_out'):
        return 'supply', 'native_symbol_pin_type'
    return 'unresolved', 'power_named_net_without_pin_role'


def inventory(board, *, timeout_s=10., max_items=32768):
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10 or type(max_items) is not int
            or not 1 <= max_items <= 32768):
        raise ValueError('invalid_power_inventory_bound')
    deadline = time.monotonic() + timeout_s
    metadata = {}
    pads = []
    all_net_pads = []
    pin_errors = []
    visited_pads = 0
    for fp in board.GetFootprints():
        if time.monotonic() >= deadline:
            raise ValueError('power_native_inventory_deadline')
        ref, value = str(fp.GetReference()), str(fp.GetValue())
        from cec_footprint_fields import footprint_properties
        mpn, footprint = footprint_properties(fp).get('MPN'), fp.GetFPIDAsString()
        supply_pins = _device_supply_pins(value, mpn=mpn, footprint=footprint)
        measurement_pins = _device_measurement_pins(value, mpn=mpn, footprint=footprint)
        manufacturer = device_roles.footprint_contract(fp)
        if manufacturer:
            supply_pins.update(pin for pin, role in manufacturer['pins'].items()
                if role in ('power_input', 'power_output'))
        ground_pins = {pin for pin, role in manufacturer['pins'].items()
            if role == 'ground'} if manufacturer else set()
        fp_pads = list(fp.Pads())
        ic = ref.startswith('U') or bool(supply_pins)
        if manufacturer:
            for domain in manufacturer['common_domains']:
                members = [p for p in fp_pads if str(p.GetNumber()) in domain['pins']]
                if (all(any(str(p.GetNumber()) == pin for p in members) for pin in domain['pins'])
                        and len({str(p.GetNetname()) for p in members}) > 1):
                    pin_errors.append(dict(ic=ref, pin='/'.join(domain['pins']), value=value,
                        reason='manufacturer_common_domain_net_mismatch',
                        domain=domain['name'], manufacturer_source=manufacturer['source']))
        for missing in sorted((supply_pins | ground_pins) - {str(p.GetNumber()) for p in fp_pads}):
            pin_errors.append(dict(ic=ref, pin=missing, value=value,
                reason='device_ground_pad_missing' if missing in ground_pins
                    else 'selected_device_supply_pad_missing'))
        for pad in fp_pads:
            visited_pads += 1
            if visited_pads > max_items:
                raise ValueError('power_native_inventory_bound')
            net, pin = str(pad.GetNetname()), str(pad.GetNumber())
            role, role_source = terminal_role(net, pin, str(pad.GetPinType()),
                supply_pins, measurement_pins, manufacturer)
            terminal = dict(uuid=_uid(pad), ref=ref, pin=pin, value=value,
                position_nm=[int(pad.GetPosition().x), int(pad.GetPosition().y)],
                pin_type=str(pad.GetPinType()), power_role=role,
                power_role_source=role_source, ic_terminal=ic)
            if manufacturer and pin in manufacturer['pins']:
                terminal.update(manufacturer_pin_role=manufacturer['pins'][pin],
                    manufacturer_source=manufacturer['source'])
            if role == 'supply' and (pad.GetNetCode() <= 0 or not net):
                pin_errors.append(dict(ic=ref, pin=pin, value=value,
                    uuid=_uid(pad), reason='device_supply_pad_unnetted'))
            if pin in supply_pins and _ground_name(net):
                pin_errors.append(dict(ic=ref, pin=pin, value=value,
                    uuid=_uid(pad), reason='selected_device_supply_pad_grounded'))
            if pin in ground_pins and (pad.GetNetCode() <= 0 or not net):
                pin_errors.append(dict(ic=ref, pin=pin, value=value,
                    uuid=_uid(pad), reason='device_ground_pad_unnetted'))
            if pad.GetNetCode() <= 0 or not net:
                continue
            all_net_pads.append(pad)
            metadata[_uid(pad)] = terminal
            if not (power_name(net) or _ground_name(net) or role in ('supply', 'ground')):
                continue
            pads.append(pad)
    names = {str(p.GetNetname()) for p in pads}
    # A renamed supply selected by its IC role still includes EVERY native
    # capacitor/header/resistor pad on that net. Selecting only recognized IC
    # pins would omit passive islands and misreport a connected IC as isolated.
    pads = [p for p in all_net_pads if str(p.GetNetname()) in names]
    unresolved = [dict(metadata[_uid(p)], net=str(p.GetNetname())) for p in pads
        if metadata[_uid(p)]['ic_terminal'] and metadata[_uid(p)]['power_role'] == 'unresolved']
    material = list(pads) + [t for t in board.GetTracks()
        if str(t.GetNetname()) in names] + [z for z in board.Zones()
        if not z.GetIsRuleArea() and str(z.GetNetname()) in names]
    if len(material) > max_items:
        raise ValueError('power_native_inventory_bound')
    identities = [_uid(i) for i in material]
    if len(set(identities)) != len(identities):
        raise ValueError('ambiguous_power_native_identity')
    conn = pcbnew.CONNECTIVITY_DATA()
    for item in material:
        if time.monotonic() >= deadline:
            raise ValueError('power_native_inventory_deadline')
        if not conn.Add(item):
            raise ValueError('power_native_item_refused')
    by_net = defaultdict(dict)
    for pad in pads:
        by_net[str(pad.GetNetname())][_uid(pad)] = pad
    nets = []
    for net, by_id in sorted(by_net.items()):
        remaining = set(by_id)
        components = []
        while remaining:
            if time.monotonic() >= deadline:
                raise ValueError('power_native_inventory_deadline')
            seed = min(remaining)
            reached = {seed} | {_uid(i) for i in conn.GetConnectedItems(by_id[seed])}
            members = sorted(remaining & reached)
            if not members:
                raise ValueError('power_native_empty_component')
            terminals = []
            for uid in members:
                terminals.append(metadata[uid])
            terminals.sort(key=lambda r: (r['ref'], r['pin'], r['uuid']))
            components.append(dict(pad_uuids=members, terminals=terminals,
                isolated_terminal=len(members) == 1,
                no_other_native_contacts=len(members) == 1 and reached == {seed}))
            remaining.difference_update(members)
        components.sort(key=lambda r: r['pad_uuids'])
        nets.append(dict(net=net, connected=len(components) == 1,
            component_count=len(components), components=components))
    return dict(schema=2, scope='native_power_terminal_partitions',
        complete=True, nets=nets, board_mutated=False,
        unresolved_ic_pin_roles=sorted(unresolved, key=lambda r: (r['ref'], r['pin'], r['uuid'])),
        supply_pin_contract_errors=sorted(pin_errors, key=lambda r: (r['ic'], r['pin'], r['reason'])),
        source_island_energization_inferred=False, current_authority=False,
        release_authority=False)


def fragmented_ics(report):
    if report.get('complete') is not True:
        raise ValueError('incomplete_power_terminal_inventory')
    rows = []
    for net in report['nets']:
        if net['connected']:
            continue
        for component in net['components']:
            for pad in component['terminals']:
                if pad['ic_terminal'] and pad['power_role'] in ('supply', 'ground', 'ground_reference'):
                    rows.append(dict(ic=pad['ref'], net=net['net'], pin=pad['pin'],
                        uuid=pad['uuid'], isolated_terminal=component['isolated_terminal'],
                        no_other_native_contacts=component['no_other_native_contacts'],
                        role=pad['power_role'], role_source=pad['power_role_source'],
                        component_pad_uuids=component['pad_uuids']))
    return sorted(rows, key=lambda r: (r['ic'], r['net'], r['pin'], r['uuid']))


def local_escape_ic_refs(directives):
    """Empty local work stays empty, never an implicit all-IC repair scope."""
    return sorted({row['ic'] for row in directives
        if (row.get('type') or row.get('directive')) == 'power_escape'
        and type(row.get('ic')) is str and row['ic']})
