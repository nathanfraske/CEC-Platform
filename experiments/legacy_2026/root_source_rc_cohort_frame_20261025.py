"""Source-selected whole RC-input-node translation FRAME, not routing admission.

Fresh canonical filter observations supply facts, not caller permissions.
This experiment owns only the exact rigid five-part pose, two complete native
input graphs, recognized closed reference maps and Source-contained Ground
barrels. Every external contact/open remains an explicit restoration debt.
It cannot be dispatched as a routed stage or qualify current/return/Kelvin.
"""
import copy
from decimal import Decimal
import json
import math
from pathlib import Path
import re
import tempfile
import time

import pcbnew
import cec_constraints as constraints
import cec_distributed_supply as supply
import cec_field_coupling as field
import cec_force_current as force
import cec_measurement_filter_span as observer
import cec_pair_semantics as pairs
import cec_source_literal_additions as literal
import cec_source_netlist_semantics as semantic
import cec_source_reference_group_transport as references
import cec_smd_macro_transport as transport


def _need(value, reason):
    if not value:
        raise ValueError(reason)


def _deadline(seconds):
    _need(type(seconds) in (float, int) and math.isfinite(seconds) and 0 < seconds <= 10.,
          'bounded_Source_RC_frame_lease_required')
    return time.monotonic()+seconds


def _remaining(deadline):
    value = deadline-time.monotonic()
    _need(value > 0, 'Source_RC_frame_deadline')
    return min(value, 10.)


def _candidate_span(board, root, deadline):
    """Cheap native geometry only; the public observer independently retypes it."""
    items = [p for fp in board.GetFootprints() for p in fp.Pads()
             if p.GetNetname() == root.GetNetname()]
    items += [t for t in board.GetTracks() if t.GetNetname() == root.GetNetname()]
    _need(len(items) <= 67, 'bounded_RC_node_material_required')
    for span in sorted((i for i in items if i.GetClass() == 'PCB_TRACK'), key=force._uid):
        _remaining(deadline)
        ends = {tuple(span.GetStart()), tuple(span.GetEnd())}
        if len(ends) != 2 or span.GetLayer() != pcbnew.F_Cu:
            continue
        contacts = {p: [] for p in ends}; valid = True
        for item in items:
            if force._uid(item) == force._uid(span):
                continue
            if not item.IsOnLayer(pcbnew.F_Cu) or not item.GetEffectiveShape(pcbnew.F_Cu).Collide(
                    span.GetEffectiveShape(pcbnew.F_Cu), 0):
                continue
            if item.GetClass() != 'PCB_TRACK':
                valid = False; break
            shared = ends & {tuple(item.GetStart()), tuple(item.GetEnd())}
            if len(shared) != 1:
                valid = False; break
            at = next(iter(shared)); a = next(p for p in ends if p != at)
            b = next(p for p in (tuple(item.GetStart()), tuple(item.GetEnd())) if p != at)
            if sum((a[k]-at[k])*(b[k]-at[k]) for k in (0, 1)) > 0:
                valid = False; break
            contacts[at].append(force._uid(item))
        if valid and all(len(v) == 1 for v in contacts.values()):
            return force._uid(span)
    raise ValueError('positively_observable_RC_internal_span_required')


