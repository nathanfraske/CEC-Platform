"""Experimental fixed-port reflow of a positively selected RC input span.

Fresh Source manufacturer/canonical/filter facts own exactly one internal
edge; no force/shunt/pad/zone/barrel may be retired. This is NOT ordinary-net
reclassification, measurement qualification or whole-parent route admission.
"""
import copy
import json
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_cell_row_rebuild as binding
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_kelvin_copper_cut as cut
import cec_measurement_filter_span as observer
import cec_native_ground_span_reflow as simple
import cec_native_rule_areas as rules
import cec_ordinary_route_receiving as partitions
import cec_pair_local_reference_refinement as chains
import cec_route_quality as quality
import cec_source_guided_ordinary_detour as integer
import cec_source_literal_additions as literal
import cec_source_netlist_semantics as semantic
from cec_native_items import discard_items


def _need(ok, reason):
    if not ok:
        raise ValueError(reason)


def _deadline(seconds):
    _need(type(seconds) in (int, float) and math.isfinite(seconds) and 0 < seconds <= 10.,
          'bounded_Source_RC_span_lease_required')
    return time.monotonic()+seconds


def _remaining(deadline):
    value = deadline-time.monotonic()
    _need(value > 0, 'Source_RC_span_deadline')
    return min(value, 10.)


