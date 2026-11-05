"""Source-declared local supply allocations with one physical trunk tap.

The aggregate rail is never reduced. A generated group's declaration is only
a proposal: the actual native board must prove an exclusive, manufacturer-
typed consumer island, unchanged other-terminal partitions after removal,
and all outside copper contacts inside one real terminal's landing aperture.
Its exact proposed tracks and positively proved exclusive retained island
receive the existing local conductor allowance. Shared-rail copper does not.
This is steady conductor sizing, not inrush, barrel or release qualification.
"""
import math
import copy
import os
import re
import time
import uuid

import pcbnew
import cec_board_policy as policy
import cec_device_power_roles as roles
import cec_fab_profile as fab
import cec_force_current as force
import cec_route_dimensions as dimensions

PREFIX = 'CEC_LOCAL_SUPPLY_ALLOCATION_V1|'
# A legal reconstruction can replace a single legacy segment with multiple
# canonical bends. Keep the native island finite without making its already
# declared budget depend on a 32-item serialization accident. All load,
# capacitor, tap, ownership and deadline proofs below remain mandatory.
MAX_RETAINED_ISLAND_ITEMS = 128


def selected_bypass_contract(fp, *, allow_pass_through_input_bulk=False):
    """Exact source-selected passive identity, never a numeric load allowance.

    Preserve the original 100 nF selector. A separately selected 10 uF input
    bulk is supported only for an already typed pass-through input. This
    grants no leakage, stored-energy, inrush, fault or thermal qualification;
    the existing design allocation and whole native island proof still own
    all conductor sizing. An arbitrary capacitor/value is not a bypass model.
    """
    from cec_footprint_fields import footprint_properties
    if type(allow_pass_through_input_bulk) is not bool:
        raise ValueError('explicit_selected_input_bulk_context_required')
    props=footprint_properties(fp);mpn=props.get('MPN');value=fp.GetValue().replace(' ','').lower()
    package=fp.GetFPIDAsString()
    if (mpn=='CL05B104KO5NNNC' and re.search(r'(?:^|:)C_0402_1005Metric$',package)
            and value in ('100nf','0.1uf','100n')):
        return dict(mpn=mpn,role='selected_local_bypass',pass_through_input_bulk=False,
            electrical_or_transient_qualified=False,release_authority=False)
    if (allow_pass_through_input_bulk and mpn=='CL21A106KAYNNNE'
            and props.get('Manufacturer')=='Samsung'
            and re.search(r'(?:^|:)C_0805_2012Metric$',package)
            and value in ('10uf','10µf','10μf','10000nf')):
        return dict(mpn=mpn,role='selected_pass_through_input_bulk',pass_through_input_bulk=True,
            source='https://product.samsungsem.com/cn/mlcc/CL21A106KAYNNN.do',
            specification='https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/5545/CL21A106KAYNNNE%20Spec.pdf',
            nominal_capacitance_f=10e-6,rated_voltage_v=25.,dielectric='X5R',
            existing_input_conductor_allocation_unchanged=True,
            leakage_inrush_fault_and_thermal_qualified=False,
            electrical_or_transient_qualified=False,release_authority=False)
    return None


def _uid(item):
    return str(item.m_Uuid.AsString())


def _number(value, label):
    if (type(value) not in (int, float) or not math.isfinite(value) or value <= 0):
        raise ValueError('invalid_consumer_' + label)
    return float(value)


def _declarations(board_hint):
    rows = (policy.load(board_hint).get('params') or {}).get('supply_consumer_allocations', [])
    if (type(rows) is not list or len(rows) > 16 or any(type(r) is not dict for r in rows)):
        raise ValueError('bounded_explicit_consumer_allocations_required')
    expected = {'net', 'device_package', 'pin', 'amps', 'maximum_consumers', 'basis'}
    if any(set(r) != expected or any(type(r[k]) is not str or not r[k]
            for k in ('net', 'device_package', 'pin', 'basis')) or
            r['maximum_consumers'] != 1 or type(r['maximum_consumers']) is not int for r in rows):
        raise ValueError('explicit_single_consumer_design_allocation_required')
    if len({(r['net'], r['device_package'], r['pin']) for r in rows}) != len(rows):
        raise ValueError('duplicate_consumer_allocation')
    for row in rows:
        _number(row['amps'], 'allocation_current')
    return rows