def _identity(value):
    """Normalize only known observation timing and generated CLI raw digest."""
    value = copy.deepcopy(value)
    for proof in value['observations']:
        proof.pop('elapsed_s', None)
        context = proof['source_context']
        context['exporter'] = semantic.replay_identity({'exporter': context['exporter']})['exporter']
    context = value['canonical_cohort']
    context['exporter'] = semantic.replay_identity({'exporter': context['exporter']})['exporter']
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _closed_bypass_island(board, owner, bypass, requirement, deadline):
    """Retain ONLY an already isolated native owner/bypass supply component.

    No global supply track, existing barrel, zone or third terminal may ride
    this frame. This is geometry preservation, not current qualification.
    """
    rail = requirement['rail']
    expected = {force._uid(owner.FindPadByNumber(str(requirement['pin']))),
                force._uid(next(p for p in bypass.Pads() if p.GetNetname() == rail))}
    pads = [p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetname() == rail]
    tracks = [t for t in board.GetTracks() if t.GetNetname() == rail]
    _need(len(pads)+len(tracks) <= 4096, 'bounded_Source_bypass_island_required')
    if any(z.GetNetname() == rail and not z.GetIsRuleArea() for z in board.Zones()):
        return dict(complete=False, reason='Source_supply_zone_boundary_not_owned', track_uuids=[])
    graph = supply._connectivity([*pads, *tracks])
    root = next(p for p in pads if force._uid(p) == force._uid(owner.FindPadByNumber(str(requirement['pin']))))
    reached = {force._uid(root)} | {force._uid(i) for i in graph.GetConnectedItems(root)}
    if {force._uid(p) for p in pads if force._uid(p) in reached} != expected:
        return dict(complete=False, reason='Source_supply_not_closed_owner_bypass_pair', track_uuids=[])
    material = [t for t in tracks if force._uid(t) in reached]
    if not material:
        return dict(complete=False, reason='Source_supply_has_no_retained_graph', track_uuids=[])
    _need(1 <= len(material) <= 32, 'bounded_Source_closed_supply_graph_required')
    grouped = {force._uid(i) for g in board.Groups() for i in g.GetItems()}
    _need(all(t.GetClass() == 'PCB_TRACK' and t.GetLayer() == pcbnew.F_Cu
              and force._uid(t) not in grouped and not t.HasSolderMask() for t in material),
          'unambiguous_Source_front_supply_graph_required')
    _remaining(deadline)
    return dict(complete=True, scope='retained_exact_closed_Source_bypass_pair_graph',
                pad_uuids=sorted(expected), track_uuids=sorted(force._uid(t) for t in material),
                current_authority=False, current_qualified=False,
                global_supply_join_still_required=True)


