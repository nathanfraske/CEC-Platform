"""Shorten one existing closed-monitor Ground leaf with exact saved receiving.

No part/pad motion, cut, new copper, current credit, or release authority. Native
adapter is bounded and independently rederived from the actual Source. Public requests
contain identities and an integer axis only; observed proofs are never grants.
"""
import copy
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time
import uuid

KIND = 'Source_closed_monitor_two_edge_ground_barrel_slide'
ROLE = 'fresh_closed_manufacturer_monitor_and_selected_ground_resistor'
PHASES = ('fresh_Source', 'exact_material_and_reference', 'unfiltered_partitions',
          'all_saved_known_Ground_returns')
FILL = ('filled_polygon', 'fill_segments')


def _need(value, reason):
    if not value:
        raise ValueError(reason)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _same(a, b, reason):
    _need(_json(a) == _json(b), reason)


def _deadline(seconds):
    _need(type(seconds) in (int, float) and math.isfinite(seconds)
          and 0 < seconds <= 9.1, 'explicit_constituent_at_most_9_1_seconds_required')
    return time.monotonic() + seconds


def _tick(deadline):
    _need(time.monotonic() < deadline, 'Ground_barrel_slide_constituent_deadline')


def _left(deadline):
    _tick(deadline)
    return min(9.1, deadline - time.monotonic())


def _axis(value):
    _need(type(value) is list and len(value) == 2
          and all(type(n) is int and abs(n) <= 2000000000 for n in value),
          'exact_integer_nm_axis_required')
    return value


def _request(via_uuid, new_axis_nm):
    _need(type(via_uuid) is str and str(uuid.UUID(via_uuid)) == via_uuid,
          'one_literal_via_UUID_required')
    return dict(via_uuid=via_uuid, new_axis_nm=list(_axis(new_axis_nm)))


def _policy(facts, new_axis_nm):
    """Pure policy over EXHAUSTIVELY observed facts; not a public authority API."""
    new = _axis(new_axis_nm)
    old, corner = [_axis(facts[k]) for k in ('axis_nm', 'corner_nm')]
    vector = [corner[i] - old[i] for i in (0, 1)]
    delta = [new[i] - old[i] for i in (0, 1)]
    square = sum(n * n for n in vector)
    dot = sum(delta[i] * vector[i] for i in (0, 1))
    _need(square > 0 and delta[0] * vector[1] == delta[1] * vector[0]
          and 0 < dot < square and 0 < sum(n*n for n in delta) <= 1000000**2,
          'strict_inside_terminal_centreline_shortening_at_most_1mm_required')
    _need(facts['role_kind'] == ROLE and facts['role_current_authority'] is False,
          'fresh_closed_monitor_lower_role_without_current_authority_required')
    _need(all(type(facts[k]) is int for k in ('edge_count', 'pad_count', 'other_barrel_count',
          'branch_count', 'foreign_zone_contact_count', 'copper_graphic_contact_count'))
          and facts['edge_count'] == 2 and facts['pad_count'] == 1
          and facts['other_barrel_count'] == 0 and facts['branch_count'] == 0
          and facts['foreign_zone_contact_count'] == 0
          and facts['copper_graphic_contact_count'] == 0,
          'exclusive_exact_two_edge_one_Ground_land_Source_leaf_required')
    _need(facts['net'] == 'GND' and facts['all_unlocked'] is True
          and facts['all_ungrouped'] is True and facts['same_face'] is True,
          'unlocked_ungrouped_same_face_literal_GND_leaf_required')
    _need(type(facts['full_width_nm']) is int and facts['full_width_nm'] > 0
          and type(facts['edge_widths_nm']) is list
          and all(type(n) is int for n in facts['edge_widths_nm'])
          and facts['edge_widths_nm'] == [facts['full_width_nm']]*2,
          'constant_exact_full_saved_Ground_class_width_required')
    _need(facts['ordinary_uniform_through'] is True
          and facts['dimensions_meet_class'] is True
          and facts['source_reference_contacts_proved'] is True,
          'ordinary_uniform_through_class_and_both_Source_reference_contacts_required')
    return dict(translation_nm=math.sqrt(sum(n*n for n in delta)),
                original_terminal_length_nm=math.sqrt(square),
                shortened_terminal_length_nm=math.dist(new, corner))


