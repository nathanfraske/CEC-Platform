"""Source-typed digital sideband monitor tap, not an ordinary/quiet waiver.

The selected connector channel must already pass through. One stranded
selected resistor land may join that retained backbone; its other net is
exactly the resistor and a manufacturer-known scalar GPIO. This receiver
does not qualify application mode, voltage, current, barrels or manufacture.
"""
import math
from pathlib import Path
import time

import pcbnew
import cec_source_connector_feedthrough as feed
import cec_force_current as force


def _need(value, reason):
    if not value:
        raise ValueError(reason)


def _tick(deadline):
    _need(time.monotonic() < deadline, 'sideband_tap_deadline')


def _identity(board, ref, components, instances, deadline):
    """Add explicit manufacturer equality to the shared selected-part proof."""
    import cec_source_ground_leaf as source
    import cec_synth_pipeline as synth
    from cec_footprint_fields import footprint_properties
    identity = source._identity(board, ref, components, instances, deadline)
    fp, _, sf, _ = identity
    blocks = [b for tag, b in sf.children
              if tag == 'symbol' and source.sch.prop_value(b, 'Reference') == ref]
    exported = {synth._val(p, 'name', ''): synth._val(p, 'value', '')
                for p in synth._kids(components[ref], 'property')}
    manufacturer = footprint_properties(fp).get('Manufacturer')
    _need(manufacturer and len(blocks) == 1
          and source.sch.prop_value(blocks[0], 'Manufacturer') == manufacturer
          and exported.get('Manufacturer') == manufacturer,
          'sideband_tap_selected_manufacturer_mismatch')
    return identity


