"""Complete Source-canonical unassigned ceramic/aggregate-supply cell.

An actual exported C/C_Small, unchanged selected part and an existing complete
aggregate rail contract own this operation. It is not a selected IC bypass,
load allocation, barrel rating, copper cut, power-pour edit or release gate.
Only a bounded translation and its exact closed Source reference map move.
Every Source track, barrel, other footprint and opaque companion stays fixed.
The saved receiver independently recompiles the expected frame and proves
the full-rail feed, a Source-owned local supply path and immediate physical
Ground return. Unassigned is not permission to export a local rail capacitor.
"""
import copy
import json
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_constraints as constraints
import cec_decoupler_cell as cells
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_fab_profile as fab
import cec_full_current_planar_reflow as full
import cec_full_current_supply_prefix as supply_role
import cec_ground_return_preservation as returns
import cec_ground_return_shortcut as reference
import cec_native_partition_pair as partitions
import cec_native_supply_via_context as web
import cec_protector_cell as placement
import cec_route_quality as craft
import cec_source_current_ports as ports
import cec_source_ground_leaf as leaf
import cec_source_literal_additions as literal
import cec_source_literal_footprint_retention as footprints
import cec_source_netlist_semantics as semantics
import cec_source_mount_stitch_reconcile as mounts
import cec_source_reference_group_transport as maps
import cec_source_retaining_ses_import as source_text
from cec_footprint_fields import footprint_properties


SCOPE = 'Source_canonical_unassigned_ceramic_aggregate_cell-v1'
# A relocation may cross a board without requiring a long new conductor.
# Keep this finite construction bound aligned with the existing literal-map
# transport bound; the default local radius and every electrical/placement
# receiver remain unchanged. This is not a clearance or route-length waiver.
MAX_SHIFT_MM = escape.MAX_EXPLICIT_AGGREGATE_CAP_SHIFT_MM
MAX_NEW_TRACKS = 16
MAX_NEW_VIAS = 2
MAX_NEW_LENGTH_NM = 32000000
MAX_LOCAL_RETURN_MM = .8


def _need(ok, reason):
    if not ok:
        raise ValueError(reason)


def _deadline(seconds):
    _need(type(seconds) in (int, float) and math.isfinite(seconds) and 0 < seconds <= 10.,
        'bounded_aggregate_capacitor_constituent_required')
    return time.monotonic() + seconds


def _left(deadline):
    left = deadline-time.monotonic()
    _need(left > 0, 'aggregate_capacitor_constituent_deadline')
    return min(10., left)


def _stable(value):
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def _request(footprint_uuid, target_pose, reference_group_uuid, max_shift_mm, supply_contact):
    _need(type(footprint_uuid) is str and bool(footprint_uuid)
        and type(target_pose) in (list, tuple) and len(target_pose) == 3
        and all(type(v) in (int, float) and math.isfinite(v) for v in target_pose)
        and type(max_shift_mm) in (int, float) and math.isfinite(max_shift_mm)
        and 0 < max_shift_mm <= MAX_SHIFT_MM
        and (reference_group_uuid is None or type(reference_group_uuid) is str and bool(reference_group_uuid)),
        'exact_bounded_aggregate_capacitor_pose_required')
    pose = [round(v*1e6)/1e6 for v in target_pose[:2]] + [target_pose[2] % 360]
    if supply_contact is not None:
        _need(type(supply_contact) is dict and set(supply_contact) == {'native_uuids', 'at_nm', 'layers'}
            and type(supply_contact['native_uuids']) is list and len(supply_contact['native_uuids']) == 1
            and all(type(u) is str and u for u in supply_contact['native_uuids'])
            and type(supply_contact['at_nm']) is list and len(supply_contact['at_nm']) == 2
            and all(type(v) is int and abs(v) <= 1000000000 for v in supply_contact['at_nm'])
            and type(supply_contact['layers']) is list and len(supply_contact['layers']) == 1
            and type(supply_contact['layers'][0]) is int,
            'one_literal_retained_aggregate_carrier_contact_required')
    return _stable(dict(footprint_uuid=footprint_uuid, target_pose=pose,
        reference_group_uuid=reference_group_uuid, max_shift_mm=max_shift_mm,
        supply_contact=supply_contact))