def _runtime():
    import cec_swig_guard
    cec_swig_guard.pin()
    import pcbnew
    import cec_force_current as force
    import cec_component_jumper_metadata as metadata
    import cec_copper_echo as syntax
    return pcbnew, force, metadata, syntax


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _raw(path):
    return Path(path).read_bytes().decode('utf-8')


def _directory(path):
    result = {}
    for item in sorted(path.parent.rglob('*')):
        _need(not item.is_symlink(), 'Source_family_alias_refused')
        if item.is_file():
            _need(len(result) < 256 and item.stat().st_size <= 32*1024*1024,
                  'bounded_complete_Source_family_required')
            result[str(item.relative_to(path.parent))] = _hash(item)
    return result


def _context(paths, hint):
    pcbnew, force, _, _ = _runtime()
    import _pcbnew
    return dict(code=force._code_identity(), operator_sha256=_hash(__file__),
        files={str(p): _hash(p) for p in paths},
        families={str(p): force._family(p, hint) for p in paths},
        directories={str(p): _directory(p) for p in paths},
        native={str(Path(m.__file__).resolve()): _hash(m.__file__) for m in (pcbnew, _pcbnew)},
        environment=sorted((k, v) for k, v in os.environ.items()
                           if k.startswith(('CEC_', 'KICAD')) or k == 'PATH'))


def _live(context, paths, hint, role=None):
    _same(context, _context(paths, hint), 'saved_Source_candidate_code_or_family_changed')
    if role is not None:
        import cec_monitor_divider_ground_return as monitor
        _need(monitor._owner_live(role), 'fresh_canonical_schematic_or_exporter_changed')


def _touch(a, b, faces):
    return any(a.IsOnLayer(l) and b.IsOnLayer(l)
               and a.GetEffectiveShape(l).Collide(b.GetEffectiveShape(l), 0) for l in faces)


def _exclusive_root_contacts(second, terminal, barrel):
    """Both wide leaf edges may touch their ONE root, never another land."""
    _need(type(second) is list and len(second) == 1 and type(terminal) is list
          and type(barrel) is list and not barrel
          and all(type(uid) is str and uid for uid in second + terminal)
          and set(terminal) <= set(second), 'one_exclusive_Source_Ground_land_required')
    return second[0]


def _saved_axis(tokens, tag):
    _need(type(tokens) is list and len(tokens) == 3 and tokens[0][0] == tag
          and all(value == lexeme and not lexeme.startswith('"') for value, lexeme in tokens),
          'exact_unextended_literal_coordinate_required')
    try:
        values = [Decimal(value)*1000000 for value, _ in tokens[1:]]
    except InvalidOperation as exc:
        raise ValueError('literal_native_coordinate_numbers_required') from exc
    _need(all(v.is_finite() and v == v.to_integral_value() for v in values),
          'exact_saved_integer_nm_coordinates_required')
    return _axis([int(v) for v in values])


def _literal_source_axes(source, via_uid, terminal_uid, endpoint, old):
    import cec_source_literal_additions as literal
    inventory, _, _, _ = literal._inventory(_raw(source))
    for uid, tag in ((via_uid, 'at'), (terminal_uid, endpoint)):
        node = inventory[uid][2]; span = literal._child(node, tag)
        _need(span is not None, 'literal_Source_coordinate_required')
        observed = _saved_axis(literal._atoms(node[span[0]+1:span[1]-1]), tag)
        _same(observed, old, 'saved_Source_axis_and_actual_native_axis_disagree')