def contract(board, pad_uuid, *, board_hint):
    """No branch current inferred from rail names, ratings or equal sharing."""
    from cec_synth_pipeline import spec_net_current_contract
    import cec_current_topology as topology
    board_hint = os.environ.get('CEC_THERMAL_BOARD_HINT') or board_hint
    pads = [p for f in board.GetFootprints() for p in f.Pads() if _uid(p) == pad_uuid]
    if len(pads) != 1:
        raise ValueError('unique_consumer_supply_land_required')
    root = pads[0]; fp = root.GetParentFootprint(); model = roles.footprint_contract(fp)
    if (fp.IsDNP() or not model or root.HasHole() or root.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
            or model['pins'].get(str(root.GetNumber())) != 'power_input'):
        raise ValueError('selected_manufacturer_consumer_supply_required')
    selected = [r for r in _declarations(board_hint) if r['net'] == root.GetNetname()
        and r['device_package'] == model['device_package'] and r['pin'] == root.GetNumber()]
    if len(selected) != 1:
        raise ValueError('unique_existing_local_allowance_required')
    declaration = selected[0]
    # Only positively modeled consumers and pass-through inputs qualify.
    # Conversion losses, regulator inputs, enable pins and other variants
    # cannot acquire a budget from a similar rail or displayed family.
    passthrough = model['device_package'] == 'TPS2121 RUX' and root.GetNumber() in ('2', '7')
    if not passthrough and (model['device_package'] != 'TJA1051T/3 SO8' or root.GetNumber() != '3'):
        raise ValueError('consumer_static_load_model_unavailable')
    consumers = []
    for owner in board.GetFootprints():
        if owner.IsDNP(): continue
        witness = roles.footprint_contract(owner)
        if witness and witness['device_package'] == model['device_package']:
            consumers.extend(p for p in owner.Pads() if p.GetNumber() == root.GetNumber()
                and p.GetNetCode() == root.GetNetCode())
    if len(consumers) != 1 or _uid(consumers[0]) != pad_uuid:
        raise ValueError('single_consumer_allocation_would_be_reused')
    domain = topology.board_current_domains(board, board_hint).get(root.GetNetname())
    if domain and (not passthrough or not domain.get('complete')
            or fp.GetReference() in domain.get('authority_refs', ())):
        raise ValueError('aggregate_force_domain_cannot_be_consumer_allocated')
    rail = spec_net_current_contract(board_hint, root.GetNetname())
    if not rail or rail.get('source') != 'board_design_basis':
        raise ValueError('unchanged_explicit_shared_supply_authority_required')
    amps = _number(declaration['amps'], 'allocation_current')
    flow = None
    if passthrough:
        from cec_pass_through_current import input_bound
        if not re.search(r'(?:^|:)RUX0012A$', fp.GetFPIDAsString()):
            raise ValueError('selected_pass_through_package_required')
        outputs = [p for p in fp.Pads() if p.GetNumber() in ('1', '8')]
        if (len(outputs) != 2 or {p.GetNumber() for p in outputs} != {'1', '8'}
                or len({p.GetNetname() for p in outputs}) != 1
                or any(p.GetNetCode() <= 0 or p.GetNetCode() == root.GetNetCode() for p in outputs)):
            raise ValueError('one_distinct_manufacturer_common_output_net_required')
        output_net = outputs[0].GetNetname()
        output = spec_net_current_contract(board_hint, output_net)
        flow = input_bound(model, root.GetNumber(), output)
        if any(rail.get(k) != output.get(k) for k in ('geometry_margin', 'margin_included')):
            raise ValueError('input_output_design_margin_semantics_mismatch')
        minimum = flow['minimum_declared_input_a']
        flow = dict(flow, output_net=output_net,
            output_pad_uuids=sorted(_uid(p) for p in outputs),
            aggregate_force_terminal_exemption_granted=False)
    else:
        # NXP TJA1051 Rev 9 table 7, including the specified CAN short.
        minimum = .110
    if not minimum <= amps < _number(rail['amps'], 'aggregate_current'):
        raise ValueError('declared_local_allowance_below_consumer_or_not_local')
    current = dict(rail, amps=amps, source='board_design_basis_consumer_allocation',
        consumer_allocation_basis=declaration['basis'])
    profile = fab.active_profile_name(board, hint=board_hint)
    if not profile:
        raise ValueError('consumer_declared_copper_profile_required')
    resolver = dimensions.project_resolver(str(board.GetFileName() or board_hint), board=board)
    spec = resolver(root.GetNetname()) or {}
    project = _number(spec.get('track_width'), 'project_width')
    ipc = dimensions.current_trace_widths(current, fab.enabled_copper_layers(board), profile, rise_c=30.)
    widths = {layer: max(width, project, dimensions.board_limits(board)['track_width'])
        for layer, width in ipc.items()}
    aggregate_widths=dimensions.current_trace_widths(rail,fab.enabled_copper_layers(board),profile,rise_c=30.)
    ordinary_diameter,ordinary_drill=dimensions.ordinary_via_geometry(spec,dimensions.board_limits(board))
    return dict(root_pad_uuid=pad_uuid, net=root.GetNetname(), declaration=declaration,
        copper_profile=profile,
        current_authority=current, aggregate_current_authority=dict(rail),
        required_by_layer_mm=widths, aggregate_required_by_layer_mm=aggregate_widths,
        ordinary_tap_geometry_mm=[ordinary_diameter,ordinary_drill],manufacturer=model,
        consumer_static_max_a=minimum, pass_through_input_bound=flow,
        manufacturer_revision=flow['manufacturer_revision'] if flow else '9',
        manufacturer_table=flow['manufacturer_table'] if flow else '7',
        static_conditions=flow['manufacturer_conditions'] if flow else
            'Tvj -40..150 C; VCC 4.5..5.5 V; specified CAN bus short -3..18 V',
        inrush_fault_barrel_and_release_qualified=False, release_authority=False)