def _owner(board, uid, group_uid, source):
    owners = [f for f in board.GetFootprints() if force._uid(f) == uid]
    _need(len(owners) == 1, 'unique_native_aggregate_capacitor_required')
    fp = owners[0]; pads = list(fp.Pads()); face = int(fp.GetLayer())
    _need(not fp.IsLocked() and leaf._ceramic(fp) and face in (pcbnew.F_Cu, pcbnew.B_Cu)
        and len({p.GetNetname() for p in pads}) == 2
        and sum(p.GetNetname() == 'GND' for p in pads) == 1
        and all(p.GetNetCode() > 0 and not p.IsLocked() and not p.GetParentGroup()
            and tuple(map(int, p.GetLayerSet().CuStack())) == (face,)
            and p.GetPinType() in ('', 'passive') for p in pads)
        and not list(fp.Zones()), 'populated_unlocked_grounded_ceramic_surface_cell_required')
    groups = {force._uid(g) for g in board.Groups() if g.ContainsItem(fp)}
    _need(groups == ({group_uid} if group_uid is not None else set()),
        'exact_closed_Source_capacitor_reference_owner_required')
    children = [*pads, *fp.GraphicalItems(), *fp.GetFields()]
    grouped_children = {force._uid(i) for g in board.Groups() for i in g.GetItems()}
    _need(not {force._uid(i) for i in children} & grouped_children,
        'no_independently_grouped_capacitor_child_may_move')
    # Native loading can omit a group member that names a nested pad/field.
    # Its literal Source ownership is still real and must not disappear just
    # because GetItems()/GetParentGroup() cannot resolve that child.
    inventory, *_ = literal._inventory(source_text.raw_text(source))
    child_ids = {force._uid(i) for i in children}
    literal_owners = set()
    for group, (_, _, node) in inventory.items():
        if source_text.kind(node) != 'group': continue
        _, members, _ = literal._members(node)
        _need(not child_ids.intersection(members),
            'literal_Source_capacitor_child_group_ownership_refused')
        if uid in members: literal_owners.add(group)
    _need(literal_owners == groups, 'literal_and_native_capacitor_group_ownership_must_match')
    _need(not any(int(g.GetLayer()) in {*map(int, board.GetEnabledLayers().CuStack()), int(pcbnew.Edge_Cuts)}
        for g in [*fp.GraphicalItems(), *fp.GetFields()]),
        'aggregate_capacitor_cannot_move_copper_artwork_or_edges')
    _need(not pads[0].GetEffectiveShape(face).Collide(pads[1].GetEffectiveShape(face), 0),
        'aggregate_capacitor_source_lands_overlap')
    return fp