def _observe(source, hint, request, deadline):
    pcbnew, force, _, _ = _runtime()
    import cec_monitor_divider_ground_return as monitor
    import cec_fr as fr
    import cec_fab_profile as fab
    import cec_ground_return_shortcut as reference
    import cec_ground_mesh_entry as mesh
    import cec_native_via_land_context as native_lands
    board = pcbnew.LoadBoard(str(source))
    _need(board is not None, 'saved_Source_board_required')
    faces = list(board.GetEnabledLayers().CuStack())
    tracks = {force._uid(t): t for t in board.GetTracks()}
    pads = {force._uid(p): p for f in board.GetFootprints() for p in f.Pads()}
    _need(len(tracks) <= 16384 and len(pads) <= 16384, 'bounded_Source_inventory_required')
    via = tracks.get(request['via_uuid'])
    _need(via is not None and via.GetClass() == 'PCB_VIA' and via.GetNetname() == 'GND',
          'actual_saved_Ground_barrel_required')
    first = [t for u, t in tracks.items() if u != request['via_uuid'] and _touch(via, t, faces)]
    _need(len(first) == 1 and first[0].GetClass() == 'PCB_TRACK', 'one_Source_terminal_edge_required')
    terminal = first[0]; old = list(via.GetPosition())
    endpoints = [list(terminal.GetStart()), list(terminal.GetEnd())]
    _need(endpoints.count(old) == 1, 'literal_terminal_endpoint_at_Source_axis_required')
    endpoint = 'start' if endpoints[0] == old else 'end'; corner = endpoints[1 if endpoint == 'start' else 0]
    _literal_source_axes(source, force._uid(via), force._uid(terminal), endpoint, old)
    neighbors = [t for u, t in tracks.items() if u not in (force._uid(via), force._uid(terminal))
                 and _touch(terminal, t, faces)]
    _need(len(neighbors) == 1 and neighbors[0].GetClass() == 'PCB_TRACK',
          'exact_second_Source_edge_required')
    second = neighbors[0]
    _need([list(second.GetStart()), list(second.GetEnd())].count(corner) == 1,
          'literal_two_edge_corner_required')
    roots = [p for p in pads.values() if _touch(second, p, faces)]
    _exclusive_root_contacts([force._uid(p) for p in roots],
        [force._uid(p) for p in pads.values() if _touch(terminal, p, faces)],
        [force._uid(p) for p in pads.values() if _touch(via, p, faces)])
    pad = roots[0]
    _need(list(pad.GetPosition()) in (list(second.GetStart()), list(second.GetEnd()))
          and pad.GetNetname() == 'GND', 'actual_Ground_land_centre_terminal_required')
    ground, role = monitor._source_owner(board, hint, force._uid(pad), deadline)
    _need(force._uid(ground) == force._uid(pad) and role['kind'] == ROLE
          and role['no_new_current_or_operating_rating'] is True, 'fresh_Source_monitor_lower_required')
    owned = [via, terminal, second]; owned_ids = {force._uid(t) for t in owned}
    branches = [u for u, t in tracks.items() if u not in owned_ids
                and any(_touch(a, t, faces) for a in owned)]
    # Also reject an independent conductor touching the ROOT land: a hidden
    # parallel pad exit would not be an exclusive leaf even without edge contact.
    branches += [u for u, t in tracks.items() if u not in owned_ids and _touch(pad, t, faces)]
    foreign = []
    for z in board.Zones():
        _tick(deadline)
        if z.GetIsRuleArea():
            continue
        if z.GetNetname() == 'GND':
            for face in faces:
                if z.IsOnLayer(face) and fr._zone_is_route_reservation(board, z, face):
                    _need(not any(a.IsOnLayer(face) and fr._reserved_zone_obstacle(board, z, face).Collide(
                        a.GetEffectiveShape(face), 0) for a in owned), 'reserved_Ground_Source_contact_refused')
            continue
        for face in faces:
            if not z.IsOnLayer(face):
                continue
            _need(z.IsFilled() and z.HasFilledPolysForLayer(face), 'actual_foreign_Source_fills_required')
            if any(a.IsOnLayer(face) and z.GetFilledPolysList(face).Collide(a.GetEffectiveShape(face), 0)
                   for a in owned):
                foreign.append([force._uid(z), int(face)])
    graphics = list(board.GetDrawings()) + [g for f in board.GetFootprints() for g in f.GraphicalItems()]
    graphics = [g for g in graphics if any(g.IsOnLayer(l) for l in faces)]
    contacts = reference._reference_contacts(board, via)
    # The saved Source may have incomplete annular coverage. Its actual
    # contact to BOTH declared planes remains mandatory; construction and
    # independent receiving require full annular coverage at the NEW axis.
    # Do not claim the inherited Source crescent was already qualified.
    spec = fr._project_netclass_resolver(str(source))('GND'); settings = board.GetDesignSettings()
    full = max(int(settings.m_TrackMinWidth), math.ceil(spec['track_width']*1000000))
    gap = max(200000, int(settings.m_MinClearance), math.ceil(spec['clearance']*1000000))
    dia = int(via.GetWidth(pcbnew.F_Cu)); drill = int(via.GetDrillValue())
    _need(via.Padstack().Mode() == pcbnew.PADSTACK.MODE_NORMAL, 'only_normal_Source_via_padstack_supported')
    native_lands.inspect(board, via, at=via.GetPosition(), maximum_diameter_nm=dia,
                         drill_nm=drill, net_code=via.GetNetCode(), clearance_nm=gap)
    ordinary = fab.board_legal_through_via_geometry(board, dia/1000000, drill/1000000)
    facts = dict(axis_nm=old, corner_nm=corner, role_kind=role['kind'], role_current_authority=False,
        edge_count=2, pad_count=len(roots), other_barrel_count=sum(tracks[u].GetClass() == 'PCB_VIA' for u in set(branches)),
        branch_count=len(set(branches)), foreign_zone_contact_count=len(foreign),
        copper_graphic_contact_count=sum(any(_touch(a, g, faces) for a in owned) for g in graphics),
        net='GND' if all(a.GetNetname() == 'GND' for a in owned) else '',
        all_unlocked=all(not a.IsLocked() for a in owned) and not pad.IsLocked() and not pad.GetParentFootprint().IsLocked(),
        # Only the edited via/terminal and its unchanged second edge must be
        # ungrouped. The ROOT footprint is not moved or edited; its existing
        # group and all memberships are preserved by literal reconstruction.
        all_ungrouped=all(a.GetParentGroup() is None for a in owned),
        same_face=terminal.GetLayer() == second.GetLayer() and pad.IsOnLayer(terminal.GetLayer())
                  and len([l for l in faces if pad.IsOnLayer(l)]) == 1,
        full_width_nm=full, edge_widths_nm=[int(terminal.GetWidth()), int(second.GetWidth())],
        ordinary_uniform_through=via.GetViaType() == pcbnew.VIATYPE_THROUGH and via.TopLayer() == pcbnew.F_Cu
            and via.BottomLayer() == pcbnew.B_Cu and all(via.IsOnLayer(l) and via.GetWidth(l) == dia for l in faces)
            and tuple(ordinary[:2]) == (dia/1000000, drill/1000000),
        dimensions_meet_class=dia >= math.ceil(spec['via_diameter']*1000000)
            and drill >= math.ceil(spec['via_drill']*1000000) and dia > drill > 0,
        source_reference_contacts_proved=True)
    policy = _policy(facts, request['new_axis_nm'])
    _tick(deadline)
    return board, dict(kind=KIND, via_uuid=force._uid(via), terminal_track_uuid=force._uid(terminal),
        terminal_endpoint=endpoint, fixed_corner_nm=corner, second_track_uuid=force._uid(second),
        Ground_pad_uuid=force._uid(pad), facts=facts, policy=policy, Source_role=role,
        source_reference_contacts=contacts, clearance_nm=gap, diameter_nm=dia, drill_nm=drill,
        face=int(terminal.GetLayer()))