def _graph(items, deadline):
    if len(items) > 4096:
        raise ValueError('consumer_native_inventory_bound')
    graph = pcbnew.CONNECTIVITY_DATA()
    for item in items:
        if time.monotonic() >= deadline or not graph.Add(item):
            raise ValueError('consumer_native_graph_unknown')
    return graph


def _partitions(pads, graph, deadline):
    pending = {_uid(p): p for p in pads}; result = []
    while pending:
        if time.monotonic() >= deadline:
            raise ValueError('consumer_partition_deadline')
        uid = min(pending); root = pending[uid]
        reached = {uid} | {_uid(i) for i in graph.GetConnectedItems(root)}
        own = set(pending) & reached; result.append(tuple(sorted(own)))
        for u in own: del pending[u]
    return sorted(result)


def _island(board, root, graph, native, deadline, *, additional_native_uuids=()):
    from cec_footprint_fields import footprint_properties
    if (not isinstance(additional_native_uuids, (list, tuple)) or len(additional_native_uuids) > 16
            or len(set(additional_native_uuids)) != len(additional_native_uuids)):
        raise ValueError('bounded_exact_retained_consumer_island_roots_required')
    members = {_uid(root)} | {_uid(i) for i in graph.GetConnectedItems(root)}
    for uid in additional_native_uuids:
        if time.monotonic() >= deadline:
            raise ValueError('consumer_island_deadline')
        if uid not in native or native[uid].GetClass() not in ('PAD', 'PCB_TRACK', 'PCB_VIA'):
            raise ValueError('retained_consumer_island_native_material_missing')
        members |= {uid} | {_uid(i) for i in graph.GetConnectedItems(native[uid])}
        if len(members) > MAX_RETAINED_ISLAND_ITEMS:
            raise ValueError('bounded_retained_consumer_island_required')
    if not 1 <= len(members) <= MAX_RETAINED_ISLAND_ITEMS or not members <= native.keys():
        raise ValueError('bounded_retained_consumer_island_required')
    model = roles.footprint_contract(root.GetParentFootprint())
    allowed = {'GND'}; caps = set(); monitors = []
    if model and model['device_package'] == 'TJA1051T/3 SO8':
        if additional_native_uuids:
            raise ValueError('existing_consumer_scope_cannot_borrow_pass_through_bypass_roots')
        vio = root.GetParentFootprint().FindPadByNumber('5')
        if vio is None or vio.GetNetCode() <= 0 or vio.GetNetCode() == root.GetNetCode():
            raise ValueError('distinct_manufacturer_io_supply_required')
        allowed.add(str(vio.GetNetname()))
    elif not model or model['device_package'] != 'TPS2121 RUX':
        raise ValueError('selected_consumer_island_model_required')
    for uid in members:
        if time.monotonic() >= deadline:
            raise ValueError('consumer_island_deadline')
        item = native[uid]; kind = item.GetClass()
        if kind == 'PAD' and uid != _uid(root):
            fp = item.GetParentFootprint(); props = footprint_properties(fp); pins = list(fp.Pads())
            if model['device_package'] == 'TPS2121 RUX':
                import cec_resistive_monitor_branch as monitor
                if monitor.resistor_contract(fp) is not None:
                    # A resistor's presence is not a load model. Re-type its
                    # entire closed divider and its selected manufacturer
                    # endpoint. It must monitor THIS exact input, not another
                    # device or merely a rail with a similar name.
                    proof = monitor.source_contract(board, uid, deadline=deadline)
                    if (proof['associated_supply_pad_uuid'] != _uid(root)
                            or proof['net'] != root.GetNetname()
                            or proof['numeric_rail_load_budget_modified'] is not False):
                        raise ValueError('consumer_monitor_not_same_manufacturer_input')
                    monitors.append(proof)
                    if len(monitors) > 2:
                        raise ValueError('bounded_same_input_monitor_loads_required')
                    continue
            # Only exact selected bypass identities may enter the island.
            # The bulk selector is restricted to this actual pass-through
            # input model; it never guesses an IC load or changes its budget.
            selected=selected_bypass_contract(fp,
                allow_pass_through_input_bulk=model['device_package']=='TPS2121 RUX')
            if (fp.IsDNP() or selected is None
                    or len(pins) != 2 or any(p.HasHole() or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD for p in pins)
                    or any(p.GetNetCode() <= 0 for p in pins)):
                raise ValueError('consumer_island_has_unowned_or_unknown_load')
            other = next(p for p in pins if _uid(p) != uid)
            if str(other.GetNetname()) not in allowed:
                raise ValueError('consumer_capacitor_cross_rail_not_selected_io_supply')
            caps.add(_uid(fp))
        elif kind not in ('PAD', 'PCB_TRACK', 'PCB_VIA'):
            raise ValueError('consumer_island_zone_or_unowned_material')
    if len(caps) > 2:
        raise ValueError('bounded_manufacturer_local_bypass_island_required')
    return members, sorted(monitors, key=lambda p:p['pad_uuid'])