def plan(board, source, *, board_hint, owner_uuid, delta_nm, timeout_s=10.):
    deadline = _deadline(timeout_s)
    _need(type(delta_nm) in (tuple, list) and len(delta_nm) == 2
          and all(type(v) is int for v in delta_nm) and 0 < math.hypot(*delta_nm) <= 6000000,
          'explicit_nonzero_bounded_rigid_RC_translation_required')
    source = Path(source).resolve(strict=True)
    _need(Path(board.GetFileName()).resolve() == source, 'actual_saved_RC_Source_required')
    sha = force._hash(source); family = force._family(source, board_hint); code = force._code_identity()
    owner = next((fp for fp in board.GetFootprints() if force._uid(fp) == owner_uuid), None)
    _need(owner is not None and not owner.IsDNP(), 'unique_actual_manufacturer_RC_owner_required')
    pair = pairs.footprint_input_contract(owner)
    _need(pair is not None and len(pair[1]) == 2, 'positive_manufacturer_RC_pair_required')
    observations = []
    for pin in pair[1]:
        pad = owner.FindPadByNumber(str(pin))
        _need(pad is not None, 'existing_manufacturer_RC_input_required')
        observations.append(observer.plan(board, source, board_hint=board_hint,
            pad_uuid=force._uid(pad), span_uuid=_candidate_span(board, pad, deadline),
            expected_source_sha256=sha, timeout_s=_remaining(deadline)))
    first, second = observations
    _need(first['lineage'] == second['lineage'] and first['node_net'] != second['node_net']
          and first['declared_series_resistance_ohms'] == second['declared_series_resistance_ohms'],
          'same_disjoint_complete_Source_RC_lineage_required')
    lineage = first['lineage']['selected']
    filter_refs = {first['capacitor']['ref'], *(
        lineage[leg]['series'][0]['ref'] for leg in ('p', 'n'))}
    _need(len(filter_refs) == 3 and owner.GetReference() not in filter_refs,
          'three_unique_Source_RC_supports_required')
    with force._thermal_hint(board_hint):
        assigned = constraints._device_bypass_assignment(board, project_max_mm=3.5)
    bypasses = [row for row in assigned['assigned'].values()
                if row['requirement']['ref'] == owner.GetReference()]
    _need(len(bypasses) == 1, 'one_unique_Source_supply_follower_required')
    bypass = bypasses[0]; req = bypass['requirement']
    _need((req.get('return_rail') or 'GND') == 'GND', 'Source_grounded_bypass_required')
    refs = filter_refs | {owner.GetReference(), bypass['cap_ref']}
    _need(len(refs) == 5, 'disjoint_complete_five_owner_RC_cohort_required')
    selected = []
    for ref in sorted(refs):
        fp = board.FindFootprintByReference(ref); selected.append(fp)
        _need(fp is not None and not fp.IsLocked() and not fp.IsDNP()
              and all(p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and not p.HasHole()
                      and tuple(p.GetLayerSet().CuStack()) == (pcbnew.F_Cu,) for p in fp.Pads()),
              'unlocked_populated_front_Source_RC_cohort_required')
        for pad in fp.Pads():
            _need(pad.GetNetCode() > 0, 'complete_Source_RC_land_assignment_required')
    # Re-export EVERY selected part, not just the three-land input subsets.
    # This binds outward resistor lands, actual VS/Ground and the bypass too.
    context, _ = observer._source_context(board, source, board_hint, refs,
        {proof['node_net']: {(p.GetParentFootprint().GetReference(), p.GetNumber())
          for fp in board.GetFootprints() for p in fp.Pads()
          if force._uid(p) in proof['node_pad_uuids']} for proof in observations}, deadline)
    # _identity proves actual selected parts. Explicitly verify every land
    # against the same fresh export, including outward and supply terminals.
    root = observer.source_nc._root(board, board_hint)
    tree, exporter = observer.source_roles._export(root, deadline)
    _, _, node_net = observer.source_roles._tables(tree)
    for fp in selected:
        for pad in fp.Pads():
            _need(node_net.get((fp.GetReference(), pad.GetNumber()), '') == pad.GetNetname(),
                  'entire_canonical_Source_RC_cohort_land_map_required')
    context['exporter'] = exporter
    groups = []
    for fp in selected:
        parents = [g for g in board.Groups() if g.ContainsItem(fp)]
        _need(len(parents) <= 1, 'unambiguous_closed_Source_RC_reference_parent_required')
        groups += [(force._uid(fp), force._uid(g)) for g in parents]
    maps = references.inspect_many(source, groups, timeout_s=_remaining(deadline)) if groups else []
    internal = sorted({u for proof in observations for u in proof['node_track_uuids']})
    _need(1 <= len(internal) <= 128
          and not set(first['node_track_uuids']) & set(second['node_track_uuids']),
          'disjoint_complete_bounded_Source_RC_graphs_required')
    supply_graph = _closed_bypass_island(board, owner, board.FindFootprintByReference(bypass['cap_ref']),
                                        req, deadline)
    poses = {fp.GetReference(): [*[v/1e6 for v in fp.GetPosition()], fp.GetOrientationDegrees()]
             for fp in selected}
    result = dict(schema=1, scope='Source_RC_complete_graph_rigid_translation_frame',
        source=str(source), source_sha256=sha, source_family=family, code_identity=code,
        prototype_sha256=force._hash(Path(__file__)), board_hint=board_hint, owner_uuid=owner_uuid,
        delta_nm=list(delta_nm), source_poses=poses,
        target_poses={ref: [pose[0]+delta_nm[0]/1e6, pose[1]+delta_nm[1]/1e6, pose[2]]
                      for ref, pose in poses.items()},
        footprint_uuids=sorted(force._uid(fp) for fp in selected),
        internal_track_uuids=internal, observations=observations, canonical_cohort=context,
        retained_local_supply_graph=supply_graph,
        reference_maps=maps, reference_group_uuids=[group for owner_id, group in groups],
        selected_bypass=dict(ref=bypass['cap_ref'], pin=str(req['pin']), rail=req['rail']),
        external_boundary_restoration_required=True, inherited_opens_must_remain_visible=True,
        current_qualified=False, return_qualified=False, kelvin_qualified=False,
        routing_admitted=False, release_authority=False)
    _remaining(deadline)
    _need(force._hash(source) == sha and force._family(source, board_hint) == family
          and force._code_identity() == code, 'RC_Source_or_code_changed')
    return result