def compile_source(board, source, *, board_hint, connector_pad_uuids,
                   target_pad_uuid, deadline):
    """Read-only role/topology proof; not a saved candidate's admission."""
    import cec_source_ground_leaf as source_roles
    import cec_quiet_signal_requests as pins
    import cec_device_power_roles as roles
    import cec_resistive_monitor_branch as resistors
    from cec_footprint_fields import footprint_properties
    _need(type(deadline) in (int, float) and math.isfinite(deadline)
          and time.monotonic() < deadline <= time.monotonic() + 10.,
          'bounded_sideband_tap_compiler_lease_required')
    _need(type(connector_pad_uuids) in (tuple, list)
          and len(connector_pad_uuids) == 2
          and all(type(u) is str and u for u in connector_pad_uuids)
          and len(set(connector_pad_uuids)) == 2
          and type(target_pad_uuid) is str and target_pad_uuid
          and target_pad_uuid not in connector_pad_uuids,
          'two_Source_connectors_and_distinct_monitor_land_required')
    source = Path(source).resolve(strict=True)
    channel = feed._canonical(board, source, board_hint, connector_pad_uuids, deadline)
    net = channel['net']
    root = Path(channel['canonical_Source']['root'])
    files, hashes, instances = source_roles._hierarchy(root, deadline)
    tree, exporter = source_roles._export(root, deadline)
    components, nets, node_net = source_roles._tables(tree)
    previous = channel['canonical_Source']
    stable_keys = ('exporter', 'exporter_sha256', 'netlist_semantic_sha256', 'netlist_semantic_policy')
    old_exporter = previous['exporter']
    same_export = ({k:exporter.get(k) for k in stable_keys}
                   == {k:old_exporter.get(k) for k in stable_keys}
                   if exporter.get('netlist_semantic_sha256') and old_exporter.get('netlist_semantic_sha256')
                   else exporter == old_exporter)
    _need(hashes == previous['schematic_files_sha256'] and same_export,
          'sideband_tap_fresh_canonical_export_changed')
    pads = {force._uid(p): p for fp in board.GetFootprints() for p in fp.Pads()}
    _need(target_pad_uuid in pads, 'exact_existing_sideband_tap_land_required')
    target = pads[target_pad_uuid]
    fp = target.GetParentFootprint()
    selected = resistors.resistor_contract(fp)
    props = footprint_properties(fp)
    _need(selected is not None and selected['nominal_ohms'] >= 1000.,
          'selected_high_value_sideband_series_resistor_required')
    maker = selected.get('manufacturer', 'UNI-ROYAL')
    _need(str(props.get('Manufacturer', '')).upper() == maker.upper(),
          'sideband_tap_resistor_model_manufacturer_required')
    lands = list(fp.Pads())
    _need(len(lands) == 2 and len({p.GetNumber() for p in lands}) == 2
          and all(p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and not p.HasHole()
                  and tuple(p.GetLayerSet().CuStack()) == (pcbnew.F_Cu,)
                  and p.FlashLayer(pcbnew.F_Cu) for p in lands)
          and target.GetNetname() == net and target.GetNetCode() > 0,
          'two_actual_front_surface_monitor_resistor_lands_required')
    identity = _identity(board, fp.GetReference(), components, instances, deadline)
    for land in lands:
        actual = pins._source_pin(identity, land.GetNumber(), deadline)
        _need(actual == dict(type='passive', name='~')
              and node_net.get((fp.GetReference(), land.GetNumber())) == land.GetNetname()
              and land.GetPinType() in ('', actual['type'])
              and land.GetPinFunction() in ('', actual['name']),
              'sideband_tap_resistor_Source_pin_contradiction')
    other = next(p for p in lands if force._uid(p) != target_pad_uuid)
    other_net = other.GetNetname()
    members = [p for p in pads.values() if p.GetNetname() == other_net]
    _need(other_net and other_net != net and other.GetNetCode() > 0
          and other_net != 'GND' and not other_net.upper().startswith('UNCONNECTED-')
          and len(members) == 2 and other in members
          and nets.get(other_net) == {(p.GetParentFootprint().GetReference(), p.GetNumber())
                                     for p in members},
          'exact_resistor_plus_one_GPIO_monitor_net_required')
    gpio = next(p for p in members if force._uid(p) != force._uid(other))
    gpio_fp = gpio.GetParentFootprint()
    _need(gpio_fp != fp and not gpio_fp.IsDNP(), 'distinct_fitted_monitor_GPIO_required')
    witness = roles.scalar_gpio_pin(gpio_fp, gpio.GetNumber())
    _need(witness is not None, 'manufacturer_known_scalar_monitor_GPIO_required')
    _need(footprint_properties(gpio_fp).get('Manufacturer') == 'Espressif Systems',
          'positive_selected_scalar_GPIO_manufacturer_required')
    gpio_identity = _identity(board, gpio_fp.GetReference(), components, instances, deadline)
    actual = pins._source_pin(gpio_identity, gpio.GetNumber(), deadline)
    _need(actual == dict(type='bidirectional', name=witness['function'])
          and node_net.get((gpio_fp.GetReference(), gpio.GetNumber())) == other_net
          and gpio.GetPinType() in ('', actual['type'])
          and gpio.GetPinFunction() in ('', actual['name']),
          'sideband_tap_actual_Source_GPIO_contradiction')
    import cec_fr as fr
    import cec_pair_semantics as pairs
    import cec_current_topology as current
    import cec_synth_pipeline as synth
    protected = {n for pair in fr._board_kelvin_pairs(board) for n in pair}
    protected |= {n for _, a, b in pairs.coupled_pair_names(board) for n in (a, b)}
    protected |= {q[k] for q in pairs.analog_input_pairs(board) for k in ('p', 'n')}
    protected |= set(pairs.unresolved_current_monitor_nets(board))
    with force._thermal_hint(board_hint):
        protected |= set(current.board_current_domains(board, board_hint))
        _need(synth.spec_net_current_contract(board_hint, other_net) is None,
              'monitor_other_net_cannot_own_current_contract')
    _need(other_net not in protected
          and not any(z.GetNetname() == other_net and not z.GetIsRuleArea()
                      for z in board.Zones()), 'monitor_GPIO_net_cannot_borrow_protected_domain')
    native = {force._uid(p) for p in pads.values() if p.GetNetname() == net}
    _need(native == set(connector_pad_uuids) | {target_pad_uuid},
          'exact_two_connectors_one_monitor_land_required')
    parts = feed._parts(board, net, deadline)
    backbone = next(p for p in parts if connector_pad_uuids[0] in p)
    _need(len(parts) == 2 and set(connector_pad_uuids) <= backbone
          and {target_pad_uuid} in parts,
          'retained_connected_pass_through_and_one_stranded_resistor_land_required')
    _need(hashes == {str(p): force._hash(p) for p in files},
          'sideband_tap_hierarchy_changed_during_compile')
    _tick(deadline)
    return dict(scope='Source_typed_digital_sideband_monitor_tap', net=net,
                connector_pad_uuids=list(connector_pad_uuids), target_pad_uuid=target_pad_uuid,
                retained_backbone_uuids=sorted(backbone), connector_channel=channel,
                resistor=dict(mpn=props['MPN'], manufacturer=props['Manufacturer'],
                              footprint=fp.GetFPIDAsString(), value=fp.GetValue(),
                              nominal_ohms=selected['nominal_ohms'], source=selected['source']),
                monitor_GPIO=dict(pad_uuid=force._uid(gpio), other_net=other_net,
                                  actual_Source_pin=actual, manufacturer_witness=witness),
                canonical_Source=previous, width_nm=channel['width_nm'],
                clearance_nm=channel['clearance_nm'], current_authority=False,
                GPIO_application_mode_or_high_impedance_assumed=False)