def _with_closed_monitor_loads(board, budget, monitors):
    """Add proved divider loads; never silently spend the device allowance.

    The existing consumer declaration and aggregate rail envelope stay exact.
    Only a complete physically exclusive island can use this derived branch
    current. The source policy's margin applies once to the complete sum;
    capacitive inrush, fault, barrel and release qualification remain unknown.
    """
    if not monitors:
        return budget
    if (not budget['pass_through_input_bound'] or not 1 <= len(monitors) <= 2
            or len({q['pad_uuid'] for q in monitors}) != len(monitors)):
        raise ValueError('bounded_unique_pass_through_monitor_loads_required')
    extra = math.fsum(_number(q['current_upper_bound_a'], 'closed_monitor_current') for q in monitors)
    amps = math.fsum((budget['current_authority']['amps'], extra))
    if not budget['current_authority']['amps'] < amps < budget['aggregate_current_authority']['amps']:
        raise ValueError('monitor_sum_must_remain_a_strict_local_branch')
    current = dict(budget['current_authority'], amps=amps,
        derivation='existing_single_consumer_allowance_plus_closed_same_input_monitor_bounds')
    ipc = dimensions.current_trace_widths(current, tuple(budget['required_by_layer_mm']),
        budget['copper_profile'], rise_c=30.)
    result = copy.deepcopy(budget)
    result.update(base_consumer_current_authority=copy.deepcopy(budget['current_authority']),
        current_authority=current,
        required_by_layer_mm={layer:max(width,budget['required_by_layer_mm'][layer])
            for layer,width in ipc.items()},
        closed_monitor_loads=copy.deepcopy(monitors),additional_monitor_current_bound_a=extra,
        existing_consumer_declaration_unchanged=True,aggregate_current_budget_modified=False)
    return result


