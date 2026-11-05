"""Complete one manufacturer-declared local auxiliary measurement strap.

Only one new planar centre-to-centre segment is owned.  The paired input's
existing non-load width policy is distinct from the unchanged force-net
class.  No external quiet-tree repair, current/load/thermal/barrel/Kelvin or
release qualification is granted; all enclosing saved-board gates remain due.
"""
import hashlib
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_force_current as force
import cec_cell_row_rebuild as binding
import cec_measurement_auxiliary_cut as auxiliary


def _need(value, reason):
    if not value:
        raise ValueError(reason)


def _deadline(timeout_s):
    _need(type(timeout_s) in (int, float) and math.isfinite(timeout_s)
          and 0 < timeout_s <= 10., 'bounded_auxiliary_join_lease_required')
    return time.monotonic() + timeout_s


def _left(deadline):
    left = deadline - time.monotonic()
    _need(left > 0, 'source_auxiliary_join_deadline')
    return min(10., left)


def _finish_stage(result, deadline, started, name, timeout_s):
    """An expired constituent cannot borrow the following stage's lease."""
    _left(deadline)
    elapsed = time.monotonic()-started
    _need(elapsed <= timeout_s, 'auxiliary_receiving_constituent_lease_exhausted:'+name)
    result.setdefault('constituent_timings_s', {})[name] = elapsed


def _flags():
    return dict(current_authority=False, numeric_load_assumed=False,
                trunk_capacity_credited=False, barrel_qualified=False,
                kelvin_qualified=False, release_authority=False,
                routing_admitted=False, retirement_authority=False,
                placement_authority=False, external_quiet_tree_qualified=False,
                whole_shared_stage_still_required=True, no_path_proof=False)


def _function_matches(actual, declared):
    # Finite publisher/selected-symbol spelling correspondence only.  Do not
    # discard punctuation, change polarity or accept an arbitrary input name.
    aliases = {'VBUS': {'VBUS','Vbus'}, 'IN-': {'IN-','VIN-','Vin-'}}
    return actual in aliases.get(declared, {declared})