def _canonical(board, fp, hint, deadline):
    root = leaf.source_nc._root(board, hint)
    _need(root is not None, 'canonical_aggregate_capacitor_hierarchy_required')
    root = root.resolve(); files, hashes, instances = leaf._hierarchy(root, deadline)
    tree, exporter = leaf._export(root, deadline); comps, nets, node_net = leaf._tables(tree)
    identity = leaf._identity(board, fp.GetReference(), comps, instances, deadline)
    _, path, sheet, symbol = identity; component = comps[fp.GetReference()]
    kind = leaf.synth._val(leaf.synth._first(component, 'libsource'), 'part', '')
    _need(kind in ('C', 'C_Small'), 'canonical_two_passive_pin_capacitor_symbol_required')
    libraries = [b for tag, b in sheet.children if tag == 'lib_symbols']
    _need(len(libraries) == 1, 'complete_capacitor_embedded_symbol_required')
    library = leaf.synth.parse_sexpr(libraries[0])
    selected = [s for s in leaf.synth._kids(library, 'symbol') if len(s) > 1 and s[1] == symbol['lib_id']]
    _need(len(selected) == 1 and leaf.synth._first(selected[0], 'extends') is None,
        'complete_capacitor_embedded_symbol_required')
    todo = [selected[0]]; pins = []; count = 0
    while todo:
        _left(deadline); node = todo.pop(); count += 1
        _need(count <= 4096, 'bounded_capacitor_source_symbol_required')
        if isinstance(node, list) and node:
            if node[0] == 'pin': pins.append(node)
            todo.extend(n for n in node if isinstance(n, list))
    _need(len(pins) == 2 and {leaf.synth._val(p, 'number', '') for p in pins}
        == {p.GetNumber() for p in fp.Pads()} and all(p[1] == 'passive' for p in pins),
        'complete_both_passive_capacitor_source_pins_required')
    blocks = [b for tag, b in sheet.children if tag == 'symbol'
        and leaf.sch.prop_value(b, 'Reference') == fp.GetReference()]
    properties = footprint_properties(fp)
    exported = {leaf.synth._val(p, 'name', ''): leaf.synth._val(p, 'value', '')
        for p in leaf.synth._kids(component, 'property')}
    _need(len(blocks) == 1, 'unique_capacitor_source_instance_required')
    for key in ('MPN', 'Manufacturer', 'LCSC'):
        _need(bool(properties.get(key)) and leaf.sch.prop_value(blocks[0], key) == properties[key]
            and exported.get(key) == properties[key], 'capacitor_selected_Source_field_mismatch:' + key)
    records = []; membership = {}
    for pad in sorted(fp.Pads(), key=lambda p: p.GetNumber()):
        _left(deadline); pin = pad.GetNumber(); net = str(pad.GetNetname())
        _need(leaf._pin(identity, pin)['type'] == 'passive'
            and node_net.get((fp.GetReference(), pin)) == net,
            'capacitor_original_source_pin_net_required')
        native = {(f.GetReference(), p.GetNumber()) for f in board.GetFootprints()
            for p in f.Pads() if p.GetNetname() == net}
        exported_members = nets.get(net, set())
        virtual = []; mechanical = None
        if net == 'GND':
            ground = leaf.complete_ground_membership(board, exported_members, comps, instances,
                board_hint=hint, deadline=deadline)
            virtual = ground['nonphysical_canonical_Ground_symbols']
            mechanical = ground['unchanged_PCB_only_canonical_Ground_mounts']
        else:
            _need(native == exported_members, 'capacitor_complete_Source_net_membership_required')
        membership[net] = dict(native_logical_members=sorted(native),
            canonical_logical_members=sorted(exported_members),
            nonphysical_canonical_Ground_symbols=virtual,
            unchanged_PCB_only_canonical_Ground_mounts=mechanical)
        records.append(dict(uuid=force._uid(pad), pin=pin, net=net, source_type='passive'))
    locality = _source_locality(board, fp, comps, nets, node_net, instances, deadline)
    _need(hashes == {str(p): force._hash(p) for p in files}, 'capacitor_Source_hierarchy_changed')
    return semantics.replay_identity(dict(root=str(root), files_sha256=hashes, exporter=exporter,
        sheet=str(path), symbol_uuid=symbol['uuid'], symbol_kind=kind,
        selected_fields={k: properties[k] for k in ('MPN', 'Manufacturer', 'LCSC')},
        pins=records, complete_net_membership=membership, locality_owner=locality))