def project(source, proposal, *, timeout_s=10., per_phase_leases=False):
    """Unsaved unfinished frame; never skips complete-macro role guards.

    Explicit composition may give Source recompilation and native projection
    separate leases; neither constituent may exceed the supplied <=10s lease.
    """
    _need(type(per_phase_leases) is bool, 'literal_RC_phase_composition_required')
    deadline = _deadline(timeout_s); source = Path(source).resolve(strict=True)
    started = time.monotonic()
    original = pcbnew.LoadBoard(str(source))
    fresh = plan(original, source, board_hint=proposal['board_hint'], owner_uuid=proposal['owner_uuid'],
                 delta_nm=proposal['delta_nm'], timeout_s=_remaining(deadline))
    _need(_identity(fresh) == _identity(proposal), 'fresh_exact_Source_RC_frame_required')
    _remaining(deadline)
    recompile_s = time.monotonic()-started
    if per_phase_leases:
        deadline = _deadline(timeout_s)
    projection_started = time.monotonic()
    board = pcbnew.LoadBoard(str(source))
    if fresh['reference_maps']:
        references.transform_many(board, [
            (proof, tuple(fresh['delta_nm'])) for proof in fresh['reference_maps']])
    mapped = {proof['owner_uuid'] for proof in fresh['reference_maps']}
    for fp in board.GetFootprints():
        if force._uid(fp) in fresh['footprint_uuids'] and force._uid(fp) not in mapped:
            fp.Move(pcbnew.VECTOR2I(*fresh['delta_nm']))
    # Existing Source-contained Ground barrels only; no new process rule,
    # conductor, endpoint stretching or current/return authority is created.
    moved = transport.apply(original, board, source_path=source, board_hint=fresh['board_hint'],
        retain_source_tracks=True, carry_ground_barrels_only=True,
        reference_group_uuids=fresh['reference_group_uuids'], maximum_shift_mm=6.,
        timeout_s=_remaining(deadline))
    live = {force._uid(t): t for t in board.GetTracks()}
    for uid in [*fresh['internal_track_uuids'], *fresh['retained_local_supply_graph']['track_uuids']]:
        _remaining(deadline)
        live[uid].Move(pcbnew.VECTOR2I(*fresh['delta_nm']))
    _remaining(deadline)
    return board, dict(source_plan=fresh, source_barrel_transport=moved,
        phase_elapsed_s=dict(Source_recompile=recompile_s,
                             native_projection=time.monotonic()-projection_started),
        per_phase_leases=per_phase_leases,
        complete_macro_scope_or_routing_authority=False,
        mandatory_external_contacts_not_yet_restored=True)


def _literal_translation(node, delta_nm):
    """Change only top-level Source coordinates, never normalize other AST."""
    kind = literal.kind(node)
    keys = {'at'} if kind in ('footprint', 'via', 'gr_text') else {'start', 'end'}
    _need(kind in ('footprint', 'via', 'segment', 'gr_text', 'gr_line'),
          'exact_translatable_Source_RC_root_kind_required')
    edits = []
    for key in keys:
        span = literal._child(node, key)
        _need(span is not None, 'exact_Source_RC_coordinate_child_required')
        a, b = span
        match = re.match(r'(\(\s*'+key+r'\s+)([^\s()]+)(\s+)([^\s()]+)', node[a:b])
        _need(match is not None, 'literal_Source_RC_coordinate_pair_required')
        for index, token_group in enumerate((2, 4)):
            value = Decimal(match.group(token_group))+Decimal(delta_nm[index])/Decimal(1000000)
            _need(value.is_finite(), 'finite_Source_RC_coordinate_required')
            x, y = match.span(token_group)
            edits.append((a+x, a+y, format(value, 'f')))
    for a, b, value in sorted(edits, reverse=True):
        node = node[:a]+value+node[b:]
    return node