def record(board, tracks, vias, *, root_pad_uuid, anchor_uuid):
    """Record exact proposed NEW tracks; the saved native proof is separate.

    Vias retain their own ordinary/POFV fabrication groups. Their UUIDs in the
    declaration are not an ownership or capacity waiver; receive retypes them.
    """
    if not 1 <= len(tracks) <= 128 or len(vias) > 8:
        raise ValueError('bounded_consumer_route_group_required')
    for uid in (root_pad_uuid, anchor_uuid, *map(_uid, vias)): uuid.UUID(uid)
    group = pcbnew.PCB_GROUP(board)
    group.SetName(PREFIX + '|'.join((root_pad_uuid, anchor_uuid, ','.join(sorted(map(_uid, vias))))))
    for item in tracks:
        if item.GetClass() != 'PCB_TRACK' or item.GetParentGroup() is not None:
            raise ValueError('exact_ungrouped_consumer_tracks_required')
        group.AddItem(item)
    board.Add(group)
    return group


def stale_anchor_annotation_plan(board, group_uuid, *, board_hint, timeout_s=2.):
    """Identify only an already invalid annotation whose anchor disappeared.

    This permits retiring a dead proposal label, never any physical copper,
    live allocation or current authority. The source root, exact members and
    all declared barrels must still exist. Other refusals require a different
    repair; neither this plan nor deletion restores a missing electrical tap.
    """
    if type(timeout_s) not in (int,float) or not 0 < timeout_s <= 10:
        raise ValueError('bounded_stale_annotation_receiving_required')
    deadline=time.monotonic()+timeout_s
    groups=[g for g in board.Groups() if _uid(g)==group_uuid]
    if len(groups)!=1 or not groups[0].GetName().startswith(PREFIX):
        raise ValueError('one_exact_native_consumer_annotation_required')
    group=groups[0];parts=group.GetName()[len(PREFIX):].split('|')
    if len(parts)!=3:raise ValueError('stale_annotation_name_invalid')
    root,anchor,via_csv=parts;vias=via_csv.split(',') if via_csv else []
    for u in (root,anchor,*vias):uuid.UUID(u)
    native={_uid(i):i for i in [*(p for f in board.GetFootprints() for p in f.Pads()),*board.GetTracks(),*board.Zones()]}
    budget=contract(board,root,board_hint=board_hint)
    members=list(group.GetItems())
    if (anchor in native or not 1<=len(members)<=128 or len(vias)>8 or len(set(vias))!=len(vias)
            or any(_uid(i) not in native or i.GetClass()!='PCB_TRACK' or i.GetNetname()!=budget['net'] for i in members)
            or any(u not in native or native[u].GetClass()!='PCB_VIA' or native[u].GetNetname()!=budget['net'] for u in vias)
            or group.GetParentGroup() is not None):
        raise ValueError('only_missing_anchor_with_all_physical_branch_material_retained_required')
    try:
        _receive(board,group,board_hint=board_hint,deadline=deadline)
    except ValueError as exc:
        if str(exc)!='native_consumer_root_boundary_or_material_missing':raise
    else:raise ValueError('valid_current_allocation_annotation_cannot_be_retired')
    return dict(group_uuid=group_uuid,source_name=group.GetName(),missing_anchor_uuid=anchor,
        retained_root_uuid=root,retained_track_uuids=sorted(map(_uid,members)),retained_via_uuids=sorted(vias),
        source_annotation_already_invalid=True,physical_route_restored=False,
        aggregate_current_authority=budget['aggregate_current_authority'],release_authority=False)


def retire_stale_anchor_annotation(board, group_uuid, *, board_hint):
    plan=stale_anchor_annotation_plan(board,group_uuid,board_hint=board_hint)
    group=next(g for g in board.Groups() if _uid(g)==group_uuid)
    for item in list(group.GetItems()):group.RemoveItem(item)
    board.Delete(group)
    return plan