def _source_locality(board, fp, comps, nets, node_net, instances, deadline):
    """Positive exact Source supply owner, separate from minimum matching.

    Every parallel ceramic is local to this owner. Free text cannot make an
    exception, select an ambiguous common-rail IC or authorize remote bulk.
    """
    import cec_device_bypass as bypass
    import cec_device_power_roles as roles
    rail=next(p.GetNetname() for p in fp.Pads() if p.GetNetname()!='GND')
    inventory=constraints._device_bypass_assignment(board,project_max_mm=3.5)
    candidates={}
    for req in inventory['requirements']:
        _left(deadline)
        if req['rail']!=rail or req.get('return_rail','GND')!='GND':continue
        key=(req['ref'],str(req['pin']))
        candidates.setdefault(key,[]).append(req)
    declared=bypass.declared_owner(footprint_properties(fp))
    if declared is not None:
        candidates={k:v for k,v in candidates.items() if k[0]==declared[0] and (not declared[1]or k[1]==declared[1])}
    _need(len(candidates)==1,'unique_positive_Source_capacitor_locality_owner_required')
    (ref,pin),requirements=next(iter(candidates.items()))
    owners=[f for f in board.GetFootprints() if f.GetReference()==ref]
    _need(len(owners)==1 and ref!=fp.GetReference(),'unique_native_locality_owner_required')
    owner=owners[0];model=roles.footprint_contract(owner)
    _need(not owner.IsDNP() and model and model['pins'].get(pin)in('power_input','power_output')
        and {p.GetNumber()for p in owner.Pads()}==set(model['pins'])
        and len(list(owner.Pads()))==len(model['pins']),
        'complete_manufacturer_capacitor_supply_owner_required')
    identity=leaf._identity(board,ref,comps,instances,deadline)
    import cec_quiet_signal_requests as source_pins
    source_pin=source_pins._source_pin(identity,pin,deadline)
    owner_pad=owner.FindPadByNumber(pin)
    _need(source_pin['type']in('power_in','power_out') and node_net.get((ref,pin))==rail
        and owner_pad is not None and owner_pad.GetNetname()==rail,
        'canonical_locality_owner_supply_pin_required')
    props=footprint_properties(owner)
    blocks=[b for tag,b in identity[2].children if tag=='symbol'and leaf.sch.prop_value(b,'Reference')==ref]
    exported={leaf.synth._val(p,'name',''):leaf.synth._val(p,'value','') for p in leaf.synth._kids(comps[ref],'property')}
    _need(len(blocks)==1,'unique_locality_owner_Source_instance_required')
    for key in ('MPN','Manufacturer'):
        _need(props.get(key) and leaf.sch.prop_value(blocks[0],key)==props[key]
            and exported.get(key)==props[key],'locality_owner_selected_Source_field_mismatch:'+key)
    cap_component=comps[fp.GetReference()]
    cap_exported={leaf.synth._val(p,'name',''):leaf.synth._val(p,'value','')for p in leaf.synth._kids(cap_component,'property')}
    # A different sheet is valid; locate the capacitor's actual Source instance.
    cap_identity=leaf._identity(board,fp.GetReference(),comps,instances,deadline)
    cap_blocks=[b for tag,b in cap_identity[2].children if tag=='symbol'and leaf.sch.prop_value(b,'Reference')==fp.GetReference()]
    _need(len(cap_blocks)==1,'unique_local_capacitor_Source_instance_required')
    cap_props=footprint_properties(fp)
    for key in ('BypassOwner','Note'):
        value=cap_props.get(key,'') or ''
        _need((leaf.sch.prop_value(cap_blocks[0],key)or '')==value and (cap_exported.get(key,'')or '')==value,
            'capacitor_locality_Source_declaration_mismatch:'+key)
    limits=[r['max_mm']for r in requirements]
    _need(all(type(x)in(int,float)and math.isfinite(x)and 0<x<=3.5 for x in limits),
        'existing_positive_capacitor_locality_bound_required')
    face=cells.cec_return_escape.smd_surface_layer(owner_pad)
    positive=next(p for p in fp.Pads()if p.GetNetname()==rail)
    _need(face is not None and cells.cec_return_escape.smd_surface_layer(positive)==face,
        'same_Source_surface_locality_owner_required')
    return dict(owner_uuid=force._uid(owner),owner_ref=ref,pin=pin,pad_uuid=force._uid(owner_pad),
        rail=rail,return_rail='GND',face=int(face),maximum_distance_mm=min(limits),
        maximum_supply_path_mm=min(limits),manufacturer_source=model['source'],source_pin=source_pin,
        source_declarations={k:cap_props.get(k,'')or ''for k in ('BypassOwner','Note')},
        free_text_is_not_routing_or_locality_authority=True,
        parallel_capacitors_do_not_replace_existing_minimum_assignment=True)


def _unassigned(board, fp, hint):
    with force._thermal_hint(hint):
        assigned = constraints._device_bypass_assignment(board, project_max_mm=3.5)
    import cec_device_bypass as bypass
    _need(bypass.declared_owner(footprint_properties(fp)) is None,
        'explicitly_declared_bypass_owner_cannot_be_reclassified')
    _need(not any(r['cap_ref'] == fp.GetReference() for r in assigned['assigned'].values()),
        'selected_manufacturer_bypass_needs_its_complete_owner_cell')
    rail = next(p.GetNetname() for p in fp.Pads() if p.GetNetname() != 'GND')
    _need(not any(r['rail'] == rail for r in assigned['missing']),
        'unresolved_same_rail_bypass_intent_cannot_be_reclassified')
    return {key: r['cap_ref'] for key, r in assigned['assigned'].items()}


def _contact(inventory, requested, toward):
    if requested is None:
        candidates = [*inventory['root_ports'],
            *[ports.stroke_port(s, toward) for s in inventory['retained_full_width_strokes']]]
        _need(bool(candidates), 'actual_retained_full_current_capacitor_port_required')
        return min(candidates, key=lambda p: (math.dist(p['at_nm'], toward), repr(p)))
    found = [s for s in inventory['retained_full_width_strokes']
        if s['native_uuid'] == requested['native_uuids'][0]]
    _need(len(found) == 1 and requested['layers'] == [found[0]['layer_id']],
        'requested_carrier_must_be_in_actual_rated_Source_component')
    s = found[0]; a, b = s['start_nm'], s['end_nm']; at = requested['at_nm']
    dx, dy = b[0]-a[0], b[1]-a[1]
    _need((at[0]-a[0])*dy == (at[1]-a[1])*dx
        and min(a[0], b[0]) <= at[0] <= max(a[0], b[0])
        and min(a[1], b[1]) <= at[1] <= max(a[1], b[1]),
        'literal_carrier_centreline_contact_required')
    return copy.deepcopy(requested)