def plan(source, *, board_hint, via_uuid, new_axis_nm, timeout_s=9.1):
    deadline = _deadline(timeout_s); source = Path(source).resolve(strict=True)
    _need(type(board_hint) is str and board_hint, 'literal_board_hint_required')
    request = _request(via_uuid, new_axis_nm); before = _context([source], board_hint)
    proof = None
    try:
        _, proof = _observe(source, board_hint, request, deadline)
        _tick(deadline)
    finally:
        _live(before, [source], board_hint, None if proof is None else proof['Source_role'])
        _tick(deadline)
    return dict(schema=1, kind=KIND, source=str(source), board_hint=board_hint, request=request,
                context=before, proof=proof, current_authority=False, release_authority=False,
                independent_saved_native_receive_required=True)


def _fresh(source, proposal, deadline):
    _need(type(proposal) is dict and proposal.get('kind') == KIND, 'exact_operator_proposal_required')
    result = plan(source, board_hint=proposal['board_hint'], **proposal['request'], timeout_s=_left(deadline))
    _same(result, proposal, 'fresh_Source_role_leaf_request_and_code_proof_must_match')
    return result


def _coordinate(axis, tag):
    return '(' + tag + ' ' + ' '.join(format(n/1000000, '.6f') for n in axis) + ')'