def _copper(item, face):
    """Actual flashed copper minus the physical hole, not a pad/body bbox."""
    result = pcbnew.SHAPE_POLY_SET()
    if not item.IsOnLayer(face):
        return result
    if item.GetClass() in ('PAD', 'PCB_VIA') and not item.FlashLayer(face):
        return result
    if item.GetClass() == 'PCB_VIA':
        _need(item.GetViaType() == pcbnew.VIATYPE_THROUGH
              and item.TopLayer() == pcbnew.F_Cu and item.BottomLayer() == pcbnew.B_Cu
              and 0 < item.GetDrillValue() < item.GetWidth(face),
              'sideband_tap_actual_normal_retained_barrel_required')
    item.TransformShapeToPolygon(result, face, 0, 1, pcbnew.ERROR_INSIDE, False)
    if item.GetClass() == 'PCB_VIA' or item.GetClass() == 'PAD' and item.HasHole():
        hole = pcbnew.SHAPE_POLY_SET()
        item.GetEffectiveHoleShape().TransformToPolygon(hole, 1, pcbnew.ERROR_OUTSIDE)
        result.BooleanSubtract(hole)
    return result


def _contact(first, second, face):
    area = _copper(first, face)
    area.BooleanIntersection(_copper(second, face))
    return area.Area() if area.OutlineCount() else 0


def _local_group_delta(source, candidate):
    """Exact incoming-only factory membership, never general group authority."""
    import cec_additive_route_receiving as additive
    import cec_fr as fr
    _, old = additive._nodes(source)
    _, new = additive._nodes(candidate)
    name = '"' + fr.LOCAL_POFV_SIGNAL_VIA_GROUP + '"'
    groups = [[u for u, n in rows.items() if n[0] == 'group' and n[1] == name]
              for rows in (old, new)]
    _need(all(len(g) <= 1 for g in groups), 'ambiguous_sideband_local_factory_group')
    if not groups[1]:
        _need(not groups[0], 'sideband_local_factory_group_removed')
        return set(), set()
    uid = groups[1][0]; node = new[uid]
    _need(all(isinstance(n, list) and n and n[0] in ('uuid', 'members')
              for n in node[2:]), 'sideband_local_factory_group_opaque_fields')
    members = additive._members(node)
    if groups[0]:
        _need(groups[0] == [uid] and additive._without(old[uid], 'members')
              == additive._without(node, 'members')
              and additive._members(old[uid]) <= members,
              'sideband_local_factory_Source_members_changed')
        members = members - additive._members(old[uid])
        if not members:
            _need(old[uid] == node, 'sideband_local_factory_Source_group_changed')
            return set(), set()
    _need(members and members <= new.keys() - old.keys()
          and all(new[u][0] == 'via' for u in members),
          'sideband_local_factory_only_incoming_vias_required')
    return {uid}, members


