"""Explicit canonical RC input prefixes for complete moving-cell reconstruction.

A fixed retained conductor is a named physical port, NOT a fabricated native
junction or a longer ordinary measurement leaf. The complete three-terminal
canonical RC node supplies ownership; every remaining filter item stays fixed.
No current, Kelvin, placement or release qualification is granted here.
"""
import copy
import json
import math
from pathlib import Path
import re
import time

import pcbnew
import cec_force_current as force
import cec_fr as fr
import cec_measurement_filter_span as observer
import cec_measurement_leaf as leaf
import cec_native_rule_areas as rules
import cec_pair_local_reference_refinement as chains
import cec_source_netlist_semantics as semantic
import cec_source_rc_elbow_reflow as native
import cec_native_ground_span_reflow as simple
import cec_cell_row_rebuild as row

SCOPE = 'source_canonical_fixed_port_RC_input_prefix'
FIELDS = {'pad_uuid', 'canonical_span_uuid', 'boundary_track_uuid'}


def _need(ok, reason):
    if not ok:
        raise ValueError(reason)


def _remaining(deadline):
    left = deadline-time.monotonic()
    _need(left > 0, 'Source_RC_macro_prefix_deadline')
    return min(10., left)


def requests(values):
    _need(type(values) in (list, tuple) and len(values) <= 8,
          'bounded_explicit_Source_RC_prefix_identities_required')
    rows = []
    for value in values:
        _need(type(value) is dict and set(value) == FIELDS and all(type(v) is str
            and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', v) for v in value.values())
            and len(set(value.values())) == 3, 'literal_Source_RC_prefix_identity_only_request_required')
        rows.append(dict(value))
    _need(len({r['pad_uuid'] for r in rows}) == len(rows), 'unique_Source_RC_prefix_input_required')
    return sorted(rows, key=lambda r: r['pad_uuid'])


def _key(item):
    # force._item_key is only a connectivity token, not physical evidence.
    # Keep actual conductor/land geometry and both native copper envelopes.
    common = [item.GetClass(), force._uid(item), item.GetNetname(), bool(item.IsLocked()),
              list(map(int, item.GetLayerSet().Seq()))]
    if item.GetClass() == 'PAD':
        fp = item.GetParentFootprint()
        geometry = [force._uid(fp), fp.GetReference(), item.GetNumber(), list(item.GetPosition()),
            item.GetOrientationDegrees(), int(item.GetAttribute()), int(item.GetShape()),
            list(item.GetSize()), list(item.GetDrillSize()), list(item.GetOffset())]
    else:
        _need(item.GetClass() == 'PCB_TRACK', 'Source_RC_fixed_material_must_be_planar')
        geometry = [list(item.GetStart()), list(item.GetEnd()), int(item.GetLayer()),
                    int(item.GetWidth()), bool(item.HasSolderMask())]
    return json.loads(json.dumps(common+[geometry,
        observer._elbow_polygon(item, False).Format(),
        observer._elbow_polygon(item, True).Format()], allow_nan=False))


def _tracks(board, points, width, net, locked=True):
    result = []
    for a, b in zip(points, points[1:]):
        t = pcbnew.PCB_TRACK(board); t.SetStart(pcbnew.VECTOR2I(*a)); t.SetEnd(pcbnew.VECTOR2I(*b))
        t.SetLayer(pcbnew.F_Cu); t.SetWidth(width); t.SetNetCode(net); t.SetLocked(locked); result.append(t)
    return result


def plan(board, source, *, board_hint, request, timeout_s=10.):
    """Freshly derive the complete exclusive prefix to one real retained port."""
    selection = requests([request])[0]
    _need(type(timeout_s) in (int, float) and math.isfinite(timeout_s) and 0 < timeout_s <= 10,
          'bounded_Source_RC_macro_prefix_lease_required')
    deadline = time.monotonic()+timeout_s; source = Path(source).resolve(strict=True)
    node = observer.plan(board, source, board_hint=board_hint, pad_uuid=selection['pad_uuid'],
        span_uuid=selection['canonical_span_uuid'], expected_source_sha256=force._hash(source),
        timeout_s=_remaining(deadline))
    pad_uid = selection['pad_uuid']; port_uid = selection['boundary_track_uuid']
    ids = set(node['node_pad_uuids']+node['node_track_uuids'])
    items = {force._uid(p): p for f in board.GetFootprints() for p in f.Pads() if force._uid(p) in ids}
    items.update({force._uid(t): t for t in board.GetTracks() if force._uid(t) in ids})
    _need(set(items) == ids and port_uid in node['node_track_uuids'], 'complete_Source_RC_prefix_node_and_port_required')
    root = items[pad_uid]; port = items[port_uid]; face = pcbnew.F_Cu
    material = [items[u] for u in node['node_track_uuids']]
    touching = [t for t in material if t.GetEffectiveShape(face).Collide(root.GetEffectiveShape(face), 0)]
    _need(touching and port not in touching, 'nonempty_Source_RC_prefix_before_fixed_port_required')
    root_chain = chains._chain(touching)
    starts = [p for p in (root_chain[0], root_chain[-1])
        if root.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*p), 0)]
    _need(len(starts) == 1, 'one_actual_Source_RC_prefix_pad_departure_required')
    choices = [t for t in touching if starts[0] in (tuple(t.GetStart()), tuple(t.GetEnd()))]
    _need(len(choices) == 1, 'one_endpoint_linear_Source_RC_prefix_required')
    current = choices[0]; points = [starts[0]]; chosen = []; length = 0.
    width = current.GetWidth(); locked = current.IsLocked()
    while True:
        _remaining(deadline); uid = force._uid(current)
        _need(uid not in chosen and uid != port_uid and current.GetWidth() == width
            and current.IsLocked() == locked and current.GetLayer() == face,
            'uniform_acyclic_Source_RC_prefix_required')
        ends = (tuple(current.GetStart()), tuple(current.GetEnd()))
        _need(points[-1] in ends and ends[0] != ends[1], 'Source_RC_prefix_exact_endpoint_chain_required')
        far = ends[1] if ends[0] == points[-1] else ends[0]
        dx, dy = abs(far[0]-points[-1][0]), abs(far[1]-points[-1][1])
        _need(dx == 0 or dy == 0 or dx == dy, 'Source_RC_prefix_canonical_existing_chain_required')
        chosen.append(uid); points.append(far); length += current.GetLength()/1e6
        _need(len(chosen) <= 11 and length <= 8., 'bounded_short_Source_RC_prefix_required')
        contacts = []
        for other_uid, other in items.items():
            _remaining(deadline)
            if other_uid in chosen or other_uid == pad_uid:
                continue
            if not other.GetEffectiveShape(face).Collide(current.GetEffectiveShape(face), 0):
                continue
            _need(other.GetClass() == 'PCB_TRACK' and far in (tuple(other.GetStart()), tuple(other.GetEnd()))
                and other.GetEffectiveShape(face).Collide(pcbnew.SHAPE_SEGMENT(
                    pcbnew.VECTOR2I(*far), pcbnew.VECTOR2I(*far), width), 0),
                'Source_RC_prefix_other_terminal_or_interior_contact_refused')
            contacts.append(other)
        _need(len(contacts) == 1, 'Source_RC_prefix_complete_single_port_required')
        if force._uid(contacts[0]) == port_uid:
            break
        current = contacts[0]
    cut_ids = set(chosen)
    _need(selection['canonical_span_uuid'] not in cut_ids, 'canonical_filter_span_must_remain_fixed')
    old = [items[u] for u in chosen]
    actual = {u for u, peer in items.items() if u not in cut_ids and any(
        peer.GetEffectiveShape(face).Collide(t.GetEffectiveShape(face), 0) for t in old)}
    _need(actual == {pad_uid, port_uid}, 'exact_two_Source_RC_prefix_external_contacts_required')
    graph = pcbnew.CONNECTIVITY_DATA()
    for uid, item in items.items():
        _remaining(deadline)
        if uid not in cut_ids:
            _need(graph.Add(item), 'Source_RC_prefix_native_partition_refused')
    root_component = {pad_uid} | {force._uid(t) for t in graph.GetConnectedItems(root)}
    fixed_component = {port_uid} | {force._uid(t) for t in graph.GetConnectedItems(port)}
    _need(root_component == {pad_uid} and fixed_component == ids-cut_ids-{pad_uid}
        and fixed_component & set(node['node_pad_uuids']) == set(node['node_pad_uuids'])-{pad_uid},
        'Source_RC_prefix_one_input_and_complete_fixed_filter_partition_required')
    apertures = []
    for outside in (False, True):
        aperture = native._contact_union(old, port, outside)
        _need(observer._elbow_positive(aperture), 'positive_native_Source_RC_fixed_port_aperture_required')
        apertures.append(observer._elbow_contours(aperture, deadline))
    gap = max(node['clearance_nm'], *(int(fr._foreign_clearance_resolver(board)(t, face)) for t in old))
    for t in old:
        _remaining(deadline)
        _need(fr._tap_foreign_clear(board, t.GetStart(), t.GetEnd(), width, face, gap, {t.GetNetCode()}),
              'Source_RC_prefix_original_clearance_refused')
    context = node['source_context']
    _need(node['source_native_binding'] == row._source_binding(board)
        and node['family'] == force._family(source, board_hint)
        and node['code_identity'] == force._code_identity()
        and all(force._hash(Path(p)) == h for p, h in context['schematic_files_sha256'].items())
        and force._hash(Path(context['exporter']['exporter'])) == context['exporter']['exporter_sha256'],
        'Source_RC_prefix_family_code_or_canonical_identity_changed')
    # Only the existing validated export date policy is non-semantic. Keep
    # every tool/semantic/hierarchy/pin/net/process/current-anchor field.
    node = copy.deepcopy(node); node.pop('elapsed_s')
    node['source_context'] = semantic.replay_identity(node['source_context'])
    result = dict(schema=1, scope=SCOPE, pad_uuid=pad_uid, owner=root.GetParentFootprint().GetReference(),
        pin=root.GetNumber(), net=root.GetNetname(), layer=int(face), width_nm=int(width), clearance_nm=gap,
        track_uuids=chosen, points_nm=[list(p) for p in points], source_points_nm=[list(p) for p in points],
        boundary_uuids=[port_uid], source_boundary_entry_nm=[list(p) for p in points[-2:]],
        source_length_mm=length, source_native_binding=node['source_native_binding'],
        identity_request=selection, Source_node_observation=node, source=str(source), board_hint=board_hint,
        source_locked=bool(locked), retained_native_keys={u: _key(items[u]) for u in sorted(fixed_component)},
        fixed_filter_component_uuids=sorted(fixed_component), root_component_uuids=[pad_uid],
        fixed_port_lower_contours=apertures[0], fixed_port_upper_contours=apertures[1],
        physical_junction_not_invented=True, ordinary_leaf_limits_unchanged=True,
        current_authority=False, kelvin_qualified=False, routing_admitted=False, release_authority=False)
    _remaining(deadline)
    return json.loads(json.dumps(result, allow_nan=False))