def _receive(board, group, *, board_hint, deadline):
    import cec_kelvin_copper_cut as cut
    name = group.GetName()[len(PREFIX):].split('|')
    if len(name) != 3:
        raise ValueError('consumer_group_identity_invalid')
    root_uid, anchor_uid, raw_vias = name
    via_ids = [] if not raw_vias else raw_vias.split(',')
    for uid in (root_uid, anchor_uid, *via_ids): uuid.UUID(uid)
    if len(via_ids) > 8 or len(set(via_ids)) != len(via_ids):
        raise ValueError('bounded_unique_consumer_barrels_required')
    budget = contract(board, root_uid, board_hint=board_hint)
    net = budget['net']; members = list(group.GetItems()); ids = set(map(_uid, members)) | set(via_ids)
    if not 1 <= len(members) <= 128 or len(ids) != len(members) + len(via_ids):
        raise ValueError('exact_bounded_consumer_group_inventory_required')
    native = {_uid(i): i for i in [*(p for f in board.GetFootprints() for p in f.Pads()),
        *board.GetTracks(), *[z for z in board.Zones() if not z.GetIsRuleArea()]] if i.GetNetname() == net}
    if not ids <= native.keys() or root_uid not in native or anchor_uid not in native or anchor_uid in ids:
        raise ValueError('native_consumer_root_boundary_or_material_missing')
    if any(i.GetClass() != 'PCB_TRACK' or i.GetNetname() != net for i in members):
        raise ValueError('consumer_group_has_unowned_track')
    if sum(i.GetLength() for i in members) > 160000000:
        raise ValueError('consumer_branch_length_bound')
    for uid in via_ids:
        via = native[uid]
        if via.GetClass() != 'PCB_VIA': raise ValueError('consumer_barrel_is_not_native_via')
        diameter, drill = via.GetWidth(via.TopLayer())/1e6, via.GetDrillValue()/1e6
        ordinary = dimensions.ordinary_via_geometry({}, dimensions.board_limits(board))
        if (diameter < ordinary[0] or drill < ordinary[1]) and not fab.local_pofv_via_decision(board, via)[0]:
            raise ValueError('consumer_barrel_factory_geometry_unqualified')
    base = {u: i for u, i in native.items() if u not in ids}
    projected = _graph(list(base.values()), deadline)
    new_consumer_roots = []
    if budget['pass_through_input_bound']:
        # New links may collect isolated selected bypasses and retained
        # pad-free source portals. Discover actual conductor contacts, never
        # proximity. Exclude the anchor's SOURCE component from island
        # discovery, not from the independent single-tap contact proof below.
        # Any second source island, IC, zone or unknown cap still fails the
        # complete native island retyping and unchanged trunk partitions.
        anchor_members = {anchor_uid} | {_uid(i) for i in projected.GetConnectedItems(base[anchor_uid])}
        discovered = {root_uid} | {_uid(i) for i in projected.GetConnectedItems(base[root_uid])}
        layers = tuple(map(int, board.GetEnabledLayers().CuStack()))
        for uid, item in base.items():
            if time.monotonic() >= deadline:
                raise ValueError('consumer_contact_discovery_deadline')
            if uid in anchor_members or uid in discovered or item.GetClass() not in ('PAD','PCB_TRACK','PCB_VIA'):
                continue
            contacted = False
            for new_uid in ids:
                for layer in layers:
                    if time.monotonic() >= deadline:
                        raise ValueError('consumer_contact_discovery_deadline')
                    if (item.IsOnLayer(layer) and native[new_uid].IsOnLayer(layer)
                            and item.GetEffectiveShape(layer).Collide(native[new_uid].GetEffectiveShape(layer), 0)):
                        contacted = True; break
                if contacted: break
            if contacted:
                new_consumer_roots.append(uid)
                discovered |= {uid} | {_uid(i) for i in projected.GetConnectedItems(item)}
                if len(new_consumer_roots) > 16 or len(discovered) > 32:
                    raise ValueError('new_pass_through_retained_contact_scope_bound')
    island, monitors = _island(board, base[root_uid], projected, base, deadline,
        additional_native_uuids=new_consumer_roots)
    budget = _with_closed_monitor_loads(board, budget, monitors)
    if anchor_uid in island:
        raise ValueError('consumer_not_an_exclusive_supply_leaf')
    full = _graph(list(native.values()), deadline)
    reached = {root_uid} | {_uid(i) for i in full.GetConnectedItems(native[root_uid])}
    if not ids | {anchor_uid} <= reached:
        raise ValueError('consumer_new_material_not_fully_connected')
    trunk_pads = [i for u, i in base.items() if u not in island and i.GetClass() == 'PAD']
    if len(trunk_pads) < 2 or _partitions(trunk_pads, projected, deadline) != _partitions(trunk_pads, full, deadline):
        raise ValueError('consumer_removal_changes_shared_terminal_partitions')
    # Count physical taps, not coincident track/via UUIDs. All contacts with
    # the shared rail must fit the ONE actual native terminal landing shape.
    # Using its outer silhouette here identifies a capture aperture only; the
    # native graph above proves continuity and grants no barrel current credit.
    anchor = native[anchor_uid]
    if anchor.GetClass() not in ('PAD', 'PCB_VIA','PCB_TRACK'):
        raise ValueError('native_terminal_single_tap_required')
    work = cut._Work(deadline); cache = {}; contacts = 0
    def shape(item, layer):
        key = (_uid(item), int(layer))
        if key not in cache:
            cache[key] = (cut._poly(item.GetFilledPolysList(layer), work)
                if item.GetClass() == 'ZONE' and item.IsFilled() else
                cut._shape(item, layer, False, work))
        return cache[key]
    capture=anchor;capture_mode='retained_native_terminal';tap_via=None
    if anchor.GetClass()=='PCB_TRACK':
        # A branch barrel may land directly on a retained full-rated rail
        # track. The ENTIRE track is never a tap aperture: all shared-rail
        # contacts must lie in this ONE independently identified, exact
        # ordinary-size new barrel. This avoids both a redundant covered
        # return to an old via and a two-tap undersized parallel trunk.
        layer=int(anchor.GetLayer());canonical=fab.COPPER_LAYER_IDS[layer]
        if anchor.GetWidth()<round(budget['aggregate_required_by_layer_mm'][canonical]*1e6):
            raise ValueError('consumer_track_tap_anchor_below_unchanged_shared_rail_requirement')
        options=[native[u] for u in via_ids if native[u].IsOnLayer(layer)
            and not shape(native[u],layer).intersection(shape(anchor,layer)).is_empty]
        if len(options)!=1:
            raise ValueError('consumer_track_tap_requires_one_actual_native_capture_barrel')
        capture=options[0];tap_via=_uid(capture);capture_mode='retained_track_single_ordinary_barrel'
        diameter,drill=budget['ordinary_tap_geometry_mm']
        if (capture.GetViaType()!=pcbnew.VIATYPE_THROUGH or capture.TopLayer()!=pcbnew.F_Cu
                or capture.BottomLayer()!=pcbnew.B_Cu
                or capture.GetWidth(capture.TopLayer())!=round(diameter*1e6)
                or capture.GetDrillValue()!=round(drill*1e6)
                or not anchor.GetEffectiveShape(layer).Collide(capture.GetPosition(),0)):
            raise ValueError('consumer_track_tap_requires_exact_ordinary_geometry_and_native_center_capture')
    layers = tuple(map(int, board.GetEnabledLayers().CuStack()))
    for uid in ids:
        item = native[uid]
        for other_uid, other in base.items():
            if other_uid in island: continue
            for layer in layers:
                work.tick()
                if not item.IsOnLayer(layer) or not other.IsOnLayer(layer): continue
                overlap = shape(item, layer).intersection(shape(other, layer))
                if overlap.is_empty: continue
                # Either operand's EXACT capture identity proves its own
                # intersection is a subset of that capture. A retained
                # barrel is the second operand, while a new capture barrel
                # is the first. Re-clipping either can make GEOS covers
                # disagree at a floating boundary vertex. This algebraic
                # identity does not apply to any OTHER native item: all of
                # its shared-rail contacts still need strict containment.
                # No buffer, tolerance, widened landing or current waiver.
                if not capture.IsOnLayer(layer) or (uid != _uid(capture)
                        and other_uid != _uid(capture)
                        and not shape(capture, layer).covers(overlap)):
                    raise ValueError('consumer_has_second_physical_shared_rail_tap:'
                        +uid+':'+other_uid+':'+fab.COPPER_LAYER_IDS[layer]+':'+_uid(capture))
                contacts += 1
    if not contacts:
        raise ValueError('consumer_has_no_physical_source_tap')
    requirements = {}
    for item in members:
        layer = fab.COPPER_LAYER_IDS[int(item.GetLayer())]
        floor = math.ceil(budget['required_by_layer_mm'][layer]*1e6)
        if item.GetWidth() < floor:
            raise ValueError('consumer_trace_below_allocated_current_or_project_floor')
        requirements[_uid(item)] = dict(current_authority=budget['current_authority'],
            required_mm=budget['required_by_layer_mm'][layer])
    # Removing the declared branch already proved this COMPLETE retained
    # island has exactly one selected consumer and only selected capacitors.
    # Applying the aggregate rail current to its old traces, while applying
    # the explicit local allowance to new traces in the SAME exclusive leaf,
    # makes rating depend on generation history rather than native topology.
    # Do not include pads, barrels, the capture terminal or any shared trunk.
    # Old undersized material remains a fault at the actual local floor;
    # these requirements are not an inherited-width or current waiver.
    island_requirements={}
    for uid in sorted(island):
        work.tick();item=base[uid]
        if item.GetClass()!='PCB_TRACK':continue
        layer=fab.COPPER_LAYER_IDS[int(item.GetLayer())]
        island_requirements[uid]=dict(current_authority=budget['current_authority'],
            required_mm=budget['required_by_layer_mm'][layer])
    return dict(root_pad_uuid=root_uid, anchor_uuid=anchor_uid, net=net, budget=budget,
        track_requirements=requirements, retained_consumer_island_uuids=sorted(island),
        retained_island_track_requirements=island_requirements,
        retained_island_allocation_reproved_from_native_topology=True,
        exact_branch_material_uuids=sorted(ids), shared_terminal_partitions_preserved=True,
        physical_trunk_tap_count=1, aggregate_rail_budget_unchanged=True,
        tap_capture_mode=capture_mode,tap_capture_via_uuid=tap_via,
        inrush_fault_barrel_and_release_qualified=False, release_authority=False)


