"""Source-derived planar RC input-prefix reconstruction, not input qualification.

An unchanged three-edge RC observer supplies the canonical node and a complete
internal separator.  Only its actual root-exclusive native component may be
absorbed into the replacement.  Callers name the three observer anchors, never
additional cuts.  The measurement land, filter-side contacts and every other
Source object remain fixed.  A later complete-cell receiver must independently
derive any moving measurement leaf; this module grants no pose authority.
"""
import copy
import json
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_measurement_filter_span as observer
import cec_native_ground_span_reflow as simple
import cec_native_rule_areas as rules
import cec_ordinary_route_receiving as partitions
import cec_pair_local_reference_refinement as chains
import cec_source_guided_ordinary_detour as integer
import cec_source_literal_additions as literal
import cec_source_netlist_semantics as semantic
import cec_source_rc_elbow_reflow as elbow
from cec_native_items import discard_items


def _need(ok, reason):
    if not ok:
        raise ValueError(reason)


def _deadline(seconds):
    _need(type(seconds) in (int, float) and math.isfinite(seconds) and 0 < seconds <= 10.,
          'bounded_Source_RC_prefix_lease_required')
    return time.monotonic()+seconds


def _remaining(deadline):
    value = deadline-time.monotonic()
    _need(value > 0, 'Source_RC_prefix_deadline')
    return min(value, 10.)