def save_diagnostic(source, board, frame, directory):
    """Preserve all unowned Source bytes; label the frame unfinished."""
    source = Path(source).resolve(strict=True); directory = Path(directory).resolve()
    _need(not directory.exists(), 'fresh_unfinished_RC_diagnostic_directory_required')
    q = frame['source_plan']; _need(force._hash(source) == q['source_sha256'], 'RC_Source_changed')
    text = source.read_text(); old, _, _, _ = literal._inventory(text)
    allowed = set(q['footprint_uuids']) | set(q['internal_track_uuids'])
    allowed |= set(q['retained_local_supply_graph']['track_uuids'])
    changes = frame['source_barrel_transport']['changes']
    for change in changes:
        _need(change['net'] == 'GND' and all(
            tuple(p[k]+q['delta_nm'][k] for k in (0, 1)) == tuple(z)
            for p, z in zip(change['source_nm'], change['candidate_nm'])),
            'Source_Ground_barrels_must_share_exact_RC_translation')
    allowed |= {change['uuid'] for change in changes}
    for group in board.Groups():
        if force._uid(group) in q['reference_group_uuids']:
            allowed |= {force._uid(item) for item in group.GetItems()}
    _need(allowed <= old.keys(), 'RC_frame_exact_root_object_scope_required')
    edits = [(old[u][0], old[u][1], _literal_translation(old[u][2], q['delta_nm'])) for u in allowed]
    for a, b, value in sorted(edits, reverse=True):
        text = text[:a]+value+text[b:]
    candidate = force._copy_family(source, directory)
    candidate.write_text(text)
    reloaded = pcbnew.LoadBoard(str(candidate))
    before = field._field_snapshot_inventory(board); after = field._field_snapshot_inventory(reloaded)
    if before != after:
        changed = [dict(key=repr(k), before=repr(before.get(k)), after=repr(after.get(k)))
                   for k in sorted(before.keys() | after.keys(), key=repr)
                   if before.get(k) != after.get(k)]
        raise ValueError('native_RC_frame_literal_reload_refused:'+json.dumps(
            dict(changed_count=len(changed), first_changes=changed[:8]), sort_keys=True))
    return candidate


def receive_frame(source, candidate, proposal, *, timeout_s=10., per_phase_leases=False):
    """Independent exact frame replay ONLY; final route receiving still due."""
    result = dict(ok=False, complete=False, errors=[], scope_only=True,
        routing_admitted=False, current_qualified=False, return_qualified=False,
        kelvin_qualified=False, release_authority=False)
    try:
        source, candidate = [Path(p).resolve(strict=True) for p in (source, candidate)]
        _need(source != candidate and force._sidecars(source) == force._sidecars(candidate),
              'distinct_Source_exact_companion_RC_frame_required')
        family = [force._family(p, proposal['board_hint']) for p in (source, candidate)]
        board, frame = project(source, proposal, timeout_s=timeout_s,
                               per_phase_leases=per_phase_leases)
        with tempfile.TemporaryDirectory(prefix='cec-RC-frame-receive-') as work:
            expected = save_diagnostic(source, board, frame, Path(work)/'unfinished')
            _need(candidate.read_bytes() == expected.read_bytes(), 'exact_Source_RC_frame_replay_refused')
        _need(family == [force._family(p, proposal['board_hint']) for p in (source, candidate)],
              'Source_RC_frame_family_changed')
        result.update(ok=True, complete=True, source_sha256=force._hash(source),
            candidate_sha256=force._hash(candidate),
            exact_rigid_whole_node_and_native_barrel_frame=True,
            mandatory_contacts_current_field_native_and_measurement_receiving_pending=True)
    except (ValueError, RuntimeError, KeyError, TypeError, OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