def inventory(board, *, board_hint, timeout_s=2.):
    if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 10:
        raise ValueError('bounded_consumer_receiving_required')
    deadline = time.monotonic() + timeout_s
    groups = [g for g in board.Groups() if g.GetName().startswith(PREFIX)]
    proofs = []; refused = []; requirements = {}; island_requirements={}; roots = set()
    if len(groups) > 16:
        return dict(complete=False, track_requirements={},all_owned_track_requirements={},
            retained_island_track_requirements={},proofs=[], refusals=['consumer_group_bound'])
    for group in groups:
        try:
            proof = _receive(board, group, board_hint=board_hint, deadline=deadline)
            owned={**proof['track_requirements'],**proof['retained_island_track_requirements']}
            if (proof['root_pad_uuid'] in roots or
                    (requirements.keys()|island_requirements.keys()) & owned.keys()):
                raise ValueError('consumer_allocation_reused_or_overlapping')
            roots.add(proof['root_pad_uuid']); requirements.update(proof['track_requirements'])
            island_requirements.update(proof['retained_island_track_requirements']);proofs.append(proof)
        except Exception as exc:
            refused.append(dict(group_uuid=_uid(group), reason=type(exc).__name__ + ':' + str(exc)))
    complete = time.monotonic() < deadline and not refused
    return dict(complete=complete, track_requirements=requirements if complete else {},
        retained_island_track_requirements=island_requirements if complete else {},
        all_owned_track_requirements={**requirements,**island_requirements} if complete else {},
        proofs=proofs if complete else [], refusals=refused, release_authority=False,
        aggregate_current_budget_modified=False)