def _identity(proposal):
    q = copy.deepcopy(proposal)
    obs = q['Source_observation']; anchor = obs['anchor_elbow']
    seen = set()
    for record in (obs, anchor, obs['Source_node_observation'], anchor['Source_node_observation']):
        if id(record) in seen:
            continue
        seen.add(id(record))
        record.pop('elapsed_s', None)
        if 'source_context' in record:
            context = record['source_context']
            context['exporter'] = semantic.replay_identity({'exporter': context['exporter']})['exporter']
    return json.dumps(q, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _observe(board, source, *, board_hint, pad_uuid, span_uuids, deadline):
    """Derive the entire exclusive prefix from real Source connectivity."""
    anchor = observer.plan_elbow(board, source, board_hint=board_hint, pad_uuid=pad_uuid,
        span_uuids=span_uuids, expected_source_sha256=force._hash(source), timeout_s=_remaining(deadline))
    node = anchor['Source_node_observation']; anchors = set(anchor['internal_span_uuids'])
    node_ids = set(node['node_pad_uuids']+node['node_track_uuids'])
    items = {force._uid(p): p for fp in board.GetFootprints() for p in fp.Pads() if force._uid(p) in node_ids}
    items.update({force._uid(t): t for t in board.GetTracks() if force._uid(t) in node_ids})
    _need(set(items) == node_ids and pad_uuid in items, 'complete_Source_RC_prefix_node_required')
    graph = pcbnew.CONNECTIVITY_DATA()
    for uid, item in items.items():
        _remaining(deadline)
        if uid not in anchors:
            _need(graph.Add(item), 'Source_RC_prefix_native_graph_refused')
    root = items[pad_uuid]
    component = {pad_uuid} | {force._uid(i) for i in graph.GetConnectedItems(root)}
    _need(component & set(node['node_pad_uuids']) == {pad_uuid}
        and component in [set(c) for c in anchor['retained_components']],
        'Source_RC_prefix_exclusive_measurement_terminal_required')
    prefix_ids = component-{pad_uuid}
    _need(1 <= len(prefix_ids) <= 4 and all(items[u].GetClass() == 'PCB_TRACK' for u in prefix_ids)
        and sum(items[u].GetLength() for u in prefix_ids) <= 4000000,
        'bounded_Source_RC_root_exclusive_track_prefix_required')
    cuts = anchors | prefix_ids
    old = [items[u] for u in sorted(cuts)]
    _, nodes = additive._nodes(source)
    process = chains._process(nodes[anchor['internal_span_uuids'][0]])
    _need(all(chains._process(nodes[u]) == process for u in cuts),
          'Source_RC_prefix_same_width_face_net_lock_process_required')
    # Original short noncanonical bonds are literal Source material, not new
    # geometry permission.  The COMPLETE original endpoint chain is required.
    points = chains._chain(old)
    root_shape = root.GetEffectiveShape(pcbnew.F_Cu)
    root_ends = [p for p in (points[0], points[-1]) if root_shape.Collide(pcbnew.VECTOR2I(*p))]
    _need(len(root_ends) == 1, 'one_literal_Source_measurement_launch_required')
    if points[0] != root_ends[0]:
        points.reverse()
    root_contacts = [t for t in old if root_shape.Collide(t.GetEffectiveShape(pcbnew.F_Cu), 0)]
    _need(len(root_contacts) == 1 and tuple(points[0]) in
        (tuple(root_contacts[0].GetStart()), tuple(root_contacts[0].GetEnd())),
        'one_actual_Source_measurement_launch_contact_required')
    far_ports = [p for p in anchor['retained_ports'] if not
        ({r['native_uuid'] for r in p['contacts']} & component)]
    _need(len(far_ports) == 1 and tuple(far_ports[0]['at_nm']) == points[-1],
          'unchanged_Source_filter_side_port_required')
    expected = {pad_uuid} | {r['native_uuid'] for r in far_ports[0]['contacts']}
    actual = {uid for uid, peer in items.items() if uid not in cuts and any(
        peer.GetEffectiveShape(pcbnew.F_Cu).Collide(t.GetEffectiveShape(pcbnew.F_Cu), 0) for t in old)}
    _need(actual == expected, 'Source_RC_prefix_extra_external_contact_refused')
    union = pcbnew.SHAPE_POLY_SET()
    for track in old:
        _remaining(deadline)
        union.BooleanAdd(observer._elbow_polygon(track))
        _need(fr._tap_foreign_clear(board, track.GetStart(), track.GetEnd(), track.GetWidth(),
            pcbnew.F_Cu, anchor['clearance_nm'], {track.GetNetCode()}),
            'Source_RC_prefix_original_clearance_unknown_or_refused')
    _need(union.OutlineCount() == 1 and union.HoleCount(0) == 0,
          'Source_RC_prefix_single_hole_free_native_chain_required')
    contacts = []
    for uid in sorted(expected):
        peer = items[uid]; apertures = []
        for outside in (False, True):
            aperture = elbow._contact_union(old, peer, outside)
            _need(observer._elbow_positive(aperture), 'Source_RC_prefix_positive_external_aperture_required')
            apertures.append(observer._elbow_contours(aperture, deadline))
        owner_uid = force._uid(peer.GetParentFootprint()) if peer.GetClass() == 'PAD' else uid
        contacts.append(dict(native_uuid=uid, kind=peer.GetClass(), literal_owner_uuid=owner_uid,
            source_node=nodes[owner_uid],
            lower_contours=apertures[0], upper_contours=apertures[1]))
    result = dict(schema=1, scope='Source_canonical_root_exclusive_RC_input_prefix',
        Source_node_observation=node, anchor_elbow=anchor, source=str(source),
        source_sha256=force._hash(source), input_pad_uuid=pad_uuid,
        anchor_span_uuids=anchor['internal_span_uuids'], retired_track_uuids=sorted(cuts),
        derived_root_prefix_uuids=sorted(prefix_ids), source_points_nm=[list(p) for p in points],
        source_width_nm=anchor['source_width_nm'], clearance_nm=anchor['clearance_nm'],
        layer=anchor['layer'], source_cut_nodes={u: nodes[u] for u in sorted(cuts)},
        retained_contacts=contacts, fixed_filter_port=far_ports[0],
        complete=True, retirement_authority=False, route_admission=False, pose_authority=False,
        current_qualified=False, kelvin_qualified=False, release_authority=False)
    elbow._live(result, board, source, board_hint, deadline)
    return result


def _geometry(points, observation):
    _need(type(points) is list and 3 <= len(points) <= 12 and all(type(p) is list and len(p) == 2
        and all(type(v) is int and abs(v) <= 2000000000 for v in p) for p in points),
        'literal_bounded_Source_RC_prefix_points_required')
    original = observation['source_points_nm']
    _need(points[0] == original[0] and points[-1] == original[-1],
          'unchanged_Source_measurement_and_filter_ports_required')
    integer.length_terms(points); simple._simple_reuse_path([tuple(p) for p in points])
    length = lambda ps: sum(math.dist(a, b) for a, b in zip(ps, ps[1:]))
    _need(points != original and length(points) <= length(original)+2000000,
          'bounded_changed_Source_RC_prefix_length_required')
    sign = lambda a, b: tuple((b[k] > a[k])-(b[k] < a[k]) for k in (0, 1))
    _need(sign(*points[:2]) == sign(*original[:2]) and sign(*points[-2:]) == sign(*original[-2:]),
          'unchanged_Source_RC_prefix_launch_and_arrival_tangents_required')
    for a, b in zip(points, points[1:]):
        _need(max(abs(b[k]-a[k]) for k in (0, 1)) >= 20000,
              'physical_Source_RC_prefix_segment_required')
    for a, b, c in zip(points, points[1:], points[2:]):
        u = [b[k]-a[k] for k in (0, 1)]; v = [c[k]-b[k] for k in (0, 1)]
        dot = sum(x*y for x, y in zip(u, v)); cross = u[0]*v[1]-u[1]*v[0]
        _need(dot > 0 and abs(cross) <= dot, 'Source_RC_prefix_new_turns_at_most_45_degrees_required')


def _path_clear(board, observation, points, deadline):
    ids = set(observation['retired_track_uuids'])
    old = [t for t in board.GetTracks() if force._uid(t) in ids]
    _need(len(old) == len(ids), 'all_derived_Source_RC_prefix_edges_required')
    width = observation['source_width_nm']; face = observation['layer']; gap = observation['clearance_nm']
    net = old[0].GetNetCode(); incoming = []
    for a, b in zip(points, points[1:]):
        t = old[0].Duplicate(); t.SetStart(pcbnew.VECTOR2I(*a)); t.SetEnd(pcbnew.VECTOR2I(*b)); incoming.append(t)
    cache = {}; areas = [r['shape'] for r in rules.areas(board, 'tracks') if face in r['layers']]
    for t in incoming:
        _remaining(deadline)
        _need(fr._edge_leg_clear(board, t.GetStart(), t.GetEnd(), (width+1)//2+gap)
            and fr._tap_foreign_clear(board, t.GetStart(), t.GetEnd(), width, face, gap, {net}, foreign_cache=cache)
            and not any(shape.Collide(t.GetEffectiveShape(face), 0) for shape in areas),
            'Source_RC_prefix_foreign_edge_or_rule_clearance')
    expected = {r['native_uuid'] for r in observation['retained_contacts']}; actual = set(); apertures = []
    for peer in [*(p for fp in board.GetFootprints() for p in fp.Pads()), *board.GetTracks()]:
        _remaining(deadline); uid = force._uid(peer)
        if uid in ids or peer.GetNetCode() != net or not peer.IsOnLayer(face):
            continue
        touched = any(peer.GetEffectiveShape(face).Collide(t.GetEffectiveShape(face), 0) for t in incoming)
        upper = elbow._contact_union(incoming, peer, True)
        if not touched and upper.OutlineCount() == 0:
            continue
        _need(uid in expected, 'Source_RC_prefix_acquired_same_net_contact:'+uid)
        for outside in (False, True):
            before = elbow._contact_union(old, peer, outside); after = elbow._contact_union(incoming, peer, outside)
            _need(observer._elbow_positive(before) and observer._elbow_positive(after)
                and elbow._same_native(before, after), 'Source_RC_prefix_contact_aperture_changed:'+uid)
        actual.add(uid); apertures.append(dict(native_uuid=uid, inside_union_equal=True, outside_union_equal=True,
            both_direction_subtractions_empty=True))
    _need(actual == expected, 'all_original_Source_RC_prefix_contacts_required')
    _remaining(deadline)
    return dict(complete=True, retained_contacts=sorted(apertures, key=lambda r: r['native_uuid']),
        exact_native_integer_apertures=True, no_area_or_bounding_box_tolerance=True)


def plan(board, source, *, board_hint, pad_uuid, span_uuids, points_nm, timeout_s=10.):
    deadline = _deadline(timeout_s); source = Path(source).resolve(strict=True)
    observed = _observe(board, source, board_hint=board_hint, pad_uuid=pad_uuid,
        span_uuids=span_uuids, deadline=deadline)
    _geometry(points_nm, observed); guard = _path_clear(board, observed, points_nm, deadline)
    elbow._live(observed, board, source, board_hint, deadline)
    return dict(schema=1, scope='Source_canonical_fixed_port_RC_input_prefix_reanchor',
        source=str(source), board_hint=board_hint, pad_uuid=pad_uuid,
        span_uuids=observed['anchor_span_uuids'], points_nm=copy.deepcopy(points_nm),
        Source_observation=observed, native_path_guard=guard, producer_sha256=force._hash(Path(__file__)),
        Source_retirements_independently_derived_not_caller_permissions=True,
        all_other_Source_objects_and_external_terminals_must_remain_literal=True,
        saved_independent_and_absolute_measurement_receiving_required=True,
        routing_admitted=False, pose_authority=False, current_qualified=False,
        kelvin_qualified=False, release_authority=False)


def _cut_text(source, ids):
    text = Path(source).read_text(); objects, _, _, _ = literal._inventory(text)
    _need(type(ids) in (list, tuple) and 4 <= len(ids) <= 7 and len(set(ids)) == len(ids)
        and all(uid in objects and literal.kind(objects[uid][2]) == 'segment' for uid in ids),
        'derived_literal_Source_RC_prefix_retirements_required')
    for a, b, unused in sorted((objects[uid] for uid in ids), reverse=True):
        text = text[:a]+text[b:]
    return text


def construct_private(source, candidate, proposal, *, timeout_s=10.):
    """Construct a distinct exact private copy; no saved verdict is forwarded."""
    deadline = _deadline(timeout_s)
    source, candidate = [Path(p).resolve(strict=True) for p in (source, candidate)]
    _need(not source.samefile(candidate) and source.read_bytes() == candidate.read_bytes()
        and force._sidecars(source) == force._sidecars(candidate), 'exact_private_Source_RC_prefix_copy_required')
    epoch = force._code_identity(); family = force._family(source, proposal['board_hint'])
    board = pcbnew.LoadBoard(str(source))
    fresh = plan(board, source, board_hint=proposal['board_hint'], pad_uuid=proposal['pad_uuid'],
        span_uuids=proposal['span_uuids'], points_nm=proposal['points_nm'], timeout_s=_remaining(deadline))
    _need(_identity(fresh) == _identity(proposal), 'fresh_exact_Source_RC_prefix_recipe_required')
    ids = fresh['Source_observation']['retired_track_uuids']
    old = [t for t in board.GetTracks() if force._uid(t) in set(ids)]
    exemplar = old[0].Duplicate(); discard_items(board, old); incoming = []
    for a, b in zip(fresh['points_nm'], fresh['points_nm'][1:]):
        t = exemplar.Duplicate(); t.m_Uuid.Clone(pcbnew.KIID())
        t.SetStart(pcbnew.VECTOR2I(*a)); t.SetEnd(pcbnew.VECTOR2I(*b)); board.Add(t); incoming.append(force._uid(t))
    additive._ground_refill(board); _remaining(deadline)
    with tempfile.TemporaryDirectory(prefix='cec-RC-prefix-native-') as work:
        native = Path(work)/'board.kicad_pcb'; field._save_field_snapshot(board, native)
        ground = [force._uid(z) for z in board.Zones() if z.GetNetname() == 'GND' and not z.GetIsRuleArea()]
        candidate.write_text(literal.assemble(_cut_text(source, ids), native.read_text(), ground_ids=ground))
    _need(field._field_snapshot_inventory(board) == field._field_snapshot_inventory(pcbnew.LoadBoard(str(candidate))),
          'literal_saved_RC_prefix_native_identity_changed')
    _need(epoch == force._code_identity() and family == force._family(source, proposal['board_hint']),
          'Source_RC_prefix_Source_or_code_changed')
    _remaining(deadline)
    return dict(complete=True, candidate=str(candidate), candidate_sha256=force._hash(candidate),
        incoming_track_uuids=incoming, retired_track_uuids=ids, routing_admitted=False,
        independent_saved_and_absolute_measurement_receiving_pending=True, release_authority=False)


def receive(source, candidate, *, board_hint, pad_uuid, span_uuids, timeout_s=10.):
    """Three fresh <=10 s stages; no supplied cut list, cached verdict or override."""
    started = time.monotonic()
    r = dict(ok=False, complete=False, errors=[], stages=[], scope_only=True, routing_admitted=False,
        pose_authority=False, current_qualified=False, kelvin_qualified=False, release_authority=False,
        whole_parent_native_current_field_return_and_absolute_measurement_receiving_required=True)
    try:
        _deadline(timeout_s); aggregate_deadline = started+3*timeout_s
        names = ('fresh_canonical_saved_path', 'exact_additive_Ground', 'partitions_restoration_final_identity')
        r['bounded_composition'] = dict(stage_order=list(names), constituent_count=3,
            constituent_timeout_s=timeout_s, aggregate_timeout_s=3*timeout_s,
            individual_leases_extended=False, cached_verdicts_used=False)

        class Stage:
            def __init__(self, name):
                self.row = dict(name=name, complete=False)
            def __enter__(self):
                self.started = time.monotonic(); self.deadline = min(self.started+timeout_s, aggregate_deadline)
                r['stages'].append(self.row); _remaining(self.deadline)
                return self.deadline
            def __exit__(self, kind, exc, traceback):
                self.row['elapsed_s'] = time.monotonic()-self.started
                if exc is not None:
                    self.row['error'] = type(exc).__name__+':'+str(exc)
                    return False
                if time.monotonic() >= self.deadline:
                    self.row['error'] = 'Source_RC_prefix_deadline'
                _remaining(self.deadline); self.row['complete'] = True

        def epoch_live(deadline):
            _need(epoch == force._code_identity()
                and families == [force._family(p, board_hint) for p in (source, candidate)],
                'saved_RC_prefix_family_or_code_changed')
            _remaining(deadline)

        with Stage(names[0]) as deadline:
            source, candidate = [Path(p).resolve(strict=True) for p in (source, candidate)]
            _need(not source.samefile(candidate) and force._sidecars(source) == force._sidecars(candidate),
                  'distinct_exact_companion_RC_prefix_candidate_required')
            families = [force._family(p, board_hint) for p in (source, candidate)]; epoch = force._code_identity()
            parent, child = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
            _need(parent is not None and child is not None, 'both_saved_native_RC_prefix_boards_required')
            unused, old = additive._nodes(source); unused, new = additive._nodes(candidate)
            incoming = new.keys()-old.keys()
            _need(2 <= len(incoming) <= 11, 'bounded_RC_prefix_additions_required')
            tracks = [t for t in child.GetTracks() if force._uid(t) in incoming]
            _need(len(tracks) == len(incoming) and all(t.GetClass() == 'PCB_TRACK' for t in tracks),
                  'RC_prefix_cannot_add_barrels_or_other_objects')
            points = [list(p) for p in chains._chain(tracks)]
            # Endpoint ordering is rederived from the unchanged actual pad.
            roots = [p for fp in parent.GetFootprints() for p in fp.Pads() if force._uid(p) == pad_uuid]
            _need(len(roots) == 1, 'same_Source_RC_prefix_input_required')
            if roots[0].GetEffectiveShape(pcbnew.F_Cu).Collide(pcbnew.VECTOR2I(*points[-1])):
                points.reverse()
            fresh = plan(parent, source, board_hint=board_hint, pad_uuid=pad_uuid,
                span_uuids=span_uuids, points_nm=points, timeout_s=_remaining(deadline))
            r['Source_plan'] = fresh; ids = fresh['Source_observation']['retired_track_uuids']
            _need(old.keys()-new.keys() == set(ids), 'exact_independently_derived_RC_prefix_cuts_required')
            epoch_live(deadline)

        with Stage(names[1]) as deadline:
            epoch_live(deadline); elbow._live(fresh['Source_observation'], parent, source, board_hint, deadline)
            process = chains._process(old[ids[0]])
            _need(all(chains._process(old[u]) == process for u in ids)
                and all(chains._process(new[u]) == process for u in incoming),
                'Source_RC_prefix_process_width_face_net_or_lock_changed')
            ground = [force._uid(z) for z in parent.Zones() if z.GetNetname() == 'GND' and not z.GetIsRuleArea()]
            _need(candidate.read_text() == literal.assemble(_cut_text(source, ids), candidate.read_text(), ground_ids=ground),
                  'RC_prefix_unowned_Source_literal_or_root_changed')
            with tempfile.TemporaryDirectory(prefix='cec-RC-prefix-independent-') as work:
                projected = force._copy_family(source, Path(work)/'Source-minus-derived-prefix')
                projected.write_text(_cut_text(source, ids))
                proof = additive.receive(projected, candidate, timeout_s=_remaining(deadline), board_hint=board_hint)
                r['independent_exact_additions_and_native_Ground_refill'] = proof
                _need(proof.get('ok') is True and proof.get('complete') is True,
                      'independent_RC_prefix_additive_or_actual_Ground_refill_refused:'+str(proof.get('errors')))
            elbow._live(fresh['Source_observation'], parent, source, board_hint, deadline); epoch_live(deadline)

        with Stage(names[2]) as deadline:
            epoch_live(deadline); elbow._live(fresh['Source_observation'], parent, source, board_hint, deadline)
            old_parts = partitions._partition(parent, deadline, retired_uuids=set(ids))
            retained = set().union(*old_parts)
            new_parts = partitions._partition(child, deadline, retained_keys=retained)
            _need(all(any(p <= q for q in new_parts) for p in old_parts), 'RC_prefix_lost_Source_partition')
            net = fresh['Source_observation']['Source_node_observation']['node_net']
            graph = pcbnew.CONNECTIVITY_DATA()
            items = [p for fp in child.GetFootprints() for p in fp.Pads() if p.GetNetname() == net]
            items += [t for t in child.GetTracks() if t.GetNetname() == net]
            _need(len(items) <= 80, 'bounded_saved_RC_prefix_node_graph_required')
            for item in items:
                _remaining(deadline); _need(graph.Add(item), 'saved_RC_prefix_native_graph_refused')
            roots = [p for p in items if force._uid(p) == pad_uuid]
            _need(len(roots) == 1, 'same_saved_RC_prefix_input_required')
            reached = {pad_uuid} | {force._uid(i) for i in graph.GetConnectedItems(roots[0])}
            _need(reached == {force._uid(i) for i in items}, 'entire_saved_RC_prefix_node_not_restored')
            elbow._live(fresh['Source_observation'], parent, source, board_hint, deadline); epoch_live(deadline)
            source_hash, candidate_hash = force._hash(source), force._hash(candidate)
        _remaining(aggregate_deadline)
        r.update(ok=True, complete=True, source_sha256=source_hash, candidate_sha256=candidate_hash,
            incoming_track_uuids=sorted(incoming), retired_track_uuids=ids,
            exact_fixed_ports_canonical_node_and_unowned_Source_preservation=True)
    except (ValueError, RuntimeError, KeyError, TypeError, OSError, TimeoutError) as exc:
        r['errors'].append(type(exc).__name__+':'+str(exc))
    r['elapsed_s'] = time.monotonic()-started
    if r['ok'] and r['elapsed_s'] > 3*timeout_s:
        r.update(ok=False, complete=False); r['errors'].append('ValueError:Source_RC_prefix_aggregate_deadline')
    return r
