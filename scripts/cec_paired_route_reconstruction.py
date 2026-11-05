"""Exact whole-pair track reconstruction, independent of the constructor.

A frozen half-route cannot be repaired by routing its other member as an
ordinary signal.  This narrowly typed transaction retires only all tracks of
one positively declared pair.  An explicit whole-barrel mode can also retire
ALL of that pair's through barrels, never pads or another bus's copper. Every
power bus, pose and external land remains immutable. A separate explicit mode
retains positively witnessed source pad barrels and owns ALL remaining route
barrels; it never accepts a caller-selected inconvenient subset. It grants no partial-pair
or release waiver; the complete saved bus must meet its physical contract.
"""
from pathlib import Path
import math
import tempfile
import time


def validate_track_scope(pair, rows, requested, *, grouped=(), protected=(),
                         allow_source_width_repair=False):
    """Own a complete old pair, never reinterpret its width as new authority.

    The default keeps the strict source-width precondition used by local craft
    repairs. A whole-pair reconstruction can explicitly retire malformed old
    widths, but must still replace BOTH members under the unchanged canonical
    contract. This flag grants retirement scope only, not route admission.
    """
    if type(allow_source_width_repair) is not bool:
        raise ValueError('explicit_source_pair_width_repair_policy_required')
    if (not isinstance(pair, dict) or pair.get('kind') not in ('can', 'usb', 'diff')
            or any(type(pair.get(k)) is not str or not pair[k] for k in ('name', 'p', 'n'))
            or pair['p'] == pair['n']
            or any(type(pair.get(k)) not in (int, float) or not math.isfinite(pair[k])
                or pair[k] <= 0 for k in ('width', 'gap', 'clearance'))):
        raise ValueError('positive_source_coupled_pair_contract_required')
    if (type(requested) not in (list, tuple, set) or not 1 <= len(requested) <= 512
            or len(set(requested)) != len(requested)
            or any(type(u) is not str or not u for u in requested)):
        raise ValueError('bounded_exact_pair_track_retirement_required')
    if len(rows) > 16384 or len({r['uuid'] for r in rows}) != len(rows):
        raise ValueError('ambiguous_source_pair_inventory')
    nets = {pair['p'], pair['n']}
    if nets & set(protected):
        raise ValueError('current_or_pour_owned_pair_cannot_be_retired')
    expected = {r['uuid'] for r in rows if r['net'] in nets and r['kind'] == 'PCB_TRACK'}
    if set(requested) != expected:
        raise ValueError('both_members_whole_source_track_scope_required')
    if any(r['net'] in nets and r['kind'] not in ('PCB_TRACK', 'PCB_VIA') for r in rows):
        raise ValueError('unsupported_source_pair_copper')
    if set(requested) & set(grouped):
        raise ValueError('group_owned_pair_tracks_require_separate_reconstruction')
    if any(type(r.get('width_nm')) is not int or not 0 < r['width_nm'] <= 2_000_000_000
            for r in rows if r['uuid'] in expected):
        raise ValueError('positive_actual_source_pair_track_width_required')
    width = round(pair['width'] * 1e6)
    if (not allow_source_width_repair
            and any(r['width_nm'] != width for r in rows if r['uuid'] in expected)):
        raise ValueError('source_pair_track_width_disagrees_with_contract')
    return sorted(expected)


def validate_barrel_scope(pair, rows, requested, *, group_rows=(), factory_group,
                          retained_pad_barrel_uuids=()):
    """Own a complete pair's barrels, not selected inconvenient obstacles.

    Factory POFV membership is the only permissible source group retirement.
    A mixed factory group may retain its other buses' members unchanged. Any
    opaque/structural/current group touching these barrels remains protected.
    """
    nets = {pair['p'], pair['n']}
    all_barrels = {r['uuid'] for r in rows if r['net'] in nets and r['kind'] == 'PCB_VIA'}
    keep=retained_pad_barrel_uuids
    if (type(keep) not in (list,tuple,set,frozenset) or len(keep)>128 or len(set(keep))!=len(keep)
            or any(type(u) is not str or not u for u in keep) or not set(keep)<=all_barrels):
        raise ValueError('bounded_actual_source_terminal_barrels_required')
    expected=all_barrels-set(keep)
    if (type(requested) not in (list, tuple, set) or not (0 if keep else 1) <= len(requested) <= 128
            or len(set(requested)) != len(requested)
            or any(type(u) is not str or not u for u in requested)):
        raise ValueError('bounded_exact_whole_pair_barrel_scope_required')
    if set(requested) != expected:
        raise ValueError('all_source_pair_barrels_required')
    if any(r.get('through') is not True or type(r.get('drill_nm')) is not int
            or r['drill_nm'] <= 0 for r in rows if r['uuid'] in all_barrels):
        raise ValueError('source_pair_barrels_must_be_positive_through_holes')
    touched = [g for g in group_rows if set(g['members']) & expected]
    if (any(g['name'] != factory_group or g.get('all_members_vias') is not True
            for g in touched) or len(touched) > 1):
        raise ValueError('opaque_or_ambiguous_group_owned_pair_barrels')
    return sorted(expected), sorted(g['uuid'] for g in touched)