def _canonical(board, source, hint, fp, model, declared, deadline):
    """Fresh complete Source/export identity, not unlabelled-pad inference."""
    import cec_source_ground_leaf as canonical
    import cec_source_no_connect as nc
    import cec_quiet_signal_requests as pins
    import cec_device_power_roles as roles
    import cec_synth_pipeline as synth
    from cec_footprint_fields import footprint_properties
    root = nc._root(board, hint)
    _need(root is not None, 'canonical_auxiliary_join_Source_required')
    root = Path(root).resolve(strict=True)
    files, hashes, instances = canonical._hierarchy(root, deadline)
    tree, exporter = canonical._export(root, deadline)
    comps, nets, node_net = canonical._tables(tree)
    _need(type(exporter) is dict and Path(exporter.get('exporter', '')).is_file()
          and force._hash(Path(exporter['exporter'])) == exporter.get('exporter_sha256'),
          'fresh_bound_auxiliary_join_exporter_required')
    identity = canonical._identity(board, fp.GetReference(), comps, instances, deadline)
    props = footprint_properties(fp)
    blocks = [b for tag, b in identity[2].children if tag == 'symbol'
              and canonical.sch.prop_value(b, 'Reference') == fp.GetReference()]
    exported = {synth._val(p, 'name', ''): synth._val(p, 'value', '')
                for p in synth._kids(comps[fp.GetReference()], 'property')}
    # All presently declared auxiliary maps are TI current monitors.  No
    # publisher/model is inferred from the net name or caller's pad choice.
    _need(model['source'].startswith('https://www.ti.com/')
          and props.get('Manufacturer') == 'Texas Instruments' and len(blocks) == 1
          and canonical.sch.prop_value(blocks[0], 'Manufacturer') == props['Manufacturer']
          and exported.get('Manufacturer') == props['Manufacturer'],
          'positive_selected_auxiliary_manufacturer_required')
    physical = roles.physical_pinmap(fp, model, board_hint=hint, timeout_s=_left(deadline))
    _need(set(physical) == set(model['pins']), 'complete_auxiliary_physical_pinmap_required')
    kind_types = {'ground': {'power_in'}, 'power_input': {'power_in'},
        'measurement': {'input'}, 'address': {'input'},
        'signal_input': {'input'}, 'signal_output': {'output', 'open_collector'},
        'signal_io': {'bidirectional'}, 'no_connect': {'no_connect'}}
    # Inspect the COMPLETE selected embedded table without pretending every
    # unrelated pin is connected.  _source_pin's no-connect veto is required
    # for the two newly joined inputs, not an unchanged optional ALERT pin.
    libraries = [b for tag,b in identity[2].children if tag == 'lib_symbols']
    _need(len(libraries) == 1, 'complete_auxiliary_embedded_library_required')
    embedded = synth.parse_sexpr(libraries[0])
    symbols = [n for n in synth._kids(embedded,'symbol') if len(n)>1 and n[1]==identity[3]['lib_id']]
    _need(len(symbols)==1 and synth._first(symbols[0],'extends') is None,
          'complete_unique_auxiliary_embedded_symbol_required')
    pending=[symbols[0]]; source_pins={}; visited=0
    while pending:
        _left(deadline); node=pending.pop(); visited+=1
        _need(visited<=8192, 'auxiliary_embedded_symbol_inventory_bound')
        if isinstance(node,list) and node:
            if node[0]=='pin':
                number=synth._val(node,'number','')
                _need(number and number not in source_pins and len(node)>1,
                      'unique_auxiliary_embedded_pin_required')
                source_pins[number]=dict(type=node[1],name=synth._val(node,'name',''))
            pending.extend(n for n in node if isinstance(n,list))
    source_positions={p['num']:p for p in identity[3]['pins']}
    _need(set(source_pins)==set(model['pins']) and set(source_positions)==set(source_pins)
          and len(source_positions)==len(identity[3]['pins']),
          'complete_auxiliary_canonical_pin_table_required')
    preserved_no_connect=[]
    native = list(fp.Pads())
    _need(len(native) == len(model['pins'])
          and len({p.GetNumber() for p in native}) == len(native),
          'one_actual_land_per_declared_auxiliary_package_pin_required')
    for pad in native:
        _left(deadline)
        number = pad.GetNumber(); actual = source_pins[number]
        _need(actual['name'] and actual['type'] == source_positions[number]['type']
              and actual['type'] in kind_types.get(model['pins'][number], set())
              and pad.GetPinType() in ('', actual['type'])
              and pad.GetPinFunction() in ('', actual['name'])
              and node_net.get((fp.GetReference(), number)) == pad.GetNetname(),
              'complete_auxiliary_Source_pin_or_net_contradiction')
        if number in declared[:2]:
            _need(pins._source_pin(identity, number, deadline)==actual,
                  'actual_connected_auxiliary_and_paired_Source_pins_required')
        elif any(nc._nm(p['pos'])==nc._nm(source_positions[number]['pos'])
                 for p in identity[2].no_connects):
            _need(nets.get(pad.GetNetname())=={(fp.GetReference(),number)},
                  'unrelated_Source_no_connect_must_keep_exact_singleton_net')
            preserved_no_connect.append(number)
    _need(source_pins[declared[0]]['type'] == source_pins[declared[1]]['type'] == 'input'
          and _function_matches(source_pins[declared[0]]['name'], declared[2])
          and _function_matches(source_pins[declared[1]]['name'], declared[3]),
          'manufacturer_auxiliary_and_paired_Source_functions_required')
    wanted = fp.FindPadByNumber(declared[1]).GetNetname()
    native_members = [(p.GetParentFootprint().GetReference(), p.GetNumber())
        for f in board.GetFootprints() for p in f.Pads() if p.GetNetname() == wanted]
    # External source terminals may have several distinct physical legs of
    # one logical pin.  Keep every native UUID in the physical graph; compare
    # only the canonical LOGICAL net inventory here, never collapse copper.
    _need(nets.get(wanted) == set(native_members)
          and all(node_net.get(member) == wanted for member in native_members),
          'complete_canonical_auxiliary_net_membership_required')
    _need(hashes == {str(p): force._hash(p) for p in files},
          'auxiliary_canonical_hierarchy_changed')
    _left(deadline)
    return dict(root=str(root), schematic_files_sha256=hashes, exporter=exporter,
        owner_uuid=force._uid(fp), owner_reference=fp.GetReference(),
        symbol_uuid=identity[3]['uuid'], lib_id=identity[3]['lib_id'],
        manufacturer=props['Manufacturer'], mpn=props['MPN'],
        model=model, canonical_pins=source_pins,
        native_pad_nets={force._uid(p): dict(number=p.GetNumber(), net=p.GetNetname()) for p in native},
        source_net_members=sorted(native_members),
        unchanged_unselected_Source_no_connect_pins=sorted(preserved_no_connect),
        current_authority=False)


