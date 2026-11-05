"""Exact three-edge Source RC elbow reconstruction and independent receiving.

Only a fresh manufacturer/canonical RC observation can identify the cut. This
scope is not an ordinary-net exception or current/Kelvin/route qualification.
All enclosing current, field, return, craft and fabrication gates remain due.
The existing single-span observer and build receiver are intentionally separate.
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
from cec_native_items import discard_items


def _need(ok, reason):
    if not ok:
        raise ValueError(reason)


def _deadline(seconds):
    _need(type(seconds) in (int, float) and math.isfinite(seconds) and 0 < seconds <= 10.,
          'bounded_Source_RC_elbow_lease_required')
    return time.monotonic()+seconds


def _remaining(deadline):
    value = deadline-time.monotonic()
    _need(value > 0, 'Source_RC_elbow_deadline')
    return min(value, 10.)


def _identity(proposal):
    q = copy.deepcopy(proposal)
    obs = q['Source_observation']; obs.pop('elapsed_s', None)
    node = obs['Source_node_observation']; node.pop('elapsed_s', None)
    context = node['source_context']
    context['exporter'] = semantic.replay_identity({'exporter': context['exporter']})['exporter']
    return json.dumps(q, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _geometry(points, observation):
    _need(type(points) is list and 4 <= len(points) <= 8
        and all(type(p) is list and len(p) == 2
            and all(type(v) is int and abs(v) <= 2000000000 for v in p) for p in points),
        'literal_bounded_RC_elbow_points_required')
    original = observation['source_points_nm']
    _need(points[0] == original[0] and points[-1] == original[-1],
          'unchanged_exact_RC_elbow_ports_required')
    integer.length_terms(points); simple._simple_reuse_path([tuple(p) for p in points])
    length = lambda ps: sum(math.dist(a, b) for a, b in zip(ps, ps[1:]))
    _need(points != original and length(points) <= length(original)+2000000,
          'bounded_changed_RC_elbow_length_required')
    sign = lambda a, b: tuple((b[k] > a[k])-(b[k] < a[k]) for k in (0, 1))
    _need(sign(*points[:2]) == sign(*original[:2])
        and sign(*points[-2:]) == sign(*original[-2:]),
        'unchanged_RC_elbow_launch_and_arrival_tangents_required')
    for a, b in zip(points, points[1:]):
        _need(max(abs(b[k]-a[k]) for k in (0, 1)) >= 20000,
              'physical_RC_elbow_phase_length_required')
    for a, b, c in zip(points, points[1:], points[2:]):
        u = [b[k]-a[k] for k in (0, 1)]; v = [c[k]-b[k] for k in (0, 1)]
        dot = sum(x*y for x, y in zip(u, v)); cross = u[0]*v[1]-u[1]*v[0]
        _need(dot > 0 and abs(cross) <= dot, 'RC_elbow_new_turns_at_most_45_degrees_required')


def _contact_union(material, peer, outside):
    result = pcbnew.SHAPE_POLY_SET()
    for track in material:
        result.BooleanAdd(observer._elbow_intersection(track, peer, outside))
    return result


def _same_native(a, b):
    lost = pcbnew.SHAPE_POLY_SET(a); lost.BooleanSubtract(b)
    gained = pcbnew.SHAPE_POLY_SET(b); gained.BooleanSubtract(a)
    return lost.OutlineCount() == 0 and gained.OutlineCount() == 0


def _path_clear(board, observation, points, deadline):
    """Native foreign/edge/rule guards and EXACT full old/new port apertures."""
    width = observation['source_width_nm']; face = observation['layer']
    net = board.GetNetcodeFromNetname(observation['Source_node_observation']['node_net'])
    _need(net > 0, 'actual_Source_RC_elbow_net_required')
    ids = set(observation['internal_span_uuids'])
    old = [t for t in board.GetTracks() if force._uid(t) in ids]
    _need(len(old) == 3, 'three_actual_Source_RC_elbow_edges_required')
    incoming = []
    for a, b in zip(points, points[1:]):
        t = old[0].Duplicate(); t.SetStart(pcbnew.VECTOR2I(*a)); t.SetEnd(pcbnew.VECTOR2I(*b))
        incoming.append(t)
    gap = observation['clearance_nm']; cache = {}
    areas = [r['shape'] for r in rules.areas(board, 'tracks') if face in r['layers']]
    for t in incoming:
        _remaining(deadline)
        _need(fr._edge_leg_clear(board, t.GetStart(), t.GetEnd(), (width+1)//2+gap)
            and fr._tap_foreign_clear(board, t.GetStart(), t.GetEnd(), width, face, gap,
                {net}, foreign_cache=cache)
            and not any(shape.Collide(t.GetEffectiveShape(face), 0) for shape in areas),
            'Source_RC_elbow_foreign_edge_or_rule_clearance')
    expected = {r['native_uuid'] for port in observation['retained_ports'] for r in port['contacts']}
    actual = set(); apertures = []
    for peer in [*(p for fp in board.GetFootprints() for p in fp.Pads()), *board.GetTracks()]:
        _remaining(deadline); uid = force._uid(peer)
        if uid in ids or peer.GetNetCode() != net or not peer.IsOnLayer(face):
            continue
        native_touch = any(peer.GetEffectiveShape(face).Collide(t.GetEffectiveShape(face), 0) for t in incoming)
        upper_contact = _contact_union(incoming, peer, True)
        if not native_touch and upper_contact.OutlineCount() == 0:
            continue
        _need(uid in expected and peer.GetClass() == 'PCB_TRACK',
              'Source_RC_elbow_acquired_same_net_contact:'+uid)
        for outside in (False, True):
            before = _contact_union(old, peer, outside)
            after = _contact_union(incoming, peer, outside)
            _need(observer._elbow_positive(before) and observer._elbow_positive(after)
                and _same_native(before, after), 'Source_RC_elbow_contact_aperture_changed:'+uid)
        actual.add(uid)
        apertures.append(dict(native_uuid=uid, inside_union_equal=True, outside_union_equal=True,
            both_direction_subtractions_empty=True))
    _need(actual == expected, 'all_original_RC_elbow_boundary_contacts_required')
    _remaining(deadline)
    return dict(complete=True, retained_contacts=sorted(apertures, key=lambda r: r['native_uuid']),
        exact_native_integer_apertures=True, no_area_or_bounding_box_tolerance=True)


def _live(observation, board, source, board_hint, deadline):
    node = observation['Source_node_observation']; context = node['source_context']
    _need(node['source_native_binding'] == observer.row._source_binding(board)
        and node['family'] == force._family(source, board_hint)
        and node['code_identity'] == force._code_identity()
        and observation['source_sha256'] == force._hash(source)
        and all(force._hash(Path(p)) == h for p, h in context['schematic_files_sha256'].items())
        and force._hash(Path(context['exporter']['exporter'])) == context['exporter']['exporter_sha256'],
        'Source_RC_elbow_family_code_or_export_changed')
    semantic.replay_identity(dict(exporter=context['exporter']))
    _remaining(deadline)


def plan(board, source, *, board_hint, pad_uuid, span_uuids, points_nm, timeout_s=10.):
    deadline = _deadline(timeout_s); source = Path(source).resolve(strict=True)
    observed = observer.plan_elbow(board, source, board_hint=board_hint, pad_uuid=pad_uuid,
        span_uuids=span_uuids, expected_source_sha256=force._hash(source), timeout_s=_remaining(deadline))
    _geometry(points_nm, observed)
    clearance = _path_clear(board, observed, points_nm, deadline)
    _live(observed, board, source, board_hint, deadline)
    return dict(schema=1, scope='Source_typed_RC_internal_fixed_port_elbow_reflow',
        source=str(source), board_hint=board_hint, pad_uuid=pad_uuid,
        span_uuids=observed['internal_span_uuids'], points_nm=copy.deepcopy(points_nm),
        Source_observation=observed, native_path_guard=clearance,
        producer_sha256=force._hash(Path(__file__)),
        exact_three_Source_edges_only=True,
        all_fixed_force_pours_shunts_pads_barrels_groups_and_other_edges_must_remain_exact=True,
        saved_independent_replay_and_absolute_measurement_receiving_still_required=True,
        routing_admitted=False, current_qualified=False, kelvin_qualified=False, release_authority=False)


def _cut_text(source, ids):
    text = Path(source).read_text(); objects, _, _, _ = literal._inventory(text)
    _need(type(ids) in (list, tuple) and len(ids) == len(set(ids)) == 3
        and all(uid in objects and literal.kind(objects[uid][2]) == 'segment' for uid in ids),
        'three_actual_literal_RC_elbow_retirements_required')
    for a, b, unused in sorted((objects[uid] for uid in ids), reverse=True):
        text = text[:a]+text[b:]
    return text


def construct_private(source, candidate, proposal, *, timeout_s=10.):
    """Write a distinct exact private copy; independent receiving remains due."""
    deadline = _deadline(timeout_s)
    source, candidate = [Path(p).resolve(strict=True) for p in (source, candidate)]
    _need(not source.samefile(candidate) and source.read_bytes() == candidate.read_bytes()
        and force._sidecars(source) == force._sidecars(candidate), 'exact_private_RC_elbow_Source_copy_required')
    epoch = force._code_identity(); family = force._family(source, proposal['board_hint'])
    board = pcbnew.LoadBoard(str(source))
    fresh = plan(board, source, board_hint=proposal['board_hint'], pad_uuid=proposal['pad_uuid'],
        span_uuids=proposal['span_uuids'], points_nm=proposal['points_nm'], timeout_s=_remaining(deadline))
    _need(_identity(fresh) == _identity(proposal), 'fresh_exact_Source_RC_elbow_recipe_required')
    old = [t for t in board.GetTracks() if force._uid(t) in set(fresh['span_uuids'])]
    exemplar = old[0].Duplicate(); discard_items(board, old); incoming = []
    for a, b in zip(fresh['points_nm'], fresh['points_nm'][1:]):
        t = exemplar.Duplicate(); t.m_Uuid.Clone(pcbnew.KIID())
        t.SetStart(pcbnew.VECTOR2I(*a)); t.SetEnd(pcbnew.VECTOR2I(*b)); board.Add(t)
        incoming.append(force._uid(t))
    additive._ground_refill(board); _remaining(deadline)
    with tempfile.TemporaryDirectory(prefix='cec-RC-elbow-native-') as work:
        native = Path(work)/'board.kicad_pcb'; field._save_field_snapshot(board, native)
        ground = [force._uid(z) for z in board.Zones() if z.GetNetname() == 'GND' and not z.GetIsRuleArea()]
        text = literal.assemble(_cut_text(source, fresh['span_uuids']), native.read_text(), ground_ids=ground)
        candidate.write_text(text)
    _need(field._field_snapshot_inventory(board) == field._field_snapshot_inventory(pcbnew.LoadBoard(str(candidate))),
          'literal_saved_RC_elbow_native_identity_changed')
    _need(epoch == force._code_identity() and family == force._family(source, proposal['board_hint']),
          'RC_elbow_Source_or_code_changed')
    _remaining(deadline)
    return dict(complete=True, candidate=str(candidate), candidate_sha256=force._hash(candidate),
        incoming_track_uuids=incoming, retired_track_uuids=fresh['span_uuids'], routing_admitted=False,
        independent_saved_and_absolute_measurement_receiving_pending=True, release_authority=False)


def receive(source, candidate, *, board_hint, pad_uuid, span_uuids, timeout_s=10.):
    """Three fresh bounded constituents, never a longer native/API lease.

    ``timeout_s`` bounds EACH fixed stage, with an aggregate cap of exactly
    three such leases. No externally supplied or cached verdict can replace a
    stage. Family/code and canonical-file liveness span the whole composition.
    """
    started = time.monotonic()
    r = dict(ok=False, complete=False, errors=[], scope_only=True, routing_admitted=False,
        current_qualified=False, kelvin_qualified=False, release_authority=False,
        stages=[],
        whole_parent_native_current_field_return_and_absolute_measurement_receiving_required=True)
    try:
        _deadline(timeout_s)
        names = ('fresh_canonical_saved_path', 'exact_additive_Ground', 'partitions_restoration_final_identity')
        aggregate_deadline = started+3*timeout_s
        r['bounded_composition'] = dict(stage_order=list(names), constituent_count=3,
            constituent_timeout_s=timeout_s, aggregate_timeout_s=3*timeout_s,
            individual_leases_extended=False, cached_verdicts_used=False)

        class Stage:
            def __init__(self, name):
                self.row = dict(name=name, complete=False)
            def __enter__(self):
                self.started = time.monotonic()
                self.deadline = min(self.started+timeout_s, aggregate_deadline)
                r['stages'].append(self.row)
                if self.started >= self.deadline:
                    self.row.update(elapsed_s=0., error='Source_RC_elbow_deadline')
                _remaining(self.deadline)
                return self.deadline
            def __exit__(self, kind, exc, traceback):
                self.row['elapsed_s'] = time.monotonic()-self.started
                if exc is not None:
                    self.row['error'] = type(exc).__name__+':'+str(exc)
                    return False
                if time.monotonic() >= self.deadline:
                    self.row['error'] = 'Source_RC_elbow_deadline'
                _remaining(self.deadline)
                self.row['complete'] = True

        def epoch_live(deadline):
            _need(epoch == force._code_identity()
                and families == [force._family(p, board_hint) for p in (source, candidate)],
                'saved_RC_elbow_family_or_code_changed')
            _remaining(deadline)

        with Stage(names[0]) as deadline:
            source, candidate = [Path(p).resolve(strict=True) for p in (source, candidate)]
            _need(type(span_uuids) in (list, tuple) and len(span_uuids) == 3
                and all(type(uid) is str for uid in span_uuids) and len(set(span_uuids)) == 3,
                'three_explicit_Source_RC_elbow_identities_required')
            _need(not source.samefile(candidate) and force._sidecars(source) == force._sidecars(candidate),
                  'distinct_exact_companion_RC_elbow_candidate_required')
            families = [force._family(p, board_hint) for p in (source, candidate)]; epoch = force._code_identity()
            parent, child = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
            _need(parent is not None and child is not None, 'both_saved_native_RC_elbow_boards_required')
            unused, old = additive._nodes(source); unused, new = additive._nodes(candidate)
            incoming = new.keys()-old.keys()
            _need(old.keys()-new.keys() == set(span_uuids) and 3 <= len(incoming) <= 7,
                  'exact_three_RC_elbow_cuts_and_bounded_additions_required')
            tracks = [t for t in child.GetTracks() if force._uid(t) in incoming]
            _need(len(tracks) == len(incoming) and all(t.GetClass() == 'PCB_TRACK' for t in tracks),
                  'RC_elbow_cannot_add_barrels_or_other_objects')
            points = [list(p) for p in chains._chain(tracks)]
            fresh = plan(parent, source, board_hint=board_hint, pad_uuid=pad_uuid,
                span_uuids=span_uuids, points_nm=points, timeout_s=_remaining(deadline))
            r['Source_plan'] = fresh
            epoch_live(deadline)

        with Stage(names[1]) as deadline:
            epoch_live(deadline)
            _live(fresh['Source_observation'], parent, source, board_hint, deadline)
            process = chains._process(old[fresh['span_uuids'][0]])
            _need(all(chains._process(old[uid]) == process for uid in fresh['span_uuids'])
                and all(chains._process(new[uid]) == process for uid in incoming),
                'Source_RC_elbow_process_width_face_net_or_lock_changed')
            ground = [force._uid(z) for z in parent.Zones() if z.GetNetname() == 'GND' and not z.GetIsRuleArea()]
            exact = literal.assemble(_cut_text(source, fresh['span_uuids']), candidate.read_text(), ground_ids=ground)
            _need(candidate.read_text() == exact, 'RC_elbow_unowned_Source_literal_or_root_changed')
            with tempfile.TemporaryDirectory(prefix='cec-RC-elbow-independent-') as work:
                projected = force._copy_family(source, Path(work)/'Source-minus-exact-elbow')
                projected.write_text(_cut_text(source, fresh['span_uuids']))
                proof = additive.receive(projected, candidate, timeout_s=_remaining(deadline), board_hint=board_hint)
                r['independent_exact_additions_and_native_Ground_refill'] = proof
                _need(proof['ok'] and proof['complete'],
                      'independent_RC_elbow_additive_or_actual_Ground_refill_refused:'+str(proof['errors']))
            _live(fresh['Source_observation'], parent, source, board_hint, deadline)
            epoch_live(deadline)

        with Stage(names[2]) as deadline:
            epoch_live(deadline)
            _live(fresh['Source_observation'], parent, source, board_hint, deadline)
            old_parts = partitions._partition(parent, deadline, retired_uuids=set(span_uuids))
            retained = set().union(*old_parts)
            new_parts = partitions._partition(child, deadline, retained_keys=retained)
            _need(all(any(p <= q for q in new_parts) for p in old_parts), 'RC_elbow_lost_Source_partition')
            net = fresh['Source_observation']['Source_node_observation']['node_net']
            graph = pcbnew.CONNECTIVITY_DATA()
            items = [p for fp in child.GetFootprints() for p in fp.Pads() if p.GetNetname() == net]
            items += [t for t in child.GetTracks() if t.GetNetname() == net]
            _need(len(items) <= 80, 'bounded_saved_RC_elbow_node_graph_required')
            for item in items:
                _remaining(deadline); _need(graph.Add(item), 'saved_RC_elbow_node_native_graph_refused')
            roots = [p for p in items if force._uid(p) == pad_uuid]
            _need(len(roots) == 1, 'same_saved_RC_elbow_input_required')
            reached = {pad_uuid} | {force._uid(i) for i in graph.GetConnectedItems(roots[0])}
            _need(reached == {force._uid(i) for i in items}, 'entire_saved_RC_elbow_node_not_restored')
            _live(fresh['Source_observation'], parent, source, board_hint, deadline)
            epoch_live(deadline)
            final_source_sha256, final_candidate_sha256 = force._hash(source), force._hash(candidate)
        _remaining(aggregate_deadline)
        r.update(ok=True, complete=True, source_sha256=final_source_sha256, candidate_sha256=final_candidate_sha256,
            Source_plan=fresh, incoming_track_uuids=sorted(incoming), retired_track_uuids=fresh['span_uuids'],
            exact_fixed_port_three_land_node_and_unowned_Source_preservation=True)
    except (ValueError, RuntimeError, KeyError, TypeError, OSError, TimeoutError) as exc:
        r['errors'].append(type(exc).__name__+':'+str(exc))
    r['elapsed_s'] = time.monotonic()-started
    if r['ok'] and r['elapsed_s'] > 3*timeout_s:
        r.update(ok=False, complete=False)
        r['errors'].append('ValueError:Source_RC_elbow_aggregate_deadline')
    return r