def _identity(proposal):
    q = copy.deepcopy(proposal)
    q['Source_observation'].pop('elapsed_s', None)
    context = q['Source_observation']['source_context']
    context['exporter'] = semantic.replay_identity({'exporter':context['exporter']})['exporter']
    return json.dumps(q, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _geometry(points, observation):
    _need(type(points) is list and 4 <= len(points) <= 8
          and all(type(p) is list and len(p) == 2
                  and all(type(v) is int and abs(v) <= 2000000000 for v in p) for p in points),
          'literal_bounded_RC_span_points_required')
    original = observation['source_points_nm']
    _need([points[0], points[-1]] == original, 'unchanged_exact_RC_span_ports_required')
    integer.length_terms(points); simple._simple_reuse_path([tuple(p) for p in points])
    _need(points != original and sum(math.dist(a,z) for a,z in zip(points,points[1:]))
          <= math.dist(*original)+2000000, 'bounded_changed_RC_span_length_required')
    sign = lambda a,z:tuple((z[k]>a[k])-(z[k]<a[k]) for k in (0,1))
    tangent = sign(*original)
    _need(sign(*points[:2]) == tangent and sign(*points[-2:]) == tangent,
          'unchanged_RC_span_launch_and_arrival_tangents_required')
    for a,z in zip(points,points[1:]):
        _need(max(abs(z[k]-a[k]) for k in (0,1)) >= 20000,
              'physical_RC_span_phase_length_required')
    for a,b,c in zip(points,points[1:],points[2:]):
        u = [b[k]-a[k] for k in (0,1)]; v = [c[k]-b[k] for k in (0,1)]
        dot = sum(x*y for x,y in zip(u,v)); cross = u[0]*v[1]-u[1]*v[0]
        _need(dot > 0 and abs(cross) <= dot, 'RC_span_new_turns_at_most_45_degrees_required')


def _path_clear(board, observation, points, deadline):
    """Actual foreign/edge/rule checks and no acquired same-net contacts."""
    from shapely.geometry import LineString
    width = observation['source_width_nm']; face = observation['layer']
    net = board.GetNetcodeFromNetname(observation['node_net'])
    _need(net > 0, 'actual_Source_RC_net_required')
    gap = observation['clearance_nm']; cache = {}
    areas = [r['shape'] for r in rules.areas(board, 'tracks') if face in r['layers']]
    for a,z in zip(points,points[1:]):
        _remaining(deadline); start,end = pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*z)
        _need(fr._edge_leg_clear(board,start,end,(width+1)//2+gap)
              and fr._tap_foreign_clear(board,start,end,width,face,gap,{net},foreign_cache=cache)
              and not any(shape.Collide(pcbnew.SHAPE_SEGMENT(start,end,width),0) for shape in areas),
              'Source_RC_span_foreign_edge_or_rule_clearance')
    body = LineString(points).buffer(width/2+1000, quad_segs=64)
    # The Source edge's original capsule is the whole permissible boundary
    # aperture. Its two retained peers point away from that edge; the fresh
    # observer rejects every interior/body tap before this check is possible.
    kernel = LineString(observation['source_points_nm']).buffer(width/2+1002, quad_segs=64)
    expected = {q['native_uuid'] for q in observation['retained_endcaps']}; contacts = set()
    work = cut._Work(deadline)
    for item in [*(p for fp in board.GetFootprints() for p in fp.Pads()),*board.GetTracks()]:
        _remaining(deadline)
        if item.GetNetCode() != net or not item.IsOnLayer(face):
            continue
        shape = cut._shape(item, face, True, work)
        overlap = body.intersection(shape)
        if overlap.is_empty:
            continue
        uid = force._uid(item)
        _need(uid in expected and overlap.difference(kernel).is_empty,
              'Source_RC_span_acquired_or_overhanging_same_net_contact:'+uid)
        contacts.add(uid)
    _need(contacts == expected, 'both_original_RC_span_boundary_contacts_required')
    return dict(complete=True, retained_contact_uuids=sorted(contacts),
                exact_original_boundary_aperture_only=True)


def plan(board, source, *, board_hint, pad_uuid, span_uuid, points_nm, timeout_s=10.):
    deadline = _deadline(timeout_s); source = Path(source).resolve(strict=True)
    sha = force._hash(source)
    observed = observer.plan(board, source, board_hint=board_hint, pad_uuid=pad_uuid,
        span_uuid=span_uuid, expected_source_sha256=sha, timeout_s=_remaining(deadline))
    _geometry(points_nm, observed)
    private = pcbnew.LoadBoard(str(source))
    discard_items(private, [t for t in private.GetTracks() if force._uid(t) == span_uuid])
    clearance = _path_clear(private, observed, points_nm, deadline)
    _remaining(deadline)
    return dict(schema=1, scope='Source_typed_RC_internal_fixed_port_span_reflow',
        source=str(source), board_hint=board_hint, pad_uuid=pad_uuid, span_uuid=span_uuid,
        points_nm=copy.deepcopy(points_nm), Source_observation=observed,
        prototype_sha256=force._hash(Path(__file__)), native_path_guard=clearance,
        bounded_exact_single_Source_edge_reconstruction_only=True,
        all_fixed_force_pours_shunts_pads_barrels_and_other_edges_must_remain_exact=True,
        saved_independent_replay_and_absolute_measurement_receiving_still_required=True,
        routing_admitted=False, current_qualified=False, kelvin_qualified=False,
        release_authority=False)


def _cut_text(source, span_uuid):
    text = Path(source).read_text(); objects,_,_,_ = literal._inventory(text)
    _need(span_uuid in objects and literal.kind(objects[span_uuid][2]) == 'segment',
          'one_actual_literal_RC_span_retirement_required')
    a,b,_ = objects[span_uuid]
    return text[:a]+text[b:]


def construct_private(source, candidate, proposal, *, timeout_s=10.):
    deadline = _deadline(timeout_s)
    source,candidate = [Path(p).resolve(strict=True) for p in (source,candidate)]
    _need(source != candidate and source.read_bytes() == candidate.read_bytes()
          and force._sidecars(source) == force._sidecars(candidate), 'exact_private_RC_span_Source_copy_required')
    epoch = force._code_identity(); family = force._family(source,proposal['board_hint'])
    board = pcbnew.LoadBoard(str(source))
    fresh = plan(board,source,board_hint=proposal['board_hint'],pad_uuid=proposal['pad_uuid'],
        span_uuid=proposal['span_uuid'],points_nm=proposal['points_nm'],timeout_s=_remaining(deadline))
    _need(_identity(fresh) == _identity(proposal), 'fresh_exact_Source_RC_span_recipe_required')
    old = next(t for t in board.GetTracks() if force._uid(t) == fresh['span_uuid'])
    exemplar = old.Duplicate(); discard_items(board,[old]); incoming = []
    for a,z in zip(fresh['points_nm'],fresh['points_nm'][1:]):
        t = exemplar.Duplicate(); t.m_Uuid.Clone(pcbnew.KIID())
        t.SetStart(pcbnew.VECTOR2I(*a)); t.SetEnd(pcbnew.VECTOR2I(*z)); board.Add(t)
        incoming.append(force._uid(t))
    additive._ground_refill(board)
    with tempfile.TemporaryDirectory(prefix='cec-RC-span-native-') as work:
        native = Path(work)/'board.kicad_pcb'; field._save_field_snapshot(board,native)
        ground = [force._uid(z) for z in board.Zones() if z.GetNetname() == 'GND' and not z.GetIsRuleArea()]
        text = literal.assemble(_cut_text(source,fresh['span_uuid']),native.read_text(),ground_ids=ground)
        candidate.write_text(text)
    _need(field._field_snapshot_inventory(board) == field._field_snapshot_inventory(pcbnew.LoadBoard(str(candidate))),
          'literal_saved_RC_span_native_identity_changed')
    _need(epoch == force._code_identity() and family == force._family(source,proposal['board_hint']),
          'RC_span_Source_or_code_changed')
    _remaining(deadline)
    return dict(complete=True,incoming_track_uuids=incoming,
                retired_track_uuids=[fresh['span_uuid']],routing_admitted=False,
                independent_saved_and_absolute_measurement_receiving_pending=True,release_authority=False)


def receive(source, candidate, *, board_hint, pad_uuid, span_uuid, timeout_s=10.):
    """Fresh scope/delta/process/contacts/partitions ONLY, never full routing."""
    r = dict(ok=False,complete=False,errors=[],scope_only=True,routing_admitted=False,
             current_qualified=False,kelvin_qualified=False,release_authority=False,
             whole_parent_native_current_field_return_and_absolute_measurement_receiving_required=True)
    try:
        deadline = _deadline(timeout_s)
        source,candidate = [Path(p).resolve(strict=True) for p in (source,candidate)]
        _need(source != candidate and force._sidecars(source) == force._sidecars(candidate),
              'distinct_exact_companion_RC_span_candidate_required')
        family = [force._family(p,board_hint) for p in (source,candidate)]; epoch = force._code_identity()
        parent,child = [pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        _need(parent is not None and child is not None, 'both_saved_native_RC_span_boards_required')
        old_root,old = additive._nodes(source); new_root,new = additive._nodes(candidate)
        incoming = new.keys()-old.keys()
        _need(old.keys()-new.keys() == {span_uuid} and 3 <= len(incoming) <= 7,
              'exact_single_RC_span_cut_and_bounded_additions_required')
        tracks = [t for t in child.GetTracks() if force._uid(t) in incoming]
        _need(len(tracks) == len(incoming) and all(t.GetClass() == 'PCB_TRACK' for t in tracks),
              'RC_span_cannot_add_barrels_or_other_objects')
        points = [list(p) for p in chains._chain(tracks)]
        original = next(t for t in parent.GetTracks() if force._uid(t) == span_uuid)
        if points[0] != list(original.GetStart()):
            points.reverse()
        fresh = plan(parent,source,board_hint=board_hint,pad_uuid=pad_uuid,
                     span_uuid=span_uuid,points_nm=points,timeout_s=_remaining(deadline))
        process = chains._process(old[span_uuid])
        _need(all(chains._process(new[u]) == process for u in incoming),
              'Source_RC_span_process_width_face_net_or_lock_changed')
        ground = [force._uid(z) for z in parent.Zones() if z.GetNetname() == 'GND' and not z.GetIsRuleArea()]
        exact = literal.assemble(_cut_text(source,span_uuid),candidate.read_text(),ground_ids=ground)
        _need(candidate.read_text() == exact, 'RC_span_unowned_Source_AST_or_root_changed')
        with tempfile.TemporaryDirectory(prefix='cec-RC-span-independent-') as work:
            projected = force._copy_family(source,Path(work)/'Source-minus-exact-span')
            projected.write_text(_cut_text(source,span_uuid))
            additive_proof = additive.receive(projected,candidate,
                timeout_s=_remaining(deadline),board_hint=board_hint)
            _need(additive_proof['ok'] and additive_proof['complete'],
                  'independent_RC_span_additive_or_actual_Ground_refill_refused:'+str(additive_proof['errors']))
        old_parts = partitions._partition(parent,deadline,retired_uuids={span_uuid})
        retained = set().union(*old_parts)
        new_parts = partitions._partition(child,deadline,retained_keys=retained)
        _need(all(any(p <= q for q in new_parts) for p in old_parts), 'RC_span_lost_Source_partition')
        # Fresh native graph must still contain the exact three Source lands
        # and every retained/new node edge in one component.
        obs = fresh['Source_observation']; net = obs['node_net']
        graph = pcbnew.CONNECTIVITY_DATA()
        items = [p for fp in child.GetFootprints() for p in fp.Pads() if p.GetNetname() == net]
        items += [t for t in child.GetTracks() if t.GetNetname() == net]
        _need(len(items) <= 80, 'bounded_saved_RC_node_graph_required')
        for item in items:
            _need(graph.Add(item), 'saved_RC_node_native_graph_refused')
        root = next(p for p in items if force._uid(p) == pad_uuid)
        reached = {pad_uuid} | {force._uid(i) for i in graph.GetConnectedItems(root)}
        _need(reached == {force._uid(i) for i in items}, 'entire_saved_RC_node_not_restored')
        _remaining(deadline)
        _need(epoch == force._code_identity() and family == [force._family(p,board_hint) for p in (source,candidate)],
              'saved_RC_span_family_or_code_changed')
        r.update(ok=True,complete=True,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
                 Source_plan=fresh,incoming_track_uuids=sorted(incoming),
                 independent_exact_additions_and_native_Ground_refill=additive_proof,
                 exact_fixed_port_three_land_node_and_unowned_Source_preservation=True)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError,TimeoutError) as exc:
        r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