def classify_source_barrels(board,pair):
    """Prove exact pad anchors and no terminal contact for every other barrel.

    This is source topology, not permission to create undersized holes or
    qualify retained manufacturing debt. Unsupported pad-contacting source
    barrels cannot be relabelled route-only just because their witness fails.
    """
    import pcbnew
    import cec_force_current as force
    import cec_fr as fr
    import cec_retained_pad_barrel_access as access
    nets={pair['p'],pair['n']}
    vias=[v for v in board.GetTracks() if v.GetClass()=='PCB_VIA' and v.GetNetname() in nets]
    pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
    if len(vias)>128 or len(pads)>16384:raise ValueError('bounded_native_source_pair_barrel_classification_required')
    ids={force._uid(v) for v in vias};anchors=set();witnesses=[]
    for pad in pads:
        if pad.GetNetname() not in nets:continue
        witness=access.inspect(board,pad,ids)
        if witness['retained_via_uuids']:
            anchors.update(witness['retained_via_uuids'])
            witnesses.append(dict(pad_uuid=force._uid(pad),net=str(pad.GetNetname()),**witness))
    for via in vias:
        if force._uid(via) in anchors:continue
        layers=fr._through_barrel_layers(board,via)
        if not layers:raise ValueError('unmodified_native_route_barrel_required')
        for pad in pads:
            # An arbitrary contact, not just a familiar pad name or package,
            # prevents route-only classification. Use actual per-face land
            # shapes; unknown/custom native geometry must not grant a cut.
            for layer in set(pad.GetLayerSet().CuStack()) & set(layers):
                if via.GetEffectiveShape(layer).Collide(pad.GetEffectiveShape(layer),0):
                    raise ValueError('unwitnessed_source_terminal_barrel_contact')
            if pad.HasHole() and pad.GetPosition()==via.GetPosition():
                raise ValueError('source_barrel_coincides_with_component_hole')
    return dict(retained_pad_barrel_uuids=sorted(anchors),route_barrel_uuids=sorted(ids-anchors),
        pad_witnesses=sorted(witnesses,key=lambda r:r['pad_uuid']),
        new_hole_geometry_authorized=False,inherited_debt_qualified=False,release_authority=False)