def provisional_prefixes(source, posed, *, board_hint, identity_requests=(), timeout_s=10.):
    """Fresh Source scopes for metal which MUST disappear later in this frame.

    This is not a saved-board clearance exception. Only the isolated-supply
    transport's foreign-contact check may consume these records, and only
    for the same moving manufacturer owner. The compiler must prove complete
    retirement and a mandatory fixed-port restoration before using the frame.
    """
    selections = requests(identity_requests)
    _need(type(timeout_s) in (int, float) and math.isfinite(timeout_s) and 0 < timeout_s <= 10,
          'bounded_provisional_Source_RC_prefix_lease_required')
    if not selections:
        return []
    deadline = time.monotonic()+timeout_s
    old_pads = {force._uid(p): p for fp in source.GetFootprints() for p in fp.Pads()}
    new_pads = {force._uid(p): p for fp in posed.GetFootprints() for p in fp.Pads()}
    new_tracks = {force._uid(t): t for t in posed.GetTracks()}
    new_items = dict(new_pads, **new_tracks)
    result = []; seen = set()
    from cec_footprint_fields import footprint_properties
    for selection in selections:
        q = plan(source, source.GetFileName(), board_hint=board_hint, request=selection,
                 timeout_s=_remaining(deadline))
        old = old_pads[q['pad_uuid']]; new = new_pads.get(q['pad_uuid'])
        _need(new is not None, 'provisional_RC_manufacturer_input_missing')
        before = old.GetParentFootprint(); after = new.GetParentFootprint()
        _need(force._uid(before) == force._uid(after) and before.GetReference() == after.GetReference()
            and before.GetValue() == after.GetValue() and before.GetFPIDAsString() == after.GetFPIDAsString()
            and before.GetPath().AsString() == after.GetPath().AsString()
            and before.IsDNP() == after.IsDNP() and before.IsFlipped() == after.IsFlipped()
            and footprint_properties(before) == footprint_properties(after)
            and (before.GetPosition() != after.GetPosition()
                or before.GetOrientationDegrees() != after.GetOrientationDegrees()),
            'provisional_RC_same_actual_moving_manufacturer_owner_required')
        peers = {force._uid(p): p for p in after.Pads()}
        _need(set(peers) == {force._uid(p) for p in before.Pads()},
              'provisional_RC_complete_owner_pin_population_required')
        for pad in before.Pads():
            peer = peers[force._uid(pad)]
            _need(pad.GetNumber() == peer.GetNumber() and pad.GetNetname() == peer.GetNetname()
                and pad.GetPinType() == peer.GetPinType() and pad.GetPinFunction() == peer.GetPinFunction()
                and pad.GetAttribute() == peer.GetAttribute() and pad.GetShape() == peer.GetShape()
                and pad.GetSize() == peer.GetSize() and pad.GetOffset() == peer.GetOffset()
                and pad.GetDrillSize() == peer.GetDrillSize()
                and list(pad.GetLayerSet().Seq()) == list(peer.GetLayerSet().Seq()),
                'provisional_RC_owner_pin_identity_or_process_changed')
        _need(all(u in new_items and _key(new_items[u]) == key
            for u, key in q['retained_native_keys'].items()),
            'provisional_RC_fixed_filter_material_changed')
        _need(not seen & set(q['track_uuids']), 'provisional_RC_disjoint_complete_prefixes_required')
        for uid in q['track_uuids']:
            t = new_tracks.get(uid)
            _need(t is not None and t.GetClass() == 'PCB_TRACK' and t.GetNetname() == q['net']
                and t.GetLayer() == q['layer'] and t.GetWidth() == q['width_nm']
                and bool(t.IsLocked()) == q['source_locked'] and not t.HasSolderMask()
                and not t.GetParentGroup(), 'provisional_RC_cut_population_or_process_changed')
        seen.update(q['track_uuids']); result.append(q)
    _remaining(deadline)
    return result