def _source_local_via(parent, source, via, tracks, width, deadline):
    """Source-clamped process plus actual Source SMD/dogbone provenance."""
    import cec_fab_profile as fab
    _tick(deadline)
    profile_name = fab.board_profile_name(parent)
    profile = fab.get_profile(profile_name) if profile_name else None
    _need(profile and profile.get('pofv') is True, 'sideband_Source_POFV_profile_required')
    geometry = (int(via.GetWidth(pcbnew.F_Cu)), int(via.GetDrillValue()))
    menu = {(round(d*1e6), round(h*1e6)) for d, h in
            fab.local_pofv_geometry_candidates(profile, minimum_web_nm=width, board=parent)}
    _need(geometry in menu, 'sideband_local_via_outside_Source_clamped_menu')
    # Only checked incoming limbs are projected. No child pad, group, fill or
    # Source verdict is imported, and numeric netcodes are independently bound.
    projection = pcbnew.LoadBoard(str(source))
    code = next((p.GetNetCode() for f in projection.GetFootprints() for p in f.Pads()
                 if p.GetNetname() == via.GetNetname()), 0)
    _need(code > 0, 'sideband_local_Source_net_binding_required')
    for item in tracks:
        _tick(deadline)
        t = pcbnew.PCB_TRACK(projection); t.SetStart(item.GetStart()); t.SetEnd(item.GetEnd())
        t.SetWidth(item.GetWidth()); t.SetLayer(item.GetLayer()); t.SetNetCode(code)
        projection.Add(t)
    v = pcbnew.PCB_VIA(projection); v.SetPosition(via.GetPosition())
    v.SetWidth(geometry[0]); v.SetDrill(geometry[1]); v.SetNetCode(code)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetViaType(pcbnew.VIATYPE_THROUGH)
    valid, reason = fab.local_pofv_via_decision(projection, v)
    _need(valid is True, 'sideband_local_Source_SMD_provenance_refused:' + str(reason))
    _tick(deadline)
    return dict(diameter_nm=geometry[0], drill_nm=geometry[1], provenance=reason,
                Source_profile=profile_name, Source_clamped_menu_nm=sorted(menu))


def _source_objects(source, candidate, parent, local_groups=()):
    """Only generated GND fill children may await independent native replay.

    Every non-Ground object stays byte exact. Existing actual Ground zones
    retain every authored AST field; the shared saved receiver, not this
    preliminary comparison, recomputes and proves their generated fills.
    """
    import cec_source_literal_additions as literal
    import cec_additive_route_receiving as additive
    old = literal._inventory(source.read_text())[0]
    new = literal._inventory(candidate.read_text())[0]
    _need(old.keys() <= new.keys(), 'sideband_tap_cannot_retire_Source_objects')
    ground = {force._uid(z) for z in parent.Zones()
              if z.GetNetname() == 'GND' and not z.GetIsRuleArea()}
    changed = {u for u in old if old[u][2] != new[u][2]}
    _need(changed <= ground | set(local_groups), 'sideband_tap_all_nonGround_Source_objects_exact_required')
    changed -= set(local_groups)
    if changed:
        _, old_nodes = additive._nodes(source)
        _, new_nodes = additive._nodes(candidate)
        _need(all(old_nodes[u][0] == new_nodes[u][0] == 'zone'
                  and additive._without(old_nodes[u], 'filled_polygon')
                  == additive._without(new_nodes[u], 'filled_polygon') for u in changed),
              'sideband_tap_Ground_authored_fields_changed')
    return old, new, sorted(changed)


def _live_bindings(proof, epoch, families, source, candidate, board_hint, deadline):
    binding = proof['canonical_Source']
    _need(all(force._hash(Path(p)) == h for p,h in {
        **binding['schematic_files_sha256'], **binding['role_records_sha256']}.items())
        and force._hash(Path(binding['exporter']['exporter'])) == binding['exporter']['exporter_sha256'],
        'sideband_tap_canonical_Source_role_or_exporter_changed')
    _need(epoch == force._code_identity()
          and families == [force._family(p, board_hint) for p in (source, candidate)],
          'sideband_tap_saved_Source_candidate_or_code_changed')
    _tick(deadline)