def plan(board, source, *, board_hint, pair_name, retired_track_uuids=None,
         retired_via_uuids=None,preserve_native_pad_barrels=False,
         allow_source_width_repair=False):
    """Derive retirement rights from the real unchanged source, not its labels."""
    import cec_force_current as force
    import cec_precision_route as precision
    import cec_current_topology as topology
    import cec_synth_pipeline as synth
    import cec_fr as fr
    import pcbnew
    if type(board_hint) is not str or not board_hint or type(pair_name) is not str or not pair_name:
        raise ValueError('explicit_source_design_and_pair_identity_required')
    if type(preserve_native_pad_barrels) is not bool:
        raise ValueError('explicit_source_pad_barrel_preservation_policy_required')
    pairs = [p for p in precision.derive_coupled_pairs(str(source), board=board)
        if p['name'] == pair_name]
    if len(pairs) != 1:
        raise ValueError('unique_positive_source_pair_required')
    pair = pairs[0]
    tracks = list(board.GetTracks())
    rows = [dict(uuid=force._uid(t), net=str(t.GetNetname()), kind=t.GetClass(),
        width_nm=t.GetWidth() if t.GetClass() == 'PCB_TRACK' else None,
        layer_id=int(t.GetLayer()) if t.GetClass() == 'PCB_TRACK' else None,
        through=t.GetViaType() == pcbnew.VIATYPE_THROUGH if t.GetClass() == 'PCB_VIA' else None,
        drill_nm=t.GetDrillValue() if t.GetClass() == 'PCB_VIA' else None) for t in tracks]
    nets = {pair['p'], pair['n']}
    with force._thermal_hint(board_hint):
        protected = set(topology.board_current_domains(board, board_hint))
        protected |= {n for n in nets if synth.spec_net_current_contract(board_hint, n) is not None}
    protected |= {str(z.GetNetname()) for z in board.Zones() if not z.GetIsRuleArea()}
    protected |= {str(p.GetNetname()) for fp in board.GetFootprints() for p in fp.Pads()
        if str(p.GetPinType()) in ('power_in', 'power_out')}
    grouped = {force._uid(t) for g in board.Groups() for t in g.GetItems()}
    requested = (retired_track_uuids if retired_track_uuids is not None else
        [r['uuid'] for r in rows if r['net'] in nets and r['kind'] == 'PCB_TRACK'])
    retired = validate_track_scope(pair, rows, requested, grouped=grouped, protected=protected,
        allow_source_width_repair=allow_source_width_repair)
    source_widths = sorted((dict(uuid=r['uuid'], net=r['net'], layer_id=r['layer_id'],
        width_nm=r['width_nm']) for r in rows if r['uuid'] in set(retired)),
        key=lambda r:r['uuid'])
    retired_vias, factory_groups = [], []
    classification=classify_source_barrels(board,pair) if preserve_native_pad_barrels else None
    if retired_via_uuids is not None or preserve_native_pad_barrels:
        group_rows = [dict(uuid=force._uid(g), name=g.GetName(),
            members=[force._uid(t) for t in g.GetItems()],
            all_members_vias=all(t.GetClass() == 'PCB_VIA' for t in g.GetItems()))
            for g in board.Groups()]
        requested_vias=(classification['route_barrel_uuids']
            if retired_via_uuids is None else retired_via_uuids)
        if classification and not classification['retained_pad_barrel_uuids'] and not classification['route_barrel_uuids']:
            if list(requested_vias):raise ValueError('source_has_no_pair_barrels_to_retire')
        else:
            retired_vias, factory_groups = validate_barrel_scope(pair, rows, requested_vias,
                group_rows=group_rows, factory_group=fr.LOCAL_POFV_SIGNAL_VIA_GROUP,
                retained_pad_barrel_uuids=classification['retained_pad_barrel_uuids'] if classification else ())
    for net in nets:
        if sum(str(p.GetNetname()) == net for fp in board.GetFootprints() for p in fp.Pads()) < 2:
            raise ValueError('complete_pair_terminal_inventory_required')
    return dict(schema=1, pair=pair, retired_track_uuids=retired,
        allow_source_width_repair=allow_source_width_repair,
        source_track_width_inventory=source_widths,
        nonconforming_source_track_uuids=sorted(r['uuid'] for r in source_widths
            if r['width_nm'] != round(pair['width']*1e6)),
        source_widths_authorize_new_geometry=False,
        retired_via_uuids=retired_vias, source_local_factory_group_uuids=factory_groups,
        retained_pair_via_uuids=sorted(r['uuid'] for r in rows
            if r['net'] in nets and r['kind'] == 'PCB_VIA' and r['uuid'] not in retired_vias),
        all_source_pair_tracks_owned=True, all_source_pair_barrels_owned=retired_via_uuids is not None and not preserve_native_pad_barrels,
        preserve_native_pad_barrels=preserve_native_pad_barrels,source_barrel_classification=classification,
        all_source_nonterminal_pair_barrels_owned=preserve_native_pad_barrels,
        source_vias_retired=bool(retired_vias),
        external_lands_retired=False, source_vias_and_external_lands_retired=False,
        power_pours_poses_pinout_and_outline_immutable=True, release_authority=False)


def _write_source_projection(source, target, outgoing, basis, *, factory_groups):
    """Serialize already-owned subtraction, never grant cut authority.

    The bounded ungrouped writer preserves all unrelated Source tokens,
    including component-model and annotation-group child ordering. Larger
    or factory-group cuts retain their existing native path and every
    subsequent exact saved-scope check; no normalized comparison is added.
    """
    if not factory_groups and 0 < len(outgoing) <= 132:
        import cec_source_literal_retirement as literal
        return literal.write_native_projection(source, target, outgoing, basis)
    import cec_field_coupling as field
    field._save_field_snapshot(basis, target)
    return dict(native_serialization=True, exact_saved_scope_receiving_still_required=True,
                electrical_retirement_authority=False)