def compile(source, *, footprint_uuid, target_pose, board_hint, reference_group_uuid=None,
            max_shift_mm=6., supply_contact=None, timeout_s=10.):
    deadline = _deadline(timeout_s)
    request = _request(footprint_uuid, target_pose, reference_group_uuid, max_shift_mm, supply_contact)
    _need(type(board_hint) is str and bool(board_hint), 'named_aggregate_capacitor_Source_required')
    source = Path(source).resolve(strict=True)
    _need(source.suffix == '.kicad_pcb', 'saved_aggregate_capacitor_Source_required')
    epoch = force._code_identity(); family = force._family(source, board_hint)
    board = pcbnew.LoadBoard(str(source)); binding = row._source_binding(board)
    fp = _owner(board, footprint_uuid, reference_group_uuid, source)
    original = [fp.GetPosition().x/1e6, fp.GetPosition().y/1e6, fp.GetOrientationDegrees()]
    target = request['target_pose']
    _need((target[2]-original[2]) % 360 == 0 and original[:2] != target[:2]
        and math.dist(original[:2], target[:2]) <= max_shift_mm,
        'bounded_nonzero_capacitor_translation_only')
    canonical = _canonical(board, fp, board_hint, deadline)
    assignments = _unassigned(board, fp, board_hint)
    positive = next(p for p in fp.Pads() if p.GetNetname() != 'GND')
    ground = next(p for p in fp.Pads() if p.GetNetname() == 'GND')
    _need(supply_role.supply_terminal_role(positive) == 'value_qualified_grounded_ceramic_supply_terminal',
        'canonical_grounded_ceramic_supply_role_required')
    graph = fr._read_only_route_connectivity(board)
    _need(not {force._uid(i) for i in graph.GetConnectedItems(positive)}-{force._uid(positive)},
        'isolated_Source_capacitor_supply_land_required')
    kind, domain, contract = full._model(board, source, str(positive.GetNetname()), board_hint)
    _need(kind == 'aggregate_source_sink' and domain is not None and domain.get('complete') is True
        and domain.get('source_refs') and domain.get('sink_refs')
        and fp.GetReference() not in domain['source_refs'],
        'unchanged_complete_aggregate_supply_not_a_capacitor_source_required')
    inventory = ports.aggregate_ports(board, source, str(positive.GetNetname()), domain, contract, deadline)
    with force._thermal_hint(board_hint): current = cells._supply_current_widths(board, str(positive.GetNetname()))
    _need(current is not None and current['current_authority'] == contract['current_authority'],
        'unchanged_whole_rail_capacitor_supply_contract_required')
    delta = tuple(round((target[k]-original[k])*1e6) for k in (0, 1))
    reference_proof = None
    if reference_group_uuid is not None:
        reference_proof, = maps.inspect_many(source, [(footprint_uuid, reference_group_uuid)], timeout_s=_left(deadline))
        maps.transform_many(board, [(reference_proof, delta)], maximum_translation_mm=max_shift_mm)
    else:
        fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in target[:2])))
    _need(_unassigned(board, fp, board_hint) == assignments,
        'all_existing_manufacturer_bypass_assignments_must_remain_exact')
    locality=canonical['locality_owner']
    locality_pad=next(p for f in board.GetFootprints()for p in f.Pads()if force._uid(p)==locality['pad_uuid'])
    _need(math.dist(tuple(positive.GetPosition()),tuple(locality_pad.GetPosition()))
        <= locality['maximum_distance_mm']*1e6,'target_capacitor_must_remain_local_to_Source_owner')
    supply_port = _contact(inventory, supply_contact, tuple(positive.GetPosition()))
    face = int(fp.GetLayer())
    width = full._source_width_floor(board, source, contract, face)
    web_contract = copy.deepcopy(contract)
    layer_ids = {name: lid for lid, name in fab.COPPER_LAYER_IDS.items()}
    for name in web_contract['routing_layers']:
        _need(name in layer_ids, 'known_Source_supply_routing_face_required')
        lid = layer_ids[name]
        web_contract['required_by_layer_mm'][name] = full._source_width_floor(board, source, contract, lid)/1e6
    feed = dict(kind='source_boundary', net=str(positive.GetNetname()), a=ports.port(positive),
        b=supply_port, width_nm=width, unchanged_full_rail_current_contract=current,
        every_surviving_source_component_port_mandatory=True)
    result = _stable(dict(schema=1, scope=SCOPE, source=str(source), source_sha256=force._hash(source),
        source_family=family, code_identity=epoch, source_native_binding=binding, board_hint=board_hint,
        request=request, owner_ref=fp.GetReference(), source_pose=original, canonical_source=canonical,
        unchanged_selected_bypass_assignments=assignments,source_locality_owner=locality,
        source_reference_map=reference_proof, delta_nm=list(delta), supply_pad_uuid=force._uid(positive),
        ground_pad_uuid=force._uid(ground), aggregate_domain=domain, aggregate_contract=contract,
        native_supply_contact_contract=web_contract, supply_inventory=inventory,
        supply_request=feed, ground_width_nm=max(200000, int(board.GetDesignSettings().m_TrackMinWidth),
            int(cells._netclass(board, 'GND')['width'])), maximum_Ground_return_mm=MAX_LOCAL_RETURN_MM,
        pose_screen=placement._screen(board, fp.GetReference(), deadline),
        projected_native_binding=row._source_binding(board), no_Source_copper_retirement=True,
        selected_bypass_or_component_load_inferred=False, current_qualified=False,
        routing_admitted=False, release_authority=False, original_parent_receiving_still_required=True))
    _need(force._code_identity() == epoch and force._family(source, board_hint) == family,
        'aggregate_capacitor_Source_or_code_changed')
    _left(deadline)
    return board, result