def require_transport_retirements(proposal, transport, retired, *, draft=None, restored_requests=None):
    """Compose fresh canonical ownership, exact cuts and mandatory restoration.

    Called before removing any Source item and again on the completed request
    frame. Saved receiving independently recompiles both calls and then proves
    actual incoming copper/contact apertures; no serialized skip list is used.
    """
    prefixes = [q for q in proposal['measurement_leaves'] if q.get('scope') == SCOPE]
    declared = requests(proposal.get('source_rc_input_prefixes', ()))
    _need(requests([q['identity_request'] for q in prefixes]) == declared,
          'provisional_RC_complete_declared_canonical_prefixes_required')
    _need(len({q['pad_uuid'] for q in prefixes}) == len(prefixes),
          'provisional_RC_unique_canonical_prefix_required')
    stable = lambda q: json.loads(json.dumps(q, allow_nan=False))
    for component in transport.get('rigid_isolated_selected_bypass_supply_components', []):
        expected = sorted((q for q in prefixes
            if q['owner'] == component['source_selected_bypass']['owner']), key=lambda q: q['pad_uuid'])
        actual = component.get('mandatory_source_rc_prefix_retirements', [])
        _need(stable(actual) == stable(expected), 'provisional_RC_retirement_proof_missing_partial_or_stale')
        _need(not {u for q in actual for u in q['track_uuids']} & set(component['track_uuids']),
              'provisional_RC_cannot_retire_isolated_supply')
    retired = set(retired)
    items = None if draft is None else {force._uid(t): t for t in draft.GetTracks()}
    if draft is not None:
        items.update({force._uid(p): p for fp in draft.GetFootprints() for p in fp.Pads()})
    for q in prefixes:
        cuts = set(q['track_uuids'])
        _need(cuts and cuts <= retired and not retired & set(q['retained_native_keys']),
              'provisional_RC_every_cut_and_fixed_filter_boundary_required')
        if items is not None:
            _need(not cuts & items.keys() and all(u in items and _key(items[u]) == key
                for u, key in q['retained_native_keys'].items()),
                'provisional_RC_draft_cut_or_fixed_filter_changed')
        if restored_requests is not None:
            _need(items is not None and q['pad_uuid'] in items, 'provisional_RC_actual_posed_input_required')
            wanted = copy.deepcopy(q); wanted['points_nm'][0] = list(items[q['pad_uuid']].GetPosition())
            rows = [r for r in restored_requests.values()
                if r.get('source_leaf', {}).get('scope') == SCOPE
                and r['source_leaf'].get('pad_uuid') == q['pad_uuid']]
            _need(len(rows) == 1 and rows[0]['kind'] == 'measurement'
                and rows[0]['net'] == q['net'] and rows[0]['width_nm'] == q['width_nm']
                and rows[0]['a'].get('pad_uuid') == q['pad_uuid']
                and rows[0]['a']['at_nm'] == wanted['points_nm'][0]
                and rows[0]['b']['at_nm'] == q['points_nm'][-1]
                and rows[0]['a']['layers'] == rows[0]['b']['layers'] == [q['layer']]
                and stable(rows[0]['source_leaf']) == stable(wanted),
                'provisional_RC_exact_mandatory_fixed_port_restoration_missing')