def receive(source, candidate, *, board_hint, pair_name, retired_track_uuids,
            retired_via_uuids=None, preserve_native_pad_barrels=False,timeout_s=10.,
            allow_source_width_repair=False):
    """Prove exact subtract/add, complete native bus and its physical contract.

The construction remains UNADMITTED until full native DRC, field, current,
stack and release receiving also pass.  Retained source POFV debt is never
qualified just because its identity is preserved.
"""
    import pcbnew
    import cec_force_current as force
    import cec_additive_route_receiving as additive
    import cec_copper_echo as sexpr
    import cec_native_partition_pair as partitions
    import cec_field_coupling as field
    import cec_precision_route as precision
    import cec_constraints as constraints
    import cec_fr as fr
    from cec_native_items import discard_items
    started = time.monotonic()
    report = dict(schema=1, ok=False, complete=False, errors=[],
        scope=('exact_whole_pair_tracks_and_all_nonterminal_barrels_with_immutable_pad_barrels'
            if preserve_native_pad_barrels else 'exact_whole_declared_pair_tracks_and_barrels_with_immutable_lands'
            if retired_via_uuids is not None else
            'exact_whole_declared_pair_tracks_with_immutable_barrels_and_lands'),
        inherited_debt_qualified=False, routing_admitted=False, release_authority=False)
    try:
        if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 30:
            raise ValueError('bounded_pair_receiving_budget_required')
        deadline = started + timeout_s
        paths = [Path(p).resolve() for p in (source, candidate)]
        families = [force._family(p, board_hint) for p in paths]
        epoch = force._code_identity()
        parent, child = [pcbnew.LoadBoard(str(p)) for p in paths]
        proof = plan(parent, paths[0], board_hint=board_hint, pair_name=pair_name,
            retired_track_uuids=retired_track_uuids, retired_via_uuids=retired_via_uuids,
            preserve_native_pad_barrels=preserve_native_pad_barrels,
            allow_source_width_repair=allow_source_width_repair)
        pair = proof['pair']; outgoing = set(proof['retired_track_uuids']) | set(proof['retired_via_uuids'])
        import cec_enrolled_pair_signal_view as enrolled_signal
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ValueError('whole_pair_receiving_deadline')
        signal_view=enrolled_signal.derive(paths[0], paths[1], parent, child, pair,
            board_hint=board_hint, timeout_s=min(10.,remaining))
        report['independently_derived_source_scope'] = proof
        if precision.derive_coupled_pairs(str(paths[0]), board=parent) != precision.derive_coupled_pairs(str(paths[1]), board=child):
            raise ValueError('source_pair_contract_changed')
        _, first = additive._nodes(paths[0]); _, last = additive._nodes(paths[1])
        if first.keys() - last.keys() != outgoing:
            raise ValueError('saved_retirement_differs_from_whole_pair_scope')
        incoming = last.keys() - first.keys()
        if not incoming or len(incoming) > 1024:
            raise ValueError('bounded_incoming_pair_reconstruction_required')
        native_new = {force._uid(t):t for t in child.GetTracks() if force._uid(t) in incoming}
        if not {pair['p'], pair['n']} <= {str(t.GetNetname()) for t in native_new.values()
                if t.GetClass() == 'PCB_TRACK'}:
            raise ValueError('both_members_must_be_constructed_atomically')
        return_groups = [g for g in child.Groups() if g.GetName() == fr.LOCAL_PAIR_RETURN_VIA_GROUP]
        ground_returns = {force._uid(t) for g in return_groups for t in g.GetItems()}
        for uid, t in native_new.items():
            if str(t.GetNetname()) not in (pair['p'], pair['n']):
                if (str(t.GetNetname()) != 'GND' or t.GetClass() != 'PCB_VIA'
                        or uid not in ground_returns):
                    raise ValueError('incoming_copper_outside_pair_and_owned_ground_returns')
            elif t.GetClass() == 'PCB_TRACK' and t.GetWidth() != round(pair['width']*1e6):
                raise ValueError('incoming_pair_width_disagrees_with_source')
        # New/retired pair barrels legitimately change refilled GND island
        # geometry. Exact single-board proxy keys cannot span that change.
        # Co-refine the two saved native fills with per-face positive-overlap
        # tokens; never substitute a whole-zone owner or omit its islands.
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ValueError('whole_pair_receiving_deadline')
        transition=partitions.compare(parent,child,timeout_s=min(10.,remaining),
            retired_uuids=outgoing)
        report['paired_native_partition_preservation']={k:v for k,v in transition.items()
            if k not in ('source_parts','child_parts','demoted_parts')}
        report['paired_native_partition_preservation']['demoted_component_count']=len(transition['demoted_parts'])
        preservation=transition
        if signal_view is not None:
            preservation=enrolled_signal.preserved(signal_view,parent,child,transition)
            report['fresh_source_enrolled_signal_partition_projection']=preservation
        if preservation['preserved'] is not True:
            raise ValueError('surviving_native_terminal_or_copper_partition_lost')
        report['all_surviving_source_terminal_and_copper_partitions_preserved'] = transition['preserved']
        report['all_surviving_source_electrical_partitions_preserved'] = True
        native = precision._native_pair_completion(child, pair, signal_view=signal_view)
        report['actual_saved_native_pair_completion'] = native
        if (native.get('complete') is not True or native.get('connected') is not True
                or any(r.get('disconnected_copper_uuids') for r in native['nets'].values())):
            raise ValueError('whole_pair_native_connectivity_incomplete')
        with force._thermal_hint(board_hint):
            physical = constraints.high_speed_pair_summary(str(paths[1]), board=child)
        matches = [r for r in physical.get('pairs', []) if (r['p'], r['n']) == (pair['p'], pair['n'])]
        if physical.get('applicable') is not True or len(matches) != 1:
            raise ValueError('complete_saved_pair_physical_contract_unavailable')
        report['actual_saved_native_pair_physical_contract'] = matches[0]
        if matches[0]['violations']:
            raise ValueError('reconstructed_pair_physical_contract_failed')
        with tempfile.TemporaryDirectory(prefix='cec-whole-pair-receiving-') as work:
            projected = force._copy_family(paths[0], Path(work)/'projected')
            basis = pcbnew.LoadBoard(str(projected))
            discard_items(basis, [t for t in basis.GetTracks() if force._uid(t) in outgoing])
            mutable_groups = set(proof['source_local_factory_group_uuids'])
            report['exact_source_subtraction_projection'] = _write_source_projection(
                paths[0], projected, outgoing, basis, factory_groups=mutable_groups)
            _, reconstructed = additive._nodes(projected)
            for uid in mutable_groups:
                if (additive._without(reconstructed[uid], 'members') !=
                        additive._without(first[uid], 'members') or
                        additive._members(reconstructed[uid]) != additive._members(first[uid])-outgoing):
                    raise ValueError('pair_barrel_retirement_changed_other_factory_members')
            if (reconstructed.keys() != first.keys()-outgoing or any(
                    sexpr._freeze(reconstructed[u]) != sexpr._freeze(first[u])
                    for u in reconstructed if u not in mutable_groups)):
                raise ValueError('retirement_changed_unrelated_source_material')
            remaining = deadline-time.monotonic()
            if remaining <= 0: raise ValueError('whole_pair_receiving_deadline')
            replay = additive.receive(projected, paths[1], timeout_s=min(30., remaining),
                allow_pair_return_via_additions=True,board_hint=board_hint)
            report['independent_exact_subtract_add_ground_and_rule_replay'] = replay
            if replay.get('ok') is not True or replay.get('complete') is not True:
                raise ValueError('whole_pair_saved_delta_replay_refused')
        if signal_view is not None:signal_view.check(child)
        stable = (families == [force._family(p, board_hint) for p in paths]
            and epoch == force._code_identity())
        report['source_candidate_and_code_unchanged'] = stable
        if not stable or time.monotonic() >= deadline:
            raise ValueError('whole_pair_identity_or_deadline_changed')
        report.update(ok=True, complete=True, added_native_uuids=sorted(incoming),
            retired_track_uuids=proof['retired_track_uuids'],
            retired_via_uuids=proof['retired_via_uuids'],
            source_local_factory_group_uuids=proof['source_local_factory_group_uuids'])
    except Exception as exc:
        report['errors'].append(type(exc).__name__+':'+str(exc))
    report['elapsed_s'] = round(time.monotonic()-started, 6)
    return report
