"""Source-canonical gate-bias resistor placement beside a STATIONARY MOSFET.

This is a placement-role/request compiler, not a MOS load or low-power IC
model.  The first bounded tier recognizes the complete selected AO3400A G/S/D
package and one rail-to-gate resistor, optionally with one stationary series
resistor on the gate.  Every old contact is an obligation, never a cut permit.
The rail keeps its existing WHOLE current contract.  No resistor load, switch
rating, nonload-width exception, routing success or release grade is inferred.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import time

import pcbnew
import cec_force_current as force
import cec_cell_row_rebuild as row
import cec_control_shunt_placement as shunt
import cec_source_ground_leaf as canonical
import cec_source_netlist_semantics as semantic
import cec_synth_pipeline as synth
from cec_footprint_fields import footprint_properties


ROLE = 'source_stationary_mos_gate_bias_passive'
MOS_SOURCE = 'https://www.aosmd.com/res/datasheets/AO3400A.pdf'
MOS_PDF = 'lib/datasheets/AO3400A.pdf'
MOS_PDF_SHA256 = '9c60d0b6c1ddc7609a4b788a91181468d8ffe6c3e9ba425c3d8ffc5ba88c5033'
MOS_PINS = {'1': {'name': 'G', 'type': 'input'},
            '2': {'name': 'S', 'type': 'passive'},
            '3': {'name': 'D', 'type': 'passive'}}


def _need(value, message):
    if not value:
        raise ValueError(message)


def _deadline(timeout_s):
    _need(type(timeout_s) in (int, float) and math.isfinite(timeout_s)
          and 0 < timeout_s <= 10., 'bounded_gate_bias_source_lease_required')
    return time.monotonic() + timeout_s


def _left(deadline):
    remaining = deadline - time.monotonic()
    _need(remaining > 0, 'gate_bias_source_deadline')
    return min(10., remaining)


def _wire(value):
    """Stable JSON-native identity, including after a saved proposal reload."""
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def _digest(value):
    return hashlib.sha256(json.dumps(_wire(value), sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def _flags():
    return dict(bypass_owner=False, current_authority=False, resistor_current_assumed=False,
        nonload_width_exception=False, source_trace_retirement_authority=False,
        new_barrel_authority=False, mos_motion_authority=False,
        switch_current_or_timing_qualified=False, power_or_thermal_qualified=False,
        routing_admitted=False, release_authority=False)


def _groups(board, item):
    uid = force._uid(item)
    return sorted((dict(uuid=force._uid(g), name=g.GetName(), locked=bool(g.IsLocked()),
                       members=sorted(force._uid(i) for i in g.GetItems()),
                       parent=force._uid(g.GetParentGroup()) if g.GetParentGroup() else None)
                  for g in board.Groups() if any(force._uid(i) == uid for i in g.GetItems())),
                  key=lambda v: v['uuid'])


def _pad(pad):
    import cec_source_current_pad_ports as ports
    return dict(identity=_wire(ports._pad_identity(pad)), locked=bool(pad.IsLocked()),
                drill_shape=int(pad.GetDrillShape()), layers=list(pad.GetLayerSet().Seq()))


def _footprint(board, fp):
    return dict(uuid=force._uid(fp), reference=fp.GetReference(), value=fp.GetValue(),
        fpid=fp.GetFPIDAsString(), fields=footprint_properties(fp),
        attributes=int(fp.GetAttributes()), dnp=bool(fp.IsDNP()), locked=bool(fp.IsLocked()),
        flipped=bool(fp.IsFlipped()), position_nm=list(fp.GetPosition()),
        angle_deg=float(fp.GetOrientationDegrees()), path=fp.GetPath().AsString(),
        groups=_groups(board, fp), pads={force._uid(p): _pad(p) for p in fp.Pads()})


def _track(board, item):
    kind = item.GetClass()
    _need(kind in ('PCB_TRACK', 'PCB_VIA', 'PCB_ARC'), 'known_gate_bias_native_copper_required')
    result = dict(uuid=force._uid(item), kind=kind, net=str(item.GetNetname()),
        locked=bool(item.IsLocked()), groups=_groups(board, item),
        layers=list(map(int, item.GetLayerSet().CuStack())))
    if kind == 'PCB_VIA':
        result.update(position_nm=list(item.GetPosition()),
            diameter_nm=int(item.GetWidth(item.TopLayer())), drill_nm=int(item.GetDrillValue()),
            via_type=int(item.GetViaType()), top=int(item.TopLayer()), bottom=int(item.BottomLayer()))
    else:
        result.update(start_nm=list(item.GetStart()), end_nm=list(item.GetEnd()),
            width_nm=int(item.GetWidth()), face=int(item.GetLayer()),
            solder_mask=bool(item.HasSolderMask()))
        if kind == 'PCB_ARC':
            result['mid_nm'] = list(item.GetMid())
    return result


def _smd(fp, count):
    pads = list(fp.Pads()); face = int(fp.GetLayer())
    _need(not fp.IsDNP() and face in (pcbnew.F_Cu, pcbnew.B_Cu)
          and len(pads) == count and len({p.GetNumber() for p in pads}) == count
          and len({tuple(p.GetPosition()) for p in pads}) == count
          and all(p.GetNumber() and p.GetNetCode() > 0 and p.GetNetname()
                  and not p.HasHole() and p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD
                  and tuple(p.GetLayerSet().CuStack()) == (face,)
                  and all(v > 0 for v in p.GetSize()) for p in pads),
          'complete_populated_single_surface_gate_bias_package_required')
    return pads


def _mos(fp):
    props = footprint_properties(fp)
    _need(props.get('MPN') == 'AO3400A' and fp.GetValue() == 'AO3400A'
          and props.get('Manufacturer') == 'Alpha & Omega Semiconductor'
          and fp.GetFPIDAsString().split(':')[-1] == 'SOT-23-3_L2.9-W1.3-P1.90-LS2.4-BR',
          'positive_selected_stationary_mos_manufacturer_package_required')
    pads = _smd(fp, 3)
    _need({p.GetNumber() for p in pads} == set(MOS_PINS)
          and len({p.GetNetname() for p in pads}) == 3
          and all(p.GetPinType() in ('', MOS_PINS[p.GetNumber()]['type'])
                  and p.GetPinFunction() in ('', MOS_PINS[p.GetNumber()]['name']) for p in pads),
          'complete_stationary_mos_G_S_D_native_identity_required')
    return dict(package='AO3400A SOT23', manufacturer=props['Manufacturer'], mpn=props['MPN'],
        source=MOS_SOURCE, selected_datasheet_path=MOS_PDF, selected_datasheet_sha256=MOS_PDF_SHA256,
        revision='Rev 3.1 July 2023', page=1, pins=copy.deepcopy(MOS_PINS), **_flags())


def _resistor(fp):
    import cec_resistive_monitor_branch as resistor
    props = footprint_properties(fp); selected = resistor.resistor_contract(fp)
    _need(selected is not None, 'positive_selected_gate_bias_resistor_required')
    manufacturer = props.get('Manufacturer')
    _need((str(props.get('MPN', '')).startswith('0402WGF') and manufacturer == 'UNI-ROYAL')
          or (str(props.get('MPN', '')).startswith('RT0402BRD07') and manufacturer == 'Yageo'),
          'positive_selected_gate_bias_resistor_manufacturer_required')
    _smd(fp, 2)
    # Deliberately carry identity/nominal resistance only.  The resistor
    # monitor's voltage-derived thin-branch current model is NOT this role.
    return dict(mpn=props['MPN'], manufacturer=manufacturer, value=fp.GetValue(),
        footprint=fp.GetFPIDAsString(), nominal_resistance_ohms=selected['nominal_ohms'],
        source=selected['source'], current_authority=False, resistor_current_assumed=False)


def _possible_owners(board, resistor):
    nets = {p.GetNetname() for p in resistor.Pads()}
    return [fp for fp in board.GetFootprints()
            if (footprint_properties(fp).get('MPN') == 'AO3400A' or fp.GetValue() == 'AO3400A')
            and fp.FindPadByNumber('1') is not None
            and fp.FindPadByNumber('1').GetNetname() in nets]


def _identity(board, fp, comps, instances, node_net, export_pins, deadline, *, model=None):
    actual = canonical._identity(board, fp.GetReference(), comps, instances, deadline)
    blocks = [b for tag, b in actual[2].children if tag == 'symbol'
              and canonical.sch.prop_value(b, 'Reference') == fp.GetReference()]
    exported = {synth._val(p, 'name', ''): synth._val(p, 'value', '')
                for p in synth._kids(comps[fp.GetReference()], 'property')}
    props = footprint_properties(fp)
    _need(len(blocks) == 1 and props.get('Manufacturer')
          and canonical.sch.prop_value(blocks[0], 'Manufacturer') == props['Manufacturer']
          and exported.get('Manufacturer') == props['Manufacturer'],
          'gate_bias_complete_canonical_manufacturer_parity_required')
    libraries = [b for tag, b in actual[2].children if tag == 'lib_symbols']
    _need(len(libraries) == 1, 'gate_bias_complete_embedded_library_required')
    symbols = [n for n in synth._kids(synth.parse_sexpr(libraries[0]), 'symbol')
               if len(n) > 1 and n[1] == actual[3]['lib_id']]
    _need(len(symbols) == 1 and synth._first(symbols[0], 'extends') is None,
          'gate_bias_unique_complete_embedded_symbol_required')
    pending = [symbols[0]]; pins = {}; count = 0
    while pending:
        _left(deadline); item = pending.pop(); count += 1
        _need(count <= 8192, 'gate_bias_embedded_symbol_bound')
        if isinstance(item, list) and item:
            if item[0] == 'pin':
                number = synth._val(item, 'number', '')
                _need(number and number not in pins and len(item) > 1,
                      'gate_bias_unique_embedded_pin_required')
                pins[number] = dict(type=item[1], name=synth._val(item, 'name', ''))
            pending.extend(v for v in item if isinstance(v, list))
    pads = list(fp.Pads())
    _need(set(pins) == {p.GetNumber() for p in pads}
          and len(pins) == len(pads) == len(actual[3]['pins']),
          'gate_bias_complete_canonical_pin_table_required')
    resistor_part = synth._val(synth._first(comps[fp.GetReference()], 'libsource'), 'part', '')
    if model is None:
        _need(resistor_part in ('R', 'R_Small') and all(v['type'] == 'passive' for v in pins.values()),
              'gate_bias_complete_canonical_passive_resistor_required')
    else:
        _need(pins == model['pins'], 'gate_bias_exact_manufacturer_G_S_D_source_map_required')
    for pad in pads:
        _left(deadline); pin = pins[pad.GetNumber()]
        exported_pin = export_pins.get((fp.GetReference(), pad.GetNumber()), {})
        # KiCad 10.0.5 makeListOfNets emits baseName + '_' + the SAME pin
        # number, including named G/S/D.  Match the two exact export forms;
        # never strip suffixes, normalize functions, or alter native metadata.
        # Primary implementation, lines 1176-1203:
        # https://github.com/KiCad/kicad-source-mirror/blob/10.0.5/eeschema/netlist_exporters/netlist_exporter_xml.cpp#L1176-L1203
        names = (pin['name'], pin['name'] + '_' + pad.GetNumber())
        if model is None and pin['name'] == '~':
            # The old absent pinfunction allowance remains ONLY for a
            # canonical anonymous passive R/R_Small, never a named MOS pin.
            names = ('', '~')
            if (resistor_part in ('R', 'R_Small')
                    and pin['type'] == exported_pin.get('type') == 'passive'):
                names += ('~_' + pad.GetNumber(),)
        _need(canonical._pin(actual, pad.GetNumber())['type'] == pin['type'] and pin['name']
              and pad.GetPinFunction() in ('', pin['name']) and pad.GetPinType() in ('', pin['type'])
              and exported_pin.get('type') == pin['type'] and exported_pin.get('name') in names
              and node_net.get((fp.GetReference(), pad.GetNumber())) == pad.GetNetname(),
              'gate_bias_complete_native_embedded_export_pin_or_net_mismatch:' + json.dumps(dict(
                  reference=fp.GetReference(), pin=pad.GetNumber(), pad_uuid=force._uid(pad),
                  native=dict(name=pad.GetPinFunction(), type=pad.GetPinType(), net=pad.GetNetname()),
                  embedded=pin, exported=dict(exported_pin,
                      net=node_net.get((fp.GetReference(), pad.GetNumber())))), sort_keys=True))
    return dict(reference=fp.GetReference(), footprint_uuid=force._uid(fp),
        symbol_uuid=actual[3]['uuid'], lib_id=actual[3]['lib_id'],
        fields=props, pins={n: dict(v, net=node_net[(fp.GetReference(), n)]) for n, v in pins.items()})


def _stationary_series_identity(board, fp, comps, instances, node_net, export_pins, deadline):
    """Canonical passive ID only, NOT the monitor's resistance/current model.

    Unlike the moving bias, this peer grants no placement or conductor
    authority: its entire native footprint and both contact sets stay fixed.
    MPN/value/manufacturer/package are freshly Source-bound, not decoded into
    a resistance tolerance, voltage, temperature or switched-load budget.
    """
    import cec_control_pullup_placement as pullup
    pads = _smd(fp, 2)
    _need(fp.GetFPIDAsString().split(':')[-1] == 'R_0402_1005Metric'
          and {p.GetNumber() for p in pads} == {'1', '2'},
          'gate_bias_stationary_series_two_land_resistor_package_required')
    identity = _identity(board, fp, comps, instances, node_net, export_pins, deadline)
    nominal = pullup._ohms(fp.GetValue())
    _need(nominal is not None, 'gate_bias_stationary_series_positive_Source_resistance_required')
    identity.update(source_only=True, identity_only=True,
        source_declared_resistance_ohms=nominal, manufacturer_resistance_model_applied=False,
        current_authority=False, resistor_current_assumed=False,
        power_or_thermal_qualified=False, voltage_qualified=False,
        resistance_or_power_qualification=False, source_trace_retirement_authority=False,
        placement_authority=False, routing_admitted=False, release_authority=False)
    return identity


def _rail(board, net, hint):
    import cec_decoupler_cell as cell
    with force._thermal_hint(hint):
        contract = cell._supply_current_widths(board, net)
    widths = contract.get('required_by_layer_nm') if isinstance(contract, dict) else None
    authority = contract.get('current_authority') if isinstance(contract, dict) else None
    _need(isinstance(widths, dict) and set(widths) == set(map(int, board.GetEnabledLayers().CuStack()))
          and all(type(v) is int and v > 0 for v in widths.values())
          and isinstance(authority, dict) and contract.get('profile')
          and all(type(authority.get(k)) in (int, float) and math.isfinite(authority[k])
                  and authority[k] > 0 for k in ('amps', 'geometry_margin'))
          and type(authority.get('margin_included')) is bool,
          'unchanged_complete_gate_bias_aggregate_supply_current_contract_required')
    return _wire(contract)


def _direct_contacts(board, pad, deadline):
    """All actual direct contacts, not bbox proximity or a chosen nearest port."""
    import cec_pad_incident_tracks as incident
    import cec_native_fill_geometry as fill
    result = []
    observed = incident.inspect(board, [pad])
    _need(observed['ok'], 'gate_bias_native_contact_inventory_refused')
    by_id = {force._uid(t): t for t in board.GetTracks()}
    for contact in observed['contacts']:
        result.append(dict(kind='PCB_TRACK', item_uuid=contact['track_uuid'],
            contact=contact, material=_track(board, by_id[contact['track_uuid']]),
            port=dict(native_uuids=[contact['track_uuid']], at_nm=contact['contact_nm'],
                      layers=[contact['layer']])))
    for contact in observed['native_barrel_contacts']:
        result.append(dict(kind='PCB_VIA', item_uuid=contact['via_uuid'],
            contact=contact, material=_track(board, by_id[contact['via_uuid']]),
            port=dict(native_uuids=[contact['via_uuid']], at_nm=contact['contact_nm'],
                      layers=[contact['layer']])))
    all_pads = [p for f in board.GetFootprints() for p in f.Pads()]
    _need(len(all_pads) + len(by_id) + len(list(board.Zones())) <= 16384,
          'gate_bias_native_inventory_bound')
    for layer in pad.GetLayerSet().CuStack():
        shape = pad.GetEffectiveShape(layer)
        for item in [*all_pads, *by_id.values()]:
            _left(deadline)
            if force._uid(item) == force._uid(pad) or not item.IsOnLayer(layer):
                continue
            if not shape.BBox().Intersects(item.GetEffectiveShape(layer).BBox()):
                continue
            if not shape.Collide(item.GetEffectiveShape(layer), 0):
                continue
            _need(item.GetNetname() == pad.GetNetname(), 'gate_bias_Source_terminal_has_foreign_copper_contact')
            if item.GetClass() == 'PAD':
                result.append(dict(kind='PAD', item_uuid=force._uid(item), material=_pad(item),
                    port=dict(pad_uuid=force._uid(item), at_nm=list(item.GetPosition()), layers=[int(layer)])))
            elif item.GetClass() == 'PCB_ARC':
                raise ValueError('gate_bias_terminal_arc_contact_not_supported')
            else:
                _need(any(r['item_uuid'] == force._uid(item) for r in result),
                      'gate_bias_uninventoried_actual_native_contact')
        for zone in board.Zones():
            _left(deadline)
            if zone.GetIsRuleArea() or not zone.IsOnLayer(layer):
                continue
            filled = zone.GetFilledPolysList(layer)
            if not filled.OutlineCount() or not filled.BBox().Intersects(shape.BBox()):
                continue
            metal = pcbnew.SHAPE_POLY_SET()
            pad.TransformShapeToPolygon(metal, layer, 0, 1, pcbnew.ERROR_INSIDE, False)
            clipped = filled.CloneDropTriangulation(); clipped.BooleanIntersection(metal)
            if not clipped.OutlineCount():
                continue
            _need(zone.GetNetname() == pad.GetNetname(), 'gate_bias_Source_terminal_has_foreign_fill_contact')
            result.append(dict(kind='ZONE', item_uuid=force._uid(zone), material=dict(
                net=zone.GetNetname(), layer=int(layer), locked=bool(zone.IsLocked()),
                outline=zone.Outline().Format(), groups=_groups(board, zone),
                actual_pad_contact_sha256=fill.identity(clipped, deadline)[0])))
    _need(len(result) <= 32, 'bounded_complete_gate_bias_terminal_contacts_required')
    return sorted(_wire(result), key=lambda v: (v['kind'], v['item_uuid'], repr(v.get('port'))))


def _gate_components(board, net, deadline):
    items = [p for f in board.GetFootprints() for p in f.Pads() if p.GetNetname() == net]
    items += [t for t in board.GetTracks() if t.GetNetname() == net]
    _need(2 <= len(items) <= 4096 and len({force._uid(i) for i in items}) == len(items)
          and not any(not z.GetIsRuleArea() and z.GetNetname() == net for z in board.Zones()),
          'bounded_unaliased_nonpour_gate_native_component_required')
    graph = pcbnew.CONNECTIVITY_DATA()
    for item in items:
        _left(deadline)
        _need(graph.Add(item), 'gate_bias_private_native_graph_refused')
    remaining = {force._uid(i): i for i in items}; components = []
    while remaining:
        _left(deadline); uid = min(remaining)
        reached = {uid} | {force._uid(i) for i in graph.GetConnectedItems(remaining[uid])}
        _need(reached <= {force._uid(i) for i in items}, 'gate_bias_native_component_unknown_member')
        members = sorted(set(remaining) & reached)
        _need(members, 'gate_bias_empty_native_component')
        components.append(members)
        for member in members:
            del remaining[member]
    return dict(net=net, components=sorted(components), material={force._uid(i):
        (_pad(i) if i.GetClass() == 'PAD' else _track(board, i)) for i in items},
        native_net_propagation_performed=False, restoration_received=False)


def _pose(fp, poses):
    value = poses[fp.GetReference()]
    _need(type(value) in (list, tuple) and len(value) == 3
          and all(type(v) in (int, float) and math.isfinite(v) for v in value)
          and all(abs(v) <= 2000 for v in value[:2])
          and (value[2] - fp.GetOrientationDegrees()) % 90 == 0,
          'finite_cardinal_gate_bias_resistor_pose_required')
    return list(value)


def _stationary(fp, poses):
    if fp.GetReference() in poses:
        value = _pose(fp, poses)
        _need(tuple(round(v * 1e6) for v in value[:2]) == tuple(fp.GetPosition())
              and (value[2] - fp.GetOrientationDegrees()) % 360 == 0,
              'gate_bias_MOS_and_series_peer_must_remain_stationary')


def _compile(board, source, poses, selected, hint, deadline, reference_group_uuids):
    import cec_decoupler_cell as cell
    import cec_ordinary_route_receiving as ordinary
    source = Path(source).resolve(strict=True)
    _need(source.suffix == '.kicad_pcb' and Path(board.GetFileName()).resolve() == source
          and source.with_suffix('.kicad_pro').is_file(), 'exact_saved_gate_bias_Source_and_project_required')
    before = row._source_binding(board); epoch = force._code_identity(); family = force._family(source, hint)
    saved = pcbnew.LoadBoard(str(source))
    _need(saved is not None and before == row._source_binding(saved),
          'gate_bias_native_board_must_equal_saved_Source')
    _left(deadline)
    authorized = shunt._reference_group_authorizations(board, poses, reference_group_uuids,
        binding=before, deadline=deadline)
    root = canonical.source_nc._root(board, hint)
    _need(root is not None, 'gate_bias_canonical_Source_required')
    root = Path(root).resolve(strict=True)
    files, hashes, instances = canonical._hierarchy(root, deadline)
    tree, exporter = canonical._export(root, deadline)
    _need(Path(exporter.get('exporter', '')).is_file()
          and force._hash(Path(exporter['exporter'])) == exporter.get('exporter_sha256')
          and all(exporter.get(k) == v for k, v in semantic.metadata(tree).items()),
          'gate_bias_fresh_complete_semantic_exporter_required')
    comps, nets, node_net = canonical._tables(tree)
    export_pins = {(synth._val(node, 'ref', ''), synth._val(node, 'pin', '')):
                  dict(name=synth._val(node, 'pinfunction', ''), type=synth._val(node, 'pintype', ''))
                  for net in synth._kids(synth._first(tree, 'nets'), 'net')
                  for node in synth._kids(net, 'node')}
    datasheet = Path(__file__).resolve().parents[1] / MOS_PDF
    _need(datasheet.is_file() and force._hash(datasheet) == MOS_PDF_SHA256,
          'reviewed_gate_bias_manufacturer_source_file_changed')
    base = semantic.replay_identity(dict(root_schematic=str(root), schematic_files_sha256=hashes,
                                        exporter=exporter, evidence_files_sha256={str(datasheet): MOS_PDF_SHA256}))
    ordinary_nets = ordinary.eligible_nets(board, source, hint)
    result = {}
    for resistor in selected:
        _left(deadline); ref = resistor.GetReference(); target = _pose(resistor, poses)
        resistor_model = _resistor(resistor); owners = _possible_owners(board, resistor)
        _need(len(owners) == 1, 'unique_selected_gate_bias_MOS_owner_required')
        owner = owners[0]; mos = _mos(owner); _stationary(owner, poses)
        gate = owner.FindPadByNumber('1'); supply = [p for p in resistor.Pads() if p.GetNetname() != gate.GetNetname()]
        _need(len(supply) == 1, 'distinct_gate_bias_rail_and_gate_required')
        supply = supply[0]; signal = next(p for p in resistor.Pads() if force._uid(p) != force._uid(supply))
        _need(supply.GetNetname() != 'GND' and supply.GetNetname() not in {p.GetNetname() for p in owner.Pads()}
              and signal.GetNetname() == gate.GetNetname() and gate.GetNetname() in ordinary_nets,
              'gate_bias_distinct_rated_nonGround_rail_and_positive_ordinary_gate_required')
        groups = {force._uid(i) for g in board.Groups() for i in g.GetItems()}
        _need(not resistor.IsLocked() and not resistor.IsDNP()
              and (force._uid(resistor) not in groups and not resistor.GetParentGroup()
                   or force._uid(resistor) in authorized)
              and all(not p.IsLocked() and force._uid(p) not in groups for p in resistor.Pads()),
              'unlocked_populated_ungrouped_or_exact_mapped_gate_bias_required')
        identities = {ref: _identity(board, resistor, comps, instances, node_net, export_pins, deadline),
            owner.GetReference(): _identity(board, owner, comps, instances, node_net, export_pins, deadline, model=mos)}
        peers = [p for f in board.GetFootprints() for p in f.Pads() if p.GetNetname() == gate.GetNetname()]
        _need(len(peers) in (2, 3) and len({(p.GetParentFootprint().GetReference(), p.GetNumber()) for p in peers}) == len(peers)
              and nets.get(gate.GetNetname()) == {(p.GetParentFootprint().GetReference(), p.GetNumber()) for p in peers},
              'complete_unique_canonical_gate_bias_peer_inventory_required')
        extra = [p for p in peers if force._uid(p) not in (force._uid(gate), force._uid(signal))]
        stationary = [owner]; series_contacts = {}
        if extra:
            peer = extra[0].GetParentFootprint(); _stationary(peer, poses)
            identities[peer.GetReference()] = _stationary_series_identity(
                board, peer, comps, instances, node_net, export_pins, deadline)
            far = next(p for p in peer.Pads() if force._uid(p) != force._uid(extra[0]))
            _need(far.GetNetname() != supply.GetNetname()
                  and far.GetNetname() not in {p.GetNetname() for p in owner.Pads()}
                  and far.GetNetname() in ordinary_nets,
                  'one_stationary_canonical_series_resistor_not_second_bias_required')
            series_contacts = {force._uid(p): _direct_contacts(board, p, deadline) for p in peer.Pads()}
            stationary.append(peer)
        rail_members = {(f.GetReference(), p.GetNumber()) for f in board.GetFootprints()
                        for p in f.Pads() if p.GetNetname() == supply.GetNetname()}
        _need(nets.get(supply.GetNetname()) == rail_members,
              'gate_bias_complete_canonical_supply_membership_required')
        rail = _rail(board, supply.GetNetname(), hint)
        direct = {force._uid(p): _direct_contacts(board, p, deadline) for p in (supply, signal)}
        # The initial movable tier is trace-fed only.  Inventory first, then
        # refuse unsupported direct pad/barrel/fill ownership explicitly.
        _need(all(v and all(r['kind'] == 'PCB_TRACK' for r in v) for v in direct.values()),
              'gate_bias_movable_terminals_require_complete_trace_only_contacts')
        ds = {force._uid(p): _direct_contacts(board, p, deadline)
              for p in owner.Pads() if p.GetNumber() in ('2', '3')}
        item = dict(role=ROLE, resistor_uuid=force._uid(resistor),
            signal_pad_uuid=force._uid(signal), supply_pad_uuid=force._uid(supply),
            control_pad_uuid=force._uid(gate), control_owner_uuid=force._uid(owner),
            control_owner=owner.GetReference(), control_pin='1',
            signal_net=str(gate.GetNetname()), supply_net=str(supply.GetNetname()),
            source_resistor=resistor_model, nominal_resistance_ohms=resistor_model['nominal_resistance_ohms'],
            target_pose=target, source_proof=dict(base, selected_components=identities, manufacturer=mos),
            source_native_binding=before, source_code_identity=epoch, source_family=family,
            source_resistor_identity=_footprint(board, resistor),
            stationary_components={force._uid(f): _footprint(board, f) for f in stationary},
            stationary_series_contacts=series_contacts,
            stationary_MOS_drain_source_contacts=ds, source_terminal_contacts=direct,
            source_gate_components=_gate_components(board, gate.GetNetname(), deadline),
            source_gate_peer_pad_uuids=sorted(force._uid(p) for p in peers),
            source_supply_logical_members=sorted(rail_members),
            unchanged_full_rail_current_contract=rail,
            source_dimensions={n: cell._netclass(board, n) for n in (supply.GetNetname(), gate.GetNetname())},
            all_source_contacts_are_mandatory=True, **_flags())
        if force._uid(resistor) in authorized:
            item['source_reference_group_authorization'] = authorized[force._uid(resistor)]
        result[ref] = _wire(item)
    _left(deadline)
    _need(before == row._source_binding(board) and epoch == force._code_identity()
          and family == force._family(source, hint)
          and hashes == {str(p): force._hash(p) for p in files}
          and force._hash(datasheet) == MOS_PDF_SHA256
          and force._hash(Path(exporter['exporter'])) == exporter['exporter_sha256'],
          'gate_bias_Source_family_canonical_or_code_changed')
    _left(deadline)
    return result


def plan(board, poses, *, board_hint, timeout_s=10., reference_group_uuids=()):
    """Ref-keyed positive role scopes; unrelated posed cells return {} cheaply."""
    deadline = _deadline(timeout_s)
    _need(type(poses) is dict and 1 <= len(poses) <= 8 and type(board_hint) is str and board_hint,
          'bounded_gate_bias_pose_context_required')
    shunt._reference_group_scope(reference_group_uuids)
    selected = [f for f in board.GetFootprints() if f.GetReference() in poses
                and len(list(f.Pads())) == 2 and _possible_owners(board, f)]
    if not selected:
        return {}
    _need(len({f.GetReference() for f in selected}) == len(selected), 'unique_gate_bias_resistor_reference_required')
    return _compile(board, board.GetFileName(), poses, selected, board_hint, deadline, reference_group_uuids)


def source_contract(board, source, *, resistor_uuid, board_hint, timeout_s=10., reference_group_uuids=()):
    """Explicit Source identity API; no caller MOS/current/net/coordinate model."""
    deadline = _deadline(timeout_s)
    _need(type(resistor_uuid) is str and resistor_uuid and type(board_hint) is str and board_hint,
          'explicit_gate_bias_Source_resistor_identity_required')
    selected = [f for f in board.GetFootprints() if force._uid(f) == resistor_uuid]
    _need(len(selected) == 1, 'unique_gate_bias_Source_resistor_required')
    fp = selected[0]
    poses = {fp.GetReference(): [fp.GetPosition().x / 1e6, fp.GetPosition().y / 1e6, fp.GetOrientationDegrees()]}
    return _compile(board, source, poses, selected, board_hint, deadline,
                    reference_group_uuids)[fp.GetReference()]


def requests(source, board, proposal, *, timeout_s=10.):
    """Mandatory projected-frame demands, NOT completed restoration evidence.

    A target names an actual original conductor.  If another positive owner
    retires that conductor, complete-component composition must replace this
    exact obligation.  No omission/skip list or caller-provided current is used.
    """
    deadline = _deadline(timeout_s)
    selected = proposal.get('selected_control_gate_biases', {})
    if not selected:
        return {}
    _need(type(selected) is dict, 'gate_bias_selected_proof_mapping_required')
    projected_binding = row._source_binding(board)
    fresh = plan(source, proposal['poses'], board_hint=proposal['board_hint'], timeout_s=_left(deadline),
                 reference_group_uuids=proposal.get('reference_group_uuids', ()))
    _need(fresh == selected, 'fresh_exact_gate_bias_Source_proposal_required')
    import cec_decoupler_cell as cell
    pads = {force._uid(p): p for f in board.GetFootprints() for p in f.Pads()}
    old = {force._uid(p): p for f in source.GetFootprints() for p in f.Pads()}
    result = {}
    for ref, item in selected.items():
        _left(deadline)
        _need(all(u in pads and u in old for u in (item['signal_pad_uuid'], item['supply_pad_uuid'], item['control_pad_uuid'])),
              'complete_projected_gate_bias_lands_required')
        first = old[item['signal_pad_uuid']].GetParentFootprint()
        resistor = pads[item['signal_pad_uuid']].GetParentFootprint()
        expected = pcbnew.FOOTPRINT(first)
        expected.SetPosition(pcbnew.VECTOR2I(*(round(v * 1e6) for v in item['target_pose'][:2])))
        expected.SetOrientationDegrees(item['target_pose'][2])
        _need(force._uid(resistor) == force._uid(first) and resistor.GetReference() == ref
              and resistor.GetFPIDAsString() == first.GetFPIDAsString()
              and footprint_properties(resistor) == footprint_properties(first)
              and resistor.GetValue() == first.GetValue() and resistor.GetAttributes() == first.GetAttributes()
              and resistor.IsDNP() == first.IsDNP() and resistor.IsLocked() == first.IsLocked()
              and resistor.IsFlipped() == first.IsFlipped()
              and tuple(resistor.GetPosition()) == tuple(expected.GetPosition())
              and (resistor.GetOrientationDegrees() - expected.GetOrientationDegrees()) % 360 == 0
              and {force._uid(p): _pad(p) for p in resistor.Pads()} == {force._uid(p): _pad(p) for p in expected.Pads()},
              'gate_bias_projected_resistor_exact_rigid_Source_identity_required')
        mapping = item.get('source_reference_group_authorization')
        _need(_groups(board, resistor) == _groups(source, first), 'gate_bias_projected_group_members_or_lock_changed')
        if mapping is None:
            _need(not resistor.GetParentGroup(), 'gate_bias_projected_arbitrary_group_refused')
        # The complete saved pose receiver owns exact moved map ink.  This
        # role still checks actual membership/locks, never grants ungrouping.
        for uid, identity in item['stationary_components'].items():
            owners = [f for f in board.GetFootprints() if force._uid(f) == uid]
            _need(len(owners) == 1 and _wire(_footprint(board, owners[0])) == identity,
                  'gate_bias_stationary_MOS_or_series_component_changed')
        for uid, contacts in item['stationary_MOS_drain_source_contacts'].items():
            _need(uid in pads and _direct_contacts(board, pads[uid], deadline) == contacts,
                  'gate_bias_stationary_drain_source_material_or_contact_changed')
        for uid, contacts in item['stationary_series_contacts'].items():
            _need(uid in pads and _direct_contacts(board, pads[uid], deadline) == contacts,
                  'gate_bias_stationary_series_material_or_contact_changed')
        rail = _rail(source, item['supply_net'], proposal['board_hint'])
        _need(rail == item['unchanged_full_rail_current_contract'], 'gate_bias_Source_current_contract_changed')
        for net in (item['signal_net'], item['supply_net']):
            _need(_wire(cell._netclass(source, net)) == item['source_dimensions'][net]
                  and cell._netclass(source, net) == cell._netclass(board, net)
                  and source.GetDesignSettings().m_TrackMinWidth == board.GetDesignSettings().m_TrackMinWidth,
                  'gate_bias_source_class_and_factory_floor_must_remain_exact')
        for role, uid in (('gate_bias_signal', item['signal_pad_uuid']), ('gate_bias_supply', item['supply_pad_uuid'])):
            pad = pads[uid]; net = str(pad.GetNetname())
            width = max(int(board.GetDesignSettings().m_TrackMinWidth), int(cell._netclass(source, net)['width']))
            if role == 'gate_bias_supply':
                width = max(width, *rail['required_by_layer_nm'].values())
            _need(width > 0, 'positive_full_Source_gate_bias_width_required')
            ends = [('source_contact:' + r['item_uuid'], r['port'], r['contact'])
                    for r in item['source_terminal_contacts'][uid]]
            if role == 'gate_bias_signal':
                control = pads[item['control_pad_uuid']]
                ends.append(('stationary_gate', dict(pad_uuid=force._uid(control), at_nm=list(control.GetPosition()),
                                                     layers=list(map(int, control.GetLayerSet().CuStack()))), None))
            for suffix, target, contact in ends:
                key = 'control_gate_bias:' + uid + ':' + suffix
                _need(key not in result, 'unique_complete_gate_bias_contact_request_required')
                request = dict(kind='source_boundary', role=role, net=net,
                    a=dict(pad_uuid=uid, at_nm=list(pad.GetPosition()), layers=list(map(int, pad.GetLayerSet().CuStack()))),
                    b=copy.deepcopy(target), width_nm=width,
                    clearance_nm=int(cell._netclass(source, net)['clearance']),
                    source_control_gate_bias=item, all_source_contacts_are_mandatory=True,
                    no_source_trace_retirement_authority=True, new_barrel_authority=False,
                    class_only_supply_prefix_authority=False, no_power_bypass_or_current_authority=True)
                if role == 'gate_bias_supply':
                    request['unchanged_full_rail_current_contract'] = rail
                if contact is not None:
                    request['source_pad_track_contact'] = copy.deepcopy(contact)
                result[key] = request
    # Fresh planning is not enough if later native contact work crossed an
    # epoch/family change.  This covers the complete request constituent.
    for item in selected.values():
        proof = item['source_proof']; exporter = proof['exporter']
        _need(row._source_binding(source) == item['source_native_binding']
              and force._code_identity() == item['source_code_identity']
              and force._family(Path(source.GetFileName()), proposal['board_hint']) == item['source_family']
              and all(force._hash(Path(p)) == digest for p, digest in
                      {**proof['schematic_files_sha256'], **proof['evidence_files_sha256']}.items())
              and force._hash(Path(exporter['exporter'])) == exporter['exporter_sha256']
              and row._source_binding(board) == projected_binding,
              'gate_bias_requests_live_Source_or_projected_identity_changed')
    _left(deadline)
    return result