def _live_canonical(proof):
    exporter = proof['exporter']
    _need(all(force._hash(Path(p)) == h for p, h in proof['schematic_files_sha256'].items())
          and force._hash(Path(exporter['exporter'])) == exporter['exporter_sha256'],
          'auxiliary_canonical_Source_or_exporter_changed')


def _isolation(board, pad, deadline):
    """Require an actual singleton including saved zone islands, not pad IDs."""
    import cec_native_partition_pair as partitions
    graph = partitions._inventory(board, deadline,
        dict(items=16384, polygons=4096, vertices=200000))
    key = force._item_key(pad)
    part = graph['components'][graph['component_of'][key]]
    _need(part == {key}, 'Source_auxiliary_land_must_be_physically_isolated')
    return dict(auxiliary_pad_uuid=force._uid(pad), native_component_size=1,
                all_saved_zone_islands_included=True)


def _native_scope(board, source, hint, paired_pad_uuid, deadline, *, isolated):
    import cec_device_power_roles as roles
    import cec_pair_semantics as semantics
    import cec_measurement_route_policy as policy
    import cec_route_dimensions as dimensions
    import cec_fr as fr
    _need(type(hint) is str and hint and type(paired_pad_uuid) is str and paired_pad_uuid,
          'explicit_Source_auxiliary_paired_input_identity_required')
    source = Path(source).resolve(strict=True)
    _need(Path(board.GetFileName()).resolve() == source,
          'exact_saved_auxiliary_native_Source_required')
    before = binding._source_binding(board)
    saved = pcbnew.LoadBoard(str(source))
    _need(saved is not None and before == binding._source_binding(saved),
          'auxiliary_native_board_must_match_saved_Source')
    pads = [p for f in board.GetFootprints() for p in f.Pads()]
    _need(len(pads) <= 16384 and len({force._uid(p) for p in pads}) == len(pads),
          'bounded_unique_auxiliary_Source_lands_required')
    roots = [p for p in pads if force._uid(p) == paired_pad_uuid]
    _need(len(roots) == 1, 'unique_actual_paired_auxiliary_input_required')
    paired = roots[0]; fp = paired.GetParentFootprint()
    model = roles.footprint_contract(fp); pair = semantics.footprint_input_contract(fp)
    mapping = semantics.current_auxiliary_input_contract(pair[0]) if pair else None
    _need(model and pair and mapping and not fp.IsDNP() and not fp.IsLocked()
          and paired.GetNumber() in pair[1], 'complete_fitted_auxiliary_measurement_package_required')
    declared = [q for q in mapping[1] if q[1] == paired.GetNumber()]
    _need(len(declared) == 1, 'unique_manufacturer_auxiliary_mapping_required')
    declared = declared[0]
    peers = [p for p in fp.Pads() if p.GetNumber() == declared[0]]
    _need(len(peers) == 1, 'unique_actual_auxiliary_package_land_required')
    aux = peers[0]; layer = int(pcbnew.F_Cu)
    _need(layer in tuple(board.GetEnabledLayers().CuStack()) and not fp.IsFlipped()
          and all(p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and not p.HasHole()
            and tuple(p.GetLayerSet().CuStack()) == (pcbnew.F_Cu,)
            and p.FlashLayer(layer) and p.GetParentGroup() is None for p in (paired, aux))
          and paired.GetNetCode() > 0 and paired.GetNetCode() == aux.GetNetCode()
          and paired.GetNetname() == aux.GetNetname(),
          'same_fitted_front_surface_auxiliary_pair_required')
    points = [list(paired.GetPosition()), list(aux.GetPosition())]
    dx, dy = [abs(a-b) for a, b in zip(*points)]
    _need(0 < math.dist(*points) <= 4000000 and (not dx or not dy or dx == dy),
          'bounded_literal_octilinear_auxiliary_join_required')
    reference = auxiliary._reference_map(board, fp, deadline=deadline) if fp.GetParentGroup() else None
    selected = policy.input_contract(board, paired_pad_uuid)
    _need(selected['kind'] == 'shunt_kelvin_front_no_via'
          and selected['permitted_layers'] == [layer] and selected['allow_layer_bridge'] is False,
          'positive_Source_paired_front_only_measurement_policy_required')
    spec = fr._project_netclass_resolver(str(source), board=board)(paired.GetNetname()) or {}
    basis = dimensions.nonload_measurement_width(board, source, paired.GetNetname(), parent_spec=spec)
    width = basis['width_nm']
    _need(type(width) is int and max(200000, int(board.GetDesignSettings().m_TrackMinWidth)) <= width <= 350000,
          'bounded_authored_auxiliary_nonload_process_width_required')
    klass = paired.GetNet().GetNetClassSlow()
    _need(klass is not None and type(spec.get('clearance')) in (int, float)
          and math.isfinite(spec['clearance']) and spec['clearance'] >= 0,
          'actual_auxiliary_clearance_authority_required')
    gap = max(200000, int(board.GetDesignSettings().m_MinClearance),
              int(klass.GetClearance()), math.ceil(spec['clearance']*1e6))
    a, b = [pcbnew.VECTOR2I(*p) for p in points]
    _need(fr._edge_leg_clear(board, a, b, (width+1)//2+gap)
          and fr._tap_foreign_clear(board, a, b, width, layer, gap, {paired.GetNetCode()}),
          'auxiliary_join_native_foreign_rule_area_hole_or_edge_refused')
    isolation = _isolation(board, aux, deadline) if isolated else None
    _need(before == binding._source_binding(board), 'auxiliary_compile_changed_native_Source')
    _left(deadline)
    return dict(schema=1, scope='Source_typed_local_auxiliary_measurement_join', complete=True,
        source=str(source), source_sha256=force._hash(source), board_hint=hint,
        paired_pad_uuid=paired_pad_uuid, auxiliary_pad_uuid=force._uid(aux), owner_uuid=force._uid(fp),
        paired_input_pin=paired.GetNumber(), auxiliary_pin=aux.GetNumber(),
        net=paired.GetNetname(), layer=layer, points_nm=points, width_nm=width, clearance_nm=gap,
        nonload_width_basis=basis, paired_input_policy=selected,
        source_native_binding=before, source_reference_map=reference, isolated_auxiliary=isolation,
        existing_external_quiet_tree_must_remain_exact=True, **_flags()), fp, model, declared


def _compile(board, source, hint, paired_pad_uuid, deadline, *, isolated):
    proof, fp, model, declared = _native_scope(
        board, source, hint, paired_pad_uuid, deadline, isolated=isolated)
    canonical = _canonical(board, source, hint, fp, model, declared, deadline)
    _need(proof['source_native_binding'] == binding._source_binding(board),
          'auxiliary_canonical_compile_changed_native_Source')
    _live_canonical(canonical); _left(deadline)
    proof['canonical_Source'] = canonical
    return proof


def _child_canonical_pin_replay(before, child):
    """Reprove native child pins after literal equality, not a second export.

    The caller first proves every original saved object, fill and root exact,
    plus exact project/library sidecars. Only the independently compiled new
    strap may differ. The one fresh complete canonical export therefore
    applies to the literal-retained child package as well; its actual native
    pin attributes are still independently read, never copied into the PCB.
    """
    canonical = before['canonical_Source']
    owners = [f for f in child.GetFootprints() if force._uid(f) == before['owner_uuid']]
    _need(len(owners) == 1, 'literal_child_auxiliary_owner_required')
    native = list(owners[0].Pads())
    pins = {force._uid(p): dict(number=p.GetNumber(), net=p.GetNetname()) for p in native}
    _need(len(pins) == len(native) and pins == canonical['native_pad_nets'],
          'literal_child_complete_auxiliary_pin_identity_required')
    for pad in native:
        declared = canonical['canonical_pins'][pad.GetNumber()]
        _need(pad.GetPinType() in ('', declared['type'])
              and pad.GetPinFunction() in ('', declared['name']),
              'literal_child_auxiliary_pin_attributes_changed')
    return dict(complete=True, canonical_Source=canonical,
        actual_child_native_pad_nets=pins,
        proof_basis='fresh_complete_Source_export_and_all_original_objects_literal_exact',
        fresh_child_schematic_export_performed=False,
        native_child_pin_attributes_independently_replayed=True,
        current_authority=False, external_quiet_tree_qualified=False)


def plan(board, source, *, board_hint, paired_pad_uuid, timeout_s=10.):
    deadline = _deadline(timeout_s); source = Path(source).resolve(strict=True)
    epoch = force._code_identity(); family = force._family(source, board_hint)
    proof = _compile(board, source, board_hint, paired_pad_uuid, deadline, isolated=True)
    _live_canonical(proof['canonical_Source'])
    _need(epoch == force._code_identity() and family == force._family(source, board_hint),
          'auxiliary_plan_Source_family_or_code_changed')
    _left(deadline)
    proof['source_family'] = family
    proof['code_sha256'] = hashlib.sha256(repr(sorted(epoch.items())).encode()).hexdigest()
    return proof


def _exact_addition(source, candidate, child):
    import cec_source_literal_additions as literal
    import cec_source_retaining_ses_import as syntax
    texts = [p.read_text() for p in (source, candidate)]
    old, new = [literal._inventory(t)[0] for t in texts]
    _need(old.keys() <= new.keys() and all(old[u][2] == new[u][2] for u in old),
          'all_original_auxiliary_Source_objects_and_fills_must_remain_literal_exact')
    roots = []
    for text in texts:
        spans, _ = literal._root(text)
        roots.append([literal._canonical(text[a:b]) for a, b in spans
                      if literal._uuid(text[a:b]) is None])
    _need(roots[0] == roots[1], 'auxiliary_Source_root_settings_changed')
    incoming = set(new)-set(old)
    _need(len(incoming) == 1 and syntax.kind(new[next(iter(incoming))][2]) == 'segment',
          'exactly_one_new_planar_auxiliary_strap_required')
    items = [t for t in child.GetTracks() if force._uid(t) in incoming]
    _need(len(items) == 1 and items[0].GetClass() == 'PCB_TRACK',
          'one_actual_native_auxiliary_segment_required')
    return items[0], literal.incoming_copper_nets(texts[1], incoming)


def receive(source, candidate, *, board_hint, paired_pad_uuid, timeout_s=10.):
    """Two explicit bounded stages, not an unlabelled twenty-second lease.

    Fresh Source/canonical/native ownership must pass its own <=10s lease
    before independent saved additive/refill/partition receiving starts.
    Both stages share immutable input/code bindings; neither alone passes.
    """
    started = time.monotonic(); stage_started = started
    deadline = _deadline(timeout_s)
    result = dict(schema=1, scope='Source_typed_local_auxiliary_measurement_join',
                  ok=False, complete=False, errors=[],
                  bounded_receiving_stages=2, each_stage_lease_s=timeout_s,
                  composed_budget_s=2*timeout_s, constituent_timings_s={}, **_flags())
    try:
        import cec_additive_route_receiving as additive
        import cec_native_partition_pair as partitions
        from cec_source_sideband_monitor_tap import _contact
        source, candidate = [Path(p).resolve(strict=True) for p in (source, candidate)]
        _need(not source.samefile(candidate), 'distinct_auxiliary_saved_Source_and_child_required')
        epoch = force._code_identity()
        families = [force._family(p, board_hint) for p in (source, candidate)]
        _need(force._sidecars(source) == force._sidecars(candidate), 'auxiliary_Source_companions_changed')
        parent, child = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
        # Establish exact retained material BEFORE using the fresh Source
        # export for either endpoint. Do not duplicate an expensive identical
        # all-pin export, or accept a caller-provided/cache proof instead.
        track, names = _exact_addition(source, candidate, child); uid = force._uid(track)
        before = _compile(parent, source, board_hint, paired_pad_uuid, deadline, isolated=True)
        after, _, _, _ = _native_scope(child, candidate, board_hint, paired_pad_uuid, deadline, isolated=False)
        child_canonical = _child_canonical_pin_replay(before, child)
        result['Source_plan'] = before; result['child_canonical_Source_replay'] = child_canonical
        keys = ('paired_pad_uuid','auxiliary_pad_uuid','owner_uuid','paired_input_pin',
                'auxiliary_pin','net','layer','points_nm','width_nm','clearance_nm')
        _need(all(before[k] == after[k] for k in keys), 'auxiliary_Source_identity_or_policy_changed')
        _need(names == {uid:before['net']} and track.GetNetname() == before['net']
              and track.GetLayer() == before['layer'] and track.GetWidth() == before['width_nm']
              and {tuple(track.GetStart()),tuple(track.GetEnd())} == set(map(tuple,before['points_nm']))
              and not track.IsLocked() and track.GetParentGroup() is None and not track.HasSolderMask(),
              'exact_Source_derived_auxiliary_track_geometry_required')
        strap = auxiliary.plan(child, paired_pad_uuid, timeout_s=_left(deadline),
                               allow_source_reference_maps=True)
        result['independent_saved_literal_strap'] = strap
        _need(strap['track_uuids'] == [uid] and strap['boundary_uuids'] == [before['auxiliary_pad_uuid']],
              'independently_recognized_auxiliary_strap_mismatch')
        pads = {force._uid(p):p for f in child.GetFootprints() for p in f.Pads()}
        contacts = {u:_contact(track, pads[u], before['layer'])
                    for u in (paired_pad_uuid,before['auxiliary_pad_uuid'])}
        _need(all(v > 0 for v in contacts.values()), 'positive_native_auxiliary_lands_contact_required')
        result['positive_native_pad_contacts_nm2'] = contacts
        _live_canonical(before['canonical_Source'])
        _need(epoch == force._code_identity()
              and families == [force._family(p, board_hint) for p in (source, candidate)],
              'auxiliary_Source_stage_family_or_code_changed')
        _finish_stage(result, deadline, stage_started, 'fresh_Source_and_native_ownership', timeout_s)
        # A separately bounded saved receiving stage is entered ONLY after
        # the complete Source stage passes. No retry or caller proof/cache.
        stage_started = time.monotonic(); deadline = _deadline(timeout_s)
        replay = additive.receive(source, candidate, board_hint=board_hint, timeout_s=_left(deadline))
        result['saved_additive_receiving'] = replay
        _need(replay.get('ok') is True and replay.get('complete') is True,
              'auxiliary_exact_saved_additive_receiving_refused')
        shared = partitions.compare(parent, child, timeout_s=_left(deadline))
        result['whole_native_Source_partitions'] = {k:v for k,v in shared.items()
            if k not in ('source_parts','child_parts','demoted_parts')}
        _need(shared.get('available') is True and shared.get('preserved') is True,
              'auxiliary_original_native_partition_loss')
        _live_canonical(before['canonical_Source'])
        _need(epoch == force._code_identity()
              and families == [force._family(p, board_hint) for p in (source, candidate)],
              'auxiliary_saved_family_or_code_changed')
        _finish_stage(result, deadline, stage_started, 'saved_additive_refill_and_partitions', timeout_s)
        _need(time.monotonic()-started <= 2*timeout_s, 'auxiliary_composed_receiving_budget_exhausted')
        result.update(ok=True, complete=True, added_track_uuid=uid, source=str(source),
            source_sha256=force._hash(source), candidate=str(candidate), candidate_sha256=force._hash(candidate),
            source_family=families[0], candidate_family=families[1],
            code_sha256=hashlib.sha256(repr(sorted(epoch.items())).encode()).hexdigest(),
            existing_external_copper_and_all_fills_literal_exact=True,
            unchanged_external_quiet_tree_debt_not_qualified=True)
    except Exception as exc:
        result['errors'].append(type(exc).__name__ + ':' + str(exc))
    return result


def construct_private(source, directory, *, board_hint, paired_pad_uuid, timeout_s=10.):
    """One bounded construction plus two saved receiving stages; no retry.

    Each constituent keeps its own <=10s lease. A completed construction is
    never itself saved admission; both independent receiving stages are due.
    """
    started = time.monotonic()
    deadline = _deadline(timeout_s)
    source = Path(source).resolve(strict=True); directory = Path(directory).resolve()
    result = dict(ok=False, complete=False, errors=[], bounded_construction_stages=3,
        each_stage_lease_s=timeout_s, composed_budget_s=3*timeout_s,
        constituent_timings_s={}, **_flags())
    try:
        import cec_field_coupling as field
        import cec_source_literal_additions as literal
        import cec_source_retaining_ses_import as textio
        force._check_proposal_directory(directory, force._protected_paths(source, board_hint))
        _need(not directory.exists(), 'fresh_auxiliary_private_directory_required')
        epoch = force._code_identity(); family = force._family(source, board_hint)
        board = pcbnew.LoadBoard(str(source))
        proposal = plan(board, source, board_hint=board_hint, paired_pad_uuid=paired_pad_uuid,
                        timeout_s=_left(deadline))
        result['proposal'] = proposal
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I(*proposal['points_nm'][0]))
        track.SetEnd(pcbnew.VECTOR2I(*proposal['points_nm'][1]))
        track.SetWidth(proposal['width_nm']); track.SetLayer(proposal['layer'])
        track.SetNet(board.GetNetInfo().GetNetItem(board.GetNetcodeFromNetname(proposal['net'])))
        board.Add(track)
        with tempfile.TemporaryDirectory(prefix='cec-auxiliary-join-') as tmp:
            native = Path(tmp)/'native.kicad_pcb'
            field._save_field_snapshot(board, native)
            output = literal.assemble(source.read_text(), native.read_text(), ground_ids=())
        _left(deadline)
        candidate = force._copy_family(source, directory)
        textio.write_raw(candidate, output)
        result.update(candidate=str(candidate), candidate_sha256=force._hash(candidate))
        _need(epoch == force._code_identity() and family == force._family(source, board_hint),
              'auxiliary_construction_stage_Source_or_code_changed')
        _finish_stage(result, deadline, started, 'Source_plan_and_literal_private_construction', timeout_s)
        replay = receive(source, candidate, board_hint=board_hint, paired_pad_uuid=paired_pad_uuid,
                         timeout_s=timeout_s)
        result['receiving'] = replay
        _need(replay.get('ok') is True and replay.get('complete') is True,
              'private_auxiliary_join_not_received')
        _need(epoch == force._code_identity() and family == force._family(source, board_hint),
              'auxiliary_constructor_Source_or_code_changed')
        _need(time.monotonic()-started <= 3*timeout_s, 'auxiliary_composed_construction_budget_exhausted')
        result.update(ok=True, complete=True)
    except Exception as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