def _project(text, proposal, filled_text=None):
    """Literal edits ONLY: two exact coordinate subtrees and optional generated fills."""
    import cec_source_literal_additions as literal
    from cec_source_retaining_ses_import import children, kind
    inventory, _, _, _ = literal._inventory(text); changes = []
    proof = proposal['proof']; axis = proposal['request']['new_axis_nm']
    for uid, tag in ((proof['via_uuid'], 'at'), (proof['terminal_track_uuid'], proof['terminal_endpoint'])):
        start, _, node = inventory[uid]; part = literal._child(node, tag)
        _need(part is not None, 'one_literal_owned_coordinate_required')
        _same(_saved_axis(literal._atoms(node[part[0]+1:part[1]-1]), tag), proof['facts']['axis_nm'],
              'literal_projection_Source_coordinate_changed')
        changes.append((start+part[0], start+part[1], _coordinate(axis, tag)))
    if filled_text is not None:
        fresh, _, _, _ = literal._inventory(filled_text)
        for uid in proposal['ordinary_Ground_zone_uuids']:
            start, end, node = inventory[uid]; replacement = fresh[uid][2]
            old_parts = [p for p in children(node) if kind(node[p[0]:p[1]]) in FILL]
            new_parts = [replacement[a:b] for a, b in children(replacement)
                         if kind(replacement[a:b]) in FILL]
            for a, b in reversed(old_parts):
                node = node[:a] + node[b:]
            node = node[:-1] + ''.join('\n' + p for p in new_parts) + ')'
            changes.append((start, end, node))
    for start, end, value in sorted(changes, reverse=True):
        text = text[:start] + value + text[end:]
    return text


def _projection(text, proposal):
    _, _, metadata, syntax = _runtime()
    tree = metadata._parse(text); proof = proposal['proof']
    for node in tree[1:]:
        if type(node) is not list:
            continue
        ids = metadata._children(node, 'uuid')
        uid = metadata._text(ids[0][1]) if len(ids) == 1 else None
        excluded = set(FILL) if uid in proposal['ordinary_Ground_zone_uuids'] else set()
        if uid == proof['via_uuid']:
            excluded.add('at')
        if uid == proof['terminal_track_uuid']:
            excluded.add(proof['terminal_endpoint'])
        node[:] = [p for p in node if not (type(p) is list and p and p[0] in excluded)]
    return syntax._freeze(tree)