def save_private(board, candidate, proposal):
    """Source-preserving constructor only; no saved proof is created here."""
    _need(proposal.get('scope') == SCOPE and force._hash(proposal['source']) == proposal['source_sha256']
        and force._code_identity() == proposal['code_identity'], 'fresh_aggregate_capacitor_save_required')
    field._save_field_snapshot(board, candidate)
    source_text.write_raw(candidate, footprints.retain(source_text.raw_text(proposal['source']),
        source_text.raw_text(candidate), [proposal['request']['footprint_uuid']]))
    # No original group membership/metadata moves in this operation. Native
    # IO may reorder a group's members; restore the SOURCE node in the
    # constructor, never normalize away a changed saved-child comparison.
    inventory, *_ = literal._inventory(source_text.raw_text(proposal['source']))
    groups = {uid for uid, (_, _, node) in inventory.items() if source_text.kind(node) == 'group'}
    if groups:
        source_text.write_raw(candidate, source_text.retain_replay_source_nodes(
            source_text.raw_text(proposal['source']), source_text.raw_text(candidate), groups, set()))
    if proposal['source_reference_map'] is not None:
        maps.preserve_literal_hidden_field_order(candidate,
            [(proposal['source_reference_map'], tuple(proposal['delta_nm']))],
            maximum_translation_mm=proposal['request']['max_shift_mm'])
    return dict(saved=True, current_qualified=False, routing_admitted=False, release_authority=False)