def receive(source, candidate, *, board_hint, connector_pad_uuids,
            target_pad_uuid, timeout_s=10., allow_source_local_pofv=False,
            staged_receiving=False):
    """Exact saved receiving; explicit staging uses TWO <=10s constituents.

    Stage1 must finish Source/geometry/field plus fresh binding barrier before
    stage2 starts independent saved replay/partitions. No failed stage is rescued
    by another lease. Legacy default retains its original ONE shared deadline.
    ``staged_receiving`` grants no local-via/process permission; the independent
    ``allow_source_local_pofv`` opt-in retains its existing two-stage behavior.
    """
    _need(type(timeout_s) in (int, float) and math.isfinite(timeout_s)
          and 0 < timeout_s <= 10., 'bounded_sideband_tap_receiving_lease_required')
    _need(type(allow_source_local_pofv) is bool, 'explicit_sideband_local_POFV_mode_required')
    _need(type(staged_receiving) is bool, 'explicit_sideband_staged_receiving_mode_required')
    composed = staged_receiving or allow_source_local_pofv
    stage_start = time.monotonic(); deadline = stage_start + timeout_s
    stage = 'Source_geometry_field'
    result = dict(scope='Source_typed_digital_sideband_monitor_tap', ok=False, complete=False,
                  errors=[], ordinary_reclassification=False, quiet_reclassification=False,
                  new_current_budget=False, current_qualified=False, voltage_qualified=False,
                  barrel_qualified=False, inherited_footprint_qualified=False,
                  release_authority=False, routing_admitted=False, whole_shared_stage_still_required=True)
    result.update(bounded_receiving_stages=2 if composed else 1,
                  each_stage_lease_s=timeout_s,
                  composed_budget_s=timeout_s*(2 if composed else 1), stage_timings_s={},
                  staged_receiving=staged_receiving,
                  allow_source_local_pofv=allow_source_local_pofv,
                  completed_receiving_stages=[], failed_stage=None)
    try:
        import cec_additive_route_receiving as additive
        import cec_source_literal_additions as literal
        import cec_native_partition_pair as partitions
        import cec_fr as fr
        import cec_route_dimensions as dimensions
        from cec_route_proposal_guard import RouteProposalGuard
        source, candidate = [Path(p).resolve(strict=True) for p in (source, candidate)]
        _need(source != candidate and type(board_hint) is str and board_hint,
              'distinct_saved_sideband_tap_paths_and_design_required')
        epoch = force._code_identity()
        families = [force._family(p, board_hint) for p in (source, candidate)]
        parent, child = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
        proof = compile_source(parent, source, board_hint=board_hint,
                               connector_pad_uuids=connector_pad_uuids,
                               target_pad_uuid=target_pad_uuid, deadline=deadline)
        result['independently_compiled_Source_scope'] = proof
        net = proof['net']; code = parent.GetNetcodeFromNetname(net)
        local_groups, local_members = (_local_group_delta(source, candidate)
            if allow_source_local_pofv else (set(), set()))
        old, new, ground_changes = _source_objects(source, candidate, parent, local_groups)
        result['new_factory_group_uuids'] = sorted(local_groups - old.keys())
        result['extended_factory_group_uuids'] = sorted(local_groups & old.keys())
        result['factory_group_delta_uuids'] = sorted(local_groups)
        result['generated_Ground_fill_changes_requiring_independent_replay'] = ground_changes
        incoming = new.keys() - old.keys() - local_groups
        items = [t for t in child.GetTracks() if force._uid(t) in incoming]
        _need(1 <= len(items) <= 32 and {force._uid(t) for t in items} == incoming,
              'only_bounded_new_sideband_tap_copper_required')
        names = literal.incoming_copper_nets(candidate.read_text(), incoming)
        _need(set(names) == incoming and all(n == net for n in names.values()),
              'literal_sideband_tap_target_net_changed')
        resolver = fr._project_netclass_resolver(str(source), board=parent)
        spec = resolver(net) or {}
        allowed = fr._lastmile_route_layers(parent, net_name=net, spec=spec, exclude_front=False)
        enabled = tuple(map(int, parent.GetEnabledLayers().CuStack()))
        gap = proof['clearance_nm']; width = proof['width_nm']
        ops = []; cache = {}; holes = fr._via_hole_snapshot(parent); vias = []
        # Tracks must pass before any incoming dogbone may fund local ownership.
        items.sort(key=lambda item: item.GetClass() != 'PCB_TRACK')
        checked_tracks = []
        for item in items:
            _tick(deadline)
            local = force._uid(item) in local_members
            group = item.GetParentGroup()
            _need(item.GetNetname() == net and
                  ((local and group is not None and item.IsLocked()
                    and any(force._uid(g) in local_groups and g.ContainsItem(item) for g in child.Groups()))
                   or (not local and group is None and not item.IsLocked())),
                  'unowned_actual_sideband_tap_copper_required')
            if item.GetClass() == 'PCB_TRACK':
                a, z = tuple(item.GetStart()), tuple(item.GetEnd())
                dx, dy = abs(a[0]-z[0]), abs(a[1]-z[1])
                _need(a != z and (dx == 0 or dy == 0 or dx == dy)
                      and item.GetWidth() == width and int(item.GetLayer()) in allowed
                      and not item.HasSolderMask(), 'authored_octilinear_sideband_tap_track_required')
                _need(fr._edge_leg_clear(parent, item.GetStart(), item.GetEnd(), (width+1)//2+gap)
                      and fr._tap_foreign_clear(parent, item.GetStart(), item.GetEnd(), width,
                          int(item.GetLayer()), gap, {code}, foreign_cache=cache),
                      'sideband_tap_track_native_clearance_refused')
                ops.append(('trk', item.GetStart(), item.GetEnd(), width, int(item.GetLayer())))
                checked_tracks.append(item)
            else:
                _need(item.GetClass() == 'PCB_VIA' and item.GetViaType() == pcbnew.VIATYPE_THROUGH
                      and item.TopLayer() == pcbnew.F_Cu and item.BottomLayer() == pcbnew.B_Cu,
                      'only_normal_through_sideband_tap_vias_supported')
                vias.append(item)
                _need(len(vias) <= 2 and spec.get('via_diameter') and spec.get('via_drill'),
                      'at_most_two_authored_normal_sideband_tap_vias_required')
                dia, drill = int(item.GetWidth(pcbnew.F_Cu)), int(item.GetDrillValue())
                klass = parent.GetNetInfo().GetNetItem(code).GetNetClassSlow()
                _need(klass is not None, 'authoritative_sideband_tap_native_via_class_required')
                minimum = dict(spec, via_diameter=max(float(spec['via_diameter']), klass.GetViaDiameter()/1e6),
                               via_drill=max(float(spec['via_drill']), klass.GetViaDrill()/1e6))
                required_dia, required_drill = dimensions.ordinary_via_geometry(
                    minimum, dimensions.board_limits(parent), requested=(dia/1e6, drill/1e6))
                if local:
                    result.setdefault('Source_local_POFV_vias', {})[force._uid(item)] = _source_local_via(
                        parent, source, item, checked_tracks, width, deadline)
                _need(drill > 0 and dia > drill and (local or (dia >= round(required_dia*1e6)
                      and drill >= round(required_drill*1e6)))
                      and all(int(item.GetWidth(face)) == dia for face in enabled),
                      'sideband_tap_normal_via_below_Source_absolute_or_class_floor')
                at = item.GetPosition()
                _need(fr._edge_leg_clear(parent, at, at, (dia+1)//2+gap)
                      and fr._via_spot_clear(parent, at, dia, gap, {code}, drill_nm=drill,
                          net_code=code, foreign_cache=cache, _via_holes=holes)
                      and all(fr._tap_foreign_clear(parent, at, at, dia, face, gap,
                          {code}, foreign_cache=cache) for face in enabled),
                      'sideband_tap_normal_via_all_face_hole_or_field_guard_refused')
                for other in vias[:-1]:
                    distance = math.dist(tuple(at), tuple(other.GetPosition()))
                    _need(distance >= (drill+other.GetDrillValue())/2
                          + parent.GetDesignSettings().m_HoleToHoleMin,
                          'sideband_tap_new_via_hole_spacing_refused')
                ops.append(('via', at, drill/1e6, dia/1e6))
        _need(sum(t.GetLength() for t in items if t.GetClass() == 'PCB_TRACK') <= 200000000,
              'bounded_sideband_tap_span_required')
        before, after = [feed._parts(b, net, deadline) for b in (parent, child)]
        _need(len(before) == 2 and len(after) == 1
              and after[0] == set().union(*before) | set(incoming),
              'exact_stranded_monitor_land_join_required')
        target = next(p for fp in child.GetFootprints() for p in fp.Pads()
                      if force._uid(p) == target_pad_uuid)
        graph = pcbnew.CONNECTIVITY_DATA()
        for item in [target, *items]:
            _tick(deadline)
            _need(graph.Add(item), 'sideband_tap_incoming_chain_graph_unknown')
        reached = {force._uid(target)} | {force._uid(t) for t in graph.GetConnectedItems(target)}
        _need(set(incoming) <= reached, 'sideband_tap_incoming_material_not_one_target_chain')
        front = [dict(uuid=force._uid(t), area_nm2=_contact(t, target, pcbnew.F_Cu)) for t in items]
        _need(any(r['area_nm2'] > 0 for r in front), 'sideband_tap_actual_front_land_contact_required')
        backbone = [i for fp in parent.GetFootprints() for i in fp.Pads()
                    if force._uid(i) in proof['retained_backbone_uuids']]
        backbone += [i for i in parent.GetTracks() if force._uid(i) in proof['retained_backbone_uuids']]
        contacts = []
        for item in items:
            for retained in backbone:
                for face in enabled:
                    _tick(deadline)
                    area = _contact(item, retained, face)
                    if area > 0:
                        contacts.append(dict(incoming_uuid=force._uid(item), retained_uuid=force._uid(retained),
                                             retained_class=retained.GetClass(), layer=face, area_nm2=area))
        _need(contacts, 'sideband_tap_actual_drill_subtracted_Source_backbone_contact_required')
        result['actual_Source_backbone_contacts'] = contacts
        result['actual_front_monitor_contacts'] = [r for r in front if r['area_nm2'] > 0]
        guard = RouteProposalGuard(parent, net, board_path=str(source), netclass_resolver=resolver,
                                   deadline=deadline, board_hint=board_hint,
                                   **(dict(preflight_s=min(10., max(.001, deadline-time.monotonic())))
                                      if composed else {}))
        accepted = guard(ops) is True
        result['native_route_proposal_guard'] = guard.report()
        _need(accepted, 'sideband_tap_full_native_route_proposal_guard_refused')
        _tick(deadline)
        if composed:
            _live_bindings(proof, epoch, families, source, candidate, board_hint, deadline)
            result['stage_timings_s'][stage] = time.monotonic() - stage_start
            # Only a positive, live first stage can reach this new constituent.
            _tick(deadline)
            result['completed_receiving_stages'].append(stage)
            stage = 'independent_saved_replay_partitions'
            stage_start = time.monotonic(); deadline = stage_start + timeout_s
        saved = additive.receive(source, candidate, board_hint=board_hint,
                                 timeout_s=min(10., deadline-time.monotonic()))
        result['exact_saved_additive_receiving'] = saved
        _need(saved.get('ok') is True and saved.get('complete') is True,
              'sideband_tap_exact_Source_plus_copper_not_received')
        _need(saved.get('existing_ground_fill_matches_independent_native_replay') is True,
              'sideband_tap_generated_Ground_fills_not_independently_recomputed')
        if allow_source_local_pofv:
            _need(set(saved.get('added_native_uuids', ())) == set(incoming) | (local_groups - old.keys()),
                  'sideband_local_saved_factory_delta_mismatch')
        _tick(deadline)
        shared = partitions.compare(parent, child, timeout_s=min(10., deadline-time.monotonic()))
        _need(shared['available'] and shared['preserved'], 'sideband_tap_lost_retained_Source_partition')
        result['whole_native_Source_partitions'] = {k:v for k,v in shared.items()
            if k not in ('source_parts', 'child_parts', 'demoted_parts')}
        _live_bindings(proof, epoch, families, source, candidate, board_hint, deadline)
        result['stage_timings_s'][stage] = time.monotonic() - stage_start
        result['completed_receiving_stages'].append(stage)
        result.update(ok=True, complete=True, source_components=2, candidate_components=1,
                      added_native_uuids=sorted(incoming), new_normal_vias=len(vias)-len(local_members),
                      new_local_vias=len(local_members),
                      only_requested_monitor_island_joined=True)
    except Exception as exc:
        result['stage_timings_s'][stage] = time.monotonic() - stage_start
        result['failed_stage'] = stage
        result['errors'].append(type(exc).__name__ + ':' + str(exc))
    return result