def _ordinary(board):
    _, force, _, _ = _runtime()
    import cec_fr as fr
    return sorted(force._uid(z) for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname() == 'GND'
                  and not any(fr._zone_is_route_reservation(board, z, l) for l in z.GetLayerSet().CuStack()))


def _expected(source, proposal, deadline, work):
    """Fresh exact native construction; no arbitrary normalized writer is used."""
    pcbnew, force, metadata, syntax = _runtime()
    import cec_field_coupling as field
    import cec_fr as fr
    import cec_zone_fill as fill
    import cec_ground_return_shortcut as reference
    import cec_ground_mesh_entry as mesh
    # Load the ACTUAL Source family/project. Changing a temporary board's file
    # name does not install Source design settings, netclasses or project.
    before = _raw(source); board = pcbnew.LoadBoard(str(source))
    _need(_ordinary(board) == proposal['ordinary_Ground_zone_uuids'], 'exact_ordinary_Ground_fill_inventory_required')
    tracks = {force._uid(t): t for t in board.GetTracks()}; p = proposal['proof']; via = tracks[p['via_uuid']]
    terminal = tracks[p['terminal_track_uuid']]
    a = pcbnew.VECTOR2I(*proposal['request']['new_axis_nm']); via.SetPosition(a)
    (terminal.SetStart if p['terminal_endpoint'] == 'start' else terminal.SetEnd)(a)
    _need(fr._edge_leg_clear(board, a, a, p['diameter_nm']/2 + p['clearance_nm'])
          and fr._via_spot_clear(board, a, p['diameter_nm'], p['clearance_nm'], {via.GetNetCode()},
              drill_nm=p['drill_nm'], net_code=via.GetNetCode(), existing_via_uuid=p['via_uuid'],
              native_padstack_via=via),
          'all_face_ordinary_barrel_pad_hole_edge_clearance_required')
    _need(fr._edge_leg_clear(board, terminal.GetStart(), terminal.GetEnd(),
                            terminal.GetWidth()/2 + p['clearance_nm'])
          and fr._tap_foreign_clear(board, terminal.GetStart(), terminal.GetEnd(), terminal.GetWidth(),
                                   terminal.GetLayer(), p['clearance_nm'], {via.GetNetCode()}),
          'shortened_full_width_edge_clearance_required')
    # The generic via probe intentionally excludes ordinary zone fills. This
    # separate actual-fill check refuses inherited foreign-plane antipads too.
    resolver = fr._foreign_clearance_resolver(board)
    for zone in board.Zones():
        if zone.GetIsRuleArea():
            continue
        if zone.GetNetname() == 'GND':
            for face in board.GetEnabledLayers().CuStack():
                if zone.IsOnLayer(face) and fr._zone_is_route_reservation(board, zone, face):
                    obstacle = fr._reserved_zone_obstacle(board, zone, face)
                    _need(not obstacle.Collide(via.GetEffectiveShape(face), p['clearance_nm'])
                          and not (terminal.IsOnLayer(face) and obstacle.Collide(
                              terminal.GetEffectiveShape(face), p['clearance_nm'])),
                          'no_reserved_Ground_window_or_shared_trunk_authority')
            continue
        for face in board.GetEnabledLayers().CuStack():
            _tick(deadline)
            if zone.IsOnLayer(face):
                _need(zone.IsFilled() and zone.HasFilledPolysForLayer(face), 'saved_foreign_plane_fills_required')
                gap = max(p['clearance_nm'], int(zone.GetLocalClearance()), resolver(zone, face))
                _need(not zone.GetFilledPolysList(face).Collide(via.GetEffectiveShape(face), gap),
                      'immutable_foreign_fill_barrel_clearance_required')
                if terminal.IsOnLayer(face):
                    _need(not zone.GetFilledPolysList(face).Collide(terminal.GetEffectiveShape(face), gap),
                          'immutable_foreign_fill_terminal_clearance_required')
    selected = pcbnew.ZONES()
    for zone in board.Zones():
        if force._uid(zone) in proposal['ordinary_Ground_zone_uuids']:
            zone.UnFill(); selected.append(zone)
    if selected.size():
        result = fill.compile_selected(board, selected, timeout_s=_left(deadline), initialize_selected=True)
        _need(result.get('stable') is True and result.get('compiled_zone_count') == selected.size(),
              'ordinary_Ground_only_fill_required')
    saved = Path(work)/'native-expected.kicad_pcb'
    field._save_field_snapshot(board, saved)
    native = _raw(saved)
    _need(_projection(before, proposal) == _projection(native, proposal),
          'native_construction_changed_unowned_Source_AST')
    exact = _project(before, proposal, native)
    target = Path(work)/'exact-literal.kicad_pcb'; target.write_bytes(exact.encode('utf-8'))
    final = pcbnew.LoadBoard(str(target))
    second = Path(work)/'strict-reload.kicad_pcb'; field._save_field_snapshot(final, second)
    _need(syntax._freeze(metadata._parse(_raw(second))) == syntax._freeze(metadata._parse(native)),
          'literal_projection_native_material_or_second_save_changed')
    # Reference/process checks use the unchanged actual Source project context,
    # NOT the temporary reload's possibly default project/design settings.
    contacts = reference._reference_contacts(board, via)
    mesh._reference_envelopes(board, via, contacts, deadline)
    _need({c[1] for c in contacts} == {c[1] for c in p['source_reference_contacts']},
          'both_declared_Ground_reference_planes_required')
    _tick(deadline)
    return exact