def _material(parent, child, proposal, incoming, deadline):
    tracks = {force._uid(t): t for t in child.GetTracks()}
    _need(type(incoming) is set and 1 <= len(incoming) <= MAX_NEW_TRACKS+MAX_NEW_VIAS
        and incoming <= tracks.keys(), 'bounded_exact_new_capacitor_material_required')
    items = [tracks[u] for u in incoming]; rail = proposal['supply_request']['net']
    vias = [i for i in items if i.GetClass() == 'PCB_VIA']
    strokes = [i for i in items if i.GetClass() == 'PCB_TRACK']
    _need(len(vias) <= MAX_NEW_VIAS and 1 <= len(strokes) <= MAX_NEW_TRACKS
        and len(strokes)+len(vias) == len(items)
        and all(i.GetNetname() in (rail, 'GND') and not i.IsLocked()
            and i.GetParentGroup() is None for i in items)
        and not any(g.ContainsItem(i) for g in child.Groups() for i in items)
        and sum(t.GetLength() for t in strokes) <= MAX_NEW_LENGTH_NM,
        'finite_new_supply_and_Ground_cell_only')
    fp = child.FindFootprintByReference(proposal['owner_ref'])
    pads = {force._uid(p): p for p in fp.Pads()}
    positive, ground = pads[proposal['supply_pad_uuid']], pads[proposal['ground_pad_uuid']]
    graph = fr._read_only_route_connectivity(child)
    reached = {net: {force._uid(p)} | {force._uid(i) for i in graph.GetConnectedItems(p)}
        for net, p in ((rail, positive), ('GND', ground))}
    _need(all(force._uid(i) in reached[i.GetNetname()] for i in items),
        'every_new_conductor_must_reach_its_actual_capacitor_land')
    for track in strokes:
        _left(deadline); net = str(track.GetNetname()); face = int(track.GetLayer())
        floor = (proposal['ground_width_nm'] if net == 'GND' else
            full._source_width_floor(parent, Path(proposal['source']), proposal['aggregate_contract'], face))
        _need(not track.HasSolderMask() and track.GetWidth() >= floor and track.GetLength() > 0
            and craft.is_canonical_stroke(tuple(track.GetStart()), tuple(track.GetEnd()), tolerance_nm=0),
            'full_Source_width_canonical_capacitor_conductors_required')
        if net == 'GND':
            # PAD.GetLayer() is not the actual copper mask of a flipped SMD
            # land. Require its one real CuStack face, as the Source owner
            # compiler does; do not turn this into multi-layer permission.
            _need(tuple(map(int, ground.GetLayerSet().CuStack())) == (face,)
                and all(math.dist(tuple(at), tuple(ground.GetPosition()))
                <= 1500000 for at in (track.GetStart(), track.GetEnd())),
                'immediate_single_surface_capacitor_Ground_only')
    received_web = []; received_reference = []
    for via in vias:
        _left(deadline)
        if via.GetNetname() == rail:
            proof = web.receive(child, force._uid(via), proposal['native_supply_contact_contract'], timeout_s=_left(deadline))
            _need(proof['ok'] and proof['complete'], 'actual_full_current_capacitor_via_web_required')
            received_web.append(proof)
        else:
            received_reference.append(reference._reference_contacts(child, via))
    connected = ports.full_width_connection(parent, child, Path(proposal['source']),
        proposal['supply_request'], proposal['board_hint'], deadline)
    _need(connected is not None and connected['all_named_contacts_connected']
        and connected['zone_and_foreign_net_edges_excluded'], 'full_aggregate_supply_connection_required')
    locality=proposal['source_locality_owner']
    local_owner=next((p for f in child.GetFootprints()for p in f.Pads()if force._uid(p)==locality['pad_uuid']),None)
    _need(local_owner is not None and local_owner.GetNetname()==rail
        and math.dist(tuple(positive.GetPosition()),tuple(local_owner.GetPosition()))
            <=locality['maximum_distance_mm']*1e6,'saved_actual_capacitor_owner_locality_required')
    # Independently rebuild a full-width SAME-FACE graph. No plane edge,
    # barrel shortcut or remote-root connectivity can replace the local loop.
    local_board=pcbnew.LoadBoard(child.GetFileName())
    from cec_native_items import discard_items
    floor=full._source_width_floor(parent,Path(proposal['source']),proposal['aggregate_contract'],locality['face'])
    discard_items(local_board,[t for t in local_board.GetTracks()
        if t.GetClass()not in('PCB_TRACK','PCB_ARC')or t.GetNetname()!=rail
        or int(t.GetLayer())!=locality['face']or t.GetWidth()<floor])
    local_pads={force._uid(p):p for f in local_board.GetFootprints()for p in f.Pads()}
    local_path=cells._shortest_track_path_mm(local_board,local_pads[proposal['supply_pad_uuid']],local_pads[locality['pad_uuid']])
    _need(local_path is not None and local_path<=locality['maximum_supply_path_mm'],
        'actual_full_width_local_supply_loop_required')
    immediate = cells._existing_return(child, ground, MAX_LOCAL_RETURN_MM, allow_native_track_body=True)
    _need(immediate is not None, 'actual_immediate_capacitor_Ground_return_required')
    _left(deadline)
    return dict(incoming_uuids=sorted(incoming), full_current_connection=connected,
        actual_Source_owner_local_supply_path_mm=local_path,source_locality_owner=locality,
        actual_supply_webs=received_web, actual_Ground_reference_contacts=received_reference,
        actual_Ground_return_mm=immediate[0], Ground_via_uuid=force._uid(immediate[1]),
        current_qualified=False, plated_barrel_capacity_qualified=False, release_authority=False)