def _check_path(board, proof, points, incoming, deadline):
    _need(proof.get('scope') == SCOPE and type(points) is list and 2 <= len(points) <= 17
        and all(type(p) is list and len(p) == 2 and all(type(v) is int
            and abs(v) <= 2000000000 for v in p) for p in points),
          'typed_bounded_Source_RC_prefix_path_required')
    simple._simple_reuse_path([tuple(p) for p in points])
    _need(points[0] == proof['points_nm'][0] and points[-1] == proof['points_nm'][-1]
        and sum(math.dist(a, b) for a, b in zip(points, points[1:])) <= 24000000,
        'Source_RC_prefix_fixed_port_or_path_work_bound_changed')
    for a, b in zip(points, points[1:]):
        dx, dy = abs(a[0]-b[0]), abs(a[1]-b[1])
        _need(max(dx, dy) >= 20000 and (dx == 0 or dy == 0 or dx == dy),
              'Source_RC_prefix_canonical_physical_strokes_required')
    for a, b, c in zip(points, points[1:], points[2:]):
        u = [b[k]-a[k] for k in (0, 1)]; v = [c[k]-b[k] for k in (0, 1)]
        dot = sum(x*y for x, y in zip(u, v)); cross = u[0]*v[1]-u[1]*v[0]
        _need(dot > 0 and abs(cross) <= dot, 'Source_RC_prefix_new_turns_at_most_45_required')
    all_items = {force._uid(p): p for f in board.GetFootprints() for p in f.Pads()}
    all_items.update({force._uid(t): t for t in board.GetTracks()})
    root = all_items.get(proof['pad_uuid']); port = all_items.get(proof['boundary_uuids'][0])
    _need(root is not None and port is not None and list(root.GetPosition()) == points[0]
        and root.GetNetname() == proof['net'] and port.GetNetname() == proof['net'],
        'actual_Source_RC_input_and_retained_filter_port_required')
    _need(all(u in all_items and _key(all_items[u]) == k for u, k in proof['retained_native_keys'].items()),
          'Source_RC_fixed_filter_material_or_terminal_changed')
    _need(not set(proof['track_uuids']) & all_items.keys(), 'Source_RC_prefix_not_completely_retired')
    gap = proof['clearance_nm']; width = proof['width_nm']; face = pcbnew.F_Cu; cache = {}
    areas = [r['shape'] for r in rules.areas(board, 'tracks') if face in r['layers']]
    for t in incoming:
        _remaining(deadline)
        _need(t.GetClass() == 'PCB_TRACK' and t.GetLayer() == face and t.GetWidth() == width
            and bool(t.IsLocked()) == proof['source_locked'] and not t.HasSolderMask()
            and fr._edge_leg_clear(board, t.GetStart(), t.GetEnd(), (width+1)//2+gap)
            and fr._tap_foreign_clear(board, t.GetStart(), t.GetEnd(), width, face, gap,
                {root.GetNetCode()}, foreign_cache=cache)
            and not any(s.Collide(t.GetEffectiveShape(face), 0) for s in areas),
            'Source_RC_prefix_new_process_face_width_or_foreign_clearance_refused')
    incoming_ids = {force._uid(t) for t in incoming}; expected = {proof['pad_uuid'], proof['boundary_uuids'][0]}
    actual = set()
    for uid, peer in all_items.items():
        _remaining(deadline)
        if uid in incoming_ids or peer.GetNetname() != proof['net'] or not peer.IsOnLayer(face):
            continue
        upper = native._contact_union(incoming, peer, True)
        touched = any(peer.GetEffectiveShape(face).Collide(t.GetEffectiveShape(face), 0) for t in incoming)
        if not touched and not upper.OutlineCount():
            continue
        _need(uid in expected, 'Source_RC_prefix_acquired_other_native_contact:'+uid)
        _need(observer._elbow_positive(native._contact_union(incoming, peer, False)),
              'Source_RC_prefix_positive_actual_contact_required')
        actual.add(uid)
    _need(actual == expected and not any(z.GetNetname() == proof['net'] and not z.GetIsRuleArea() for z in board.Zones()),
          'Source_RC_prefix_missing_port_or_new_zone_refused')
    old = _tracks(board, proof['source_points_nm'], width, root.GetNetCode(), proof['source_locked'])
    for outside in (False, True):
        before = native._contact_union(old, port, outside); after = native._contact_union(incoming, port, outside)
        _need(native._same_native(before, after), 'Source_RC_prefix_fixed_contact_aperture_changed')
    _remaining(deadline)
    return dict(complete=True, unchanged_full_native_fixed_port_aperture=True,
        all_fixed_filter_items_and_terminals_unchanged=True, F_only=True, no_new_barrels=True,
        current_authority=False, kelvin_qualified=False, release_authority=False)


def path_clear(board, proof, points, *, timeout_s=10.):
    _need(type(timeout_s) in (int, float) and math.isfinite(timeout_s) and 0 < timeout_s <= 10,
          'bounded_Source_RC_macro_prefix_lease_required')
    deadline = time.monotonic()+timeout_s
    try:
        net = board.GetNetcodeFromNetname(proof['net'])
        return bool(_check_path(board, proof, points,
            _tracks(board, points, proof['width_nm'], net, proof['source_locked']), deadline))
    except ValueError:
        return False


def receive_paths(parent, child, proof, incoming_uuids, *, deadline):
    """Saved compiler-owned scope, actual native contacts, not a producer pass."""
    _remaining(deadline)
    fresh = plan(parent, Path(parent.GetFileName()), board_hint=proof['board_hint'],
        request=proof['identity_request'], timeout_s=_remaining(deadline))
    expected = copy.deepcopy(proof); expected['points_nm'][0] = fresh['points_nm'][0]
    _need(fresh == expected, 'fresh_exact_Source_RC_prefix_receiving_required')
    incoming = [t for t in child.GetTracks() if force._uid(t) in incoming_uuids and t.GetNetname() == proof['net']]
    _need(1 <= len(incoming) <= 16 and all(t.GetClass() == 'PCB_TRACK' for t in incoming),
          'bounded_planar_saved_Source_RC_prefix_material_required')
    points = [list(p) for p in chains._chain(incoming)]
    if points[-1] == proof['points_nm'][0]:
        points.reverse()
    return _check_path(child, proof, points, incoming, deadline)