def construct(source, directory, proposal, *, timeout_s=9.1):
    """ONE bounded construction constituent, not independent receiving."""
    deadline = _deadline(timeout_s); source = Path(source).resolve(strict=True)
    directory = Path(directory).resolve(); _need(not directory.exists(), 'new_private_directory_required')
    fresh = _fresh(source, proposal, deadline); pcbnew, force, _, _ = _runtime()
    try:
        board = pcbnew.LoadBoard(str(source)); fresh['ordinary_Ground_zone_uuids'] = _ordinary(board)
        with tempfile.TemporaryDirectory(prefix='cec-ground-slide-') as work:
            text = _expected(source, fresh, deadline, work)
        _live(fresh['context'], [source], fresh['board_hint'], fresh['proof']['Source_role'])
        _tick(deadline); target = force._copy_family(source, directory)
        target.write_bytes(text.encode('utf-8'))
    finally:
        _live(fresh['context'], [source], fresh['board_hint'], fresh['proof']['Source_role'])
        _tick(deadline)
    return dict(candidate=str(target), candidate_sha256=_hash(target), construction_only=True,
                independent_receive_required=True, current_authority=False, release_authority=False)


def _material(source, candidate, proposal, deadline):
    pcbnew, force, _, _ = _runtime()
    _need(force._sidecars(source) == force._sidecars(candidate), 'all_saved_family_sidecars_must_be_exact')
    board = pcbnew.LoadBoard(str(source)); proposal = copy.deepcopy(proposal)
    proposal['ordinary_Ground_zone_uuids'] = _ordinary(board)
    with tempfile.TemporaryDirectory(prefix='cec-ground-slide-receive-') as work:
        exact = _expected(source, proposal, deadline, work)
    _need(candidate.read_bytes() == exact.encode('utf-8'), 'exact_fresh_reconstructed_literal_candidate_required')
    _tick(deadline)
    return dict(exact_literal_two_coordinates_and_ordinary_Ground_generated_fills_only=True,
                foreign_fills_and_every_other_Source_AST_item_exact=True,
                full_annular_both_Ground_planes_and_strict_native_reload=True)