def receive(source, candidate, proposal, *, timeout_s=10.):
    """Fresh Source recompile, saved exact delta, then actual paths/partitions.

    Three explicit <=10s constituents; no cached constructor witness, loop,
    extended native call, Source cut or substitution of counts for topology.
    """
    _deadline(timeout_s)
    stages = ['Source_recompile', 'exact_saved_frame_and_additions', 'actual_paths_and_returns']
    result = dict(scope='independent_saved_Source_aggregate_capacitor_cell', ok=False, complete=False,
        errors=[], timings_s={}, bounded_composition=dict(constituents=stages,
            per_constituent_limit_s=timeout_s, aggregate_limit_s=len(stages)*timeout_s),
        current_qualified=False, routing_admitted=False, release_authority=False,
        whole_original_parent_current_field_Kelvin_native_parity_and_assembly_still_required=True)
    started = phase_started = time.monotonic(); stage = stages[0]
    try:
        deadline = _deadline(timeout_s)
        source, candidate = [Path(p).resolve(strict=True) for p in (source, candidate)]
        _need(source != candidate and not source.samefile(candidate) and proposal.get('scope') == SCOPE
            and proposal.get('source') == str(source), 'distinct_Source_capacitor_saved_context_required')
        request = proposal['request']; frame, fresh = compile(source, board_hint=proposal['board_hint'],
            timeout_s=_left(deadline), **request)
        _need(_stable(proposal) == fresh and fresh['pose_screen']['ok'],
            'fresh_complete_Source_capacitor_proposal_required')
        epoch = force._code_identity(); families = [force._family(p, proposal['board_hint']) for p in (source, candidate)]
        _left(deadline); result['timings_s'][stage] = time.monotonic()-phase_started
        stage = stages[1]; phase_started = time.monotonic(); deadline = _deadline(timeout_s)
        with tempfile.TemporaryDirectory(prefix='cec-aggregate-capacitor-receive-') as work:
            expected = force._copy_family(source, Path(work)/'expected')
            additive._ground_refill(frame); save_private(frame, expected, fresh)
            proof = additive.receive(expected, candidate, board_hint=proposal['board_hint'], timeout_s=_left(deadline))
            result['exact_saved_Source_frame_and_additions'] = proof
            _need(proof['ok'] and proof['complete'], 'exact_Source_capacitor_pose_and_additions_refused')
        _left(deadline); result['timings_s'][stage] = time.monotonic()-phase_started
        stage = stages[2]; phase_started = time.monotonic(); deadline = _deadline(timeout_s)
        parent, child = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
        result['actual_cell_paths'] = _material(parent, child, fresh, set(proof['added_native_uuids']), deadline)
        old = {force._uid(p): p for f in parent.GetFootprints() for p in f.Pads()}
        new = {force._uid(p): p for f in child.GetFootprints() for p in f.Pads()}
        owner = parent.FindFootprintByReference(fresh['owner_ref'])
        rebindings = {force._item_key(new[force._uid(p)]): force._item_key(old[force._uid(p)]) for p in owner.Pads()}
        paired = partitions.compare(parent, child, timeout_s=_left(deadline), identity_rebindings=rebindings)
        _need(paired['preserved'] is True and not paired['demoted_parts'],
            'every_original_capacitor_and_copper_partition_required')
        result['native_partition_preservation'] = {k: v for k, v in paired.items()
            if k not in ('source_parts', 'child_parts', 'demoted_parts')}
        result['all_original_Ground_returns'] = returns.receive(parent, child, timeout_s=_left(deadline))
        _need(result['all_original_Ground_returns']['ok'] and result['all_original_Ground_returns']['complete'],
            'known_Source_Ground_return_must_not_worsen')
        _need(epoch == force._code_identity()
            and families == [force._family(p, proposal['board_hint']) for p in (source, candidate)],
            'saved_capacitor_Source_family_or_code_changed')
        _left(deadline); result['timings_s'][stage] = time.monotonic()-phase_started
        result.update(ok=True, complete=True, source_sha256=force._hash(source), candidate_sha256=force._hash(candidate),
            all_Source_copper_retained_exactly=True, no_bypass_assignment_or_component_current_inferred=True)
    except (ValueError, RuntimeError, TypeError, KeyError, OSError) as exc:
        result['errors'].append(type(exc).__name__ + ':' + str(exc)); result['failed_stage'] = stage
        result['timings_s'][stage] = time.monotonic()-phase_started
    result['elapsed_s'] = time.monotonic()-started
    return result