def _partitions(source, candidate, deadline):
    pcbnew, _, _, _ = _runtime()
    import cec_native_partition_pair as pair
    result = pair.compare(pcbnew.LoadBoard(str(source)), pcbnew.LoadBoard(str(candidate)), timeout_s=_left(deadline))
    _need(result.get('available') is True and result.get('preserved') is True,
          'all_native_partition_keys_without_filter_must_be_preserved')
    _tick(deadline); return result


def _returns(source, candidate, deadline):
    pcbnew, _, _, _ = _runtime()
    import cec_ground_return_preservation as returns
    result = returns.receive(pcbnew.LoadBoard(str(source)), pcbnew.LoadBoard(str(candidate)), timeout_s=_left(deadline))
    _need(result.get('ok') is True and result.get('complete') is True, 'every_saved_known_Ground_return_required')
    _tick(deadline); return result


def receive_phase(source, candidate, proposal, *, phase, timeout_s=9.1):
    """One externally schedulable phase; NEVER complete/admitted authority.

    Only fresh_Source re-canonicalizes. Other phases verify immutable Source,
    code and canonical-file bindings; their partial result has meaning ONLY
    beside a successful fresh_Source for the exact same proposal/context.
    No earlier worker receipt is an input and no result is a new permission.
    """
    deadline = _deadline(timeout_s)
    _need(type(phase) is str and phase in PHASES, 'one_named_receiving_phase_required')
    source, candidate = [Path(p).resolve(strict=True) for p in (source, candidate)]
    _need(source != candidate and not source.samefile(candidate), 'distinct_saved_candidate_required')
    hint = proposal['board_hint']; context = _context([source, candidate], hint)
    role = None
    try:
        _need(proposal.get('kind') == KIND and proposal.get('source') == str(source), 'exact_Source_proposal_required')
        role = proposal['proof']['Source_role']
        _live(proposal['context'], [source], hint, role)
        if phase == PHASES[0]:
            fresh = _fresh(source, proposal, deadline); role = fresh['proof']['Source_role']; evidence = True
        else:
            role = proposal['proof']['Source_role']
            operation = dict(zip(PHASES[1:], (_material, _partitions, _returns)))[phase]
            evidence = operation(source, candidate, proposal, deadline) if phase == PHASES[1] else operation(source, candidate, deadline)
        _tick(deadline)
    finally:
        _live(context, [source, candidate], hint, role)
        _tick(deadline)
    return dict(phase=phase, phase_complete=True, complete=False, ok=True, context=context,
        proposal_sha256=hashlib.sha256(_json(proposal).encode()).hexdigest(),
        Source_role=role, evidence=evidence, constituent_limit_s=timeout_s,
        requires_all_four_identically_bound_phases=True, current_authority=False,
        release_authority=False, routing_admitted=False)


def receive(source, candidate, proposal, *, constituent_timeout_s=9.1):
    """Explicit four-phase composite. Observe public receive_phase boundaries.

    This does not accept externally supplied receipts. Each phase executes
    here; all exact context/proposal/role bindings must agree. An external
    supervisor may instead call receive_phase once per process and preserve
    four partial proofs, but those are NOT a complete receiver verdict.
    """
    _deadline(constituent_timeout_s); started = time.monotonic(); results = {}
    for phase in PHASES:
        results[phase] = receive_phase(source, candidate, proposal, phase=phase, timeout_s=constituent_timeout_s)
        if phase != PHASES[0]:
            for key in ('context', 'proposal_sha256', 'Source_role'):
                _same(results[PHASES[0]][key], results[phase][key], 'receiving_phase_binding_changed:' + key)
    return dict(ok=True, complete=True, scope=KIND, source_sha256=_hash(source), candidate_sha256=_hash(candidate),
        phase_results=results, named_constituent_limit_s=constituent_timeout_s,
        declared_maximum_composite_s=len(PHASES)*constituent_timeout_s, elapsed_s=time.monotonic()-started,
        current_authority=False, release_authority=False, routing_admitted=False,
        native_DRC_current_craft_field_and_priority_receiving_still_required=True)
